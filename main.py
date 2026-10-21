#!/usr/bin/env python3
"""Repository review; optional target execution is restricted to Docker."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

from src.schemas import ReviewOptions


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub Python 仓库智能审查助手")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="验证依赖与模型 API")
    doctor.add_argument("--env-file")
    doctor.add_argument("--model")
    review = sub.add_parser("review", help="审查公开 GitHub 仓库或本地目录")
    review.add_argument("repository")
    review.add_argument("--local", action="store_true")
    review.add_argument("--ref", help="分支或 tag")
    review.add_argument("--scope", default="", help="限定仓库相对目录或文件")
    review.add_argument(
        "--mode",
        choices=["evidence", "full", "assisted", "direct", "static"],
        default="evidence",
    )
    review.add_argument("--max-files", type=int, default=12)
    review.add_argument("--max-calls", type=int, default=24)
    review.add_argument("--max-file-bytes", type=int, default=200_000)
    review.add_argument("--chunk-lines", type=int, default=180)
    review.add_argument("--chunk-chars", type=int, default=20_000)
    review.add_argument("--timeout", type=int, default=45)
    review.add_argument("--model")
    review.add_argument("--env-file")
    review.add_argument("--output", help="新建的报告目录（不能已存在）")
    review.add_argument(
        "--repro-image", default="python:3.13-slim", help="预先准备的隔离测试镜像"
    )
    review.add_argument("--repro-timeout", type=int, default=15)
    review.add_argument("--max-reproductions", type=int, default=4)
    review.add_argument(
        "--context-strategy",
        choices=["legacy", "callgraph"],
        default="legacy",
        help="evidence模式的上下文选择；callgraph为调用链检索实验，尚无检出率提升结论",
    )
    review.add_argument(
        "--review-strategy",
        choices=["baseline", "hypothesis", "hypothesis_tools", "tool_first"],
        default="baseline",
        help="evidence发现策略；hypothesis/hypothesis_tools/tool_first为实验，尚无检出率提升结论",
    )
    review.add_argument(
        "--enforce-admission",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="结构化预期准入；默认开启，--no-enforce-admission仅用于对照实验",
    )
    review.add_argument(
        "--max-repro-repairs",
        type=int,
        choices=[0, 1],
        default=0,
        help="测试未调用目标时的反馈修正次数，实验功能，仍计入模型预算",
    )
    replay = sub.add_parser("reproduce", help="从保存证据复跑测试，不调用模型")
    replay.add_argument("evidence")
    replay.add_argument("repository", help="与证据源码哈希相同的本地目录")
    replay.add_argument("--output", required=True, help="新的执行证据目录")
    args = parser.parse_args()
    try:
        if args.command == "reproduce":
            from src.reproduction import replay_evidence

            result = replay_evidence(
                Path(args.evidence), Path(args.repository), Path(args.output)
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "failure_observed" else 2
        if args.command == "doctor":
            from src.agents import MeteredLLM, load_config

            load_config(args.env_file)
            llm = MeteredLLM(1, 15, args.model)
            try:
                llm.current_stage = "doctor"
                answer = llm.invoke(
                    [{"role": "user", "content": 'Return only JSON: {"ok":true}.'}],
                    response_format={"type": "json_object"},
                )
                result = json.loads(answer)
                if result.get("ok") is not True:
                    raise RuntimeError("模型探测返回格式不符合预期。")
                print(
                    json.dumps(
                        {"status": "ok", "model": llm.model, "calls": llm.calls},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            finally:
                llm.close()
            return 0
        options = ReviewOptions(
            **{key: getattr(args, key) for key in ReviewOptions.model_fields}
        )
        output = (
            Path(args.output).expanduser().resolve()
            if args.output
            else (
                Path(__file__).resolve().parent
                / "outputs"
                / (
                    datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    + "-"
                    + uuid.uuid4().hex[:6]
                )
            )
        )
        if output.exists():
            raise ValueError("报告目录已存在，请使用新的 --output 路径。")
        from src.pipeline import run_review
        from src.repository import acquire_repository
        from src.report import write_reports

        print("[1/5] 获取仓库并固定审查版本", flush=True)
        with acquire_repository(args.repository, args.ref, args.local) as repo:
            report = run_review(
                repo,
                options,
                args.env_file,
                progress=lambda msg: print(msg, flush=True),
            )
        print("[5/5] 保存报告", flush=True)
        write_reports(report, output)
        print(
            json.dumps(
                {
                    "status": report["run"]["status"],
                    "report": str(output / "report.html"),
                    "findings": report["run"]["active_findings"],
                    "calls": report["run"]["api_calls"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if report["run"]["status"] in {"completed", "static_only"} else 2
    except KeyboardInterrupt:
        print("运行已中止。", file=sys.stderr)
        return 130
    except Exception as exc:
        # Known controlled errors are useful; SDK/subprocess errors are sanitized elsewhere.
        print(f"错误：{str(exc)[:500]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
