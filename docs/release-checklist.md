# CLI release checklist

Bytepleat CLI 0.5.2 has already been released. This checklist is for a future
CLI release; choose its version and source tag before using the commands below.
It does not cover a desktop consumer release. Desktop remains an alpha with no
published installer; see the [beta testing guide](beta-testing.md) and
[desktop validation record](desktop-validation.md).

Dry run (report only, writes nothing, no network):

Replace the placeholders with the chosen versions before running the dry run:

```sh
python3 scripts/release_dryrun.py --from VERSION_FROM --to VERSION_TO
```

## 1. Local verification (before any bump)

```sh
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
cargo clippy --locked --manifest-path desktop/core/Cargo.toml --all-targets -- -D warnings
cargo test --locked --manifest-path desktop/core/Cargo.toml
cargo clippy --locked --manifest-path desktop/src-tauri/Cargo.toml --all-targets -- -D warnings
cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml
python3 -I -m unittest discover -s desktop/scripts/tests
python3 -I -m unittest discover -s scripts/tests
```

All must pass on a clean tree. The native package checks (macOS Apple silicon, Linux x86-64 GNU, Windows x86-64 MSVC) run in CI and must be green for the release commit.

## 2. Version bump (after the release commit is ready)

Use the dry-run report to find references that need the new version. Preserve
historical release notes, benchmark records, and validation records.

1. `Cargo.toml` `version`.
2. `cargo update -p bytepleat --offline` to refresh `Cargo.lock`. Do not hand-edit the lockfile.
3. `README.md`: download URLs, `curl`/PowerShell examples, install tag, and release status.
4. `RELEASE.md`: title, asset names, sidecar names, and install tag.
5. `site/project.json`: version, filenames, URLs, and checksum URLs. Fill hashes only after release assets exist and are verified.
6. Site pages and scripts: version text, download links, and install commands.
7. Bug report version placeholder.
8. `.github/workflows/ci.yml`: version arguments in package and verify steps.
9. `.github/workflows/release.yml`: tag guard, expected asset names, `SHA256SUMS` names, notes, and upload assets.
10. Re-run the dry run with the selected versions and resolve every unexpected stale reference.
11. Re-run step 1.

Do not push or publish without maintainer authorization. Update public download
links only when the corresponding release assets exist.

## 3. Owner-only steps (publishing)

Owner runs these. Do not automate them.

1. Create an annotated tag for the approved release version on the release commit.
2. Let the release workflow build the native packages and checksums, or use the named runners as the workflow expects.
3. Create the GitHub release and upload the expected archives, sidecars, and `SHA256SUMS`.
4. Signing and notarization require a separate maintainer decision and credentials. Signing changes archive bytes, so calculate hashes from the final assets.
   - a. Put signing credentials only in the approved secret store. Never commit values.
   - b. Only after assets exist: copy verified SHA-256 values from their sidecars into public metadata. Never type hashes from memory.
5. Homebrew tap (`megasoft1978/homebrew-tap`, formula from the owner's local lab notes, not in this repository): update the formula with the real hashes after step 4b.
6. winget: generate the manifest for the approved version from verified hashes, validate it, and open the PR to `microsoft/winget-pkgs`.
7. crates.io: skipped. Decided in the owner's local lab notes, not in this repository; `[patch.crates-io]` would drop the hardened 7z reader on publish.
8. Commit the `sha256` fill-in and any site changes, then push and tag only with owner approval.

## 4. Post-release verification

1. For each published platform asset: download into an empty directory.
2. Verify the sidecar: `shasum -a 256 -c <asset>.sha256` (macOS), `sha256sum -c <asset>.sha256` (Linux), `Get-FileHash` against the sidecar (Windows). Confirm the digest equals the value in `site/project.json` and `README.md`.
3. Extract and run `--version`; it must print the approved release version, and `--help` must run.
4. Check that the GitHub release lists exactly the expected assets, with no extras.
5. Check the Pages site: download links, version text, and install commands point at the approved release; no broken links (`.github/workflows/pages.yml` deploys).
6. Check the `cargo install --locked --git ... --tag <tag>` command builds from the release tag.
7. Record the results in the release notes, or in `RELEASE.md` if the owner asks.
