#!/usr/bin/env python3
"""SlabRail drawing set: dimensioned 2D sheets (ANSI B landscape, third-angle projection) generated from the CAD.

Run from the cad/ folder:  python3 drawings.py
Writes  cad/out/drawings/SlabRail_drawings.pdf   every sheet
        cad/out/drawings/png/<sheet>.png         130 dpi previews
        cad/out/drawings/dims.json               every dimension shown: sheet, label, value_mm, source

Where the numbers come from: every dimension is measured here from the model's own shapes (exact bounding boxes,
cylindrical and planar faces, the flag-blank polygon) or read from a named layout.py constant. Tolerances and notes
quote the docs (BUILD_GUIDE); a tolerance no doc states is marked PROPOSED. Views are OpenCascade hidden-line-removed
projections of cad/model.py (assembly poses from build.py, printed parts as exported by build.py).

Self-check (runs at the end, exit code 1 if it fails): the shapes are built again from scratch, every geometry dimension
is re-measured and compared with the number printed on the sheet (0.05 mm), every layout constant is read again, every
dimension line is as long as its value at its view's scale, and every view's axes extent is checked so that one paper
mm is exactly 1/scale model mm.

Hidden-line results are cached in $SLABRAIL_DRAWINGS_CACHE (default: <system temp>/slabrail_hlr_cache), keyed on the
shape's vertices, so a changed part is projected again. Options: --only D-07,D-08 (draw some sheets; dev use).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402
from OCP.BRep import BRep_Tool  # noqa: E402
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface  # noqa: E402
from OCP.BRepBndLib import BRepBndLib  # noqa: E402
from OCP.BRepClass3d import BRepClass3d_SolidClassifier  # noqa: E402
from OCP.BRepGProp import BRepGProp, BRepGProp_Face  # noqa: E402
from OCP.BRepLib import BRepLib  # noqa: E402
from OCP.Bnd import Bnd_Box  # noqa: E402
from OCP.GCPnts import GCPnts_QuasiUniformDeflection  # noqa: E402
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_Plane  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec  # noqa: E402
from OCP.GProp import GProp_GProps  # noqa: E402
from OCP.HLRAlgo import HLRAlgo_Projector  # noqa: E402
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape  # noqa: E402
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_VERTEX  # noqa: E402
from OCP.TopExp import TopExp_Explorer  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402

import cadquery as cq  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build as B  # noqa: E402
import layout as L  # noqa: E402
import model as M  # noqa: E402

OUT = HERE / "out" / "drawings"
REPO = HERE.parent
CACHE = Path(os.environ.get("SLABRAIL_DRAWINGS_CACHE") or Path(tempfile.gettempdir()) / "slabrail_hlr_cache")
CACHE_VERSION = "hlr-v3"

# ---------------------------------------------------------------------------------------------------------------- page
PW, PH = 17 * 25.4, 11 * 25.4  # ANSI B landscape, mm
FR = 10.0  # drawing frame inset
TB_X0, TB_Y0, TB_W, TB_H = PW - FR - 250.0, FR, 250.0, 40.0  # title block, bottom right
TOP = PH - FR  # frame top
FS = 10.0  # body text, pt: cap height 0.716 em of Liberation Sans = 2.53 mm (>= 2.5 mm on ANSI B)
FS_DIM = 10.0
PT = 25.4 / 72  # mm per point
LW_VIS, LW_THIN, LW_HID = 0.9, 0.5, 0.45  # pt (0.32, 0.18, 0.16 mm)
LW_ASM = 0.55
INK, GREY, HIDDEN = "#000000", "#555555", "#666666"
DATE = "2026-10-27"
PROJECT = "SlabRail - graded-slab batch scanner"
REV = "Rev A - DRAFT FOR DESIGN REVIEW, not released for fabrication"

matplotlib.rcParams.update({
    "font.family": ["Liberation Sans", "DejaVu Sans"], "pdf.fonttype": 42, "lines.scale_dashes": False,
    "lines.solid_capstyle": "round", "lines.dash_capstyle": "butt", "savefig.dpi": 130, "figure.dpi": 100,
})
DASH_HID = (0, (5.0, 2.5))
DASH_CTR = (0, (14.0, 3.0, 2.5, 3.0))
DASH_PHANTOM = (0, (14.0, 3.0, 2.5, 3.0, 2.5, 3.0))


def git_hash() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# ------------------------------------------------------------------------------------------------------------- scales
@dataclass(frozen=True)
class Scale:
    num: int  # paper
    den: int  # model

    @property
    def k(self) -> float:  # model mm per paper mm
        return self.den / self.num

    def __str__(self) -> str:
        return f"{self.num}:{self.den}"


S51, S21, S11, S12, S15, S110 = Scale(5, 1), Scale(2, 1), Scale(1, 1), Scale(1, 2), Scale(1, 5), Scale(1, 10)
STD_SCALES = [S51, S21, S11, S12, S15, S110]

# ------------------------------------------------------------------------------------------------- geometry helpers


def _wrapped(s):
    if isinstance(s, cq.Workplane):
        vals = [v.wrapped for v in s.vals() if hasattr(v, "wrapped")]
        return vals[0] if len(vals) == 1 else cq.Compound.makeCompound([cq.Shape.cast(v) for v in vals]).wrapped
    if isinstance(s, cq.Shape):
        return s.wrapped
    return s


def compound(shapes):
    shapes = [_wrapped(s) for s in shapes]
    return shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound([cq.Shape.cast(s) for s in shapes]).wrapped


def bbox(shape) -> tuple[float, float, float, float, float, float]:
    """Exact bounding box (no triangulation, no tolerance): xmin, ymin, zmin, xmax, ymax, zmax."""
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(_wrapped(shape), b, False, False)
    return b.Get()


AX = {"x": 0, "y": 1, "z": 2}


def bb_value(shape, which: str) -> float:
    b = bbox(shape)
    a = AX[which[0]]
    lo, hi = b[a], b[a + 3]
    return {"min": lo, "max": hi, "len": hi - lo, "mid": (lo + hi) / 2}[which[1:]]


def _faces(shape):
    exp = TopExp_Explorer(_wrapped(shape), TopAbs_FACE)
    while exp.More():
        yield TopoDS.Face_s(exp.Current())
        exp.Next()


def cyl_features(shape) -> list[dict]:
    """Axis-aligned cylindrical faces, merged per axis line and diameter: axis, d, c (the two other coordinates of the axis
    line, in x/y/z order), lo/hi (extent along the axis), span (total angle, 2 pi = full), hole (material outside)."""
    feats: dict = {}
    for f in _faces(shape):
        s = BRepAdaptor_Surface(f, True)
        if s.GetType() != GeomAbs_Cylinder:
            continue
        cy = s.Cylinder()
        ax = cy.Axis()
        d, o = ax.Direction(), ax.Location()
        dv = np.array([d.X(), d.Y(), d.Z()])
        k = int(np.argmax(np.abs(dv)))
        if abs(abs(dv[k]) - 1) > 1e-6:
            continue
        u0, u1, v0, v1 = s.FirstUParameter(), s.LastUParameter(), s.FirstVParameter(), s.LastVParameter()
        ov = np.array([o.X(), o.Y(), o.Z()])
        a0, a1 = ov[k] + dv[k] * v0, ov[k] + dv[k] * v1
        oth = [i for i in range(3) if i != k]
        pnt, vec = gp_Pnt(), gp_Vec()
        BRepGProp_Face(f).Normal((u0 + u1) / 2, (v0 + v1) / 2, pnt, vec)
        rad = np.array([pnt.X(), pnt.Y(), pnt.Z()]) - ov
        rad[k] = 0.0
        hole = float(np.dot(rad, [vec.X(), vec.Y(), vec.Z()])) < 0
        dia = 2 * cy.Radius()
        key = ("xyz"[k], round(dia, 3), round(ov[oth[0]], 3), round(ov[oth[1]], 3), hole)
        g = feats.setdefault(key, {"axis": "xyz"[k], "d": dia, "c": (ov[oth[0]], ov[oth[1]]), "lo": 1e18, "hi": -1e18, "span": 0.0, "hole": hole})
        g["lo"], g["hi"] = min(g["lo"], a0, a1), max(g["hi"], a0, a1)
        g["span"] += abs(u1 - u0)
    return list(feats.values())


def plane_faces(shape) -> list[dict]:
    """Planar faces with an axis-aligned normal: axis, coord (position along it), box (face bounding box), area."""
    out = []
    for f in _faces(shape):
        s = BRepAdaptor_Surface(f, True)
        if s.GetType() != GeomAbs_Plane:
            continue
        n = s.Plane().Axis().Direction()
        nv = np.array([n.X(), n.Y(), n.Z()])
        k = int(np.argmax(np.abs(nv)))
        if abs(abs(nv[k]) - 1) > 1e-6:
            continue
        b = bbox(f)
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        out.append({"axis": "xyz"[k], "coord": (b[k] + b[k + 3]) / 2, "box": b, "area": g.Mass()})
    return out


def is_inside(solid, p) -> bool:
    c = BRepClass3d_SolidClassifier(_wrapped(solid), gp_Pnt(*map(float, p)), 1e-6)
    return c.State() == TopAbs_IN


def hole_depth(solid, f: dict) -> float | None:
    """None if the hole is open at both ends (THRU), else its depth (the cylinder's length)."""
    k = AX[f["axis"]]
    oth = [i for i in range(3) if i != k]
    r = f["d"] / 2 * 0.85
    closed = 0
    for end, sgn in ((f["lo"], -1), (f["hi"], 1)):
        votes = 0
        for ang in (0.3, 1.9, 3.5, 5.1):
            p = [0.0, 0.0, 0.0]
            p[k] = end + sgn * 0.3
            p[oth[0]] = f["c"][0] + r * math.cos(ang)
            p[oth[1]] = f["c"][1] + r * math.sin(ang)
            votes += is_inside(solid, p)
        closed += votes >= 2
    return None if closed == 0 else f["hi"] - f["lo"]


def _rot(p, axis: str | None, deg: float):
    if axis is None or deg == 0:
        return np.array(p, dtype=float)
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = p
    if axis == "x":
        return np.array([x, c * y - s * z, s * y + c * z])
    if axis == "y":
        return np.array([c * x + s * z, y, -s * x + c * z])
    return np.array([c * x - s * y, s * x + c * y, z])


# Print orientation of each printed part, as model.printed_catalog() makes it from the part's local builder (checked).
PRINTED_LOCAL = {
    "station_mount": (M.station_mount, None, 0), "x_motor_mount": (M.x_motor_mount, "x", -90), "x_bumper_L": (M.x_bumper, "x", -90),
    "x_idler_mount": (M.x_idler_mount, None, 0), "x_idler_slider": (M.x_idler_slider, None, 0), "x_bracket": (M.x_bracket, "x", 90),
    "belt_clamp": (M.belt_clamp, None, 0), "z_motor_mount": (M.z_motor_mount, "x", 180), "z_end_cap": (M.z_end_cap, None, 0),
    "z_plate": (M.z_plate, "x", -90), "head_foot": (lambda: M.head_foot(L.ARM_TO_CUP), None, 0),
    "camera_bracket": (lambda: M.camera_bracket(L.ARM_TO_CUP), "x", 180), "gate_post_L": (lambda: M.gate_post("L"), None, 0),
    "gate_post_R": (lambda: M.gate_post("R"), None, 0), "drill_template": (M.drill_template, None, 0), "phase0_base": (M.phase0_base, None, 0),
    "phase0_tray": (M.phase0_tray, None, 0), "phase0_top": (M.phase0_top, "x", 180), "phase0_occluder_mount": (M.phase0_occluder_mount, None, 0),
    "carry_sensor_mount": (M.carry_sensor_mount, "y", 90), "carry_flag_arm": (M.carry_flag_arm, None, 0), "x_switch_mount": (M.x_switch_mount, "x", -90),
    "z_switch_mount": (M.z_switch_mount, "y", -90), "awl_adapter": (M.awl_adapter, None, 0), "fill_gauge": (M.fill_gauge, "x", 90),
}


class Geo:
    """The model's shapes by key, built on demand: 'asm/<pose>/<part>' (build.assembly), 'p0/<part>' (model.phase0_parts),
    'xdet/<cup_x>/<part>' (frame + carriage at a given cup X, c = C_SAFE_LOADED), 'printed/<part>' (as build.py exports it:
    print orientation, bounding-box minimum at the origin), 'local/<name>' (single model.py shapes in their own frame).
    One instance draws; the self-check builds a fresh one."""

    def __init__(self):
        self._parts: dict = {}
        self._printed: dict | None = None
        self._local: dict = {}
        self._feat: dict = {}
        self._planes: dict = {}

    def parts(self, src: str) -> dict:
        if src not in self._parts:
            if src.startswith("asm:"):
                lst = B.assembly(src[4:])
            elif src == "p0":
                lst = M.phase0_parts()
            elif src.startswith("xdet:"):
                x = float(src[5:])
                lst = M.frame_parts(x) + M.carriage_parts(x, L.C_SAFE_LOADED)
            else:
                raise KeyError(src)
            self._parts[src] = {p.name: p for p in lst}
        return self._parts[src]

    def printed(self) -> dict:
        if self._printed is None:
            d = {}
            for name, wp, qty, note in M.printed_catalog():
                bb = wp.val().BoundingBox()
                placed = wp.translate((-bb.xmin, -bb.ymin, -bb.zmin))  # as build.export_printed
                d[name] = {"shape": placed.val().wrapped, "qty": qty, "note": note, "off": np.array([bb.xmin, bb.ymin, bb.zmin])}
            self._printed = d
        return self._printed

    def local(self, name: str):
        if name not in self._local:
            fns = {"probe_flag": M.probe_flag, "carry_flag": M.carry_flag}
            self._local[name] = _wrapped(fns[name]())
        return self._local[name]

    def shape(self, key: str):
        kind, rest = key.split("/", 1)
        if kind == "asm":
            pose, name = rest.split("/", 1)
            return _wrapped(self.parts("asm:" + pose)[name].shape)
        if kind == "p0":
            return _wrapped(self.parts("p0")[rest].shape)
        if kind == "xdet":
            x, name = rest.split("/", 1)
            return _wrapped(self.parts("xdet:" + x)[name].shape)
        if kind == "printed":
            return self.printed()[rest]["shape"]
        if kind == "local":
            return self.local(rest)
        raise KeyError(key)

    def to_print(self, name: str, p) -> np.ndarray:
        """A point in the printed part's model.py frame -> the exported print frame."""
        _, ax, deg = PRINTED_LOCAL[name]
        return _rot(p, ax, deg) - self.printed()[name]["off"]

    def frame_point(self, key: str, p) -> np.ndarray:
        if key.startswith("printed/"):
            return self.to_print(key.split("/", 1)[1], p)
        return np.array(p, dtype=float)

    def feats(self, key: str) -> list[dict]:
        if key not in self._feat:
            self._feat[key] = cyl_features(self.shape(key))
        return self._feat[key]

    def planes(self, key: str) -> list[dict]:
        if key not in self._planes:
            self._planes[key] = plane_faces(self.shape(key))
        return self._planes[key]


def find_cyl(geo: Geo, key: str, axis: str, d: float, near, hole: bool = True) -> dict:
    p = geo.frame_point(key, near)
    k = AX[axis]
    oth = [i for i in range(3) if i != k]
    best, bd = None, 1e18
    for f in geo.feats(key):
        if f["axis"] != axis or f["hole"] != hole or abs(f["d"] - d) > max(0.25, 0.02 * d):
            continue
        dist = math.hypot(p[oth[0]] - f["c"][0], p[oth[1]] - f["c"][1]) + max(0.0, f["lo"] - p[k], p[k] - f["hi"])
        if dist < bd:
            best, bd = f, dist
    if best is None:
        raise LookupError(f"no {'hole' if hole else 'boss'} d~{d} along {axis} in {key}")
    return best


def find_plane(geo: Geo, key: str, axis: str, near) -> dict:
    p = geo.frame_point(key, near)
    best, bd = None, 1e18
    for f in geo.planes(key):
        if f["axis"] != axis:
            continue
        b = f["box"]
        dist = math.sqrt(sum(max(b[i] - p[i], 0.0, p[i] - b[i + 3]) ** 2 for i in range(3)))
        if dist < bd - 1e-9:
            best, bd = f, dist
    if best is None:
        raise LookupError(f"no plane normal to {axis} in {key}")
    return best


def holes_of(geo: Geo, key: str, axis: str, d: float) -> list[dict]:
    return [f for f in geo.feats(key) if f["axis"] == axis and f["hole"] and abs(f["d"] - d) <= max(0.05, 0.005 * d) and f["span"] > 6.2]


def measure(geo: Geo, spec) -> float:
    """Evaluate a measurement spec on geo's shapes (see MEASURES)."""
    fn, *a = spec
    return MEASURES[fn](geo, *a)


def _m_bb(geo, key, which):
    return bb_value(geo.shape(key), which)


def _m_bbu(geo, keys, which):
    return bb_value(compound([geo.shape(k) for k in keys]), which)


def _m_cyl(geo, key, axis, d, near, what, hole=True):
    f = find_cyl(geo, key, axis, d, near, hole)
    if what == "d":
        return f["d"]
    if what in ("lo", "hi"):
        return f[what]
    if what == "len":
        return f["hi"] - f["lo"]
    oth = [c for c in "xyz" if c != axis]
    return f["c"][oth.index(what)]


def _m_plane(geo, key, axis, near):
    return find_plane(geo, key, axis, near)["coord"]


def _m_pat(geo, key, axis, d, what):
    hs = holes_of(geo, key, axis, d)
    if what == "n":
        return float(len(hs))
    oth = [c for c in "xyz" if c != axis]
    vals = [h["c"][oth.index(what)] for h in hs]
    return max(vals) - min(vals)


def _m_sub(geo, a, b):
    return measure(geo, a) - measure(geo, b)


def _m_add(geo, a, b):
    return measure(geo, a) + measure(geo, b)


def _m_mul(geo, a, f):
    return measure(geo, a) * f


def _m_flag(geo, what):
    pts = M.flag_blank()
    us, vs = [u for u, _ in pts], [v for _, v in pts]
    if what in ("umin", "umax", "vmin", "vmax"):
        return {"umin": min(us), "umax": max(us), "vmin": min(vs), "vmax": max(vs)}[what]
    i, c = what  # point index, 'u' | 'v'
    return pts[i][0 if c == "u" else 1]


def _m_layout(geo, name):
    return float(getattr(L, name))


def _m_count(geo, src, prefix):
    return float(sum(1 for n in geo.parts(src) if n.startswith(prefix)))


MEASURES = {"bb": _m_bb, "bbu": _m_bbu, "cyl": _m_cyl, "plane": _m_plane, "pat": _m_pat, "sub": _m_sub, "add": _m_add,
            "mul": _m_mul, "flag": _m_flag, "layout": _m_layout, "count": _m_count}

# ------------------------------------------------------------------------------------------------ hidden-line removal
VIEWDIR = {  # name: (direction toward the viewer, page x direction); page y = dir x xdir
    "front": ((0, -1, 0), (1, 0, 0)), "top": ((0, 0, 1), (1, 0, 0)), "right": ((1, 0, 0), (0, 1, 0)),
    "left": ((-1, 0, 0), (0, -1, 0)), "rear": ((0, 1, 0), (-1, 0, 0)), "bottom": ((0, 0, -1), (1, 0, 0)),
}


def proj(view: str, p) -> tuple[float, float]:
    n, xd = (np.array(v, dtype=float) for v in VIEWDIR[view])
    yd = np.cross(n, xd)
    p = np.asarray(p, dtype=float)
    return float(p @ xd), float(p @ yd)


def proj_box(view: str, b) -> tuple[float, float, float, float]:
    xs = [b[0], b[3]]
    ys = [b[1], b[4]]
    zs = [b[2], b[5]]
    pts = [proj(view, (x, y, z)) for x in xs for y in ys for z in zs]
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    return min(us), min(vs), max(us), max(vs)


def fingerprint(shape) -> str:
    exp = TopExp_Explorer(_wrapped(shape), TopAbs_VERTEX)
    pts = []
    while exp.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(exp.Current()))
        pts.append((round(p.X(), 4), round(p.Y(), 4), round(p.Z(), 4)))
        exp.Next()
    pts.sort()
    nf = sum(1 for _ in _faces(shape))
    return hashlib.sha1((repr(pts) + f"|{nf}").encode()).hexdigest()


