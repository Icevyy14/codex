"""Geometric verification of the SlabRail model.

Builds the machine at every critical pose and measures exact minimum distances
(OpenCascade BRepExtrema) and overlap volumes:
  * picking the bottom slab of every pocket while both neighbours are full,
  * placing the first slab into an empty pocket (slab-to-rod play),
  * empty and loaded travel over full stacks (head AND carriage), incl. a double pick of thick holders,
  * ALL-PAIRS interference at every pose: head vs head, head vs carriage, carriage vs carriage,
    movers vs static, and static vs static once (X drive, frame), with an explicit allow-list of
    intended overlaps; fastener heads that could foul something are modelled as parts,
  * the held slab against every part above it at every lift height up to the Z hard top stop,
  * reading at the upward-camera station, camera line-of-sight to the label (head and station),
  * X / Z hard stops (bumpers, Z end cap, top stop) and carriage-on-rail margins,
  * the contact probe over the whole 25 mm buffer stroke: trip travel, beam fully blocked after the trip, flag
    clear of the sensor and of its anti-rotation guide (also turned against the guide, for a rotating buffer),
    trip adjustment, and the flag out of the head camera's label view,
  * every printed part is ONE solid, and the Phase 0 jig (ledge overlap, line of sight, fit, and its occluder
    against the machine's: same parts at the same place under the lens, same blocked view).
What is NOT checked: flexible parts (belt slack, cables, vacuum tube), real purchased-part shapes beyond the
envelopes in model.py (the buffer above the foot and the sensor package are partly guessed), print tolerances,
the flag's bend accuracy, and anything under load.
Exit code 1 if any check fails. Run:  python checks.py
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass

import cadquery as cq

import layout as L
import model as M
from dims import SLAB_H, SLAB_T, SLAB_W

P = L.pockets()
FULL = {p.index: L.STACK_MAX for p in P if p.role == "source"}
OVERLAP_TOL = 0.5  # mm3


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


def _bb(s: cq.Shape):
    b = s.BoundingBox()
    return b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax


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


X_DRIVE = ("x_rail", "x_belt", "x_beam", "x_pulley", "x_idler", "x_motor", "x_bumper", "fx_")


def split(parts, include_carriage=False):
    groups = ("head", "carriage") if include_carriage else ("head",)
    moving = [p for p in parts if p.group in groups]
    static = [p for p in parts if p.group == "static" and not p.name.startswith("pad_") and p.name != "bed_plywood"]
    if include_carriage:  # the carriage rides on the rail and clamps the belt by design: covered by check_interference
        static = [s for s in static if not s.name.startswith(X_DRIVE)]
    return moving, static


# ------------------------------------------------------------------ all-pairs interference


def allowed(a: str, b: str) -> bool:
    """Intended overlaps / contacts (everything else must not overlap)."""
    a, b = sorted((a, b))
    rules = [
        lambda: (a, b) == ("held_label", "held_slab") or (a, b) == ("p0_label", "p0_slab"),
        lambda: a.startswith("labels_") and b.startswith("stack_") and a[7:] == b[6:],
        lambda: a == "bed_plywood" and b.startswith("rod_"),  # rods glued into the bed
        lambda: (a, b) == ("gate_beam", "gate_post_L") or (a, b) == ("gate_beam", "gate_post_R"),  # beam starts in the barrel
        lambda: "gate_beam" in (a, b) and not (MOVING_NAMES.isdisjoint((a, b))),  # light, not a part: the head crosses it on every
        # descent; the software reads it only with the head homed at the top (check_gate_beam)
        lambda: a in ("x_belt_hi", "x_belt_lo") and b in ("x_idler", "x_pulley"),  # strands drawn axis to axis
        lambda: (a, b) in (("x_belt_hi", "x_bracket"), ("belt_clamp_L", "x_belt_hi"), ("belt_clamp_R", "x_belt_hi")),  # belt teeth in the clamp rack
        lambda: (a, b) in (("x_carriage", "x_rail"), ("z_carriage", "z_rail")),  # block wraps its rail
        lambda: (a, b) in (("buffer", "buffer_rod"), ("p0_buffer", "p0_buffer_rod")),  # the rod slides inside the buffer body
    ]
    return any(r() for r in rules)


MOVING_NAMES: set[str] = set()


def interferences(parts, movers_only=True) -> list[tuple[float, str, str]]:
    MOVING_NAMES.clear()
    MOVING_NAMES.update(p.name for p in parts if p.group != "static")
    sh = [(p, p.shape.val()) for p in parts]
    boxes = [_bb(s) for _, s in sh]
    out = []
    for i in range(len(sh)):
        pa, sa = sh[i]
        ba = boxes[i]
        for j in range(i + 1, len(sh)):
            pb, sb = sh[j]
            if movers_only and pa.group == "static" and pb.group == "static":
                continue
            bb = boxes[j]
            if ba[1] <= bb[0] + 0.01 or bb[1] <= ba[0] + 0.01 or ba[3] <= bb[2] + 0.01 or bb[3] <= ba[2] + 0.01 or ba[5] <= bb[4] + 0.01 or bb[5] <= ba[4] + 0.01:
                continue
            if allowed(pa.name, pb.name):
                continue
            v = sa.intersect(sb).Volume()
            if v > OVERLAP_TOL:
                out.append((v, pa.name, pb.name))
    return sorted(out, reverse=True)


def record_interference(label: str, parts, movers_only=True) -> None:
    hits = interferences(parts, movers_only)
    worst = hits[0][0] if hits else 0.0
    record(f"interference, {label}: worst overlap (mm3)", worst, OVERLAP_TOL, "; ".join(f"{a}/{b} {v:.0f}" for v, a, b in hits[:4]), larger_is_better=False)


def moving_only(cup_x, c, held_slab=False):
    parts = M.carriage_parts(cup_x) + M.head_parts(cup_x, c)
    if held_slab:
        parts.append(M.Part("held_slab", M.slab(cup_x, L.Y_ROW, c - SLAB_T), M.SLAB, "slab", "head"))
        parts.append(M.Part("held_label", M.slab_label(cup_x, L.Y_ROW, c - SLAB_T), M.LABEL, "slab", "head"))
    return parts


def check_interference() -> None:
    poses = [
        ("pick last slab, pocket 0", P[0].x, SLAB_T, False, {**FULL, 0: 1}),
        ("pick last slab, pocket 6", P[6].x, SLAB_T, False, {**FULL, 6: 1}),
        ("pick last slab, pocket 12", P[12].x, SLAB_T, False, {**FULL, 12: 1}),
        ("empty travel 6->7", (P[6].x + P[7].x) / 2, L.C_SAFE_EMPTY, False, FULL),
        ("loaded travel 6->7", (P[6].x + P[7].x) / 2, L.C_SAFE_LOADED, True, FULL),
        ("held slab at C_MAX", P[3].x, L.C_MAX, True, FULL),
        ("station read", L.station_xy()[0], L.STATION_READ_C, True, FULL),
        ("X left hard stop", L.X_HARD_STOP[0], L.C_SAFE_EMPTY, False, FULL),
        ("X right hard stop", L.X_HARD_STOP[1], L.C_SAFE_EMPTY, False, FULL),
    ]
    for label, x, c, held, fill in poses:
        record_interference(label, M.machine(x, c, held_slab=held, fill=fill))
    # Z hard stops: moving groups only (at c = -14 the cup is pushed into the pad by design)
    record_interference(f"Z bottom hard stop c={L.C_HARD_BOTTOM:.0f} (carriage + head)", moving_only(P[3].x, L.C_HARD_BOTTOM))
    record_interference(f"Z top hard stop c={L.C_HARD_TOP:.0f} with a held slab (carriage + head)", moving_only(P[3].x, L.C_HARD_TOP, held_slab=True))
    # static vs static once (frame, X drive, bed, station, gate posts)
    record_interference("static parts vs each other", M.machine(P[1].x, L.C_SAFE_EMPTY, fill=FULL), movers_only=False)


# ------------------------------------------------------------------ poses


def check_pockets() -> None:
    for p in P:
        fill = dict(FULL)
        fill[p.index] = 1  # cup resting on the last slab of this pocket; neighbours full
        parts = M.machine(p.x, SLAB_T, fill=fill)
        mov, sta = split(parts, include_carriage=True)
        sta = [s for s in sta if s.name not in (f"stack_{p.index}", f"labels_{p.index}")]
        d, pair = min_dist(mov, sta)
        record(f"pick last slab, pocket {p.index:2d}: head/carriage clearance", d, 3.0, pair)
    p0 = P[0]
    parts = M.machine(p0.x, SLAB_T, held_slab=True, fill=FULL, seated=True)
    held = [p for p in parts if p.name == "held_slab"]
    rods = [p for p in parts if p.name.startswith("rod_")]
    d, pair = min_dist(held, rods)
    record("place first slab in pocket 0: slab-to-rod play (centred)", d, 1.0, pair)


def check_travel() -> None:
    for a, b in [(P[1], P[2]), (P[6], P[7]), (P[10], P[11])]:
        mx = (a.x + b.x) / 2
        parts = M.machine(mx, L.C_SAFE_EMPTY, fill=FULL)
        mov, sta = split(parts, include_carriage=True)
        d, pair = min_dist(mov, sta)
        record(f"empty travel {a.index}->{b.index}: head/carriage clearance over rods/stacks", d, 9.0, pair)
        parts = M.machine(mx, L.C_SAFE_LOADED, held_slab=True, fill=FULL)
        mov, sta = split(parts, include_carriage=True)
        d, pair = min_dist(mov, sta)
        record(f"loaded travel {a.index}->{b.index}: head/carriage/slab clearance", d, 9.0, pair)
    # double pick of two thick holders hanging under the cup at the loaded travel height
    mx = (P[6].x + P[7].x) / 2
    parts = M.machine(mx, L.C_SAFE_LOADED, fill=FULL)
    dbl = M.Part("double_pick", M.cbox(mx, L.Y_ROW, L.C_SAFE_LOADED - L.CUP_HANG - L.SLAB_T_THICK_MAX, SLAB_W, SLAB_H, 2 * L.SLAB_T_THICK_MAX), M.SLAB, "slab", "head")
    sta = [q for q in parts if q.group == "static" and q.name.startswith(("rod_", "stack_", "gate_"))]
    d, pair = min_dist([dbl], sta)
    record(f"loaded travel: double pick of 2 x {L.SLAB_T_THICK_MAX} mm holders over the rods", d, L.CARRY_CLEAR - 0.01, pair)
    for c in (L.C_HARD_BOTTOM, 0.0, SLAB_T):
        p = P[5]
        parts = M.machine(p.x, c, fill={**FULL, 5: 1})
        hi = [q for q in parts if q.name in ("z_spine", "z_rail", "z_plate", "z_carriage", "x_bracket", "z_end_cap", "z_leadscrew") or q.name.startswith(("fc_", "fh_"))]
        sta = [q for q in parts if q.group == "static" and (q.name.startswith("rod_") or q.name.startswith("stack_"))]
        d, pair = min_dist(hi, sta)
        record(f"Z machinery over rods with cup at c={c:.1f}", d, 5.0, pair)


def check_held_slab() -> None:
    """The held slab against every carriage/head part (except the cup it hangs on) at every lift height."""
    x = P[3].x
    worst, wpair, wc = 1e9, "", 0.0
    heights = sorted({SLAB_T, 50.0, 100.0, 150.0, 200.0, L.C_SAFE_EMPTY, L.C_SAFE_LOADED, L.C_MAX, L.Z_SWITCH_C, L.C_HARD_TOP})
    for c in heights:
        parts = moving_only(x, c, held_slab=True)
        held = [p for p in parts if p.name == "held_slab"]
        others = [p for p in parts if p.name not in ("held_slab", "held_label", "cup")]
        d, pair = min_dist(held, others, margin=400)
        if c in (L.C_MAX, L.C_HARD_TOP):  # the spine, rail, end cap and lead screw do NOT rise with Z
            dc, pc = min_dist(held, [p for p in others if p.group == "carriage"], margin=400)
            lim = 10.0 if c == L.C_MAX else L.HELD_SLAB_CLEAR - 0.01
            record(f"held slab at c={c:.0f}{' (Z hard top stop)' if c == L.C_HARD_TOP else ' (C_MAX)'}: clearance to the parts fixed to the X carriage", dc, lim, pc)
        if d < worst:
            worst, wpair, wc = d, pair, c
    record(f"held slab vs every non-cup part, c = {SLAB_T}..{L.C_HARD_TOP:.0f} (worst at c={wc:.0f})", worst, 2.0, wpair)


def check_gate_beam() -> None:
    """runner._check_gate reads the overfill beam right after homing: the head must be clear of it there."""
    c_home = L.Z_SWITCH_C - 3.0  # firmware mpos after the 3 mm pull-off
    for p in (P[0], P[6], P[12]):
        parts = M.machine(p.x, c_home, fill=FULL)
        beam = [q for q in parts if q.name == "gate_beam"]
        d, pair = min_dist([q for q in parts if q.group != "static"], beam, margin=300)
        record(f"overfill beam clear of the head homed at c={c_home:.0f}, over pocket {p.index}", d, 5.0, pair)


def frustum(apex, c0, c1) -> cq.Shape:
    """Pyramid from a point (camera) to an axis-aligned rectangle at height c0[2] (label)."""
    (x0, y0, z), (x1, y1, _) = c0, c1
    pts = [cq.Vector(x0, y0, z), cq.Vector(x1, y0, z), cq.Vector(x1, y1, z), cq.Vector(x0, y1, z)]
    a = cq.Vector(*apex)
    faces = [cq.Face.makeFromWires(cq.Wire.makePolygon([pts[i], pts[(i + 1) % 4], a], close=True)) for i in range(4)]
    faces.append(cq.Face.makeFromWires(cq.Wire.makePolygon(pts, close=True)))
    return cq.Solid.makeSolid(cq.Shell.makeShell(faces))


def blocked(fr, parts) -> tuple[float, str]:
    vol, who = 0.0, []
    for b in parts:
        s = b.shape.val()
        if not _near(fr, s, 1):
            continue
        v = fr.intersect(s).Volume()
        if v > 0.5:
            vol += v
            who.append(b.name)
    return vol, ",".join(who)


def check_station() -> None:
    sx, sy = L.station_xy()
    c = L.STATION_READ_C
    parts = M.machine(sx, c, held_slab=True, fill=FULL)
    held = [p for p in parts if p.name in ("held_slab", "held_label")]
    sta = [p for p in parts if p.group == "static" and not p.name.startswith(("pad_", "bed_"))]
    d, pair = min_dist(held, sta, margin=300)
    record("station read: held slab clearance to everything static", d, 1.0, pair)
    dist = (c - L.CUP_HANG - SLAB_T) - L.STATION_LENS_Z  # the slab hangs free over the lens
    record("station read: lens-to-slab-front distance error (mm)", abs(dist - L.CAM_TO_SLAB), 3.0, f"{dist:.1f} vs {L.CAM_TO_SLAB}", larger_is_better=False)
    label_y = sy - SLAB_H / 2 + 5 + 10
    fr = frustum((sx, sy, L.STATION_LENS_Z), (sx - 37, label_y - 12, c - L.CUP_HANG - SLAB_T - 0.5), (sx + 37, label_y + 12, c - L.CUP_HANG - SLAB_T - 0.5))
    vol, who = blocked(fr, [p for p in parts if p.name.startswith(("station", "rod_"))])
    record("station camera line-of-sight to front label: blocked volume (mm3)", vol, 1.0, who, larger_is_better=False)


def check_head_camera() -> None:
    p = P[4]
    c = L.C_SAFE_LOADED
    parts = M.machine(p.x, c, held_slab=True, fill=FULL)
    lens_z = c + M.CAM_Z
    label_y = p.y - SLAB_H / 2 + 5 + 10
    fr = frustum((p.x, p.y, lens_z - 0.5), (p.x - 37, label_y - 12, c + 0.5), (p.x + 37, label_y + 12, c + 0.5))
    vol, who = blocked(fr, [q for q in parts if q.group in ("head", "carriage") and q.name not in ("head_camera", "held_slab", "held_label")])
    record("head camera line-of-sight to back label: blocked volume (mm3)", vol, 1.0, who, larger_is_better=False)
    need = math.degrees(math.atan2(abs(label_y - 12 - p.y), lens_z - c))
    record("head camera half-angle needed to see label edge (deg, <= 30)", need, 30.0, "", larger_is_better=False)


def _moved(shape: cq.Shape, dz: float = 0.0, deg: float = 0.0) -> cq.Shape:
    """Copy raised by dz and turned by deg about the cup axis (head-local coordinates: the axis is X = Y = 0)."""
    s = shape.translate(cq.Vector(0, 0, dz))
    return s.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), deg) if deg else s


def _bisect(f, lo: float, hi: float, n: int = 14) -> float:
    """Boundary in [lo, hi] where the predicate f changes from False (at lo) to True (at hi)."""
    for _ in range(n):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if f(mid) else (mid, hi)
    return (lo + hi) / 2


STROKE = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, L.BUFFER_STROKE]


def check_probe() -> None:
    """Probe flag vs the TCST2103's beam, the sensor, its guide in head_foot and the head camera's label view, swept over
    the whole buffer stroke (t = 0 free .. 25 mm), in head-local coordinates (cup axis X = Y = 0, c = 0)."""
    rest = {p.name: p.shape.val() for p in M.head_parts(0.0, 0.0, compression=0.0)}
    flag, sensor, foot = rest["probe_flag"], rest["contact_sensor"], rest["head_foot"]
    ap = M.probe_aperture().val()
    full = M.TCST_AP * M.TCST_AP_H * M.FLAG_T  # aperture area x plate thickness
    frac = lambda t: _moved(flag, t).intersect(ap).Volume() / full  # noqa: E731  share of the beam the flag blocks
    trip = _bisect(lambda t: frac(t) >= 0.5, 0.0, 6.0)
    record(f"probe: buffer travel at which the flag edge crosses the beam centre, error vs {L.CUP_HANG} mm (mm)", abs(trip - L.CUP_HANG), 0.05,
           f"trips at {trip:.2f} mm", larger_is_better=False)
    first = _bisect(lambda t: frac(t) > 1e-4, 0.0, 6.0)
    record("probe: flag clear of the beam at rest: buffer travel before it starts to cover the aperture (mm)", first, 1.0,
           f"blocked share at rest {frac(0.0):.3f}")
    after = [t for t in STROKE if t >= trip + M.TCST_AP / 2 + 0.05]
    worst_t = min(after, key=frac)
    record(f"probe: beam fully blocked from {after[0]:.1f} to {L.BUFFER_STROKE:.0f} mm of buffer travel (min blocked share)", frac(worst_t), 0.999,
           f"lowest at {worst_t:.0f} mm")
    # clearances over the whole stroke (the buffer stop rests ON the body top when free, so it is checked against the rest)
    guide_box = M.box(M.FLAG_X[0] + 0.5, M.PROBE_Y - M.GUIDE_GAP / 2, M.FOOT_Z[0], M.FLAG_X[1], M.PROBE_Y + M.GUIDE_GAP / 2, M.GUIDE_TOP).val()
    blade_w = M.FLAG_X[1] - M.FLAG_X[0] - 0.5
    fixed_other = [rest[n] for n in rest if n in ("buffer", "camera_bracket", "head_camera", "drop_arm") or n.startswith("probe_m3") or n.startswith("probe_nut")]
    above = [rest[n] for n in ("head_foot", "contact_sensor", "camera_bracket", "head_camera", "drop_arm")]
    ds, dg, do, dm, eng = (1e9, 0), (1e9, 0), (1e9, 0), (1e9, 0), (1e9, 0)
    for t in STROKE:
        ft = _moved(flag, t)
        ds = min(ds, (ft.distance(sensor), t))
        dg = min(dg, (ft.distance(foot), t))
        do = min(do, (min(ft.distance(o) for o in fixed_other), t))
        movers = [_moved(rest["buffer_stop"], t), _moved(rest["vac_fitting"], t)]
        dm = min(dm, (min(m.distance(o) for m in movers for o in above), t))
        eng = min(eng, (ft.intersect(guide_box).Volume() / (blade_w * M.FLAG_T), t))
    record("probe: flag vs the sensor over 0..25 mm of buffer travel (min clearance, mm)", ds[0], 0.5, f"at {ds[1]:.0f} mm")
    record("probe: flag vs its guide in head_foot over 0..25 mm (min clearance, mm)", dg[0], 0.3, f"at {dg[1]:.0f} mm; slot {M.GUIDE_GAP:.1f} for a {M.FLAG_T:.1f} flag")
    record("probe: flag vs buffer nut, board screws, arm and camera over 0..25 mm (min clearance, mm)", do[0], 1.0, f"at {do[1]:.0f} mm")
    record("probe: buffer stop + vacuum fitting vs foot, sensor, arm and camera over 0..25 mm (min clearance, mm)", dm[0], 1.0, f"at {dm[1]:.0f} mm")
    record("probe: blade depth in the guide, worst over 0..25 mm (mm)", eng[0], 3.0, f"at {eng[1]:.0f} mm")
    # rotating (J) buffer: turn the flag about the cup axis until it touches the guide; the sensor must still be clear
    worst = (1e9, 0.0, 0.0)
    for t in (L.CUP_HANG, L.BUFFER_STROKE):
        for sgn in (1, -1):
            th = _bisect(lambda a: _moved(flag, t, sgn * a).distance(foot) < 0.005, 0.0, 6.0)
            worst = min(worst, (_moved(flag, t, sgn * th).distance(sensor), sgn * th, t))
    record("probe: rotating buffer, flag turned until the guide stops it: clearance to the sensor (mm)", worst[0], 0.3,
           f"guide stops it at {worst[1]:+.2f} deg (travel {worst[2]:.0f} mm)")
    # trip adjustment: the board slides +/- PROBE_ADJ in its slots without touching the guide or the flag
    worst_o, worst_f = 0.0, (1e9, 0.0)
    for dz in (-M.PROBE_ADJ, M.PROBE_ADJ):
        sz = _moved(sensor, dz)
        worst_o = max(worst_o, sz.intersect(foot).Volume())
        worst_f = min(worst_f, (min(_moved(flag, t).distance(sz) for t in STROKE), dz))
    record(f"probe: trip adjustment, board slots +/-{M.PROBE_ADJ} mm (>= +/-{L.PROBE_TRIP_TOL}): board vs head_foot overlap at the slot ends (mm3)",
           worst_o, OVERLAP_TOL, "", larger_is_better=False)
    record("probe: trip adjustment: flag vs the sensor with the board at either slot end, over 0..25 mm (min clearance, mm)", worst_f[0], 0.5, f"board at {worst_f[1]:+.1f}")
    # the flag and the buffer stop stay out of the head camera's label view over the whole stroke; the fitting while reading
    label_y = -SLAB_H / 2 + 5 + 10
    fr = frustum((0, 0, M.CAM_Z - 0.5), (-37, label_y - 12, 0.5), (37, label_y + 12, 0.5))
    worst_v = (0.0, 0.0)
    for t in STROKE:
        for nm in ("probe_flag", "buffer_stop"):
            sh = _moved(rest[nm], t)
            if _near(fr, sh, 1):
                worst_v = max(worst_v, (fr.intersect(sh).Volume(), t))
    record("head camera label view: flag + buffer stop over the whole 25 mm stroke (max blocked mm3)", worst_v[0], 1.0, f"at {worst_v[1]:.0f} mm" if worst_v[0] else "",
           larger_is_better=False)
    vf = max(fr.intersect(_moved(rest["vac_fitting"], t)).Volume() for t in (0.0, L.CUP_HANG))
    record("head camera label view: vacuum fitting while reading (buffer travel 0..2 mm, blocked mm3)", vf, 1.0, "", larger_is_better=False)


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
    frame_names = ("upright", "x_motor", "x_idler", "x_beam", "x_bumper", "base_", "rod_", "station", "gate_post", "fx_")
    for x in t["x"]:
        for c in (SLAB_T, L.C_MAX):
            parts = M.machine(x, c, with_slabs=False)
            mov = [p for p in parts if p.group in ("carriage", "head")]
            frame = [p for p in parts if p.name.startswith(frame_names)]
            d, pair = min_dist(mov, frame, margin=40)
            record(f"travel extreme x={x:.0f} c={c:.0f}: moving parts vs frame", d, 2.0, pair)
    # X hard stops: the x_bracket edge lands on a bumper; nothing else comes within 2 mm
    for x, bumper in ((L.X_HARD_STOP[0], "x_bumper_L"), (L.X_HARD_STOP[1], "x_motor_mount")):
        parts = M.machine(x, L.C_SAFE_EMPTY, with_slabs=False)
        br = [p for p in parts if p.name == "x_bracket"]
        stop = [p for p in parts if p.name == bumper]
        d, _ = min_dist(br, stop)
        record(f"X hard stop x={x:.0f}: x_bracket lands on {bumper} (gap mm)", d, 0.01, "", larger_is_better=False)
        mov = [p for p in parts if p.group in ("carriage", "head") and p.name != "x_bracket"]
        frame = [p for p in parts if p.name.startswith(frame_names)]
        d1, pair1 = min_dist(mov, frame, margin=40)
        d2, pair2 = min_dist(br, [p for p in frame if p.name != bumper], margin=40)
        d, pair = (d1, pair1) if d1 < d2 else (d2, pair2)
        record(f"X hard stop x={x:.0f}: everything else vs frame", d, 2.0, pair)
    record("X carriage on rail at the left hard stop (mm margin)", (L.X_HARD_STOP[0] - L.MGN12H_L / 2) - M.X_RAIL_X0, 2.0)
    record("X carriage on rail at the right hard stop (mm margin)", (M.X_RAIL_X0 + M.X_RAIL_LEN) - (L.X_HARD_STOP[1] + L.MGN12H_L / 2), 2.0)
    record("X left hard stop below the home switch trip (mm)", L.X_HOME_SWITCH - L.X_HARD_STOP[0], 3.0)
    # Z hard stops
    rail_lo, rail_hi = L.Z_RAIL_BOTTOM, L.Z_RAIL_BOTTOM + L.Z_RAIL_LEN
    lo = moving_only(P[3].x, L.C_HARD_BOTTOM)
    d, _ = min_dist([p for p in lo if p.name == "z_carriage"], [p for p in lo if p.name == "z_end_cap"])
    record(f"Z bottom hard stop c={L.C_HARD_BOTTOM:.0f}: carriage lands on the z_end_cap lips (gap mm)", d, 0.01, "", larger_is_better=False)
    record(f"Z carriage on rail at the bottom hard stop c={L.C_HARD_BOTTOM:.0f} (mm margin)", L.Z_CARRIAGE_ABOVE_CUP + L.C_HARD_BOTTOM - rail_lo, 2.0)
    record(f"Z carriage on rail at c={L.C_MIN:.0f} (mm margin)", L.Z_CARRIAGE_ABOVE_CUP + L.C_MIN - rail_lo, 2.0)
    record("Z bottom hard stop before the buffer bottoms on the bare pad (mm)", L.C_HARD_BOTTOM + L.BUFFER_STROKE, 2.0)
    hi = moving_only(P[3].x, L.C_HARD_TOP)
    d, _ = min_dist([p for p in hi if p.name == "z_plate"], [p for p in hi if p.name == "z_motor_mount"])
    record(f"Z top hard stop c={L.C_HARD_TOP:.0f}: z_plate lands on the z_motor_mount (gap mm)", d, 0.01, "", larger_is_better=False)
    record(f"Z carriage on rail at the top hard stop c={L.C_HARD_TOP:.0f} (mm margin)", rail_hi - (L.Z_CARRIAGE_ABOVE_CUP + L.C_HARD_TOP + L.MGN12H_L), 2.0)
    record(f"Z switch c={L.Z_SWITCH_C:.0f}: overtravel to the top hard stop (mm)", L.C_HARD_TOP - L.Z_SWITCH_C, 2.0)
    nut_bottom = L.Z_CARRIAGE_ABOVE_CUP + L.C_HARD_BOTTOM + 36.0
    record(f"T8 nut stays on the {L.Z_SCREW_LEN:.0f} mm screw at the bottom hard stop (mm of screw below the nut)", nut_bottom - L.Z_SCREW_TIP, 5.0)


def check_printed() -> None:
    bad = []
    for name, shape, _, _ in M.printed_catalog():
        n = len(shape.solids().vals())
        if n != 1:
            bad.append(f"{name}:{n}")
    record("printed parts that are not ONE solid (count)", len(bad), 0, ",".join(bad), larger_is_better=False)


def check_phase0() -> None:
    aw, al = M.p0_tray_opening()
    shift = M.P0_TRAY_PLAY / 2
    record("Phase 0 tray: ledge under the slab edge, slab shifted by the full play (mm, X)", (SLAB_W - aw) / 2 - shift, 2.0)
    record("Phase 0 tray: ledge under the slab edge, slab shifted by the full play (mm, Y)", (SLAB_H - al) / 2 - shift, 2.0)
    record("Phase 0 tray: label clear of the opening edge (mm, X)", aw / 2 - 35.0, 1.0)
    parts = M.phase0_parts()
    record_interference("Phase 0 jig", parts, movers_only=False)
    label_y = -SLAB_H / 2 + 5 + 10
    fr = frustum((0, 0, L.STATION_LENS_Z), (-37, label_y - 12, M.P0_SLAB_Z - 0.5), (37, label_y + 12, M.P0_SLAB_Z - 0.5))
    vol, who = blocked(fr, [p for p in parts if p.name in ("p0_base", "p0_tray", "p0_post_-1", "p0_post_1")])
    record("Phase 0: station camera line-of-sight to the front label: blocked volume (mm3)", vol, 1.0, who, larger_is_better=False)
    zb = M.P0_SLAB_Z + SLAB_T
    viewers = [p for p in parts if p.name not in ("p0_head_camera", "p0_slab", "p0_label")]  # occluder included
    fr = frustum((0, 0, M.P0_TOP_Z - 0.5), (-37, label_y - 12, zb + 0.5), (37, label_y + 12, zb + 0.5))
    vol, who = blocked(fr, viewers)
    record("Phase 0: head camera line-of-sight to the back label, occluder fitted: blocked volume (mm3)", vol, 1.0, who, larger_is_better=False)
    # occluder: the jig must show the head camera what the machine shows it
    jp = {p.name: p for p in parts}
    cup = jp["p0_cup"].shape.val().BoundingBox()
    record("Phase 0: cup face above the slab back (mm)", cup.zmin - zb, 0.2, f"cup centre {math.hypot(cup.center.x, cup.center.y):.2f} mm off the lens axis")
    mx, mc = P[4].x, L.C_SAFE_LOADED
    mp = {p.name: p for p in M.machine(mx, mc, held_slab=True, fill=FULL)}
    lens_m, lens_j = (mx, 0.0, mc + M.CAM_Z), (0.0, 0.0, M.P0_TOP_Z)
    def rel(part, lens, keep=6):
        b = part.shape.val().BoundingBox()
        return [v - lens[i // 2] for i, v in enumerate((b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax))][:keep]
    pairs = [(n, "p0_" + n, 6) for n in mp if mp[n].group == "head" and "p0_" + n in jp] + [("drop_arm", "p0_arm_stub", 5)]  # stub = the arm's lower end
    worst = max((max(abs(a - b) for a, b in zip(rel(mp[m], lens_m, k), rel(jp[j], lens_j, k))), m) for m, j, k in pairs)
    record("Phase 0 occluder vs machine, relative to the head lens: worst bounding-box offset (mm)", worst[0], 1.0, f"{worst[1]}; {len(pairs)} parts compared",
           larger_is_better=False)
    def whole(lens):  # the head camera's view of the WHOLE slab back, down to 1 mm above the cup face
        z = lens[2] - M.CAM_Z + 1.0
        return frustum((lens[0], lens[1], lens[2] - 0.5), (lens[0] - SLAB_W / 2, lens[1] - SLAB_H / 2, z), (lens[0] + SLAB_W / 2, lens[1] + SLAB_H / 2, z))
    # head parts only: the parts fixed to the X carriage (lead screw tip, z_end_cap) also reach into this view over the
    # slab's back half, by an amount that depends on the Z height, so the jig does not copy them
    vm, whom = blocked(whole(lens_m), [q for q in mp.values() if q.group == "head" and q.name not in ("head_camera", "held_slab", "held_label")])
    vc, whoc = blocked(whole(lens_m), [q for q in mp.values() if q.group == "carriage"])
    vj, whoj = blocked(whole(lens_j), viewers)
    names_m = set(whom.split(",")) - {""}
    names_j = {("drop_arm" if n == "p0_arm_stub" else n[3:]) for n in whoj.split(",") if n}
    record("Phase 0 vs machine: head camera's whole-slab-back view blocked by the occluder, |jig - machine| (% of machine)", abs(vj - vm) / vm * 100, 1.0,
           f"jig {vj:.0f} vs machine {vm:.0f} mm3 (carriage parts add {vc:.0f} at c={mc:.0f}: {whoc or 'none'})", larger_is_better=False)
    record("Phase 0 vs machine: parts in the whole-slab-back view that are not in both (count)", len(names_m ^ names_j), 0,
           ",".join(sorted(names_m ^ names_j)) or ",".join(sorted(names_m)), larger_is_better=False)
    # the occluder buffer pushed through its stroke (changing slabs) stays clear of the mount, bridge and camera
    jrest = {p.name: p.shape.val() for p in M.phase0_parts(compression=0.0)}
    obst = [jrest[n] for n in ("p0_occluder_mount", "p0_top", "p0_head_camera", "p0_arm_stub", "p0_post_1")]
    dj = min((min(_moved(jrest[n], t).distance(o) for n in ("p0_probe_flag", "p0_buffer_stop", "p0_vac_fitting") for o in obst), t) for t in STROKE)
    record("Phase 0: occluder flag, buffer stop and fitting over 0..25 mm vs mount, bridge, camera, stub, post (min clearance, mm)", dj[0], 1.0, f"at {dj[1]:.0f} mm")
    record("Phase 0: head board standoff for an 8 mm board-to-lens-front camera (mm, >= 0 = the posts work)", M.p0_board_spacer(8.0), 0.0)


def main() -> int:
    print("layout checks:", L.check() or "OK")
    check_pockets()
    check_travel()
    check_held_slab()
    check_interference()
    check_gate_beam()
    check_station()
    check_head_camera()
    check_probe()
    check_extremes()
    check_rail_slots()
    check_printed()
    check_phase0()
    w = max(len(r.name) for r in results)
    bad = 0
    for r in results:
        bad += not r.ok
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name:<{w}}  {r.value:>9}  (limit {r.limit})  {r.detail}")
    print(f"\n{len(results) - bad}/{len(results)} checks passed")
    return 1 if bad or L.check() else 0


if __name__ == "__main__":
    sys.exit(main())
