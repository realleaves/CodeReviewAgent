"""Offline audit of persistent request accounting and frozen experiment sources."""

import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root, project=None):
    state = json.loads((root / "budget.json").read_text())
    events = [
        json.loads(line) for line in (root / "attempts.jsonl").read_text().splitlines()
    ]
    assert len(events) == state["reserved"] <= state["limit"] == 600
    assert [e["id"] for e in events] == list(range(1, len(events) + 1))
    requests = list(root.glob("**/requests/*/request.json"))
    by_id = {}
    unknown_responses = []
    for path in requests:
        request = json.loads(path.read_text())
        reservation = request["reservation"]
        assert reservation["id"] not in by_id
        by_id[reservation["id"]] = path
        assert reservation == events[reservation["id"] - 1]
        response = path.with_name("response.json")
        if response.exists():
            assert json.loads(response.read_text())["reservation"] == reservation
        else:
            interruption = json.loads(path.with_name("interruption.json").read_text())
            assert interruption["reservation"] == reservation
            assert interruption["status"] == "response_missing_process_absent"
            record = json.loads((path.parents[2] / "record.json").read_text())
            assert record["status"] == "failed" and record["findings"] == []
            assert record["error"]["type"] == "ProcessInterrupted"
            assert any(
                c.get("reservation_id") == reservation["id"]
                and c.get("response_unknown")
                for c in record["calls"]
            )
            unknown_responses.append(reservation["id"])
    assert set(by_id) == set(range(1, state["reserved"] + 1))
    phases = {}
    for event in events:
        phases[event["phase"]] = phases.get(event["phase"], 0) + 1
    assert phases == state["phases"]
    windows = 0
    protected = json.loads((root / "protected.json").read_text())
    project = (
        Path(project) if project is not None else Path(__file__).resolve().parents[1]
    )
    assert all(digest(project / p) == h for p, h in protected.items())
    assert (
        digest(root / "reference-rubric.json")
        == protected["evaluation/bugsinpy-rubric.json"]
    )
    for phase in sorted(root.iterdir()):
        if not phase.is_dir() or not (phase / "manifest.json").exists():
            continue
        manifest = json.loads((phase / "manifest.json").read_text())
        if "input_windows" not in manifest:
            continue
        results = json.loads((phase / "results.json").read_text())
        assert results["status"] in {"sampled", "sampled_with_interruption"}
        for relative, hashed in manifest["source_sha256"].items():
            assert digest(phase / "implementation" / relative) == hashed
        if "rubric_sha256" in manifest:
            assert digest(phase / "reference-rubric.json") == manifest["rubric_sha256"]
        for relative, hashed in manifest.get("protected_sha256", {}).items():
            parts = Path(relative).parts
            target = (
                root.joinpath(*parts[2:])
                if parts[:2] == ("outputs", "discovery-goal-20261015")
                else project / relative
            )
            assert digest(target) == hashed
        records = results["records"]
        expected = (
            manifest["repetitions"]
            * len(manifest["strategies"])
            * len(manifest["input_windows"])
        )
        assert len(records) == expected
        assert sum(r["api_calls"] for r in records) == state["phases"][phase.name]
        for record in records:
            folder = phase / record["folder"]
            assert record == json.loads((folder / "record.json").read_text())
            assert record["api_calls"] <= manifest["window_call_limit"]
            calls = list((folder / "requests").glob("*/request.json"))
            assert len(calls) == record["api_calls"]
            payload = json.loads((folder / "initial-payload.json").read_text())
            assert payload["primary_path"] == record["path"]
            assert (
                payload["start"] == record["start"] and payload["end"] == record["end"]
            )
            if calls:
                first = sorted(calls)[0]
                messages = json.loads(first.read_text())["messages"]
                assert json.loads(messages[1]["content"]) == payload
            assert (
                not {"case", "side", "variant", "reference_issue", "test_command"}
                & payload.keys()
            )
            for request_path in calls:
                request = json.loads(request_path.read_text())
                if "arms" in manifest:
                    arm = manifest["arms"][record["strategy"]]
                else:
                    assert phase.name == "r0-context"
                    arm = {"thinking_mode": manifest["model"]["thinking_mode"]}
                if "generation" not in request:
                    # r0 predates per-request generation fields. Its original
                    # model manifest and provider call metadata are retained.
                    assert phase.name == "r0-context"
                    call = json.loads(
                        request_path.with_name("response.json").read_text()
                    )["call"]
                    assert call["thinking_mode"] == arm["thinking_mode"]
                    assert (
                        call["max_output_tokens"]
                        == manifest["model"]["max_output_tokens"]
                    )
                    continue
                generation = request["generation"]
                assert generation["thinking_mode"] == arm["thinking_mode"]
                assert generation["max_output_tokens"] == arm.get(
                    "max_output_tokens", 6000
                )
                assert generation["model"] == manifest["model"]["model"]
            windows += 1
        for window in manifest["input_windows"]:
            for repetition in range(1, manifest["repetitions"] + 1):
                pair = [
                    r
                    for r in records
                    if r["case"] == window["case"]
                    and r["side"] == window["side"]
                    and r["path"] == window["path"]
                    and r["start"] == window["start"]
                    and r["end"] == window["end"]
                    and r["repetition"] == repetition
                ]
                assert len(pair) == len(manifest["strategies"])
                payloads = [
                    json.loads(
                        (phase / r["folder"] / "initial-payload.json").read_text()
                    )
                    for r in pair
                ]
                for payload in payloads[1:]:
                    for key in ["primary_path", "start", "end", "code"]:
                        assert payload[key] == payloads[0][key]
                    if manifest.get("comparison_variable") in {
                        "thinking_mode",
                        "max_output_tokens",
                        "review_strategy",
                    }:
                        assert payload == payloads[0]
    return {
        "provider_attempts": state["reserved"],
        "limit": state["limit"],
        "phases": phases,
        "audited_windows": windows,
        "unknown_response_attempts_charged": unknown_responses,
        "original_reference_rubric_and_scorer_unchanged": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
