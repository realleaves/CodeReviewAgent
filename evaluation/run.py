"""Bounded smoke comparison. Location/category matching needs semantic human QA."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.pipeline import run_review
from src.repository import Repository
from src.report import write_reports
from src.schemas import ReviewOptions


def score(report: dict, expected: list[dict]) -> dict:
    active = [
        f
        for f in report["findings"]
        if f["status"] != "rejected" and f["category"] in {"bug", "security"}
    ]
    matched = set()
    false_predictions = set()
    for finding in active:
        match = next(
            (
                i
                for i, label in enumerate(expected)
                if finding["category"] == label["category"]
                and label["start"] <= finding["line"] <= label["end"]
            ),
            None,
        )
        if match is not None:
            matched.add(match)
        else:
            false_predictions.add(
                (finding["line"], finding["category"], finding["title"])
            )
    return {
        "tp": len(matched),
        "fp": len(false_predictions),
        "fn": len(expected) - len(matched),
        "matching": "位置与类别自动粗匹配；触发条件和问题语义需人工核对。",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--max-total-calls", type=int, default=24)
    parser.add_argument("--env-file")
    parser.add_argument("--output", default="outputs/evaluation")
    args = parser.parse_args()
    if args.limit < 1 or args.max_total_calls < 1:
        parser.error("limit 和 max-total-calls 必须大于零")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cases = json.loads(Path(__file__).with_name("cases.json").read_text())[: args.limit]
    records, total_calls = [], 0
    for mode in ["direct", "assisted", "full"]:
        for case in cases:
            remaining = args.max_total_calls - total_calls
            if remaining <= 0:
                break
            print(
                f"评测 {mode}/{case['id']} · 总调用 {total_calls}/{args.max_total_calls}",
                flush=True,
            )
            with tempfile.TemporaryDirectory(
                prefix="code-review-evaluation-"
            ) as directory:
                root = Path(directory)
                (root / "sample.py").write_text(case["code"], encoding="utf-8")
                repo = Repository(
                    root, "local-evaluation", "fixed-fixture", "fixture", case["id"]
                )
                report = run_review(
                    repo,
                    ReviewOptions(
                        mode=mode, max_files=1, max_calls=min(4, remaining), timeout=45
                    ),
                    args.env_file,
                    progress=lambda _: None,
                )
            total_calls += report["run"]["api_calls"]
            write_reports(report, output / mode / case["id"])
            records.append(
                {
                    "mode": mode,
                    "case": case["id"],
                    "expected": case["expected"],
                    "status": report["run"]["status"],
                    "calls": report["run"]["api_calls"],
                    "seconds": report["run"]["elapsed_seconds"],
                    "score": score(report, case["expected"]),
                }
            )
    aggregates = []
    for mode in ["direct", "assisted", "full"]:
        rows = [r for r in records if r["mode"] == mode]
        complete = [r for r in rows if r["status"] == "completed"]
        sums = {
            key: sum(r["score"][key] for r in complete) for key in ["tp", "fp", "fn"]
        }
        aggregates.append(
            {
                "mode": mode,
                "completed_cases": len(complete),
                "attempted_cases": len(rows),
                "planned_cases": len(cases),
                **sums,
                "precision": sums["tp"] / (sums["tp"] + sums["fp"])
                if sums["tp"] + sums["fp"]
                else None,
                "recall": sums["tp"] / (sums["tp"] + sums["fn"])
                if sums["tp"] + sums["fn"]
                else None,
                "calls": sum(r["calls"] for r in rows),
                "seconds": round(sum(r["seconds"] for r in rows), 3),
            }
        )
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_calls": total_calls,
        "note": "小样本冒烟对比，位置与类别自动匹配；尚未经人工语义判定，不能作为泛化准确率。",
        "aggregates": aggregates,
        "records": records,
    }
    (output / "comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 小样本方案对比",
        "",
        result["note"],
        "",
        "| 模式 | 完成/计划样本 | TP | FP | FN | 粗匹配精确率 | 粗匹配召回率 | 调用 | 耗时(s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in aggregates:
        rate = lambda x: f"{x:.1%}" if x is not None else "N/A"
        lines.append(
            f"| {row['mode']} | {row['completed_cases']}/{row['planned_cases']} | {row['tp']} | {row['fp']} | {row['fn']} | {rate(row['precision'])} | {rate(row['recall'])} | {row['calls']} | {row['seconds']} |"
        )
    (output / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result["aggregates"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
