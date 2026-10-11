from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import time

from .agents import BudgetExceeded, MeteredLLM, ReviewAgents, load_config
from .code_index import CodeIndex, chunks
from .deduplication import deduplicate
from .repository import Repository, inventory, snapshot_digest
from .schemas import ReviewOptions, public_options
from .static_analysis import analyze


def run_review(
    repo: Repository,
    options: ReviewOptions,
    env_file: str | None = None,
    llm=None,
    progress=print,
) -> dict:
    start = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    progress("[2/5] 筛选文件并建立代码索引")
    files, excluded = inventory(repo.root, options.scope, options.max_file_bytes)
    index = CodeIndex(files)
    # Put application code before tests/examples, then use stable path order.
    ordered = sorted(
        files,
        key=lambda p: (
            any(
                part in {"tests", "test", "examples", "docs"} for part in Path(p).parts
            ),
            p,
        ),
    )
    selected = ordered[: options.max_files]
    excluded += [
        {"path": p, "reason": "file_count_limit"} for p in ordered[options.max_files :]
    ]
    coverage = [
        {
            "path": p,
            "lines": len(files[p].splitlines()),
            "reviewed_chunks": 0,
            "total_chunks": 0,
            "semantic_status": "not_started",
            "static_status": "not_run",
        }
        for p in selected
    ]
    findings, stages, failures, trace = [], [], [], []
    if options.mode != "direct" and selected:
        progress("[3/5] 运行 AST、Ruff 和 Bandit 静态检查")
        findings, static_stages = analyze(index, selected, options.timeout)
        stages.extend(static_stages)
        static_complete = all(s["status"] == "completed" for s in static_stages)
        for row in coverage:
            row["static_status"] = "completed" if static_complete else "partial"
        for stage in static_stages:
            if stage["status"] != "completed":
                failures.append(stage)
    own_llm = False
    if options.mode != "static" and selected:
        try:
            if llm is None:
                load_config(env_file)
                llm = MeteredLLM(options.max_calls, options.timeout, options.model)
                own_llm = True
            agents = ReviewAgents(index, llm)
        except Exception as exc:
            failures.append({"stage": "configuration", "reason": str(exc)[:300]})
            llm = None
            agents = None
        progress("[4/5] 执行语义审查与复核")
        consecutive_errors = 0
        stop = False
        if agents:
            for row in coverage:
                path = row["path"]
                if stop:
                    row["semantic_status"] = "budget_or_circuit_limit"
                    continue
                if not files[path].strip():
                    row["semantic_status"] = "empty"
                    continue
                if path in index.syntax_errors:
                    row["semantic_status"] = "syntax_error"
                    continue
                try:
                    parts = chunks(
                        path, files[path], options.chunk_lines, options.chunk_chars
                    )
                except ValueError as exc:
                    row["semantic_status"] = "input_limit"
                    failures.append(
                        {"stage": "chunking", "path": path, "reason": str(exc)}
                    )
                    continue
                row["total_chunks"] = len(parts)
                row["semantic_status"] = "partial"
                for part in parts:
                    if len(llm.calls) >= options.max_calls:
                        stop = True
                        break
                    progress(
                        f"  审查 {path}:{part.start}-{part.end} · 调用 {len(llm.calls)}/{options.max_calls}"
                    )
                    try:
                        candidates = agents.review(
                            part, findings, direct=options.mode == "direct"
                        )
                        consecutive_errors = 0
                        row["reviewed_chunks"] += 1
                    except BudgetExceeded as exc:
                        failures.append(
                            {"stage": "review", "path": path, "reason": str(exc)}
                        )
                        stop = True
                        break
                    except Exception as exc:
                        failures.append(
                            {
                                "stage": "review",
                                "path": path,
                                "start": part.start,
                                "end": part.end,
                                "reason": str(exc)[:300],
                            }
                        )
                        consecutive_errors += 1
                        if consecutive_errors >= 2:
                            stop = True
                            break
                        continue
                    findings.extend(candidates)
                    if options.mode == "full":
                        # Recheck static diagnostics in the same window as well as semantic candidates.
                        to_verify = [
                            f
                            for f in findings
                            if f.status == "unverified"
                            and f.path == path
                            and part.start <= f.line <= part.end
                        ]
                        for offset in range(0, len(to_verify), 8):
                            batch = to_verify[offset : offset + 8]
                            if len(llm.calls) >= options.max_calls:
                                for item in batch:
                                    item.verification = "调用预算耗尽，尚未复核。"
                                break
                            progress(f"  复核 {len(batch)} 个候选问题")
                            try:
                                agents.verify(batch)
                            except Exception as exc:
                                failures.append(
                                    {
                                        "stage": "verify",
                                        "path": path,
                                        "reason": str(exc)[:300],
                                    }
                                )
                                for item in batch:
                                    item.verification = "复核失败，保留为未复核候选。"
                if row["reviewed_chunks"] == row["total_chunks"]:
                    row["semantic_status"] = "completed"
                elif stop:
                    row["semantic_status"] = "budget_or_circuit_limit"
            trace = agents.trace
        else:
            for row in coverage:
                row["semantic_status"] = "configuration_failed"
    elif options.mode == "static":
        for row in coverage:
            row["semantic_status"] = "not_requested"
    calls = llm.calls if llm is not None else []
    model = llm.model if llm is not None else None
    if own_llm:
        llm.close()
    all_findings = sorted(
        deduplicate(findings),
        key=lambda f: ({"high": 0, "medium": 1, "low": 2}[f.severity], f.path, f.line),
    )
    semantic_done = sum(
        r["semantic_status"] in {"completed", "empty"} for r in coverage
    )
    active = [f for f in all_findings if f.status != "rejected"]
    verification_complete = all(f.status != "unverified" for f in active)
    if not selected:
        state = "no_supported_files"
    elif failures or len(selected) < len(files):
        state = "partial"
    elif options.mode == "static":
        state = "static_only"
    elif semantic_done < len(selected) or (
        options.mode == "full" and not verification_complete
    ):
        state = "partial"
    else:
        state = "completed"
    return {
        "schema_version": "1.0",
        "repository": {
            "url": repo.url,
            "name": repo.name,
            "ref": repo.ref,
            "commit": repo.commit,
            "indexed_snapshot_sha256": snapshot_digest(files),
        },
        "run": {
            "started_at": started_at,
            "status": state,
            "mode": options.mode,
            "model": model,
            "options": public_options(options),
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "api_calls": len(calls),
            "usage": {
                "prompt_tokens": sum(
                    c.get("usage", {}).get("prompt_tokens", 0) for c in calls
                ),
                "completion_tokens": sum(
                    c.get("usage", {}).get("completion_tokens", 0) for c in calls
                ),
            },
            "indexed_python_files": len(files),
            "selected_files": len(selected),
            "fully_reviewed_files": semantic_done,
            "semantic_coverage_percent": round(100 * semantic_done / len(files), 1)
            if files
            else 0,
            "active_findings": len(active),
            "rejected_findings": len(all_findings) - len(active),
            "severity_counts": dict(Counter(f.severity for f in active)),
            "status_counts": dict(Counter(f.status for f in active)),
        },
        "coverage": coverage,
        "excluded": excluded,
        "stages": stages,
        "failures": failures,
        "calls": calls,
        "tool_reads": index.reads,
        "trace": trace,
        "findings": [f.model_dump() for f in all_findings],
        "limitations": [
            "仅支持 Python；外部依赖和业务约定可能缺失。",
            "审查基于静态诊断与模型代码推断，未执行待审代码或复现测试。",
            "supported 表示模型复核认为有代码依据，不代表运行证明或无误报保证。",
            "覆盖率以所选 scope 内已索引 Python 文件为分母；索引限制及未支持文件另列。",
            "按预算分块；import 关联和只读查询提供有限跨文件上下文。",
        ],
    }
