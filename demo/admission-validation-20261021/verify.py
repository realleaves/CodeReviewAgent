"""Offline verification of the 2026-10-21 admission control archive."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    summary = json.loads((ROOT / "summary.json").read_text())
    results = json.loads((ROOT / "results.json").read_text())
    protocol = json.loads((ROOT / "protocol.json").read_text())
    budget = json.loads((ROOT / "budget.json").read_text())
    assert summary["status"] == "sampled"
    assert summary["cases"] == 4 and len(results["records"]) == 4
    assert summary["api_calls"] == budget["reserved"] == 5
    assert budget["limit"] == 24 and budget["phases"] == {"admission-controls": 5}
    assert summary["positive_reproduced"] is True
    assert summary["negatives_downgraded"] is True
    assert summary["incomplete"] == []
    assert protocol["model"]["provider_is_deepseek"] is True
    assert protocol["model"]["thinking_mode"] == "disabled"
    assert protocol["model"]["max_output_tokens"] == 6000
    by_case = {row["case"]: row for row in summary["positive"] + summary["negatives"]}
    assert set(by_case) == {
        "PySnooper-3",
        "tornado-1-fixed",
        "youtube-dl-4-fixed",
        "youtube-dl-8-buggy",
    }
    positive = by_case["PySnooper-3"]["current"]
    assert positive["finding_status"] == "reproduced"
    assert positive["admission"]["accepted"] is True
    assert all(positive["admission"]["audit"]["checks"].values())
    assert positive["attempt_verdicts"] == ["failure_observed", "failure_observed"]
    for case in ["tornado-1-fixed", "youtube-dl-4-fixed"]:
        current = by_case[case]["current"]
        assert current["finding_status"] == "pending_evidence"
        assert current["evidence_status"] == "unsupported"
        assert current["attempt_verdicts"] == []
    negative = by_case["youtube-dl-8-buggy"]["current"]
    assert negative["finding_status"] == "pending_evidence"
    assert negative["evidence_status"] == "contract_unconfirmed"
    assert negative["admission"]["requirement"]["accepted"] is False
    assert "另一种异常" in negative["admission"]["requirement"]["reason"]
    assert negative["expected_exception"] == "SyntaxError"
    assert negative["attempt_verdicts"] == ["failure_observed", "failure_observed"]
    requests = list((ROOT / "cases").glob("*/requests/*/request.json"))
    responses = list((ROOT / "cases").glob("*/requests/*/response.json"))
    assert len(requests) == len(responses) == 5
    for row in results["records"]:
        case = row["case"]
        for relative, expected in row["artifacts"].items():
            assert digest(ROOT / "cases" / case / "artifacts" / relative) == expected
    for relative, expected in protocol["source_sha256"].items():
        assert digest(PROJECT / relative) == expected
    print(
        json.dumps(
            {
                "status": "PASS",
                "cases": 4,
                "provider_attempts": 5,
                "budget_limit": 24,
                "positive_preserved": positive["finding_status"],
                "negatives": [
                    {
                        "case": case,
                        "evidence_status": by_case[case]["current"]["evidence_status"],
                    }
                    for case in by_case
                    if case != "PySnooper-3"
                ],
                "docker_executions": 4,
                "note": "seen fixed candidates; no official tests/labels; no new-sample or full-repo score",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
