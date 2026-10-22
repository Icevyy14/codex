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
  * the head camera's view of the face-down card window (layout.FACE_DOWN_WINDOW_MM): nothing in it at hover over a low,
    half and full stack or with the slab held at travel height, the window on the card, clear of the label, and how far
    the head camera may be off its nominal aim before that stops being true,
  * the carry-height sensor (Z stall guard): trip height, beam clear below / blocked up to the hard top stop, the highest
    Z stall it cannot see (a double pick there still over the rods), flag and arm clear of the carriage over the whole Z
    travel, and a path for its lead,
  * X / Z hard stops (bumpers, Z end cap, top stop) and carriage-on-rail margins,
  * the contact probe over the whole 20 mm buffer stroke: trip travel, beam fully blocked after the trip, flag
    clear of the sensor and of its anti-rotation guide (also turned against the guide, for a rotating buffer),
    the pad clear of the buffer body, trip adjustment, the buffer moved +/-3 mm on its thread (lens setting),
    hex-key access to the board screws, and the moving parts out of the head camera's label view,
  * every printed part is ONE solid, and the Phase 0 jig (ledge overlap, line of sight, fit, its occluder against
    the machine's: same parts at the same place under the lens, same blocked view, and the face-up lift).
What is NOT checked: flexible parts (belt slack, cables, vacuum tube), real purchased-part shapes beyond the
envelopes in model.py (the buffer's neck and rod, the barb elbow's arm and the endstop board are read off drawings or
guessed), print tolerances, the flag's bend accuracy, and anything under load.
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
    lens_z, lens_y = c + M.CAM_Z, p.y + M.CAM_DY
    label_y = p.y - SLAB_H / 2 + 5 + 10
    fr = frustum((p.x, lens_y, lens_z - 0.5), (p.x - 37, label_y - 12, c + 0.5), (p.x + 37, label_y + 12, c + 0.5))
    vol, who = blocked(fr, [q for q in parts if q.group in ("head", "carriage") and q.name not in ("head_camera", "held_slab", "held_label")])
    record("head camera line-of-sight to back label: blocked volume (mm3)", vol, 1.0, who, larger_is_better=False)
    need = math.degrees(math.atan2(abs(label_y - 12 - lens_y), lens_z - c))
    record("head camera half-angle needed to see label edge (deg, <= 30)", need, 30.0, "", larger_is_better=False)


HOVER_GAP = 7.0  # cup face above the top slab's back for the frame from above (software: approach_gap 5 + 2; lens 147 above it)


def _free_machine(x: float, c: float, fill: dict) -> list:
    """The machine with the cup FREE (buffer at rest), as at hover and while a slab hangs on it (machine() poses the probe trip)."""
    return M.frame_parts() + M.bed_parts() + M.carriage_parts(x) + M.head_parts(x, c, compression=0.0) + M.stacks(fill)


def _window_view(parts, lens, plane_z: float, skip: tuple) -> tuple[float, float, str]:
    """Frustums from the lens to every FACE_DOWN_WINDOW_MM rectangle 0.5 mm above the slab plane z: total volume of parts
    inside them (no threshold), and the smallest gap between them and any part (mm, 0 = touching), with its name."""
    fr = [frustum((lens[0], lens[1], lens[2] - 0.5), (lens[0] + x0, lens[1] - M.CAM_DY + y0, plane_z + 0.5), (lens[0] + x1, lens[1] - M.CAM_DY + y1, plane_z + 0.5))
          for x0, y0, x1, y1 in L.FACE_DOWN_WINDOW_MM]
    vol, gap = 0.0, (1e9, "")
    for p in parts:
        if p.name in skip or p.name.startswith(("pad_", "bed_")):
            continue
        s = p.shape.val()
        for f in fr:
            if not _near(f, s, 5.0):
                continue
            d = f.distance(s)
            gap = min(gap, (d, p.name))
            if d < 1e-6:
                vol += f.intersect(s).Volume()
    return vol, gap[0], gap[1]


def check_face_down_window() -> None:
    """The software's face-down check compares the card back seen through FACE_DOWN_WINDOW_MM (layout.py) with earlier
    face-down slabs: the head camera must see all of it, and only card. Exact frustums from the lens (CAM_DY toward the label
    from the cup axis) to each rectangle, against every part except the camera and the slab looked at, at hover (free cup
    HOVER_GAP above the top slab, over a stack of 1, 15 and 30) and with the slab held (it hangs CUP_HANG below c) at travel
    height. Then where the window lies on the slab: area, card top, card sides, label band."""
    p = P[4]
    worst = (-1.0, 1e9, "", "")
    for n in (1, 15, L.STACK_MAX):
        top = n * SLAB_T
        c = top + HOVER_GAP
        parts = _free_machine(p.x, c, {**FULL, p.index: n})
        vol, gap, who = _window_view(parts, (p.x, p.y + M.CAM_DY, c + M.CAM_Z), top, ("head_camera", f"stack_{p.index}", f"labels_{p.index}"))
        record(f"face-down window, hover over a stack of {n} (lens {M.CAM_Z + HOVER_GAP:.0f} mm above the slab): parts in view (mm3)", vol, 0.01, who if vol else "",
               larger_is_better=False)
        worst = min(worst, (gap, n, who), key=lambda w: w[0] if w[0] >= 0 else 1e9)
    record("face-down window at hover: nearest part to the view, all stack heights (clearance mm)", worst[0], 0.5, f"{worst[2]}, stack of {worst[1]}")
    for c in sorted({L.C_SAFE_EMPTY, L.C_SAFE_LOADED}):  # the travel heights (one since the carry sensor moved up)
        parts = _free_machine(p.x, c, FULL)
        z0 = c - L.CUP_HANG - SLAB_T
        parts.append(M.Part("held_slab", M.slab(p.x, L.Y_ROW, z0), M.SLAB, "slab", "head"))
        vol, gap, who = _window_view(parts, (p.x, p.y + M.CAM_DY, c + M.CAM_Z), z0 + SLAB_T, ("head_camera", "held_slab"))
        record(f"face-down window, slab held at c={c:.1f} (hanging {L.CUP_HANG:.0f} mm under the cup): parts in view (mm3)", vol, 0.01, who if vol else "",
               larger_is_better=False)
        record(f"face-down window, slab held at c={c:.1f}: nearest part to the view (clearance mm)", gap, 0.5, who)
    # where it lies on the slab (mm from the cup axis; the slab may lie WINDOW_PLACE_TOL off it)
    edge = -SLAB_H / 2
    card_top = edge + L.CARD_TOP_FROM_EDGE[2] + L.WINDOW_PLACE_TOL
    side = L.CARD_W / 2 - 1.85 - L.XY_CAL_RESIDUAL - 1.0
    w = L.FACE_DOWN_WINDOW_MM
    record(f"face-down window area: {len(w)} rectangle(s) (mm2, software needs 300)", L.window_area(), 300.0)
    record("face-down window inside the card's top edge, latest card top measured (37.8 mm) and the slab at the end of its play (mm)",
           min(r[1] for r in w) - card_top, 0.0, f"median card top: {min(r[1] for r in w) - (edge + L.CARD_TOP_FROM_EDGE[1]):.1f} mm inside, slab centred")
    record("face-down window inside the card's side edges, slab at the end of its X play (mm)", side - max(max(abs(r[0]), abs(r[2])) for r in w), 0.0)
    record("face-down window clear of the label band, slab at the end of its play (mm)", min(r[1] for r in w) - (edge + L.LABEL_BAND + L.WINDOW_PLACE_TOL), 3.0)


AIM_SEARCH = 4.0  # deg: aim errors searched. [Guessing] an M12 lens off its board's sensor centre plus a printed bracket: 0.5-2 deg
AIM_FLOOR = 0.5  # deg: a floor that keeps head or window changes from eating the margin. A real camera can be further off, so
# the software has to find where the head parts and the card top fall in its own frames; this is no build tolerance.
AIM_DIRS = {"toward the cup (+Y)": ((1, 0, 0), 1), "toward the label (-Y)": ((1, 0, 0), -1), "+X": ((0, 1, 0), -1), "-X": ((0, 1, 0), 1)}


def _aim_turn(v, axis, deg: float) -> tuple[float, float, float]:
    """Vector v turned by deg about a unit axis (right hand, as cq.Shape.rotate)."""
    a, (kx, ky, kz), (x, y, z) = math.radians(deg), axis, v
    c, s, d = math.cos(a), math.sin(a), (kx * x + ky * y + kz * z) * (1 - math.cos(a))
    return (x * c + (ky * z - kz * y) * s + kx * d, y * c + (kz * x - kx * z) * s + ky * d, z * c + (kx * y - ky * x) * s + kz * d)


def check_camera_aim() -> None:
    """How far the head camera may be off its nominal aim before the face-down window stops showing only card. The software
    places the window in pixels from a nominal camera (image centre on the optical axis, square to the slab, mapped at the
    hover distance), so an aim error turns every ray of the window about the lens. Head parts: the exact frustums of
    check_face_down_window turned about the lens, nearest-part test, bisection (the head's own parts sit at fixed angles from
    the lens, so one hover pose holds for every stack and for a held slab). Card edges: the window's corners turned the
    same way onto the slab plane, for a median card on a centred slab and for the worst-case slab (as above)."""
    p, n = P[4], 15
    top = n * SLAB_T
    c = top + HOVER_GAP
    parts = [q for q in _free_machine(p.x, c, {**FULL, p.index: n})
             if q.name not in ("head_camera", f"stack_{p.index}", f"labels_{p.index}") and not q.name.startswith(("pad_", "bed_"))]
    lens = cq.Vector(p.x, p.y + M.CAM_DY, c + M.CAM_Z)
    win = L.face_down_window_cam()  # camera-axis mm at the hover distance, as the software has it
    fr = [frustum((lens.x, lens.y, lens.z - 0.5), (lens.x + x0, lens.y + y0, top + 0.5), (lens.x + x1, lens.y + y1, top + 0.5)) for x0, y0, x1, y1 in win]

    def hit(axis, deg: float) -> str:
        for f in fr:
            g = f.rotate(lens, lens + cq.Vector(*axis), deg) if deg else f
            for q in parts:
                s = q.shape.val()
                if _near(g, s, 1.0) and g.distance(s) < 1e-6:
                    return q.name
        return ""

    head = {}
    for k, (axis, sg) in AIM_DIRS.items():
        if not hit(axis, sg * AIM_SEARCH):
            head[k] = (AIM_SEARCH, "")
            continue
        d = _bisect(lambda a: bool(hit(axis, sg * a)), 0.0, AIM_SEARCH, 12)
        head[k] = (d, hit(axis, sg * (d + 0.01)))  # the part that comes into view first
    k = min(head, key=lambda j: head[j][0])
    record(f"head camera aim error before a head part is in the face-down window, worst direction (deg; searched to {AIM_SEARCH:.0f})", round(head[k][0], 2),
           AIM_FLOOR, f"{head[k][1]} first; " + ", ".join(f"{j} {v[0]:.2f}" + ("" if v[1] else "+") for j, v in head.items()))
    dist = M.CAM_Z + HOVER_GAP
    edge = -SLAB_H / 2
    slabs = {"median card, slab centred": (edge + L.CARD_TOP_FROM_EDGE[1], L.CARD_W / 2, AIM_FLOOR),
             "worst-case slab (latest card top, end of its play)": (edge + L.CARD_TOP_FROM_EDGE[2] + L.WINDOW_PLACE_TOL, L.CARD_W / 2 - 1.85 - L.XY_CAL_RESIDUAL - 1.0, 0.0)}
    for name, (card_top, side, floor) in slabs.items():
        def on_card(axis, deg: float) -> bool:
            for x0, y0, x1, y1 in win:
                for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                    vx, vy, vz = _aim_turn((x, y, -dist), axis, deg)
                    px, py = vx * dist / -vz, vy * dist / -vz + L.HEAD_CAM_DY  # on the slab plane, from the cup axis
                    if py < card_top or abs(px) > side:
                        return False
            return True
        tol = {k: (_bisect(lambda d: not on_card(axis, sg * d), 0.0, AIM_SEARCH, 16) if not on_card(axis, sg * AIM_SEARCH) else AIM_SEARCH)
               for k, (axis, sg) in AIM_DIRS.items()}
        k = min(tol, key=tol.get)
        record(f"head camera aim error before the face-down window leaves the card, {name}, worst direction (deg)", round(tol[k], 2), floor,
               f"{k}; " + ", ".join(f"{j} {v:.2f}" + ("+" if v >= AIM_SEARCH else "") for j, v in tol.items()))


CARRY_STEPS = sorted({L.C_HARD_BOTTOM, *range(-10, 262, 4), L.CARRY_SENSOR_C0 - 0.5, L.CARRY_SENSOR_C0, L.CARRY_SENSOR_C0 + 0.5, L.C_SAFE_EMPTY,
                      L.C_SAFE_LOADED, L.C_MAX, L.Z_SWITCH_C, L.C_HARD_TOP})


def check_carry_sensor() -> None:
    """The Z stall guard: the spare TCST2103 on the Z spine (fixed to the X carriage) and its flag on the z_plate (moves with Z).
    The beam must be blocked for every cup height from CARRY_SENSOR_C0 up to the Z hard top stop and clear below it; the flag,
    its arm and their screws must clear everything fixed to the carriage over the whole Z travel; the board's lead must have a
    path to the spine top clear of everything that moves. Carriage-local (cup X = 0); the flag set moves rigidly with c."""
    fixed = {p.name: p.shape.val() for p in M.carriage_parts(0.0)}
    mov = {p.name: p.shape.val() for p in M.carry_flag_parts(0.0, 0.0)}
    flag, ap = mov["carry_flag"], M.carry_sensor_aperture().val()
    full = M.TCST_AP * M.TCST_AP_DEPTH * M.FLAG_T
    frac = lambda c: _moved(flag, c).intersect(ap).Volume() / full  # noqa: E731
    c0 = L.CARRY_SENSOR_C0
    trip = _bisect(lambda c: frac(c) >= 0.5, c0 - 5.0, c0 + 5.0)
    record(f"carry sensor: cup height at which the flag edge crosses the beam centre, error vs CARRY_SENSOR_C0 = {c0:.1f} (mm)", abs(trip - c0), 0.05,
           f"trips at c = {trip:.2f}", larger_is_better=False)
    below = [c for c in CARRY_STEPS if c <= c0 - M.TCST_AP / 2 - 0.05]
    worst_lo = max(below, key=frac)
    record(f"carry sensor: beam clear at every height from c = {L.C_HARD_BOTTOM:.0f} to {below[-1]:.1f} (max blocked share)", frac(worst_lo), 0.0,
           f"highest at c = {worst_lo:.1f}", larger_is_better=False)
    above = [c for c in CARRY_STEPS if c >= c0 + M.TCST_AP / 2 + 0.05]
    worst_hi = min(above, key=frac)
    record(f"carry sensor: beam fully blocked from c = {above[0]:.1f} to the hard top stop {L.C_HARD_TOP:.0f} (min blocked share)", frac(worst_hi), 0.999,
           f"lowest at c = {worst_hi:.1f}; {M.CF_LEN - (L.C_HARD_TOP - c0) - M.TCST_AP / 2:.1f} mm of flag left below the beam at the top stop")
    travel = min(L.C_SAFE_EMPTY, L.C_SAFE_LOADED)
    record(f"carry sensor: margin between its trip and the lowest travel height {travel} (mm, software needs CARRY_BAND)", travel - trip, L.CARRY_BAND)
    # one edge: a head that stalled on the way up still reads blocked down to the trip less the band, and moves sideways
    low = trip - L.CARRY_BAND
    record("carry sensor: a double pick of two thick holders on a head stalled just above where it reads clear, over the rod tops (mm)",
           low - L.CUP_HANG - 2 * L.SLAB_T_THICK_MAX - L.POST_H, 2.0, f"head at c = {low:.1f}: a Z loss over {L.C_SAFE_LOADED - low:.1f} mm reads clear before any sideways move")
    sensor = fixed["carry_sensor"]
    others = {n: s for n, s in fixed.items() if n != "carry_sensor"}
    dflag, dall = (1e9, 0.0, ""), (1e9, 0.0, "")
    for c in CARRY_STEPS:
        mv = {n: _moved(s, c) for n, s in mov.items()}
        dflag = min(dflag, (mv["carry_flag"].distance(sensor), c, "carry_flag/carry_sensor"))
        for n, s in mv.items():
            for o, os_ in others.items():
                if _near(s, os_, 3.0):
                    dall = min(dall, (s.distance(os_), c, f"{n}/{o}"))
            if n != "carry_flag" and _near(s, sensor, 3.0):
                dall = min(dall, (s.distance(sensor), c, f"{n}/carry_sensor"))
    S = f"c = {L.C_HARD_BOTTOM:.0f}..{L.C_HARD_TOP:.0f}"
    record(f"carry sensor: flag vs the sensor over {S} (min clearance, mm)", dflag[0], 0.5, f"at c = {dflag[1]:.0f}")
    record(f"carry sensor: flag, arm and screw heads vs every part fixed to the X carriage over {S} (min clearance, mm)", dall[0], 1.0,
           f"{dall[2]} at c = {dall[1]:.0f}")
    cable = M.carry_sensor_cable().val()
    head = [p for p in M.head_parts(0.0, 0.0, compression=0.0)]
    dc = (1e9, 0.0, "")
    for c in CARRY_STEPS:
        for p in head:
            s = _moved(p.shape.val(), c)
            if _near(s, cable, 60.0):
                dc = min(dc, (s.distance(cable), c, p.name))
    record(f"carry sensor: its lead (header up to the spine top) vs everything that moves with Z over {S} (min clearance, mm)", dc[0], 3.0, f"{dc[2]} at c = {dc[1]:.0f}")
    hit = [n for n, s in fixed.items() if n not in ("carry_sensor", "carry_sensor_mount") and _near(s, cable, 0.0) and s.intersect(cable).Volume() > OVERLAP_TOL]
    record("carry sensor: its lead vs the parts fixed to the X carriage (parts it would cut through, count)", len(hit), 0, ",".join(hit), larger_is_better=False)


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


STROKE = sorted({0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, L.BUFFER_STROKE})
READ_T = L.CUP_HANG + L.PROBE_TRIP_TOL  # the head camera reads with the cup free or seated (a late trip at most)
PROBE_T = READ_T + L.PROBE_WINDOW  # deepest buffer travel while probing (a late trip plus the whole window)


def check_probe() -> None:
    """Probe flag vs the TCST2103's beam, the sensor, its guide in head_foot and the head camera's label view, swept over
    the whole buffer stroke (t = 0 free .. 20 mm), in head-local coordinates (cup axis X = Y = 0, c = 0)."""
    rest = {p.name: p.shape.val() for p in M.head_parts(0.0, 0.0, compression=0.0)}
    flag, sensor, foot = rest["probe_flag"], rest["contact_sensor"], rest["head_foot"]
    ap = M.probe_aperture().val()
    full = M.TCST_AP * M.TCST_AP_DEPTH * M.FLAG_T  # aperture area x plate thickness
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
    S = f"0..{L.BUFFER_STROKE:.0f} mm"
    guide_box = M.box(M.FLAG_X[0] + 0.5, M.PROBE_Y - M.GUIDE_GAP / 2, M.FOOT_Z[0], M.FLAG_X[1], M.PROBE_Y + M.GUIDE_GAP / 2, M.GUIDE_TOP).val()
    blade_w = M.FLAG_X[1] - M.FLAG_X[0] - 0.5
    fixed_other = [rest[n] for n in rest if n in ("buffer", "camera_bracket", "head_camera", "drop_arm") or n.startswith("probe_m3") or n.startswith("probe_nut")]
    above = [rest[n] for n in ("head_foot", "contact_sensor", "camera_bracket", "head_camera", "drop_arm")]
    ds, dg, do, dm, dc, eng = (1e9, 0), (1e9, 0), (1e9, 0), (1e9, 0), (1e9, 0), (1e9, 0)
    for t in STROKE:
        ft = _moved(flag, t)
        ds = min(ds, (ft.distance(sensor), t))
        dg = min(dg, (ft.distance(foot), t))
        do = min(do, (min(ft.distance(o) for o in fixed_other), t))
        movers = [_moved(rest["buffer_stop"], t), _moved(rest["vac_fitting"], t)]
        dm = min(dm, (min(m.distance(o) for m in movers for o in above), t))
        dc = min(dc, (_moved(rest["cup"], t).distance(rest["buffer"]), t))
        eng = min(eng, (ft.intersect(guide_box).Volume() / (blade_w * M.FLAG_T), t))
    record(f"probe: flag vs the sensor over {S} of buffer travel (min clearance, mm)", ds[0], 0.5, f"at {ds[1]:.0f} mm")
    record(f"probe: flag vs its guide in head_foot over {S} (min clearance, mm)", dg[0], 0.3, f"at {dg[1]:.0f} mm; slot {M.GUIDE_GAP:.1f} for a {M.FLAG_T:.1f} flag")
    record(f"probe: flag vs buffer body and nuts, board screws, arm and camera over {S} (min clearance, mm)", do[0], 1.0, f"at {do[1]:.0f} mm")
    record(f"probe: buffer stop + vacuum fitting vs foot, sensor, arm and camera over {S} (min clearance, mm)", dm[0], 1.0, f"at {dm[1]:.0f} mm")
    record(f"probe: pad and its hex vs the buffer body over {S} (min clearance, mm)", dc[0], 1.0, f"at {dc[1]:.0f} mm")
    record(f"probe: blade depth in the guide, worst over {S} (mm)", eng[0], 3.0, f"at {eng[1]:.0f} mm")
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
    record(f"probe: trip adjustment, board slots +/-{M.PROBE_ADJ} mm: board vs head_foot overlap at the slot ends (mm3)",
           worst_o, OVERLAP_TOL, "", larger_is_better=False)
    record(f"probe: trip adjustment: flag vs the sensor with the board at either slot end, over {S} (min clearance, mm)", worst_f[0], 0.5, f"board at {worst_f[1]:+.1f}")
    check_buffer_shift(rest)
    check_key_access()
    # the head camera's label view: every moving part while it reads; the flag and the buffer stop to the end of a probe
    label_y = -SLAB_H / 2 + 5 + 10
    fr = frustum((0, M.CAM_DY, M.CAM_Z - 0.5), (-37, label_y - 12, 0.5), (37, label_y + 12, 0.5))
    def view(names, ts):
        w = (0.0, 0.0)
        for t in ts:
            for nm in names:
                sh = _moved(rest[nm], t)
                if _near(fr, sh, 1):
                    w = max(w, (fr.intersect(sh).Volume(), t))
        return w
    vr = view(("probe_flag", "buffer_stop", "vac_fitting", "cup", "buffer_rod"), [t for t in STROKE if t <= READ_T])
    record(f"head camera label view while reading (buffer travel 0..{READ_T} mm): every moving part (max blocked mm3)", vr[0], 1.0,
           f"at {vr[1]:.1f} mm" if vr[0] else "", larger_is_better=False)
    vp = view(("probe_flag", "buffer_stop"), [t for t in STROKE if t <= PROBE_T] + [PROBE_T])
    record(f"head camera label view: flag + buffer stop to the end of a probe (0..{PROBE_T} mm, max blocked mm3)", vp[0], 1.0,
           f"at {vp[1]:.1f} mm" if vp[0] else "", larger_is_better=False)


def check_buffer_shift(rest: dict) -> None:
    """BUILD_GUIDE 7.5 sets the head lens 140 mm above the cup by moving the buffer on its M10 nuts. A buffer moved up by d
    carries the flag d higher past the foot-mounted sensor and guide; the board is slid d to keep the 2 mm trip, and the
    lens ends up 140 mm above the cup again, so the head camera moves with the buffer. Sweep d = +/-BUFFER_SHIFT."""
    d0 = M.BUFFER_SHIFT
    record(f"probe: buffer moved +/-{d0:.0f} mm on its thread: board slide needed incl. the trip tolerance, vs the +/-{M.PROBE_ADJ} slots (spare mm)",
           M.PROBE_ADJ - d0 - L.PROBE_TRIP_TOL, 0.0)
    moving = ("cup", "buffer_rod", "buffer_stop", "probe_flag", "vac_fitting")
    board = [n for n in rest if n == "contact_sensor" or n.startswith(("probe_m3", "probe_nut"))]
    guide_box = M.box(M.FLAG_X[0] + 0.5, M.PROBE_Y - M.GUIDE_GAP / 2, M.FOOT_Z[0], M.FLAG_X[1], M.PROBE_Y + M.GUIDE_GAP / 2, M.GUIDE_TOP).val()
    blade_w = M.FLAG_X[1] - M.FLAG_X[0] - 0.5
    nuts = M.cyl((0, 0, M.FOOT_Z[0] - M.BUFFER_NUT[1]), *M.BUFFER_NUT).val().fuse(M.cyl((0, 0, M.FOOT_Z[1]), *M.BUFFER_NUT).val())  # stay on the foot
    lims = {"head_foot": 0.3, "contact_sensor": 0.5}  # the guide, the sensor; everything else 1.0 (as over the stroke above)
    eng, dflag, dstk = (1e9, 0, 0), (1e9, 0, 0, ""), (1e9, 0, 0, "")
    for d in (-d0, d0):
        fixed = {"head_foot": rest["head_foot"], "drop_arm": rest["drop_arm"], "camera_bracket": rest["camera_bracket"], "nuts": nuts,
                 "buffer body": M.cyl((0, 0, M.BODY_Z[0] + d), 10.0, M.BUF_G).val(), "head_camera": _moved(rest["head_camera"], d),
                 **{n: _moved(rest[n], d) for n in board}}
        for t in (0.0, L.CUP_HANG, L.PROBE_WINDOW, L.BUFFER_STROKE):
            mv = {n: _moved(rest[n], d + t) for n in moving}
            fl = mv["probe_flag"]
            if t == L.BUFFER_STROKE:
                eng = min(eng, (fl.intersect(guide_box).Volume() / (blade_w * M.FLAG_T), d, t))
            for n, o in fixed.items():
                dflag = min(dflag, (fl.distance(o) - lims.get(n, 1.0), d, t, n))
                for k in ("buffer_stop", "vac_fitting", "cup"):
                    if n not in ("buffer body", "nuts") or k == "cup":  # the stop rests on the body top when free
                        dstk = min(dstk, (mv[k].distance(o), d, t, f"{k}/{n}"))
    record(f"probe: buffer moved +/-{d0:.0f} mm on its thread: blade depth in the guide at full stroke (mm)", eng[0], 3.0, f"buffer {eng[1]:+.0f} mm")
    record(f"probe: buffer moved +/-{d0:.0f} mm: flag vs guide (0.3), sensor (0.5), body, nuts, screws, arm, camera (1.0): worst margin over its limit (mm)", dflag[0], 0.0,
           f"{dflag[3]}, buffer {dflag[1]:+.0f} mm, travel {dflag[2]:.0f} mm")
    record(f"probe: buffer moved +/-{d0:.0f} mm: buffer stop, fitting and pad vs foot, sensor, board, body, nuts, arm, camera (min clearance, mm)", dstk[0], 1.0,
           f"{dstk[3]}, buffer {dstk[1]:+.0f} mm, travel {dstk[2]:.0f} mm")


def check_key_access() -> None:
    """Step 8 of BUILD_GUIDE 7.6 slides the board with both M3 screws loose and the flag and fitting in place. The rear screw
    (Y +17) takes a plain 2.5 mm key straight along -X; the front one (label side, Y -2) sits in the buffer's and the
    fitting's shadow, so it needs a ball-end key tilted toward the label. Both at the slot ends and centre, free and tripped."""
    tilt = 20.0
    out = {}
    for y, deg in ((M.PROBE_Y - M.PROBE_HOLES / 2, tilt), (M.PROBE_Y + M.PROBE_HOLES / 2, 0.0)):
        a = math.radians(deg)
        direction = (-math.cos(a), -math.sin(a), 0.0)
        worst = (1e9, "")
        for t in (0.0, L.CUP_HANG):
            parts = [p for p in M.head_parts(0.0, 0.0, compression=t) if not p.name.startswith(("probe_m3", "probe_nut", "z_", "fh_"))]
            for dz in (-M.PROBE_ADJ, 0.0, M.PROBE_ADJ):
                x0 = M.TCST_BASE_X - M.TCST_FLANGE_T - M.M3_WASHER[1] - M.M3_HEAD[1] + 1.5  # 1.5 mm into the M3 socket (head on its washer)
                key = M.cyl((x0, y, M.PROBE_BEAM_Z + dz), 2.5, 70.0, direction).val()
                for p in parts:
                    sh = _moved(p.shape.val(), dz) if p.name == "contact_sensor" else p.shape.val()
                    if _near(key, sh, 5):
                        worst = min(worst, (key.distance(sh), p.name))
        out[y] = worst
    yf, yr = sorted(out)
    record(f"probe board: 2.5 mm ball-end key into the front (label-side) M3 screw, tilted {tilt:.0f} deg toward the label (min clearance, mm)", out[yf][0], 0.5, out[yf][1])
    record("probe board: 2.5 mm key straight into the rear M3 screw (min clearance, mm)", out[yr][0], 0.5, out[yr][1])


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
    record("Z bottom hard stop before the buffer bottoms on the bare pad (mm)", L.C_HARD_BOTTOM + L.BUFFER_STROKE - L.CUP_HANG, 2.0)
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
    fr = frustum((0, M.CAM_DY, M.P0_TOP_Z - 0.5), (-37, label_y - 12, zb + 0.5), (37, label_y + 12, zb + 0.5))
    vol, who = blocked(fr, viewers)
    record("Phase 0: head camera line-of-sight to the back label, occluder fitted: blocked volume (mm3)", vol, 1.0, who, larger_is_better=False)
    # occluder: the jig must show the head camera what the machine shows it
    jp = {p.name: p for p in parts}
    cup = jp["p0_cup"].shape.val().BoundingBox()
    record(f"Phase 0: cup face on the slab back, pushed up the {L.CUP_HANG:.0f} mm trip travel (gap mm)", abs(cup.zmin - zb), 0.05,
           f"cup centre {math.hypot(cup.center.x, cup.center.y):.2f} mm off the lens axis", larger_is_better=False)
    mx, mc = P[4].x, L.C_SAFE_LOADED
    mp = {p.name: p for p in M.machine(mx, mc, held_slab=True, fill=FULL)}
    lens_m, lens_j = (mx, M.CAM_DY, mc + M.CAM_Z), (0.0, M.CAM_DY, M.P0_TOP_Z)
    def rel(part, lens, keep=6):
        b = part.shape.val().BoundingBox()
        return [v - lens[i // 2] for i, v in enumerate((b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax))][:keep]
    pairs = [(n, "p0_" + n, 6) for n in mp if mp[n].group == "head" and "p0_" + n in jp] + [("drop_arm", "p0_arm_stub", 5)]  # stub = the arm's lower end
    worst = max((max(abs(a - b) for a, b in zip(rel(mp[m], lens_m, k), rel(jp[j], lens_j, k))), m) for m, j, k in pairs)
    record("Phase 0 occluder vs machine, relative to the head lens: worst bounding-box offset (mm)", worst[0], 1.0, f"{worst[1]}; {len(pairs)} parts compared",
           larger_is_better=False)
    def whole(lens):  # the head camera's view of the WHOLE slab back (centred on the cup axis), down to 1 mm above the cup face
        z, cy = lens[2] - M.CAM_Z + 1.0, lens[1] - M.CAM_DY
        return frustum((lens[0], lens[1], lens[2] - 0.5), (lens[0] - SLAB_W / 2, cy - SLAB_H / 2, z), (lens[0] + SLAB_W / 2, cy + SLAB_H / 2, z))
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
    S = f"0..{L.BUFFER_STROKE:.0f} mm"
    movers = ("p0_probe_flag", "p0_buffer_stop", "p0_vac_fitting")
    jrest = {p.name: p.shape.val() for p in M.phase0_parts(compression=0.0)}
    obst = [jrest[n] for n in ("p0_occluder_mount", "p0_top", "p0_head_camera", "p0_arm_stub", "p0_post_1")]
    dj = min((min(_moved(jrest[n], t).distance(o) for n in movers for o in obst), t) for t in STROKE)
    record(f"Phase 0: occluder flag, buffer stop and fitting over {S} vs mount, bridge, camera, stub, post (min clearance, mm)", dj[0], 1.0, f"at {dj[1]:.0f} mm")
    # face-up pass: the mount (with the stub and the whole occluder) slid P0_FACE_UP_LIFT up its post
    lift = M.P0_FACE_UP_LIFT
    up = M.phase0_parts(compression=0.0, lift=lift)
    record_interference(f"Phase 0 jig, occluder mount slid up {lift:.0f} mm for the face-up pass", up, movers_only=False)
    ju = {p.name: p.shape.val() for p in up}
    record(f"Phase 0 face-up pass (mount slid up {lift:.0f} mm): free cup above the slab's front (mm)", ju["p0_cup"].BoundingBox().zmin - zb, 0.5)
    obst = [ju[n] for n in ("p0_occluder_mount", "p0_top", "p0_head_camera", "p0_arm_stub", "p0_post_1")]
    push = [t for t in STROKE if t <= 12.0]
    du = min((min(_moved(ju[n], t).distance(o) for n in movers for o in obst), t) for t in push)
    record(f"Phase 0 face-up pass: flag, stop and fitting pushed up 0..12 mm to change a slab vs mount, bridge, camera, stub, post (min clearance, mm)",
           du[0], 1.0, f"at {du[1]:.0f} mm")
    df = min((min(_moved(ju[n], t).distance(o) for n in movers for o in obst), t) for t in STROKE if t > 12.0)
    record(f"Phase 0 face-up pass: the same pushed on to the buffer's end ({L.BUFFER_STROKE:.0f} mm): no contact (min clearance, mm)", df[0], 0.1,
           f"at {df[1]:.0f} mm")
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
    check_face_down_window()
    check_camera_aim()
    check_probe()
    check_carry_sensor()
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
