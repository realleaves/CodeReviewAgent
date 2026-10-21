import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "demo/discovery-trace-analysis-20261021/analysis.json"


def test_trace_analysis_counts_reflect_the_frozen_adjudications():
    data = json.loads(ANALYSIS.read_text())
    assert data["api_calls"] == 0
    assert data["docker_executions"] == 0
    counts = data["counts"]
    assert counts == {
        "cases": 6,
        "candidate_hits": 1,
        "promotion_gap": 1,
        "precision_gap": 3,
        "discovery_gap": 1,
    }
    categories = [case["category"] for case in data["cases"]]
    assert len(categories) == 6
    assert categories.count("hit") == 1
    assert categories.count("promotion_gap") == 1
    assert categories.count("precision_gap") == 3
    assert categories.count("discovery_gap") == 1
