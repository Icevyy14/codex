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
        feats.setdefault(key, []).append((min(a0, a1), max(a0, a1), abs(u1 - u0), (ov[oth[0]], ov[oth[1]]), dia))
    out = []
    for (axis, _, _, _, hole), segs in feats.items():  # coaxial faces of one diameter: one feature per touching axial run
        segs.sort()
        cur = None
        for lo, hi, span, c, dia in segs:
            if cur is not None and lo <= cur["hi"] + 1e-6:
                cur["hi"] = max(cur["hi"], hi)
                cur["span"] += span
                continue
            cur = {"axis": axis, "d": dia, "c": c, "lo": lo, "hi": hi, "span": span, "hole": hole}
            out.append(cur)
    return out


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


def _m_pat(geo, key, axis, d, what, lo=None, hi=None):
    hs = [h for h in holes_of(geo, key, axis, d) if lo is None or (abs(h["lo"] - lo) < 0.01 and abs(h["hi"] - hi) < 0.01)]
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
    "station_mount": {("z", 4.5): "#8 wood screws into the bed", ("z", 1.8): "camera board, M2 self-tapping", ("z", 64.0, 1): "station LED ring seat bore",
                      ("z", 64.0, 0): "hollow under the ring shelf (45° cone roof)", ("z", 44.0): "ring shelf inner edge"},
    "phase0_base": {("z", 1.8): "camera board, M2 self-tapping", ("z", 64.0, 1): "station LED ring seat bore",
                    ("z", 64.0, 0): "hollow under the ring shelf (45° cone roof)", ("z", 44.0): "ring shelf inner edge"},
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


def _use(name: str, axis: str, d: float, hole: bool = True, idx: int = 0) -> str:
    """idx: which run of this size along this axis (0 = lowest along the axis), for PART_USE keys (axis, d, idx)."""
    for key_, s in PART_USE.get(name, {}).items():
        if key_[0] == axis and abs(key_[1] - d) < 0.02 and (len(key_) == 2 or key_[2] == idx):
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
    if n < 2 or len({(round(h["c"][0], 2), round(h["c"][1], 2)) for h in hs}) < 2:
        return "", []
    lo, hi = hs[0]["lo"], hs[0]["hi"]
    us = sorted({round(h["c"][0], 2) for h in hs})
    vs = sorted({round(h["c"][1], 2) for h in hs})
    recs = []
    if len(us) > 1:
        recs.append(G(f"{key} {n}x d{fmt(d)} along {axis}: centre span in {oth[0].upper()}", ("pat", key, axis, d, oth[0], lo, hi),
                      f"{key[8:]} {n} holes d{fmt(d)} along {axis}: centre span {oth[0].upper()}"))
    if len(vs) > 1:
        recs.append(G(f"{key} {n}x d{fmt(d)} along {axis}: centre span in {oth[1].upper()}", ("pat", key, axis, d, oth[1], lo, hi),
                      f"{key[8:]} {n} holes d{fmt(d)} along {axis}: centre span {oth[1].upper()}"))
    grid = len(us) * len(vs) == n
    if len(recs) == 1:
        lab = oth[0] if len(us) > 1 else oth[1]
        txt = f"{recs[0].text} apart in {lab.upper()}" if n == 2 else f"centres over {recs[0].text} in {lab.upper()}"
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
        if f["hole"] and f["span"] > 4.6:  # full bores (and bores broken only by ribs or a notch); one row per size and axial run
            groups.setdefault((f["axis"], round(f["d"], 2), round(f["lo"], 2), round(f["hi"], 2)), []).append(f)
    seen: dict = {}
    for (axis, dd, _, _), hs in sorted(groups.items(), key=lambda kv: kv[0]):
        idx = seen.get((axis, dd), 0)
        seen[(axis, dd)] = idx + 1
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
        txt += f"Ø{rd.text} {dtxt}, axis {axis.upper()}" + (f", {ptxt}" if ptxt else "") + f": {_use(name, axis, rep['d'], idx=idx)}"
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
                    spans.append(f"{r.text} apart in {o.upper()}")
            extra = ", centres " + " and ".join(spans) if spans else ""
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


def _m_mid(geo, a, b):
    return (measure(geo, a) + measure(geo, b)) / 2


MEASURES["mid"] = _m_mid


def _m_ribd2(geo, name, axis_local, c_local, zlo_local, zhi_local):
    """As ribd, but only faces that contain the foot of the perpendicular from the axis (the ribs' inner faces, not their
    sides or a lead slot's end)."""
    pa = print_axis(name, axis_local)
    k = AX[pa]
    a = np.zeros(3)
    a[k] = 1.0
    c = geo.to_print(name, c_local)
    zs = []
    for z in (zlo_local, zhi_local):
        q = np.array(c_local, dtype=float)
        q[AX[axis_local]] = z
        zs.append(geo.to_print(name, q)[k])
    lo, hi = sorted(zs)
    best = 1e18
    for f in all_planes(geo.shape("printed/" + name)):
        n = f["n"]
        if abs(float(n @ a)) > 1e-6:
            continue
        b = f["box"]
        if b[k] < lo - 1e-3 or b[k + 3] > hi + 1e-3:
            continue
        dist = float(n @ (f["o"] - c))
        foot = c + dist * n
        if all(b[i] - 0.01 <= foot[i] <= b[i + 3] + 0.01 for i in range(3) if i != k):
            best = min(best, abs(dist))
    return 2 * best


MEASURES["ribd"] = _m_ribd2


def _row(text: str, recs: list[Rec], at=None) -> dict:
    """A custom table row; at = (axis_local, local point, radius) of a feature to balloon (optional)."""
    return {"text": text, "recs": recs, "at": at}


