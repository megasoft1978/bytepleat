# Release 0.5.1

Bytepleat 0.5.1 is the clean initial supported release from the reviewed source export. Product behavior and codecs are unchanged; there is no new compression algorithm.

## Download and verify

The release workflow publishes these packages after native execution checks:

| Platform | Archive | Individual checksum sidecar |
| --- | --- | --- |
| macOS Apple silicon | `bytepleat-0.5.1-aarch64-apple-darwin.tar.gz` | `bytepleat-0.5.1-aarch64-apple-darwin.tar.gz.sha256` |
| Linux x86-64 | `bytepleat-0.5.1-x86_64-unknown-linux-gnu.tar.gz` | `bytepleat-0.5.1-x86_64-unknown-linux-gnu.tar.gz.sha256` |
| Windows x86-64 | `bytepleat-0.5.1-x86_64-pc-windows-msvc.zip` | `bytepleat-0.5.1-x86_64-pc-windows-msvc.zip.sha256` |

Download the archive for your platform and its matching `.sha256` sidecar from the same release. Each sidecar contains the SHA-256 digest followed by that exact archive filename. Verify from the directory containing both files; these commands compare only the selected archive, so they work when assets for other platforms are not downloaded.

macOS (Apple silicon):

```sh
shasum -a 256 -c bytepleat-0.5.1-aarch64-apple-darwin.tar.gz.sha256
```

Linux (x86-64):

```sh
sha256sum -c bytepleat-0.5.1-x86_64-unknown-linux-gnu.tar.gz.sha256
```

Windows PowerShell (x86-64):

```powershell
$asset = 'bytepleat-0.5.1-x86_64-pc-windows-msvc.zip'
$sidecar = "$asset.sha256"
$entry = Get-Content -LiteralPath $sidecar -Raw
if ($entry -notmatch '^([0-9a-fA-F]{64})\s+bytepleat-0\.5\.0-x86_64-pc-windows-msvc\.zip\s*$') { throw 'Invalid checksum sidecar or filename' }
$expected = $Matches[1]
$actual = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw 'SHA-256 mismatch' }
'SHA-256 verified'
```

The release may also include aggregate `SHA256SUMS` for all three archives. It is useful when you have downloaded all listed archives; do not use its all-assets check as the installation check for a single platform, because the other archive files may not be present. A checksum detects accidental corruption when compared with the sidecar; it is not a signature and does not establish who built the archive.

The Windows package requires the x64 [Microsoft Visual C++ v14 runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist); it is not bundled. If Windows reports `VCRUNTIME140.dll` missing, install the current x64 redistributable from Microsoft.

## Extract and run

Each archive contains a top-level directory named after the archive without its final extension. For example, the macOS archive contains `bytepleat-0.5.1-aarch64-apple-darwin/`, and the executable is `bytepleat` directly inside it. The Linux archive has the analogous target-named directory and root `bytepleat`; the Windows ZIP contains `bytepleat-0.5.1-x86_64-pc-windows-msvc/bytepleat.exe`.

Extract using Finder/Archive Utility, your Linux archive manager or `tar -xzf <archive>`, or File Explorer/`Expand-Archive` on Windows. From the extracted directory, run `./bytepleat --help` on macOS/Linux or `./bytepleat.exe --help` in PowerShell. The package preserves the executable bit on Unix files. To run `bytepleat` without a directory prefix, add the extracted directory (the one containing the executable) to your `PATH`.

Fresh native CI for 0.5.1 is pending on macOS Apple silicon, Linux x86-64, and Windows x86-64 MSVC. Platform support and package execution status will be updated after those checks complete.

Packages are unsigned, and the macOS build is not notarized.

## Build from source

With Rust 1.93 or newer and a C compiler toolchain installed, build the checked-out release source using the lockfile:

```sh
cargo build --release --locked
```

The binary is `target/release/bytepleat` (or `target/release/bytepleat.exe` on Windows). Install the tagged source with the locked dependency versions:

```sh
cargo install --locked --git https://github.com/megasoft1978/bytepleat --tag v0.5.1
```

Rust 1.93 or newer and a C compiler toolchain are required. The release adds no compression codec; Bytepleat continues to read and write established formats.
