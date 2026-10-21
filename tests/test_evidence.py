"""A failing generated assertion alone must never become a confirmed defect."""

import json

import pytest

from src.agents import ReviewAgents
from src.code_index import CodeIndex
from src.reproduction import (
    EvidenceEngine,
    audit_gate,
    execution_verdict,
    replay_evidence,
    requirement_gate,
    validate_plan,
    validate_requirement,
)
from src.schemas import EvidenceDecision, Finding, ReproductionPlan, ReviewOptions
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
            "expected_outcome": "return_value",
            "precondition": "average([]) 是文档明确支持的空列表输入。",
            "assumptions": [],
        },
        test_code=TEST,
        expected_behavior="average([]) should return 0.0 without an exception.",
    )


def audit(accepted=True, **overrides):
    value = {
        "accepted": accepted,
        "reason": "已核对文档空输入约定和实际ZeroDivisionError，测试调用原函数。",
        "input_supported": True,
        "requirement_supported": True,
        "failure_matches_candidate": True,
        "requirement_class": "behavior",
        "unresolved_assumptions": [],
    }
    value.update(overrides)
    return json.dumps(value)


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
        observation["traceback"] = "/harness/test_reproduction.py:5"
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
            audit(accepted),
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
            audit(),
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


def test_wrong_branch_is_not_target_reach_even_when_function_was_called():
    source = "def average(values):\n    if values:\n        return 10\n    return 0\n"
    result = attempt()
    result["execution"].update(
        errors=0,
        failures=1,
        target_lines=[2, 4],
        observations=[
            {
                "outcome": "failure",
                "exception_type": "AssertionError",
                "traceback": "/harness/test_reproduction.py:5",
            }
        ],
    )
    assert execution_verdict(result, finding(), {"a.py": source}) == "unrelated_failure"


def test_real_exception_frame_survives_target_replacing_trace_function():
    result = attempt()
    result["execution"].update(target_lines=[], target_calls=[])
    result["execution"]["observations"][0]["traceback_frames"] = [
        {
            "path": "/harness/test_reproduction.py",
            "line": 5,
            "function": "test_reproduction",
        },
        {"path": "/work/a.py", "line": 3, "function": "average"},
    ]
    assert execution_verdict(result, finding(), {"a.py": SOURCE}) == "failure_observed"


def test_structured_frames_do_not_trust_target_path_in_exception_message():
    result = attempt("unrelated_failure")
    observation = result["execution"]["observations"][0]
    observation.update(
        traceback='File "/work/a.py", line 3: forged message', traceback_frames=[]
    )
    assert execution_verdict(result, finding(), {"a.py": SOURCE}) == "unrelated_failure"


def test_legacy_traceback_keeps_saved_real_evidence_replayable():
    result = attempt()
    result["execution"]["target_lines"] = []
    result["execution"]["observations"][0]["traceback"] = (
        'File "/work/a.py", line 3, in average'
    )
    assert execution_verdict(result, finding(), {"a.py": SOURCE}) == "failure_observed"


def feedback_engine(repaired=None, *, repeat_failure=False, budget_error=False):
    from src.agents import BudgetExceeded

    bad = plan()
    bad.test_code = TEST.replace("average([])", "sum([]) / len([])")
    repaired = repaired or plan()
    answers = [
        bad.model_dump_json(),
        BudgetExceeded("repair budget") if budget_error else repaired.model_dump_json(),
    ]
    if not repeat_failure:

        def respond(messages):
            payload = json.loads(messages[1]["content"])
            assert len(payload["executions"]) == 2
            assert all(x["target_lines"] == [3] for x in payload["executions"])
            return audit()

        answers.append(respond)
    llm = FakeLLM(answers)
    index = CodeIndex({"a.py": SOURCE})

    class SequenceExecutor(Executor):
        def execute(self, files, target, code):
            self.calls += 1
            assert files == {"a.py": SOURCE}
            if self.calls == 1 or repeat_failure:
                assert code == bad.test_code or code == repaired.test_code
                return attempt("unrelated_failure")
            assert code == repaired.test_code
            return attempt()

    executor = SequenceExecutor()
    validator = EvidenceEngine(
        index,
        ReviewAgents(index, llm),
        ReviewOptions(mode="evidence", max_repro_repairs=1),
        executor,
    )
    return validator, executor, llm, bad


