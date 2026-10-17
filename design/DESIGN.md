# Bytepleat design system v1

Status: proposed, ready to build. Covers the desktop app (Tauri 2, alpha), the website (GitHub Pages) and the GitHub README.
Files in this folder: `DESIGN.md` (this), `tokens.css` (all values), `pleat.svg` (signature motif), `mark.svg` (logo mark).

The one-line direction: **Bytepleat looks like a well-made sheet of paper, and the only time it shows off is when files fold into an archive or unfold out of one.**

---

## 1. Research: references and what to take from each

Research done 2026-10-17. "Verified" means the claim was read on the primary page today. "Unverified" means it comes from secondary sources or memory and must be checked before anyone quotes it.

| # | Reference | URL | Steal this | Source status |
|---|---|---|---|---|
| 1 | uv README (Astral) | https://github.com/astral-sh/uv | No banner. H1, a one-line tagline, three badges and then one image that proves the claim. Install commands go in one code block per OS, each with a `# On macOS and Linux.` comment instead of tabs. That works on GitHub, where tabs can't. | Verified |
| 2 | Spacedrive README | https://github.com/spacedriveapp/spacedrive | A single quick-links row under the badges (Download · Docs · Build from source), then a **status callout block above the screenshot** that sets expectations for a pre-release. | Verified |
| 3 | Keka (macOS archiver) | https://www.keka.io/en/ | Under the download button: **file size, OS requirement and checksum** in one quiet line. Formats are plain lists split into "creates" and "extracts", with no icons. | Verified |
| 4 | Ghostty download page | https://ghostty.org/download | One section per OS, each offering exactly two routes: direct download, or package manager / source. Each OS states its requirement ("macOS 13+"). | Verified |
| 5 | Tailscale download | https://tailscale.com/download | One target per OS with its own deep link (`/download/mac`). Install instructions get linkable URLs, so support replies can point at them. | Verified |
| 6 | Linear UI redesign | https://linear.app/now/how-we-redesigned-the-linear-ui | Themes are **generated from three inputs (base, accent, contrast) in LCH**, not hand-picked across 98 variables. They use a display cut for headings and the text cut everywhere else. We copy the discipline: few raw colours, semantic tokens on top. | Verified |
| 7 | Windows Fluent motion | https://learn.microsoft.com/en-us/windows/apps/design/motion/timing-and-easing | Exact durations **83 / 167 / 250 ms** and entrance easing `cubic-bezier(0,0,0,1)`. We adopt them for small transitions so the app feels native on Windows. | Verified |
| 8 | GNOME HIG, writing style | https://developer.gnome.org/hig/guidelines/writing-style.html | Use an **ellipsis only when the control asks for more input** ("Choose folder…"). No period on single-sentence labels. Use the user's words, not system jargon. (We do not copy GNOME's header-caps buttons: Bytepleat is sentence case everywhere.) | Verified |
| 9 | Apple Liquid Glass / HIG materials (macOS 26) | https://developer.apple.com/documentation/technologyoverviews/liquid-glass | The principle is that **content stays primary and material is reserved for controls and navigation**. We take the principle and not the glass: a Tauri webview cannot reproduce the system material faithfully, so fake glass would look cheap. | Unverified: only secondary sources were reachable. Read Apple's page before citing it. |
| 10 | Things 3 | https://culturedcode.com/things/ | Press quote on the page: "Lovely, unfolding animations keep your place" (WIRED). Motion exists to keep spatial continuity: **the thing you acted on is the thing that moves.** | Verified (quote present on the page) |
| 11 | Raycast | https://raycast.com/ | Keycaps recur as their visual motif because the keyboard is the product's core interaction. **Derive the motif from the core action.** For Bytepleat that is folding. | Verified (keycap motif described on the page) |
| 12 | Zed | https://zed.dev/ | Download is the single repeated CTA (nav, hero, close), always paired with "Clone source". We pair "Download" with "View source" the same way. | Verified |
| 13 | WCAG 2.2 Focus Appearance (2.4.13) | https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html | Focus indicator: at least a **2px perimeter at 3:1 contrast against the unfocused state**. That is AAA; we meet it anyway with a 2px accent outline and a 2px offset. | Verified |

Rejected after looking: Ollama's stat-and-logo hero (9M+ installs, partner logos). Bytepleat has no numbers to show and no speed claims to make. CleanShot's "There are average apps. And there's X" headline: we make no competitive boast. Arc, Warp, 1Password and Spacedrive's own site: not opened today, so nothing is claimed from them.

---

## 2. Plan (first pass)

**Concept: the pleat.** A wide sheet of files gathers into parallel folds and becomes compact, and can be opened again flat. The UI is the sheet: flat, calm paper with hairline creases. Folding happens only when an archive is made (fold) or opened (unfold).

**Palette (named, light / dark)**

| Name | Role | Light | Dark |
|---|---|---|---|
| Paper | window and page background | `#f4f7f4` | `#0f1613` |
| Sheet | lists, panels, drop zone | `#ffffff` | `#18211d` |
| Ink | text | `#17211d` | `#e4ece7` |
| Pleat | accent: primary button, links, progress, focus | `#17674d` | `#6fd0a8` |
| Mint | selection, drop target | `#bce5d4` | `#1f4536` |
| Fold light / Fold shade | the two faces of a pleat | `#e3ebe6` / `#cfdad3` | `#24312b` / `#141c18` |

Status colours: Caution `#9c6127` / `#e3a868`, Danger `#a3372e` / `#f28b80`. Muted text `#4f5d56` / `#9eada6`. Crease (hairline) `#c9d3cd` / `#2c3a34`. Strong crease (control borders) `#7d8b84` / `#62716a`.

**Type roles.** One family, Instrument Sans (variable, OFL-1.1): display, title, body and caption. JetBrains Mono (OFL-1.1) is used only for commands, file paths and checksums.

**Layout concept.** "Sheet over a band": a sheet (the content) above a fixed action band at the bottom of the window, where the primary action, the destination and the progress live. The band is where the fold lands.

**Principles**
1. Say what will happen before it happens: destination and format are always visible before the primary button.
2. Nothing irreversible is hidden. The app never overwrites, and the copy says so at the point of action.
3. Cancel is always one key away (Esc) and always honest about what was left behind.
4. Calm by default, one moment of delight (the fold).
5. Plain words. Errors name the fix.

---

## 3. Review against generic defaults, and what changed

