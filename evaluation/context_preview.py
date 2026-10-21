"""Offline paired context inspection on preregistered, previously missed windows."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.bugsinpy_review import reviewer_files
from src.agents import EVIDENCE_REVIEW_PROMPT, ReviewAgents
from src.code_index import Chunk, CodeIndex, numbered
from src.repository import snapshot_digest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="离线检查上下文选择，不调用模型、不运行目标代码"
    )
    parser.add_argument("--experiment", default="outputs/context-callgraph-20261015")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    experiment, out = Path(args.experiment).resolve(), Path(args.output).resolve()
    protocol = json.loads((experiment / "manifest.json").read_text())
    baseline = experiment / "baseline"
    for relative, hashed in protocol["baseline_sha256"].items():
        assert digest(baseline / relative) == hashed
    spec = importlib.util.spec_from_file_location(
        "frozen_context_baseline",
        baseline / "src/__init__.py",
        submodule_search_locations=[str(baseline / "src")],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    spec.loader.exec_module(package)
    old = __import__("frozen_context_baseline.agents", fromlist=["ReviewAgents"])
    assert old.EVIDENCE_REVIEW_PROMPT == EVIDENCE_REVIEW_PROMPT
    out.mkdir(parents=True, exist_ok=False)
    implementation = {
        str(p.relative_to(root)): digest(p) for p in sorted((root / "src").glob("*.py"))
    }
    save(
        out / "manifest.json",
        {
            "protocol": protocol,
            "implementation_sha256": implementation,
            "api_calls": 0,
            "scope": "Initial payload only, not full tool conversation, model inference, recall or proof success. Both arms receive the same original production-only index; resources remain empty as in the historical benchmark.",
        },
    )
    batch = root / "outputs/evidence-original20-20261014"
    selection = json.loads((batch / "selection.json").read_text())
    records = []
    for case_id in protocol["development_cases"]:
        case = next(c for c in selection if c["id"] == case_id)
        for side in ["buggy", "fixed"]:
            historical = json.loads(
                (
                    batch / "reviews" / case_id / "evidence" / side / "report.json"
                ).read_text()
            )
            files, _ = reviewer_files(
                root / "outputs/bugsinpy-work" / case["snapshot_paths"][side]
            )
            index = CodeIndex(files)
            assert (
                snapshot_digest(files)
                == historical["repository"]["indexed_snapshot_sha256"]
            )
            original, legacy, revised = (
                old.ReviewAgents(index, None),
                ReviewAgents(index, None),
                ReviewAgents(index, None, "callgraph"),
            )
            for n, trace in enumerate(
                t for t in historical["trace"] if t["stage"] == "review"
            ):
                path, start, end = trace["path"], trace["start"], trace["end"]
                part = Chunk(path, start, end, numbered(files[path], start, end))
                captured = {}

                def capture(stage, prompt, payload):
                    assert prompt == EVIDENCE_REVIEW_PROMPT
                    captured.update(payload)
                    return '{"findings":[]}'

                original._run = capture
                original.review(part, [], evidence=True)
                assert captured == legacy.review_payload(part, [], evidence=True)
                began = time.monotonic()
                new = revised.review_payload(part, [], evidence=True)
                seconds = round(time.monotonic() - began, 4)
                for key in ["primary_path", "start", "end", "code"]:
                    assert new[key] == captured[key]
                supplement = {k: new[k] for k in ["context", "documents"]}
                assert len(json.dumps(supplement, ensure_ascii=False)) <= 10000
                for entries in supplement.values():
                    for item in entries:
                        if "code" not in item:
                            continue
                        assert item["path"] in files
                        assert item["code"] == numbered(
                            files[item["path"]], item["start"], item["end"]
                        )
                        if item["path"] == path:
                            assert item["end"] < start or item["start"] > end
                folder = out / f"{case_id}-{side}-{n + 1}"
                folder.mkdir()
                save(folder / "legacy.json", captured)
                save(folder / "callgraph.json", new)
                source_paths = {path} | {
                    i["path"] for i in supplement["context"] if "code" in i
                }
                save(
                    folder / "source.json", {p: files[p] for p in sorted(source_paths)}
                )
                old_supplement = {k: captured[k] for k in ["context", "documents"]}
                records.append(
                    {
                        "case": case_id,
                        "side": side,
                        "path": path,
                        "start": start,
                        "end": end,
                        "original_prompt_and_legacy_payload_preserved": True,
                        "legacy_supplemental_chars": len(
                            json.dumps(old_supplement, ensure_ascii=False)
                        ),
                        "callgraph_supplemental_chars": len(
                            json.dumps(supplement, ensure_ascii=False)
                        ),
                        "relations": {
                            relation: sum(
                                i["relation"] == relation for i in new["context"]
                            )
                            for relation in sorted(
                                {i["relation"] for i in new["context"]}
                            )
                        },
                        "legacy_context_symbols": [
                            i["name"] for i in captured["context"]
                        ],
                        "retrieval_seconds": seconds,
                        "folder": folder.relative_to(out).as_posix(),
                        "payload_sha256": {
                            s: digest(folder / f"{s}.json")
                            for s in ["legacy", "callgraph"]
                        },
                    }
                )
            print(case_id, side, "offline payloads saved", flush=True)
    assert all(digest(root / p) == h for p, h in implementation.items())
    save(
        out / "results.json",
        {
            "api_calls": 0,
            "cases": len(protocol["development_cases"]),
            "windows": len(records),
            "records": records,
            "source_frozen": True,
            "recall_or_precision_measured": False,
        },
    )
    save(
        out / "files.json",
        {str(p.relative_to(out)): digest(p) for p in sorted(out.rglob("*.json"))},
    )


if __name__ == "__main__":
    main()
