#!/usr/bin/env python3
"""Reject generated, compiled, or private files in the tracked source export."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

MAX_FILES = 10_000
MAX_CONTENT_BYTES = 2 * 1024 * 1024
BLOCKED_DIRS = {
    "target", ".ci-results", "release-workspace", "worker-logs",
    "worker-prompts", "results", "datasets", "__pycache__",
    ".pytest_cache", ".mypy_cache", "node_modules",
}
BLOCKED_SUFFIXES = {".rlib", ".rmeta", ".o", ".obj", ".exe", ".d", ".pyc",
    ".pyo", ".class", ".so", ".dylib", ".dll"}

# Build sensitive path/token patterns from fragments so these checks do not
# match their own source when the tracked files are scanned.
PRIVATE_PATH = re.compile(
    rb"/(?:Users|home)/[^/\s\x00]+/(?:Desktop|Documents|Downloads|workspaces?)(?:/|\b)", re.I
)
TOKEN_PATTERNS = [
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(rb"AKIA[A-Z0-9]{16}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{24,}"),
]


def audit(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        return ["cannot read tracked paths with git ls-files: " + result.stderr.decode("utf-8", "replace").strip()]
    paths = result.stdout.split(b"\0")
    if paths and paths[-1] == b"":
        paths.pop()
    if len(paths) > MAX_FILES:
        return [f"tracked file count {len(paths)} exceeds safety limit {MAX_FILES}"]

    errors: list[str] = []
    for raw_path in paths:
        path = Path(raw_path.decode("utf-8", "surrogateescape"))
        display = path.as_posix()
        if any(part.lower() in BLOCKED_DIRS for part in path.parts):
            errors.append(f"generated/private directory is tracked: {display}")
        if path.suffix.lower() in BLOCKED_SUFFIXES:
            errors.append(f"compiled/cache file is tracked: {display}")

        try:
            with (root / path).open("rb") as source:
                data = source.read(MAX_CONTENT_BYTES + 1)
        except OSError as exc:
            errors.append(f"cannot inspect tracked file {display}: {exc}")
            continue
        if len(data) > MAX_CONTENT_BYTES:
            errors.append(f"tracked file exceeds content scan limit ({MAX_CONTENT_BYTES} bytes): {display}")
            continue
        if b"\0" in data:  # Binary payloads are still checked by path above.
            continue
        if PRIVATE_PATH.search(data):
            errors.append(f"private desktop/home workspace path found in tracked file: {display}")
        if any(pattern.search(data) for pattern in TOKEN_PATTERNS):
            errors.append(f"credential-like token found in tracked file: {display}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = audit(args.root.resolve())
    if errors:
        print("Source export guard failed:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1
    print("Source export guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
