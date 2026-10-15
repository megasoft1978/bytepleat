import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReleaseInstructionsTests(unittest.TestCase):
    def test_windows_checksum_example_accepts_the_current_release_asset(self):
        version = tomllib.loads((ROOT / "Cargo.toml").read_text())["package"]["version"]
        asset_expected = f"bytepleat-{version}-x86_64-pc-windows-msvc.zip"
        release = (ROOT / "RELEASE.md").read_text()
        section = re.search(r"Windows PowerShell.*?```powershell\n(.*?)```", release, re.S)
        self.assertIsNotNone(section, "Windows PowerShell checksum example is missing")
        code = section.group(1)

        asset = re.search(r"^\$asset = '([^']+)'$", code, re.M)
        self.assertIsNotNone(asset, "Windows checksum example must name its ZIP")
        self.assertEqual(asset.group(1), asset_expected)

        pattern = re.search(r"-notmatch '([^']+)'", code)
        self.assertIsNotNone(pattern, "Windows checksum example must validate the sidecar")
        sidecar_entry = f"{'a' * 64}  {asset_expected}"
        self.assertIsNotNone(re.fullmatch(pattern.group(1), sidecar_entry))
        self.assertIsNone(re.fullmatch(pattern.group(1), f"{'a' * 64}  {asset_expected}.other"))


if __name__ == "__main__":
    unittest.main()