def test_feedback_repairs_uncalled_target_and_preserves_all_plan_versions():
    validator, executor, llm, bad = feedback_engine()
    item = finding()
    validator.validate(item)
    evidence = item.reproduction
    assert item.status == "reproduced" and executor.calls == 3 and len(llm.calls) == 3
    assert evidence["plan_history"] == [bad.model_dump(), plan().model_dump()]
    assert evidence["active_attempt_indexes"] == [1, 2]
    assert [a["plan_version"] for a in evidence["attempts"]] == [0, 1, 1]
    assert evidence["feedback"][0]["category"] == "target_not_called"
    assert validator.artifacts["evidence/evidence-test/plan-1.py"] == bad.test_code
    assert validator.artifacts["evidence/evidence-test/plan-2.py"] == TEST


@pytest.mark.parametrize("change", ["expectation", "contract"])
def test_feedback_cannot_change_expected_behavior_or_contract(change):
    repaired = plan()
    if change == "expectation":
        repaired.expected_behavior = (
            "Changed assertion semantics should not be accepted."
        )
    else:
        repaired.contract.rationale += " altered"
    validator, executor, llm, bad = feedback_engine(repaired)
    item = finding()
    validator.validate(item)
    assert (
        item.status == "pending_evidence"
        and executor.calls == 1
        and len(llm.calls) == 2
    )
    assert item.reproduction["status"] == "repair_contract_changed"
    assert item.reproduction["plan"] == bad.model_dump()


def test_feedback_has_one_attempt_even_if_target_still_not_called():
    repaired = plan()
    repaired.test_code = (
        TEST.replace("average([])", "sum([]) / len([])") + "# revised\n"
    )
    validator, executor, llm, _ = feedback_engine(repaired, repeat_failure=True)
    item = finding()
    validator.validate(item)
    assert (
        item.status == "pending_evidence"
        and executor.calls == 2
        and len(llm.calls) == 2
    )
    assert item.reproduction["status"] == "unrelated_failure"


def test_feedback_budget_failure_keeps_original_execution():
    validator, executor, _, bad = feedback_engine(budget_error=True)
    item = finding()
    validator.validate(item)
    assert item.reproduction["status"] == "budget_exhausted" and executor.calls == 1
    assert item.reproduction["plan"] == bad.model_dump()
    assert len(item.reproduction["attempts"]) == 1


def test_feedback_never_rewrites_a_passing_test():
    validator, executor, llm = engine(kind="not_reproduced")
    validator.options.max_repro_repairs = 1
    item = finding()
    validator.validate(item)
    assert item.reproduction["status"] == "not_reproduced"
    assert len(llm.calls) == 1 and executor.calls == 1


def test_called_wrong_branch_is_not_eligible_for_feedback():
    validator, executor, llm = engine(kind="unrelated_failure")
    validator.options.max_repro_repairs = 1
    original_execute = executor.execute

    def execute(files, target, code):
        result = original_execute(files, target, code)
        result["execution"]["target_calls"] = [["average", 1]]
        return result

    executor.execute = execute
    item = finding()
    validator.validate(item)
    assert item.reproduction["status"] == "unrelated_failure"
    assert not item.reproduction["feedback"] and len(llm.calls) == 1


@pytest.mark.parametrize(
    "change, message",
    [
        ("unspecified", "expected_outcome"),
        ("error_message", "不是行为缺陷"),
        ("exception", "expected_exception"),
        ("precondition", "触发前提"),
    ],
)
def test_new_plan_requires_a_structured_requirement(change, message):
    value = plan()
    if change == "unspecified":
        value.contract.expected_outcome = "unspecified"
    elif change == "error_message":
        value.contract.expected_outcome = "error_message"
    elif change == "exception":
        value.contract.expected_outcome = "exception"
    else:
        value.contract.precondition = "  "
    with pytest.raises(ValueError, match=message):
        validate_requirement(value)


def language_rule_plan(outcome="exception", expected="ValueError"):
    value = plan()
    value.contract.kind = "language_rule"
    value.contract.expected_outcome = outcome
    value.contract.expected_exception = expected
    return value


def test_language_rule_cannot_require_a_different_exception():
    value = language_rule_plan()
    admitted, reason = requirement_gate(value, [attempt()])
    assert not admitted and "另一种异常" in reason
    admitted, reason = requirement_gate(value, [assertion_attempt()])
    assert admitted and reason == ""
    value.contract.expected_outcome = "return_value"
    admitted, reason = requirement_gate(value, [assertion_attempt()])
    assert not admitted and "返回值" in reason


