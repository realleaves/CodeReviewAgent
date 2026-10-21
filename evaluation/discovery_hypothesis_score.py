"""Score the P1 baseline-vs-hypothesis discovery experiment."""

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
                "completed": 0,
                "windows": 0,
                "hypothesis_traces": 0,
            },
        )
        group["windows"] += 1
        group["completed"] += int(row["status"] == "completed")
        group["calls"] += row["api_calls"]
        group["tool_reads"] += len(row.get("tool_reads", []))
        group["hypothesis_traces"] += sum(
            trace.get("stage") == "hypothesis_review" for trace in row.get("trace", [])
        )
        for finding in row.get("findings", []):
            group["findings"][finding["id"]] = finding
        for call in row.get("calls", []):
            for key, value in call.get("usage", {}).items():
                if isinstance(value, int):
                    group["usage"][key] = group["usage"].get(key, 0) + value
    assert len(groups) == 24
    assert set(groups) == set(decisions)
    for key, group in groups.items():
        decision = decisions[key]
        active = {finding["id"] for finding in decision["active_findings"]}
        assert active == set(group["findings"])
        assert set(decision["matched_finding_ids"]) <= active
    arms = []
    for arm in ["baseline", "hypothesis"]:
        detected = alarms = discriminated = 0
        hits = []
        for case in sorted({key[0] for key in groups}):
            buggy = decisions[(case, arm, "buggy")]
            fixed = decisions[(case, arm, "fixed")]
            detected += int(buggy["target_issue_detected"] is True)
            alarms += int(fixed["target_issue_detected"] is True)
            discriminated += int(
                buggy["target_issue_detected"] is True
                and fixed["target_issue_detected"] is not True
            )
            if buggy["target_issue_detected"]:
                hits.append(case)
        arm_groups = [group for key, group in groups.items() if key[1] == arm]
        arms.append(
            {
                "arm": arm,
                "eligible_cases": 6,
                "candidate_hits": detected,
                "candidate_hit_cases": hits,
                "fixed_side_alarms": alarms,
                "correctly_discriminated_cases": discriminated,
                "candidate_findings": sum(
                    len(group["findings"]) for group in arm_groups
                ),
                "completed_windows": sum(group["completed"] for group in arm_groups),
                "planned_windows": sum(group["windows"] for group in arm_groups),
                "calls": sum(group["calls"] for group in arm_groups),
                "usage": {
                    key: sum(group["usage"].get(key, 0) for group in arm_groups)
                    for key in ["prompt_tokens", "completion_tokens", "total_tokens"]
                },
                "tool_reads": sum(group["tool_reads"] for group in arm_groups),
                "hypothesis_traces": sum(
                    group["hypothesis_traces"] for group in arm_groups
                ),
            }
        )
    baseline, hypothesis = arms
    return {
        "metrics": arms,
        "delta_hypothesis_minus_baseline": {
            "candidate_hits": hypothesis["candidate_hits"] - baseline["candidate_hits"],
            "fixed_side_alarms": hypothesis["fixed_side_alarms"]
            - baseline["fixed_side_alarms"],
            "candidate_findings": hypothesis["candidate_findings"]
            - baseline["candidate_findings"],
            "calls": hypothesis["calls"] - baseline["calls"],
            "completion_tokens": hypothesis["usage"]["completion_tokens"]
            - baseline["usage"]["completion_tokens"],
            "tool_reads": hypothesis["tool_reads"] - baseline["tool_reads"],
        },
        "adoption": (
            "Not met: hypothesis does not add reference candidates; it misses the "
            "one baseline hit and performs no tool reads despite reporting checked items."
        ),
        "scope": (
            "Discovery only on the 6 r0 development cases, 18 windows per arm, "
            "one repetition; known-location windows; not a new-sample or full-repo score."
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
        "# P1 baseline vs hypothesis-first discovery",
        "",
        "| arm | candidate hits | fixed alarms | discriminated | candidates | calls | completion tokens | tool reads | completed |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["metrics"]:
        lines.append(
            f"| {row['arm']} | {row['candidate_hits']}/6 | {row['fixed_side_alarms']} | {row['correctly_discriminated_cases']}/6 | {row['candidate_findings']} | {row['calls']} | {row['usage']['completion_tokens']} | {row['tool_reads']} | {row['completed_windows']}/{row['planned_windows']} |"
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
