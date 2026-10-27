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


MODEL_SOURCES = ["cad/model.py", "cad/layout.py", "cad/dims.py", "cad/build.py"]  # what the geometry is built from


def git_hash() -> str:
    """HEAD's short hash, plus '+uncommitted' when the model sources in the working tree differ from HEAD (the sheets then
    show geometry that is not in that commit)."""
    try:
        h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    try:
        dirty = subprocess.run(["git", "status", "--porcelain", "--", *MODEL_SOURCES], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        dirty = ""
    return h + ("+uncommitted" if dirty else "")


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
            fns = {"probe_flag": M.probe_flag, "carry_flag": M.carry_flag, "drill_template": M.drill_template}
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


def _m_pat2(geo, key, axis, d, what, centres):
    """Span along `what` of the axis lines of the holes (axis, d) found nearest each listed centre (page coords of the view)."""
    oth = [c for c in "xyz" if c != axis]
    fs = [f for f in geo.feats(key) if f["axis"] == axis and f["hole"] and abs(f["d"] - d) <= max(0.05, 0.005 * d)]
    vals = []
    for c in centres:
        f = min(fs, key=lambda f: math.hypot(f["c"][0] - c[0], f["c"][1] - c[1]))
        if math.hypot(f["c"][0] - c[0], f["c"][1] - c[1]) > 0.5:
            raise LookupError(f"{key}: no hole d {d} at {c}")
        vals.append(f["c"][oth.index(what)])
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


def _m_layout(geo, name, idx=None):
    return float(getattr(L, name) if idx is None else getattr(L, name)[idx])


def _m_count(geo, src, prefix):
    return float(sum(1 for n in geo.parts(src) if n.startswith(prefix)))


def _m_const(geo, v, why=""):
    """A value quoted from a doc (why names it), combined with geometry in a 'derived' record."""
    return float(v)


def _m_max(geo, a, b):
    return max(measure(geo, a), measure(geo, b))


MEASURES = {"bb": _m_bb, "bbu": _m_bbu, "cyl": _m_cyl, "plane": _m_plane, "pat": _m_pat, "pat2": _m_pat2, "sub": _m_sub, "add": _m_add,
            "mul": _m_mul, "flag": _m_flag, "layout": _m_layout, "count": _m_count, "const": _m_const, "max": _m_max}

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
def fmt(v: float, res: float = 0.01) -> str:
    """res 0.01: shown to 0.1 when the measured value is within 0.012 of it (the model's 0.01 mm overlaps, e.g. 9.99 -> 10),
    else to 0.01. res 0.1 (printed parts): to the nearest 0.1, a whole number when within 0.05 of one. The self-check still
    holds every shown value to 0.05 of the geometry."""
    if res >= 0.1:
        s = f"{round(v):d}" if abs(v - round(v)) < 0.05 else f"{round(v, 1):.1f}"
        return "0" if s in ("-0", "-0.0") else s
    if abs(v - round(v)) < 0.012:
        s = f"{round(v):d}"
    elif abs(v - round(v, 1)) < 0.012:
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
        self.res = 0.01  # display resolution of this sheet's values (0.1 on the printed-part sheets)

    def g(self, label: str, spec, src: str, unit: str = "mm", kind: str = "geometry") -> Rec:
        """A geometry measurement (kind 'derived': geometry or layout combined with a value quoted from a doc, spec 'const')."""
        v = measure(self.geo, spec)
        r = Rec(self.sheet, label, v, f"{kind}:" + src, fmt(v, self.res), spec, unit)
        self.recs.append(r)
        return r

    def c(self, name: str, label: str | None = None, unit: str = "mm", idx: int | None = None) -> Rec:
        """A layout.py constant (idx: element of a tuple constant)."""
        v = float(getattr(L, name) if idx is None else getattr(L, name)[idx])
        src = f"layout.{name}" if idx is None else f"layout.{name}[{idx}]"
        r = Rec(self.sheet, label or (name if idx is None else f"{name}[{idx}]"), v, src, fmt(v, self.res), ("layout", name, idx), unit)
        self.recs.append(r)
        return r


REG: Registry  # set in main()


def G(label, spec, src, unit="mm", kind="geometry") -> Rec:
    return REG.g(label, spec, src, unit, kind)


def C(name, label=None, unit="mm", idx=None) -> Rec:
    return REG.c(name, label, unit, idx)


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
        self.last_wrap = [self.text(x, y - i * size * PT * lh, ln, size=size, va="top", **kw) for i, ln in enumerate(lines)]
        return y - len(lines) * size * PT * lh

    def note(self, x, y, s, recs=(), **kw):
        """Single-line text that carries dimension values (recs)."""
        t = self.text(x, y, s, **kw)
        attach_recs([t], recs)
        return t

    def wrap_recs(self, x, y, s, width_mm, recs=(), **kw) -> float:
        yb = self.wrap(x, y, s, width_mm, **kw)
        attach_recs(self.last_wrap, recs)
        return yb

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

    def polys(self, polys, lw=LW_VIS, color=INK, ls="-", track=True, clip=False):
        if not polys:
            return
        lc = LineCollection([p for p in polys], linewidths=lw, colors=color, linestyles=ls, clip_on=clip, capstyle="round")
        self.ax.add_collection(lc)
        if track:
            for p in polys:
                pp = np.column_stack([self.x + (p[:, 0] - self.u0) / self.k, self.y + (p[:, 1] - self.v0) / self.k])
                if clip:
                    pp = pp[(pp[:, 0] >= self.x - 0.01) & (pp[:, 0] <= self.x + self.w + 0.01) & (pp[:, 1] >= self.y - 0.01) & (pp[:, 1] <= self.y + self.h + 0.01)]
                    if len(pp) < 2:
                        continue
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
    def dim(self, p1, p2, axis: str, off: float, rec: Rec, pre: str = "", post: str = "", text_at: str | None = None, flip_text=False,
            over: float = 2.0, text_du: float = 0.0):
        """Linear dimension between model points p1, p2 measured along axis 'h' (page x) or 'v' (page y). The dimension line
        sits off paper mm beyond the outermost point (sign = side). The value printed is rec.text. over: extension-line
        overshoot past the dimension line (paper mm); text_du: shift of a centred 'h' text along the line (paper mm)."""
        k = self.k
        own = self.sheet.owner()
        (u1, v1), (u2, v2) = p1, p2
        gap = 1.0
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
                t = self.text((a + b) / 2 + text_du * k, vl + 0.9 * k, s, ha="center", va="bottom", owner=own)
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
            # a short span: the text is taller than the gap between the extension lines, so clear their overshoot
            tx = over + 1.0 if span < th() + 1.5 and (side == "left") == (sg < 0) else 1.0
            if side == "left":
                t = self.text(ul - tx * k, (a + b) / 2, s, ha="right", va="center", owner=own)
            else:
                t = self.text(ul + tx * k, (a + b) / 2, s, ha="left", va="center", owner=own)
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
        # dimension, leader and centre lines already drawn (not the views' own edges, owner -1): a balloon must not sit on one,
        # and its leader must not cross a dimension or another leader (owner > 0)
        lines = [pts for o, pts in self.sheet.segs if o != -1]
        dims_ = [pts for o, pts in self.sheet.segs if o > 0]
        mine = [pts for o, pts in self.sheet.segs if o == -1 and _hit((pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()), vb)]
        own_edges = np.vstack([np.hstack([p_[:-1], p_[1:]]) for p_ in mine]) if mine else np.zeros((0, 4))
        for dist in (5.5, 8.0, 11.0, 14.0, 18.0, 23.0, 30.0, 38.0, 48.0):
            for a in angs:
                cx = x0 + (r_pap + dist) * math.cos(math.radians(a))
                cy = y0 + (r_pap + dist) * math.sin(math.radians(a))
                rr = (cx - R - 0.4, cy - R - 0.4, cx + R + 0.4, cy + R + 0.4)
                if not (reg[0] <= rr[0] and rr[2] <= reg[2] and reg[1] <= rr[1] and rr[3] <= reg[3]):
                    continue
                if any(_hit(rr, o) for o in self.sheet.occ if o != vb):
                    continue
                rl = (rr[0] - 0.6, rr[1] - 0.6, rr[2] + 0.6, rr[3] + 0.6)  # a clear 1 mm round the balloon
                if any(_poly_hits_rect(pts, rl) for pts in lines):
                    continue
                # nor may its leader cross a dimension's text
                la, lb = (x0 + r_pap * math.cos(math.radians(a)), y0 + r_pap * math.sin(math.radians(a))), (cx, cy)
                if any(_seg_rect(la[0], la[1], lb[0], lb[1], o) for o in self.sheet.occ if o != vb and not _hit(o, vb)):
                    continue
                if any(_seg_cross(la, lb, q0, q1) for pts in dims_ for q0, q1 in zip(pts[:-1], pts[1:])):
                    continue
                inview = _hit(rr, vb)
                # each crossing of the part's own outline past the first (the way out of the view) costs as much as 6 mm more leader
                ncross = _count_cross(la, lb, own_edges)
                score = dist + (40.0 if inview and avoid_view else 0.0) + 6.0 * max(0, ncross - (0 if inview else 1))
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


def _count_cross(a, b, segs: np.ndarray) -> int:
    """How many of the segments (N x 4: x0 y0 x1 y1) the segment ab properly crosses."""
    if len(segs) == 0:
        return 0
    c, d = segs[:, 0:2], segs[:, 2:4]
    def orient(p, q, r):
        return (q[..., 0] - p[..., 0]) * (r[..., 1] - p[..., 1]) - (q[..., 1] - p[..., 1]) * (r[..., 0] - p[..., 0])
    A, Bv = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    o1, o2 = orient(A, Bv, c), orient(A, Bv, d)
    o3, o4 = orient(c, d, A), orient(c, d, Bv)
    return int(np.count_nonzero((o1 * o2 < 0) & (o3 * o4 < 0)))


def _seg_cross(a, b, c, d) -> bool:
    """Do the segments ab and cd cross (proper intersection)?"""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0


def _hit(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def make_view(sheet: Sheet, shape, vname: str, scale: Scale, x: float, y: float, label=None, hidden=True, lw=LW_VIS,
              window=None, hid_color=HIDDEN, color=INK, defl=None, clip=False, breaks=True) -> View:
    """clip: cut the drawing at the window; breaks: then mark each place an edge leaves the window with a break line."""
    shape = _wrapped(shape)
    win = window or proj_box(vname, bbox(shape))
    v = View(sheet, vname, win, scale, x, y, label)
    vis, hid = hlr(shape, vname, defl or max(0.01, 0.03 * scale.k))
    if hidden:
        v.polys(hid, lw=LW_HID, color=hid_color, ls=DASH_HID, track=False, clip=clip)
    v.polys(vis, lw=lw, color=color, clip=clip)
    v.vis, v.hid = vis, hid
    if clip and breaks:
        break_marks(v)
    return v


def break_marks(v: View, amp: float = 0.8, wave: float = 4.0, cluster: float = 45.0):
    """Thin wavy break lines along the window edges where the view's visible edges are cut off (clipped views); cuts less
    than `cluster` model mm apart (one extrusion's two faces) share one line."""
    k = v.k
    edges = {"bottom": (1, v.v0, -1, (v.u0, v.u1)), "top": (1, v.v1, 1, (v.u0, v.u1)), "left": (0, v.u0, -1, (v.v0, v.v1)),
             "right": (0, v.u1, 1, (v.v0, v.v1))}  # (page axis, window line, outside sign, extent along the line)
    for _, (ax, c, sg, (lo, hi)) in edges.items():
        hits = []
        for p in v.vis:
            for p0, p1 in zip(p[:-1], p[1:]):
                d0, d1 = sg * (p0[ax] - c), sg * (p1[ax] - c)  # > 0: outside the window
                if not ((d0 > 1e-6) != (d1 > 1e-6)) or max(d0, d1) <= 1e-6:
                    continue  # both outside, or both inside / on the line: not cut here
                t = d0 / (d0 - d1)
                w = p0[1 - ax] + t * (p1[1 - ax] - p0[1 - ax])
                if lo + 1e-6 < w < hi - 1e-6:
                    hits.append(w)
        if not hits:
            continue
        hits.sort()
        groups = [[hits[0], hits[0]]]
        for w in hits[1:]:
            if w - groups[-1][1] < cluster:
                groups[-1][1] = w
            else:
                groups.append([w, w])
        for g0, g1 in groups:
            w0, w1 = max(lo, g0 - 1.5 * k), min(hi, g1 + 1.5 * k)
            ws = np.linspace(w0, w1, max(8, int((w1 - w0) / k / 0.5)))
            off = amp * k * np.sin(2 * math.pi * (ws - w0) / (wave * k))
            pts = np.column_stack([ws, c + off]) if ax == 1 else np.column_stack([c + off, ws])
            v.polys([pts], lw=0.35, track=False)


HATCH = {"printed": "//", "purchased": "\\\\", "made": "xx", "wood": "--"}  # per part kind; slabs (clear acrylic) are not hatched


def section_half(shape, x_cut: float):
    """The part of shape at X <= x_cut: what a section on the plane X = x_cut shows when seen from +X ('right' view)."""
    big = 5000.0
    c = cq.Shape.cast(_wrapped(shape)).intersect(cq.Solid.makeBox(big, 2 * big, 2 * big, pnt=cq.Vector(x_cut - big, -big, -big)))
    return c if c.Volume() > 1e-6 else None


def _wire_yz(w, defl: float) -> np.ndarray:
    from OCP.BRepAdaptor import BRepAdaptor_CompCurve

    q = GCPnts_QuasiUniformDeflection(BRepAdaptor_CompCurve(w), defl)
    return np.array([(q.Value(i).Y(), q.Value(i).Z()) for i in range(1, q.NbPoints() + 1)])


def hatch_section(view: View, halves: list, x_cut: float, defl: float = 0.05):
    """Hatch the cut faces (planar, on X = x_cut) of the section halves [(shape, kind)] in a 'right' view."""
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MPath
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_WIRE

    for shp, kind in halves:
        hatch = HATCH.get(kind)
        if hatch is None:
            continue
        for f in shp.Faces():
            if f.geomType() != "PLANE" or abs(abs(f.normalAt().x) - 1) > 1e-6 or abs(f.Center().x - x_cut) > 1e-6:
                continue
            outer = BRepTools.OuterWire_s(f.wrapped)
            verts, codes = [], []
            exp = TopExp_Explorer(f.wrapped, TopAbs_WIRE)
            while exp.More():
                w = TopoDS.Wire_s(exp.Current())
                exp.Next()
                pts = _wire_yz(w, defl)
                area = 0.5 * float(np.sum(pts[:-1, 0] * pts[1:, 1] - pts[1:, 0] * pts[:-1, 1]))
                if (area < 0) == w.IsSame(outer):  # outer loop counter-clockwise, holes clockwise
                    pts = pts[::-1]
                verts += [tuple(p) for p in pts] + [tuple(pts[0])]
                codes += [MPath.MOVETO] + [MPath.LINETO] * (len(pts) - 1) + [MPath.CLOSEPOLY]
            view.ax.add_patch(PathPatch(MPath(verts, codes), facecolor="none", edgecolor="#444444", lw=0, hatch=hatch, clip_on=False))


def cutting_plane(view: View, u: float, letter: str, direction: int = -1, ext: float = 6.0):
    """Cutting-plane ends (thick strokes outside the view, top and bottom) at page x = u of a front view, arrows pointing
    along the line of sight (direction -1 = toward -X) and the section letter."""
    k = view.k
    lo, hi = view.v0, view.v1
    own = -3
    for v0_, v1_ in ((hi + 1.0 * k, hi + ext * k), (lo - 1.0 * k, lo - ext * k)):
        view.seg((u, v0_), (u, v1_), lw=1.4, owner=own)
        tip = (u + direction * 7.0 * k, v1_)
        view.seg((u, v1_), tip, lw=0.6, owner=own)
        view.arrow(tip, (direction, 0), own)
        view.text(tip[0] + direction * 2.8 * k, v1_, letter, ha="center", va="center", weight="bold")


def spread(desired: list[float], gap: float, lo: float = -1e9, hi: float = 1e9) -> list[float]:
    """Positions as near the desired ones as possible, in the same order, at least gap apart (clusters centred)."""
    order = sorted(range(len(desired)), key=lambda i: desired[i])
    clusters = [[i] for i in order]
    pos = {i: desired[i] for i in order}

    def place(cl):
        c = sum(desired[i] for i in cl) / len(cl)
        start = c - gap * (len(cl) - 1) / 2
        start = min(max(start, lo), hi - gap * (len(cl) - 1))
        for j, i in enumerate(cl):
            pos[i] = start + j * gap

    changed = True
    while changed:
        changed = False
        for cl in clusters:
            place(cl)
        for a in range(len(clusters) - 1):
            if pos[clusters[a + 1][0]] - pos[clusters[a][-1]] < gap - 1e-9:
                clusters[a] = clusters[a] + clusters[a + 1]
                del clusters[a + 1]
                changed = True
                break
    return [pos[i] for i in range(len(desired))]


def ordinates_v(view: View, items, u_from: float, x_text: float, gap: float = 4.6, side: str = "right", lo=None, hi=None, style: str = "arrow"):
    """Height labels: items = (v_model, text, recs), the labels spread at least gap apart at x_text (paper).
    style 'arrow': an arrow at (u_from, v), for a line that is itself the feature (an edge the view shows running to u_from).
    style 'scale': a height scale 3 mm outside the view at u_from, ticked at each height (no arrowheads, nothing touching the
    view's geometry), for heights of features inside an assembly view; each label names its feature."""
    sh = view.sheet
    ys = [view.P(u_from, v)[1] for v, _, _ in items]
    ty = spread(ys, gap, lo if lo is not None else -1e9, hi if hi is not None else 1e9)
    x0 = view.P(u_from, 0)[0]
    sg = 1 if side == "right" else -1
    if style == "scale":
        xb = x0 + sg * 3.0
        sh.line([(xb, min(ys) - 1.5), (xb, max(ys) + 1.5)], lw=0.5, owner=-3)
    for (v, txt, recs), y, yt in zip(items, ys, ty):
        own = sh.owner()
        if style == "scale":
            xa = x_text - sg * 4.5
            sh.line([(xb - sg * 1.3, y), (xb + sg * 1.3, y)], lw=0.6, owner=-3)  # the tick
            sh.line([(xb + sg * 1.3, y), (xa, y), (x_text - sg * 1.0, yt)], lw=LW_THIN, owner=own)
        else:
            xa = x_text - sg * 7.0
            sh.line([(x0 + sg * 1.0, y), (xa, y), (x_text - sg * 1.5, yt)], lw=LW_THIN, owner=own)
            sh.pg.add_patch(Polygon([(x0 + sg * 1.0, y), (x0 + sg * 3.2, y + 0.5), (x0 + sg * 3.2, y - 0.5)], closed=True, color=INK, clip_on=False))
        t = sh.text(x_text, yt, txt, ha="left" if side == "right" else "right", va="center", owner=own)
        for r in recs:
            r.artist, r.view = t, view
    return ty


def ordinates_h(view: View, items, v_from: float, y_text: float, gap: float = 4.6, side: str = "below"):
    """X labels, text vertical: items = (u_model, text, recs); leader from (u, v_from) to the text at y_text (paper)."""
    sh = view.sheet
    xs = [view.P(u, v_from)[0] for u, _, _ in items]
    tx = spread(xs, gap)
    y0 = view.P(0, v_from)[1]
    sg = -1 if side == "below" else 1
    for (u, txt, recs), x, xt in zip(items, xs, tx):
        own = sh.owner()
        ya = y_text - sg * 6.0
        sh.line([(x, y0 + sg * 1.0), (x, ya), (xt, y_text - sg * 1.5)], lw=LW_THIN, owner=own)
        t = sh.text(xt, y_text, txt, ha="center", va="top" if side == "below" else "bottom", rot=90, owner=own,
                    rotation_mode="anchor") if False else sh.pg.text(xt, y_text, txt, fontsize=FS, rotation=90, ha="center", va="top" if side == "below" else "bottom", clip_on=False)
        t._owner = own  # noqa: SLF001
        w = tw(txt)
        sh.occ.append((xt - 2.0, y_text - w if side == "below" else y_text, xt + 2.0, y_text if side == "below" else y_text + w))
        for r in recs:
            r.artist, r.view = t, view
    return tx


def asm_compound(geo: Geo, src: str, keep=None, drop_kinds=("fastener", "slab"), drop=("gate_beam", "light_roof")):
    parts = geo.parts(src)
    return compound([p.shape for n, p in parts.items() if (keep is None or keep(n, p)) and p.kind not in drop_kinds and n not in drop])


def akey(name: str, src: str = "home") -> str:
    return f"asm/{src}/{name}"


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
        dist = math.hypot(p[oth[0]] - f["c"][0], p[oth[1]] - f["c"][1]) + max(0.0, f["lo"] - p[k], p[k] - f["hi"])
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
            key=lambda f: math.hypot(p[oth[0]] - f["c"][0], p[oth[1]] - f["c"][1]) + max(0.0, f["lo"] - p[k], p[k] - f["hi"]))
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
                       ("z", 2.2): "head camera board (ELP, 32 x 32 pattern about the lens axis [Guessing], BUILD_GUIDE 3.3), M2 + nuts"},
    "phase0_top": {("z", 42.8): "head LED ring pocket (ribbed)", ("z", 1.8): "M2 standoffs, blind"},
    "z_plate": {("z", 2.5): "carry_flag_arm, M3x10 self-tapping", ("y", 10.5): "T8 nut body clearance"},
    "carry_flag_arm": {("y", 2.5): "carry flag, M3x8 self-tapping"},
    "awl_adapter": {("z", 3.1): "3 mm steel pin, pressed in + CA"},
    "x_idler_mount": {("y", 5.3): "M5 idler axle (tension travel)"},
    "x_motor_mount": {("z", 9.5): "M5 head, sunk: 1x, at the stop-end M5 hole only"},
    "x_bracket": {("y", 3.4): "belt_clamp caps, 2 x M3x12 + nut per cap (BUILD_GUIDE 6.5)"},
    "head_foot": {("x", 3.4): "endstop board M3 slots (trip adjustment)"},
}
PART_HOLE_EXTENT = {  # (print axis, diameter) -> how far the hole runs, where "THRU" would mislead
    "gate_post_L": {("y", 2.5): "from the +Y face into the barrel bore"},
    "gate_post_R": {("y", 2.5): "from the +Y face into the barrel bore"},
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


def _pattern_text(geo, key, axis, d, centres) -> tuple[str, list[Rec]]:
    """Pattern of distinct hole centres (view coordinates): '35 apart in Y', 'on 20 x 25 (X x Y)', 'centres over 92 in X'."""
    oth = [c for c in "xyz" if c != axis]
    n = len(centres)
    if n < 2:
        return "", []
    us = sorted({round(c[0], 2) for c in centres})
    vs = sorted({round(c[1], 2) for c in centres})
    cs = tuple((round(c[0], 4), round(c[1], 4)) for c in centres)
    recs = []
    nm = key.split("/", 1)[1]
    for i, (vals, o) in enumerate(((us, oth[0]), (vs, oth[1]))):
        if len(vals) > 1:
            recs.append(G(f"{nm}: {n}x d{fmt(d)} along {axis}: centre span in {o.upper()}", ("pat2", key, axis, d, o, cs),
                          f"{nm} {n} holes d{fmt(d)} along {axis}: centre span {o.upper()}"))
    grid = len(us) * len(vs) == n
    if len(recs) == 1:
        lab = oth[0] if len(us) > 1 else oth[1]
        txt = f"{recs[0].text} apart in {lab.upper()}" if n == 2 else f"centres over {recs[0].text} in {lab.upper()}"
    else:
        txt = (f"on {recs[0].text} x {recs[1].text} ({oth[0].upper()} x {oth[1].upper()})" if grid else
               f"centres spread over {recs[0].text} x {recs[1].text} ({oth[0].upper()} x {oth[1].upper()}), not a grid")
    return txt, recs


def auto_features(geo: Geo, name: str) -> list[dict]:
    """Rows for the feature table: hole groups (diameter + axis), slots, bosses; each with its numbers as Recs and a
    representative feature to balloon."""
    key = "printed/" + name
    solid = geo.shape(key)
    rows = []
    feats = geo.feats(key)
    by_ad: dict = {}
    for f in feats:
        if f["hole"] and f["span"] > 4.6:  # full bores (and bores broken only by ribs or a notch)
            by_ad.setdefault((f["axis"], round(f["d"], 2)), []).append(f)
    items = []  # a hole = one axis line; runs through several walls on one line count as one THRU hole
    for (axis, dd), fs in by_ad.items():
        lines: dict = {}
        for f in fs:
            lines.setdefault((round(f["c"][0], 2), round(f["c"][1], 2)), []).append(f)
        for c, runs in lines.items():
            deps = [hole_depth(solid, r) for r in runs]
            if len(runs) > 1 and all(dp is None for dp in deps):
                items.append({"axis": axis, "d": dd, "rep": max(runs, key=lambda r: r["hi"] - r["lo"]), "c": runs[0]["c"], "depth": None, "runs": len(runs),
                              "intr": any(r["span"] < 6.2 for r in runs)})
            else:
                for r, dp in zip(runs, deps):
                    items.append({"axis": axis, "d": dd, "rep": r, "c": r["c"], "depth": dp, "runs": 1, "intr": r["span"] < 6.2})
    groups: dict = {}
    for it in items:
        groups.setdefault((it["axis"], it["d"], None if it["depth"] is None else round(it["depth"], 2), it["runs"]), []).append(it)
    order = sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], min(i["rep"]["lo"] for i in kv[1])))
    seen: dict = {}
    for (axis, dd, dep, runs), its in order:
        idx = seen.get((axis, dd), 0)
        seen[(axis, dd)] = idx + 1
        its = sorted(its, key=lambda i: (round(i["c"][0], 2), round(i["c"][1], 2)))
        rep = its[0]["rep"]
        near = _axis_point(rep, (rep["lo"] + rep["hi"]) / 2)
        rd = G(f"{name}: hole d{dd} along {axis}: diameter", ("cylk", key, axis, rep["d"], tuple(near), "d"), f"{name} hole along {axis}: cylinder diameter")
        recs = [rd]
        ov = next((t for (a_, d_), t in PART_HOLE_EXTENT.get(name, {}).items() if a_ == axis and abs(d_ - dd) < 0.02), None)
        if ov is not None:
            dtxt = ov  # open at both ends, but not through the part (e.g. from an outer face into a bore)
        elif dep is None:
            dtxt = "THRU" + (f" ({runs} walls on one axis)" if runs > 1 else "")
        else:
            r = G(f"{name}: hole d{dd} along {axis}: depth", ("hdepth", key, axis, rep["d"], tuple(near)), f"{name} blind hole along {axis}: cylinder length")
            recs.append(r)
            dtxt = f"x {r.text} deep"
        if any(i["intr"] for i in its):
            dtxt += ", interrupted"
        ptxt, precs = _pattern_text(geo, key, axis, rep["d"], [i["c"] for i in its])
        recs += precs
        n = len(its)
        txt = (f"{n}x " if n > 1 else "") + f"Ø{rd.text} {dtxt}, axis {axis.upper()}" + (f", {ptxt}" if ptxt else "") + f": {_use(name, axis, rep['d'], idx=idx)}"
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
        if not f["hole"] and f["span"] > 4.6 and f["d"] >= 4.0:  # full bosses, and bosses merged into a wall on one side
            bgroups.setdefault((f["axis"], round(f["d"], 2)), []).append(f)
    for (axis, dd), bs in sorted(bgroups.items()):
        bs = sorted(bs, key=lambda h: (round(h["c"][0], 2), round(h["c"][1], 2)))
        rep = bs[0]
        near = _axis_point(rep, (rep["lo"] + rep["hi"]) / 2)
        rd = G(f"{name} boss d{dd} along {axis}: diameter", ("cylk", key, axis, rep["d"], tuple(near), "d", False), f"{name} outer cylinder along {axis}: diameter")
        rh = G(f"{name} boss d{dd} along {axis}: length", ("cylk", key, axis, rep["d"], tuple(near), "len", False), f"{name} outer cylinder along {axis}: length")
        n = len(bs)
        part = ", part-round (joins the wall)" if any(h["span"] < 6.2 for h in bs) else ""
        txt = (f"{n}x " if n > 1 else "") + f"Ø{rd.text} x {rh.text} long (outside){part}, axis {axis.upper()}: {_use(name, axis, rep['d'], hole=False)}"
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
        cx_, cy_, zu = M.CLAMP_X, M.CLAMP_SCREW_Y[0], zf - 8.7  # locators: a clamp screw and the tab underside (model.x_bracket)
        hx = [h for h in geo.feats("printed/" + n) if h["hole"] and abs(h["d"] - M.M3_CLR) < 0.05 and h["axis"] == print_axis(n, "z")]
        if hx:  # the tab's nut traps exist only with the clamp holes (model.py fix)
            af = G("x_bracket: tab nut trap across flats", s_sub(s_lpl(n, "y", (cx_, cy_ + 2.9, zu + 1.3)), s_lpl(n, "y", (cx_, cy_ - 2.9, zu + 1.3))),
                   "x_bracket nut-trap flats Y")
            dp = G("x_bracket: tab nut trap depth", s_sub(s_lpl(n, "z", (cx_ + 2.0, cy_, zu + 2.6)), s_lpl(n, "z", (cx_ + 8.0, cy_, zu))),
                   "x_bracket nut-trap floor Z - tab underside Z")
            out.append(_row(f"4x M3 nut trap, hex {af.text} across flats x {dp.text} deep, in the tab underside under the belt_clamp holes", [af, dp]))
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
        lz = G("phase0_tray: recess lead-in depth (Z)", ("chamfer", n, (41.15, 0, 3.5), "z"), "phase0_tray recess lead-in 45-deg face: Z extent")
        lx = G("phase0_tray: recess lead-in width (X)", ("chamfer", n, (41.15, 0, 3.5), "x"), "phase0_tray recess lead-in 45-deg face: X extent")
        out.append(_row(f"45° lead-in round the top edge of the recess, {lx.text} wide x {lz.text} deep", [lx, lz]))
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


