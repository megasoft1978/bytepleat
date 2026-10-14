# Release 0.5.0

Bytepleat 0.5.0 is the first public release, based on reviewed stable 0.3.1. The version and name change cover branding, CLI identity, packaging, and release experience; there is no new compression algorithm.

## Download and verify

The release workflow publishes these packages after native execution checks:

| Platform | Archive | Individual checksum sidecar |
| --- | --- | --- |
| macOS Apple silicon | `bytepleat-0.5.0-aarch64-apple-darwin.tar.gz` | `bytepleat-0.5.0-aarch64-apple-darwin.tar.gz.sha256` |
| Linux x86-64 | `bytepleat-0.5.0-x86_64-unknown-linux-gnu.tar.gz` | `bytepleat-0.5.0-x86_64-unknown-linux-gnu.tar.gz.sha256` |
| Windows x86-64 | `bytepleat-0.5.0-x86_64-pc-windows-msvc.zip` | `bytepleat-0.5.0-x86_64-pc-windows-msvc.zip.sha256` |

Download the archive for your platform and its matching `.sha256` sidecar from the same release. Each sidecar contains the SHA-256 digest followed by that exact archive filename. Verify from the directory containing both files; these commands compare only the selected archive, so they work when assets for other platforms are not downloaded.

macOS (Apple silicon):

```sh
shasum -a 256 -c bytepleat-0.5.0-aarch64-apple-darwin.tar.gz.sha256
```

Linux (x86-64):

```sh
sha256sum -c bytepleat-0.5.0-x86_64-unknown-linux-gnu.tar.gz.sha256
```

Windows PowerShell (x86-64):

```powershell
$asset = 'bytepleat-0.5.0-x86_64-pc-windows-msvc.zip'
$sidecar = "$asset.sha256"
$entry = Get-Content -LiteralPath $sidecar -Raw
if ($entry -notmatch '^([0-9a-fA-F]{64})\s+bytepleat-0\.5\.0-x86_64-pc-windows-msvc\.zip\s*$') { throw 'Invalid checksum sidecar or filename' }
$expected = $Matches[1]
$actual = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw 'SHA-256 mismatch' }
'SHA-256 verified'
```

The release may also include aggregate `SHA256SUMS` for all three archives. It is useful when you have downloaded all listed archives; do not use its all-assets check as the installation check for a single platform, because the other archive files may not be present. A checksum detects accidental corruption when compared with the sidecar; it is not a signature and does not establish who built the archive.

## Extract and run

Each archive contains a top-level directory named after the archive without its final extension. For example, the macOS archive contains `bytepleat-0.5.0-aarch64-apple-darwin/`, and the executable is `bytepleat` directly inside it. The Linux archive has the analogous target-named directory and root `bytepleat`; the Windows ZIP contains `bytepleat-0.5.0-x86_64-pc-windows-msvc/bytepleat.exe`.

Extract using Finder/Archive Utility, your Linux archive manager or `tar -xzf <archive>`, or File Explorer/`Expand-Archive` on Windows. From the extracted directory, run `./bytepleat --help` on macOS/Linux or `./bytepleat.exe --help` in PowerShell. The package preserves the executable bit on Unix files. To run `bytepleat` without a directory prefix, add the extracted directory (the one containing the executable) to your `PATH`.

Native package execution passed on macOS Apple silicon, Linux x86-64, and Windows x86-64 MSVC. The verified runner baselines were macOS 26.6.2 arm64, Ubuntu 24.04 with glibc 2.39, and Windows Server 2025 x86-64. These results do not establish compatibility with every OS version; older GNU/Linux systems may need a source build. Rust 1.93 locked checks and tests also passed on Linux. [Native CI evidence](https://github.com/megasoft1978/bytepleat/actions/runs/38601762226).

Packages are unsigned, and the macOS build is not notarized.

## Build from source

With Rust 1.93 or newer and a C compiler toolchain installed, build the checked-out release source using the lockfile:

```sh
cargo build --release --locked
```

The binary is `target/release/bytepleat` (or `target/release/bytepleat.exe` on Windows). Install the tagged source with the locked dependency versions:

```sh
cargo install --locked --git https://github.com/megasoft1978/bytepleat --tag v0.5.0
```

Rust 1.93 or newer and a C compiler toolchain are required. The release adds no compression codec; Bytepleat continues to read and write established formats.