def _polylines(comp, defl: float) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    if comp is None or comp.IsNull():
        return out
    BRepLib.BuildCurves3d_s(comp, 1e-6)
    exp = TopExp_Explorer(comp, TopAbs_EDGE)
    while exp.More():
        e = TopoDS.Edge_s(exp.Current())
        exp.Next()
        try:
            c = BRepAdaptor_Curve(e)
        except Exception:  # noqa: BLE001 - an edge without a curve
            continue
        if c.GetType() == GeomAbs_Line:
            a, b = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
            pts = [(a.X(), a.Y()), (b.X(), b.Y())]
        else:
            q = GCPnts_QuasiUniformDeflection(c, defl)
            if not q.IsDone() or q.NbPoints() < 2:
                continue
            pts = [(q.Value(i).X(), q.Value(i).Y()) for i in range(1, q.NbPoints() + 1)]
        out.append(np.array(pts, dtype=np.float64))
    return out


HLR_STATS = {"computed": 0, "cached": 0, "seconds": 0.0}


def hlr(shape, view: str, defl: float) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """(visible, hidden) polylines of shape projected in view, page coordinates (model mm)."""
    shape = _wrapped(shape)
    key = hashlib.sha1(f"{CACHE_VERSION}|{fingerprint(shape)}|{view}|{defl:.4f}".encode()).hexdigest()
    path = CACHE / f"{key}.pkl"
    if path.exists():
        try:
            HLR_STATS["cached"] += 1
            return pickle.loads(path.read_bytes())
        except (OSError, pickle.UnpicklingError, EOFError):
            pass
    t0 = time.time()
    algo = HLRBRep_Algo()
    algo.Add(shape, 0)
    n, xd = VIEWDIR[view]
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*n), gp_Dir(*xd))))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    vis = _polylines(h.VCompound(), defl) + _polylines(h.OutLineVCompound(), defl)
    hid = _polylines(h.HCompound(), defl) + _polylines(h.OutLineHCompound(), defl)
    res = (vis, hid)
    HLR_STATS["computed"] += 1
    HLR_STATS["seconds"] += time.time() - t0
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(res))
    except OSError:
        pass
    return res


