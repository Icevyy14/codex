"""Export printable parts (STL + STEP), the assembly (STEP), a cut list, the probe-flag drawing, the head occluders for the
simulator (heads_cad.json), and PNG renders.

Run from the cad/ folder:  python build.py            (everything)
                           python build.py --renders  (renders only)
Renders need OpenSCAD + xvfb-run (headless). STL/STEP need only CadQuery.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path

import cadquery as cq

import layout as L
import model as M

OUT = Path(__file__).resolve().parent / "out"

_P = L.pockets()
_FULL = {p.index: L.STACK_MAX for p in _P if p.role == "source"}
POSES = {
    # name: (cup_x, c, held_slab, fill)
    "home": (_P[1].x, L.C_SAFE_EMPTY, False, None),
    "pick_bottom": (_P[11].x, 6.6, False, {**_FULL, 11: 1}),
    "carry": ((_P[1].x + _P[0].x) / 2, L.C_SAFE_LOADED, True, {**_FULL, 0: 12, 1: 17}),
    "station": (L.station_xy()[0], L.STATION_READ_C, True, {**_FULL, 0: 30, 1: 30, 2: 30, 3: 12, 4: 0}),
}

VIEWS = {
    # name: openscad --camera=eye_x,eye_y,eye_z,center_x,center_y,center_z  (None = follow the head)
    "iso": (1650, -1650, 1250, 640, 40, 200),
    "front": (640, -2600, 330, 640, 40, 260),
    "side": (2600, 40, 330, 640, 40, 260),
    "top": (640, 40, 2900, 640, 41, 0),
    "head_closeup": None,
}


def export_printed() -> list[dict]:
    d = OUT / "printed"
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, shape, qty, note in M.printed_catalog():
        n = len(shape.solids().vals())
        if n != 1:  # a floating island prints as spaghetti or a loose block
            raise SystemExit(f"printed part {name} is {n} separate solids, not one: fix model.py before exporting")
        bb = shape.val().BoundingBox()
        placed = shape.translate((-bb.xmin, -bb.ymin, -bb.zmin))  # sit on the build plate
        cq.exporters.export(placed, str(d / f"{name}.stl"), tolerance=0.05, angularTolerance=0.1)
        cq.exporters.export(placed, str(d / f"{name}.step"))
        rows.append({"part": name, "qty": qty, "size_mm": [round(bb.xlen, 1), round(bb.ylen, 1), round(bb.zlen, 1)], "volume_cm3": round(shape.val().Volume() / 1000, 1), "note": note})
    (d / "print_list.json").write_text(json.dumps(rows, indent=2))
    return rows


def assembly(pose: str) -> list[M.Part]:
    x, c, held, fill = POSES[pose]
    return M.machine(x, c, held_slab=held, fill=fill)


def export_assembly(pose: str = "home") -> Path:
    d = OUT / "assembly"
    d.mkdir(parents=True, exist_ok=True)
    assy = cq.Assembly(name=f"slabrail_{pose}")
    for p in assembly(pose):
        assy.add(p.shape, name=p.name, color=cq.Color(*p.color))
    path = d / f"slabrail_{pose}.step"
    assy.save(str(path))
    return path


def _scene(pose: str, d: Path, hide: tuple[str, ...] = ()) -> Path:
    stl_dir = d / f"stl_{pose}"
    stl_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for p in assembly(pose):
        if any(p.name.startswith(h) for h in hide):
            continue
        f = stl_dir / f"{p.name}.stl"
        cq.exporters.export(p.shape, str(f), tolerance=0.2, angularTolerance=0.3)
        r, g, b, a = p.color
        lines.append(f'color([{r},{g},{b},{a}]) import("{f.name}");')
    scad = stl_dir / "scene.scad"
    scad.write_text("\n".join(lines) + "\n")
    return scad


def render(pose: str, views=("iso",), size=(1600, 1100), hide: tuple[str, ...] = ()) -> list[Path]:
    if not shutil.which("openscad"):
        raise SystemExit("openscad not installed")
    d = OUT / "renders"
    d.mkdir(parents=True, exist_ok=True)
    scad = _scene(pose, d, hide)
    outs = []
    for v in views:
        cv = VIEWS[v]
        if cv is None:  # close-up that follows the head
            x, c = POSES[pose][0], POSES[pose][1]
            cv = (x + 420, -520, c + 380, x, 0, c + 60)
        cam = ",".join(str(n) for n in cv)
        png = d / f"{pose}_{v}.png"
        cmd = ["xvfb-run", "-a", "openscad", "-o", str(png), f"--imgsize={size[0]},{size[1]}", f"--camera={cam}", "--projection=p", "--colorscheme=Tomorrow", str(scad)]
        subprocess.run(cmd, check=True, cwd=scad.parent, capture_output=True, timeout=600)
        outs.append(png)
    return outs


def write_cut_list() -> None:
    """cad/out/cut_list.csv. Fields with commas are quoted (csv module), so every row has exactly 4 columns."""
    OUT.mkdir(exist_ok=True)
    rows = [("profile", "use", "length_mm", "qty")] + [(a, b, f"{c:.0f}", q) for a, b, c, q in M.cut_list()]
    rows += [("8mm hardwood dowel", "guide rod", f"{L.POST_H + L.PAD_T + L.ROD_EMBED:.0f}", len(L.rods()))]
    with open(OUT / "cut_list.csv", "w", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


def _flag_drawing() -> tuple[list, float, float]:
    """Probe-flag blank as drawing primitives in mm (page coordinates, y down): ("poly", pts) | ("line", p, q, dashed)
    | ("circle", p, r) | ("text", p, str, size). Returns (items, width, height)."""
    pts = M.flag_blank()
    us, vs = [u for u, _ in pts], [v for _, v in pts]
    m, right = 20.0, 66.0  # margin; notes column right of the part
    w, h = max(us) - min(us) + 2 * m + right, max(vs) - min(vs) + 2 * m + 16
    X = lambda u: u - min(us) + m  # noqa: E731
    Y = lambda v: max(vs) - v + m  # noqa: E731
    P = lambda u, v: (X(u), Y(v))  # noqa: E731
    tx, x0, x1 = M.FLAG_TAB_X, M.FLAG_X[0], M.FLAG_X[1]
    top, bot, band = M.FLAG_TOP - M.FLAG_BEND_Z, M.FLAG_BOTTOM - M.FLAG_BEND_Z, M.FLAG_BAND_Z - M.FLAG_BEND_Z
    ba = 1.5708 * (M.FLAG_BEND_R + 0.44 * M.FLAG_T)  # [Likely] bend allowance, 90 deg, K = 0.44
    hole_v = ba + (M.PROBE_Y - M.FLAG_T / 2 - M.FLAG_BEND_R)  # where the hole lands if drilled flat
    it = [("poly", [P(u, v) for u, v in pts])]
    it.append(("line", P(-tx - 13, 0), P(tx + 3, 0), True))  # bend line
    it.append(("text", P(-tx - 19.5, 0.8), "BEND", 2.2))
    it.append(("line", P(0, bot - 3), P(0, 13 + 3), True))  # neck centre line = hole line
    it.append(("circle", P(0, hole_v), M.FLAG_HOLE / 2))
    it.append(("line", P(-3.5, hole_v), P(3.5, hole_v), False))
    sz = 2.0
    def dim_h(v, ua, ub, label):  # horizontal dimension at height v
        it.extend([("line", P(ua, v), P(ub, v), False), ("line", P(ua, v - 1), P(ua, v + 1), False), ("line", P(ub, v - 1), P(ub, v + 1), False),
                   ("text", P((ua + ub) / 2 - len(label) * 0.55, v + 0.8), label, sz)])
    def dim_v(u, va, vb, label, left=False):  # vertical dimension at u, label right (or left) of it
        tu = u - 1.2 - len(label) * 1.1 if left else u + 1.2
        it.extend([("line", P(u, va), P(u, vb), False), ("line", P(u - 1, va), P(u + 1, va), False), ("line", P(u - 1, vb), P(u + 1, vb), False),
                   ("text", P(tu, (va + vb) / 2 - 0.7), label, sz)])
    dim_h(bot - 4, 0, x1, f"{x1:.1f}")
    dim_h(bot - 8, 0, x0, f"{x0:.1f}")
    dim_h(13 + 3, -tx, tx, f"{2 * tx:.1f}")
    dim_v(x1 + 4, 0, top, f"{-top:.1f}")  # trip edge, below the bend line
    dim_v(x1 + 9, 0, bot, f"{-bot:.2f}")
    dim_v(-tx - 3, 0, band, f"{-band:.1f}", left=True)
    dim_v(-tx - 3, 0, 13, "13 (trim)", left=True)
    notes = [
        "SlabRail probe flag, 1:1 (check the 10 mm bar)",
        f"1.0 mm aluminium sheet. Blank {x1 + tx:.1f} x {13 - bot:.2f} mm.",
        "Dimensions from the BEND line and the dashed",
        "neck centre line (= hole centre line).",
        "1. Cut and file to the outline. The blade's top",
        "   edge is the trip edge: straight, square.",
        "2. This view shows the face that faces the buffer.",
        "   Neck in the vise, jaws at the BEND line; bend",
        "   the tab 90 deg TOWARD YOU (r ~1 mm). Bent the",
        "   other way the blade ends up on the wrong side.",
        "   Plate stays flat; check 90 deg with a square.",
        "3. THEN drill 5.2 mm on the centre line,",
        f"   {M.PROBE_Y - M.FLAG_T / 2:.1f} mm from the plate's inner face",
        f"   (lands ~{hole_v:.1f} above the bend line flat).",
        "4. Trim the tab to 2 mm past the hole.",
        "5. Deburr. It rides in a 1.9 mm guide slot",
        "   and a 3.1 mm sensor slot.",
    ]
    for i, n in enumerate(notes):
        it.append(("text", (X(x1) + 18, m + 2 + i * 3.4), n, 2.0))
    sb = (m, h - 6)  # 10 mm scale bar
    it.extend([("line", sb, (sb[0] + 10, sb[1]), False), ("line", (sb[0], sb[1] - 1.5), (sb[0], sb[1] + 1.5), False),
               ("line", (sb[0] + 10, sb[1] - 1.5), (sb[0] + 10, sb[1] + 1.5), False), ("text", (sb[0] + 12, sb[1] + 0.8), "10 mm", 2.0)])
    return it, w, h


def export_flag_drawing(png: Path | None = None) -> Path:
    """cad/out/probe_flag_blank.svg (print at 100 %) + .dxf (outline), and optionally a PNG of the same drawing."""
    OUT.mkdir(exist_ok=True)
    items, w, h = _flag_drawing()
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.1f}mm" height="{h:.1f}mm" viewBox="0 0 {w:.2f} {h:.2f}">',
           f'<rect width="{w:.2f}" height="{h:.2f}" fill="white"/>']
    for kind, *a in items:
        if kind == "poly":
            svg.append('<polygon points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in a[0]) + '" fill="#dde3ea" stroke="black" stroke-width="0.25"/>')
        elif kind == "line":
            (x0, y0), (x1, y1), dashed = a
            svg.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" stroke="black" stroke-width="0.15"' + (' stroke-dasharray="1.2,0.8"' if dashed else "") + "/>")
        elif kind == "circle":
            (x, y), r = a
            svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="none" stroke="black" stroke-width="0.15" stroke-dasharray="0.8,0.6"/>')
        else:
            (x, y), s, size = a
            svg.append(f'<text x="{x:.2f}" y="{y:.2f}" font-family="sans-serif" font-size="{size}">{s}</text>')
    path = OUT / "probe_flag_blank.svg"
    path.write_text("\n".join(svg + ["</svg>"]) + "\n")
    cq.exporters.export(cq.Workplane("XY").polyline(M.flag_blank()).close(), str(OUT / "probe_flag_blank.dxf"))
    if png is not None:
        from PIL import Image, ImageDraw, ImageFont

        k = 12  # px per mm
        im = Image.new("RGB", (int(w * k), int(h * k)), (255, 255, 255))
        d = ImageDraw.Draw(im)
        for kind, *a in items:
            if kind == "poly":
                d.polygon([(x * k, y * k) for x, y in a[0]], fill=(221, 227, 234), outline=(0, 0, 0), width=3)
            elif kind == "line":
                (x0, y0), (x1, y1), dashed = a
                if dashed:
                    n = int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / 2.0)
                    for i in range(n):
                        f0, f1 = i / n, (i + 0.6) / n
                        d.line([((x0 + (x1 - x0) * f0) * k, (y0 + (y1 - y0) * f0) * k), ((x0 + (x1 - x0) * f1) * k, (y0 + (y1 - y0) * f1) * k)], fill=(0, 0, 0), width=2)
                else:
                    d.line([(x0 * k, y0 * k), (x1 * k, y1 * k)], fill=(0, 0, 0), width=2)
            elif kind == "circle":
                (x, y), r = a
                d.ellipse([(x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k], outline=(0, 0, 0), width=2)
            else:
                (x, y), s, size = a
                try:
                    font = ImageFont.truetype("DejaVuSans.ttf", int(size * k))
                except OSError:
                    font = ImageFont.load_default()
                d.text((x * k, y * k - size * k * 0.85), s, fill=(0, 0, 0), font=font)
        im.save(png)
    return path


def export_heads(path: Path | None = None) -> Path:
    """The head as the head camera sees it, for software/slabscan/sim.py HEADS (model.occluder_boxes), plus the camera offset,
    the face-down card window and the carry-sensor trip height the software needs."""
    path = path or OUT / "heads_cad.json"
    rows = M.occluder_boxes(0.0)
    doc = {
        "about": "Head occluders for the simulator, from cad/model.py occluder_boxes(). Boxes (x0, y0, x1, y1, z0, z1, grey): mm, "
                 "X along the row, Y along the slab (label end negative), from the CUP axis; z above the cup height c. "
                 "Pose: cup FREE (buffer at rest), as in the hover frame and with a slab held. Each box bounds one CAD solid "
                 "(their shadow covers the CAD's exactly at hover and held, 0.5 % larger). The lens is NOT on the cup axis: "
                 "project a point (x, y, z) to the slab plane D below the lens as lens_xy + ((x, y) - lens_xy) * D / (lens_z - z).",
        "lens": {"x": 0.0, "y": M.CAM_DY, "z": M.CAM_Z},
        "hover_lens_to_slab_mm": M.CAM_Z + 7.0,
        "held_lens_to_slab_mm": M.CAM_Z + L.CUP_HANG,
        "HEADS": [[*b, g] for _, b, g in rows],
        "names": [n for n, _, _ in rows],
        "FACE_DOWN_WINDOW_MM": L.FACE_DOWN_WINDOW_MM,
        "face_down_window_mm_from_camera_axis": L.face_down_window_cam(),
        "HEAD_CAM_DY": L.HEAD_CAM_DY,
        "CARRY_SENSOR_C0": L.CARRY_SENSOR_C0,
        "card_top_from_label_edge_mm": {"min": L.CARD_TOP_FROM_EDGE[0], "median": L.CARD_TOP_FROM_EDGE[1], "max": L.CARD_TOP_FROM_EDGE[2]},
    }
    lines = []
    for k, v in doc.items():  # one HEADS row (and its name) per line, so it diffs and pastes
        if k in ("HEADS", "names"):
            lines.append(f' "{k}": [\n' + ",\n".join("  " + json.dumps(r) for r in v) + "\n ]")
        else:
            lines.append(f' "{k}": {json.dumps(v)}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{\n" + ",\n".join(lines) + "\n}\n")
    json.loads(path.read_text())
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders", action="store_true")
    a = ap.parse_args()
    if not a.renders:
        print(json.dumps(export_printed(), indent=1))
        write_cut_list()
        print("flag drawing", export_flag_drawing())
        print("head occluders", export_heads())
        for pose in POSES:
            print("assembly", export_assembly(pose))
    for pose in POSES:
        print(render(pose, views=("iso", "front", "side", "top") if pose == "home" else ("iso", "head_closeup")))
