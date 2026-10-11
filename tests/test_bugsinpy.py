"""Benchmark safeguards: hidden answers, valid pair evidence, honest denominators."""

import json

import pytest

from evaluation.bugsinpy_data import metadata, patch_ranges, safe_relative, windows
from evaluation.bugsinpy_reproduce import test_commands as parse_test_commands
from evaluation.bugsinpy_review import reviewer_files, run_scoped_review
from evaluation.bugsinpy_score import score_pairs
from src.agents import BoundedAgent, BudgetExceeded


def test_dataset_metadata_is_parsed_without_shell_execution(tmp_path):
    path = tmp_path / "bug.info"
    path.write_text(
        'fixed_commit_id ="abc"\r\npython_version="3.7.0"\n$(touch sentinel)\n'
    )
    assert metadata(path) == {"fixed_commit_id": "abc", "python_version": "3.7.0"}
    assert not (tmp_path / "sentinel").exists()


@pytest.mark.parametrize(
    "value", ["../answers.json", "/etc/passwd", "a/../../escape", "a\\b"]
)
def test_dataset_paths_cannot_escape(value):
    with pytest.raises(ValueError):
        safe_relative(value)


def test_patch_sides_keep_distinct_line_ranges():
    patch = "diff --git a/lib/a.py b/lib/a.py\n@@ -10,3 +10,5 @@ def f():\n"
    assert patch_ranges(patch) == {
        "lib/a.py": {"buggy": [[10, 12]], "fixed": [[10, 14]]}
    }


def test_windows_keep_function_context_and_real_positions():
    source = "\n" * 100 + "def f(x):\n    return 1 / x\n"
    result = windows(source, [[102, 102]])
    assert result[0][0] <= 101 and result[0][1] == 102


def test_test_selectors_are_not_shell_commands():
    assert parse_test_commands(
        "python -m unittest -q t.test\npytest -q tests/a.py::test_a"
    ) == [
        ["python", "-m", "unittest", "-q", "t.test"],
        ["python", "-m", "pytest", "-q", "tests/a.py::test_a"],
    ]
    with pytest.raises(ValueError):
        parse_test_commands("python -m unittest t.test; curl evil")
    with pytest.raises(ValueError):
        parse_test_commands("bash setup.sh")


class ObservedLLM:
    model = "test-double"
    current_stage = ""

    def __init__(self):
        self.calls = []
        self.messages = []

    def invoke(self, messages, **kwargs):
        self.messages.extend(messages)
        self.calls.append({"status": "completed"})
        return '{"findings":[]}'


def test_reviewer_never_receives_tests_patch_or_oracle_label(tmp_path):
    (tmp_path / "lib.py").write_text("def f(x):\n    return x\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/answers.py").write_text('ANSWER = "hidden-golden-marker"\n')
    (tmp_path / "bug_patch.txt").write_text("hidden-patch-marker")
    (tmp_path / "bug.info").write_text('expected="hidden-label-marker"')
    files, _ = reviewer_files(tmp_path)
    assert list(files) == ["lib.py"]
    llm = ObservedLLM()
    report = run_scoped_review(
        tmp_path, {"lib.py": [[2, 2]]}, "direct", 4, llm=llm, progress=lambda _: None
    )
    serialized = json.dumps(llm.messages)
    assert all(
        value not in serialized
        for value in [
            "hidden-golden-marker",
            "hidden-patch-marker",
            "hidden-label-marker",
        ]
    )
    assert report["run"]["status"] == "completed"
    assert report["run"]["fully_reviewed_files"] == 0
    assert report["run"]["scope_kind"] == "known_location_windows"


def pair_inputs():
    runs = [
        {
            "case": "p-1",
            "mode": "full",
            "variant": side,
            "status": "completed",
            "reproduction": "reproduced",
        }
        for side in ["buggy", "fixed"]
    ]
    decisions = [
        {
            "case": "p-1",
            "mode": "full",
            "variant": side,
            "target_issue_detected": side == "buggy",
            "matched_finding_ids": ["known"] if side == "buggy" else [],
            "active_findings": [{"id": "known"}, {"id": "unrelated"}],
            "reason": "Evidence describes the known target problem and its actual trigger.",
            "adjudicator": "test-reviewer",
        }
        for side in ["buggy", "fixed"]
    ]
    return runs, decisions


def test_extra_fixed_findings_do_not_automatically_become_false_positives():
    runs, decisions = pair_inputs()
    metric = score_pairs(runs, decisions)["metrics"][0]
    assert metric["known_bug_detection_rate"] == 1
    assert metric["fixed_target_alarm_rate"] == 0
    assert metric["correctly_discriminated_pairs"] == 1


@pytest.mark.parametrize("condition", ["partial", "not_reproduced", "pending"])
def test_failed_or_unjudged_pairs_are_excluded_with_reasons(condition):
    runs, decisions = pair_inputs()
    if condition == "partial":
        runs[0]["status"] = "partial"
    elif condition == "not_reproduced":
        runs[0]["reproduction"] = "not_reproduced"
    else:
        decisions[0].update(target_issue_detected=None, matched_finding_ids=[])
    metric = score_pairs(runs, decisions)["metrics"][0]
    assert metric["eligible_pairs"] == 0
    assert metric["known_bug_detection_rate"] is None
    assert len(metric["exclusions"]) == 1


def test_scoring_rejects_fabricated_matching_ids_and_missing_evidence():
    runs, decisions = pair_inputs()
    decisions[0]["matched_finding_ids"] = ["not-in-report"]
    with pytest.raises(ValueError):
        score_pairs(runs, decisions)
    decisions[0]["matched_finding_ids"] = ["known"]
    decisions[0]["reason"] = ""
    with pytest.raises(ValueError):
        score_pairs(runs, decisions)


def test_array_output_gets_one_explicit_json_object_correction():
    class Model(ObservedLLM):
        def invoke(self, messages, **kwargs):
            self.calls.append(
                {"status": "completed", "format": kwargs.get("response_format")}
            )
            return "[]" if len(self.calls) == 1 else '{"findings":[]}'

    model = Model()
    agent = BoundedAgent(
        name="review", llm=model, system_prompt="Return a JSON object."
    )
    assert json.loads(agent.run("Review source.")) == {"findings": []}
    assert len(model.calls) == 2
    assert model.calls[-1]["format"] == {"type": "json_object"}
    assert model.calls[0]["format_repair_requested"] is True


def test_format_correction_cannot_bypass_call_budget():
    class Model(ObservedLLM):
        def invoke(self, messages, **kwargs):
            if self.calls:
                raise BudgetExceeded("one call only")
            self.calls.append({"status": "completed"})
            return "[]"

    model = Model()
    agent = BoundedAgent(name="review", llm=model, system_prompt="Return JSON.")
    with pytest.raises(BudgetExceeded):
        agent.run("Review source.")
    assert len(model.calls) == 1


def test_scoring_keeps_fixed_target_alarm_separate_from_detection():
    runs, decisions = pair_inputs()
    decisions[1].update(target_issue_detected=True, matched_finding_ids=["known"])
    metric = score_pairs(runs, decisions)["metrics"][0]
    assert metric["detected_known_bugs"] == 1
    assert metric["same_issue_alarms_on_fixed"] == 1
    assert metric["paired_discrimination_rate"] == 0
