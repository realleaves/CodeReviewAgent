"""Run installed scanners against a clean snapshot, ignoring repo configs."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

from .code_index import CodeIndex, finding_id, numbered
from .schemas import Finding


def make_finding(
    index: CodeIndex,
    *,
    path: str,
    line: int,
    title: str,
    source: str,
    rule: str,
    explanation: str,
    severity: str = "low",
    category: str = "quality",
    suggestion: str = "根据诊断检查对应代码。",
) -> Finding | None:
    if path not in index.files:
        return None
    lines = index.files[path].splitlines()
    if not lines or not 1 <= line <= len(lines):
        return None
    return Finding(
        path=path,
        line=line,
        end_line=line,
        title=title[:200],
        severity=severity,
        category=category,
        explanation=explanation[:2000],
        trigger="触发条件需结合业务调用确认。",
        evidence=f"{source} {rule}: {explanation}"[:2000],
        suggestion=suggestion,
        id=finding_id(path, line, rule, title),
        source=source,
        rule=rule,
        snippet=numbered(index.files[path], max(1, line - 2), line + 2),
    )


def analyze(
    index: CodeIndex, paths: list[str], timeout: int = 45
) -> tuple[list[Finding], list[dict]]:
    findings = []
    stages = []
    for path in paths:
        if path in index.syntax_errors:
            error = index.syntax_errors[path]
            finding = make_finding(
                index,
                path=path,
                line=error["line"],
                title="Python 语法解析失败",
                source="ast",
                rule="SYNTAX",
                explanation=error["message"],
                severity="high",
                category="bug",
                suggestion="修复语法后重新审查。",
            )
            if finding:
                findings.append(finding)
    stages.append({"stage": "ast", "status": "completed", "files": len(paths)})
    with tempfile.TemporaryDirectory(prefix="code-review-scan-") as directory:
        root = Path(directory)
        snapshot = root / "snapshot"
        snapshot.mkdir()
        for path in paths:
            target = snapshot / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(index.files[path], encoding="utf-8")
        commands = {
            "ruff": [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--isolated",
                "--no-cache",
                "--select",
                "F,E9,B",
                "--output-format",
                "json",
                str(snapshot),
            ],
            "bandit": [
                sys.executable,
                "-m",
                "bandit",
                "-r",
                str(snapshot),
                "-f",
                "json",
                "-q",
                "--ignore-nosec",
            ],
        }
        for tool, command in commands.items():
            try:
                result = subprocess.run(
                    command,
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                if result.returncode not in (0, 1):
                    raise RuntimeError("扫描器执行失败")
                data = json.loads(result.stdout)
                diagnostics = data if tool == "ruff" else data.get("results", [])
                stages.append(
                    {
                        "stage": tool,
                        "status": "completed",
                        "files": len(paths),
                        "diagnostics": len(diagnostics),
                    }
                )
                if tool == "bandit" and data.get("errors"):
                    stages[-1]["status"] = "partial"
                    stages[-1]["errors"] = [
                        {
                            "path": Path(e["filename"])
                            .relative_to(snapshot)
                            .as_posix(),
                            "reason": e.get("reason", "scan error"),
                        }
                        for e in data["errors"]
                    ]
                for item in diagnostics:
                    filename = Path(item["filename"])
                    try:
                        path = filename.relative_to(snapshot).as_posix()
                    except ValueError:
                        continue
                    if tool == "ruff":
                        rule = item.get("code") or "syntax"
                        line = item["location"]["row"]
                        category = (
                            "bug"
                            if rule in {"F821", "F823", "B006", "B008", "B023"}
                            else "quality"
                        )
                        severity = "medium" if category == "bug" else "low"
                        explanation = item["message"]
                    else:
                        rule = item["test_id"]
                        line = item["line_number"]
                        category = "security"
                        severity = item["issue_severity"].lower()
                        explanation = item["issue_text"]
                    finding = make_finding(
                        index,
                        path=path,
                        line=line,
                        title=f"{rule}: {explanation}",
                        source=tool,
                        rule=rule,
                        explanation=explanation,
                        category=category,
                        severity=severity,
                    )
                    if finding:
                        findings.append(finding)
            except (
                subprocess.TimeoutExpired,
                RuntimeError,
                json.JSONDecodeError,
                OSError,
                KeyError,
            ) as exc:
                stages.append(
                    {"stage": tool, "status": "failed", "reason": type(exc).__name__}
                )
    return findings, stages
