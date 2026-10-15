# Bytepleat

**Compress files. Pack folders. Restore the same bytes.**

Bytepleat is a Rust archiver built around familiar formats and careful file handling. Everything runs on your device; inputs are never moved or removed.

| | Status | Get it |
| --- | --- | --- |
| **Command-line tool 0.5.1** | Released. Native CI passed on macOS Apple silicon, Linux x86-64 and Windows x86-64. | [Install](#install) |
| **Desktop app** | Alpha, in development. No consumer installer is published. | [Build and try it](#desktop-app-alpha) |

```sh
bytepleat compress report.pdf
bytepleat test report.pdf.zst
bytepleat decompress report.pdf.zst -o report-restored.pdf

bytepleat pack project -o project.tar.zst
bytepleat test project.tar.zst
bytepleat unpack project.tar.zst -o project-restored
```

Your originals stay in place. Named outputs are published after successful completion, and unpacking requires a new destination directory. Bytepleat uses established codecs and archive formats; it does not introduce a proprietary archive format.

## Desktop app (alpha)

A calm desktop window for everyday archive work, built on the same bounded archive engine as the CLI. It uses your system's file dialogs and has three views:

- **Create:** choose files or a folder, pick a format, and save a new archive.
- **Extract:** unpack one archive into a new folder. An existing destination is refused, never overwritten.
- **Inspect:** list an archive's entries without extracting. Listing does not verify file contents. Extracting selected entries still decodes the whole archive before keeping the ones you chose.

There is no desktop installer yet; the packages under [Install](#install) are the CLI release. To try the alpha, build it from source (Rust 1.93 or newer, Node.js/npm and the [Tauri v2 prerequisites](https://v2.tauri.app/start/prerequisites/)):

```sh
cd desktop
npm install --ignore-scripts
npm run tauri -- dev
```

Desktop operations are capped at 1 GiB of output and 100,000 entries; listings preview up to 5,000 entries. ZIP is classic Stored/Deflate only, 7z is a bounded subset, and compressed tar uses Zstandard, gzip or LZ4. RAR, password-protected archives and ZIP64 are not supported. See [supported formats](docs/formats.md).

**Platform evidence.** Platform validation is incomplete. This summarizes [desktop validation](docs/desktop-validation.md), which has the exact scope, versions and open items:

| Platform | What has been checked |
| --- | --- |
| macOS 27.0.1 · Apple silicon | Interactive GUI runs of create, inspect, selected and full extraction, overwrite refusal, cancellation, and selected Finder handoffs. Unsigned local build; not notarized. macOS 13 (the bundle minimum) is unverified. |
| Ubuntu 24.04.5 · ARM64 | Interactive runs in XFCE/Xorg and GNOME/Xorg, including Nautilus and Dolphin handoffs. Some GNOME checks still need repeating on the latest package. Wayland and Kubuntu are unverified. |
| Windows | Native CI tests and MSIX package validation only. Installed GUI and Explorer behavior are unverified. |

These are results from specific sessions, not a claim of support for every OS version or architecture. See [desktop/README.md](desktop/README.md) for build notes and limitations.

## Install

**Downloads:** [Release packages](https://github.com/megasoft1978/bytepleat/releases). Download the archive for your platform and verify its adjacent `.sha256` file; see [verification and extraction](RELEASE.md). Packages are unsigned and macOS builds are not notarized.

| Tested release target | Package |
| --- | --- |
| macOS Apple silicon | `bytepleat-0.5.1-aarch64-apple-darwin.tar.gz` |
| Linux x86-64 GNU | `bytepleat-0.5.1-x86_64-unknown-linux-gnu.tar.gz` |
| Windows x86-64 MSVC | `bytepleat-0.5.1-x86_64-pc-windows-msvc.zip` |

Native CI builds, tests, and package execution passed on all three targets. See [release notes](RELEASE.md) for the tested runner baselines. Other OS versions and architectures are outside that verification.

The Windows package requires the x64 [Microsoft Visual C++ v14 runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist); it is not bundled. If Windows reports `VCRUNTIME140.dll` missing, install the current x64 redistributable from Microsoft.

Each archive extracts into a same-named directory containing `bytepleat` (or `bytepleat.exe` on Windows) at its root. Run it from that directory as `./bytepleat --help` on macOS/Linux or `.\bytepleat.exe --help` in PowerShell; to invoke `bytepleat` from any directory, add the extracted directory to your `PATH`.

**Build from source** (Rust 1.93 or newer and a C compiler toolchain required):

```sh
git clone https://github.com/megasoft1978/bytepleat.git
cd bytepleat
cargo build --release --locked
```

The executable is `target/release/bytepleat` (`target/release/bytepleat.exe` on Windows).

**Install from the Git tag** (Rust 1.93 or newer and a C compiler toolchain required):

```sh
cargo install --locked --git https://github.com/megasoft1978/bytepleat --tag v0.5.1
```

## Quick start

Zstandard is the default. Use `--format` to choose another codec or archive format. Inspect metadata with `bytepleat info project.tar.zst --json`; run `bytepleat test project.tar.zst` to fully decode and check supported content before extraction.

Windows PowerShell uses the same commands and options; substitute paths as needed. For a directory with ZIP compatibility:

```powershell
bytepleat pack .\photos --format zip -o .\photos.zip
bytepleat unpack .\photos.zip -o .\photos-out
```

Bytepleat never removes the input. Named output files are staged and published after successful completion; an existing output is an error unless `--force` is given. Extraction requires a new destination directory. Output to stdout can be partial if a stream operation fails; use a named output when you need all-or-nothing file publication.

### Choose a compression preset

Choose `--preset fast`, `--preset balanced` (the default), or `--preset compact` for Zstandard and gzip. Fine-tune with `--level`; compression time and output size depend on your files and settings. The [guide](docs/user-guide.md) documents the exact levels. LZ4 has one supported level; Pco requires an explicit numeric `--type`.

See the [user guide](docs/user-guide.md) for pipes, archive options, and numeric buffers, and [supported formats](docs/formats.md) for the precise compatibility boundaries.

## Supported formats

| Format | Single-file streams | Folder archive | Notes |
| --- | --- | --- | --- |
| Zstandard, gzip, LZ4 | Compress and decompress | Compressed tar | Standard codecs; presets available for Zstandard and gzip |
| ZIP | — | Create, inspect, test, and extract a supported subset | Stored and Deflate entries |
| 7z | — | Create, inspect, test, and extract a bounded subset | LZMA2; compatibility limits apply |
| Pco | Typed numeric streams | — | Standalone little-endian values; requires an explicit type |

RAR can be identified for metadata display but is not decoded. See [supported formats](docs/formats.md) for exact compatibility boundaries.

Archive contents preserve file bytes and relative paths within the supported scope. Permissions, ownership, links, extended attributes, and portable timestamps are not restored. `test` checks decoding and format integrity; `info` reads metadata. Neither authenticates the sender or scans for malware. See [security and limits](docs/security-limits.md) for extraction checks, default caps, and publication behavior.

## Project

- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Security reporting](SECURITY.md)
- [Support](SUPPORT.md)
- [Release notes and verification](RELEASE.md)
- [GitHub repository](https://github.com/megasoft1978/bytepleat)
- [Project website](https://megasoft1978.github.io/bytepleat/)

## License

Bytepleat is [MIT licensed](LICENSE). Dependencies retain their own licenses; see [THIRD-PARTY.json](THIRD-PARTY.json) and the [vendored dependency notes](vendor/README.md).
