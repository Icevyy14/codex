"""Geometric verification of the SlabRail model.

Builds the machine at every critical pose and measures exact minimum distances
(OpenCascade BRepExtrema) between moving and static parts:
  * picking the bottom slab of every pocket while both neighbours are full,
  * placing the first slab into an empty pocket (slab-to-rod play),
  * empty and loaded travel over full stacks,
  * reading at the upward-camera station,
  * X / Z travel extremes against the frame, carriage-on-rail margins,
  * camera line-of-sight to the label (head camera and station camera).
Exit code 1 if any check fails. Run:  python checks.py
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass

import cadquery as cq

import layout as L
import model as M
from dims import SLAB_H, SLAB_T

P = L.pockets()
FULL = {p.index: L.STACK_MAX for p in P if p.role == "source"}


@dataclass
class Result:
    name: str
    ok: bool
    value: float
    limit: float
    detail: str = ""


results: list[Result] = []


def record(name, value, limit, detail="", larger_is_better=True):
    ok = value >= limit if larger_is_better else value <= limit
    results.append(Result(name, ok, round(value, 2), limit, detail))


def _near(a: cq.Shape, b: cq.Shape, margin: float) -> bool:
    ba, bb = a.BoundingBox(), b.BoundingBox()
    return not (ba.xmax + margin < bb.xmin or bb.xmax + margin < ba.xmin or ba.ymax + margin < bb.ymin or bb.ymax + margin < ba.ymin or ba.zmax + margin < bb.zmin or bb.zmax + margin < ba.zmin)


def min_dist(movers, obstacles, margin: float = 60.0) -> tuple[float, str]:
    best, pair = 1e9, ""
    for m in movers:
        ms = m.shape.val()
        for o in obstacles:
            os_ = o.shape.val()
            if not _near(ms, os_, margin):
                continue
            d = ms.distance(os_)
            if d < best:
                best, pair = d, f"{m.name} <-> {o.name}"
    return best, pair


def split(parts, include_carriage=False):
    groups = ("head", "carriage") if include_carriage else ("head",)
    moving = [p for p in parts if p.group in groups]
    static = [p for p in parts if p.group == "static" and not p.name.startswith("pad_") and p.name != "bed_plywood"]
    return moving, static


def check_pockets() -> None:
    for p in P:
        fill = dict(FULL)
        fill[p.index] = 1  # cup resting on the last slab of this pocket; neighbours full
        parts = M.machine(p.x, SLAB_T, fill=fill)
        mov, sta = split(parts, include_carriage=True)
        # the carriage rides on the rail and clamps the belt by design; those interfaces are covered by check_extremes
        sta = [s for s in sta if s.name not in (f"stack_{p.index}", f"labels_{p.index}") and not s.name.startswith(("x_rail", "x_belt", "x_beam", "x_pulley", "x_idler", "x_motor"))]
        d, pair = min_dist(mov, sta)
        record(f"pick last slab, pocket {p.index:2d}: head/carriage clearance", d, 3.0, pair)
    p0 = P[0]
    parts = M.machine(p0.x, SLAB_T, held_slab=True, fill=FULL)
    held = [p for p in parts if p.name == "held_slab"]
    rods = [p for p in parts if p.name.startswith("rod_")]
    d, pair = min_dist(held, rods)
    record("place first slab in pocket 0: slab-to-rod play (centred)", d, 1.0, pair)


def check_travel() -> None:
    for a, b in [(P[1], P[2]), (P[6], P[7]), (P[10], P[11])]:
        mx = (a.x + b.x) / 2
        parts = M.machine(mx, L.C_SAFE_EMPTY, fill=FULL)
        mov, sta = split(parts)
        d, pair = min_dist(mov, sta)
        record(f"empty travel {a.index}->{b.index}: clearance over rods/stacks", d, 9.0, pair)
        parts = M.machine(mx, L.C_SAFE_LOADED, held_slab=True, fill=FULL)
        mov, sta = split(parts)
        d, pair = min_dist(mov, sta)
        record(f"loaded travel {a.index}->{b.index}: clearance", d, 9.0, pair)
    for c in (0.0, SLAB_T):
        p = P[5]
        parts = M.machine(p.x, c, fill={**FULL, 5: 1})
        hi = [q for q in parts if q.name in ("z_spine", "z_rail", "z_plate", "z_carriage", "x_bracket")]
        sta = [q for q in parts if q.group == "static" and (q.name.startswith("rod_") or q.name.startswith("stack_"))]
        d, pair = min_dist(hi, sta)
        record(f"Z machinery over rods with cup at c={c:.1f}", d, 5.0, pair)


def frustum(apex, c0, c1) -> cq.Shape:
    """Pyramid from a point (camera) to an axis-aligned rectangle at height c0[2] (label)."""
    (x0, y0, z), (x1, y1, _) = c0, c1
    pts = [cq.Vector(x0, y0, z), cq.Vector(x1, y0, z), cq.Vector(x1, y1, z), cq.Vector(x0, y1, z)]
    a = cq.Vector(*apex)
    faces = [cq.Face.makeFromWires(cq.Wire.makePolygon([pts[i], pts[(i + 1) % 4], a], close=True)) for i in range(4)]
    faces.append(cq.Face.makeFromWires(cq.Wire.makePolygon(pts, close=True)))
    return cq.Solid.makeSolid(cq.Shell.makeShell(faces))


def check_station() -> None:
    sx, sy = L.station_xy()
    c = L.STATION_READ_C
    parts = M.machine(sx, c, held_slab=True, fill=FULL)
    held = [p for p in parts if p.name in ("held_slab", "held_label")]
    sta = [p for p in parts if p.group == "static" and not p.name.startswith(("pad_", "bed_"))]
    d, pair = min_dist(held, sta, margin=300)
    record("station read: held slab clearance to everything static", d, 1.0, pair)
    dist = (c - SLAB_T) - L.STATION_LENS_Z
    record("station read: lens-to-slab-front distance error (mm)", abs(dist - L.CAM_TO_SLAB), 3.0, f"{dist:.1f} vs {L.CAM_TO_SLAB}", larger_is_better=False)
    label_y = sy - SLAB_H / 2 + 5 + 10
    fr = frustum((sx, sy, L.STATION_LENS_Z), (sx - 37, label_y - 12, c - SLAB_T - 0.5), (sx + 37, label_y + 12, c - SLAB_T - 0.5))
    blockers = [p for p in parts if p.name.startswith(("station", "rod_"))]
    vol = sum(fr.intersect(b.shape.val()).Volume() for b in blockers if _near(fr, b.shape.val(), 1))
    record("station camera line-of-sight to front label: blocked volume (mm3)", vol, 1.0, "", larger_is_better=False)


def check_head_camera() -> None:
    p = P[4]
    c = L.C_SAFE_LOADED
    parts = M.machine(p.x, c, held_slab=True, fill=FULL)
    lens_z = c + M.CAM_Z
    label_y = p.y - SLAB_H / 2 + 5 + 10
    fr = frustum((p.x, p.y, lens_z - 0.5), (p.x - 37, label_y - 12, c + 0.5), (p.x + 37, label_y + 12, c + 0.5))
    blockers = [q for q in parts if q.group == "head" and q.name not in ("head_camera", "held_slab", "held_label")]
    vol, who = 0.0, []
    for b in blockers:
        v = fr.intersect(b.shape.val()).Volume()
        if v > 0.5:
            vol += v
            who.append(b.name)
    record("head camera line-of-sight to back label: blocked volume (mm3)", vol, 1.0, ",".join(who), larger_is_better=False)
    need = math.degrees(math.atan2(abs(label_y - 12 - p.y), lens_z - c))
    record("head camera half-angle needed to see label edge (deg, <= 30)", need, 30.0, "", larger_is_better=False)


def check_rail_slots() -> None:
    """Rails must sit on an extrusion slot (20-series slots are every 20 mm, 10 mm from each edge)."""
    beam_slots = [L.X_BEAM_Z - 10, L.X_BEAM_Z + 10]
    record("X rail centre on a 4040 front-face slot (mm off)", min(abs(L.X_RAIL_Z - z) for z in beam_slots), 0.01, "", larger_is_better=False)
    spine_slots = [L.Z_SPINE_OFFSET_X - 10, L.Z_SPINE_OFFSET_X + 10]  # relative to the cup axis
    record("Z rail centre on a 2040 spine slot (mm off)", min(abs(0 - x) for x in spine_slots), 0.01, "", larger_is_better=False)
    parts = M.machine(P[3].x, L.C_SAFE_EMPTY, with_slabs=False)
    bed = next(p for p in parts if p.name == "bed_plywood").shape.val()
    ups = [p.shape.val() for p in parts if p.name.startswith("upright")]
    vol = sum(bed.intersect(u).Volume() for u in ups)
    record("bed plywood vs uprights overlap (mm3)", vol, 1.0, "", larger_is_better=False)


def check_extremes() -> None:
    t = L.travel_needed()
    for x in t["x"]:
        for c in (SLAB_T, L.C_MAX):
            parts = M.machine(x, c, with_slabs=False)
            mov = [p for p in parts if p.group in ("carriage", "head")]
            frame = [p for p in parts if p.name.startswith(("upright", "x_motor", "x_idler", "x_beam", "base_", "rod_", "station"))]
            d, pair = min_dist(mov, frame, margin=40)
            record(f"travel extreme x={x:.0f} c={c:.0f}: moving parts vs frame", d, 2.0, pair)
    record("X carriage on rail at left limit (mm margin)", (t["x"][0] - L.MGN12H_L / 2) - M.X_RAIL_X0, 3.0)
    record("X carriage on rail at right limit (mm margin)", (M.X_RAIL_X0 + M.X_RAIL_LEN) - (t["x"][1] + L.MGN12H_L / 2), 3.0)
    z_lo = L.Z_CARRIAGE_ABOVE_CUP + L.C_MIN
    z_hi = L.Z_CARRIAGE_ABOVE_CUP + L.C_MAX + L.MGN12H_L
    record(f"Z carriage on rail at c={L.C_MIN:.0f} (mm margin)", z_lo - (L.Z_SPINE_BOTTOM + 1), 2.0)
    record("Z carriage on rail at c=max (mm margin)", (L.Z_SPINE_BOTTOM + L.Z_SPINE_LEN - 9) - z_hi, 2.0)
    record("X bracket clears X motor / idler mounts at the ends (mm)", min(M.X_MOTOR_X - 26 - (t["x"][1] + 30), (t["x"][0] - 30) - (M.X_IDLER_X + 18)), 2.0)


def main() -> int:
    print("layout checks:", L.check() or "OK")
    check_pockets()
    check_travel()
    check_station()
    check_head_camera()
    check_extremes()
    check_rail_slots()
    w = max(len(r.name) for r in results)
    bad = 0
    for r in results:
        bad += not r.ok
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name:<{w}}  {r.value:>9}  (limit {r.limit})  {r.detail}")
    print(f"\n{len(results) - bad}/{len(results)} checks passed")
    return 1 if bad or L.check() else 0


if __name__ == "__main__":
    sys.exit(main())
