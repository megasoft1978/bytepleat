# Third-Party Fonts

Bytepleat self-hosts two fonts. Both are licensed under the SIL Open Font License 1.1 (OFL-1.1).

## Instrument Sans (variable)

- Source: Google Fonts (`fonts.gstatic.com`), fetched 2026-10-17. Upstream project: https://github.com/Instrument/instrument-sans
- Files: `InstrumentSans-latin.woff2`, `InstrumentSans-latin-ext.woff2`
- Format: subsetted woff2, not modified by us
- Licence: SIL OPEN FONT LICENSE Version 1.1 (OFL-1.1)
- Copyright: `Copyright 2022 The Instrument Sans Project Authors (https://github.com/Instrument/instrument-sans)`
- Licence text: `OFL-InstrumentSans.txt` in each font directory below

## JetBrains Mono (variable)

- Source: Google Fonts (`fonts.gstatic.com`), fetched 2026-10-17. Upstream project: https://github.com/JetBrains/JetBrainsMono
- Files: `JetBrainsMono-latin.woff2`
- Format: subsetted woff2, not modified by us
- Licence: SIL OPEN FONT LICENSE Version 1.1 (OFL-1.1)
- Copyright: `Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)`
- Licence text: `OFL-JetBrainsMono.txt` in each font directory below

## Locations

Each font directory ships the font files and both licence texts:

- `design/fonts/`
- `desktop/ui/fonts/`
- `site/assets/fonts/`

## Packaged notices

`desktop/ui/` is embedded in the desktop app binary, so the OFL texts and copyright lines must ship with every desktop package. `desktop/scripts/collect-desktop-notices.py` lists both fonts in `THIRD-PARTY.json` under `runtime_components` (kind `bundled-ui-font`: name, version, licence `OFL-1.1`, copyright, source URL, font files) and copies `desktop/ui/fonts/OFL-*.txt` to `third-party-licenses/bundled-ui/<font>/` with SHA-256 hashes. The Linux `.deb` builder and the Windows MSIX notice step already install every `notices` entry of `runtime_components`, so the fonts ship with them unchanged.

The collector is strict: if `desktop/ui` exists and a font file or its OFL text is missing, collection fails. Adding or renaming a bundled font requires updating `BUNDLED_UI_FONTS` in the collector.
