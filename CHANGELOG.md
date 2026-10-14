# Changelog

## 0.5.0 — initial public Bytepleat release

Bytepleat 0.5.0 is the first public release of the reviewed stable 0.3.1 product line under its new name. This release changes product branding, command-line identity, packaging, and release documentation. It adds no compression algorithm or codec.

Supported behavior remains the established-format functionality described in the [format guide](docs/formats.md): byte streams, tar-based folder archives, classic ZIP, bounded 7z, and explicitly typed standalone Pco. See [security and limits](docs/security-limits.md) for archive and metadata constraints.

Native macOS Apple silicon, Linux x86-64 GNU, and Windows x86-64 MSVC CI builds, tests, and package execution passed. Release packages include checksums and target dependency inventories. Packages are unsigned; macOS builds are not notarized.
