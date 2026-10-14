# Release 0.5.0

Arqlet 0.5.0 is the first public release, based on reviewed stable 0.3.1. The version and name change cover branding, CLI identity, packaging, and release experience; there is no new compression algorithm.

## Download and verify

Release assets are pending publication. Planned asset names are `arqlet-0.5.0-<Rust target>.tar.gz` on macOS/Linux and `arqlet-0.5.0-<Rust target>.zip` on Windows, plus `SHA256SUMS`. Download an asset only when its target triple matches the intended platform. The checksum file detects accidental corruption; it is not a signature and does not establish who built an asset.

After downloading the asset and `SHA256SUMS` from the same release, verify from the directory containing both files:

```sh
# macOS / Linux
shasum -a 256 -c SHA256SUMS
```

```powershell
# Windows PowerShell
$asset = Get-ChildItem .\arqlet-0.5.0-*.zip | Select-Object -First 1
$entry = Select-String -Path .\SHA256SUMS -SimpleMatch $asset.Name
if (-not $entry) { throw 'No checksum entry for this asset' }
$expected = ($entry.Line -split '\s+')[0]
$actual = (Get-FileHash $asset.FullName -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $expected) { throw 'SHA-256 mismatch' }
```

Replace `<Rust target>` with the exact target in the downloaded filename. Check that the checksum entry names that exact asset; do not compare a different platform package. Release assets are unsigned and macOS packages are not notarized.

## Build from source

With a Rust toolchain installed, build the checked-out release source using the lockfile:

```sh
cargo build --release --locked
```

The binary is `target/release/arqlet` (or `target/release/arqlet.exe` on Windows). Once the GitHub tag exists, Cargo installation is:

```sh
cargo install --locked --git https://github.com/megasoft1978/arqlet --tag v0.5.0
```

Hosted native CI is planned and pending. This document does not claim successful native macOS, Windows, or Linux CI execution.
