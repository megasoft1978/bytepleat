#!/usr/bin/env python3
"""Install/remove Bytepleat Linux file-manager integrations for one user."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

SCRIPT_DIR = Path(__file__).resolve().parent
DESKTOP_DIR = SCRIPT_DIR.parent
NAUTILUS_SOURCE = DESKTOP_DIR / "integrations/linux/nautilus/bytepleat_extension.py"
OWNED = (
    Path(".local/share/applications/bytepleat.desktop"),
    Path(".local/share/kio/servicemenus/bytepleat.desktop"),
    Path(".local/share/nautilus-python/extensions/bytepleat_extension.py"),
    Path(".local/share/nautilus-python/extensions/bytepleat_cli_args.py"),
    Path(".config/bytepleat/desktop-integration.json"),
)


def desktop_quote(value):
    """Quote one executable argument according to Desktop Entry Exec rules."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    for character in ("`", "$", "%"):
        escaped = escaped.replace(character, "\\" + character if character != "%" else "%%")
    return '"' + escaped + '"'


def launcher_text(application):
    app = desktop_quote(application)
    return (
        "[Desktop Entry]\nVersion=1.0\nType=Application\nName=Bytepleat\n"
        "Comment=Create and extract archives with Bytepleat\nIcon=bytepleat\n"
        f"Exec={app} --open -- %F\nTerminal=false\nStartupNotify=true\nCategories=Utility;Archiving;\n"
        "MimeType=application/zip;application/x-7z-compressed;"
        "application/gzip;application/zstd;application/x-lz4;\n"
    )


def service_menu_text(application):
    app = desktop_quote(application)
    return (
        "[Desktop Entry]\nType=Service\nMimeType=application/octet-stream;inode/directory;\n"
        "X-KDE-ServiceTypes=KonqPopupMenu/Plugin;\nActions=compress;extract;\n"
        "X-KDE-Priority=TopLevel\nX-KDE-Protocols=file\n\n"
        "[Desktop Action compress]\nName=Compress with Bytepleat\n"
        f"Exec={app} --create -- %F\n\n"
        "[Desktop Action extract]\nName=Extract with Bytepleat\n"
        f"Exec={app} --extract -- %F\n"
    )


def _write_new_file(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Refusing to replace existing path: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        temporary.chmod(mode)
        os.link(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def install(home, application):
    home = Path(home)
    app = Path(application).expanduser().resolve(strict=True)
    if not app.is_file() or not os.access(app, os.X_OK):
        raise ValueError(f"--app must be an executable file: {app}")
    targets = [home / relative for relative in OWNED]
    if any(path.exists() or path.is_symlink() for path in targets):
        raise FileExistsError("Refusing to overwrite an existing Bytepleat integration path")
    created = []
    try:
        launcher, kde, nautilus, cli_args, config = targets
        _write_new_file(launcher, launcher_text(str(app))); created.append(launcher)
        # KDE requires executable permission for user-installed service menus.
        _write_new_file(kde, service_menu_text(str(app)), mode=0o755); created.append(kde)
        _write_new_file(nautilus, NAUTILUS_SOURCE.read_text(encoding="utf-8")); created.append(nautilus)
        _write_new_file(cli_args, (DESKTOP_DIR / "integrations/linux/nautilus/bytepleat_cli_args.py").read_text(encoding="utf-8")); created.append(cli_args)
        config_data = json.dumps({"application": str(app)}, ensure_ascii=False) + "\n"
        _write_new_file(config, config_data); created.append(config)
    except Exception:
        for path in reversed(created):
            if path.is_file() or path.is_symlink():
                path.unlink()
        raise
    return targets


def uninstall(home):
    home = Path(home)
    removed = []
    for relative in OWNED:
        target = home / relative
        if target.is_symlink() or target.is_file():
            target.unlink()
            removed.append(target)
        elif target.exists():
            raise IsADirectoryError(f"Refusing to remove unexpected directory: {target}")
    return removed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--install", action="store_true")
    commands.add_argument("--uninstall", action="store_true")
    parser.add_argument("--app", help="path to the built bytepleat-desktop executable (required for install)")
    args = parser.parse_args(argv)
    try:
        if args.install:
            if not args.app:
                parser.error("--app is required with --install")
            paths = install(Path.home(), args.app)
            print("Installed per-user integrations:")
            for path in paths:
                print(path)
        else:
            removed = uninstall(Path.home())
            print(f"Removed {len(removed)} Bytepleat integration files")
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
