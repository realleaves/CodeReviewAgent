from collections import Counter
from html import escape
import json
from pathlib import Path


LABELS = {
    "supported": "有代码依据",
    "needs_context": "待确认",
    "unverified": "未复核",
    "rejected": "已驳回",
    "reproduced": "已复现",
    "pending_evidence": "待验证",
    "high": "高",
    "medium": "中",
    "low": "低",
}


def source_label(finding: dict) -> str:
    values = [f"{finding['source']} {finding['rule']}".strip()]
    values.extend(
        f"{d['source']} {d['rule']}".strip()
        for d in finding.get("related_diagnostics", [])
    )
    return " + ".join(values)


def markdown(report: dict) -> str:
    repo, run = report["repository"], report["run"]
    lines = [
        "# GitHub 仓库代码审查报告",
        "",
        f"- 仓库：{repo['url']}",
        f"- 分支：{repo['ref']}",
        f"- Commit：`{repo['commit']}`",
        f"- 状态：**{run['status']}**；模式：{run['mode']}；模型：{run['model']}",
        f"- 完成语义审查：{run['fully_reviewed_files']}/{run['indexed_python_files']} 个已索引 Python 文件",
        f"- 调用：{run['api_calls']}；耗时：{run['elapsed_seconds']} 秒",
        "",
        "## 范围与限制",
        "",
    ]
    lines += [f"- {value}" for value in report["limitations"]]
    active = [f for f in report["findings"] if f["status"] != "rejected"]
    evidence_mode = run["mode"] == "evidence"
    formal = [f for f in active if f["status"] == "reproduced"]
    if evidence_mode:
        lines += [
            "",
            f"## 已复现缺陷（{len(formal)}）",
            "",
            "正式缺陷附测试与运行证据；其余候选和静态建议单列，不表示已经证实。",
            "",
        ]
        active = formal + [f for f in active if f["status"] != "reproduced"]
    else:
        lines += ["", f"## 候选问题（{len(active)}）", ""]
    if not active:
        lines += [
            "本次已完成的分析未保留候选问题。请结合覆盖范围和失败记录解读；不代表仓库没有问题。",
            "",
        ]
    pending_heading = False
    for f in active:
        if evidence_mode and f["status"] != "reproduced" and not pending_heading:
            lines += ["## 待验证候选与静态建议", ""]
            pending_heading = True
        lines += [
            f"### [{LABELS[f['severity']]}] {f['title']}",
            "",
            f"- 位置：`{f['path']}:{f['line']}`",
            f"- 来源：{source_label(f)}",
            f"- 复核：{LABELS[f['status']]} — {f['verification']}",
            f"- 问题：{f['explanation']}",
            f"- 触发条件：{f['trigger']}",
            f"- 依据：{f['evidence']}",
            f"- 修复建议：{f['suggestion']}",
            f"- 验证方式：{f['validation']}",
            "",
            "```python",
            f["snippet"],
            "```",
            "",
        ]
        reproduction = f.get("reproduction")
        if reproduction:
            lines += [
                f"- 复现状态：{reproduction['status']}",
                f"- 证据说明：{reproduction['reason']}",
                "",
            ]
            if reproduction.get("artifact"):
                lines += [f"[运行证据]({reproduction['artifact']})", ""]
            if reproduction.get("plan", {}).get("test_code"):
                lines += [
                    "复现测试：",
                    "",
                    "```python",
                    reproduction["plan"]["test_code"],
                    "```",
                    "",
                ]
            for i, attempt in enumerate(reproduction.get("attempts", []), 1):
                version = attempt.get("plan_version")
                test_note = f"；测试版本 {version + 1}" if version is not None else ""
                lines += [
                    f"执行{i}：镜像 `{attempt['image_id']}`；Python `{(attempt.get('execution') or {}).get('python', 'unknown')}`；状态 `{attempt.get('verdict')}`{test_note}。",
                    "",
                    "```text",
                    attempt["log"],
                    "```",
                    "",
                ]
    lines += [
        "## 覆盖范围",
        "",
        "| 文件 | 静态检查 | 语义审查 | 完成分块 |",
        "|---|---|---|---|",
    ]
    for row in report["coverage"]:
        path = row["path"].replace("|", "\\|")
        lines.append(
            f"| {path} | {row['static_status']} | {row['semantic_status']} | {row['reviewed_chunks']}/{row['total_chunks']} |"
        )
    lines += ["", "## 失败记录", ""]
    lines += [
        "```json",
        json.dumps(report["failures"], ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    rejected = [f for f in report["findings"] if f["status"] == "rejected"]
    lines += [f"## 驳回的问题（{len(rejected)}）", ""]
    for f in rejected:
        lines.append(f"- `{f['path']}:{f['line']}` {f['title']}：{f['verification']}")
    reasons = Counter(e["reason"] for e in report["excluded"])
    lines += [
        "",
        "## 跳过文件",
        "",
        json.dumps(dict(reasons), ensure_ascii=False),
        "",
        "逐文件跳过原因、模型调用用量和复核轨迹见 report.json / run.json。",
        "",
    ]
    return "\n".join(lines)


def html_report(report: dict) -> str:
    e = lambda value: escape(str(value), quote=True)
    repo, run = report["repository"], report["run"]
    evidence_mode = run["mode"] == "evidence"
    cards = []
    for f in report["findings"]:
        url = ""
        if repo["url"].startswith("https://github.com/"):
            from urllib.parse import quote

            url = f"{repo['url']}/blob/{repo['commit']}/{quote(f['path'], safe='/')}#L{f['line']}"
        location = f"{f['path']}:{f['line']}"
        link = (
            f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">{e(location)}</a>'
            if url
            else e(location)
        )
        details = "".join(
            f'<div class="detail"><dt>{label}</dt><dd>{e(f[key])}</dd></div>'
            for label, key in [
                ("问题说明", "explanation"),
                ("触发条件", "trigger"),
                ("代码依据", "evidence"),
                ("修复建议", "suggestion"),
                ("复核理由", "verification"),
                ("验证方式", "validation"),
            ]
        )
        evidence_html = ""
        reproduction = f.get("reproduction")
        if reproduction:
            evidence_html = f"<p>复现：{e(reproduction['status'])} · {e(reproduction['reason'])}</p>"
            artifact = reproduction.get("artifact", "")
            from pathlib import PurePosixPath

            if (
                artifact.startswith("evidence/")
                and ".." not in PurePosixPath(artifact).parts
            ):
                evidence_html += f'<p><a href="{e(artifact)}">完整运行证据</a></p>'
            if reproduction.get("plan", {}).get("test_code"):
                evidence_html += f"<details><summary>复现测试与预期行为</summary><p>{e(reproduction['plan']['expected_behavior'])}</p><pre><code>{e(reproduction['plan']['test_code'])}</code></pre></details>"
            for i, attempt in enumerate(reproduction.get("attempts", []), 1):
                version = attempt.get("plan_version")
                test_note = f" · 测试版本 {version + 1}" if version is not None else ""
                evidence_html += f"<details><summary>执行{i} · {e(attempt.get('verdict'))} · Python {e((attempt.get('execution') or {}).get('python', 'unknown'))}{test_note}</summary><p>镜像 {e(attempt['image_id'])}</p><pre>{e(attempt['log'])}</pre></details>"
        cards.append(f'''<article class="finding" data-severity="{e(f["severity"])}" data-status="{e(f["status"])}">
          <div class="tags"><span class="badge {e(f["severity"])}">{LABELS[f["severity"]]}风险</span>
          <span class="badge">{LABELS[f["status"]]}</span><span class="origin">{e(source_label(f))}</span></div>
          <h3>{e(f["title"])}</h3><div class="location">{link}</div><dl>{details}</dl>
          <pre><code>{e(f["snippet"])}</code></pre>{evidence_html}</article>''')
    coverage = "".join(
        f"<tr><td>{e(r['path'])}</td><td>{e(r['static_status'])}</td>"
        f"<td>{e(r['semantic_status'])}</td><td>{r['reviewed_chunks']}/{r['total_chunks']}</td></tr>"
        for r in report["coverage"]
    )
    excluded = "".join(
        f"<tr><td>{e(r['path'])}</td><td>{e(r['reason'])}</td></tr>"
        for r in report["excluded"]
    )
    limitations = "".join(f"<li>{e(s)}</li>" for s in report["limitations"])
    failure_box = (
        "<p>没有执行失败记录。</p>"
        if not report["failures"]
        else f"<pre>{e(json.dumps(report['failures'], ensure_ascii=False, indent=2))}</pre>"
    )
    primary_label = "已复现缺陷" if evidence_mode else "保留的候选问题"
    primary_filter = (
        '<option value="reproduced">已复现缺陷</option><option value="pending">待验证候选与静态建议</option>'
        if evidence_mode
        else '<option value="active">保留的问题</option>'
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>CodeReview · {e(repo["name"])}</title>
<style>
:root{{--bg:#f4f6fa;--ink:#182635;--muted:#526376;--line:#dbe3ed;--accent:#126b65}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 system-ui,sans-serif}}
header{{background:#112e38;color:#fff;padding:38px max(24px,calc((100vw - 1100px)/2))}}
.eyebrow{{letter-spacing:2px;font-size:12px;color:#94d9cc}}h1{{font-size:32px;margin:10px 0}}header p{{margin:6px 0;color:#c7d8df;overflow-wrap:anywhere}}
main{{max-width:1150px;margin:auto;padding:28px 24px 60px}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.stat,.panel,.finding{{background:white;border:1px solid var(--line);border-radius:12px;padding:22px}}
.stat strong{{display:block;font-size:30px;color:var(--accent)}}.stat span{{color:var(--muted)}}
.panel{{margin:22px 0}}h2{{font-size:20px;margin:0 0 14px}}.filters{{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}}
select,input{{font:inherit;padding:9px 12px;border:1px solid var(--line);border-radius:7px;background:white}}input{{min-width:220px;flex:1}}
.finding{{margin:14px 0}}.finding[hidden]{{display:none}}h3{{font-size:19px;margin:12px 0 5px}}.tags{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.badge{{border-radius:5px;padding:3px 9px;background:#edf2f7;font-size:12px}}.badge.high{{color:#a12f37;background:#ffebed}}
.badge.medium{{color:#96590c;background:#fff1dc}}.badge.low{{color:#176467;background:#e7f5f3}}.origin,.location{{color:var(--muted);font-size:13px}}
a{{color:var(--accent)}}dl{{margin:18px 0}}.detail{{display:grid;grid-template-columns:90px 1fr;gap:12px;margin:9px 0}}dt{{font-weight:600}}dd{{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}}
pre{{background:#122b37;color:#e0edf2;padding:17px;border-radius:8px;overflow:auto;font:13px/1.7 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}}
.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid var(--line)}}td{{overflow-wrap:anywhere}}
.note{{color:var(--muted)}}summary{{cursor:pointer;font-weight:600}}footer{{color:var(--muted);margin-top:25px}}#empty{{padding:30px;text-align:center;color:var(--muted)}}
@media(max-width:700px){{.stats{{grid-template-columns:repeat(2,1fr)}}header{{padding:25px 20px}}main{{padding:20px 14px}}.detail{{grid-template-columns:1fr;gap:2px}}h1{{font-size:25px}}}}
</style></head><body><header><div class="eyebrow">CODE REVIEW AGENT / REPOSITORY REPORT</div>
<h1>{e(repo["name"])}</h1><p>{e(repo["url"])} · {e(repo["ref"])}</p>
<p>Commit {e(repo["commit"])} · 运行状态 {e(run["status"])}</p></header><main>
<div class="stats"><div class="stat"><strong>{run["active_findings"]}</strong><span>{primary_label}</span></div>
<div class="stat"><strong>{run["semantic_coverage_percent"]}%</strong><span>已索引 Python 文件语义覆盖</span></div>
<div class="stat"><strong>{run["api_calls"]}</strong><span>模型调用</span></div>
<div class="stat"><strong>{run["elapsed_seconds"]}s</strong><span>运行耗时</span></div></div>
<section class="panel"><h2>审查范围与证据</h2><p>模式 {e(run["mode"])} · 模型 {e(run["model"])} · 完整语义审查 {run["fully_reviewed_files"]}/{run["indexed_python_files"]} 个文件</p>
<ul class="note">{limitations}</ul></section>
<h2>审查发现</h2><div class="filters"><input id="search" aria-label="搜索问题或文件" placeholder="搜索问题、文件路径或依据…">
<select id="severity" aria-label="风险程度"><option value="">全部风险</option><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select>
<select id="status" aria-label="复核状态">{primary_filter}<option value="all">全部含驳回</option><option value="supported">有代码依据</option><option value="needs_context">待确认</option><option value="unverified">未复核</option><option value="rejected">已驳回</option></select></div>
<div id="findings">{"".join(cards)}</div><p id="empty" hidden>当前筛选没有候选问题；请结合覆盖范围和失败记录解读。</p>
<section class="panel"><h2>文件覆盖</h2><div class="table-wrap"><table><thead><tr><th>文件</th><th>静态检查</th><th>语义审查</th><th>完成分块</th></tr></thead><tbody>{coverage}</tbody></table></div></section>
<section class="panel"><h2>失败记录</h2>{failure_box}</section>
<section class="panel"><details><summary>跳过文件（{len(report["excluded"])}）</summary><div class="table-wrap"><table><thead><tr><th>文件</th><th>原因</th></tr></thead><tbody>{excluded}</tbody></table></div></details></section>
<footer>Token 用量：输入 {run["usage"]["prompt_tokens"]} / 输出 {run["usage"]["completion_tokens"]}。完整结构化结果及复核轨迹见 report.json。</footer>
</main><script>
const search=document.getElementById('search'),severity=document.getElementById('severity'),status=document.getElementById('status');
function filter(){{let count=0;for(const card of document.querySelectorAll('.finding')){{const s=status.value;
const show=(!severity.value||card.dataset.severity===severity.value)&&(s==='all'||(s==='pending'?!['reproduced','rejected'].includes(card.dataset.status):(s==='active'?card.dataset.status!=='rejected':card.dataset.status===s)))&&card.textContent.toLowerCase().includes(search.value.toLowerCase());
card.hidden=!show;if(show)count++;}}document.getElementById('empty').hidden=count!==0;}}
for(const control of [search,severity,status])control.addEventListener('input',filter);filter();
</script></body></html>"""


def write_reports(report: dict, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    for name, data in (
        ("report.json", report),
        (
            "run.json",
            {
                k: v
                for k, v in report.items()
                if k not in {"findings", "trace", "evidence_artifacts"}
            },
        ),
    ):
        (output / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    (output / "report.md").write_text(markdown(report), encoding="utf-8")
    (output / "report.html").write_text(html_report(report), encoding="utf-8")
    for path, content in report.get("evidence_artifacts", {}).items():
        from pathlib import PurePosixPath

        relative = PurePosixPath(path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.parts[0] != "evidence"
            or relative.suffix not in {".json", ".py", ".log"}
        ):
            raise ValueError("复现附件路径不合法。")
        destination = output / str(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
