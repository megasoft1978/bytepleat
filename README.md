# Arqlet

Arqlet is an open-source Rust command-line file and folder archiver. It reads and writes established formats and restores the original file bytes; it does not introduce a new compression algorithm.

**Initial public release:** 0.5.0, based on the reviewed stable 0.3.1 line. Version 0.5.0 updates the product name, command-line identity, packaging, and release experience. It does not add a codec.

## Install

**Downloads:** [Arqlet releases](https://github.com/megasoft1978/arqlet/releases) — release assets are pending publication. The planned packages are `arqlet-0.5.0-<Rust target>.tar.gz` for macOS/Linux and `arqlet-0.5.0-<Rust target>.zip` for Windows, with `SHA256SUMS` alongside them. Use only an asset matching your operating system and Rust target triple. Packages are unsigned and macOS builds are not notarized.

**Build from source** (Rust 1.93 or newer required):

```sh
git clone https://github.com/megasoft1978/arqlet.git
cd arqlet
cargo build --release --locked
```

The executable is `target/release/arqlet` (`target/release/arqlet.exe` on Windows).

**Install from the Git tag** once v0.5.0 is published:

```sh
cargo install --locked --git https://github.com/megasoft1978/arqlet --tag v0.5.0
```

## Quick start

Arqlet writes a Zstandard byte stream by default. These examples use a shell on macOS/Linux:

```sh
arqlet compress report.pdf                 # creates report.pdf.zst
arqlet decompress report.pdf.zst -o report-restored.pdf
arqlet test report.pdf.zst                 # fully decode and validate
arqlet pack photos -o photos.tar.zst       # archive a directory
arqlet unpack photos.tar.zst -o photos-out
arqlet info photos.tar.zst --json          # inspect bounded metadata
```

Windows PowerShell uses the same commands and options; substitute paths as needed. For a directory with ZIP compatibility:

```powershell
arqlet pack .\photos --format zip -o .\photos.zip
arqlet unpack .\photos.zip -o .\photos-out
```

Arqlet never removes the input. Named output files are staged and published after successful completion; an existing output is an error unless `--force` is given. Extraction requires a new destination directory. Output to stdout can be partial if a stream operation fails; use a named output when you need all-or-nothing file publication.

See the [user guide](docs/user-guide.md) for pipes, archive options, and numeric buffers, and [supported formats](docs/formats.md) for the precise compatibility boundaries.

## Supported formats at a glance

- Byte streams: Zstandard, gzip, LZ4 frames, and explicitly typed standalone Pco.
- Folder archives: standard tar carried by Zstandard, gzip, or LZ4; classic ZIP Stored/Deflate; and a bounded 7z subset written with LZMA2.
- RAR is recognized for information display but is not decoded by Arqlet. An external tool may be used separately.

Arqlet does not create a full filesystem backup image. It does not preserve permissions, ownership, links, extended attributes, or portable timestamps. Consult [security and limits](docs/security-limits.md) before processing untrusted archives.

## Project

- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Security reporting](SECURITY.md)
- [Support](SUPPORT.md)
- [Release notes and verification](RELEASE.md)
- [GitHub repository](https://github.com/megasoft1978/arqlet)
- [Project website](https://megasoft1978.github.io/arqlet/)

## License

Arqlet is [MIT licensed](LICENSE). Dependencies retain their own licenses; see [THIRD-PARTY.json](THIRD-PARTY.json) and the [vendored dependency notes](vendor/README.md).