def custom_rows(geo: Geo, name: str) -> list[dict]:  # noqa: C901 - one branch per part
    """Functional features the hole table does not show. Model constants only LOCATE a feature (near points); every number
    printed is measured on the exported shape."""
    n = name
    out: list[dict] = []
    s = 1 if n == "gate_post_R" else -1
    if n in ("gate_post_L", "gate_post_R"):
        bore = 7.2 if n == "gate_post_L" else 6.2  # locator only: picks the bore (its diameter printed is measured)
        hz = L.GATE_Z + L.PAD_T
        r = G(f"{n}: bore axis above the foot underside", s_sub(s_lcyl(n, "x", bore, (s * 4, 0, hz), "z"), s_lpl(n, "z", (s * 4, 18, 0))),
              f"{n} barrel bore axis Z - foot underside Z")
        g = C("GATE_Z")
        out.append(_row(f"Barrel bore axis {r.text} above the foot underside: on bare plywood the beam is GATE_Z = {g.text} above the pad top (BUILD_GUIDE 5.9: no shim)", [r, g], ("x", (s * 4, 0, hz), bore / 2)))
    elif n == "station_mount":
        sh = G("station_mount: ring shelf above the base-plate top", s_sub(s_lpl(n, "z", (-27, 0, M.STATION_RING_Z)), s_lpl(n, "z", (-36, -40, 0))),
               "station_mount ring shelf Z - base plate top Z")
        bo = G("station_mount: camera boss tops above the base-plate top", s_sub(s_lpl(n, "z", (M.CM3_HOLES[0][0] - 2.0, M.CM3_HOLES[0][1], 11.5)), s_lpl(n, "z", (-36, -40, 0))),
               "station_mount M2 boss top Z - base plate top Z")
        lz = C("STATION_LENS_Z")
        out.append(_row(f"Ring shelf (ring back face, LEDs up) {sh.text} above the base-plate top, which is level with the pad tops", [sh]))
        out.append(_row(f"Camera bosses: tops {bo.text} above the base-plate top (board back); lens front STATION_LENS_Z = {lz.text}", [bo, lz]))
    elif n == "x_motor_mount":
        r = G("x_motor_mount: bumper face to the motor axis", s_sub(s_lcyl(n, "y", 23.0, (0, -2.5, 20), "x"), s_lpl(n, "x", (M.X_MOTOR_X0, -12, -30))),
              "x_motor_mount pilot axis X - left end face X")
        z = G("x_motor_mount: motor axis above the beam top", s_lcyl(n, "y", 23.0, (0, -2.5, 20), "z"), "x_motor_mount pilot axis Z (model.py frame, Z 0 = beam top)")
        out.append(_row(f"Left end = right X hard stop face, {r.text} from the motor axis; motor axis {z.text} above the beam top", [r, z]))
    elif n == "x_idler_slider":
        w = G("x_idler_slider: M3 nut slot width", s_sub(s_lpl(n, "x", (-11.7, 6, 34)), s_lpl(n, "x", (-14.3, 6, 34))), "x_idler_slider nut slot faces X")
        out.append(_row(f"M3 nut slot {w.text} wide, from the top, in the bridge", [w]))
    elif n == "x_bracket":
        ln = G("x_bracket: switch finger length past the left edge", s_sub(s_lpl(n, "x", (-30, -4, 400)), s_lpl(n, "x", (-30 - M.XF_LEN, -4, 377.5))),
               "x_bracket plate left face X - finger end face X")
        fz = G("x_bracket: finger flat underside, machine Z", s_lpl(n, "z", (-38, -4, M.XF_Z[0])), "x_bracket finger underside Z (model.py frame = machine Z)")
        ch = G("x_bracket: finger lead-in depth", ("chamfer", n, (-30 - M.XF_LEN + 2.0, -4, M.XF_Z[0] + 2.0), "z"), "x_bracket finger 45-deg face: Z extent")
        out.append(_row(f"X-switch finger {ln.text} past the left edge; flat underside at machine Z {fz.text}; 45° lead-in {ch.text} deep", [ln, fz, ch],
                        ("y", (-30 - M.XF_LEN / 2, -4, M.XF_Z[0]), 0.0)))
        zf = M.CLAMP_FLOOR_Z
        p = G("x_bracket: GT2 rack tooth pitch", s_sub(s_lpl(n, "x", (12.5, 19, zf + 0.4)), s_lpl(n, "x", (10.5, 19, zf + 0.4))), "x_bracket rack tooth faces X")
        out.append(_row(f"GT2 rack on the tab floor, both sides: teeth at {p.text} pitch (belt teeth down, belt_clamp cap on top)", [p]))
    elif n == "z_motor_mount":
        r = G("z_motor_mount: tab hole below the spine-top face", s_sub(s_lpl(n, "z", (-25, 80, 0)), s_lcyl(n, "y", 5.5, (-20, 63.5, -15), "z")),
              "z_motor_mount plate underside Z - tab hole axis Z")
        out.append(_row(f"Plate underside sits on the spine top and is the Z top hard stop; tab hole {r.text} below it (left slot)", [r]))
    elif n == "z_end_cap":
        r = G("z_end_cap: lip height above the plate top", s_sub(s_lpl(n, "z", (8, 60, L.Z_END_CAP_LIP)), s_lpl(n, "z", (-20, 75, 0))), "z_end_cap lip top Z - plate top Z")
        out.append(_row(f"Two lips {r.text} above the plate top, under the Z carriage skirts: the Z bottom hard stop (c = C_HARD_BOTTOM)", [r]))
    elif n == "z_plate":
        cy = G("z_plate: switch chamfer depth (Y)", ("chamfer", n, (30, -1, L.Z_PLATE_TOP - 1), "y"), "z_plate 45-deg chamfer face: Y extent")
        cz = G("z_plate: switch chamfer height (Z)", ("chamfer", n, (30, -1, L.Z_PLATE_TOP - 1), "z"), "z_plate 45-deg chamfer face: Z extent")
        cx = G("z_plate: switch chamfer length (X)", ("chamfer", n, (30, -1, L.Z_PLATE_TOP - 1), "x"), "z_plate 45-deg chamfer face: X extent")
        out.append(_row(f"Z-switch chamfer 45°, {cy.text} x {cz.text}, {cx.text} long at the right end of the top back edge", [cy, cz, cx]))
        tz = G("z_plate: top edge above the Z carriage bottom", s_lpl(n, "z", (0, -4, L.Z_PLATE_TOP)), "z_plate top face Z (model.py frame, Z 0 = Z carriage bottom)")
        sz = G("z_plate: T8 flange shelf top above the Z carriage bottom", s_lpl(n, "z", (L.Z_SCREW_DX + 9, -12, 48)), "z_plate shelf top Z (model.py frame)")
        out.append(_row(f"Top edge (Z top hard stop) {tz.text} and T8 flange shelf top {sz.text} above the Z carriage's bottom edge", [tz, sz]))
    elif n == "head_foot":
        sw = G("head_foot: arm socket width", s_sub(s_lpl(n, "x", (10.2, 35, 80)), s_lpl(n, "x", (-10.2, 35, 80))), "head_foot arm socket faces X")
        fl = G("head_foot: socket floor above the underside", s_sub(s_lpl(n, "z", (0, 35, 65)), s_lpl(n, "z", (-12, -5, 62))), "head_foot socket floor Z - underside Z")
        xh = G("head_foot: cross hole above the socket floor", s_sub(s_lcyl(n, "x", 5.5, (10, 35, 84), "z"), s_lpl(n, "z", (0, 35, 65))), "head_foot M5 cross hole axis Z - socket floor Z")
        out.append(_row(f"Drop-arm socket {sw.text} square, floor {fl.text} above the underside; cross hole {xh.text} above the floor (match-drill the arm)", [sw, fl, xh]))
        gw = G("head_foot: flag guide slot width", s_sub(s_lpl(n, "y", (15, M.PROBE_Y + M.GUIDE_GAP / 2, 68)), s_lpl(n, "y", (15, M.PROBE_Y - M.GUIDE_GAP / 2, 68))),
               "head_foot flag slot faces Y")
        uz = G("head_foot: underside above the cup face (model.py frame)", s_lpl(n, "z", (-12, -5, 62)), "head_foot underside Z (model.py frame: Z 0 = cup face c)")
        out.append(_row(f"Flag guide slot {gw.text} wide through the fins and the foot (clear it after printing); underside at c + {uz.text}", [gw, uz],
                        ("z", (16, M.PROBE_Y, 70), 0.0)))
    elif n == "camera_bracket":
        rb = G("camera_bracket: ring seat rib diameter", ("ribd", n, "z", (0, M.CAM_DY, 0), M.CAM_Z + M.HEAD_RING_FACE_DZ - 1.0, M.CAM_Z + M.HEAD_RING_FACE_DZ + M.HEAD_RING[2]),
               "camera_bracket ring-seat rib inner faces: 2 x distance from the seat axis")
        lip = G("camera_bracket: lip (ring back face) below the board shelf", s_sub(s_lpl(n, "z", (20, 20, M.CAM_Z + M.HEAD_LENS_PROJ)), s_lpl(n, "z", (0, M.CAM_DY - 18, M.CAM_Z + M.HEAD_RING_FACE_DZ + M.HEAD_RING[2]))),
                "camera_bracket shelf top Z - lip underside Z")
        out.append(_row(f"Ring seat: 3 ribs leave Ø{rb.text} (shave for a larger ring, BUILD_GUIDE 3.3); ring back face (lip) {lip.text} below the board shelf", [rb, lip]))
        off = G("camera_bracket: lens axis to drop-arm centre", s_sub(("mid", s_lpl(n, "y", (0, L.ARM_TO_CUP + 10.2, M.CAM_Z + 5)), s_lpl(n, "y", (0, L.ARM_TO_CUP - 10.2, M.CAM_Z + 5))),
                                                                     s_lcyl(n, "z", M.LENS_WINDOW_D, (0, M.CAM_DY, M.CAM_Z + M.HEAD_LENS_PROJ - 2), "y")),
                "camera_bracket arm bore centre Y - lens window axis Y")
        dy = C("HEAD_CAM_DY")
        out.append(_row(f"Lens axis {off.text} from the drop-arm centre (ARM_TO_CUP + lens offset HEAD_CAM_DY = {dy.text})", [off, dy]))
    elif n == "drill_template":
        sx = G("drill_template: side holes X", s_sub(s_lcyl(n, "z", 8.3, (46, 57.5, 6), "x"), s_lcyl(n, "z", 8.3, (-46, 57.5, 6), "x")), "drill_template side-rod holes X")
        sy = G("drill_template: side holes Y", s_sub(s_lcyl(n, "z", 8.3, (46, 57.5, 6), "y"), s_lcyl(n, "z", 8.3, (46, -57.5, 6), "y")), "drill_template side-rod holes Y")
        fx = G("drill_template: front/back holes X", s_sub(s_lcyl(n, "z", 8.3, (30, 73.5, 6), "x"), s_lcyl(n, "z", 8.3, (-30, 73.5, 6), "x")), "drill_template front/back-rod holes X")
        fy = G("drill_template: front/back holes Y", s_sub(s_lcyl(n, "z", 8.3, (30, 73.5, 6), "y"), s_lcyl(n, "z", 8.3, (30, -73.5, 6), "y")), "drill_template front/back-rod holes Y")
        out.append(_row(f"Side-rod holes {sx.text} x {sy.text}; front/back-rod holes {fx.text} x {fy.text} (centres)", [sx, sy, fx, fy]))
        dd = G("drill_template: dimple spacing", s_sub(("cone", "printed/" + n, (40, 0, 4), "x"), ("cone", "printed/" + n, (-40, 0, 4), "x")), "drill_template cone dimples: apex X spacing")
        dm = G("drill_template: dimple diameter", ("cone", "printed/" + n, (40, 0, 4), "d"), "drill_template cone dimple: top diameter")
        out.append(_row(f"Two cone dimples Ø{dm.text}, {dd.text} apart on the row centre line (the awl finds them)", [dd, dm]))
        wx = G("drill_template: window X", s_sub(s_lpl(n, "x", (25, 0, 2)), s_lpl(n, "x", (-25, 0, 2))), "drill_template window faces X")
        wy = G("drill_template: window Y", s_sub(s_lpl(n, "y", (0, 45, 2)), s_lpl(n, "y", (0, -45, 2))), "drill_template window faces Y")
        out.append(_row(f"Window {wx.text} x {wy.text} to see the pencil centre line", [wx, wy]))
    elif n == "fill_gauge":
        mx = G("fill_gauge: MAX line above the foot", s_sub(s_lpl(n, "z", (20, 2, L.MAX_LINE)), s_lpl(n, "z", (8, 2, 0))), "fill_gauge top-bar underside Z - foot Z")
        ml = C("MAX_LINE")
        pt = G("fill_gauge: notch pitch", s_sub(s_lpl(n, "z", (1.5, 2, 2 * 5 * L.SLAB_T)), s_lpl(n, "z", (1.5, 2, 5 * L.SLAB_T))), "fill_gauge notch floors Z")
        nw = G("fill_gauge: notch width", s_sub(s_lpl(n, "z", (1.5, 2, 5 * L.SLAB_T + 0.8)), s_lpl(n, "z", (1.5, 2, 5 * L.SLAB_T))), "fill_gauge notch faces Z")
        nd = G("fill_gauge: notch depth", s_sub(s_lpl(n, "x", (3, 2, 5 * L.SLAB_T + 0.4)), s_lpl(n, "x", (0, 2, 50))), "fill_gauge notch back X - bar face X")
        out.append(_row(f"MAX line = underside of the top bar, {mx.text} above the foot (MAX_LINE = {ml.text})", [mx, ml]))
        out.append(_row(f"Count notches every {pt.text} (5 slabs), {nw.text} wide, {nd.text} deep", [pt, nw, nd]))
    elif n == "carry_flag_arm":
        r = G("carry_flag_arm: flag seat behind the ear face", s_sub(s_lpl(n, "y", (-58, M.CS_Y - M.FLAG_T / 2, 8)), s_lpl(n, "y", (-24, Z_PLATE_FACE, 8))),
              "carry_flag_arm leg end face Y - ear face Y")
        out.append(_row(f"Leg end face (carry flag seat) {r.text} behind the ear face that sits on the z_plate", [r]))
    elif n == "phase0_base":
        sw = G("phase0_base: socket width", s_sub(s_lpl(n, "x", (M.P0_POST_X + 10.2, 0, 12)), s_lpl(n, "x", (M.P0_POST_X - 10.2, 0, 12))), "phase0_base socket faces X")
        fl = G("phase0_base: socket floor", s_sub(s_lpl(n, "z", (M.P0_POST_X, 0, M.P0_SOCKET_FLOOR)), s_lpl(n, "z", (-30, -50, 0))), "phase0_base socket floor Z - underside Z")
        cc = G("phase0_base: socket centres", s_sub(("mid", s_lpl(n, "x", (M.P0_POST_X + 10.2, 0, 12)), s_lpl(n, "x", (M.P0_POST_X - 10.2, 0, 12))),
                                                    ("mid", s_lpl(n, "x", (-M.P0_POST_X + 10.2, 0, 12)), s_lpl(n, "x", (-M.P0_POST_X - 10.2, 0, 12)))), "phase0_base socket centres X")
        out.append(_row(f"Post sockets {sw.text} square, floor {fl.text} above the underside, centres {cc.text} apart", [sw, fl, cc]))
        sh = G("phase0_base: ring shelf above the underside", s_sub(s_lpl(n, "z", (-27, 0, M.STATION_RING_Z)), s_lpl(n, "z", (-30, -50, 0))), "phase0_base ring shelf Z - underside Z")
        xh = G("phase0_base: cross hole height", s_sub(s_lcyl(n, "y", 5.5, (M.P0_POST_X, 0, 16), "z"), s_lpl(n, "z", (-30, -50, 0))), "phase0_base M5 cross hole axis Z - underside Z")
        out.append(_row(f"Ring shelf {sh.text} and socket cross holes {xh.text} above the underside", [sh, xh]))
    elif n == "phase0_tray":
        rx = G("phase0_tray: recess X", s_sub(s_lpl(n, "x", (40.65, 0, 1.5)), s_lpl(n, "x", (-40.65, 0, 1.5))), "phase0_tray recess faces X")
        ry = G("phase0_tray: recess Y", s_sub(s_lpl(n, "y", (35, 68.25, 1.5)), s_lpl(n, "y", (35, -68.25, 1.5))), "phase0_tray recess faces Y")
        rd = G("phase0_tray: recess depth", s_sub(s_lpl(n, "z", (45, 0, 4)), s_lpl(n, "z", (39, 0, 0))), "phase0_tray frame top Z - ledge top Z")
        ox = G("phase0_tray: opening X", s_sub(s_lpl(n, "x", (37.55, 0, -1)), s_lpl(n, "x", (-37.55, 0, -1))), "phase0_tray opening faces X")
        oy = G("phase0_tray: opening Y", s_sub(s_lpl(n, "y", (0, 65.15, -1)), s_lpl(n, "y", (0, -65.15, -1))), "phase0_tray opening faces Y")
        out.append(_row(f"Slab recess {rx.text} x {ry.text}, {rd.text} deep; opening {ox.text} x {oy.text}; the ledges carry the slab's front face", [rx, ry, rd, ox, oy]))
        cw = G("phase0_tray: clamp bore", s_sub(s_lpl(n, "x", (M.P0_POST_X + 10.2, 0, 6)), s_lpl(n, "x", (M.P0_POST_X - 10.2, 0, 6))), "phase0_tray clamp bore faces X")
        cc = G("phase0_tray: clamp centres", s_sub(("mid", s_lpl(n, "x", (M.P0_POST_X + 10.2, 0, 6)), s_lpl(n, "x", (M.P0_POST_X - 10.2, 0, 6))),
                                                   ("mid", s_lpl(n, "x", (-M.P0_POST_X + 10.2, 0, 6)), s_lpl(n, "x", (-M.P0_POST_X - 10.2, 0, 6)))), "phase0_tray clamp centres X")
        out.append(_row(f"Post clamps {cw.text} square, centres {cc.text} apart", [cw, cc]))
    elif n == "phase0_top":
        sw = G("phase0_top: socket width", s_sub(s_lpl(n, "x", (M.P0_POST_X + 10.2, 0, 2.5)), s_lpl(n, "x", (M.P0_POST_X - 10.2, 0, 2.5))), "phase0_top socket faces X")
        sd = G("phase0_top: socket depth", s_sub(s_lpl(n, "z", (M.P0_POST_X, 0, M.P0_BAR_SOCKET)), s_lpl(n, "z", (40, 20, 0))), "phase0_top socket roof Z - underside Z")
        mid0 = ("mid", s_lpl(n, "y", (M.P0_POST_X, 10.2, 2.5)), s_lpl(n, "y", (M.P0_POST_X, -10.2, 2.5)))
        e1 = G("phase0_top: bar edge toward the label end", s_sub(mid0, s_lpl(n, "y", (40, M.CAM_DY - 25, 5))), "phase0_top socket centre line Y - front edge Y")
        e2 = G("phase0_top: bar edge toward the back", s_sub(s_lpl(n, "y", (40, 25, 5)), mid0), "phase0_top back edge Y - socket centre line Y")
        out.append(_row(f"Blind post sockets {sw.text} square, {sd.text} deep; bar runs {e1.text} toward the label end and {e2.text} toward the back of the socket centre line", [sw, sd, e1, e2]))
        rb = G("phase0_top: ring pocket rib diameter", ("ribd", n, "z", (0, M.CAM_DY, 0), 0.0, M.P0_TOP_Z + M.HEAD_RING_FACE_DZ - M.P0_BAR_Z0 + M.HEAD_RING[2]),
               "phase0_top ring-pocket rib inner faces: 2 x distance from the pocket axis")
        out.append(_row(f"Head-ring pocket ribs leave Ø{rb.text} (as camera_bracket's seat)", [rb]))
    elif n == "phase0_occluder_mount":
        pw = G("phase0_occluder_mount: post bore", s_sub(s_lpl(n, "x", (M.P0_POST_X + 10.2, 0, 9)), s_lpl(n, "x", (M.P0_POST_X - 10.2, 0, 9))), "phase0_occluder_mount post bore faces X")
        sw = G("phase0_occluder_mount: stub bore", s_sub(s_lpl(n, "x", (10.2, L.ARM_TO_CUP, 9)), s_lpl(n, "x", (-10.2, L.ARM_TO_CUP, 9))), "phase0_occluder_mount stub bore faces X")
        dx = G("phase0_occluder_mount: bore centres X", s_sub(("mid", s_lpl(n, "x", (M.P0_POST_X + 10.2, 0, 9)), s_lpl(n, "x", (M.P0_POST_X - 10.2, 0, 9))),
                                                             ("mid", s_lpl(n, "x", (10.2, L.ARM_TO_CUP, 9)), s_lpl(n, "x", (-10.2, L.ARM_TO_CUP, 9)))), "phase0_occluder_mount bore centres X")
        dy = G("phase0_occluder_mount: bore centres Y", s_sub(("mid", s_lpl(n, "y", (0, L.ARM_TO_CUP + 10.2, 9)), s_lpl(n, "y", (0, L.ARM_TO_CUP - 10.2, 9))),
                                                             ("mid", s_lpl(n, "y", (M.P0_POST_X, 10.2, 9)), s_lpl(n, "y", (M.P0_POST_X, -10.2, 9)))), "phase0_occluder_mount bore centres Y")
        out.append(_row(f"Post bore {pw.text} square and stub bore {sw.text} square, centres {dx.text} apart in X and {dy.text} in Y", [pw, sw, dx, dy]))
    return out


