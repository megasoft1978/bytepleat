#!/usr/bin/env python3
"""Fetch and verify the public Sprint 3 benchmark inputs outside the repository."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("corpus-manifest.json")
PROJECT_ROOT = REPO
SOURCE_URL = "https://github.com/lz4/lz4/archive/refs/tags/v1.10.0.tar.gz"
LZ4_SHA256 = "fd33f2ea8f797d4d02452e80f1819a472f584471bc7b1fa09c0a17099b5f43f3"
LZ4_BYTES = 1_843_200
MAX_DOWNLOAD = 40 * 1024 * 1024
MAX_EXPANDED = 24 * 1024 * 1024


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def safe_name(name: str) -> PurePosixPath:
    if not isinstance(name, str):
        raise ValueError("archive member path must be a string")
    p = PurePosixPath(name)
    if p.is_absolute() or "\\" in name or not p.parts or any(x in ("", ".", "..") for x in p.parts):
        raise ValueError(f"unsafe upstream member path: {name!r}")
    if p.parts[0] != "lz4-v1.10.0":
        raise ValueError(f"unexpected upstream root: {name!r}")
    return p


def upstream_name(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if p.is_absolute() or "\\" in name or not p.parts or any(x in ("", ".", "..") for x in p.parts):
        raise ValueError(f"unsafe upstream member path: {name!r}")
    if p.parts[0] != "lz4-1.10.0":
        raise ValueError(f"unexpected upstream root: {name!r}")
    return PurePosixPath("lz4-v1.10.0", *p.parts[1:])


def tree(root: Path) -> list[dict]:
    result = []
    for p in sorted(root.rglob("*"), key=lambda x: x.relative_to(root).as_posix().encode("utf-8")):
        if p.is_symlink():
            raise ValueError(f"symlink in extracted source: {p}")
        if p.is_file():
            result.append({"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)})
    return result


def load_manifest() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (manifest.get("schema") != "bytepleat-benchmark-corpus-v1"
            or manifest.get("source_url") != SOURCE_URL
            or manifest.get("derived_ustar", {}).get("bytes") != LZ4_BYTES
            or manifest.get("derived_ustar", {}).get("sha256") != LZ4_SHA256):
        raise ValueError("benchmark corpus pin manifest is invalid")
    return manifest


def validate_file_manifest(files: list[dict]) -> None:
    if not isinstance(files, list) or not files or len(files) > 10_000:
        raise ValueError("prepared file manifest is empty or invalid")
    seen = set()
    total = 0
    for row in files:
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise ValueError("prepared file manifest row has invalid fields")
        path = safe_name(row["path"]).as_posix()
        if path in seen or type(row["bytes"]) is not int or row["bytes"] < 0:
            raise ValueError("prepared file manifest has duplicate paths or invalid sizes")
        total += row["bytes"]
        if total > MAX_EXPANDED:
            raise ValueError("prepared file manifest exceeds 24 MiB expansion limit")
        if not isinstance(row["sha256"], str) or len(row["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in row["sha256"]):
            raise ValueError("prepared file manifest has invalid SHA-256")
        seen.add(path)


def fetch(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "BytepleatPublicBenchmark/1.0"})
    count = 0
    with urllib.request.urlopen(request, timeout=45) as response, dest.open("xb") as out:
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > MAX_DOWNLOAD:
            raise ValueError("upstream download exceeds 40 MiB bound")
        while block := response.read(1 << 20):
            count += len(block)
            if count > MAX_DOWNLOAD:
                raise ValueError("upstream download exceeds 40 MiB bound")
            out.write(block)


def make_lz4_archive(download: Path, archive: Path, extracted: Path,
                     expected_bytes: Optional[int] = LZ4_BYTES,
                     expected_sha256: Optional[str] = LZ4_SHA256) -> list[dict]:
    with tarfile.open(download, "r:gz") as source:
        members = []
        for member in source:
            if member.isdir():
                upstream_name(member.name.rstrip("/"))
                continue
            if not member.isfile():
                continue
            name = upstream_name(member.name)
            if member.size < 0 or member.size > MAX_EXPANDED:
                raise ValueError(f"invalid or oversized member: {member.name}")
            members.append((name, member))
        # Match the original pathlib.Path ordering (component-wise), rather
        # than byte-sorting the rendered POSIX path.
        members.sort(key=lambda pair: tuple(pair[0].parts))
        total = sum(member.size for _, member in members)
        if total > MAX_EXPANDED:
            raise ValueError("expanded LZ4 source exceeds 24 MiB bound")
        with tarfile.open(archive, "w", format=tarfile.USTAR_FORMAT) as out:
            for name, member in members:
                data = source.extractfile(member)
                if data is None:
                    raise ValueError(f"missing regular-file bytes: {member.name}")
                info = tarfile.TarInfo(name.as_posix())
                info.size = member.size
                # The original corpus preparation copied files into a fresh tree
                # with normal 0666 & umask 0022 permissions before making USTAR.
                info.mode = 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                out.addfile(info, data)
    if ((expected_bytes is not None and archive.stat().st_size != expected_bytes)
            or (expected_sha256 is not None and sha(archive) != expected_sha256)):
        raise ValueError("derived deterministic USTAR does not match pinned 1,843,200-byte SHA-256")
    extracted.mkdir()
    with tarfile.open(archive, "r:") as inp:
        for member in inp:
            name = safe_name(member.name)
            target = extracted.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = inp.extractfile(member)
            if stream is None:
                raise ValueError(f"archive member has no file data: {member.name}")
            with target.open("xb") as out:
                shutil.copyfileobj(stream, out)
            target.chmod(member.mode & 0o7777)
    return tree(extracted)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path, help="new external directory for prepared inputs")
    args = ap.parse_args()
    output = args.output.expanduser().resolve()
    if output == PROJECT_ROOT or PROJECT_ROOT in output.parents:
        ap.error("output must be outside the repository")
    if output.exists():
        ap.error(f"refusing to overwrite existing output: {output}")
    manifest = load_manifest()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bytepleat-prepare-", dir=output.parent))
    try:
        downloads = stage / "downloads"
        downloads.mkdir()
        source = downloads / "lz4-v1.10.0.tar.gz"
        fetch(manifest["source_url"], source)
        archive = stage / "lz4-v1.10.0.tar"
        files = make_lz4_archive(source, archive, stage / "source-tree")
        validate_file_manifest(files)
        payload = {"schema": "bytepleat-public-benchmark-prepared-v1", "corpus_manifest_sha256": sha(MANIFEST),
                   "source_url": manifest["source_url"], "revision": manifest["revision"],
                   "license_note": manifest["license_note"],
                   "derived_archive": {"path": "lz4-v1.10.0.tar", "bytes": LZ4_BYTES, "sha256": LZ4_SHA256,
                   "format": "USTAR; component-wise sorted POSIX paths; uid/gid 0; empty uname/gname; mtime 0; normalized file mode 0644"},
                   "files": files}
        (stage / "PREPARED-MANIFEST.json").write_text(json.dumps(payload, indent=2) + "\n")
        os.replace(stage, output)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    print(f"Prepared verified LZ4 tree at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