| Generic tell | Was it in the plan? | Change made |
|---|---|---|
| Single accented or italic word in the headline | The first hero draft had "*exactly*" in italics | Removed. Headlines are one weight, one colour. |
| Tracked ALL-CAPS eyebrow above headings | Nearly: a "FORMATS" eyebrow above the formats table | Removed. Section headings stand alone. "Alpha" is a sentence-case chip, not an eyebrow. |
| 01 / 02 numbered markers | A "01 Create, 02 Extract, 03 Inspect" feature row | Removed: these are modes, not a sequence. Numbers survive only in the install steps (download → verify → open), which really are a sequence. They render as a plain `<ol>`. |
| Identical rounded cards with the same soft shadow | Three feature cards, four promise cards | Feature rows are full-width text + screenshot pairs that alternate sides. The promises are a definition list separated by crease lines. Shadows are assigned by role (`--shadow-sheet` is a 1px line, not a blur); only dialogs get a real shadow. |
| Gradient washes as decoration | Considered a mint-to-paper wash behind the hero | Removed. The only tonal variation in the system is the two pleat faces, which mean something: light and shadow on a fold. |
| Mono face for small labels | Planned mono for format chips ("tar.zst") | Changed: chips use Instrument Sans 600. Mono is reserved for text the user could type or copy. |
| "→" on links and buttons | "Download →" | Removed. Verb-first labels do the work. |
| Cream + serif + terracotta | Not present. Caution `#9c6127` sits near terracotta, so it is used only for warnings, never as decoration. | Kept with that rule. |
| Near-black + acid accent | Dark mode first used `#3dffa0` | Changed to `#6fd0a8`: a lit version of the brand green, 9.8:1 on dark paper. Bright enough to read, never neon. |
| Glass, blur, glow | Tempted by macOS 26 | Rejected (see reference 9). Flat sheet, real hairlines. |

**Where the boldness goes:** only the pleat. It appears as (a) the logo mark, (b) the hero illustration on the website, and (c) the fold/unfold animation and pleated progress strip in the app. Nowhere else: no pleat dividers, no pleat backgrounds, no pleat bullets.

---

## 4. Final system

### 4.1 Colour

All values live in `tokens.css`. Components use only semantic tokens (`--color-*`), never `--raw-*`.

Contrast, measured with the WCAG 2.x formula:

| Pair | Light | Dark |
|---|---|---|
| Text on bg | 15.3:1 | 15.3:1 |
| Text on surface | 16.5:1 | 13.7:1 |
| Muted text on bg / surface | 6.4 / 6.9:1 | 7.9 / 7.1:1 |
| Accent (link) on bg | 6.3:1 | 9.8:1 |
| On-accent text on accent (button) | 6.8:1 | 9.6:1 |
| Text on selection | 12.0:1 | 8.9:1 |
| Accent on selection (selected link) | 5.0:1 | n/a |
| Caution on bg | 4.7:1 | 8.8:1 |
| Caution text on caution-bg | 5.2:1 | 7.7:1 |
| Danger on bg | 6.2:1 | 7.7:1 |
| Danger text on danger-bg | 5.5:1 | 6.9:1 |
| Strong crease (checkbox, input border) on bg | 3.3:1 | 3.6:1 |

Notes:
- `--color-border` (hairline crease) is decorative and below 3:1 on purpose. Any boundary the user must perceive to operate a control uses `--color-border-strong`.
- Status is never colour alone. It always comes with an icon and words.
- Theme order: OS preference, overridden by `<html data-theme="light|dark">` from the in-app Appearance menu (System / Light / Dark). The site follows the OS only.
- `forced-colors: active` maps focus and borders to system colours.

### 4.2 Typography

