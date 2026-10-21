"""Offline verification of the P1 baseline-vs-hypothesis discovery archive."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
PHASE = ROOT / "p1-hypothesis"
sys.path.insert(0, str(PROJECT))
from evaluation.discovery_hypothesis_score import score


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    budget = json.loads((ROOT / "budget.json").read_text())
    setup = json.loads((ROOT / "setup.json").read_text())
    manifest = json.loads((PHASE / "manifest.json").read_text())
    results = json.loads((PHASE / "results.json").read_text())
    adjudications = json.loads((PHASE / "adjudications.json").read_text())
    scores = json.loads((PHASE / "scores.json").read_text())
    assert budget["phases"]["p1-hypothesis"] == 39 and budget["limit"] == 80
    assert budget["reserved"] >= 39
    assert setup["windows"] == 18 and len(setup["selection"]) == 6
    assert results["status"] == "sampled" and len(results["records"]) == 36
    assert len(manifest["input_windows"]) == 18
    assert manifest["comparison_variable"] == "review_strategy"
    assert set(manifest["strategies"]) == {"baseline", "hypothesis"}
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
    assert len(decisions) == 24 and set(decisions) == set(groups)
    for key, active in groups.items():
        supplied = {finding["id"] for finding in decisions[key]["active_findings"]}
        assert active == supplied
        assert set(decisions[key]["matched_finding_ids"]) <= active
    assert decisions[("youtube-dl-4", "baseline", "buggy")]["target_issue_detected"]
    assert (
        decisions[("youtube-dl-4", "hypothesis", "buggy")]["target_issue_detected"]
        is False
    )
    assert not any(
        row["target_issue_detected"]
        for (case, arm, side), row in decisions.items()
        if side == "fixed"
    )
    recomputed = score(PHASE, adjudications)
    assert recomputed["metrics"] == scores["metrics"]
    baseline = next(row for row in scores["metrics"] if row["arm"] == "baseline")
    hypothesis = next(row for row in scores["metrics"] if row["arm"] == "hypothesis")
    assert baseline["candidate_hits"] == 1 and baseline["tool_reads"] == 6
    assert hypothesis["candidate_hits"] == 0 and hypothesis["tool_reads"] == 0
    assert baseline["candidate_hit_cases"] == ["youtube-dl-4"]
    assert hypothesis["candidate_hit_cases"] == []
    assert baseline["fixed_side_alarms"] == hypothesis["fixed_side_alarms"] == 0
    assert baseline["completed_windows"] == hypothesis["completed_windows"] == 18
    print(
        json.dumps(
            {
                "status": "PASS",
                "windows": 36,
                "provider_attempts": 39,
                "budget_limit": 80,
                "baseline": {
                    "candidate_hits": 1,
                    "calls": baseline["calls"],
                    "tool_reads": baseline["tool_reads"],
                    "candidates": baseline["candidate_findings"],
                },
                "hypothesis": {
                    "candidate_hits": 0,
                    "calls": hypothesis["calls"],
                    "tool_reads": hypothesis["tool_reads"],
                    "candidates": hypothesis["candidate_findings"],
                },
                "decision": "not adopted: no recall gain and no real tool reads in the hypothesis arm",
                "note": "discovery only; 6 development cases; one repetition; known-location windows",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