Z_PLATE_FACE = M.Z_CAR_FRONT - L.Z_PLATE_T  # z_plate front face Y (locator)
VIEW_OF_AXIS = {"y": "front", "z": "top", "x": "right"}


def _feat_uv(f: dict) -> tuple[float, float]:
    return f["c"][0], f["c"][1]  # (x, z) for 'y', (x, y) for 'z', (y, z) for 'x' = the view's page axes


def _attach(rows_artists, rows):
    for (i, arts) in rows_artists.items():
        for r in rows[i]["recs"]:
            pat = re.compile(r"(?<![\d.])" + re.escape(r.text) + r"(?!\.?\d)")
            for a in arts:
                if pat.search(a.get_text()):
                    r.artist = a
                    break


def choose_scale(X, Y, Z, w, h, ML=18.0, MR=6.0, MB=16.0, MT=6.0, GAP=15.0):
    for sc in STD_SCALES:
        k = sc.k
        if ML + X / k + GAP + Y / k + MR <= w and MB + Z / k + GAP + Y / k + MT <= h:
            return sc
    return STD_SCALES[-1]


def printed_cell(sh: Sheet, geo: Geo, name: str, cell, layout="side", table_w=100.0, scale: Scale | None = None, hidden=True, tsize=FS):
    x0, y0, x1, y1 = cell
    key = "printed/" + name
    info = geo.printed()[name]
    plist = {r["part"]: r for r in json.loads((HERE / "out" / "printed" / "print_list.json").read_text())}[name]
    shape = info["shape"]
    b = bbox(shape)
    X, Y, Z = b[3] - b[0], b[4] - b[1], b[5] - b[2]
    rows = auto_features(geo, name) + custom_rows(geo, name)
    tags = [chr(ord("A") + i) for i in range(len(rows))]
    # header
    hy = y1 - 1.0
    sh.text(x0, hy, name, size=12, weight="bold", va="top")
    hdr_y = hy - 5.6
    note = f"Printed part (P), qty {plist['qty']}, cad/out/printed/{name}.step. Print: {plist['note']}"
    # table geometry
    if layout == "side":
        tx, tw_ = x1 - table_w, table_w
    else:
        tx, tw_ = x0, x1 - x0
    widths = [7.0, tw_ - 7.0]
    chars = max(4, int((widths[1] - 2.4) / (0.53 * tsize * PT)))
    nlines = sum(len(textwrap.wrap(r["text"], chars)) for r in rows) + 1
    t_h = nlines * tsize * PT * 1.35 + 1.2 * (len(rows) + 1) + 2
    hdr_bottom = sh.wrap(x0, hdr_y, note, (x1 - x0), size=FS)
    vy1 = hdr_bottom - 2.0
    if layout == "side":
        vx0, vx1, vy0 = x0, tx - 3.0, y0
    else:
        vx0, vx1, vy0 = x0, x1, y0 + t_h + 2.0
    sc = scale or choose_scale(X, Y, Z, vx1 - vx0, vy1 - vy0)
    k = sc.k
    ML, MB, GAP = 18.0, 16.0, 15.0
    tot_w, tot_h = X / k + GAP + Y / k, Z / k + GAP + Y / k
    fx = vx0 + ML + max(0.0, (vx1 - vx0 - ML - 6.0 - tot_w) / 2)
    fy = vy0 + MB + max(0.0, (vy1 - vy0 - MB - 6.0 - tot_h) / 2)
    vf = make_view(sh, shape, "front", sc, fx, fy, hidden=hidden)
    vt = make_view(sh, shape, "top", sc, fx, fy + Z / k + GAP, hidden=hidden)
    vr = make_view(sh, shape, "right", sc, fx + X / k + GAP, fy, hidden=hidden)
    sh.text(vt.x, vt.y + vt.h + 2.0, f"SCALE {sc}", size=FS, weight="bold")
    rx = G(f"{name}: overall X", ("bb", key, "xlen"), f"{name} exported shape bounding box X")
    ry = G(f"{name}: overall Y", ("bb", key, "ylen"), f"{name} exported shape bounding box Y")
    rz = G(f"{name}: overall Z", ("bb", key, "zlen"), f"{name} exported shape bounding box Z")
    vf.dim((b[0], b[2]), (b[3], b[2]), "h", -7.0, rx)
    vf.dim((b[0], b[2]), (b[0], b[5]), "v", -7.0, rz)
    vt.dim((b[0], b[1]), (b[0], b[4]), "v", -7.0, ry)
    views = {"front": vf, "top": vt, "right": vr}
    region = (vx0, vy0, vx1, vy1)
    for tag, r in zip(tags, rows):
        if "feat" in r:
            f = r["feat"]
            v = views[VIEW_OF_AXIS[f["axis"]]]
            u, w = _feat_uv(f)
            v.balloon((u, w), r["r"], tag, region=region)
        elif r.get("at"):
            ax_l, p_l, rad = r["at"]
            pa = print_axis(name, ax_l)
            q = geo.to_print(name, p_l)
            v = views[VIEW_OF_AXIS[pa]]
            v.balloon(proj(v.name, q), rad, tag, region=region)
    trows = [["", "FEATURES (axes = the STEP file's; positions: see the STEP)"]] + [[t, r["text"]] for t, r in zip(tags, rows)]
    ty = y1 - 1.0 if layout == "side" else y0 + t_h
    if layout == "side":
        ty = hdr_bottom - 1.0
    _, cells = sh.table(tx, ty, trows, widths, size=tsize)
    ra: dict = {}
    for ri, ci, art in cells:
        if ri >= 1:
            ra.setdefault(ri - 1, []).append(art)
    _attach(ra, rows)
    return {"scale": sc, "views": views}


