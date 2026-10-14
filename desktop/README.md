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

The app and core crate have separate Cargo manifests and lockfiles. Build commands are run from this directory so Tauri resolves `src-tauri/tauri.conf.json`. The archive engine has locked build and test evidence on macOS Apple silicon and Ubuntu 24.04 (Linux x86-64 GNU); that does not establish desktop GUI behavior. A native macOS GUI launch and initial file selection have been observed, but native dialog workflow verification is still in progress. Desktop behavior and installers have not been verified across Windows, macOS, and Linux. The macOS bundle minimum is set to 13.0, but this setting is not evidence of testing on that OS version. See the [engine release verification notes](../RELEASE.md) for runner baselines and CI evidence.

## Operation notes

- The interface supervises a child process of its own executable. The child receives a bounded JSON request and writes progress/result JSON inside a unique private staging directory.
- Published results are moved from staging only after a successful worker exit. Existing destinations fail instead of being overwritten. Inputs are not moved or removed.
- Creating a multi-selection stages copies so each selected item's basename is represented in the archive; this adds I/O and storage overhead. A single selected directory archives its contents.
- Extraction uses the selected parent folder and creates a sibling subfolder named after the archive plus `-extracted`. Choose a location where that name does not already exist.
- Native file paths enter the UI as UTF-8 strings. A selection containing a path that cannot be represented as UTF-8 is rejected in full with an error; it is never silently shortened. The underlying Rust CLI worker uses OS paths.
- One operation runs at a time. The interface disables new work while a job is active, and the broker also rejects concurrent requests. Jobs are retained in a bounded history. Closing the app cancels and reaps its owned worker before exit, removing its private staging directory without publishing.
- Windows file association launches may pass paths directly without flags; these are treated as archive-open selections. Unknown command-line options are rejected.
- Browser preview only presents the interface and an explicit native-backend notice. It cannot browse files or report successful archive operations.

## File associations

The bundle declares `.zip`, `.7z`, `.tar.zst`, `.tar.gz`, and `.tar.lz4` associations. OS registration behavior depends on the installer and platform. These declarations do not promise support for other archive formats.

## Implementation references

Tauri version pins and bundle settings follow the [Tauri v2 configuration reference](https://v2.tauri.app/reference/config/), its [single-instance plugin](https://docs.rs/tauri-plugin-single-instance/latest/tauri_plugin_single_instance/), and the current [macOS `Opened` run event](https://docs.rs/tauri/latest/tauri/enum.RunEvent.html). The app embeds its static frontend and makes no external CDN requests.
