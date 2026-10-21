import json

import pytest

from src.agents import ReviewAgents
from src.code_index import Chunk, CodeIndex, numbered
from src.schemas import ReviewOptions
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
