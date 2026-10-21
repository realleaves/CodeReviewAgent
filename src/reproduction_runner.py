"""Trusted container harness. This file is mounted read-only, never from the target."""

import json
from pathlib import Path
import sys
import traceback
import unittest


def main():
    specification = json.loads(Path("/harness/spec.json").read_text())
    source = Path("/harness/test_reproduction.py").read_text()
    # Preload harness dependencies before putting untrusted source on the path.
    sys.path.extend(["/work", "/work/src"])
    target = "/work/" + specification["path"]
    visited, calls = set(), set()

    def trace(frame, event, arg):
        if frame.f_code.co_filename == target:
            if event == "line" and len(visited) < 2000:
                visited.add(frame.f_lineno)
            if event == "call" and len(calls) < 100:
                calls.add((frame.f_code.co_name, frame.f_code.co_firstlineno))
        return trace

    class Result(unittest.TestResult):
        def __init__(self):
            super().__init__()
            self.observations = []

        def record(self, test, err, outcome):
            self.observations.append(
                {
                    "test": test.id(),
                    "outcome": outcome,
                    "exception_type": err[0].__name__,
                    "message": str(err[1])[:3000],
                    "traceback": "".join(traceback.format_exception(*err))[-10000:],
                    "traceback_frames": [
                        {
                            "path": frame.filename,
                            "line": frame.lineno,
                            "function": frame.name,
                        }
                        for frame in traceback.extract_tb(err[2])[-40:]
                    ],
                }
            )

        def addFailure(self, test, err):
            super().addFailure(test, err)
            self.record(test, err, "failure")

        def addError(self, test, err):
            super().addError(test, err)
            self.record(test, err, "error")

    result = Result()
    load_error = None
    sys.settrace(trace)
    try:
        namespace = {
            "__name__": "generated_reproduction",
            "__file__": "/harness/test_reproduction.py",
        }
        exec(compile(source, "/harness/test_reproduction.py", "exec"), namespace)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            namespace["ReproductionTest"]
        )
        # Import-time definitions do not establish that the test exercised them.
        visited.clear()
        calls.clear()
        suite.run(result)
    except BaseException as error:
        load_error = {
            "exception_type": type(error).__name__,
            "message": str(error)[:2000],
        }
    finally:
        sys.settrace(None)
    record = {
        "python": sys.version.split()[0],
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "load_error": load_error,
        "observations": result.observations,
        "target_lines": sorted(visited),
        "target_calls": sorted(calls),
        "target_trace_scope": "test_execution",
    }
    print(
        "\nCODE_REVIEW_EXECUTION=" + json.dumps(record, ensure_ascii=True), flush=True
    )


if __name__ == "__main__":
    main()
