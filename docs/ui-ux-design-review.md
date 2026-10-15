# UI/UX design review

This records the design decisions for the desktop alpha UI, the README and the website, which are meant to read as one product. It is a decision log, not a validation record: nothing here was checked in a running GUI or browser. Platform status lives in [desktop validation](desktop-validation.md).

## Design plan

**Audience and job.** People who open, make and unpack everyday archives and want to know exactly what will happen to their files. The core job is: choose a source, choose a destination, run, and see a clear result. Developers who want scripting use the released CLI.

**Direction.** A precise, calm file workbench. The memorable motif is a folded (pleated) file strip, used sparingly: the brand mark, the edge of the workspace card, the progress fill, and the strip across the site's illustration. There are no gradient heroes, remote fonts, UI dependencies, or rows of identical rounded cards.

**Color tokens** (light, with a matching dark set that follows the system setting):

| Role | Light | Dark |
| --- | --- | --- |
| Ink | `#17211d` | `#e7efea` |
| Paper | `#f4f7f4` | `#0e1411` |
| Surface | `#ffffff` | `#161e1a` |
| Spruce (action) | `#17674d` | `#8fd4ae` |
| Mint (pleat, selection) | `#bce5d4` | `#2c5f48` |
| Caution (limits, cancelled) | `#9c6127` | `#e0a56a` |

Calculated from the sRGB hex values with the WCAG contrast formula, the sampled light theme ratios are 15.30:1 for body text, 5.89:1 for muted text, 6.81:1 for button text, 6.67:1 for caution text, 6.18:1 for focus against the page, and 3.33:1 for the strong border against white. The sampled dark theme ratios are 15.91:1, 8.55:1, 10.00:1, 9.67:1, 9.62:1 and 4.21:1 respectively. These sampled pairs clear WCAG AA text contrast and the 3:1 non-text contrast threshold; this calculation does not cover every rendered combination. Focus is a 3 px outline in a separate blue.

**Type roles.** Native system sans everywhere (the same stack in the app and the site). Monospace is reserved for paths, file extensions, sizes and build targets. Eyebrows are plain sentence-case text, not tiny all-caps labels.

**App wireframe.** Left rail: brand with an Alpha badge, then Recent jobs. Main pane: privacy line and appearance toggle, then a task heading, then one workspace card with Create / Extract / Inspect tabs. Inside the card: step 1 source (drop zone and system dialog buttons), step 2 format (Create only), a destination step, then the Run row with a plain reason when Run is unavailable. The current job sits directly under Run in a stable place; format limits sit beside the card and stack below it on narrow windows.

**Site wireframe.** Header, then a compact hero (status pill, headline, one paragraph, two actions) beside a labeled illustration of the Inspect tab. Then: how it works (Create, Extract, Inspect), careful by default, formats with a visible limits note, platform status, CLI downloads, FAQ.

**Platform behavior.** The app keeps the OS-native Open/Save and folder dialogs and does not imitate native controls. Appearance follows the system, with a System / Light / Dark override. Explorer, Finder and Dolphin context actions remain handoffs implemented outside this UI.

## Decisions adopted

