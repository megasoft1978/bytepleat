# Bytepleat

**Compress files. Pack folders. Restore the same bytes.**

Bytepleat is a Rust archiver built around familiar formats and careful file handling. Everything runs on your device; inputs are never moved or removed. Bytepleat uses established codecs and archive formats; it does not introduce a proprietary archive format.

- **[Install the CLI 0.5.1](#install)** — released for macOS Apple silicon, Linux x86-64 and Windows x86-64, with native CI checks on those targets.
- **[Explore the desktop alpha](#desktop-app-alpha)** — in development; build from source. No consumer installer is published.

[Quick start](#quick-start) · [Supported formats](#supported-formats) · [User guide](docs/user-guide.md)

## Install

**Downloads:** [Release packages](https://github.com/megasoft1978/bytepleat/releases). Download the archive for your platform and verify its adjacent `.sha256` file; see [verification and extraction](RELEASE.md). Packages are unsigned and macOS builds are not notarized.

| Tested release target | Package |
| --- | --- |
| macOS Apple silicon | `bytepleat-0.5.1-aarch64-apple-darwin.tar.gz` |
| Linux x86-64 GNU | `bytepleat-0.5.1-x86_64-unknown-linux-gnu.tar.gz` |
| Windows x86-64 MSVC | `bytepleat-0.5.1-x86_64-pc-windows-msvc.zip` |

Native CI builds, tests, and package execution passed on all three targets. See [release notes](RELEASE.md) for the tested runner baselines. Other OS versions and architectures are outside that verification; there is no Linux ARM64 CLI package.

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

```sh
bytepleat compress report.pdf
bytepleat test report.pdf.zst
bytepleat decompress report.pdf.zst -o report-restored.pdf

bytepleat pack project -o project.tar.zst
bytepleat test project.tar.zst
bytepleat unpack project.tar.zst -o project-restored
```

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

## Desktop app (alpha)

A desktop window for everyday archive work, built on the same bounded archive engine as the CLI. It uses your system's file dialogs and has three views:

- **Create:** choose files or a folder, pick a format, and save a new archive.
- **Extract:** unpack one archive into a new folder. The desktop app never overwrites an existing file or folder; the CLI does so only with `--force` on a named output file.
- **Inspect:** list an archive's entries without extracting, then tick entries and choose **Extract selected** to carry them to the Extract tab. Listing does not verify file contents. ZIP and 7z are listed from their metadata; a compressed tar can only be listed by fully decoding it into private temporary staging, which is removed afterwards. Extracting selected entries decodes the whole archive again before keeping the ones you chose.

There is no desktop installer yet; the packages under [Install](#install) are the CLI release. To try the alpha, build it from source (Rust 1.93 or newer, Node.js/npm and the [Tauri v2 prerequisites](https://v2.tauri.app/start/prerequisites/)):

```sh
cd desktop
npm install --ignore-scripts
npm run tauri -- dev
```

Desktop operations are capped at 1 GiB of output and 100,000 entries; listings preview up to 5,000 entries. ZIP is classic Stored/Deflate only, 7z is a bounded subset, and compressed tar uses Zstandard, gzip or LZ4. RAR, password-protected archives and ZIP64 are not supported. See [supported formats](docs/formats.md).

### Desktop validation

Platform validation is incomplete. These are desktop results from specific sessions, not a claim of support for every OS version or architecture; the [desktop validation record](docs/desktop-validation.md) has the exact scope, versions, open items, and the matching build, package, and Rust CI runs.

At merged source `d1ed936`, the [desktop workflow](https://github.com/megasoft1978/bytepleat/actions/runs/38770917796) passed app builds/tests on macOS ARM64, Linux x64, and Windows x64, compiled the Windows ARM64 app and adapters, and passed Windows x64/ARM64 MSIX package checks. It also installed the normal Linux development `.deb` under private D-Bus and Xvfb and captured a rendered, nonblank Bytepleat window. That proves packaged window rendering on Ubuntu 24.04 x64; it does not test a GNOME desktop session or archive workflows. The latest [native WebView smoke](https://github.com/megasoft1978/bytepleat/actions/runs/38766872361) exercised the app UI on macOS ARM64, Linux x64/ARM64, and Windows x64/ARM64; on Windows it checked create, extract, and open startup arguments. CI still does not establish interactive Finder, Explorer, Nautilus, or Dolphin menu behavior or signed public installers. Per-platform detail:

| Platform | What has been checked |
| --- | --- |
| macOS 27.0.1 · Apple silicon | Interactive GUI runs of create, inspect, selected and full extraction, overwrite refusal, cancellation, and selected Finder handoffs. Unsigned local build, not notarized. macOS 13 (the bundle minimum) is unverified. |
| Ubuntu 24.04.5 · ARM64 | Interactive runs in XFCE/Xorg and GNOME/Xorg, including Nautilus and Dolphin handoffs. On GNOME, cancellation, overwrite refusal, and selected extraction passed on an earlier package and have not been repeated on the installed v10 package. The latest Ubuntu 24.04 x64 `.deb` was installed and its window rendered under Xvfb in CI; this is not a fresh GNOME workflow test. Wayland and Kubuntu are unverified. |
| Windows | Native WebView E2E on x64 and ARM64; MSIX schema and payload checks; Windows 11 ARM64 test-package install, alias registration, and Explorer-command COM activation and argument handoff. Interactive Explorer menu behavior and signed public installers remain unverified. |

The interactive Linux desktop checks above were on ARM64; the Linux CLI package is x86-64, tested separately by CI. See [desktop/README.md](desktop/README.md) for build notes and limitations.

## Supported formats

| Format | Single-file streams | Folder archive | Notes |
| --- | --- | --- | --- |
| Zstandard, gzip, LZ4 | Compress and decompress | Compressed tar | Byte-stream codecs; presets available for Zstandard and gzip |
| ZIP | — | Create, inspect, test, and extract a supported subset | Stored and Deflate entries |
| 7z | — | Create, inspect, test, and extract a bounded subset | LZMA2; compatibility limits apply |
| Pco | Typed numeric streams | — | CLI-only typed stream; raw little-endian values, explicit type required; not arbitrary files or CSV |

RAR can be identified for metadata display but is not decoded. See [supported formats](docs/formats.md) for exact compatibility boundaries and [compression research](docs/compression-research.md) for the evidence behind codec and format decisions.

Archive contents preserve file bytes and relative paths within the supported scope. Permissions, ownership, links, extended attributes, and portable timestamps are not restored. `test` checks decoding and format integrity; `info` reads metadata. Neither authenticates the sender or scans for malware. See [security and limits](docs/security-limits.md) for extraction checks, default caps, and publication behavior.

## Project

- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Security reporting](SECURITY.md)
- [Support](SUPPORT.md)
- [Release notes and verification](RELEASE.md)
- [Benchmark results and reproduction](docs/benchmarks.md)
- [GitHub repository](https://github.com/megasoft1978/bytepleat)
- [Project website](https://megasoft1978.github.io/bytepleat/)

## License

Bytepleat is [MIT licensed](LICENSE). Dependencies retain their own licenses; see [THIRD-PARTY.json](THIRD-PARTY.json) and the [vendored dependency notes](vendor/README.md).
