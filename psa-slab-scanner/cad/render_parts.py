"""Isometric contact sheet of every printed part -> docs/img/printed_parts.png"""

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

D = Path(__file__).resolve().parent / "out" / "printed"
OUT = Path(__file__).resolve().parents[1] / "docs" / "img" / "printed_parts.png"


def main():
    rows = json.loads((D / "print_list.json").read_text())
    tiles = []
    for r in rows:
        scad = D / f"_{r['part']}.scad"
        scad.write_text(f'color([0.95,0.45,0.1]) import("{(D / (r["part"] + ".stl")).resolve()}");\n')
        png = D / f"_{r['part']}.png"
        subprocess.run(["xvfb-run", "-a", "openscad", "-o", str(png), "--imgsize=500,400", "--camera=0,0,0,55,0,25,0", "--viewall", "--autocenter", "--colorscheme=Tomorrow", str(scad)], check=True, capture_output=True, timeout=300)
        tiles.append((r, Image.open(png).convert("RGB")))
        scad.unlink()
    cols = 4
    w, h = 500, 460
    sheet = Image.new("RGB", (cols * w, ((len(tiles) + cols - 1) // cols) * h), (250, 250, 250))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    for i, (r, im) in enumerate(tiles):
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(im, (x, y))
        sx, sy, sz = r["size_mm"]
        d.text((x + 12, y + 405), f"{r['part']}  x{r['qty']}   {sx:.0f}x{sy:.0f}x{sz:.0f} mm", fill=(20, 20, 20), font=font)
    sheet.save(OUT)
    for r in rows:
        (D / f"_{r['part']}.png").unlink(missing_ok=True)
    print(OUT)


if __name__ == "__main__":
    main()
