import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

import prepare_public


class PreparationFixtureTests(unittest.TestCase):
    def test_member_path_policy(self):
        self.assertEqual(prepare_public.safe_name("lz4-v1.10.0/lib/lz4.c").as_posix(), "lz4-v1.10.0/lib/lz4.c")
        self.assertEqual(prepare_public.upstream_name("lz4-1.10.0/lib/lz4.c").as_posix(), "lz4-v1.10.0/lib/lz4.c")
        for value in ("../escape", "/absolute", "lz4-v1.10.0/../../escape", "lz4-v1.10.0\\escape", "other-root/file"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prepare_public.safe_name(value)

    def test_manifest_hashes_generated_fixture_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nested").mkdir()
            sample = root / "nested" / "sample.txt"
            sample.write_bytes(b"generated fixture only\n")
            expected = hashlib.sha256(sample.read_bytes()).hexdigest()
            self.assertEqual(prepare_public.tree(root), [{"path": "nested/sample.txt", "bytes": 23, "sha256": expected}])

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "target").write_text("fixture")
            (root / "link").symlink_to(root / "target")
            with self.assertRaisesRegex(ValueError, "symlink"):
                prepare_public.tree(root)

    def test_prepared_manifest_validation(self):
        good = [{"path": "lz4-v1.10.0/a.c", "bytes": 2, "sha256": hashlib.sha256(b"a\n").hexdigest()}]
        prepare_public.validate_file_manifest(good)
        for invalid in ([], good + good,
                        [{"path": "../escape", "bytes": 1, "sha256": "0" * 64}],
                        [{"path": None, "bytes": 1, "sha256": "0" * 64}],
                        [{"path": "lz4-v1.10.0/a.c", "bytes": True, "sha256": "0" * 64}],
                        [{"path": "lz4-v1.10.0/a.c", "bytes": 1, "sha256": "z" * 64}]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                prepare_public.validate_file_manifest(invalid)

    def test_deterministic_ustar_from_generated_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.tar.gz"
            with tarfile.open(source, "w:gz") as archive:
                for name, content, mode in (("lz4-1.10.0/fullbench/file.c", b"f\n", 0o755), ("lz4-1.10.0/fullbench-dll/file.c", b"d\n", 0o644), ("lz4-1.10.0/a.c", b"a\n", 0o644)):
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    info.mode = mode
                    archive.addfile(info, io.BytesIO(content))
            first = root / "first.tar"
            second = root / "second.tar"
            one = prepare_public.make_lz4_archive(source, first, root / "one", None, None)
            two = prepare_public.make_lz4_archive(source, second, root / "two", None, None)
            self.assertEqual(prepare_public.sha(first), prepare_public.sha(second))
            self.assertEqual(one, two)
            self.assertEqual([x["path"] for x in one], ["lz4-v1.10.0/a.c", "lz4-v1.10.0/fullbench-dll/file.c", "lz4-v1.10.0/fullbench/file.c"])
            self.assertEqual(one, [
                {"path": "lz4-v1.10.0/a.c", "bytes": 2, "sha256": hashlib.sha256(b"a\n").hexdigest()},
                {"path": "lz4-v1.10.0/fullbench-dll/file.c", "bytes": 2, "sha256": hashlib.sha256(b"d\n").hexdigest()},
                {"path": "lz4-v1.10.0/fullbench/file.c", "bytes": 2, "sha256": hashlib.sha256(b"f\n").hexdigest()},
            ])
            with tarfile.open(first, "r:") as archive:
                self.assertEqual({member.mode for member in archive}, {0o644})


if __name__ == "__main__":
    unittest.main()
