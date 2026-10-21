"""Paired discovery-only experiments with a durable, shared provider-attempt cap."""

import argparse
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.bugsinpy_review import reviewer_files
from src.agents import BudgetExceeded, MeteredLLM, ReviewAgents, load_config
from src.code_index import Chunk, CodeIndex, numbered
from src.repository import snapshot_digest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "outputs/discovery-goal-20261015"


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AttemptBudget:
    """Reserve before every invocation, including failures; never refund attempts."""

    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "budget.json"

    @contextmanager
    def locked(self):
        with (self.root / "budget.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.path.read_text())
            yield state
            save(self.path, state)

    def reserve(self, phase, phase_limit, label):
        with self.locked() as state:
            if state["reserved"] >= state["limit"]:
                raise BudgetExceeded("持续目标的模型调用总预算已耗尽。")
            previous = state["phases"].get(phase, 0)
            if previous >= phase_limit:
                raise BudgetExceeded("本轮模型调用预算已耗尽。")
            state["reserved"] += 1
            state["phases"][phase] = previous + 1
            reservation = {
                "id": state["reserved"],
                "phase": phase,
                "label": label,
                "reserved_at": now(),
            }
            # Commit the reservation before a crash could reach the network.
            save(self.path, state)
            with (self.root / "attempts.jsonl").open("a") as stream:
                stream.write(json.dumps(reservation, ensure_ascii=False) + "\n")
            return reservation

    def state(self):
        return json.loads(self.path.read_text())


class RecordedLLM(MeteredLLM):
    def __init__(self, budget, phase, phase_limit, destination, label, max_calls=3):
        super().__init__(max_calls, 45)
        self.budget, self.phase, self.phase_limit = budget, phase, phase_limit
        self.destination, self.label = destination, label

    def invoke(self, messages, **kwargs):
        # These are local rejections, before any provider request can be made.
        if len(self.calls) >= self.max_calls:
            raise BudgetExceeded("达到窗口模型调用上限。")
        if sum(len(str(m.get("content", ""))) for m in messages) > 90000:
            raise BudgetExceeded("单次上下文超过90000字符。")
        reservation = self.budget.reserve(self.phase, self.phase_limit, self.label)
        folder = self.destination / "requests" / f"{reservation['id']:04d}"
        save(
            folder / "request.json",
            {
                "reservation": reservation,
                "messages": messages,
                "options": kwargs,
                "generation": {
                    "model": self.model,
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                    "thinking_mode": self.thinking_mode,
                },
            },
        )
        response = None
        error = None
        count = len(self.calls)
        try:
            response = super().invoke(messages, **kwargs)
            return response
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            save(
                folder / "response.json",
                {
                    "reservation": reservation,
                    "raw_response": response,
                    "error_type": error,
                    "call": self.calls[-1] if len(self.calls) > count else None,
                },
            )


def initialize(root):
    root.mkdir(parents=True, exist_ok=False)
    save(
        root / "budget.json",
        {"limit": 600, "reserved": 0, "phases": {}, "started_at": now()},
    )
    save(
        root / "goal.json",
        {
            "authorization": "User-authorized persistent local evaluation and at most two additional single-variable improvement rounds; do not push GitHub.",
            "deepseek_attempt_limit": 600,
            "additional_improvement_round_limit": 2,
            "scoring": "Existing reference-issue rubric; concrete root cause plus valid trigger required. Extra findings not automatically false positives. Model-assisted adjudication, human review pending.",
            "new_validation_selection": [
                "tornado-13",
                "youtube-dl-14",
                "tornado-14",
                "youtube-dl-15",
            ],
            "selection_policy": "Numeric IDs immediately after previously inspected samples, fixed before development model experiments. Do not inspect reference semantics until a candidate implementation is frozen.",
            "historical_scores_unchanged": True,
        },
    )
    shutil.copy2(
        ROOT / "evaluation/bugsinpy-rubric.json", root / "reference-rubric.json"
    )
    save(
        root / "protected.json",
        {
            str(p.relative_to(ROOT)): digest(p)
            for p in [
                ROOT / "evaluation/bugsinpy-rubric.json",
                ROOT / "evaluation/bugsinpy_score.py",
            ]
        },
    )


def fingerprint():
    paths = [*sorted((ROOT / "src").glob("*.py")), ROOT / "main.py", Path(__file__)]
    for name in [
        "discovery_hypothesis.py",
        "discovery_hypothesis_tools.py",
        "discovery_tool_first.py",
        "discovery_tool_external.py",
        "discovery_hypothesis_audit.py",
        "discovery_mechanism_audit.py",
    ]:
        runner = ROOT / "evaluation" / name
        if runner.exists():
            paths.append(runner)
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}


