"""Regression tests for the tracked source-export guard."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import check_source_export


class SourceExportGuardTests(unittest.TestCase):
    def make_repo(self, root: Path, files: dict[str, bytes]) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        for name, contents in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        subprocess.run(["git", "-C", str(root), "add", "--", *files], check=True)

    def test_clean_tracked_source_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "clean"
            root.mkdir()
            self.make_repo(root, {"src/main.rs": b"fn main() {}\n", "LICENSE": b"MIT\n"})
            self.assertEqual(check_source_export.audit(root), [])

    def test_nested_tracked_release_workspace_target_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dirty"
            root.mkdir()
            self.make_repo(root, {
                "src/main.rs": b"fn main() {}\n",
                "release-workspace/arqlet/target/debug/deps/cache.d": b"binary\0payload",
            })
            errors = check_source_export.audit(root)
            self.assertTrue(any("release-workspace" in error for error in errors), errors)
            self.assertTrue(any(".d" in error for error in errors), errors)

    def test_binary_file_is_still_checked_by_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dirty"
            root.mkdir()
            self.make_repo(root, {"nested/cache.exe": b"\0\xffbinary"})
            self.assertTrue(any("compiled/cache" in error for error in check_source_export.audit(root)))


if __name__ == "__main__":
    unittest.main()