# ------------------------------------------------------------------------------------------------- printed-part sheets
CA = (14.0, TB_Y0 + TB_H + 4.0, PW - 14.0, PH - FR - 3.0)  # content area above the title block
NOTE_AREA = (14.0, 14.0, TB_X0 - 4.0, TB_Y0 + TB_H)  # left of the title block

PRINTED_SHEETS = [
    ("Printed parts: gate posts", [("gate_post_L", (14, 54, 214, 266), "side", 118), ("gate_post_R", (218, 54, 418, 266), "side", 118)]),
    ("Printed parts: X drive", [("x_motor_mount", (14, 160, 214, 266), "side", 92), ("x_bumper_L", (218, 160, 418, 266), "side", 100),
                                ("x_idler_mount", (14, 54, 214, 156), "side", 92), ("x_idler_slider", (218, 54, 418, 156), "side", 100)]),
    ("Printed parts: X carriage", [("x_bracket", (14, 54, 214, 266), "below", None), ("belt_clamp", (218, 160, 418, 266), "side", 100),
                                   ("x_switch_mount", (218, 54, 418, 156), "side", 100)]),
    ("Printed parts: Z axis", [("z_plate", (14, 160, 214, 266), "side", 96), ("z_motor_mount", (218, 160, 418, 266), "side", 96),
                               ("z_end_cap", (14, 54, 214, 156), "side", 96), ("z_switch_mount", (218, 54, 418, 156), "side", 96)]),
    ("Printed parts: head", [("head_foot", (14, 54, 214, 266), "below", None), ("camera_bracket", (218, 54, 418, 266), "below", None)]),
    ("Printed parts: station mount, carry-height sensor", [("station_mount", (14, 54, 160, 266), "below", None),
                                                           ("carry_sensor_mount", (166, 54, 292, 266), "below", None),
                                                           ("carry_flag_arm", (296, 54, 418, 266), "below", None)]),
    ("Printed parts: build and loading tools", [("drill_template", (14, 54, 160, 266), "below", None), ("awl_adapter", (166, 54, 292, 266), "below", None),
                                                ("fill_gauge", (296, 54, 418, 266), "below", None)]),
    ("Printed parts: Phase 0 jig (base, tray)", [("phase0_base", (14, 54, 214, 266), "below", None), ("phase0_tray", (218, 54, 418, 266), "below", None)]),
    ("Printed parts: Phase 0 jig (top, occluder mount)", [("phase0_top", (14, 54, 214, 266), "below", None), ("phase0_occluder_mount", (218, 54, 418, 266), "below", None)]),
]