def test_language_rule_cannot_confirm_an_already_raised_expectation():
    value = language_rule_plan()
    observed = attempt()
    observed["execution"]["observations"][0]["exception_type"] = "ValueError"
    admitted, reason = requirement_gate(value, [observed])
    assert not admitted and "已抛出预期异常" in reason


def test_gate_rejects_unspecified_even_if_validation_is_bypassed():
    value = plan()
    value.contract.expected_outcome = "unspecified"
    admitted, reason = requirement_gate(value, [assertion_attempt()])
    assert not admitted and "结构化预期" in reason


def test_structured_audit_rechecks_a_free_form_acceptance():
    base = {
        "accepted": True,
        "reason": "测试调用目标函数并观察到预期失败类型，引用与输入前提均已核对。",
        "input_supported": True,
        "requirement_supported": True,
        "failure_matches_candidate": True,
        "requirement_class": "behavior",
        "unresolved_assumptions": [],
    }
    decision = EvidenceDecision.model_validate(base)
    admitted, checks, failed = audit_gate(decision)
    assert admitted and not failed and all(checks.values())
    for change, failed_name in [
        ({"input_supported": False}, "input_supported"),
        ({"requirement_supported": False}, "requirement_supported"),
        ({"failure_matches_candidate": False}, "failure_matches_candidate"),
        ({"requirement_class": "diagnostic_quality"}, "behavior_class"),
        ({"unresolved_assumptions": ["输入前提未证实"]}, "no_unresolved_assumptions"),
        ({"accepted": False}, "model_accepted"),
    ]:
        admitted, _, failed = audit_gate(EvidenceDecision.model_validate(base | change))
        assert not admitted and failed_name in failed
    incomplete = EvidenceDecision.model_validate(
        {"accepted": True, "reason": base["reason"]}
    )
    admitted, _, failed = audit_gate(incomplete)
    assert not admitted and {
        "input_supported",
        "requirement_supported",
        "failure_matches_candidate",
        "behavior_class",
    } <= set(failed)


def assertion_attempt():
    result = attempt()
    result["execution"].update(
        errors=0,
        failures=1,
        observations=[
            {
                "outcome": "failure",
                "exception_type": "AssertionError",
                "traceback": "/harness/test_reproduction.py:5",
            }
        ],
        target_lines=[3],
    )
    return result


class FixedExecutor(Executor):
    def __init__(self, result):
        super().__init__()
        self.result = result

    def execute(self, files, target, code):
        self.calls += 1
        return self.result


def test_language_rule_mismatch_keeps_candidate_without_an_audit_call():
    llm = FakeLLM([language_rule_plan().model_dump_json()])
    index = CodeIndex({"a.py": SOURCE})
    executor = FixedExecutor(attempt())
    validator = EvidenceEngine(
        index, ReviewAgents(index, llm), ReviewOptions(mode="evidence"), executor
    )
    item = finding()
    validator.validate(item)
    assert item.status == "pending_evidence"
    assert item.reproduction["status"] == "contract_unconfirmed"
    assert "另一种异常" in item.reproduction["reason"]
    assert item.reproduction["admission"]["requirement"]["accepted"] is False
    assert executor.calls == 2 and len(llm.calls) == 1


def test_missing_expected_exception_is_not_raised_by_code_still_needs_audit():
    llm = FakeLLM(
        [
            language_rule_plan().model_dump_json(),
            audit(),
        ]
    )
    index = CodeIndex({"a.py": SOURCE})
    executor = FixedExecutor(assertion_attempt())
    validator = EvidenceEngine(
        index, ReviewAgents(index, llm), ReviewOptions(mode="evidence"), executor
    )
    item = finding()
    validator.validate(item)
    assert item.status == "reproduced"
    assert item.reproduction["admission"]["accepted"] is True
    assert executor.calls == 2 and len(llm.calls) == 2


