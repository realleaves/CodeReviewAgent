"""Verify archived evidence identity and score arithmetic, without model calls.

The supplied semantic adjudications remain subject to human review.
"""

import collections
import hashlib
import json
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    metrics = json.loads((root / "metrics.json").read_text())
    decisions = json.loads((root / "adjudications.json").read_text())
    records = json.loads((root / "run-records.json").read_text())
    configs = json.loads((root / "run-configs.json").read_text())
    manifest = json.loads((root / "raw-manifest.json").read_text())
    archive = root / "raw-results.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["archive_sha256"]
    judgments = {
        (d["batch"], d["case"], d["mode"], d["variant"]): d for d in decisions
    }
    assert len(judgments) == len(decisions) == len(records)
    proof_statuses = collections.Counter()
    automatic_accepts = 0
    with zipfile.ZipFile(archive) as packed:
        assert packed.testzip() is None
        assert set(packed.namelist()) == set(manifest["files"])
        for filename, expected in manifest["files"].items():
            assert hashlib.sha256(packed.read(filename)).hexdigest() == expected
        for batch, config in configs.items():
            assert json.loads(packed.read(batch + "/run_config.json")) == config
            original = json.loads(packed.read(batch + "/results.json"))["records"]
            assert [{k: v for k, v in r.items() if k != "batch"} for r in records if r["batch"] == batch] == original
        for record in records:
            key = tuple(record[k] for k in ["batch", "case", "mode", "variant"])
            decision = judgments[key]
            raw = packed.read(record["batch"] + "/" + record["report"])
            assert hashlib.sha256(raw).hexdigest() == decision["report_sha256"]
            report = json.loads(raw)
            assert report["run"]["status"] == record["status"]
            assert report["run"]["window_review_completed"] == record["window_review_completed"]
            findings = {
                f["id"]: f for f in report["findings"]
                if f["source"] == "llm" and f["status"] != "rejected"
            }
            assert set(findings) == {f["id"] for f in decision["active_llm_findings"]}
            assert set(decision["candidate_match_ids"]) <= set(findings)
            accepted = {i for i, f in findings.items() if f["status"] == "reproduced"}
            assert set(decision["valid_reproduced_match_ids"]) <= accepted
            assert set(decision["agent_reported_reproduced_ids"]) == accepted
            automatic_accepts += len(accepted)
            if record["mode"] == "evidence":
                proof_statuses.update((f.get("reproduction") or {}).get("status", "none") for f in findings.values())
    evidence_pairs = evidence_hits = candidate_hits = 0
    for score in metrics["scores"]:
        batch, mode = score["batch"], score["mode"]
        current = [r for r in records if r["batch"] == batch and r["mode"] == mode]
        groups = {c: [r for r in current if r["case"] == c] for c in {r["case"] for r in current}}
        eligible = []
        for case, runs in groups.items():
            assert len(runs) == 2 and {r["variant"] for r in runs} == {"buggy", "fixed"}
            if all(r["window_review_completed"] and r["official_reproduction"] == "reproduced" for r in runs):
                eligible.append(case)
        raw_hits = sum(bool(judgments[(batch, c, mode, "buggy")]["candidate_match_ids"]) for c in eligible)
        proof_hits = sum(bool(judgments[(batch, c, mode, "buggy")]["valid_reproduced_match_ids"]) for c in eligible)
        fixed = sum(bool(judgments[(batch, c, mode, "fixed")]["candidate_match_ids"]) for c in eligible)
        assert set(eligible) == set(score["eligible_case_ids"])
        assert len(eligible) == score["eligible_pairs"] and len(groups) == score["planned_pairs"]
        assert raw_hits == score["candidate_known_issue_hits"]
        assert fixed == score["same_known_issue_alarms_on_fixed"]
        assert raw_hits / len(eligible) == score["candidate_detection_rate"]
        if mode == "evidence":
            assert proof_hits == score["valid_reproduced_known_issue_hits"]
            assert proof_hits / len(eligible) == score["evidence_detection_rate"]
            evidence_pairs += len(eligible)
            evidence_hits += proof_hits
            candidate_hits += raw_hits
    assert evidence_pairs == metrics["evidence_combined"]["eligible_pairs"]
    assert evidence_hits == metrics["evidence_combined"]["valid_reproduced_known_issue_hits"]
    assert candidate_hits == metrics["evidence_combined"]["known_issue_candidate_hits"]
    assert evidence_hits / evidence_pairs == metrics["evidence_combined"]["evidence_detection_rate"]
    assert automatic_accepts == metrics["agent_reported_reproduced_candidates"]
    assert dict(proof_statuses) == metrics["proof_status_counts_all_evidence_candidates"]
    assert len(records) == metrics["reviews"]
    assert sum(r["calls"] for r in records) == metrics["calls"]
    assert sum(r["window_review_completed"] for r in records) == metrics["window_complete"]
    assert sum(r["status"] == "completed" for r in records) == metrics["status_completed"]
    print(f"Verified {len(manifest['files'])} archived files, {len(records)} reports and score arithmetic; no API calls.")
    print("Semantic adjudications are model-assisted and still need human review.")


if __name__ == "__main__":
    main()
