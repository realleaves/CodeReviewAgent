"""Seen-sample control for the structured expectation admission gate.

This is a diagnostic, not a new benchmark. It loads the frozen 2026-10-14
candidates, lets the current model generate a fresh reproduction plan under the
current prompt, runs the two-container evidence check, and records whether the
deterministic and audit admission gates keep or downgrade the candidate.

Historical old-gate outcomes (all four were reproduced) are saved as reference,
but they are not a fresh paired baseline: the old plans used an older prompt and
are not resampled. All provider attempts are reserved before the call and are
never refunded. Official tests and reference labels are not used.
"""

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.bugsinpy_data import is_production
from evaluation.discovery_experiment import AttemptBudget, RecordedLLM, digest, save
from src.agents import MeteredLLM, ReviewAgents, load_config
from src.code_index import CodeIndex
from src.reproduction import DockerExecutor, EvidenceEngine, contract_documents
from src.repository import inventory, snapshot_digest
from src.schemas import Finding, ReviewOptions


ROOT = Path(__file__).resolve().parents[1]
RETEST = ROOT / "demo/evidence-retest13-20261015/results.json"

CASES = [
    {
        "id": "PySnooper-3",
        "finding_id": "9261f543fc85",
        "historical": "reproduced",
        "role": "documented positive: output_path must write the log file",
    },
    {
        "id": "tornado-1-fixed",
        "finding_id": "2cd97d34b1a2",
        "historical": "reproduced",
        "role": "negative: KeyError observed, ValueError requested by language rule",
    },
    {
        "id": "youtube-dl-4-fixed",
        "finding_id": "791eec547d5f",
        "historical": "reproduced",
        "role": "negative: ValueError observed, ExtractorError requested by language rule",
    },
    {
        "id": "youtube-dl-8-buggy",
        "finding_id": "248543bf3d91",
        "historical": "reproduced",
        "role": "negative: AttributeError observed, SyntaxError requested by language rule",
    },
]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def fingerprint():
    paths = [
        *sorted((ROOT / "src").glob("*.py")),
        ROOT / "main.py",
        Path(__file__),
        ROOT / "evaluation/bugsinpy_data.py",
        ROOT / "evaluation/discovery_experiment.py",
    ]
    return {str(path.relative_to(ROOT)): digest(path) for path in paths}


def load_case(case):
    records = json.loads(RETEST.read_text())["records"]
    record = next(item for item in records if item["finding_id"] == case["finding_id"])
    report = json.loads(Path(record["report"]).read_text())
    finding = Finding.model_validate(
        next(item for item in report["findings"] if item["id"] == case["finding_id"])
    )
    evidence = finding.reproduction
    snapshot = Path(record["snapshot"]).resolve()
    files, _ = inventory(snapshot, evidence["scope"], evidence["max_file_bytes"])
    files = {path: source for path, source in files.items() if is_production(path)}
    if snapshot_digest(files) != evidence["execution_snapshot_sha256"]:
        raise ValueError(f"{case['id']} 的源码快照与冻结证据不一致。")
    index = CodeIndex(files, contract_documents(snapshot, evidence["scope"]))
    index.production_only = True
    index.execution_scope = evidence["scope"]
    image = evidence["attempts"][0]["image_id"]
    return record, finding, index, image


