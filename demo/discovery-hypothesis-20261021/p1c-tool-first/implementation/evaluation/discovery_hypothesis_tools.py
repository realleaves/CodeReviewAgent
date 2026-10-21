"""P1b smoke: require real tool evidence in the hypothesis-first discovery.

The P1 prompt allowed the model to write ``checked`` entries without calling a
tool. P1b adds ``hypothesis_tools``: if the first hypothesis response performs no
read-only tool call, one bounded retry asks for a real read; if the retry still
performs none, findings are dropped and the trace records the reason.

This is a 3-case, one-window-per-side smoke against the frozen P1 budget. It is
not a full development or holdout score.
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
CASES = ["tornado-3", "youtube-dl-4", "youtube-dl-8"]
SNAPSHOTS = ROOT / "outputs/bugsinpy-work"

PROTOCOL = {
    "title": "P1b smoke: hypothesis-first with enforced tool evidence",
    "date": "2026-10-21",
    "kind": "P1b single-variable tool-evidence enforcement; discovery only",
    "hypothesis": (
        "P1 failed because checked was self-reported and the hypothesis arm made "
        "zero real tool reads. Requiring one real read (with one bounded retry) "
        "should increase tool use and recover or maintain candidate recall; if the "
        "retry still reads nothing, findings must be dropped rather than trusted."
    ),
    "selection": CASES,
    "selection_reason": (
        "One no-candidate case (tornado-3), the baseline candidate hit "
        "(youtube-dl-4), and an off-target case (youtube-dl-8); both sides, one r0 "
        "window per side, six windows per arm."
    ),
    "arms": {
        "baseline": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "baseline",
        },
        "hypothesis_tools": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "hypothesis_tools",
        },
    },
    "variable": "review_strategy",
    "repetitions": 1,
    "window_call_limit": 3,
    "budget": {"phase_limit": 41, "remaining_after_p1": 41, "per_window": 3},
    "metrics": [
        "reference candidate recall on the 3 cases",
        "real tool reads and bounded retries",
        "findings dropped for missing tool evidence",
        "fixed-side same-issue alarms",
        "completed windows, calls and tokens",
    ],
    "adoption": (
        "At least one more candidate hit than baseline with real tool reads and no "
        "fixed-side alarm; or, at minimum, restore the youtube-dl-4 hit while "
        "adding real reads. A six-window smoke is exploratory; a gain requires the "
        "full 18-window development set and a repeat before adoption."
    ),
    "scope": (
        "Discovery only; no evidence engine, official tests/labels/opposite version "
        "in the Agent input. One repetition; all requests, failures and dropped "
        "findings retained."
    ),
}


def prepare():
    if (P1ROOT / "p1b-goal.json").exists():
        raise SystemExit("P1b 已经准备过。")
    budget = json.loads((P1ROOT / "budget.json").read_text())
    if budget["reserved"] != 39 or budget["limit"] != 80:
        raise SystemExit("P1 账本不是预期的 39/80，停止。")
    windows = [
        row
        for row in json.loads((PREVIEW / "results.json").read_text())["records"]
        if row["case"] in CASES
    ]
    assert len(windows) == 6
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
    save(P1ROOT / "p1b-goal.json", PROTOCOL)
    save(P1ROOT / "arms-p1b.json", PROTOCOL["arms"])
    save(
        P1ROOT / "setup-p1b.json",
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
                "phase_limit": 41,
                "source_sha256": fingerprint(),
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
        ["baseline", "hypothesis_tools"],
        P1ROOT / "arms-p1b.json",
        "review_strategy",
        case_ids=CASES,
        max_windows_per_side=1,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--phase", default="p1b-tools")
    parser.add_argument("--limit", type=int, default=41)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        execute(args.phase, args.limit)


if __name__ == "__main__":
    main()