# -------------------------------------------------------------------------------------------------- dimension records
def fmt(v: float) -> str:
    if abs(v - round(v)) < 0.005:
        s = f"{round(v):d}"
    elif abs(v - round(v, 1)) < 0.005:
        s = f"{v:.1f}"
    else:
        s = f"{v:.2f}"
    return "0" if s in ("-0", "-0.0") else s


@dataclass
class Rec:
    sheet: str
    label: str
    value: float
    source: str
    text: str
    spec: tuple
    unit: str = "mm"
    artist: object = None
    p1: tuple | None = None
    p2: tuple | None = None
    axis: str | None = None
    view: object = None
    factor: float = 1.0  # drawn length = value * factor (e.g. radius drawn for a diameter: not used for lengths)


class Registry:
    def __init__(self, geo: Geo):
        self.geo = geo
        self.recs: list[Rec] = []
        self.sheet = ""

    def g(self, label: str, spec, src: str, unit: str = "mm") -> Rec:
        """A geometry measurement."""
        v = measure(self.geo, spec)
        r = Rec(self.sheet, label, v, "geometry:" + src, fmt(v), spec, unit)
        self.recs.append(r)
        return r

    def c(self, name: str, label: str | None = None, unit: str = "mm") -> Rec:
        """A layout.py constant."""
        v = float(getattr(L, name))
        r = Rec(self.sheet, label or name, v, f"layout.{name}", fmt(v), ("layout", name), unit)
        self.recs.append(r)
        return r


