#!/usr/bin/env python3
"""Report-only release bump dry run.

Lists tracked lines that contain the old version, grouped by category, and
cross-checks the release workflows. Writes nothing, makes no network calls and
never computes checksums.

Usage: python3 scripts/release_dryrun.py --from 0.5.1 --to 0.5.2 [--repo DIR]
"""

import argparse
import re
import subprocess
import sys

# Files whose version strings are not bump targets.
EXCLUDED_NAMES = {"Cargo.lock", "CHANGELOG.md"}
EXCLUDED_PATTERNS = (
    re.compile(r"(^|/)THIRD-PARTY[^/]*\.json$"),
    re.compile(r"(^|/)package-lock\.json$"),
)

SHA256_RE = re.compile(r"\b[0-9a-f]{64}\b")
SHA_HINT_RE = re.compile(r"sha256|checksum", re.IGNORECASE)
SHA_FILES = ("README.md", "site/project.json")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

CATEGORIES = (
    ("manifest", lambda p: p.endswith("Cargo.toml") or p.endswith("tauri.conf.json") or p.endswith("package.json")),
    ("ci-release", lambda p: p.startswith(".github/")),
    ("site", lambda p: p.startswith("site/")),
    ("docs-readme", lambda p: p in ("README.md", "RELEASE.md", "SECURITY.md", "SUPPORT.md") or p.startswith("docs/") or p.startswith("design/")),
    ("tests", lambda p: "/tests/" in "/" + p or p.startswith("tests/")),
    ("source", lambda p: p.startswith("src/") or p.startswith("desktop/") or p.startswith("scripts/")),
    ("vendored-third-party", lambda p: p.startswith("vendor/") or p.startswith("third-party-licenses/")),
)


def categorize(path):
    for name, match in CATEGORIES:
        if match(path):
            return name
    return "other"


def git_grep(repo, old):
    result = subprocess.run(
        ["git", "-C", repo, "grep", "-n", "-F", "--", old],
        capture_output=True,
        text=True,
    )
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        sys.exit("git grep failed: " + result.stderr.strip())
    return result.stdout.splitlines()


def is_excluded(path):
    name = path.rsplit("/", 1)[-1]
    if name in EXCLUDED_NAMES:
        return True
    return any(p.search(path) for p in EXCLUDED_PATTERNS)


def read_tracked(repo, path):
    result = subprocess.run(
        ["git", "-C", repo, "show", ":" + path],
        capture_output=True,
        text=True,
        errors="replace",
    )
    return result.stdout.splitlines() if result.returncode == 0 else []


def main(argv=None):
    parser = argparse.ArgumentParser(description="Report-only release bump dry run.")
    parser.add_argument("--from", dest="old", required=True, help="current version, e.g. 0.5.1")
    parser.add_argument("--to", dest="new", required=True, help="next version, e.g. 0.5.2")
    parser.add_argument("--repo", default=".", help="repository root (default: current directory)")
    args = parser.parse_args(argv)

    for v in (args.old, args.new):
        if not VERSION_RE.match(v):
            sys.exit("version must look like X.Y.Z: " + v)
    if args.old == args.new:
        sys.exit("--from and --to are the same version")

    print("Release dry run: %s -> %s (report only, nothing is written)" % (args.old, args.new))
    print()

    hits = {}
    for line in git_grep(args.repo, args.old):
        path, lineno, text = line.split(":", 2)
        if is_excluded(path):
            continue
        hits.setdefault(categorize(path), []).append((path, lineno, text.strip()))

    total = sum(len(v) for v in hits.values())
    print("Lines containing '%s' (excluding Cargo.lock, THIRD-PARTY*.json, package-lock.json, CHANGELOG.md): %d" % (args.old, total))
    for category in sorted(hits):
        print()
        print("[%s] %d" % (category, len(hits[category])))
        for path, lineno, text in hits[category]:
            print("  %s:%s: %s" % (path, lineno, text[:160]))

    print()
    print("Release workflow cross-check:")
    for wf in (".github/workflows/release.yml", ".github/workflows/ci.yml"):
        lines = read_tracked(args.repo, wf)
        found = [(i + 1, l.strip()) for i, l in enumerate(lines) if args.old in l]
        if not found:
            print("  %s: no hardcoded %s" % (wf, args.old))
        for lineno, text in found:
            print("  %s:%d: hardcoded %s -> change to %s at bump time: %s" % (wf, lineno, args.old, args.new, text[:160]))
    print("  NOTE: release.yml tag guard must match the tag you create (v%s); the tag cannot exist before the owner creates it." % args.new)

    print()
    print("Checksums (MUST NOT be filled until assets exist; take values only from the uploaded release assets):")
    for path in SHA_FILES:
        lines = read_tracked(args.repo, path)
        for i, line in enumerate(lines):
            if SHA256_RE.search(line) or SHA_HINT_RE.search(line):
                print("  %s:%d: MUST NOT be filled until assets exist: %s" % (path, i + 1, line.strip()[:160]))

    print()
    print("Report complete. Exit 0 (report mode).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
