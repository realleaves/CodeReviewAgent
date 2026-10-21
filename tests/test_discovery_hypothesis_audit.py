import json
from pathlib import Path

from evaluation.discovery_hypothesis_audit_score import score


ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "demo/discovery-hypothesis-20261021/p1e-hypothesis-audit"


def test_audit_smoke_is_inconclusive_when_the_premise_is_not_reproduced():
    adjudications = json.loads((PHASE / "adjudications.json").read_text())
    result = score(PHASE, adjudications)
    metrics = {row["arm"]: row for row in result["metrics"]}
    assert metrics["baseline"]["candidate_hits"] == 0
    assert metrics["hypothesis_audit"]["candidate_hits"] == 0
    assert metrics["baseline"]["completed_windows"] == 2
    assert metrics["hypothesis_audit"]["completed_windows"] == 2
    assert metrics["hypothesis_audit"]["calls"] == 4
    assert metrics["hypothesis_audit"]["audit_windows"] == 2
    assert metrics["hypothesis_audit"]["audit_added"] == 0
    assert metrics["hypothesis_audit"]["target_concept_mentioned"] is False
    assert "inconclusive" in result["adoption"]
