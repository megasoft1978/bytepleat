"""Nautilus context actions for local file selections (GNOME Files)."""
import json
import os

from gi.repository import Gio, GLib, GObject, Nautilus
from bytepleat_cli_args import selection_arguments


def _application_path():
    config = os.path.join(GLib.get_user_config_dir(), "bytepleat", "desktop-integration.json")
    try:
        with open(config, encoding="utf-8") as stream:
            value = json.load(stream).get("application")
        return value if isinstance(value, str) and os.path.isabs(value) else None
    except (OSError, ValueError, TypeError):
        return None


class BytepleatExtension(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, *args):
        files = args[-1]  # Nautilus 3 supplied (window, files); Nautilus 4 supplies (files,).
        if not files or any(file.get_uri_scheme() != "file" for file in files):
            return []
        paths = [file.get_location().get_path() for file in files]
        if any(path is None for path in paths):
            return []
        return [
            self._item("create", "Compress with Bytepleat", paths),
            self._item("extract", "Extract with Bytepleat", paths),
        ]

    @staticmethod
    def _item(action, label, paths):
        item = Nautilus.MenuItem(
            name="Bytepleat::" + action,
            label=label,
        )
        item.connect("activate", BytepleatExtension._activate, action, paths)
        return item

    @staticmethod
    def _activate(_item, action, paths):
        application = _application_path()
        if application is None:
            return
        Gio.Subprocess.new([application, *selection_arguments(action, paths)], Gio.SubprocessFlags.NONE)
