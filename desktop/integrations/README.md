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
macOS 27.0.1 ARM64, the Services entries were visible; warm Compress and cold
Extract passed. A two-file selection was also forwarded to Create with both
paths intact. Separately, Finder Open With cold-launched the app for a ZIP and
listed a 7z archive; the 7z check did not extract files. This tests Finder's
Open With action for the desktop app, not the Services provider's Open With
invocation. The native file picker accepted keyboard Go to Folder navigation.
Dock Quit cleanup and the provider's Open With invocation remain unverified.
See the [desktop validation record](../../docs/desktop-validation.md) for exact
test scope.

Developer signing may be used for local testing. Developer ID signing,
Hardened Runtime, and notarization are release tasks and remain pending.

## Linux file managers

The Linux installer targets Ubuntu 24.04/26.04 GNOME Files and Kubuntu 26.04
Dolphin as planned compatibility targets. On Ubuntu 24.04.5 ARM64 with
XFCE/Xorg, archive creation, full and selected extraction, hashes,
empty-directory restoration, no-overwrite refusal, and Nautilus and Dolphin
context actions were verified. A separate Ubuntu 24.04.5 ARM64 GNOME/Xorg run
tested Nautilus Open With, Extract, and Compress on the installed v10 package.
The latest source has since been rebuilt and packaged in CI, but has not been
installed for a fresh GNOME runtime test. Wayland and Kubuntu 26.04/Dolphin
remain unverified. The installer
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
| macOS Finder Services and Open With | Implemented; Swift compile required on macOS | On macOS 27.0.1 ARM64, Services registration, warm Compress, cold Extract, two-file Services selection, cold Open With listing, and file-picker keyboard navigation passed. 7z was listed only; Dock Quit cleanup remains unverified. |
| GNOME Files / Nautilus | Implemented; Nautilus Python GI required at runtime | Nautilus 46.4 context Compress/Extract passed on Ubuntu 24.04.5 ARM64 XFCE/Xorg. On GNOME/Xorg, Open With and one cold Extract and Compress passed on installed v10. Latest source was rebuilt and packaged in CI, but has not been installed for runtime validation; cancellation, no-overwrite, and selected extraction still need repeating on the current package. |
| KDE Dolphin service menu | Implemented; desktop-entry registration handled by KDE | Dolphin 23.08.5 warm Compress and cold Extract passed on Ubuntu 24.04.5 ARM64 XFCE/Xorg. Kubuntu 26.04 remains unverified. |
| Windows File Explorer | `IExplorerCommand` source and MSIX packaging implemented | x64 native adapter tests passed; Windows 11 ARM64 test MSIX installed and package registration, alias, packaged COM activation/enumeration, and test-receiver argument handoff passed in [CI](https://github.com/megasoft1978/bytepleat/actions/runs/38754501942). Interactive Explorer menu behavior and x64 installed-app behavior remain unverified. |
| Thunar custom action | Documented manual configuration | Pending runtime verification |

GUI correctness checks do not establish compression performance. See the
[desktop validation record](../../docs/desktop-validation.md) for scope,
remaining checks, and links to public CI runs.

User-installed Dolphin service menus are marked executable and restricted to local file URLs, following the [KDE service-menu instructions](https://develop.kde.org/docs/apps/dolphin/service-menus/).