REG: Registry  # set in main()


def G(label, spec, src, unit="mm") -> Rec:
    return REG.g(label, spec, src, unit)


def C(name, label=None, unit="mm") -> Rec:
    return REG.c(name, label, unit)


def tw(s: str, size: float = FS) -> float:
    """Estimated text width, paper mm (Liberation Sans: ~0.53 em average; digits 0.556 em)."""
    return len(s) * 0.54 * size * PT


def th(size: float = FS) -> float:
    return size * PT * 1.0


# ------------------------------------------------------------------------------------------------------------ sheet
class Sheet:
    def __init__(self, num: str, title: str, total: str, src_hash: str):
        self.num, self.title, self.total, self.hash = num, title, total, src_hash
        self.fig = plt.figure(figsize=(PW / 25.4, PH / 25.4))
        self.pg = self.fig.add_axes((0, 0, 1, 1))
        self.pg.set_xlim(0, PW)
        self.pg.set_ylim(0, PH)
        self.pg.set_autoscale_on(False)
        self.pg.axis("off")
        self.views: list[View] = []
        self.occ: list[tuple[float, float, float, float]] = []  # paper rects used (balloon placement)
        self.scales: list[Scale] = []
        self.images: list = []
        self.segs: list[tuple[int, np.ndarray]] = []  # (owner, paper polyline) for the layout check
        self._owner = 0

    def owner(self) -> int:
        self._owner += 1
        return self._owner

    # ---- primitives in paper mm
    def text(self, x, y, s, size=FS, ha="left", va="baseline", weight="normal", color=INK, rot=0, owner=0, occ=True, **kw):
        t = self.pg.text(x, y, s, fontsize=size, ha=ha, va=va, fontweight=weight, color=color, rotation=rot, clip_on=False, **kw)
        t._owner = owner  # noqa: SLF001
        if occ:
            w, h = tw(s.split("\n")[0], size) if "\n" not in s else max(tw(q, size) for q in s.split("\n")), th(size) * (1 + 1.25 * s.count("\n"))
            x0 = x - (w / 2 if ha == "center" else (w if ha == "right" else 0))
            y0 = y - (h / 2 if va == "center" else (h if va == "top" else 0.25 * th(size)))
            self.occ.append((x0, y0, x0 + w, y0 + h))
        return t

    def line(self, pts, lw=LW_THIN, color=INK, ls="-", owner=0, track=True):
        pts = np.asarray(pts, dtype=float)
        self.pg.plot(pts[:, 0], pts[:, 1], lw=lw, color=color, ls=ls, clip_on=False, solid_capstyle="butt")
        if track:
            self.segs.append((owner, pts))

    def rect(self, x0, y0, x1, y1, lw=LW_THIN, color=INK, fill=None, ls="-"):
        self.pg.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=fill is not None, facecolor=fill or "none", edgecolor=color, lw=lw, ls=ls, clip_on=False))

    def frame(self):
        self.rect(FR, FR, PW - FR, PH - FR, lw=1.4)
        self.rect(3, 3, PW - 3, PH - 3, lw=0.4, color=GREY)
        ncol, nrow = 8, 4
        cw, rh = (PW - 2 * FR) / ncol, (PH - 2 * FR) / nrow
        for i in range(ncol + 1):
            x = FR + i * cw
            for y0, y1 in ((3, FR), (PH - FR, PH - 3)):
                self.line([(x, y0), (x, y1)], lw=0.4, track=False)
        for j in range(nrow + 1):
            y = FR + j * rh
            for x0, x1 in ((3, FR), (PW - FR, PW - 3)):
                self.line([(x0, y), (x1, y)], lw=0.4, track=False)
        for i in range(ncol):
            for y in (FR / 2 + 1.5, PH - FR / 2 - 1.5):
                self.pg.text(FR + (i + 0.5) * cw, y, str(ncol - i), fontsize=FS, ha="center", va="center", clip_on=False)
        for j in range(nrow):
            for x in (FR / 2 + 1.5, PW - FR / 2 - 1.5):
                self.pg.text(x, FR + (j + 0.5) * rh, "ABCD"[j], fontsize=FS, ha="center", va="center", clip_on=False)

    def third_angle_symbol(self, x, y, s=1.0):
        """Third-angle projection symbol, lower-left at (x, y): the frustum's side view (large end left), then its end view
        seen from the small end (two circles) to the right."""
        D, d, ln = 7.0 * s, 3.8 * s, 8.0 * s
        cy = y + D / 2
        self.line([(x, cy - D / 2), (x + ln, cy - d / 2), (x + ln, cy + d / 2), (x, cy + D / 2), (x, cy - D / 2)], lw=0.8, track=False)
        cx = x + ln + 4.0 * s + D / 2
        for r in (D / 2, d / 2):
            self.pg.add_patch(Circle((cx, cy), r, fill=False, lw=0.8, clip_on=False))
        self.line([(x - 1.5 * s, cy), (x + ln + 1.5 * s, cy)], lw=0.35, ls=DASH_CTR, track=False)
        self.line([(cx - D / 2 - 1.5 * s, cy), (cx + D / 2 + 1.5 * s, cy)], lw=0.35, ls=DASH_CTR, track=False)
        self.line([(cx, cy - D / 2 - 1.5 * s), (cx, cy + D / 2 + 1.5 * s)], lw=0.35, ls=DASH_CTR, track=False)

    def title_block(self, scale_text: str):
        x0, y0, w, h = TB_X0, TB_Y0, TB_W, TB_H
        x1, y1 = x0 + w, y0 + h
        self.rect(x0, y0, x1, y1, lw=1.2)
        rh = h / 4
        xs = x0 + 160.0
        for j in range(1, 4):
            self.line([(x0, y0 + j * rh), (x1, y0 + j * rh)], lw=0.6, track=False)
        self.line([(xs, y0), (xs, y1)], lw=0.6, track=False)
        cy = lambda j: y0 + (3.5 - j) * rh  # noqa: E731
        self.text(x0 + 2.5, cy(0), PROJECT, size=12, va="center", weight="bold", occ=False)
        self.text(xs + 2.5, cy(0), f"SHEET {self.num} of {self.total}", size=12, va="center", weight="bold", occ=False)
        self.text(x0 + 2.5, cy(1), self.title, size=11.5, va="center", weight="bold", occ=False)
        self.text(xs + 2.5, cy(1), f"SCALE {scale_text}", size=FS, va="center", occ=False)
        self.text(xs + 2.5, cy(2), "UNITS: mm", size=FS, va="center", occ=False)
        self.text(xs + 26.0, cy(2), "3RD ANGLE", size=FS, va="center", occ=False)
        self.third_angle_symbol(xs + 52.0, y0 + rh + 1.5, s=0.95)
        self.text(x0 + 2.5, cy(2), REV, size=FS, va="center", occ=False)
        self.text(x0 + 2.5, cy(3), f"SOURCE: cad/model.py @ {self.hash}   (drawn by cad/drawings.py)", size=FS, va="center", occ=False)
        self.text(xs + 2.5, cy(3), f"DATE {DATE}", size=FS, va="center", occ=False)
        self.text(x1 - 2.5, cy(3), "DO NOT SCALE", size=FS, va="center", ha="right", weight="bold", occ=False)

    def image(self, path: Path, x, y, w, label: str | None = None):
        import matplotlib.image as mpimg

        im = mpimg.imread(str(path))
        h = w * im.shape[0] / im.shape[1]
        ax = self.fig.add_axes((x / PW, y / PH, w / PW, h / PH))
        ax.imshow(im, interpolation="lanczos")
        ax.axis("off")
        self.images.append((x, y, x + w, y + h))
        self.occ.append((x, y, x + w, y + h))
        self.rect(x, y, x + w, y + h, lw=0.5, color=GREY)
        if label:
            self.text(x, y + h + 2.0, label, weight="bold")
        return h

    def wrap(self, x, y, s, width_mm, size=FS, lh=1.3, **kw) -> float:
        """Wrapped paragraph from (x, y) down; returns the y under it."""
        chars = max(10, int(width_mm / (0.53 * size * PT)))
        lines = []
        for para in s.split("\n"):
            lines += textwrap.wrap(para, chars, subsequent_indent=kw.pop("indent", "")) or [""]
        for i, ln in enumerate(lines):
            self.text(x, y - i * size * PT * lh, ln, size=size, va="top", **kw)
        return y - len(lines) * size * PT * lh

    def table(self, x, y, rows, widths, size=FS, lh=1.35, header=True, wrap_cols=None, bold_first=False):
        """Ruled table from its top-left corner; rows of strings; returns the bottom y. Cells wrap to their width."""
        rh = size * PT * lh
        yy = y
        cells_out = []
        for ri, row in enumerate(rows):
            wrapped = []
            for ci, cell in enumerate(row):
                chars = max(4, int((widths[ci] - 2.4) / (0.53 * size * PT)))
                wrapped.append(textwrap.wrap(str(cell), chars) or [""])
            n = max(len(w) for w in wrapped)
            h = n * rh + 1.2
            xx = x
            for ci, w in enumerate(wrapped):
                for li, ln in enumerate(w):
                    t = self.text(xx + 1.2, yy - 0.9 - li * rh, ln, size=size, va="top",
                                  weight="bold" if (header and ri == 0) or (bold_first and ci == 0) else "normal")
                    cells_out.append((ri, ci, t))
                xx += widths[ci]
            self.line([(x, yy - h), (x + sum(widths), yy - h)], lw=0.35, track=False)
            yy -= h
        self.rect(x, yy, x + sum(widths), y, lw=0.6)
        xx = x
        for wd in widths[:-1]:
            xx += wd
            self.line([(xx, yy), (xx, y)], lw=0.35, track=False)
        self.occ.append((x, yy, x + sum(widths), y))
        return yy, cells_out


