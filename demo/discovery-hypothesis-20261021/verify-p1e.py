"""Offline verification of the P1e hypothesis-audit smoke archive."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
PHASE = ROOT / "p1e-hypothesis-audit"
sys.path.insert(0, str(PROJECT))
from evaluation.discovery_hypothesis_audit_score import score


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    goal = json.loads((ROOT / "p1e-goal.json").read_text())
    arms = json.loads((ROOT / "arms-p1e.json").read_text())
    setup = json.loads((ROOT / "setup-p1e.json").read_text())
    budget = json.loads((ROOT / "budget.json").read_text())
    manifest = json.loads((PHASE / "manifest.json").read_text())
    results = json.loads((PHASE / "results.json").read_text())
    adjudications = json.loads((PHASE / "adjudications.json").read_text())
    scores = json.loads((PHASE / "scores.json").read_text())
    assert goal["selection"] == ["youtube-dl-2"]
    assert set(arms) == {"baseline", "hypothesis_audit"}
    assert setup["windows"] == 2 and len(setup["window_records"]) == 2
    assert budget["phases"]["p1e-hypothesis-audit"] == 6
    assert budget["reserved"] == 80 and budget["limit"] == 80
    assert results["status"] == "sampled" and len(results["records"]) == 4
    assert len(manifest["input_windows"]) == 2
    assert manifest["comparison_variable"] == "review_strategy"
    assert set(manifest["strategies"]) == {"baseline", "hypothesis_audit"}
    assert all(row["status"] == "completed" for row in results["records"])
    for relative, expected in manifest["source_sha256"].items():
        assert digest(PHASE / "implementation" / relative) == expected
    groups = {}
    for row in results["records"]:
        key = (row["case"], row["strategy"], row["side"])
        groups.setdefault(key, set()).update(
            finding["id"] for finding in row.get("findings", [])
        )
        requests = list((PHASE / row["folder"] / "requests").glob("*/request.json"))
        responses = list((PHASE / row["folder"] / "requests").glob("*/response.json"))
        assert len(requests) == len(responses) == row["api_calls"]
    decisions = {
        (row["case"], row["mode"], row["variant"]): row for row in adjudications
    }
    assert len(decisions) == 4 and set(decisions) == set(groups)
    for key, active in groups.items():
        assert active == {
            finding["id"] for finding in decisions[key]["active_findings"]
        }
        assert decisions[key]["target_issue_detected"] is False
    recomputed = score(PHASE, adjudications)
    assert recomputed["metrics"] == scores["metrics"]
    baseline = next(row for row in scores["metrics"] if row["arm"] == "baseline")
    audit = next(row for row in scores["metrics"] if row["arm"] == "hypothesis_audit")
    assert baseline["candidate_hits"] == audit["candidate_hits"] == 0
    assert baseline["fixed_side_alarms"] == audit["fixed_side_alarms"] == 0
    assert baseline["completed_windows"] == audit["completed_windows"] == 2
    assert baseline["calls"] == 2 and audit["calls"] == 4
    assert audit["audit_windows"] == 2 and audit["audit_added"] == 0
    assert audit["target_concept_mentioned"] is False
    print(
        json.dumps(
            {
                "status": "PASS",
                "windows": 4,
                "provider_attempts": 6,
                "budget": {"phase": 6, "total": 80, "limit": 80},
                "baseline": {
                    "candidate_hits": 0,
                    "completed": 2,
                    "calls": 2,
                },
                "hypothesis_audit": {
                    "candidate_hits": 0,
                    "completed": 2,
                    "calls": 4,
                    "audit_windows": 2,
                    "audit_added": 0,
                    "target_concept_mentioned": False,
                },
                "decision": "inconclusive for the audit mechanism: the omitted reference hypothesis was not reproduced",
                "note": "1-case 2-window smoke; P1 ledger exhausted at 80/80",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
