#!/usr/bin/env python3
"""Build the SlabRail engineering package from the files in this repo.

Run from the psa-slab-scanner/ folder:

    python3 package/build_package.py

Writes into package/:

    SlabRail_Design_Review.pdf           for reviewers: brief, design, drawings, wiring, BOM
    SlabRail_Complete_Documentation.pdf  every document plus the drawings
    SlabRail_CAD.zip                     every file in package/cad_manifest.txt, under SlabRail_CAD/
    README.md                            what each file is, sizes, page counts, how to rebuild

Needs: pandoc 3.x, Python 3 with pypdf, Pillow and playwright (the Python package, with
Playwright's Chromium browser installed), and git for the commit hash. pdftoppm is not needed.

How it works: each Markdown file goes through pandoc (-f gfm-tex_math_dollars, so dollar
amounts stay text) to JSON, is cleaned up here (images embedded, links rewritten, table widths
left to the browser), then to HTML. All the documents of one PDF go into one HTML page, which
Chromium prints to PDF; then pypdf inserts the drawing set as-is, stamps the footers, fixes the
links, writes the bookmarks and checks the result. The contents page is laid out twice so its
page numbers are those of the merged file.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

# ---------------------------------------------------------------------------------------------
# The one place the repository link lives. Change it here when the project moves.
REPO_URL = "https://github.com/Icevyy14/codex/tree/claude/psa-slab-batch-scanner-w2e2m9/psa-slab-scanner"
# ---------------------------------------------------------------------------------------------

PACKAGE_DATE = "2026-10-27"
TITLE = "SlabRail: graded-slab batch scanner"
SUBTITLE = "Engineering design package – Rev A, draft for design review"
STATUS = "Designed, CAD-checked and simulated. Not yet built."
COVER_IMAGE = "docs/img/machine_iso.png"
DRAWINGS_PDF = "cad/out/drawings/SlabRail_drawings.pdf"
CAD_MANIFEST = "package/cad_manifest.txt"
CAD_README = "cad/README.md"
ZIP_NAME = "SlabRail_CAD.zip"
ZIP_TOP = "SlabRail_CAD"
DRAWINGS = "@drawings"  # marks where the drawing set goes in a volume

VOLUMES = [
    {
        "file": "SlabRail_Design_Review.pdf",
        "name": "Design review set",
        "what": "For reviewers: the reviewer brief, the design rationale and checks, the drawing set, "
                "the wiring and the bill of materials.",
        "toc_depth": 2,
        "parts": ["docs/REVIEWER_BRIEF.md", "docs/DESIGN.md", DRAWINGS, "docs/WIRING.md", "docs/BOM.md"],
    },
    {
        "file": "SlabRail_Complete_Documentation.pdf",
        "name": "Complete documentation",
        "what": "Every document in the repo, in reading order, plus the drawing set.",
        "toc_depth": 1,
        "parts": ["README.md", "docs/REVIEWER_BRIEF.md", "docs/DESIGN.md", "docs/CONTRACT.md",
                  "docs/BUILD_GUIDE.md", "docs/WIRING.md", "docs/FIRMWARE.md", "docs/OPERATING.md",
                  "docs/BOM.md", "docs/SHOPPING_LIST.md", "docs/RESEARCH.md", "software/README.md",
                  "cad/README.md", DRAWINGS],
    },
]

MAX_PDF_MB = 25.0          # hard limit per PDF
JPEG_OVER_BYTES = 600_000  # PNGs bigger than this go into the HTML as JPEG
JPEG_QUALITY = 90
PAGE_MARGIN = {"top": "1.8cm", "bottom": "2.0cm", "left": "1.8cm", "right": "1.8cm"}

ROOT = Path(__file__).resolve().parent.parent  # psa-slab-scanner/
OUT = ROOT / "package"

# Links that only live between the HTML and the final PDF; none may survive into a PDF.
XDOC = "https://xdoc.slabrail.invalid/"      # cross-document link inside one HTML page
SHEET = "https://sheet.slabrail.invalid/"    # link to a drawing sheet (resolved after the merge)

KNOWN_HTML_TAGS = set("""a abbr b bdi bdo blockquote br caption center cite code col colgroup dd del details
dfn div dl dt em figcaption figure font h1 h2 h3 h4 h5 h6 hr i img ins kbd li mark ol p picture pre q s
samp section small source span strike strong sub summary sup table tbody td tfoot th thead tr tt u ul
var video wbr""".split())


class BuildError(RuntimeError):
    pass


WARNINGS: list[str] = []


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"  WARNING: {msg}", flush=True)


def log(msg: str) -> None:
    print(msg, flush=True)


def rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix()


def repo_url_for(path: str) -> str:
    """Web link to one file or folder of the repo, built from REPO_URL alone."""
    path = path.strip("/")
    if "/tree/" in REPO_URL:  # .../tree/<branch>/<folder>  ->  .../blob/<branch>/<folder>/<file>
        return REPO_URL.replace("/tree/", "/blob/", 1).rstrip("/") + "/" + path
    return REPO_URL.rstrip("/") + "/blob/HEAD/" + path  # a repo root: the default branch


def doc_key(path: str) -> str:
    p = PurePosixPath(path)
    stem = p.stem
    return stem if p.parent.as_posix() in (".", "docs") else f"{p.parent.as_posix().replace('/', '-')}-{stem}"


# ---------------------------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------------------------

def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, **kw)
    except FileNotFoundError as e:
        raise BuildError(f"{cmd[0]} is not installed or not on PATH") from e
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else e.stderr
        raise BuildError(f"{' '.join(cmd[:3])} ... failed:\n{err}") from e


def check_tools() -> dict:
    versions = {}
    out = run(["pandoc", "--version"], text=True).stdout.splitlines()[0]
    m = re.search(r"(\d+)\.(\d+)", out)
    if not m or int(m.group(1)) < 3:
        raise BuildError(f"pandoc 3.x is needed, found: {out}")
    versions["pandoc"] = out.split()[1]
    try:
        import pypdf  # noqa: F401
        import PIL  # noqa: F401
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as e:
        raise BuildError(f"missing Python package: {e.name}. Install pypdf, Pillow and playwright.") from e
    versions["pypdf"] = pypdf.__version__
    versions["Pillow"] = PIL.__version__
    return versions


def git_info(inputs: list[str]) -> dict:
    info = {"short": "unknown", "full": "unknown", "date": "", "dirty": []}
    try:
        info["full"] = run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).stdout.strip()
        info["short"] = run(["git", "-C", str(ROOT), "rev-parse", "--short=7", "HEAD"], text=True).stdout.strip()
        info["date"] = run(["git", "-C", str(ROOT), "log", "-1", "--format=%cs", "HEAD"], text=True).stdout.strip()
        st = run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all", "--", *inputs],
                 text=True).stdout
        info["dirty"] = sorted({line[3:].strip() for line in st.splitlines() if line.strip()})
    except BuildError as e:
        warn(f"git information not available ({str(e).splitlines()[0]})")
    return info


# ---------------------------------------------------------------------------------------------
# Markdown -> cleaned pandoc AST -> HTML fragment
# ---------------------------------------------------------------------------------------------

def stringify(x) -> str:
    out: list[str] = []

    def w(y):
        if isinstance(y, dict):
            t = y.get("t")
            if t == "Str":
                out.append(y["c"])
            elif t in ("Space", "SoftBreak", "LineBreak"):
                out.append(" ")
            elif t in ("Code", "Math", "RawInline"):
                out.append(y["c"][1])
            elif t == "Note":
                return
            elif t in ("Link", "Image", "Span"):
                w(y["c"][1])
            else:
                w(y.get("c"))
        elif isinstance(y, list):
            for z in y:
                w(z)

    w(x)
    return re.sub(r"\s+", " ", "".join(out)).strip()


_image_cache: dict[Path, str] = {}


def image_data_uri(path: Path) -> str:
    if path in _image_cache:
        return _image_cache[path]
    data = path.read_bytes()
    ext = path.suffix.lower()
    if ext == ".svg":
        mime = "image/svg+xml"
    elif ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".png":
        mime = "image/png"
        if len(data) > JPEG_OVER_BYTES:
            from PIL import Image
            im = Image.open(io.BytesIO(data))
            if im.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", im.size, "white")
                im = im.convert("RGBA")
                bg.paste(im, mask=im.split()[-1])
                im = bg
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True, subsampling=0)
            data, mime = buf.getvalue(), "image/jpeg"
    elif ext == ".gif":
        mime = "image/gif"
    else:
        raise BuildError(f"unsupported image type: {rel(path)}")
    uri = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    _image_cache[path] = uri
    return uri


class Doc:
    """One Markdown file prepared for one volume."""

    def __init__(self, path: str):
        self.path = path
        self.key = doc_key(path)
        self.abs = ROOT / path
        if not self.abs.is_file():
            raise BuildError(f"document missing: {path}")
        self.dir = self.abs.parent
        self.ast = json.loads(run(["pandoc", "-f", "gfm-tex_math_dollars", "-t", "json", str(self.abs)]).stdout)
        self.headings: list[tuple[int, str, str]] = []  # (level, id, text) in document order
        self.ids: set[str] = set()
        self._collect(self.ast["blocks"])
        h1 = [h for h in self.headings if h[0] == 1]
        self.title = h1[0][2] if h1 else path
        self._audit()

    def _collect(self, x):
        if isinstance(x, dict):
            t = x.get("t")
            if t == "Header":
                level, attr, inl = x["c"]
                self.headings.append((level, attr[0], stringify(inl)))
                if attr[0]:
                    self.ids.add(attr[0])
            elif t in ("Div", "Span", "CodeBlock", "Table", "Code", "Link", "Image", "Figure"):
                c = x["c"]
                if isinstance(c, list) and c and isinstance(c[0], list) and c[0] and isinstance(c[0][0], str):
                    if c[0][0]:
                        self.ids.add(c[0][0])
            for v in x.values():
                self._collect(v)
        elif isinstance(x, list):
            for v in x:
                self._collect(v)

    def _audit(self):
        found = {"Math": [], "Strikeout": []}

        def w(y):
            if isinstance(y, dict):
                if y.get("t") in found:
                    found[y["t"]].append(stringify(y["c"])[:60])
                for v in y.values():
                    w(v)
            elif isinstance(y, list):
                for v in y:
                    w(v)

        w(self.ast["blocks"])
        for k, v in found.items():
            if v:
                warn(f"{self.path}: pandoc found {len(v)} {k} span(s), e.g. {v[0]!r}")


LONG_TOKEN = 22          # a word longer than this in a table cell may break anywhere
CODE_PT = 7.8            # code block font size, made smaller for long lines
CODE_MIN_PT = 5.6
MONO_ADVANCE = 0.602     # DejaVu Sans Mono advance width, in em
TEXT_WIDTH_PT = 612 - 2 * 72 * 1.8 / 2.54  # US Letter less the side margins


def long_token(text: str) -> bool:
    return any(len(w) > LONG_TOKEN for w in text.split())


def code_font_pt(code: str, depth: int) -> float | None:
    """Font size that fits the longest line of a code block on the page, or None for the default."""
    longest = max((len(line.rstrip()) for line in code.split("\n")), default=0)
    if not longest:
        return None
    avail = (TEXT_WIDTH_PT - 2 - 16 * depth) * 0.97
    size = avail / (MONO_ADVANCE * longest + 1.2)  # 1.2 em of padding
    if size >= CODE_PT:
        return None
    return max(CODE_MIN_PT, int(size * 10) / 10)


def prepare_fragment(doc: Doc, volume_docs: dict[str, Doc]) -> str:
    """Return the HTML of one document for one volume (ids prefixed with '<key>--')."""
    ast = json.loads(json.dumps(doc.ast))  # deep copy: link targets depend on the volume
    by_path = {d.path: d for d in volume_docs.values()}
    fig_counter = [0]

    def resolve_local(url: str) -> tuple[str, str]:
        path, _, frag = url.partition("#")
        target = (doc.dir / unquote(path)).resolve()
        try:
            rp = target.relative_to(ROOT).as_posix()
        except ValueError:
            rp = None
        return (rp or ""), frag

    def fix_link(el, extra_after: list):
        attr, inl, (url, ttl) = el["c"]
        if not url or url.startswith("#"):
            return
        if urlparse(url).scheme:  # https, http, mailto: leave as they are
            return
        rp, frag = resolve_local(url)
        if not rp:
            warn(f"{doc.path}: link outside the repo left as text: {url}")
            el["t"], el["c"] = "Span", [["", [], []], inl]
            return
        if rp in by_path:
            tgt = by_path[rp]
            if frag and frag not in tgt.ids:
                warn(f"{doc.path}: link to {rp}#{frag}: no such anchor, linking to the document start")
                frag = ""
            el["c"][2][0] = XDOC + (f"{tgt.key}--{frag}" if frag else f"doc-{tgt.key}")
            return
        p = ROOT / rp
        if not p.exists():
            warn(f"{doc.path}: link to {rp}, which does not exist in the repo")
        if p.is_file() and p.suffix.lower() in (".png", ".svg", ".jpg", ".jpeg", ".gif"):
            fig_counter[0] += 1
            fid = f"linked-figure-{fig_counter[0]}"
            el["c"][2][0] = "#" + fid
            extra_after.append({"t": "Div", "c": [[fid, ["linked-figure"], []], [
                {"t": "Para", "c": [{"t": "Image", "c": [["", [], []], [{"t": "Str", "c": rp}],
                                                         [image_data_uri(p), ""]]}]},
                {"t": "Para", "c": [{"t": "Emph", "c": [{"t": "Str", "c": f"Figure: {rp}"}]}]}]]})
            return
        el["c"][2][0] = repo_url_for(rp)

    def fix_image(el):
        attr, alt, (src, ttl) = el["c"]
        if urlparse(src).scheme:
            warn(f"{doc.path}: remote image left as a link target: {src}")
            return
        rp, _ = resolve_local(src)
        p = ROOT / rp if rp else None
        if not p or not p.is_file():
            raise BuildError(f"{doc.path}: image not found: {src}")
        el["c"][2][0] = image_data_uri(p)

    def raw_to_text(el):
        fmt, text = el["c"]
        if fmt.lower() != "html":
            return None
        s = text.strip()
        if s.startswith("<!--"):
            return None
        m = re.match(r"</?([A-Za-z][A-Za-z0-9-]*)", s)
        if m and m.group(1).lower() in KNOWN_HTML_TAGS:
            return None
        return text  # not real HTML (e.g. a "<where>" placeholder): show it as text

    def walk(x, extra_after, in_table=False, depth=0):
        if isinstance(x, dict):
            t = x.get("t")
            if t == "Link":
                fix_link(x, extra_after)
                if in_table and long_token(stringify(x["c"][1])):
                    x["c"][0][1] = list(x["c"][0][1]) + ["brk"]
            elif t == "Image":
                fix_image(x)
            elif t == "Code" and in_table and long_token(x["c"][1]):
                x["c"][0][1] = list(x["c"][0][1]) + ["brk"]
            elif t == "CodeBlock":
                size = code_font_pt(x["c"][1], depth)
                if size is not None:
                    x["c"][0][2] = list(x["c"][0][2]) + [["style", f"font-size: {size:.1f}pt"]]
            elif t == "RawInline":
                txt = raw_to_text(x)
                if txt is not None:
                    x["t"], x["c"] = "Str", txt
            elif t == "RawBlock":
                txt = raw_to_text(x)
                if txt is not None:
                    x["t"], x["c"] = "Para", [{"t": "Str", "c": txt}]
            elif t == "Table":
                attr, caption, colspecs = x["c"][0], x["c"][1], x["c"][2]
                attr[1] = list(attr[1]) + [f"cols-{len(colspecs)}"]
                for cs in colspecs:  # let the browser size the columns
                    cs[1] = {"t": "ColWidthDefault"}
                in_table = True
            if t in ("BulletList", "OrderedList", "BlockQuote", "DefinitionList"):
                depth += 1
            for v in list(x.values()):
                walk(v, extra_after, in_table, depth)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                if in_table and isinstance(v, dict) and v.get("t") == "Str" and long_token(v["c"]):
                    x[i] = {"t": "Span", "c": [["", ["brk"], []], [v]]}
                else:
                    walk(v, extra_after, in_table, depth)

    blocks = []
    for b in ast["blocks"]:
        extra: list = []
        walk(b, extra)
        blocks.append(b)
        blocks.extend(extra)
    ast["blocks"] = blocks
    res = run(["pandoc", "-f", "json", "-t", "html5", "--no-highlight", "--wrap=none",
               f"--id-prefix={doc.key}--"], input=json.dumps(ast).encode())
    frag = res.stdout.decode()
    frag = frag.replace(f'href="{XDOC}', 'href="#')
    if XDOC in frag:
        raise BuildError(f"{doc.path}: an internal cross-document link was not rewritten")
    return frag


# ---------------------------------------------------------------------------------------------
# drawing set
# ---------------------------------------------------------------------------------------------

def read_sheets(pdf_path: Path, allow_incomplete: bool = False) -> list[tuple[str, str]]:
    """(sheet number, title) for each page of the drawing PDF, in page order."""
    from pypdf import PdfReader
    if not pdf_path.is_file():
        raise BuildError(f"drawing set missing: {rel(pdf_path)}")
    r = PdfReader(pdf_path)
    if not r.pages:
        raise BuildError("the drawing set has no pages")
    texts = [p.extract_text() or "" for p in r.pages]
    index: dict[str, str] = {}
    lines = texts[0].splitlines()
    if "SHEET INDEX" in lines:
        for line in lines[lines.index("SHEET INDEX") + 1:]:
            m = re.match(r"^(D-\d{2})\s+(.+?)\s*$", line)
            if m:
                index[m.group(1)] = m.group(2)
            elif index:
                break
    sheets = []
    for i, t in enumerate(texts):
        m = re.search(r"SHEET\s+(D-\d{2})\s+of\s+(D-\d{2})", t)
        if not m:
            raise BuildError(f"drawing set page {i + 1}: no 'SHEET D-nn of D-nn' in the title block")
        num = m.group(1)
        title = index.get(num)
        if not title:  # fall back to the title block: the line after the sheet number
            after = t[m.end():].lstrip("\n").splitlines()
            title = re.sub(r"\s+SCALE\b.*$", "", after[0]).strip() if after else num
            warn(f"sheet {num} is not in the D-00 index; title taken from the title block: {title}")
        sheets.append((num, title))
    nums = [s[0] for s in sheets]
    if len(set(nums)) != len(nums):
        raise BuildError(f"drawing set: repeated sheet numbers {nums}")
    last = max(int(m) for m in re.findall(r"SHEET\s+D-\d{2}\s+of\s+D-(\d{2})", "\n".join(texts)))
    expected = [f"D-{i:02d}" for i in range(last + 1)]
    if nums != expected:
        gap = sorted(set(expected) - set(nums))
        msg = (f"drawing set is incomplete or out of order: {len(nums)} pages, title blocks say D-00 to "
               f"D-{last:02d}; missing {gap or 'none'}, order {nums}")
        if not allow_incomplete:
            raise BuildError(msg + " (use --allow-incomplete-drawings to build anyway)")
        warn(msg)
    if index and len(index) != len(sheets):
        warn(f"drawing set: the D-00 index lists {len(index)} sheets, the PDF has {len(sheets)} pages")
    for p in r.pages:
        w, h = float(p.mediabox.width), float(p.mediabox.height)
        if not (abs(w - 1224) < 2 and abs(h - 792) < 2):
            warn(f"drawing page is {w:.0f} x {h:.0f} pt, not ANSI B landscape (1224 x 792)")
            break
    return sheets


# ---------------------------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------------------------

CSS = r"""
@page { size: Letter; margin: %(top)s %(right)s %(bottom)s %(left)s; }
@page cover { margin: 1.8cm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Liberation Sans", "Arimo", "Arial", "DejaVu Sans", "FreeSans", "FreeSerif", sans-serif;
       font-size: 10pt; line-height: 1.38; color: #1a1a1a; margin: 0; }
p { margin: 0 0 0.55em 0; orphans: 2; widows: 2; }
a { color: #1f4e9c; text-decoration: none; overflow-wrap: anywhere; }
h1, h2, h3, h4, h5, h6 { font-weight: 700; line-height: 1.2; break-after: avoid; page-break-after: avoid;
       break-inside: avoid; color: #111; }
h1 { font-size: 18pt; margin: 0 0 0.6em 0; padding-bottom: 0.2em; border-bottom: 1.5px solid #333; }
h2 { font-size: 13.5pt; margin: 1.2em 0 0.45em 0; padding-bottom: 0.1em; border-bottom: 0.5px solid #bbb; }
h3 { font-size: 11.5pt; margin: 1.0em 0 0.35em 0; }
h4, h5, h6 { font-size: 10.5pt; margin: 0.9em 0 0.3em 0; }
ul, ol { margin: 0 0 0.6em 0; padding-left: 1.6em; }
ol { padding-left: 2.1em; }
li { margin: 0.1em 0; }
li > p { margin: 0 0 0.25em 0; }
blockquote { margin: 0.4em 0 0.7em 0; padding: 0.1em 0.8em; border-left: 3px solid #bbb; color: #333; }
hr { border: 0; border-top: 0.5px solid #999; margin: 1em 0; }
code { font-family: "DejaVu Sans Mono", "JetBrains Mono", "Liberation Mono", "FreeMono", monospace;
       font-size: 0.86em; background: #f2f2f2; padding: 0 0.15em; border-radius: 2px;
       overflow-wrap: anywhere; }
pre { font-family: "DejaVu Sans Mono", "JetBrains Mono", "Liberation Mono", "FreeMono", monospace;
      font-size: 7.8pt; line-height: 1.3; background: #f5f5f5; border: 0.5px solid #ddd; border-radius: 3px;
      padding: 0.45em 0.6em; margin: 0 0 0.7em 0; white-space: pre-wrap; overflow-wrap: anywhere;
      word-break: break-word; }
pre code { background: none; padding: 0; font-size: inherit; overflow-wrap: anywhere; }
table { width: 100%%; border-collapse: collapse; margin: 0.3em 0 0.9em 0; font-size: 8.4pt; line-height: 1.28;
        table-layout: auto; }
table.cols-5, table.cols-6 { font-size: 7.8pt; }
table.cols-7, table.cols-8, table.cols-9, table.cols-10 { font-size: 7.3pt; }
thead { display: table-header-group; }
tr { break-inside: avoid; page-break-inside: avoid; }
th, td { border: 0.5px solid #b8b8b8; padding: 2.5px 4px; vertical-align: top; text-align: left;
         overflow-wrap: break-word; word-break: normal; hyphens: manual; }
td a, th a, td code, th code { overflow-wrap: break-word; }
.brk, td a.brk, th a.brk, td code.brk, th code.brk { overflow-wrap: anywhere; word-break: break-all; }
th { background: #e9edf3; font-weight: 700; }
tbody tr:nth-child(even) td { background: #fafafa; }
td code, th code { font-size: 0.92em; }
img { max-width: 100%%; max-height: 7.6in; height: auto; display: block; margin: 0.3em auto 0.6em auto;
      break-inside: avoid; }
p > img:only-child { margin-bottom: 0.2em; }
.linked-figure { break-inside: avoid; margin: 0.4em 0 0.8em 0; }
.linked-figure p { text-align: center; font-size: 8.5pt; color: #444; }
section.doc { break-before: page; page-break-before: always; }
section.doc:first-of-type { break-before: auto; }

/* cover */
.cover { page: cover; break-after: page; page-break-after: always; text-align: center;
         height: 9.3in; display: flex; flex-direction: column; align-items: center; overflow: hidden; }
.cover > * { flex: 0 0 auto; }
.cover .kicker { font-size: 10pt; letter-spacing: 0.12em; text-transform: uppercase; color: #555; margin-top: 0.4in; }
.cover .title { font-size: 27pt; font-weight: 700; margin: 0.25in 0 0.12in 0; color: #111; }
.cover .subtitle { font-size: 14pt; color: #333; margin-bottom: 0.25in; }
.cover img { width: auto; height: auto; max-width: 100%%; max-height: 4.0in; margin: 0.15in auto 0.2in auto;
              border: 0.5px solid #ccc; }
.cover .status { display: inline-block; margin: 0.1in auto 0.2in auto; padding: 0.45em 1.1em;
                 border: 1.2px solid #8a1c1c; color: #8a1c1c; font-weight: 700; font-size: 11.5pt; }
.cover .volume { font-size: 11pt; color: #222; margin: 0.1in 0.6in 0.15in 0.6in; }
.cover .meta { font-size: 9.5pt; color: #333; margin-top: auto; line-height: 1.6; }
.cover .meta a { overflow-wrap: anywhere; }

/* contents */
.toc { break-after: page; page-break-after: always; }
.toc .toc-title { font-size: 18pt; font-weight: 700; margin: 0 0 0.7em 0; padding-bottom: 0.2em;
                  border-bottom: 1.5px solid #333; }
.toc a.row { display: flex; align-items: baseline; color: #1a1a1a; text-decoration: none; margin: 0; }
.toc a.row .t { flex: 0 1 auto; }
.toc a.row .src { color: #666; font-size: 0.85em; margin-left: 0.6em; white-space: nowrap; }
.toc a.row .dots { flex: 1 1 auto; border-bottom: 1px dotted #999; margin: 0 0.4em; min-width: 1.5em;
                   transform: translateY(-0.25em); }
.toc a.row .pn { flex: 0 0 auto; min-width: 2em; text-align: right; font-variant-numeric: tabular-nums; }
.toc a.l1 { font-weight: 700; font-size: 10.5pt; margin-top: 0.55em; }
.toc a.l2 { font-size: 9pt; padding-left: 1.4em; margin-top: 0.08em; color: #333; }
.toc .note { font-size: 8.5pt; color: #555; margin-top: 1.2em; }
""" % PAGE_MARGIN


def cover_html(vol: dict, git: dict) -> str:
    img = image_data_uri(ROOT / COVER_IMAGE)
    commit = git["short"] + (" + uncommitted changes" if git["dirty"] else "")
    return f"""
<div class="cover">
  <div class="kicker">{html.escape(vol['name'])}</div>
  <div class="title">{html.escape(TITLE)}</div>
  <div class="subtitle">{html.escape(SUBTITLE)}</div>
  <img src="{img}" alt="SlabRail, CAD render">
  <div><span class="status">{html.escape(STATUS)}</span></div>
  <div class="volume">{html.escape(vol['what'])}</div>
  <div class="meta">
    {PACKAGE_DATE} &nbsp;&middot;&nbsp; built from git commit <code>{html.escape(commit)}</code><br>
    <a href="{html.escape(REPO_URL)}">{html.escape(REPO_URL)}</a>
  </div>
</div>"""


def toc_html(vol: dict, docs: dict[str, Doc], sheets, pages: dict | None) -> str:
    def pn(key: str) -> str:
        return str(pages[key]) if pages and key in pages else "888"

    rows = ['<div class="toc"><div class="toc-title">Contents</div>']
    for part in vol["parts"]:
        if part == DRAWINGS:
            rows.append(f'<a class="row l1" href="{SHEET}first"><span class="t">Drawing set, Rev A</span>'
                        f'<span class="src">{html.escape(DRAWINGS_PDF)}</span><span class="dots"></span>'
                        f'<span class="pn">{pn("@drawings")}</span></a>')
            for num, title in sheets:
                rows.append(f'<a class="row l2" href="{SHEET}{num}"><span class="t">{num} &nbsp;{html.escape(title)}'
                            f'</span><span class="dots"></span><span class="pn">{pn("@" + num)}</span></a>')
            continue
        d = docs[part]
        rows.append(f'<a class="row l1" href="#doc-{d.key}"><span class="t">{html.escape(d.title)}</span>'
                    f'<span class="src">{html.escape(d.path)}</span><span class="dots"></span>'
                    f'<span class="pn">{pn("doc-" + d.key)}</span></a>')
        if vol["toc_depth"] >= 2:
            for level, hid, text in d.headings:
                if level == 2 and hid:
                    k = f"{d.key}--{hid}"
                    rows.append(f'<a class="row l2" href="#{html.escape(k)}"><span class="t">{html.escape(text)}'
                                f'</span><span class="dots"></span><span class="pn">{pn(k)}</span></a>')
    rows.append('<div class="note">Page numbers are those of this PDF. The drawing sheets are ANSI B landscape '
                'and carry their own sheet numbers. Links to files that are not in this PDF open the repository.'
                '</div></div>')
    return "\n".join(rows)


def volume_html(vol: dict, docs: dict[str, Doc], frags: dict[str, str], sheets, git: dict,
                pages: dict | None) -> str:
    body = [cover_html(vol, git), toc_html(vol, docs, sheets, pages)]
    for part in vol["parts"]:
        if part == DRAWINGS:
            continue
        d = docs[part]
        body.append(f'<section class="doc" id="doc-{d.key}">\n{frags[part]}\n</section>')
    return (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<title>{html.escape(TITLE)}: {html.escape(vol["name"])}</title>'
            f'<style>{CSS}</style></head><body>\n' + "\n".join(body) + "\n</body></html>\n")


FOOTER_CSS = """
@page { size: Letter; margin: 0; }
html, body { margin: 0; padding: 0; }
body { font-family: "Liberation Sans", "Arimo", "Arial", "DejaVu Sans", sans-serif; font-size: 7.6pt; color: #555; }
.pg { position: relative; width: 8.5in; height: 10.98in; overflow: hidden; break-after: page; page-break-after: always; }
.pg:last-child { break-after: auto; page-break-after: auto; }
.ft { position: absolute; left: 1.8cm; right: 1.8cm; bottom: 0.95cm; display: flex; border-top: 0.5px solid #aaa;
      padding-top: 3px; }
.ft .l { flex: 1 1 auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 1em; }
.ft .r { flex: 0 0 auto; white-space: nowrap; }
"""


def footer_html(items: list[tuple[str, str]]) -> str:
    pages = "".join(f'<div class="pg"><div class="ft"><span class="l">{html.escape(l)}</span>'
                    f'<span class="r">{html.escape(r)}</span></div></div>' for l, r in items)
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{FOOTER_CSS}</style></head>'
            f'<body>{pages}</body></html>')


# ---------------------------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------------------------

class Printer:
    def __init__(self, workdir: Path):
        from playwright.sync_api import sync_playwright
        self.workdir = workdir
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.launch()
        except Exception as e:
            self._pw.stop()
            raise BuildError(f"Chromium for Playwright could not start: {e}") from e
        self.version = self.browser.version

    def pdf(self, html_text: str, name: str, outline: bool = True) -> Path:
        src = self.workdir / f"{name}.html"
        dst = self.workdir / f"{name}.pdf"
        src.write_text(html_text, encoding="utf-8")
        page = self.browser.new_page()
        page.set_default_timeout(600_000)
        try:
            page.goto(src.as_uri(), wait_until="load")
            page.evaluate("document.fonts.ready.then(() => true)")
            broken = page.evaluate("Array.from(document.images).filter(i => !i.complete || i.naturalWidth === 0)"
                                   ".map(i => i.alt || i.src.slice(0, 60))")
            if broken:
                raise BuildError(f"{name}: images that did not load: {broken}")
            page.pdf(path=str(dst), prefer_css_page_size=True, print_background=True,
                     outline=outline, tagged=outline)
        finally:
            page.close()
        return dst

    def close(self):
        try:
            self.browser.close()
        finally:
            self._pw.stop()


def flatten_outline(reader) -> list[tuple[str, int, float | None]]:
    out = []

    def w(items):
        for it in items:
            if isinstance(it, list):
                w(it)
            else:
                try:
                    pg = reader.get_destination_page_number(it)
                except Exception:
                    pg = None
                top = it.get("/Top")
                out.append((str(it.title), pg, float(top) if top is not None else None))

    w(reader.outline)
    return out


def named_pages(reader) -> dict[str, tuple[int, float | None]]:
    res = {}
    for name, dest in reader.named_destinations.items():
        try:
            pg = reader.get_destination_page_number(dest)
        except Exception:
            continue
        top = dest.get("/Top")
        res[name.lstrip("/")] = (pg, float(top) if top is not None else None)
    return res


def norm(s: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", s.lower())


def build_volume(vol: dict, printer: Printer, sheets, git: dict, workdir: Path) -> dict:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, ByteStringObject, NameObject, NullObject, NumberObject
    from pypdf.generic import Fit

    t0 = time.time()
    log(f"\n== {vol['file']}")
    doc_parts = [p for p in vol["parts"] if p != DRAWINGS]
    docs = {p: Doc(p) for p in doc_parts}
    keyed = {d.key: d for d in docs.values()}
    if len(keyed) != len(docs):
        raise BuildError("two documents map to the same key")
    frags = {p: prepare_fragment(d, keyed) for p, d in docs.items()}
    log(f"  {len(docs)} documents converted ({time.time() - t0:.1f} s)")

    draw_reader = PdfReader(ROOT / DRAWINGS_PDF)
    n_draw = len(draw_reader.pages)
    has_draw = DRAWINGS in vol["parts"]
    after_draw = None  # first document after the drawing set
    if has_draw:
        i = vol["parts"].index(DRAWINGS)
        after_draw = next((p for p in vol["parts"][i + 1:] if p != DRAWINGS), None)

    pages = None
    for attempt in range(1, 5):
        html_text = volume_html(vol, docs, frags, sheets, git, pages)
        pdf_path = printer.pdf(html_text, f"{Path(vol['file']).stem}_pass{attempt}")
        reader = PdfReader(pdf_path)
        n_html = len(reader.pages)
        dests = named_pages(reader)
        if has_draw:
            ins = dests[f"doc-{docs[after_draw].key}"][0] if after_draw else n_html
        else:
            ins = n_html

        def final(h: int) -> int:  # page index in the HTML pdf -> page index in the merged pdf
            return h + n_draw if has_draw and h >= ins else h

        new = {}
        for name, (pg, _top) in dests.items():
            new[name] = final(pg) + 1
        for d in docs.values():
            if f"doc-{d.key}" not in new:
                raise BuildError(f"{vol['file']}: no page found for {d.path}")
        if has_draw:
            new["@drawings"] = ins + 1
            for j, (num, _t) in enumerate(sheets):
                new["@" + num] = ins + j + 1
        log(f"  layout pass {attempt}: {n_html} HTML pages ({time.time() - t0:.1f} s)")
        if pages is not None and all(pages.get(k) == v for k, v in new.items()):
            break
        pages = new
    else:
        raise BuildError(f"{vol['file']}: contents page numbers did not settle")

    # ---- merge
    writer = PdfWriter(clone_from=reader)
    if has_draw:
        for j, p in enumerate(draw_reader.pages):
            writer.insert_page(p, index=ins + j)
    total = len(writer.pages)
    html_final = [final(h) for h in range(n_html)]

    # which document each HTML page belongs to
    starts = sorted((dests[f"doc-{d.key}"][0], d) for d in docs.values())
    owner: dict[int, Doc | None] = {}
    for h in range(n_html):
        cur = None
        for s, d in starts:
            if h >= s:
                cur = d
        owner[h] = cur

    # ---- footers (every HTML page but the cover)
    items, targets = [], []
    for h in range(1, n_html):
        d = owner[h]
        left = f"{d.title}  ·  {d.path}" if d else "Contents"
        f = html_final[h]
        items.append((f"SlabRail Rev A, draft for design review  ·  {left}", f"Page {f + 1} of {total}"))
        targets.append(f)
    if items:
        foot = PdfReader(printer.pdf(footer_html(items), f"{Path(vol['file']).stem}_footer", outline=False))
        if len(foot.pages) != len(items):
            raise BuildError(f"footer overlay has {len(foot.pages)} pages, expected {len(items)}")
        for fp, f in zip(foot.pages, targets):
            writer.pages[f].merge_page(fp)
    for page in writer.pages:  # pypdf leaves merged and inserted page contents uncompressed
        page.compress_content_streams(level=9)

    # ---- links: drawing-sheet links become page links; no placeholder link may remain
    sheet_page = {"first": ins} if has_draw else {}
    for j, (num, _t) in enumerate(sheets):
        if has_draw:
            sheet_page[num] = ins + j
    n_ext = 0
    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        for a in annots:
            a = a.get_object()
            act = a.get("/A")
            if not act or act.get("/S") != "/URI":
                continue
            uri = str(act.get("/URI"))
            if uri.startswith(SHEET):
                key = uri[len(SHEET):]
                if key not in sheet_page:
                    raise BuildError(f"link to an unknown drawing sheet: {key}")
                del a["/A"]
                a[NameObject("/Dest")] = ArrayObject([writer.pages[sheet_page[key]].indirect_reference,
                                                      NameObject("/Fit")])
            elif ".slabrail.invalid" in uri or uri.startswith("file:"):
                raise BuildError(f"{vol['file']}: unresolved internal link left in the PDF: {uri}")
            else:
                n_ext += 1

    # ---- bookmarks
    if "/Outlines" in writer.root_object:
        del writer.root_object["/Outlines"]
    flat = flatten_outline(reader)
    seq = [(d, lvl, hid, txt) for _s, d in starts for (lvl, hid, txt) in d.headings]
    h2_pos: dict[tuple[str, str], tuple[int, float | None]] = {}
    # Chromium names outline items after the heading text, but repeats parts of it when the heading
    # holds inline elements, so match the two lists in order and only loosely by text.
    def same(outline_title: str, text: str) -> bool:
        a, b = norm(outline_title), norm(text)
        return a == b or (bool(a) and bool(b) and (b in a or a in b))

    if len(flat) == len(seq) and all(same(a[0], b[3]) for a, b in zip(flat, seq)):
        for (title, pg, top), (d, lvl, hid, txt) in zip(flat, seq):
            if lvl == 2 and pg is not None:
                h2_pos[(d.key, hid)] = (pg, top)
    else:
        warn(f"{vol['file']}: Chromium's heading outline ({len(flat)}) does not match the documents' headings "
             f"({len(seq)}); section bookmarks come from the contents links only")
    for (name, (pg, top)) in dests.items():
        if "--" in name:
            k, hid = name.split("--", 1)
            h2_pos.setdefault((k, hid), (pg, top))

    bookmarks = []
    writer.add_outline_item("Cover", 0)
    bookmarks.append(("Cover", 1, 0))
    writer.add_outline_item("Contents", 1)
    bookmarks.append(("Contents", 2, 0))
    for part in vol["parts"]:
        if part == DRAWINGS:
            parent = writer.add_outline_item(f"Drawing set ({len(sheets)} sheets, ANSI B)", ins, is_open=True)
            bookmarks.append((f"Drawing set ({len(sheets)} sheets, ANSI B)", ins + 1, 0))
            for j, (num, title) in enumerate(sheets):
                writer.add_outline_item(f"{num} {title}", ins + j, parent=parent)
                bookmarks.append((f"{num} {title}", ins + j + 1, 1))
            continue
        d = docs[part]
        pg = final(dests[f"doc-{d.key}"][0])
        label = f"{d.title} ({PurePosixPath(d.path).name})" if d.path != "README.md" else f"{d.title} (README.md)"
        if PurePosixPath(d.path).parent.as_posix() not in (".", "docs"):
            label = f"{d.title} ({d.path})"
        parent = writer.add_outline_item(label, pg, is_open=False)
        bookmarks.append((label, pg + 1, 0))
        for level, hid, text in d.headings:
            if level != 2 or (d.key, hid) not in h2_pos:
                continue
            hp, top = h2_pos[(d.key, hid)]
            fit = Fit.xyz(top=top) if top is not None else Fit.fit()
            writer.add_outline_item(text, final(hp), parent=parent, fit=fit)
            bookmarks.append((text, final(hp) + 1, 1))
    writer.page_mode = "/UseOutlines"

    # ---- metadata, reproducible
    for k in ("/Metadata",):
        if k in writer.root_object:
            del writer.root_object[k]
    date = "D:" + PACKAGE_DATE.replace("-", "") + "000000Z"
    writer.metadata = None
    writer.add_metadata({
        "/Title": f"{TITLE}: {vol['name']}",
        "/Subject": SUBTITLE,
        "/Creator": "package/build_package.py",
        "/Keywords": f"SlabRail; Rev A; git {git['short']}",
        "/CreationDate": date,
        "/ModDate": date,
    })
    try:  # drop the objects that merging left behind
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    except TypeError:  # pypdf < 5.x
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    tmp = workdir / vol["file"]
    with open(tmp, "wb") as fh:
        writer.write(fh)
    digest = hashlib.md5(tmp.read_bytes()).digest()
    writer._ID = ArrayObject([ByteStringObject(digest), ByteStringObject(digest)])
    with open(tmp, "wb") as fh:
        writer.write(fh)

    log(f"  {total} pages, {n_ext} external links, {len(bookmarks)} bookmarks ({time.time() - t0:.1f} s)")
    return {"tmp": tmp, "pages": total, "html_pages": n_html, "draw_at": ins + 1 if has_draw else None,
            "docs": [(docs[p].title, p, pages[f"doc-{docs[p].key}"]) for p in doc_parts],
            "bookmarks": bookmarks, "ext_links": n_ext, "page_map": pages}


# ---------------------------------------------------------------------------------------------
# checks on the finished PDFs and zip
# ---------------------------------------------------------------------------------------------

def check_pdf(path: Path) -> dict:
    from pypdf import PdfReader
    r = PdfReader(path)
    size_mb = path.stat().st_size / 1e6
    if size_mb > MAX_PDF_MB:
        raise BuildError(f"{path.name} is {size_mb:.1f} MB, over the {MAX_PDF_MB:.0f} MB limit")
    not_embedded, seen, type3 = set(), set(), set()

    def fonts_in(res):
        if res is None:
            return
        res = res.get_object()
        fonts = res.get("/Font")
        if fonts:
            for _n, f in fonts.get_object().items():
                f = f.get_object()
                if id(f) in seen:
                    continue
                seen.add(id(f))
                sub = f.get("/Subtype")
                if sub == "/Type3":
                    type3.add(str(f.get("/Name") or f.get("/BaseFont") or "?"))
                    continue
                desc = f.get("/FontDescriptor")
                if sub == "/Type0":
                    desc = f["/DescendantFonts"][0].get_object().get("/FontDescriptor")
                desc = desc.get_object() if desc is not None else None
                if desc is None or not any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                    not_embedded.add(str(f.get("/BaseFont")))
        xo = res.get("/XObject")
        if xo:
            for _n, x in xo.get_object().items():
                x = x.get_object()
                if x.get("/Subtype") == "/Form":
                    fonts_in(x.get("/Resources"))

    for p in r.pages:
        fonts_in(p.get("/Resources"))
    if not_embedded:
        raise BuildError(f"{path.name}: fonts not embedded: {sorted(not_embedded)}")
    if type3:
        warn(f"{path.name}: {len(type3)} Type 3 font(s) (embedded, but drawn as glyph procedures; usually a CFF "
             f"or colour font that Chromium could not embed as TrueType)")
    return {"pages": len(r.pages), "mb": size_mb}


def build_zip(workdir: Path) -> dict:
    t0 = time.time()
    log(f"\n== {ZIP_NAME}")
    mpath = ROOT / CAD_MANIFEST
    if not mpath.is_file():
        raise BuildError(f"manifest missing: {CAD_MANIFEST}")
    entries = []
    for n, line in enumerate(mpath.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        p = PurePosixPath(s)
        if p.is_absolute() or ".." in p.parts:
            raise BuildError(f"{CAD_MANIFEST} line {n}: path must be relative and inside the repo: {s}")
        entries.append(p.as_posix())
    if len(set(entries)) != len(entries):
        dup = sorted({e for e in entries if entries.count(e) > 1})
        raise BuildError(f"{CAD_MANIFEST}: repeated paths {dup}")
    missing = [e for e in entries if not (ROOT / e).is_file()]
    if missing:
        raise BuildError(f"{CAD_MANIFEST}: {len(missing)} file(s) missing:\n  " + "\n  ".join(missing))
    if not (ROOT / CAD_README).is_file():
        raise BuildError(f"missing {CAD_README}")
    stamp = tuple(int(x) for x in PACKAGE_DATE.split("-")) + (0, 0, 0)
    files = [(f"{ZIP_TOP}/README.md", ROOT / CAD_README)] + [(f"{ZIP_TOP}/{e}", ROOT / e) for e in entries]
    tmp = workdir / ZIP_NAME
    total = 0
    with zipfile.ZipFile(tmp, "w") as z:
        for arc, src in files:
            zi = zipfile.ZipInfo(arc, date_time=stamp)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zi.create_system = 3
            data = src.read_bytes()
            total += len(data)
            z.writestr(zi, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(tmp) as z:
        bad = z.testzip()
        if bad:
            raise BuildError(f"{ZIP_NAME}: CRC error in {bad}")
        names = z.namelist()
        for arc, src in files:
            if z.getinfo(arc).file_size != src.stat().st_size:
                raise BuildError(f"{ZIP_NAME}: size mismatch for {arc}")
    if len(names) != len(files):
        raise BuildError(f"{ZIP_NAME}: {len(names)} entries, expected {len(files)}")
    kinds: dict[str, int] = {}
    for e in entries:
        ext = PurePosixPath(e).suffix.lower() or "(none)"
        kinds[ext] = kinds.get(ext, 0) + 1
    log(f"  {len(files)} files, {total / 1e6:.1f} MB uncompressed, "
        f"{tmp.stat().st_size / 1e6:.1f} MB zipped ({time.time() - t0:.1f} s)")
    return {"tmp": tmp, "count": len(files), "manifest_count": len(entries), "raw": total, "kinds": kinds}


# ---------------------------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------------------------

def human(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{n / 1e3:.0f} kB"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_readme(results: dict, zipres: dict, sheets, git: dict, versions: dict, elapsed: float) -> str:
    L = []
    L.append("# SlabRail engineering package\n")
    L.append(f"{TITLE}. {SUBTITLE}. {STATUS}\n")
    L.append("Everything in this folder except `build_package.py` and `cad_manifest.txt` is generated by "
             "`build_package.py` from the files in the repo. Do not edit the outputs by hand: change the source "
             "files and rebuild.\n")
    L.append(f"- Package date: {PACKAGE_DATE}")
    commit = f"`{git['short']}` (`{git['full']}`)" if git["full"] != "unknown" else "unknown (no git)"
    L.append(f"- Inputs from git commit: {commit}")
    if git["dirty"]:
        L.append(f"- **The inputs had uncommitted changes when this was built** ({len(git['dirty'])} file(s): "
                 + ", ".join(f"`{d}`" for d in git["dirty"][:12]) + (", ..." if len(git["dirty"]) > 12 else "")
                 + "). Commit them and rebuild for a package that matches a commit exactly.")
    else:
        L.append("- The inputs had no uncommitted changes: the package matches that commit.")
    L.append(f"- Repository: {REPO_URL}\n")
    L.append("## Files\n")
    L.append("| File | What it is | Size | Pages |")
    L.append("|---|---|---:|---:|")
    for vol in VOLUMES:
        r = results[vol["file"]]
        L.append(f"| `{vol['file']}` | {vol['what']} | {human(r['bytes'])} | {r['pages']} |")
    L.append(f"| `{ZIP_NAME}` | The CAD files: {zipres['manifest_count']} files from `cad_manifest.txt` "
             f"(assembly STEP and GLB, printed-part STEP and STL, print list, cut list, probe-flag DXF/SVG, "
             f"geometry-check results, the drawing set PDF, `docs/BOM.csv`) under `{ZIP_TOP}/` with their repo "
             f"paths, plus `cad/README.md` again as `{ZIP_TOP}/README.md`. {human(zipres['raw'])} unzipped. | "
             f"{human(results[ZIP_NAME]['bytes'])} | |")
    L.append("| `build_package.py` | The script that builds everything here. | | |")
    L.append("| `cad_manifest.txt` | The list of files that go into the zip, one repo-relative path per line. | | |")
    L.append("")
    for vol in VOLUMES:
        r = results[vol["file"]]
        L.append(f"### {vol['file']}\n")
        L.append("| Starts on page | Section | Source |")
        L.append("|---:|---|---|")
        L.append("| 1 | Cover | |")
        L.append("| 2 | Contents | |")
        for part in vol["parts"]:
            if part == DRAWINGS:
                L.append(f"| {r['draw_at']} | Drawing set, {len(sheets)} sheets ({sheets[0][0]} to {sheets[-1][0]}), "
                         f"ANSI B landscape, merged as-is | `{DRAWINGS_PDF}` |")
                continue
            title, path, pg = next(x for x in r["docs"] if x[1] == part)
            L.append(f"| {pg} | {title} | `{path}` |")
        L.append("")
    L.append("### Drawing sheets\n")
    L.append("| Sheet | Title |")
    L.append("|---|---|")
    for num, title in sheets:
        L.append(f"| {num} | {title} |")
    L.append("")
    L.append("## Checksums (SHA-256)\n")
    L.append("```")
    for name in [v["file"] for v in VOLUMES] + [ZIP_NAME]:
        L.append(f"{results[name]['sha256']}  {name}")
    L.append("```\n")
    L.append("## How to rebuild\n")
    L.append("From the `psa-slab-scanner/` folder:\n")
    L.append("```\npython3 package/build_package.py\n```\n")
    L.append("It needs pandoc 3.x, Python 3 with `pypdf`, `Pillow` and `playwright` (the Python package) and "
             "Playwright's Chromium browser (on a new machine: `python3 -m playwright install chromium`), plus git "
             "for the commit hash. It stops with an error if a document, image, drawing or manifest file is "
             "missing, and checks each PDF (size, embedded fonts, no unresolved internal links) and the zip "
             "(every manifest file present, sizes and CRCs) before it replaces the old outputs.\n")
    L.append("What it does: each Markdown file is converted by pandoc with `-f gfm-tex_math_dollars` (dollar "
             "amounts are not math); images are embedded from the document's folder; links between documents in "
             "the same PDF become PDF links; links to files that are not in the PDF point to the repository. "
             "Chromium (through Playwright) prints the documents on US Letter; pypdf inserts the drawing set "
             "unchanged, adds the footers, bookmarks and contents page numbers (laid out twice so they are "
             "right). The PDF metadata date is the package date, so a rebuild from the same inputs with the "
             "same tools gives the same content.\n")
    L.append("To change the repository link, edit `REPO_URL` at the top of `build_package.py`; the date, title "
             "and status line are next to it. The documents in each PDF and their order are in `VOLUMES`.\n")
    tools = ", ".join(f"{k} {v}" for k, v in versions.items())
    L.append(f"Last built with {tools}; the build took {elapsed:.0f} s.")
    if WARNINGS:
        L.append("\nBuild warnings:\n")
        for w in WARNINGS:
            L.append(f"- {w}")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--keep-work", metavar="DIR", help="keep the intermediate HTML and PDFs in DIR")
    ap.add_argument("--require-clean", action="store_true",
                    help="stop if any input file has uncommitted changes")
    ap.add_argument("--allow-incomplete-drawings", action="store_true",
                    help="build even if the drawing set's sheet numbers have gaps (for test builds only)")
    args = ap.parse_args()

    t_start = time.time()
    os.chdir(ROOT)
    log(f"Building the SlabRail package in {rel(OUT)}/")
    versions = check_tools()

    inputs = sorted({p for v in VOLUMES for p in v["parts"] if p != DRAWINGS}
                    | {DRAWINGS_PDF, CAD_MANIFEST, CAD_README, "docs/img", "package/build_package.py"})
    if (ROOT / CAD_MANIFEST).is_file():
        inputs += [s.strip() for s in (ROOT / CAD_MANIFEST).read_text().splitlines() if s.strip()]
    git = git_info(sorted(set(inputs)))
    log(f"  git {git['short']}" + (f", {len(git['dirty'])} input file(s) with uncommitted changes"
                                    if git["dirty"] else ", inputs clean"))
    if git["dirty"] and args.require_clean:
        raise BuildError("uncommitted input changes:\n  " + "\n  ".join(git["dirty"]))

    if args.keep_work:
        workdir = Path(args.keep_work).resolve()
        workdir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        workdir = Path(tempfile.mkdtemp(prefix="slabrail_pkg_"))
        cleanup = True
    try:
        sheets = read_sheets(ROOT / DRAWINGS_PDF, args.allow_incomplete_drawings)
        log(f"  drawing set: {len(sheets)} sheets, {sheets[0][0]} to {sheets[-1][0]}")
        zipres = build_zip(workdir)
        printer = Printer(workdir)
        versions["Chromium"] = printer.version
        try:
            vols = {v["file"]: build_volume(v, printer, sheets, git, workdir) for v in VOLUMES}
        finally:
            printer.close()

        results = {}
        for name, r in vols.items():
            info = check_pdf(r["tmp"])
            if info["pages"] != r["pages"]:
                raise BuildError(f"{name}: page count changed on re-reading")
        for name, r in vols.items():
            dst = OUT / name
            os.replace(r["tmp"], dst) if r["tmp"].parent == dst.parent else shutil.move(str(r["tmp"]), dst)
            results[name] = {"bytes": dst.stat().st_size, "pages": r["pages"], "sha256": sha256(dst),
                             "draw_at": r["draw_at"], "docs": r["docs"]}
        dst = OUT / ZIP_NAME
        shutil.move(str(zipres["tmp"]), dst)
        results[ZIP_NAME] = {"bytes": dst.stat().st_size, "sha256": sha256(dst)}

        elapsed = time.time() - t_start
        (OUT / "README.md").write_text(write_readme(results, zipres, sheets, git, versions, elapsed),
                                       encoding="utf-8")
        log("\nWritten:")
        for name in [v["file"] for v in VOLUMES] + [ZIP_NAME, "README.md"]:
            p = OUT / name
            extra = f", {results[name]['pages']} pages" if name in vols else ""
            log(f"  package/{name}: {p.stat().st_size:,} bytes{extra}")
        for name, r in vols.items():
            log(f"\nBookmarks in {name}:")
            for title, pg, lvl in r["bookmarks"]:
                if lvl == 0 or name == VOLUMES[0]["file"]:
                    log(f"  {'    ' * lvl}{title} .... p{pg}")
        if WARNINGS:
            log(f"\n{len(WARNINGS)} warning(s):")
            for w in WARNINGS:
                log(f"  - {w}")
        log(f"\nDone in {elapsed:.1f} s")
        return 0
    finally:
        if cleanup:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as e:
        print(f"\nBUILD FAILED: {e}", file=sys.stderr)
        sys.exit(1)
