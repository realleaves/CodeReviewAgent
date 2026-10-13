"""Blinded evidence evaluation. Official tests are exclusively evaluator-side."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.bugsinpy_reproduce import reproduce_case
from evaluation.bugsinpy_data import make_manifest, prepare
from evaluation.bugsinpy_review import run_scoped_review
from src.report import write_reports
from src.schemas import ReviewOptions


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", default="outputs/evidence-holdout-work")
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=["direct", "evidence"],
        default=["direct", "evidence"],
    )
    parser.add_argument("--output")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--dataset", default="outputs/bugsinpy-data")
    parser.add_argument("--max-calls", type=int, default=20)
    parser.add_argument("--max-total-calls", type=int, default=320)
    parser.add_argument("--max-reproductions", type=int, default=3)
    parser.add_argument("--python37-image", default="python:3.7-slim")
    parser.add_argument(
        "--python38-image", default="code-review-bugsinpy:py38-complete"
    )
    parser.add_argument("--official-tests", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        manifest = make_manifest(
            Path(args.dataset).resolve(),
            {"tornado": 12, "youtube-dl": 13},
            {"tornado": 9, "youtube-dl": 10},
        )
        prepare(manifest, Path(args.work).resolve())
        return
    if not args.output:
        parser.error("运行需要指定新的 --output；准备数据时使用 --prepare")
    if min(args.max_calls, args.max_total_calls, args.max_reproductions) < 1:
        parser.error("预算必须为正数")
    work, root = Path(args.work).resolve(), Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    cases = json.loads((work / "prepared.json").read_text())
    if args.case_ids:
        by_id = {c["id"]: c for c in cases}
        if set(args.case_ids) - set(by_id):
            parser.error("样本未准备")
        cases = [by_id[c] for c in args.case_ids]
    images = {"3.7": args.python37_image, "3.8": args.python38_image}
    project = Path(__file__).resolve().parents[1]
    save(root / "selection.json", cases)
    save(
        root / "run_config.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dataset_commit": json.loads((work / "manifest.json").read_text())[
                "dataset_commit"
            ],
            "max_calls": args.max_calls,
            "max_total_calls": args.max_total_calls,
            "max_reproductions": args.max_reproductions,
            "modes": args.modes,
            "source_sha256": {
                str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((project / "src").glob("*.py"))
            },
            "protocol": "Known-location windows; target tests/patches/variant hidden. Only indexed production source is mounted in agent containers. Official tests are evaluator-only.",
            "scoring": "Score all window-complete, official-test-verified pairs; unconfirmed or failed agent reproductions count as misses, not excluded successful runs.",
        },
    )
    records = []
    calls = 0
    for case in cases:
        # Labels never enter the code index, planner, audit or agent container.
        official = "not_run"
        if args.official_tests:
            print("Evaluator tests:", case["id"], flush=True)
            try:
                official = reproduce_case(
                    case, work, root / "official-tests" / case["id"], images
                )["status"]
            except Exception as error:
                official = "environment_failed"
                save(
                    root / "official-tests" / case["id"] / "error.json",
                    {"error_type": type(error).__name__},
                )
        for mode in args.modes:
            for side in ["buggy", "fixed"]:
                row = {
                    "case": case["id"],
                    "mode": mode,
                    "variant": side,
                    "official_reproduction": official,
                }
                if calls >= args.max_total_calls:
                    row.update(
                        status="budget_exhausted",
                        window_review_completed=False,
                        calls=0,
                    )
                else:
                    print(
                        f"Review {case['id']}/{mode}/{side}; calls {calls}/{args.max_total_calls}",
                        flush=True,
                    )
                    limit = min(args.max_calls, args.max_total_calls - calls)
                    image = images[".".join(case["python_version"].split(".")[:2])]
                    options = ReviewOptions(
                        mode=mode,
                        max_calls=limit,
                        max_file_bytes=1_000_000,
                        repro_image=image,
                        max_reproductions=args.max_reproductions,
                    )
                    regions = {p: h[side] for p, h in case["production_hunks"].items()}
                    report = run_scoped_review(
                        work / case["snapshot_paths"][side],
                        regions,
                        mode,
                        limit,
                        evidence_options=options,
                    )
                    report["benchmark_provenance"] = {
                        "case": case["id"],
                        "variant": side,
                        "buggy_commit": case["buggy_commit"],
                        "fixed_commit": case["fixed_commit"],
                        "snapshot_protocol": "buggy baseline plus fixed-commit changed files",
                    }
                    report["repository"].update(
                        name=case["project"],
                        url=case["repository"]
                        if side == "buggy"
                        else "local-benchmark",
                        commit=case["buggy_commit"],
                    )
                    relative = Path("reviews") / case["id"] / mode / side
                    write_reports(report, root / relative)
                    calls += report["run"]["api_calls"]
                    row.update(
                        status=report["run"]["status"],
                        window_review_completed=report["run"][
                            "window_review_completed"
                        ],
                        calls=report["run"]["api_calls"],
                        seconds=report["run"]["elapsed_seconds"],
                        usage=report["run"]["usage"],
                        report=str(relative / "report.json"),
                        reproduced=sum(
                            f["status"] == "reproduced" for f in report["findings"]
                        ),
                    )
                records.append(row)
                save(
                    root / "results.json",
                    {
                        "records": records,
                        "calls": calls,
                        "semantic_scoring": "pending reference-issue adjudication; reproduced does not imply matching the official known defect",
                    },
                )
    print(
        json.dumps(
            {"output": str(root), "reviews": len(records), "calls": calls}, indent=2
        )
    )


if __name__ == "__main__":
    main()
