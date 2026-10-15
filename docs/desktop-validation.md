# Desktop validation status

Bytepleat Desktop is an alpha under validation, not a consumer release. This
record separates interactive GUI evidence from build/test results and package
inspection. Correctness in a GUI workflow says nothing about compression speed
or size; use the existing measured CLI results in the [archive benchmark
report](benchmarks.md) for performance, with
their stated scope and limitations.

## Interactive validation

### macOS 27.0.1 · ARM64

Verified in a native GUI session:

- Created and saved a ZIP through the actual save dialog; independently checked
  both file hashes and restoration of an empty directory.
- Opened a four-entry archive, extracted only the selected Japanese-named file,
  and completed full extraction.
- Refused overwrite. Cancelling a 96 MiB 7z operation left neither a final
  output nor a private staging directory.
- Finder Compress via Services passed with a warm app and selected input
  folder; Finder Extract via Services passed with a cold app and selected ZIP.

Finder Open With cold launch passed with the generated ZIP. Finder Services
also forwarded a two-file selection to Create with both exact paths. The native
file picker accepted a generated input via keyboard Go to Folder navigation.
Quit cleanup during an active operation remains pending. The local
app was unsigned/ad-hoc signed; this is not Developer ID signing or notarization.
The bundle's macOS 13 minimum is metadata only; macOS 13 runtime behavior is
unverified.

### Ubuntu 24.04.5 · ARM64 · XFCE/Xorg

The native GUI session created a ZIP through the GTK save dialog. Independent
checks matched both file hashes and the empty directory. The app opened the
folder, handed off archive opening, and showed four entries with its
listing-only integrity notice. Selected extraction and full extraction passed;
the restored file hash and both directories independently matched the generated
input. An existing destination was refused without changing the retained paths
or file hash. Refusal/recovery is verified. Cancelling a 96 MiB 7z compression left no final
archive or staging directory.

Nautilus 46.4 and Dolphin 23.08.5 each passed right-click Compress with a warm
app and Extract with a cold app, forwarding the generated selection correctly.
The Nautilus creation selection included an accented folder name. These handoff
checks do not repeat every archive workflow through each menu. This XFCE/Xorg
session does not establish GNOME default-shell behavior or Kubuntu 26.04.

The installed `/usr/bin/bytepleat-desktop` package copy was also opened cold
through Nautilus Open With with “Always use” off. It listed four entries and
extracted the selected Japanese-named file; the exact output SHA-256 was
`291de3adfe866500865cc97d48754b76b09c00abb6fd1ebf31fde81af49f0621`.
This installed-copy GUI evidence covers that listing and selected extraction
flow. Separately, 21 installed-worker smoke checks passed across five formats
(round trips, selected extraction, and bounded rejections); those are
subprocess correctness checks, not GUI coverage of all formats. The installed
ELF SHA-256 was
`3165b8d6e48515401d1b8278151b468d9489c46b5bcd4eb75c790f5a2ebd08b5`.

### Ubuntu 24.04.5 · ARM64 · GNOME/Xorg

The installed package also rendered in the Ubuntu GNOME Xorg session. A cold
`--open` handoff displayed the generated ZIP, inspection listed four entries,
and selected extraction through the native GTK folder chooser completed.
Independent checks found only `nested/日本語.txt` and its parent directory;
the file matched the SHA-256 above. Repeating extraction refused the existing
destination. GNOME create, full extraction, cancellation, and context-menu
workflows still need separate interactive checks.

## Build and package evidence

At commit `f72200bae62953cf55cbc2d20f7182a70dd0c4fb`, all seven jobs passed in
public CI run [38646891788](https://github.com/megasoft1978/bytepleat/actions/runs/38646891788).
App/core checks passed on macOS ARM64, Linux x64, and Windows x64. Native x64
Explorer COM and quoting tests passed; the ARM64 Explorer adapter compiled,
but its native COM tests were skipped, so this is compile-only evidence. The
x64 and ARM64 MSIX jobs passed package schema/payload validation and reported
notices. The CI does not establish Windows installation or runtime behavior,
Explorer interaction in an installed app, or ARM64 runtime behavior.

The local unsigned ARM64 Debian development package v4 was built twice with
identical bytes (SHA-256
`17b1e9bb1c75330167c77f923dcd80e6da21eb7c7ad2c4ea4a4a06a397de4469`). It
contains 377 notice packages and 673 literal notice files, with zero literal
gaps; this is not legal clearance. The package upgrade installed successfully
on Ubuntu 24.04.5, and the installed executable retained the compiled ELF hash
above. No consumer desktop installer download is published.

## Remaining validation

- Verify macOS quit cleanup during an active operation; test the minimum
  supported macOS version.
- Separately verify Kubuntu 26.04 and its newer Dolphin/Plasma combination.
- Complete Windows 11 installation and Explorer interaction on x64 and ARM64;
  distinguish native runtime results from ARM64 cross-compilation and package
  schema/payload probes.
- Extend GNOME/Xorg checks beyond listing, selected extraction, and overwrite
  refusal. Package validation covers Ubuntu 24.04.5 ARM64, not other
  distributions or architectures.
- Qualify signed packages, including Developer ID/notarized macOS distribution
  and appropriate Windows signing.
- Expand interactive coverage across supported operating systems and archive
  formats. Existing GUI tests do not establish performance; no new codec or
  performance claim is made by this validation record.
