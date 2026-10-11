"""Reproducible, known-location BugsInPy evaluation. No fabricated semantic scores."""

import argparse
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.bugsinpy_data import make_manifest, prepare
from evaluation.bugsinpy_reproduce import reproduce_case
from evaluation.bugsinpy_review import run_scoped_review
from src.report import write_reports

PROJECT = Path(__file__).resolve().parents[1]


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def summarize(output, records):
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol": "BugsInPy known-location windows; no official leaderboard score",
        "records": records,
        "calls": sum(r.get("calls", 0) for r in records),
        "semantic_scoring": "pending evidence-based adjudication; proximity to patch is not a true-positive decision",
    }
    save(output / "results.json", result)
    lines = [
        "# BugsInPy 定范围审查评测",
        "",
        "Agent 未获得缺陷标签、修复补丁、测试或另一版本。窗口位置由参考补丁确定；结果不代表全仓库检测能力。",
        "",
        "修复版本可能仍有其他问题。修复后对同一个参考问题的报告才算该问题的误报；额外候选需要独立判断。",
        "",
        "| 样本 | 模式 | 版本 | 审查状态 | 复现 | 调用 | 耗时(s) | 候选数 |",
        "|---|---|---|---|---|---:|---:|---:|",
    ]
    for row in records:
        lines.append(
            f"| {row['case']} | {row['mode']} | {row['variant']} | {row['status']} | {row.get('reproduction', 'not_run')} | {row.get('calls', 0)} | {row.get('seconds', 0)} | {row.get('active_findings', 0)} |"
        )
    lines += [
        "",
        f"总模型调用：{result['calls']}。",
        "",
        "## 评分",
        "",
        "自动位置重叠只用于筛选人工复查项。未完成语义判定前，不报告缺陷检出率或准确率。评分输入见 adjudication-template.json。",
        "",
    ]
    (output / "comparison.md").write_text("\n".join(lines))
    return result