def attach_recs(arts, recs):
    for r in recs:
        pat = re.compile(r"(?<![\d.])" + re.escape(r.text) + r"(?!\.?\d)")
        for a in arts:
            if pat.search(a.get_text()):
                r.artist = a
                break


def _attach(rows_artists, rows):
    for (i, arts) in rows_artists.items():
        for r in rows[i]["recs"]:
            pat = re.compile(r"(?<![\d.])" + re.escape(r.text) + r"(?!\.?\d)")
            for a in arts:
                if pat.search(a.get_text()):
                    r.artist = a
                    break


def _extra_fill_gauge(sh: Sheet, geo: Geo, n: str, views: dict, b, ry: Rec):
    """fill_gauge lies flat in its print orientation, so its TOP view shows it full length, foot at the top: name both ends and
    dimension the MAX line and the first counting notch from the foot (the face that stands on the pad)."""
    vt = views["top"]
    tp = lambda x, z: proj("top", geo.to_print(n, (x, 2.0, z)))  # noqa: E731 - a model.py-frame point (Y mid-thickness) in the view
    foot_l, foot_r = tp(0.0, 0.0), tp(12.0, 0.0)
    bar_ul, bar_end = tp(30.0, L.MAX_LINE), tp(30.0, L.MAX_LINE + 4.0)
    notch = tp(0.0, 5 * L.SLAB_T)
    mx = G("fill_gauge: MAX line (bar underside) above the foot, drawn", s_sub(s_lpl(n, "z", (20, 2, L.MAX_LINE)), s_lpl(n, "z", (8, 2, 0))),
           "fill_gauge top-bar underside Z - foot Z")
    pt = G("fill_gauge: first counting notch above the foot, drawn", s_sub(s_lpl(n, "z", (1.5, 2, 5 * L.SLAB_T)), s_lpl(n, "z", (8, 2, 0))),
           "fill_gauge notch floor Z - foot Z")
    vt.dim(foot_r, bar_ul, "v", 24.0, mx, post=" MAX line")  # right of the bar end, room for the FOOT note inside it
    vt.dim(foot_l, (foot_l[0], bar_end[1]), "v", -16.0, ry)  # overall, left, outside the notch dimension
    vt.dim(foot_l, notch, "v", -5.0, pt)
    vt.leader((foot_r[0], foot_r[1] - 3.0), 3.0, -6.0, ["FOOT", "(on the pad)"])
    vt.leader((bar_ul[0] - 8.0, bar_end[1]), 10.0, -6.0, ["TOP BAR (underside = MAX line)"])


