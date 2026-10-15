import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "collect-desktop-notices.py"
SPEC = importlib.util.spec_from_file_location("desktop_notices", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class GraphTests(unittest.TestCase):
    def test_release_walk_includes_normal_and_build_but_excludes_dev_only(self):
        nodes = {
            "root": {"deps": [
                {"pkg": "normal", "dep_kinds": [{"kind": None}]},
                {"pkg": "build", "dep_kinds": [{"kind": "build"}]},
                {"pkg": "dev", "dep_kinds": [{"kind": "dev"}]},
            ]},
            "normal": {"deps": [{"pkg": "transitive", "dep_kinds": [{"kind": None}]}]},
            "build": {"deps": []}, "dev": {"deps": []}, "transitive": {"deps": []},
        }
        self.assertEqual(module.graph(nodes, "root"), {"root", "normal", "build", "transitive"})


class ToolOutputEncodingTests(unittest.TestCase):
    def test_tool_stdout_is_utf8_independent_of_locale_and_stderr_is_replace_decoded(self):
        source = "import sys; sys.stdout.buffer.write('{\"name\":\"日本語\"}'.encode('utf-8')); sys.stderr.buffer.write(b'warning \\x81')"
        output = module.run_utf8([sys.executable, "-c", source], Path.cwd(), "encoding fixture")
        self.assertEqual(json.loads(output), {"name": "日本語"})

    def test_tool_failure_reports_bounded_replacement_decoded_stderr(self):
        source = "import sys; sys.stderr.buffer.write(b'bad \\x81'); sys.exit(3)"
        with self.assertRaisesRegex(ValueError, "encoding fixture failed: bad \\ufffd"):
            module.run_utf8([sys.executable, "-c", source], Path.cwd(), "encoding fixture")


class NoticeScanTests(unittest.TestCase):
    def test_scan_keeps_literal_notice_and_ignores_symlinks_and_large_content(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pkg"
            root.mkdir()
            (root / "LICENSE-MIT").write_text("license")
            (root / "readme.txt").write_text("not a notice")
            outside = Path(temp) / "outside"
            outside.write_text("external")
            (root / "COPYRIGHT").symlink_to(outside)
            self.assertEqual([p.name for p in module.notice_files(root)], ["LICENSE-MIT"])

    def test_symlinked_root_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            real = base / "real"
            real.mkdir()
            (real / "LICENSE").write_text("x")
            alias = base / "alias"
            alias.symlink_to(real)
            self.assertEqual(module.notice_files(alias), [])

    def test_generated_dependency_inventory_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pkg"
            nested = root / "target/node_modules/third-party-licenses/desktop"
            nested.mkdir(parents=True)
            (nested / "LICENSE").write_text("irrelevant")
            (root / "LICENSE-MIT").write_text("applicable")
            self.assertEqual([p.relative_to(root.resolve()).as_posix() for p in module.notice_files(root)], ["LICENSE-MIT"])

    def test_scan_bound_raises_instead_of_returning_partial_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("one", "two"):
                (root / name).write_text("x")
            old = module.MAX_FILES
            module.MAX_FILES = 1
            try:
                with self.assertRaisesRegex(ValueError, "exceeded 1 files"):
                    module.notice_files(root)
            finally:
                module.MAX_FILES = old

    def test_safe_copy_rejects_source_traversal_and_destination_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source_root, output_root = base / "source", base / "out"
            source_root.mkdir()
            output_root.mkdir()
            source = source_root / "LICENSE"
            source.write_text("text")
            with self.assertRaises(ValueError):
                module.safe_copy(base / "outside-source", output_root / "copied", source_root, output_root)
            outside = base / "outside"
            outside.mkdir()
            (output_root / "escape").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                module.safe_copy(source, output_root / "escape/copied", source_root, output_root)


class SupplementalCatalogTests(unittest.TestCase):
    def make_catalog(self, root: Path, *, path="desktop/notice-sources/NOTICE", version="1.2.3", digest=None):
        notice = root / "desktop/notice-sources/NOTICE"
        notice.parent.mkdir(parents=True, exist_ok=True)
        notice.write_text("upstream notice")
        record = {"license": "NOTICE", "path": path, "sha256": digest if digest is not None else module.sha256(notice), "source_url": "https://example.invalid/NOTICE"}
        (root / "desktop").mkdir(exist_ok=True)
        (root / "desktop/notice-sources.json").write_text(__import__("json").dumps({"records": [{"name": "sample", "version": version, "notices": [record]}]}))

    def test_supplemental_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_catalog(root, digest="0" * 64)
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                module.supplemental_records(root)

    def test_supplemental_version_is_an_exact_inventory_key(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_catalog(root)
            records = module.supplemental_records(root)
            self.assertIn(("sample", "1.2.3"), records)
            self.assertNotIn(("sample", "1.2.4"), records)

    def test_supplemental_unsafe_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_catalog(root, path="../NOTICE")
            with self.assertRaisesRegex(ValueError, "unsafe supplemental notice path"):
                module.supplemental_records(root)

    def test_supplemental_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_catalog(root)
            outside = root / "outside"
            outside.write_text("outside")
            notice = root / "desktop/notice-sources/NOTICE"
            notice.unlink()
            notice.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "unsafe or missing"):
                module.supplemental_records(root)

    def test_supplemental_notice_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_catalog(root)
            old = module.MAX_NOTICE_BYTES
            module.MAX_NOTICE_BYTES = 2
            try:
                with self.assertRaisesRegex(ValueError, "exceeds 2 bytes"):
                    module.supplemental_records(root)
            finally:
                module.MAX_NOTICE_BYTES = old

    def test_catalog_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_catalog(root)
            old = module.MAX_NOTICE_BYTES
            module.MAX_NOTICE_BYTES = 10
            try:
                with self.assertRaisesRegex(ValueError, "supplemental catalog exceeds"):
                    module.supplemental_records(root)
            finally:
                module.MAX_NOTICE_BYTES = old

    def test_catalog_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_catalog(root)
            catalog = root / "desktop/notice-sources.json"
            catalog.unlink()
            outside = root / "catalog-outside.json"
            outside.write_text('{"records": []}')
            catalog.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "unsafe supplemental catalog"):
                module.supplemental_records(root)

    def test_local_missing_license_does_not_scan_recursive_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "cache/LICENSE").parent.mkdir(parents=True)
            (root / "cache/LICENSE").write_text("unrelated")
            self.assertEqual(module.local_license_sources("bytepleat", "MIT", root, root), [])

    def test_objc2_source_findings_and_shared_mit_mapping_are_structured(self):
        root = SCRIPT.parents[2]
        records = module.supplemental_records(root)
        for key in (("objc2", "0.6.5"), ("block2", "0.6.2"), ("objc2-encode", "4.1.0")):
            licenses = {n["license"]: n for n in records[key]}
            self.assertIn("MIT", licenses)
            self.assertIn("source-mapping", licenses)
            self.assertEqual(module.catalog_record(root, *key)["selected_license"], "MIT")
            self.assertEqual(licenses["source-mapping"]["sha256"], module.sha256(root / "desktop/notice-sources/objc2-LICENSE.md"))
            item = module.catalog_record(root, *key)
            finding = item["source_finding"]
            self.assertEqual((finding["name"], finding["version"]), key)
            self.assertEqual(finding["pinned_git_sha"], item["pinned_git_sha"])
            self.assertIn("generic copyright", finding["mapping_note"])
            self.assertNotIn("Copyright (c)", finding["mapping_note"])

    def test_objc2_exception_helper_mapping_status_matches_manifest_mapping(self):
        root = SCRIPT.parents[2]
        item = module.catalog_record(root, "objc2-exception-helper", "0.1.1")
        self.assertEqual(item["source_mapping_status"], "verified_source_mapping")

    def test_objc2_alternative_branch_does_not_bundle_zlib_or_apache_text(self):
        root = SCRIPT.parents[2]
        records = module.supplemental_records(root)
        for key in (("dispatch2", "0.3.1"), ("objc2-exception-helper", "0.1.1")):
            licenses = {n["license"] for n in records[key]}
            self.assertIn("MIT", licenses)
            self.assertNotIn("Zlib", licenses)
            self.assertNotIn("Apache-2.0", licenses)

    def test_source_finding_propagates_to_release_entry_and_unresolved_gaps(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "desktop/src-tauri/Cargo.toml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("[package]\nname='sample-root'\n")
            (manifest.parent / "Cargo.lock").write_text("lock")
            package_manifest = root / "registry/sample/Cargo.toml"
            package_manifest.parent.mkdir(parents=True)
            package_manifest.write_text("[package]\nname='sample'\n")
            (root / "THIRD-PARTY.json").write_text('{"packages": []}')
            notice = root / "desktop/notice-sources/NOTICE"
            notice.parent.mkdir(parents=True)
            notice.write_text("canonical terms")
            finding = {"name": "sample", "version": "1.0.0", "repository": "https://example.invalid/sample", "pinned_git_sha": "abc123", "source_mapping_status": "verified_with_gap", "mapping_note": "Generic placeholder; upstream attribution unavailable."}
            catalog = {"records": [{"name": "sample", "version": "1.0.0", "notices": [{"license": "MIT", "path": "notice-sources/NOTICE", "sha256": module.sha256(notice)}], "repository": finding["repository"], "pinned_git_sha": finding["pinned_git_sha"], "source_mapping_status": finding["source_mapping_status"], "mapping_note": finding["mapping_note"], "source_finding": finding}]}
            (root / "desktop/notice-sources.json").write_text(json.dumps(catalog))
            metadata = {"packages": [{"id": "root", "name": "bytepleat-desktop", "version": "1.0.0", "manifest_path": str(manifest), "license": "MIT"}, {"id": "sample-id", "name": "sample", "version": "1.0.0", "manifest_path": str(package_manifest), "license": "MIT", "source": "registry+https://example.invalid", "repository": finding["repository"]}], "resolve": {"nodes": [{"id": "root", "deps": [{"pkg": "sample-id", "dep_kinds": [{"kind": None}]}]}, {"id": "sample-id", "deps": []}]}}
            metadata["encoding_probe"] = "日本語"
            fake_process = type("Result", (), {"returncode": 0, "stdout": json.dumps(metadata, ensure_ascii=False).encode("utf-8"), "stderr": b""})()
            with patch.object(module.subprocess, "run", return_value=fake_process), patch.object(module, "rust_runtime", return_value=([], [])):
                report = module.collect("aarch64-apple-darwin", root / "out", root)
            entry = next(p for p in report["packages"] if p["name"] == "sample")
            self.assertEqual(entry["source_findings"], [finding])
            self.assertEqual(entry["source_mapping_status"], "verified_with_gap")
            self.assertEqual(report["unresolved_gaps"][0]["source_finding"], finding)
            self.assertFalse(report["literal_inventory_complete"])


if __name__ == "__main__":
    unittest.main()
