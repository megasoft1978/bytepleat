"""Headless tests for the GNOME Files/Nautilus context menu extension."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[3]
EXTENSION = ROOT / "desktop/integrations/linux/nautilus/bytepleat_extension.py"


class FakeLocation:
    def __init__(self, path):
        self.path = path

    def get_path(self):
        return self.path


class FakeFile:
    def __init__(self, path, scheme="file"):
        self.path = path
        self.scheme = scheme

    def get_uri_scheme(self):
        return self.scheme

    def get_location(self):
        return FakeLocation(self.path)


class FakeMenuItem:
    def __init__(self, *, name, label):
        self.name = name
        self.label = label
        self.connection = None

    def connect(self, signal, callback, *args):
        self.connection = (signal, callback, args)

    def activate(self):
        signal, callback, args = self.connection
        if signal != "activate":
            raise AssertionError("unexpected signal")
        callback(self, *args)


class NautilusExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config_root = Path(self.temp.name)
        self.subprocess_new = Mock()

        gio = types.SimpleNamespace(
            Subprocess=types.SimpleNamespace(new=self.subprocess_new),
            SubprocessFlags=types.SimpleNamespace(NONE=object()),
        )
        glib = types.SimpleNamespace(get_user_config_dir=lambda: str(self.config_root))
        gobject = types.SimpleNamespace(GObject=type("GObject", (), {}))
        nautilus = types.SimpleNamespace(
            MenuProvider=type("MenuProvider", (), {}), MenuItem=FakeMenuItem
        )
        repository = types.ModuleType("gi.repository")
        repository.Gio = gio
        repository.GLib = glib
        repository.GObject = gobject
        repository.Nautilus = nautilus
        gi = types.ModuleType("gi")
        gi.repository = repository
        helper_spec = importlib.util.spec_from_file_location(
            "bytepleat_cli_args", EXTENSION.with_name("bytepleat_cli_args.py")
        )
        helper = importlib.util.module_from_spec(helper_spec)
        helper_spec.loader.exec_module(helper)
        modules = {
            "gi": gi,
            "gi.repository": repository,
            "bytepleat_cli_args": helper,
        }
        self.module_name = "bytepleat_extension_test"
        spec = importlib.util.spec_from_file_location(self.module_name, EXTENSION)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.module)

    def write_config(self, value):
        path = self.config_root / "bytepleat" / "desktop-integration.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_nautilus_three_and_four_signatures_create_expected_items(self):
        extension = self.module.BytepleatExtension()
        files = [FakeFile("/tmp/a file"), FakeFile("/tmp/日本語")]
        for result in (extension.get_file_items(object(), files), extension.get_file_items(files)):
            self.assertEqual(
                [(item.name, item.label) for item in result],
                [
                    ("Bytepleat::create", "Compress with Bytepleat"),
                    ("Bytepleat::extract", "Extract with Bytepleat"),
                ],
            )
            self.assertEqual([item.connection[2][1] for item in result], [files and [f.path for f in files]] * 2)

    def test_empty_remote_and_missing_local_paths_are_rejected(self):
        extension = self.module.BytepleatExtension()
        self.assertEqual(extension.get_file_items([]), [])
        self.assertEqual(extension.get_file_items([FakeFile("/tmp/local"), FakeFile(None, "smb")]), [])
        self.assertEqual(extension.get_file_items([FakeFile(None)]), [])

    def test_activation_launches_configured_app_with_exact_direct_argv(self):
        application = "/opt/Bytepleat folder/bytepleat'日本"
        paths = ["/tmp/ leading-dash", "/tmp/O'Brien", "/tmp/雪 file"]
        self.write_config({"application": application})
        items = self.module.BytepleatExtension().get_file_items([FakeFile(path) for path in paths])
        flags = self.module.Gio.SubprocessFlags.NONE

        items[0].activate()
        self.subprocess_new.assert_called_once_with(
            [application, "--create", "--", *paths], flags
        )
        self.subprocess_new.reset_mock()
        items[1].activate()
        self.subprocess_new.assert_called_once_with(
            [application, "--extract", "--", *paths], flags
        )

    def test_missing_or_invalid_application_config_is_a_noop(self):
        item = self.module.BytepleatExtension().get_file_items([FakeFile("/tmp/input")])[0]
        for contents in (None, "not json", {"application": "relative/path"}, {"application": 7}):
            if contents is not None:
                path = self.config_root / "bytepleat" / "desktop-integration.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents if isinstance(contents, str) else json.dumps(contents), encoding="utf-8")
            else:
                path = self.config_root / "bytepleat" / "desktop-integration.json"
                path.unlink(missing_ok=True)
            item.activate()
        self.subprocess_new.assert_not_called()


if __name__ == "__main__":
    unittest.main()