PART_EXTRA = {"fill_gauge": _extra_fill_gauge}


def _auto_at(name: str, recs) -> tuple | None:
    """Where to balloon a custom row that names no feature: the locator of its first measurement on this part. A cylinder is
    ballooned end-on (its own axis), a planar face edge-on (a view along Y, or Z for a face normal to Y), a chamfer edge-on,
    a rib ring at its circle, a cone dimple from above. Returns (axis_local, point_local, radius) or None."""
    def walk(spec):
        if not isinstance(spec, tuple) or not spec or not isinstance(spec[0], str):
            return None
        k = spec[0]
        if k == "lcyl" and spec[1] == name:
            return (spec[2], spec[4], spec[3] / 2)
        if k == "lplane" and spec[1] == name:
            return ("y" if spec[2] != "y" else "z", spec[3], 0.0)
        if k == "chamfer" and spec[1] == name:
            return ("y" if spec[3] != "y" else "x", spec[2], 0.0)
        if k == "ribd" and spec[1] == name:
            c = list(spec[3])
            c[AX[spec[2]]] = spec[5]
            return (spec[2], tuple(c), None)
        if k == "cone" and spec[1] == "printed/" + name:
            return ("z", spec[2], 3.0)
        for sub in spec[1:]:
            w = walk(sub)
            if w:
                return w
        return None

    for r in recs:
        w = walk(r.spec)
        if w:
            return (w[0], w[1], r.value / 2) if w[2] is None else w
    return None


def choose_scale(X, Y, Z, w, h, ML=16.0, MR=4.0, MB=15.0, MT=5.0, GAP=13.0):
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
    ML, MB, GAP = 16.0, 15.0, 13.0
    tot_w, tot_h = X / k + GAP + Y / k, Z / k + GAP + Y / k
    fx = vx0 + ML + max(0.0, (vx1 - vx0 - ML - 4.0 - tot_w) / 2)
    fy = vy0 + MB + max(0.0, (vy1 - vy0 - MB - 5.0 - tot_h) / 2)
    vf = make_view(sh, shape, "front", sc, fx, fy, hidden=hidden)
    vt = make_view(sh, shape, "top", sc, fx, fy + Z / k + GAP, hidden=hidden)
    vr = make_view(sh, shape, "right", sc, fx + X / k + GAP, fy, hidden=hidden)
    sh.text(vt.x, vt.y + vt.h + 2.0, f"TOP     SCALE {sc}", size=FS, weight="bold")
    sh.text(vf.x + vf.w / 2, vf.y - 10.5, "FRONT", size=FS, weight="bold", ha="center", va="top")
    sh.text(vr.x + vr.w / 2, vr.y - 10.5, "RIGHT", size=FS, weight="bold", ha="center", va="top")
    rx = G(f"{name}: overall X", ("bb", key, "xlen"), f"{name} exported shape bounding box X")
    ry = G(f"{name}: overall Y", ("bb", key, "ylen"), f"{name} exported shape bounding box Y")
    rz = G(f"{name}: overall Z", ("bb", key, "zlen"), f"{name} exported shape bounding box Z")
    vf.dim((b[0], b[2]), (b[3], b[2]), "h", -7.0, rx)
    vf.dim((b[0], b[2]), (b[0], b[5]), "v", -7.0, rz)
    views = {"front": vf, "top": vt, "right": vr}
    if name in PART_EXTRA:
        PART_EXTRA[name](sh, geo, name, views, b, ry)  # draws the overall Y dimension itself
    else:
        vt.dim((b[0], b[1]), (b[0], b[4]), "v", -7.0, ry)
    region = (vx0, vy0, vx1, vy1)
    for tag, r in zip(tags, rows):
        if "feat" in r:
            f = r["feat"]
            v = views[VIEW_OF_AXIS[f["axis"]]]
            u, w = _feat_uv(f)
            v.balloon((u, w), r["r"], tag, region=region)
        elif r.get("at") or _auto_at(name, r["recs"]):
            ax_l, p_l, rad = r.get("at") or _auto_at(name, r["recs"])
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

L2 = (14, 54, 214, 266)  # left / right half of the content area
R2 = (218, 54, 418, 266)
TL, TR, BL, BR = (14, 160, 214, 266), (218, 160, 418, 266), (14, 54, 214, 156), (218, 54, 418, 156)
PRINTED_SHEETS = [
    ("Printed parts: gate posts", [("gate_post_L", L2, "side", 118), ("gate_post_R", R2, "side", 118)]),
    ("Printed parts: X drive", [("x_motor_mount", TL, "side", 92), ("x_bumper_L", TR, "side", 100), ("x_idler_mount", BL, "side", 92),
                                ("x_idler_slider", BR, "side", 100)]),
    ("Printed parts: X carriage", [("x_bracket", L2, "below", None), ("belt_clamp", TR, "side", 100), ("x_switch_mount", BR, "side", 100)]),
    ("Printed parts: Z carriage plate, Z motor mount", [("z_plate", L2, "below", None), ("z_motor_mount", R2, "below", None)]),
    ("Printed parts: Z end cap, Z switch mount, carry-height sensor", [("z_end_cap", TL, "side", 92), ("z_switch_mount", TR, "side", 100),
                                                                      ("carry_sensor_mount", BL, "side", 92), ("carry_flag_arm", BR, "side", 90)]),
    ("Printed parts: head", [("head_foot", L2, "below", None), ("camera_bracket", R2, "below", None)]),
    ("Printed parts: station mount, drill template", [("station_mount", L2, "below", None), ("drill_template", R2, "below", None)]),
    ("Printed parts: awl adapter, fill gauge", [("awl_adapter", L2, "below", None), ("fill_gauge", R2, "below", None)]),
    ("Printed parts: Phase 0 jig (base, tray)", [("phase0_base", L2, "below", None), ("phase0_tray", R2, "below", None)]),
    ("Printed parts: Phase 0 jig (top, occluder mount)", [("phase0_top", L2, "below", None), ("phase0_occluder_mount", R2, "below", None)]),
]

PRINTED_NOTES = ("Printed parts are drawn as exported (cad/out/printed/<part>.step): print orientation, bounding-box minimum at the "
                 "origin; FRONT looks along +Y, TOP down -Z, RIGHT along -X. Dimensions measured on that shape. Drill M3 holes 3.4 and M5 "
                 "holes 5.5 after printing (BUILD_GUIDE 3.4). Tolerance: see D-00 (PROPOSED).")


def sheet_printed(sh: Sheet, geo: Geo, cells):
    for name, cell, layout, tw_ in cells:
        printed_cell(sh, geo, name, cell, layout=layout, table_w=tw_ or 100.0)
    sh.wrap(NOTE_AREA[0], NOTE_AREA[3] - 1.0, PRINTED_NOTES, NOTE_AREA[2] - NOTE_AREA[0])


SHEET_FUNCS: dict = {}


# ------------------------------------------------------------------------------------------------- D-01 general arrangement
def sheet_ga(sh: Sheet, geo: Geo, plan):
    shape = asm_compound(geo, "asm:home")
    b = bbox(shape)
    fx, fy = 32.0, 80.0
    vf = make_view(sh, shape, "front", S110, fx, fy, hidden=False, lw=LW_ASM)
    vt = make_view(sh, shape, "top", S110, fx, fy + vf.h + 28.0, hidden=False, lw=LW_ASM)
    vr = make_view(sh, shape, "right", S110, fx + vf.w + 24.0, fy, hidden=False, lw=LW_ASM)
    sh.text(vf.x, vf.y - 22.0, "FRONT (looking along +Y)", weight="bold")
    sh.text(vt.x, vt.y + vt.h + 21.0, "TOP", weight="bold")
    sh.text(vr.x - 6.0, vr.y - 22.0, "RIGHT SIDE (along -X)", weight="bold")
    keys = [akey(n) for n, p in geo.parts("asm:home").items() if p.kind not in ("fastener", "slab") and n not in ("gate_beam", "light_roof")]
    rL = G("overall length X (rubber feet)", ("bbu", tuple(keys), "xlen"), "assembly (home pose, no fasteners or slabs) bounding box X: the feet strips")
    rW = G("overall depth Y", ("bbu", tuple(keys), "ylen"), "assembly (home pose) bounding box Y")
    rH = G("overall height Z", ("bbu", tuple(keys), "zlen"), "assembly (home pose) bounding box Z, feet underside to Z motor top")
    vf.dim((b[0], b[2]), (b[3], b[2]), "h", -8.0, rL, post=" over the feet")
    vf.dim((b[0], b[2]), (b[0], b[5]), "v", -8.0, rH)
    vt.dim((b[0], b[1]), (b[0], b[4]), "v", -8.0, rW)
    p0x, p1x, p12x = (bb_value(geo.shape(akey(n)), "xmid") for n in ("pad_0", "pad_1", "pad_12"))
    pitch = G("pocket pitch X", s_sub(("bb", akey("pad_1"), "xmid"), ("bb", akey("pad_0"), "xmid")), "pad_1 centre X - pad_0 centre X")
    row = G("pocket 0 to pocket 12 centres", s_sub(("bb", akey("pad_12"), "xmid"), ("bb", akey("pad_0"), "xmid")), "pad_12 centre X - pad_0 centre X")
    vt.dim((p0x, 0.0), (p1x, 0.0), "h", b[4] / 10 + 5.0, pitch, text_at="left")
    vt.dim((p0x, 0.0), (p12x, 0.0), "h", b[4] / 10 + 12.0, row, post=" pocket 0 to 12 (13 pockets + the station cell)")
    for cx in (p0x, p1x, p12x):
        vt.centerline((cx, -75.0), (cx, 75.0), lw=0.35)
    vt.centerline((b[0] - 30, 0.0), (b[3] + 30, 0.0), lw=0.35)
    mx = C("MAX_LINE")
    gz = C("GATE_Z")
    ylo, yhi = bb_value(geo.shape(akey("pad_1")), "ymin"), bb_value(geo.shape(akey("pad_1")), "ymax")
    vr.seg((ylo, mx.value), (yhi, mx.value), lw=0.5, ls=DASH_PHANTOM, owner=-3)
    vr.seg((-6.0, gz.value), (6.0, gz.value), lw=0.5, owner=-3)
    vr.seg((0.0, gz.value - 6.0), (0.0, gz.value + 6.0), lw=0.5, owner=-3)
    vf.seg((p0x - 41.5, mx.value), (p12x + 41.5, mx.value), lw=0.5, ls=DASH_PHANTOM, owner=-3)
    lv = [
        (G("feet underside Z", ("bb", akey("foot_L"), "zmin"), "foot_L bounding box Z min"), "feet underside"),
        (G("bed top Z", ("bb", akey("bed_plywood"), "zmax"), "bed_plywood top face Z"), "bed top"),
        (G("pad top Z", ("bb", akey("pad_1"), "zmax"), "pad_1 top face Z"), "pad top = datum Z 0"),
        (C("STATION_READ_C"), "cup at station read"),
        (mx, "MAX fill line (MAX_LINE)"),
        (gz, "laser beam (GATE_Z)"),
        (G("rod top Z", ("bb", akey("rod_00"), "zmax"), "rod_00 top Z"), "guide-rod tops"),
        (C("C_SAFE_LOADED"), "cup at carry (C_SAFE_LOADED)"),
        (G("X beam bottom Z", ("bb", akey("x_beam"), "zmin"), "x_beam bounding box Z min"), "X beam bottom"),
        (G("X rail centre Z", ("bb", akey("x_rail"), "zmid"), "x_rail bounding box centre Z"), "X rail centre"),
        (G("X beam top Z", ("bb", akey("x_beam"), "zmax"), "x_beam bounding box Z max"), "X beam top"),
        (G("Z motor top Z", ("bb", akey("z_motor"), "zmax"), "z_motor bounding box Z max"), "Z motor top"),
    ]
    items = [(r.value, f"Z {r.text}  {t}", [r]) for r, t in lv]
    ordinates_v(vr, items, b[4], vr.x + vr.w + 14.0, gap=4.6, lo=58.0, hi=152.0)
    sh.text(vr.x + vr.w + 14.0, 156.0, "Heights, machine Z (cup face where noted)", weight="bold")
    tx, ty = 318.0, 150.0
    rows = [["Main data", "Value", "From"]]
    r1, r2 = C("N_POCKETS", unit="count"), C("STATION_CELL", unit="count")
    rows.append(["Pockets, one row", f"{r1.text} + station (cell {r2.text})", "layout"])
    r3, r4 = C("PITCH_X"), C("STACK_MAX", unit="count")
    rows.append(["Pitch; slabs per pocket", f"{r3.text}; {r4.text}", "layout"])
    r5, r6 = C("POCKET_W"), C("POCKET_L")
    rows.append(["Pocket interior X x Y", f"{r5.text} x {r6.text}", "layout"])
    r7 = G("guide rod count", ("count", "asm:home", "rod_"), "number of rod_ parts in the assembly", unit="count")
    r8 = G("guide rod diameter", ("cyl", akey("rod_00"), "z", L.ROD_D, (L.rods()[0][0], L.rods()[0][1], 100.0), "d", False), "rod_00 cylinder diameter")
    rows.append(["Guide rods", f"{r7.text} x Ø{r8.text}", "CAD"])
    r9, r10 = G("cup X at pocket 0", ("bb", akey("pad_0"), "xmid"), "pad_0 centre X"), G("cup X at pocket 12", ("bb", akey("pad_12"), "xmid"), "pad_12 centre X")
    rows.append(["X used (cup X)", f"{r9.text} to {r10.text}", "CAD"])
    r11, r12, r13 = C("X_HARD_STOP", idx=0), C("X_HARD_STOP", idx=1), C("X_HOME_SWITCH")
    rows.append(["X stops; home trip", f"{r11.text} / {r12.text}; {r13.text}", "layout"])
    r14, r15 = C("C_MIN"), C("C_MAX")
    rows.append(["Z used (cup face c)", f"{r14.text} to {r15.text}", "layout"])
    r16, r17 = C("C_HARD_BOTTOM"), C("C_HARD_TOP")
    rows.append(["Z hard stops (c)", f"{r16.text} / {r17.text}", "layout"])
    yb, cells = sh.table(tx, ty, rows, [38.0, 44.0, 18.0])
    allr = [[], [r1, r2], [r3, r4], [r5, r6], [r7, r8], [r9, r10], [r11, r12, r13], [r14, r15], [r16, r17]]
    _attach({ri: [a for rr, cc, a in cells if rr == ri] for ri in range(1, len(rows))}, [{"recs": x} for x in allr])
    h = sh.image(REPO / "docs" / "img" / "machine_iso.png", 250.0, 160.0, 168.0)
    sh.text(250.0, 160.0 + h + 1.5, "ISO (render, docs/img/machine_iso.png; not to scale)", weight="bold")
    sh.wrap(NOTE_AREA[0], NOTE_AREA[3] - 1.0,
            "Pose 'home' (build.POSES): cup over pocket 1 at the carry height. Not shown: fasteners, slabs, light roof, cables. "
            "Heights are machine Z above the pad top (Z 0); X from the machine origin O (D-03). Dash-dot: MAX fill line; "
            "cross on the right view: the overfill laser beam.", NOTE_AREA[2] - NOTE_AREA[0])


SHEET_FUNCS["ga"] = sheet_ga


