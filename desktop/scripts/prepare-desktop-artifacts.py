#!/usr/bin/env python3
"""Prepare checksummed, unsigned desktop executables with matching notices.

This tool stages test executables only. It does not build installers, sign files,
or establish that a build is ready for redistribution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys


TARGETS = {
    "aarch64-apple-darwin": ("macOS", "arm64", ".app executable"),
    "x86_64-unknown-linux-gnu": ("Linux", "x86_64", "ELF executable"),
    "x86_64-pc-windows-msvc": ("Windows", "x86_64", "PE executable"),
    "aarch64-pc-windows-msvc": ("Windows", "x86_64", "ARM64 PE executable"),
}
MAX_REPORT_BYTES = 8 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_report_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or "\\" in value or "\x00" in value or ":" in value:
        raise ValueError("notice report contains a non-string notice path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe notice path in report: {value}")
    return path


def checked_source(root: Path, relative: PurePosixPath) -> Path:
    candidate = root.joinpath(*relative.parts)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"missing or unsafe notice file: {relative.as_posix()}")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"notice path escaped its inventory: {relative.as_posix()}")
    return candidate


def inventory_entries(report: dict) -> dict[str, str]:
    entries: dict[str, str] = {}
    for collection_name in ("packages", "runtime_components"):
        collection = report.get(collection_name)
        if not isinstance(collection, list):
            raise ValueError(f"notice report {collection_name} must be a list")
        for component in collection:
            if not isinstance(component, dict) or not isinstance(component.get("notices"), list):
                raise ValueError(f"notice report has an invalid {collection_name} entry")
            for notice in component["notices"]:
                if not isinstance(notice, dict):
                    raise ValueError("notice report contains an invalid notice entry")
                relative = safe_report_path(notice.get("path")).as_posix()
                expected_hash = notice.get("sha256")
                if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
                    raise ValueError(f"notice report has an invalid SHA-256 for {relative}")
                previous = entries.setdefault(relative, expected_hash)
                if previous != expected_hash:
                    raise ValueError(f"notice report has conflicting hashes for {relative}")
    if not entries:
        raise ValueError("notice report contains no literal notice files")
    return entries


def prepare(executable: Path, notices_dir: Path, target: str, host_os: str,
            host_arch: str, revision: str, output_dir: Path) -> dict:
    if target not in TARGETS:
        raise ValueError(f"unsupported desktop target: {target}")
    expected_host_os, expected_target_arch, _artifact_kind = TARGETS[target]
    if host_os != expected_host_os:
        raise ValueError(f"host OS {host_os!r} is not supported for target {target}")
    if target == "aarch64-pc-windows-msvc":
        if host_arch != "x86_64":
            raise ValueError("Windows ARM64 cross-build requires an x86_64 Windows host")
    elif host_arch != expected_target_arch:
        raise ValueError(f"host architecture {host_arch!r} does not match target {target}")
    if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise ValueError("revision must be a full lowercase Git commit hash")
    if executable.is_symlink() or not executable.is_file():
        raise ValueError("executable must be an existing regular, non-symlink file")
    if notices_dir.is_symlink() or not notices_dir.is_dir():
        raise ValueError("notice inventory must be an existing non-symlink directory")
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError(f"refusing to replace existing output directory: {output_dir}")

    report_path = notices_dir / "THIRD-PARTY.json"
    if report_path.is_symlink() or not report_path.is_file() or report_path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("notice inventory must contain a bounded regular THIRD-PARTY.json")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not parse THIRD-PARTY.json: {exc}") from None
    if (not isinstance(report, dict)
            or report.get("schema_version") != 1
            or report.get("generated_by") != "desktop/scripts/collect-desktop-notices.py"
            or report.get("target") != target
            or report.get("cargo_metadata_filter_platform") != target
            or not isinstance(report.get("project"), dict)
            or report["project"].get("name") != "bytepleat-desktop"
            or report["project"].get("version") != "0.1.0"):
        raise ValueError("notice inventory does not match the exact desktop target and source version")
    gaps = report.get("unresolved_gaps")
    if (not isinstance(gaps, list) or gaps
            or report.get("literal_inventory_complete") is not True):
        raise ValueError("notice inventory is incomplete or has unresolved notice gaps")

    files = inventory_entries(report)
    executable_name = "bytepleat-desktop.exe" if target.endswith("windows-msvc") else "bytepleat-desktop"
    if executable.name != executable_name:
        raise ValueError(f"executable filename must be {executable_name} for target {target}")
    reserved = {executable_name, "THIRD-PARTY.json", "artifact-manifest.json", "SHA256SUMS"}
    if reserved.intersection(files):
        raise ValueError("notice inventory collides with a reserved artifact filename")
    sources: dict[str, Path] = {}
    for relative, expected_hash in files.items():
        source = checked_source(notices_dir, PurePosixPath(relative))
        if sha256(source) != expected_hash:
            raise ValueError(f"notice file SHA-256 mismatch: {relative}")
        sources[relative] = source

    output_dir.mkdir(parents=True)
    try:
        staged_executable = output_dir / executable_name
        shutil.copy2(executable, staged_executable, follow_symlinks=False)
        staged_files = [{"path": executable_name, "sha256": sha256(staged_executable), "role": "test-executable"}]
        for relative, source in sorted(sources.items()):
            destination = output_dir.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination, follow_symlinks=False)
            staged_files.append({"path": relative, "sha256": sha256(destination), "role": "third-party-notice"})
        shutil.copyfile(report_path, output_dir / "THIRD-PARTY.json", follow_symlinks=False)
        staged_files.append({"path": "THIRD-PARTY.json", "sha256": sha256(output_dir / "THIRD-PARTY.json"), "role": "notice-inventory"})
        manifest = {
            "schema_version": 1,
            "claim": "Unsigned test executable and matching literal notice inventory; not an installer or consumer release.",
            "artifact_type": "test-executable",
            "installer": False,
            "signed": False,
            "host": {"os": host_os, "architecture": host_arch},
            "target": target,
            "revision": revision,
            "project_version": report["project"]["version"],
            "notice_inventory": {
                "target": target,
                "literal_inventory_complete": True,
                "redistribution_ready": False,
                "legal_clearance": "Not assessed",
            },
            "files": staged_files,
        }
        manifest_path = output_dir / "artifact-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (output_dir / "SHA256SUMS").write_text(
            "".join(f"{item['sha256']}  {item['path']}\n" for item in staged_files), encoding="ascii"
        )
    except BaseException:
        shutil.rmtree(output_dir)
        raise
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--notices-dir", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--host-os", required=True, choices=("macOS", "Linux", "Windows"))
    parser.add_argument("--host-arch", required=True, choices=("arm64", "x86_64"))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare(args.executable, args.notices_dir, args.target, args.host_os,
                       args.host_arch, args.revision, args.output_dir)
    print(json.dumps({"artifact_type": manifest["artifact_type"], "target": manifest["target"],
                      "revision": manifest["revision"], "files": len(manifest["files"])}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"prepare-desktop-artifacts: {exc}", file=sys.stderr)
        raise SystemExit(2)
