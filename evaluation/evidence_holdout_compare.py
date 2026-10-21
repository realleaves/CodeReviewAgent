"""Baseline vs structured-admission evidence pilot on four holdout cases.

This is the first evidence-stage run on the 2026-10-20 holdout samples. The
samples were used earlier for discovery-only validation, so they are not fully
unseen; the reference rubric and official tests stay evaluator-side. Both arms
use the same prompt, model, windows and call budget. The only switch is
``ReviewOptions.enforce_admission``: baseline accepts the model audit directly,
admission requires the structured requirement and audit checks.

All provider attempts are reserved before the call and retained. The run does
not use reference labels or official tests in the Agent input.
"""

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.bugsinpy_review import run_scoped_review
from evaluation.discovery_experiment import AttemptBudget, RecordedLLM, digest, save
from src.agents import MeteredLLM, load_config
from src.report import write_reports
from src.schemas import ReviewOptions


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "outputs/discovery-goal-20261015/holdout-work"
OFFICIAL = ROOT / "outputs/discovery-goal-20261015/holdout-reproduction/results.json"
REFERENCE = (
    ROOT / "outputs/discovery-goal-20261015/holdout-freeze/reference-rubric.json"
)
IMAGE = "sha256:a255ffcb469f2ec40f2958a76beb0c2bbebfe92ce9af67a9b48d84b4cb695ac8"
ARMS = {"baseline": False, "admission": True}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def fingerprint():
    paths = [
        *sorted((ROOT / "src").glob("*.py")),
        ROOT / "main.py",
        Path(__file__),
        ROOT / "evaluation/bugsinpy_review.py",
        ROOT / "evaluation/bugsinpy_data.py",
        ROOT / "evaluation/discovery_experiment.py",
        ROOT / "evaluation/bugsinpy_score.py",
    ]
    return {str(path.relative_to(ROOT)): digest(path) for path in paths}


