"""Score the P1d static external-read smoke."""

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def score(phase, adjudications):
    results = load(phase / "results.json")["records"]
    decisions = {
        (row["case"], row["mode"], row["variant"]): row for row in adjudications
    }
    groups = {}
    for row in results:
        key = (row["case"], row["strategy"], row["side"])
        group = groups.setdefault(
            key,
            {
                "findings": {},
                "calls": 0,
                "usage": {},
                "tool_reads": 0,
                "external_calls": 0,
                "no_external": 0,
                "completed": 0,
            },
        )
        group["completed"] += int(row["status"] == "completed")
        group["calls"] += row["api_calls"]
        group["tool_reads"] += len(row.get("tool_reads", []))
        for trace in row.get("trace", []):
            if trace.get("stage") == "tool_first_external":
                group["external_calls"] += len(trace.get("calls", []))
                group["no_external"] += int(trace.get("status") == "no_external_span")
        for finding in row.get("findings", []):
            group["findings"][finding["id"]] = finding
        for call in row.get("calls", []):
            for key, value in call.get("usage", {}).items():
                if isinstance(value, int):
                    group["usage"][key] = group["usage"].get(key, 0) + value
    assert len(groups) == 4
    assert set(groups) == set(decisions)
    for key, group in groups.items():
        active = {finding["id"] for finding in decisions[key]["active_findings"]}
        assert active == set(group["findings"])
    cases = sorted({key[0] for key in groups})
    metrics = []
    for arm in ["baseline", "tool_first_external"]:
        eligible = detected = alarms = 0
        for case in cases:
            buggy = groups[(case, arm, "buggy")]
            fixed = groups[(case, arm, "fixed")]
            if buggy["completed"] != 1 or fixed["completed"] != 1:
                continue
            eligible += 1
            detected += int(
                decisions[(case, arm, "buggy")]["target_issue_detected"] is True
            )
            alarms += int(
                decisions[(case, arm, "fixed")]["target_issue_detected"] is True
            )
        arm_groups = [group for key, group in groups.items() if key[1] == arm]
        metrics.append(
            {
                "arm": arm,
                "planned_cases": len(cases),
                "eligible_pairs": eligible,
                "candidate_hits": detected,
                "fixed_side_alarms": alarms,
                "candidate_findings": sum(
                    len(group["findings"]) for group in arm_groups
                ),
                "completed_windows": sum(group["completed"] for group in arm_groups),
                "calls": sum(group["calls"] for group in arm_groups),
                "usage": {
                    key: sum(group["usage"].get(key, 0) for group in arm_groups)
                    for key in ["prompt_tokens", "completion_tokens"]
                },
                "tool_reads": sum(group["tool_reads"] for group in arm_groups),
                "external_calls": sum(group["external_calls"] for group in arm_groups),
                "no_external_span": sum(group["no_external"] for group in arm_groups),
            }
        )
    return {
        "metrics": metrics,
        "mechanical_result": (
            "The static call context selected caller/callee spans and the code read "
            "them on every external-arm window; no no-external-span window occurred."
        ),
        "detection_result": (
            "Neither arm matched the DASH format_id uniqueness/merge reference; the "
            "external-arm candidates remained SegmentTimeline/duration issues."
        ),
        "adoption": (
            "Not adopted: external reads were real and cheap, but they did not change "
            "the candidate away from the adjacent SegmentTimeline/ISM issues."
        ),
        "scope": (
            "1 development case, one r0 window per side, two windows per arm, one "
            "repetition; smoke only, not a full development/holdout score."
        ),
        "adjudicators": sorted(
            {
                row["adjudicator"]
                for row in adjudications
                if row["target_issue_detected"] is not None
            }
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=Path, required=True)
    parser.add_argument("--adjudications", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = score(args.phase, load(args.adjudications))
    target = args.output or (args.phase / "scores.json")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# P1d static external-read smoke",
        "",
        "| arm | eligible | candidate hits | fixed alarms | candidates | completed | calls | tool reads | external calls |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["metrics"]:
        lines.append(
            f"| {row['arm']} | {row['eligible_pairs']}/{row['planned_cases']} | {row['candidate_hits']} | {row['fixed_side_alarms']} | {row['candidate_findings']} | {row['completed_windows']}/2 | {row['calls']} | {row['tool_reads']} | {row['external_calls']} |"
        )
    lines += [
        "",
        "Candidate hit = concrete reference root cause/symptom + valid trigger at the candidate stage. "
        "No evidence engine was run; extra findings are not automatic false positives.",
        "",
        "Adjudicators: " + ", ".join(result["adjudicators"]),
        "",
    ]
    target.with_suffix(".md").write_text("\n".join(lines))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
