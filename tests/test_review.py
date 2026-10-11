import json
import subprocess
from types import SimpleNamespace

import pytest

from src.agents import (
    BudgetExceeded,
    BoundedAgent,
    MeteredLLM,
    ModelResponseError,
    ReviewAgents,
    parse_json,
)
from src.code_index import CodeIndex, chunks
from src.pipeline import run_review
from src.report import html_report, write_reports
from src.repository import Repository, acquire_repository, github_url, inventory
from src.schemas import ReviewOptions
from src.static_analysis import analyze


class FakeLLM:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []
        self.model = "test-double"
        self.current_stage = ""

    def invoke(self, messages, **kwargs):
        self.calls.append({"status": "completed", "stage": self.current_stage})
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            return answer(messages)
        return answer


def candidate(path="a.py", line=2):
    return {
        "path": path,
        "line": line,
        "end_line": line,
        "severity": "medium",
        "category": "bug",
        "title": "空列表除零",
        "explanation": "空列表长度为零。",
        "trigger": "values=[]",
        "evidence": "sum(values) / len(values)",
        "suggestion": "处理空输入。",
    }


def verify_answer(messages):
    payload = json.loads(messages[-1]["content"])
    return json.dumps(
        {
            "decisions": [
                {
                    "id": f["id"],
                    "status": "supported",
                    "reason": "空列表作为除数为零；未运行测试。",
                }
                for f in payload["candidates"]
            ]
        }
    )


def fixture_repo(
    tmp_path, source="def average(values):\n    return sum(values) / len(values)\n"
):
    (tmp_path / "a.py").write_text(source)
    return Repository(tmp_path, "local", "test-snapshot", "fixture", "fixture")


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/u/r",
        "https://github.com/u/r/tree/main",
        "https://user:password@github.com/u/r",
        "http://github.com/u/r",
        "https://github.com/u/r?token=x",
        "https://github.com/u/..",
        "https://github.com:443/u/r",
    ],
)
def test_repository_url_rejects_unsafe_or_non_root_urls(url):
    with pytest.raises(ValueError):
        github_url(url)


def test_repository_url_normalizes_suffix():
    assert (
        github_url("https://github.com/psf/requests.git/")[0]
        == "https://github.com/psf/requests"
    )


