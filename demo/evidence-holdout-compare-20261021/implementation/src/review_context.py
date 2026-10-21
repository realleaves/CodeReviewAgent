"""Bounded, static context retrieval. No imports or repository code execution."""

import ast
from dataclasses import dataclass, field
import json
import re

from .code_index import numbered, parse_source


@dataclass(eq=False)
class Scope:
    path: str
    name: str
    node: ast.AST
    parent: "Scope | None" = None
    bindings: dict = field(default_factory=dict)
    star_import: bool = False

    def bind(self, name, value):
        self.bindings.setdefault(name, []).append(value)


class Collector(ast.NodeVisitor):
    def __init__(self, graph, scope):
        self.graph, self.scope = graph, scope

    def definition(self, node):
        parent = self.scope
        scope = Scope(parent.path, node.name, node, parent)
        parent.bind(node.name, scope)
        self.graph.definitions.append(scope)
        # Defaults and decorators execute in the enclosing scope.
        for expression in node.decorator_list:
            self.visit(expression)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for expression in [*node.args.defaults, *node.args.kw_defaults]:
                if expression is not None:
                    self.visit(expression)
            arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            arguments += [a for a in [node.args.vararg, node.args.kwarg] if a]
            for argument in arguments:
                scope.bind(argument.arg, None)
            decorators = {d.id for d in node.decorator_list if isinstance(d, ast.Name)}
            if (
                isinstance(parent.node, ast.ClassDef)
                and "staticmethod" not in decorators
            ):
                positional = [*node.args.posonlyargs, *node.args.args]
                if positional:
                    scope.bindings[positional[0].arg] = [parent]
        self.scope = scope
        for statement in node.body:
            self.visit(statement)
        self.scope = parent

    visit_FunctionDef = definition
    visit_AsyncFunctionDef = definition
    visit_ClassDef = definition

    def visit_Import(self, node):
        self.graph.imports.append((self.scope, node))
        for alias in node.names:
            self.scope.bind(
                alias.asname or alias.name.split(".")[0],
                alias.name if alias.asname else alias.name.split(".")[0],
            )

    def visit_ImportFrom(self, node):
        self.graph.imports.append((self.scope, node))
        package = self.graph.module_name(self.scope.path).split(".")
        if not self.scope.path.endswith("/__init__.py"):
            package = package[:-1]
        if node.level:
            if node.level > len(package):
                module = ""  # Invalid relative import: leave unresolved.
            else:
                module = ".".join(
                    package[: len(package) - node.level + 1]
                    + ([node.module] if node.module else [])
                )
        else:
            module = node.module or ""
        for alias in node.names:
            if alias.name == "*":
                self.scope.star_import = True
            else:
                self.scope.bind(
                    alias.asname or alias.name,
                    f"{module}.{alias.name}" if module else None,
                )

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.scope.bind(node.id, None)

    def visit_Attribute(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.graph.mutations.append((self.scope, node.value, node.attr))
        self.generic_visit(node)

    def visit_MatchAs(self, node):
        if node.name:
            self.scope.bind(node.name, None)
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node):
        if node.rest:
            self.scope.bind(node.rest, None)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.scope.bind(node.name, None)
        self.generic_visit(node)

    def visit_Global(self, node):
        for name in node.names:
            self.scope.bind(name, None)

    visit_Nonlocal = visit_Global

    def visit_Call(self, node):
        self.graph.calls.append((self.scope, node))
        self.generic_visit(node)

    def visit_Lambda(self, node):
        # Dynamic closures and comprehensions need separate binding analysis.
        pass

    visit_ListComp = visit_Lambda
    visit_SetComp = visit_Lambda
    visit_DictComp = visit_Lambda
    visit_GeneratorExp = visit_Lambda


