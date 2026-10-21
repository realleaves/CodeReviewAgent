"""P1d smoke: external-read plan selected by the static call context.

P1c forced real tool use but the model still chose local ranges. P1d removes
model read selection: the static call context picks up to three external spans
(caller/callee/enclosing), code reads them, and only then the hypothesis stage
runs. One case (youtube-dl-2), both sides, two windows per arm, budget 10.
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
CASES = ["youtube-dl-2"]
SNAPSHOTS = ROOT / "outputs/bugsinpy-work"

PROTOCOL = {
    "title": "P1d smoke: static external-read plan",
    "date": "2026-10-21",
    "kind": "P1d single-variable external-read selection; discovery only",
    "hypothesis": (
        "P1c achieved real tool use but the model chose local ranges. Selecting "
        "external caller/callee/enclosing spans with the static call context, and "
        "reading them before the hypothesis stage, should expose the DASH "
        "format_id/data-source relation that the model missed. If the candidate "
        "still does not match, external read selection is not the bottleneck."
    ),
    "selection": CASES,
    "selection_reason": (
        "youtube-dl-2 has a static caller (_extract_mpd_formats), callees and an "
        "enclosing definition, and the reference issue is a DASH format_id "
        "uniqueness/merge relation rather than a single local line. Both sides, "
        "one r0 window per side."
    ),
    "arms": {
        "baseline": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "baseline",
        },
        "tool_first_external": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "tool_first_external",
        },
    },
    "variable": "review_strategy",
    "repetitions": 1,
    "window_call_limit": 3,
    "budget": {"phase_limit": 10, "remaining_after_p1c": 10, "per_window": 3},
    "metrics": [
        "external spans selected and actually read",
        "reference candidate recall on youtube-dl-2",
        "fixed-side same-issue alarms",
        "completed/failed windows, calls and tokens",
    ],
    "adoption": (
        "A strict reference candidate hit, or a clearly closer root-cause candidate "
        "with the correct DASH format_id/merge trigger, with no fixed-side alarm; "
        "otherwise reject. One-case/two-window smoke is exploratory."
    ),
    "scope": (
        "Discovery only; no evidence engine, official tests/labels/opposite version "
        "in the Agent input. One repetition; all requests, failures and no-span "
        "windows retained."
    ),
}


def prepare():
    if (P1ROOT / "p1d-goal.json").exists():
        raise SystemExit("P1d 已经准备过。")
    budget = json.loads((P1ROOT / "budget.json").read_text())
    if budget["reserved"] != 70 or budget["limit"] != 80:
        raise SystemExit("P1 账本不是预期的 70/80，停止。")
    windows = [
        row
        for row in json.loads((PREVIEW / "results.json").read_text())["records"]
        if row["case"] in CASES
    ]
    assert len(windows) == 2
    case = next(
        item
        for item in json.loads(
            (ROOT / "outputs/evidence-original20-20261014/selection.json").read_text()
        )
        if item["id"] == CASES[0]
    )
    snapshots = {}
    for side in ["buggy", "fixed"]:
        files, _ = reviewer_files(SNAPSHOTS / case["snapshot_paths"][side])
        snapshots[f"{case['id']}/{side}"] = {
            "files": len(files),
            "snapshot_sha256": snapshot_digest(files),
        }
    save(P1ROOT / "p1d-goal.json", PROTOCOL)
    save(P1ROOT / "arms-p1d.json", PROTOCOL["arms"])
    save(
        P1ROOT / "setup-p1d.json",
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
                "phase_limit": 10,
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
        ["baseline", "tool_first_external"],
        P1ROOT / "arms-p1d.json",
        "review_strategy",
        case_ids=CASES,
        max_windows_per_side=1,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--phase", default="p1d-tool-external")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        execute(args.phase, args.limit)


if __name__ == "__main__":
    main()