def compact_findings(report):
    rows = []
    for finding in report["findings"]:
        reproduction = finding.get("reproduction") or {}
        plan = reproduction.get("plan") or {}
        contract = plan.get("contract") or {}
        rows.append(
            {
                "id": finding["id"],
                "path": finding["path"],
                "line": finding["line"],
                "end_line": finding["end_line"],
                "title": finding["title"],
                "category": finding["category"],
                "status": finding["status"],
                "source": finding["source"],
                "evidence_status": reproduction.get("status"),
                "evidence_reason": reproduction.get("reason"),
                "plan_kind": contract.get("kind"),
                "expected_outcome": contract.get("expected_outcome"),
                "expected_exception": contract.get("expected_exception"),
                "admission": reproduction.get("admission"),
                "attempt_verdicts": [
                    attempt.get("verdict")
                    for attempt in reproduction.get("attempts", [])
                ],
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/evidence-holdout-compare-20261021",
    )
    parser.add_argument("--limit", type=int, default=140)
    parser.add_argument("--max-calls", type=int, default=8)
    parser.add_argument("--max-reproductions", type=int, default=2)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        parser.error("输出目录必须是不存在的新路径。")
    if args.limit < 1 or args.max_calls < 1 or args.max_reproductions < 1:
        parser.error("预算必须为正数。")
    root.mkdir(parents=True)
    cases = json.loads((WORK / "prepared.json").read_text())
    official_rows = json.loads(OFFICIAL.read_text())
    official = {row["case"]: row for row in official_rows}
    assert set(official) == {case["id"] for case in cases}
    assert all(row["status"] == "reproduced" for row in official_rows)
    reference = json.loads(REFERENCE.read_text())
    assert set(reference["issues"]) == set(official)
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
    frozen = fingerprint()
    save(
        root / "protocol.json",
        {
            "created_at": timestamp(),
            "kind": "evidence-stage pilot on the 2026-10-20 holdout; reuse of discovery samples",
            "selection": [case["id"] for case in cases],
            "arms": ARMS,
            "model": model,
            "budget": {
                "limit": args.limit,
                "per_run": args.max_calls,
                "max_reproductions": args.max_reproductions,
            },
            "image": IMAGE,
            "source_sha256": frozen,
            "official": {
                "path": "outputs/discovery-goal-20261015/holdout-reproduction/results.json",
                "status": {case: row["status"] for case, row in official.items()},
            },
            "reference": {
                "path": "outputs/discovery-goal-20261015/holdout-freeze/reference-rubric.json",
                "sha256": digest(REFERENCE),
            },
            "protocol": (
                "Same prompt, model, production-only windows and per-run budget in both arms; "
                "only ReviewOptions.enforce_admission differs. Baseline accepts the model audit "
                "directly; admission requires requirement_gate and audit_gate. Official tests and "
                "reference labels are evaluator-only. All planned runs, failures and provider "
                "attempts are retained. No repetition and no new-sample claim beyond these 4 cases."
            ),
            "scoring": (
                "A reference hit requires a reproduced Agent finding matching the frozen reference "
                "cause and trigger. Extra findings are separate. Candidate identification without "
                "reproduced evidence is reported separately."
            ),
        },
    )
    for relative in frozen:
        target = root / "implementation" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    shutil.copy2(REFERENCE, root / "reference-rubric.json")
    save(root / "official.json", official)
    save(
        root / "budget.json",
        {"limit": args.limit, "reserved": 0, "phases": {}, "started_at": timestamp()},
    )
    budget = AttemptBudget(root)
    rows = []
    save(root / "results.json", {"status": "running", "records": rows})
    index = 0
    for case in cases:
        for side in ["buggy", "fixed"]:
            arms = (
                ["baseline", "admission"]
                if index % 2 == 0
                else ["admission", "baseline"]
            )
            index += 1
            for arm in arms:
                assert fingerprint() == frozen, "采样期间源码发生变化。"
                label = {"case": case["id"], "arm": arm, "side": side}
                if budget.state()["reserved"] >= args.limit:
                    row = {
                        **label,
                        "status": "budget_exhausted",
                        "api_calls": 0,
                        "error": "全局预算已耗尽，未启动。",
                    }
                    rows.append(row)
                    save(root / "results.json", {"status": "running", "records": rows})
                    continue
                run_dir = root / "runs" / case["id"] / arm / side
                request_dir = root / "requests" / case["id"] / arm / side
                request_dir.mkdir(parents=True, exist_ok=True)
                llm = RecordedLLM(
                    budget,
                    "evidence-holdout-compare",
                    args.limit,
                    request_dir,
                    label,
                    max_calls=args.max_calls,
                )
                llm.thinking_mode = model["thinking_mode"]
                llm.max_tokens = model["max_output_tokens"]
                assert llm.model == model["model"]
                options = ReviewOptions(
                    mode="evidence",
                    max_calls=args.max_calls,
                    max_file_bytes=1_000_000,
                    repro_image=IMAGE,
                    max_reproductions=args.max_reproductions,
                    max_repro_repairs=0,
                    context_strategy="legacy",
                    enforce_admission=ARMS[arm],
                )
                regions = {
                    path: hunks[side]
                    for path, hunks in case["production_hunks"].items()
                }
                started = timestamp()
                report, error = None, None
                try:
                    with redirect_stdout(io.StringIO()):
                        report = run_scoped_review(
                            WORK / case["snapshot_paths"][side],
                            regions,
                            "evidence",
                            args.max_calls,
                            timeout=45,
                            llm=llm,
                            progress=lambda message: print(message, file=sys.stderr),
                            evidence_options=options,
                        )
                except Exception as exc:
                    error = {"type": type(exc).__name__, "message": str(exc)[:300]}
                finally:
                    llm.close()
                calls = list(llm.calls)
                if report is not None:
                    write_reports(report, run_dir)
                    findings = compact_findings(report)
                    status = report["run"]["status"]
                    window_completed = report["run"]["window_review_completed"]
                    usage = report["run"]["usage"]
                    reproduced = sum(
                        finding["status"] == "reproduced" for finding in findings
                    )
                    pending = sum(
                        finding["status"] == "pending_evidence" for finding in findings
                    )
                else:
                    findings = []
                    status = "failed"
                    window_completed = False
                    usage = {
                        key: sum(call.get("usage", {}).get(key, 0) for call in calls)
                        for key in ["prompt_tokens", "completion_tokens"]
                    }
                    reproduced = 0
                    pending = 0
                save(run_dir / "findings.json", findings)
                save(run_dir / "calls.json", calls)
                row = {
                    **label,
                    "status": status,
                    "window_review_completed": window_completed,
                    "api_calls": len(calls),
                    "usage": usage,
                    "reproduced_findings": reproduced,
                    "pending_findings": pending,
                    "findings": findings,
                    "official_reproduction": official[case["id"]]["status"],
                    "error": error,
                    "started_at": started,
                    "finished_at": timestamp(),
                    "report": str(run_dir.relative_to(root) / "report.json"),
                }
                rows.append(row)
                save(
                    root / "results.json",
                    {"status": "running", "records": rows, "budget": budget.state()},
                )
                print(
                    json.dumps(
                        {
                            **label,
                            "status": status,
                            "window_completed": window_completed,
                            "calls": len(calls),
                            "reproduced": reproduced,
                            "pending": pending,
                            "global_used": budget.state()["reserved"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    assert fingerprint() == frozen, "采样期间源码发生变化。"
    save(
        root / "results.json",
        {"status": "sampled", "records": rows, "budget": budget.state()},
    )
    summary = {
        "status": "sampled",
        "cases": len(cases),
        "runs": len(rows),
        "api_calls": budget.state()["reserved"],
        "budget": budget.state(),
        "by_arm": {
            arm: {
                "runs": sum(row.get("arm") == arm for row in rows),
                "completed_windows": sum(
                    row.get("arm") == arm and row.get("window_review_completed") is True
                    for row in rows
                ),
                "api_calls": sum(
                    row.get("api_calls", 0) for row in rows if row.get("arm") == arm
                ),
                "reproduced_findings": sum(
                    row.get("reproduced_findings", 0)
                    for row in rows
                    if row.get("arm") == arm
                ),
                "pending_findings": sum(
                    row.get("pending_findings", 0)
                    for row in rows
                    if row.get("arm") == arm
                ),
            }
            for arm in ARMS
        },
        "scope": "4 discovery-holdout cases; first evidence-stage run; one repetition; not a fully unseen or full-repo benchmark",
        "source_frozen": True,
    }
    save(root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