@pytest.mark.parametrize(
    "change, failed_name",
    [
        ({"input_supported": False}, "input_supported"),
        ({"requirement_class": "diagnostic_quality"}, "behavior_class"),
        ({"unresolved_assumptions": ["输入前提未证实"]}, "no_unresolved_assumptions"),
    ],
)
def test_model_acceptance_with_failed_structured_check_stays_pending(
    change, failed_name
):
    llm = FakeLLM([plan().model_dump_json(), audit(**change)])
    index = CodeIndex({"a.py": SOURCE})
    executor = FixedExecutor(attempt())
    validator = EvidenceEngine(
        index, ReviewAgents(index, llm), ReviewOptions(mode="evidence"), executor
    )
    item = finding()
    validator.validate(item)
    assert item.status == "pending_evidence"
    assert item.reproduction["status"] == "contract_unconfirmed"
    assert failed_name in item.reproduction["admission"]["audit"]["failed"]
    assert "准入检查未通过" in item.reproduction["reason"]


def test_free_form_acceptance_without_structured_checks_cannot_confirm():
    llm = FakeLLM(
        [
            plan().model_dump_json(),
            json.dumps(
                {
                    "accepted": True,
                    "reason": "模型口头接受，但没有填写结构化准入字段，不能作为正式缺陷。",
                }
            ),
        ]
    )
    index = CodeIndex({"a.py": SOURCE})
    validator = EvidenceEngine(
        index,
        ReviewAgents(index, llm),
        ReviewOptions(mode="evidence"),
        FixedExecutor(attempt()),
    )
    item = finding()
    validator.validate(item)
    assert item.status == "pending_evidence"
    assert "input_supported" in item.reproduction["admission"]["audit"]["failed"]


def test_error_message_only_expectation_is_retried_then_not_a_behavior_defect():
    value = plan()
    value.contract.expected_outcome = "error_message"
    llm = FakeLLM([value.model_dump_json(), value.model_dump_json()])
    index = CodeIndex({"a.py": SOURCE})
    executor = FixedExecutor(attempt())
    validator = EvidenceEngine(
        index, ReviewAgents(index, llm), ReviewOptions(mode="evidence"), executor
    )
    item = finding()
    validator.validate(item)
    assert item.status == "pending_evidence"
    assert item.reproduction["status"] == "invalid_plan"
    assert "不是行为缺陷" in item.reproduction["reason"]
    assert executor.calls == 0 and len(llm.calls) == 2


def test_retest13_control_admits_only_the_documented_positive():
    from evaluation.expectation_controls import evaluate

    rows = evaluate()
    assert len(rows) == 13
    assert [row["finding_id"] for row in rows if row["admitted_to_audit"]] == [
        "9261f543fc85"
    ]
    assert all(
        not row["admitted_to_audit"]
        for row in rows
        if row["contract_kind"] == "language_rule"
    )


def test_legacy_plan_without_structured_fields_is_still_parseable_and_replayable():
    saved = plan().model_dump()
    for key in [
        "expected_outcome",
        "expected_exception",
        "precondition",
        "assumptions",
    ]:
        saved["contract"].pop(key)
    parsed = ReproductionPlan.model_validate(saved)
    assert parsed.contract.expected_outcome == "unspecified"
    validate_plan(parsed, CodeIndex({"a.py": SOURCE}))
    with pytest.raises(ValueError, match="expected_outcome"):
        validate_requirement(parsed)


def test_baseline_without_admission_accepts_a_free_form_audit():
    llm = FakeLLM(
        [
            plan().model_dump_json(),
            json.dumps(
                {
                    "accepted": True,
                    "reason": "对照实验：模型口头接受，未填写结构化准入字段。",
                }
            ),
        ]
    )
    index = CodeIndex({"a.py": SOURCE})
    validator = EvidenceEngine(
        index,
        ReviewAgents(index, llm),
        ReviewOptions(mode="evidence", enforce_admission=False),
        FixedExecutor(attempt()),
    )
    item = finding()
    validator.validate(item)
    assert item.status == "reproduced"
    assert item.reproduction["admission"]["enforced"] is False
    assert item.reproduction["admission"]["audit"]["checks"] is None
    assert "关闭结构化准入" in item.validation


def test_baseline_without_admission_does_not_pre_reject_a_language_rule():
    llm = FakeLLM([language_rule_plan().model_dump_json(), audit()])
    index = CodeIndex({"a.py": SOURCE})
    validator = EvidenceEngine(
        index,
        ReviewAgents(index, llm),
        ReviewOptions(mode="evidence", enforce_admission=False),
        FixedExecutor(attempt()),
    )
    item = finding()
    validator.validate(item)
    assert item.status == "reproduced"
    assert item.reproduction["admission"]["enforced"] is False
    assert "requirement" not in item.reproduction["admission"]
