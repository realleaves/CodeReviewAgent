"""Offline verification of the P1c tool-first smoke archive."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
PHASE = ROOT / "p1c-tool-first"
sys.path.insert(0, str(PROJECT))
from evaluation.discovery_tool_first_score import score


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    goal = json.loads((ROOT / "p1c-goal.json").read_text())
    arms = json.loads((ROOT / "arms-p1c.json").read_text())
    setup = json.loads((ROOT / "setup-p1c.json").read_text())
    budget = json.loads((ROOT / "budget.json").read_text())
    manifest = json.loads((PHASE / "manifest.json").read_text())
    results = json.loads((PHASE / "results.json").read_text())
    adjudications = json.loads((PHASE / "adjudications.json").read_text())
    scores = json.loads((PHASE / "scores.json").read_text())
    assert goal["selection"] == ["tornado-3", "youtube-dl-4"]
    assert set(arms) == {"baseline", "tool_first"}
    assert setup["windows"] == 4 and len(setup["window_records"]) == 4
    assert budget["phases"]["p1c-tool-first"] == 12
    assert budget["reserved"] == 70 and budget["limit"] == 80
    assert results["status"] == "sampled" and len(results["records"]) == 8
    assert len(manifest["input_windows"]) == 4
    assert manifest["comparison_variable"] == "review_strategy"
    assert set(manifest["strategies"]) == {"baseline", "tool_first"}
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
    assert len(decisions) == 8 and set(decisions) == set(groups)
    for key, active in groups.items():
        assert active == {
            finding["id"] for finding in decisions[key]["active_findings"]
        }
        assert decisions[key]["target_issue_detected"] is False
    recomputed = score(PHASE, adjudications)
    assert recomputed["metrics"] == scores["metrics"]
    baseline = next(row for row in scores["metrics"] if row["arm"] == "baseline")
    tool_first = next(row for row in scores["metrics"] if row["arm"] == "tool_first")
    assert baseline["candidate_hits"] == tool_first["candidate_hits"] == 0
    assert baseline["fixed_side_alarms"] == tool_first["fixed_side_alarms"] == 0
    assert baseline["completed_windows"] == tool_first["completed_windows"] == 4
    assert baseline["tool_calls"] == 0 and tool_first["tool_calls"] == 12
    assert baseline["tool_reads"] == 0 and tool_first["tool_reads"] == 6
    assert tool_first["no_tool_call"] == 0
    assert baseline["calls"] == 4 and tool_first["calls"] == 8
    print(
        json.dumps(
            {
                "status": "PASS",
                "windows": 8,
                "provider_attempts": 12,
                "budget": {"phase": 12, "total": 70, "limit": 80},
                "baseline": {
                    "candidate_hits": 0,
                    "completed": 4,
                    "tool_calls": 0,
                    "calls": 4,
                },
                "tool_first": {
                    "candidate_hits": 0,
                    "completed": 4,
                    "tool_calls": 12,
                    "tool_reads": 6,
                    "no_tool_call": 0,
                    "calls": 8,
                },
                "decision": "mechanical tool use achieved; no recall gain; not adopted as a detection improvement",
                "note": "2-case 4-window smoke; one repetition; not a full development or holdout score",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
