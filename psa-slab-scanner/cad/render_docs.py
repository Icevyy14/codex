"""Render the documentation images (docs/img/*.png) from the model.

Run from cad/:  python render_docs.py
"""

from __future__ import annotations

import shutil
import textwrap
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


def face_down_view(dest: Path, px: float = 8.0) -> None:
    """What the head camera sees of the top slab at hover (free cup 7 mm above it, lens 147 mm above it, CAM_DY toward the
    label): every head part below the lens projected from the lens onto the slab plane (tessellated CAD solids), over the slab,
    the measured card position, the label band and the face-down card window. +Y (the arm) is up, the label end down.
    Dashed: the nearest the cup a PSA and a CGC card top can come (layout.card_top_worst); yellow: where the camera sees its
    LED ring mirrored in the slab back (glare)."""
    import model as M
    from PIL import Image, ImageDraw, ImageFont
    from dims import SLAB_H, SLAB_W

    lz, ly, plane = M.CAM_Z, M.CAM_DY, -(L.CUP_HANG + 5.0)
    xr, yr, foot = (-52.0, 52.0), (-74.0, 74.0), 224
    W, H = int((xr[1] - xr[0]) * px), int((yr[1] - yr[0]) * px)
    P_ = lambda x, y: ((x - xr[0]) * px, (yr[1] - y) * px)  # noqa: E731  image y down = slab -Y down
    im = Image.new("RGB", (W, H + foot), (250, 250, 250))
    d = ImageDraw.Draw(im, "RGBA")
    edge = -SLAB_H / 2
    d.rectangle([P_(-SLAB_W / 2, SLAB_H / 2), P_(SLAB_W / 2, edge)], fill=(225, 232, 240), outline=(60, 60, 60))
    d.rounded_rectangle([P_(-L.CARD_W / 2, edge + L.CARD_TOP_FROM_EDGE[1] + L.CARD_L), P_(L.CARD_W / 2, edge + L.CARD_TOP_FROM_EDGE[1])],
                        radius=L.CARD_CORNER_R * px, fill=(70, 95, 170))
    d.rectangle([P_(-37, edge + 26.0), P_(37, edge + 5.0)], fill=(245, 245, 245), outline=(120, 120, 120))  # label insert
    for p in M.head_parts(0.0, 0.0, compression=0.0):
        sh = p.shape.val()
        bb = sh.BoundingBox()
        if p.name in ("head_camera", "head_led_ring", "head_ring_leads") or bb.zmin >= lz - 0.01:  # the ring sits round the lens, out of view
            continue
        verts, tris = sh.tessellate(0.1, 0.3)
        v = [(q.x, q.y, min(q.z, lz - 0.05)) for q in verts]
        r, g, b, _ = p.color
        col = (int(r * 200), int(g * 200), int(b * 200), 255)
        for t in tris:
            if any(verts[i].z >= lz - 0.05 for i in t):
                continue
            pts = []
            for i in t:
                x, y, z = v[i]
                s = (lz - plane) / (lz - z)
                pts.append(P_(x * s, ly + (y - ly) * s))
            d.polygon(pts, fill=col)
    h = lz - plane  # glare: the ring mirrored in the slab back, a band round the lens axis
    r_in, r_out = (M.HEAD_RING[k] / 2 * h / (2 * h + M.HEAD_RING_FACE_DZ) for k in (1, 0))
    for r, w in ((r_out, 6), (r_in, 6)):
        d.ellipse([P_(-r, ly + r), P_(r, ly - r)], outline=(235, 190, 20, 255), width=w)
    for g, col in (("PSA", (40, 40, 40)), ("CGC", (150, 30, 150))):
        y = L.card_top_worst(g)
        for x in range(int(xr[0]), int(xr[1]), 4):
            d.line([P_(x, y), P_(x + 2, y)], fill=col, width=3)
        d.text(P_(xr[0] + 1, y + 3.2), f"{g} card top, worst case", fill=col)
    for x0, y0, x1, y1 in L.FACE_DOWN_WINDOW_MM:
        d.rectangle([P_(x0, y1), P_(x1, y0)], outline=(230, 30, 30), width=4)
    d.line([P_(-3, 0), P_(3, 0)], fill=(0, 0, 0), width=2)
    d.line([P_(0, -3), P_(0, 3)], fill=(0, 0, 0), width=2)
    d.ellipse([P_(-1.5, ly + 1.5), P_(1.5, ly - 1.5)], outline=(0, 140, 0), width=3)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    a = L.window_area()
    text = (f"Head camera at hover: lens {lz + 7:.0f} mm above the slab, {-ly:.0f} mm toward the label (green circle; + = cup axis). "
            f"Red: the face-down card window, {a:.0f} mm2, clear of every head part. Blue: the median PSA card, label at the bottom. "
            "Dashed: worst-case card tops (PSA, CGC). Yellow: where the camera sees its ring light mirrored in the slab (glare).")
    for k, line in enumerate(textwrap.wrap(text, 66)):
        d.text((16, H + 8 + 29 * k), line, fill=(20, 20, 20), font=font)
    im.save(dest)


