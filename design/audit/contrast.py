#!/usr/bin/env python3
"""WCAG 2.2 contrast audit for Bytepleat design tokens.

Usage (read-only, stdlib only):
    python3 -I design/audit/contrast.py [tokens.css ...]

With no arguments it audits ../tokens.css (design/tokens.css) relative to this file.
Extra token files (e.g. the shipped copies in desktop/ui and site/assets) are
compared against the first one: any raw colour value that differs is reported.

Resolves var() chains, hex and rgb()/rgba() colours, composites alpha over the
background, and computes relative luminance per WCAG 2.x (sRGB, 0.2126/0.7152/0.0722).
Light = :root. Dark = :root merged with the prefers-color-scheme dark block and the
[data-theme="dark"] block. color-mix() and forced-colors values are not computed.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- CSS parsing

def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def parse_css(css):
    """Return list of (ancestors, selector, declarations-dict) for every block."""
    css = strip_comments(css)
    blocks, stack, buf = [], [], ""
    for ch in css:
        if ch == "{":
            stack.append((list(a for a in stack_sel(stack)), buf.strip()))
            buf = ""
        elif ch == "}":
            ancestors, sel = stack.pop()
            blocks.append((ancestors, sel, parse_decls(buf)))
            buf = ""
        else:
            buf += ch
    return blocks


def stack_sel(stack):
    return [s for _, s in stack]


def parse_decls(text):
    out = {}
    for part in text.split(";"):
        if ":" not in part:
            continue
        name, value = part.split(":", 1)
        name = name.strip()
        if name.startswith("--"):
            out[name] = " ".join(value.split())
    return out


def build_themes(path):
    """Return (light_vars, dark_vars, comment_claims) for a tokens file."""
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    blocks = parse_css(raw)
    light, dark_auto, dark_forced = {}, {}, {}
    for ancestors, sel, decls in blocks:
        in_dark_media = any("prefers-color-scheme: dark" in a for a in ancestors)
        in_other_media = any(a.startswith("@") and "prefers-color-scheme" not in a for a in ancestors)
        if in_other_media:
            continue  # reduced-motion / forced-colors / others: not colour themes
        if not ancestors and sel == ":root":
            light.update(decls)
        elif in_dark_media and sel == ':root:not([data-theme="light"])':
            dark_auto.update(decls)
        elif not ancestors and sel == ':root[data-theme="dark"]':
            dark_forced.update(decls)
    dark = dict(light)
    dark.update(dark_auto)
    dark.update(dark_forced)
    return light, dark


# ---------------------------------------------------------------- colour maths

VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*))?\)")


def resolve(value, env, depth=0):
    if depth > 20:
        raise ValueError("var() cycle")
    def repl(m):
        name, fallback = m.group(1), m.group(2)
        if name in env:
            return resolve(env[name], env, depth + 1)
        if fallback is not None:
            return resolve(fallback.strip(), env, depth + 1)
        raise KeyError(name)
    prev = None
    while prev != value:
        prev, value = value, VAR_RE.sub(repl, value)
    return value.strip()


def parse_color(value):
    """Return (r, g, b, a) with components 0..255 / 0..1, or None if not a colour."""
    v = value.strip().lower()
    if v == "transparent":
        return (0, 0, 0, 0.0)
    if v == "white":
        return (255, 255, 255, 1.0)
    if v == "black":
        return (0, 0, 0, 1.0)
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
    m = re.fullmatch(r"rgba?\((.*)\)", v)
    if m:
        body = m.group(1).replace(",", " ")
        alpha = 1.0
        if "/" in body:
            body, a = body.split("/", 1)
            alpha = float(a.strip())
        nums = body.split()
        if len(nums) != 3:
            return None
        r, g, b = (float(x) for x in nums)
        return (r, g, b, alpha)
    return None


def composite(fg, bg):
    r, g, b, a = fg
    if a >= 1.0:
        return (r, g, b)
    br, bg_, bb = bg
    return (r * a + br * (1 - a), g * a + bg_ * (1 - a), b * a + bb * (1 - a))


def luminance(rgb):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(c1, c2):
    l1, l2 = luminance(c1), luminance(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def colour_of(env, token, over=None):
    """Resolve token to an opaque RGB tuple, compositing over `over` if translucent."""
    c = parse_color(resolve(env[token], env))
    if c is None:
        raise ValueError(f"{token} is not a colour: {env[token]}")
    if c[3] < 1.0:
        if over is None:
            raise ValueError(f"{token} translucent with no backdrop")
        return composite(c, over)
    return (c[0], c[1], c[2])


# ---------------------------------------------------------------- pairs

# kind: text (4.5:1), ui (3:1 non-text / component boundary and focus),
#       exempt (disabled control: WCAG 1.4.3 exempts; reported for information),
#       decor (decorative hairline: not required; reported for information)
PAIRS = [
    ("P01", "page text on page bg", "text", "--color-text", "--color-bg",
     "styles.css:9-10; site.css:13-14"),
    ("P02", "text on sheet surface (rows, status error)", "text", "--color-text", "--color-surface",
     "styles.css:125, 326"),
    ("P03", "text on raised surface (dialog, history)", "text", "--color-text", "--color-surface-raised",
     "styles.css:402, 441"),
    ("P04", "muted text on page bg", "text", "--color-text-muted", "--color-bg",
     "styles.css:116; site.css:150, 156, 269-273, 298, 304, 435, 487"),
    ("P05", "muted text on sheet surface", "text", "--color-text-muted", "--color-surface",
     "styles.css:161, 173, 186, 220; site.css:178, 248, 449"),
    ("P06", "muted text on raised surface (history list)", "text", "--color-text-muted", "--color-surface-raised",
     "styles.css:411-419 (mobile history panel)"),
    ("P07", "muted text on fold-light (mode tab, segmented ctl)", "text", "--color-text-muted", "--color-fold-light",
     "styles.css:85-93; site.css:340"),
    ("P08", "accent text (links, text buttons) on page bg", "text", "--color-accent", "--color-bg",
     "styles.css:56-59; site.css:26, 201, 284, 373"),
    ("P09", "accent text (copy button) on code surface", "text", "--color-accent", "--color-surface",
     "site.css:187-189"),
    ("P10", "accent text on fold-light (copy on hero code)", "text", "--color-accent", "--color-fold-light",
     "site.css:194, 196"),
    ("P11", "accent-hover link text on page bg", "text", "--color-accent-hover", "--color-bg",
     "site.css:27, 202, 289"),
    ("P12", "primary button label on accent", "text", "--color-on-accent", "--color-accent",
     "styles.css:41; site.css:67, 92, 360"),
    ("P13", "primary button label on accent-hover", "text", "--color-on-accent", "--color-accent-hover",
     "styles.css:42; site.css:93"),
    ("P14", "selected text on selection (format option, checked row)", "text", "--color-on-selection", "--color-selection",
     "styles.css:215, 301, 22"),
    ("P15", "text on fold-light (hover states, hero code)", "text", "--color-text", "--color-fold-light",
     "styles.css:44, 46, 180, 299; site.css:121, 196"),
    ("P16", "text on selection (drag-over sheet)", "text", "--color-text", "--color-selection",
     "styles.css:136"),
    ("P17", "caution text on caution tint (notes, chip)", "text", "--color-caution-text", "--color-caution-bg",
     "styles.css:313; site.css:77, 430"),
    ("P18", "caution text on raised surface (limit dialog)", "text", "--color-caution", "--color-surface-raised",
     "styles.css:451"),
    ("P19", "danger text on danger tint (error glyph)", "text", "--color-danger-text", "--color-danger-bg",
     "styles.css:253 (token defined; glyph uses --color-danger)"),
    ("P20", "danger text on surface (error glyph, status ring)", "text", "--color-danger", "--color-surface",
     "styles.css:328, 333, 415"),
    ("P21", "caution note border on page bg (3px rule)", "ui", "--color-caution", "--color-bg",
     "site.css:431"),
    ("P22", "success icon on raised surface", "ui", "--color-success", "--color-surface-raised",
     "styles.css:414"),
    ("P23", "input / checkbox / secondary button border on surface", "ui", "--color-border-strong", "--color-surface",
     "styles.css:43, 226, 290; site.css:357"),
    ("P24", "chip / toggle border on page bg", "ui", "--color-border-strong", "--color-bg",
     "styles.css:82; site.css:117, 421"),
    ("P25", "checked checkbox fill vs surface", "ui", "--color-accent", "--color-surface",
     "styles.css:230"),
    ("P26", "focus ring vs page bg", "ui", "--focus-color", "--color-bg",
     "styles.css:29; site.css:56"),
    ("P27", "focus ring vs surface", "ui", "--focus-color", "--color-surface",
     "styles.css:29, 205 (sheet, rows)"),
    ("P28", "focus ring vs fold-light", "ui", "--focus-color", "--color-fold-light",
     "styles.css:299, 302 (hover / mode tabs)"),
    ("P29", "focus ring vs raised surface", "ui", "--focus-color", "--color-surface-raised",
     "styles.css:402 (history / dialog controls)"),
    ("P30", "progress fill vs track", "ui", "--color-accent", "--color-fold-light",
     "styles.css:376-387"),
    ("P31", "decorative hairline vs surface", "decor", "--color-border", "--color-surface",
     "styles.css:74, 184, 208; site.css:170"),
    ("P32", "disabled primary label", "exempt", "--color-text-muted", "--color-fold-shade",
     "styles.css:51; site.css:361"),
    ("P33", "disabled secondary label", "exempt", "--color-text-muted", "--color-surface",
     "styles.css:52"),
    ("P34", "selected-row directory text (opacity .78)", "text", "--color-on-selection", "--color-selection",
     "styles.css:219 (opacity .78 applied)"),
]
# Pairs whose foreground is drawn with element opacity (blended over the background).
OPACITY = {"P34": 0.78}

# Ratios written into tokens.css comments: (token, claimed ratio, reference bg token).
CLAIM_RE = re.compile(r"(--color-[\w-]+):.*?/\*[^*]*?(\d+(?:\.\d+)?):1(?:\s+on\s+([\w-]+))?")


def claims_from(path):
    """Yield (token, claimed, reference-token-name or None, theme) from tokens.css comments.

    Theme is 'dark' for lines inside the prefers-color-scheme dark block, else 'light'.
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    dark_start = next(i for i, l in enumerate(lines) if "prefers-color-scheme: dark" in l)
    dark_end = next(i for i, l in enumerate(lines) if i > dark_start and ':root[data-theme="dark"]' in l)
    for i, line in enumerate(lines):
        m = CLAIM_RE.search(line)
        if m:
            ref = m.group(3)
            theme = "dark" if dark_start <= i < dark_end else "light"
            yield m.group(1), float(m.group(2)), (f"--color-{ref}" if ref else None), theme


