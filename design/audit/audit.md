# Bytepleat redesign audit: contrast, static HTML, type size

Scope: design/tokens.css, desktop/ui/{index.html,styles.css}, site/{index.html,docs/index.html,404.html,assets/site.css}. Read-only. No files outside design/audit/ were changed. Root: release-workspace/bytepleat/.

## Method

1. **Contrast.** `design/audit/contrast.py` (stdlib, `python3 -I`). Parses `:root` (light), the `prefers-color-scheme: dark` block and `[data-theme="dark"]` (dark, merged over light). Resolves `var()` chains, hex and `rgb()/rgba()`, composites translucent colours over the background, computes WCAG relative luminance. 34 pairs x 2 themes, each tied to the selectors that use it. Thresholds: text 4.5:1; UI components and focus 3:1; disabled controls reported as exempt; decorative hairlines reported, not required. Also checks the ratios written in tokens.css comments (16 claims) and compares the two shipped token copies with the source.
2. **Static HTML.** `design/audit/static_checks.py` (html.parser). Checks: img alt, accessible names on buttons/links/summaries, input labels (for= or wrapping label or aria-label), duplicate ids, aria-labelledby/describedby/controls and label for= and in-page href targets resolving, lang, title, viewport, heading order, h1 count, tabindex > 0.
3. **Type size.** `font-size` declarations in both stylesheets resolved through the tokens, 16px root. Clamp uses the minimum. App floor 13px, site floor 14px.

Raw outputs: `design/audit/contrast-output.txt`, `design/audit/static-output.txt`.

Caveat: contrast uses the token values as written. color-mix() backgrounds and forced-colors values are not computed. Static HTML does not see DOM built by app.js or site.js.

## Results: contrast (design/tokens.css)

Required = text and UI pairs. "Muted" = `--color-text-muted`. "Accent" = `--color-accent`.

| Pair | Light | Dark | Result |
|---|---|---|---|
| P01 text on bg | 15.30 | 15.25 | PASS |
| P02 text on surface | 16.51 | 13.70 | PASS |
| P03 text on surface-raised | 16.51 | 12.32 | PASS |
| P04 muted on bg | 6.42 | 7.85 | PASS |
| P05 muted on surface | 6.92 | 7.05 | PASS |
| P06 muted on surface-raised | 6.92 | 6.34 | PASS |
| P07 muted on fold-light (mode tabs, seg) | 5.70 | 5.80 | PASS |
| P08 accent text on bg | 6.31 | 9.84 | PASS |
| P09 accent text on surface (copy) | 6.81 | 8.84 | PASS |
| P10 accent text on fold-light (copy on hero) | 5.61 | 7.27 | PASS |
| P11 accent-hover text on bg | 8.71 | 11.38 | PASS |
| P12 on-accent on accent (primary label) | 6.81 | 9.61 | PASS |
| P13 on-accent on accent-hover | 9.41 | 11.11 | PASS |
| P14 on-selection on selection | 12.03 | 8.89 | PASS |
| P15 text on fold-light (hover) | 13.60 | 11.26 | PASS |
| P16 text on selection (drag-over) | 12.03 | 8.89 | PASS |
| P17 caution text on caution-bg | 5.20 | 7.65 | PASS |
| P18 caution text on surface-raised (limit dialog) | 5.06 | 7.11 | PASS |
| P19 danger text on danger-bg (token not used in CSS) | 5.46 | 6.90 | PASS |
| P20 danger on surface (error glyph) | 6.68 | 6.89 | PASS |
| P21 caution rule on bg (UI) | 4.69 | 8.80 | PASS |
| P22 success icon on surface-raised (UI) | 6.81 | 7.95 | PASS |
| P23 input / checkbox / button border on surface (UI) | 3.56 | 3.21 | PASS, dark is close to 3:1 |
| P24 chip / toggle border on bg (UI) | 3.30 | 3.57 | PASS, light is close to 3:1 |
| P25 checked checkbox fill on surface (UI) | 6.81 | 8.84 | PASS |
| P26 focus ring on bg | 6.31 | 9.84 | PASS |
| P27 focus ring on surface | 6.81 | 8.84 | PASS |
| P28 focus ring on fold-light | 5.61 | 7.27 | PASS |
| P29 focus ring on surface-raised | 6.81 | 7.95 | PASS |
| P30 progress fill on track (UI) | 5.61 | 7.27 | PASS |
| P34 selected-row directory text (opacity .78) | 6.62 | 6.12 | PASS |
| P31 decorative hairline on surface | 1.53 | 1.38 | INFO, not required |
| P32 disabled primary label | 4.82 | 7.43 | EXEMPT (disabled) |
| P33 disabled secondary label | 6.92 | 7.05 | EXEMPT (disabled) |
| Opacity-dimmed aria-disabled primary label (.55, styles.css:53) | 2.58 | 3.74 | FAIL if the control counts as operable |
| Opacity-dimmed aria-disabled mode tab label (.6, styles.css:98) | 2.48 | 3.04 | FAIL if the control counts as operable |

Required pairs checked: 62 (31 pairs x 2 themes). Failing: 0. Opacity-dimmed rows are computed separately because the whole element, label included, is blended over the page.

Token comments: all 16 ratio claims in tokens.css match the computed values within 0.15, for both themes.

