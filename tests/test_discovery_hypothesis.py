import json
from pathlib import Path

from evaluation.discovery_hypothesis_score import score


ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "demo/discovery-hypothesis-20261021/p1-hypothesis"


def test_hypothesis_p1_result_keeps_the_negative_finding():
    adjudications = json.loads((PHASE / "adjudications.json").read_text())
    result = score(PHASE, adjudications)
    metrics = {row["arm"]: row for row in result["metrics"]}
    assert metrics["baseline"]["candidate_hits"] == 1
    assert metrics["baseline"]["candidate_hit_cases"] == ["youtube-dl-4"]
    assert metrics["hypothesis"]["candidate_hits"] == 0
    assert metrics["baseline"]["tool_reads"] == 6
    assert metrics["hypothesis"]["tool_reads"] == 0
    assert metrics["baseline"]["fixed_side_alarms"] == 0
    assert metrics["hypothesis"]["fixed_side_alarms"] == 0
    assert metrics["baseline"]["completed_windows"] == 18
    assert metrics["hypothesis"]["completed_windows"] == 18
    assert result["delta_hypothesis_minus_baseline"]["candidate_hits"] == -1
    assert result["delta_hypothesis_minus_baseline"]["tool_reads"] == -6
