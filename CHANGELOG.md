# Changelog

## 0.5.1 — clean initial supported release

Bytepleat 0.5.1 is the clean initial supported release from the reviewed source export. It has the same product behavior and codecs as 0.5.0; no new compression algorithm or codec is introduced. A source-export guard now rejects tracked build output, nested release workspaces, and common private-path or credential patterns before CI builds begin. Fresh native macOS Apple silicon, Linux x86-64 GNU, and Windows x86-64 MSVC tests and package execution passed.

## 0.5.0 — withdrawn

Version 0.5.0 was withdrawn after the source export was found to contain nested build caches. Its public release and tag were withdrawn; use 0.5.1. The current release uses a clean source tree and fresh native verification.
