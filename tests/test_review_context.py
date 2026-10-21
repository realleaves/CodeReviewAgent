import hashlib
import json

import pytest

from src.agents import EVIDENCE_REVIEW_PROMPT, ReviewAgents
from src.code_index import Chunk, CodeIndex, numbered
from src.pipeline import run_review
from src.repository import Repository
from src.review_context import CallContext
from src.schemas import ReviewOptions
from tests.test_review import FakeLLM


def pairs(graph):
    return {(s.path, c.lineno, t.path, graph.label(t)) for s, c, t in graph.edges}


def test_import_alias_and_caller_guard_are_retrieved_without_same_name_collision():
    files = {
        "pkg/worker.py": 'def normalize(value):\n    """Accept a nonempty value."""\n    return value[0]\n',
        "pkg/api.py": "from .worker import normalize as clean\ndef handle(value):\n    if not value:\n        return None\n    return clean(value)\n",
        "other.py": "def normalize(value):\n    raise RuntimeError('wrong definition')\n",
    }
    graph = CallContext(CodeIndex(files))
    supplement = graph.supplement("pkg/api.py", 5, 5)
    callees = [i for i in supplement["context"] if i["relation"] == "callee"]
    assert [i["path"] for i in callees] == ["pkg/worker.py"]
    supplement = graph.supplement("pkg/worker.py", 1, 3)
    callers = [i for i in supplement["context"] if i["relation"] == "caller"]
    assert len(callers) == 1
    assert callers[0]["path"] == "pkg/api.py"
    assert "if not value:" in callers[0]["code"]
    assert "return clean(value)" in callers[0]["code"]


@pytest.mark.parametrize(
    "statement",
    [
        "from pkg.worker import normalize as clean\nclean(1)",
        "import pkg.worker as worker\nworker.normalize(1)",
        "import pkg.worker\npkg.worker.normalize(1)",
        "from pkg import worker\nworker.normalize(1)",
        "from pkg import normalize\nnormalize(1)",
    ],
)
def test_static_import_forms_and_reexports(statement):
    files = {
        "pkg/worker.py": "def normalize(value):\n    return value\n",
        "pkg/__init__.py": "from .worker import normalize\n",
        "api.py": statement,
    }
    graph = CallContext(CodeIndex(files))
    assert any(
        p == "api.py" and t == "pkg/worker.py" and n == "normalize"
        for p, _, t, n in pairs(graph)
    )


@pytest.mark.parametrize(
    "source",
    [
        "from pkg.worker import normalize\ndef call(normalize):\n    return normalize(1)\n",
        "from pkg.worker import normalize\ndef call():\n    normalize = get_callable()\n    return normalize(1)\n",
        "from pkg.worker import normalize\nnormalize = object()\nnormalize(1)\n",
        "from pkg.worker import *\nnormalize(1)\n",
        "def call(obj):\n    return obj.normalize(1)\n",
    ],
)
def test_unknown_or_shadowed_bindings_do_not_guess_a_same_name_target(source):
    files = {
        "pkg/worker.py": "def normalize(value):\n    return value\n",
        "api.py": source,
    }
    graph = CallContext(CodeIndex(files))
    assert not any(t == "pkg/worker.py" for _, _, t, _ in pairs(graph))
    supplement = graph.supplement("api.py", 1, len(source.splitlines()))
    assert any(i["relation"] == "unresolved_calls" for i in supplement["context"])


def test_self_methods_nested_functions_and_shadowed_instance_method():
    source = """class A:
    def helper(self):
        return 1
    def call(self):
        def nested():
            return self.helper()
        return nested()
class B:
    def helper(self):
        return 2
    def call(self):
        return self.helper()
class C:
    def helper(self):
        return 3
    def __init__(self, other):
        self.helper = other
    def call(self):
        return self.helper()
"""
    graph = CallContext(CodeIndex({"a.py": source}))
    targets = {(line, name) for _, line, _, name in pairs(graph)}
    assert (6, "A.helper") in targets
    assert (7, "A.call.nested") in targets
    assert (12, "B.helper") in targets
    assert (19, "C.helper") not in targets


def test_import_cycles_and_duplicate_modules_stay_unresolved():
    graph = CallContext(
        CodeIndex({"a.py": "from b import fn\nfn()\n", "b.py": "from a import fn\n"})
    )
    assert not graph.edges
    graph = CallContext(
        CodeIndex(
            {
                "pkg.py": "def fn():\n    pass\n",
                "pkg/__init__.py": "def fn():\n    pass\n",
                "a.py": "from pkg import fn\nfn()\n",
            }
        )
    )
    assert not graph.edges


@pytest.mark.parametrize(
    "source",
    [
        "from pkg.worker import normalize\ndef run(value):\n    match value:\n        case normalize:\n            return normalize(1)\n",
        "import pkg.worker as worker\nworker.normalize = replacement\nworker.normalize(1)\n",
    ],
)
def test_pattern_capture_and_module_attribute_rebinding_do_not_create_false_edges(
    source,
):
    graph = CallContext(
        CodeIndex(
            {
                "pkg/worker.py": "def normalize(value):\n    return value\n",
                "api.py": source,
            }
        )
    )
    assert not any(target == "pkg/worker.py" for _, _, target, _ in pairs(graph))