- **Same words everywhere.** The tab, heading, button, job title and completion message all say Create archive, Extract archive or Inspect archive. States are Queued, Running, Stopping…, Completed, Failed, Cancelled.
- **Run explains itself.** The hint beside Run says what is missing (choose a source, choose a destination, select an entry, wait for the running job) instead of only disabling the button.
- **Destination is explicit.** For Extract, the UI names the new folder that will be created and says the job stops if it already exists. For Create, it says an existing file is not replaced. Changing the format asks for the save location again.
- **Progress in a stable place.** The current job is shown under Run with a determinate bar when the backend reports a total, and an indeterminate bar otherwise. Both use `role="progressbar"`; reduced motion removes the sliding animation. Cancel is available while a job runs. Terminal states are announced once through a polite live region.
- **Honest assurance lines.** Completed, failed and cancelled jobs say the originals were not changed. Inspect says it is listing only. No line claims anything the engine does not do.
- **Caveats stay findable.** Format limits are always visible beside the workspace, and the listing-only warning appears with every archive listing.
- **Keyboard and focus.** Tabs have roving tabindex and arrow/Home/End movement (selection stays on Enter or Space so browsing tabs never clears a choice). Progress re-rendering restores focus to the same Cancel or Open folder button.
- **Archive-only dialogs for archives.** In Extract and Inspect the folder button is hidden and the file button reads Choose archive….
- **Appearance cycle.** System, Light and Dark; System removes the override so the OS setting applies. A removed duplicate toggle reference in `app.js` previously threw at startup.
- **README.** Opens with a status table (released CLI versus desktop alpha), then the desktop section with a source quick start, limits, and a per-platform evidence summary that links to the validation record. No screenshot.
- **Site.** Primary action is the CLI download (the only released download); the desktop alpha is a secondary, labeled link. The hero illustration mirrors the real Inspect tab and is labeled as an illustration with sample file names. Platform status labels use words ("Partly checked", "CI only"), not color or icons alone. The site mark and favicon now match the app's pleat mark; the site palette matches the app, with a system dark mode.
- **Small fixes found on the way.** The site's copy-confirmation element was missing, so "Command copied" never appeared; the CLI guide links to `#install`, which now exists on the home page.

## Follow-up polish (copy and Inspect flow)

- **Site trust copy.** The stale link to the merged PR is gone. The released CLI and the desktop alpha are separated in the hero, the no-overwrite claim is scoped to the desktop app with the CLI's `--force` disclosed, platform cards say "Desktop" and name the ARM64 desktop checks versus the x86-64 CLI package, and the Linux card names the v10 package instead of "latest". The "Create, Extract, Inspect" list is no longer numbered because those are views, not steps. Headline tracking was loosened. No Open Graph or social-card tags were added because no correct share image exists; a native screenshot would be needed and none has been captured.
- **Inspect to Extract hand-off.** Choosing Extract selected… used to switch tabs and clear the listing, leaving the chosen entries invisible. The Extract tab now shows an "Entries to extract" review with Change selection (restores the earlier listing from memory, without re-reading the archive) and Extract everything instead. The Inspect list says what to do when nothing is ticked.
- **Explicit destination.** Extract shows the full result folder before running, and a completed job labels its path "Extracted to" or "Saved to".
- **Limits beside controls.** The 1 GiB output cap, 100,000-entry limit and 5,000-entry preview sit in each tab's source hint instead of one generic line, and the sidebar note follows the active tab.
- **TAR listing disclosed before Inspect.** When the chosen file name ends in .tar.zst, .tar.gz or .tar.lz4, a note says listing fully decodes into private temporary staging. The note is based on the file name only; the engine still detects the format from content.

## Follow-up polish (screenshot review of baseline `20b5129`)

Evidence: hosted-CI native screenshots (macOS ARM64, Linux x64/ARM64, Windows x64/ARM64; fixture ZIP, window about 1024 px wide) plus headless website and README captures. The macOS, Windows and Linux x64 captures compared look the same apart from path style and fonts, so these changes are not platform-specific. No Finder, Explorer or GNOME context-menu interaction and no assistive-technology run was captured.

- **One next step after a listing.** With a listing shown, Inspect archive used to stay the filled primary button below a disabled secondary Extract selected…. The run button now reads Inspect again and steps back to secondary; Extract selected… becomes the primary action. The element IDs are unchanged.
- **No focus ring on the hand-off heading.** The Entries to extract heading takes programmatic focus so screen readers announce it, but showed a blue box in the native captures. Headings with `tabindex="-1"` no longer draw a ring; controls keep theirs.
- **Less repeated text on hand-off.** The Extract tab showed the same "choose a destination folder" instruction twice (status line and Run hint). The status text is now announced through the live region only.
- **Placeholder is not a path.** “No location chosen yet.” was set in the monospace face reserved for paths. It now uses the body face in the muted colour.
- **Terms.** The listing summary says “entries” (as the Extract review and the limits already did) instead of “items”; the selection count says “1 archive selected” in Extract and Inspect and keeps “items” for Create. The website illustration says “4 entries”. The entry hint no longer says to choose a destination “on the Extract tab” before the user has left the Inspect tab.
- **Failure recovery.** A failed job's note now adds “Check the message above, adjust your choices, and run it again” to the unchanged-originals line. It makes no claim about partial output.
- **Website.** Each platform-status card leads with its verdict label, so the label is read first on a 390 px screen instead of after a long paragraph. The hero note drops the release facts already in the pill and buttons.
- **README.** The Inspect bullet says how to carry entries to Extract, and the two overlapping validation paragraphs are merged.

