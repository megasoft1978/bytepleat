#!/usr/bin/env python3
"""Collect target-specific, literal Cargo and Rust runtime notices for desktop builds."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_RELATIVE = Path("desktop/src-tauri/Cargo.toml")
MAX_FILES = 100_000
MAX_NOTICE_BYTES = 2 * 1024 * 1024
NAMES = {"license", "licence", "copying", "notice", "copyright"}
SKIP_DIRS = {"target", "node_modules", "third-party-licenses", "vendor", "build", "dist", "out", "coverage", ".git", ".cache", "cache", ".next", ".turbo", ".pytest_cache", "__pycache__", "results", "worker", "workers"}


def run_utf8(command: list[str], root: Path, label: str) -> str:
    """Run a tool whose stdout is UTF-8; tolerate arbitrary diagnostic bytes."""
    cp = subprocess.run(command, cwd=root, capture_output=True)
    if cp.returncode:
        stderr = cp.stderr.decode("utf-8", errors="replace")
        raise ValueError(f"{label} failed: {stderr[-2500:]}")
    try:
        return cp.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} returned invalid UTF-8 on stdout at byte {exc.start}") from None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def graph(nodes: dict, root_id: str) -> set[str]:
    found, todo = set(), [root_id]
    while todo:
        pid = todo.pop()
        if pid in found:
            continue
        found.add(pid)
        node = nodes.get(pid)
        if node:
            for edge in node.get("deps", []):
                kinds = edge.get("dep_kinds", [])
                if kinds and not any(k.get("kind") in (None, "build") for k in kinds):
                    continue
                todo.append(edge["pkg"])
    return found


def notice_files(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        return []
    found, visited = [], 0
    root = root.resolve()
    for current, dirs, names in os.walk(root, followlinks=False):
        base = Path(current)
        dirs[:] = sorted(d for d in dirs if d.lower() not in SKIP_DIRS and not (base / d).is_symlink())
        for name in sorted(names):
            visited += 1
            if visited > MAX_FILES:
                raise ValueError(f"notice scan exceeded {MAX_FILES} files: {root}")
            path = base / name
            lower = name.lower()
            if path.is_symlink() or not path.is_file() or not any(lower == n or lower.startswith(n + "-") or lower.startswith(n + ".") for n in NAMES):
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError("notice path escaped package root")
            if path.stat().st_size > MAX_NOTICE_BYTES:
                continue
            found.append(path)
    return found


def safe_copy(src: Path, dst: Path, source_root: Path, output_root: Path) -> None:
    source_root, output_root = source_root.resolve(), output_root.resolve()
    if src.is_symlink() or not src.is_file() or not src.resolve().is_relative_to(source_root):
        raise ValueError(f"unsafe notice source path: {src}")
    # Check existing ancestors before creating anything, including symlinked output parents.
    parent = dst.parent
    while parent != output_root and output_root in parent.parents:
        if parent.is_symlink():
            raise ValueError(f"unsafe notice destination path: {dst}")
        parent = parent.parent
    if dst.is_symlink() or not dst.resolve(strict=False).is_relative_to(output_root):
        raise ValueError(f"unsafe notice destination path: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def safe_relative(value: str, label: str) -> Path:
    rel = Path(value)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts or any(part in ("", ".") for part in rel.parts):
        raise ValueError(f"unsafe {label} path: {value}")
    return rel


def supplemental_records(root: Path) -> dict[tuple[str, str], list[dict]]:
    root = root.resolve()
    catalog_path = root / "desktop/notice-sources.json"
    if not catalog_path.is_file():
        return {}
    if catalog_path.is_symlink() or not catalog_path.resolve().is_relative_to(root):
        raise ValueError("unsafe supplemental catalog path")
    if catalog_path.stat().st_size > MAX_NOTICE_BYTES:
        raise ValueError(f"supplemental catalog exceeds {MAX_NOTICE_BYTES} bytes")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    records: dict[tuple[str, str], list[dict]] = {}
    for item in catalog.get("records", []):
        key = (item.get("name"), item.get("version"))
        if not all(isinstance(part, str) and part for part in key):
            raise ValueError("supplemental notice record needs exact package name and version")
        notices = item.get("notices")
        if not isinstance(notices, list) or not notices:
            raise ValueError(f"supplemental notice record has no notice texts: {key[0]} {key[1]}")
        for notice in notices:
            rel = safe_relative(notice.get("path", ""), "supplemental notice")
            root_rel = rel if rel.parts[0] == "desktop" else Path("desktop") / rel
            src = root / root_rel
            if src.is_symlink() or not src.is_file() or not src.resolve().is_relative_to(root):
                raise ValueError(f"unsafe or missing supplemental notice path: {root_rel.as_posix()}")
            if src.stat().st_size > MAX_NOTICE_BYTES:
                raise ValueError(f"supplemental notice exceeds {MAX_NOTICE_BYTES} bytes: {root_rel.as_posix()}")
            if sha256(src) != notice.get("sha256"):
                raise ValueError(f"supplemental notice hash mismatch: {root_rel.as_posix()}")
        records.setdefault(key, []).extend(notices)
    return records


def catalog_record(root: Path, name: str, version: str) -> dict:
    data = json.loads((root / "desktop/notice-sources.json").read_text(encoding="utf-8"))
    return next((r for r in data.get("records", []) if r.get("name") == name and r.get("version") == version), {})


def local_license_sources(name: str, declared_license: str, package_root: Path, root: Path) -> list[Path]:
    """Return only the exact local package LICENSE; never scan descendants."""
    expected = root / "LICENSE" if name == "bytepleat-desktop-core" else package_root / "LICENSE"
    return [expected] if declared_license == "MIT" and expected.is_file() and not expected.is_symlink() else []


def rust_runtime(root: Path, target: str, out: Path) -> tuple[list[dict], list[dict]]:
    version = run_utf8(["rustc", "--version", "--verbose"], root, "rustc --version --verbose")
    sysroot = Path(run_utf8(["rustc", "--print", "sysroot"], root, "rustc --print sysroot").strip())
    commit = next((line.split(":", 1)[1].strip() for line in version.splitlines() if line.startswith("commit-hash:")), None)
    docroot = sysroot / "share/doc/rust"
    candidates = notice_files(docroot) if docroot.is_dir() else []
    selected = [p for p in candidates if p.name.upper() in {"COPYRIGHT", "LICENSE-MIT", "LICENSE-APACHE"}]
    runtime, gaps = [], []
    if len(selected) < 2 and commit:
        selected = []
        for name in ("COPYRIGHT", "LICENSE-MIT", "LICENSE-APACHE"):
            url = f"https://raw.githubusercontent.com/rust-lang/rust/{commit}/{name}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "bytepleat-desktop-notice-collector"})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = response.read(MAX_NOTICE_BYTES + 1)
                if data and len(data) <= MAX_NOTICE_BYTES:
                    selected.append((name, data, url))
            except (OSError, ValueError):
                continue
    base = out / "third-party-licenses/runtime" / version.splitlines()[0].replace(" ", "-")
    notices = []
    for item in selected:
        if isinstance(item, tuple):
            name, data, provenance = item
            rel = Path(name)
            path = base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        else:
            name = item.name
            rel = item.relative_to(docroot)
            path = base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, path)
            provenance = f"Rust sysroot share/doc/rust/{rel.as_posix()}"
        notices.append({"path": path.relative_to(out).as_posix(), "sha256": sha256(path), "source": provenance})
    if len(notices) < 2:
        gaps.append({"component": "Rust standard library distribution", "gap": "Fewer than two applicable Rust runtime notice texts found in bounded sysroot or matching official Rust commit."})
    runtime.append({"component": "Rust standard library distribution", "toolchain": version.splitlines()[0], "toolchain_commit": commit, "target": target, "notices": notices})
    return runtime, gaps


BUNDLED_UI_FONTS = (
    {"component": "Instrument Sans", "version": "variable (Google Fonts, fetched 2026-10-17)", "license": "OFL-1.1", "copyright": "Copyright 2022 The Instrument Sans Project Authors (https://github.com/Instrument/instrument-sans)", "source_url": "https://github.com/Instrument/instrument-sans", "files": ["InstrumentSans-latin.woff2", "InstrumentSans-latin-ext.woff2"], "notice": "OFL-InstrumentSans.txt"},
    {"component": "JetBrains Mono", "version": "variable (Google Fonts, fetched 2026-10-17)", "license": "OFL-1.1", "copyright": "Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)", "source_url": "https://github.com/JetBrains/JetBrainsMono", "files": ["JetBrainsMono-latin.woff2"], "notice": "OFL-JetBrainsMono.txt"},
)


def bundled_ui_assets(root: Path, out: Path) -> list[dict]:
    """Inventory UI assets embedded in the app binary (desktop/ui). Strict: a missing font or OFL text raises."""
    fonts_dir = root / "desktop/ui/fonts"
    if not (root / "desktop/ui").is_dir():
        return []
    components = []
    for font in BUNDLED_UI_FONTS:
        for name in font["files"]:
            if not (fonts_dir / name).is_file():
                raise ValueError(f"bundled UI font file missing: desktop/ui/fonts/{name}")
        src = fonts_dir / font["notice"]
        if src.is_symlink() or not src.is_file():
            raise ValueError(f"bundled UI font licence text missing: desktop/ui/fonts/{font['notice']}")
        if src.stat().st_size > MAX_NOTICE_BYTES:
            raise ValueError(f"bundled UI font licence text exceeds {MAX_NOTICE_BYTES} bytes: {font['notice']}")
        dst = out / "third-party-licenses/bundled-ui" / font["component"].replace(" ", "-") / font["notice"]
        safe_copy(src, dst, root, out)
        components.append({"component": font["component"], "kind": "bundled-ui-font", "version": font["version"], "license": font["license"], "copyright": font["copyright"], "source_url": font["source_url"], "files": [f"desktop/ui/fonts/{n}" for n in font["files"]], "notices": [{"path": dst.relative_to(out).as_posix(), "sha256": sha256(dst), "source_relative_path": f"desktop/ui/fonts/{font['notice']}", "source": "desktop/ui/fonts"}]})
    return components


def collect(target: str, out: Path, root: Path = ROOT) -> dict:
    root = root.resolve()
    manifest = root / MANIFEST_RELATIVE
    if out.exists() and any(out.iterdir()):
        raise ValueError("output directory must be absent or empty")
    cp = subprocess.run(["cargo", "metadata", "--locked", "--format-version", "1", "--manifest-path", str(manifest), "--filter-platform", target], cwd=root, capture_output=True)
    if cp.returncode:
        stderr = cp.stderr.decode("utf-8", errors="replace")
        raise ValueError("cargo metadata failed: " + stderr[-2500:])
    try:
        meta = json.loads(cp.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cargo metadata returned invalid UTF-8 JSON: {exc}") from None
    packages = {p["id"]: p for p in meta["packages"]}
    nodes = {n["id"]: n for n in meta["resolve"]["nodes"]}
    desktop_root = [p["id"] for p in meta["packages"] if p["name"] == "bytepleat-desktop" and Path(p["manifest_path"]).resolve() == manifest.resolve()]
    if len(desktop_root) != 1:
        raise ValueError("could not identify unique desktop manifest root")
    ids = graph(nodes, desktop_root[0]) - {desktop_root[0]}
    catalog = json.loads((root / "THIRD-PARTY.json").read_text(encoding="utf-8"))
    reviewed = {(p["name"], p["version"]): p for p in catalog.get("packages", [])}
    supplemental = supplemental_records(root)
    out.mkdir(parents=True, exist_ok=True)
    result, gaps = [], []
    for pid in sorted(ids, key=lambda x: (packages[x]["name"].casefold(), packages[x]["version"], x)):
        pkg = packages[pid]
        records = []
        local_roots = {"bytepleat": root, "bytepleat-desktop-core": root / "desktop/core"}
        if pkg["name"] in local_roots:
            expected = local_roots[pkg["name"]].resolve()
            package_root = Path(pkg["manifest_path"]).parent.resolve()
            if package_root != expected:
                raise ValueError(f"unexpected local package root for {pkg['name']}")
            # Local workspace packages never fall back to recursive dependency scans.
            srcs = local_license_sources(pkg["name"], pkg.get("license"), expected, root)
            for src in srcs:
                rel = Path("LICENSE")
                dst = out / "third-party-licenses" / f"{pkg['name']}-{pkg['version']}" / rel
                safe_copy(src, dst, root, out)
                records.append({"path": dst.relative_to(out).as_posix(), "sha256": sha256(dst), "source_relative_path": "LICENSE", "source": "local-package-root"})
        prior = None if pkg["name"] in local_roots else reviewed.get((pkg["name"], pkg["version"]))
        if prior:
            for record in prior.get("notices", []) + prior.get("vendored_component_notices", []):
                rel = Path(record["path"])
                if rel.is_absolute() or ".." in rel.parts:
                    raise ValueError(f"unsafe reviewed notice path: {record['path']}")
                src = root / rel
                if not src.is_file() or src.is_symlink() or not src.resolve().is_relative_to(root) or sha256(src) != record.get("sha256"):
                    raise ValueError(f"reviewed notice missing or hash mismatch: {record['path']}")
                dst = out / record["path"]
                safe_copy(src, dst, root, out)
                records.append({"path": record["path"], "sha256": record["sha256"], "source_relative_path": record.get("source_relative_path"), "source": "THIRD-PARTY.json"})
        elif not records and pkg["name"] not in local_roots:
            package_root = Path(pkg["manifest_path"]).parent.resolve()
            srcs = notice_files(package_root)
            for src in srcs:
                rel = Path("LICENSE") if pkg["name"] == "bytepleat-desktop-core" else src.relative_to(package_root)
                dst = out / "third-party-licenses" / f"{pkg['name']}-{pkg['version']}" / rel
                source_root = root if pkg["name"] == "bytepleat-desktop-core" else package_root
                safe_copy(src, dst, source_root, out)
                source_rel = "LICENSE" if pkg["name"] == "bytepleat-desktop-core" else rel.as_posix()
                records.append({"path": dst.relative_to(out).as_posix(), "sha256": sha256(dst), "source_relative_path": source_rel, "source": source_rel})
        for record in supplemental.get((pkg["name"], pkg["version"]), []):
            rel = safe_relative(record["path"], "supplemental notice")
            if rel.parts[0] != "desktop":
                rel = Path("desktop") / rel
            src = root / rel
            notice_name = safe_relative(record.get("license", src.name), "supplemental notice name")
            if len(notice_name.parts) != 1:
                raise ValueError(f"unsafe supplemental notice name: {notice_name}")
            dst_rel = Path("third-party-licenses") / f"{pkg['name']}-{pkg['version']}" / notice_name
            if dst_rel.is_absolute() or ".." in dst_rel.parts:
                raise ValueError(f"unsafe supplemental output path: {dst_rel}")
            dst = out / dst_rel
            safe_copy(src, dst, root, out)
            records.append({"path": dst.relative_to(out).as_posix(), "sha256": sha256(dst), "source_relative_path": rel.as_posix(), "source_url": record.get("source_url"), "source": "desktop/notice-sources.json", "license": record.get("license")})
        entry = {"name": pkg["name"], "version": pkg["version"], "declared_license": pkg.get("license"), "cargo_source": pkg.get("source"), "repository": pkg.get("repository"), "notices": records}
        supplemental_items = supplemental.get((pkg["name"], pkg["version"]), [])
        if supplemental_items:
            provenance = catalog_record(root, pkg["name"], pkg["version"])
            for key in ("pinned_git_sha", "source_mapping_status", "mapping_note", "mapping_source_url", "selected_license"):
                if key in provenance:
                    entry[key] = provenance[key]
            finding = provenance.get("source_finding")
            if finding:
                entry["source_findings"] = [finding]
                gaps.append({"package": pkg["name"], "version": pkg["version"], "source_finding": finding})
        if not entry["declared_license"]:
            gaps.append({"package": pkg["name"], "version": pkg["version"], "gap": "Cargo metadata has no declared license string."})
        if not records:
            gaps.append({"package": pkg["name"], "version": pkg["version"], "gap": "No literal notice text found in reviewed catalog or bounded exact Cargo package root."})
        if pkg["name"] in local_roots and pkg.get("license") == "MIT" and not records:
            gaps.append({"package": pkg["name"], "version": pkg["version"], "gap": "Local package LICENSE is missing; local package roots are not scanned recursively."})
        result.append(entry)
    runtime, runtime_gaps = rust_runtime(root, target, out)
    gaps.extend(runtime_gaps)
    runtime = runtime + bundled_ui_assets(root, out)
    systems = {"aarch64-apple-darwin": "macOS frameworks and system libraries are provided by macOS; WebView is the OS-provided WKWebView. No OS libraries are bundled here.", "x86_64-pc-windows-msvc": "Windows system libraries and WebView2 runtime are platform prerequisites; the MSVC toolchain/redistributable may be required. They are not inventoried as Cargo packages.", "x86_64-unknown-linux-gnu": "GNU/Linux system libraries and a supported WebKitGTK/WebView runtime are platform prerequisites; they are not Cargo packages."}
    report = {"schema_version": 1, "generated_by": "desktop/scripts/collect-desktop-notices.py", "project": {"name": "bytepleat-desktop", "version": packages[desktop_root[0]]["version"]}, "target": target, "cargo_metadata_filter_platform": target, "cargo_lock_sha256": sha256(manifest.parent / "Cargo.lock"), "package_count": len(result), "notice_file_count": sum(len(p["notices"]) for p in result) + sum(len(c["notices"]) for c in runtime), "packages": result, "runtime_components": runtime, "platform_prerequisites": {"status": "not bundled; verify for each installer", "description": systems.get(target, "Target operating system libraries and WebView/toolchain prerequisites are not Cargo packages.")}, "unresolved_gaps": gaps, "literal_inventory_complete": not gaps, "platform_qa": "Not assessed by literal notice inventory; verify each installer and target independently.", "redistribution_ready": False, "legal_clearance": "Not assessed; literal inventory and declared metadata do not constitute legal clearance."}
    (out / "THIRD-PARTY.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.target, args.output_dir)
    print(json.dumps({"target": args.target, "packages": report["package_count"], "notice_files": report["notice_file_count"], "unresolved_gaps": len(report["unresolved_gaps"])}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"collect-desktop-notices: {exc}", file=sys.stderr)
        raise SystemExit(2)
