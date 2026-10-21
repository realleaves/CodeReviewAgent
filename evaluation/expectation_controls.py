"""Offline controls for the expectation-admission gate.

The 13 already-accepted 2026-10-14 records are frozen. Their original plans
predate the structured contract fields, so this script applies an explicit,
reviewable mapping from each plan's own text (not from a new model call) to
expected_outcome/expected_exception, then runs the deterministic
requirement_gate. It never executes Docker and never calls a model.

This checks the admission policy against fixed positives/negatives. It is not
an end-to-end recall or precision measurement.
"""

import argparse
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.reproduction import requirement_gate
from src.schemas import ReproductionPlan

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "demo/evidence-retest13-20261015/raw-results.zip"

# finding id -> (expected_outcome, expected_exception)
# Derived from the frozen plan text and the 2026-10-15 per-case adjudication.
MAPPING = {
    # PySnooper-1: empty source should fall back to unavailable source.
    "65bac8b9d901": ("return_value", ""),
    # tornado-1: expected only the formatting of the ValueError message.
    "9c3894d4b559": ("error_message", ""),
    # tornado-1: observed KeyError, requested ValueError.
    "2cd97d34b1a2": ("exception", "ValueError"),
    # PySnooper-3: documented output_path file output.
    "9261f543fc85": ("output", ""),
    # youtube-dl-4: observed ValueError, requested ExtractorError.
    "791eec547d5f": ("exception", "ExtractorError"),
    # youtube-dl-6: zero-duration cue should be retained.
    "b8651e68a886": ("output", ""),
    # youtube-dl-8: observed AttributeError, requested SyntaxError.
    "248543bf3d91": ("exception", "SyntaxError"),
    "328973b86f3e": ("exception", "SyntaxError"),
    "49a68ceac4ab": ("exception", "SyntaxError"),
    "617648cc5081": ("exception", "SyntaxError"),
    "e7aa719b31af": ("exception", "SyntaxError"),
    # youtube-dl-9: empty selector should yield nothing.
    "9f669fbbebd2": ("return_value", ""),
    # youtube-dl-12: filter predicate should return True/False.
    "9758e8ca5215": ("return_value", ""),
}


def load_records():
    records = []
    with zipfile.ZipFile(ARCHIVE) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith("/original-evidence.json"):
                continue
            saved = json.loads(archive.read(name))
            records.append((name.split("/")[0], saved))
    return records


def evaluate():
    rows = []
    for folder, saved in load_records():
        finding = saved["finding"]
        reproduction = finding["reproduction"]
        finding_id = finding["id"]
        if finding_id not in MAPPING:
            raise SystemExit(f"缺少固定映射：{finding_id}")
        outcome, expected = MAPPING[finding_id]
        plan = ReproductionPlan.model_validate(reproduction["plan"])
        plan.contract.expected_outcome = outcome
        plan.contract.expected_exception = expected
        admitted, reason = requirement_gate(
            plan,
            [
                reproduction["attempts"][index]
                for index in reproduction.get("active_attempt_indexes", [0])
            ],
        )
        rows.append(
            {
                "folder": folder,
                "case": folder.split("-", 1)[1].rsplit("-", 2)[0],
                "finding_id": finding_id,
                "title": finding["title"],
                "contract_kind": plan.contract.kind,
                "expected_outcome": outcome,
                "expected_exception": expected,
                "admitted_to_audit": admitted,
                "reason": reason,
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = evaluate()
    admitted = [row for row in rows if row["admitted_to_audit"]]
    rejected = [row for row in rows if not row["admitted_to_audit"]]
    summary = {
        "source": "demo/evidence-retest13-20261015/raw-results.zip",
        "api_calls": 0,
        "docker_executions": 0,
        "scope": "fixed 13 previously accepted evidence records; deterministic expectation gate only",
        "mapping_note": (
            "expected_outcome/expected_exception are fixed evaluator annotations taken from each "
            "frozen plan text and the 2026-10-15 adjudication, not new model output."
        ),
        "records": rows,
        "admitted": len(admitted),
        "rejected": len(rejected),
        "admitted_ids": [row["finding_id"] for row in admitted],
        "expected_admitted_ids": ["9261f543fc85"],
    }
    assert summary["admitted_ids"] == summary["expected_admitted_ids"], summary
    assert summary["admitted"] + summary["rejected"] == 13
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
