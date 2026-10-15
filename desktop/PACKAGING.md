# Linux Debian development package

`build-linux-package.py` creates an unsigned local development `.deb` from an
already-built Tauri desktop ELF and the matching target-specific output of
`collect-desktop-notices.py`. It does not compile the app, install the package,
run `apt`, or alter the invoking user's file associations.

The builder supports these exact Rust targets and Debian architecture names:

| Rust target | ELF machine/class | Debian architecture |
| --- | --- | --- |
| `x86_64-unknown-linux-gnu` | x86-64, ELF64 | `amd64` |
| `aarch64-unknown-linux-gnu` | AArch64, ELF64 | `arm64` |

Example from this directory (build and collect notices for the same target
before invoking this command):

```sh
SOURCE_DATE_EPOCH=1760400000 python3 scripts/build-linux-package.py \
  --executable src-tauri/target/x86_64-unknown-linux-gnu/release/bytepleat-desktop \
  --target x86_64-unknown-linux-gnu \
  --notices-dir /path/to/x86_64-notices \
  --output /path/to/bytepleat-desktop_0.1.0~alpha.0_amd64.deb
```

The notice directory must contain `THIRD-PARTY.json` and every referenced
literal notice text. The collector's source version must be `0.1.0` (from the
Cargo manifests); the Debian package's explicitly alpha version is
`0.1.0~alpha.0`. Target and source version must match; paths must stay
inside that directory; notice hashes are checked. `readelf` (GNU binutils) and
`dpkg-deb` (Debian `dpkg`) must already be installed. No build tools are
downloaded. The final output must not exist and its parent directory must
exist. Publication uses an atomic no-overwrite filesystem link.

The package installs the executable as `/usr/bin/bytepleat-desktop`, its
launcher and icon in standard freedesktop locations, the project's `LICENSE`,
the supplied third-party JSON inventory and all listed texts under
`/usr/share/doc/bytepleat-desktop/`. The Linux integration installer and its
Nautilus helper data are retained under `/usr/lib/bytepleat/desktop/` so their
existing relative-path contract continues to work.

The package does not run maintainer scripts or automatically register file
associations, context menus, or a default application. After installing the
package as a root task through apt/dpkg, a user can separately opt into the
per-user integration installer:

```sh
python3 /usr/lib/bytepleat/desktop/scripts/install-linux-integrations.py \
  --install --app /usr/bin/bytepleat-desktop
```

Remove those per-user integration files with the same script and `--uninstall`.
The package is version `0.1.0~alpha.0`, unsigned, intended for local
development, and is neither released nor consumer-ready.

## Dependencies and reproducibility

The builder reads ELF `DT_NEEDED` entries and version needs with `readelf`,
maps recognized SONAMEs to Debian runtime package names, and rejects an unmapped direct shared
library instead of silently omitting it. For WebKitGTK it includes GTK and
librsvg runtime packages as Tauri's documented Linux runtime stack requires.
When the ELF has public `GLIBC_x.y[.z...]` version needs, the `libc6` dependency
includes the numerically highest required version, for example
`libc6 (>= 2.39)`. No GLIBC version-needs entries means no inferred floor;
`GLIBC_PRIVATE` is rejected because it is not a public compatibility ABI.
The current Tauri prerequisites document lists the corresponding Debian/Ubuntu
development packages (`libwebkit2gtk-4.1-dev`, `libayatana-appindicator3-dev`,
and `librsvg2-dev`) and notes availability on Debian Bookworm and Ubuntu
Noble: <https://v2.tauri.app/start/prerequisites/>. Runtime package names are
inferred from those documented components and Debian's runtime package naming;
this is not evidence of compatibility with every distribution or release.

