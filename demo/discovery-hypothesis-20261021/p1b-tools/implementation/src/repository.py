"""Obtain a fixed checkout without executing repository code."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit


@dataclass
class Repository:
    root: Path
    url: str
    commit: str
    ref: str
    name: str


def github_url(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "仓库地址必须是 https://github.com/owner/repo，分支请用 --ref 指定。"
        )
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        raise ValueError("请提供仓库根地址，不是文件、目录或 PR 链接。")
    owner, name = parts
    if name.endswith(".git"):
        name = name[:-4]
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in (owner, name)):
        raise ValueError("仓库用户名或名称不合法。")
    if any(p in (".", "..", "") for p in (owner, name)):
        raise ValueError("仓库用户名或名称不合法。")
    return f"https://github.com/{owner}/{name}", f"{owner}-{name}"


def git_run(args: list[str], timeout: int = 120) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    command = [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "protocol.ext.allow=never",
        "-c",
        "protocol.file.allow=never",
        *args,
    ]
    try:
        result = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Git 操作超时，请检查网络或使用 --local 本地仓库。") from exc
    if result.returncode:
        # Do not print git stderr: credential helpers/proxies may put secrets there.
        raise RuntimeError("Git 操作失败，请检查仓库地址、分支、网络和访问权限。")
    return result.stdout.strip()


@contextmanager
def acquire_repository(target: str, ref: str | None = None, local: bool = False):
    if local:
        root = Path(target).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("本地仓库目录不存在。")
        try:
            commit = git_run(["-C", str(root), "rev-parse", "HEAD"])
            dirty = bool(git_run(["-C", str(root), "status", "--porcelain"]))
            if dirty:
                commit += " (working-tree-modified)"
        except RuntimeError:
            commit = "local-unversioned"
        yield Repository(root, "local", commit, ref or "working-tree", root.name)
        return
    url, name = github_url(target)
    if ref and (ref.startswith("-") or any(ord(c) < 32 for c in ref)):
        raise ValueError("分支名称不合法。")
    with tempfile.TemporaryDirectory(prefix="code-review-") as directory:
        root = Path(directory) / "checkout"
        args = ["clone", "--depth", "1", "--single-branch", "--no-tags"]
        if ref:
            args += ["--branch", ref]
        git_run([*args, "--", url + ".git", str(root)])
        commit = git_run(["-C", str(root), "rev-parse", "HEAD"])
        branch = git_run(["-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"])
        yield Repository(root, url, commit, ref or branch, name)


IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
}


def inventory(
    root: Path, scope: str, max_file_bytes: int
) -> tuple[dict[str, str], list[dict]]:
    scope_path = (root / scope).resolve()
    if not scope_path.is_relative_to(root) or not scope_path.exists():
        raise ValueError("--scope 必须指向仓库内存在的文件或目录。")
    files: dict[str, str] = {}
    excluded: list[dict] = []
    paths = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in IGNORED_DIRS and not (Path(directory) / d).is_symlink()
        )
        paths.extend(Path(directory) / n for n in sorted(names))
        if len(paths) > 20_000:
            raise ValueError("仓库超过 20000 个文件，请使用较小仓库或本地精简副本。")
    for path in paths:
        relative = path.relative_to(root).as_posix()
        reason = ""
        if path.is_symlink():
            reason = "symlink"
        elif path.name.startswith(".env") or path.suffix.lower() in {
            ".pem",
            ".key",
            ".p12",
        }:
            reason = "sensitive_file"
        elif not (path == scope_path or path.is_relative_to(scope_path)):
            reason = "outside_scope"
        elif path.suffix != ".py":
            reason = "unsupported_language_or_resource"
        elif path.stat().st_size > max_file_bytes:
            reason = "file_size_limit"
        if reason:
            excluded.append({"path": relative, "reason": reason})
            continue
        try:
            source = path.read_text(encoding="utf-8-sig")
            if "\0" in source:
                raise UnicodeError("binary")
        except (OSError, UnicodeError):
            excluded.append({"path": relative, "reason": "unreadable_or_non_utf8"})
            continue
        if sum(len(v) for v in files.values()) + len(source) > 8_000_000:
            excluded.append({"path": relative, "reason": "index_size_limit"})
            continue
        files[relative] = source
    return files, excluded


def snapshot_digest(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for path, content in sorted(files.items()):
        digest.update(path.encode() + b"\0" + content.encode() + b"\0")
    return digest.hexdigest()
