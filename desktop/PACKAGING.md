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

The local ARM64 development package v4 was built twice with identical bytes:
SHA-256 `17b1e9bb1c75330167c77f923dcd80e6da21eb7c7ad2c4ea4a4a06a397de4469`.
It contains 377 notice packages, 673 literal notice files, and zero literal
gaps. Zero literal gaps do not establish legal clearance. The v4 upgrade
installed successfully on Ubuntu 24.04.5 ARM64 XFCE/Xorg, and the installed
executable retained SHA-256
`3165b8d6e48515401d1b8278151b468d9489c46b5bcd4eb75c790f5a2ebd08b5`.
The installed app was opened cold through Nautilus Open With with “Always use”
off; it listed four entries and selected extraction restored the Japanese-named
file with SHA-256
`291de3adfe866500865cc97d48754b76b09c00abb6fd1ebf31fde81af49f0621`. In
separate installed-worker subprocess smoke checks, 21 checks passed across
five formats (five create/extract pairs, five selected extractions, and six
bounded rejections); these do not constitute GUI coverage across all formats.

This is evidence for that package and system only. It does not claim support for
all Debian or Ubuntu releases, distributions, architectures, or consumer release readiness. Installed-copy GNOME/Xorg
listing and selected extraction were separately verified; see the
[desktop validation record](../docs/desktop-validation.md) for exact scope.

This script packages an existing ELF; it does not establish GUI behavior,
runtime availability, desktop integration behavior, or native OS support. Run
package validation on the intended Debian/Ubuntu target and architecture.