Not changed: the native captures are cropped mid-scroll CI fixtures with temporary paths, so they were not added to the README or website. Provenance mismatch to be aware of: the brief names baseline `20b5129`, but `capture-metadata.json` for the website and README captures records commit `b1e36fe`, and the native captures were taken at `38e945b`.

## Recommendations deferred

- **Windows Explorer verbs.** Modern Explorer commands need `IExplorerCommand` and package identity; that is packaging and backend work outside this change.
- **Finder and Dolphin menus.** Existing handoffs are unchanged. Richer contextual menus are not part of the UI surface.
- **Per-phase determinate progress.** The bar only appears for phases where the backend reports a trustworthy total; changing the worker's reporting was out of scope.
- **Select all / clear in the entry list.** Lists can hold up to 5,000 entries; ticking many by hand is slow, but Extract everything instead covers the common case and a bulk control was not requested.
- **Dismissing finished jobs and multi-job queues.** The engine runs one job at a time, so a queue UI would be speculative.
- **Auto-activating tabs on arrow keys.** Deferred so keyboard browsing cannot clear a selection.
- **Screenshots and a product preview image.** None added; they would need real captures from a verified build.
- **Theme flash on launch.** Applying a saved theme before first paint would need an inline script, which the app's content security policy (`script-src 'self'`) blocks.

## Validation performed

Headless Chromium smoke checks loaded the app preview and site at 1440 px and 390 px widths, in light and dark system color schemes. The app's Create, Extract and Inspect tabs, theme toggle, keyboard tab movement, and a mocked archive job with determinate progress and preserved Cancel-button focus were exercised. The site mobile menu, Linux target selector, and checksum-command copy confirmation were exercised. There were no JavaScript errors or horizontal overflow at those widths. One oversized mobile gap above Run was found and corrected in the app stylesheet. `node --check` passed for `desktop/ui/app.js` and `site/assets/site.js`; `git diff --check` passed.

No native desktop GUI, Finder/Explorer/Dolphin action, screen reader, reduced-motion mode or physical touch interaction was tested. The browser preview cannot validate Tauri dialogs or archive operations. Layout at 320 px and a complete rendered-state contrast audit remain unverified.

## References

Platform guidance:

- Apple HIG, [progress indicators](https://developer.apple.com/design/human-interface-guidelines/progress-indicators) and [accessing files from the macOS App Sandbox](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox)
- Microsoft, [Windows app design basics](https://learn.microsoft.com/en-us/windows/apps/design/basics/) and [best practices](https://learn.microsoft.com/en-in/windows/apps/get-started/best-practices)
- GNOME HIG, [principles](https://developer.gnome.org/hig/principles.html), [navigation](https://developer.gnome.org/hig/guidelines/navigation.html) and [writing style](https://developer.gnome.org/hig/guidelines/writing-style.html)
- KDE, [Dolphin service menus](https://develop.kde.org/docs/apps/dolphin/service-menus/)

Comparable products (patterns only; no claims copied): [NanaZip](https://github.com/rescenic/nanazip), [Keka](https://www.keka.io/en/), [PeaZip](https://peazip.github.io/), [The Unarchiver](https://theunarchiver.com/). Bytepleat differentiates on clarity, careful extraction, local processing and stated compatibility limits, not on format breadth or speed.