class CallContext:
    def __init__(self, index):
        self.index = index
        self.modules, self.definitions, self.calls, self.imports = {}, [], [], []
        self.mutations = []
        for path, source in sorted(index.files.items()):
            try:
                tree = parse_source(source)
            except (SyntaxError, ValueError, RecursionError):
                continue
            scope = Scope(path, "", tree)
            module = self.module_name(path)
            self.modules.setdefault(module, []).append(scope)
            try:
                Collector(self, scope).visit(tree)
            except RecursionError:
                self.modules[module].remove(scope)
                self.definitions = [s for s in self.definitions if s.path != path]
                self.calls = [(s, c) for s, c in self.calls if s.path != path]
                self.imports = [(s, n) for s, n in self.imports if s.path != path]
                self.mutations = [
                    (s, n, a) for s, n, a in self.mutations if s.path != path
                ]
        for scope, expression, attribute in self.mutations:
            target = self.resolve(scope, expression)
            if isinstance(target, Scope):
                target.bind(attribute, None)
        self.edges, self.unresolved = [], []
        for scope, call in self.calls:
            target = self.resolve(scope, call.func)
            if isinstance(target, Scope) and target.parent is not None:
                self.edges.append((scope, call, target))
            else:
                self.unresolved.append((scope, call))

    @staticmethod
    def module_name(path):
        return path.removesuffix(".py").replace("/", ".").removesuffix(".__init__")

    def lookup(self, scope, name):
        while scope:
            if scope.star_import:
                return None
            if name in scope.bindings:
                values = scope.bindings[name]
                return values[0] if len(values) == 1 else None
            parent = scope.parent
            # Class namespaces are not closure scopes for method bodies.
            while parent and isinstance(parent.node, ast.ClassDef):
                parent = parent.parent
            scope = parent
        return None

    def imported(self, value, seen):
        if not isinstance(value, str):
            return value
        if value in seen or len(seen) >= 8:
            return None
        seen = seen | {value}
        if value in self.modules:
            matches = self.modules[value]
            return matches[0] if len(matches) == 1 else None
        module, _, name = value.rpartition(".")
        modules = self.modules.get(module, [])
        if len(modules) != 1 or modules[0].star_import:
            return None
        bindings = modules[0].bindings.get(name, [])
        if len(bindings) == 1:
            return self.imported(bindings[0], seen)
        return None

    def resolve(self, scope, expression):
        if isinstance(expression, ast.Name):
            return self.imported(self.lookup(scope, expression.id), set())
        if not isinstance(expression, ast.Attribute):
            return None
        # Resolve imported module chains, including `import package.module`.
        attributes = []
        base = expression
        while isinstance(base, ast.Attribute):
            attributes.insert(0, base.attr)
            base = base.value
        if not isinstance(base, ast.Name):
            return None
        value = self.lookup(scope, base.id)
        for attribute in attributes:
            if isinstance(value, str):
                candidate = value + "." + attribute
                if candidate in self.modules:
                    value = candidate
                    continue
                value = self.imported(value, set())
            if not isinstance(value, Scope):
                return None
            bindings = value.bindings.get(attribute, [])
            value = (
                bindings[0] if len(bindings) == 1 and not value.star_import else None
            )
        return self.imported(value, set())

    @staticmethod
    def label(scope):
        names = []
        while scope and scope.parent:
            names.insert(0, scope.name)
            scope = scope.parent
        return ".".join(names)

    def supplement(self, path, start, end, max_chars=10000):
        """Return source spans, with an exact JSON character cap including metadata."""
        payload = {"context": [], "documents": []}
        if max_chars < len(json.dumps(payload, ensure_ascii=False)):
            raise ValueError("上下文预算不足以容纳空结构。")
        covered = {path: [(start, end)]}

        def add(
            source_path,
            low,
            high,
            relation,
            symbol="",
            destination="context",
            **metadata,
        ):
            source = {**self.index.resources, **self.index.files}[source_path]
            lines = source.splitlines()
            low, high = max(1, low), min(high, len(lines))
            spans = [(low, high)]
            for left, right in covered.get(source_path, []):
                spans = [(a, min(b, left - 1)) for a, b in spans if a < left] + [
                    (max(a, right + 1), b) for a, b in spans if b > right
                ]
            for low, high in spans:
                if high < low:
                    continue
                item = dict(
                    path=source_path,
                    start=low,
                    end=high,
                    relation=relation,
                    symbol=symbol,
                    **metadata,
                )
                original_high = high
                while high >= low:
                    item.update(
                        end=high,
                        code=numbered(source, low, high),
                        truncated=high < original_high,
                    )
                    payload[destination].append(item)
                    fits = len(json.dumps(payload, ensure_ascii=False)) <= max_chars
                    if fits:
                        covered.setdefault(source_path, []).append((low, high))
                        break
                    payload[destination].pop()
                    high -= 1

        focus = [
            s
            for s in self.definitions
            if s.path == path
            and s.node.lineno <= end
            and s.node.end_lineno >= start
            and not isinstance(s.node, ast.ClassDef)
        ]
        # Keep the enclosing public function ahead of small nested helpers.
        focus.sort(
            key=lambda s: (
                not (s.node.lineno <= start and s.node.end_lineno >= end),
                -(min(s.node.end_lineno, end) - max(s.node.lineno, start) + 1),
                s.node.end_lineno - s.node.lineno,
                s.node.lineno,
            )
        )
        focus = focus[:6]
        caller_edges = [
            (s, c, t)
            for s, c, t in self.edges
            if t in focus and not (s.path == path and start <= c.lineno <= end)
        ]
        caller_edges.sort(
            key=lambda edge: (
                focus.index(edge[2]),
                edge[0] is edge[2],
                edge[0].path,
                edge[1].lineno,
            )
        )
        seen_callers, unique_callers = set(), []
        for edge in caller_edges:
            key = edge[0], edge[2]
            if key not in seen_callers:
                unique_callers.append(edge)
                seen_callers.add(key)
        caller_edges = unique_callers
        callee_edges = [
            (s, c, t)
            for s, c, t in self.edges
            if s.path == path
            and start <= c.lineno <= end
            and not (
                t.path == path and start <= t.node.lineno and t.node.end_lineno <= end
            )
        ]
        callee_edges.sort(
            key=lambda edge: (isinstance(edge[2].node, ast.ClassDef), edge[1].lineno)
        )
        seen_callees, unique_callees = set(), []
        for edge in callee_edges:
            if edge[2] not in seen_callees:
                unique_callees.append(edge)
                seen_callees.add(edge[2])
        callee_edges = unique_callees
        # Preserve a budget for documentation instead of spending everything on code.
        full_limit = max_chars
        max_chars = max(0, full_limit - 2000)
        for scope in focus[:3]:
            add(
                path,
                scope.node.lineno,
                min(scope.node.end_lineno, scope.node.lineno + 17),
                "enclosing_definition",
                self.label(scope),
            )
        used_names = {
            node.id
            for scope_list in self.modules.values()
            for module in scope_list
            if module.path == path
            for node in ast.walk(module.node)
            if isinstance(node, ast.Name) and start <= node.lineno <= end
        }
        relevant_imports = []
        for scope, node in self.imports:
            if scope.path != path:
                continue
            imported_names = {
                a.asname
                or (a.name.split(".")[0] if isinstance(node, ast.Import) else a.name)
                for a in node.names
            }
            if imported_names & used_names:
                relevant_imports.append((scope, node))
        for scope, node in relevant_imports[:4]:
            if node.end_lineno - node.lineno <= 8:
                add(path, node.lineno, node.end_lineno, "import_binding")
            else:
                add(path, node.lineno, node.lineno + 1, "import_binding")
                relevant_aliases = [
                    a for a in node.names if (a.asname or a.name) in used_names
                ]
                for alias in relevant_aliases[:2]:
                    add(path, alias.lineno, alias.end_lineno, "import_binding")
        for i in range(max(min(len(caller_edges), 3), min(len(callee_edges), 3))):
            if i < len(caller_edges) and i < 3:
                scope, call, target = caller_edges[i]
                low = max(getattr(scope.node, "lineno", 1), call.lineno - 22)
                add(
                    scope.path,
                    low,
                    call.end_lineno + 8,
                    "caller",
                    self.label(scope),
                    calls=self.label(target),
                    call_line=call.lineno,
                    resolution="static_binding",
                )
            if i < len(callee_edges) and i < 3:
                _, call, target = callee_edges[i]
                add(
                    target.path,
                    target.node.lineno,
                    min(target.node.end_lineno, target.node.lineno + 44),
                    "callee",
                    self.label(target),
                    call_line=call.lineno,
                    resolution="static_binding",
                )
        for scope in focus[:2]:
            add(
                path,
                max(scope.node.lineno, start - 22),
                start - 1,
                "preceding_code",
                self.label(scope),
            )
            add(
                path,
                end + 1,
                min(scope.node.end_lineno, end + 30),
                "following_code",
                self.label(scope),
            )
        max_chars = full_limit
        names = {s.name for s in focus}
        names.update(t.name for _, _, t in callee_edges)
        tokens = {
            word.lower()
            for name in names
            for word in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", name)
            if len(word) >= 4
        }
        tokens -= {"self", "init", "return", "build", "value", "values"}
        matches = []
        for document, text in sorted(self.index.resources.items()):
            for line, value in enumerate(text.splitlines(), 1):
                words = set(re.findall(r"[a-z]+", value.lower()))
                score = sum(
                    4 for name in names if len(name) > 3 and name in value
                ) + len(tokens & words)
                if score:
                    matches.append((-score, document, line))
        for _, document, line in sorted(matches)[:3]:
            add(
                document,
                line - 3,
                line + 8,
                "documentation_match",
                destination="documents",
                basis="lexical_relevance_only",
            )
        unresolved = []
        for scope, call in self.unresolved:
            if scope.path == path and start <= call.lineno <= end:
                expression = ast.get_source_segment(self.index.files[path], call.func)
                unresolved.append(
                    {
                        "path": path,
                        "line": call.lineno,
                        "expression": (expression or "")[:100],
                    }
                )
        if unresolved:
            item = {
                "relation": "unresolved_calls",
                "reason": "Static analysis could not establish repository bindings; no same-name target assumed.",
                "calls": unresolved[:8],
            }
            payload["context"].append(item)
            if len(json.dumps(payload, ensure_ascii=False)) > max_chars:
                payload["context"].pop()
        return payload
