# Bytepleat

Compress files. Pack folders.

Bytepleat is a Rust command-line archiver for files and folders. Compress, pack, inspect, test, and restore through one consistent set of commands, using familiar formats and preserving the original file bytes.

```sh
bytepleat compress report.pdf
bytepleat test report.pdf.zst
bytepleat decompress report.pdf.zst -o report-restored.pdf

bytepleat pack project -o project.tar.zst
bytepleat test project.tar.zst
bytepleat unpack project.tar.zst -o project-restored
```

Your originals stay in place. Named outputs are published after successful completion, and unpacking requires a new destination directory. Built for scripts and everyday file workflows, Bytepleat puts format choice and file-handling behavior in your hands.

## Install

**Downloads:** [Bytepleat releases](https://github.com/megasoft1978/bytepleat/releases) — v0.5.0 assets are pending publication. The planned packages are `bytepleat-0.5.0-aarch64-apple-darwin.tar.gz` (macOS Apple silicon), `bytepleat-0.5.0-x86_64-unknown-linux-gnu.tar.gz` (Linux x86-64), and `bytepleat-0.5.0-x86_64-pc-windows-msvc.zip` (Windows x86-64). Choose the matching package and verify it with its adjacent `.sha256` file; see [release verification and extraction](RELEASE.md). Hosted macOS and Linux CI have passed. Windows compiler checks, tests, and 28 smoke cases pass, but archive interoperability is unresolved; Windows is not yet verified. Packages are unsigned and macOS builds are not notarized.

Each archive extracts into a same-named directory containing `bytepleat` (or `bytepleat.exe` on Windows) at its root. Run it from that directory as `./bytepleat --help` on macOS/Linux or `.\bytepleat.exe --help` in PowerShell; to invoke `bytepleat` from any directory, add the extracted directory to your `PATH`.

**Build from source** (Rust 1.93 or newer required):

```sh
git clone https://github.com/megasoft1978/bytepleat.git
cd bytepleat
cargo build --release --locked
```

The executable is `target/release/bytepleat` (`target/release/bytepleat.exe` on Windows).

**Install from the Git tag** once v0.5.0 is published (Rust 1.93 or newer required):

```sh
cargo install --locked --git https://github.com/megasoft1978/bytepleat --tag v0.5.0
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

## Supported formats at a glance

- Byte streams: Zstandard, gzip, LZ4 frames, and explicitly typed standalone Pco.
- Folder archives: standard tar carried by Zstandard, gzip, or LZ4; classic ZIP Stored/Deflate; and a bounded 7z subset written with LZMA2.
- RAR is recognized for information display but is not decoded by Bytepleat. An external tool may be used separately.

Bytepleat uses established compression algorithms. Archive contents preserve file bytes and relative paths, with full filesystem metadata outside the supported scope: permissions, ownership, links, extended attributes, and portable timestamps are not restored. `test` checks decoding and format integrity; `info` reads metadata. Neither authenticates the sender or scans for malware. See [security and limits](docs/security-limits.md) for extraction checks, default caps, and publication behavior.

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
