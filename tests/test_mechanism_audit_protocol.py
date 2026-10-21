import json
from pathlib import Path

import pytest

from evaluation import discovery_experiment as experiment
from evaluation import discovery_mechanism_audit as p2
from src.agents import MeteredLLM
from src.repository import snapshot_digest

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "demo/mechanism-audit-20261021"


def test_mechanism_audit_protocol_is_prepared_but_not_run():
    goal = json.loads((PROTOCOL / "p2-goal.json").read_text())
    setup = json.loads((PROTOCOL / "setup-p2.json").read_text())
    budget = json.loads((PROTOCOL / "budget.json").read_text())
    assert goal["selection"] == ["youtube-dl-2", "tornado-3"]
    assert goal["variable"] == "review_strategy"
    assert goal["repetitions"] == 1
    assert goal["window_call_limit"] == 3
    assert goal["budget"]["phase_limit"] == 20
    assert setup["windows"] == 4
    assert len(setup["window_records"]) == 4
    assert budget == {"limit": 20, "reserved": 0, "phases": {}}
    assert "mechanism_audit" in goal["adoption"]


def test_p2_rejects_used_ledger_and_unfrozen_limits_without_running(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(p2, "P2ROOT", tmp_path)
    experiment.save(
        tmp_path / "budget.json", {"limit": 20, "reserved": 1, "phases": {"p2": 1}}
    )
    monkeypatch.setattr(p2, "run", lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(SystemExit, match="不重置或退款"):
        p2.execute("p2-mechanism-audit", 20)
    with pytest.raises(SystemExit, match="已冻结"):
        p2.execute("another-phase", 20)
    with pytest.raises(SystemExit, match="已冻结"):
        p2.execute("p2-mechanism-audit", 21)
    assert json.loads((tmp_path / "budget.json").read_text())["reserved"] == 1


def test_provider_failure_stops_before_next_window_and_retains_charge(
    tmp_path, monkeypatch
):
    project, output = tmp_path / "project", tmp_path / "output"
    output.mkdir()
    experiment.save(output / "budget.json", {"limit": 20, "reserved": 0, "phases": {}})
    experiment.save(output / "protected.json", {})
    files = {"a.py": "value = 1\n"}
    windows = [
        {
            "case": "sample",
            "side": side,
            "path": "a.py",
            "start": 1,
            "end": 1,
            "folder": side,
        }
        for side in ["buggy", "fixed"]
    ]
    preview = project / "outputs/context-callgraph-20261015/preview-final"
    experiment.save(preview / "results.json", {"records": windows})
    experiment.save(
        project / "outputs/evidence-original20-20261014/selection.json",
        [{"id": "sample", "snapshot_paths": {"buggy": "buggy", "fixed": "fixed"}}],
    )
    payload = {"primary_path": "a.py"}
    for side in ["buggy", "fixed"]:
        experiment.save(preview / side / "legacy.json", payload)
        experiment.save(
            project
            / "outputs/evidence-original20-20261014/reviews/sample/evidence"
            / side
            / "report.json",
            {"repository": {"indexed_snapshot_sha256": snapshot_digest(files)}},
        )
    monkeypatch.setattr(experiment, "ROOT", project)
    monkeypatch.setattr(experiment, "load_config", lambda: None)
    monkeypatch.setattr(experiment, "fingerprint", lambda: {})
    monkeypatch.setattr(experiment, "reviewer_files", lambda _: (files, []))

    class Probe:
        model, thinking_mode, temperature, max_tokens = (
            "test-model",
            "disabled",
            0.1,
            6000,
        )
        is_deepseek = True

        def __init__(self, *args):
            pass

        def close(self):
            pass

    recorded_class = experiment.RecordedLLM

    def recorded(budget, phase, phase_limit, destination, label):
        llm = object.__new__(recorded_class)
        llm.budget, llm.phase, llm.phase_limit = budget, phase, phase_limit
        llm.destination, llm.label = destination, label
        llm.calls, llm.max_calls = [], 3
        llm.model, llm.temperature, llm.max_tokens = "test-model", 0.1, 6000
        llm.thinking_mode, llm.close = "disabled", lambda: None
        return llm

    def unavailable(self, messages, **kwargs):
        self.calls.append({"status": "failed", "error_type": "AuthenticationError"})
        raise RuntimeError("sanitized provider failure")

    class Agent:
        def __init__(self, index, llm, *args):
            self.llm, self.trace = llm, []

        def review_payload(self, *args, **kwargs):
            return payload

        def review(self, *args, **kwargs):
            self.llm.invoke([{"role": "user", "content": "test"}])

    monkeypatch.setattr(experiment, "MeteredLLM", Probe)
    monkeypatch.setattr(experiment, "RecordedLLM", recorded)
    monkeypatch.setattr(experiment, "ReviewAgents", Agent)
    monkeypatch.setattr(MeteredLLM, "invoke", unavailable)
    with pytest.raises(SystemExit, match="stopped after the first failed"):
        experiment.run(output, "p2", 1, 20, ["legacy"], stop_on_provider_error=True)
    results = json.loads((output / "p2/results.json").read_text())
    assert results["status"] == "stopped_provider_error"
    assert len(results["records"]) == 1
    assert results["budget"]["reserved"] == 1
    assert json.loads((output / "p2/manifest.json").read_text())["global_limit"] == 20
    requests = list((output / "p2").glob("windows/*/requests/*/request.json"))
    assert len(requests) == 1 and requests[0].with_name("response.json").exists()