CARRY_PARTS = ("z_spine", "z_plate", "carry_", "fc_carry", "fh_carry", "z_carriage", "z_rail")


def carry_closeup(dest: Path) -> None:
    """The carry-height sensor just below its trip (slot clear) and at the Z hard top stop (flag through the slot)."""
    import subprocess

    import cadquery as cq
    import model as M
    from PIL import Image, ImageDraw, ImageFont

    tiles = []
    c0 = L.CARRY_SENSOR_C0
    for c, text in ((c0 - 2.0, f"c = {c0 - 2:g}: flag 2 mm below the beam, slot clear"), (L.C_HARD_TOP, f"c = {L.C_HARD_TOP:.0f} (top stop): flag still in the beam")):
        d = build.OUT / "renders" / f"stl_carry_{c:.0f}"
        d.mkdir(parents=True, exist_ok=True)
        lines = []
        for p in M.carriage_parts(0.0) + M.head_parts(0.0, c):
            if not p.name.startswith(CARRY_PARTS):
                continue
            shape = p.shape.intersect(M.box(-90, 20, M.CS_BEAM_Z - 60, 40, 100, M.CS_BEAM_Z + 60)) if p.name.startswith(("z_spine", "z_rail")) else p.shape
            cq.exporters.export(shape, str(d / f"{p.name}.stl"), tolerance=0.05, angularTolerance=0.1)
            r, g, b, a = p.color
            a = {"carry_sensor": 0.35, "z_spine": 0.3}.get(p.name, a)
            lines.append(f'color([{r},{g},{b},{a}]) import("{p.name}.stl");')
        beam = M.cyl((M.CS_TIP_X + M.TCST_AXIS, M.CS_Y - 7, M.CS_BEAM_Z), 0.8, 14, (0, 1, 0))
        cq.exporters.export(beam, str(d / "beam.stl"), tolerance=0.05, angularTolerance=0.1)
        lines.append('color([1.0,0.1,0.1,1.0]) import("beam.stl");')
        lines.sort(key=lambda ln: ",0.35]" in ln or ",0.3]" in ln)
        (d / "scene.scad").write_text("\n".join(lines) + "\n")
        png = d / "carry.png"
        z = M.CS_BEAM_Z
        subprocess.run(["xvfb-run", "-a", "openscad", "-o", str(png), "--imgsize=900,900", f"--camera=-175,215,{z + 55},-42,62,{z - 6}", "--projection=p",
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


XSW_PARTS = ("x_beam", "upright_L", "x_bumper_L", "x_switch_mount", "x_home_switch", "fx_xsw", "x_bracket", "x_rail")
ZSW_PARTS = ("z_spine", "z_rail", "z_motor_mount", "z_switch_mount", "z_top_switch", "fc_zsw", "z_plate", "z_carriage", "fc_mount_tab")


def switch_closeups(dest: Path) -> None:
    """The X home switch and the Z top switch at their trip points (cup X = X_HOME_SWITCH, c = Z_SWITCH_C), each on its printed
    mount, with the part that works it (the x_bracket's finger, the z_plate's chamfered back face). Big parts are cut down to
    the corner that matters and drawn see-through."""
    import subprocess

    import cadquery as cq
    import model as M
    from PIL import Image, ImageDraw, ImageFont

    x, c = L.X_HOME_SWITCH, L.Z_SWITCH_C
    xclip = {"x_bracket": M.box(-60, 80, 330, 2, 100, 400), "x_beam": M.box(-75, 100, 375, 5, 150, 425), "upright_L": M.box(-75, 100, 300, 5, 150, 400),
             "x_rail": M.box(-75, 90, 375, 5, 110, 425)}
    zclip = {"z_spine": M.box(-45, 60, 560, 80, 100, 640), "z_rail": M.box(-45, 50, 560, 80, 100, 640), "z_plate": M.box(-45, 0, 560, 80, 60, 640),
             "z_carriage": M.box(-45, 0, 560, 80, 100, 640)}
    tiles = []
    for tag, parts, keep, clip, ghost, cam, text in (
            ("x", M.frame_parts(x) + M.carriage_parts(x, c), XSW_PARTS, xclip, {"x_beam": 0.25, "upright_L": 0.25, "x_rail": 0.4},
             "-95,-140,300,-20,92,366", f"X home switch at cup X {x:g}: the x_bracket's finger has just pressed the lever"),
            ("z", M.carriage_parts(0.0, c) + M.head_parts(0.0, c), ZSW_PARTS, zclip, {"z_spine": 0.3, "z_motor_mount": 0.25, "z_rail": 0.4},
             "195,55,655,36,56,604", f"Z top switch at c = {c:g}: the z_plate's chamfer has just pressed the lever")):
        d = build.OUT / "renders" / f"stl_switch_{tag}"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        lines = []
        for p in parts:
            if not p.name.startswith(keep):
                continue
            shape = p.shape.intersect(clip[p.name]) if p.name in clip else p.shape
            if not shape.vals() or shape.val().Volume() < 1e-3:
                continue
            cq.exporters.export(shape, str(d / f"{p.name}.stl"), tolerance=0.05, angularTolerance=0.1)
            r, g, b, a = p.color
            lines.append((ghost.get(p.name, a), f'color([{r},{g},{b},{ghost.get(p.name, a)}]) import("{p.name}.stl");'))
        (d / "scene.scad").write_text("\n".join(ln for _, ln in sorted(lines, key=lambda t: -t[0])) + "\n")  # opaque first
        png = d / "switch.png"
        subprocess.run(["xvfb-run", "-a", "openscad", "-o", str(png), "--imgsize=900,900", f"--camera={cam}", "--projection=p",
                        "--colorscheme=Tomorrow", "scene.scad"], check=True, cwd=d, capture_output=True, timeout=600)
        tiles.append((Image.open(png).convert("RGB"), text))
    w, h = tiles[0][0].size
    bar = 60
    out = Image.new("RGB", (2 * w, h + bar), (250, 250, 250))
    dr = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for i, (im, text) in enumerate(tiles):
        out.paste(im, (i * w, 0))
        dr.text((i * w + 18, h + 18), text, fill=(20, 20, 20), font=font)
    out.save(dest)


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    face_down_view(DOCS / "face_down_view.png")
    print(DOCS / "face_down_view.png")
    carry_closeup(DOCS / "carry_sensor.png")
    print(DOCS / "carry_sensor.png")
    switch_closeups(DOCS / "home_switches.png")
    print(DOCS / "home_switches.png")
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
