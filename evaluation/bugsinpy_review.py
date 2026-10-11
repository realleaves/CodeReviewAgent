"""Known-location review using the production agents, with no evaluator labels."""

from collections import Counter
from datetime import datetime, timezone
import time

from src.agents import BudgetExceeded, MeteredLLM, ReviewAgents, load_config
from src.code_index import Chunk, CodeIndex, chunks, numbered
from src.deduplication import deduplicate
from src.repository import inventory, snapshot_digest
from src.schemas import ReviewOptions
from src.static_analysis import analyze
from evaluation.bugsinpy_data import is_production, windows


def reviewer_files(root):
    root = root.resolve()
    files, excluded = inventory(root, "", 1_000_000)
    for path in list(files):
        if not is_production(path):
            del files[path]
            excluded.append({"path": path, "reason": "benchmark_tests_hidden"})
    return files, excluded


def run_scoped_review(
    root, regions, mode, max_calls, timeout=45, env_file=None, llm=None, progress=print
):
    start = time.monotonic()
    started = datetime.now(timezone.utc).isoformat()
    files, excluded = reviewer_files(root)
    index = CodeIndex(files)
    scopes = {path: windows(files[path], hunks) for path, hunks in regions.items()}
    selected = sorted(scopes)
    parts = []
    coverage = []
    for path in selected:
        source_lines = files[path].splitlines()
        count = 0
        for low, high in scopes[path]:
            text = "\n".join(source_lines[low - 1 : high])
            for piece in chunks(path, text, 180, 20_000):
                first, last = low + piece.start - 1, low + piece.end - 1
                parts.append(
                    Chunk(path, first, last, numbered(files[path], first, last))
                )
                count += 1
        coverage.append(
            {
                "path": path,
                "lines": len(source_lines),
                "windows": scopes[path],
                "total_chunks": count,
                "reviewed_chunks": 0,
                "semantic_status": "not_started",
                "static_status": "not_requested",
            }
        )
    findings, stages, failures, trace = [], [], [], []
    if mode != "direct":
        diagnostics, stages = analyze(index, selected, timeout)
        findings = [
            f for f in diagnostics if any(a <= f.line <= b for a, b in scopes[f.path])
        ]
        failures.extend(s for s in stages if s["status"] != "completed")
        for row in coverage:
            row["static_status"] = "completed" if not failures else "partial"
    own_llm = llm is None
    if own_llm:
        load_config(env_file)
        llm = MeteredLLM(max_calls, timeout)
    agent = ReviewAgents(index, llm)
    consecutive_errors = 0
    try:
        for part in parts:
            if len(llm.calls) >= max_calls:
                failures.append(
                    {
                        "stage": "budget",
                        "reason": "窗口审查未完成，模型调用预算已耗尽。",
                    }
                )
                break
            progress(
                f"    {part.path}:{part.start}-{part.end} · {len(llm.calls)}/{max_calls} 次调用"
            )
            row = next(r for r in coverage if r["path"] == part.path)
            try:
                new = agent.review(part, findings, direct=mode == "direct")
                consecutive_errors = 0
                findings.extend(new)
                row["reviewed_chunks"] += 1
                if mode == "full":
                    pending = [
                        f
                        for f in findings
                        if f.status == "unverified"
                        and f.path == part.path
                        and part.start <= f.line <= part.end
                    ]
                    for offset in range(0, len(pending), 8):
                        if len(llm.calls) >= max_calls:
                            raise BudgetExceeded("复核预算耗尽")
                        agent.verify(pending[offset : offset + 8])
            except Exception as exc:
                failures.append(
                    {
                        "stage": "review_or_verify",
                        "path": part.path,
                        "reason": str(exc)[:300],
                    }
                )
                if isinstance(exc, BudgetExceeded):
                    break
                consecutive_errors += 1
                if consecutive_errors >= 2:
                    break
        trace = agent.trace
    finally:
        if own_llm:
            llm.close()
    all_findings = deduplicate(findings)
    active = [f for f in all_findings if f.status != "rejected"]
    for row in coverage:
        row["semantic_status"] = (
            "window_completed"
            if row["reviewed_chunks"] == row["total_chunks"]
            else "partial"
        )
    complete = not failures and all(
        r["semantic_status"] == "window_completed" for r in coverage
    )
    if mode == "full" and any(f.status == "unverified" for f in active):
        complete = False
    return {
        "schema_version": "1.0",
        "repository": {
            "url": "local-benchmark",
            "name": "snapshot",
            "ref": "blinded-snapshot",
            "commit": "snapshot",
            "indexed_snapshot_sha256": snapshot_digest(files),
        },
        "run": {
            "started_at": started,
            "status": "completed" if complete else "partial",
            "mode": mode,
            "model": llm.model,
            "scope_kind": "known_location_windows",
            "options": ReviewOptions(
                mode=mode,
                max_calls=max_calls,
                timeout=timeout,
                max_file_bytes=1_000_000,
            ).model_dump(),
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "api_calls": len(llm.calls),
            "usage": {
                k: sum(c.get("usage", {}).get(k, 0) for c in llm.calls)
                for k in ["prompt_tokens", "completion_tokens"]
            },
            "indexed_python_files": len(files),
            "selected_files": len(selected),
            "fully_reviewed_files": 0,
            "semantic_coverage_percent": 0,
            "reviewed_window_chunks": sum(r["reviewed_chunks"] for r in coverage),
            "total_window_chunks": len(parts),
            "active_findings": len(active),
            "rejected_findings": len(all_findings) - len(active),
            "severity_counts": dict(Counter(f.severity for f in active)),
            "status_counts": dict(Counter(f.status for f in active)),
        },
        "coverage": coverage,
        "excluded": excluded,
        "stages": stages,
        "failures": failures,
        "calls": llm.calls,
        "tool_reads": index.reads,
        "trace": trace,
        "findings": [f.model_dump() for f in all_findings],
        "limitations": [
            "BugsInPy定范围评测：使用参考补丁选择代码窗口，Agent未看到补丁、测试、标签或另一版本。",
            "completed仅表示所选窗口及复核完成；完整文件审查数为0，不表示全仓库或全文件审查。",
            "修复版本可能含其他缺陷；额外发现不自动计为误报。",
            "本报告是静态分析及模型推断；外部容器复现证据由评测程序另行保存。",
        ],
    }
