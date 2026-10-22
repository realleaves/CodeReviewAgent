"""Verify the complete P2 archive offline, without importing model clients."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parent
PHASE = ROOT / "p2-mechanism-audit"


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parsed_response(response):
    text = response["raw_response"].strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:-1])
    return json.loads(text)


def identity(finding):
    return tuple(finding[k] for k in ["path", "line", "category", "title"])


def main():
    hashes = load(ROOT / "artifacts-sha256.json")
    actual_files = {
        str(p.relative_to(ROOT))
        for p in ROOT.rglob("*")
        if p.is_file()
        and p.name != "artifacts-sha256.json"
        and "__pycache__" not in p.parts
    }
    assert set(hashes) == actual_files, "Missing/untracked archive files"
    for relative, expected in hashes.items():
        assert digest(ROOT / relative) == expected, relative
    goal = load(PHASE / "p2-goal.json")
    setup = load(PHASE / "setup-p2.json")
    arms = load(PHASE / "arms-p2.json")
    before = load(PHASE / "budget-before.json")
    budget = load(PHASE / "budget.json")
    manifest = load(PHASE / "manifest.json")
    results = load(PHASE / "results.json")
    decisions = load(PHASE / "adjudications.json")
    saved_scores = load(PHASE / "scores.json")
    assert goal["selection"] == ["youtube-dl-2", "tornado-3"]
    assert goal["repetitions"] == manifest["repetitions"] == 1
    assert goal["variable"] == manifest["comparison_variable"] == "review_strategy"
    assert goal["window_call_limit"] == manifest["window_call_limit"] == 3
    assert (
        goal["budget"]["total_limit"]
        == manifest["global_limit"]
        == budget["limit"]
        == 20
    )
    assert manifest["phase_call_limit"] == 20
    assert before == {"limit": 20, "reserved": 0, "phases": {}}
    assert before == load(ROOT / "budget.json")
    assert budget == {"limit": 20, "reserved": 12, "phases": {"p2-mechanism-audit": 12}}
    for name in ["p2-goal.json", "setup-p2.json", "arms-p2.json"]:
        assert (PHASE / name).read_bytes() == (ROOT / name).read_bytes()
    assert arms == manifest["arms"] == goal["arms"]
    assert {k: v for k, v in arms["baseline"].items() if k != "review_strategy"} == {
        k: v for k, v in arms["mechanism_audit"].items() if k != "review_strategy"
    }
    assert manifest["input_windows"] == setup["window_records"]
    assert manifest["source_sha256"] == setup["source_sha256"]
    assert all(manifest["model"][k] == v for k, v in setup["model"].items())
    assert setup["model"] == {
        "model": "deepseek-flash",
        "thinking_mode": "disabled",
        "temperature": 0.1,
        "max_output_tokens": 6000,
        "provider_is_deepseek": True,
    }
    assert results["status"] == "sampled" and results["source_frozen"] is True
    assert results["budget"] == budget
    assert len(results["records"]) == len(decisions) == 8
    assert all(
        r["status"] == "completed" and r["error"] is None for r in results["records"]
    )
    for relative, expected in manifest["source_sha256"].items():
        assert digest(PHASE / "implementation" / relative) == expected
    for relative, expected in load(PHASE / "protected.json").items():
        assert digest(PHASE / "references/protected" / relative) == expected
    assert digest(PHASE / "reference-rubric.json") == digest(
        PHASE / "references/protected/evaluation/bugsinpy-rubric.json"
    )

    # Exact production-only source files reproduce the setup snapshot digests.
    with zipfile.ZipFile(PHASE / "input-sources.zip") as archive:
        assert archive.testzip() is None
        members = archive.namelist()
        assert len(members) == len(set(members)) == 1726
        groups = {}
        for name in members:
            parts = PurePosixPath(name).parts
            assert (
                not name.startswith("/") and ".." not in parts and name.endswith(".py")
            )
            key, relative = "/".join(parts[:2]), "/".join(parts[2:])
            assert key in setup["snapshots"]
            groups.setdefault(key, {})[relative] = archive.read(name).decode("utf-8")
        assert set(groups) == set(setup["snapshots"])
        for key, files in groups.items():
            h = hashlib.sha256()
            for path, content in sorted(files.items()):
                h.update(path.encode() + b"\0" + content.encode() + b"\0")
            assert {"files": len(files), "snapshot_sha256": h.hexdigest()} == setup[
                "snapshots"
            ][key]

    attempts = [
        json.loads(line) for line in (PHASE / "attempts.jsonl").read_text().splitlines()
    ]
    assert [a["id"] for a in attempts] == list(range(1, 13))
    reserved = {a["id"]: a for a in attempts}
    seen, payloads, prompts = set(), {}, {}
    decision_map = {(d["case"], d["mode"], d["variant"]): d for d in decisions}
    for row in results["records"]:
        folder = PHASE / row["folder"]
        assert load(folder / "record.json") == row
        requests = sorted((folder / "requests").glob("*/request.json"))
        responses = sorted((folder / "requests").glob("*/response.json"))
        count = 1 if row["strategy"] == "baseline" else 2
        assert len(requests) == len(responses) == row["api_calls"] == count
        assert row["tool_reads"] == []
        payload = load(folder / "initial-payload.json")
        pair = row["case"], row["side"]
        if pair in payloads:
            assert payload == payloads[pair]
        payloads[pair] = payload
        raw = []
        for i, (request_path, response_path) in enumerate(zip(requests, responses)):
            request, response = load(request_path), load(response_path)
            attempt = request["reservation"]
            assert attempt == response["reservation"] == reserved[attempt["id"]]
            assert attempt["id"] not in seen
            seen.add(attempt["id"])
            assert attempt["phase"] == "p2-mechanism-audit"
            assert all(attempt["label"][k] == row[k] for k in attempt["label"])
            assert (
                response["error_type"] is None and response["call"] == row["calls"][i]
            )
            assert response["call"]["status"] == "completed"
            assert request["generation"] == {
                k: setup["model"][k]
                for k in ["model", "temperature", "max_output_tokens", "thinking_mode"]
            }
            messages = request["messages"]
            assert [m["role"] for m in messages] == ["system", "user"]
            stage = response["call"]["stage"]
            if stage in prompts:
                assert messages[0]["content"] == prompts[stage]
            prompts[stage] = messages[0]["content"]
            assert not any(case in messages[0]["content"] for case in goal["selection"])
            request_payload = json.loads(messages[1]["content"])
            if i == 0:
                assert request_payload == payload
            else:
                assert request_payload == {
                    **payload,
                    "initial_checked": raw[0]["checked"],
                    "initial_hypotheses": raw[0]["hypotheses"],
                    "initial_findings": raw[0]["findings"],
                }
            raw.append(parsed_response(response))
        final = raw[-1]["findings"]
        if row["strategy"] == "mechanism_audit":
            (trace,) = [t for t in row["trace"] if t["stage"] == "mechanism_audit"]
            initial_ids = {identity(f) for f in raw[0]["findings"]}
            final_ids = {identity(f) for f in final}
            fallback = not final
            assert trace["fallback_initial"] is fallback
            assert len(trace["removed"]) == (
                0 if fallback else len(initial_ids - final_ids)
            )
            assert len(trace["added"]) == (
                0 if fallback else len(final_ids - initial_ids)
            )
            assert raw[0] == raw[1], (
                "Frozen P2 audit returned the same hypotheses/findings"
            )
            review = decision_map[row["case"], row["strategy"], row["side"]][
                "initial_hypothesis_review"
            ]
            assert review["hypothesis_count"] == len(raw[0]["hypotheses"])
            assert review["reference_hypothesis_present"] is False
            assert review["reference_finding_present"] is False
            assert review["source_request"] == str(requests[1].relative_to(PHASE))
            if fallback:
                final = raw[0]["findings"]
        assert len(final) == len(row["findings"])
        assert all(
            all(stored[k] == v for k, v in candidate.items())
            for candidate, stored in zip(final, row["findings"])
        )
    assert seen == set(reserved)

    # Recompute with the exact archived scorer; no project/model import is needed.
    scorer = PHASE / "scoring/discovery_mechanism_audit_score.py"
    namespace = {"__name__": "frozen_p2_scorer"}
    exec(compile(scorer.read_text(), str(scorer), "exec"), namespace)
    assert namespace["score"](PHASE, decisions) == saved_scores
    baseline, audit = saved_scores["metrics"]
    assert baseline["candidate_hits"] == audit["candidate_hits"] == 0
    assert baseline["fixed_side_alarms"] == audit["fixed_side_alarms"] == 0
    assert baseline["eligible_pairs"] == audit["eligible_pairs"] == 2
    assert (baseline["calls"], audit["calls"]) == (4, 8)
    assert (baseline["candidate_findings"], audit["candidate_findings"]) == (6, 7)
    assert audit["audit_windows"] == 4 and audit["fallback_initial"] == 1
    assert audit["audit_removed"] == audit["audit_added"] == 0
    assert saved_scores["smoke_gate_met"] is False
    print(
        json.dumps(
            {
                "status": "PASS",
                "windows": 8,
                "requests": 12,
                "responses": 12,
                "adjudications": 8,
                "finding_reviews": 13,
                "source_files": 1726,
                "budget_used": 12,
                "budget_limit": 20,
                "candidate_hits": {"baseline": 0, "mechanism_audit": 0},
                "default": "baseline",
                "model_calls_by_verifier": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
