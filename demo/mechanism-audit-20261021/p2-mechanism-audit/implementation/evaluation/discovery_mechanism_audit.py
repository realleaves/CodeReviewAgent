"""P2 mechanism/ranking audit protocol and runner (not run by prepare).

P2 changes one thing versus P1: after the first hypothesis pass, a second audit
must compare candidate mechanisms and REPLACE a weaker/adjacent finding with a
more specific hypothesis. It does not add tools, external reads, or reference
labels. Prepare writes a new 20-call ledger; run is intentionally separate.
"""

import argparse
from contextlib import redirect_stdout
from pathlib import Path
import io
import json
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.bugsinpy_review import reviewer_files
from evaluation.discovery_experiment import fingerprint, run, save
from src.repository import snapshot_digest
from src.agents import MeteredLLM, load_config


ROOT = Path(__file__).resolve().parents[1]
P1ROOT = ROOT / "outputs/hypothesis-discovery-20261021"
P2ROOT = ROOT / "outputs/mechanism-audit-20261021"
PREVIEW = ROOT / "outputs/context-callgraph-20261015/preview-final"
CASES = ["youtube-dl-2", "tornado-3"]
SNAPSHOTS = ROOT / "outputs/bugsinpy-work"

PROTOCOL = {
    "title": "P2 smoke: candidate mechanism/ranking audit",
    "date": "2026-10-21",
    "kind": "P2 single-variable candidate replacement audit; discovery only",
    "hypothesis": (
        "The P1 trace analysis found 1 promotion gap and 3 precision gaps: the "
        "reference concept was already in the reasoning/findings, but the model "
        "selected a weaker or adjacent mechanism. A second audit that maps each "
        "finding to a hypothesis and replaces it with a more specific mechanism "
        "should improve candidate precision without adding tools or reference labels."
    ),
    "selection": CASES,
    "selection_reason": (
        "youtube-dl-2 is the clearest promotion gap (duplicate representation_id "
        "overwrites fragments was already hypothesized but not emitted); tornado-3 "
        "is a precision gap (cache/close present, but the candidate chose __new__). "
        "Both sides, one r0 window per side."
    ),
    "arms": {
        "baseline": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "baseline",
        },
        "mechanism_audit": {
            "context_strategy": "legacy",
            "thinking_mode": "disabled",
            "review_strategy": "mechanism_audit",
        },
    },
    "variable": "review_strategy",
    "repetitions": 1,
    "window_call_limit": 3,
    "budget": {"phase_limit": 20, "total_limit": 20, "per_window": 3},
    "metrics": [
        "reference candidate hit on the two cases",
        "findings replaced/added by the audit",
        "fixed-side same-issue alarms",
        "completed/failed windows, calls and tokens",
    ],
    "adoption": (
        "At least one reference candidate hit in mechanism_audit on youtube-dl-2 "
        "or tornado-3, with no fixed-side alarm; a four-window smoke only, not a "
        "general improvement claim."
    ),
    "scope": (
        "Discovery only; no evidence engine, official tests/labels/opposite version "
        "in the Agent input. One repetition; all requests, failures, replacements "
        "and fallbacks retained. The audit prompt contains no reference labels."
    ),
}


def prepare():
    if (P2ROOT / "p2-goal.json").exists():
        raise SystemExit("P2 已经准备过。")
    P2ROOT.mkdir(parents=True, exist_ok=True)
    for name in ["protected.json", "reference-rubric.json"]:
        source = P1ROOT / name
        if not source.exists():
            raise SystemExit(f"缺少 {source}，不能建立 P2 账本。")
        shutil.copy2(source, P2ROOT / name)
    windows = [
        row
        for row in json.loads((PREVIEW / "results.json").read_text())["records"]
        if row["case"] in CASES
    ]
    assert len(windows) == 4
    assert {row["case"] for row in windows} == set(CASES)
    cases = {
        item["id"]: item
        for item in json.loads(
            (ROOT / "outputs/evidence-original20-20261014/selection.json").read_text()
        )
        if item["id"] in CASES
    }
    snapshots = {}
    for case_id, case in cases.items():
        for side in ["buggy", "fixed"]:
            files, _ = reviewer_files(SNAPSHOTS / case["snapshot_paths"][side])
            snapshots[f"{case_id}/{side}"] = {
                "files": len(files),
                "snapshot_sha256": snapshot_digest(files),
            }
    save(P2ROOT / "budget.json", {"limit": 20, "reserved": 0, "phases": {}})
    save(P2ROOT / "p2-goal.json", PROTOCOL)
    save(P2ROOT / "arms-p2.json", PROTOCOL["arms"])
    save(
        P2ROOT / "setup-p2.json",
        {
            "windows": len(windows),
            "selection": CASES,
            "window_records": windows,
            "snapshots": snapshots,
            "source_sha256": fingerprint(),
            "model": json.loads((P1ROOT / "setup.json").read_text())["model"],
        },
    )
    print(
        json.dumps(
            {
                "status": "prepared_not_run",
                "windows": len(windows),
                "selection": CASES,
                "budget": {"limit": 20, "reserved": 0},
                "phase_limit": 20,
                "api_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def execute(phase, limit):
    # Validate the already-prepared protocol; never prepare or reset a ledger here.
    if phase != "p2-mechanism-audit" or limit != 20:
        raise SystemExit("P2 smoke 的 phase/limit 已冻结；更改需另写协议。")
    budget = json.loads((P2ROOT / "budget.json").read_text())
    if budget != {"limit": 20, "reserved": 0, "phases": {}}:
        raise SystemExit("P2 账本不是未启动的 0/20；停止，不重置或退款。")
    setup = json.loads((P2ROOT / "setup-p2.json").read_text())
    assert json.loads((P2ROOT / "p2-goal.json").read_text()) == PROTOCOL
    assert json.loads((P2ROOT / "arms-p2.json").read_text()) == PROTOCOL["arms"]
    assert fingerprint() == setup["source_sha256"], "P2 源码与准备快照不一致。"
    load_config()
    with redirect_stdout(io.StringIO()):
        probe = MeteredLLM(1, 45)
    try:
        actual_model = {
            "model": probe.model,
            "thinking_mode": probe.thinking_mode,
            "temperature": probe.temperature,
            "max_output_tokens": probe.max_tokens,
            "provider_is_deepseek": probe.is_deepseek,
        }
        assert actual_model == setup["model"], "P2 模型配置与协议不一致。"
    finally:
        probe.close()
    run(
        P2ROOT,
        phase,
        1,
        limit,
        ["baseline", "mechanism_audit"],
        P2ROOT / "arms-p2.json",
        "review_strategy",
        case_ids=CASES,
        max_windows_per_side=1,
        stop_on_provider_error=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--phase", default="p2-mechanism-audit")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        execute(args.phase, args.limit)


if __name__ == "__main__":
    main()
