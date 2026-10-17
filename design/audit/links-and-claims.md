# Links and claims audit

Date: 2026-10-17. Read-only audit. Checker: `/private/tmp/claude-501/-Users-megasoft78-Desktop-Freelance-mosaic-byte-compression-lab/563fbee7-d3b9-494a-be57-e30a1d84f0a9/scratchpad/check_links.py` (run with `python3 -I`; raw results in the sibling `links.json`).

## 1. Links

Scope: README.md, desktop/README.md, site/index.html, site/docs/index.html, site/404.html, docs/*.md (10 files). Includes fenced-code URLs and bare URLs.

- Occurrences checked: 220 in 15 files.
- Unique external URLs: 73. Checked with HEAD, GET fallback, 15 s timeout, 4 workers. Elapsed 4 s, inside the 5-minute budget.
- Local paths and `#anchors`: all resolve.
- Broken: 0 real. One reported 404 is a false positive: README.md:94 `$base = '.../releases/download/v0.5.1'` is a PowerShell base directory, not a link.
- Redirects: 21, all expected and no action needed except the cosmetic one below.
  - 13 GitHub release downloads and `.sha256` files return 302 to the signed release-assets CDN. Only the first hop was followed, so the final bytes were not fetched.
  - 4 DOI links redirect to the publisher (docs/compression-research.md:17,25,26; docs/formats.md:52).
  - 3 learn.microsoft.com 301s to `?view=msvc-170` (README.md:90; site/index.html:222; site/docs/index.html:75).
  - README.md:179 `bytepleat.git` 301s to the repo without `.git`. Cosmetic.
- GitHub `blob/main/...` links (all in site/): 200 OK, and each path exists in the working tree.

## 2. Claims: ranked findings

| # | Sev | file:line | Problem | Suggested replacement |
|---|---|---|---|---|
| 1 | High | site/index.html:10, 15, 24, 60; design/DESIGN.md:57, 560 | Absolute "It never overwrites" for the product. The CLI has `--force` (site/index.html:166; README.md:147). | "It does not overwrite existing files unless you pass `--force`." Desktop copy may keep "never replaces existing files" (README.md:157). |
| 2 | High | desktop/ui/index.html:104; design/DESIGN.md:320 | "Smaller archive for people who have 7-Zip or Keka." is an unsupported size comparison. It contradicts site/index.html:337 ("We make no general speed or size claim") and DESIGN.md:325 ("no ratio language"). | "Writes LZMA2 compression. Output size depends on your files." |
| 3 | High | desktop/ui/app.js:386; app.js:35 (aside) | "Nothing appears in the destination until it is complete" and "moved into place only after everything succeeds" overstate. Docs say multi-file publication is best-effort, not atomic, and may expose partial files (docs/formats.md:24; docs/security-limits.md:20; README.md:148; site/docs/index.html:103). | "Extracting into a temporary folder first. Files are moved into place after the archive checks pass. Moving many files is not atomic." |
| 4 | Med | desktop/ui/app.js:354, 386; README.md:148 | "staging folder" is jargon in UI strings. app.js:35 already says "temporary folder", so the terms conflict. | Use "temporary folder" in UI strings (app.js:354, 386). README.md:148 may keep "staging" if it stays a technical note. |
| 5 | Med | site/index.html:338 (also :167); design/DESIGN.md:601; desktop/ui/app.js:33; desktop/ui/index.html:53 | "makes no network requests", "runs offline", and "Nothing leaves this device" are runtime claims. In-scope evidence is weak: desktop/README.md:52 only says no external CDN requests. A grep found no HTTP client crates in the desktop Cargo manifests or source. This is not a runtime test. | "Bytepleat does not upload files. It reads and writes on this device." Drop "no network requests" and "offline" unless a network test is documented. |
| 6 | Med | docs/security-limits.md (missing); desktop/README.md:45; README.md:161; desktop/ui/app.js:35; design/DESIGN.md:408 | The 5,000-entry listing preview appears in four user-facing places but not in security-limits.md. The 1 GiB cap is also worded differently: security-limits.md:7 says "decoded byte-stream output", while README.md:149 and app.js:33 say "archive output". | Add to security-limits.md Defaults: "Archive output: 1 GiB (`--max-output`; desktop per operation). Listing preview: 5,000 entries (display only; archives may hold 100,000)." Confirm scope in src before editing. |
| 7 | Med | docs/security-limits.md:11 vs docs/formats.md:32 | security-limits says the 7z dictionary is "128 MiB by default and maximum". formats.md says the writer default is 16 MiB, settable up to 128 MiB. The 128 MiB figure is the reader cap (src/archive_safety.rs:30). | security-limits.md:11: "7z writer default dictionary 16 MiB; reader cap 128 MiB (`--max-dictionary`)." |
| 8 | Med | design/DESIGN.md:399 | "more than 1 GB" and "`--max-output 8GiB`" conflict with the product's 1 GiB (README.md:149; app.js:33). The row already flags the flag name as a placeholder (DESIGN.md:406). `--max-output` exists (src/main.rs:132). The GiB suffix parse is unverified. | "more than 1 GiB". Keep the placeholder note. |
| 9 | Med | site/index.html:227 | "The package was tested on Ubuntu 24.04" is for the Linux x86-64 CLI tarball. In-scope docs show Ubuntu 24.04 only for the desktop .deb (docs/desktop-validation.md:248, 280) and an ARM64 VM. CHANGELOG.md:5 says Linux x86-64 GNU tests passed, with no distro named. | "Tested on Linux x86-64 (GNU). The desktop .deb was tested on Ubuntu 24.04." Or verify the CLI on Ubuntu 24.04 x86-64. |
| 10 | Low | design/DESIGN.md:600 vs site/index.html:337 | The design FAQ answer ("Sometimes, sometimes not") differs from the site ("We make no general speed or size claim"). Not wrong, but inconsistent. | Use the site wording in DESIGN.md. |
| 11 | Low | design/DESIGN.md:561, 630 vs README.md:29 | "The command-line tool is the stable part" implies a stability promise. README says "released (version 0.5.1)". | "The command-line tool is released (0.5.1)." |
| 12 | Low | design/DESIGN.md:19, 555 | "macOS 13+" is not stated in README, site, or docs. DESIGN.md:670 says requirements must come from release metadata. | Take from build metadata, or remove. |
| 13 | Low | site/docs/index.html:99 | Preset level mapping (fast/balanced/compact = zstd 1/3/9; gzip 1/6/9) is not in formats.md, security-limits.md, or user-guide.md. The preset enum exists (src/main.rs:37-40). | Move the mapping into docs/user-guide.md, or cite it. Numeric mapping not verified. |
| 14 | Low | site/index.html:201, 339; site/docs/index.html:75 ("notarised"); site/docs/index.html:93 ("recognised"); site/index.html:340 ("recognises") | British spelling, while README.md:56 uses "notarized" and README.md:140 uses "Recognized". | Use US spelling throughout. |
| 15 | Low | site/index.html:287, 292; site/docs/index.html:92, 102; README.md:138 | "bounded" is internal jargon in user-facing copy. | "limited" or "supported subset". |

Consistent, no action:
- Version 0.5.1 everywhere in scope. No `0.5.0` outside CHANGELOG.
- Rust 1.93 (README.md:106, 166; desktop/README.md:7; site/index.html:244; site/docs/index.html:73).
- 100,000 entries; ZIP 65,534; path depth 64; 128 MiB Zstandard window; 16 MiB 7z header; 1 GiB ZIP compressed input. Matching across README, site, desktop, formats, and security-limits.
- ZIP64, RAR, encryption, and split-archive exclusions match everywhere.
- Cancel behavior ("removes temporary output"): README.md:157, app.js:354, DESIGN.md:604.
- Speed and size claims elsewhere are hedged (site/index.html:170, 337; site/docs/index.html:99).
- No "53 tests" or any other test count appears in any in-scope file (0 matches).
- No "Arqlet" or "mosaic" in README, site, desktop/ui, or docs/formats.md, docs/security-limits.md.
- "worker" does not appear in user-facing copy in scope.

## Could not verify

- Runtime "no network requests" and "nothing leaves this device" (#5). Needs a network capture.
- Ubuntu 24.04 testing of the CLI tarball (#9).
- Preset-to-level mapping (#13).
- Whether the 1 GiB cap covers archive creation and extraction totals, or only byte-stream output (#6, #8).
- Final bytes of the 13 release-asset downloads, which were only checked to their first redirect hop.
- "macOS 13+" requirement (#12).
- The `8GiB` suffix parse for `--max-output` (#8).
- Test counts: none in scope, so none checked.