# --------------------------------------------------------------------------------------------- D-02 frame and cut list
def _sheet_of_part(plan, part: str) -> str:
    for num, title, fn in plan:
        if isinstance(fn, tuple) and any(c[0] == part for c in fn[1]):
            return num
    return "?"


def _num_of(plan, fn_name: str) -> str:
    return next(num for num, _, fn in plan if fn == fn_name)


def _bar(sh: Sheet, x: float, yc: float, rec: Rec, depth: float, scale: Scale, holes=(), tapped=False, dome=False, rod=False) -> View:
    """A cut bar drawn schematically at scale (length along page x), its length dimensioned from rec; holes = [(pos, d)]."""
    ln = rec.value
    v = View(sh, "bar", (0.0, -depth / 2, ln, depth / 2), scale, x, yc - depth / 2 / scale.k)
    k = scale.k
    if dome:
        r = depth / 2
        a = np.linspace(-math.pi / 2, math.pi / 2, 25)
        pts = [(0.0, -r), (ln - r, -r)] + [(ln - r + r * math.cos(t), r * math.sin(t)) for t in a] + [(0.0, r), (0.0, -r)]
        v.polys([np.array(pts)], lw=LW_VIS)
    else:
        v.polys([np.array([(0, -depth / 2), (ln, -depth / 2), (ln, depth / 2), (0, depth / 2), (0, -depth / 2)])], lw=LW_VIS)
    if not rod:
        v.polys([np.array([(0, -depth / 2 + depth * 0.25), (ln, -depth / 2 + depth * 0.25)]), np.array([(0, depth / 2 - depth * 0.25), (ln, depth / 2 - depth * 0.25)])],
                lw=0.3, color=GREY, track=False)
    for pos, d in holes:
        v.ax.add_patch(Circle((pos, 0.0), d / 2, fill=False, lw=0.6, clip_on=False))
        v.centerline((pos, -depth / 2 - 1.5 * k), (pos, depth / 2 + 1.5 * k))
    if tapped:
        for xe in (0.0, ln):
            for dy in (-depth / 4, depth / 4):
                v.seg((xe, dy), (xe + (1 if xe == 0 else -1) * 2.5 * k, dy), lw=0.8, owner=-3)
    v.dim((0.0, depth / 2), (ln, depth / 2), "h", 1.6, rec)
    return v


def sheet_frame(sh: Sheet, geo: Geo, plan):
    names = ["base_rail_0", "base_rail_1", "upright_L", "upright_R", "x_beam", "bed_plywood", "foot_L", "foot_M", "foot_R"]
    shape = compound([geo.shape(akey(n)) for n in names])
    b = bbox(shape)
    vf = make_view(sh, shape, "front", S110, 40.0, 210.0, hidden=True)
    vr = make_view(sh, shape, "right", S110, 40.0 + vf.w + 30.0, 210.0, hidden=True)
    sh.text(vf.x + vf.w / 2, vf.y - 4.0, "FRAME, FRONT (1:10)", weight="bold", ha="center", va="top")
    sh.text(vr.x + vr.w / 2, vr.y - 12.0, "RIGHT (1:10)", weight="bold", ha="center", va="top")
    g = lambda n, w: bb_value(geo.shape(akey(n)), w)  # noqa: E731
    for n in ("upright_L", "upright_R"):
        vf.centerline((g(n, "xmid"), g(n, "zmin") - 25.0), (g(n, "xmid"), g("x_beam", "zmax") + 25.0))
    r_in = G("upright inner faces", s_sub(("bb", akey("upright_R"), "xmin"), ("bb", akey("upright_L"), "xmax")), "upright_R X min - upright_L X max")
    vf.dim((g("upright_L", "xmax"), 120.0), (g("upright_R", "xmin"), 120.0), "h", 0.0, r_in, post=" inner faces")
    r_cc = G("upright centres", s_sub(("bb", akey("upright_R"), "xmid"), ("bb", akey("upright_L"), "xmid")), "upright_R centre X - upright_L centre X")
    vf.dim((g("upright_L", "xmid"), 300.0), (g("upright_R", "xmid"), 300.0), "h", 0.0, r_cc, post=" upright centres")
    r_bl = G("X beam length", ("bb", akey("x_beam"), "xlen"), "x_beam bounding box X")
    vf.dim((g("x_beam", "xmin"), g("x_beam", "zmax")), (g("x_beam", "xmax"), g("x_beam", "zmax")), "h", 5.0, r_bl, post=" beam = bed length")
    r_bh = G("bed top to beam bottom", s_sub(("bb", akey("x_beam"), "zmin"), ("bb", akey("bed_plywood"), "zmax")), "x_beam Z min - bed_plywood Z max")
    # outside the frame, off its right end (the beam's underside meets the upright's top there): crosses no other dimension
    xe = g("bed_plywood", "xmax")
    vf.dim((xe, g("bed_plywood", "zmax")), (xe, g("x_beam", "zmin")), "v", (g("foot_R", "xmax") - xe) / 10 + 7.0, r_bh, text_at="right")
    r_rc = G("base rail centres", s_sub(("bb", akey("base_rail_1"), "ymid"), ("bb", akey("base_rail_0"), "ymid")), "base_rail_1 centre Y - base_rail_0 centre Y")
    vr.dim((g("base_rail_0", "ymid"), g("base_rail_0", "zmin")), (g("base_rail_1", "ymid"), g("base_rail_0", "zmin")), "h", -5.0, r_rc, text_at="right")
    for n in ("base_rail_0", "base_rail_1"):
        vr.centerline((g(n, "ymid"), g(n, "zmin") - 30), (g(n, "ymid"), g(n, "zmax") + 30))
    # set-up notes (quoted tolerances)
    nx = vr.x + vr.w + 26.0
    sh.text(nx, TOP - 5.0, "Frame set-up (BUILD_GUIDE 4.5; tolerances quoted)", weight="bold", va="top")
    sh.wrap(nx, TOP - 10.5,
            "Base rails: centre distance (RIGHT view) +/-0.5 at both ends; diagonals equal within 1. Upright inner faces (FRONT) +/-0.5, "
            "equal at the bottom and the top [Certain, CAD]. Bed top to beam bottom +/-0.5, equal at both ends [Certain, CAD]. Uprights stand on "
            "the back base rail through notches in the bed (D-03); the beam sits on the uprights, flush with their outer faces. "
            "Joints (L brackets, back joining plates) are NOT in the CAD: BUILD_GUIDE 4.3 [Guessing on the exact layout]. Nor are the "
            "bed-to-base-rail bolts (16x M5x25 with washers into T-nuts in the rails' outer slots, BUILD_GUIDE 4.3 [Likely]): drill the bed "
            "for them on assembly, after a test on a rail offcut.",
            PW - 14.0 - nx)
    # cut list
    rows = list(__import__("csv").reader(open(HERE / "out" / "cut_list.csv")))[1:]
    cx = POSES_HOME = B.POSES["home"]
    cupx, c = POSES_HOME[0], POSES_HOME[1]
    hf_near = (cupx + 10.0, L.ARM_TO_CUP, c + M.FOOT_Z[1] + 9.0)
    cb_near = (cupx + 10.0, L.ARM_TO_CUP, c + M.CAM_Z + 9.0)
    arm0 = ("bb", akey("drop_arm"), "zmin")
    h19 = G("drop arm: foot cross hole from the socket end", s_sub(("cyl", akey("head_foot"), "x", M.M5_CLR, hf_near, "z"), arm0), "head_foot M5 cross hole axis Z - drop_arm Z min")
    h84 = G("drop arm: camera-bracket cross hole from the socket end", s_sub(("cyl", akey("camera_bracket"), "x", M.M5_CLR, cb_near, "z"), arm0), "camera_bracket M5 cross hole axis Z - drop_arm Z min")
    hd = G("drop arm cross hole diameter (head_foot hole)", ("cyl", akey("head_foot"), "x", M.M5_CLR, hf_near, "d"), "head_foot M5 cross hole diameter")
    p0n = (10.0, L.ARM_TO_CUP, M.P0_OCC_C + M.FOOT_Z[1] + 9.0)
    s19 = G("jig stub: cross hole from the end", s_sub(("cyl", "p0/p0_head_foot", "x", M.M5_CLR, p0n, "z"), ("bb", "p0/p0_arm_stub", "zmin")), "p0_head_foot M5 cross hole axis Z - p0_arm_stub Z min")
    ec = holes_of(geo, akey("z_end_cap"), "z", M.M5_CLR)
    sp = G("Z spine tapped end bores apart", ("pat2", akey("z_end_cap"), "z", M.M5_CLR, "x", tuple((f["c"][0], f["c"][1]) for f in ec)), "z_end_cap M5 holes (on the spine end bores): centre span X")
    dome = C("ROD_DOME_R")
    spec = [  # length spec, profile depth, scale, bar options, use text, recs in the text, tolerance
        (("bb", akey("base_rail_0"), "xlen"), "base_rail_0 X", 20, S110, {}, "base rail, lying flat under the bed; square ends", [], "+/-0.5"),
        (("bb", akey("upright_L"), "zlen"), "upright_L Z", 40, S110, {}, "upright; square ends", [], "+/-0.5"),
        (("bb", akey("x_beam"), "xlen"), "x_beam X", 40, S110, {}, "X beam, on top of the uprights; square ends", [], "+/-0.5"),
        (("bb", akey("z_spine"), "zlen"), "z_spine Z", 20, S15, {"tapped": True},
         f"Z spine; BOTH ends: 2x M5 tapped, the two centre bores ({sp.text} apart), for 2x M5x12 button heads (bottom) and 2x M5x16 (top), BUILD_GUIDE 7.1, 7.3", [sp], "+/-0.5"),
        (("bb", akey("drop_arm"), "zlen"), "drop_arm Z", 20, S15, {"holes": [(h19.value, hd.value), (h84.value, hd.value)]},
         f"head drop arm; 2x Ø{hd.text} THRU across the arm (machine X), {h19.text} and {h84.text} from the end in head_foot's socket: match-drill (BUILD_GUIDE 7.5)", [hd, h19, h84], "+/-0.5"),
        (("bb", akey("z_leadscrew"), "zlen"), "z_leadscrew Z", 8, S15, {"rod": True}, "T8x8 Z screw, length below the motor face: cut the motor's 400 mm screw; 311-356 works (cut_list.csv)", [], "311-356"),
        (None, None, None, None, None, "probe flag blank: D-06", [], "D-06"),
        (("bb", "p0/p0_post_1", "zlen"), "p0_post_1 Z", 20, S15, {}, "Phase 0 jig post; cut square", [], "+/-0.5"),
        (("bb", "p0/p0_arm_stub", "zlen"), "p0_arm_stub Z", 20, S15, {"holes": [(s19.value, hd.value)]}, f"Phase 0 jig arm stub; Ø{hd.text} THRU cross hole {s19.text} from one end, match-drilled through head_foot (BUILD_GUIDE 1.5)", [hd, s19], "+/-0.5"),
        (None, None, None, None, None, "carry-sensor flag: D-06", [], "D-06"),
        (("bb", akey("rod_00"), "zlen"), "rod_00 Z", 8, S15, {"dome": True, "rod": True}, f"guide rod; dome the top R{dome.text}-3 (ROD_DOME_R; BUILD_GUIDE 5.4), chamfer the bottom lightly", [dome], "PROPOSED +/-0.5"),
    ]
    assert len(spec) == len(rows), "cut_list.csv rows changed: update the D-02 table"
    x0, ytop = 16.0, 192.0
    widths = [14.0, 156.0, 30.0, 150.0, 14.0, 34.0]
    hdr = ["Item", "Bar (length from the CAD; scale per row)", "Profile / stock", "Use, ends, holes", "Qty", "Tolerance"]
    sh.text(x0, ytop + 1.5, "CUT LIST (cad/out/cut_list.csv; extrusion cuts +/-0.5 with square ends, BUILD_GUIDE 4.1)", weight="bold")
    sh.text(x0 + sum(widths), ytop + 1.5, "Extrusions: 20-series, slot 6 (Misumi HFS5, BOM.csv)", ha="right")
    xs = np.cumsum([x0] + widths)
    hh = 7.0
    for i, t in enumerate(hdr):
        sh.text(xs[i] + 1.2, ytop - 1.0, t, va="top", weight="bold")
    y = ytop - hh
    sh.line([(x0, y), (xs[-1], y)], lw=0.5, track=False)
    for i, (row, (lspec, lsrc, depth, sc, opts, use, recs, tol)) in enumerate(zip(rows, spec)):
        prof, _, lcsv, qty = row
        rh = 12.2 if lspec is not None else 8.0
        yc = y - rh / 2
        sh.text(xs[0] + 1.2, yc, f"C-{i + 1:02d}", va="center")
        if lspec is not None:
            r = G(f"cut length C-{i + 1:02d} ({prof})", lspec, f"{lsrc} length")
            if abs(r.value - float(lcsv)) > 0.5:
                raise SystemExit(f"cut_list.csv row {i + 1} ({lcsv}) disagrees with the CAD ({r.value})")
            v = _bar(sh, xs[1] + 3.0, yc - 1.8, r, depth, sc, **opts)
            sh.text(xs[1] + 3.0 + v.w + 4.0, yc - 1.8, str(sc), va="center", color=GREY)
        lines = textwrap.wrap(use, int((widths[3] - 2.4) / (0.53 * FS * PT)))
        assert len(lines) <= 2, f"cut list row C-{i + 1:02d}: use text longer than two lines"
        arts = []
        for j, ln in enumerate(lines[:2]):
            arts.append(sh.text(xs[3] + 1.2, yc + (len(lines[:2]) - 1) * 2.3 - j * 4.6, ln, va="center"))
        _attach({0: arts}, [{"recs": recs}])
        sh.text(xs[2] + 1.2, yc, prof if len(prof) < 14 else prof.replace(" lead screw", "").replace(" aluminium sheet", " Al sheet").replace(" (7.94 mm) hardwood dowel", " dowel"), va="center")
        sh.text(xs[4] + 1.2, yc, qty, va="center")
        sh.text(xs[5] + 1.2, yc, tol, va="center")
        y -= rh
        sh.line([(x0, y), (xs[-1], y)], lw=0.35, track=False)
    sh.rect(x0, y, xs[-1], ytop, lw=0.6)
    for xx in xs[1:-1]:
        sh.line([(xx, y), (xx, ytop)], lw=0.35, track=False)
    sh.occ.append((x0, y, xs[-1], ytop + 6))


SHEET_FUNCS["frame"] = sheet_frame


