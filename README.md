# Bytepleat

Compress files, pack folders, and restore the same bytes, using standard formats.

[![CI](https://github.com/megasoft1978/bytepleat/actions/workflows/ci.yml/badge.svg)](https://github.com/megasoft1978/bytepleat/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/megasoft1978/bytepleat)](LICENSE)
[![Release](https://img.shields.io/github/v/release/megasoft1978/bytepleat)](https://github.com/megasoft1978/bytepleat/releases)

## Why Bytepleat

- Uses established formats (Zstandard, gzip, LZ4, ZIP, 7z, tar). It does not add a proprietary archive format.
- Runs on your device. Your input files are never moved or removed.
- Careful file handling: output is written to a temporary file first, nothing is overwritten by default, and extraction goes into a new folder.
- One command-line tool for byte streams and folder archives, with a `test` command that fully decodes an archive before you extract it.

### When to use something else

- You need RAR, encrypted or password-protected archives, ZIP64, or arbitrary 7z files. See [supported formats](docs/formats.md).
- You need a full filesystem backup. Permissions, ownership, links, extended attributes, and timestamps are not restored.
- You already rely on 7-Zip, `tar`, or `zstd` and they do what you need. They are mature, widely available tools; Bytepleat is a smaller, stricter alternative.

## Install

Release 0.5.1 packages are on the [releases page](https://github.com/megasoft1978/bytepleat/releases). Download the archive and its matching `.sha256` file from the same release, verify it, then extract it. Packages are unsigned and the macOS build is not notarized. More detail is in [RELEASE.md](RELEASE.md).

**macOS (Apple silicon)**

```sh
shasum -a 256 -c bytepleat-0.5.1-aarch64-apple-darwin.tar.gz.sha256
tar -xzf bytepleat-0.5.1-aarch64-apple-darwin.tar.gz
./bytepleat-0.5.1-aarch64-apple-darwin/bytepleat --help
```

**Linux (x86-64)**

```sh
sha256sum -c bytepleat-0.5.1-x86_64-unknown-linux-gnu.tar.gz.sha256
tar -xzf bytepleat-0.5.1-x86_64-unknown-linux-gnu.tar.gz
./bytepleat-0.5.1-x86_64-unknown-linux-gnu/bytepleat --help
```

**Windows (x86-64, PowerShell)**

Needs the x64 [Microsoft Visual C++ v14 runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist), which is not bundled.

```powershell
$asset = 'bytepleat-0.5.1-x86_64-pc-windows-msvc.zip'
$entry = Get-Content -LiteralPath "$asset.sha256" -Raw
if ($entry -notmatch '^([0-9a-fA-F]{64})\s+bytepleat-0\.5\.1-x86_64-pc-windows-msvc\.zip\s*$') { throw 'Invalid checksum sidecar or filename' }
if ((Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash -ne $Matches[1]) { throw 'SHA-256 mismatch' }
Expand-Archive -LiteralPath $asset -DestinationPath .
.\bytepleat-0.5.1-x86_64-pc-windows-msvc\bytepleat.exe --help
```

Add the extracted folder to your `PATH` to run `bytepleat` from anywhere. There is no Linux ARM64 CLI package.

**From source with Cargo** (Rust 1.93 or newer and a C compiler toolchain):

```sh
cargo install --locked --git https://github.com/megasoft1978/bytepleat --tag v0.5.1
```

## Quick start

```sh
bytepleat compress report.pdf && bytepleat decompress report.pdf.zst -o report-restored.pdf
bytepleat pack project -o project.tar.zst && bytepleat unpack project.tar.zst -o project-restored
bytepleat info project.tar.zst --json    # read metadata
bytepleat test project.tar.zst           # fully decode and check
```

Zstandard is the default; use `--format` for another codec or archive type. See the [user guide](docs/user-guide.md) for presets, pipes, and archive options.

## Supported formats

| Format | Write | Read and test | Limits |
| --- | --- | --- | --- |
| Zstandard, gzip (single file) | Yes | Yes | Only Zstandard uses multiple threads |
| LZ4 (single file) | Yes | Yes | Concatenated LZ4 frames are rejected |
| tar + Zstandard, gzip, or LZ4 (folder) | Yes | Yes | `pack` needs a directory; regular files and directories only |
| ZIP | Yes | Yes | Classic Stored/Deflate only; no ZIP64, encryption, or split volumes; up to 65,534 entries |
| 7z | Yes | Yes | Writer uses LZMA2; reader handles a bounded subset, unencrypted and single-volume; up to 100,000 entries |
| Pco (numeric data) | Yes | Yes | Raw little-endian numbers with an explicit `--type`; not for general files or CSV |
| RAR | No | No | Recognized by `info` only |

Details and exact boundaries: [docs/formats.md](docs/formats.md).

## Safety behavior

- Input files are never modified, moved, or removed.
- Named outputs are written to a temporary file and published after success. An existing output is an error unless you pass `--force`.
- Output to stdout is a stream and can be partial if an error occurs; use a named output for all-or-nothing results.
- Extraction requires a new destination folder, validates in staging first, and accepts only regular files and directories. Links, special files, and unsafe paths are rejected. Publishing many files is best-effort, not atomic.
- Default caps: 1 GiB of decoded output, 100,000 archive entries, path depth 64, 128 MiB Zstandard window. Some can be changed with options.
- `test` checks decoding and format integrity. Neither `test` nor `info` verifies who sent a file or scans for malware.

See [security and limits](docs/security-limits.md).

## Desktop app (alpha)

A desktop window for creating, extracting, and inspecting archives (ZIP, 7z, and compressed tar). It is an early alpha with no installer; build it from source (Rust 1.93 or newer, Node.js/npm, and the [Tauri v2 prerequisites](https://v2.tauri.app/start/prerequisites/)):

```sh
cd desktop
npm install --ignore-scripts
npm run tauri -- dev
```

Platform testing is incomplete. See [docs/desktop-validation.md](docs/desktop-validation.md) for what has and has not been checked, and [desktop/README.md](desktop/README.md) for the contributor guide.

## Build and contribute

```sh
git clone https://github.com/megasoft1978/bytepleat.git
cd bytepleat
cargo build --release --locked
```

The binary is `target/release/bytepleat` (`.exe` on Windows). Before opening a pull request, run the checks in [CONTRIBUTING.md](CONTRIBUTING.md). Other links: [changelog](CHANGELOG.md), [security reporting](SECURITY.md), [support](SUPPORT.md), [release notes](RELEASE.md), [benchmarks](docs/benchmarks.md), [project website](https://megasoft1978.github.io/bytepleat/).

## License

Bytepleat is [MIT licensed](LICENSE). Dependencies keep their own licenses; see [THIRD-PARTY.json](THIRD-PARTY.json) and the [vendored dependency notes](vendor/README.md).
