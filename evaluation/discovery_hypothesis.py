"""P1 protocol and runner: baseline vs hypothesis-first discovery.

The experiment is discovery-only: the same six development cases, both sides,
one repetition, and two prompt strategies. It never runs the evidence engine.
The protocol and setup are written before any provider call; the actual run is a
separate command so the budget can be checked first.
"""

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.bugsinpy_review import reviewer_files
from evaluation.discovery_experiment import digest, now, run, save
from src.agents import MeteredLLM, load_config
from src.repository import snapshot_digest


ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "outputs/context-callgraph-20261015/preview-final"
CASES = ROOT / "outputs/evidence-original20-20261014/selection.json"
SNAPSHOTS = ROOT / "outputs/bugsinpy-work"

PROTOCOL = {
    "title": "baseline vs hypothesis-first discovery",
    "date": "2026-10-21",
    "kind": "P1 single-variable prompt/workflow experiment; discovery only",
    "hypothesis": (
        "The current one-pass broad prompt often returns no candidate or an "
        "adjacent issue. A structured understand -> enumerate -> counterexample -> "
        "check -> candidates prompt should increase reference candidate recall "
        "without increasing fixed-side same-issue alarms or lowering completion."
    ),
    "selection": [
        "tornado-1",
        "tornado-3",
        "tornado-7",
        "youtube-dl-2",
        "youtube-dl-4",
        "youtube-dl-8",
    ],
    "selection_reason": (
        "The six development cases used by r0/r1/r2; frozen before this experiment. "
        "Both buggy and fixed sides and all 18 r0 input windows are used."
    ),
    "arms": {
        "baseline": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "baseline",
        },
        "hypothesis": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "hypothesis",
        },
    },
    "variable": "review_strategy",
    "repetitions": 1,
    "window_call_limit": 3,
    "budget": {"limit": 80, "per_window": 3},
    "metrics": [
        "reference candidate recall on the buggy side",
        "fixed-side same-issue alarms",
        "extra candidate count (not automatically false positives)",
        "completed windows and provider failures",
        "calls and reported tokens",
    ],
    "adoption": (
        "At least two more correctly identified reference pairs than baseline, "
        "with no increase in fixed-side same-issue alarms and no lower completed "
        "window count. A single repetition is exploratory; repeat before adoption."
    ),
    "holdout": (
        "Only if the development result meets the adoption condition; use the "
        "four prepared holdout cases in a separate phase and budget."
    ),
    "scope": (
        "Discovery only; no Agent-generated tests, no evidence engine, no official "
        "tests/labels/opposite version in the Agent input. Known-location windows; "
        "not a full-repo or new-sample score. All failures and requests retained."
    ),
}


def prepare(root, limit):
    if root.exists():
        raise SystemExit("输出目录必须是不存在的新路径。")
    root.mkdir(parents=True)
    save(
        root / "budget.json",
        {"limit": limit, "reserved": 0, "phases": {}, "started_at": now()},
    )
    save(root / "goal.json", PROTOCOL)
    shutil.copy2(
        ROOT / "evaluation/bugsinpy-rubric.json", root / "reference-rubric.json"
    )
    save(
        root / "protected.json",
        {
            "evaluation/bugsinpy-rubric.json": digest(
                ROOT / "evaluation/bugsinpy-rubric.json"
            ),
            "evaluation/bugsinpy_score.py": digest(
                ROOT / "evaluation/bugsinpy_score.py"
            ),
        },
    )
    save(root / "arms.json", PROTOCOL["arms"])
    load_config()
    with redirect_stdout(io.StringIO()):
        probe = MeteredLLM(1, 45)
    model = {
        "model": probe.model,
        "thinking_mode": probe.thinking_mode,
        "temperature": probe.temperature,
        "max_output_tokens": probe.max_tokens,
        "provider_is_deepseek": probe.is_deepseek,
    }
    probe.close()
    assert model["provider_is_deepseek"]
    assert model["thinking_mode"] == "disabled"
    assert model["temperature"] == 0.1
    assert model["max_output_tokens"] == 6000
    windows = json.loads((PREVIEW / "results.json").read_text())["records"]
    cases = {case["id"]: case for case in json.loads(CASES.read_text())}
    assert {window["case"] for window in windows} == set(PROTOCOL["selection"])
    assert len(windows) == 18
    checked = {}
    for case_id, case in cases.items():
        if case_id not in PROTOCOL["selection"]:
            continue
        for side in ["buggy", "fixed"]:
            files, _ = reviewer_files(SNAPSHOTS / case["snapshot_paths"][side])
            checked[f"{case_id}/{side}"] = {
                "files": len(files),
                "snapshot_sha256": snapshot_digest(files),
            }
    save(
        root / "setup.json",
        {
            "windows": len(windows),
            "selection": sorted({window["case"] for window in windows}),
            "snapshots": checked,
            "model": model,
            "protocol": PROTOCOL,
        },
    )
    print(
        json.dumps(
            {
                "status": "prepared",
                "output": str(root),
                "windows": len(windows),
                "selection": sorted({window["case"] for window in windows}),
                "budget_limit": limit,
                "model": model,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/hypothesis-discovery-20261021",
    )
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--phase", default="p1-hypothesis")
    args = parser.parse_args()
    root = args.output.resolve()
    if args.command == "prepare":
        prepare(root, args.limit)
        return
    if not root.exists():
        parser.error("请先运行 prepare。")
    run(
        root,
        args.phase,
        args.repetitions,
        args.limit,
        ["baseline", "hypothesis"],
        root / "arms.json",
        "review_strategy",
    )


if __name__ == "__main__":
    main()
