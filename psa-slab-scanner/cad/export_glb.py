"""Export the assembly as binary glTF (GLB) for viewing: one named, coloured mesh per part, fasteners merged into one mesh.

Run from the cad/ folder:  python3 export_glb.py              (home and carry poses)
                           python3 export_glb.py station      (any pose in build.POSES)
                           python3 export_glb.py --no-verify  (skip the trimesh check)

Writes cad/out/assembly/slabrail_<pose>.glb. The parts come from build.assembly(pose), the same list the STEP export uses.

Units and axes. The mesh vertices are the CAD coordinates in mm (X along the row, Y front to back, Z up; see README.md).
glTF expects metres and +Y up, so the single root node "slabrail_<pose>" carries a matrix that scales by 0.001 and turns
Z-up into Y-up (CAD -Y, the operator side, faces glTF +Z). Viewers therefore show the machine upright and at real size;
a tool that reads the raw mesh data gets millimetres.

Each part node keeps the part's name, and its glTF "extras" hold kind (printed | purchased | made | slab | wood | foam |
fastener), group (static | carriage | head) and the model note. Colours are the model's RGBA; parts with alpha < 1 (slabs,
the overfill beam) use alphaMode BLEND. Tessellation: 0.25 mm linear, 0.3 rad angular deflection. This file is for looking
at the design; measure on the STEP files.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np

import build

TOL, ANG_TOL = 0.25, 0.3  # mm, rad
DEFAULT_POSES = ("home", "carry")
FASTENER_MESH = "fasteners"
# CAD (mm, Z up) -> glTF (m, Y up): x' = x, y' = z, z' = -y, all x 0.001
ROOT_MATRIX = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float) @ np.diag([0.001, 0.001, 0.001, 1.0])

ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963
FLOAT, USHORT, UINT = 5126, 5123, 5125


def tessellate(shape) -> tuple[np.ndarray, np.ndarray]:
    """Vertices (n, 3) in mm and triangles (m, 3) of every solid/compound in a cq.Workplane. cadquery lists the vertices
    face by face, so no vertex is shared between two B-rep faces."""
    verts, tris, base = [], [], 0
    for v in shape.vals():
        if not hasattr(v, "tessellate"):
            continue
        vs, ts = v.tessellate(TOL, ANG_TOL)
        if not ts:
            continue
        verts.append(np.array([(q.x, q.y, q.z) for q in vs], dtype=np.float64))
        tris.append(np.array(ts, dtype=np.int64) + base)
        base += len(vs)
    if not tris:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return np.vstack(verts), np.vstack(tris)


def vertex_normals(v: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals. Vertices are per B-rep face, so curved faces shade smooth and edges stay sharp."""
    fn = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    n = np.zeros_like(v)
    for k in range(3):
        np.add.at(n, t[:, k], fn)
    ln = np.linalg.norm(n, axis=1)
    bad = ln < 1e-12
    n[bad] = (0.0, 0.0, 1.0)  # vertices of degenerate triangles only
    ln[bad] = 1.0
    return n / ln[:, None]