Shipped copies: desktop/ui/tokens.css and site/assets/tokens.css resolve to the same colour values as design/tokens.css. Only font URLs and comments differ.

## Results: static HTML (4 pages)

No findings. Title, lang, viewport and h1 present; every img has alt; every control has a name; no duplicate ids; all aria-* id references, label for= targets and `#` links resolve; heading order has no skips; no tabindex > 0.

Limits: this is markup only. Dynamic DOM from app.js and site.js is not covered.

## Results: type size

- App (styles.css): every declaration resolves to at least 13px. Smallest is `--app-text-caption` 0.8125rem = 13px, used for captions, code and paths. No issue.
- Site (site.css): every declaration resolves to at least 14px except site.css:49 `0.875em` (inline code). It is 14px in the 16px context, but would be 12.25px inside a 14px parent. No such parent exists in the current markup.

## Findings, ranked

| # | Severity | Location | Finding | Suggested fix |
|---|---|---|---|---|
| 1 | Medium | site/404.html:10 and :18 | `<base href="/bytepleat/">` makes the skip link `href="#main"` resolve to `/bytepleat/#main`. On the 404 page, activating it leaves for the home page instead of moving focus to main. | Drop the `<base>` element. Use root-absolute paths for assets and links (`/bytepleat/assets/site.css`, `/bytepleat/`, `/bytepleat/docs/`) so `#main` stays in-document. |
| 2 | Medium | desktop/ui/styles.css:53 and :98 | `aria-disabled` is dimmed by opacity (`.55` on buttons, `.6` on mode tabs). The label drops to 2.5 to 3.0:1 in light, 3.0 to 3.7:1 in dark. These controls stay focusable, so the disabled exemption is doubtful. | Replace opacity with the token states already used for `:disabled` (styles.css:51-52): `--color-fold-shade` and `--color-text-muted` for the button, `--color-text-muted` for the tab with no opacity. Or confirm the controls are truly inert and remove focusability. |
| 3 | Medium (not rendered) | desktop/ui/styles.css:36 and forced-colors block 496-503 | `.button` uses `border: 1px solid transparent`. The desktop forced-colors block does not restore a border on `.button-primary`. The site has the equivalent fix (site.css:524). Under Windows High Contrast the primary button may lose its boundary. | Add `.button-primary { border-color: ButtonText; }` inside `@media (forced-colors: active)` in styles.css. Verify in a forced-colors render. |
| 4 | Low | design/tokens.css:198-201 and :229-232 | Dark caution and danger tints (`#2a2016`, `#2d1a18`) are literals in both dark blocks, outside the raw-palette layer that the file says components should use. | Add `--raw-night-caution-bg` and `--raw-night-danger-bg` and reference them. |
| 5 | Low | design/tokens.css:81, :202, :233 (copies: desktop/ui/tokens.css:92, :213, :244; site/assets/tokens.css:93, :214, :245) | `--color-danger-text` is defined in all modes but not used by either stylesheet. Error glyphs use `--color-danger`. | Remove it, or use it for `.status-message.is-error` text, where it has the same colour. |
| 6 | Low | desktop/ui/tokens.css, site/assets/tokens.css (11.2K and 11.3K vs 10.6K source) | Two hand copies of the tokens. Colour values match today, but nothing enforces it. | Generate the copies in the build, or add a CI diff of the colour blocks against design/tokens.css. |
| 7 | Low | site/assets/site.css:49 | `font-size: 0.875em` on inline code. It shrinks inside any parent below 16px. | Use `0.875rem`, or keep `em` and add a rule against use inside 14px contexts. |
| 8 | Info | design/tokens.css:68 and :189 | Border-strong has the thinnest margin of any required pair: 3.30:1 light (P24, on bg) and 3.21:1 dark (P23, on surface). Both pass 3:1. | No change required. Avoid lightening these tokens or using them on a lighter surface. |

Also noted, not findings: desktop focus rules, link underlines and skip links are present.

## Could not verify

- **Screen readers.** No NVDA, JAWS, VoiceOver or Orca run. Live-region order (`#announce`, `#status-message`, `#selection-count`), focus moves on mode change and dialog focus return are untested.
- **Real rendering.** No browser screenshots. Fold animation, hover and transition states, drag-over, and text overflow in the 960px minimum window are unchecked.
- **color-mix() backgrounds.** Not computed: `.cap-note code`, `.selected-item:hover`, `.entry-row:hover`, `.progress-track` fill, and the folded fold-strip backgrounds.
- **Forced colours.** Windows High Contrast and Linux high-contrast themes are not rendered. Item 3 above is a code reading only.
- **Fonts and platform.** Instrument Sans and JetBrains Mono are not checked for glyph coverage or metrics against the system fallbacks (Segoe UI, Adwaita Sans, SF Mono). Windows and Linux text rendering, Tauri webview differences (WebView2, WebKitGTK) and subpixel AA are not checked.
- **Zoom and reflow.** 200% zoom, 320px width and the 960px app minimum are not rendered.
- **JS-driven state.** Theme toggle label (`site/assets/site.js:28`), history panel focus trap, and `aria-disabled` toggling in app.js are not verified in a browser.
- **Reduced motion.** Only read from CSS, not exercised.
- **Other audit output.** `design/audit/links-and-claims.md` is present in this folder and was not created by this audit. It was not read or changed.
