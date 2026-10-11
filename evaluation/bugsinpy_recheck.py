"""Retry only reproduction after an environment fix, preserving every attempt."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.bugsinpy import save, summarize
from evaluation.bugsinpy_reproduce import reproduce_case


def main():
    parser = argparse.ArgumentParser(description="补齐环境后只复跑测试，不再次调用模型")
    parser.add_argument("--run", required=True)
    parser.add_argument("--work", default="outputs/bugsinpy-work")
    parser.add_argument("--cases", nargs="+", required=True)
    parser.add_argument("--python37-image", default="python:3.7-slim")
    parser.add_argument("--python38-image", default="code-review-bugsinpy:py38")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    root, work = Path(args.run).resolve(), Path(args.work).resolve()
    selection = json.loads((root / "selection.json").read_text())
    prepared = {c["id"]: c for c in json.loads((work / "prepared.json").read_text())}
    cases = {c["id"]: c for c in selection}
    config = json.loads((root / "run_config.json").read_text())
    manifest = json.loads((work / "manifest.json").read_text())
    if config["dataset_commit"] != manifest["dataset_commit"]:
        parser.error("工作目录的数据版本不同")
    if len(args.cases) != len(set(args.cases)):
        parser.error("样本不可重复")
    for name in args.cases:
        if name not in cases or cases[name] != prepared.get(name):
            parser.error("样本缺失或工作快照来源不一致")
    attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / "reproduction-attempts" / attempt
    directory.mkdir(parents=True, exist_ok=False)
    images = {"3.7": args.python37_image, "3.8": args.python38_image}
    outcomes = {}
    for name in args.cases:
        evidence = reproduce_case(cases[name], work, directory / name, images)
        outcomes[name] = {
            "status": evidence["status"],
            "evidence": str((directory / name / "result.json").relative_to(root)),
        }
        print(name, evidence["status"], flush=True)
    save(directory / "attempt.json", {"reason": args.reason, "outcomes": outcomes})
    result = json.loads((root / "results.json").read_text())
    for row in result["records"]:
        if row["case"] in outcomes:
            row["initial_reproduction"] = row.get(
                "initial_reproduction", row["reproduction"]
            )
            row["reproduction"] = outcomes[row["case"]]["status"]
            row["reproduction_evidence"] = outcomes[row["case"]]["evidence"]
    summarize(root, result["records"])
    for filename in ["adjudication-template.json", "adjudications.json"]:
        path = root / filename
        if not path.exists():
            continue
        decisions = json.loads(path.read_text())
        for row in decisions:
            if row["case"] in outcomes:
                row["reproduction"] = outcomes[row["case"]]["status"]
        save(path, decisions)
    # The first attempt and all model reports stay at their original paths.
    print("Attempt:", directory)


if __name__ == "__main__":
    main()
