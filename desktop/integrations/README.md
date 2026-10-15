# Desktop file-manager integrations

These are opt-in alpha adapters for the desktop CLI contract:

```text
bytepleat-desktop --create -- PATH...
bytepleat-desktop --extract -- PATH...
bytepleat-desktop --open -- PATH...
```

The `--` separator ends option parsing. Paths are passed as individual OS
arguments, including names with whitespace, apostrophes, Unicode, or a leading
dash. Integrations do not invoke a shell to assemble a selection.

## macOS Finder Services

`scripts/build-macos-services.sh --output-dir DIR` uses the machine's `swiftc` to
compile `BytepleatServices.app`. The output is an unsigned development bundle.
After the desktop app bundle exists, explicitly opt in with:

```sh
scripts/install-macos-services.sh \
  --service-app /path/to/BytepleatServices.app \
  --bytepleat-app /path/to/Bytepleat.app
```

The per-user installer owns only `~/Library/Services/BytepleatServices.app`,
refuses to overwrite an existing path, and opens the service bundle for
LaunchServices registration. Remove exactly that bundle with
`scripts/uninstall-macos-services.sh`. The provider reads file URLs first and
falls back to the Services filename pasteboard type. It uses the explicit app
path recorded during installation, or checks for a neighboring `Bytepleat.app`.
`BYTEPLEAT_APP_PATH` is an optional process environment override.

To verify registration, select local files in Finder and check **Finder →
Services** for **Compress with Bytepleat** and **Extract with Bytepleat**. On
macOS 27.0.1 ARM64, the Services entries were visible. A warm Compress action
on a selected input folder and a cold Extract action on a selected ZIP were
verified. This does not establish general multi-selection handling or the
provider's Open With invocation; those checks remain pending. The related GUI
workflow evidence is summarized in [desktop validation](../../docs/desktop-validation.md).

Developer signing may be used for local testing. Developer ID signing,
Hardened Runtime, and notarization are release tasks and remain pending.

## Linux file managers

The Linux installer targets Ubuntu 24.04/26.04 GNOME Files and Kubuntu 26.04
Dolphin as planned compatibility targets. A GUI session on Ubuntu 24.04.5
ARM64 with XFCE/Xorg verified archive creation, full and selected extraction,
hashes, empty-directory restoration, and no-overwrite refusal. This does not
verify the GNOME default shell, Nautilus actions, or Kubuntu 26.04/Dolphin. It
requires Python 3.10+, an executable desktop app binary, and writes only these
per-user files: `~/.local/share/applications/bytepleat.desktop`,
`~/.local/share/kio/servicemenus/bytepleat.desktop`,
`~/.local/share/nautilus-python/extensions/bytepleat_extension.py`,
`~/.local/share/nautilus-python/extensions/bytepleat_cli_args.py`,
and `~/.config/bytepleat/desktop-integration.json`.

Install with an explicit executable path:

```sh
python3 desktop/scripts/install-linux-integrations.py --install \
  --app "/absolute/path/to/bytepleat-desktop"
```

It refuses to replace any existing owned path. Uninstall removes only those
exact regular files or symlinks, and refuses unexpected directories:

```sh
python3 desktop/scripts/install-linux-integrations.py --uninstall
```

The launcher advertises supported archive MIME types as an application choice;
it does not silently change the default application. Dolphin receives `%F` as
separate filename arguments. Nautilus receives selected `file:` URLs, converts
only local URLs to paths, then uses `Gio.Subprocess` with an argument array.
Remote selections are omitted. For Thunar, see
[`linux/thunar/README.md`](linux/thunar/README.md) for opt-in custom-action
commands and selection-parameter guidance.

## Status

| Platform component | Source status | Native runtime status |
| --- | --- | --- |
| macOS Services bundle | Implemented; Swift compile required on macOS | Finder registration visible; warm Compress and cold Extract passed on macOS 27.0.1 ARM64. Open With invocation, multi-selection, keyboard browsing, and quit cleanup pending. |
| GNOME Files / Nautilus | Implemented; Nautilus Python GI required at runtime | Nautilus46.4 warm Compress/cold Extract passed on Ubuntu24.04.5 ARM64 XFCE/Xorg; defaultGNOME shell unverified. |
| KDE Dolphin service menu | Implemented; desktop-entry registration handled by KDE | Dolphin23.08.5 warm Compress/cold Extract passed on Ubuntu24.04.5 ARM64 XFCE/Xorg; Kubuntu26.04 unverified.. |
| Thunar custom action | Documented manual configuration | Pending runtime verification |

GUI correctness checks do not establish compression performance. See the
[desktop validation record](../../docs/desktop-validation.md) for scope,
remaining checks, and links to public CI runs.

User-installed Dolphin service menus are marked executable and restricted to local file URLs, following the [KDE service-menu instructions](https://develop.kde.org/docs/apps/dolphin/service-menus/).