def test_inventory_scope_symlinks_secrets_and_file_limits(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("x=1\n")
    (tmp_path / "outside.py").write_text("x=2\n")
    (tmp_path / ".env").write_text("PRIVATE=secret")
    (tmp_path / "src/link.py").symlink_to(tmp_path / ".env")
    (tmp_path / "src/big.py").write_text("x=" + "1" * 300)
    files, excluded = inventory(tmp_path, "src", 100)
    assert list(files) == ["src/a.py"]
    reasons = {r["path"]: r["reason"] for r in excluded}
    assert reasons["src/link.py"] == "symlink"
    assert reasons[".env"] == "sensitive_file"
    assert reasons["outside.py"] == "outside_scope"
    assert reasons["src/big.py"] == "file_size_limit"
    with pytest.raises(ValueError):
        inventory(tmp_path, "../", 100)


def test_chunks_cover_all_original_lines_and_keep_numbers():
    source = "\n".join(f"v{i} = {i}" for i in range(35))
    parts = chunks("a.py", source, 10, 1000)
    assert [(p.start, p.end) for p in parts] == [(1, 10), (11, 20), (21, 30), (31, 35)]
    assert parts[1].text.startswith("11: v10 = 10")
    with pytest.raises(ValueError):
        chunks("a.py", "x" * 2000, 10, 1000)


def test_read_tools_cannot_escape_or_read_unsupported_files():
    index = CodeIndex({"a.py": "def f():\n    return 1\n"})
    assert "error" in json.loads(index.read("../.env"))
    assert "error" in json.loads(index.read("a.py", 0, 10))
    assert json.loads(index.search("f"))["matches"][0]["line"] == 1


def test_real_scanners_ignore_repo_config_and_do_not_execute_code(tmp_path):
    sentinel = tmp_path / "executed"
    source = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('unsafe')\nprint(undefined_name)\n"
    index = CodeIndex({"a.py": source})
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nignore=["F821"]\n')
    findings, stages = analyze(index, ["a.py"])
    assert any(f.rule == "F821" and f.line == 3 for f in findings)
    assert all(s["status"] == "completed" for s in stages)
    assert not sentinel.exists()


def test_agent_calls_read_tool_and_validates_real_locations():
    index = CodeIndex(
        {"a.py": "def average(values):\n    return sum(values) / len(values)\n"}
    )
    fake = FakeLLM(
        [
            "[TOOL_CALL:read_code:path=a.py,start=1,end=2]",
            json.dumps({"findings": [candidate(), candidate(path="invented.py")]}),
        ]
    )
    agents = ReviewAgents(index, fake)
    findings = agents.review(chunks("a.py", index.files["a.py"], 10, 1000)[0], [])
    assert len(findings) == 1
    assert index.reads[0]["path"] == "a.py"
    assert any(t.get("reason") == "invalid_location" for t in agents.trace)


def test_verifier_cannot_replace_or_omit_candidate_ids():
    index = CodeIndex(
        {"a.py": "def average(values):\n    return sum(values) / len(values)\n"}
    )
    fake = FakeLLM(
        [
            json.dumps({"findings": [candidate()]}),
            '{"decisions":[{"id":"made-up","status":"supported","reason":"wrong"}]}',
        ]
    )
    agents = ReviewAgents(index, fake)
    findings = agents.review(chunks("a.py", index.files["a.py"], 10, 1000)[0], [])
    with pytest.raises(ValueError):
        agents.verify(findings)
    assert findings[0].status == "unverified"


def test_full_pipeline_rechecks_and_generates_all_report_formats(tmp_path):
    repo = fixture_repo(tmp_path)
    fake = FakeLLM([json.dumps({"findings": [candidate()]}), verify_answer])
    result = run_review(
        repo, ReviewOptions(max_calls=4), llm=fake, progress=lambda _: None
    )
    assert result["run"]["status"] == "completed"
    assert result["findings"][0]["status"] == "supported"
    assert result["run"]["fully_reviewed_files"] == 1
    output = tmp_path / "report"
    write_reports(result, output)
    assert {p.name for p in output.iterdir()} == {
        "report.html",
        "report.md",
        "report.json",
        "run.json",
    }
    assert json.loads((output / "report.json").read_text())["run"]["api_calls"] == 2


def test_budget_exhaustion_is_partial_not_clean(tmp_path):
    repo = fixture_repo(tmp_path)
    (tmp_path / "b.py").write_text("x=1\n")
    fake = FakeLLM([json.dumps({"findings": [candidate()]})])
    result = run_review(
        repo, ReviewOptions(max_calls=1), llm=fake, progress=lambda _: None
    )
    assert result["run"]["status"] == "partial"
    assert result["findings"][0]["status"] == "unverified"
    assert result["run"]["fully_reviewed_files"] == 1
    assert result["coverage"][1]["semantic_status"] == "budget_or_circuit_limit"


def test_model_failures_circuit_break_and_keep_static_diagnostics(tmp_path):
    repo = fixture_repo(tmp_path, "print(undefined_name)\n" * 30)
    fake = FakeLLM([RuntimeError("test timeout"), RuntimeError("test timeout")])
    result = run_review(
        repo, ReviewOptions(chunk_lines=10), llm=fake, progress=lambda _: None
    )
    assert result["run"]["status"] == "partial"
    assert result["run"]["fully_reviewed_files"] == 0
    assert len(fake.calls) == 2
    assert any(f["rule"] == "F821" for f in result["findings"])


def test_syntax_and_empty_files_have_explicit_status(tmp_path):
    repo = fixture_repo(tmp_path, "def broken(\n")
    (tmp_path / "b.py").write_text("")
    result = run_review(repo, ReviewOptions(), llm=FakeLLM([]), progress=lambda _: None)
    states = {r["path"]: r["semantic_status"] for r in result["coverage"]}
    assert states == {"a.py": "syntax_error", "b.py": "empty"}
    assert result["run"]["status"] == "partial"


def test_no_supported_files_is_explicit(tmp_path):
    (tmp_path / "readme.md").write_text("hello")
    repo = Repository(tmp_path, "local", "fixture", "fixture", "empty")
    result = run_review(repo, ReviewOptions(mode="static"), progress=lambda _: None)
    assert result["run"]["status"] == "no_supported_files"


def test_report_escapes_untrusted_titles_and_preserves_separate_issues(tmp_path):
    repo = fixture_repo(tmp_path)
    c1 = candidate()
    c1["title"] = '<script>alert("x")</script>'
    c2 = dict(c1, title="另一个问题")
    result = run_review(
        repo,
        ReviewOptions(mode="direct"),
        llm=FakeLLM([json.dumps({"findings": [c1, c2]})]),
        progress=lambda _: None,
    )
    assert len(result["findings"]) == 2
    html = html_report(result)
    assert '<script>alert("x")</script>' not in html
    assert "&lt;script&gt;" in html


def test_git_timeout_has_controlled_message(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 120)

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="超时"):
        with acquire_repository("https://github.com/psf/requests"):
            pass


