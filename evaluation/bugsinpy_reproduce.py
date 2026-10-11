"""Run trusted benchmark test selectors in disposable, restricted containers."""

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid


def test_commands(text):
    """Accept the selected corpus' Python unittest/pytest commands, never a shell."""
    commands = []
    for line in text.splitlines():
        tokens = shlex.split(line)
        if not tokens:
            continue
        if tokens[:3] == ["python", "-m", "unittest"] or tokens[0] == "pytest":
            if any(re.search(r"[;&|<>`$\n]", token) for token in tokens):
                raise ValueError("Shell expressions are not benchmark test arguments")
            if tokens[0] == "pytest":
                tokens = ["python", "-m", "pytest", *tokens[1:]]
            commands.append(tokens)
        else:
            raise ValueError("Unsupported benchmark command; explicit adapter required")
    if not commands:
        raise ValueError("Empty test selector")
    return commands


def run_test(root, image, commands, output, timeout=90, locale="C.UTF-8"):
    output.mkdir(parents=True, exist_ok=False)
    inspected = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    details = json.loads(inspected.stdout)[0]
    records = []
    with tempfile.TemporaryDirectory(prefix="bugsinpy-reproduction-") as temp:
        work = Path(temp) / "work"
        shutil.copytree(root, work)
        for index, command in enumerate(commands):
            name = "code-review-test-" + uuid.uuid4().hex[:12]
            args = [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "128",
                "--memory",
                "512m",
                "--cpus",
                "1",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--tmpfs",
                "/tmp:rw,nosuid,size=128m",
                "--mount",
                f"type=bind,src={work},dst=/work",
                "--workdir",
                "/work",
                "-e",
                "PYTHONPATH=/work",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "-e",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
                "-e",
                f"LC_ALL={locale}",
                "-e",
                "PYTHONCOERCECLOCALE=0",
                "-e",
                "PYTHONUTF8=0",
                details["Id"],
                *command,
            ]
            start = time.monotonic()
            try:
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=timeout
                )
                text = result.stdout + result.stderr
                exit_code = result.returncode
                timed_out = False
            except subprocess.TimeoutExpired as exc:
                subprocess.run(
                    ["docker", "rm", "--force", name], capture_output=True, timeout=15
                )
                text = (
                    (exc.stdout or b"").decode(errors="replace")
                    if isinstance(exc.stdout, bytes)
                    else (exc.stdout or "")
                )
                exit_code, timed_out = None, True
            log = output / f"test-{index + 1}.log"
            log.write_text(text)
            # A nonzero process is not enough: require that a test actually ran.
            ran = bool(
                re.search(r"Ran [1-9]\d* tests?", text)
                or re.search(r"\d+ (?:passed|failed)", text)
            )
            errors = bool(
                re.search(
                    r"ModuleNotFoundError|ImportError|SyntaxError|not found:|no tests ran|PermissionError",
                    text,
                )
            )
            total_match = re.search(r"Ran ([1-9]\d*) tests?", text)
            skipped_match = re.search(r"skipped=(\d+)", text)
            all_skipped = bool(
                total_match
                and skipped_match
                and int(total_match[1]) <= int(skipped_match[1])
            )
            records.append(
                {
                    "command": command,
                    "exit_code": exit_code,
                    "timeout": timed_out,
                    "test_executed": ran and not all_skipped,
                    "environment_error": errors,
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                    "log": log.name,
                    "log_sha256": hashlib.sha256(text.encode()).hexdigest(),
                }
            )
    valid = all(
        r["test_executed"] and not r["environment_error"] and not r["timeout"]
        for r in records
    )
    version = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            details["Id"],
            "python",
            "--version",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    result = {
        "image": image,
        "image_id": details["Id"],
        "python_actual": version.stdout.strip(),
        "environment": {
            "LC_ALL": locale,
            "PYTHONCOERCECLOCALE": "0",
            "PYTHONUTF8": "0",
        },
        "valid_test_execution": valid,
        "all_passed": valid and all(r["exit_code"] == 0 for r in records),
        "has_failure": valid and any(r["exit_code"] != 0 for r in records),
        "tests": records,
    }
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    return result


def reproduce_case(case, work, output, images):
    result = {
        "case": case["id"],
        "python_declared": case["python_version"],
        "variants": {},
    }
    image = images[".".join(case["python_version"].split(".")[:2])]
    commands = test_commands(case["test_command"])
    # This encoding defect is masked when the operating-system locale is UTF-8.
    # Change only the locale, identically for the two variants; do not alter tests.
    locale = "C" if case["id"] == "PySnooper-1" else "C.UTF-8"
    for side in ["buggy", "fixed"]:
        result["variants"][side] = run_test(
            work / case["snapshot_paths"][side],
            image,
            commands,
            output / side,
            locale=locale,
        )
    result["status"] = (
        "reproduced"
        if result["variants"]["buggy"]["has_failure"]
        and result["variants"]["fixed"]["all_passed"]
        else "not_reproduced"
    )
    result["environment_note"] = (
        "Same Python major/minor as dataset; actual micro-version and image ID recorded. Minimal test dependencies, not the original complete pip freeze."
    )
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    return result
