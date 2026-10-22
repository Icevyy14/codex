"""Render the documentation images (docs/img/*.png) from the model.

Run from cad/:  python render_docs.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

import build
import layout as L

DOCS = Path(__file__).resolve().parents[1] / "docs" / "img"
P = L.pockets()
FULL = {p.index: L.STACK_MAX for p in P if p.role == "source"}
SX = L.station_xy()[0]

SHOTS = {
    # name: (cup_x, c, held, fill, camera(eye..., center...))
    "storyboard_1_loaded": (P[1].x, L.C_SAFE_EMPTY, False, FULL, (640, -2150, 1350, 640, 0, 230)),
    "storyboard_2_first_transfer": ((P[0].x + P[1].x) / 2, L.C_SAFE_LOADED, True, {**FULL, 1: 29}, (640, -2150, 1350, 640, 0, 230)),
    "storyboard_3_midway": (P[2].x, 140.0, False, {**FULL, 0: 30, 1: 18, 2: 12}, (640, -2150, 1350, 640, 0, 230)),
    "storyboard_4_done": (P[11].x, L.C_SAFE_EMPTY, False, {**{i: 30 for i in range(0, 11)}, 11: 0, 12: 2}, (640, -2150, 1350, 640, 0, 230)),
    "machine_iso": (P[4].x, L.C_SAFE_EMPTY, False, {**FULL, 0: 30, 1: 30, 2: 30, 3: 11, 4: 19}, (2150, -1750, 1500, 640, 30, 260)),
    "machine_front": (P[4].x, L.C_SAFE_EMPTY, False, FULL, (640, -3000, 360, 640, 0, 320)),
    "head_closeup": (P[5].x, 6.6 * 4, False, {**FULL, 5: 4}, (P[5].x + 430, -560, 470, P[5].x, 0, 130)),
    "station_read": (SX, L.STATION_READ_C, True, {**FULL, 0: 30, 1: 30, 2: 30, 3: 30, 4: 30, 5: 12, 6: 18}, (SX + 520, -620, 420, SX, 0, 160)),
}


CAPTIONS = {
    "storyboard_1_loaded": "1. Load: 11 stacks of up to 30, face-down, label toward you. Pocket 0 (left) and pocket 12 (right) stay empty.",
    "storyboard_2_first_transfer": "2. The cup lifts the TOP slab of stack 1 straight up, reads it, and sets it down in empty pocket 0.",
    "storyboard_3_midway": "3. Repeat until stack 1 is gone - then stack 2 moves into the now-empty pocket 1, and so on.",
    "storyboard_4_done": "4. Done: every slab read, every stack one pocket to the left (order reversed). Rejects wait in pocket 12.",
}


def caption(png: Path, text: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    im = Image.open(png).convert("RGB")
    bar = 70
    out = Image.new("RGB", (im.width, im.height + bar), (250, 250, 250))
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 30)
    except OSError:
        font = ImageFont.load_default()
    d.text((24, im.height + 18), text, fill=(20, 20, 20), font=font)
    out.save(png)


def contact_sheet(names: list[str], dest: Path) -> None:
    from PIL import Image

    ims = [Image.open(DOCS / f"{n}.png") for n in names]
    w, h = ims[0].size
    sheet = Image.new("RGB", (w * 2, h * 2), (255, 255, 255))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % 2) * w, (i // 2) * h))
    sheet = sheet.resize((w, h))
    sheet.save(dest)


def phase0_jig(dest: Path) -> None:
    """The Phase 0 camera jig on its own (model.phase0_parts)."""
    import subprocess

    import cadquery as cq
    import model as M

    d = build.OUT / "renders" / "stl_phase0"
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for p in M.phase0_parts():
        cq.exporters.export(p.shape, str(d / f"{p.name}.stl"), tolerance=0.1, angularTolerance=0.2)
        r, g, b, a = p.color
        lines.append(f'color([{r},{g},{b},{a}]) import("{p.name}.stl");')
    (d / "scene.scad").write_text("\n".join(lines) + "\n")
    subprocess.run(["xvfb-run", "-a", "openscad", "-o", str(dest), "--imgsize=1100,1300", "--camera=640,-820,620,0,0,165", "--projection=p",
                    "--colorscheme=Tomorrow", "scene.scad"], check=True, cwd=d, capture_output=True, timeout=600)


PROBE_PARTS = ("head_foot", "buffer", "buffer_rod", "buffer_stop", "cup", "probe_flag", "vac_fitting", "contact_sensor", "probe_m3", "probe_nut")


def probe_closeup(dest: Path) -> None:
    """The contact probe on head_foot, buffer free (slot clear) and fully pushed up (flag through the slot),
    side by side. The sensor is drawn see-through so the flag shows inside its slot."""
    import subprocess

    import cadquery as cq
    import model as M
    from PIL import Image, ImageDraw, ImageFont

    tiles = []
    for t, text in ((0.0, "Cup free: flag 2 mm below the beam, slot clear"), (float(L.BUFFER_STROKE), f"Pushed up {L.BUFFER_STROKE:.0f} mm: flag through the slot, still in its guide")):
        d = build.OUT / "renders" / f"stl_probe_{t:.0f}"
        d.mkdir(parents=True, exist_ok=True)
        lines = []
        for p in M.head_parts(0.0, 0.0, compression=t):
            if not p.name.startswith(PROBE_PARTS):
                continue
            cq.exporters.export(p.shape, str(d / f"{p.name}.stl"), tolerance=0.05, angularTolerance=0.1)
            r, g, b, a = p.color
            a = {"contact_sensor": 0.35, "head_foot": 0.45}.get(p.name, a)
            lines.append(f'color([{r},{g},{b},{a}]) import("{p.name}.stl");')
        beam = M.cyl((M.TCST_AXIS_X, M.PROBE_Y - 7, M.PROBE_BEAM_Z), 0.8, 14, (0, 1, 0))  # the light beam, drawn as a red rod
        cq.exporters.export(beam, str(d / "beam.stl"), tolerance=0.05, angularTolerance=0.1)
        lines.append('color([1.0,0.1,0.1,1.0]) import("beam.stl");')
        lines.sort(key=lambda ln: ",0.35]" in ln or ",0.45]" in ln)  # opaque first: see-through parts blend over them
        (d / "scene.scad").write_text("\n".join(lines) + "\n")
        png = d / "probe.png"
        subprocess.run(["xvfb-run", "-a", "openscad", "-o", str(png), "--imgsize=900,900", "--camera=128,-224,152,13,6,92", "--projection=p",
                        "--colorscheme=Tomorrow", "scene.scad"], check=True, cwd=d, capture_output=True, timeout=600)
        tiles.append((Image.open(png).convert("RGB"), text))
    w, h = tiles[0][0].size
    bar = 60
    out = Image.new("RGB", (2 * w, h + bar), (250, 250, 250))
    dr = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    for i, (im, text) in enumerate(tiles):
        out.paste(im, (i * w, 0))
        dr.text((i * w + 18, h + 16), text, fill=(20, 20, 20), font=font)
    out.save(dest)


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    phase0_jig(DOCS / "phase0_jig.png")
    print(DOCS / "phase0_jig.png")
    probe_closeup(DOCS / "probe_closeup.png")
    print(DOCS / "probe_closeup.png")
    build.export_flag_drawing(DOCS / "probe_flag.png")
    print(DOCS / "probe_flag.png")
    for name, (x, c, held, fill, cam) in SHOTS.items():
        build.POSES[name] = (x, c, held, fill)
        build.VIEWS[name] = cam
        out = build.render(name, views=(name,), size=(1800, 1100))[0]
        dest = DOCS / f"{name}.png"
        shutil.copy(out, dest)
        if name in CAPTIONS:
            caption(dest, CAPTIONS[name])
        print(dest)
    contact_sheet(list(CAPTIONS), DOCS / "storyboard.png")


if __name__ == "__main__":
    main()