# ------------------------------------------------------------------------------------------------------------- view
class View:
    """An orthographic view: an axes whose extent is set in model mm so that one paper mm is exactly scale.k model mm."""

    def __init__(self, sheet: Sheet, name: str, window, scale: Scale, x: float, y: float, label: str | None = None):
        self.sheet, self.name, self.scale = sheet, name, scale
        self.u0, self.v0, self.u1, self.v1 = window
        self.k = scale.k
        self.x, self.y = x, y
        self.w, self.h = (self.u1 - self.u0) / self.k, (self.v1 - self.v0) / self.k
        self.ax = sheet.fig.add_axes((x / PW, y / PH, self.w / PW, self.h / PH))
        self.ax.set_xlim(self.u0, self.u1)
        self.ax.set_ylim(self.v0, self.v1)
        self.ax.set_aspect("auto")
        self.ax.set_autoscale_on(False)
        self.ax.axis("off")
        sheet.views.append(self)
        if scale not in sheet.scales:
            sheet.scales.append(scale)
        sheet.occ.append((x, y, x + self.w, y + self.h))
        if label:
            self.label(label)

    def label(self, s: str, where="above", dy=2.5):
        if where == "above":
            self.sheet.text(self.x, self.y + self.h + dy, s, weight="bold")
        else:
            self.sheet.text(self.x + self.w / 2, self.y - dy, s, weight="bold", ha="center", va="top")

    def P(self, u, v):
        return self.x + (u - self.u0) / self.k, self.y + (v - self.v0) / self.k

    def Mdl(self, x, y):
        return self.u0 + (x - self.x) * self.k, self.v0 + (y - self.v0 * 0 - self.y) * self.k

    def polys(self, polys, lw=LW_VIS, color=INK, ls="-", track=True):
        if not polys:
            return
        lc = LineCollection([p for p in polys], linewidths=lw, colors=color, linestyles=ls, clip_on=False, capstyle="round")
        self.ax.add_collection(lc)
        if track:
            for p in polys:
                pp = np.column_stack([self.x + (p[:, 0] - self.u0) / self.k, self.y + (p[:, 1] - self.v0) / self.k])
                self.sheet.segs.append((-1, pp))

    def seg(self, a, b, lw=LW_THIN, color=INK, ls="-", owner=0):
        self.ax.plot([a[0], b[0]], [a[1], b[1]], lw=lw, color=color, ls=ls, clip_on=False, solid_capstyle="butt")
        self.sheet.segs.append((owner, np.array([self.P(*a), self.P(*b)])))

    def text(self, u, v, s, size=FS, ha="center", va="baseline", rot=0, owner=0, weight="normal", color=INK):
        x, y = self.P(u, v)
        return self.sheet.text(x, y, s, size=size, ha=ha, va=va, rot=rot, owner=owner, weight=weight, color=color)

    def arrow(self, tip, direction, owner=0, length=2.6, half=0.5):
        """Filled arrowhead at tip (model), pointing along direction (unit, page)."""
        dx, dy = direction
        tx, ty = self.P(*tip)
        bx, by = tx - dx * length, ty - dy * length
        px, py = -dy * half, dx * half
        pts = [(tx, ty), (bx + px, by + py), (bx - px, by - py)]
        self.sheet.pg.add_patch(Polygon(pts, closed=True, facecolor=INK, edgecolor=INK, lw=0.2, clip_on=False))

    def centerline(self, a, b, lw=0.4):
        self.seg(a, b, lw=lw, ls=DASH_CTR, color=INK, owner=-2)

    def cmark(self, u, v, r_model, ext=2.0):
        """Centre mark: cross extending ext paper mm past the circle."""
        e = r_model + ext * self.k
        self.centerline((u - e, v), (u + e, v))
        self.centerline((u, v - e), (u, v + e))

    # ---- dimensions
    def dim(self, p1, p2, axis: str, off: float, rec: Rec, pre: str = "", post: str = "", text_at: str | None = None, flip_text=False):
        """Linear dimension between model points p1, p2 measured along axis 'h' (page x) or 'v' (page y). The dimension line
        sits off paper mm beyond the outermost point (sign = side). The value printed is rec.text."""
        k = self.k
        own = self.sheet.owner()
        (u1, v1), (u2, v2) = p1, p2
        gap, over = 1.0, 2.0
        s = pre + rec.text + post
        if axis == "h":
            base = max(v1, v2) if off > 0 else min(v1, v2)
            vl = base + off * k
            sg = 1 if off > 0 else -1
            for u, v in (p1, p2):
                if abs(vl - v) / k > gap + 0.3:
                    self.seg((u, v + sg * gap * k), (u, vl + sg * over * k), owner=own)
            span = abs(u2 - u1) / k
            a, b = min(u1, u2), max(u1, u2)
            inside = span >= 7.0
            if inside:
                self.seg((a, vl), (b, vl), owner=own)
                self.arrow((a, vl), (-1, 0), own)
                self.arrow((b, vl), (1, 0), own)
            else:
                self.seg((a - 4.0 * k, vl), (b + 4.0 * k, vl), owner=own)
                self.arrow((a, vl), (1, 0), own)
                self.arrow((b, vl), (-1, 0), own)
            w = tw(s)
            if text_at == "right" or (text_at is None and span < w + 1.0):
                t = self.text(b + 5.0 * k, vl - 1.0 * k, s, ha="left", va="bottom", owner=own) if not flip_text else self.text(a - 5.0 * k, vl - 1.0 * k, s, ha="right", va="bottom", owner=own)
            elif text_at == "left":
                t = self.text(a - 5.0 * k, vl - 1.0 * k, s, ha="right", va="bottom", owner=own)
            else:
                t = self.text((a + b) / 2, vl + 0.9 * k, s, ha="center", va="bottom", owner=own)
        else:
            base = max(u1, u2) if off > 0 else min(u1, u2)
            ul = base + off * k
            sg = 1 if off > 0 else -1
            for u, v in (p1, p2):
                if abs(ul - u) / k > gap + 0.3:
                    self.seg((u + sg * gap * k, v), (ul + sg * over * k, v), owner=own)
            span = abs(v2 - v1) / k
            a, b = min(v1, v2), max(v1, v2)
            inside = span >= 7.0
            if inside:
                self.seg((ul, a), (ul, b), owner=own)
                self.arrow((ul, a), (0, -1), own)
                self.arrow((ul, b), (0, 1), own)
            else:
                self.seg((ul, a - 4.0 * k), (ul, b + 4.0 * k), owner=own)
                self.arrow((ul, a), (0, 1), own)
                self.arrow((ul, b), (0, -1), own)
            side = text_at or ("left" if off < 0 else "right")
            if side == "left":
                t = self.text(ul - 1.0 * k, (a + b) / 2, s, ha="right", va="center", owner=own)
            else:
                t = self.text(ul + 1.0 * k, (a + b) / 2, s, ha="left", va="center", owner=own)
        rec.artist, rec.p1, rec.p2, rec.axis, rec.view = t, tuple(p1), tuple(p2), axis, self
        return t

    def leader(self, p, dx, dy, lines: list[str], recs: list[Rec] = (), shoulder=3.0):
        """Leader from model point p to a note offset (dx, dy) paper mm; text lines after a short shoulder."""
        own = self.sheet.owner()
        x0, y0 = self.P(*p)
        x1, y1 = x0 + dx, y0 + dy
        sg = 1 if dx >= 0 else -1
        x2 = x1 + sg * shoulder
        self.sheet.line([(x0, y0), (x1, y1), (x2, y1)], lw=LW_THIN, owner=own)
        ln = math.hypot(dx, dy) or 1.0
        self.arrow(p, (-dx / ln, -dy / ln), own, length=2.2, half=0.45)
        txt = "\n".join(lines)
        t = self.sheet.text(x2 + sg * 1.0, y1, txt, ha="left" if sg > 0 else "right", va="center", owner=own, linespacing=1.15)
        for r in recs:
            r.artist = t
            r.view = self
        return t

    def balloon(self, p, r_model: float, tag: str, region=None, prefer=None, avoid_view=True):
        """Lettered balloon near model point p (a feature of radius r_model), placed where nothing else is on the sheet."""
        own = self.sheet.owner()
        x0, y0 = self.P(*p)
        r_pap = r_model / self.k
        R = 2.7
        reg = region or (FR + 2, TB_Y0 + TB_H + 2, PW - FR - 2, PH - FR - 2)
        vb = (self.x, self.y, self.x + self.w, self.y + self.h)
        angs = prefer or [45, 135, -45, -135, 90, -90, 0, 180, 22, 158, -22, -158, 68, 112, -68, -112]
        best = None
        for dist in (5.5, 8.0, 11.0, 14.0, 18.0, 23.0):
            for a in angs:
                cx = x0 + (r_pap + dist) * math.cos(math.radians(a))
                cy = y0 + (r_pap + dist) * math.sin(math.radians(a))
                rr = (cx - R - 0.4, cy - R - 0.4, cx + R + 0.4, cy + R + 0.4)
                if not (reg[0] <= rr[0] and rr[2] <= reg[2] and reg[1] <= rr[1] and rr[3] <= reg[3]):
                    continue
                if any(_hit(rr, o) for o in self.sheet.occ if o != vb):
                    continue
                inview = _hit(rr, vb)
                score = dist + (40.0 if inview and avoid_view else 0.0)
                if best is None or score < best[0]:
                    best = (score, cx, cy, a)
            if best is not None and best[0] < 30:
                break
        if best is None:
            best = (0, x0 + r_pap + 6, y0 + r_pap + 6, 45)
        _, cx, cy, a = best
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        self.sheet.line([(x0 + r_pap * ca, y0 + r_pap * sa), (cx - R * ca, cy - R * sa)], lw=LW_THIN, owner=own)
        self.sheet.pg.add_patch(Circle((x0 + r_pap * ca, y0 + r_pap * sa), 0.45, color=INK, clip_on=False))
        self.sheet.pg.add_patch(Circle((cx, cy), R, fill=True, facecolor="white", edgecolor=INK, lw=0.6, clip_on=False, zorder=5))
        t = self.sheet.text(cx, cy - 0.05, tag, ha="center", va="center", weight="bold", owner=own, occ=False, zorder=6)
        self.sheet.occ.append((cx - R, cy - R, cx + R, cy + R))
        return t