PRINTED_NOTES = ("Printed parts are drawn as exported (cad/out/printed/<part>.step): print orientation, bounding-box minimum at the "
                 "origin; FRONT looks along +Y, TOP down -Z, RIGHT along -X. Dimensions measured on that shape. Drill M3 holes 3.4 and M5 "
                 "holes 5.5 after printing (BUILD_GUIDE 3.4). Tolerance: see D-00 (PROPOSED).")


def sheet_printed(sh: Sheet, geo: Geo, cells):
    for name, cell, layout, tw_ in cells:
        printed_cell(sh, geo, name, cell, layout=layout, table_w=tw_ or 100.0)
    sh.wrap(NOTE_AREA[0], NOTE_AREA[3] - 1.0, PRINTED_NOTES, NOTE_AREA[2] - NOTE_AREA[0])


# --------------------------------------------------------------------------------------------------------- self-check
def self_check(sheets: list[Sheet]) -> list[str]:
    errs = []
    fresh = Geo()
    # 1. every stated scale exact on the page
    for sh in sheets:
        dpi = sh.fig.dpi
        for v in sh.views:
            pos = v.ax.get_position()
            w_mm, h_mm = pos.width * PW, pos.height * PH
            x0, x1 = v.ax.get_xlim()
            y0, y1 = v.ax.get_ylim()
            if abs((x1 - x0) / w_mm - v.scale.k) > 1e-9 * v.scale.k or abs((y1 - y0) / h_mm - v.scale.k) > 1e-9 * v.scale.k:
                errs.append(f"{sh.num} view {v.name}: axes extent is not {v.scale}")
            a = v.ax.transData.transform([(x0, y0), (x0 + 100.0, y0 + 100.0)])
            want = 100.0 / v.scale.k / 25.4 * dpi
            if abs(a[1][0] - a[0][0] - want) > 1e-6 * want or abs(a[1][1] - a[0][1] - want) > 1e-6 * want:
                errs.append(f"{sh.num} view {v.name}: 100 model mm is not {100 / v.scale.k} paper mm")
    # 2. every dimension: shown, re-measured from fresh geometry, and (linear dims) drawn to its value
    for r in REG.recs:
        if r.artist is None:
            errs.append(f"{r.sheet} {r.label}: not shown on the sheet")
            continue
        txt = r.artist.get_text()
        if not re.search(r"(?<![\d.])" + re.escape(r.text) + r"(?!\.?\d)", txt):
            errs.append(f"{r.sheet} {r.label}: '{r.text}' not in its text '{txt}'")
        try:
            v2 = measure(fresh, r.spec)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{r.sheet} {r.label}: re-measure failed: {e}")
            continue
        drawn = float(r.text)
        if abs(drawn - v2) > 0.05:
            errs.append(f"{r.sheet} {r.label}: drawn {r.text}, re-measured {v2:.3f}")
        if r.p1 is not None and r.axis in ("h", "v"):
            i = 0 if r.axis == "h" else 1
            ln = abs(r.p2[i] - r.p1[i])
            if abs(ln - abs(v2) * r.factor) > 0.05:
                errs.append(f"{r.sheet} {r.label}: dimension line spans {ln:.3f} model mm, value {v2:.3f}")
    return errs


