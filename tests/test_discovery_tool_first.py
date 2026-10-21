import json
from pathlib import Path

from evaluation.discovery_tool_first_score import score


ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "demo/discovery-hypothesis-20261021/p1c-tool-first"


def test_tool_first_smoke_keeps_mechanical_success_and_zero_recall_gain():
    adjudications = json.loads((PHASE / "adjudications.json").read_text())
    result = score(PHASE, adjudications)
    metrics = {row["arm"]: row for row in result["metrics"]}
    assert metrics["baseline"]["candidate_hits"] == 0
    assert metrics["tool_first"]["candidate_hits"] == 0
    assert metrics["baseline"]["completed_windows"] == 4
    assert metrics["tool_first"]["completed_windows"] == 4
    assert metrics["baseline"]["tool_calls"] == 0
    assert metrics["tool_first"]["tool_calls"] == 12
    assert metrics["tool_first"]["tool_reads"] == 6
    assert metrics["tool_first"]["no_tool_call"] == 0
    assert metrics["baseline"]["calls"] == 4
    assert metrics["tool_first"]["calls"] == 8
    assert "no candidate-recall gain" in result["adoption"]
