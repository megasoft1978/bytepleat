import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "release_dryrun.py"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class ReleaseDryRunTests(unittest.TestCase):
    def make_fixture(self, root):
        git(root, "init", "-q")
        (root / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.5.1"\n')
        (root / "Cargo.lock").write_text('version = "0.5.1"\n')
        (root / "CHANGELOG.md").write_text("## 0.5.1 history\n")
        (root / "README.md").write_text("Download 0.5.1 here\n")
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "release.yml").write_text('test "$RELEASE_TAG" = v0.5.1\n')
        (workflows / "ci.yml").write_text("--version 0.5.1\n")
        git(root, "add", "-A")

    def run_script(self, repo):
        out = io.StringIO()
        with redirect_stdout(out):
            import importlib.util

            spec = importlib.util.spec_from_file_location("release_dryrun", SCRIPT)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            code = module.main(["--from", "0.5.1", "--to", "0.5.2", "--repo", str(repo)])
        return code, out.getvalue()

    def test_finds_old_version_lines_without_writing_or_exiting_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(root)
            before = sorted(p.relative_to(root) for p in root.rglob("*") if ".git" not in p.parts)
            before_text = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}

            code, out = self.run_script(root)

            self.assertEqual(code, 0)
            self.assertIn("Cargo.toml:3:", out)
            self.assertIn("README.md:1:", out)
            self.assertIn("MUST NOT be filled until assets exist", out)
            self.assertIn("v0.5.1", out)
            # Lockfile and changelog history are excluded from the bump list.
            self.assertNotIn("Cargo.lock:1:", out)
            self.assertNotIn("CHANGELOG.md:1:", out)
            # Report only: no file added, removed or changed.
            after = sorted(p.relative_to(root) for p in root.rglob("*") if ".git" not in p.parts)
            after_text = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
            self.assertEqual(before, after)
            self.assertEqual(before_text, after_text)

    def test_subprocess_entrypoint_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(root)
            result = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), "--from", "0.5.1", "--to", "0.5.2", "--repo", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Release dry run: 0.5.1 -> 0.5.2", result.stdout)

    def test_rejects_bad_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), "--from", "0.5", "--to", "0.5.2", "--repo", tmp],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
