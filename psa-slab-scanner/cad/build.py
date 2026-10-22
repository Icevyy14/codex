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

POSES = {
    # name: (cup_x, cup_y, c, held_slab, fill)
    "home": (M.CX_MID, 120.0, L.C_SAFE_EMPTY, False, None),
    "pick_bottom": (L.pockets()[13].x, L.pockets()[13].y, 0.0, False, {13: 1, **{p.index: 25 for p in L.pockets() if p.role == "source" and p.index != 13}}),
    "carry": ((L.pockets()[1].x + L.pockets()[0].x) / 2, L.pockets()[0].y, L.C_SAFE_LOADED, True, None),
    "station": (L.station_xy()[0], L.station_xy()[1], L.STATION_READ_C, True, None),
}

VIEWS = {
    # name: openscad --camera=eye_x,eye_y,eye_z,center_x,center_y,center_z
    "iso": (1350, -1150, 1150, 226, 160, 150),
    "front": (226, -1900, 260, 226, 160, 230),
    "side": (2000, 160, 260, 226, 160, 230),
    "top": (226, 160, 2100, 226, 161, 0),
    "head_closeup": (560, -330, 470, 226, 120, 170),
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
    x, y, c, held, fill = POSES[pose]
    return M.machine(x, y, c, held_slab=held, fill=fill)


def export_assembly(pose: str = "home") -> Path:
    d = OUT / "assembly"
    d.mkdir(parents=True, exist_ok=True)
    assy = cq.Assembly(name=f"slabstack_{pose}")
    for p in assembly(pose):
        assy.add(p.shape, name=p.name, color=cq.Color(*p.color))
    path = d / f"slabstack_{pose}.step"
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
        cam = ",".join(str(n) for n in VIEWS[v])
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
