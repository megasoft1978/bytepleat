# Desktop internals

How Bytepleat Desktop works behind the interface, for contributors. For build and run steps see [desktop/README.md](../desktop/README.md). Test evidence is in [desktop-validation.md](desktop-validation.md).

## Worker and staging

- The interface supervises a child process of its own executable. The child receives a bounded JSON request and writes progress and result JSON inside a unique private staging directory.
- Published results are moved from staging only after a successful worker exit. Existing destinations fail instead of being overwritten. Inputs are not moved or removed.
- Creating from a multi-selection stages copies so each selected item's basename appears in the archive; this adds I/O and storage overhead. A single selected directory archives its contents.
- Extraction uses the selected parent folder and creates a sibling subfolder named after the archive plus `-extracted`. The chosen location must not already contain that name.
- Opening an archive shows a bounded listing; listing does not validate contents. Extraction decodes into private staging before publication. Selecting entries still decodes the whole archive before keeping the selected ones, so it is not random access.

## Broker and job control

- One operation runs at a time. The interface disables new work while a job is active, and the broker also rejects concurrent requests.
- Archive inspection runs in the same managed child worker and broker slot, including the full-decode listing of compressed tar. It can be cancelled, and it is killed, reaped, and cleaned up on app shutdown.
- Inspection returns a size-bounded preview with the total entry count and an explicit truncation flag, and never publishes output. Cancelling an inspection is shown as a cancelled job and keeps no partial listing.
- Jobs are kept in a bounded history.
- Closing the app cancels and reaps its owned worker before exit, removing its private staging directory without publishing.
- The one-active-job rule and the shutdown reservation are covered by backend regression tests.

## Limits and paths

- The desktop uses the engine's fixed 1 GiB decoded-output and 100,000-entry limits. Listings preview at most 5,000 entries. Exceeding an operation limit fails before output is published, and worker validation errors appear in the job history.
- Native file paths enter the UI as UTF-8 strings. A selection containing a path that cannot be represented as UTF-8 is rejected in full with an error; it is never silently shortened. The underlying Rust CLI worker uses OS paths.
- Windows file association launches may pass paths directly without flags; these are treated as archive-open selections. Unknown command-line options are rejected.

## File associations

The bundle declares `.zip`, `.7z`, `.tar.zst`, `.tar.gz`, and `.tar.lz4`. OS registration depends on the installer and platform. The declarations do not promise support for other archive formats. The macOS bundle minimum is set to 13.0.

## Validation history

The full record, with versions, run links, and open items, is in [desktop-validation.md](desktop-validation.md). Summary of scope:

- macOS 27.0.1 ARM64: GUI workflows and selected Finder Service handoffs exercised. The tested build was unsigned and ad-hoc signed only, not Developer ID signed or notarized.
- Ubuntu 24.04.5 ARM64: XFCE/Xorg passed full GUI extraction and refusal/recovery checks, plus Nautilus 46.4 and Dolphin 23.08.5 Compress/Extract handoffs. GNOME/Xorg passed broader v6 GUI workflows; on the v10 unsigned ARM64 development package, one cold and ten warm Nautilus Open With launches reached the foreground with only the requested ZIP selected. A cold Nautilus Compress made a ZIP that passed `unzip -t`; cold Extract produced byte-for-byte matching contents in a fresh folder. GNOME cancellation, overwrite refusal, and selected extraction passed on the earlier v6 package and have not been repeated on v10; the current CI source builds the Linux x64 development `.deb` reproducibly and launches its rendered window under private D-Bus/Xvfb (a package-startup smoke, not an installed GNOME workflow check).
- Not verified: Kubuntu 26.04, Windows interactive behavior, macOS 13 minimum-version behavior, macOS Dock Quit cleanup.
- Native macOS and Ubuntu ARM64 checks cover 5,000-of-40,001-item TAR previews, inspection cancellation, and app/window close during inspection, with independent worker-exit and staging-removal observations.

These results establish only the stated session scope.

### Local verification of the inspection worker change

`cargo fmt --all -- --check`, `cargo clippy --locked --all-targets -- -D warnings`, and `cargo test --locked` were run in both `desktop/core` and `desktop/src-tauri`; `node --check desktop/ui/app.js` was also run. These checks do not replace native GUI verification.