# ---------------------------------------------------------------- main

def fmt(r):
    return f"{r:.2f}:1"


def verdict(kind, r):
    if kind == "text":
        return "PASS" if r >= 4.5 else "FAIL"
    if kind in ("ui",):
        return "PASS" if r >= 3.0 else "FAIL"
    if kind == "exempt":
        return "EXEMPT" if r >= 4.5 else "EXEMPT-FAIL"
    return "INFO"


def main(argv):
    paths = argv or [os.path.normpath(os.path.join(HERE, "..", "tokens.css"))]
    primary = paths[0]
    light, dark = build_themes(primary)
    themes = {"light": light, "dark": dark}

    rows, fails, counted = [], 0, 0
    for pid, label, kind, fg, bg, where in PAIRS:
        for tname, env in themes.items():
            try:
                bg_rgb = colour_of(env, bg)
                fg_rgb = colour_of(env, fg, over=bg_rgb)
            except (KeyError, ValueError) as exc:
                rows.append((pid, tname, label, "n/a", f"unresolved: {exc}", kind, where))
                continue
            if pid in OPACITY:
                a = OPACITY[pid]
                fg_rgb = tuple(a * f + (1 - a) * b for f, b in zip(fg_rgb, bg_rgb))
            r = ratio(fg_rgb, bg_rgb)
            v = verdict(kind, r)
            if kind in ("text", "ui"):
                counted += 1
                if v == "FAIL":
                    fails += 1
            rows.append((pid, tname, label, fmt(r), v, kind, where))

    print(f"Primary tokens: {primary}")
    print()
    print("| Pair | Theme | Foreground on background | Ratio | Result | Kind | Used at |")
    print("|---|---|---|---|---|---|---|")
    for pid, tname, label, r, v, kind, where in rows:
        print(f"| {pid} | {tname} | {label} | {r} | {v} | {kind} | {where} |")
    print()
    print(f"Required pairs checked (text+ui, both themes): {counted}")
    print(f"Failing: {fails}")
    print()

    print("| Token comment claim | Theme | Claimed | Computed vs reference | Match |")
    print("|---|---|---|---|---|")
    for tok, claimed, ref, tname in claims_from(primary):
        env = themes[tname]
        if tok not in env:
            continue
        # Unlabelled claims: on-* tokens are measured on their own background, others on bg.
        ref_name = ref or ("--color-" + tok[len("--color-on-"):] if tok.startswith("--color-on-") else "--color-bg")
        try:
            bg_rgb = colour_of(env, ref_name)
            fg_rgb = colour_of(env, tok, over=bg_rgb)
        except (KeyError, ValueError):
            continue
        r = ratio(fg_rgb, bg_rgb)
        ok = "yes" if abs(r - claimed) <= 0.15 else "NO"
        print(f"| {tok} vs {ref_name} | {tname} | {claimed}:1 | {r:.2f}:1 | {ok} |")
    print()

    if len(paths) > 1:
        print("Raw colour drift vs primary (theme-resolved values):")
        for other in paths[1:]:
            o_light, o_dark = build_themes(other)
            print(f"  {other}")
            for tname, env, oenv in (("light", light, o_light), ("dark", dark, o_dark)):
                for tok in sorted(set(env) & set(oenv)):
                    if not tok.startswith("--color-") and not tok.startswith("--raw-"):
                        continue
                    try:
                        a = resolve(env[tok], env)
                        b = resolve(oenv[tok], oenv)
                    except KeyError:
                        continue
                    if a != b:
                        print(f"    {tname} {tok}: {a} != {b}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
