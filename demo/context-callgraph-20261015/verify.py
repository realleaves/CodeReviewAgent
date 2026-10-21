"""Verify archived payloads and code spans without model or target execution."""

import ast
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent


def digest(value):
    return hashlib.sha256(value).hexdigest()


def numbered(source, start, end):
    lines = source.splitlines()
    return "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))


def constant_source(source, name):
    tree = ast.parse(source)
    return next(
        ast.get_source_segment(source, node)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
    )


def main():
    manifest = json.loads((HERE / "raw-manifest.json").read_text())
    metrics = json.loads((HERE / "metrics.json").read_text())
    protocol = json.loads((HERE / "protocol.json").read_text())
    implementation = json.loads((HERE / "implementation.json").read_text())
    assert (
        digest((HERE / "raw-contexts.zip").read_bytes()) == manifest["archive_sha256"]
    )
    with zipfile.ZipFile(HERE / "raw-contexts.zip") as z:
        assert set(z.namelist()) == set(manifest["files"])
        for name, hashed in manifest["files"].items():
            assert digest(z.read(name)) == hashed, name
        for path, hashed in protocol["baseline_sha256"].items():
            assert digest(z.read("baseline/" + path)) == hashed, path
        for path, hashed in implementation.items():
            assert digest(z.read("implementation/" + path)) == hashed, path
        for path in [
            "src/reproduction.py",
            "src/reproduction_runner.py",
            "src/report.py",
        ]:
            assert z.read("implementation/" + path) == z.read("baseline/" + path)
        old_source = z.read("baseline/src/agents.py").decode()
        new_source = z.read("implementation/src/agents.py").decode()
        for name in [
            "COMMON",
            "REVIEW_PROMPT",
            "VERIFY_PROMPT",
            "EVIDENCE_REVIEW_PROMPT",
        ]:
            assert constant_source(old_source, name) == constant_source(
                new_source, name
            )
        results = json.loads(z.read("preview/results.json"))
        assert (HERE / "preview-results.json").read_bytes() == z.read(
            "preview/results.json"
        )
        files = json.loads(z.read("preview/files.json"))
        for path, hashed in files.items():
            assert digest(z.read("preview/" + path)) == hashed
        records = results["records"]
        assert len(records) == metrics["windows"] == 18
        assert {r["case"] for r in records} == set(protocol["development_cases"])
        assert len(protocol["development_cases"]) == metrics["cases"] == 6
        for record in records:
            prefix = "preview/" + record["folder"] + "/"
            old, new = [
                json.loads(z.read(prefix + s + ".json"))
                for s in ["legacy", "callgraph"]
            ]
            source = json.loads(z.read(prefix + "source.json"))
            for strategy in ["legacy", "callgraph"]:
                assert (
                    digest(z.read(prefix + strategy + ".json"))
                    == record["payload_sha256"][strategy]
                )
            for key in ["primary_path", "start", "end", "code"]:
                assert old[key] == new[key]
            path, start, end = new["primary_path"], new["start"], new["end"]
            assert new["code"] == numbered(source[path], start, end)
            assert record["original_prompt_and_legacy_payload_preserved"]
            for payload, strategy in [(old, "legacy"), (new, "callgraph")]:
                size = len(
                    json.dumps(
                        {k: payload[k] for k in ["context", "documents"]},
                        ensure_ascii=False,
                    )
                )
                assert size == record[strategy + "_supplemental_chars"]
            assert record["callgraph_supplemental_chars"] <= 10000
            for entries in [new["context"], new["documents"]]:
                for item in entries:
                    if "code" in item:
                        assert item["code"] == numbered(
                            source[item["path"]], item["start"], item["end"]
                        )
                        if item["path"] == path:
                            assert item["end"] < start or item["start"] > end
        assert (
            metrics["windows_with_static_caller_context"]
            == sum(r["relations"].get("caller", 0) > 0 for r in records)
            == 12
        )
        assert (
            metrics["legacy_total_supplemental_chars"]
            == sum(r["legacy_supplemental_chars"] for r in records)
            == 48057
        )
        assert (
            metrics["callgraph_total_supplemental_chars"]
            == sum(r["callgraph_supplemental_chars"] for r in records)
            == 97519
        )
        assert results["api_calls"] == metrics["model_api_calls"] == 0
        assert not results["recall_or_precision_measured"]
        assert not metrics["candidate_recall_measured"]
        assert results["source_frozen"]
    print(
        f"PASS: {len(manifest['files'])} archived files; 18 paired contexts, unchanged primary code, exact source spans, 10000-character cap; no performance claim."
    )


if __name__ == "__main__":
    main()
