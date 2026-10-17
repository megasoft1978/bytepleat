# Changelog

## 0.5.2 (unreleased)

Bytepleat 0.5.2 is not published yet. ZIP archives made by bsdtar or Windows `tar.exe` with a bare `./` root directory entry now unpack; the traversal, absolute-path and duplicate-entry rules are unchanged (`src/archive_zip.rs`). Interrupting a pack with SIGINT, SIGTERM or SIGHUP now removes the staging file; this applies on Unix only, because Windows has no handler (`src/file_io.rs`). On Windows, the Explorer commands "Extract with Bytepleat" and "Open in Bytepleat" are now enabled for `.zip` files, since Explorer reports a `.zip` as a folder (`desktop/integrations/windows/src/ExplorerCommands.cpp`). The desktop app UI, the website and the README have been redesigned. The SIL Open Font License notices for the bundled fonts now ship in the package notices. `bytepleat pack` now infers the archive format from the `-o` extension when `--format` is omitted; a `--format` that conflicts with the extension is an error. The desktop window now opens at 960x640 (minimum 760x520) and shrinks to fit small screens.

## 0.5.1 — clean initial supported release

Bytepleat 0.5.1 is the clean initial supported release from the reviewed source export. It has the same product behavior and codecs as 0.5.0; no new compression algorithm or codec is introduced. A source-export guard now rejects tracked build output, nested release workspaces, and common private-path or credential patterns before CI builds begin. Fresh native macOS Apple silicon, Linux x86-64 GNU, and Windows x86-64 MSVC tests and package execution passed.

## 0.5.0 — withdrawn

Version 0.5.0 was withdrawn after the source export was found to contain nested build caches. Its public release and tag were withdrawn; use 0.5.1. The current release uses a clean source tree and fresh native verification.
