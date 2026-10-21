"""Validate the frozen exploratory thinking signal on preselected unseen cases."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import time

from evaluation.bugsinpy_data import windows
from evaluation.bugsinpy_review import reviewer_files
from evaluation.discovery_experiment import (
    AttemptBudget, RecordedLLM, digest, now, save,
)
from src.agents import MeteredLLM, ReviewAgents, load_config
from src.code_index import Chunk, CodeIndex, chunks, numbered
from src.repository import snapshot_digest


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "outputs/discovery-goal-20261015"


def main():
    freeze = EXPERIMENT / "holdout-freeze"
    decision = json.loads((freeze / "decision.json").read_text())
    for relative, hashed in decision["source_sha256"].items():
        assert digest(ROOT / relative) == hashed
    phase = EXPERIMENT / "v-holdout"
    phase.mkdir(exist_ok=False)
    work = EXPERIMENT / "holdout-work"
    cases = json.loads((work / "prepared.json").read_text())
    assert [c["id"] for c in cases] == decision["selection"]
    snapshots, originals, source_hashes = {}, [], {}
    for case in cases:
        for side in ["buggy", "fixed"]:
            files, _ = reviewer_files(work / case["snapshot_paths"][side])
            snapshots[case["id"], side] = files
            source_hashes[case["id"] + "/" + side] = snapshot_digest(files)
            ordinal = 0
            for path, hunks in sorted(case["production_hunks"].items()):
                for low, high in windows(files[path], hunks[side]):
                    text = "\n".join(files[path].splitlines()[low - 1:high])
                    for part in chunks(path, text, 180, 20000):
                        ordinal += 1
                        originals.append({
                            "case": case["id"], "side": side, "path": path,
                            "start": low + part.start - 1,
                            "end": low + part.end - 1,
                            "folder": f"{case['id']}-{side}-{ordinal}",
                        })
    arms = list(decision["arms"])
    repetitions = 2 if len(originals) * len(arms) * 2 * 3 <= 192 else 1
    assert len(originals) * len(arms) * repetitions * 3 <= 192
    frozen = dict(decision["source_sha256"])
    frozen[str(Path(__file__).relative_to(ROOT))] = digest(Path(__file__))
    rubric = json.loads((freeze / "reference-rubric.json").read_text())
    assert set(rubric["issues"]) == set(decision["selection"])
    protected = {
        str(p.relative_to(ROOT)): digest(p)
        for p in [freeze / "reference-rubric.json", freeze / "decision.json",
                  ROOT / "evaluation/bugsinpy_score.py"]
    }
    load_config()
    with redirect_stdout(io.StringIO()):
        probe = MeteredLLM(1, 45)
    assert probe.is_deepseek
    model = {"model": probe.model, "temperature": probe.temperature,
             "timeout_seconds": 45, "max_output_tokens": probe.max_tokens,
             "provider_is_deepseek": probe.is_deepseek}
    assert model["max_output_tokens"] == 6000 and model["temperature"] == 0.1
    probe.close()
    save(phase / "manifest.json", {
        "created_at": now(), "kind": "unseen validation, not third improvement",
        "source_sha256": frozen, "protected_sha256": protected,
        "dataset_commit": json.loads((work / "manifest.json").read_text())["dataset_commit"],
        "snapshots_sha256": source_hashes,
        "selection": decision["selection"], "model": model,
        "strategies": arms, "arms": decision["arms"],
        "comparison_variable": "thinking_mode", "input_windows": originals,
        "repetitions": repetitions, "window_call_limit": 3,
        "phase_call_limit": 192, "global_limit": 600,
        "rubric_sha256": digest(freeze / "reference-rubric.json"),
        "protocol": "Fresh independent discovery windows, production-only sources, no tests/patches/labels/opposite versions. Identical payloads, alternate arms and reverse repetition order. All failures retained. No generated proof stage.",
        "adoption": decision["primary_adoption_criterion"],
    })
    for relative in frozen:
        target = phase / "implementation" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    shutil.copy2(freeze / "reference-rubric.json", phase / "reference-rubric.json")
    budget = AttemptBudget(EXPERIMENT)
    records = []
    save(phase / "results.json", {"records": records, "status": "running"})
    for repetition in range(1, repetitions + 1):
        for ordinal, window in enumerate(originals):
            order = arms if (ordinal + repetition) % 2 else list(reversed(arms))
            for arm in order:
                assert all(digest(ROOT / p) == h for p, h in {**frozen, **protected}.items())
                label = {k: window[k] for k in ["case", "side", "path", "start", "end"]}
                label.update(strategy=arm, repetition=repetition)
                name = f"rep{repetition}-{window['folder']}-{arm}"
                destination = phase / "windows" / name
                destination.mkdir(parents=True)
                index = CodeIndex(snapshots[window["case"], window["side"]])
                index.production_only = True
                config = decision["arms"][arm]
                llm = RecordedLLM(budget, phase.name, 192, destination, label)
                llm.thinking_mode = config["thinking_mode"]
                llm.max_tokens = config["max_output_tokens"]
                assert llm.model == model["model"] and llm.temperature == model["temperature"]
                with redirect_stdout(io.StringIO()):
                    agent = ReviewAgents(index, llm, config["context_strategy"])
                part = Chunk(window["path"], window["start"], window["end"], numbered(
                    index.files[window["path"]], window["start"], window["end"]))
                save(destination / "initial-payload.json", agent.review_payload(part, [], evidence=True))
                began = time.monotonic()
                findings, error, status = [], None, "completed"
                with (destination / "stdout.log").open("w") as stdout:
                    try:
                        with redirect_stdout(stdout):
                            findings = agent.review(part, [], evidence=True)
                    except Exception as exc:
                        status = "failed"
                        error = {"type": type(exc).__name__, "message": str(exc)[:300]}
                    finally:
                        llm.close()
                record = {
                    **label, "name": name, "status": status, "error": error,
                    "api_calls": len(llm.calls), "calls": llm.calls,
                    "findings": [f.model_dump() for f in findings],
                    "trace": agent.trace, "tool_reads": index.reads,
                    "elapsed_seconds": round(time.monotonic() - began, 3),
                    "folder": str(destination.relative_to(phase)),
                }
                save(destination / "record.json", record)
                records.append(record)
                save(phase / "results.json", {"records": records, "status": "running", "budget": budget.state()})
                print(json.dumps({"progress": f"{len(records)}/{len(originals)*len(arms)*repetitions}",
                    **label, "status": status, "calls": len(llm.calls),
                    "candidates": len(findings), "global_used": budget.state()["reserved"]}, ensure_ascii=False), flush=True)
    assert all(digest(ROOT / p) == h for p, h in {**frozen, **protected}.items())
    save(phase / "results.json", {"records": records, "status": "sampled",
        "budget": budget.state(), "source_frozen": True, "semantic_adjudication": "pending"})


if __name__ == "__main__":
    main()
