"""Verify archived accounting, inputs, executions and recomputed scores offline."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import runpy
import tempfile
import zipfile


HERE = Path(__file__).resolve().parent


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    manifest = read(HERE / "raw-manifest.json")
    archive_path = HERE / "raw-results.zip"
    assert sha(archive_path.read_bytes()) == manifest["archive_sha256"]
    with tempfile.TemporaryDirectory(prefix="discovery-audit-") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive_path) as archive:
            assert len(archive.namelist()) == len(set(archive.namelist()))
            assert set(archive.namelist()) == set(manifest["files"])
            for name, expected in manifest["files"].items():
                path = PurePosixPath(name)
                assert not path.is_absolute() and ".." not in path.parts
                assert sha(archive.read(name)) == expected, name
            archive.extractall(root)
        support = root / "audit-support"
        auditor = runpy.run_path(str(support / "evaluation/verify_discovery_run.py"))
        audit = auditor["verify"](root, project=support)
        assert audit == read(HERE / "audit.json")
        grader = runpy.run_path(str(support / "evaluation/bugsinpy_score.py"))["score_pairs"]
        development = {
            (r["case"], r["variant"]): r["official_reproduction"]
            for r in read(support / "development-run-records.json")
        }
        new_reproductions = read(root / "holdout-reproduction/results.json")
        assert len(new_reproductions) == 4
        for result in new_reproductions:
            assert result["status"] == "reproduced"
            assert result["variants"]["buggy"]["has_failure"]
            assert result["variants"]["fixed"]["all_passed"]
            for side, execution in result["variants"].items():
                assert execution["valid_test_execution"]
                for test in execution["tests"]:
                    assert test["test_executed"] and not test["environment_error"]
                    log = root / "holdout-reproduction" / result["case"] / side / test["log"]
                    assert sha(log.read_bytes()) == test["log_sha256"]
        for phase_name in ["r0-context", "r1-thinking", "r2-output-budget", "v-holdout"]:
            phase = root / phase_name
            records = read(phase / "results.json")["records"]
            protocol = read(phase / "manifest.json")
            groups = read(phase / "groups.json")
            decisions = read(phase / "adjudications.json")
            by_key = {(d["case"], d["mode"], d["variant"]): d for d in decisions}
            assert len(by_key) == len(decisions) == len(groups)
            rows = []
            for group in groups:
                arm, repetition = group["mode"].split("/rep")
                actual = [r for r in records if r["case"] == group["case"]
                          and r["side"] == group["variant"]
                          and r["strategy"] == arm and r["repetition"] == int(repetition)]
                expected_windows = sum(w["case"] == group["case"] and w["side"] == group["variant"]
                                       for w in protocol["input_windows"])
                complete = len(actual) == expected_windows and all(r["status"] == "completed" for r in actual)
                assert group["status"] == ("completed" if complete else "partial")
                findings = {f["id"]: f for r in actual for f in r["findings"]}
                decision = by_key[group["case"], group["mode"], group["variant"]]
                assert findings == {f["id"]: f for f in group["findings"]}
                assert findings == {f["id"]: f for f in decision["active_findings"]}
                reproduction = (
                    next(r["status"] for r in new_reproductions if r["case"] == group["case"])
                    if phase_name == "v-holdout"
                    else development[group["case"], group["variant"]]
                )
                rows.append({"case": group["case"], "mode": group["mode"], "variant": group["variant"],
                             "status": group["status"], "reproduction": reproduction})
            stored = read(phase / "scores.json")
            assert stored["metrics"] == grader(rows, decisions)["metrics"]
            assert sha((phase / "adjudications.json").read_bytes()) == stored["decisions_sha256"]
        origin = read(root / "r1-origin-audit/summary.json")
        assert origin["api_calls"] == 0 and len(origin["checks"]) == 3
        for check in origin["checks"]:
            execution = check["execution"]
            assert execution["tests_run"] == 2 and execution["failures"] == 0
            assert execution["errors"] == (0 if check["evaluator_patched_copy"] else 1)
        metrics = read(HERE / "metrics.json")
        assert metrics["budget"] == read(root / "budget.json")
        assert metrics["windows"] == audit["audited_windows"]
        assert metrics["additional_improvement_rounds"] == 2
        for name in ["metrics.json", "audit.json"]:
            assert (HERE / name).read_bytes() == (root / name).read_bytes()
        print(json.dumps({"status": "PASS", "archived_files": len(manifest["files"]), **audit}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
