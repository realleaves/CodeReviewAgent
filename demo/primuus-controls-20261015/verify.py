"""Check original evidence identity and derived presentation; no model calls."""

import hashlib
import json
from pathlib import Path
import zipfile


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "raw-manifest.json").read_text())
    summary = json.loads((root / "summary.json").read_text())
    archive = root / "raw-results.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["archive_sha256"]
    with zipfile.ZipFile(archive) as packed:
        assert packed.testzip() is None
        assert set(packed.namelist()) == set(manifest["files"])
        for name, digest in manifest["files"].items():
            assert hashlib.sha256(packed.read(name)).hexdigest() == digest
        frozen = json.loads(packed.read("implementation.json"))
        assert hashlib.sha256(packed.read("executed-driver.py")).hexdigest() == frozen["evaluation/evidence_controls.py"]
        feedback = json.loads(packed.read("feedback-results.json"))
        assert len(feedback["trials"]) == 6
        assert sum(t["api_calls"] for t in feedback["trials"]) == feedback["total_api_calls"] == 5
        assert all(t["finding_status"] != "reproduced" for t in feedback["trials"])
        assert summary["feedback"]["model_calls"] == 5
        for trial in feedback["trials"]:
            original_bytes = packed.read(trial["report"])
            original = json.loads(original_bytes)
            derived = json.loads((root / trial["report"]).read_text())
            assert derived["presentation_source_sha256"] == hashlib.sha256(original_bytes).hexdigest()
            for key in ["findings", "calls", "trace", "evidence_artifacts"]:
                assert original[key] == derived[key]
            assert not derived["run"]["window_review_completed"]
            assert derived["run"]["options"] == derived["diagnostic_options"]
    print(f"Verified {len(manifest['files'])} original files and six derived diagnostic reports; no API calls.")
    print("These are development controls, not a new end-to-end detection score.")


if __name__ == "__main__":
    main()
