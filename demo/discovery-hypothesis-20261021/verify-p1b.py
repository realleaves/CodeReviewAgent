"""Offline verification of the P1b tool-evidence smoke archive."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
PHASE = ROOT / "p1b-tools"
sys.path.insert(0, str(PROJECT))
from evaluation.discovery_hypothesis_tools_score import score


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    goal = json.loads((ROOT / "p1b-goal.json").read_text())
    arms = json.loads((ROOT / "arms-p1b.json").read_text())
    setup = json.loads((ROOT / "setup-p1b.json").read_text())
    budget = json.loads((ROOT / "budget.json").read_text())
    manifest = json.loads((PHASE / "manifest.json").read_text())
    results = json.loads((PHASE / "results.json").read_text())
    adjudications = json.loads((PHASE / "adjudications.json").read_text())
    scores = json.loads((PHASE / "scores.json").read_text())
    assert goal["selection"] == ["tornado-3", "youtube-dl-4", "youtube-dl-8"]
    assert set(arms) == {"baseline", "hypothesis_tools"}
    assert setup["windows"] == 6 and len(setup["window_records"]) == 6
    assert budget["phases"]["p1b-tools"] == 19 and budget["limit"] == 80
    assert budget["reserved"] >= 58
    assert budget["phases"]["p1b-tools"] == 19
    assert results["status"] == "sampled" and len(results["records"]) == 12
    assert len(manifest["input_windows"]) == 6
    assert manifest["comparison_variable"] == "review_strategy"
    assert set(manifest["strategies"]) == {"baseline", "hypothesis_tools"}
    assert sum(row["status"] == "completed" for row in results["records"]) == 10
    assert sum(row["status"] == "failed" for row in results["records"]) == 2
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
    assert len(decisions) == 12 and set(decisions) == set(groups)
    for key, active in groups.items():
        assert active == {
            finding["id"] for finding in decisions[key]["active_findings"]
        }
        assert decisions[key]["target_issue_detected"] is False
    recomputed = score(PHASE, adjudications)
    assert recomputed["metrics"] == scores["metrics"]
    baseline = next(row for row in scores["metrics"] if row["arm"] == "baseline")
    hypothesis = next(
        row for row in scores["metrics"] if row["arm"] == "hypothesis_tools"
    )
    assert baseline["candidate_hits"] == 0 and baseline["completed_windows"] == 6
    assert hypothesis["candidate_hits"] == 0 and hypothesis["completed_windows"] == 4
    assert baseline["fixed_side_alarms"] == hypothesis["fixed_side_alarms"] == 0
    assert baseline["tool_reads"] == 2 and hypothesis["tool_reads"] == 4
    assert hypothesis["tool_retries"] == 4 and hypothesis["dropped_findings"] == 2
    assert baseline["calls"] == 7 and hypothesis["calls"] == 12
    print(
        json.dumps(
            {
                "status": "PASS",
                "windows": 12,
                "provider_attempts": 19,
                "budget": {"phase": 19, "total_after_p1": 58, "limit": 80},
                "baseline": {
                    "candidate_hits": 0,
                    "completed": baseline["completed_windows"],
                    "tool_reads": baseline["tool_reads"],
                    "calls": baseline["calls"],
                },
                "hypothesis_tools": {
                    "candidate_hits": 0,
                    "completed": hypothesis["completed_windows"],
                    "failed": hypothesis["failed_windows"],
                    "tool_reads": hypothesis["tool_reads"],
                    "retries": hypothesis["tool_retries"],
                    "dropped": hypothesis["dropped_findings"],
                    "calls": hypothesis["calls"],
                },
                "decision": "not adopted: no strict hit, two schema failures, key window findings dropped",
                "note": "3-case 6-window smoke; one repetition; not a full development or holdout score",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
