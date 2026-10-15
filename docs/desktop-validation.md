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

On 2026-10-15, the current desktop UI at commit `0d9a8a8` was rebuilt as an
isolated, unsigned macOS review app and exercised with a two-file ZIP. Full GUI
extraction completed and both restored files matched their inputs byte for
byte. A second extraction targeting an already-existing output directory was
refused; the directory remained empty. The test archive SHA-256 is
`c1ec09726227056e689011c155425281c28c7f2c56164627b9bf54d9e604806a`; the
review app executable SHA-256 is
`7f4cd56107b8839de71c96302ae952f4c440296f17f15200009d94b20aa27c92`. This
validates those workflows on macOS 27.0.1 ARM64 only and is not release-signing
or notarization evidence.

Finder Open With cold launch passed with the generated ZIP. Finder Services
also forwarded a two-file selection to Create with both exact paths. The native
file picker accepted a generated input via keyboard Go to Folder navigation.
The managed inspection build also listed a generated TAR+Gzip archive with
40,001 items, showing a bounded preview of 5,000. Cancelling inspection, Cmd+Q
during inspection, and closing the window during inspection each passed;
independent process/filesystem observation confirmed the owned worker exited
and its staging directory, including decoded scratch files, was removed. A
150,000-entry TAR also hit the engine's 100,000-entry limit; the desktop now
shows `archive entry limit exceeded` in the active workflow and retains the
specific cause in job history, instead of surfacing only a generic worker exit
code. The failed inspection left no Bytepleat staging directory. The latest
native UI observation and executable hash are recorded in
[`mac-worker-error-reporting.json`](../../../results/desktop-sprint1/qa/mac-worker-error-reporting.json).
Dock-context-menu Quit remains unverified. The local
app was unsigned/ad-hoc signed; this is not Developer ID signing or notarization.
The bundle's macOS 13 minimum is metadata only; macOS 13 runtime behavior is
unverified.

On 2026-10-15, the current native bundle repeated the 40,001-entry listing.
The UI reported 40,001 entries, limited the preview to 5,000, and retained the
listing-only integrity disclaimer. This does not verify archive payload
integrity. The fixture and executable hashes are recorded in
[`mac-large-archive-listing-2026-10-15.json`](../../../results/desktop-sprint1/qa/mac-large-archive-listing-2026-10-15.json).

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
flow. Separately, the installed v6 worker passed 38 subprocess smoke
operations across five formats (20 successes and 18 expected rejections);
these are not GUI coverage of all formats. The earlier installed ELF hash was
`3165b8d6e48515401d1b8278151b468d9489c46b5bcd4eb75c790f5a2ebd08b5`.

### Ubuntu 24.04.5 · ARM64 · GNOME/Xorg

The installed v6 package (source `ccdeb9db6947f4a52cb0bd75ad5433927fae3c15`)
rendered in the Ubuntu GNOME/Xorg session. A cold `--open` handoff opened a
generated TAR+Gzip fixture with 40,001 items (40,000 files and one directory).
Inspection displayed a bounded preview of 5,000 entries and the listing-only
disclaimer; it did not offer an output-folder action. Cancelling inspection
showed “Cancelled,” cleared the preview, and re-enabled Inspect archive.
Alt+F4 closed the app during inspection. Independent process and filesystem
observations confirmed the worker exited and its private staging directory,
including decoded scratch data, was removed after listing, cancellation, and
close.

The installed app also created a ZIP through the GTK save dialog. Independent
ZIP parsing verified both file contents and two directories, including an
empty directory. Nautilus 46.4’s “Compress with Bytepleat” and “Extract with
Bytepleat” context actions forwarded the selected paths. Full extraction
completed and restored both files and both directories with matching hashes.
Repeating into the existing destination failed without changing any output.
Selective extraction completed with only `nested/日本語.txt` present and its
expected SHA-256. The context action was invoked from the keyboard on the
selected item; this run does not add a mouse right-click gesture check.

With the archive selected in Nautilus, warm “Open With Bytepleat” and
“Always use” off forwarded the exact archive to the existing process and
changed the app to Open mode in the earlier v6 test. That package remained
behind Nautilus; this historical observation is superseded by the limited v10
foreground samples below and should not be generalized to newer packages.

The installed executable SHA-256 was
`efb4a7221de0ff6d6d96acdc30e6e72e0c3d6610cabc00634ca93528c5160883`; the
package SHA-256 was
`82457192c7c573ad452b6bdf16b48278ca78b012bfbc57b2f465dc7fd9b44571`. The
package rebuilt twice with identical bytes. Its inventory has 377 notice
packages, 673 literal notice texts, and zero literal gaps; this is not legal
clearance. At the time of this v6 package test, GNOME warm Open With foreground
activation remained unresolved; see the later v10 runtime samples below.

