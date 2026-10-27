"""Tessellate the SlabRail assembly into a compact mesh pack for the 3D viewer page.

Writes model.bin (per mesh: Int16 positions quantised over the model's bounding box, then Uint16/Uint32
indices) and model.json (mesh table + part info). Run from cad/:  python3 export_meshes.py OUT_DIR [pose]
"""

import json
import re
import sys
from pathlib import Path

import cadquery as cq
import numpy as np

import build
import layout as L

OUT = Path(sys.argv[1])
POSE = sys.argv[2] if len(sys.argv) > 2 else "carry"
OUT.mkdir(parents=True, exist_ok=True)

LABELS = {
    "x_beam": "X beam (4040 extrusion)", "upright_L": "Left upright (4040)", "upright_R": "Right upright (4040)",
    "x_rail": "X linear rail (MGN12, 1300 mm)", "x_carriage": "X rail carriage (MGN12H)", "x_motor": "X motor (NEMA 17)",
    "x_pulley": "X drive pulley (GT2 20T)", "x_idler": "X idler pulley", "z_spine": "Z spine (2040 extrusion)",
    "z_rail": "Z linear rail (MGN12, 330 mm)", "z_carriage": "Z rail carriage (MGN12H)", "z_motor": "Z motor (NEMA 17, T8x8 lead screw)",
    "z_leadscrew": "Z lead screw (T8x8, cut to 340 mm)", "drop_arm": "Drop arm (2020 extrusion, 285 mm)", "buffer": "Spring buffer body (M10)",
    "buffer_rod": "Spring buffer rod", "buffer_stop": "Buffer stop nut", "cup": "Vacuum cup (25 mm)", "vac_fitting": "Vacuum fitting (M5)",
    "contact_sensor": "Contact sensor (slotted optical)", "probe_flag": "Probe flag (cut from strip)", "head_camera": "Head camera (USB 8 MP)",
    "station_camera": "Station camera (Pi Camera Module 3)", "gate_beam": "Overfill laser beam", "bed_plywood": "Bed (18 mm plywood)",
    "held_slab": "Slab on the cup", "foot": "Rubber feet", "base_rail": "Base rails (2040)", "rod": "Guide rods (8 mm dowels)",
    "pad": "Pocket pads (EVA + microfiber)", "stack": "Slab stacks", "fastener": "Screws, nuts and bolts", "x_belt": "GT2 belt",
    "station": "Station camera mount (printed)",
    "carry_sensor": "Carry-height sensor (slotted optical)", "carry_flag": "Carry-height flag (cut from sheet)",
    "carry_sensor_mount": "Carry sensor mount", "carry_flag_arm": "Carry flag arm",
    "x_switch_mount": "X home switch mount", "z_switch_mount": "Z top switch mount",
    "x_switch": "X home switch (lever microswitch)", "z_switch": "Z top switch (lever microswitch)",
    "head_ring": "Head LED ring (40 mm)", "station_ring": "Station LED ring (60 mm)",
}


def merge_key(p) -> str:
    n = p.name
    if p.kind == "fastener":
        return "fastener"
    if n in ("held_slab", "held_label"):
        return "held_slab"
    for pre in ("rod_", "pad_", "stack_", "labels_", "foot_", "base_rail", "x_belt"):
        if n.startswith(pre):
            return {"labels_": "stack_"}.get(pre, pre).rstrip("_")
    return n


def category(p, key) -> str:
    if key in ("stack", "held_slab"):
        return "Slabs"
    if key == "fastener":
        return "Fasteners"
    if p.kind == "printed":
        return "3D-printed parts"
    if p.group == "head":
        return "Head (moves up and down)"
    if p.group == "carriage":
        return "Z axis (rides on the X rail)"
    if p.kind in ("wood", "foam") or key in ("rod", "pad"):
        return "Bed and guide rods"
    return "Frame, X axis and electronics"


def tess(shape) -> tuple[np.ndarray, np.ndarray]:
    vals = shape.vals() if hasattr(shape, "vals") else [shape]
    verts, tris, base = [], [], 0
    for v in vals:
        if not hasattr(v, "tessellate"):
            continue
        vs, ts = v.tessellate(0.25, 0.3)
        verts += [(q.x, q.y, q.z) for q in vs]
        tris += [(a + base, b + base, c + base) for a, b, c in ts]
        base += len(vs)
    return np.asarray(verts, np.float64).reshape(-1, 3), np.asarray(tris, np.int64).reshape(-1, 3)


parts = build.assembly(POSE)
_pl = Path(build.OUT) / "printed" / "print_list.json"
print_info = {d["part"]: d for d in json.load(open(_pl))} if _pl.exists() else {}
meshes = {}
for p in parts:
    key = merge_key(p)
    v, t = tess(p.shape)
    if not len(t):
        continue
    m = meshes.setdefault(key, {"v": [], "t": [], "n": 0, "count": 0, "part": p})
    m["t"].append(t + m["n"])
    m["v"].append(v)
    m["n"] += len(v)
    m["count"] += 1

allv = np.vstack([np.vstack(m["v"]) for m in meshes.values()])
lo, hi = allv.min(0), allv.max(0)
scale = (hi - lo) / 65534.0
blob, table = bytearray(), []
for key, m in meshes.items():
    v = np.vstack(m["v"])
    t = np.vstack(m["t"])
    q = np.round((v - lo) / scale - 32767).astype(np.int16)
    off_v = len(blob)
    blob += q.tobytes()
    while len(blob) % 4:
        blob += b"\0"
    idx = t.astype(np.uint16 if m["n"] < 65536 else np.uint32)
    off_i = len(blob)
    blob += idx.tobytes()
    while len(blob) % 4:
        blob += b"\0"
    p = m["part"]
    name = LABELS.get(key) or LABELS.get(re.sub(r"_[LR]$", "", key)) or key.replace("_", " ")
    base = re.sub(r"_[LR]$", "", key)
    info = print_info.get(key) or print_info.get(base) or {}
    if p.kind == "printed":
        side = {"_L": " (left)", "_R": " (right)"}.get(key[-2:], "")
        name = (LABELS.get(key) or base.replace("_", " ")).replace(" (printed)", "")
        name = name[0].upper() + name[1:] + ("" if name.endswith(")") else side)
    name = name[0].upper() + name[1:]
    table.append({
        "key": key, "name": name, "category": category(p, key), "kind": p.kind, "group": p.group, "count": m["count"],
        "color": [round(c, 3) for c in p.color], "note": p.note, "nv": int(m["n"]), "nt": int(len(t)),
        "v": off_v, "i": off_i, "i32": bool(m["n"] >= 65536),
        "print": {k: info.get(k) for k in ("size_mm", "volume_cm3", "note")} if info else None,
    })
(OUT / "model.bin").write_bytes(bytes(blob))
meta = {"pose": POSE, "lo": lo.tolist(), "scale": scale.tolist(), "meshes": table,
        "post_h": L.POST_H, "c_safe_loaded": L.C_SAFE_LOADED}
(OUT / "model.json").write_text(json.dumps(meta, separators=(",", ":")))
print(len(table), "meshes", sum(m["nt"] for m in table), "triangles", len(blob) // 1024, "KB")