**Choice: Instrument Sans** (Instrument; SIL OFL-1.1; variable axes `wght` 400–700 and `wdth` 75–100, per the official repo https://github.com/Instrument/instrument-sans and Fontsource. Read the bundled OFL text when packaging.)

Why this face for this brief:
- It is a neutral, slightly squarish grotesque with open apertures, so it reads well at 13–14px in dense file lists without the Inter / SF lookalike default.
- It has a **width axis**. Compression is the product, and the compact width (88%) on the website H1 is a quiet nod to it without becoming a gimmick. The app keeps 100% width (96% on titles) for legibility.
- One variable file covers every role, so self-hosting stays small.
- Alternatives rejected: Geist (strongly associated with Vercel, reads as "startup default"), Bricolage Grotesque (too characterful for a utility), Fraunces (serif; pulls toward the cream + serif tell), Hanken Grotesk (good, but no width axis).

**JetBrains Mono** (JetBrains; OFL-1.1) is used only for commands, paths and checksums. Inside the app the system mono stack is an acceptable fallback, so the app need not ship it.

**App scale** (never below 13px)

| Role | Size / line height | Weight | Width | Tracking | Use |
|---|---|---|---|---|---|
| Display | 28 / 32 | 650 | 92% | -0.022em | empty-state heading only |
| Title | 20 / 26 | 600 | 96% | -0.012em | mode title ("Create an archive") |
| Subhead | 16 / 22 | 600 | 100% | 0 | section headings inside a mode |
| Body | 14 / 20 | 400 | 100% | 0 | everything by default |
| Body strong | 14 / 20 | 600 | 100% | 0 | file names in lists, button labels |
| Caption | 13 / 18 | 450 | 100% | 0 | sizes, counts, help lines |
| Mono | 13 / 18 | 400 | n/a | 0 | paths, commands |

**Site scale** (fluid from 360 to 1440px; see `tokens.css`)

| Role | Size | Line height | Weight | Width | Tracking |
|---|---|---|---|---|---|
| H1 | 38 → 64 | 1.02 | 650 | 88% | -0.022em |
| H2 | 26 → 36 | 1.15 | 600 | 96% | -0.012em |
| H3 | 19 → 22 | 1.3 | 600 | 100% | 0 |
| Lead | 18 → 21 | 1.5 | 400 | 100% | 0 |
| Body | 17 | 1.6 | 400 | 100% | 0 |
| Small | 14 | 1.5 | 450 | 100% | 0 |

Line length: body text `max-inline-size: 68ch`, never above 78ch. The H1 is capped at 18ch so it breaks into two or three lines.

Numerals: `font-variant-numeric: tabular-nums` in lists, progress and history (sizes and counts must not jitter).

### 4.3 Spacing, radii, elevation

- 4px base: 4, 8, 12, 16, 24, 32, 48, 64, 96.
- Rows and controls are 36px tall; the primary action is 44px.
- Radii by role: control 6, checkbox 4, sheet 10, dialog 14, pill (status chip only) 999.
- Elevation by role: the sheet is a 1px crease line (no blur). Raised (menus, popovers) is a small two-step shadow. Dialogs get a strong shadow. Pleat faces get an inner crease line (`--shadow-fold`). In dark mode, borders replace most shadow.

### 4.4 Motion

| Token | Value | Use |
|---|---|---|
| `--dur-instant` | 83ms | hover, press |
| `--dur-fast` | 167ms | tab switch, checkbox, state swap |
| `--dur-normal` | 250ms | drawer, dialog, toast enter/exit |
| `--dur-fold` | 520ms | signature fold and unfold only |
| `--ease-enter` | `cubic-bezier(0,0,0,1)` | things arriving |
| `--ease-exit` | `cubic-bezier(0.3,0,1,1)` | things leaving |
| `--ease-fold` | `cubic-bezier(0.65,0,0.25,1)` | the fold: weighted, settles like cloth |

Small transitions move at most 8px and fade. Lists never animate row by row, except during the fold.

Reduced motion (`prefers-reduced-motion: reduce`): durations become 0, except 120ms opacity crossfades. The fold jumps to its end state. The progress strip becomes a plain filled bar. Nothing loops.

### 4.5 Focus, keyboard, accessibility

- Focus ring: 2px `--focus-color` outline with a 2px offset on `:focus-visible`, on every interactive element, in both themes. It is never removed.
- Hit targets are at least 36×36px (24px is the WCAG 2.5.8 AA minimum; we exceed it).
- Every state change that matters is announced through one `aria-live="polite"` status region. Errors use `role="alert"` once.
- The progress strip is `role="progressbar"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax` and `aria-valuetext` ("412 of 1,280 files").
- Keyboard map (shown in a Help → Keyboard shortcuts dialog; Cmd on macOS, Ctrl elsewhere):

| Keys | Action |
|---|---|
| Cmd/Ctrl+1 / 2 / 3 | Create / Extract / Inspect |
| Cmd/Ctrl+O | Choose files… (Create) or Open archive… (Extract, Inspect) |
| Cmd/Ctrl+Shift+O | Choose folder… |
| Cmd/Ctrl+Enter | Primary action (Create archive / Extract / Inspect) |
| Esc | Cancel running job (asks nothing; cancel is safe) / close drawer or dialog |
| Cmd/Ctrl+Y | Show history drawer (960px layout) |
| Space | Toggle checkbox in the entry list |
| Cmd/Ctrl+A | Select all listed entries (selective extract) |
| Delete / Backspace | Remove focused file from the selection |
| Arrow keys | Move within list, segmented control and format group (roving tabindex) |

---

## 5. Signature motif: the pleat

`pleat.svg` shows a flat sheet with three text lines on the left that gathers into nine pleats on the right, the faces narrowing as the fold tightens. It is drawn entirely in `currentColor` with fill-opacity (lit faces .92, shaded .42, flat sheet .14), so it inherits the accent in either theme.

`mark.svg` is the same idea reduced to four faces (lit, shade, lit, shade) on a 32px grid. It stays legible at 16px.

Construction rule for all pleat drawings: faces are vertical parallelograms between crease lines. Top and bottom vertices alternate by about 1/8 of the face height to suggest depth. Lit and shaded faces alternate. There are no outlines on faces, and the crease is the edge where the two tones meet.

---

## 6. Desktop app

### 6.1 Window anatomy

The default window size is 960×640 and the minimum is 760×520; the design target is 1280×800. On startup the window is clamped to fit the screen's work area (the monitor minus taskbar or Dock) when the default plus a 48px margin does not fit, and then it is centred. The OS draws the native title bar and frame. There is no custom chrome, because Tauri's custom decorations break platform conventions.

Regions:
1. **Header** (56px): mark (20px) + "Bytepleat" (Subhead) + "Alpha" chip; mode switch (segmented control: Create · Extract · Inspect); on the right, History button (windows narrower than 1200px only) and an Appearance menu (System / Light / Dark).
2. **Mode title row** (Title + one Body line explaining the mode).
3. **Sheet**: the drop zone when empty, the file or entry list when filled. Lists scroll internally. At window heights of 640px or less the empty drop zone keeps its full height and the area above the band scrolls instead. The action band stays anchored at the bottom, and the window itself never scrolls.
4. **Options row** (Create: format group; Extract: destination note; Inspect: cap note).
5. **Action band** (72px, fixed at the bottom, `--color-surface`, top crease line): destination on the left, primary button on the right. During a job the band becomes the pleated progress strip + Cancel.
6. **History**: a persistent right panel (288px) at window widths ≥1200px; a right drawer opened by the History button below 1200px.

**960×640 (default)**

```
+------------------------------------------------------------------------------+
| [pleat] Bytepleat  Alpha      ( Create | Extract | Inspect )   History  ◐    |  56
+------------------------------------------------------------------------------+
|  Create an archive                                                           |
|  Pack files or folders into one new archive. Your originals stay put.       |
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  |                                                                        |  |
|  |                     (sheet: drop zone or file list)                    |  |  ~300
|  |                                                                        |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  Format   ( ZIP | 7z | tar.zst | tar.gz | tar.lz4 )                          |
|           Classic ZIP. Opens almost anywhere.                                |
+------------------------------------------------------------------------------+
|  Save to  ~/Desktop/project.zip   Change…                [ Create archive ]  |  72
+------------------------------------------------------------------------------+
```

**1280×800 (target)**

```
+----------------------------------------------------------------------------------------------+
| [pleat] Bytepleat  Alpha             ( Create | Extract | Inspect )                       ◐  |
+------------------------------------------------------------------------+---------------------+
|  Create an archive                                                     |  History            |
|  Pack files or folders into one new archive. Your originals stay put. |                     |
|                                                                        |  project.zip        |
|  +------------------------------------------------------------------+  |  Created · 2 min ago|
|  |                                                                  |  |  Show in folder     |
|  |                 (sheet: drop zone or file list)                  |  |  ------------------ |
|  |                                                                  |  |  photos.7z          |
|  |                                                                  |  |  Extracted · 1 h ago|
|  +------------------------------------------------------------------+  |  ------------------ |
|                                                                        |  backup.tar.zst     |
|  Format   ( ZIP | 7z | tar.zst | tar.gz | tar.lz4 )                    |  Cancelled · today  |
|           Classic ZIP. Opens almost anywhere.                          |                     |
+------------------------------------------------------------------------+                     |
|  Save to  ~/Desktop/project.zip   Change…          [ Create archive ]  |                     |
+------------------------------------------------------------------------+---------------------+
```

Horizontal padding is 24px at 960 and 32px at 1280. The sheet fills the available height. Format descriptions sit under the group, never in tooltips.

### 6.2 States, wireframes and exact microcopy

Copy conventions used below: `[Button]`, `( segmented )`, `[x]` checkbox, `…` means a picker opens.

#### A. Empty (Create, first run)

```
|  Create an archive                                                           |
|  Pack files or folders into one new archive. Your originals stay put.       |
|  +- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -+  |
|  |                         [ pleat.svg, flat, 160px ]                     |  |
|  |                     Drop files or folders here                         |  |
|  |               [ Choose files… ]   [ Choose folder… ]                   |  |
|  |            Nothing leaves this device. Nothing is overwritten.         |  |
|  +- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -+  |
|  Save to  Not chosen yet   Choose…                    [ Create archive ]     |
|           Choose what to archive first.                 (disabled)           |
```

- Drop zone: 1.5px dashed `--color-border-strong`, radius sheet. On drag-over: background `--color-selection`, border solid accent, and the pleat illustration closes slightly (scaleX .92, 167ms). This hints at the fold to come.
- Heading (Display): **Drop files or folders here**
- Buttons: **Choose files…** · **Choose folder…**
- Reassurance (Caption, muted): **Nothing leaves this device. Nothing is overwritten.**
- Disabled-button reason (Caption, next to the button, also `aria-describedby`): **Choose what to archive first.**
- Extract empty heading: **Drop an archive here** · button **Open archive…** · caption **ZIP, 7z, tar.zst, tar.gz and tar.lz4.**
- Inspect empty heading: **Drop an archive to see what is inside** · button **Open archive…** · caption **Inspecting only reads the archive. Nothing is extracted.**

#### B. Files chosen

```
|  +------------------------------------------------------------------------+  |
|  |  report.pdf                                   2.4 MB               ✕   |  |
|  |  photos/                                      318 files · 1.1 GB   ✕   |  |
|  |  notes.md                                     4 KB                 ✕   |  |
|  |  ----------------------------------------------------------------------|  |
|  |  3 items · 1.1 GB          [ Add files… ]  [ Add folder… ]  Clear all  |  |
|  +------------------------------------------------------------------------+  |
```

- Rows are 36px: name (Body strong), size or count (Caption, tabular, muted) and a remove button (icon, accessible name **Remove report.pdf from the selection**).
- Footer: **3 items · 1.1 GB**, then **Add files…** · **Add folder…** · **Clear all** (text button).
- When the folder size is still being counted: **Counting…** in the size column, never a spinner.
- The destination is auto-suggested beside the first item: **Save to ~/Desktop/project.zip**, then **Change…**
- If the suggested name exists, Bytepleat proposes the next free name (`project 2.zip`) and says so in Caption: **project.zip already exists, so this will be saved as project 2.zip.**

#### C. Format choice

Segmented radio group (`role="radiogroup"`, arrow keys). The description under it updates on selection (167ms crossfade):

| Option label | Description (exact) |
|---|---|
| ZIP | Classic ZIP. Opens almost anywhere. Up to 65,534 files. |
| 7z | Smaller archive for people who have 7-Zip or Keka. |
| tar.zst | Compressed tar with Zstandard. Common on Linux and macOS. |
| tar.gz | Compressed tar with gzip. Opens on nearly every Unix system. |
| tar.lz4 | Compressed tar with LZ4. Needs a tool that reads LZ4. |

There is no speed or ratio language anywhere. Under the group: **What each format supports** (link to the in-app formats dialog). Default: ZIP.

#### D. Running: progress + cancel (signature fold plays first)

```
|  +------------------------------------------------------------------------+  |
|  |  (rows folded away; sheet shows)                                       |  |
|  |      Creating project.zip                                              |  |
|  |      Writing to a temporary file. It becomes project.zip when done.    |  |
|  +------------------------------------------------------------------------+  |
+------------------------------------------------------------------------------+
|  /\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/____________________  [Cancel] |
|  412 of 1,280 files · 380 MB of 1.1 GB                                        |
+------------------------------------------------------------------------------+
```

- Sheet heading (Title): **Creating project.zip** / Extract: **Extracting photos.7z** / Inspect: **Reading photos.7z**
- Sheet line (Body, muted): **Writing to a temporary file. It becomes project.zip when done.** Extract: **Extracting into a staging folder first. Nothing appears in Downloads until it is complete.**
- Progress strip, 40px tall: completed portion = pleat faces (accent lit / accent at 70%), remaining = flat `--color-fold-light`. The leading edge is a crease. `aria-valuetext` = the count line.
- Count line (Caption, tabular): **412 of 1,280 files · 380 MB of 1.1 GB**
- When the total is unknown (streams): a flat strip with a single crease travelling every 1.6s (removed under reduced motion), and the line reads **412 files so far · 380 MB**
- **Cancel** is a secondary button with focus moved to it when the job starts. Esc triggers it. No confirmation: cancel is always safe.
- The mode switch and inputs are disabled with `aria-disabled` and the reason **A job is running. Cancel it to change things.**

**Cancelled** (band returns, sheet message):
- Title: **Cancelled**
- Body: **Nothing was saved. The temporary file was removed, and your originals are untouched.**
- Extract variant: **Nothing was extracted. The staging folder was removed.**
- Buttons: **Start again** (primary, same choices restored) · **Change files**

#### E. Success with Show in folder (signature unfold plays on extract)

```
|  +------------------------------------------------------------------------+  |
|  |  [mark, accent]  project.zip is ready                                  |  |
|  |  1,280 files packed into 642 MB.                                       |  |
|  |  ~/Desktop/project.zip                                                 |  |
|  |  [ Show in folder ]   Test archive   Create another                    |  |
|  +------------------------------------------------------------------------+  |
```

- Create Title: **project.zip is ready**
- Body: **1,280 files packed into 642 MB.** (Facts only: no "saved 42%!" and no speed.)
- Path in mono, selectable, with a copy button labelled **Copy path**.
- Primary: **Show in folder** (macOS label: **Show in Finder**; Windows: **Show in File Explorer**; Linux: **Show in folder**). Secondary: **Test archive** (runs the full decode check) · **Create another** (text).
- Extract Title: **Extracted to photos-extracted** · Body: **318 files, 1.1 GB. The archive itself was not changed.** · Primary **Show in folder** · Secondary **Extract another**
- Test result: **Test passed. Every file in project.zip decoded without errors.** (Caption under it: **This checks the archive's integrity. It does not check who made it or scan for malware.**)
- Focus moves to the primary button. Live region announces the Title + Body.

#### F. Error with a plain-language fix

```
|  +------------------------------------------------------------------------+  |
|  |  [!]  Could not create project.zip                                     |  |
|  |  There is not enough free space on Macintosh HD. About 650 MB more is  |  |
|  |  needed. Free some space or choose another location, then try again.   |  |
|  |  Nothing was saved and your originals are untouched.                   |  |
|  |  [ Choose another location… ]   Try again    Technical details  v      |  |
|  +------------------------------------------------------------------------+  |
```

Structure, always in this order: **what failed** (Title) → **why, in plain words** → **the fix** → **what state things are in** → actions. "Technical details" is a disclosure that shows the raw error in mono with **Copy details**. Icon + Danger colour on the icon and the left crease only; the body text stays Ink.

Exact messages:

| Cause | Title | Body | Primary action |
|---|---|---|---|
| Not enough space | Could not create project.zip | There is not enough free space on {volume}. About {n} more is needed. Free some space or choose another location, then try again. Nothing was saved and your originals are untouched. | Choose another location… |
| No permission (destination) | Could not save to {folder} | Bytepleat is not allowed to write there. Choose a folder you own, such as Documents or Desktop. Nothing was saved. | Choose another location… |
| No permission (source) | Could not read {name} | Bytepleat is not allowed to open this file. Check that it is not open in another app, or remove it from the selection. Nothing was saved. | Remove it and continue |
| Destination exists (extract) | photos-extracted already exists | Bytepleat never replaces existing files. Choose another location, or rename or move the existing folder. Nothing was extracted. | Choose another location… |
| Unsupported format | Bytepleat cannot open RAR archives | It can read ZIP, 7z, tar.zst, tar.gz and tar.lz4. To open this file, use a tool that supports RAR, such as The Unarchiver or 7-Zip. | See supported formats |
| Encrypted / ZIP64 / split | Bytepleat cannot open this ZIP | It is {password-protected / larger than classic ZIP allows / split into parts}, which Bytepleat does not support yet. Try 7-Zip or your system's archive tool. | See supported formats |
| Damaged archive | photos.7z looks damaged | Part of the file could not be read, so nothing was extracted. If you downloaded it, download it again. If someone sent it, ask them to send it again. | Close |
| Over the size cap | photos.7z would unpack to more than 1 GB | Bytepleat stops large extractions to protect your disk. Use the command line with a higher limit, for example `bytepleat unpack photos.7z --max-output 8GiB`. Nothing was extracted. | Copy command |
| Over the entry cap | Too many files in this archive | It has more than 100,000 entries, which is Bytepleat's safety limit. Nothing was extracted. | Close |
| Too many for ZIP | ZIP can hold up to 65,534 files | Your selection has 71,200. Choose 7z or a tar format instead. | Choose 7z |
| Unsafe path in archive | photos.zip contains an unsafe path | One entry tries to write outside the destination folder ({path}). Bytepleat stopped and extracted nothing. Do not trust this archive. | Close |
| Links / special files | Some entries were skipped | {n} entries are links or special files, which Bytepleat does not extract. The other {m} files were extracted. | Show in folder |
| Unknown | Something went wrong while creating project.zip | Nothing was saved and your originals are untouched. Try again. If it happens again, copy the technical details and report it. | Try again |

The `--max-output` flag in the size-cap row is a placeholder: confirm the real CLI option name in `docs/security-limits.md` before shipping. Do not invent it.

#### G. Inspect list, with the 5,000-entry cap

```
|  photos.7z · 7z · 12,408 entries · 1.1 GB unpacked                         |
|  +------------------------------------------------------------------------+  |
|  |  Name                                   Size        Modified            |  |
|  |  photos/2024/IMG_0001.jpg               3.1 MB      12 Mar 2024         |  |
|  |  ...                                                                    |  |
|  +------------------------------------------------------------------------+  |
|  [i] Showing the first 5,000 of 12,408 entries. Only listed entries can be   |
|      chosen for extraction. To get everything, extract the whole archive.    |
+------------------------------------------------------------------------------+
|                                  [ Extract everything… ]  [ Choose entries ]  |
```

- Summary line (Caption): **photos.7z · 7z · 12,408 entries · 1.1 GB unpacked**
- Columns: Name (path, folders shown as prefix in muted), Size, Modified. Sortable by keyboard (Enter on header).
- Cap note (Caution colours, info icon, only when total > 5,000): **Showing the first 5,000 of 12,408 entries. Only listed entries can be chosen for extraction. To get everything, extract the whole archive.** For a full listing, a second line in Caption: **For the full list, run `bytepleat info photos.7z --json`** (with Copy).
- Under the cap: **Showing all 318 entries.**
- Inspect is read-only. The header line repeats this: **Reading only. Nothing is extracted.**

#### H. Selective-extract review, with checkboxes

```
|  Choose what to extract from photos.7z                                       |
|  +------------------------------------------------------------------------+  |
|  | [-] Select all listed (5,000)                       12 of 5,000 chosen  |  |
|  | [x] photos/2024/IMG_0001.jpg                        3.1 MB              |  |
|  | [ ] photos/2024/IMG_0002.jpg                        2.9 MB              |  |
|  +------------------------------------------------------------------------+  |
|  Extracts 12 files (38 MB) into a new folder: ~/Downloads/photos-extracted   |
|  If that folder already exists, the job stops instead of replacing anything. |
+------------------------------------------------------------------------------+
|  Into  ~/Downloads   Change…                         [ Extract 12 files ]     |
```

- Checkboxes are 18px boxes with 36px rows; the whole row toggles. The tri-state header checkbox has the label **Select all listed (5,000)**.
- Counter (Caption, live, polite, debounced 500ms): **12 of 5,000 chosen**
- Review line: **Extracts 12 files (38 MB) into a new folder: {path}**, followed by **If that folder already exists, the job stops instead of replacing anything.**
- The primary label carries the count: **Extract 12 files** / **Extract 1 file**
- Secondary: **Extract everything instead** (text button).

#### I. Empty selection rejected

When the user presses Extract with zero chosen (the button stays enabled so the reason can be explained, since a disabled button explains nothing):
- Inline message above the band, Caution style, `role="alert"`: **Choose at least one entry to extract. Nothing was started.**
- Focus moves to the "Select all listed" checkbox. The message clears as soon as one box is ticked.

#### J. Multiple archives dropped

On Extract or Inspect with two or more archives dropped:
- Sheet notice (info, not error): **Bytepleat opens one archive at a time. It kept the first one: photos.zip.**
- Second line (Caption): **The other 2 were not opened: backup.7z, logs.tar.zst.**
- Action: **Open a different one…**
- Mixed drop on Create (files + archives): every item is treated as a file to pack. Notice: **2 archives were added as files. To open an archive instead, switch to Extract.**
- Drop of an archive on Create with nothing else: offer **Extract photos.zip instead?** with **Switch to Extract** / **Add it as a file**.

#### K. History list

Panel at ≥1200px, drawer below that. The newest job is first, and the list keeps the last 50 jobs for this device only.

```
|  History                               Clear history  |
|  project.zip                                         |
|  Created · 1,280 files · 642 MB · 2 min ago          |
|  Show in folder                                      |
|  ---------------------------------------------------|
|  photos.7z                                           |
|  Extracted · 12 files · 14:02                        |
|  Show in folder                                      |
|  ---------------------------------------------------|
|  backup.tar.zst                                      |
|  Cancelled · nothing saved · yesterday               |
|  ---------------------------------------------------|
|  logs.zip                                            |
|  Failed · not enough space · 3 Oct                   |
```

- Entry: name (Body strong), status line (Caption: verb · facts · relative time), and one action if the output still exists (**Show in folder**). If the output was moved or deleted: **File no longer there**, muted, no action.
- Status words: Created, Extracted, Inspected, Tested, Cancelled, Failed. A status icon (check, minus, alert) accompanies the word; colour is never used alone.
- Empty: **Your jobs will appear here. History stays on this device.**
- **Clear history** asks once in a small dialog: **Clear history? This removes the list only. Your archives and files are not touched.** · **Clear history** / **Keep**

### 6.3 Light and dark

Both themes share the same layout and tokens. Specific dark rules:
- The sheet is lighter than the paper (`#18211d` on `#0f1613`), and elevation comes from lightness, not shadow.
- In dark mode the primary button is the light accent `#6fd0a8` with dark text `#0b1a14` (9.6:1), not white-on-green, so it stays the brightest thing in the window.
- Pleat faces use `--color-fold-light` / `--color-fold-shade`, which invert their relationship correctly in dark: the lit face is lighter than the sheet and the shaded face is darker.
- The Appearance menu lists **System**, **Light**, **Dark**, in that order. The choice persists locally.

### 6.4 Motion

**Signature moment: the fold** (Create, on pressing Create archive)
1. 0–80ms: the primary button presses (scale .98) and the mode switch dims.
2. 80–600ms (`--dur-fold`, `--ease-fold`): the visible file rows (up to 8; extra rows are represented by one more face) become pleat faces. Even rows hinge from their top edge and odd rows from their bottom edge (`rotateX` to ±64°, `perspective: 700px`). Their backgrounds crossfade to fold-light / fold-shade, and the list height collapses toward the action band. Text fades out over the first 160ms, so nothing is read mid-rotation.
3. At the end, the folded stack *is* the progress strip: it lands in the band, and progress continues as pleats closing from left to right.
4. Implementation: CSS transforms + opacity only (GPU-friendly), with no layout animation except one `height` collapse on the sheet container. Use the FLIP technique for the landing.

**Reverse: the unfold** (Extract success): the strip in the band lifts and opens into up to 8 rows of the top-level extracted entries, with the same timing in reverse (`--ease-fold`). Then the success content appears.

The fold does not play for Inspect (nothing is being made) or for jobs under 300ms (it would hold up the result). For those, the success state appears with a 167ms crossfade.

**Small functional transitions**: tab switch is a 167ms crossfade with a 4px rise. Format description is a 167ms crossfade. The drawer slides in 250ms enter / 167ms exit, 288px. Dialogs scale .98→1 + fade, 250ms. The drag-over drop zone takes a 167ms background change and its pleat closes slightly. Row remove is a 167ms fade + height collapse. Nothing bounces, and nothing overshoots.

**Reduced motion**: the fold and unfold are replaced by a 120ms crossfade between states. The progress strip is a flat bar filling left to right without animated creases. The indeterminate crease does not travel; the count text alone shows activity.

### 6.5 Copy rules

1. Sentence case everywhere: buttons, titles, menus, tabs.
2. Buttons are plain verbs + object: "Create archive", "Extract 12 files", "Show in folder". Never "OK", "Submit" or "Proceed".
3. An ellipsis means a picker or dialog follows ("Choose folder…"). No ellipsis otherwise.
4. Errors follow what failed → why → fix → current state. No blame ("you did"), no codes in the main text, and no "Oops" or "Uh-oh".
5. Always state the safety fact at the moment it matters ("Nothing was saved", "The archive itself was not changed").
6. No speed, ratio-percentage or "blazing" language. Report sizes and counts as facts.
7. No exclamation marks. No emoji.
8. Numbers: use thousands separators by locale. Sizes are decimal units (KB, MB, GB) with one decimal above 10 MB. Times are relative for under 24 hours and dates otherwise.
9. No period on single-sentence labels or captions. Use periods in multi-sentence bodies.
10. "Archive" for the container, "files" for what the user dropped, "entries" only inside Inspect/selective extract (where folders count too).

---

## 7. Website (GitHub Pages)

One page plus `/install/{macos,windows,linux}` anchors. Static HTML + `tokens.css` + self-hosted fonts. No analytics, trackers, cookies or external requests: the site practises what the app promises.

Container: `max-inline-size: var(--site-max)` (1152px) with `--gutter-site` (16 → 40px). Breakpoints: 360 (base), 640, 960, 1200, 1440.

### 7.1 Sections in order

**1. Header** (sticky only on ≥960px, 64px; static on mobile)
- Mark + "Bytepleat" on the left. On ≥640: links **Install** · **Formats** · **FAQ** · **Source on GitHub**. On <640: Install + a menu button labelled **Menu**.

**2. Hero** (the one bold place on the site)

```
1440                                                         360
+--------------------------------------------------------+   +----------------------+
| Pack files into ZIP, 7z or tar.     [ sheet of file    ]|   | Pack files into ZIP, |
| Get the same bytes back.            [ names folding    ]|   | 7z or tar. Get the   |
|                                     [ into pleats, and ]|   | same bytes back.     |
| A small, careful archiver for your  [ labelled         ]|   |                      |
| desktop and terminal. It never      [ project.zip      ]|   | A small, careful ... |
| overwrites, stops when you cancel,  [                  ]|   | [ Download for macOS]|
| and keeps files on your device.                         |   | Other systems · Source|
|                                                         |   | [ fold illustration ]|
| [ Download for macOS ]  View source                     |   |  full width, 180px   |
| Version 0.5.1 · 4.1 MB · macOS 13+ · SHA-256            |   |                      |
+--------------------------------------------------------+   +----------------------+
```

- H1: **Pack files into ZIP, 7z or tar. Get the same bytes back.**
- Lead: **A small, careful archiver for your desktop and terminal. It never overwrites, stops when you cancel, and keeps your files on your device.**
- Primary button: **Download for {detected OS}** (falls back to **Download** linking to #install without JS). Secondary text link: **View source**. Under them (Small, muted, Keka-style): **Version 0.5.1 · {size} · {requirement} · SHA-256 checksum**, where "SHA-256 checksum" links to the `.sha256` file. Below that, the alpha status in one line: **The desktop app is an early alpha. The command-line tool is the stable part.**
- Hero visual: an inline SVG + CSS (not video, not a raster image). A white sheet (`--color-surface`, 1px crease) lists six real-looking names (report.pdf, photos/, notes.md, budget.xlsx, slides.key, readme.txt) in Body. About 600ms after first paint, the sheet folds into pleats using the same construction as `pleat.svg` and the app fold timing, and a label **project.zip · 1 archive** appears under the folded band. A small text button **Unfold** under it plays the reverse, and toggles to **Fold**. It never autoplays again or loops.
- Responsive: two columns (text 6/12, visual 6/12) on ≥960; stacked with the visual after the buttons on <960; visual height 180px on 360 and 320px on 1440.
- Reduced motion: renders the folded end state with the six names listed beside it at 40% opacity, and the Fold/Unfold toggle swaps states without animation.

**3. What it does** (H2: **Three things, done carefully**)
- Three full-width rows, alternating text left/right on ≥960 and stacked on mobile. Each has an H3, two sentences and a screenshot (light/dark via `<picture>`):
  - **Create an archive.** *Drop files or folders, choose ZIP, 7z or compressed tar, and pick where it goes. Bytepleat writes to a temporary file and only names it when it is complete.*
  - **Extract into a new folder.** *Everything lands in a fresh folder next to the archive, never on top of existing files. Choose only the entries you need, or take the whole archive.*
  - **Look inside first.** *Inspect lists what an archive holds without extracting anything. Test decodes every byte to check it is intact.*
- The screenshots are real app captures (see the asset list). No device frames and no mock browser chrome.

**4. Promises** (H2: **What Bytepleat will not do**)
- A definition list in two columns on ≥960 and one column on mobile, separated by crease lines. No cards and no icons.
  - **Overwrite your files.** If a name is taken, the job stops or picks a new name, and tells you which.
  - **Send anything anywhere.** No accounts, no uploads, no telemetry. It works offline.
  - **Hold you hostage.** Cancel at any time; partial output is cleaned up.
  - **Invent a format.** Everything it writes opens in standard tools.
  - **Make speed claims.** We publish benchmarks with their method, and you can rerun them. (Links to docs/benchmarks.md.)

**5. Install** (H2: **Install**, `id="install"`)
- Tabs: **macOS** · **Windows** · **Linux** · **From source**. They are ARIA tabs (`role="tablist"`, arrow keys, Home/End). The default tab matches the detected OS. Without JS all four panels render stacked with H3s (Ghostty pattern), and each panel has a linkable anchor (`#install-macos`), Tailscale-style.
- Each panel holds a requirement line, the download button, then a short `<ol>` (a true sequence): **Download** → **Check the checksum** → **Open it**, each with a copyable command in mono. A copy button sits on each code block, with accessible name **Copy command** and visible feedback **Copied** for 2s.
- Honest notes inline (Caution style): **Packages are not signed yet. macOS will warn you the first time; here is how to open it anyway.** · **Windows needs the Microsoft Visual C++ runtime (x64).** · **There is no Linux ARM64 build yet.**
- At 360px, tabs scroll horizontally inside their own row (no page scroll) and code blocks wrap (`white-space: pre-wrap; overflow-wrap: anywhere`).

**6. Formats** (H2: **Formats**)
- A real `<table>` with Format, Create, Open and test, and Limits columns. Rows: ZIP, 7z, tar + Zstandard, tar + gzip, tar + LZ4, Zstandard / gzip / LZ4 (single file, CLI only), RAR. The cells are text: "Yes", "No", "Recognised only", never ✓/✗ alone.
- On <640 each row becomes a stacked block (CSS grid with `data-label` headers via `::before`), with no horizontal scroll.
- Under the table: **Not supported: passwords and encryption, ZIP64, split archives, RAR extraction.** Link: **Exact limits**.

**7. Honest comparison** (H2: **When to use something else**)
- A short lead: **Bytepleat is small and strict on purpose. Mature tools do more.**
- A table with columns Bytepleat, 7-Zip, Keka, The Unarchiver and tar + zstd. Rows: Platforms; Creates archives; Opens RAR; Passwords and encryption; Graphical app; Command line; Maturity. Bytepleat's column states its gaps plainly (Opens RAR: No; Encryption: No; Maturity: Alpha app, 0.5 CLI).
- **Every competitor cell must be checked against that project's own site in the week of publishing**, with an "as of {date}" line under the table. Nothing in this design asserts competitor facts.
- Responsive: on <960 the table becomes one block per tool.

**8. FAQ** (H2: **Questions**), using `<details>`/`<summary>` with a chevron rotation (167ms, none under reduced motion). Questions:
- **Why is it called Bytepleat?** A pleat is a fold that makes something wide compact and lets it open flat again. That is the job.
- **Is it faster or smaller than 7-Zip?** Sometimes, sometimes not. It uses the same standard codecs. Our benchmarks show the method and results so you can judge.
- **Does it upload my files?** No. Bytepleat makes no network requests. You can run it offline.
- **Why does macOS say it cannot check the app?** The alpha is not notarised yet. Here is how to open it, and how to verify the checksum first.
- **Can it open RAR or password-protected ZIPs?** Not yet. Use The Unarchiver, Keka or 7-Zip for those.
- **What happens if I cancel?** The job stops, temporary output is deleted, and your originals are untouched.
- **Is the desktop app ready for daily use?** It is an alpha. The command-line tool is further along.

**9. Footer**
- Mark (muted), **Bytepleat 0.5.1 · MIT licence**, then links: **Source** · **Changelog** · **Security** · **Third-party licences** · **Report a problem**. Last line: **This site uses no cookies, trackers or external fonts.** No newsletter, no social icons.

### 7.2 Responsive rules (360 → 1440)

- At 360px: 16px gutters, single column, H1 38px, body 17px, buttons full width (stacked). The pleat hero sits below the CTAs. No horizontal scroll at any width (test 360, 390, 768, 1024, 1280, 1440).
- At 640: inline buttons, header links visible.
- At 960: two-column hero, alternating feature rows, sticky header.
- At 1200–1440: content is capped at 1152px; only the hero visual grows (to 560px wide).
- Images use `width`/`height` attributes, `loading="lazy"` below the fold, and `<picture>` with `prefers-color-scheme` sources.

---

## 8. README

**Tone**: same as the site. First person plural is fine; claims are factual and limits are stated early. Keep the current README's content: it is already honest. This spec is about order and assets.

**Order**
1. **Banner** (`<picture>`, light/dark): `docs/assets/readme-banner-light.png` and `docs/assets/readme-banner-dark.png`, displayed at 1280×320 and exported at 2560×640, under 200 KB each. Content: the mark + "Bytepleat" wordmark on the left (Instrument Sans 650, 88% width) and the pleat motif on the right in accent, on the Paper/dark-Paper background. No tagline in the image (the text follows as real text). Alt text: **Bytepleat**.
   GitHub's documented `<picture><source media="(prefers-color-scheme: dark)">` pattern handles the light/dark switch.
2. **One-line description** (keep): *Compress files, pack folders, and restore the same bytes, using standard formats.*
3. **Badge row** (keep three, add none that imply popularity): CI · License · Release. Optionally add one static badge "desktop: alpha" (shields.io static, Caution colour `9c6127`) so the status is visible at a glance.
4. **Quick links row** (Spacedrive pattern): **Install** · **Quick start** · **Formats** · **Desktop app (alpha)** · **Website**
5. **Status callout** (GitHub `> [!NOTE]`): *The command-line tool is the stable part. The desktop app is an early alpha without an installer; packages are unsigned.*
6. **Screenshot**: `docs/assets/screenshot-create-light.png` / `-dark.png` via `<picture>`, 1280×800 displayed at width 640 (capture at 2560×1600), the Create mode with three items chosen and ZIP selected. Alt: **Bytepleat desktop app with three files chosen and ZIP selected**.
7. **Why Bytepleat** (keep) → **When to use something else** (keep, directly after, as today).
8. **Install**: keep per-OS code blocks with bold OS headings (GitHub cannot render tabs; uv shows comments are enough).
9. **Quick start**, followed by the GIF: `docs/assets/fold-demo.gif`, 960×600, ≤ 4 MB, 12–15 fps, under 8 s. It shows drop → ZIP → Create archive → fold → success → Show in folder. Also commit `docs/assets/fold-demo.mp4` (same content, H.264) for the site. Alt: **Creating a ZIP archive in Bytepleat: files fold into the archive, then Show in folder**.
10. **Supported formats** (keep table) → **Safety behavior** (keep) → **Desktop app (alpha)**, with `docs/assets/screenshot-inspect-light.png` / `-dark.png` (1280×800 @2x) showing the 5,000-entry cap note → **Build and contribute** → **License**.

No ASCII art and no emoji section headings. Images live in `docs/assets/`, and none are hotlinked.

---

## 9. Asset list

| Asset | File | Spec |
|---|---|---|
| Logo mark | `design/mark.svg` (delivered) | 32-unit grid, four pleat faces, `currentColor` with opacity. Minimum size 16px. Clear space = one face width (6.5 units) all round. |
| Pleat motif | `design/pleat.svg` (delivered) | 320×80 viewBox, flat sheet → nine narrowing pleats, `currentColor`. Used for the app empty state (at 160px wide), the README banner and the site hero (animated version built from the same geometry). |
| Wordmark lockup | `site/assets/lockup.svg` (to make) | mark + "Bytepleat" in Instrument Sans 650, 96% width, converted to outlines. Gap between mark and text = 0.5× mark height. Light: mark in Pleat, text in Ink. Dark: mark in `#6fd0a8`, text in `#e4ece7`. |
| Favicon | `site/favicon.svg` + `site/favicon.ico` (16, 32, 48) + `site/apple-touch-icon.png` (180) | SVG: mark with an embedded `@media (prefers-color-scheme: dark)` style switching fill `#17674d` ↔ `#6fd0a8`. ICO/PNG: white mark on a Pleat green rounded square (radius 22%). |
| OG image | `site/og.png`, 1200×630, < 300 KB | Paper background. On the left, at 80px from the edge: lockup, then the H1 text "Pack files into ZIP, 7z or tar. Get the same bytes back." in Instrument Sans 650 at 60px, 88% width, Ink, max 3 lines. On the right, the pleat motif at 520px wide in Pleat green. No gradient, no screenshot (unreadable at thumbnail size). |
| README banner | `docs/assets/readme-banner-{light,dark}.png` | 2560×640, see section 8. |
| Screenshots | `docs/assets/screenshot-{create,inspect,extract-review,success}-{light,dark}.png` | 2560×1600 (1280×800 window at 2x), macOS capture with the window shadow removed, PNG, compressed with oxipng. Same sample data across all: `project/` with report.pdf, photos/ (318 files), notes.md. |
| Demo | `docs/assets/fold-demo.gif` + `.mp4` | 960×600, ≤ 8 s, see section 8. |
| App icon | `desktop/src-tauri/icons/` | See notes below. |

**App icon notes**
- Concept: the mark's four faces, white (lit at 100% and shaded at 70% white), on a Pleat green `#17674d` field with a very subtle top-to-bottom tonal shift from `#1b7356` to `#145c45`. This is the one permitted gradient, because the icon is a physical-object metaphor where light falls from above.
- macOS 26: the system applies the rounded-rect shape and its own material treatment. Supply a layered source (background layer: green field; foreground layer: mark) via Apple's Icon Composer if available. Treat the tool name and process as **unverified**, and check current Apple documentation. Also export a flat 1024×1024 PNG for `tauri icon`.
- Windows: `icon.ico` with 16, 24, 32, 48 and 256. At 16 and 24px use a simplified three-face mark with no shading difference below 0.6 contrast.
- Linux: `512x512.png` + `scalable/apps/bytepleat.svg` (hicolor), using the same art without a platform shape: a 20% radius square.
- Generate the Tauri set with `npm run tauri icon <1024.png>` (Tauri 2 CLI `icon` command), then hand-replace the 16/24/32 PNGs with the simplified mark.

---

## 10. Open items and unverified claims

- Apple Liquid Glass guidance was read only through secondary sources (reference 9), so it is not quoted as Apple's words.
- Instrument Sans axes come from the official repo and Fontsource; the Google Fonts specimen page did not render for verification. Confirm the shipped woff2 includes `wdth` before relying on 88% width. If it does not, fall back to 100% width with -0.03em tracking on H1.
- The CLI flag name in the "over the size cap" error must be confirmed in `docs/security-limits.md`.
- Competitor comparison cells are deliberately left for verification at publishing time.
- Download sizes and requirement lines on the site must be generated from the release assets, never typed by hand.

---

## Revision: palette

Supersedes the palette values in section 2, the ratio table in 4.1, the currentColor sentence in section 5 and the hex values in section 9 (favicon, app icon). `tokens.css` and the table below govern.

Kept: Instrument Sans and JetBrains Mono (type is unchanged; both are self-hosted OFL faces with the width axis). The pleat motif stays as the only expressive element, because folding is the product's one idea (archive and unarchive), and its geometry and placement are unchanged.

Why the palette changed:
- Accent moved from green `#17674d` to deep indigo-ink `#2f3e86`. Indigo reads as printed ink on paper; teal sat too close to the eco-green and mint look we rejected.
- Paper is warm neutral `#f6f4ef` and ink is graphite `#1e2025`, so surfaces read as paper and print rather than cool SaaS grey.
- Dark mode is graphite `#121315` with a lifted indigo accent `#a9b8ef` (9.6:1), not green-black with neon.
- Hairlines are warm grey creases. Any boundary the user must see to operate a control uses `--color-border-strong` (3.3:1 light, 3.6:1 dark).
- Caution is muted ochre-brown and danger is muted brick, used only with an icon and words. No gradients, glow, mint or amber tints as decoration.
- Success reuses the accent, so no token was added. Status is never colour alone.
- Token names and the raw-token scheme are unchanged. `--raw-mint` keeps its name but is now a pale indigo tint.
- `mark.svg` and `pleat.svg` use explicit fills (`.bp-fill`, `.bp-line`) with a `prefers-color-scheme: dark` rule, instead of `currentColor`. Geometry is unchanged.

Contrast: `python3 design/audit/contrast.py` exits 0. All 62 required text and UI pairs pass in both themes. Lowest UI pair: input border on surface, 3.22:1 (dark).

Token table (copy these values; light / dark):

| Token | Light | Dark |
|---|---|---|
| `--color-bg` | `#f6f4ef` | `#121315` |
| `--color-surface` | `#fffdf9` | `#1b1d21` |
| `--color-surface-raised` | `#fffdf9` | `#23262b` |
| `--color-text` | `#1e2025` | `#e7e5e0` |
| `--color-text-muted` | `#5c5a52` | `#a6a39b` |
| `--color-border` | `#d8d5cb` | `#2e3137` |
| `--color-border-strong` | `#8a877c` | `#6f6c65` |
| `--color-accent` | `#2f3e86` | `#a9b8ef` |
| `--color-accent-hover` | `#232f6b` | `#c4cff7` |
| `--color-on-accent` | `#ffffff` | `#111a44` |
| `--color-selection` | `#dfe3f1` | `#2a3150` |
| `--color-on-selection` | `#1e2025` | `#e7e5e0` |
| `--color-fold-light` | `#ecebe6` | `#22242a` |
| `--color-fold-shade` | `#dedbd2` | `#17181c` |
| `--color-caution` | `#8a5d12` | `#d9a95c` |
| `--color-caution-bg` | `#f1ece0` | `#2a2317` |
| `--color-caution-text` | `#6e4c10` | `#d9a95c` |
| `--color-danger` | `#a13b36` | `#ec8a80` |
| `--color-danger-bg` | `#f5e6e4` | `#2e1d1b` |
| `--color-danger-text` | `#a13b36` | `#ec8a80` |
| `--color-success` | `#2f3e86` | `#a9b8ef` |
| `--color-backdrop` | `rgb(30 32 37 / 0.32)` | `rgb(0 0 0 / 0.5)` |