## Build and package evidence

At commit `ccdeb9db6947f4a52cb0bd75ad5433927fae3c15`, all seven jobs passed in
public CI run [38683351950](https://github.com/megasoft1978/bytepleat/actions/runs/38683351950).
App/core checks passed on macOS ARM64, Linux x64, and Windows x64. Native x64
Explorer COM and quoting tests passed; the ARM64 Explorer adapter compiled,
but its native COM tests were skipped, so this is compile-only evidence. The
x64 and ARM64 MSIX jobs passed package schema/payload validation and reported
notices. The CI does not establish Windows installation or runtime behavior,
Explorer interaction in an installed app, or ARM64 runtime behavior.

The local unsigned ARM64 Debian development package v6 was built twice with
identical bytes (SHA-256
`82457192c7c573ad452b6bdf16b48278ca78b012bfbc57b2f465dc7fd9b44571`). It
contains 377 notice packages and 673 literal notice files, with zero literal
gaps; this is not legal clearance. It installed on Ubuntu 24.04.5 ARM64 and
the installed executable hash is recorded above. No consumer desktop installer
download is published.

A later Linux activation change was built natively on the same Ubuntu 24.04.5
ARM64 guest. Formatting, warnings-as-errors Clippy, 14 desktop library tests
plus the Linux-only startup test, and all 17 Linux installer/package tests
passed. The v10 native release executable SHA-256 is
`c0ac97eff1de3235f637c8bc79bf3606422a97a029923499271688f3f48bbd77`. Its
unsigned development Debian package SHA-256 is
`5763af5c5fca5a49b7b6d3a38e4e4d69ddec29507d425a78aac09cb496cf530a`; rebuilding
with the same source-date epoch produced byte-identical package bytes. The
installed package and per-user launcher use `--open -- %F` and
`StartupNotify=true`.

On the installed GNOME/Xorg guest, one direct cold Nautilus Open With launch
with “Always use” off reproduced an unbounded startup-argument growth loop.
The v10 startup handoff and argument parser were rebuilt to stop repeated
re-execution and discard the duplicated open-option group. After installing
v10, a direct cold Open With launch came to the foreground and selected only
`gnome-v6.zip`; clicking Inspect completed and displayed four entries. Ten serial warm Open With launches while Bytepleat was already running each
brought the app forward with only the requested archive selected. The earlier
listing checks are not integrity checks. A cold Extract from the Nautilus
context action completed into a fresh destination folder. The result contained
the expected two files and nested empty directory; source archive and extracted
file contents were compared byte-for-byte and matched. A cold Nautilus Compress
handoff on the `Input café` folder also created a ZIP; `unzip -t` validated all
four entries with no errors. The exact scope is one cold and ten warm Open With
samples, one cold Extract, and one cold Compress in Ubuntu 24.04.5 ARM64
GNOME/Xorg. This does not cover Wayland, other distributions, or other
architectures. The earlier installed v6 package also passed GNOME inspection
cancellation, existing-destination refusal, and selective extraction. Those
three workflows have not been repeated against the later v10 activation
package. No hard VM reset was performed.

After those v10 package tests, the desktop argument parser was narrowed so it
strips repeated `--open --` tokens only inside Bytepleat's private startup
frame. Regression tests preserve literal selected paths named `--open` and
`--`, with and without `argv[0]`. On macOS, the current source passed Tauri
formatting, warnings-as-errors Clippy, and all 16 applicable Tauri library
tests. The change has not yet been rebuilt and exercised as a Linux package;
the v10 hashes and GUI observations above describe the prior binary, not this
latest source revision. Linux-native startup and GNOME runtime verification
remain pending.

## Remaining validation

- Verify macOS Dock Quit cleanup; test the minimum supported macOS version.
- Separately verify Kubuntu 26.04 and its newer Dolphin/Plasma combination.
- Complete Windows 11 installation and Explorer interaction on x64 and ARM64;
  distinguish native runtime results from ARM64 cross-compilation and package
  schema/payload probes.
- Re-run GNOME inspection cancellation, no-overwrite, and selective extraction
  against the later v10 activation package; these passed on the earlier
  installed v6 package. Wayland remains unverified. Package validation covers
  Ubuntu 24.04.5 ARM64, not other distributions or architectures.
- Qualify signed packages, including Developer ID/notarized macOS distribution
  and appropriate Windows signing.
- Expand interactive coverage across supported operating systems and archive
  formats. Existing GUI tests do not establish performance; no new codec or
  performance claim is made by this validation record.
