"""A failing generated assertion alone must never become a confirmed defect."""

import json

import pytest

from src.agents import ReviewAgents
from src.code_index import CodeIndex
from src.reproduction import (
    EvidenceEngine,
    execution_verdict,
    replay_evidence,
    validate_plan,
)
from src.schemas import Finding, ReproductionPlan, ReviewOptions
from tests.test_review import FakeLLM, candidate


SOURCE = 'def average(values):\n    """Return 0.0 when values is empty."""\n    return sum(values) / len(values)\n'
TEST = "import unittest\nfrom a import average\nclass ReproductionTest(unittest.TestCase):\n    def test_reproduction(self):\n        self.assertEqual(average([]), 0.0)\n"


def plan():
    return ReproductionPlan(
        applicable=True,
        reason="文档承诺空输入返回零。",
        contract={
            "path": "a.py",
            "start": 2,
            "end": 2,
            "quote": "Return 0.0 when values is empty.",
            "kind": "documented_behavior",
            "rationale": "文档明确承诺空列表返回0.0，此输入符合接口约定。",
        },
        test_code=TEST,
        expected_behavior="average([]) should return 0.0 without an exception.",
    )


def finding():
    return Finding(
        **dict(candidate(line=3)),
        id="evidence-test",
        source="llm",
        snippet="3: return sum(values) / len(values)",
    )


def attempt(kind="failure_observed"):
    observation = {
        "test": "generated_reproduction.ReproductionTest.test_reproduction",
        "outcome": "error",
        "exception_type": "ZeroDivisionError",
        "message": "division by zero",
        "traceback": "/work/a.py:3",
    }
    result = {
        "tests_run": 1,
        "skipped": 0,
        "load_error": None,
        "failures": 0,
        "errors": 1,
        "observations": [observation],
        "target_lines": [3],
        "target_calls": [["average", 1]],
        "python": "3.13.0",
    }
    if kind == "not_reproduced":
        result.update(errors=0, observations=[])
    if kind == "environment_failed":
        observation["exception_type"] = "ModuleNotFoundError"
    if kind == "unrelated_failure":
        result.update(target_lines=[], target_calls=[])
    return {
        "execution": result,
        "image_id": "sha256:test",
        "log": "actual test output",
        "log_sha256": "test",
    }


class Executor:
    def __init__(self, kind="failure_observed"):
        self.kind, self.calls = kind, 0

    def inspect(self):
        return {"Id": "sha256:test"}

    def execute(self, files, target, code):
        self.calls += 1
        assert files["a.py"] == SOURCE and code == TEST
        return attempt(self.kind)


def engine(accepted=True, kind="failure_observed"):
    llm = FakeLLM(
        [
            plan().model_dump_json(),
            json.dumps(
                {
                    "accepted": accepted,
                    "reason": "已核对文档空输入约定和实际ZeroDivisionError，测试调用原函数。",
                }
            ),
        ]
    )
    index = CodeIndex({"a.py": SOURCE})
    executor = Executor(kind)
    return (
        EvidenceEngine(
            index, ReviewAgents(index, llm), ReviewOptions(mode="evidence"), executor
        ),
        executor,
        llm,
    )


def test_real_failure_requires_two_runs_and_contract_audit():
    validator, executor, llm = engine()
    item = finding()
    validator.validate(item)
    assert item.status == "reproduced" and executor.calls == 2
    assert len(llm.calls) == 2
    assert "evidence/evidence-test/test_reproduction.py" in validator.artifacts
    assert item.reproduction["execution_snapshot_sha256"]


def test_failure_with_unjustified_contract_stays_pending():
    validator, executor, _ = engine(accepted=False)
    item = finding()
    validator.validate(item)
    assert executor.calls == 2 and item.status == "pending_evidence"
    assert item.reproduction["status"] == "contract_unconfirmed"


@pytest.mark.parametrize(
    "kind", ["not_reproduced", "environment_failed", "unrelated_failure"]
)
def test_pass_import_failure_or_wrong_target_cannot_confirm(kind):
    validator, executor, llm = engine(kind=kind)
    item = finding()
    validator.validate(item)
    assert item.status == "pending_evidence" and executor.calls == 1
    assert item.reproduction["status"] == kind and len(llm.calls) == 1


def test_quote_and_unconditional_failure_are_checked_before_execution():
    index = CodeIndex({"a.py": SOURCE})
    value = plan()
    value.contract.quote = "invented promise"
    with pytest.raises(ValueError, match="原文"):
        validate_plan(value, index)
    value = plan()
    value.test_code = TEST.replace(
        "self.assertEqual(average([]), 0.0)", 'self.fail("fake")'
    )
    with pytest.raises(ValueError):
        validate_plan(value, index)


def test_generated_code_cannot_override_harness_or_install_packages():
    index = CodeIndex({"a.py": SOURCE})
    for code in [
        TEST.replace("import unittest", "import subprocess\nimport unittest"),
        TEST.replace("def test_reproduction(self):", "def run(self):"),
        TEST.replace(
            "self.assertEqual(average([]), 0.0)", 'raise AssertionError("fake")'
        ),
    ]:
        value = plan()
        value.test_code = code
        with pytest.raises(ValueError):
            validate_plan(value, index)


def test_failure_counters_and_observations_must_agree():
    result = attempt()
    result["execution"]["errors"] = 0
    assert (
        execution_verdict(result, finding(), {"a.py": SOURCE}) == "environment_failed"
    )


def test_budget_before_audit_cannot_confirm():
    validator, executor, llm = engine()
    from src.agents import BudgetExceeded

    llm.answers = iter([plan().model_dump_json(), BudgetExceeded("test budget")])
    item = finding()
    validator.validate(item)
    assert executor.calls == 2 and item.status == "pending_evidence"
    assert item.reproduction["status"] == "budget_exhausted"


def test_replay_refuses_changed_source_before_launching_container(tmp_path):
    validator, _, _ = engine()
    item = finding()
    validator.validate(item)
    path = tmp_path / "evidence.json"
    path.write_text(validator.artifacts[item.reproduction["artifact"]])
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text(SOURCE + "# edited\n")
    with pytest.raises(ValueError, match="不一致"):
        replay_evidence(path, repo, tmp_path / "output")


def test_text_search_finds_alias_assignments_and_documents():
    index = CodeIndex({"a.py": "compat_chr = chr\n"}, {"README.md": "Return a string."})
    assert json.loads(index.search_text("compat_chr"))["matches"][0]["line"] == 1
    assert json.loads(index.read("README.md"))["code"] == "1: Return a string."


def test_invalid_plan_is_preserved_and_corrected_once_with_metered_calls():
    bad = plan()
    bad.contract.quote = "invented contract"
    llm = FakeLLM(
        [
            bad.model_dump_json(),
            plan().model_dump_json(),
            json.dumps(
                {
                    "accepted": True,
                    "reason": "原文明确规定空输入返回零，两个执行记录均复现同一除零错误。",
                }
            ),
        ]
    )
    executor = Executor()
    index = CodeIndex({"a.py": SOURCE})
    validator = EvidenceEngine(
        index, ReviewAgents(index, llm), ReviewOptions(mode="evidence"), executor
    )
    item = finding()
    validator.validate(item)
    assert item.status == "reproduced" and len(llm.calls) == 3
    assert len(item.reproduction["generation_attempts"]) == 2
    assert "validation_error" in item.reproduction["generation_attempts"][0]