# ---------------------------------------------------------------------------------------------------------- D-03 bed
def sheet_bed(sh: Sheet, geo: Geo, plan):
    parts = geo.parts("asm:home")
    names = [n for n in parts if n == "bed_plywood" or n.startswith(("pad_", "rod_", "base_rail", "foot_")) or n in ("station", "gate_post_L", "gate_post_R")]
    shape = compound([parts[n].shape for n in names])
    b = bbox(shape)
    vp = make_view(sh, shape, "top", S15, 84.0, 178.0, hidden=True, lw=LW_ASM)
    sh.text(16.0, TOP - 5.0, "PLAN (1:5): bed, pads, rods, station mount,", weight="bold", va="top")
    sh.text(16.0, TOP - 10.0, "gate posts; base rails and feet hidden", weight="bold", va="top")
    g = lambda n, w: bb_value(geo.shape(akey(n)), w)  # noqa: E731
    # datum O
    from matplotlib.patches import Wedge

    vp.seg((-14.0, 0.0), (14.0, 0.0), lw=0.6, owner=-3)
    vp.seg((0.0, -14.0), (0.0, 14.0), lw=0.6, owner=-3)
    vp.ax.add_patch(Circle((0.0, 0.0), 9.0, fill=False, lw=0.6, clip_on=False))  # origin symbol: two quadrants filled
    for a0 in (0.0, 180.0):
        vp.ax.add_patch(Wedge((0.0, 0.0), 9.0, a0, a0 + 90.0, facecolor=INK, edgecolor=INK, lw=0.3, clip_on=False))
    vp.text(2.0, -16.0, "DATUM O", weight="bold", va="top", ha="left")  # inside pad 0's outline, clear of its lines
    vp.centerline((b[0] - 20, 0.0), (b[3] + 20, 0.0), lw=0.35)
    # pocket centres along the top
    items = []
    for p in L.pockets():
        r = G(f"pocket {p.index} centre X", ("bb", akey(f"pad_{p.index}"), "xmid"), f"pad_{p.index} bounding box centre X")
        items.append((r.value, f"{r.text}  P{p.index}", [r]))
    rs = G("station cell centre X", ("bb", akey("station"), "xmid"), "station (station_mount) bounding box centre X")
    items.append((rs.value, f"{rs.text}  STATION", [rs]))
    items.sort()
    ordinates_h(vp, items, b[4], vp.y + vp.h + 8.0, gap=4.6, side="above")
    # X features along the bottom
    rods = L.rods()

    def rod_at(x, y):  # bed_parts() names the rods rod_<index in layout.rods()>
        i = min(range(len(rods)), key=lambda j: math.hypot(rods[j][0] - x, rods[j][1] - y))
        return akey(f"rod_{i:02d}"), (rods[i][0], rods[i][1], 100.0)

    def rod_c(label, x, y, what):
        k_, near = rod_at(x, y)
        return G(label, ("cyl", k_, "z", L.ROD_D, near, what, False), f"{k_.split('/')[-1]} axis {what.upper()}")

    xs_l = sorted({x for x, _ in rods})
    ys_l = sorted({y for _, y in rods})
    bx = [
        (G("bed left edge X", ("bb", akey("bed_plywood"), "xmin"), "bed_plywood X min"), "bed"),
        (G("left notch inner face X", ("plane", akey("bed_plywood"), "x", (M.XL + 20.5, M.BEAM_Y0 + 20, -10.0)), "bed_plywood left notch inner face X"), "notch"),
        (G("left gate post centre X", ("bb", akey("gate_post_L"), "xmid"), "gate_post_L bounding box centre X"), "gate L"),
        (rod_c("first rod line X", xs_l[0], ys_l[1], "x"), "rods"),
        (rod_c("last rod line X", xs_l[-1], ys_l[1], "x"), "rods"),
        (G("right gate post centre X", ("bb", akey("gate_post_R"), "xmid"), "gate_post_R bounding box centre X"), "gate R"),
        (G("right notch inner face X", ("plane", akey("bed_plywood"), "x", (M.XR - 20.5, M.BEAM_Y0 + 20, -10.0)), "bed_plywood right notch inner face X"), "notch"),
        (G("bed right edge X", ("bb", akey("bed_plywood"), "xmax"), "bed_plywood X max"), "bed"),
    ]
    ordinates_h(vp, [(r.value, f"{r.text} {t}", [r]) for r, t in bx], b[1], vp.y - 7.0, gap=4.6, side="below")
    # Y along the left (rod rows measured on rods that sit on those rows)
    ry = [
        (G("bed front edge Y", ("bb", akey("bed_plywood"), "ymin"), "bed_plywood Y min"), "bed front edge"),
        (rod_c("front rod row Y", xs_l[0] + L.WALL / 2 + L.ROD_INSET, ys_l[0], "y"), "front rods"),
        (G("front base rail centre Y", ("bb", akey("base_rail_0"), "ymid"), "base_rail_0 centre Y"), "front base rail"),
        (rod_c("front side-rod row Y", xs_l[0], ys_l[1], "y"), "side rods"),
        (G("row centre line Y", ("bb", akey("pad_1"), "ymid"), "pad_1 centre Y"), "row centre (O)"),
        (rod_c("back side-rod row Y", xs_l[0], ys_l[2], "y"), "side rods"),
        (rod_c("back rod row Y", xs_l[0] + L.WALL / 2 + L.ROD_INSET, ys_l[3], "y"), "back rods"),
        (G("notch front edge Y", ("plane", akey("bed_plywood"), "y", (M.XR, M.BEAM_Y0 - 0.5, -10.0)), "bed_plywood notch front face Y"), "notch front"),
        (G("back base rail centre Y", ("bb", akey("base_rail_1"), "ymid"), "base_rail_1 centre Y"), "back base rail"),
        (G("bed back edge Y", ("bb", akey("bed_plywood"), "ymax"), "bed_plywood Y max"), "bed back edge"),
    ]
    want = [None, -L.POCKET_L / 2 - L.WALL / 2, None, -L.POCKET_L / 2 + L.ROD_INSET, None, L.POCKET_L / 2 - L.ROD_INSET, L.POCKET_L / 2 + L.WALL / 2]
    for (r, t), w in zip(ry, want):  # the locators above must land on the rows they name
        assert w is None or abs(r.value - w) < 1e-6, (t, r.value, w)
    ordinates_v(vp, [(r.value, f"Y {r.text}  {t}", [r]) for r, t in ry], b[0], vp.x - 9.0, gap=4.5, side="left", lo=136.0, hi=250.0)
    # notches
    nx = G("notch size X", s_sub(("bb", akey("bed_plywood"), "xmax"), ("plane", akey("bed_plywood"), "x", (M.XR - 20.5, M.BEAM_Y0 + 20, -10.0))), "bed_plywood X max - right notch inner face X")
    ny = G("notch size Y", s_sub(("plane", akey("bed_plywood"), "y", (M.XR, M.BEAM_Y1 + 0.5, -10.0)), ("plane", akey("bed_plywood"), "y", (M.XR, M.BEAM_Y0 - 0.5, -10.0))), "bed_plywood notch faces Y")
    vp.leader((b[3] - 10.0, M.BEAM_Y0 + 20.0), 18.0, 9.0, [f"2x notch {nx.text} x {ny.text}", "(uprights pass)"], [nx, ny])
    rl = G("bed length", ("bb", akey("bed_plywood"), "xlen"), "bed_plywood X")
    rw = G("bed depth", ("bb", akey("bed_plywood"), "ylen"), "bed_plywood Y")
    rt = G("bed thickness", ("bb", akey("bed_plywood"), "zlen"), "bed_plywood Z")
    pw = G("pad X", ("bb", akey("pad_1"), "xlen"), "pad_1 X")
    pl = G("pad Y", ("bb", akey("pad_1"), "ylen"), "pad_1 Y")
    pt = G("pad thickness", ("bb", akey("pad_1"), "zlen"), "pad_1 Z")
    # detail C: one cell = drill_template (its model.py frame: cell centre at 0, 0)
    dt = geo.shape("local/drill_template")
    vd = make_view(sh, dt, "top", S12, 34.0, 52.0, hidden=False)
    sh.text(16.0, 146.0, "DETAIL C (1:2): one cell's rod holes = drill_template", weight="bold")
    sh.text(16.0, 141.5, "(cell centre at 0, 0; the machine drills them, BUILD_GUIDE 5.6)")
    n = "drill_template"
    sx = G("rod holes: side pair X", s_sub(s_lcyl(n, "z", 8.3, (46, 57.5, 6), "x"), s_lcyl(n, "z", 8.3, (-46, 57.5, 6), "x")), "drill_template side-rod holes X")
    sy = G("rod holes: side pair Y", s_sub(s_lcyl(n, "z", 8.3, (-46, 57.5, 6), "y"), s_lcyl(n, "z", 8.3, (-46, -57.5, 6), "y")), "drill_template side-rod holes Y")
    fx = G("rod holes: front/back pair X", s_sub(s_lcyl(n, "z", 8.3, (30, 73.5, 6), "x"), s_lcyl(n, "z", 8.3, (-30, 73.5, 6), "x")), "drill_template front/back-rod holes X")
    fy = G("rod holes: front/back pair Y", s_sub(s_lcyl(n, "z", 8.3, (30, 73.5, 6), "y"), s_lcyl(n, "z", 8.3, (30, -73.5, 6), "y")), "drill_template front/back-rod holes Y")
    dd = G("alignment dimples apart", s_sub(("cone", "printed/" + n, (40, 0, 4), "x"), ("cone", "printed/" + n, (-40, 0, 4), "x")), "drill_template cone dimples: apex X spacing")
    hx, hy = sx.value / 2, sy.value / 2
    ax_, ay_ = fx.value / 2, fy.value / 2
    ybot = bb_value(dt, "ymin")
    vd.dim((-hx, -hy), (hx, -hy), "h", (ybot - 10.0 + hy) / 2, sx)
    vd.dim((-ax_, -ay_), (ax_, -ay_), "h", (ybot - 22.0 + ay_) / 2, fx)
    vd.dim((-hx, -hy), (-hx, hy), "v", -8.0, sy)
    vd.dim((ax_, -ay_), (ax_, ay_), "v", (bb_value(dt, "xmax") - ax_) / 2 + 6.0, fy)
    vd.dim((-dd.value / 2, 0.0), (dd.value / 2, 0.0), "h", 0.0, dd, post=" dimples")
    for x, y in [(sx_, sy_) for sx_ in (-hx, hx) for sy_ in (-hy, hy)] + [(ax2, ay2) for ax2 in (-ax_, ax_) for ay2 in (-ay_, ay_)]:
        vd.cmark(x, y, 4.15, ext=1.2)
    hd = G("drill_template hole diameter", s_lcyl(n, "z", 8.3, (46, 57.5, 6), "d"), "drill_template rod hole diameter")
    k0, near0 = rod_at(xs_l[0], ys_l[1])
    rd = G("rod diameter (CAD)", ("cyl", k0, "z", L.ROD_D, near0, "d", False), "rod diameter")
    vd.leader((hx + 4.15 * 0.707, hy - 4.15 * 0.707), 16.0, -12.0, [f"8x Ø{hd.text} guide", f"(rods Ø{rd.text}", "in the CAD)"], [hd, rd])
    # detail D: rod in the bed, front, broken
    rx = rods[0][0] + L.PITCH_X  # the second rod line (cell 0 / cell 1 wall): locator
    sel = [parts[nm].shape for nm in parts if nm.startswith("rod_") and abs(bb_value(_wrapped(parts[nm].shape), "xmid") - rx) < 0.5]
    sel += [parts[nm].shape for nm in ("bed_plywood", "pad_0", "pad_1")]
    shp = compound(sel)
    u0, u1 = rx - 24.0, rx + 24.0
    vlo = make_view(sh, shp, "front", S12, 172.0, 62.0, hidden=True, window=(u0, -24.0, u1, 10.0), clip=True, breaks=False)
    vhi = make_view(sh, shp, "front", S12, 172.0, 62.0 + vlo.h + 9.0, hidden=True, window=(u0, 202.0, u1, 224.0), clip=True, breaks=False)
    for vv, vb in ((vlo, 10.0), (vhi, 202.0)):
        xs_ = np.linspace(u0, u1, 9)
        zz = [vb + (1.2 if i % 2 else -1.2) * 2 for i in range(9)]
        vv.polys([np.column_stack([xs_, zz])], lw=0.5, track=False)
    sh.text(vlo.x - 6.0, vhi.y + vhi.h + 10.0, "DETAIL D (1:2): rod in the bed,", weight="bold")
    sh.text(vlo.x - 6.0, vhi.y + vhi.h + 5.5, "front, broken")
    zs = [
        (vlo, G("bed underside Z", ("bb", akey("bed_plywood"), "zmin"), "bed_plywood Z min"), "bed underside"),
        (vlo, G("rod bottom Z", ("bb", akey("rod_00"), "zmin"), "rod_00 Z min"), "rod bottom"),
        (vlo, G("bed top Z (detail)", ("bb", akey("bed_plywood"), "zmax"), "bed_plywood Z max"), "bed top"),
        (vlo, G("pad top Z (detail)", ("bb", akey("pad_1"), "zmax"), "pad_1 Z max"), "pad top"),
    ]
    ordinates_v(vlo, [(r.value, f"Z {r.text}  {t}", [r]) for _, r, t in zs], u1, vlo.x + vlo.w + 12.0, gap=4.6)
    mxl, gzl = C("MAX_LINE"), C("GATE_Z")
    rtop = G("rod top Z (detail)", ("bb", akey("rod_00"), "zmax"), "rod_00 Z max")
    for vz in (mxl.value, gzl.value):
        vhi.seg((u0, vz), (u1, vz), lw=0.45, ls=DASH_PHANTOM, owner=-3)
    ordinates_v(vhi, [(mxl.value, f"Z {mxl.text}  MAX line", [mxl]), (gzl.value, f"Z {gzl.text}  laser beam", [gzl]), (rtop.value, f"Z {rtop.text}  rod top", [rtop])],
                u1, vhi.x + vhi.w + 12.0, gap=4.6)
    emb = G("rod embed in the bed", s_sub(("bb", akey("bed_plywood"), "zmax"), ("bb", akey("rod_00"), "zmin")), "bed_plywood Z max - rod_00 Z min")
    vlo.dim((rx - 4.0, -3.0 - emb.value), (rx - 4.0, -3.0), "v", -(u0 + 4.0 - (rx - 4.0)) / 2 - 4.0, emb)
    # notes and table
    tx = 268.0
    npads = G("pad count", ("count", "asm:home", "pad_"), "number of pad_ parts", unit="count")
    nrods = G("rod count", ("count", "asm:home", "rod_"), "number of rod_ parts", unit="count")
    stc = C("STATION_CELL", unit="count")
    sh.text(tx, 142.0, "Bed and pads", weight="bold")
    rows = [["Item", "Size (from the CAD)", "Note"],
            ["Bed, plywood (W)", f"{rl.text} x {rw.text} x {rt.text}", "cut on site; test-drill for voids first (BUILD_GUIDE 5.1)"],
            [f"Pads (EVA + microfiber), {npads.text}", f"{pw.text} x {pl.text} x {pt.text}", "spray adhesive, after the rods (5.9)"],
            [f"Rods (dowels), {nrods.text}", "D-02 item C-11", "glued; plumb within 1 over 200 [Guessing target] (5.7)"]]
    yb, cells = sh.table(tx, 137.0, rows, [40.0, 40.0, 70.0])
    _attach({i: [a for r_, c_, a in cells if r_ == i] for i in (1, 2, 3)}, [{"recs": []}, {"recs": [rl, rw, rt]}, {"recs": [npads, pw, pl, pt]}, {"recs": [nrods]}])
    t = sh.wrap(tx, yb - 3.0,
                f"Datum O = machine origin (X 0; Y 0 = the pocket-row centre line), as the software uses it; X ordinates from O. The machine "
                f"drills the rod holes through drill_template, so they are not laid out from the bed edges (BUILD_GUIDE 5.6). Station mount: "
                f"cell\u00a0{stc.text}, four #8 wood screws, no pad. Gate posts: bare plywood, no shim (5.9).", PW - 14.0 - tx)
    for a in sh.pg.texts[-8:]:
        if f"cell\u00a0{stc.text}," in a.get_text():
            stc.artist = a
    # rod holes: callout on the plan + the pattern in words (the bed itself has no holes in the CAD: the rods pass into it)
    rdc = C("ROD_D")
    emc = C("ROD_EMBED")
    nr2 = G("rod hole count", ("count", "asm:home", "rod_"), "number of rod_ parts (one hole each)", unit="count")
    last_k, last_near = rod_at(xs_l[-1], ys_l[1])
    vp.leader((xs_l[-1] + 4.0 * 0.707, ys_l[1] - 4.0 * 0.707), 22.0, -16.0, [f"{nr2.text}x Ø{rdc.text} x {emc.text} deep", "rod holes:", "see ROD HOLES note"], [nr2, rdc, emc])
    f0 = rod_c("rod holes: first side-rod line X", xs_l[0], ys_l[1], "x")
    wall_xs = sorted(x for x, y in rods if abs(y - ys_l[1]) < 1e-6)  # the side rods of one row = the cell wall lines
    k1, n1 = rod_at(wall_xs[1], ys_l[1])
    k0_, n0_ = rod_at(wall_xs[0], ys_l[1])
    pit = G("rod holes: side-rod line pitch", s_sub(("cyl", k1, "z", L.ROD_D, n1, "x", False), ("cyl", k0_, "z", L.ROD_D, n0_, "x", False)),
            "second minus first side-rod line X")
    sr = rod_c("rod holes: side-rod row Y (back)", xs_l[0], ys_l[2], "y")
    fr = rod_c("rod holes: front/back-rod row Y (back)", xs_l[0] + L.WALL / 2 + L.ROD_INSET, ys_l[3], "y")
    xa_ = xs_l[0] + L.WALL / 2 + L.ROD_INSET  # pocket 0's back rods: locators
    ka_, na_ = rod_at(xa_, ys_l[3])
    kb_, nb_ = rod_at(xa_ + L.POCKET_W - 2 * L.ROD_INSET, ys_l[3])
    fp = G("rod holes: front/back pair X", s_sub(("cyl", kb_, "z", L.ROD_D, nb_, "x", False), ("cyl", ka_, "z", L.ROD_D, na_, "x", False)),
           "pocket 0 back rods: right rod X - left rod X")
    stc2 = C("STATION_CELL", unit="count")
    sh.wrap_recs(tx, t - 2.5,
                 f"ROD HOLES: {nr2.text}x Ø{rdc.text} (ROD_D; brad-point bit to suit the dowels: 5/16 in for the BOM's 7.94 dowels) x {emc.text} deep "
                 f"(ROD_EMBED), square to the bed (guide block, 5.6). Side rods on the wall lines: X\u00a0{f0.text}, then every {pit.text}, at "
                 f"Y\u00a0±{sr.text}. Front/back rods: pairs {fp.text} apart about each pocket centre, at Y\u00a0±{fr.text}; none in cell {stc2.text}.",
                 PW - 14.0 - tx, [nr2, rdc, emc, f0, pit, sr, fr, fp, stc2])


