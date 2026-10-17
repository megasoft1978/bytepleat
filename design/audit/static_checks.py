#!/usr/bin/env python3
"""Static accessibility and type-size checks for the Bytepleat UI and site.

Usage (read-only, stdlib only):
    python3 -I design/audit/static_checks.py

HTML checks: stdlib html.parser. Not a browser; no computed accessible names.
CSS checks: font-size declarations resolved through tokens.css (16px root).
"""
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

PAGES = [
    "desktop/ui/index.html",
    "site/index.html",
    "site/docs/index.html",
    "site/404.html",
]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
ARIA_ID_REFS = ["aria-labelledby", "aria-describedby", "aria-controls", "aria-owns", "aria-activedescendant", "aria-errormessage"]


class Audit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.findings = []        # (severity, check, line, detail)
        self.ids = {}             # id -> first line
        self.dup_ids = []
        self.refs = []            # (attr, idref, line)
        self.labels_for = set()
        self.headings = []        # (level, line)
        self.stack = []           # open interactive elements to evaluate on close
        self.has_lang = False
        self.has_title = False
        self.has_viewport = False
        self.title_text = ""
        self._in_title = False
        self.inputs = []          # (line, type, attrs) needing a label
        self.sr_text_depth = 0
        self.svg_depth = 0
        self.label_stack = []

    def add(self, sev, check, line, detail):
        self.findings.append((sev, check, line, detail))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        line = self.getpos()[0]
        if tag == "html":
            self.has_lang = bool(a.get("lang"))
            if not a.get("lang"):
                self.add("High", "missing lang on <html>", line, "")
        if tag == "title":
            self._in_title = True
            self.has_title = True
        if tag == "meta" and (a.get("name") or "").lower() == "viewport":
            self.has_viewport = True
        if "id" in a and a["id"] is not None:
            if a["id"] in self.ids:
                self.dup_ids.append((a["id"], self.ids[a["id"]], line))
            else:
                self.ids[a["id"]] = line
        for k in ARIA_ID_REFS + ["for"]:
            if k in a and a[k]:
                for ref in a[k].split():
                    self.refs.append((k, ref, line))
        if tag == "a" and (a.get("href") or "").startswith("#") and len(a["href"]) > 1:
            self.refs.append(("href", a["href"][1:], line))
        if tag == "label" and "for" in a:
            self.labels_for.add(a["for"])
        if tag == "img":
            if "alt" not in a:
                self.add("High", "img without alt", line, a.get("src", ""))
        if tag == "svg":
            if a.get("role") == "img" and not (a.get("aria-label") or a.get("aria-labelledby")):
                self.add("Medium", "svg role=img without name", line, "")
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append((int(tag[1]), line))
        if "tabindex" in a:
            try:
                if int(a["tabindex"]) > 0:
                    self.add("High", "tabindex > 0", line, a["tabindex"])
            except ValueError:
                pass
        if tag == "input":
            itype = (a.get("type") or "text").lower()
            if itype not in ("hidden", "submit", "button", "reset", "image") and "label" not in self.label_stack:
                self.inputs.append((line, itype, a))
        if tag in ("button", "a", "summary"):
            name_attr = bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title"))
            self.stack.append({"tag": tag, "line": line, "text": "", "named": name_attr, "attrs": a,
                               "hidden_text": False})
        if tag not in VOID:
            self.label_stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                el = self.stack.pop(i)
                if not el["named"] and not el["text"].strip():
                    # icon-only controls need a name; aria-hidden children do not count
                    if el["attrs"].get("aria-hidden") != "true":
                        sev = "High" if tag == "button" else "High"
                        self.add(sev, f"<{tag}> without accessible name", el["line"],
                                 str({k: v for k, v in el["attrs"].items() if k in ("class", "id", "href", "type")}))
                break
        if tag in self.label_stack:
            idx = len(self.label_stack) - 1 - self.label_stack[::-1].index(tag)
            del self.label_stack[idx:]

    def handle_data(self, data):
        if self._in_title:
            self.title_text += data
        for el in self.stack:
            el["text"] += data

    def handle_startendtag(self, tag, attrs):
        # self-closing inputs/imgs/etc.
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)


