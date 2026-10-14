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

Finder Open With registration is visible, but invocation is unverified. General
multi-selection, keyboard browsing, and quit cleanup remain pending. The local
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

## Build and package evidence

At commit `520a83`, app/core checks on macOS, Linux, and Windows passed in public
CI run [38626708085](https://github.com/megasoft1978/bytepleat/actions/runs/38626708085).
That workflow as a whole **failed** at the old MSIX manifest validation. Native
x64 Explorer COM tests passed and the ARM64 Explorer adapter compiled; ARM64
was compile-only, not runtime evidence.

The later package probe [38632655348](https://github.com/megasoft1978/bytepleat/actions/runs/38632655348)
validated the corrected manifest (`d514936`). Its x64 and ARM64 schema and
package payload checks passed. The earlier payload run was
[38626708085](https://github.com/megasoft1978/bytepleat/actions/runs/38626708085).
These are package schema/payload checks, not Windows installation or Explorer
interaction. A Windows 11 ARM64 VM check awaits an official ISO.

Linux package-builder work is ongoing. No installer download or Linux package
runtime result is claimed here.

## Remaining validation

- Verify macOS Open With invocation, multi-selection, keyboard browsing, and
  quit cleanup; test the minimum supported macOS version.
- Verify GNOME default-shell behavior; separately verify Kubuntu 26.04 and its
  newer Dolphin/Plasma combination.
- Complete Windows 11 installation and Explorer interaction on x64 and ARM64;
  distinguish native runtime results from cross-compilation and package probes.
- Complete Linux package building, then validate its actual package and
  installation workflow.
- Qualify signed packages, including Developer ID/notarized macOS distribution
  and appropriate Windows signing.
- Expand interactive coverage across supported operating systems and archive
  formats. Existing GUI tests do not establish performance; no new codec or
  performance claim is made by this validation record.