SHEET_FUNCS["bed"] = sheet_bed


# ------------------------------------------------------------------------------------------------------- D-04 X axis
X_PARTS = ("x_beam", "x_rail", "x_carriage", "x_bracket", "belt_clamp_L", "belt_clamp_R", "x_belt_lo", "x_belt_hi", "x_motor", "x_motor_mount",
           "x_pulley", "x_idler", "x_idler_mount", "x_idler_slider", "x_bumper_L", "x_switch_mount", "x_home_switch", "upright_L", "upright_R")


def sheet_xaxis(sh: Sheet, geo: Geo, plan):
    parts = geo.parts("asm:home")
    shape = compound([parts[n].shape for n in X_PARTS])
    vf = make_view(sh, shape, "front", S15, 70.0, 190.0, hidden=False, lw=LW_ASM, window=(-72.0, 325.0, 1352.0, 470.0), clip=True)
    sh.text(16.0, vf.y + vf.h - 4.0, "FRONT (1:5)", weight="bold")
    g = lambda n, w, src="asm:home": bb_value(_wrapped(geo.parts(src)[n].shape), w)  # noqa: E731
    rr = G("X rail length", ("bb", akey("x_rail"), "xlen"), "x_rail X")
    vf.dim((g("x_rail", "xmin"), 404.0), (g("x_rail", "xmax"), 404.0), "h", -(404.0 - 325.0) / 5 - 3.0, rr, post=" X rail (MGN12)")
    below = [
        (G("beam left end X", ("bb", akey("x_beam"), "xmin"), "x_beam X min"), "beam"),
        (G("idler axle X", ("cyl", akey("x_idler"), "y", 18.0, (M.X_IDLER_X, M.BEAM_Y0 + 6, M.X_PULLEY_Z), "x", False), "x_idler axis X"), "idler"),
        (G("left bumper face X", ("bb", akey("x_bumper_L"), "xmax"), "x_bumper_L X max (stop face)"), "stop"),
        (G("rail left end X", ("bb", akey("x_rail"), "xmin"), "x_rail X min"), "rail"),
        (G("rail right end X", ("bb", akey("x_rail"), "xmax"), "x_rail X max"), "rail"),
        (G("right bumper face X", ("bb", akey("x_motor_mount"), "xmin"), "x_motor_mount X min (its left end is the stop face)"), "stop"),
        (G("motor axis X", ("cyl", akey("x_pulley"), "y", 16.0, (M.X_MOTOR_X, M.BEAM_Y0 + 9, M.X_PULLEY_Z), "x", False), "x_pulley axis X"), "motor"),
        (G("beam right end X", ("bb", akey("x_beam"), "xmax"), "x_beam X max"), "beam"),
    ]
    ordinates_h(vf, [(r.value, f"{r.text} {t}", [r]) for r, t in below], 325.0, vf.y - 15.0, gap=4.6, side="below")
    above = [
        (C("X_HARD_STOP", idx=0), "left stop"), (C("X_HOME_SWITCH"), "home trip"),
        (G("cup X pocket 0", ("bb", akey("pad_0"), "xmid"), "pad_0 centre X"), "pocket 0"),
        (G("cup X at home pose", ("cyl", akey("buffer"), "z", 10.0, (B.POSES["home"][0], 0.0, 300.0), "x", False), "buffer body axis X at the home pose"), "home pose"),
        (G("cup X station", ("bb", akey("station"), "xmid"), "station centre X"), "station"),
        (G("cup X pocket 12", ("bb", akey("pad_12"), "xmid"), "pad_12 centre X"), "pocket 12"),
        (C("X_HARD_STOP", idx=1), "right stop"),
    ]
    yl = vf.y + vf.h + 6.0
    xa, xb = vf.P(above[0][0].value, 0)[0], vf.P(above[-1][0].value, 0)[0]
    sh.line([(xa, yl), (xb, yl)], lw=0.8, track=False)
    sh.text(xa - 2.0, yl, "cup X", ha="right", va="center", weight="bold")
    for r, _ in above:
        x = vf.P(r.value, 0)[0]
        sh.line([(x, yl - 1.5), (x, yl + 1.5)], lw=0.8, track=False)
    ordinates_h(vf, [(r.value, f"{r.text} {t}", [r]) for r, t in above], (yl - vf.y) * 5 + 325.0, yl + 9.0, gap=4.6, side="above")
    # detail A: left end at the home-switch trip
    sa = "xdet:19"
    pa = geo.parts(sa)
    da = compound([pa[n].shape for n in X_PARTS if n in pa and n not in ("x_motor", "x_motor_mount", "x_pulley", "upright_R")])
    va = make_view(sh, da, "front", S12, 40.0, 64.0, hidden=False, window=(-72.0, 322.0, 46.0, 470.0), clip=True)
    sh.text(16.0, va.y + va.h + 16.0, "DETAIL A (1:2): left end, carriage at the home-switch trip", weight="bold")
    sh.text(16.0, va.y + va.h + 11.5, f"(cup X = X_HOME_SWITCH; front view)")
    ka = lambda n: f"xdet/19/{n}"  # noqa: E731
    gap = G("x_bracket to left bumper at the switch trip", s_sub(("plane", ka("x_bracket"), "x", (L.X_HOME_SWITCH - M.XB_HALF, 90.0, 400.0)), ("plane", ka("x_bumper_L"), "x", (L.X_HARD_STOP[0] - M.XB_HALF, 98.0, 388.0))),
            "x_bracket plate left face X - x_bumper_L stop face X, cup X = X_HOME_SWITCH")
    # below the clipped view (its window ends at Z 322): the text then crosses none of the view's edges
    va.dim((L.X_HARD_STOP[0] - M.XB_HALF, 388.0), (L.X_HOME_SWITCH - M.XB_HALF, 388.0), "h", -(388.0 - 322.0) / 2 - 4.0, gap,
           post=" gap at the trip", text_at="left")
    hs = C("X_HOME_SWITCH")
    zs = [
        (G("X rail centre Z (detail)", ("bb", ka("x_rail"), "zmid"), "x_rail centre Z"), "X rail centre"),
        (G("beam top Z (detail)", ("bb", ka("x_beam"), "zmax"), "x_beam Z max"), "beam top"),
        (G("lower belt strand Z", ("bb", ka("x_belt_lo"), "zmid"), "x_belt_lo centre Z"), "lower strand"),
        (G("idler axle Z", ("cyl", ka("x_idler"), "y", 18.0, (M.X_IDLER_X, M.BEAM_Y0 + 6, M.X_PULLEY_Z), "z", False), "x_idler axis Z"), "idler axle"),
        (G("upper belt strand Z", ("bb", ka("x_belt_hi"), "zmid"), "x_belt_hi centre Z"), "upper strand"),
        (G("beam bottom Z (detail)", ("bb", ka("x_beam"), "zmin"), "x_beam Z min"), "beam bottom"),
        (G("switch finger flat Z", ("plane", ka("x_bracket"), "z", (L.X_HOME_SWITCH - M.XB_HALF - 8.0, 90.0, M.XF_Z[0])), "x_bracket finger underside Z"), "finger flat"),
    ]
    ordinates_v(va, [(r.value, f"Z {r.text}  {t}", [r]) for r, t in zs], 46.0, va.x + va.w + 12.0, gap=4.6, lo=58.0, hi=150.0)
    sh.note(va.x, va.y - 9.0, f"Click at cup X {hs.text} (+/-2, BUILD_GUIDE 6.8)", [hs], va="top")
    # detail B: right end at the right hard stop
    sb_ = "xdet:1262"
    pb = geo.parts(sb_)
    dbs = compound([pb[n].shape for n in X_PARTS if n in pb and n not in ("x_idler", "x_idler_mount", "x_idler_slider", "x_bumper_L", "x_switch_mount", "x_home_switch", "upright_L")])
    vb = make_view(sh, dbs, "front", S12, 190.0, 64.0, hidden=False, window=(1222.0, 322.0, 1352.0, 470.0), clip=True)
    sh.text(vb.x, vb.y + vb.h + 16.0, "DETAIL B (1:2): right end, carriage on the right stop", weight="bold")
    kb = lambda n: f"xdet/1262/{n}"  # noqa: E731
    sh.text(vb.x, vb.y + vb.h + 11.5, "(cup X = X_HARD_STOP[1]; front view)")
    ma = G("motor axis to the right stop face", s_sub(("cyl", kb("x_pulley"), "y", 16.0, (M.X_MOTOR_X, M.BEAM_Y0 + 9, M.X_PULLEY_Z), "x", False), ("bb", kb("x_motor_mount"), "xmin")),
           "x_pulley axis X - x_motor_mount X min")
    # above the clipped view (window top Z 470), to the motor's centre line: crosses neither the motor nor the mount outline
    zt = g("x_motor_mount", "zmax", sb_)
    vb.centerline((M.X_MOTOR_X, M.X_PULLEY_Z - 30.0), (M.X_MOTOR_X, 470.0 + 8.0 * vb.k))
    vb.dim((g("x_motor_mount", "xmin", sb_), zt), (M.X_MOTOR_X, zt), "h", (470.0 - zt) / vb.k + 4.0, ma)
    sh.text(vb.x + vb.w / 2, vb.y - 3.0, "x_bracket lands on the mount's left end", ha="center", va="top")
    # Y stack-up from the cup axis to the beam
    tx = 318.0
    sh.text(tx, 146.0, "Y stack-up, cup axis to the X beam's front face", weight="bold")
    stack = [("ARM_TO_CUP", "drop-arm centre to cup axis"), ("EXT20", "drop arm (2020): half = 10", 0.5), ("Z_PLATE_T", "z_plate"), ("MGN12_H", "Z carriage (MGN12H)"),
             ("EXT20", "Z spine (2040, 20 deep)"), ("X_BRACKET_T", "x_bracket"), ("MGN12_H", "X carriage (MGN12H)")]
    rows = [["Constant (layout.py)", "mm", "Part"]]
    recs = [[]]
    for st in stack:
        name, what = st[0], st[1]
        r = C(name)
        if len(st) > 2:
            rows.append([f"{name} / 2", fmt(r.value * st[2]) + f" (of {r.text})", what])
        else:
            rows.append([name, r.text, what])
        recs.append([r])
    tot = C("Y_CUP_TO_BEAM")
    rows.append(["= Y_CUP_TO_BEAM", tot.text, "sum: cup axis to beam front face"])
    recs.append([tot])
    yb, cells = sh.table(tx, 141.0, rows, [38.0, 24.0, 38.0])
    _attach({i: [a for r_, c_, a in cells if r_ == i] for i in range(1, len(rows))}, [{"recs": x} for x in recs])
    bf = G("beam front face Y", ("bb", akey("x_beam"), "ymin"), "x_beam Y min (cup axis at Y 0)")
    sh.note(tx, yb - 4.0, f"CAD check: beam front face at Y {bf.text}", [bf], va="top")
    sh.wrap(NOTE_AREA[0], NOTE_AREA[3] - 1.0, "FRONT: X axis with the carriage at home (cup over pocket 1); Z axis and head not shown. "
            "cup X = machine X of the suction-cup axis. Belt: GT2 loop over the beam top, both ends clamped on the x_bracket tab (BUILD_GUIDE 6.5).",
            NOTE_AREA[2] - NOTE_AREA[0])


SHEET_FUNCS["xaxis"] = sheet_xaxis


# --------------------------------------------------------------------------------------- D-05 Z axis and head stack-up
Z_TABLE = [
    ("SLAB_T", "c at pick contact = top of the stack: one slab (pose pick_bottom) = SLAB_T; n slabs = n x SLAB_T, nominal"),
    ("CUP_HANG", "the free cup hangs this far below c; the probe trips after this much buffer travel"),
    ("PROBE_TRIP_TOL", "trip tolerance on CUP_HANG (BUILD_GUIDE 7.6)"),
    ("PROBE_WINDOW", "max probing travel past the predicted contact"),
    ("BUFFER_STROKE", "spring buffer stroke (SMC ZPT25UUK20-B5-A10)"),
    ("STATION_LENS_Z", "station lens front above the pad top"),
    ("STATION_READ_C", "c at the station read = STATION_LENS_Z + CAM_TO_SLAB + SLAB_T + CUP_HANG"),
    ("CAM_TO_SLAB", "both cameras: lens front to the slab face"),
    ("HEAD_CAM_DY", "head lens axis, Y from the cup axis (negative = toward the label end)"),
    ("POST_H", "guide-rod tops above the pad top"),
    ("C_SAFE_LOADED", "carry height, loaded and empty (C_SAFE_EMPTY is the same)"),
    ("CARRY_SENSOR_C0", "carry sensor: beam blocked from this c up to the top stop"),
    ("CARRY_BAND", "carry sensor band: within it either reading is allowed"),
    ("C_MAX", "top of the software's Z travel"),
    ("Z_SWITCH_C", "Z top (home) switch trip"),
    ("C_HARD_TOP", "top hard stop: z_plate meets z_motor_mount"),
    ("C_MIN", "lowest c the design allows"),
    ("C_HARD_BOTTOM", "bottom hard stop: Z carriage skirts on the z_end_cap lips"),
    ("Z_CARRIAGE_ABOVE_CUP", "Z carriage bottom edge above the cup face"),
    ("Z_SPINE_BOTTOM", "spine bottom end above the pad top (set +/-1, BUILD_GUIDE 7.1)"),
    ("Z_SCREW_DX", "lead screw axis, X from the cup axis"),
    ("Z_SPINE_OFFSET_X", "Z spine centre, X from the cup axis"),
]


