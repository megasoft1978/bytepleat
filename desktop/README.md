# Bytepleat Desktop alpha

Bytepleat Desktop is a local Tauri 2 interface for the Bytepleat archive engine. This is an early alpha. It currently exposes ZIP, 7z, TAR+Zstandard, TAR+Gzip, and TAR+LZ4. RAR, password-protected archives, and ZIP64 are not supported. Opening an archive displays its bounded listing; listing does not validate archive contents. Extraction decodes into private staging before publication. Selecting entries still decodes the whole archive before retaining the selected entries, so it is not random access.

## Build locally

Requirements are Rust 1.93 or newer, Node.js/npm, and the platform prerequisites listed in the [Tauri v2 prerequisites](https://v2.tauri.app/start/prerequisites/). From this directory:

```sh
npm install --ignore-scripts
npm run tauri -- dev
```

For a desktop bundle:

```sh
CARGO_BUILD_JOBS=4 npm run tauri -- build
```

The app and core crate have separate Cargo manifests and lockfiles. Build commands are run from this directory so Tauri resolves `src-tauri/tauri.conf.json`. Current GUI and integration evidence is summarized in [desktop validation](../docs/desktop-validation.md). In brief: macOS 27.0.1 ARM64 GUI and selected Finder Service workflows have been exercised; Ubuntu 24.04.5 ARM64 XFCE/Xorg has passed full GUI extraction and refusal/recovery checks. These results establish only the stated session scope. Nautilus 46.4 and Dolphin 23.08.5 Compress/Extract handoffs have also passed in that Ubuntu XFCE session. Ubuntu GNOME/Xorg also passed listing, selected extraction, and existing-destination refusal in the installed app. Other GNOME flows, Kubuntu 26.04, Windows interactive behavior, and macOS 13 minimum-version behavior remain unverified. The macOS bundle minimum is set to 13.0; the locally tested build was unsigned and ad-hoc signed only, not Developer ID signed or notarized. See the [engine release verification notes](../RELEASE.md) for runner baselines and CI evidence.

## Operation notes

- The interface supervises a child process of its own executable. The child receives a bounded JSON request and writes progress/result JSON inside a unique private staging directory.
- Published results are moved from staging only after a successful worker exit. Existing destinations fail instead of being overwritten. Inputs are not moved or removed.
- Creating a multi-selection stages copies so each selected item's basename is represented in the archive; this adds I/O and storage overhead. A single selected directory archives its contents.
- Extraction uses the selected parent folder and creates a sibling subfolder named after the archive plus `-extracted`. Choose a location where that name does not already exist.
- Native file paths enter the UI as UTF-8 strings. A selection containing a path that cannot be represented as UTF-8 is rejected in full with an error; it is never silently shortened. The underlying Rust CLI worker uses OS paths.
- One operation runs at a time. The interface disables new work while a job is active, and the broker also rejects concurrent requests. Archive inspection runs in that same managed child worker and broker slot, including TAR full-decode listing; it can be cancelled and is killed, reaped, and cleaned up on app shutdown. Inspection returns a size-bounded preview with the total entry count and an explicit truncation flag, and never publishes output. Inspection cancellation is shown as a cancelled job and does not retain or display a partial listing. Jobs are retained in a bounded history. Closing the app cancels and reaps its owned worker before exit, removing its private staging directory without publishing.
- Windows file association launches may pass paths directly without flags; these are treated as archive-open selections. Unknown command-line options are rejected.
- Browser preview only presents the interface and an explicit native-backend notice. It cannot browse files or report successful archive operations.

Desktop Rust verification for the inspection worker change: `cargo fmt --all -- --check`, `cargo clippy --locked --all-targets -- -D warnings`, and `cargo test --locked` were run in both `desktop/core` and `desktop/src-tauri`; `node --check desktop/ui/app.js` was also run. These checks do not replace native GUI verification. Native macOS 27.0.1 ARM64 checks now cover a 5,000-of-40,001-item TAR listing preview, inspection cancellation, Cmd+Q, and window close during inspection, with independent worker-exit and staging-removal observations. Dock Quit and corresponding Windows/Linux inspection workflows remain unverified. The one-active-job rule and shutdown reservation are covered by backend regression tests; GUI coverage does not establish every platform or exit path.

## File associations

The bundle declares `.zip`, `.7z`, `.tar.zst`, `.tar.gz`, and `.tar.lz4` associations. OS registration behavior depends on the installer and platform. These declarations do not promise support for other archive formats.

## Implementation references

Tauri version pins and bundle settings follow the [Tauri v2 configuration reference](https://v2.tauri.app/reference/config/), its [single-instance plugin](https://docs.rs/tauri-plugin-single-instance/latest/tauri_plugin_single_instance/), and the current [macOS `Opened` run event](https://docs.rs/tauri/latest/tauri/enum.RunEvent.html). The app embeds its static frontend and makes no external CDN requests.
