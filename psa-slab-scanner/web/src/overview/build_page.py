"""Fill template.html from the repository: BOM totals, check/test counts, sim timing, embedded renders."""

import base64
import csv
import datetime as dt
import io
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[3]  # psa-slab-scanner/
sys.path.insert(0, str(ROOT / "cad"))
import layout as L  # noqa: E402

BRANCH = "claude/psa-slab-batch-scanner-w2e2m9"
REPO = f"https://github.com/icevyy14/codex/blob/{BRANCH}/psa-slab-scanner"
TREE = f"https://github.com/icevyy14/codex/tree/{BRANCH}/psa-slab-scanner"
PALETTE = ["#2a5a8a", "#4f7fae", "#7aa3c9", "#2b7149", "#5c9a72", "#8dbf9b", "#8d5c00", "#b88a3a", "#d9b878", "#6b5b8a", "#9585b0", "#56625e"]


def img_uri(name: str, width: int = 1400) -> str:
    im = Image.open(ROOT / "docs" / "img" / f"{name}.png").convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=82, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def bom():
    rows = list(csv.DictReader((ROOT / "docs" / "BOM.csv").open()))
    cats, allowance, pct = {}, 0.0, ""
    for r in rows:
        v = float(r["total_usd"] or 0)
        if r["category"] == "Allowance":
            allowance += v
            m = re.search(r"(\d+)%", r["item"] + r["spec"])
            pct = m.group(1) if m else pct
            continue
        if v:
            cats[r["category"]] = cats.get(r["category"], 0.0) + v
    return cats, allowance, pct


def main(tests: str, school: str, sec_per_slab: float, run_time: str) -> None:
    s = (HERE / "template.html").read_text()
    cats, allowance, pct = bom()
    sub = sum(cats.values())
    total = sub + allowance
    order = sorted(cats.items(), key=lambda kv: -kv[1])
    bar = "".join(f'<i style="width:{100 * v / sub:.2f}%;background:{PALETTE[i % len(PALETTE)]}" title="{k} ${v:,.0f}"></i>' for i, (k, v) in enumerate(order))
    legend = "".join(f'<li><i style="background:{PALETTE[i % len(PALETTE)]}"></i><span>{k}</span><span>${v:,.0f}</span></li>' for i, (k, v) in enumerate(order))
    checks = re.search(r"(\d+)/(\d+) checks passed", (ROOT / "cad" / "out" / "checks.txt").read_text())
    cells = []
    pockets = {round(p.x): p for p in L.pockets()}
    sx = round(L.station_xy()[0])
    for cell in range(L.N_CELLS):
        x = round(42 + 92 * cell)
        if x == sx:
            cells.append('<div class="cell cam"><b>Cam</b><span>reads fronts</span></div>')
            continue
        p = pockets[x]
        if p.index == 0:
            cells.append('<div class="cell out"><b>0</b><span>starts empty</span></div>')
        elif p.index == 12:
            cells.append('<div class="cell exc"><b>12</b><span>set aside</span></div>')
        else:
            cells.append(f'<div class="cell"><b>{p.index}</b><span>30 slabs</span></div>')
    rep = {
        "DATE": dt.date.today().strftime("%-d %B %Y"),
        "REPO": REPO, "TREE": TREE,
        "BOM_TOTAL": f"${total:,.0f}", "BOM_TOTAL_SHORT": f"${total / 1000:.1f}k", "BOM_SCHOOL": school, "ALLOW_PCT": pct,
        "COSTBAR": bar, "COSTLEGEND": legend,
        "CHECKS": f"{checks.group(1)}/{checks.group(2)}", "TESTS": tests,
        "SEC_PER_SLAB": f"{sec_per_slab:.1f}", "RUN_TIME": run_time,
        "C_EMPTY": f"{L.C_SAFE_EMPTY:g}", "C_LOADED": f"{L.C_SAFE_LOADED:g}",
        "ROW": "".join(cells),
    }
    for k, v in rep.items():
        s = s.replace("{{" + k + "}}", v)
    s = re.sub(r"\{\{IMG:(\w+)\}\}", lambda m: img_uri(m.group(1)), s)
    left = re.findall(r"\{\{[A-Z_:a-z0-9]+\}\}", s)
    assert not left, left
    out = HERE / "slabrail.html"
    out.write_text(s)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB); BOM ${sub:,.2f} + ${allowance:,.2f} = ${total:,.2f}; checks {rep['CHECKS']}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4])