def sheet_zaxis(sh: Sheet, geo: Geo, plan):
    parts = geo.parts("asm:home")
    keep = [n for n, p in parts.items() if p.group in ("carriage", "head") and p.kind not in ("fastener", "slab")] + ["x_beam", "x_rail"]
    shape = compound([parts[n].shape for n in keep])
    cup = ("bb", akey("cup"), "zmin")
    # window: the cup face (248) to just over the Z motor (671); placed clear of the title block (its top is at 50)
    vr = make_view(sh, shape, "right", S12, 74.0, 52.0, hidden=False, window=(-34.0, 245.0, 150.0, 674.0), clip=True, lw=0.7)
    xr_ = vr.x + vr.w + 12.0  # the right-hand label column
    sh.text(xr_, TOP - 4.0, "RIGHT SIDE (1:2): Z axis and head, home pose", weight="bold", va="top")
    sh.text(xr_, TOP - 9.0, "(c = C_SAFE_LOADED); fasteners not shown", va="top")
    vr.centerline((0.0, 220.0), (0.0, 674.0))
    g = lambda n, w: bb_value(geo.shape(akey(n)), w)  # noqa: E731
    head = [
        (G("cup face (home pose)", cup, "cup (pad) Z min at the home pose"), "c = {}  cup face (home pose)"),
        (G("head_foot underside above c", s_sub(("bb", akey("head_foot"), "zmin"), cup), "head_foot Z min - cup face Z"), "c + {}  head_foot underside"),
        (G("probe beam above c", s_sub(("bb", akey("contact_sensor"), "zmid"), cup), "contact_sensor (TCST2103 board) centre Z - cup face Z"), "c + {}  probe sensor beam"),
        (G("head LED ring face above c", s_sub(("bb", akey("head_led_ring"), "zmin"), cup), "head_led_ring Z min - cup face Z"), "c + {}  head LED ring face"),
        (G("head lens front above c", s_sub(("bb", akey("head_camera"), "zmin"), cup), "head_camera Z min (lens front) - cup face Z"), "c + {}  head lens front"),
        (G("Z carriage bottom above c", s_sub(("bb", akey("z_carriage"), "zmin"), cup), "z_carriage Z min - cup face Z"), "c + {}  Z carriage bottom"),
        (G("carry flag top edge above c", s_sub(("bb", akey("carry_flag"), "zmax"), cup), "carry_flag Z max (trip edge) - cup face Z"), "c + {}  carry flag trip edge"),
        (G("z_plate top above c", s_sub(("bb", akey("z_plate"), "zmax"), cup), "z_plate Z max - cup face Z"), "c + {}  z_plate top (top stop)"),
    ]
    cz = head[0][0].value
    hv = [cz] + [cz + r.value for r, _ in head[1:]]
    ordinates_v(vr, [(v, t.format(r.text), [r]) for v, (r, t) in zip(hv, head)], 150.0, xr_, gap=4.6, lo=TB_Y0 + TB_H + 4.0, hi=TOP - 22.0)
    sh.text(xr_, TOP - 16.0, "Moves with Z (c = cup face):", weight="bold", va="top")
    fixed = [
        (G("z_end_cap underside Z", ("bb", akey("z_end_cap"), "zmin"), "z_end_cap Z min"), "end cap underside"),
        (G("Z spine bottom Z", ("bb", akey("z_spine"), "zmin"), "z_spine Z min"), "spine bottom"),
        (G("Z rail bottom Z", ("bb", akey("z_rail"), "zmin"), "z_rail Z min"), "Z rail bottom"),
        (G("lead screw tip Z", ("bb", akey("z_leadscrew"), "zmin"), "z_leadscrew Z min"), "lead screw tip"),
        (G("carry sensor beam Z", ("bb", akey("carry_sensor"), "zmid"), "carry_sensor (board) centre Z"), "carry sensor beam"),
        (G("Z rail top Z", ("bb", akey("z_rail"), "zmax"), "z_rail Z max"), "Z rail top"),
        (G("Z spine top Z", ("bb", akey("z_spine"), "zmax"), "z_spine Z max"), "spine top"),
        (G("Z motor face Z", ("bb", akey("z_motor_mount"), "zmax"), "z_motor_mount Z max (motor face)"), "motor face"),
        (G("Z motor top Z (D-05)", ("bb", akey("z_motor"), "zmax"), "z_motor Z max"), "Z motor top"),
    ]
    ordinates_v(vr, [(r.value, f"Z {r.text}  {t}", [r]) for r, t in fixed], -34.0, vr.x - 10.0, gap=4.6, side="left", lo=50.0, hi=TOP - 10.0)
    sh.text(16.0, TOP - 4.0, "Fixed to the X carriage, Z:", weight="bold", va="top")
    # Y offsets
    arm = G("drop arm centre Y from the cup axis", s_sub(("bb", akey("drop_arm"), "ymid"), ("bb", akey("cup"), "ymid")), "drop_arm centre Y - cup centre Y")
    vr.dim((0.0, cz), (arm.value, g("drop_arm", "zmin")), "h", -5.0, arm, post=" drop arm", text_at="left")
    cam = G("head lens axis offset from the cup axis, toward -Y (the label end)", _neg(s_sub(("bb", akey("head_camera"), "ymid"), ("bb", akey("cup"), "ymid"))),
            "cup centre Y - head_camera centre Y")
    vr.dim((-cam.value, g("head_camera", "zmax")), (0.0, g("head_camera", "zmax")), "h", 4.0, cam, pre="lens axis ", post=" toward -Y", text_at="left")
    beam = G("beam front face Y from the cup axis", s_sub(("bb", akey("x_beam"), "ymin"), ("bb", akey("cup"), "ymid")), "x_beam Y min - cup centre Y")
    # under the view, below the cup: a line from the cup axis to the beam face at any height in the view would cross the arm, rail and spine
    vr.dim((0.0, cz), (beam.value, g("x_beam", "zmin")), "h", -13.0, beam, post=" to the X beam face")
    # table
    tx, ty = 270.0, TOP - 3.0
    sh.text(tx, ty, "Z-height table (values read from cad/layout.py)", weight="bold", va="top")
    rows = [["Constant", "Value", "Meaning"]]
    recs = [[]]
    for name, what in Z_TABLE:
        r = C(name)
        rows.append([name, r.text, what])
        recs.append([r])
    yb, cells = sh.table(tx, ty - 5.5, rows, [51.0, 14.0, PW - 14.0 - tx - 65.0])
    _attach({i: [a for r_, c_, a in cells if r_ == i and c_ == 1] for i in range(1, len(rows))}, [{"recs": x} for x in recs])


SHEET_FUNCS["zaxis"] = sheet_zaxis


# ---------------------------------------------------------------------------------------------------- D-06 flat parts
def _neg(spec):
    return ("mul", spec, -1.0)


def sheet_flat(sh: Sheet, geo: Geo, plan):
    pts = M.flag_blank()
    us, vs = [u for u, _ in pts], [v for _, v in pts]
    F = lambda i, c: ("flag", (i, c))  # noqa: E731
    i_band, i_blade_in, i_bot_in, i_bot_out, i_top_out, i_top_in, i_tab_r, i_tab_l = range(8)
    vb = View(sh, "blank", (min(us), min(vs), max(us), max(vs)), S21, 46.0, 102.0)
    poly = np.array(pts + [pts[0]])
    vb.ax.fill(poly[:, 0], poly[:, 1], color="#e4e8ee", zorder=0)
    vb.polys([poly], lw=LW_VIS)
    vb.seg((min(us) - 6.0, 0.0), (pts[i_tab_r][0] + 6.0, 0.0), lw=0.6, ls=DASH_HID, owner=-3)
    vb.text(pts[i_tab_r][0] + 3.5, 0.6, "BEND LINE", ha="left", va="bottom")
    vb.centerline((0.0, min(vs) - 4.0), (0.0, max(vs) + 1.5))  # stops under the tab-width dimension
    sh.text(vb.x - 26.0, vb.y + vb.h + 30.0, "PROBE FLAG BLANK (2:1), flat, before bending", weight="bold")
    sh.text(vb.x - 26.0, vb.y + vb.h + 25.5, "u from the neck centre line (= hole line), v from the bend line")
    r_tot = G("probe flag blank width", s_sub(F(i_bot_out, "u"), F(i_band, "u")), "model.flag_blank(): blade outer edge u - neck edge u")
    r_tab = G("probe flag neck/tab width", s_sub(F(i_tab_r, "u"), F(i_tab_l, "u")), "model.flag_blank(): tab edges u")
    r_bi = G("probe flag blade inner edge from the centre line", F(i_blade_in, "u"), "model.flag_blank(): blade inner edge u (u 0 = neck centre line)")
    r_bo = G("probe flag blade outer edge from the centre line", F(i_bot_out, "u"), "model.flag_blank(): blade outer edge u")
    r_top = G("probe flag trip edge below the bend line", _neg(F(i_top_out, "v")), "model.flag_blank(): blade top (trip) edge v, below the bend line")
    r_bot = G("probe flag blade bottom below the bend line", _neg(F(i_bot_out, "v")), "model.flag_blank(): blade bottom v, below the bend line")
    r_band = G("probe flag band bottom below the bend line", _neg(F(i_band, "v")), "model.flag_blank(): band bottom v")
    r_tabv = G("probe flag tab length past the bend line (trim)", F(i_tab_r, "v"), "model.flag_blank(): tab end v")
    tl, tr = pts[i_tab_l], pts[i_tab_r]
    vb.dim(tl, tr, "h", 5.0, r_tab, text_du=5.0)  # text right of the neck centre line
    vb.dim(tl, pts[i_top_out], "h", 12.0, r_tot, pre="(", post=") blank, reference")  # = tab half width + blade outer edge
    vb.dim((0.0, pts[i_bot_in][1]), pts[i_bot_in], "h", -5.0, r_bi)
    vb.dim((0.0, pts[i_bot_out][1]), pts[i_bot_out], "h", -12.0, r_bo)
    vb.dim((pts[i_top_out][0], 0.0), pts[i_top_out], "v", 5.0, r_top, post=" to the\ntrip edge")
    vb.dim((pts[i_bot_out][0], 0.0), pts[i_bot_out], "v", 28.0, r_bot)  # outside the 8.5 dimension's text
    vb.dim((tl[0], 0.0), pts[i_band], "v", -5.0, r_band)
    vb.dim((tl[0], 0.0), tl, "v", -5.0, r_tabv, post=" (trim)")
    r_len = G("probe flag blank length", s_sub(F(i_tab_r, "v"), F(i_bot_out, "v")), "model.flag_blank(): tab end v - blade bottom v")
    vb.dim(tr, pts[i_bot_out], "v", 40.0, r_len, pre="(", post=") blank,\nreference")  # = trim length + blade bottom below the bend
    # the bent flag, for reference
    pf = geo.shape("local/probe_flag")
    b = bbox(pf)
    fx, fy = 168.0, 104.0
    vfr = make_view(sh, pf, "front", S21, fx, fy, hidden=True)
    vto = make_view(sh, pf, "top", S21, fx, fy + vfr.h + 12.0, hidden=True)
    vri = make_view(sh, pf, "right", S21, fx + vfr.w + 14.0, fy, hidden=True)
    sh.text(vfr.x + vfr.w / 2, vfr.y - 3.0, "FRONT", weight="bold", ha="center", va="top")
    sh.text(vto.x + vto.w + 3.0, vto.y + vto.h / 2, "TOP", weight="bold", va="center")
    sh.text(vri.x + vri.w / 2, vri.y - 11.0, "RIGHT", weight="bold", ha="center", va="top")
    sh.text(fx, vto.y + vto.h + 14.0, "PROBE FLAG AS BENT (2:1), for reference", weight="bold")
    sh.text(fx, vto.y + vto.h + 9.5, "(head frame: X along the row, Z above the cup face)")
    hole = ("cyl", "local/probe_flag", "z", M.FLAG_HOLE, (0.0, 0.0, b[5] - 0.5), "d")
    hy = ("cyl", "local/probe_flag", "z", M.FLAG_HOLE, (0.0, 0.0, b[5] - 0.5), "y")
    inner = ("plane", "local/probe_flag", "y", (15.0, M.PROBE_Y - M.FLAG_T / 2, (M.FLAG_TOP + M.FLAG_BOTTOM) / 2))
    outer = ("plane", "local/probe_flag", "y", (15.0, M.PROBE_Y + M.FLAG_T / 2, (M.FLAG_TOP + M.FLAG_BOTTOM) / 2))
    r_hd = G("probe flag hole diameter", hole, "probe_flag tab hole diameter")
    r_hp = G("probe flag hole axis to the plate's inner face", s_sub(inner, hy), "probe_flag plate inner face Y - tab hole axis Y")
    r_t = G("probe flag sheet thickness", s_sub(outer, inner), "probe_flag plate faces Y")
    r_end = G("probe flag tab end past the hole", s_sub(s_sub(hy, ("mul", hole, 0.5)), ("bb", "local/probe_flag", "ymin")), "probe_flag hole edge Y - tab end Y")
    r_ri = G("probe flag bend inside radius", ("mul", ("cyl", "local/probe_flag", "x", 2 * M.FLAG_BEND_R, (0.0, M.PROBE_Y - M.FLAG_T / 2 - M.FLAG_BEND_R, M.FLAG_BEND_Z), "d"), 0.5),
           "probe_flag bend inner cylinder radius")
    vto.dim((0.0, 0.0), (12.0, M.PROBE_Y - M.FLAG_T / 2), "v", (b[0] - 0.0) / vto.k - 6.0, r_hp)
    vto.leader((r_hd.value / 2 * 0.707, -r_hd.value / 2 * 0.707), 14.0, -10.0, [f"Ø{r_hd.text} drill AFTER bending"], [r_hd])
    vri.leader((M.PROBE_Y - M.FLAG_T / 2 - M.FLAG_BEND_R, M.FLAG_BEND_Z + 0.7), 12.0, 6.0, [f"bend 90°, inside R{r_ri.text}", "(90 +/-0.5°, BUILD_GUIDE 7.6)"], [r_ri])
    vri.dim((M.PROBE_Y - M.FLAG_T / 2, M.FLAG_BOTTOM), (M.PROBE_Y + M.FLAG_T / 2, M.FLAG_BOTTOM), "h", -5.0, r_t, post=" sheet")
    # carry flag
    cf = geo.shape("local/carry_flag")
    cb = bbox(cf)
    vc = make_view(sh, cf, "front", S21, 332.0, 116.0, hidden=False)
    sh.text(vc.x - 18.0, vc.y + vc.h + 22.0, "CARRY FLAG (2:1), flat", weight="bold")
    sh.text(vc.x - 18.0, vc.y + vc.h + 17.5, "(seen from the front; top edge = trip edge)")
    hs = sorted(holes_of(geo, "local/carry_flag", "y", M.M3_CLR), key=lambda f: f["c"][1])
    lo_, hi_ = hs[0], hs[-1]
    cyl_ = lambda f, w: ("cyl", "local/carry_flag", "y", M.M3_CLR, (f["c"][0], M.CS_Y, f["c"][1]), w)  # noqa: E731
    r_w = G("carry flag width", ("bb", "local/carry_flag", "xlen"), "carry_flag X")
    r_h = G("carry flag height", ("bb", "local/carry_flag", "zlen"), "carry_flag Z")
    r_ct = G("carry flag thickness", ("bb", "local/carry_flag", "ylen"), "carry_flag Y")
    r_out = G("carry flag holes from the outer edge", s_sub(cyl_(lo_, "x"), ("bb", "local/carry_flag", "xmin")), "carry_flag hole axis X - outer edge X")
    r_in = G("carry flag holes from the inner edge", s_sub(("bb", "local/carry_flag", "xmax"), cyl_(lo_, "x")), "carry_flag inner edge X - hole axis X")
    r_t1 = G("carry flag upper hole below the top edge", s_sub(("bb", "local/carry_flag", "zmax"), cyl_(hi_, "z")), "carry_flag top edge Z - upper hole Z")
    r_t2 = G("carry flag lower hole below the top edge", s_sub(("bb", "local/carry_flag", "zmax"), cyl_(lo_, "z")), "carry_flag top edge Z - lower hole Z")
    r_cd = G("carry flag hole diameter", cyl_(lo_, "d"), "carry_flag hole diameter")
    hx = lo_["c"][0]
    vc.dim((cb[0], cb[2]), (cb[3], cb[2]), "h", -6.0, r_w)
    vc.dim((cb[0], cb[2]), (cb[0], cb[5]), "v", -6.0, r_h)
    vc.dim((cb[0], cb[5]), (hx, hi_["c"][1]), "h", 5.0, r_out, pre="(", post=")")  # reference: = width - the inner-edge distance
    vc.dim((hx, hi_["c"][1]), (cb[3], cb[5]), "h", 5.0, r_in, text_at="right")
    vc.dim((cb[3], cb[5]), (hx, hi_["c"][1]), "v", 6.0, r_t1)
    vc.dim((cb[3], cb[5]), (hx, lo_["c"][1]), "v", 15.0, r_t2)
    for f in hs:
        vc.cmark(f["c"][0], f["c"][1], M.M3_CLR / 2, ext=1.5)
    vc.leader((hx + M.M3_CLR / 2 * 0.707, lo_["c"][1] - M.M3_CLR / 2 * 0.707), 10.0, -12.0, [f"2x Ø{r_cd.text}"], [r_cd])
    # notes
    ny = 84.0
    sh.text(16.0, ny, "Probe flag (BUILD_GUIDE 7.6; build.py probe_flag_blank.svg notes)", weight="bold")
    sh.wrap_recs(16.0, ny - 4.0,
                 f"Aluminium sheet, {r_t.text} thick, a soft alloy: 1050, 3003 or 5052-H32, not 6061-T6 (a 1 mm inside bend radius can crack it "
                 f"[Likely], BOM.csv). Blank {r_tot.text} x {r_len.text} (cut_list C-07 and BUILD_GUIDE 4.1 round the length to 55). "
                 f"1. Cut and file to the outline; the blade's top edge is the trip edge: straight, "
                 f"square. 2. This view shows the face toward the buffer. Neck in the vise, jaws at the BEND line; bend the tab 90° TOWARD YOU. "
                 f"3. THEN drill on the centre line, {r_hp.text} from the plate's inner face. 4. Trim the tab to {r_end.text} past the hole. 5. Deburr: it rides "
                 f"in head_foot's guide slot and the sensor slot. Outline: cad/out/probe_flag_blank.dxf (1:1 print: .svg).", 270.0,
                 [r_t, r_hp, r_end, r_tot, r_len])
    sh.text(300.0, 100.0, "Carry flag (BUILD_GUIDE 7.4a)", weight="bold")
    sh.wrap_recs(300.0, 96.0, f"Aluminium sheet, {r_ct.text} thick, flat: 1050, 3003 or 5052-H32 as the probe flag (BOM.csv) (cut_list C-10). "
                 "File the top edge straight. Fix to carry_flag_arm's leg end with "
                 "2 x M3x8, inner edge toward the spine, top edge flush with the arm's top.", PW - 14.0 - 300.0, [r_ct])
    sh.wrap(NOTE_AREA[0], 44.0, "Tolerance: outlines PROPOSED +/-0.2 (no doc states one); bend 90 +/-0.5° (BUILD_GUIDE 7.6). The trip points are set by "
            "adjustment on assembly (probe 7.6, carry 7.4a), not by these outlines.", NOTE_AREA[2] - NOTE_AREA[0])


