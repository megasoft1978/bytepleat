import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "prepare-desktop-artifacts.py"
SPEC = importlib.util.spec_from_file_location("desktop_artifacts", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class DesktopArtifactPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.executable = self.root / "bytepleat-desktop"
        self.executable.write_bytes(b"unsigned test executable")
        self.notices = self.root / "notices"
        (self.notices / "third-party-licenses").mkdir(parents=True)
        self.literal = self.notices / "third-party-licenses" / "LICENSE"
        self.literal.write_text("literal license terms\n", encoding="utf-8")
        report = {
            "schema_version": 1,
            "generated_by": "desktop/scripts/collect-desktop-notices.py",
            "project": {"name": "bytepleat-desktop", "version": "0.1.0"},
            "target": "x86_64-unknown-linux-gnu",
            "cargo_metadata_filter_platform": "x86_64-unknown-linux-gnu",
            "packages": [{"name": "fixture", "notices": [{
                "path": "third-party-licenses/LICENSE",
                "sha256": hashlib.sha256(self.literal.read_bytes()).hexdigest(),
            }]}],
            "runtime_components": [],
            "unresolved_gaps": [],
            "literal_inventory_complete": True,
            "redistribution_ready": False,
        }
        self.report_path = self.notices / "THIRD-PARTY.json"
        self.report_path.write_text(json.dumps(report), encoding="utf-8")
        self.output = self.root / "prepared"

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self):
        return module.prepare(
            self.executable, self.notices, "x86_64-unknown-linux-gnu", "Linux",
            "x86_64", "a" * 40, self.output,
        )

    def test_stages_executable_matching_inventory_manifest_and_checksums(self):
        manifest = self.prepare()
        self.assertFalse(manifest["installer"])
        self.assertFalse(manifest["signed"])
        self.assertEqual(manifest["revision"], "a" * 40)
        self.assertEqual(manifest["notice_inventory"]["redistribution_ready"], False)
        self.assertEqual((self.output / "third-party-licenses/LICENSE").read_text(), "literal license terms\n")
        lines = (self.output / "SHA256SUMS").read_text().splitlines()
        self.assertIn(f"{hashlib.sha256((self.output / 'bytepleat-desktop').read_bytes()).hexdigest()}  bytepleat-desktop", lines)
        self.assertEqual(json.loads((self.output / "artifact-manifest.json").read_text()), manifest)

    @unittest.skipUnless(os.name == "posix", "executable mode bits are only meaningful on POSIX hosts")
    def test_executable_mode_survives_staging_and_tar_extraction(self):
        self.executable.chmod(0o755)
        self.prepare()
        staged = self.output / "bytepleat-desktop"
        self.assertTrue(staged.stat().st_mode & stat.S_IXUSR)

        archive = self.root / "prepared.tar.gz"
        extracted = self.root / "extracted"
        extracted.mkdir()
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(self.output, arcname=".")
        with tarfile.open(archive, "r:gz") as bundle:
            member = bundle.getmember("./bytepleat-desktop")
            if hasattr(tarfile, "data_filter"):
                bundle.extract(member, extracted, filter="data")
            else:
                bundle.extract(member, extracted)
        unpacked = extracted / "bytepleat-desktop"
        self.assertTrue(unpacked.stat().st_mode & stat.S_IXUSR)
        self.assertEqual(unpacked.read_bytes(), self.executable.read_bytes())

    def test_rejects_unsupported_packaging_target(self):
        with self.assertRaisesRegex(ValueError, "unsupported desktop target"):
            module.prepare(self.executable, self.notices, "x86_64-unknown-freebsd", "Linux", "x86_64", "a" * 40, self.output)

    def test_rejects_host_target_mismatch(self):
        with self.assertRaisesRegex(ValueError, "host OS"):
            module.prepare(self.executable, self.notices, "x86_64-unknown-linux-gnu", "Windows", "x86_64", "a" * 40, self.output)

    def test_rejects_missing_inventory(self):
        self.report_path.unlink()
        with self.assertRaisesRegex(ValueError, "THIRD-PARTY.json"):
            self.prepare()

    def test_rejects_missing_or_hash_mismatched_literal_notice(self):
        self.literal.write_text("changed license terms\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.prepare()
        self.literal.unlink()
        with self.assertRaisesRegex(ValueError, "missing or unsafe notice file"):
            self.prepare()

    def test_rejects_unresolved_notice_gaps(self):
        report = json.loads(self.report_path.read_text())
        report["unresolved_gaps"] = [{"component": "fixture", "gap": "missing terms"}]
        report["literal_inventory_complete"] = False
        self.report_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "incomplete or has unresolved"):
            self.prepare()

    def test_rejects_traversal_and_symlink_notice_paths(self):
        report = json.loads(self.report_path.read_text())
        report["packages"][0]["notices"][0]["path"] = "../outside"
        self.report_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsafe notice path"):
            self.prepare()

        report["packages"][0]["notices"][0]["path"] = "third-party-licenses/LINK"
        self.report_path.write_text(json.dumps(report), encoding="utf-8")
        outside = self.root / "outside"
        outside.write_text("external", encoding="utf-8")
        (self.notices / "third-party-licenses" / "LINK").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "missing or unsafe notice file"):
            self.prepare()

    def test_refuses_to_replace_output_directory(self):
        self.output.mkdir()
        sentinel = self.output / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "refusing to replace"):
            self.prepare()
        self.assertEqual(sentinel.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
