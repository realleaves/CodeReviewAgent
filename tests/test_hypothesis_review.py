import json

import pytest

from src.agents import ReviewAgents
from src.code_index import Chunk, CodeIndex, numbered
from src.schemas import Hypothesis, ReviewOptions
from tests.test_review import FakeLLM, candidate


SOURCE = "def f(x):\n    return 1 // x\n"


def hypothesis_answer():
    return json.dumps(
        {
            "checked": ["读取 f 的实现", "检查 x=0 和负数输入"],
            "hypotheses": [
                {
                    "claim": "x=0 时发生除零",
                    "expected_behavior": "f(0) 应返回明确错误，而不是未捕获的 ZeroDivisionError。",
                    "counterexample": "调用 f(0)。",
                    "contract": "函数没有声明零输入为支持用法。",
                }
            ],
            "findings": [candidate("a.py", 2)],
        }
    )


def chunk():
    return Chunk("a.py", 1, 2, numbered(SOURCE, 1, 2))


def test_hypothesis_review_parses_findings_and_preserves_reasoning_trace():
    index = CodeIndex({"a.py": SOURCE})
    llm = FakeLLM([hypothesis_answer()])
    agents = ReviewAgents(index, llm, review_strategy="hypothesis")
    findings = agents.review(chunk(), [], evidence=True)
    assert len(findings) == 1
    trace = next(t for t in agents.trace if t["stage"] == "hypothesis_review")
    assert trace["checked"] == ["读取 f 的实现", "检查 x=0 和负数输入"]
    assert trace["hypotheses"][0]["claim"] == "x=0 时发生除零"
    assert any(
        t["stage"] == "review" and t.get("strategy") == "hypothesis"
        for t in agents.trace
    )
    assert llm.calls[0]["stage"] == "review_hypothesis"


def test_default_review_strategy_still_uses_the_baseline_schema():
    index = CodeIndex({"a.py": SOURCE})
    llm = FakeLLM([json.dumps({"findings": [candidate("a.py", 2)]})])
    agents = ReviewAgents(index, llm)
    findings = agents.review(chunk(), [], evidence=True)
    assert len(findings) == 1
    assert not any(t["stage"] == "hypothesis_review" for t in agents.trace)
    assert any(
        t["stage"] == "review" and t.get("strategy") == "baseline" for t in agents.trace
    )
    assert ReviewOptions().review_strategy == "baseline"


def test_unknown_review_strategy_is_rejected():
    index = CodeIndex({"a.py": SOURCE})
    with pytest.raises(ValueError, match="发现策略"):
        ReviewAgents(index, FakeLLM([]), review_strategy="unknown")


def tool_call():
    return "[TOOL_CALL:read_code:path=a.py,start=1,end=2]"


def test_hypothesis_tools_retries_once_and_keeps_findings_after_a_real_read():
    index = CodeIndex({"a.py": SOURCE})
    llm = FakeLLM(
        [
            hypothesis_answer(),
            tool_call(),
            hypothesis_answer(),
        ]
    )
    agents = ReviewAgents(index, llm, review_strategy="hypothesis_tools")
    findings = agents.review(chunk(), [], evidence=True)
    assert len(findings) == 1
    trace = next(t for t in agents.trace if t["stage"] == "hypothesis_review")
    assert trace["tool_retry"] is True
    assert trace["tool_evidence"] is True
    assert trace["tool_reads_after"] > trace["tool_reads_before"]
    assert index.reads
    assert llm.calls[0]["stage"] == "review_hypothesis"
    assert llm.calls[1]["stage"] == "review_hypothesis_retry"


def test_hypothesis_tools_drops_findings_when_retry_still_has_no_read():
    index = CodeIndex({"a.py": SOURCE})
    llm = FakeLLM([hypothesis_answer(), hypothesis_answer()])
    agents = ReviewAgents(index, llm, review_strategy="hypothesis_tools")
    findings = agents.review(chunk(), [], evidence=True)
    assert findings == []
    trace = next(t for t in agents.trace if t["stage"] == "hypothesis_review")
    assert trace["tool_retry"] is True
    assert trace["tool_evidence"] is False
    assert trace["findings_dropped"] == "no_tool_evidence"
    assert not index.reads


def test_hypothesis_tools_does_not_retry_when_the_first_call_reads():
    index = CodeIndex({"a.py": SOURCE})
    llm = FakeLLM([tool_call(), hypothesis_answer()])
    agents = ReviewAgents(index, llm, review_strategy="hypothesis_tools")
    findings = agents.review(chunk(), [], evidence=True)
    assert len(findings) == 1
    trace = next(t for t in agents.trace if t["stage"] == "hypothesis_review")
    assert trace["tool_retry"] is False
    assert trace["tool_evidence"] is True
    assert index.reads


def test_short_expected_behavior_is_accepted():
    hypothesis = Hypothesis(
        claim="空输入会崩溃",
        expected_behavior="应报错",
        counterexample="f()",
        contract="语言规则",
    )
    assert hypothesis.expected_behavior == "应报错"