class _Glb:
    """Minimal glTF 2.0 binary writer: one buffer, float32 positions and normals, uint16/uint32 indices."""

    def __init__(self) -> None:
        self.bin = bytearray()
        self.views: list[dict] = []
        self.accessors: list[dict] = []
        self.materials: list[dict] = []
        self.meshes: list[dict] = []
        self.nodes: list[dict] = []
        self._mat_index: dict[tuple, int] = {}

    def _view(self, data: bytes, target: int) -> int:
        while len(self.bin) % 4:
            self.bin += b"\0"
        self.views.append({"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data), "target": target})
        self.bin += data
        return len(self.views) - 1

    def _accessor(self, view: int, ctype: int, count: int, atype: str, **extra) -> int:
        self.accessors.append({"bufferView": view, "componentType": ctype, "count": count, "type": atype, **extra})
        return len(self.accessors) - 1

    def material(self, rgba: tuple[float, ...], kind: str) -> int:
        key = (kind, tuple(round(c, 4) for c in rgba))
        if key not in self._mat_index:
            r, g, b, a = (float(c) for c in rgba)
            hexc = "".join(f"{round(c * 255):02x}" for c in (r, g, b))
            m = {"name": f"{kind}_{hexc}", "pbrMetallicRoughness": {"baseColorFactor": [r, g, b, a], "metallicFactor": 0.0, "roughnessFactor": 0.6}}
            if a < 1.0:
                m["alphaMode"] = "BLEND"
                m["doubleSided"] = True
            self.materials.append(m)
            self._mat_index[key] = len(self.materials) - 1
        return self._mat_index[key]

    def mesh(self, name: str, v: np.ndarray, t: np.ndarray, material: int) -> int:
        pos = v.astype(np.float32)
        nrm = vertex_normals(v, t).astype(np.float32)
        idx = t.astype(np.uint16 if len(v) < 65536 else np.uint32)
        a_pos = self._accessor(self._view(pos.tobytes(), ARRAY_BUFFER), FLOAT, len(pos), "VEC3",
                               min=[float(c) for c in pos.min(0)], max=[float(c) for c in pos.max(0)])
        a_nrm = self._accessor(self._view(nrm.tobytes(), ARRAY_BUFFER), FLOAT, len(nrm), "VEC3")
        a_idx = self._accessor(self._view(idx.tobytes(), ELEMENT_ARRAY_BUFFER), USHORT if idx.dtype == np.uint16 else UINT, idx.size, "SCALAR")
        self.meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_nrm}, "indices": a_idx, "material": material, "mode": 4}]})
        return len(self.meshes) - 1

    def write(self, path: Path, root_name: str, root_extras: dict) -> None:
        children = list(range(1, len(self.nodes) + 1))
        root = {"name": root_name, "matrix": [float(c) for c in ROOT_MATRIX.T.flatten()], "children": children, "extras": root_extras}
        doc = {
            "asset": {"version": "2.0", "generator": "SlabRail cad/export_glb.py"},
            "scene": 0,
            "scenes": [{"name": root_name, "nodes": [0]}],
            "nodes": [root] + self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "accessors": self.accessors,
            "bufferViews": self.views,
            "buffers": [{"byteLength": len(self.bin)}],
        }
        js = json.dumps(doc, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        bn = bytes(self.bin) + b"\0" * (-len(self.bin) % 4)
        total = 12 + 8 + len(js) + 8 + len(bn)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
            f.write(struct.pack("<II", len(bn), 0x004E4942) + bn)


def export_glb(pose: str) -> tuple[Path, dict]:
    """Write cad/out/assembly/slabrail_<pose>.glb. Returns its path and a summary (meshes, triangles, bbox in mm)."""
    g = _Glb()
    fast_v, fast_t, fast_names, fast_n, fast_color = [], [], [], 0, None
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    tris = 0
    for p in build.assembly(pose):
        v, t = tessellate(p.shape)
        if not len(t):
            continue
        lo, hi = np.minimum(lo, v.min(0)), np.maximum(hi, v.max(0))
        tris += len(t)
        if p.kind == "fastener":
            fast_v.append(v)
            fast_t.append(t + fast_n)
            fast_n += len(v)
            fast_names.append(p.name)
            fast_color = fast_color or p.color
            continue
        mi = g.mesh(p.name, v, t, g.material(p.color, p.kind))
        extras = {"kind": p.kind, "group": p.group}
        if p.note:
            extras["note"] = p.note
        g.nodes.append({"name": p.name, "mesh": mi, "extras": extras})
    if fast_v:
        mi = g.mesh(FASTENER_MESH, np.vstack(fast_v), np.vstack(fast_t), g.material(fast_color, "fastener"))
        g.nodes.append({"name": FASTENER_MESH, "mesh": mi, "extras": {"kind": "fastener", "group": "mixed", "count": len(fast_names), "parts": fast_names}})
    path = build.OUT / "assembly" / f"slabrail_{pose}.glb"
    path.parent.mkdir(parents=True, exist_ok=True)
    extras = {"pose": pose, "source": "cad/build.py assembly(pose)", "mesh_units": "mm, CAD axes (Z up)",
              "root_matrix": "scale 0.001 and Z-up to Y-up, so the scene is in metres, Y up", "tessellation_mm_rad": [TOL, ANG_TOL]}
    g.write(path, f"slabrail_{pose}", extras)
    return path, {"meshes": len(g.meshes), "nodes": len(g.nodes), "fasteners_merged": len(fast_names), "triangles": tris,
                  "bbox_mm": [*lo.round(3).tolist(), *hi.round(3).tolist()], "bytes": path.stat().st_size}


def verify(path: Path, summary: dict, pose: str, tol_mm: float = 0.5) -> list[str]:
    """Reload the GLB with trimesh: mesh count and scene bounds (back in CAD mm) against the STEP file's bounding box."""
    import trimesh
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    import cadquery as cq

    problems = []
    scene = trimesh.load(path, force="scene")
    if len(scene.geometry) != summary["meshes"]:
        problems.append(f"{path.name}: trimesh sees {len(scene.geometry)} meshes, expected {summary['meshes']}")
    corners = np.array([[x, y, z, 1.0] for x in scene.bounds[:, 0] for y in scene.bounds[:, 1] for z in scene.bounds[:, 2]])
    mm = (np.linalg.inv(ROOT_MATRIX) @ corners.T).T[:, :3]
    glb_box = [*mm.min(0), *mm.max(0)]
    step = build.OUT / "assembly" / f"slabrail_{pose}.step"
    if step.exists():
        b = Bnd_Box()
        for s in cq.importers.importStep(str(step)).solids().vals():
            BRepBndLib.AddOptimal_s(s.wrapped, b, False, False)
        step_box = list(b.Get())
        diff = max(abs(a - c) for a, c in zip(glb_box, step_box))
        summary["step_bbox_mm"] = [round(c, 3) for c in step_box]
        summary["max_bbox_diff_mm"] = round(diff, 3)
        if diff > tol_mm:
            problems.append(f"{path.name}: bounds differ from {step.name} by {diff:.3f} mm (> {tol_mm})")
    else:
        problems.append(f"{step.name} missing: run build.py first, bounds not checked")
    summary["glb_bbox_mm"] = [round(c, 3) for c in glb_box]
    return problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("poses", nargs="*", help=f"poses to export (default: {' '.join(DEFAULT_POSES)}; any of {', '.join(build.POSES)})")
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()
    a.poses = a.poses or list(DEFAULT_POSES)
    unknown = [p for p in a.poses if p not in build.POSES]
    if unknown:
        ap.error(f"unknown pose {', '.join(unknown)}; choose from {', '.join(build.POSES)}")
    failed = []
    for pose in a.poses:
        path, s = export_glb(pose)
        if not a.no_verify:
            failed += verify(path, s, pose)
        print(path.name, json.dumps(s))
    if failed:
        raise SystemExit("\n".join(failed))