def _hit(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def make_view(sheet: Sheet, shape, vname: str, scale: Scale, x: float, y: float, label=None, hidden=True, lw=LW_VIS,
              window=None, hid_color=HIDDEN, color=INK, defl=None) -> View:
    shape = _wrapped(shape)
    win = window or proj_box(vname, bbox(shape))
    v = View(sheet, vname, win, scale, x, y, label)
    vis, hid = hlr(shape, vname, defl or max(0.01, 0.03 * scale.k))
    if hidden:
        v.polys(hid, lw=LW_HID, color=hid_color, ls=DASH_HID, track=False)
    v.polys(vis, lw=lw, color=color)
    v.vis, v.hid = vis, hid
    return v


# ------------------------------------------------------------------------------------- printed parts: local-frame specs
def print_axis(name: str, axis_local: str) -> str:
    _, ax, deg = PRINTED_LOCAL[name]
    v = np.zeros(3)
    v[AX[axis_local]] = 1.0
    w = _rot(v, ax, deg)
    return "xyz"[int(np.argmax(np.abs(w)))]


def to_local(geo: Geo, name: str, q) -> np.ndarray:
    _, ax, deg = PRINTED_LOCAL[name]
    return _rot(np.asarray(q, dtype=float) + geo.printed()[name]["off"], ax, -deg)


def _axis_point(f: dict, along: float) -> np.ndarray:
    k = AX[f["axis"]]
    oth = [i for i in range(3) if i != k]
    q = np.zeros(3)
    q[oth[0]], q[oth[1]] = f["c"]
    q[k] = along
    return q


def _m_lcyl(geo, name, axis_local, d, p_local, what, hole=True):
    """A cylinder of a printed part, found near p_local (model.py frame) on the exported shape; what: 'd', 'lo'/'hi'/'len'
    (its extent along its axis, model.py frame) or 'x'/'y'/'z' (its axis line, model.py frame)."""
    pa = print_axis(name, axis_local)
    f = find_cyl(geo, "printed/" + name, pa, d, p_local, hole)
    if what == "d":
        return f["d"]
    ends = sorted(to_local(geo, name, _axis_point(f, e))[AX[axis_local]] for e in (f["lo"], f["hi"]))
    if what in ("lo", "hi", "len"):
        return {"lo": ends[0], "hi": ends[1], "len": ends[1] - ends[0]}[what]
    return float(to_local(geo, name, _axis_point(f, (f["lo"] + f["hi"]) / 2))[AX[what]])


def _m_lplane(geo, name, axis_local, p_local):
    """The model.py-frame coordinate of the printed part's planar face (normal along axis_local) nearest p_local."""
    pa = print_axis(name, axis_local)
    f = find_plane(geo, "printed/" + name, pa, p_local)
    q = geo.to_print(name, p_local).copy()
    q[AX[pa]] = f["coord"]
    return float(to_local(geo, name, q)[AX[axis_local]])


def _m_cylk(geo, key, axis, d, near, what, hole=True):
    """As 'cyl', near given in the key's own frame (print frame for printed parts)."""
    p = np.asarray(near, dtype=float)
    k = AX[axis]
    oth = [i for i in range(3) if i != k]
    best, bd = None, 1e18
    for f in geo.feats(key):
        if f["axis"] != axis or f["hole"] != hole or abs(f["d"] - d) > max(0.05, 0.005 * d):
            continue
        dist = math.hypot(p[oth[0]] - f["c"][0], p[oth[1]] - f["c"][1])
        if dist < bd:
            best, bd = f, dist
    if best is None:
        raise LookupError(f"{key}: no cylinder d {d} along {axis} near {near}")
    if what == "d":
        return best["d"]
    if what == "len":
        return best["hi"] - best["lo"]
    return best["c"][[c for c in "xyz" if c != axis].index(what)]


def _m_hdepth(geo, key, axis, d, near):
    """Depth of a blind hole (its cylinder's length); a through hole has no depth (error)."""
    p = np.asarray(near, dtype=float)
    k = AX[axis]
    oth = [i for i in range(3) if i != k]
    f = min((f for f in geo.feats(key) if f["axis"] == axis and f["hole"] and abs(f["d"] - d) <= max(0.05, 0.005 * d)),
            key=lambda f: math.hypot(p[oth[0]] - f["c"][0], p[oth[1]] - f["c"][1]))
    dep = hole_depth(geo.shape(key), f)
    if dep is None:
        raise ValueError("through hole has no depth")
    return dep


def slots_of(geo: Geo, key: str) -> list[dict]:
    """Slots: pairs of half-cylinder hole faces with the same diameter, axis and length (round ends of a straight slot)."""
    parts = [f for f in geo.feats(key) if f["hole"] and 2.5 < f["span"] < 3.8]
    used, out = set(), []
    for i, a in enumerate(parts):
        if i in used:
            continue
        best = None
        for j, b in enumerate(parts):
            if j <= i or j in used or b["axis"] != a["axis"] or abs(b["d"] - a["d"]) > 1e-3:
                continue
            if abs(b["lo"] - a["lo"]) > 0.01 or abs(b["hi"] - a["hi"]) > 0.01:
                continue
            sep = math.hypot(b["c"][0] - a["c"][0], b["c"][1] - a["c"][1])
            if sep < 1e-3:
                continue
            if best is None or sep < best[1]:
                best = (j, sep)
        if best is not None:
            j, sep = best
            used |= {i, j}
            b = parts[j]
            out.append({"axis": a["axis"], "d": a["d"], "len": sep + a["d"], "c": ((a["c"][0] + b["c"][0]) / 2, (a["c"][1] + b["c"][1]) / 2),
                        "lo": a["lo"], "hi": a["hi"], "ends": (a["c"], b["c"])})
    return out


def _m_slot(geo, key, axis, d, near, what):
    p = np.asarray(near, dtype=float)
    k = AX[axis]
    oth = [i for i in range(3) if i != k]
    cands = [s for s in slots_of(geo, key) if s["axis"] == axis and abs(s["d"] - d) < 0.05]
    s = min(cands, key=lambda s: math.hypot(p[oth[0]] - s["c"][0], p[oth[1]] - s["c"][1]))
    if what == "w":
        return s["d"]
    if what == "len":
        return s["len"]
    return s["c"][[c for c in "xyz" if c != axis].index(what)]


def _m_slotpat(geo, key, axis, d, length, coord):
    """Span (max - min) of the centres of all slots of this width and length, along coord."""
    cands = [s for s in slots_of(geo, key) if s["axis"] == axis and abs(s["d"] - d) < 0.05 and abs(s["len"] - length) < 0.05]
    vals = [s["c"][[c for c in "xyz" if c != axis].index(coord)] for s in cands]
    return max(vals) - min(vals)


def all_planes(shape) -> list[dict]:
    out = []
    for f in _faces(shape):
        s = BRepAdaptor_Surface(f, True)
        if s.GetType() != GeomAbs_Plane:
            continue
        pl = s.Plane()
        n, o = pl.Axis().Direction(), pl.Location()
        out.append({"n": np.array([n.X(), n.Y(), n.Z()]), "o": np.array([o.X(), o.Y(), o.Z()]), "box": bbox(f)})
    return out


def _m_chamfer(geo, name, p_local, axis_local):
    """Extent along axis_local of the non-axis-aligned planar face nearest p_local (a chamfer), printed part."""
    p = geo.to_print(name, p_local)
    best, bd = None, 1e18
    for f in all_planes(geo.shape("printed/" + name)):
        if np.max(np.abs(f["n"])) > 0.999:
            continue
        b = f["box"]
        dist = math.sqrt(sum(max(b[i] - p[i], 0.0, p[i] - b[i + 3]) ** 2 for i in range(3)))
        if dist < bd:
            best, bd = f, dist
    k = AX[print_axis(name, axis_local)]
    return best["box"][k + 3] - best["box"][k]


def _m_ribd(geo, name, axis_local, c_local, zlo_local, zhi_local):
    """Twice the smallest distance from a seat axis (through c_local along axis_local) to a planar face parallel to it that
    lies between zlo and zhi along the axis (model.py frame): the diameter the centring ribs leave."""
    pa = print_axis(name, axis_local)
    a = np.zeros(3)
    a[AX[pa]] = 1.0
    c = geo.to_print(name, c_local)
    lo, hi = sorted(geo.to_print(name, np.where(np.arange(3) == AX[axis_local], z, np.asarray(c_local, dtype=float)))[AX[pa]] for z in (zlo_local, zhi_local))
    best = 1e18
    for f in all_planes(geo.shape("printed/" + name)):
        if abs(float(f["n"] @ a)) > 1e-6:
            continue
        b = f["box"]
        if b[AX[pa]] < lo - 1e-3 or b[AX[pa] + 3] > hi + 1e-3:
            continue
        best = min(best, abs(float(f["n"] @ (f["o"] - c))))
    return 2 * best


def cone_feats(shape) -> list[dict]:
    from OCP.GeomAbs import GeomAbs_Cone

    out = []
    for f in _faces(shape):
        s = BRepAdaptor_Surface(f, True)
        if s.GetType() != GeomAbs_Cone:
            continue
        ap = s.Cone().Apex()
        out.append({"apex": np.array([ap.X(), ap.Y(), ap.Z()]), "box": bbox(f)})
    return out


def _m_cone(geo, key, near, what):
    p = geo.frame_point(key, near)
    f = min(cone_feats(geo.shape(key)), key=lambda f: float(np.linalg.norm(f["apex"][:2] - p[:2])))
    if what in "xyz":
        return float(f["apex"][AX[what]])
    return f["box"][3] - f["box"][0]  # 'd': the cone's largest diameter (along X)


MEASURES.update({"lcyl": _m_lcyl, "lplane": _m_lplane, "cylk": _m_cylk, "hdepth": _m_hdepth, "slot": _m_slot, "slotpat": _m_slotpat,
                 "chamfer": _m_chamfer, "ribd": _m_ribd, "cone": _m_cone})


def s_lcyl(name, ax, d, p, what, hole=True):
    return ("lcyl", name, ax, d, tuple(float(v) for v in p), what, hole)


def s_lpl(name, ax, p):
    return ("lplane", name, ax, tuple(float(v) for v in p))


def s_sub(a, b):
    return ("sub", a, b)


# ---------------------------------------------------------------------------------- printed parts: automatic tables
HOLE_USE = [(1.8, "M2, self-tapping"), (2.2, "M2 screw + nut"), (2.35, "M2"), (2.4, "M2"), (2.5, "M3 self-tapping pilot"),
            (3.1, "3 mm pin"), (3.2, "M3"), (3.4, "M3 clearance"), (4.5, "wood screw"), (5.3, "M5 axle"), (5.5, "M5 clearance"),
            (6.4, "M5 heat-set insert pocket"), (6.5, "M3 head counterbore"), (8.3, "dowel drill guide"), (9.5, "M5 head, sunk"),
            (10.0, "M5 button-head recess"), (10.4, "M10x1 buffer body"), (10.5, "lead-screw / T8 nut clearance"),
            (23.0, "NEMA 17 pilot clearance"), (25.0, "lens window")]
PART_USE = {  # (axis in print frame, diameter) -> use, where the generic one is wrong or vague
    "gate_post_L": {("x", 7.2): "laser barrel bore (7 mm Class 2 laser)", ("y", 2.5): "M3 set screw onto the barrel (tap or self-form)",
                    ("z", 4.5): "yaw slot, wood screws"},
    "gate_post_R": {("x", 6.2): "receiver barrel bore (6 mm module)", ("y", 2.5): "M3 set screw onto the barrel (tap or self-form)",
                    ("z", 4.5): "yaw slot, wood screws"},
    "station_mount": {("z", 4.5): "#8 wood screws into the bed", ("z", 1.8): "camera board, M2 self-tapping", ("z", 64.0): "station LED ring seat bore",
                      ("z", 44.0): "ring shelf inner edge"},
    "phase0_base": {("z", 1.8): "camera board, M2 self-tapping", ("z", 64.0): "station LED ring seat bore", ("z", 44.0): "ring shelf inner edge"},
    "camera_bracket": {("z", 42.8): "head LED ring seat bore (ribbed)", ("z", 33.0): "ring lip (ring back face rests on it)",
                       ("z", 2.2): "camera board, M2 + nuts"},
    "phase0_top": {("z", 42.8): "head LED ring pocket (ribbed)", ("z", 1.8): "M2 standoffs, blind"},
    "z_plate": {("z", 2.5): "carry_flag_arm, M3x10 self-tapping", ("y", 10.5): "T8 nut body clearance"},
    "carry_flag_arm": {("y", 2.5): "carry flag, M3x8 self-tapping"},
    "awl_adapter": {("z", 3.1): "3 mm steel pin, pressed in + CA"},
    "x_idler_mount": {("y", 5.3): "M5 idler axle (tension travel)"},
    "head_foot": {("x", 3.4): "endstop board M3 slots (trip adjustment)"},
}
BOSS_USE = {5.0: "M2 boss", 14.0: "body", 16.0: "drill-guide boss", 70.0: "ring seat tube", 48.8: "ring seat tube", 49.8: "ring seat tube"}


def _use(name: str, axis: str, d: float, hole: bool = True) -> str:
    for (ax, dd), s in PART_USE.get(name, {}).items():
        if ax == axis and abs(dd - d) < 0.02:
            return s
    if not hole:
        for dd, s in BOSS_USE.items():
            if abs(dd - d) < 0.02:
                return s
        return "outer cylinder"
    for dd, s in HOLE_USE:
        if abs(dd - d) < 0.02:
            return s
    return "bore"


def _pattern_text(geo, key, axis, d, hs) -> tuple[str, list[Rec]]:
    oth = [c for c in "xyz" if c != axis]
    n = len(hs)
    if n < 2:
        return "", []
    us = sorted({round(h["c"][0], 2) for h in hs})
    vs = sorted({round(h["c"][1], 2) for h in hs})
    recs = []
    if len(us) > 1:
        recs.append(G(f"{key} {n}x d{fmt(d)} along {axis}: centre span in {oth[0].upper()}", ("pat", key, axis, d, oth[0]),
                      f"{key[8:]} {n} holes d{fmt(d)} along {axis}: centre span {oth[0].upper()}"))
    if len(vs) > 1:
        recs.append(G(f"{key} {n}x d{fmt(d)} along {axis}: centre span in {oth[1].upper()}", ("pat", key, axis, d, oth[1]),
                      f"{key[8:]} {n} holes d{fmt(d)} along {axis}: centre span {oth[1].upper()}"))
    grid = len(us) * len(vs) == n
    if len(recs) == 1:
        lab = oth[0] if len(us) > 1 else oth[1]
        txt = f"{recs[0].text} apart in {lab.upper()}" if n == 2 else f"over {recs[0].text} in {lab.upper()}"
    else:
        txt = f"on {recs[0].text} x {recs[1].text} ({oth[0].upper()} x {oth[1].upper()})" + ("" if grid else ", not a grid")
    return txt, recs


def auto_features(geo: Geo, name: str) -> list[dict]:
    """Rows for the feature table: hole groups (diameter + axis), slots, bosses; each with its numbers as Recs and a
    representative feature to balloon."""
    key = "printed/" + name
    solid = geo.shape(key)
    rows = []
    feats = geo.feats(key)
    groups: dict = {}
    for f in feats:
        if f["hole"] and f["span"] > 4.6:  # full bores (and bores broken only by ribs or a notch)
            groups.setdefault((f["axis"], round(f["d"], 2)), []).append(f)
    for (axis, dd), hs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        hs = sorted(hs, key=lambda h: (round(h["c"][0], 2), round(h["c"][1], 2)))
        rep = hs[0]
        near = _axis_point(rep, (rep["lo"] + rep["hi"]) / 2)
        rd = G(f"{name} hole d{dd} along {axis}: diameter", ("cylk", key, axis, rep["d"], tuple(near), "d"), f"{name} hole group along {axis}: diameter")
        deps = [hole_depth(solid, h) for h in hs]
        recs = [rd]
        if all(dp is None for dp in deps):
            dtxt = "THRU"
        else:
            j = next(i for i, dp in enumerate(deps) if dp is not None)
            hn = _axis_point(hs[j], (hs[j]["lo"] + hs[j]["hi"]) / 2)
            r = G(f"{name} hole d{dd} along {axis}: depth", ("hdepth", key, axis, rep["d"], tuple(hn)), f"{name} blind hole along {axis}: cylinder length")
            recs.append(r)
            dtxt = f"x {r.text} deep" + (" (some THRU)" if any(dp is None for dp in deps) else "")
        if rep["span"] < 6.2:
            dtxt += ", interrupted"
        ptxt, precs = _pattern_text(geo, key, axis, rep["d"], [h for h in hs if h["span"] > 6.2] if len(hs) > 1 else hs)
        recs += precs
        n = len(hs)
        txt = f"{n}x " if n > 1 else ""
        txt += f"Ø{rd.text} {dtxt}, axis {axis.upper()}" + (f", {ptxt}" if ptxt else "") + f": {_use(name, axis, rep['d'])}"
        rows.append({"text": txt, "recs": recs, "feat": rep, "axis": axis, "r": rep["d"] / 2})
    sgroups: dict = {}
    for s in slots_of(geo, key):
        sgroups.setdefault((s["axis"], round(s["d"], 2), round(s["len"], 2)), []).append(s)
    for (axis, dd, ln), ss in sorted(sgroups.items()):
        ss = sorted(ss, key=lambda s: (round(s["c"][0], 2), round(s["c"][1], 2)))
        rep = ss[0]
        near = _axis_point(rep, (rep["lo"] + rep["hi"]) / 2)
        rw = G(f"{name} slot along {axis}: width", ("slot", key, axis, rep["d"], tuple(near), "w"), f"{name} slot (paired half-cylinders) along {axis}: width")
        rl = G(f"{name} slot along {axis}: length", ("slot", key, axis, rep["d"], tuple(near), "len"), f"{name} slot along {axis}: end-centre distance + width")
        recs = [rw, rl]
        extra = ""
        if len(ss) > 1:
            oth = [c for c in "xyz" if c != axis]
            spans = []
            for i, o in enumerate(oth):
                vals = [s["c"][i] for s in ss]
                if max(vals) - min(vals) > 0.01:
                    r = G(f"{name} slots along {axis}: centre span {o.upper()}", ("slotpat", key, axis, rep["d"], rep["len"], o), f"{name} slot centres along {axis}: span {o.upper()}")
                    recs.append(r)
                    spans.append(f"{r.text} in {o.upper()}")
            extra = ", centres " + " and ".join(spans) + " apart" if spans else ""
        n = len(ss)
        txt = (f"{n}x " if n > 1 else "") + f"slot {rw.text} wide x {rl.text} long, axis {axis.upper()}{extra}: {_use(name, axis, rep['d'])}"
        rows.append({"text": txt, "recs": recs, "feat": rep, "axis": axis, "r": rep["d"] / 2, "slot": True})
    bgroups: dict = {}
    for f in feats:
        if not f["hole"] and f["span"] > 6.2 and f["d"] >= 4.0:
            bgroups.setdefault((f["axis"], round(f["d"], 2)), []).append(f)
    for (axis, dd), bs in sorted(bgroups.items()):
        bs = sorted(bs, key=lambda h: (round(h["c"][0], 2), round(h["c"][1], 2)))
        rep = bs[0]
        near = _axis_point(rep, (rep["lo"] + rep["hi"]) / 2)
        rd = G(f"{name} boss d{dd} along {axis}: diameter", ("cylk", key, axis, rep["d"], tuple(near), "d", False), f"{name} outer cylinder along {axis}: diameter")
        rh = G(f"{name} boss d{dd} along {axis}: length", ("cylk", key, axis, rep["d"], tuple(near), "len", False), f"{name} outer cylinder along {axis}: length")
        n = len(bs)
        txt = (f"{n}x " if n > 1 else "") + f"Ø{rd.text} x {rh.text} long (outside), axis {axis.upper()}: {_use(name, axis, rep['d'], hole=False)}"
        rows.append({"text": txt, "recs": [rd, rh], "feat": rep, "axis": axis, "r": rep["d"] / 2, "boss": True})
    return rows