def layout_report(sh: Sheet) -> list[str]:
    """Overlapping text, text off the frame or under the title block, text crossing drawn lines (other than its own dim)."""
    sh.fig.canvas.draw()
    rend = sh.fig.canvas.get_renderer()
    k = 25.4 / sh.fig.dpi
    boxes = []
    for t in sh.fig.findobj(matplotlib.text.Text):
        s = t.get_text()
        if not s.strip() or not t.get_visible():
            continue
        bb = t.get_window_extent(rend)
        r = (bb.x0 * k, bb.y0 * k, bb.x1 * k, bb.y1 * k)
        boxes.append((r, s, getattr(t, "_owner", 0), t.get_fontsize()))
    out = []
    for i, (a, sa, oa, fa) in enumerate(boxes):
        if fa < 9.99:
            out.append(f"small text {fa}pt: {sa[:40]!r}")
        if a[0] < FR - 0.01 or a[2] > PW - FR + 0.01 or a[1] < FR - 0.01 or a[3] > PH - FR + 0.01:
            if not (len(sa) <= 2 and (a[0] < FR or a[2] > PW - FR or a[1] < FR or a[3] > PH - FR)):
                out.append(f"off frame: {sa[:40]!r}")
        if _hit(a, (TB_X0, TB_Y0, TB_X0 + TB_W, TB_Y0 + TB_H)) and not (TB_X0 - 0.5 <= a[0] and a[2] <= TB_X0 + TB_W + 0.5 and TB_Y0 - 0.5 <= a[1] and a[3] <= TB_Y0 + TB_H + 0.5):
            out.append(f"crosses title block: {sa[:40]!r}")
        for j in range(i + 1, len(boxes)):
            b, sb, ob, _ = boxes[j]
            sh_a = (a[0] + 0.3, a[1] + 0.3, a[2] - 0.3, a[3] - 0.3)
            if _hit(sh_a, b):
                out.append(f"overlap: {sa[:30]!r} / {sb[:30]!r}")
    for (a, sa, oa, _) in boxes:
        if len(sa) <= 2:  # zone letters, balloon tags
            continue
        sa_r = (a[0] + 0.4, a[1] + 0.4, a[2] - 0.4, a[3] - 0.4)
        for own, pts in sh.segs:
            if own == oa and oa != 0:
                continue
            xs, ys = pts[:, 0], pts[:, 1]
            if xs.max() < sa_r[0] or xs.min() > sa_r[2] or ys.max() < sa_r[1] or ys.min() > sa_r[3]:
                continue
            if _poly_hits_rect(pts, sa_r):
                out.append(f"line through text: {sa[:40]!r}")
                break
    return out


