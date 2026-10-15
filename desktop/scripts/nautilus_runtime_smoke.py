#!/usr/bin/env python3
"""Exercise the installed Nautilus extension in a real Files context menu.

Run inside a private D-Bus session and fixed-size Xvfb display with Nautilus,
python3-nautilus, python3-pyatspi, and xdotool installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import pyatspi


ROOT = Path(__file__).resolve().parents[2]


def descendants(node):
    yield node
    try:
        count = node.childCount
    except Exception:
        return
    for index in range(count):
        try:
            yield from descendants(node[index])
        except Exception:
            continue


def nautilus_accessible():
    desktop = pyatspi.Registry.getDesktop(0)
    for index in range(desktop.childCount):
        application = desktop[index]
        if application.name == "org.gnome.Nautilus":
            return application
    return desktop


def visible_windows():
    result = subprocess.run(
        ["xdotool", "search", "--onlyvisible", ".*"],
        check=False,
        capture_output=True,
        text=True,
    )
    return [window for window in result.stdout.splitlines() if window]


def main() -> None:
    if os.geteuid() == 0:
        raise RuntimeError("Nautilus runtime smoke must run as an unprivileged user")
    for tool in ("nautilus", "xdotool"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"missing required command: {tool}")
    version = subprocess.check_output(
        ["dpkg-query", "-W", "-f=${Version}", "nautilus"], text=True
    ).strip()
    print(f"GNOME Files/Nautilus package {version}", flush=True)

    with tempfile.TemporaryDirectory(prefix="bytepleat-nautilus-runtime-") as temporary:
        home = Path(temporary)
        data = home / ".local/share"
        config = home / ".config"
        fixture_dir = home / "Bytepleat Nautilus Runtime"
        fixture_dir.mkdir()
        fixture = fixture_dir / "-leading dash_日本語.txt"
        fixture.write_text("runtime extension fixture\n", encoding="utf-8")
        capture = home / "captured-argv.json"
        app = home / "Bytepleat capture application"
        app.write_text(
            "#!/usr/bin/python3\n"
            "import json, os, sys\n"
            "with open(os.environ['BYTEPLEAT_CAPTURE'], 'w', encoding='utf-8') as f:\n"
            "    json.dump(sys.argv[1:], f, ensure_ascii=False)\n",
            encoding="utf-8",
        )
        app.chmod(0o755)
        environment = os.environ.copy()
        environment.update(
            HOME=str(home),
            XDG_DATA_HOME=str(data),
            XDG_CONFIG_HOME=str(config),
            XDG_CACHE_HOME=str(home / ".cache"),
            XDG_STATE_HOME=str(home / ".local/state"),
            BYTEPLEAT_CAPTURE=str(capture),
            GTK_A11Y="atspi",
        )

        subprocess.run(
            [
                sys.executable,
                str(ROOT / "desktop/scripts/install-linux-integrations.py"),
                "--install",
                "--app",
                str(app),
            ],
            env=environment,
            check=True,
        )
        extension = data / "nautilus-python/extensions/bytepleat_extension.py"
        if not extension.is_file():
            raise RuntimeError("installer did not install the Nautilus extension")

        subprocess.run(
            [
                "dbus-update-activation-environment",
                "HOME",
                "XDG_DATA_HOME",
                "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME",
                "XDG_STATE_HOME",
                "BYTEPLEAT_CAPTURE",
                "GTK_A11Y",
            ],
            env=environment,
            check=True,
        )

        nautilus_process = None
        try:
            nautilus_log = home / "nautilus.log"
            with nautilus_log.open("w", encoding="utf-8") as log_stream:
                nautilus_process = subprocess.Popen(
                    ["nautilus", "--new-window", "--select", fixture.as_uri()],
                    env=environment,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                )

            window = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                for candidate in visible_windows():
                    title = subprocess.run(
                        ["xdotool", "getwindowname", candidate],
                        check=False,
                        capture_output=True,
                        text=True,
                    ).stdout
                    if fixture_dir.name in title:
                        window = candidate
                        break
                if window:
                    break
                time.sleep(0.25)
            if window is None:
                raise RuntimeError("Nautilus did not open the selected fixture folder")
            subprocess.run(["xdotool", "windowfocus", window], check=True)

            # Wait for Nautilus to expose the selected fixture before opening
            # its context menu. AT-SPI provides reliable selection discovery,
            # but GTK4 reports incorrect screen origins for these icon cells.
            selected = False
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not selected:
                for node in descendants(nautilus_accessible()):
                    try:
                        if (
                            node.name == fixture.name
                            and node.getRoleName() == "table cell"
                        ):
                            selected = True
                            break
                    except Exception:
                        continue
                if not selected:
                    time.sleep(0.25)
            if not selected:
                raise RuntimeError("Nautilus accessibility tree did not expose the selected fixture")

            def activate_and_check(action: str, down_presses: int, expected: list[str]) -> None:
                # The isolated 1280x1024 Xvfb display and fresh Nautilus
                # window place the first selected icon at (282,138). GTK4's
                # AT-SPI extents omit the icon-view origin, so they cannot
                # drive this right-click.
                subprocess.run(
                    ["xdotool", "mousemove", "--sync", "282", "138", "click", "3"],
                    check=True,
                )
                time.sleep(0.5)
                # Nautilus 46 presents Open first. The two installed actions
                # follow the standard file actions and focus at offsets 9/10.
                subprocess.run(
                    [
                        "xdotool",
                        "key",
                        "--repeat",
                        str(down_presses),
                        "--delay",
                        "50",
                        "Down",
                    ],
                    check=True,
                )
                subprocess.run(["xdotool", "key", "Return"], check=True)

                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not capture.is_file():
                    time.sleep(0.1)
                if not capture.is_file():
                    raise RuntimeError(
                        f"activating the visible Nautilus {action} action did not launch the installed target; "
                        f"Nautilus log tail: {nautilus_log.read_text(encoding='utf-8')[-2000:]}"
                    )
                argv = json.loads(capture.read_text(encoding="utf-8"))
                if argv != expected:
                    raise RuntimeError(
                        f"Nautilus {action} action passed unexpected argv: {argv!r}"
                    )
                print(f"PASS: Nautilus {action} action launched with argv {argv!r}", flush=True)
                capture.unlink()

            activate_and_check(
                "Compress", 9, ["--create", "--", str(fixture)]
            )
            activate_and_check(
                "Extract", 10, ["--extract", "--", str(fixture)]
            )
        finally:
            try:
                subprocess.run(
                    ["nautilus", "--quit"], env=environment, check=False, timeout=5
                )
            except subprocess.TimeoutExpired:
                pass
            if nautilus_process is not None:
                try:
                    nautilus_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    nautilus_process.terminate()
                    nautilus_process.wait(timeout=5)


if __name__ == "__main__":
    main()