def audit_file(rel):
    path = os.path.join(ROOT, rel)
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    p = Audit()
    p.feed(src)
    p.close()

    if not p.has_title or not p.title_text.strip():
        p.add("High", "missing or empty <title>", 1, "")
    if not p.has_viewport:
        p.add("High", "missing viewport meta", 1, "")
    for id_, first, line in p.dup_ids:
        p.add("High", "duplicate id", line, f"{id_} (first at line {first})")
    for attr, ref, line in p.refs:
        if attr == "for":
            continue
        if ref not in p.ids:
            p.add("High", f"{attr} references missing id", line, ref)
    for attr, ref, line in p.refs:
        if attr == "for" and ref not in p.ids:
            p.add("High", "label for= references missing id", line, ref)
    for line, itype, a in p.inputs:
        iid = a.get("id")
        named = bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title"))
        if not named and not (iid and iid in p.labels_for):
            p.add("High", f"<input type={itype}> without label", line, a.get("name", ""))
    prev = 0
    for level, line in p.headings:
        if prev and level > prev + 1:
            p.add("Medium", f"heading order skip h{prev} -> h{level}", line, "")
        prev = level
    h1s = [l for lvl, l in p.headings if lvl == 1]
    if len(h1s) != 1:
        p.add("Low", f"expected exactly one h1, found {len(h1s)}", 1, "")
    return p


# ---------------------------------------------------------------- CSS type sizes

def load_tokens(path):
    vals = {}
    with open(path, encoding="utf-8") as fh:
        txt = re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)
    for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", txt):
        vals.setdefault(m.group(1), " ".join(m.group(2).split()))
    return vals


def px_of(value, tokens, depth=0):
    """Smallest px size a font-size value can take (clamp -> min at 16px root). None if unknown."""
    if depth > 10:
        return None
    v = value.strip()
    m = re.fullmatch(r"var\((--[\w-]+)\)", v)
    if m:
        return px_of(tokens.get(m.group(1), ""), tokens, depth + 1)
    m = re.match(r"clamp\(\s*([^,]+),", v)
    if m:
        return px_of(m.group(1), tokens, depth + 1)
    m = re.fullmatch(r"([\d.]+)(px|rem|em)", v)
    if m:
        n, unit = float(m.group(1)), m.group(2)
        return n * 16 if unit in ("rem", "em") else n
    return None


def css_font_sizes(rel, tokens):
    path = os.path.join(ROOT, rel)
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    out = []
    for i, line in enumerate(lines, 1):
        for m in re.finditer(r"font-size\s*:\s*([^;}]+)", line):
            raw = m.group(1).strip()
            out.append((i, raw, px_of(raw, tokens), line.strip()[:110]))
    return out


def main():
    html_summary = []
    for rel in PAGES:
        p = audit_file(rel)
        html_summary.append((rel, p))

    print("## HTML findings")
    total = 0
    for rel, p in html_summary:
        print(f"\n### {rel}")
        if not p.findings:
            print("none")
        for sev, check, line, detail in sorted(p.findings, key=lambda f: (f[0], f[2])):
            total += 1
            print(f"- [{sev}] line {line}: {check} {detail}".rstrip())
    print(f"\nHTML findings total: {total}")

    app_tokens = load_tokens(os.path.join(ROOT, "desktop/ui/tokens.css"))
    site_tokens = load_tokens(os.path.join(ROOT, "site/assets/tokens.css"))
    print("\n## CSS font-size: app (desktop/ui/styles.css), minimum 13px")
    for line, raw, px, ctx in css_font_sizes("desktop/ui/styles.css", app_tokens):
        if px is None or px < 13:
            print(f"- styles.css:{line} font-size {raw} -> {px}px :: {ctx}")
    print("\n## CSS font-size: site (site/assets/site.css), minimum 14px (em values shown for review)")
    for line, raw, px, ctx in css_font_sizes("site/assets/site.css", site_tokens):
        flag = ""
        if px is None:
            flag = "UNRESOLVED"
        elif px < 14:
            flag = "BELOW 14px"
        if raw.endswith("em") and not raw.endswith("rem"):
            flag = (flag + " relative-em").strip()
        if flag:
            print(f"- site.css:{line} font-size {raw} -> {px}px [{flag}] :: {ctx}")
    print("\n## Site/app font-size tokens (resolved)")
    for name in sorted(k for k in list(app_tokens) + list(site_tokens) if "text" in k and k.startswith("--app")):
        print(f"- app {name}: {app_tokens[name]}")
    for name in sorted(k for k in site_tokens if k.startswith("--site-text")):
        print(f"- site {name}: {site_tokens[name]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