def _poly_hits_rect(pts, r) -> bool:
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        if _seg_rect(x0, y0, x1, y1, r):
            return True
    return False


def _seg_rect(x0, y0, x1, y1, r) -> bool:
    """Liang-Barsky clip test."""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - r[0]), (dx, r[2] - x0), (-dy, y0 - r[1]), (dy, r[3] - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return t0 <= t1


# --------------------------------------------------------------------------------------------------------------- main
def sheet_list():
    """(number suffix, title, function) in order; printed parts take D-07 onward, the jig is last."""
    s = [("Index and general notes", "index"), ("General arrangement", "ga"), ("Frame and extrusion cut list", "frame"),
         ("Bed, pockets and guide rods", "bed"), ("X axis", "xaxis"), ("Z axis and head stack-up", "zaxis"),
         ("Flat parts (probe flag, carry flag)", "flat")]
    s += [(t, ("printed", cells)) for t, cells in PRINTED_SHEETS]
    s += [("Phase 0 test jig", "jig")]
    return [(f"D-{i:02d}", t, f) for i, (t, f) in enumerate(s)]


SHEET_FUNCS: dict = {}


def main() -> int:
    global REG
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated sheet numbers (dev use; the full set is the deliverable)")
    ap.add_argument("--no-check", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "png").mkdir(exist_ok=True)
    geo = Geo()
    REG = Registry(geo)
    hsh = git_hash()
    plan = sheet_list()
    total = plan[-1][0]
    only = {s.strip() for s in a.only.split(",") if s.strip()}
    sheets: list[Sheet] = []
    for num, title, fn in plan:
        if only and num not in only:
            continue
        REG.sheet = num
        sh = Sheet(num, title, total, hsh)
        sh.frame()
        if isinstance(fn, tuple):
            sheet_printed(sh, geo, fn[1])
        else:
            SHEET_FUNCS[fn](sh, geo, plan)
        sc = sorted(set(sh.scales), key=lambda s: s.k)
        sh.title_block(", ".join(str(s) for s in sc) + (" (as noted)" if len(sc) > 1 else "") if sc else "NONE (not to scale)")
        sheets.append(sh)
        print(f"{num} {title}: drawn ({time.time() - t0:.0f} s)", flush=True)
    pdf_path = OUT / "SlabRail_drawings.pdf"
    with PdfPages(pdf_path, metadata={"Title": "SlabRail drawing set", "Subject": REV}) as pdf:
        for sh in sheets:
            pdf.savefig(sh.fig)
            sh.fig.savefig(OUT / "png" / f"{sh.num}.png", dpi=130)
    print(f"wrote {pdf_path} ({len(sheets)} pages, {time.time() - t0:.0f} s)", flush=True)
    dims = [{"sheet": r.sheet, "label": r.label, "value_mm" if r.unit == "mm" else "value": round(r.value, 4), "unit": r.unit, "drawn": r.text, "source": r.source}
            for r in REG.recs]
    (OUT / "dims.json").write_text(json.dumps(dims, indent=1, ensure_ascii=False) + "\n")
    issues = 0
    for sh in sheets:
        rep = layout_report(sh)
        issues += len(rep)
        for line in rep[:40]:
            print(f"  layout {sh.num}: {line}")
    print(f"layout report: {issues} issues")
    if a.no_check:
        return 0
    errs = self_check(sheets)
    nviews = sum(len(s.views) for s in sheets)
    if errs:
        for e in errs[:60]:
            print("SELF-CHECK FAIL:", e)
        print(f"self-check FAILED: {len(errs)} problems")
        return 1
    print(f"self-check passed: {len(REG.recs)} dimensions re-measured from fresh geometry (0.05 mm), {nviews} view scales exact. "
          f"HLR: {HLR_STATS['computed']} projected ({HLR_STATS['seconds']:.0f} s), {HLR_STATS['cached']} from cache. Total {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
