"""Adjudicate and score the baseline-vs-admission evidence pilot."""

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def score(root, adjudications):
    results = load(root / "results.json")["records"]
    records = {(r["case"], r["arm"], r["side"]): r for r in results}
    decisions = {(d["case"], d["mode"], d["variant"]): d for d in adjudications}
    assert len(records) == len(decisions) == 16
    assert set(records) == set(decisions)
    arms = sorted({key[1] for key in records})
    output = []
    for arm in arms:
        eligible = detected = alarms = discriminated = identified = pending = 0
        calls = reproduced = pending_findings = 0
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        exclusions = []
        for case in sorted({key[0] for key in records}):
            buggy = records.get((case, arm, "buggy"))
            fixed = records.get((case, arm, "fixed"))
            if (
                buggy is None
                or fixed is None
                or not buggy["window_review_completed"]
                or not fixed["window_review_completed"]
                or buggy["official_reproduction"] != "reproduced"
                or fixed["official_reproduction"] != "reproduced"
            ):
                exclusions.append(
                    {"case": case, "reason": "window_or_official_incomplete"}
                )
                continue
            bug = decisions[(case, arm, "buggy")]
            repair = decisions[(case, arm, "fixed")]
            eligible += 1
            detected += int(bug["target_issue_detected"] is True)
            alarms += int(repair["target_issue_detected"] is True)
            discriminated += int(
                bug["target_issue_detected"] is True
                and repair["target_issue_detected"] is not True
            )
            identified += int(bug["target_issue_identified"] is True)
            pending += int(
                bug["target_issue_identified"] is True
                and bug["target_issue_detected"] is not True
            )
            for row in (buggy, fixed):
                calls += row["api_calls"]
                reproduced += row["reproduced_findings"]
                pending_findings += row["pending_findings"]
                for key in usage:
                    usage[key] += row.get("usage", {}).get(key, 0)
        output.append(
            {
                "arm": arm,
                "planned_pairs": 4,
                "eligible_pairs": eligible,
                "detected_known_bugs": detected,
                "identified_reference_candidates": identified,
                "candidate_identified_but_not_reproduced": pending,
                "same_issue_alarms_on_fixed": alarms,
                "correctly_discriminated_pairs": discriminated,
                "api_calls": calls,
                "reproduced_findings": reproduced,
                "pending_findings": pending_findings,
                "usage": usage,
                "exclusions": exclusions,
            }
        )
    return {
        "metrics": output,
        "scoring_scope": "Frozen reference issue; a hit requires a reproduced Agent finding. Extra findings are separate, not automatic false positives.",
        "stage": "evidence-stage pilot on 4 discovery-holdout cases; one repetition; not a new-sample or full-repo benchmark",
        "adjudicators": sorted(
            {
                d["adjudicator"]
                for d in adjudications
                if d["target_issue_detected"] is not None
            }
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--adjudications", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    decisions = load(args.adjudications)
    result = score(args.run, decisions)
    target = args.output or (args.run / "scores.json")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# baseline vs admission evidence pilot",
        "",
        "| arm | eligible/planned | detected | identified | pending match | fixed alarm | discriminated | calls | reproduced | pending |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["metrics"]:
        lines.append(
            f"| {row['arm']} | {row['eligible_pairs']}/{row['planned_pairs']} | {row['detected_known_bugs']} | {row['identified_reference_candidates']} | {row['candidate_identified_but_not_reproduced']} | {row['same_issue_alarms_on_fixed']} | {row['correctly_discriminated_pairs']} | {row['api_calls']} | {row['reproduced_findings']} | {row['pending_findings']} |"
        )
    lines += [
        "",
        "A hit requires a reproduced Agent finding matching the frozen reference cause and trigger. "
        "Identified-but-not-reproduced is reported separately; extra findings are not automatic false positives.",
        "",
        "Adjudicators: " + ", ".join(result["adjudicators"]),
        "",
    ]
    target.with_suffix(".md").write_text("\n".join(lines))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
