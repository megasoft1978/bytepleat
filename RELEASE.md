# Release 0.5.0

Arqlet 0.5.0 is the first public release, based on reviewed stable 0.3.1. The version and name change cover branding, CLI identity, packaging, and release experience; there is no new compression algorithm.

## Download and verify

Release assets are pending publication. The planned assets are:

| Platform | Archive | Individual checksum sidecar |
| --- | --- | --- |
| macOS Apple silicon | `arqlet-0.5.0-aarch64-apple-darwin.tar.gz` | `arqlet-0.5.0-aarch64-apple-darwin.tar.gz.sha256` |
| Linux x86-64 | `arqlet-0.5.0-x86_64-unknown-linux-gnu.tar.gz` | `arqlet-0.5.0-x86_64-unknown-linux-gnu.tar.gz.sha256` |
| Windows x86-64 | `arqlet-0.5.0-x86_64-pc-windows-msvc.zip` | `arqlet-0.5.0-x86_64-pc-windows-msvc.zip.sha256` |

Download the archive for your platform and its matching `.sha256` sidecar from the same release. Each sidecar contains the SHA-256 digest followed by that exact archive filename. Verify from the directory containing both files; these commands compare only the selected archive, so they work when assets for other platforms are not downloaded.

macOS (Apple silicon):

```sh
shasum -a 256 -c arqlet-0.5.0-aarch64-apple-darwin.tar.gz.sha256
```

Linux (x86-64):

```sh
sha256sum -c arqlet-0.5.0-x86_64-unknown-linux-gnu.tar.gz.sha256
```

Windows PowerShell (x86-64):

```powershell
$asset = 'arqlet-0.5.0-x86_64-pc-windows-msvc.zip'
$sidecar = "$asset.sha256"
$entry = Get-Content -LiteralPath $sidecar -Raw
if ($entry -notmatch '^([0-9a-fA-F]{64})\s+arqlet-0\.5\.0-x86_64-pc-windows-msvc\.zip\s*$') { throw 'Invalid checksum sidecar or filename' }
$expected = $Matches[1]
$actual = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw 'SHA-256 mismatch' }
'SHA-256 verified'
```

The release may also include aggregate `SHA256SUMS` for all three archives. It is useful when you have downloaded all listed archives; do not use its all-assets check as the installation check for a single platform, because the other archive files may not be present. A checksum detects accidental corruption when compared with the sidecar; it is not a signature and does not establish who built the archive.

## Extract and run

Each archive contains a top-level directory named after the archive without its final extension. For example, the macOS archive contains `arqlet-0.5.0-aarch64-apple-darwin/`, and the executable is `arqlet` directly inside it. The Linux archive has the analogous target-named directory and root `arqlet`; the Windows ZIP contains `arqlet-0.5.0-x86_64-pc-windows-msvc/arqlet.exe`.

Extract using Finder/Archive Utility, your Linux archive manager or `tar -xzf <archive>`, or File Explorer/`Expand-Archive` on Windows. From the extracted directory, run `./arqlet --help` on macOS/Linux or `./arqlet.exe --help` in PowerShell. The package preserves the executable bit on Unix files. To run `arqlet` without a directory prefix, add the extracted directory (the one containing the executable) to your `PATH`.

The hosted native CI checks cover macOS Apple silicon and Linux x86-64 and have passed. The Windows x86-64 MSVC job is still being repaired after a compiler failure; Windows CI and runtime are not yet verified. These target checks do not establish support on every OS version or machine. Packages are unsigned, and the macOS build is not notarized.

## Build from source

With a Rust toolchain installed, build the checked-out release source using the lockfile:

```sh
cargo build --release --locked
```

The binary is `target/release/arqlet` (or `target/release/arqlet.exe` on Windows). Once the `v0.5.0` tag is published, install from the repository with the locked dependency versions:

```sh
cargo install --locked --git https://github.com/megasoft1978/arqlet --tag v0.5.0
```

The tag and install are not available until publication. Rust 1.93 or newer is required. The release adds no compression codec; Arqlet continues to read and write established formats.
