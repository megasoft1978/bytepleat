# Release checklist

Ordered steps for the next release. Target: 0.5.2 (from 0.5.1). Nothing here publishes, tags or signs; the owner-only steps are marked.

Dry run (report only, writes nothing, no network):

```sh
python3 scripts/release_dryrun.py --from 0.5.1 --to 0.5.2
```

## State of the release-0.5.2 branch

Changed on `release-0.5.2`: `Cargo.toml` version (0.5.2); the `bytepleat` entry in the root `Cargo.lock` only; `--version` arguments in `.github/workflows/ci.yml`; tag guard, expected asset names, `SHA256SUMS`, release title and notes in `.github/workflows/release.yml`; the `.github/ISSUE_TEMPLATE/bug_report.yml` placeholder; the CHANGELOG heading (`## 0.5.2 (unreleased)`); this paragraph.

Deliberately unchanged, because they need real assets: download URLs, asset file names and `sha256` values in `README.md`, `RELEASE.md`, `site/project.json`, the `site/` pages, `site/assets/site.js` and the distribution drafts. Also unchanged: the `THIRD-PARTY.json` project version, the historical benchmark and desktop-validation records, and the `bytepleat` entries in `desktop/core/Cargo.lock` and `desktop/src-tauri/Cargo.lock` (they pin 0.5.1 as a path dependency, so `--locked` fails there until updated). `scripts/tests/test_release_instructions.py` fails until `RELEASE.md` names the 0.5.2 Windows ZIP.

Left for the owner after the tag: build and upload the assets; fill the `sha256` values and URLs in `README.md`, `site/project.json`, `RELEASE.md` and the site pages; merge to `main` (the site goes live on merge); decide signing and registries (crates.io skipped).

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

Every hardcoded `0.5.1` from the dry run changes to `0.5.2`:

1. `Cargo.toml` `version`.
2. `cargo update -p bytepleat --offline` to refresh `Cargo.lock`. Do not hand-edit the lockfile.
3. `README.md`: download URLs, `curl`/PowerShell examples, `--tag v0.5.2`, status lines.
4. `RELEASE.md`: title, asset names, sidecar names, `--tag v0.5.2`.
5. `site/project.json`: `version`, filenames, URLs, `checksum_url`s. Leave `sha256` values as they are until step 4b.
6. `site/index.html`, `site/docs/index.html`, `site/404.html`: version text, download links, install commands.
7. `.github/ISSUE_TEMPLATE/bug_report.yml` placeholder.
8. `.github/workflows/ci.yml`: `--version` arguments in the package and verify steps.
9. `.github/workflows/release.yml`: tag guard (`test "$RELEASE_TAG" = v0.5.2`), expected asset names, `SHA256SUMS` names, release notes text, `gh release create` asset names.
10. Re-run `python3 scripts/release_dryrun.py --from 0.5.1 --to 0.5.2` and confirm no `0.5.1` remains outside the excluded files and historical benchmark records.
11. Re-run step 1.

Do not push the bump until the owner says to publish: the live Pages site and README point at assets that do not exist before the release.

## 3. Owner-only steps (publishing)

Owner runs these. Do not automate them.

1. Create the annotated tag `v0.5.2` on the release commit.
2. Let the release workflow build the native packages and checksums, or build them on the named runners as the workflow expects.
3. Create the GitHub release `v0.5.2`. Upload the three archives and their `.sha256` sidecars plus `SHA256SUMS`.
4. Signing (open decision: sign 0.5.2 or ship unsigned as 0.5.1 was). Signing changes archive bytes, so any signed release gets new hashes.
   - a. Apple Developer ID and notarization, Windows Trusted Signing: credentials go only into GitHub secrets (names in the owner's local lab notes, not in this repository). Never commit values.
   - b. Only after the assets exist: copy the real `sha256` values from the uploaded sidecars into `README.md` and `site/project.json`. Never compute or type these from memory.
5. Homebrew tap (`megasoft1978/homebrew-tap`, formula from the owner's local lab notes, not in this repository): update the formula with the real hashes after step 4b.
6. winget (`manifests/m/Megasoft1978/Bytepleat/0.5.2/`): regenerate from the real hashes, validate, open the PR to `microsoft/winget-pkgs`.
7. crates.io: skipped. Decided in the owner's local lab notes, not in this repository; `[patch.crates-io]` would drop the hardened 7z reader on publish.
8. Commit the `sha256` fill-in and any site changes, then push and tag only with owner approval.

## 4. Post-release verification

1. For each asset (macOS arm64 tar.gz, Linux x86-64 tar.gz, Windows x86-64 zip): download into an empty directory.
2. Verify the sidecar: `shasum -a 256 -c <asset>.sha256` (macOS), `sha256sum -c <asset>.sha256` (Linux), `Get-FileHash` against the sidecar (Windows). Confirm the digest equals the value in `site/project.json` and `README.md`.
3. Extract and run `--version`; it must print `bytepleat 0.5.2`, and `--help` must run.
4. Check that the GitHub release lists exactly the expected assets, with no extras.
5. Check the Pages site: download links, version text, and install commands point at `v0.5.2`; no broken links (`.github/workflows/pages.yml` deploys).
6. Check the `cargo install --locked --git ... --tag v0.5.2` command builds from the tag.
7. Record the results in the release notes, or in `RELEASE.md` if the owner asks.
