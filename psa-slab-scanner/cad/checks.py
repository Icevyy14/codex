"""Geometric verification of the SlabStack model.

Builds the machine at every critical pose and measures exact minimum distances
(OpenCascade BRepExtrema) between moving and static parts:
  * picking the bottom slab of a pocket while all neighbours are full,
  * placing the first slab into an empty pocket,
  * empty and loaded travel over full stacks,
  * reading at the upward-camera station,
  * gantry/carriage/Z travel extremes against the frame,
  * camera line-of-sight to the label (head camera and station camera).
Exit code 1 if any check fails. Run:  python checks.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import cadquery as cq

import layout as L
import model as M
from dims import SLAB_H, SLAB_T, SLAB_W

FULL = {p.index: L.STACK_MAX for p in L.pockets() if p.role == "source"}


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


def min_dist(movers: list[M.Part], obstacles: list[M.Part], margin: float = 60.0) -> tuple[float, str]:
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


def split(parts: list[M.Part]):
    moving = [p for p in parts if p.group == "head"]
    static = [p for p in parts if p.group == "static" and not p.name.startswith("pad_") and p.name != "bed_plywood"]
    return moving, static


def check_pockets() -> None:
    for p in L.pockets():
        # cup resting on the last (bottom) slab of this pocket; every other source pocket full
        fill = dict(FULL)
        fill[p.index] = 1
        parts = M.machine(p.x, p.y, SLAB_T, fill=fill)
        mov, sta = split(parts)
        sta = [s for s in sta if s.name not in (f"stack_{p.index}", f"labels_{p.index}")]
        d, pair = min_dist(mov, sta)
        record(f"pick bottom slab, pocket {p.index:2d}: head clearance", d, 3.0, pair)
    # first slab placed into empty start pocket: held slab vs guide rods (pocket play)
    p0 = L.pockets()[0]
    parts = M.machine(p0.x, p0.y, SLAB_T, held_slab=True, fill={k: v for k, v in FULL.items()})
    held = [p for p in parts if p.name == "held_slab"]
    rods = [p for p in parts if p.name.startswith("rod_")]
    d, pair = min_dist(held, rods)
    record("place first slab in pocket 0: slab-to-rod play (centred)", d, 1.0, pair)


def check_travel() -> None:
    ps = L.pockets()
    # empty travel over full stacks, above a rod line and above pocket centres
    for a, b in [(ps[1], ps[2]), (ps[4], ps[5]), (ps[9], ps[10])]:
        mx, my = (a.x + b.x) / 2, (a.y + b.y) / 2
        parts = M.machine(mx, my, L.C_SAFE_EMPTY, fill=FULL)
        mov, sta = split(parts)
        d, pair = min_dist(mov, sta)
        record(f"empty travel between {a.index}->{b.index}: clearance over rods/stacks", d, 9.0, pair)
        parts = M.machine(mx, my, L.C_SAFE_LOADED, held_slab=True, fill=FULL)
        mov, sta = split(parts)
        d, pair = min_dist(mov, sta)
        record(f"loaded travel between {a.index}->{b.index}: clearance", d, 9.0, pair)
    # Rigid gantry parts (Z spine/rail bottom, Z plate) sweep over everything at every Z
    for c in (0.0, SLAB_T):
        p = ps[7]
        parts = M.machine(p.x, p.y, c, fill={**FULL, 7: 1})
        hi = [q for q in parts if q.name in ("z_spine", "z_rail", "z_plate", "z_carriage", "x_bracket")]
        sta = [q for q in parts if q.group == "static" and (q.name.startswith("rod_") or q.name.startswith("stack_"))]
        d, pair = min_dist(hi, sta)
        record(f"Z machinery over rods with cup at c={c:.1f}", d, 5.0, pair)


def check_station() -> None:
    sx, sy = L.station_xy()
    c = L.STATION_READ_C
    parts = M.machine(sx, sy, c, held_slab=True, fill=FULL)
    held = [p for p in parts if p.name in ("held_slab", "held_label")]
    sta = [p for p in parts if p.name in ("station", "station_camera")]
    d, pair = min_dist(held, sta, margin=500)
    record("station read: held slab clearance to station", d, 5.0, pair)
    lens_top = L.STATION_LENS_Z
    dist = (c - SLAB_T) - lens_top
    record("station read: lens-to-slab-front distance (mm)", dist, abs(dist - L.CAM_TO_SLAB) if abs(dist - L.CAM_TO_SLAB) > 10 else dist, "target %.0f" % L.CAM_TO_SLAB)
    results[-1].ok = abs(dist - L.CAM_TO_SLAB) <= 12
    # station line of sight: frustum from lens to the label on the slab front (label toward -Y)
    label_y = sy - SLAB_H / 2 + 5 + 10
    fr = frustum((sx, sy, lens_top), (sx - 37, label_y - 12, c - SLAB_T - 0.5), (sx + 37, label_y + 12, c - SLAB_T - 0.5))
    blockers = [p for p in parts if p.name in ("station",)]
    vol = sum(fr.intersect(b.shape.val()).Volume() for b in blockers)
    record("station camera line-of-sight to front label: blocked volume (mm3)", vol, 1.0, "", larger_is_better=False)


def frustum(apex, c0, c1) -> cq.Shape:
    """Pyramid from a point (camera) to an axis-aligned rectangle at height c0[2] (label)."""
    (x0, y0, z), (x1, y1, _) = c0, c1
    pts = [cq.Vector(x0, y0, z), cq.Vector(x1, y0, z), cq.Vector(x1, y1, z), cq.Vector(x0, y1, z)]
    a = cq.Vector(*apex)
    faces = [cq.Face.makeFromWires(cq.Wire.makePolygon([pts[i], pts[(i + 1) % 4], a], close=True)) for i in range(4)]
    faces.append(cq.Face.makeFromWires(cq.Wire.makePolygon(pts, close=True)))
    return cq.Solid.makeSolid(cq.Shell.makeShell(faces))


def check_head_camera() -> None:
    p = L.pockets()[6]
    c = L.C_SAFE_LOADED
    parts = M.machine(p.x, p.y, c, held_slab=True, fill=FULL)
    lens_z = c + M.CAM_Z
    slab_top = c  # back face of the held slab = cup face
    label_y = p.y - SLAB_H / 2 + 5 + 10
    fr = frustum((p.x, p.y, lens_z - 0.5), (p.x - 37, label_y - 12, slab_top + 0.5), (p.x + 37, label_y + 12, slab_top + 0.5))
    blockers = [q for q in parts if q.group == "head" and q.name not in ("head_camera", "held_slab", "held_label")]
    vol, who = 0.0, []
    for b in blockers:
        v = fr.intersect(b.shape.val()).Volume()
        if v > 0.5:
            vol += v
            who.append(b.name)
    record("head camera line-of-sight to back label: blocked volume (mm3)", vol, 1.0, ",".join(who), larger_is_better=False)
    # field of view: Camera Module 3-class / IMX179 3.6 mm lens horizontal FOV ~65 deg along Y must cover label far edge
    import math

    need = math.degrees(math.atan2(abs(label_y - 12 - p.y), lens_z - slab_top))
    record("head camera half-angle needed to see label edge (deg, <= 30)", need, 30.0, "", larger_is_better=False)


def check_extremes() -> None:
    t = L.travel_needed()
    for name, (x, y) in {"x_min,y_min": (t["x"][0], t["y"][0]), "x_max,y_max": (t["x"][1], t["y"][1]), "x_min,y_max": (t["x"][0], t["y"][1]), "x_max,y_min": (t["x"][1], t["y"][0])}.items():
        for c in (0.0 + SLAB_T, L.C_MAX):
            parts = M.machine(x, y, c, with_slabs=False)
            mov = [p for p in parts if p.group in ("gantry", "carriage", "head")]
            frame = [p for p in parts if p.name.startswith(("upright", "y_beam", "base_"))]
            d, pair = min_dist(mov, frame, margin=40)
            record(f"travel extreme {name} c={c:.0f}: moving parts vs frame", d, 2.0, pair)
    # rails: carriages must stay on their rails
    yb_lo, yb_hi = t["y"][0] + L.Y_CUP_TO_BEAM + 10, t["y"][1] + L.Y_CUP_TO_BEAM + 10
    record("Y carriage on rail at front limit (mm margin)", (yb_lo - L.MGN12H_L / 2) - M.Y_RAIL_Y0, 3.0)
    record("Y carriage on rail at back limit (mm margin)", (M.Y_RAIL_Y0 + M.Y_RAIL_LEN) - (yb_hi + L.MGN12H_L / 2), 3.0)
    record("X carriage on rail at left limit (mm margin)", (t["x"][0] - L.MGN12H_L / 2) - M.X_RAIL_X0, 3.0)
    record("X carriage on rail at right limit (mm margin)", (M.X_RAIL_X0 + M.X_RAIL_LEN) - (t["x"][1] + L.MGN12H_L / 2), 3.0)
    z_lo = L.Z_CARRIAGE_ABOVE_CUP + 0.0
    z_hi = L.Z_CARRIAGE_ABOVE_CUP + L.C_MAX + L.MGN12H_L
    record("Z carriage on rail at c=0 (mm margin)", z_lo - (L.Z_SPINE_BOTTOM + 1), 2.0)
    record("Z carriage on rail at c=max (mm margin)", (L.Z_SPINE_BOTTOM + L.Z_SPINE_LEN - 9) - z_hi, 2.0)
    record("X carriage clears X motor/idler mounts (mm)", min(M.X_MOTOR_X - 26 - (t["x"][1] + 30), (t["x"][0] - 30) - (M.X_IDLER_X + 18)), 2.0)


def main() -> int:
    print("layout checks:", L.check() or "OK")
    check_pockets()
    check_travel()
    check_station()
    check_head_camera()
    check_extremes()
    w = max(len(r.name) for r in results)
    bad = 0
    for r in results:
        bad += not r.ok
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name:<{w}}  {r.value:>9}  (limit {r.limit})  {r.detail}")
    print(f"\n{len(results) - bad}/{len(results)} checks passed")
    return 1 if bad or L.check() else 0


if __name__ == "__main__":
    sys.exit(main())