def test_json_results_reject_extra_prose():
    assert parse_json('```json\n{"findings":[]}\n```') == {"findings": []}
    with pytest.raises(ValueError):
        parse_json('Here is a report: {"findings":[]}')


def test_metered_client_enforces_budget_and_preserves_truncation_reason():
    llm = MeteredLLM.__new__(MeteredLLM)
    llm.model = "fake"
    llm.temperature = 0.1
    llm.max_tokens = 6000
    llm.max_calls = 1
    llm.current_stage = "review"
    llm.calls = []
    llm.is_deepseek = True
    llm.thinking_mode = "disabled"
    received = []

    def create(**kwargs):
        received.append(kwargs)
        return SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    finish_reason="length", message=SimpleNamespace(content=None)
                )
            ],
        )

    llm._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    with pytest.raises(ModelResponseError, match="长度上限"):
        llm.invoke([{"role": "user", "content": "review"}])
    assert received[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert llm.calls[0]["reason"].startswith("模型输出达到")
    with pytest.raises(BudgetExceeded):
        llm.invoke([{"role": "user", "content": "again"}])
    assert len(received) == 1


def test_tool_round_limit_forces_json_without_another_tool_round():
    index = CodeIndex({"a.py": "x = 1\n"})
    fake = FakeLLM(
        [
            "[TOOL_CALL:read_code:path=a.py,start=1,end=1]",
            "[TOOL_CALL:read_code:path=a.py,start=1,end=1]",
            '{"findings":[]}',
        ]
    )
    agents = ReviewAgents(index, fake)
    agent = BoundedAgent(
        name="test",
        llm=fake,
        system_prompt="Return JSON.",
        tool_registry=agents.registry,
    )
    assert parse_json(agent.run('{"path":"a.py"}')) == {"findings": []}
    assert len(fake.calls) == 3
    assert len(index.reads) == 2


def test_same_mutable_default_diagnosis_is_merged_with_provenance(tmp_path):
    repo = fixture_repo(
        tmp_path,
        "def collect(value, items=[]):\n    items.append(value)\n    return items\n",
    )
    c = dict(
        candidate(line=1), title="可变默认参数共享状态", evidence="items=[]", end_line=1
    )
    fake = FakeLLM([json.dumps({"findings": [c]}), verify_answer])
    report = run_review(repo, ReviewOptions(), llm=fake, progress=lambda _: None)
    assert len(report["findings"]) == 1
    assert report["findings"][0]["source"] == "llm"
    assert report["findings"][0]["related_diagnostics"][0]["rule"] == "B006"
