"""Offline verification of the P1 trace-analysis report."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
DEMO = PROJECT / "demo/discovery-hypothesis-20261021"


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    analysis = load(ROOT / "analysis.json")
    assert analysis["api_calls"] == 0
    assert analysis["docker_executions"] == 0
    counts = analysis["counts"]
    assert counts["cases"] == 6
    assert (
        counts["candidate_hits"]
        + counts["promotion_gap"]
        + counts["precision_gap"]
        + counts["discovery_gap"]
        == 6
    )
    categories = [case["category"] for case in analysis["cases"]]
    assert categories.count("hit") == counts["candidate_hits"] == 1
    assert categories.count("promotion_gap") == counts["promotion_gap"] == 1
    assert categories.count("precision_gap") == counts["precision_gap"] == 3
    assert categories.count("discovery_gap") == counts["discovery_gap"] == 1
    files = {
        "p1_results": DEMO / "p1-hypothesis/results.json",
        "p1_adjudications": DEMO / "p1-hypothesis/adjudications.json",
        "p1b_results": DEMO / "p1b-tools/results.json",
        "p1b_adjudications": DEMO / "p1b-tools/adjudications.json",
        "p1c_results": DEMO / "p1c-tool-first/results.json",
        "p1c_adjudications": DEMO / "p1c-tool-first/adjudications.json",
        "p1d_results": DEMO / "p1d-tool-external/results.json",
        "p1d_adjudications": DEMO / "p1d-tool-external/adjudications.json",
        "p1e_results": DEMO / "p1e-hypothesis-audit/results.json",
        "p1e_adjudications": DEMO / "p1e-hypothesis-audit/adjudications.json",
    }
    for name, path in files.items():
        assert digest(path) == analysis["source_sha256"][name]
    p1_adjudications = {
        (row["case"], row["mode"], row["variant"]): row
        for row in load(files["p1_adjudications"])
    }
    assert p1_adjudications[("youtube-dl-4", "baseline", "buggy")][
        "target_issue_detected"
    ]
    assert not p1_adjudications[("youtube-dl-2", "hypothesis", "buggy")][
        "target_issue_detected"
    ]
    assert not p1_adjudications[("youtube-dl-2", "baseline", "buggy")][
        "target_issue_detected"
    ]
    p1 = load(files["p1_results"])["records"]
    youtube = next(
        row
        for row in p1
        if row["case"] == "youtube-dl-2"
        and row["side"] == "buggy"
        and row["strategy"] == "hypothesis"
    )
    reasoning = json.dumps(youtube.get("trace", []), ensure_ascii=False).lower()
    findings = json.dumps(youtube.get("findings", []), ensure_ascii=False).lower()
    assert "representation_id" in reasoning
    assert "representation_id" not in findings
    p1e = load(files["p1e_results"])["records"]
    p1e_text = json.dumps(p1e, ensure_ascii=False).lower()
    assert "representation_id" not in p1e_text
    assert "format_id" not in p1e_text
    p1e_adjudications = load(files["p1e_adjudications"])
    assert not any(row["target_issue_detected"] for row in p1e_adjudications)
    print(
        json.dumps(
            {
                "status": "PASS",
                "cases": counts["cases"],
                "candidate_hits": counts["candidate_hits"],
                "promotion_gap": counts["promotion_gap"],
                "precision_gap": counts["precision_gap"],
                "discovery_gap": counts["discovery_gap"],
                "api_calls": 0,
                "docker_executions": 0,
                "note": "offline trace screen; P1 budget remains exhausted at 80/80",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
