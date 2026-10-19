# Trying Bytepleat Desktop

**Status: desktop alpha, not a beta-ready consumer download.** As of 2026-10-19,
the downloadable release is the Bytepleat CLI 0.5.2. There is no published
desktop installer. Desktop builds and platform validation are still in
progress. The current evidence and its exact limits are in the
[desktop validation record](desktop-validation.md).

## What you can download

The [0.5.2 release page](https://github.com/megasoft1978/bytepleat/releases/tag/v0.5.2)
has CLI archives for macOS Apple silicon, Linux x86-64, and Windows x86-64.
The archives are unsigned; the macOS CLI is not notarized. Verify the matching
SHA-256 sidecar before extracting. A checksum detects accidental corruption; it
does not authenticate the publisher. See the root [README](../README.md) for
download links, checksums, and platform-specific commands.

There is no desktop download to install. To evaluate the desktop alpha, build
and run it from a source checkout. This requires Rust 1.93 or newer, Node.js/npm,
and the [Tauri v2 prerequisites](https://v2.tauri.app/start/prerequisites/) for
your operating system. From the repository root:

```sh
cd desktop
npm install --ignore-scripts
npm run tauri -- dev
```

This is a developer workflow, not a packaged beta. Builds and integrations are
unsigned development artifacts. Your operating system may warn about an
unidentified or untrusted app. Do not bypass a warning unless you built the
program yourself from source you trust. No signing or notarization is provided
by this guide.

## A safe first session

Use copies of ordinary, non-sensitive test files. Keep the originals and make
the output path easy to inspect. The app processes files locally, but it does
not scan archives for malware or establish who created them.

1. **Create:** choose Create, add a few test files or a folder, choose ZIP, 7z,
   TAR+Zstandard, TAR+gzip, or TAR+LZ4, then choose a new output path and create
   the archive. The app refuses to replace an existing output. Confirm the new
   archive appears at the chosen path; the input files should remain unchanged.
2. **Inspect:** choose Inspect and select the archive. The app lists archive
   entries and a bounded preview (up to 5,000 entries). Inspection is a listing,
   not a full integrity check. TAR inspection decodes into private temporary
   staging. Use a trusted archive if you do not want to spend time or disk space
   on untrusted input.
3. **Extract:** choose Extract and select the archive. Extract everything, or
   use Inspect to select entries and continue to the selected-extraction review.
   Choose a new destination folder. The destination must not already exist; the
   app refuses overwrite. Compare extracted files with your test inputs.
4. **Cancel:** during a long create, extract, or inspect operation, use Cancel.
   The UI should report cancellation, stop the active work, and remove temporary
   staging/output rather than publish a partial final result. Cancellation and
   cleanup have passed in documented macOS and Linux runs; do not assume every
   platform and operation has the same level of GUI validation yet.

Completed operations show a result and output location. Failed operations show
an error in the active workflow and job history. Inputs are not moved or
removed. Extracted regular-file contents and relative paths are restored;
permissions, ownership, links, extended attributes, and portable timestamps are
not preserved. Multi-file extraction publication is best-effort rather than an
atomic directory transaction.

## Supported subset and limits

- Create, inspect, and extract ZIP, 7z, TAR+Zstandard, TAR+gzip, and TAR+LZ4.
- No encrypted/password-protected archives, ZIP64, split volumes, or RAR
  extraction. 7z reading is bounded and does not support every coder graph or
  codec. ZIP is classic ZIP using Stored or Deflate.
- Default decoded output cap is 1 GiB per operation; archive metadata is capped
  at 100,000 entries, and inspect previews at most 5,000 entries.
- One operation runs at a time. Selective extraction decodes the archive before
  publishing selected files. A selected path that is not valid UTF-8 is
  rejected.
- Only regular files and directories are extracted. Unsafe paths, links, and
  special files are rejected.

See [supported formats](formats.md), [security and limits](security-limits.md),
and [desktop behavior details](desktop-internals.md) for the complete
boundaries. The desktop app is not a full filesystem backup tool.

## Integrations and removal

The source-run app itself has no consumer installer or one-click uninstaller.
Quit it and remove the source checkout/build artifacts you created when you
finish. If you separately installed an optional per-user integration, remove
that integration using its matching script:

- Linux file-manager actions: from the repository root run
  `python3 desktop/scripts/install-linux-integrations.py --uninstall`.
- macOS Finder Services: run
  `desktop/scripts/uninstall-macos-services.sh` from the repository root.

These commands remove only the integration files owned by those installers;
they do not uninstall a separately installed app bundle. Windows Explorer
integration is not a consumer install path. See the
[integration notes](../desktop/integrations/README.md) before enabling any
optional shell integration.

## Report a useful bug

Use the repository's [bug report form](https://github.com/megasoft1978/bytepleat/issues/new?template=bug_report.yml).
Include:

- OS version, CPU architecture, desktop environment/window system, and whether
  this was a source run or a locally built package.
- The exact app version or source commit, and build/run command.
- Which action you used (Create, Inspect, Extract, or Cancel), the selected
  format, approximate input and output sizes, and the steps to reproduce.
- The exact error text and relevant job-history text. Say whether a final output
  or temporary staging directory remained.
- For correctness reports, a small synthetic or public fixture and checksums
  before/after, if you can share them safely. Do not attach private archives,
  personal files, credentials, or sensitive paths; redact usernames from logs.

Do not report archive contents you are not authorized to share. Inspection does
not validate all payload bytes, and successful extraction is not a malware scan.

## Validation still needed

The validation record contains platform- and build-specific evidence; CI and a
single successful run do not establish broad OS support. Current gaps include
interactive Windows installed-app workflows and Explorer behavior, Windows
x64 installed-app coverage, fresh validation of the latest source as an
installed Linux package, and remaining Wayland/Kubuntu checks. Some older GUI
observations apply only to earlier package builds. Signing and notarization are
also not complete. Treat the desktop as an experimental alpha and keep backups
of important data.
