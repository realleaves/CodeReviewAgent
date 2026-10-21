"""Verify the prepared P2 protocol without calling a model."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    goal = json.loads((ROOT / "p2-goal.json").read_text())
    arms = json.loads((ROOT / "arms-p2.json").read_text())
    setup = json.loads((ROOT / "setup-p2.json").read_text())
    budget = json.loads((ROOT / "budget.json").read_text())
    assert goal["selection"] == ["youtube-dl-2", "tornado-3"]
    assert set(arms) == {"baseline", "mechanism_audit"}
    assert setup["windows"] == 4 and len(setup["window_records"]) == 4
    assert {row["case"] for row in setup["window_records"]} == set(goal["selection"])
    assert budget == {"limit": 20, "reserved": 0, "phases": {}}
    assert goal["budget"]["phase_limit"] == 20
    assert goal["repetitions"] == 1
    assert goal["window_call_limit"] == 3
    assert "review_strategy" == goal["variable"]
    assert "mechanism_audit" in goal["adoption"]
    assert (
        "no reference labels" in goal["scope"].lower()
        or "reference labels" in goal["scope"]
    )
    for relative, expected in setup["source_sha256"].items():
        assert digest(PROJECT / relative) == expected
    assert "evaluation/discovery_mechanism_audit.py" in setup["source_sha256"]
    print(
        json.dumps(
            {
                "status": "PASS",
                "prepared": True,
                "run": False,
                "api_calls": 0,
                "windows": 4,
                "cases": goal["selection"],
                "budget": budget,
                "model": setup["model"],
                "note": "protocol and budget only; no model calls",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
