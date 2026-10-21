from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from evaluation.discovery_experiment import AttemptBudget, RecordedLLM, save
from src.agents import BudgetExceeded, MeteredLLM


def budget(tmp_path, limit=5):
    save(tmp_path / "budget.json", {"limit": limit, "reserved": 0, "phases": {}})
    return AttemptBudget(tmp_path)


def test_reservations_are_shared_between_instances_and_enforce_phase_and_total(
    tmp_path,
):
    first = budget(tmp_path, 3)
    assert first.reserve("r0", 1, {})["id"] == 1
    with pytest.raises(BudgetExceeded):
        first.reserve("r0", 1, {})
    second = AttemptBudget(tmp_path)
    assert second.reserve("r1", 2, {})["id"] == 2
    assert first.reserve("r1", 2, {})["id"] == 3
    with pytest.raises(BudgetExceeded):
        second.reserve("holdout", 100, {})
    assert first.state()["reserved"] == 3


def test_concurrent_reservations_cannot_overspend(tmp_path):
    ledger = budget(tmp_path, 7)

    def reserve(_):
        try:
            return AttemptBudget(tmp_path).reserve("test", 20, {})["id"]
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        reserved = list(pool.map(reserve, range(25)))
    assert sorted(i for i in reserved if i is not None) == list(range(1, 8))
    assert ledger.state()["reserved"] == 7


def test_failed_provider_attempt_is_charged_and_raw_request_is_preserved(
    tmp_path, monkeypatch
):
    ledger = budget(tmp_path, 1)

    def fail(self, messages, **kwargs):
        assert ledger.state()["reserved"] == 1
        self.calls.append({"status": "failed", "error_type": "MockTransportError"})
        raise RuntimeError("sanitized provider failure")

    monkeypatch.setattr(MeteredLLM, "invoke", fail)
    llm = object.__new__(RecordedLLM)
    llm.calls = []
    llm.max_calls = 3
    llm.budget = ledger
    llm.phase = "test"
    llm.phase_limit = 3
    llm.destination = tmp_path / "window"
    llm.label = {"case": "test"}
    llm.model = "test-double"
    llm.temperature = 0.1
    llm.max_tokens = 6000
    llm.thinking_mode = "disabled"
    with pytest.raises(RuntimeError):
        llm.invoke([{"role": "user", "content": "review this code"}])
    assert ledger.state()["reserved"] == 1
    response = json.loads((llm.destination / "requests/0001/response.json").read_text())
    assert response["error_type"] == "RuntimeError"
    assert response["call"]["error_type"] == "MockTransportError"
    assert (llm.destination / "requests/0001/request.json").exists()
    with pytest.raises(BudgetExceeded):
        llm.invoke([{"role": "user", "content": "retry"}])
    assert len(llm.calls) == 1


def test_local_context_rejection_does_not_issue_or_charge_a_request(tmp_path):
    ledger = budget(tmp_path)
    llm = object.__new__(RecordedLLM)
    llm.calls = []
    llm.max_calls = 3
    llm.budget = ledger
    with pytest.raises(BudgetExceeded):
        llm.invoke([{"role": "user", "content": "x" * 90001}])
    assert ledger.state()["reserved"] == 0
