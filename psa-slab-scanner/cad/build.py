"""Export printable parts (STL + STEP), the assembly (STEP), a cut list, and PNG renders.

Run from the cad/ folder:  python build.py            (everything)
                           python build.py --renders  (renders only)
Renders need OpenSCAD + xvfb-run (headless). STL/STEP need only CadQuery.
"""

from __future__ import annotations

import argparse
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
    OUT.mkdir(exist_ok=True)
    rows = ["profile,use,length_mm,qty"] + [f"{a},{b},{c:.0f},{q}" for a, b, c, q in M.cut_list()]
    rows += [f"8mm hardwood dowel,guide rod,{L.POST_H + L.PAD_T + L.ROD_EMBED:.0f},{len(L.rods())}"]
    (OUT / "cut_list.csv").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders", action="store_true")
    a = ap.parse_args()
    if not a.renders:
        print(json.dumps(export_printed(), indent=1))
        write_cut_list()
        for pose in POSES:
            print("assembly", export_assembly(pose))
    for pose in POSES:
        print(render(pose, views=("iso", "front", "side", "top") if pose == "home" else ("iso", "head_closeup")))
