import ast
from dataclasses import dataclass
import hashlib
import json


@dataclass
class Chunk:
    path: str
    start: int
    end: int
    text: str


def numbered(source: str, start: int = 1, end: int | None = None) -> str:
    lines = source.splitlines()
    end = min(end or len(lines), len(lines))
    return "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))


def chunks(path: str, source: str, max_lines: int, max_chars: int) -> list[Chunk]:
    lines = source.splitlines()
    result = []
    start = 1
    while start <= len(lines):
        end = start - 1
        size = 0
        while end < len(lines) and end - start + 1 < max_lines:
            next_size = len(lines[end]) + 12
            if size + next_size > max_chars:
                if end < start:
                    raise ValueError(
                        "单行代码超过输入预算，文件需要提高 --chunk-chars。"
                    )
                break
            size += next_size
            end += 1
        result.append(Chunk(path, start, end, numbered(source, start, end)))
        start = end + 1
    return result


class CodeIndex:
    def __init__(self, files: dict[str, str]):
        self.files = files
        self.symbols: list[dict] = []
        self.imports: dict[str, list[str]] = {}
        self.syntax_errors: dict[str, dict] = {}
        self.reads: list[dict] = []
        for path, source in files.items():
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError, RecursionError) as exc:
                self.syntax_errors[path] = {
                    "line": getattr(exc, "lineno", 1) or 1,
                    "message": str(exc)[:300],
                }
                continue
            imports = []
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    self.symbols.append(
                        {
                            "path": path,
                            "name": node.name,
                            "line": node.lineno,
                            "end": node.end_lineno,
                        }
                    )
                elif isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append("." * node.level + (node.module or ""))
            self.imports[path] = imports

    def outline(self, path: str) -> dict:
        return {
            "path": path,
            "lines": len(self.files[path].splitlines()),
            "imports": self.imports.get(path, [])[:30],
            "symbols": [s for s in self.symbols if s["path"] == path][:60],
        }

    def related(self, path: str, limit: int = 3, chars: int = 6500) -> list[dict]:
        """Find repository modules mentioned in imports; no dynamic imports."""
        names = {
            p: p[:-3].replace("/", ".").removesuffix(".__init__") for p in self.files
        }
        related = []
        budget = chars
        for imported in self.imports.get(path, []):
            tail = imported.lstrip(".")
            if not tail:
                continue
            for other, module in names.items():
                if other == path or any(r["path"] == other for r in related):
                    continue
                if module == tail or module.endswith("." + tail):
                    snippet = numbered(self.files[other], 1, 80)
                    if len(snippet) > budget:
                        continue
                    budget -= len(snippet)
                    related.append(
                        {"path": other, "outline": self.outline(other), "code": snippet}
                    )
                    if len(related) >= limit:
                        return related
        return related

    def read(self, path: str, start: int = 1, end: int = 80) -> str:
        if path not in self.files:
            return json.dumps(
                {"error": "只能读取已索引的仓库 Python 文件。"}, ensure_ascii=False
            )
        line_count = len(self.files[path].splitlines())
        if start < 1 or end < start or start > line_count:
            return json.dumps({"error": "行号不合法。"}, ensure_ascii=False)
        end = min(end, start + 119, line_count)
        text = numbered(self.files[path], start, end)
        while len(text) > 12_000 and end > start:
            end -= 1
            text = numbered(self.files[path], start, end)
        if len(text) > 12_000:
            return json.dumps({"error": "单行代码超过读取预算。"}, ensure_ascii=False)
        self.reads.append({"path": path, "start": start, "end": end})
        return json.dumps(
            {"path": path, "start": start, "end": end, "code": text}, ensure_ascii=False
        )

    def search(self, symbol: str) -> str:
        if not symbol or len(symbol) > 200:
            return '{"error":"请提供长度1至200的符号名"}'
        return json.dumps(
            {"matches": [s for s in self.symbols if symbol in s["name"]][:20]},
            ensure_ascii=False,
        )


def finding_id(path: str, line: int, rule: str, title: str) -> str:
    return hashlib.sha256(f"{path}:{line}:{rule}:{title}".encode()).hexdigest()[:12]