def test_nested_helpers_cannot_displace_outer_definition_and_public_caller():
    source = (
        'def parse_format(value):\n    """Parse a documented format expression."""\n'
    )
    for i in range(8):
        source += f"    def helper{i}(value):\n        return value\n"
    source += "    return helper7(value)\ndef handle(value):\n    return parse_format(value)\n"
    graph = CallContext(CodeIndex({"a.py": source}))
    result = graph.supplement("a.py", 3, 18)
    assert any(
        i.get("symbol") == "parse_format" and i["relation"] == "enclosing_definition"
        for i in result["context"]
    )
    assert any(
        i.get("symbol") == "handle" and i["relation"] == "caller"
        for i in result["context"]
    )


def test_deep_unrelated_source_does_not_break_retrieval():
    files = {
        "deep.py": "value = " + "+".join(["1"] * 1500),
        "a.py": "def f():\n    return 1\n",
        "b.py": "from a import f\nf()\n",
    }
    graph = CallContext(CodeIndex(files))
    assert any(t == "a.py" for _, _, t, _ in pairs(graph))


def test_partial_function_and_relevant_document_beyond_prefix_keep_real_spans():
    source = 'def choose(value):\n    """Choose a format for the value."""\n    return value[0]\n'
    doc = "\n".join(
        ["unrelated introduction"] * 100
        + ["The choose function accepts a nonempty value."]
    )
    index = CodeIndex({"a.py": source}, {"README.md": doc})
    supplement = CallContext(index).supplement("a.py", 3, 3)
    assert any(
        i.get("relation") == "enclosing_definition" and "nonempty" not in i["code"]
        for i in supplement["context"]
    )
    assert any(
        i["end"] > 80 and "nonempty value" in i["code"] for i in supplement["documents"]
    )
    for entries in supplement.values():
        for item in entries:
            if "code" not in item:
                continue
            text = {**index.files, **index.resources}[item["path"]]
            assert item["code"] == numbered(text, item["start"], item["end"])
            if item["path"] == "a.py":
                assert item["end"] < 3


def test_supplement_is_bounded_deterministic_and_does_not_execute_source(tmp_path):
    sentinel = tmp_path / "executed"
    source = f"open({str(sentinel)!r}, 'w').write('unsafe')\n"
    source += (
        "def worker(value):\n"
        + "".join(f"    v{i} = {('x' * 130)!r}\n" for i in range(100))
        + "    return value\n"
    )
    index = CodeIndex(
        {
            "worker.py": source,
            "api.py": "from worker import worker\ndef call():\n    return worker(1)\n",
            "broken.py": "def broken(\n",
        },
        {"README.md": "worker accepts value.\n" * 1000},
    )
    graph = CallContext(index)
    first = graph.supplement("api.py", 3, 3, max_chars=2400)
    assert len(json.dumps(first, ensure_ascii=False)) <= 2400
    assert first == graph.supplement("api.py", 3, 3, max_chars=2400)
    assert not sentinel.exists()
    with pytest.raises(ValueError):
        graph.supplement("api.py", 3, 3, max_chars=1)


def test_only_evidence_context_changes_and_original_prompt_and_payload_are_preserved():
    index = CodeIndex(
        {"a.py": "def f():\n    return 1\n"}, {"README.md": "f returns one."}
    )
    chunk = Chunk("a.py", 1, 2, numbered(index.files["a.py"]))
    original = ReviewAgents(index, FakeLLM([]))
    expected = {
        "primary_path": "a.py",
        "start": 1,
        "end": 2,
        "code": chunk.text,
        "context": index.context("a.py", 1, 2),
        "documents": [
            {"path": p, "code": numbered(s, 1, 80)} for p, s in index.resources.items()
        ],
    }
    assert original.review_payload(chunk, [], evidence=True) == expected
    messages_seen = []

    def answer(messages):
        messages_seen.append(messages)
        return '{"findings":[]}'

    llm = FakeLLM([answer])
    revised = ReviewAgents(index, llm, "callgraph")
    assert original.review_payload(chunk, [], direct=True) == revised.review_payload(
        chunk, [], direct=True
    )
    assert original.review_payload(chunk, []) == revised.review_payload(chunk, [])
    assert revised.review(chunk, [], evidence=True) == []
    assert len(llm.calls) == 1
    assert messages_seen[0][0]["content"].startswith(EVIDENCE_REVIEW_PROMPT)
    actual = messages_seen[0][1]["content"]
    trace = next(t for t in revised.trace if t["stage"] == "review_context")
    assert trace["strategy"] == "callgraph"
    assert trace["payload_sha256"] == hashlib.sha256(actual.encode()).hexdigest()


def test_cli_option_reaches_pipeline_and_report(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    repo = Repository(tmp_path, "local", "fixture", "fixture", "fixture")
    options = ReviewOptions(mode="evidence", context_strategy="callgraph")
    report = run_review(
        repo, options, llm=FakeLLM(['{"findings":[]}']), progress=lambda _: None
    )
    assert report["run"]["options"]["context_strategy"] == "callgraph"
    assert any(t.get("strategy") == "callgraph" for t in report["trace"])
    assert report["run"]["api_calls"] == 1
    assert ReviewOptions().context_strategy == "legacy"
