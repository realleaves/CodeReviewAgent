"""Offline verification of the baseline-vs-admission evidence pilot archive."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
SNAPSHOT = ROOT / "implementation"
sys.path.insert(0, str(PROJECT))
from evaluation.evidence_holdout_score import score


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = json.loads((ROOT / "protocol.json").read_text())
    results = json.loads((ROOT / "results.json").read_text())
    summary = json.loads((ROOT / "summary.json").read_text())
    official = json.loads((ROOT / "official.json").read_text())
    adjudications = json.loads((ROOT / "adjudications.json").read_text())
    scores = json.loads((ROOT / "scores.json").read_text())
    budget = json.loads((ROOT / "budget.json").read_text())
    assert len(results["records"]) == 16
    assert len(adjudications) == 16
    assert summary["runs"] == 16 and summary["api_calls"] == 37
    assert budget["reserved"] == 37 and budget["limit"] == 140
    assert summary["by_arm"]["baseline"]["api_calls"] == 18
    assert summary["by_arm"]["admission"]["api_calls"] == 19
    assert summary["by_arm"]["baseline"]["completed_windows"] == 8
    assert summary["by_arm"]["admission"]["completed_windows"] == 8
    assert all(row["status"] == "reproduced" for row in official.values())
    assert all(row["window_review_completed"] for row in results["records"])
    assert not any(row.get("error") for row in results["records"])
    by_key = {(row["case"], row["arm"], row["side"]): row for row in results["records"]}
    decisions = {
        (row["case"], row["mode"], row["variant"]): row for row in adjudications
    }
    assert set(by_key) == set(decisions)
    for key, row in by_key.items():
        decision = decisions[key]
        active = {
            finding["id"]
            for finding in row["findings"]
            if finding["status"] != "rejected"
        }
        supplied = {finding["id"] for finding in decision["active_findings"]}
        assert active == supplied
        assert set(decision["matched_finding_ids"]) <= active
        if decision["target_issue_detected"] is True:
            assert decision["matched_finding_ids"]
            assert all(
                finding["status"] == "reproduced"
                for finding in decision["active_findings"]
                if finding["id"] in decision["matched_finding_ids"]
            )
        request_dir = ROOT / "requests" / key[0] / key[1] / key[2] / "requests"
        requests = list(request_dir.glob("*/request.json"))
        responses = list(request_dir.glob("*/response.json"))
        assert len(requests) == len(responses) == row["api_calls"]
    assert len(list((ROOT / "requests").glob("*/*/*/requests/*/request.json"))) == 37
    recomputed = score(ROOT, adjudications)
    assert recomputed["metrics"] == scores["metrics"]
    for relative, expected in protocol["source_sha256"].items():
        assert digest(SNAPSHOT / relative) == expected
    print(
        json.dumps(
            {
                "status": "PASS",
                "runs": 16,
                "provider_attempts": 37,
                "budget_limit": 140,
                "completed_windows": {"baseline": 8, "admission": 8},
                "metrics": {
                    row["arm"]: {
                        "detected": row["detected_known_bugs"],
                        "alarms": row["same_issue_alarms_on_fixed"],
                        "discriminated": row["correctly_discriminated_pairs"],
                        "calls": row["api_calls"],
                        "reproduced": row["reproduced_findings"],
                        "pending": row["pending_findings"],
                    }
                    for row in recomputed["metrics"]
                },
                "note": "4 discovery-holdout cases; first evidence-stage run; one repetition; not fully unseen or full-repo",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