def main():
    parser = argparse.ArgumentParser(description="BugsInPy 定范围真实缺陷评测")
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("prepare")
    setup.add_argument("--dataset", default="outputs/bugsinpy-data")
    setup.add_argument("--work", default="outputs/bugsinpy-work")
    setup.add_argument("--manifest", default="evaluation/bugsinpy-manifest.json")
    run = sub.add_parser("run")
    run.add_argument("--work", default="outputs/bugsinpy-work")
    run.add_argument("--limit", type=int, default=3)
    run.add_argument(
        "--modes", nargs="+", choices=["direct", "full"], default=["direct", "full"]
    )
    run.add_argument("--max-calls", type=int, default=16)
    run.add_argument("--max-total-calls", type=int, default=240)
    run.add_argument("--timeout", type=int, default=45)
    run.add_argument("--env-file")
    run.add_argument("--output", required=True)
    run.add_argument("--reproduce", action="store_true")
    run.add_argument("--python37-image", default="python:3.7-slim")
    run.add_argument("--python38-image", default="code-review-bugsinpy:py38")
    args = parser.parse_args()
    if args.command == "prepare":
        dataset, work = Path(args.dataset).resolve(), Path(args.work).resolve()
        manifest = make_manifest(dataset)
        save(Path(args.manifest).resolve(), manifest)
        prepare(manifest, work)
        return 0
    if args.limit < 1 or args.max_calls < 1 or args.max_total_calls < 1:
        parser.error("样本数和调用预算必须为正数")
    work, output = Path(args.work).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cases = json.loads((work / "prepared.json").read_text())[: args.limit]
    source_files = sorted((PROJECT / "src").glob("*.py")) + sorted(
        (PROJECT / "evaluation").glob("bugsinpy*.py")
    )
    save(
        output / "run_config.json",
        {
            "dataset_commit": json.loads((work / "manifest.json").read_text())[
                "dataset_commit"
            ],
            "source_sha256": {
                str(p.relative_to(PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in source_files
            },
            "limit": args.limit,
            "modes": args.modes,
            "max_calls_per_review": args.max_calls,
            "max_total_calls": args.max_total_calls,
            "timeout": args.timeout,
            "reproduction_requested": args.reproduce,
            "reviewer_answers_hidden": True,
        },
    )
    save(output / "selection.json", cases)
    records, adjudications, calls = [], [], 0
    images = {"3.7": args.python37_image, "3.8": args.python38_image}
    for case in cases:
        reproduction = "not_run"
        if args.reproduce:
            print(f"复现 {case['id']}", flush=True)
            try:
                evidence = reproduce_case(
                    case, work, output / "reproduction" / case["id"], images
                )
                reproduction = evidence["status"]
            except Exception as exc:
                reproduction = "environment_failed"
                save(
                    output / "reproduction" / case["id"] / "error.json",
                    {"status": reproduction, "error_type": type(exc).__name__},
                )
        for mode in args.modes:
            for variant in ["buggy", "fixed"]:
                folder = output / "reviews" / case["id"] / mode / variant
                if calls >= args.max_total_calls:
                    records.append(
                        {
                            "case": case["id"],
                            "mode": mode,
                            "variant": variant,
                            "status": "global_budget_exhausted",
                            "reproduction": reproduction,
                        }
                    )
                    continue
                print(
                    f"审查 {case['id']}/{mode}/{variant} · 总调用 {calls}/{args.max_total_calls}",
                    flush=True,
                )
                try:
                    regions = {
                        p: h[variant] for p, h in case["production_hunks"].items()
                    }
                    report = run_scoped_review(
                        work / case["snapshot_paths"][variant],
                        regions,
                        mode,
                        min(args.max_calls, args.max_total_calls - calls),
                        args.timeout,
                        args.env_file,
                    )
                    # Label is attached only after inference, for report provenance.
                    report["repository"].update(
                        url=case["repository"],
                        name=case["project"],
                        commit=case[f"{variant}_commit"]
                        if variant == "buggy"
                        else case["buggy_commit"],
                        ref="BugsInPy reconstructed snapshot",
                    )
                    report["benchmark_provenance"] = {
                        "case": case["id"],
                        "variant": variant,
                        "fixed_commit": case["fixed_commit"],
                        "snapshot_protocol": "buggy baseline plus fixed-commit changed files",
                    }
                    # Reconstructed fixed snapshots can differ from the upstream full fixed tree.
                    if variant == "fixed":
                        report["repository"]["url"] = "local-benchmark"
                    calls += report["run"]["api_calls"]
                    write_reports(report, folder)
                    row = {
                        "case": case["id"],
                        "mode": mode,
                        "variant": variant,
                        "status": report["run"]["status"],
                        "reproduction": reproduction,
                        "calls": report["run"]["api_calls"],
                        "seconds": report["run"]["elapsed_seconds"],
                        "usage": report["run"]["usage"],
                        "active_findings": report["run"]["active_findings"],
                        "report": str(folder.relative_to(output) / "report.json"),
                    }
                    active = [
                        f for f in report["findings"] if f["status"] != "rejected"
                    ]
                    adjudications.append(
                        {
                            "case": case["id"],
                            "mode": mode,
                            "variant": variant,
                            "run_status": row["status"],
                            "reproduction": reproduction,
                            "target_issue_detected": None,
                            "matched_finding_ids": [],
                            "reason": "",
                            "adjudicator": "",
                            "location_candidates": [
                                f["id"]
                                for f in active
                                if any(
                                    a <= f["line"] <= b
                                    for a, b in regions.get(f["path"], [])
                                )
                            ],
                            "active_findings": [
                                {
                                    k: f[k]
                                    for k in [
                                        "id",
                                        "path",
                                        "line",
                                        "title",
                                        "explanation",
                                        "trigger",
                                        "status",
                                    ]
                                }
                                for f in active
                            ],
                        }
                    )
                except Exception as exc:
                    row = {
                        "case": case["id"],
                        "mode": mode,
                        "variant": variant,
                        "status": "failed",
                        "reproduction": reproduction,
                        "error_type": type(exc).__name__,
                    }
                    save(folder / "error.json", row)
                records.append(row)
                summarize(output, records)
                save(output / "adjudication-template.json", adjudications)
    result = summarize(output, records)
    print(
        json.dumps(
            {
                "output": str(output),
                "calls": result["calls"],
                "completed": sum(r["status"] == "completed" for r in records),
                "planned_reviews": len(cases) * len(args.modes) * 2,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all(r["status"] == "completed" for r in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