Pass a fixed non-negative `SOURCE_DATE_EPOCH` (or `--source-date-epoch`). The
builder fixes file/directory modes and mtimes, uses root ownership, uniform
gzip compression, and Debian's `dpkg-deb`. With the same ELF, notice output,
builder, dpkg-deb version, and epoch, repeated builds should have identical
bytes. Debian documents `SOURCE_DATE_EPOCH`, root-owner-group, and uniform
compression in [`dpkg-deb(1)`](https://manpages.debian.org/dpkg-deb).

The generated inventory's `unresolved_gaps`, `literal_inventory_complete`,
`redistribution_ready`, and `legal_clearance` values are carried verbatim in
the package inventory. Gaps do not block packaging: they identify missing
literal texts or metadata that require separate review. A complete literal
inventory is not legal clearance. The collector itself reports those limits;
this development packager makes no legal-clearance claim.

## Scope

The local ARM64 development package v6 was built twice with identical bytes:
SHA-256 `82457192c7c573ad452b6bdf16b48278ca78b012bfbc57b2f465dc7fd9b44571`.
It contains 377 notice packages, 673 literal notice files, and zero literal
gaps. Zero literal gaps do not establish legal clearance. The package installed
on Ubuntu 24.04.5 ARM64 GNOME/Xorg, and the installed executable SHA-256 was
`efb4a7221de0ff6d6d96acdc30e6e72e0c3d6610cabc00634ca93528c5160883`. The
installed app passed a cold TAR+Gzip open and bounded inspection of 40,001
items, displaying 5,000. Cancelling inspection showed a cancelled state with
no partial preview; closing the window during inspection cleaned up the worker
and decoded staging. GUI workflows also passed ZIP creation, full and selective
extraction, overwrite refusal, and Nautilus context actions. In that earlier
v6 run, warm Open With forwarded the archive to the running app but did not
foreground it; the later v10 samples below supersede that limited observation.

Separate installed-worker subprocess smoke checks on the latest source revision
passed 38 operations (20 successes and 18 expected rejections) across macOS
and Ubuntu ARM64. These include all five listing formats and are not GUI
coverage across all formats.

The subsequent Linux activation worktree passed native Ubuntu 24.04.5 ARM64
formatting, warnings-as-errors Clippy, 14 desktop library tests plus one
Linux-only startup test, and the 17 installer/package tests. Its v10 unsigned
Debian package has executable SHA-256
`c0ac97eff1de3235f637c8bc79bf3606422a97a029923499271688f3f48bbd77` and
package SHA-256
`5763af5c5fca5a49b7b6d3a38e4e4d69ddec29507d425a78aac09cb496cf530a`. Two
packages built with the same source-date epoch were byte-identical. The
installed GNOME/Xorg package passed one cold and ten warm Nautilus Open With
checks with “Always use” off: each handoff brought the app to the foreground
with only the selected ZIP. At final inspection one app process remained with
no repeated startup handoff markers in its arguments. Cold Compress from
Nautilus created a ZIP that passed
`unzip -t`; cold Extract completed into an initially empty test folder, and
the extracted file bytes matched the archive contents. A prior direct-launch
test on v9 reproduced a startup-argument growth loop and selected the injected
`--open --` tokens as paths; v10 includes loop and duplicate-argument fixes.
These ten serial warm samples do not establish behavior across other GNOME or
Wayland configurations.

The current source further limits duplicate-argument removal to a recognized
private startup frame and preserves literal selected files named `--open` or
`--`. Its macOS formatting, Clippy, and 16 applicable Tauri library tests pass.
This follow-up has not yet been rebuilt as a Linux package or rechecked in the
GNOME guest; the v10 hashes and runtime observations above apply to the tested
v10 binary only.

This is evidence for that package and system only. It does not claim support for
all Debian or Ubuntu releases, distributions, architectures, or consumer release readiness. Earlier installed-copy XFCE/Xorg listing and selected extraction remain separately verified; see the
[desktop validation record](../docs/desktop-validation.md) for exact scope.

This script packages an existing ELF; it does not establish GUI behavior,
runtime availability, desktop integration behavior, or native OS support. Run
package validation on the intended Debian/Ubuntu target and architecture.