def run_case(root, budget, phase_limit, case, model_config):
    destination = root / "cases" / case["id"]
    destination.mkdir(parents=True, exist_ok=False)
    record, finding, index, image = load_case(case)
    historical = {
        "finding_status": finding.status,
        "evidence_status": (finding.reproduction or {}).get("status"),
        "plan_kind": (
            (finding.reproduction or {}).get("plan", {}).get("contract") or {}
        ).get("kind"),
        "plan_outcome": (
            (finding.reproduction or {}).get("plan", {}).get("contract") or {}
        ).get("expected_outcome"),
    }
    save(destination / "historical.json", historical)
    llm = RecordedLLM(
        budget,
        "admission-controls",
        phase_limit,
        destination,
        {"case": case["id"], "finding_id": case["finding_id"]},
    )
    llm.max_calls = 6
    llm.thinking_mode = model_config["thinking_mode"]
    llm.max_tokens = model_config["max_output_tokens"]
    assert llm.model == model_config["model"]
    started = timestamp()
    error = None
    with redirect_stdout(io.StringIO()):
        agents = ReviewAgents(index, llm, "legacy")
    options = ReviewOptions(
        mode="evidence",
        max_calls=6,
        max_file_bytes=1000000,
        repro_image=image,
        max_reproductions=1,
        max_repro_repairs=0,
        context_strategy="legacy",
    )
    engine = EvidenceEngine(index, agents, options, executor=DockerExecutor(image, 15))
    try:
        engine.validate(finding)
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)[:300]}
    finally:
        llm.close()
    artifacts = {}
    for relative, content in engine.artifacts.items():
        target = destination / "artifacts" / relative
        if ".." in Path(relative).parts or Path(relative).is_absolute():
            raise ValueError("证据附件路径不合法。")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        artifacts[relative] = hashlib.sha256(content.encode()).hexdigest()
    save(destination / "finding.json", finding.model_dump())
    save(destination / "calls.json", llm.calls)
    save(destination / "trace.json", agents.trace)
    reproduction = finding.reproduction or {}
    plan = reproduction.get("plan") or {}
    contract = plan.get("contract") or {}
    usage = {
        key: sum(call.get("usage", {}).get(key, 0) for call in llm.calls)
        for key in ["prompt_tokens", "completion_tokens"]
    }
    row = {
        "case": case["id"],
        "finding_id": case["finding_id"],
        "role": case["role"],
        "historical": historical,
        "current": {
            "finding_status": finding.status,
            "evidence_status": reproduction.get("status"),
            "reason": reproduction.get("reason"),
            "plan_kind": contract.get("kind"),
            "expected_outcome": contract.get("expected_outcome"),
            "expected_exception": contract.get("expected_exception"),
            "precondition": contract.get("precondition"),
            "admission": reproduction.get("admission"),
            "audit": reproduction.get("audit"),
            "attempt_verdicts": [
                a.get("verdict") for a in reproduction.get("attempts", [])
            ],
            "generation_attempts": len(reproduction.get("generation_attempts", [])),
        },
        "image_id": image,
        "api_calls": len(llm.calls),
        "usage": usage,
        "error": error,
        "started_at": started,
        "finished_at": timestamp(),
        "artifacts": artifacts,
        "record_report": record["report"],
        "record_snapshot": record["snapshot"],
    }
    save(destination / "result.json", row)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/admission-validation-20261021",
    )
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--cases", nargs="*", default=[case["id"] for case in CASES])
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        parser.error("输出目录必须是不存在的新路径。")
    selected = [case for case in CASES if case["id"] in args.cases]
    if not selected:
        parser.error("没有匹配的固定案例。")
    root.mkdir(parents=True)
    load_config()
    with redirect_stdout(io.StringIO()):
        probe = MeteredLLM(1, 45)
    model_config = {
        "model": probe.model,
        "thinking_mode": probe.thinking_mode,
        "temperature": probe.temperature,
        "max_output_tokens": probe.max_tokens,
        "provider_is_deepseek": probe.is_deepseek,
    }
    probe.close()
    assert model_config["provider_is_deepseek"], "固定案例只使用已授权的 DeepSeek。"
    assert model_config["temperature"] == 0.1, "固定案例要求 temperature=0.1。"
    assert model_config["max_output_tokens"] == 6000
    frozen = fingerprint()
    save(
        root / "protocol.json",
        {
            "created_at": timestamp(),
            "kind": "seen-sample admission diagnostic; no fresh baseline arm",
            "cases": selected,
            "budget": {"limit": args.limit, "per_case": 6},
            "model": model_config,
            "source_sha256": frozen,
            "protocol": (
                "Load the frozen 2026-10-14 candidate and snapshot; let the current model "
                "generate a fresh plan and test under the current prompt; run two isolated "
                "containers; apply requirement_gate then audit_gate. Official tests, reference "
                "labels and the opposite version are never given to the Agent. Historical old-gate "
                "outcomes are reference only, not a resampled paired baseline. Every provider "
                "attempt is reserved before the call and retained."
            ),
            "reference": "Historical old gate accepted all selected cases; new gate is expected to keep the documented PySnooper-3 positive and downgrade the three language-rule negatives if the same requirement kind is produced.",
        },
    )
    for relative in frozen:
        target = root / "implementation" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    save(
        root / "budget.json",
        {"limit": args.limit, "reserved": 0, "phases": {}, "started_at": timestamp()},
    )
    budget = AttemptBudget(root)
    rows = []
    save(root / "results.json", {"status": "running", "records": rows})
    for case in selected:
        assert fingerprint() == frozen, "采样期间源码发生变化。"
        try:
            row = run_case(root, budget, args.limit, case, model_config)
        except Exception as exc:
            row = {
                "case": case["id"],
                "finding_id": case["finding_id"],
                "role": case["role"],
                "error": {"type": type(exc).__name__, "message": str(exc)[:300]},
                "api_calls": 0,
            }
        rows.append(row)
        save(
            root / "results.json",
            {"status": "running", "records": rows, "budget": budget.state()},
        )
        print(json.dumps(row, ensure_ascii=False), flush=True)
    assert fingerprint() == frozen, "采样期间源码发生变化。"
    positive = [row for row in rows if row["case"] == "PySnooper-3"]
    negatives = [row for row in rows if row["case"] != "PySnooper-3"]
    incomplete = [row["case"] for row in rows if "current" not in row]
    summary = {
        "status": "sampled",
        "cases": len(rows),
        "api_calls": budget.state()["reserved"],
        "budget": budget.state(),
        "positive": positive,
        "negatives": negatives,
        "incomplete": incomplete,
        "positive_reproduced": bool(
            positive
            and "current" in positive[0]
            and positive[0]["current"].get("finding_status") == "reproduced"
        ),
        "negatives_downgraded": not incomplete
        and all(
            row.get("current", {}).get("finding_status") != "reproduced"
            for row in negatives
        ),
        "admission_observed": {
            row["case"]: row.get("current", {}).get("admission") for row in rows
        },
        "scope": "seen fixed candidates; model-generated plans only; no official tests/labels; not a new-sample or full-repo score",
        "source_frozen": True,
    }
    save(root / "summary.json", summary)
    save(
        root / "results.json",
        {"status": "sampled", "records": rows, "budget": budget.state()},
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
