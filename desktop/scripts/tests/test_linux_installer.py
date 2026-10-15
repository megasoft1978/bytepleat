import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "install-linux-integrations.py"
SPEC = importlib.util.spec_from_file_location("linux_installer", SCRIPT)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)
ARGS_SPEC = importlib.util.spec_from_file_location(
    "bytepleat_cli_args",
    SCRIPT.parents[1] / "integrations/linux/nautilus/bytepleat_cli_args.py",
)
cli_args = importlib.util.module_from_spec(ARGS_SPEC)
ARGS_SPEC.loader.exec_module(cli_args)


class LinuxInstallerTests(unittest.TestCase):
    def test_desktop_exec_quotes_unusual_application_path(self):
        executable = "/tmp/Bytepleat O'Brien 🧵/bytepleat-desktop"
        line = next(line for line in installer.launcher_text(executable).splitlines() if line.startswith("Exec="))
        self.assertIn("StartupNotify=true", installer.launcher_text(executable))
        self.assertTrue(line.startswith('Exec="/tmp/Bytepleat O\'Brien 🧵/bytepleat-desktop" '))
        self.assertIn(" --open -- %F", line)

    def test_services_keep_filename_field_outside_quoted_argument(self):
        text = installer.service_menu_text('/tmp/Bytepleat"dev/bytepleat-desktop')
        lines = [line for line in text.splitlines() if line.startswith("Exec=")]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.endswith(" %F") for line in lines))
        self.assertTrue(all(" -- " in line for line in lines))

    def test_selection_paths_are_individual_arguments_verbatim(self):
        paths = [
            "/tmp/a file.zip",
            "/tmp/O'Brien.txt",
            "/tmp/雪だるま",
            "/tmp/-leading-dash",
        ]
        self.assertEqual(cli_args.selection_arguments("extract", paths), ["--extract", "--", *paths])

    def test_desktop_quote_escapes_literal_percent_field_marker(self):
        line = next(line for line in installer.launcher_text("/tmp/100%/bytepleat").splitlines() if line.startswith("Exec="))
        self.assertTrue(line.startswith('Exec="/tmp/100%%/bytepleat" '))

    def test_install_and_uninstall_touch_only_owned_paths(self):
        with tempfile.TemporaryDirectory(prefix="bytepleat integration ") as temporary:
            root = Path(temporary)
            executable = root / "O'Brien 🧵" / "-bytepleat-desktop"
            executable.parent.mkdir()
            executable.write_text("generated executable fixture\n", encoding="utf-8")
            executable.chmod(0o755)
            installed = installer.install(root, executable)
            self.assertEqual(len(installed), len(installer.OWNED))
            config = json.loads((root / installer.OWNED[-1]).read_text(encoding="utf-8"))
            self.assertEqual(config["application"], str(executable.resolve()))
            self.assertTrue((root / installer.OWNED[0]).is_file())
            if os.name != "nt":
                self.assertTrue(os.access(root / installer.OWNED[1], os.X_OK))
            service = (root / installer.OWNED[1]).read_text(encoding="utf-8")
            self.assertIn("MimeType=application/octet-stream;inode/directory;", service)
            self.assertIn("X-KDE-Protocols=file", service)
            removed = installer.uninstall(root)
            self.assertEqual(len(removed), len(installer.OWNED))
            self.assertTrue(executable.exists())

    def test_refuses_to_overwrite_any_existing_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            occupied = root / installer.OWNED[1]
            occupied.parent.mkdir(parents=True)
            occupied.write_text("user-owned fixture", encoding="utf-8")
            executable = root / "bytepleat-desktop"
            executable.write_text("generated executable fixture", encoding="utf-8")
            executable.chmod(0o755)
            with self.assertRaises(FileExistsError):
                installer.install(root, executable)
            self.assertEqual(occupied.read_text(encoding="utf-8"), "user-owned fixture")


if __name__ == "__main__":
    unittest.main()
