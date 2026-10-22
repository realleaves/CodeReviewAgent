import copy
import json

import pytest

from evaluation.discovery_mechanism_audit_score import score


def fixture(tmp_path, hit=False, alarm=False):
    manifest = {
        "repetitions": 1,
        "strategies": ["baseline", "mechanism_audit"],
        "input_windows": [
            {"case": "example", "side": side} for side in ["buggy", "fixed"]
        ],
    }
    records, decisions = [], []
    for arm in manifest["strategies"]:
        for side in ["buggy", "fixed"]:
            findings = (
                []
                if arm == "baseline"
                else [{"id": side, "trigger": "explicit test input"}]
            )
            matched = arm == "mechanism_audit" and (hit if side == "buggy" else alarm)
            calls = [
                {
                    "status": "completed",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            ] * (1 if arm == "baseline" else 2)
            records.append(
                {
                    "case": "example",
                    "strategy": arm,
                    "side": side,
                    "status": "completed",
                    "findings": findings,
                    "api_calls": len(calls),
                    "calls": calls,
                }
            )
            decisions.append(
                {
                    "case": "example",
                    "mode": arm,
                    "variant": side,
                    "target_issue_detected": matched,
                    "matched_finding_ids": [side] if matched else [],
                    "active_findings": copy.deepcopy(findings),
                    "finding_reviews": [
                        {
                            "id": side,
                            "reference_match": matched,
                            "reason": "explicit synthetic semantic decision",
                        }
                    ]
                    if findings
                    else [],
                    "reason": "synthetic scoring fixture",
                    "adjudicator": "test fixture",
                }
            )
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "results.json").write_text(json.dumps({"records": records}))
    return decisions, records


def test_more_extra_candidates_without_reference_hits_does_not_pass(tmp_path):
    decisions, _ = fixture(tmp_path)
    result = score(tmp_path, decisions)
    assert result["smoke_gate_met"] is False
    assert result["metrics"][1]["candidate_findings"] == 2
    assert result["metrics"][1]["candidate_hits"] == 0
    assert result["delta_mechanism_audit_minus_baseline"]["calls"] == 2
    assert result["delta_mechanism_audit_minus_baseline"]["usage"] == {
        "prompt_tokens": 20,
        "completion_tokens": 10,
    }


def test_strict_hit_passes_only_the_smoke_gate_without_evidence_or_holdout_claim(
    tmp_path,
):
    decisions, _ = fixture(tmp_path, hit=True)
    result = score(tmp_path, decisions)
    assert result["smoke_gate_met"] is True
    assert result["metrics"][1]["correctly_discriminated_cases"] == 1
    assert result["scope"]["evidence_stage_run"] is False
    assert result["scope"]["holdout_run"] is False
    assert "not default adoption" in result["decision"]


def test_same_reference_fixed_alarm_blocks_smoke_gate(tmp_path):
    decisions, _ = fixture(tmp_path, hit=True, alarm=True)
    result = score(tmp_path, decisions)
    assert result["smoke_gate_met"] is False
    assert result["metrics"][1]["fixed_side_alarms"] == 1
    assert result["metrics"][1]["correctly_discriminated_cases"] == 0


def test_incomplete_pair_and_its_failed_call_remain_visible(tmp_path):
    decisions, records = fixture(tmp_path, hit=True, alarm=True)
    failed = records[-1]
    failed["status"] = "failed"
    failed["calls"][-1] = {"status": "failed", "error_type": "MockTransportError"}
    (tmp_path / "results.json").write_text(json.dumps({"records": records}))
    result = score(tmp_path, decisions)
    audit = result["metrics"][1]
    assert audit["eligible_pairs"] == audit["candidate_hits"] == 0
    assert audit["planned_cases"] == audit["observed_buggy_hits"] == 1
    assert audit["failed_windows"] == audit["failed_provider_calls"] == 1
    assert audit["calls"] == 4
    assert audit["fixed_side_alarms"] == 1
    assert result["smoke_gate_met"] is False


@pytest.mark.parametrize(
    "tamper",
    ["unknown_match", "missing_decision", "duplicate_decision", "altered_finding"],
)
def test_inconsistent_adjudications_are_rejected(tmp_path, tamper):
    decisions, _ = fixture(tmp_path)
    if tamper == "unknown_match":
        decisions[-1]["matched_finding_ids"] = ["not-in-results"]
    elif tamper == "missing_decision":
        decisions.pop()
    elif tamper == "duplicate_decision":
        decisions.append(copy.deepcopy(decisions[-1]))
    else:
        decisions[-1]["active_findings"][0]["trigger"] = "altered answer"
    with pytest.raises(AssertionError):
        score(tmp_path, decisions)
