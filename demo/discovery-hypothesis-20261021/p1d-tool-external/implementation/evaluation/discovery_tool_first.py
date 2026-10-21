"""P1c smoke: tool-first discovery.

Stage 1 may return only read-only tool calls; the code executes them. If no tool
call is returned, the window fails immediately and no hypothesis/candidate stage
runs. Stage 2 receives the real tool results and returns checked/hypotheses/
findings. This tests a stricter workflow than the P1b text retry.
"""

import argparse
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.bugsinpy_review import reviewer_files
from evaluation.discovery_experiment import fingerprint, run, save
from src.repository import snapshot_digest


ROOT = Path(__file__).resolve().parents[1]
P1ROOT = ROOT / "outputs/hypothesis-discovery-20261021"
PREVIEW = ROOT / "outputs/context-callgraph-20261015/preview-final"
CASES = ["tornado-3", "youtube-dl-4"]
SNAPSHOTS = ROOT / "outputs/bugsinpy-work"

PROTOCOL = {
    "title": "P1c smoke: tool-first discovery",
    "date": "2026-10-21",
    "kind": "P1c single-variable tool-first workflow; discovery only",
    "hypothesis": (
        "P1/P1b failed because the model could skip tools and self-report checks. "
        "A tool-only first stage, executed by code, should guarantee real reads; "
        "the hypothesis stage can then use those reads. If stage 1 returns no tool "
        "call, the window fails without a hypothesis/candidate call."
    ),
    "selection": CASES,
    "selection_reason": (
        "tornado-3 (no candidate in P1) and youtube-dl-4 (the one P1 baseline hit); "
        "both sides, one r0 window per side, four windows per arm."
    ),
    "arms": {
        "baseline": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "baseline",
        },
        "tool_first": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "tool_first",
        },
    },
    "variable": "review_strategy",
    "repetitions": 1,
    "window_call_limit": 3,
    "budget": {"phase_limit": 22, "remaining_after_p1b": 22, "per_window": 3},
    "metrics": [
        "first-stage real tool calls and executed results",
        "reference candidate recall on the two cases",
        "fixed-side same-issue alarms",
        "completed/failed windows, calls and tokens",
    ],
    "adoption": (
        "At least one real tool call on both buggy windows and no loss of the "
        "baseline reference hit, with no fixed-side alarm; otherwise reject. A "
        "four-window smoke is exploratory and cannot be generalized."
    ),
    "scope": (
        "Discovery only; no evidence engine, official tests/labels/opposite version "
        "in the Agent input. One repetition; all requests, failures and no-tool "
        "windows retained."
    ),
}


def prepare():
    if (P1ROOT / "p1c-goal.json").exists():
        raise SystemExit("P1c 已经准备过。")
    budget = json.loads((P1ROOT / "budget.json").read_text())
    if budget["reserved"] != 58 or budget["limit"] != 80:
        raise SystemExit("P1 账本不是预期的 58/80，停止。")
    windows = [
        row
        for row in json.loads((PREVIEW / "results.json").read_text())["records"]
        if row["case"] in CASES
    ]
    assert len(windows) == 4
    assert {row["case"] for row in windows} == set(CASES)
    snapshots = {}
    cases = {
        case["id"]: case
        for case in json.loads(
            (ROOT / "outputs/evidence-original20-20261014/selection.json").read_text()
        )
        if case["id"] in CASES
    }
    for case_id, case in cases.items():
        for side in ["buggy", "fixed"]:
            files, _ = reviewer_files(SNAPSHOTS / case["snapshot_paths"][side])
            snapshots[f"{case_id}/{side}"] = {
                "files": len(files),
                "snapshot_sha256": snapshot_digest(files),
            }
    save(P1ROOT / "p1c-goal.json", PROTOCOL)
    save(P1ROOT / "arms-p1c.json", PROTOCOL["arms"])
    save(
        P1ROOT / "setup-p1c.json",
        {
            "windows": len(windows),
            "selection": CASES,
            "window_records": windows,
            "snapshots": snapshots,
            "budget_before": budget,
            "source_sha256": fingerprint(),
            "model": json.loads((P1ROOT / "setup.json").read_text())["model"],
        },
    )
    print(
        json.dumps(
            {
                "status": "prepared",
                "windows": len(windows),
                "selection": CASES,
                "budget_before": budget,
                "phase_limit": 22,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def execute(phase, limit):
    run(
        P1ROOT,
        phase,
        1,
        limit,
        ["baseline", "tool_first"],
        P1ROOT / "arms-p1c.json",
        "review_strategy",
        case_ids=CASES,
        max_windows_per_side=1,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--phase", default="p1c-tool-first")
    parser.add_argument("--limit", type=int, default=22)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        execute(args.phase, args.limit)


if __name__ == "__main__":
    main()
