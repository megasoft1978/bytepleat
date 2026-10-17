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

A separate Finder **Open With → Bytepleat** smoke check used a two-file 7z
archive created with the installed 7-Zip 17.05 CLI. Finder forwarded the file
and the UI listed both expected paths and sizes (35 B and 8.2 KB). The archive
SHA-256 was
`f27a3033438e9a03dc96651efd9153a27be0d9762747f3252b7106f1f064d6ca`; `7z t`
reported the fixture valid independently. Bytepleat's UI explicitly described
the view as listing only; it did not verify payload integrity. Selecting one
entry moved the UI to the extraction workflow, but no extraction job completed
and no extracted output was verified. This is format-opening/listing and Finder
handoff evidence only, not 7z extraction support evidence or a performance
result.

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

At source revision `d85dddacbfbf2d70b54745885d74fbcc48f3a435`,
passed all jobs in [Desktop alpha native checks run
38699179705](https://github.com/megasoft1978/bytepleat/actions/runs/38699179705).
Core and desktop app formatting, Clippy, tests, and executable builds passed on
macOS ARM64, Ubuntu 24.04 x64, and Windows x64. The Windows x64 runner also
cross-compiled the desktop executable for Windows ARM64. Native Explorer COM
and quoting tests passed on x64; the ARM64 adapter compiled, but its native
tests were skipped. Unsigned x64 and ARM64 MSIX packages passed MakeAppx
payload/schema validation. These CI checks are headless build, test, and package
evidence: they do not establish installed Windows GUI behavior, Explorer
handoff, Windows ARM64 runtime behavior, or signing.

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

At source revision `d85dddacbfbf2d70b54745885d74fbcc48f3a435`, the desktop
argument parser was narrowed so it strips repeated `--open --` tokens only
inside Bytepleat's private startup frame. Regression tests preserve literal
selected paths named `--open` and `--`, with and without `argv[0]`. That source
revision passed Tauri formatting, warnings-as-errors Clippy, and all 16
applicable Tauri library tests on macOS. The v10 hashes and GUI observations
above describe the earlier installed package, not this later source. The
current automated build evidence is recorded below; testing the latest source
as an installed GNOME package remains pending.

## Current automated baseline · 2026-10-15

The current merged source tree is `d1ed936aac3fd28093377e3ac1aca39f5d60d90f`.
The [desktop workflow](https://github.com/megasoft1978/bytepleat/actions/runs/38770917796)
passed builds and tests on macOS ARM64, Linux x64, and Windows x64, compiled the
Windows ARM64 app and adapters, and passed Windows x64/ARM64 package checks.
The [native Rust CI](https://github.com/megasoft1978/bytepleat/actions/runs/38770917965)
also passed. The latest [native WebView smoke](https://github.com/megasoft1978/bytepleat/actions/runs/38766872361)
exercised the real app UI on macOS ARM64, Linux x64/ARM64, and Windows x64/ARM64;
its WebView tests covered generated-ZIP inspection, selected-extraction review,
create, selective extract, existing-destination preservation, and Windows
startup arguments. It did not exercise native file dialogs or shell menus.

The native UI workflow built and launched the Tauri app on GitHub-hosted
macOS ARM64, Ubuntu Linux x64 and ARM64, Windows x64, and Windows 11 ARM64
runners. On each target, WebDriver operated the real embedded WebView to inspect
a generated ZIP and open the selected-extraction review; two screenshots and a
successful test report were retained per target in the workflow artifacts.
The same suite also called the app's Tauri command bridge to create a ZIP,
inspect it, selectively extract one file, verify that the unselected file was
absent, and confirm that an existing destination stayed unchanged. Those
command-level checks exercised native builds but did not use the operating
system file dialogs or shell context menus.

The desktop build workflow also passed formatting, Clippy, and tests on macOS
ARM64, Linux x64, and Windows x64; built Windows x64 and ARM64 desktop apps;
rebuilt the Linux development package; and validated unsigned Windows x64/ARM64
MSIX package schemas and payloads. Native Explorer COM and quoting tests passed
on Windows x64. On Windows 11 ARM64, the packaged smoke installed a test MSIX,
verified package registration and its execution alias, then activated the
packaged Explorer-command COM classes, enumerated their menu children, and
invoked Compress, Extract, and Open with arguments captured by a test receiver.
The native Rust workflow passed on macOS ARM64, Linux x64, and Windows x64.
These runs verify app behavior in CI and development-package construction; they do
not verify interactive Finder/Explorer/Nautilus/Dolphin menu behavior, signed
public distribution, or behavior on every OS version.

The current desktop workflow additionally builds the normal Linux development
`.deb` reproducibly, installs it on Ubuntu 24.04 x64, launches it under private
D-Bus and Xvfb, and captures its visible nonblank window. The archived screenshot
from run `38770917796` was inspected and showed the rendered app. This validates
package startup and window rendering in that isolated environment. It does not
validate an interactive GNOME session, file-manager actions, or archive workflows.
The same run's Windows 11 ARM64 packaged smoke installed a test MSIX and checked
package registration, alias activation, packaged Explorer COM enumeration, and
argument handoff to a test receiver; it does not prove a visible Explorer menu
launches the production GUI.

### Isolated Nautilus integration runtime · Ubuntu 24.04 · 2026-10-15

The new headless Nautilus smoke was run three consecutive times in an isolated
Ubuntu 24.04 ARM64 container with GNOME Files/Nautilus `1:46.4-0ubuntu0.2`,
under a 1280×1024 Xvfb display and a private D-Bus session. Each run installed
the per-user integration through the real Linux installer into a temporary
home, opened a selected fixture in Nautilus, and activated both visible context
actions. A recorder executable verified the exact handoff three times for each
action: Compress received `--create -- <fixture-path>` and Extract received
`--extract -- <fixture-path>`, including a Unicode filename and paths with
spaces and a leading dash. The recorder replaced the desktop app: these checks
verify extension loading, menu activation, and argument handoff only. They did
not run compression or extraction, and do not establish behavior in an
interactive GNOME Shell session, on Wayland, or on other distributions. The
first hosted Nautilus runtime job passed in [GitHub Actions run
38762493952](https://github.com/megasoft1978/bytepleat/actions/runs/38762493952).
The same job passed again in [run 38770917796](https://github.com/megasoft1978/bytepleat/actions/runs/38770917796).

### Packaged Linux window render · Ubuntu 24.04 x64 · 2026-10-15

Run `38770917796` built the ordinary Linux development `.deb` twice and checked
the package files were byte-for-byte identical. In a dependent hosted job, CI
installed that package on Ubuntu 24.04 x64, started `/usr/bin/bytepleat-desktop`
inside a private D-Bus session and Xvfb, found the visible `Bytepleat` window,
and waited for a nonblank capture. The retained 1200×800 screenshot contains
2,146 colors and visibly shows the Create view. This catches a blank or missing
window after package installation; it does not establish live GNOME Files
behavior or any create/extract workflow. Current GNOME workflow repetition,
including cancellation, no-overwrite, and selective extraction, remains pending.

## Windows ARM64 packaged integration smoke

The desktop workflow now defines a bounded, noninteractive ARM64 packaged smoke
in the separate `windows-arm64-packaged-smoke` job on `windows-11-arm`, using
same-revision Explorer, smoke-probe, notice and desktop artifacts. The existing unsigned x64/ARM64 package artifacts
and both MakeAppx validation paths remain unchanged. A separate test MSIX uses
a unique publisher and ephemeral self-signed development certificate. Only that public
certificate is temporarily trusted in the runner's LocalMachine TrustedPeople
store; installation is for the current user.

The test refuses preexisting Bytepleat packages across users, a preexisting alias,
and classic registrations for the command CLSIDs. It verifies current-user
package identity and registration, the manifest execution alias and its
package-family reparse point, then uses a console process to activate all four
packaged `IExplorerCommand` classes and enumerate exactly three expected children.
It invokes packaged Compress with two real temporary file selections, then
Extract and Open with one each. For this isolated check only, the package's GUI
executable is replaced by a tiny ARM64 console receiver that captures parsed
arguments and exits; the real packaged Explorer DLL, COM registration, and
app-execution alias are used. The test verifies action flags, the `--`
terminator, and exact selection paths (including spaces and Unicode) without
displaying Bytepleat or controlling Explorer. This proves packaged COM
invocation and argument handoff to a receiver, not that the production app
consumes these arguments or that the visible Explorer menu works. The probes
have a 120-second deadline inside a ten-minute workflow step. Cleanup in
`finally` attempts exact test-package removal even after partial installation,
exact temporary certificate/thumbprint and private-key removal, and private work
directory deletion; cleanup errors fail the step. Forced runner termination can
prevent `finally`, so this belongs on a disposable runner.

This passed as a development-package runtime check on the named Windows 11
ARM64 runner. It is not a public-release installer test.
The manifest minimum remains `10.0.26200.0`, with no override. The public
[GitHub Windows 11 ARM64 image inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows11-Arm64-Readme.md)
reports OS `10.0.26200`. The smoke checks the actual OS version and requires both
the OS and PowerShell process to be native ARM64 before creating test state; it
also rejects a probe artifact whose PE machine is not ARM64. The console probe
is compiled only for ARM64 and independently rejects an emulated process.
Local macOS checks cover PowerShell parsing and mocked ownership/cleanup,
workflow lint, and static/unit checks. Installation, Windows certificate-store
operations, and packaged COM activation/invocation are validated only by the
Windows CI runner.

Local headless checks on macOS on 2026-10-15 passed workflow `actionlint`,
PowerShell parsing (eight scripts), ownership/cleanup and prerequisite mocks,
and Python 3.12 unit suites in `scripts/tests`, `desktop/scripts/tests`, and
`desktop/integrations/windows/tests` (69 passed, one native Debian packaging test
skipped). `cargo fmt --all -- --check`, locked Clippy for all targets with
warnings denied, and locked tests passed for the CLI, desktop core, and Tauri
app. Source-export and diff-whitespace checks passed. These checks do not compile
or run the Windows-only C++ probe or validate Windows SDK/package runtime behavior.

A passing run establishes development current-user installation, package
registration, alias activation, and packaged COM invocation with argument
handoff to a test receiver on the specific native Windows ARM64 runner. It does
not establish production package startup through Explorer, consumer signing
trust, interactive Explorer menus, or x64 installed-package behavior.
No desktop is launched or controlled by this smoke. See the
[Windows integration instructions](../desktop/integrations/windows/README.md#arm64-packaged-integration-smoke)
for the exact script and cleanup scope.

## Ubuntu 24.04.5 ARM64 VM revalidation of `6fbeec2` · 2026-10-16

Run in the existing UTM virtual machine (GNOME on X11, 640x480 display) against a clean `git archive` of `main` at `6fbeec2`.

- **Passed:** CLI, desktop core and Tauri tests (55, 15 and 20), `cargo fmt --check` and `cargo clippy -D warnings` on all three crates, and building the unsigned ARM64 `.deb`.
- **Passed on a separate `ui-test` build** (same source, with the optional embedded WebDriver; the ordinary package excludes it): opening a ZIP, creating an archive, extracting checked entries, rejecting an empty selective extraction, refusing an existing destination folder with its contents unchanged, cancelling a job without staging remnants, and the single-archive message.
- **Passed:** interrupting a 600 MB compact compression with SIGINT exited 130, left no `.tmp*` file, and left the existing output byte-identical.
- **Passed (follow-up, same VM, XFCE/Xorg 1280x800):** the ordinary installed `.deb` (ELF sha256 `3347dd67bdccfd00...`) was visually checked. The window renders the new empty state ("Drop files to compress, or an archive to inspect", "Existing files are never overwritten.", format step hidden until input is chosen), and `--open -- <zip>` forwards the archive to the running window and opens the Inspect tab with it selected. Note: reinstalling a package with the same version string needs `dpkg -i`; `apt-get install ./pkg.deb` silently kept the older build, so an earlier check of the "installed" app was of the wrong binary.
- **Nautilus (XFCE/Xorg, same VM):** the first check of the ordinary package found a bug: Nautilus's startup ID contains the program path, which made the app list `--open` and `--` as archives on Open With ("3 archives selected"). Fixed in `9a45a25`. A package rebuilt from that commit (ELF sha256 `bcd891f18674fa5e...`, Linux tests passing) showed only the selected ZIP with "1 archive selected" and Inspect enabled on both a cold start and a warm start (app already running). Nautilus Compress and Extract opened the expected modes with the right selections; no archive job was run from the menus.
- **Not verified:** Dolphin menu clicks (the context menu did not appear under `xdotool`; the installed Open With, Compress and Extract commands were run by hand and worked). Wayland and Kubuntu are untested, and the Windows desktop app and Explorer menus are untested (see the Windows section).

## Windows 11 ARM64 VM: command-line checks · 2026-10-17

Run in a UTM virtual machine on Apple silicon: Windows 11 Pro 26H2, build 10.0.26300, ARM64, unactivated, installed unattended from Microsoft's official ARM64 ISO. Only the **command-line tool** was tested here; the desktop app, the MSIX package and the Explorer menus were not.

- **Passed (released 0.5.1 x86-64 package, which runs under Windows' x64 emulation):** the download matches its published SHA-256; `--version` prints 0.5.1; a 1.1 MB text file compressed and restored byte for byte; `pack` and `unpack` worked for ZIP, 7z and tar.gz; Windows' own `Expand-Archive` read our ZIP; compressing over an existing output was refused with a non-zero exit.
- **Found:** a ZIP made by Windows' built-in `tar.exe` (bsdtar 3.8.8) rooted at `.` failed to unpack with "empty archive path" on 0.5.1. A build of current `main` (the CI package) unpacks it correctly, and a ZIP containing `../evil.txt` was still rejected ("non-portable archive path component") with nothing written outside the target. The fix is in `main` but not in a release yet.
- **Note:** `pack` defaults to `--format zstd`, so `bytepleat pack dir -o out.zip` writes a tar+zstd archive under a `.zip` name. Use `--format zip`.
- **Not verified:** the desktop app, MSIX install, Explorer context menus, a native ARM64 command-line build (none is published), signed packages, and other Windows versions.

## Remaining validation

- Verify macOS Dock Quit cleanup; test the minimum supported macOS version.
- Separately verify Kubuntu 26.04 and its newer Dolphin/Plasma combination.
- Verify installed Windows app and Explorer interaction on x64, plus
  interactive Explorer menu behavior and app handoff on ARM64. Native WebView
  E2E passes on both runners; the ARM64 packaged smoke verifies installation,
  registration, and COM activation, but not interactive menu use.
- Install the latest Linux development package in GNOME and re-run inspection
  cancellation, no-overwrite, and selective extraction; those flows passed on
  the earlier installed v6 package. The current x64 package was launched in
  isolated Xvfb, but has not received this installed GNOME workflow check. Wayland remains
  unverified. Package validation covers Ubuntu 24.04.5 ARM64, not other
  distributions or architectures.
- Qualify signed packages, including Developer ID/notarized macOS distribution
  and appropriate Windows signing.
- Expand interactive coverage across supported operating systems and archive
  formats. Existing GUI tests do not establish performance; no new codec or
  performance claim is made by this validation record.

## Scope notes

- The CLI release package for Linux is x86-64 and is tested separately by native CI. The interactive Linux desktop checks in this record were on Ubuntu 24.04.5 ARM64.
- CI native UI smoke results cover the app's inspect, selected-extraction review, create, selected extraction, and overwrite-preservation checks on macOS ARM64, Linux x64/ARM64, and Windows x64/ARM64. They do not establish interactive Finder, Explorer, Nautilus, or Dolphin menu behavior or signed public installers.
- Local checks for the inspection worker change: `cargo fmt --all -- --check`, `cargo clippy --locked --all-targets -- -D warnings`, and `cargo test --locked` in `desktop/core` and `desktop/src-tauri`, plus `node --check desktop/ui/app.js`. See [desktop internals](desktop-internals.md).
