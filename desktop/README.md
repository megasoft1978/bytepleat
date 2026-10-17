# Bytepleat Desktop (alpha)

A local desktop app (Tauri 2) for the Bytepleat archive tools. It is an early alpha with no installer. How it works internally: [docs/desktop-internals.md](../docs/desktop-internals.md). What has been tested: [docs/desktop-validation.md](../docs/desktop-validation.md).

## Prerequisites

Rust 1.93 or newer, Node.js/npm, and the [Tauri v2 prerequisites](https://v2.tauri.app/start/prerequisites/) for your platform. Run all commands from this directory.

## Run

```sh
npm install --ignore-scripts
npm run tauri -- dev
```

## Test

The app and core crate have separate Cargo manifests and lockfiles. In each of `core` and `src-tauri`:

```sh
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
```

Native GUI checks live in `e2e/` and run in CI; these commands do not replace them.

## Package

```sh
CARGO_BUILD_JOBS=4 npm run tauri -- build
```

Linux `.deb` development packages: see [PACKAGING.md](PACKAGING.md). Packages are unsigned.

## What it does

- **Create:** pick files or a folder, choose a format, save a new archive.
- **Extract:** unpack an archive into a new folder named after the archive plus `-extracted`. Existing files and folders are never overwritten.
- **Inspect:** list an archive without extracting. Listing does not check file contents.
- Formats: ZIP, 7z, TAR+Zstandard, TAR+gzip, TAR+LZ4. RAR, password-protected archives, and ZIP64 are not supported.

## Limits

- 1 GiB of output and 100,000 entries per operation; listings preview up to 5,000 entries.
- One operation at a time.
- Extracting selected entries still decodes the whole archive first.
- A selected path that is not valid UTF-8 is rejected with an error.
- The bundle declares `.zip`, `.7z`, `.tar.zst`, `.tar.gz`, and `.tar.lz4` file associations; how the OS registers them depends on the installer and platform.
- The window opens at 960×640 with a 760×520 minimum. On a screen too small for the default plus a 48 px margin, it is shrunk to the work area and centred.
- A browser preview shows the interface only; it cannot open files or run archive operations.

References: [Tauri v2 configuration](https://v2.tauri.app/reference/config/), [single-instance plugin](https://docs.rs/tauri-plugin-single-instance/latest/tauri_plugin_single_instance/), [macOS `Opened` run event](https://docs.rs/tauri/latest/tauri/enum.RunEvent.html). The app embeds its frontend and makes no external CDN requests.