def run(
    root,
    phase_name,
    repetitions,
    phase_limit,
    strategies,
    arm_config=None,
    variable="context_strategy",
    case_ids=None,
    max_windows_per_side=None,
    stop_on_provider_error=False,
):
    budget = AttemptBudget(root)
    phase = root / phase_name
    phase.mkdir(exist_ok=False)
    load_config()
    with redirect_stdout(io.StringIO()):
        probe = MeteredLLM(1, 45)
    model_config = {
        "model": probe.model,
        "thinking_mode": probe.thinking_mode,
        "temperature": probe.temperature,
        "max_output_tokens": probe.max_tokens,
        "timeout": 45,
        "provider_is_deepseek": probe.is_deepseek,
    }
    probe.close()
    assert model_config["provider_is_deepseek"], (
        "Use the explicitly authorized existing DeepSeek provider."
    )
    configs = (
        json.loads(arm_config.read_text())
        if arm_config
        else {
            name: {
                "context_strategy": name,
                "thinking_mode": model_config["thinking_mode"],
                "review_strategy": "baseline",
            }
            for name in strategies
        }
    )
    assert set(configs) == set(strategies)
    for config in configs.values():
        assert config["context_strategy"] in {"legacy", "callgraph"}
        assert config["thinking_mode"] in {"enabled", "disabled"}
        assert config.get("review_strategy", "baseline") in {
            "baseline",
            "hypothesis",
            "hypothesis_tools",
            "tool_first",
            "tool_first_external",
            "hypothesis_audit",
            "mechanism_audit",
        }
        assert (
            1
            <= config.get("max_output_tokens", model_config["max_output_tokens"])
            <= 12000
        )
    assert all(
        digest(ROOT / p) == h
        for p, h in json.loads((root / "protected.json").read_text()).items()
    )
    preview = ROOT / "outputs/context-callgraph-20261015/preview-final"
    original = json.loads((preview / "results.json").read_text())["records"]
    if case_ids:
        wanted = set(case_ids)
        original = [row for row in original if row["case"] in wanted]
    if max_windows_per_side:
        per_side = {}
        filtered = []
        for row in original:
            key = row["case"], row["side"]
            if per_side.get(key, 0) < max_windows_per_side:
                filtered.append(row)
                per_side[key] = per_side.get(key, 0) + 1
        original = filtered
    assert original, "过滤后没有输入窗口。"
    cases = json.loads(
        (ROOT / "outputs/evidence-original20-20261014/selection.json").read_text()
    )
    snapshots = {}
    for record in original:
        case = next(c for c in cases if c["id"] == record["case"])
        key = record["case"], record["side"]
        if key not in snapshots:
            files, _ = reviewer_files(
                ROOT / "outputs/bugsinpy-work" / case["snapshot_paths"][record["side"]]
            )
            historical = json.loads(
                (
                    ROOT
                    / "outputs/evidence-original20-20261014/reviews"
                    / record["case"]
                    / "evidence"
                    / record["side"]
                    / "report.json"
                ).read_text()
            )
            assert (
                snapshot_digest(files)
                == historical["repository"]["indexed_snapshot_sha256"]
            )
            snapshots[key] = files
    frozen = fingerprint()
    save(
        phase / "manifest.json",
        {
            "created_at": now(),
            "model": model_config,
            "source_sha256": frozen,
            "phase_call_limit": phase_limit,
            "global_limit": budget.state()["limit"],
            "repetitions": repetitions,
            "strategies": strategies,
            "arms": configs,
            "comparison_variable": variable,
            "window_call_limit": 3,
            "window_count_per_strategy_per_repetition": len(original),
            "protocol": "Fresh independent discovery only, same original production-only sources and windows; no official tests, labels, reference rubric or opposite version in agent inputs. Arms alternate by window and reverse each repetition. No candidate reproduction stage. All planned records retained.",
            "scoring": "Existing reference rubric frozen in parent; score known-issue candidates separately from generated proof. No unconfirmed extra finding is automatically a false positive.",
            "adoption": "More correctly discriminated known-issue pairs in each repetition, no increase in same-issue fixed alarms, no lower completeness. Extra findings audited separately and tokens/calls reported. An exploratory gain requires unseen validation before default adoption.",
            "input_windows": original,
        },
    )
    # Keep an exact source copy, preserving relative paths.
    for relative in frozen:
        dest = phase / "implementation" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, dest)
    records = []
    save(phase / "results.json", {"records": records, "status": "running"})
    for repetition in range(1, repetitions + 1):
        for i, window in enumerate(original):
            arms = strategies if (i + repetition) % 2 else list(reversed(strategies))
            for strategy in arms:
                assert fingerprint() == frozen, (
                    "Implementation changed during sampling."
                )
                label = {
                    "case": window["case"],
                    "side": window["side"],
                    "repetition": repetition,
                    "strategy": strategy,
                    "path": window["path"],
                    "start": window["start"],
                    "end": window["end"],
                }
                name = f"rep{repetition}-{window['folder']}-{strategy}"
                destination = phase / "windows" / name
                destination.mkdir(parents=True)
                files = snapshots[window["case"], window["side"]]
                index = CodeIndex(files)
                index.production_only = True
                part = Chunk(
                    window["path"],
                    window["start"],
                    window["end"],
                    numbered(files[window["path"]], window["start"], window["end"]),
                )
                llm = RecordedLLM(budget, phase_name, phase_limit, destination, label)
                llm.thinking_mode = configs[strategy]["thinking_mode"]
                llm.max_tokens = configs[strategy].get(
                    "max_output_tokens", model_config["max_output_tokens"]
                )
                assert llm.model == model_config["model"]
                with redirect_stdout(io.StringIO()):
                    agent = ReviewAgents(
                        index,
                        llm,
                        configs[strategy]["context_strategy"],
                        configs[strategy].get("review_strategy", "baseline"),
                    )
                payload = agent.review_payload(part, [], evidence=True)
                expected = (
                    json.loads(
                        (
                            preview
                            / window["folder"]
                            / (configs[strategy]["context_strategy"] + ".json")
                        ).read_text()
                    )
                    if configs[strategy]["context_strategy"] in ["legacy", "callgraph"]
                    else None
                )
                if expected is not None:
                    assert payload == expected
                save(destination / "initial-payload.json", payload)
                start = time.monotonic()
                findings = []
                status = "completed"
                error = None
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
                    **label,
                    "name": name,
                    "status": status,
                    "error": error,
                    "api_calls": len(llm.calls),
                    "calls": llm.calls,
                    "findings": [f.model_dump() for f in findings],
                    "trace": agent.trace,
                    "tool_reads": index.reads,
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                    "folder": str(destination.relative_to(phase)),
                }
                save(destination / "record.json", record)
                records.append(record)
                save(
                    phase / "results.json",
                    {"records": records, "status": "running", "budget": budget.state()},
                )
                print(
                    json.dumps(
                        {
                            "phase": phase_name,
                            "progress": f"{len(records)}/{repetitions * len(original) * len(strategies)}",
                            **label,
                            "status": status,
                            "candidates": len(findings),
                            "calls": len(llm.calls),
                            "global_used": budget.state()["reserved"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                if stop_on_provider_error and any(
                    call.get("status") == "failed"
                    and call.get("error_type") != "ModelResponseError"
                    for call in llm.calls
                ):
                    save(
                        phase / "results.json",
                        {
                            "records": records,
                            "status": "stopped_provider_error",
                            "budget": budget.state(),
                            "source_frozen": fingerprint() == frozen,
                            "semantic_adjudication": "pending",
                        },
                    )
                    raise SystemExit(
                        "Provider unavailable: stopped after the first failed "
                        "request; reservation and failure retained."
                    )
    assert fingerprint() == frozen
    save(
        phase / "results.json",
        {
            "records": records,
            "status": "sampled",
            "budget": budget.state(),
            "source_frozen": True,
            "semantic_adjudication": "pending",
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "run"])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--phase", default="r0-context")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--phase-limit", type=int, default=216)
    parser.add_argument("--strategies", nargs=2, default=["legacy", "callgraph"])
    parser.add_argument("--arm-config", type=Path)
    parser.add_argument("--variable", default="context_strategy")
    args = parser.parse_args()
    if args.command == "init":
        initialize(args.root.resolve())
    else:
        run(
            args.root.resolve(),
            args.phase,
            args.repetitions,
            args.phase_limit,
            args.strategies,
            args.arm_config,
            args.variable,
        )


if __name__ == "__main__":
    main()
