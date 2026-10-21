"""Offline verification of the P1d static external-read smoke archive."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
PHASE = ROOT / "p1d-tool-external"
sys.path.insert(0, str(PROJECT))
from evaluation.discovery_tool_external_score import score


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    goal = json.loads((ROOT / "p1d-goal.json").read_text())
    arms = json.loads((ROOT / "arms-p1d.json").read_text())
    setup = json.loads((ROOT / "setup-p1d.json").read_text())
    budget = json.loads((ROOT / "budget.json").read_text())
    manifest = json.loads((PHASE / "manifest.json").read_text())
    results = json.loads((PHASE / "results.json").read_text())
    adjudications = json.loads((PHASE / "adjudications.json").read_text())
    scores = json.loads((PHASE / "scores.json").read_text())
    assert goal["selection"] == ["youtube-dl-2"]
    assert set(arms) == {"baseline", "tool_first_external"}
    assert setup["windows"] == 2 and len(setup["window_records"]) == 2
    assert budget["phases"]["p1d-tool-external"] == 4
    assert budget["reserved"] == 74 and budget["limit"] == 80
    assert results["status"] == "sampled" and len(results["records"]) == 4
    assert len(manifest["input_windows"]) == 2
    assert manifest["comparison_variable"] == "review_strategy"
    assert set(manifest["strategies"]) == {"baseline", "tool_first_external"}
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
    external = next(
        row for row in scores["metrics"] if row["arm"] == "tool_first_external"
    )
    assert baseline["candidate_hits"] == external["candidate_hits"] == 0
    assert baseline["fixed_side_alarms"] == external["fixed_side_alarms"] == 0
    assert baseline["completed_windows"] == external["completed_windows"] == 2
    assert baseline["external_calls"] == 0 and external["external_calls"] == 6
    assert baseline["tool_reads"] == 0 and external["tool_reads"] == 6
    assert external["no_external_span"] == 0
    assert baseline["calls"] == external["calls"] == 2
    print(
        json.dumps(
            {
                "status": "PASS",
                "windows": 4,
                "provider_attempts": 4,
                "budget": {"phase": 4, "total": 74, "limit": 80},
                "baseline": {
                    "candidate_hits": 0,
                    "completed": 2,
                    "external_calls": 0,
                    "calls": 2,
                },
                "tool_first_external": {
                    "candidate_hits": 0,
                    "completed": 2,
                    "external_calls": 6,
                    "tool_reads": 6,
                    "no_external_span": 0,
                    "calls": 2,
                },
                "decision": "external reads executed; no reference hit; not adopted",
                "note": "1-case 2-window smoke; one repetition; not a full development/holdout score",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
