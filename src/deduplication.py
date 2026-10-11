from .schemas import Finding


def matches_rule(rule: str, finding: Finding) -> bool:
    text = (finding.title + " " + finding.explanation + " " + finding.evidence).lower()
    if rule == "B006":
        return ("默认" in text or "default" in text) and (
            "可变" in text or "mutable" in text
        )
    if rule == "B608":
        return "sql" in text and any(
            word in text for word in ["注入", "拼接", "injection", "interpolation"]
        )
    if rule == "B101":
        return "assert" in text and any(
            word in text for word in ["优化", "-o", "optim", "移除"]
        )
    if rule == "B028":
        return "stacklevel" in text
    return False


def deduplicate(findings: list[Finding]) -> list[Finding]:
    """Merge only unambiguous same-location diagnostics with the same verdict."""
    semantic = [f.model_copy(deep=True) for f in findings if f.source == "llm"]
    result = list(semantic)
    for diagnostic in findings:
        if diagnostic.source == "llm":
            continue
        matches = [
            f
            for f in semantic
            if f.path == diagnostic.path
            and f.line == diagnostic.line
            and f.category == diagnostic.category
            and f.status == diagnostic.status
            and matches_rule(diagnostic.rule, f)
        ]
        if len(matches) == 1:
            if not any(
                d["id"] == diagnostic.id for d in matches[0].related_diagnostics
            ):
                matches[0].related_diagnostics.append(
                    diagnostic.model_dump(exclude={"related_diagnostics"})
                )
        else:
            result.append(diagnostic)
    unique = {}
    for finding in result:
        key = (finding.path, finding.line, finding.rule, finding.title.strip().lower())
        unique.setdefault(key, finding)
    return list(unique.values())
