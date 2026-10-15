import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "build-linux-package.py"
SPEC = importlib.util.spec_from_file_location("linux_package", SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def elf_fixture(path: Path, machine: int = 62, elf_class: int = 2) -> Path:
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4:7] = bytes((elf_class, 1, 1))
    header[18:20] = machine.to_bytes(2, "little")
    path.write_bytes(header)
    path.chmod(0o755)
    return path


@unittest.skipUnless(os.name == "posix", "Linux package tests require POSIX executable modes and symlink/mtime semantics")
class LinuxPackageTests(unittest.TestCase):
    def test_packaged_launcher_advertises_startup_notification(self):
        entry = builder.desktop_entry_text()
        self.assertIn("StartupNotify=true", entry)
        self.assertIn("Icon=bytepleat", entry)
        self.assertIn("Exec=/usr/bin/bytepleat-desktop --open -- %F", entry)

    def test_native_loader_dependencies_keep_the_required_libc_floor(self):
        for loader in ("ld-linux-aarch64.so.1", "ld-linux-x86-64.so.2"):
            self.assertEqual(builder.package_dependencies([loader, "libc.so.6"], "2.39"), "libc6 (>= 2.39)")

    def test_accepts_minimal_supported_elf_and_reads_needed_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = elf_fixture(Path(temporary) / "app")
            outputs = [
                " 0x1 (NEEDED) Shared library: [libc.so.6]\n",
                "Version needs section '.gnu.version_r':\n Name: GLIBC_2.9\n Name: GLIBC_2.39\n",
            ]
            with mock.patch.object(builder.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 0, item, "") for item in outputs]):
                machine, needed, glibc_floor = builder.elf_info(executable)
            self.assertEqual(machine, 62)
            self.assertEqual(needed, ["libc.so.6"])
            self.assertEqual(glibc_floor, "2.39")

    def test_glibc_dependency_floor_and_missing_version_needs(self):
        self.assertEqual(builder.package_dependencies(["libc.so.6"], "2.39"), "libc6 (>= 2.39)")
        self.assertEqual(builder.package_dependencies(["libc.so.6"], None), "libc6")
        with self.assertRaisesRegex(ValueError, "invalid GLIBC floor"):
            builder.package_dependencies(["libc.so.6"], "2.x")

    def test_elf_without_glibc_version_needs_has_no_inferred_floor(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = elf_fixture(Path(temporary) / "app")
            outputs = ["", "Version needs section '.gnu.version_r': no GLIBC names\n"]
            with mock.patch.object(builder.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 0, item, "") for item in outputs]):
                _, _, glibc_floor = builder.elf_info(executable)
            self.assertIsNone(glibc_floor)

    def test_refuses_private_glibc_abi(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = elf_fixture(Path(temporary) / "app")
            outputs = ["", "Version needs section '.gnu.version_r':\n Name: GLIBC_2.2.5\n Name: GLIBC_PRIVATE\n"]
            with mock.patch.object(builder.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 0, item, "") for item in outputs]):
                with self.assertRaisesRegex(ValueError, "GLIBC_PRIVATE"):
                    builder.elf_info(executable)

    def test_rejects_symlink_and_target_architecture_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = elf_fixture(root / "app")
            link = root / "link"
            link.symlink_to(executable)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                builder.elf_info(link)
            notices = root / "notices"
            notices.mkdir()
            report = {"schema_version": 1, "target": "aarch64-unknown-linux-gnu", "project": {"version": "0.1.0"}, "packages": [], "runtime_components": []}
            (notices / "THIRD-PARTY.json").write_text(json.dumps(report), encoding="utf-8")
            with mock.patch.object(builder.shutil, "which", return_value="dpkg-deb"), mock.patch.object(
                builder.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")
            ):
                with self.assertRaisesRegex(ValueError, "architecture does not match"):
                    builder.build(executable, "aarch64-unknown-linux-gnu", notices, root / "out.deb", 0)

    def test_rejects_traversal_and_duplicate_package_destination(self):
        with self.assertRaisesRegex(ValueError, "unsafe"):
            builder.safe_relative("../outside", "notice")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_text("fixture", encoding="utf-8")
            stage = root / "stage"
            stage.mkdir()
            seen = set()
            builder.add_file(stage, "usr/share/doc/copy", source, 0o644, 0, seen)
            with self.assertRaisesRegex(ValueError, "collision"):
                builder.add_file(stage, "usr/share/doc/copy", source, 0o644, 0, seen)

    def test_refuses_existing_output_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = elf_fixture(root / "app")
            output = root / "existing.deb"
            output.write_bytes(b"user data")
            with self.assertRaises(FileExistsError):
                builder.build(executable, "x86_64-unknown-linux-gnu", root, output, 0)
            self.assertEqual(output.read_bytes(), b"user data")

    @unittest.skipUnless(shutil.which("dpkg-deb") and shutil.which("readelf"), "requires native Debian packaging tools")
    def test_native_deb_rebuild_is_byte_for_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = elf_fixture(root / "app")
            # A tiny genuine ELF is unnecessary here: readelf reports no dynamic
            # section, while the builder still exercises the actual dpkg-deb path.
            notices = root / "notices"
            notices.mkdir()
            report = {"schema_version": 1, "target": "x86_64-unknown-linux-gnu", "project": {"version": "0.1.0"}, "packages": [], "runtime_components": [], "unresolved_gaps": [], "literal_inventory_complete": True}
            (notices / "THIRD-PARTY.json").write_text(json.dumps(report), encoding="utf-8")
            # readelf may reject a minimal header. Use a patched readelf result,
            # keeping dpkg-deb itself native and observable.
            real_run = subprocess.run

            def run(command, *args, **kwargs):
                if command[0] == builder.ELF_READELF:
                    if command[1] == "-V":
                        return subprocess.CompletedProcess(command, 0, "", "")
                    return subprocess.CompletedProcess(command, 0, "", "")
                return real_run(command, *args, **kwargs)

            first, second = root / "one.deb", root / "two.deb"
            with mock.patch.object(builder.subprocess, "run", side_effect=run):
                builder.build(executable, "x86_64-unknown-linux-gnu", notices, first, 1_700_000_000)
                builder.build(executable, "x86_64-unknown-linux-gnu", notices, second, 1_700_000_000)
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            extracted = root / "extracted"
            extracted.mkdir()
            subprocess.run(["dpkg-deb", "-x", str(first), str(extracted)], check=True)
            desktop_entry = (extracted / "usr/share/applications/bytepleat.desktop").read_text(encoding="utf-8")
            self.assertIn("StartupNotify=true", desktop_entry)

    def test_rejects_wrong_collector_version_and_notice_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            notices = root / "notices"
            notices.mkdir()
            executable = elf_fixture(root / "app")
            report_path = notices / "THIRD-PARTY.json"
            report = {"schema_version": 1, "target": "x86_64-unknown-linux-gnu", "project": {"version": "0.1.0-alpha.0"}, "packages": [], "runtime_components": []}
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "notice report must"):
                builder.build(executable, "x86_64-unknown-linux-gnu", notices, root / "wrong-version.deb", 0)
            report["project"]["version"] = "0.1.0"
            notice = notices / "LICENSE"
            notice.write_text("fixture notice", encoding="utf-8")
            report["packages"] = [{"notices": [{"path": "LICENSE", "sha256": "0" * 64}]}]
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with mock.patch.object(builder.shutil, "which", return_value="dpkg-deb"), mock.patch.object(
                builder.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")
            ):
                with self.assertRaisesRegex(ValueError, "notice content hash mismatch"):
                    builder.build(executable, "x86_64-unknown-linux-gnu", notices, root / "bad-hash.deb", 0)


if __name__ == "__main__":
    unittest.main()
