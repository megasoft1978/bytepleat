#!/usr/bin/env python3
"""Build a deterministic, unsigned local-development Debian desktop package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

VERSION = "0.1.0~alpha.0"
TARGETS = {
    "x86_64-unknown-linux-gnu": ("amd64", 62, 2),
    "aarch64-unknown-linux-gnu": ("arm64", 183, 2),
}
ROOT = Path(__file__).resolve().parents[2]
ELF_READELF = "readelf"
# Tauri's documented Debian/Ubuntu runtime stack. Each optional component is
# emitted only when the supplied ELF actually needs one of its shared objects.
SONAME_PACKAGES = {
    "libgtk-3.so.0": "libgtk-3-0",
    "libayatana-appindicator3.so.1": "libayatana-appindicator3-1",
    "libayatana-ido3-0.4.so.0": "libayatana-ido3-0.4-0",
    "librsvg-2.so.2": "librsvg2-2",
    "libgdk-3.so.0": "libgtk-3-0",
    "libgobject-2.0.so.0": "libglib2.0-0",
    "libglib-2.0.so.0": "libglib2.0-0",
    "libgio-2.0.so.0": "libglib2.0-0",
    "libgmodule-2.0.so.0": "libglib2.0-0",
    "libgdk_pixbuf-2.0.so.0": "libgdk-pixbuf-2.0-0",
    "libcairo.so.2": "libcairo2",
    "libcairo-gobject.so.2": "libcairo2",
    "libpango-1.0.so.0": "libpango-1.0-0",
    "libpangocairo-1.0.so.0": "libpangocairo-1.0-0",
    "libpangoft2-1.0.so.0": "libpangoft2-1.0-0",
    "libatk-1.0.so.0": "libatk1.0-0",
    "libwebkit2gtk-4.1.so.0": "libwebkit2gtk-4.1-0",
    "libjavascriptcoregtk-4.1.so.0": "libjavascriptcoregtk-4.1-0",
    "libsoup-3.0.so.0": "libsoup-3.0-0",
    "libdbus-1.so.3": "libdbus-1-3",
    "libX11.so.6": "libx11-6",
    "libXcomposite.so.1": "libxcomposite1",
    "libXdamage.so.1": "libxdamage1",
    "libXext.so.6": "libxext6",
    "libXfixes.so.3": "libxfixes3",
    "libXrender.so.1": "libxrender1",
    "libXrandr.so.2": "libxrandr2",
    "libXcursor.so.1": "libxcursor1",
    "libXi.so.6": "libxi6",
    "libXinerama.so.1": "libxinerama1",
    "libxkbcommon.so.0": "libxkbcommon0",
    "libfontconfig.so.1": "libfontconfig1",
    "libfreetype.so.6": "libfreetype6",
    "libz.so.1": "zlib1g",
    "libexpat.so.1": "libexpat1",
    "libc.so.6": "libc6",
    "ld-linux-aarch64.so.1": "libc6",
    "ld-linux-x86-64.so.2": "libc6",
    "libgcc_s.so.1": "libgcc-s1",
    "libstdc++.so.6": "libstdc++6",
    "libm.so.6": "libc6",
    "libdl.so.2": "libc6",
    "libpthread.so.0": "libc6",
    "librt.so.1": "libc6",
}


def safe_relative(value: str, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"invalid {label} path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe {label} path: {value!r}")
    return path


def source_file(root: Path, relative: PurePosixPath, label: str) -> Path:
    path = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlink in {label} path: {relative}")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"missing or escaping {label}: {relative}")
    return path


def elf_info(executable: Path) -> tuple[int, list[str], str | None]:
    if executable.is_symlink() or not executable.is_file():
        raise ValueError("--executable must be a regular, non-symlink ELF file")
    mode = executable.stat().st_mode
    if not mode & 0o111:
        raise ValueError("--executable is not marked executable")
    with executable.open("rb") as stream:
        header = stream.read(20)
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[5] != 1:
        raise ValueError("--executable must be a little-endian ELF file")
    elf_class = header[4]
    machine = int.from_bytes(header[18:20], "little")
    if elf_class not in (1, 2):
        raise ValueError("unsupported ELF class")
    try:
        result = subprocess.run([ELF_READELF, "-d", str(executable)], check=True, capture_output=True, text=True)
        versions = subprocess.run([ELF_READELF, "-V", str(executable)], check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ValueError("readelf from GNU binutils is required to inspect ELF dependencies") from exc
    needed = re.findall(r"\(NEEDED\).*?\[(.+?)\]", result.stdout)
    needs_match = re.search(
        r"Version needs section.*?(?=\nVersion .*? section|\Z)", versions.stdout, re.DOTALL
    )
    glibc_versions = set()
    needs_text = needs_match.group(0) if needs_match else ""
    for name in re.findall(r"Name:\s*(\S+)", needs_text):
        if name == "GLIBC_PRIVATE":
            raise ValueError("ELF requires GLIBC_PRIVATE, which is not a public compatible ABI")
        if name.startswith("GLIBC_"):
            version = name.removeprefix("GLIBC_")
            if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version):
                raise ValueError(f"invalid GLIBC symbol version: {name}")
            glibc_versions.add(tuple(int(part) for part in version.split(".")))
    floor = ".".join(map(str, max(glibc_versions))) if glibc_versions else None
    return machine, needed, floor


def package_dependencies(needed: list[str], glibc_floor: str | None = None) -> str:
    packages = set()
    unknown = sorted(set(needed) - SONAME_PACKAGES.keys())
    if unknown:
        raise ValueError("unmapped ELF shared-library dependencies: " + ", ".join(unknown))
    packages.update(SONAME_PACKAGES[name] for name in needed)
    if glibc_floor is not None:
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", glibc_floor):
            raise ValueError(f"invalid GLIBC floor: {glibc_floor}")
        packages.discard("libc6")
        packages.add(f"libc6 (>= {glibc_floor})")
    if "libwebkit2gtk-4.1.so.0" in needed:
        packages.update(("libgtk-3-0", "librsvg2-2"))
    return ", ".join(sorted(packages))


def desktop_entry_text() -> str:
    return (
        "[Desktop Entry]\nType=Application\nName=Bytepleat\nComment=Create and extract archives with Bytepleat\n"
        "Exec=/usr/bin/bytepleat-desktop --open -- %F\nIcon=bytepleat\nTerminal=false\nStartupNotify=true\nCategories=Utility;Archiving;\n"
        "MimeType=application/zip;application/x-7z-compressed;application/gzip;application/zstd;application/x-lz4;\n"
    )


def add_file(stage: Path, destination: str, source: Path, mode: int, epoch: int, seen: set[str]) -> None:
    rel = safe_relative(destination, "package destination").as_posix()
    if any(rel == prior or rel.startswith(prior + "/") or prior.startswith(rel + "/") for prior in seen):
        raise ValueError(f"package path collision: /{rel}")
    seen.add(rel)
    target = stage.joinpath(*PurePosixPath(rel).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target, follow_symlinks=False)
    target.chmod(mode)
    os.utime(target, (epoch, epoch), follow_symlinks=False)


def verify_notice_hash(path: Path, record: dict) -> None:
    expected = record.get("sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError(f"notice record has invalid SHA-256: {record.get('path')}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise ValueError(f"notice content hash mismatch: {record.get('path')}")


def build(executable: Path, target: str, notices_dir: Path, output: Path, epoch: int) -> None:
    if target not in TARGETS:
        raise ValueError(f"unsupported target: {target}")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"refusing to overwrite output: {output}")
    if not output.parent.is_dir():
        raise ValueError("output parent directory must already exist")
    if notices_dir.is_symlink() or not notices_dir.is_dir():
        raise ValueError("--notices-dir must be a real directory")
    notices_dir = notices_dir.resolve()
    report_path = source_file(notices_dir, PurePosixPath("THIRD-PARTY.json"), "notice report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema_version") != 1 or report.get("target") != target or report.get("project", {}).get("version") != "0.1.0":
        raise ValueError("notice report must be schema 1 for this exact target and desktop version")
    inventory = report.get("packages")
    runtime = report.get("runtime_components")
    if not isinstance(inventory, list) or not isinstance(runtime, list):
        raise ValueError("notice report is missing package/runtime inventory")
    machine, needed, glibc_floor = elf_info(executable)
    deb_arch, expected_machine, expected_class = TARGETS[target]
    with executable.open("rb") as stream:
        actual_class = stream.read(5)[4]
    if machine != expected_machine or actual_class != expected_class:
        raise ValueError(f"ELF architecture does not match {target} ({deb_arch})")
    depends = package_dependencies(needed, glibc_floor)
    system_command = shutil.which("dpkg-deb")
    if not system_command:
        raise ValueError("dpkg-deb (from Debian dpkg) is required")
    epoch_text = str(epoch)
    with tempfile.TemporaryDirectory(prefix="bytepleat-deb-", dir=output.parent) as temporary:
        work = Path(temporary)
        stage = work / "root"
        stage.mkdir()
        seen: set[str] = set()
        add_file(stage, "usr/bin/bytepleat-desktop", executable, 0o755, epoch, seen)
        icon = source_file(ROOT, PurePosixPath("desktop/src-tauri/icons/bytepleat.svg"), "application icon")
        add_file(stage, "usr/share/icons/hicolor/scalable/apps/bytepleat.svg", icon, 0o644, epoch, seen)
        launcher = work / "bytepleat.desktop"
        launcher.write_text(desktop_entry_text(), encoding="utf-8")
        add_file(stage, "usr/share/applications/bytepleat.desktop", launcher, 0o644, epoch, seen)

        # Preserve the installer's expected relative layout, enabling explicit
        # per-user setup without any package maintainer script or auto-registration.
        integration_sources = (
            ("desktop/scripts/install-linux-integrations.py", "usr/lib/bytepleat/desktop/scripts/install-linux-integrations.py", 0o755),
            ("desktop/integrations/linux/nautilus/bytepleat_extension.py", "usr/lib/bytepleat/desktop/integrations/linux/nautilus/bytepleat_extension.py", 0o644),
            ("desktop/integrations/linux/nautilus/bytepleat_cli_args.py", "usr/lib/bytepleat/desktop/integrations/linux/nautilus/bytepleat_cli_args.py", 0o644),
        )
        for source_rel, destination, mode in integration_sources:
            source = source_file(ROOT, PurePosixPath(source_rel), "integration asset")
            add_file(stage, destination, source, mode, epoch, seen)
        readme = source_file(ROOT, PurePosixPath("desktop/integrations/linux/thunar/README.md"), "integration documentation")
        add_file(stage, "usr/share/doc/bytepleat-desktop/linux-integrations.md", readme, 0o644, epoch, seen)

        license_file = source_file(ROOT, PurePosixPath("LICENSE"), "project license")
        add_file(stage, "usr/share/doc/bytepleat-desktop/LICENSE", license_file, 0o644, epoch, seen)
        add_file(stage, "usr/share/doc/bytepleat-desktop/THIRD-PARTY.json", report_path, 0o644, epoch, seen)
        notice_destinations: set[str] = set()
        for package in inventory:
            for notice in package.get("notices", []):
                rel = safe_relative(notice.get("path"), "notice")
                src = source_file(notices_dir, rel, "notice")
                verify_notice_hash(src, notice)
                dest = f"usr/share/doc/bytepleat-desktop/{rel.as_posix()}"
                if dest in notice_destinations:
                    raise ValueError(f"duplicate notice reference: {rel}")
                notice_destinations.add(dest)
                add_file(stage, dest, src, 0o644, epoch, seen)
        for component in runtime:
            for notice in component.get("notices", []):
                rel = safe_relative(notice.get("path"), "runtime notice")
                src = source_file(notices_dir, rel, "runtime notice")
                verify_notice_hash(src, notice)
                dest = f"usr/share/doc/bytepleat-desktop/{rel.as_posix()}"
                if dest in notice_destinations:
                    raise ValueError(f"duplicate notice reference: {rel}")
                notice_destinations.add(dest)
                add_file(stage, dest, src, 0o644, epoch, seen)

        control_dir = stage / "DEBIAN"
        control_dir.mkdir()
        control = ["Package: bytepleat-desktop", f"Version: {VERSION}", f"Architecture: {deb_arch}", "Maintainer: Bytepleat development build <noreply@example.invalid>", "Section: utils", "Priority: optional", "Description: Bytepleat desktop alpha (local development package)", " Unsigned local development package; not a released or consumer-ready build."]
        if depends:
            control.append(f"Depends: {depends}")
        control_file = control_dir / "control"
        control_file.write_text("\n".join(control) + "\n", encoding="utf-8")
        control_file.chmod(0o644)
        os.utime(control_file, (epoch, epoch))
        for directory, _, _ in os.walk(stage, topdown=False):
            directory_path = Path(directory)
            directory_path.chmod(0o755)
            os.utime(directory_path, (epoch, epoch))
        temp_deb = work / "package.deb"
        env = os.environ.copy()
        env["SOURCE_DATE_EPOCH"] = epoch_text
        subprocess.run([system_command, "--root-owner-group", "--uniform-compression", "-Zgzip", "-z9", "--build", str(stage), str(temp_deb)], check=True, env=env)
        # Link publication is atomic and fails if another process created output.
        os.link(temp_deb, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--notices-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-date-epoch", type=int, default=os.environ.get("SOURCE_DATE_EPOCH", "0"))
    args = parser.parse_args(argv)
    try:
        if args.source_date_epoch < 0:
            raise ValueError("SOURCE_DATE_EPOCH must be a non-negative integer")
        build(args.executable, args.target, args.notices_dir, args.output, args.source_date_epoch)
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"build-linux-package: {error}", file=sys.stderr)
        return 2
    print(f"Built unsigned development package: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
