import json
from pathlib import Path

from evaluation.discovery_tool_external_score import score


ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "demo/discovery-hypothesis-20261021/p1d-tool-external"


def test_external_read_smoke_keeps_mechanical_success_and_zero_recall_gain():
    adjudications = json.loads((PHASE / "adjudications.json").read_text())
    result = score(PHASE, adjudications)
    metrics = {row["arm"]: row for row in result["metrics"]}
    assert metrics["baseline"]["candidate_hits"] == 0
    assert metrics["tool_first_external"]["candidate_hits"] == 0
    assert metrics["baseline"]["completed_windows"] == 2
    assert metrics["tool_first_external"]["completed_windows"] == 2
    assert metrics["baseline"]["external_calls"] == 0
    assert metrics["tool_first_external"]["external_calls"] == 6
    assert metrics["tool_first_external"]["tool_reads"] == 6
    assert metrics["tool_first_external"]["no_external_span"] == 0
    assert metrics["baseline"]["calls"] == metrics["tool_first_external"]["calls"] == 2
    assert "Not adopted" in result["adoption"]
