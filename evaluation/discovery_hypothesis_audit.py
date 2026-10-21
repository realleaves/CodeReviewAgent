"""P1e smoke: audit the hypothesis-to-candidate promotion step.

P1's youtube-dl-2 trace already contained the duplicate-representation_id
hypothesis with a concrete counterexample, but the finding was not emitted. P1e
adds one completeness audit call after the first hypothesis call and checks
whether the omitted reference candidate is promoted. One case, two windows per
arm, budget 6 (P1 ledger 74/80).
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
    "title": "P1e smoke: hypothesis-to-candidate completeness audit",
    "date": "2026-10-21",
    "kind": "P1e single-variable hypothesis audit; discovery only",
    "hypothesis": (
        "P1's youtube-dl-2 trace formed the reference hypothesis (duplicate "
        "representation_id overwrites fragments) with a concrete counterexample "
        "but did not emit it as a finding. A second completeness audit should "
        "promote that omitted hypothesis without adding vague candidates."
    ),
    "selection": CASES,
    "selection_reason": (
        "The P1 trace contains the reference-adjacent hypothesis at the merge by "
        "representation_id; the case has a known DASH format_id uniqueness "
        "reference. Both sides, one r0 window per side."
    ),
    "arms": {
        "baseline": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "baseline",
        },
        "hypothesis_audit": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "hypothesis_audit",
        },
    },
    "variable": "review_strategy",
    "repetitions": 1,
    "window_call_limit": 3,
    "budget": {"phase_limit": 6, "remaining_after_p1d": 6, "per_window": 3},
    "metrics": [
        "initial vs audit findings and added candidates",
        "reference candidate hit on youtube-dl-2",
        "fixed-side same-issue alarms",
        "completed windows, calls and tokens",
    ],
    "adoption": (
        "The audit adds a concrete DASH format_id/representation_id candidate on "
        "the buggy side, with no fixed-side alarm; otherwise reject. One-case/two-"
        "window smoke is exploratory."
    ),
    "scope": (
        "Discovery only; no evidence engine, official tests/labels/opposite version "
        "in the Agent input. One repetition; all requests, failures and audit "
        "additions retained."
    ),
}


def prepare():
    if (P1ROOT / "p1e-goal.json").exists():
        raise SystemExit("P1e 已经准备过。")
    budget = json.loads((P1ROOT / "budget.json").read_text())
    if budget["reserved"] != 74 or budget["limit"] != 80:
        raise SystemExit("P1 账本不是预期的 74/80，停止。")
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
    save(P1ROOT / "p1e-goal.json", PROTOCOL)
    save(P1ROOT / "arms-p1e.json", PROTOCOL["arms"])
    save(
        P1ROOT / "setup-p1e.json",
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
                "phase_limit": 6,
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
        ["baseline", "hypothesis_audit"],
        P1ROOT / "arms-p1e.json",
        "review_strategy",
        case_ids=CASES,
        max_windows_per_side=1,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--phase", default="p1e-hypothesis-audit")
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        execute(args.phase, args.limit)


if __name__ == "__main__":
    main()