SHEET_FUNCS["flat"] = sheet_flat


# ----------------------------------------------------------------------------------------------------------- D-00 index
def sheet_index(sh: Sheet, geo: Geo, plan):
    sh.text(16.0, TOP - 4.0, "SHEET INDEX", weight="bold", va="top")
    rows = [["Sheet", "Title"]] + [[num, title] for num, title, _ in plan]
    yb, _ = sh.table(16.0, TOP - 9.5, rows, [20.0, 150.0])
    sh.text(16.0, yb - 6.0, "PART TYPES (how each part is identified)", weight="bold", va="top")
    pr = [["Type", "Identified by"],
          ["B  bought", "its line in docs/BOM.csv; modelled as an envelope, exact only where it meets other parts"],
          ["C  cut stock", "item C-01 to C-11 on D-02 = the rows of cad/out/cut_list.csv (extrusions, lead screw, dowels)"],
          ["P  printed", "file name in cad/out/printed/ (<part>.step / .stl); qty, material and print note from print_list.json"],
          ["W  plywood", "the bed (D-03)"],
          ["S  sheet metal", "the 1 mm aluminium flags (D-06); probe flag outline cad/out/probe_flag_blank.dxf"]]
    sh.table(16.0, yb - 11.5, pr, [30.0, 140.0])
    x0, w = 200.0, PW - 14.0 - 200.0
    sh.text(x0, TOP - 4.0, "GENERAL NOTES", weight="bold", va="top")
    y = TOP - 10.0
    hb, zb, xs, zs, cs, ch, sl, gz, ct = (C("Z_SPINE_BOTTOM"), C("Z_CARRIAGE_ABOVE_CUP"), C("X_HOME_SWITCH"), C("Z_SWITCH_C"), C("CARRY_SENSOR_C0"),
                                          C("CUP_HANG"), C("STATION_LENS_Z"), C("GATE_Z"), C("CAM_TO_SLAB"))
    post = G("Phase 0 jig post length", ("bb", "p0/p0_post_1", "zlen"), "p0_post_1 Z")
    paras = [
        ("1. Units: millimetres; angles in degrees. Do not scale the drawing.", []),
        ("2. Projection: third angle. Views are hidden-line-removed projections of cad/model.py (build.py poses; printed parts as exported); "
         "hidden edges, where shown, are dashed; a section view hatches the faces its cutting plane cuts (D-17).", []),
        ("3. Coordinates (cad/layout.py): X left to right along the pocket row, Y front to back, Z up; Z 0 = top of the pocket pads. "
         "Cup X = machine X of the suction-cup axis; c = height of the cup face. Datum O (X 0, Y 0): D-03.", []),
        ("4. Every dimension is measured from the CAD by cad/drawings.py or read from a named cad/layout.py constant; "
         "cad/out/drawings/dims.json lists each one with its source, and a self-check re-measures them from fresh geometry (0.05). "
         "Confidence tags [Certain] / [Likely] / [Guessing] are the docs'.", []),
        ("5. Bought parts are envelopes; check them on arrival (BUILD_GUIDE 3.3). Not in the CAD and not drawn: frame joints "
         "(BUILD_GUIDE 4.3), cables and drag chain, vacuum tube, belt slack, supports of the light roof.", []),
        ("6. GENERAL TOLERANCES, unless a sheet states otherwise:", []),
        ("a) Extrusion cut lengths +/-0.5, square ends (BUILD_GUIDE 4.1, the supplier's cut tolerance). Phase 0 jig posts "
         f"{post.text} +/-0.5, square (BUILD_GUIDE 1.1). Lead screw: 311 to 356 below the motor face works (cut_list.csv).", [post]),
        ("b) Frame (BUILD_GUIDE 4.5, D-02): base-rail centres +/-0.5; upright inner faces +/-0.5 [Certain, CAD]; bed top to beam "
         "bottom +/-0.5 [Certain, CAD]; diagonals equal within 1. X rail top edge 4.00 +/-0.1 below the beam top (6.2).", []),
        (f"c) Set on assembly (BUILD_GUIDE): spine bottom {hb.text} +/-1 above the pad top (7.1); Z carriage bottom {zb.text} +/-2 above "
         f"the cup face (7.5); X home click at cup X {xs.text} +/-2 (6.8); Z top click at c {zs.text} +/-2 (7.4); carry-sensor trip at "
         f"c {cs.text} +/-1 (7.4a); probe trip at {ch.text} +/-0.5 of buffer travel (7.6); station lens front {sl.text} +/-1 above the pads "
         f"(5.9); laser beam {gz.text} +/-1 above the pad top (12.5); flag bend 90 +/-0.5° (7.6); Phase 0 jig: slab ledge {ct.text} +/-2 above "
         f"the station lens (1.5).", [hb, zb, xs, zs, cs, ch, sl, gz, ct]),
        ("d) PROPOSED, no doc states one (to agree in review): printed parts +/-0.3; plywood outline +/-0.5; sheet-metal outlines "
         "+/-0.2; dowel cut length +/-0.5. Printed clearance holes are drilled out after printing: M3 3.4, M5 5.5 (BUILD_GUIDE 3.4).", []),
        ("7. Status: Rev A, draft for design review. Nothing has been built; the Phase 0 go / no-go tests (D-17) come first. "
         "Not released for fabrication.", []),
    ]
    for txt, recs in paras:
        ind = 6.0 if txt[:2] in ("a)", "b)", "c)", "d)") else 0.0
        y = sh.wrap_recs(x0 + ind, y, txt, w - ind, recs) - 2.2


SHEET_FUNCS["index"] = sheet_index


# ---------------------------------------------------------------------------------------------------- D-17 Phase 0 jig
def sheet_jig(sh: Sheet, geo: Geo, plan):
    parts = geo.parts("p0")
    shape = compound([p.shape for n, p in parts.items() if p.kind != "fastener"])
    b = bbox(shape)
    vf = make_view(sh, shape, "front", S12, 34.0, 70.0, hidden=False, lw=0.7)
    # SECTION A-A on X = 0 (both lens axes), seen from +X: the half at X <= 0, cut faces hatched
    halves = [(h_, p.kind) for p in parts.values() if p.kind != "fastener" for h_ in [section_half(p.shape, 0.0)] if h_ is not None]
    vr = make_view(sh, compound([h_ for h_, _ in halves]), "right", S12, 34.0 + vf.w + 20.0, 70.0, hidden=False, lw=0.7,
                   window=proj_box("right", b))
    hatch_section(vr, halves, 0.0)
    cutting_plane(vf, 0.0, "A")
    sh.text(vf.x, vf.y + vf.h + 6.0, "FRONT (1:2)", weight="bold")
    sh.text(vr.x, vr.y + vr.h + 6.0, "SECTION A-A (1:2)", weight="bold")
    sh.text(vr.x, vr.y + vr.h + 1.5, "on both lens axes, seen from +X; cut faces hatched")
    sh.text(16.0, TOP - 4.0, "PHASE 0A TEST JIG: one slab between the two cameras, as on the machine (BUILD_GUIDE 1.5); fasteners not shown",
            weight="bold", va="top")
    g = lambda n, w: bb_value(geo.shape(f"p0/{n}"), w)  # noqa: E731
    post = G("jig post length", ("bb", "p0/p0_post_1", "zlen"), "p0_post_1 Z")
    vf.dim((g("p0_post_-1", "xmin"), g("p0_post_-1", "zmin")), (g("p0_post_-1", "xmin"), g("p0_post_-1", "zmax")), "v",
           -(g("p0_post_-1", "xmin") - b[0]) / 2 - 6.0, post)
    pc = G("jig post centres", s_sub(("bb", "p0/p0_post_1", "xmid"), ("bb", "p0/p0_post_-1", "xmid")), "p0_post_1 centre X - p0_post_-1 centre X")
    vf.dim((g("p0_post_-1", "xmid"), b[2]), (g("p0_post_1", "xmid"), b[2]), "h", -14.0, pc, post=" post centres")  # below the A-A arrow
    for n in ("p0_post_-1", "p0_post_1"):
        vf.centerline((g(n, "xmid"), b[2] - 4.0), (g(n, "xmid"), b[5] + 4.0))
    lv = [
        (G("jig socket floor Z", ("bb", "p0/p0_post_1", "zmin"), "p0_post_1 Z min (socket floor)"), "post bottoms (socket floor)"),
        (G("jig station lens front Z", ("bb", "p0/p0_station_camera", "zmax"), "p0_station_camera Z max (lens front)"), "station lens front"),
        (G("jig slab front face Z", ("bb", "p0/p0_slab", "zmin"), "p0_slab Z min (front face, on the ledges)"), "slab front face (ledges)"),
        (G("jig slab back Z", ("bb", "p0/p0_slab", "zmax"), "p0_slab Z max"), "slab back"),
        (G("jig bridge underside Z", ("bb", "p0/p0_top", "zmin"), "p0_top Z min"), "bridge underside"),
        (G("jig head lens front Z", ("bb", "p0/p0_head_camera", "zmin"), "p0_head_camera Z min (lens front)"), "head lens front"),
        (G("jig post tops Z", ("bb", "p0/p0_post_1", "zmax"), "p0_post_1 Z max"), "post tops"),
    ]
    ordinates_v(vr, [(r.value, f"Z {r.text}  {t}", [r]) for r, t in lv], vr.u1, vr.x + vr.w + 12.0, gap=4.6, lo=58.0, hi=TOP - 12.0)
    sh.text(vr.x + vr.w + 12.0, TOP - 9.0, "Heights above the base underside", weight="bold", va="top")
    d1 = G("jig station lens to slab front", s_sub(("bb", "p0/p0_slab", "zmin"), ("bb", "p0/p0_station_camera", "zmax")), "p0_slab Z min - p0_station_camera Z max")
    d2 = G("jig slab back to head lens", s_sub(("bb", "p0/p0_head_camera", "zmin"), ("bb", "p0/p0_slab", "zmax")), "p0_head_camera Z min - p0_slab Z max")
    # each along a clear vertical in the section (CAD clearances): station side at Y -20 (inside the ring seat's shelf, outside the
    # post seen behind); head side at Y -15.5 (inside the bridge's lens window, outside the cup and the head_foot)
    r_sl, r_hl = 4.5, 7.0  # lens radii (model.station_camera, phase0_parts): locate the extension lines only
    vr.dim((-r_sl, g("p0_station_camera", "zmax")), (-20.0, g("p0_slab", "zmin")), "v", 0.0, d1, text_at="left", over=1.0)
    vr.dim((-15.5, g("p0_slab", "zmax")), (M.CAM_DY - r_hl, g("p0_head_camera", "zmin")), "v", 0.0, d2, text_at="left", over=1.0)
    ct = C("CAM_TO_SLAB")
    # right-hand column (x >= 296): the ISO render over the parts table; the height labels keep x 229..292 free at every height
    h = sh.image(REPO / "docs" / "img" / "phase0_jig.png", 342.0, 166.0, 76.0)
    sh.text(342.0, 166.0 + h + 1.5, "ISO (render; not to scale)", weight="bold")
    stub = G("jig arm stub length", ("bb", "p0/p0_arm_stub", "zlen"), "p0_arm_stub Z")
    sp = {n: _sheet_of_part(plan, n) for n in ("phase0_base", "phase0_tray", "phase0_top", "phase0_occluder_mount", "head_foot")}
    rows = [["Part", "Type", "Qty", "Sheet"],
            ["phase0_base (camera mast, ring seat, post sockets)", "P", "1", sp["phase0_base"]],
            ["phase0_tray (the slab on edge ledges)", "P", "1", sp["phase0_tray"]],
            ["phase0_top (bridge: head camera, head ring)", "P", "1", sp["phase0_top"]],
            ["phase0_occluder_mount", "P", "1", sp["phase0_occluder_mount"]],
            ["head_foot, the machine's own (occluder)", "P", "1", sp["head_foot"]],
            [f"2020 post, {post.text}, cut square +/-0.5 (C-08)", "C", "2", "D-02"],
            [f"2020 arm stub, {stub.text} (C-09)", "C", "1", "D-02"],
            ["probe flag (C-07)", "S", "1", "D-06"],
            ["cameras, LED rings, SMC buffer + cup + elbow, endstop board", "B", "-", "BOM.csv"]]
    yb, cells = sh.table(296.0, 160.0, rows, [80.0, 10.0, 10.0, 21.8])
    _attach({i: [a for r_, c_, a in cells if r_ == i] for i in (6, 7)}, [{"recs": []}] * 6 + [{"recs": [post]}, {"recs": [stub]}])
    sh.wrap_recs(NOTE_AREA[0], NOTE_AREA[3] - 1.0,
                 f"The posts set the bridge height: cut them square. Both lens-to-slab distances (SECTION A-A) equal CAM_TO_SLAB = {ct.text} "
                 f"on the machine (set +/-2, BUILD_GUIDE 1.5). Phase 0 is the go / no-go test before any motion parts are bought.",
                 NOTE_AREA[2] - NOTE_AREA[0], [ct])


SHEET_FUNCS["jig"] = sheet_jig


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
        REG.res = 0.1 if isinstance(fn, tuple) else 0.01  # printed parts to 0.1 mm
        if isinstance(fn, tuple):
            sheet_printed(sh, geo, fn[1])
        else:
            SHEET_FUNCS[fn](sh, geo, plan)
        sc = sorted(set(sh.scales), key=lambda s: s.k)
        sh.title_block(", ".join(str(s) for s in sc) + (" (as noted)" if len(sc) > 1 else "") if sc else "NONE (text sheet)")
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
