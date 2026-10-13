"""Pinned BugsInPy metadata and independent snapshots; never source shell metadata."""

import ast
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

from src.repository import git_run, github_url

DATASET_COMMIT = "11c5f1eea954a42132cfd06bf257766a7963e0fd"
PROJECT_COUNTS = {"PySnooper": 3, "tornado": 8, "youtube-dl": 9}


def read_text(path):
    data = Path(path).read_bytes()
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    return data.decode(encoding)


def metadata(path):
    result = {}
    for line in read_text(path).splitlines():
        match = re.fullmatch(r'\s*([a-z_]+)\s*=\s*"([^"\r\n]*)"\s*', line)
        if match:
            result[match[1]] = match[2]
    return result


def safe_relative(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or not value:
        raise ValueError("Unsafe dataset path")
    return path.as_posix()


def patch_ranges(text):
    """Keep full hunk context; scoring must separately check issue meaning."""
    result = defaultdict(lambda: {"buggy": [], "fixed": []})
    path = None
    for line in text.splitlines():
        if line.startswith("diff --git a/"):
            match = re.fullmatch(r"diff --git a/(.+) b/(.+)", line)
            if not match or match[1] != match[2]:
                raise ValueError("Renamed paths require explicit dataset adaptation")
            path = safe_relative(match[1])
        elif line.startswith("@@") and path:
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not match:
                raise ValueError("Invalid patch hunk")
            for side, position in [("buggy", 1), ("fixed", 3)]:
                start = int(match[position])
                count = int(match[position + 1] or 1)
                result[path][side].append([max(1, start), max(1, start + count - 1)])
    return dict(result)


def is_production(path):
    return path.endswith(".py") and not any(
        part in {"test", "tests", "docs", "examples"} or part.startswith("test_")
        for part in Path(path).parts
    )


def make_manifest(dataset, project_counts=None, start_ids=None):
    actual = git_run(["-C", str(dataset), "rev-parse", "HEAD"])
    if actual != DATASET_COMMIT:
        raise ValueError(f"BugsInPy must be pinned to {DATASET_COMMIT}")
    if git_run(["-C", str(dataset), "status", "--porcelain", "--", "projects"]):
        raise ValueError("BugsInPy project metadata has local changes")
    cases = []
    counts = project_counts or PROJECT_COUNTS
    starts = start_ids or {p: 1 for p in counts}
    # Interleave projects: the first three cases cover one project each.
    for offset in range(max(counts[p] - starts[p] + 1 for p in counts)):
        for project, count in counts.items():
            number = starts[project] + offset
            if number > count:
                continue
            base = dataset / "projects" / project
            folder = base / "bugs" / str(number)
            info = metadata(folder / "bug.info")
            url, _ = github_url(metadata(base / "project.info")["github_url"])
            for key in ["buggy_commit_id", "fixed_commit_id"]:
                if not re.fullmatch("[0-9a-f]{40}", info[key]):
                    raise ValueError("Invalid commit in dataset")
            patch = read_text(folder / "bug_patch.txt")
            regions = {p: r for p, r in patch_ranges(patch).items() if is_production(p)}
            if not regions:
                raise ValueError("Selected case has no production Python change")
            tests = [safe_relative(p.strip()) for p in info["test_file"].split(";")]
            cases.append(
                {
                    "id": f"{project}-{number}",
                    "project": project,
                    "bug_id": number,
                    "repository": url,
                    "python_version": info["python_version"],
                    "buggy_commit": info["buggy_commit_id"],
                    "fixed_commit": info["fixed_commit_id"],
                    "test_files": tests,
                    "test_command": read_text(folder / "run_test.sh").strip(),
                    "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
                    "production_hunks": regions,
                }
            )
    return {
        "dataset": "BugsInPy",
        "dataset_commit": actual,
        "dataset_url": "https://github.com/soarsmu/BugsInPy",
        "selection": "First numeric IDs: PySnooper 1-3, tornado 1-8, youtube-dl 1-9; selected before inference; all failures retained."
        if project_counts is None and start_ids is None
        else f"Preselected numeric IDs: {', '.join(f'{p} {starts[p]}-{counts[p]}' for p in counts)}; all failures retained.",
        "protocol": "Known-location production-code windows; fixed snapshot follows BugsInPy checkout semantics (buggy baseline plus fixed-commit changed files); fixed test files copied into both reproduction snapshots. Labels and tests are excluded from reviewer context.",
        "cases": cases,
    }


def archive_snapshot(cache, commit, output):
    """Extract regular files only, without traversing archive links."""
    data = subprocess.run(
        ["git", "--git-dir", str(cache), "archive", commit],
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout
    output.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive:
            if not member.isfile():
                continue
            relative = safe_relative(member.name)
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source:
                target.write_bytes(source.read())


def checkout_file(cache, commit, relative, target):
    relative = safe_relative(relative)
    mode = git_run(["--git-dir", str(cache), "ls-tree", commit, "--", relative]).split()
    if not mode or mode[0] not in {"100644", "100755"}:
        raise ValueError("Expected a regular file in fixed commit")
    data = subprocess.run(
        ["git", "--git-dir", str(cache), "show", f"{commit}:{relative}"],
        capture_output=True,
        timeout=30,
        check=True,
    ).stdout
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def prepare(manifest, output, progress=print):
    """Download fixed commits once per project; never run target setup scripts."""
    cache_root = output / "source-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    by_project = defaultdict(list)
    for case in manifest["cases"]:
        by_project[case["project"]].append(case)
    for project, cases in by_project.items():
        cache = cache_root / f"{project}.git"
        if not cache.exists():
            git_run(["init", "--bare", str(cache)])
            git_run(
                [
                    "--git-dir",
                    str(cache),
                    "remote",
                    "add",
                    "origin",
                    cases[0]["repository"] + ".git",
                ]
            )
        commits = sorted(
            {c[k] for c in cases for k in ["buggy_commit", "fixed_commit"]}
        )
        missing = [
            c
            for c in commits
            if subprocess.run(
                ["git", "--git-dir", str(cache), "cat-file", "-e", c],
                capture_output=True,
            ).returncode
        ]
        if missing:
            progress(f"获取 {project} 的 {len(missing)} 个固定 commit")
            git_run(
                [
                    "--git-dir",
                    str(cache),
                    "fetch",
                    "--depth",
                    "2",
                    "--no-tags",
                    "origin",
                    *missing,
                ],
                timeout=240,
            )
    prepared = []
    for index, case in enumerate(manifest["cases"], 1):
        progress(f"准备快照 {index}/{len(manifest['cases'])}: {case['id']}")
        cache = cache_root / f"{case['project']}.git"
        folder = output / "snapshots" / f"{index:04d}"
        mapping = (
            {"buggy": "A", "fixed": "B"} if index % 2 else {"buggy": "B", "fixed": "A"}
        )
        roots = {side: folder / letter for side, letter in mapping.items()}
        marker = folder / "prepared.json"
        if marker.exists():
            old = json.loads(marker.read_text())
            if (
                old["buggy_commit"] != case["buggy_commit"]
                or old["fixed_commit"] != case["fixed_commit"]
            ):
                raise ValueError("Existing snapshot does not match manifest")
            prepared.append(old)
            continue
        if folder.exists():
            raise ValueError("Unfinished snapshot exists; use a fresh --work directory")
        archive_snapshot(cache, case["buggy_commit"], roots["buggy"])
        shutil.copytree(roots["buggy"], roots["fixed"])
        changed = git_run(
            [
                "--git-dir",
                str(cache),
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                case["fixed_commit"],
            ]
        ).splitlines()
        if not changed:
            raise ValueError(
                "Fixed commit has no readable parent diff; fetch with depth >= 2"
            )
        # Official checkout restores changed fixed files on the buggy baseline.
        for relative in changed:
            if (
                relative
                and subprocess.run(
                    [
                        "git",
                        "--git-dir",
                        str(cache),
                        "cat-file",
                        "-e",
                        f"{case['fixed_commit']}:{relative}",
                    ],
                    capture_output=True,
                ).returncode
                == 0
            ):
                checkout_file(
                    cache,
                    case["fixed_commit"],
                    relative,
                    roots["fixed"] / safe_relative(relative),
                )
        for relative in case["test_files"]:
            for root in roots.values():
                checkout_file(cache, case["fixed_commit"], relative, root / relative)
        record = {
            **case,
            "snapshot_paths": {s: str(p.relative_to(output)) for s, p in roots.items()},
            "changed_fixed_files": changed,
        }
        marker.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        prepared.append(record)
    (output / "prepared.json").write_text(
        json.dumps(prepared, ensure_ascii=False, indent=2) + "\n"
    )
    return prepared


def windows(source, hunks, max_lines=220):
    """Expand a known hunk to its containing function, or bounded nearby context."""
    lines = source.splitlines()
    try:
        nodes = [
            n
            for n in ast.walk(ast.parse(source))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
    except SyntaxError:
        nodes = []
    ranges = []
    for start, end in hunks:
        start, end = max(1, start), min(len(lines), max(start, end))
        enclosing = [n for n in nodes if n.lineno <= start and n.end_lineno >= end]
        enclosing.sort(key=lambda n: n.end_lineno - n.lineno)
        if enclosing and enclosing[0].end_lineno - enclosing[0].lineno < max_lines:
            node = enclosing[0]
            low, high = max(1, node.lineno - 8), min(len(lines), node.end_lineno + 8)
        else:
            low, high = max(1, start - 45), min(len(lines), end + 45)
            if high - low + 1 > max_lines:
                # Include all hunk lines through several non-overlapping windows.
                for pos in range(low, high + 1, max_lines):
                    ranges.append([pos, min(pos + max_lines - 1, high)])
                continue
        ranges.append([low, high])
    merged = []
    for start, end in sorted(ranges):
        if (
            merged
            and start <= merged[-1][1] + 1
            and end - merged[-1][0] + 1 <= max_lines
        ):
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
