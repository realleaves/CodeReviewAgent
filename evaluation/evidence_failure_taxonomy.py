"""Deterministic failure taxonomy for the 2026-10-14 evidence assessment.

No model or Docker calls. Reads the frozen 72-run reports' adjudications and
classifies the 26 eligible pairs at the candidate stage:

- valid_evidence: reference candidate + valid reproduced evidence
- candidate_hit_evidence_failed: reference candidate, no valid evidence
- no_candidate: no LLM finding in the buggy-side report
- off_target_reproduced: findings reproduced, none matches the reference
- off_target_unproven: findings exist, none reproduced, none matches

The taxonomy is about the buggy side; the paired fixed side is used by the
assessment but does not change the candidate-stage category.
"""

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "demo/evidence-assessment-20261014"


def load(name):
    return json.loads((BASE / name).read_text())


def build():
    metrics = load("metrics.json")
    adjudications = load("adjudications.json")
    runs = load("run-records.json")
    eligible = []
    for score in metrics["scores"]:
        if score["mode"] == "evidence":
            eligible.extend(score["eligible_case_ids"])
    assert len(eligible) == 26
    decisions = {
        (row["case"], row["variant"]): row
        for row in adjudications
        if row["mode"] == "evidence"
    }
    run_records = {
        (row["case"], row["variant"]): row for row in runs if row["mode"] == "evidence"
    }
    rows = []
    for case in sorted(eligible):
        decision = decisions[(case, "buggy")]
        run = run_records[(case, "buggy")]
        findings = decision.get("active_llm_findings", [])
        reproduced = sum(
            finding["reproduction_status"] == "reproduced" for finding in findings
        )
        candidate_hit = bool(decision["candidate_match_ids"])
        valid = bool(decision["valid_reproduced_match_ids"])
        if valid:
            category = "valid_evidence"
        elif candidate_hit:
            category = "candidate_hit_evidence_failed"
        elif not findings:
            category = "no_candidate"
        elif reproduced:
            category = "off_target_reproduced"
        else:
            category = "off_target_unproven"
        rows.append(
            {
                "case": case,
                "batch": decision["batch"],
                "category": category,
                "candidate_hit": candidate_hit,
                "valid_evidence": valid,
                "llm_findings": len(findings),
                "reproduced_findings": reproduced,
                "report_status": run["status"],
                "window_review_completed": run["window_review_completed"],
                "calls": run["calls"],
                "candidate_match_ids": decision["candidate_match_ids"],
                "valid_match_ids": decision["valid_reproduced_match_ids"],
                "reference_issue": decision["reference_issue"],
                "reason": decision["reason"],
                "findings": findings,
            }
        )
    counts = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    expected = {
        "valid_evidence": 1,
        "candidate_hit_evidence_failed": 3,
        "no_candidate": 8,
        "off_target_reproduced": 4,
        "off_target_unproven": 10,
    }
    assert counts == expected, counts
    assert sum(row["candidate_hit"] for row in rows) == 4
    assert sum(row["valid_evidence"] for row in rows) == 1
    assert sum(not row["candidate_hit"] for row in rows) == 22
    return {
        "source": str(BASE.relative_to(ROOT)),
        "scope": "26 eligible evidence pairs from the frozen 2026-10-14 assessment; buggy-side candidate stage",
        "api_calls": 0,
        "docker_executions": 0,
        "counts": {
            "eligible_pairs": len(rows),
            "candidate_hits": 4,
            "valid_evidence": 1,
            "misses": 22,
            **counts,
        },
        "rates": {
            "candidate_hit_rate": round(4 / 26, 4),
            "valid_evidence_rate": round(1 / 26, 4),
            "no_candidate_share_of_misses": round(8 / 22, 4),
            "off_target_share_of_misses": round(14 / 22, 4),
        },
        "records": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "demo/evidence-failure-taxonomy-20261021/taxonomy.json",
    )
    args = parser.parse_args()
    result = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "counts": result["counts"],
                "rates": result["rates"],
                "no_candidate_cases": [
                    row["case"]
                    for row in result["records"]
                    if row["category"] == "no_candidate"
                ],
                "off_target_cases": [
                    row["case"]
                    for row in result["records"]
                    if row["category"].startswith("off_target")
                ],
                "candidate_hit_evidence_failed_cases": [
                    row["case"]
                    for row in result["records"]
                    if row["category"] == "candidate_hit_evidence_failed"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
