"""Development diagnostics with frozen saved plans; never an end-to-end score."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from evaluation.bugsinpy_data import is_production
from src.agents import MeteredLLM, ReviewAgents, load_config
from src.code_index import CodeIndex
from src.report import write_reports
from src.repository import inventory, snapshot_digest
from src.reproduction import (
    DockerExecutor,
    EvidenceEngine,
    contract_documents,
    execution_verdict,
    validate_plan,
)
from src.schemas import Finding, ReproductionPlan, ReviewOptions


ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fingerprint():
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [
            *sorted((ROOT / "src").glob("*.py")),
            ROOT / "main.py",
            Path(__file__),
        ]
    }


def load_saved(batch, case_id, finding_id):
    folder = ROOT / "outputs" / batch
    cases = json.loads((folder / "selection.json").read_text())
    case = next(case for case in cases if case["id"] == case_id)
    work = "bugsinpy-work" if "original20" in batch else "evidence-holdout-work"
    repo = ROOT / "outputs" / work / case["snapshot_paths"]["buggy"]
    report = json.loads(
        (folder / "reviews" / case_id / "evidence/buggy/report.json").read_text()
    )
    finding = next(item for item in report["findings"] if item["id"] == finding_id)
    evidence = finding["reproduction"]
    files, _ = inventory(repo, evidence["scope"], evidence["max_file_bytes"])
    files = {path: source for path, source in files.items() if is_production(path)}
    assert snapshot_digest(files) == evidence["execution_snapshot_sha256"]
    index = CodeIndex(files, contract_documents(repo, evidence["scope"]))
    index.production_only = True
    index.execution_scope = evidence["scope"]
    plan = ReproductionPlan.model_validate(evidence["plan"])
    validate_plan(plan, index)
    fixed = ROOT / "outputs" / work / case["snapshot_paths"]["fixed"]
    fixed_files, _ = inventory(fixed, evidence["scope"], evidence["max_file_bytes"])
    fixed_files = {
        path: source for path, source in fixed_files.items() if is_production(path)
    }
    return report, Finding.model_validate(finding), plan, index, fixed_files


def gate_controls(output):
    destination = output / "gate-controls"
    destination.mkdir(exist_ok=False)
    records = json.loads((output / "baseline-records.json").read_text())
    compared = []
    for record in records:
        report = json.loads(Path(record["report"]).read_text())
        item = next(f for f in report["findings"] if f["id"] == record["finding_id"])
        finding = Finding.model_validate(item)
        files = {finding.path: (Path(record["snapshot"]) / finding.path).read_text()}
        verdict = execution_verdict(item["reproduction"]["attempts"][0], finding, files)
        compared.append({**record, "new_verdict": verdict})
    fresh = []
    for batch, case, finding_id in [
        ("evidence-original20-20261014", "PySnooper-3", "9261f543fc85"),
        ("evidence-new8-20261014", "youtube-dl-12", "9758e8ca5215"),
    ]:
        _, finding, plan, index, fixed_files = load_saved(batch, case, finding_id)
        executor = DockerExecutor(finding.reproduction["attempts"][0]["image_id"])
        for side, files in [("buggy", index.files), ("fixed", fixed_files)]:
            attempt = executor.execute(files, finding, plan.test_code)
            verdict = execution_verdict(attempt, finding, files)
            save(destination / f"{case}-{side}.json", attempt)
            (destination / f"{case}-{side}.log").write_text(attempt["log"])
            fresh.append(
                {
                    "case": case,
                    "side": side,
                    "verdict": verdict,
                    "tests_run": (attempt.get("execution") or {}).get("tests_run"),
                }
            )
    expected = {
        ("PySnooper-3", "buggy"): "failure_observed",
        ("PySnooper-3", "fixed"): "not_reproduced",
        ("youtube-dl-12", "buggy"): "unrelated_failure",
        ("youtube-dl-12", "fixed"): "unrelated_failure",
    }
    assert all(row["verdict"] == expected[row["case"], row["side"]] for row in fresh)
    save(
        destination / "results.json",
        {
            "api_calls": 0,
            "saved_execution_comparison": compared,
            "fresh_docker_controls": fresh,
        },
    )
    print(json.dumps(fresh, ensure_ascii=False), flush=True)


class FrozenPlanAgents:
    def __init__(self, index, llm, plan):
        self.real = ReviewAgents(index, llm)
        self.plan = plan

    def _run(self, stage, prompt, payload):
        if stage == "reproduction_plan":
            return self.plan.model_dump_json()
        return self.real._run(stage, prompt, payload)


def feedback_controls(output):
    load_config()
    llm = MeteredLLM(24, 45)
    report, original, plan, index, fixed_files = load_saved(
        "evidence-original20-20261014",
        "tornado-4",
        "3e533c03160d",
    )
    image = original.reproduction["attempts"][0]["image_id"]
    # The frozen 2026-10-14 plan predates structured requirements. Annotate it
    # once so the current admission gate can run without changing its test.
    plan.contract.expected_outcome = "state_change"
    plan.contract.precondition = (
        "构造10字节临时文件并请求 Range: bytes=-100；httputil doctest 已固定 "
        "bytes=-N 解析为负 start，临时期望文件可读。"
    )
    results = []
    model_config = {
        "model": llm.model,
        "thinking_mode": llm.thinking_mode,
        "temperature": llm.temperature,
        "max_output_tokens": llm.max_tokens,
        "max_calls_total": llm.max_calls,
        "timeout": 45,
    }
    save(output / "feedback-model-config.json", model_config)
    try:
        for repetition in range(1, 4):
            for enabled in [0, 1] if repetition % 2 else [1, 0]:
                assert fingerprint() == json.loads(
                    (output / "implementation.json").read_text()
                )
                start = time.monotonic()
                first_call = len(llm.calls)
                llm.max_calls = min(24, first_call + 8)
                item = original.model_copy(deep=True)
                agents = FrozenPlanAgents(index, llm, plan)
                options = ReviewOptions(
                    mode="evidence",
                    max_calls=8,
                    max_file_bytes=1000000,
                    repro_image=image,
                    max_repro_repairs=enabled,
                )
                engine = EvidenceEngine(index, agents, options)
                engine.validate(item)
                llm.max_calls = 24
                calls = deepcopy(llm.calls[first_call:])
                trial = {
                    "repetition": repetition,
                    "feedback": bool(enabled),
                    "finding_status": item.status,
                    "evidence_status": item.reproduction["status"],
                    "api_calls": len(calls),
                    "execution_count": len(item.reproduction["attempts"]),
                    "seconds": round(time.monotonic() - start, 3),
                    "evaluator_fixed_test_passed": None,
                }
                trial_name = f"trial-{repetition}-feedback-{'on' if enabled else 'off'}"
                trial_dir = output / trial_name
                current = deepcopy(report)
                current["run"].update(
                    status="completed" if item.status == "reproduced" else "partial",
                    model=llm.model,
                    api_calls=len(calls),
                    elapsed_seconds=trial["seconds"],
                    fully_reviewed_files=0,
                    window_review_completed=False,
                    scope_kind="fixed_candidate_diagnostic",
                    options=options.model_dump(),
                    semantic_coverage_percent=0,
                    reviewed_window_chunks=0,
                    total_window_chunks=0,
                    active_findings=int(item.status == "reproduced"),
                    candidate_findings=1,
                    rejected_findings=0,
                    severity_counts={item.severity: 1},
                    status_counts={item.status: 1},
                    usage={
                        key: sum(c.get("usage", {}).get(key, 0) for c in calls)
                        for key in ["prompt_tokens", "completion_tokens"]
                    },
                )
                current.update(
                    findings=[item.model_dump()],
                    calls=calls,
                    failures=[],
                    trace=agents.real.trace,
                    evidence_artifacts=engine.artifacts,
                    coverage=[],
                    excluded=[],
                    stages=[],
                    tool_reads=[],
                )
                current["limitations"] = [
                    "固定已知候选与原始生成计划的开发集诊断，不是Agent独立发现或全仓库审查。",
                    "模型调用只包含本轮修正/核验，原始计划由2026-10-14记录重放。",
                    "两种条件使用同一新执行判定，仅切换一次反馈修正；参考修复仅由评测侧对照。",
                ]
                current["diagnostic_options"] = options.model_dump()
                write_reports(current, trial_dir)
                if item.status == "reproduced":
                    active_plan = item.reproduction["plan"]
                    fixed = DockerExecutor(image).execute(
                        fixed_files, item, active_plan["test_code"]
                    )
                    save(trial_dir / "evaluator-fixed-control.json", fixed)
                    executed = fixed.get("execution") or {}
                    trial["evaluator_fixed_test_passed"] = (
                        executed.get("tests_run") == 1
                        and not executed.get("load_error")
                        and not executed.get("failures")
                        and not executed.get("errors")
                        and not executed.get("skipped")
                    )
                trial["report"] = trial_name + "/report.json"
                results.append(trial)
                save(
                    output / "feedback-results.json",
                    {
                        "config": model_config,
                        "trials": results,
                        "total_api_calls": len(llm.calls),
                        "calls": llm.calls,
                    },
                )
                print(json.dumps(trial, ensure_ascii=False), flush=True)
    finally:
        llm.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["gate", "feedback"], required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    assert (output / "manifest.json").exists(), (
        "Run requires its predeclared manifest and baseline."
    )
    implementation = output / "implementation.json"
    if implementation.exists():
        assert json.loads(implementation.read_text()) == fingerprint(), (
            "Implementation changed; preserve prior results and start a new experiment."
        )
    else:
        save(implementation, fingerprint())
    if args.phase == "gate":
        gate_controls(output)
    else:
        assert not (output / "feedback-results.json").exists(), (
            "Use new output for another sampling."
        )
        feedback_controls(output)


if __name__ == "__main__":
    main()
