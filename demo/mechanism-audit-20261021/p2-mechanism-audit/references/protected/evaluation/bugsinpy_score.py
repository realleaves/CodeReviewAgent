"""Target-specific pair scores require explicit semantic adjudication evidence."""

import argparse
import json
from pathlib import Path


def score_pairs(records, adjudications):
    outcomes = {(r["case"], r["mode"], r["variant"]): r for r in records}
    if len(outcomes) != len(records):
        raise ValueError("Duplicate run records")
    decisions = {}
    for decision in adjudications:
        key = (decision["case"], decision["mode"], decision["variant"])
        if key in decisions or key not in outcomes:
            raise ValueError("Duplicate or unknown adjudication")
        verdict = decision["target_issue_detected"]
        if verdict is not None and not isinstance(verdict, bool):
            raise ValueError("Verdict must be boolean or null")
        active_ids = {f["id"] for f in decision["active_findings"]}
        matched = decision["matched_finding_ids"]
        if not set(matched) <= active_ids or len(matched) != len(set(matched)):
            raise ValueError("Matched IDs must refer to unique active findings")
        if verdict is not None:
            if not decision["adjudicator"] or len(decision["reason"].strip()) < 15:
                raise ValueError("Semantic decisions need an adjudicator and evidence")
            if verdict and not matched or not verdict and matched:
                raise ValueError("Matched IDs contradict the target verdict")
        decisions[key] = decision
    groups = sorted({(r["case"], r["mode"]) for r in records})
    scores = []
    for mode in sorted({r["mode"] for r in records}):
        eligible, detected, repaired_alarm, discriminated = 0, 0, 0, 0
        exclusions = []
        for case, current_mode in groups:
            if current_mode != mode:
                continue
            keys = [(case, mode, side) for side in ["buggy", "fixed"]]
            runs = [outcomes.get(key) for key in keys]
            if any(r is None or r["status"] != "completed" for r in runs):
                exclusions.append({"case": case, "reason": "review_incomplete"})
                continue
            if any(r.get("reproduction") != "reproduced" for r in runs):
                exclusions.append({"case": case, "reason": "reproduction_not_verified"})
                continue
            judgments = [decisions.get(key) for key in keys]
            if any(d is None or d["target_issue_detected"] is None for d in judgments):
                exclusions.append({"case": case, "reason": "semantic_judgment_pending"})
                continue
            bug, fixed = (d["target_issue_detected"] for d in judgments)
            eligible += 1
            detected += int(bug)
            repaired_alarm += int(fixed)
            discriminated += int(bug and not fixed)
        scores.append(
            {
                "mode": mode,
                "planned_pairs": sum(m == mode for _, m in groups),
                "eligible_pairs": eligible,
                "detected_known_bugs": detected,
                "same_issue_alarms_on_fixed": repaired_alarm,
                "correctly_discriminated_pairs": discriminated,
                "known_bug_detection_rate": detected / eligible if eligible else None,
                "fixed_target_alarm_rate": repaired_alarm / eligible
                if eligible
                else None,
                "paired_discrimination_rate": discriminated / eligible
                if eligible
                else None,
                "exclusions": exclusions,
            }
        )
    return {
        "metrics": scores,
        "scoring_scope": "Only the known reference issue; extra findings are not automatically false positives.",
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
    parser.add_argument("--run", required=True)
    parser.add_argument("--adjudications", required=True)
    args = parser.parse_args()
    root = Path(args.run)
    records = json.loads((root / "results.json").read_text())["records"]
    decisions = json.loads(Path(args.adjudications).read_text())
    by_key = {(d["case"], d["mode"], d["variant"]): d for d in decisions}
    for record in records:
        key = (record["case"], record["mode"], record["variant"])
        if key not in by_key or "report" not in record:
            continue
        path = (root / record["report"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Report path escapes run directory")
        actual = json.loads(path.read_text())
        if actual["run"]["status"] != record["status"]:
            raise ValueError("Run summary does not match original report")
        original_ids = {
            f["id"] for f in actual["findings"] if f["status"] != "rejected"
        }
        supplied_ids = {f["id"] for f in by_key[key]["active_findings"]}
        if original_ids != supplied_ids:
            raise ValueError("Adjudication findings differ from original report")
    score = score_pairs(records, decisions)
    (root / "scores.json").write_text(
        json.dumps(score, ensure_ascii=False, indent=2) + "\n"
    )
    summary = json.loads((root / "results.json").read_text())
    summary["semantic_scoring"] = (
        "Explicit semantic adjudications supplied; see scores.json for eligible pairs and exclusions, and the named adjudicators for review status."
    )
    (root / "results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    lines = [
        "# BugsInPy 参考问题评分",
        "",
        "只统计审查完整、成对复现成功且有语义判读的样本。所有排除项见 scores.json。",
        "",
        "| 模式 | 有效/计划缺陷对 | 已知缺陷检出 | 修复后同问题误报 | 成对区分正确 |",
        "|---|---|---:|---:|---:|",
    ]
    for row in score["metrics"]:
        lines.append(
            f"| {row['mode']} | {row['eligible_pairs']}/{row['planned_pairs']} | {row['detected_known_bugs']} | {row['same_issue_alarms_on_fixed']} | {row['correctly_discriminated_pairs']} |"
        )
    lines += [
        "",
        "判读者：" + ", ".join(score["adjudicators"]),
        "",
        "这些是限定窗口、限定参考缺陷的结果，不能解释为全仓库精确率；模型辅助判读仍需人类复查。",
        "",
    ]
    (root / "scores.md").write_text("\n".join(lines))
    print(json.dumps(score, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
