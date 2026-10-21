"""Aggregate window records and apply the unchanged reference-pair scorer."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.bugsinpy_score import score_pairs


def aggregate(phase):
    manifest = json.loads((phase / "manifest.json").read_text())
    results = json.loads((phase / "results.json").read_text())
    groups = {}
    for row in results["records"]:
        mode = f"{row['strategy']}/rep{row['repetition']}"
        key = row["case"], mode, row["side"]
        group = groups.setdefault(
            key,
            {
                "case": row["case"],
                "mode": mode,
                "variant": row["side"],
                "windows": [],
                "findings": {},
                "api_calls": 0,
                "usage": {},
            },
        )
        group["windows"].append(row)
        group["api_calls"] += row["api_calls"]
        for finding in row["findings"]:
            group["findings"][finding["id"]] = finding
        for call in row["calls"]:
            for token in ["prompt_tokens", "completion_tokens", "total_tokens"]:
                group["usage"][token] = group["usage"].get(token, 0) + call.get(
                    "usage", {}
                ).get(token, 0)
    for group in groups.values():
        expected = sum(
            w["case"] == group["case"] and w["side"] == group["variant"]
            for w in manifest["input_windows"]
        )
        group["status"] = (
            "completed"
            if len(group["windows"]) == expected
            and all(w["status"] == "completed" for w in group["windows"])
            else "partial"
        )
        group["findings"] = list(group["findings"].values())
        group["expected_windows"] = expected
    return list(groups.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=Path, required=True)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    groups = aggregate(args.phase)
    (args.phase / "groups.json").write_text(
        json.dumps(groups, ensure_ascii=False, indent=2) + "\n"
    )
    if args.decisions:
        decisions = json.loads(args.decisions.read_text())
        by_key = {(d["case"], d["mode"], d["variant"]): d for d in decisions}
        assert len(by_key) == len(decisions) == len(groups)
        for group in groups:
            decision = by_key[group["case"], group["mode"], group["variant"]]
            assert {f["id"] for f in group["findings"]} == {
                f["id"] for f in decision["active_findings"]
            }
        # Official reproduction provenance comes from the preexisting verified run.
        root = Path(__file__).resolve().parents[1]
        verified = json.loads(
            (root / "demo/evidence-assessment-20261014/run-records.json").read_text()
        )
        rows = []
        for group in groups:
            historical = next(
                r
                for r in verified
                if r["case"] == group["case"]
                and r["variant"] == group["variant"]
                and r["mode"] == "evidence"
            )
            rows.append(
                {
                    "case": group["case"],
                    "mode": group["mode"],
                    "variant": group["variant"],
                    "status": group["status"],
                    "reproduction": historical["official_reproduction"],
                }
            )
        result = score_pairs(rows, decisions)
        result["stage"] = (
            "discovery only; does not measure Agent-generated proof or change the historical 1/26 score"
        )
        result["decisions_sha256"] = hashlib.sha256(
            args.decisions.read_bytes()
        ).hexdigest()
        result["all_planned_groups_retained"] = True
        (args.phase / "scores.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            json.dumps(
                [
                    {
                        "case": g["case"],
                        "mode": g["mode"],
                        "variant": g["variant"],
                        "status": g["status"],
                        "candidates": len(g["findings"]),
                        "calls": g["api_calls"],
                    }
                    for g in groups
                ],
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
