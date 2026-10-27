"""SlabRail parametric model (CadQuery).

Everything is built from layout.py:
  * static: base, bed, guide rods, read station, uprights, X beam + rail, X motor/idler, X end bumpers, X home switch
  * carriage (moves in X): X carriage, X bracket + belt clamps, Z spine + rail + end cap, Z motor, Z top switch
  * head (moves in Z): Z carriage, Z plate, drop arm, cup + spring buffer, contact sensor + probe flag + its guide,
    camera; the buffer's moving parts take the buffer travel as a parameter (head_parts(compression=...))
  * printed parts (exported individually as STL/STEP in print orientation)
  * the Phase 0A jig, which hangs the machine's own occluder parts (occluder_parts) under its head camera
  * fastener heads where a head could foul another part (kind "fastener"), so checks.py sees them

Purchased parts (extrusions, rails, motors, cameras) are simplified envelopes: accurate
where they interface with something, not cosmetically detailed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq

import layout as L
from dims import SLAB_H, SLAB_T, SLAB_W

# --------------------------------------------------------------------------- helpers


def box(x0, y0, z0, x1, y1, z1) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cbox(cx, cy, cz, sx, sy, sz) -> cq.Workplane:
    return cq.Workplane("XY").box(sx, sy, sz).translate((cx, cy, cz))


def cyl(p, d, h, direction=(0, 0, 1)) -> cq.Workplane:
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(d / 2, h, cq.Vector(*p), cq.Vector(*direction)))


def hexagon(cx, cy, z0, af, h) -> cq.Workplane:
    """Hex nut trap (vertical axis), `af` across flats."""
    return cq.Workplane("XY").polygon(6, af / 0.8660254).extrude(h).translate((cx, cy, z0))


def holes_z(body, pts, d, z0=-50, h=200):
    for x, y in pts:
        body = body.cut(cyl((x, y, z0), d, h))
    return body


def holes_y(body, pts_xz, d, y0=-500, h=1000):
    for x, z in pts_xz:
        body = body.cut(cyl((x, y0, z), d, h, (0, 1, 0)))
    return body


def holes_x(body, pts_yz, d, x0=-500, h=1000):
    for y, z in pts_yz:
        body = body.cut(cyl((x0, y, z), d, h, (1, 0, 0)))
    return body


def slot_y(body, x0, x1, z, d):
    """Slot through the body along Y, axis at height z, running from x0 to x1."""
    body = body.cut(box(x0, -500, z - d / 2, x1, 500, z + d / 2))
    return holes_y(body, [(x0, z), (x1, z)], d)


M3_CLR, M5_CLR = 3.4, 5.5
M3_HEAD, M5_HEAD, M5_BUTTON = (5.5, 3.0), (8.5, 5.0), (9.5, 2.75)  # (dia, height)
M3_CBORE = (6.5, 3.5)  # counterbore for an M3 socket head: dia, depth
NEMA = 42.3


@dataclass
class Part:
    name: str
    shape: cq.Workplane
    color: tuple[float, float, float, float]
    kind: str  # printed | purchased | made (cut from stock) | slab | wood | foam | fastener
    group: str  # static | carriage | head
    note: str = ""
    meta: dict = field(default_factory=dict)


ALU = (0.72, 0.74, 0.77, 1.0)
STEEL = (0.55, 0.57, 0.6, 1.0)
BLACK = (0.12, 0.12, 0.13, 1.0)
PETG = (0.95, 0.45, 0.1, 1.0)
WOOD = (0.82, 0.68, 0.48, 1.0)
DOWEL = (0.86, 0.75, 0.55, 1.0)
PAD = (0.25, 0.25, 0.3, 1.0)
SLAB = (0.85, 0.92, 1.0, 0.55)
LABEL = (0.95, 0.95, 0.95, 1.0)
LABEL_RED = (0.85, 0.15, 0.12, 1.0)
GREEN = (0.1, 0.55, 0.25, 1.0)
RING = (0.97, 0.96, 0.88, 1.0)  # LED ring diffuser
LEAD = (0.8, 0.12, 0.1, 1.0)


def head(name, p, axis, size, group) -> Part:
    """A screw head sitting on a surface at p, growing along axis."""
    d, h = size
    return Part(name, cyl(p, d, h, axis), STEEL, "fastener", group)


# --------------------------------------------------------------------------- frame geometry

GX0, GX1, GY0, GY1 = L.grid_extent()
SX, SY = L.station_xy()
T = L.travel_needed()
BEAM_Y0 = L.Y_ROW + L.Y_CUP_TO_BEAM  # X beam front face (rail mounting face)
BEAM_Y1 = BEAM_Y0 + 40
Z_BEAM_BOT, Z_BEAM_TOP = L.X_BEAM_Z - 20, L.X_BEAM_Z + 20
Z_BED_TOP = -L.PAD_T
Z_BED_BOT = Z_BED_TOP - L.BED_T
Z_BASE_TOP, Z_BASE_BOT = Z_BED_BOT, Z_BED_BOT - 20
XL, XR = GX0 - 40, GX1 + 40  # upright centre lines (X)
BEAM_X0, BEAM_X1 = XL - 20, XR + 20
BED_X0, BED_X1 = BEAM_X0, BEAM_X1
BED_Y0, BED_Y1 = GY0 - 40, BEAM_Y1 + 25
BASE_RAIL_YS = (GY0 + 10, (BEAM_Y0 + BEAM_Y1) / 2)
FOOT_XS = (("L", XL), ("M", (XL + XR) / 2), ("R", XR))  # rubber feet under both base rails: ends + midspan
X_RAIL_LEN = L.X_RAIL_LEN
X_RAIL_X0 = L.X_RAIL_X0
XB_HALF = 30.0  # x_bracket half width (X); its edges land on the end bumpers
X_MOTOR_X = X_RAIL_X0 + X_RAIL_LEN + 32  # 1322: motor in FRONT of the beam, just past the rail end
X_IDLER_X = X_RAIL_X0 - 22  # -32
# GT2 loop in a vertical plane over the beam top. 20 mm up: the 16 mm pulley, the 18 mm idler and the lower
# strand clear the beam top and the idler foot, and the NEMA screws (heads on the beam side) clear the beam top.
X_PULLEY_Z = Z_BEAM_TOP + 20.0
X_STRAND_DZ = 6.4  # strand centre line above / below the pulley axis (20T pitch radius 6.37)
BELT_W, BELT_T = 6.0, 1.4
X_BELT_YC = 6.0  # belt centre line, Y from the beam front face
X_BELT_Y = (X_BELT_YC - BELT_W / 2, X_BELT_YC + BELT_W / 2)  # (3, 9)
X_PULLEY_Y = (1.5, 17.5)  # GT2 20T pulley (16 mm, teeth next to the motor plate, hub outboard), Y from the beam front face
X_IDLER_W = 9.0  # 20T toothed idler, flange to flange
X_MOTOR_PLATE_T = 5.0  # x_motor_mount face plate; the motor face sits on its front, so the shaft (24 mm) reaches Y +19
CLAMP_FLOOR_Z = X_PULLEY_Z + X_STRAND_DZ - BELT_T / 2  # upper-strand underside = x_bracket clamp floor (445.7)
IDLER_SLOT = (-6.0, 2.0)  # idler axle travel in the cheek slots (tension pulls toward -X)
ROOF_Z = 690.0
GATE_X = (GX0 - 12, GX1 + 12)  # overfill light-beam posts, just outside the end rods


def cut_list() -> list[tuple[str, str, float, int]]:
    """(profile, use, length mm, qty) - purchased cut-to-length stock."""
    return [
        ("2040", "base rail (lying flat, under the bed)", round(BED_X1 - BED_X0), 2),
        ("4040", "upright", round(Z_BEAM_BOT - Z_BASE_TOP), 2),
        ("4040", "X beam (on top of the uprights)", round(BEAM_X1 - BEAM_X0), 1),
        ("2040", "Z spine (both ends tapped M5)", L.Z_SPINE_LEN, 1),
        ("2020", "head drop arm", round(ARM_Z[1] - ARM_Z[0]), 1),
        ("T8x8 lead screw", "Z screw below the motor face (cut the 400 mm screw; 311-356 works)", L.Z_SCREW_LEN, 1),
        ("1 mm aluminium sheet", f"probe flag blank, {FLAG_X[1] + FLAG_TAB_X:.1f} wide (cut to cad/out/probe_flag_blank.svg; bend; then drill 5.2)",
         round(13.0 - (FLAG_BOTTOM - FLAG_BEND_Z), 1), 1),
        ("2020", "Phase 0 jig post (cut square +/-0.5)", P0_POST, 2),
        ("2020", "Phase 0 jig arm stub (5.5 mm cross hole 19 mm from one end, match-drilled through head_foot)", P0_STUB, 1),
        ("1 mm aluminium sheet", f"carry-sensor flag, {CF_X[1] - CF_X[0]:.1f} wide, flat (2 x 3.4 holes {CF_X[1] - CF_SCREWS[0][0]:.1f} mm from the inner edge, "
         f"{CF_Z_TOP - CF_SCREWS[1][1]:.0f} and {CF_Z_TOP - CF_SCREWS[0][1]:.0f} mm below the top edge = the trip edge)", CF_LEN, 1),
    ]


# --------------------------------------------------------------------------- static


def frame_parts(cup_x: float | None = None) -> list[Part]:
    """``cup_x``: where the X carriage is, for the X home switch's lever (None = lever free)."""
    parts: list[Part] = []
    for i, y in enumerate(BASE_RAIL_YS):
        parts.append(Part(f"base_rail_{i}", box(BED_X0, y - 20, Z_BASE_BOT, BED_X1, y + 20, Z_BASE_TOP), ALU, "purchased", "static"))
    for x, side in ((XL, "L"), (XR, "R")):
        parts.append(Part(f"upright_{side}", box(x - 20, BEAM_Y0, Z_BASE_TOP, x + 20, BEAM_Y1, Z_BEAM_BOT), ALU, "purchased", "static"))
    for side, x in FOOT_XS:  # a free midspan would sag 1-3 mm under a full load; shim every foot to the bench
        parts.append(Part(f"foot_{side}", cbox(x, (BED_Y0 + BED_Y1) / 2, Z_BASE_BOT - 4, 60, BED_Y1 - BED_Y0, 8), BLACK, "purchased", "static", note="rubber foot strip"))
    parts.append(Part("x_beam", box(BEAM_X0, BEAM_Y0, Z_BEAM_BOT, BEAM_X1, BEAM_Y1, Z_BEAM_TOP), ALU, "purchased", "static"))
    parts.append(Part("x_rail", box(X_RAIL_X0, BEAM_Y0 - L.MGN12_RAIL_H, L.X_RAIL_Z - 6, X_RAIL_X0 + X_RAIL_LEN, BEAM_Y0, L.X_RAIL_Z + 6), STEEL, "purchased", "static", note="MGN12 1300 mm, M3 screws into T-nuts in the beam's upper front slot"))
    bed = box(BED_X0, BED_Y0, Z_BED_BOT, BED_X1, BED_Y1, Z_BED_TOP)
    for x in (XL, XR):  # notches so the uprights pass through the bed down to the base rail
        bed = bed.cut(box(x - 20.5, BEAM_Y0 - 0.5, Z_BED_BOT - 1, x + 20.5, BEAM_Y1 + 0.5, Z_BED_TOP + 1))
    parts.append(Part("bed_plywood", bed, WOOD, "wood", "static", note="18 mm plywood, 41x41 mm notches at the upright positions"))
    parts += x_drive_parts()
    parts += x_switch_parts(cup_x)
    parts.append(Part("light_roof", box(BED_X0, BED_Y0 - 40, ROOF_Z, BED_X1, BED_Y1 + 20, ROOF_Z + 5), (0.05, 0.05, 0.06, 0.35), "purchased", "static", note="black foam board light roof"))
    return parts


def x_drive_parts() -> list[Part]:
    """GT2 loop: motor in front of the beam (shaft +Y) at the right end, tensioned idler on the beam top at the left."""
    xm, xi, pz, yb = X_MOTOR_X, X_IDLER_X, X_PULLEY_Z, BEAM_Y0
    h = pz - Z_BEAM_TOP
    parts = [
        Part("x_motor", cbox(xm, yb - X_MOTOR_PLATE_T - 24, pz, NEMA, 48, NEMA), BLACK, "purchased", "static", note="NEMA17 48 mm, 24 mm shaft"),
        Part("x_motor_mount", x_motor_mount().translate((xm, yb, Z_BEAM_TOP)), PETG, "printed", "static"),
        Part("x_idler_mount", x_idler_mount().translate((xi, yb, Z_BEAM_TOP)), PETG, "printed", "static"),
        Part("x_idler_slider", x_idler_slider().translate((xi, yb, Z_BEAM_TOP)), PETG, "printed", "static"),
        Part("x_bumper_L", x_bumper().translate((L.X_HARD_STOP[0] - XB_HALF, yb, L.X_BEAM_Z)), PETG, "printed", "static"),
        Part("x_pulley", cyl((xm, yb + X_PULLEY_Y[0], pz), 16, X_PULLEY_Y[1] - X_PULLEY_Y[0], (0, 1, 0)), STEEL, "purchased", "static"),
        Part("x_idler", cyl((xi, yb + X_BELT_YC - X_IDLER_W / 2, pz), 18, X_IDLER_W, (0, 1, 0)), STEEL, "purchased", "static"),
    ]
    for zz, nm in ((pz - X_STRAND_DZ, "lo"), (pz + X_STRAND_DZ, "hi")):
        parts.append(Part(f"x_belt_{nm}", box(xi, yb + X_BELT_Y[0], zz - BELT_T / 2, xm, yb + X_BELT_Y[1], zz + BELT_T / 2), BLACK, "purchased", "static"))
    # fastener heads that could foul something
    for dx in (-15.5, 15.5):
        for dz in (-15.5, 15.5):  # NEMA screws from the beam side, over the beam top
            parts.append(head(f"fx_motor_m3_{dx:+.0f}{dz:+.0f}", (xm + dx, yb, pz + dz), (0, 1, 0), M3_HEAD, "static"))
    for dx, dz, y in X_MOTOR_BEAM_BOLTS:
        parts.append(head(f"fx_motor_m5_{dx:+.0f}{dz:+.0f}", (xm + dx, yb + y, Z_BEAM_TOP + dz), (0, -1, 0), M5_HEAD, "static"))
    for dx in X_IDLER_FOOT_BOLTS_X:
        parts.append(head(f"fx_idler_m5_{dx:+.0f}", (xi + dx, yb + 30, Z_BEAM_TOP + 5), (0, 0, 1), M5_HEAD, "static"))
    parts.append(head("fx_idler_tension", (xi - 28, yb + X_BELT_YC, Z_BEAM_TOP + h + 12), (-1, 0, 0), M3_HEAD, "static"))
    parts.append(head("fx_idler_axle", (xi, yb + X_BELT_YC + 12, Z_BEAM_TOP + h), (0, 1, 0), M5_HEAD, "static"))
    return parts


def bed_parts() -> list[Part]:
    parts: list[Part] = []
    for p in L.pockets():
        parts.append(Part(f"pad_{p.index}", cbox(p.x, p.y, -L.PAD_T / 2, L.POCKET_W - 1, L.POCKET_L - 1, L.PAD_T), PAD, "foam", "static", note="EVA + microfiber"))
    rod_h = L.POST_H + L.PAD_T + L.ROD_EMBED  # tops sanded to a dome = lead-in
    for i, (x, y) in enumerate(L.rods()):
        parts.append(Part(f"rod_{i:02d}", cyl((x, y, Z_BED_TOP - L.ROD_EMBED), L.ROD_D, rod_h), DOWEL, "wood", "static"))
    parts.append(Part("station", station_mount().translate((SX, SY, 0)), PETG, "printed", "static"))
    for side, x in (("L", GATE_X[0]), ("R", GATE_X[1])):
        parts.append(Part(f"gate_post_{side}", gate_post(side).translate((x, L.Y_ROW, Z_BED_TOP)), PETG, "printed", "static"))
    parts.append(Part("gate_beam", cyl((GATE_X[0], L.Y_ROW, L.GATE_Z), 1.2, GATE_X[1] - GATE_X[0], (1, 0, 0)), (1.0, 0.1, 0.1, 0.6), "purchased", "static", note="laser beam (not a part)"))
    parts.append(Part("station_camera", station_camera(SX, SY, 0.0), GREEN, "purchased", "static", note="Pi Camera Module 3"))
    parts += station_ring_parts(SX, SY, 0.0, "station")
    return parts


def station_ring_parts(x: float, y: float, z0: float, prefix: str, group: str = "static") -> list[Part]:
    """The station LED ring (LEDs up) and its leads in the seat of a camera mast whose Z = 0 is at z0."""
    face = (x, y, z0 + STATION_RING_Z + STATION_RING[2])
    return [Part(f"{prefix}_led_ring", led_ring(STATION_RING, leds_up=True).translate(face), RING, "purchased", group,
                 note=f"{STATION_RING[0]:.0f} mm COB ring, 12 V, LEDs up"),
            Part(f"{prefix}_ring_leads", ring_leads(STATION_RING, STATION_RING_LEAD_DEG, leds_up=True).translate(face), LEAD, "purchased", group,
                 note="solder pads + the leads' first mm")]


# Camera Module 3: 25 x 24 mm board, 11.5 mm from the board's back to the lens front [Likely, RPi product brief]
CM3_H = 11.5
CM3_HOLES = [(-10.5, -6.25), (10.5, -6.25), (-10.5, 6.25), (10.5, 6.25)]  # 21 x 12.5 mm, M2
CAM_FLOOR_Z = 4.0  # floor of the camera mast's hollow (station_mount and phase0_base)


def station_camera(x, y, z0) -> cq.Workplane:
    zb = z0 + L.STATION_LENS_Z - CM3_H  # board back on the standoff bosses
    return cbox(x, y, zb + 3, 25, 24, 6).union(cyl((x, y, zb + 6), 9, CM3_H - 6))


def camera_mast(z_bottom: float) -> cq.Workplane:
    """Upward camera mast + LED ring seat, shared by station_mount and phase0_base. Z = 0 is the pad top
    (machine) or the base underside (Phase 0); the lens front ends up at STATION_LENS_Z in both."""
    mast = box(-17, -17, z_bottom, 17, 17, 14.5).cut(box(-13, -13, CAM_FLOOR_Z, 13, 13, 16))
    body = mast.union(station_ring_seat())
    boss_top = L.STATION_LENS_Z - CM3_H  # 11.5: the CM3 board back rests here
    for x, y in CM3_HOLES:  # M2 standoff bosses rising from the mast floor
        # Each boss carries a 3 mm web 0.5 mm into the wall: a bare 5 mm boss at x +/-10.5 only touches the wall (x +/-13) along a
        # line, a non-manifold edge in the STL. The web lies outside the 25 mm board, so the board still rests on the boss tops.
        web = box(min(x, math.copysign(13.5, x)), y - 1.5, CAM_FLOOR_Z - 0.5, max(x, math.copysign(13.5, x)), y + 1.5, boss_top)
        body = body.union(cyl((x, y, CAM_FLOOR_Z - 0.5), 5, boss_top - CAM_FLOOR_Z + 0.5).union(web))
    body = holes_z(body, CM3_HOLES, 1.8)  # M2 self-tapping
    body = body.cut(box(-9, 12, CAM_FLOOR_Z + 0.5, 9, STATION_SEAT[0] / 2 + STATION_SEAT[1] + 1, 13.5))  # FPC exit through the mast wall AND the ring seat
    return body


def station_mount() -> cq.Workplane:
    """Upward camera mount for the station cell: base plate screwed to the bed (replaces the pad),
    camera board on four bosses, LED ring around the lens."""
    base = cbox(0, 0, -1.5, 80, 130, 3)  # replaces the pad in the station cell (same thickness)
    body = base.union(camera_mast(-3.0))
    body = holes_z(body, [(-34, -58), (34, -58), (-34, 58), (34, 58)], 4.5)  # wood screws
    return body


def gate_post(side: str) -> cq.Workplane:
    """Holds the laser module (left) or the laser-receiver module (right) at GATE_Z on the row centre line.
    It stands on the bare plywood (no pad there), so its foot is at Z = -PAD_T and the barrel hole is
    GATE_Z + PAD_T above the foot. Local origin: foot underside, on the beam axis.
    Aim: slotted foot holes give +/-9 deg of yaw, shims under the foot give pitch; then an M3 set screw
    locks the barrel and a drop of glue fixes it (BUILD_GUIDE sec. 12.5)."""
    s = -1 if side == "L" else 1  # posts stand outside the row
    hz = L.GATE_Z + L.PAD_T
    foot = cbox(s * 4, 0, 1.5, 22, 50, 3)
    for y in (-18, 18):  # yaw slots (along X)
        foot = foot.cut(box(s * 4 - 3, y - 2.25, -1, s * 4 + 3, y + 2.25, 5))
        foot = holes_z(foot, [(s * 4 - 3, y), (s * 4 + 3, y)], 4.5)
    post = cbox(s * 4, 0, hz / 2 + 6, 10, 16, hz + 12)
    bore = 7.2 if side == "L" else 6.2  # left: the 7 mm Class 2 laser (BOM); right: the 6 mm receiver module
    post = post.cut(cyl((s * 15, 0, hz), bore, 30, (-s, 0, 0)))  # laser / receiver barrel
    post = post.cut(cyl((s * 4, 0, hz), 2.5, 10, (0, 1, 0)))  # M3 set screw (tap or self-form) onto the barrel
    post = post.cut(cbox(s * 4, 0, hz + 9, 12, 2, 5))  # wire slot
    return foot.union(post)


X_MOTOR_X0 = L.X_HARD_STOP[1] + XB_HALF - X_MOTOR_X  # x_motor_mount left end (= right bumper face), local X
# Beam-front-face bolts of x_motor_mount: (local X, local Z, Y of the head seat from the beam front face)
X_MOTOR_BEAM_BOLTS = [(X_MOTOR_X0 + 7, -30.0, -19.0 + 5.5), (18.0, -30.0, -X_MOTOR_PLATE_T), (-22.0, -10.0, -X_MOTOR_PLATE_T), (18.0, -10.0, -X_MOTOR_PLATE_T)]
X_IDLER_FOOT_BOLTS_X = (-20.0, 6.0)


def x_motor_mount() -> cq.Workplane:
    """Face plate bolted to the beam's FRONT face past the rail end (4 x M5 into both front slots).
    The motor sits in front of it, shaft pointing +Y over the beam top, so a standard 24 mm shaft carries
    the pulley. Its left end is the right X end bumper. Local origin: X = motor axis, Y = beam front face,
    Z = beam top."""
    t = X_MOTOR_PLATE_T
    h = X_PULLEY_Z - Z_BEAM_TOP
    x0 = X_MOTOR_X0  # bumper face: the x_bracket edge lands here
    zb = Z_BEAM_BOT + 2 - Z_BEAM_TOP
    plate = box(x0, -t, zb, 26, 0, h + 26)
    plate = plate.cut(cyl((0, -t - 1, h), 23, t + 2, (0, 1, 0)))  # motor pilot boss
    plate = holes_y(plate, [(dx, h + dz) for dx in (-15.5, 15.5) for dz in (-15.5, 15.5)], M3_CLR)  # NEMA17, heads on the beam side
    bump = box(x0, -19, zb, x0 + 14, -t, -20)  # right X end bumper (in front of the plate, below the rail)
    body = plate.union(bump)
    body = holes_y(body, [(dx, dz) for dx, dz, _ in X_MOTOR_BEAM_BOLTS], M5_CLR)
    body = body.cut(cyl((X_MOTOR_BEAM_BOLTS[0][0], -20, X_MOTOR_BEAM_BOLTS[0][1]), 9.5, 6.5, (0, 1, 0)))  # head sunk into the bumper
    return body


def x_bumper() -> cq.Workplane:
    """Left X end bumper: one M5 into a T-nut in the beam's lower front slot, head sunk.
    Local origin: X = bumper face (the x_bracket's left edge lands on it), Y = beam front face, Z = beam centre."""
    body = box(-12, -19, -20, 0, 0, -5)
    body = holes_y(body, [(-6, -10)], M5_CLR)
    return body.cut(cyl((-6, -20, -10), 9.5, 6.5, (0, 1, 0)))


def x_idler_mount() -> cq.Workplane:
    """Fixed part on the beam top: foot (2 x M5 into the rear top slot), two cheeks with X slots for the
    M5 idler axle, and an end wall for the M3 tension screw that pulls x_idler_slider toward -X.
    Local origin: X = nominal idler axis, Y = beam front face, Z = beam top."""
    h, yc = X_PULLEY_Z - Z_BEAM_TOP, X_BELT_YC
    foot = box(-28, yc - 12, 0, 14, 40, 5)
    foot = holes_z(foot, [(x, 30) for x in X_IDLER_FOOT_BOLTS_X], M5_CLR)
    cheeks = box(-24, yc - 12, 0, 14, yc - 8.5, h + 8).union(box(-24, yc + 8.5, 0, 14, yc + 12, h + 8))
    wall = box(-28, yc - 12, 0, -24, yc + 12, h + 16)
    body = foot.union(cheeks).union(wall)
    body = slot_y(body, IDLER_SLOT[0], IDLER_SLOT[1], h, 5.3)
    body = holes_x(body, [(yc, h + 12)], M3_CLR)  # tension screw (above the idler)
    return body


def x_idler_slider() -> cq.Workplane:
    """U block that carries the toothed idler between its arms; rides on the idler mount's foot between the
    cheeks. The M3 tension screw threads into a captive nut in its bridge. Tighten the axle to lock it.
    Same local origin as x_idler_mount (shown at the nominal position)."""
    h, yc = X_PULLEY_Z - Z_BEAM_TOP, X_BELT_YC
    body = box(-16, yc - 8, 5, 12, yc + 8, h + 8)
    body = body.cut(box(-10, yc - 5, 4, 13, yc + 5, h + 9))  # idler gap (9 mm idler, 18 mm flanges); belt leaves through the open end
    body = body.union(box(-16, yc - 8, 5, -10, yc + 8, h + 16))  # bridge, tall enough for the tension screw over the idler
    body = holes_y(body, [(0, h)], 5.3)
    body = holes_x(body, [(yc, h + 12)], M3_CLR)
    body = body.cut(box(-14.3, yc - 3.0, h + 12 - 3.0, -11.7, yc + 3.0, h + 17))  # M3 nut slot from the top
    return body


# --------------------------------------------------------------------------- carriage (moves with X)

Z_SPINE_Y = (BEAM_Y0 - L.MGN12_H - L.X_BRACKET_T - 20, BEAM_Y0 - L.MGN12_H - L.X_BRACKET_T)  # (66, 86)
Z_RAIL_FACE = Z_SPINE_Y[0] - L.MGN12_RAIL_H  # 58: Z rail "top" (faces -Y)
Z_CAR_FRONT = Z_SPINE_Y[0] - L.MGN12_H  # 53: Z carriage front face
Z_CAR_SKIRT = Z_SPINE_Y[0] - L.MGN12_H1  # 63: Z carriage underside (skirts beside the rail)
SPINE_END_BORES = [(L.Z_SPINE_OFFSET_X - 10, sum(Z_SPINE_Y) / 2), (L.Z_SPINE_OFFSET_X + 10, sum(Z_SPINE_Y) / 2)]  # 2040 centre bores, tapped M5


def mgn12h(cx, rail_face, zc, along: str) -> cq.Workplane:
    """MGN12H block wrapping its rail. rail_face = Y of the rail top, block grows toward -Y.
    along = 'x' (X rail; zc = rail centre Z, cx = block centre X) or 'z' (Z rail; zc = block bottom Z)."""
    y0, y1 = rail_face - (L.MGN12_H - L.MGN12_RAIL_H), rail_face + (L.MGN12_RAIL_H - L.MGN12_H1)
    hw, rw, ln = L.MGN12H_W / 2, L.MGN12_RAIL_W / 2, L.MGN12H_L
    if along == "x":
        blk = box(cx - ln / 2, y0, zc - hw, cx + ln / 2, y1, zc + hw)
        return blk.cut(box(cx - ln, rail_face, zc - rw, cx + ln, y1 + 1, zc + rw))
    blk = box(cx - hw, y0, zc, cx + hw, y1, zc + ln)
    return blk.cut(box(cx - rw, rail_face, zc - 1, cx + rw, y1 + 1, zc + ln + 1))


def carriage_parts(cup_x: float, c: float | None = None) -> list[Part]:
    """``c``: the cup height, for the Z top switch's lever (None = lever free)."""
    yb = BEAM_Y0
    yc0 = yb - L.MGN12_H  # X carriage front face = x_bracket local Y origin
    parts: list[Part] = []
    parts.append(Part("x_carriage", mgn12h(cup_x, yb - L.MGN12_RAIL_H, L.X_RAIL_Z, "x"), STEEL, "purchased", "carriage"))
    parts.append(Part("x_bracket", x_bracket().translate((cup_x, yc0, 0)), PETG, "printed", "carriage"))
    for s, nm in ((-1, "L"), (1, "R")):
        parts.append(Part(f"belt_clamp_{nm}", belt_clamp().translate((cup_x + s * CLAMP_X, yc0, CLAMP_FLOOR_Z + BELT_T)), PETG, "printed", "carriage"))
        for y in CLAMP_SCREW_Y:
            parts.append(head(f"fc_clamp_{nm}_{y:.0f}", (cup_x + s * CLAMP_X, yc0 + y, CLAMP_FLOOR_Z + BELT_T + 3), (0, 0, 1), M3_HEAD, "carriage"))
    for x, z in XB_CAR_HOLES:  # in counterbores on the spine side
        parts.append(head(f"fc_xcar_{x:+.0f}{z:.0f}", (cup_x + x, yc0 - L.X_BRACKET_T + M3_CBORE[1], z), (0, -1, 0), M3_HEAD, "carriage"))
    for x, z in XB_SPINE_HOLES:  # T-nut bolts, heads on the carriage side, below the X carriage
        parts.append(head(f"fc_spine_{x:+.0f}{z:.0f}", (cup_x + x, yc0, z), (0, 1, 0), M5_HEAD, "carriage"))
    sy0, sy1 = Z_SPINE_Y
    sb, ztop = L.Z_SPINE_BOTTOM, L.Z_SPINE_TOP
    sx = cup_x + L.Z_SPINE_OFFSET_X
    parts.append(Part("z_spine", box(sx - 20, sy0, sb, sx + 20, sy1, ztop), ALU, "purchased", "carriage", note="2040, Z rail in its +10 slot (on the cup axis), both ends tapped M5"))
    parts.append(Part("z_rail", box(cup_x - 6, Z_RAIL_FACE, L.Z_RAIL_BOTTOM, cup_x + 6, sy0, L.Z_RAIL_BOTTOM + L.Z_RAIL_LEN), STEEL, "purchased", "carriage", note="MGN12 330 mm"))
    parts.append(Part("z_end_cap", z_end_cap().translate((cup_x, 0, sb)), PETG, "printed", "carriage", note="Z bottom hard stop"))
    parts.append(Part("z_motor_mount", z_motor_mount().translate((cup_x, 0, ztop)), PETG, "printed", "carriage"))
    mt = L.Z_MOTOR_MOUNT_T
    mx, my = cup_x + L.Z_SCREW_DX, L.Z_SCREW_Y
    parts.append(Part("z_motor", cbox(mx, my, ztop + mt + 24, NEMA, NEMA, 48), BLACK, "purchased", "carriage", note="NEMA17 + T8x8 integrated lead screw"))
    parts.append(Part("z_leadscrew", cyl((mx, my, L.Z_SCREW_TIP), 8, ztop + mt - L.Z_SCREW_TIP), STEEL, "purchased", "carriage", note=f"cut to {L.Z_SCREW_LEN:.0f} mm below the motor face"))
    for x, y in SPINE_END_BORES:
        parts.append(head(f"fc_mount_m5_{x:+.0f}", (cup_x + x, y, ztop + mt), (0, 0, 1), M5_HEAD, "carriage"))
        parts.append(head(f"fc_cap_m5_{x:+.0f}", (cup_x + x, y, sb - L.Z_END_CAP_T + 3.0), (0, 0, -1), M5_BUTTON, "carriage"))
    for dx in (-15.5, 15.5):
        for dy in (-15.5, 15.5):  # Z motor screws from below, in counterbores
            parts.append(head(f"fc_zmot_{dx:+.0f}{dy:+.0f}", (mx + dx, my + dy, ztop + M3_CBORE[1]), (0, 0, -1), M3_HEAD, "carriage"))
    parts.append(head("fc_mount_tab", (cup_x + ZMM_TAB_BOLT[0], ZMM_TAB_Y[0], ztop + ZMM_TAB_BOLT[1]), (0, -1, 0), M5_HEAD, "carriage"))
    parts += carry_sensor_parts(cup_x)
    parts += z_switch_parts(cup_x, c)
    return parts


XB_CAR_HOLES = [(dx, L.X_RAIL_Z + dz) for dx in (-10, 10) for dz in (-10, 10)]  # MGN12H 20 x 20
XB_SPINE_HOLES = [(L.Z_SPINE_OFFSET_X + dx, z) for dx in (-10, 10) for z in (L.X_RAIL_Z - 70, L.X_RAIL_Z - 45)]
CLAMP_X = 19.0  # belt clamp centres, X from the cup axis
CLAMP_SCREW_Y = (L.MGN12_H + X_BELT_Y[0] - 4, L.MGN12_H + X_BELT_Y[1] + 4)  # x_bracket local Y of the clamp screws (12, 26)


def x_bracket() -> cq.Workplane:
    """Plate in the XZ plane: X carriage (MGN12H) on its back, Z spine (2040) on its front.
    Local origin: X = cup axis, Y = X-carriage front face (plate grows toward -Y), Z = machine Z.
    The top tab reaches back over the beam to clamp both ends of the upper X-belt strand: a GT2 rack on its
    floor, a printed belt_clamp cap on top, 2 x M3 + nut per belt end. A finger off its left edge, under the beam, works the
    X home switch (x_finger())."""
    t = L.X_BRACKET_T
    zb = L.X_RAIL_Z
    zf = CLAMP_FLOOR_Z
    plate = box(-XB_HALF, -t, zb - 80, XB_HALF, 0, zf)
    plate = holes_y(plate, XB_CAR_HOLES, M3_CLR)
    for x, z in XB_CAR_HOLES:  # counterbored: the spine bolts flat over these heads
        plate = plate.cut(cyl((x, -t - 1, z), M3_CBORE[0], 1 + M3_CBORE[1], (0, 1, 0)))
    plate = holes_y(plate, XB_SPINE_HOLES, M5_CLR)  # Z spine T-nuts (both slots)
    yb0, yb1 = L.MGN12_H + X_BELT_Y[0], L.MGN12_H + X_BELT_Y[1]
    tab = box(-XB_HALF, 0, zf - 8.7, XB_HALF, CLAMP_SCREW_Y[1] + 4, zf)
    for s in (-1, 1):
        for k in range(10):  # GT2 rack, 2 mm pitch, under each belt end
            x = s * (10 + 2 * k)
            tab = tab.union(box(x - 0.5, yb0 - 0.5, zf - 0.01, x + 0.5, yb1 + 0.5, zf + 0.75))
        tab = holes_z(tab, [(s * CLAMP_X, y) for y in CLAMP_SCREW_Y], M3_CLR)
        for y in CLAMP_SCREW_Y:  # M3 nut traps on the underside
            tab = tab.cut(hexagon(s * CLAMP_X, y, zf - 8.7 - 1, 5.8, 1 + 2.6))
    return plate.union(tab).union(x_finger())


def belt_clamp() -> cq.Workplane:
    """Cap that presses one belt end onto the x_bracket's rack. Local origin: X = clamp centre,
    Y = X-carriage front face (as x_bracket), Z = belt top."""
    cap = box(-9, CLAMP_SCREW_Y[0] - 4, 0, 9, CLAMP_SCREW_Y[1] + 4, 3)
    return holes_z(cap, [(0, y) for y in CLAMP_SCREW_Y], M3_CLR)


def z_end_cap() -> cq.Workplane:
    """Bottom hard stop: plate under the spine's bottom end (2 x button-head M5 up into the 2040's tapped end
    bores, heads sunk), with two lips under the Z carriage's skirts beside the rail. The carriage lands on the
    lips at C_HARD_BOTTOM, 5 mm before it could leave the rail. Local origin: X = cup axis, Y = machine Y,
    Z = spine bottom."""
    t = L.Z_END_CAP_T
    plate = box(L.Z_SPINE_OFFSET_X - 20, Z_RAIL_FACE, -t, L.MGN12H_W / 2 + 0.5, Z_SPINE_Y[1], 0)
    for s in (-1, 1):
        x0, x1 = sorted((s * (L.MGN12_RAIL_W / 2 + 1), s * L.MGN12H_W / 2))
        plate = plate.union(box(x0, Z_RAIL_FACE, -0.01, x1, Z_CAR_SKIRT, L.Z_END_CAP_LIP))
    plate = holes_z(plate, SPINE_END_BORES, M5_CLR)
    for x, y in SPINE_END_BORES:
        plate = plate.cut(cyl((x, y, -t - 1), 10, 1 + 3.0))
    return plate


ZMM_TAB_Y = (Z_SPINE_Y[0] - 5, Z_SPINE_Y[0])  # tab on the spine's front face
ZMM_TAB_X = (L.Z_SPINE_OFFSET_X - 20, -L.MGN12H_W / 2 - 1.5)  # left of the rail AND the Z carriage
ZMM_TAB_BOLT = (L.Z_SPINE_OFFSET_X - 10, -15.0)  # left slot, 15 mm below the spine top


def z_motor_mount() -> cq.Workplane:
    """Plate on the spine's top end face (2 x M5 into the tapped end bores) that carries the Z motor in front
    of the spine, screw pointing down. A 5 mm tab down the spine's front face bolts into the LEFT slot only.
    Its underside is the top hard stop for the z_plate. Local origin: X = cup axis, Y = machine Y, Z = spine top."""
    t = L.Z_MOTOR_MOUNT_T
    mx, my = L.Z_SCREW_DX, L.Z_SCREW_Y
    plate = box(L.Z_SPINE_OFFSET_X - 20, my - NEMA / 2 - 1, 0, mx + NEMA / 2 + 2, Z_SPINE_Y[1], t)
    plate = plate.cut(cyl((mx, my, -1), 23, t + 2))
    nema = [(mx + dx, my + dy) for dx in (-15.5, 15.5) for dy in (-15.5, 15.5)]
    plate = holes_z(plate, nema, M3_CLR)
    for x, y in nema:  # heads sunk from below: the z_plate meets this face at the top stop
        plate = plate.cut(cyl((x, y, -1), M3_CBORE[0], 1 + M3_CBORE[1]))
    plate = holes_z(plate, SPINE_END_BORES, M5_CLR)
    tab = box(ZMM_TAB_X[0], ZMM_TAB_Y[0], -30, ZMM_TAB_X[1], ZMM_TAB_Y[1], 0.01)
    tab = holes_y(tab, [ZMM_TAB_BOLT], M5_CLR)
    return plate.union(tab)


# --------------------------------------------------------------------------- head (moves with Z)

FOOT_Z = (62.0, 75.0)
# The foot stops FOOT_LABEL_Y short of the cup axis on the label side (was 15): further out it is in the head camera's view
# of the face-down card window (layout.FACE_DOWN_WINDOW_MM; checks.py check_face_down_window). 9 mm still carries the 14 mm
# M10 nuts (7 mm to the flats, 8.1 to the corners) and leaves 3.8 mm of wall round the M10 hole.
FOOT_LABEL_Y = 9.0
CAM_Z = L.CAM_TO_SLAB  # lens face height above the cup face (= held slab back)
CAM_DY = L.HEAD_CAM_DY  # lens axis, Y from the cup axis (toward the label end): see layout.py
ARM_Z = (FOOT_Z[0] + 3.0, L.Z_CARRIAGE_ABOVE_CUP + 55.0)  # arm bottoms on head_foot's socket floor; top 3 mm under the z_plate top
Z_PLATE_ARM_BOLTS = (-12.0, 51.5)  # z_plate local Z: below and above the MGN12H block (0 .. 45.4)
SENSOR_POST_X = (26.5, 30.5)  # contact-sensor post on the +X side of the buffer (clear of the arm at Y >= 25)
# Head camera (ELP IMX179 board, M12 holder). [Guessing] board underside to lens front; MEASURE yours (BUILD_GUIDE 3.3).
HEAD_LENS_PROJ = 20.0
LENS_WINDOW_D = 25.0  # passes a 16 mm square M12 holder (22.6 mm diagonal)
# LED rings: 12 V COB "angel eye" rings, white (BOM). [Likely] the OD, which is the size the listings sell by. [Guessing] the ID,
# the thickness, and the solder pads + lead exit: two pads on the back face, mid-band, the leads leaving straight out of the
# back. MEASURE yours (BUILD_GUIDE 3.3). Head: 40 mm (a 60 mm ring would cut into the drop arm). Station: one "60 mm" COB
# listing measures ~63 x 47 mm [Likely, sourcing notes], so the station seat takes a 60 or a 63 mm ring.
HEAD_RING = (40.0, 30.0, 5.0)  # OD, ID, thickness
# The head seat takes any ring from HEAD_RING_OD[0] to [1]: a 42.8 mm bore, three ribs that centre the ring (printed to fit
# HEAD_RING[0] line to line, so they grip it; shave each by half of (ring OD - HEAD_RING[0]) for a bigger ring, or set HEAD_RING to
# the ring you measured and re-export; a smaller one sits loose by up to 0.25 mm: centre it by eye and glue), and a lip that holds
# the band of the smallest. checks.py runs the ring checks at both ends of the range.
HEAD_RING_OD = (39.5, 42.5)
HEAD_RING_RANGE = ((HEAD_RING_OD[0], HEAD_RING_OD[0] - 10.0, 5.0), (HEAD_RING_OD[1], HEAD_RING_OD[1] - 10.0, 5.0))  # [Guessing] ID = OD - 10
HEAD_SEAT_BORE = HEAD_RING_OD[1] + 0.3  # 42.8
HEAD_LIP_ID = 33.0  # lip under the ring's back face: 3.25 mm of a 39.5 mm ring's band, clear of the 16 mm lens holder (22.6 diagonal)
SEAT_RIB_W = 1.2  # centring rib width (tangential)
HEAD_RIB_DEG = (7.5, 127.5, 247.5)  # 60 deg either side of the lead notch, and opposite it
HEAD_NOTCH_R0 = 14.0  # the lead notch runs from here out: the pads of every ring in the range (mid-band, [Guessing]) pass it
STATION_RING = (63.0, 47.0, 5.0)  # the larger case; STATION_RING_ALT is a true 60 mm ring
STATION_RING_ALT = (60.0, 46.0, 5.0)  # [Guessing] ID and thickness
RING_PAD = (7.0, 3.0, 1.5)  # solder pads + joints on the back face: along the ring, across the band, height
RING_LEAD = (3.2, 2.0, 6.0)  # the two leads leaving the back face over the pads: width (side by side), depth, length modelled
HEAD_RING_FACE_DZ = -1.0  # head ring's LED face, from the lens front: just under it, so no part of the ring is in the lens's
# view, and the barb elbow at the full 20 mm stroke stays well under the ring (with the face 4 mm under the lens it was 0.75 mm)
HEAD_RING_LEAD_DEG = 67.5  # head ring lead exit, deg from +X toward +Y about the lens axis: between the 45-deg board nut and the +Y leg
STATION_RING_Z = 20.0  # station ring's back face (it lies LEDs up on the seat's shelf), above the pad top
STATION_RING_LEAD_DEG = 90.0  # toward +Y: the leads drop through the shelf into the camera ribbon's slot and leave with it
STATION_SEAT = (64.0, 3.0, 6.0, 44.0)  # station ring seat: bore, wall, bore depth above the shelf, shelf inner dia

# Cup + spring buffer: SMC ZPT25UUK20-B5-A10 (25 mm flat urethane pad, non-rotating buffer, 20 mm stroke, M5 female vacuum
# port on top, M10x1 body). [Certain, SMC ZP catalog p.13-11-12, ø20/ø25 at 20 mm stroke] the M10x1 body is G = 51 long and
# starts E = 44.5 above the pad face; the port top is F = 108.5 above the pad face, on an 8 mm hex 5 mm tall; the pad is
# øA 25 (lip) / øB 28 (outside), its own 8 mm hex ends D = 23 above the face; the nuts are 14 mm across flats.
# [Likely, read off the same drawing] the 13 mm above the body is an ~8 mm neck (Ø~8) plus the 5 mm hex, both rising with
# the rod and resting on the body top when the cup is free; the nuts are 3 mm thick. [Guessing] hollow rod Ø6, pad hub Ø14.
# Heights are above c with the buffer AT REST (fully extended); the moving parts (pad, rod, neck + hex, flag, fitting) rise by
# the buffer travel t. The model's standard pose is t = CUP_HANG, the probe trip, which puts the pad face at c (a free cup
# hangs CUP_HANG lower). The buffer's place on its thread puts the foot's underside 64 mm above the free pad face.
BUF_E, BUF_G, BUF_F = 44.5, 51.0, 108.5  # pad face to the body bottom, body length, pad face to the port top
PAD_B, PAD_Y, PAD_HUB, PAD_C, PAD_D = 28.0, 4.0, 14.0, 14.0, 23.0  # pad outside dia, skirt height, hub dia, hub top, pad hex top
HEX8 = 8.0 / 0.8660254  # 8 mm hex across corners (envelopes are round)
BUFFER_NUT = (14.0 / 0.8660254, 3.0)  # M10x1 nut on each face of the foot: across corners, thickness
BUFFER_ROD_D = 6.0
BUF_NECK = (8.0, 8.0)  # neck between the body top and the port hex: dia, height
PAD_REST = -L.CUP_HANG  # free pad face, above c
BODY_Z = (PAD_REST + BUF_E, PAD_REST + BUF_E + BUF_G)  # (42.5, 93.5): the fixed M10 body
PORT_TOP = PAD_REST + BUF_F  # 106.5: top of the M5 port hex at rest; the flag tab sits on it, under the fitting
# Vacuum fitting: SMC M-5ALU-4 barb elbow (M5, 7 mm hex, for 4 x 2.5 urethane tube), tube toward +Y (away from the label).
# [Likely, SMC part page: A 13.3, B 9.3, hex 7] 9.3 mm above the port face on a 4 mm M5 thread (A - B = 4 for every size).
# [Guessing] the barb arm's height and reach. A push-in elbow is too tall here: SMC KQ2L04-M5A stands 15.9 mm above its seat
# [Certain, SMC KQ2 catalog], so at full stroke it would reach 3.4 mm past the head lens front.
VAC_FITTING = (7.0 / 0.8660254, 9.3)  # body envelope: dia (7 mm hex across corners), height above the flag tab
VAC_BARB = (4.5, 12.0, 5.5)  # barb arm + tube end envelope: dia, reach along +Y from the axis, axis height above the tab
VAC_THREAD = 4.0  # M5 thread length: 3 mm (3.75 turns) engaged through the 1 mm flag tab

# Contact probe: a TCST2103 slotted optical sensor on its endstop board, on the post's -X face. Optical axis along Y;
# the slot is open toward the buffer AND along Z, so the flag (a flat plate in the slot's mid-plane) passes straight
# THROUGH it over the whole stroke and never bottoms. [Certain, Vishay doc 81147, drawing 6.550-5040.01-4] 24.5 x 6.3 x
# 10.8 mm with mounting flanges, 3.1 mm gap, flange holes 19 mm apart and symmetric about the slot, slot bottom and flange
# top 3.1 mm above the base (slot 7.7 deep), optical axis 2.6 mm below the arm tips, aperture a 1 mm slit running 3.8 mm
# down from the tips. [Likely] the endstop board's two holes are the flange holes. [Guessing] the board outline and the
# 3-pin header at its +Y end.
PROBE_Y = 7.5  # slot (= flag) mid-plane, Y from the cup axis: clears the port hex and the body, and stays on the far side from the label
PROBE_BEAM_Z = 99.0  # beam centre above c; the flag's top edge crosses it after CUP_HANG of buffer travel
PROBE_ADJ = 4.0  # vertical slots for the board's M3 screws: +/- this much trip adjustment (covers BUFFER_SHIFT + PROBE_TRIP_TOL)
PROBE_PCB = (33.0, 10.5, 1.6)  # endstop board: along the hole line (Y), across (Z), thickness (X)
PROBE_HOLES = 19.0
# Board screws: M3x16 with a washer under the head and under the nut (BUILD_GUIDE 7.6: solder joints under the board stand it
# off the post, and an M3x12 then leaves no thread in the nut). The tip runs on 3.9 mm past the nut.
PROBE_SCREW_L = 16.0
M3_WASHER = (7.0, 0.5)  # ISO 7089 M3: OD, thickness
TCST_GAP, TCST_AP, TCST_AP_DEPTH = 3.1, 1.0, 3.8  # slot width (Y); aperture slit width along the flag travel (Z), depth from the arm tips (X)
TCST_H, TCST_W, TCST_L, TCST_U = 10.8, 6.3, 24.5, 11.9  # height (X), width (Z), flange length (Y), U-body length (Y)
TCST_FLANGE_T, TCST_SLOT_DEPTH, TCST_AXIS = 3.1, 7.7, 2.6  # flange thickness; slot depth and optical axis from the arm tips
TCST_BASE_X = SENSOR_POST_X[0] - PROBE_PCB[2]  # 24.9: sensor base on the board
TCST_TIP_X = TCST_BASE_X - TCST_H  # 14.1: arm tips (slot mouth)
TCST_SLOT_X = TCST_TIP_X + TCST_SLOT_DEPTH  # 21.8: slot bottom
TCST_AXIS_X = TCST_TIP_X + TCST_AXIS  # 16.7: optical axis
SENSOR_POST_TOP = PROBE_BEAM_Z + PROBE_ADJ + 4.5

# Probe flag: 1 mm aluminium sheet, one 90-deg bend (BUILD_GUIDE 7.6 and cad/out/probe_flag_blank.svg).
FLAG_T, FLAG_BEND_R = 1.0, 1.0  # sheet thickness, inside bend radius
FLAG_X = (12.0, TCST_TIP_X + TCST_AP_DEPTH + 1.5)  # blade inner / outer edge: covers the aperture slit with 2.1 / 1.5 mm to spare
FLAG_TAB_X = 5.0  # neck and tab half width
FLAG_HOLE = 5.2  # tab hole: clears the M5 fitting thread
FLAG_BEND_Z = PORT_TOP - FLAG_BEND_R  # 105.5: top of the plate's flat part (= the bend line), at rest
FLAG_TOP = PROBE_BEAM_Z - L.CUP_HANG  # 97: blade top edge at rest
FLAG_BAND_Z = FLAG_TOP - 6.0  # bottom of the band that joins the neck to the blade; its top edge is the blade's
FLAG_TAB_END = -(FLAG_HOLE / 2 + 2.0)  # tab end, Y: 2 mm of metal past the hole
# Anti-rotation guide in head_foot: two fins with a slot between them, continued through the foot. The blade rides in
# it over the whole stroke, so even a rotating (J) buffer cannot swing the flag into the sensor.
GUIDE_GAP, GUIDE_WALL = FLAG_T + 2 * 0.45, 2.5  # 1.9 mm slot: 0.45 mm each side of the flag
GUIDE_TOP = PROBE_BEAM_Z - TCST_W / 2 - PROBE_ADJ - 0.6  # fins stop under the sensor even with the board slid to its lowest
BUFFER_SHIFT = 3.0  # BUILD_GUIDE 7.5 may move the buffer this far either way on its thread (lens height); checks.py sweeps it
FLAG_ENGAGE = 8.0  # the blade stays this deep in the guide at full stroke (5 mm with the buffer BUFFER_SHIFT higher)
FLAG_BOTTOM = GUIDE_TOP - L.BUFFER_STROKE - FLAG_ENGAGE  # 63.25: blade bottom at rest, inside the foot's slot


def occluder_parts(cup_x: float, cup_y: float, c: float, compression: float = L.CUP_HANG, prefix: str = "", group: str = "head") -> list[Part]:
    """The parts between the head camera and the held slab: head_foot, buffer, cup, probe flag and sensor.
    head_parts() puts them on the machine; phase0_parts() hangs the same set under the Phase 0A camera.
    ``compression`` = buffer travel t (0 = free cup); the moving parts sit t above their rest heights."""
    m = c + compression  # rest heights of the moving parts are given above c
    x, y = cup_x, cup_y
    pad = cyl((x, y, m + PAD_REST), PAD_B, PAD_Y).union(cyl((x, y, m + PAD_REST + PAD_Y), PAD_HUB, PAD_C - PAD_Y))
    pad = pad.union(cyl((x, y, m + PAD_REST + PAD_C), HEX8, PAD_D - PAD_C))
    stop = cyl((x, y, m + BODY_Z[1]), BUF_NECK[0], BUF_NECK[1]).union(cyl((x, y, m + BODY_Z[1] + BUF_NECK[1]), HEX8, PORT_TOP - BODY_Z[1] - BUF_NECK[1]))
    parts = [
        Part(prefix + "head_foot", head_foot(L.ARM_TO_CUP).translate((x, y, c)), PETG, "printed", group),
        Part(prefix + "buffer", cyl((x, y, c + BODY_Z[0]), 10.0, BUF_G)
             .union(cyl((x, y, c + FOOT_Z[0] - BUFFER_NUT[1]), BUFFER_NUT[0], BUFFER_NUT[1]))
             .union(cyl((x, y, c + FOOT_Z[1]), BUFFER_NUT[0], BUFFER_NUT[1])),
             STEEL, "purchased", group, note="M10x1 x 51 buffer body + 2 nuts, 20 mm stroke"),
        Part(prefix + "cup", pad, BLACK, "purchased", group, note="25 mm flat urethane pad on its 8 mm hex adapter"),
        Part(prefix + "buffer_rod", cyl((x, y, m + PAD_REST + PAD_D), BUFFER_ROD_D, BODY_Z[1] - PAD_REST - PAD_D), STEEL, "purchased", group,
             note="hollow rod, slides up through the body on contact"),
        Part(prefix + "buffer_stop", stop, STEEL, "purchased", group, note="neck + 8 mm hex with the M5 port; rests on the body top when free"),
        Part(prefix + "probe_flag", probe_flag().translate((x, y, m)), ALU, "made", group, note="1 mm aluminium, cut + bent"),
        Part(prefix + "vac_fitting", vac_fitting().translate((x, y, m + PORT_TOP + FLAG_T)), BLACK, "purchased", group, note="M5 barb elbow, 4 mm tube toward +Y"),
        Part(prefix + "contact_sensor", probe_sensor().translate((x, y, c)), BLACK, "purchased", group, note="TCST2103 optical endstop, slot along Z"),
    ]
    for yy in (PROBE_Y - PROBE_HOLES / 2, PROBE_Y + PROBE_HOLES / 2):  # M3x16 + washers through the sensor flange, board and post slot
        hx = x + TCST_BASE_X - TCST_FLANGE_T  # flange top: the head's washer sits here
        head_w = cyl((hx, y + yy, c + PROBE_BEAM_Z), M3_WASHER[0], M3_WASHER[1], (-1, 0, 0))
        head_w = head_w.union(cyl((hx - M3_WASHER[1], y + yy, c + PROBE_BEAM_Z), M3_HEAD[0], M3_HEAD[1], (-1, 0, 0)))
        parts.append(Part(prefix + f"probe_m3_{yy:+.0f}", head_w, STEEL, "fastener", group))
        nx = x + SENSOR_POST_X[1]  # post's +X face: washer, nut, then the screw tip
        tip = hx - M3_WASHER[1] + PROBE_SCREW_L
        nut = cyl((nx, y + yy, c + PROBE_BEAM_Z), M3_WASHER[0], M3_WASHER[1], (1, 0, 0))
        nut = nut.union(cyl((nx + M3_WASHER[1], y + yy, c + PROBE_BEAM_Z), 6.4, 2.4, (1, 0, 0)))
        nut = nut.union(cyl((nx + M3_WASHER[1] + 2.0, y + yy, c + PROBE_BEAM_Z), 3.0, tip - nx - M3_WASHER[1] - 2.0, (1, 0, 0)))
        parts.append(Part(prefix + f"probe_nut_{yy:+.0f}", nut, STEEL, "fastener", group, note=f"washer + nut + the M3x{PROBE_SCREW_L:.0f} tip"))
    return parts


def occluder_boxes(compression: float = 0.0) -> list[tuple[str, tuple[float, float, float, float, float, float], int]]:
    """The head as the head camera sees it, for the simulator (software/slabscan/sim.py HEADS): (name, (x0, y0, x1, y1, z0, z1),
    grey) boxes, mm from the CUP axis (X along the row, Y along the slab, label end negative), z above the cup height c. The
    lens front is at z = CAM_Z, CAM_DY from the cup axis. Each box bounds one simple solid of a CAD part; only what lies below
    the lens (the drop arm is cut there; the LED-ring seat around the lens is outside the field of view). ``compression`` =
    buffer travel (0 = free cup: the hover frame and a held slab). Greys are guesses for the sim (matte black PETG ~52)."""
    t = compression
    out: list = []

    def cylb(name, d, z0, z1, g, x=0.0, y=0.0):
        out.append((name, (x - d / 2, y - d / 2, x + d / 2, y + d / 2, z0, z1), g))

    cylb("cup pad", PAD_B, t + PAD_REST, t + PAD_REST + PAD_Y, 25)
    cylb("cup hub", PAD_HUB, t + PAD_REST + PAD_Y, t + PAD_REST + PAD_C, 30)
    cylb("cup hex", HEX8, t + PAD_REST + PAD_C, t + PAD_REST + PAD_D, 120)
    cylb("buffer rod", BUFFER_ROD_D, t + PAD_REST + PAD_D, BODY_Z[0], 170)
    cylb("buffer nut (under the foot)", BUFFER_NUT[0], FOOT_Z[0] - BUFFER_NUT[1], FOOT_Z[0], 150)
    cylb("buffer body", 10.0, BODY_Z[0], BODY_Z[1], 120)
    z0, z1 = FOOT_Z
    py0, py1 = PROBE_Y - 17.0, PROBE_Y + 17.0
    out.append(("head_foot plate", (-15.0, -FOOT_LABEL_Y, 15.0, L.ARM_TO_CUP + 10, z0, z1), 52))
    out.append(("head_foot extension", (15.0, py0, SENSOR_POST_X[1], py1, z0, z1), 52))
    out.append(("head_foot arm sleeve", (-12.0, L.ARM_TO_CUP - 12, 12.0, L.ARM_TO_CUP + 12, z0, z1 + 18), 52))
    cylb("buffer nut (on the foot)", BUFFER_NUT[0], FOOT_Z[1], FOOT_Z[1] + BUFFER_NUT[1], 150)
    out.append(("sensor post", (SENSOR_POST_X[0], py0, SENSOR_POST_X[1], py1, z1, SENSOR_POST_TOP), 52))
    gx0, gx1 = FLAG_X[0] - 1.0, TCST_BASE_X - 0.5
    out.append(("flag guide fins", (gx0, PROBE_Y - GUIDE_GAP / 2 - GUIDE_WALL, gx1, PROBE_Y + GUIDE_GAP / 2 + GUIDE_WALL, z1, GUIDE_TOP), 52))
    pl, pw, _ = PROBE_PCB
    out.append(("endstop board + TCST2103", (TCST_TIP_X, PROBE_Y - pl / 2, SENSOR_POST_X[0], PROBE_Y + pl / 2, PROBE_BEAM_Z - pw / 2, PROBE_BEAM_Z + pw / 2), 32))
    out.append(("flag blade", (FLAG_X[0], PROBE_Y - FLAG_T / 2, FLAG_X[1], PROBE_Y + FLAG_T / 2, t + FLAG_BOTTOM, t + FLAG_TOP), 180))
    out.append(("flag neck + band", (-FLAG_TAB_X, PROBE_Y - FLAG_T / 2 - FLAG_BEND_R, FLAG_X[1], PROBE_Y + FLAG_T / 2, t + FLAG_BAND_Z, t + FLAG_BEND_Z + FLAG_BEND_R + FLAG_T), 180))
    cylb("buffer neck", BUF_NECK[0], t + BODY_Z[1], t + BODY_Z[1] + BUF_NECK[1], 140)
    cylb("port hex", HEX8, t + BODY_Z[1] + BUF_NECK[1], t + PORT_TOP, 140)
    out.append(("flag tab", (-FLAG_TAB_X, FLAG_TAB_END, FLAG_TAB_X, PROBE_Y - FLAG_T / 2, t + PORT_TOP, t + PORT_TOP + FLAG_T), 180))
    d, h = VAC_FITTING
    ad, reach, az = VAC_BARB
    cylb("vacuum elbow", d, t + PORT_TOP + FLAG_T, t + PORT_TOP + FLAG_T + h, 140)
    out.append(("elbow barb + tube end (toward +Y)", (-ad / 2, 0.0, ad / 2, reach, t + PORT_TOP + FLAG_T + az - ad / 2, t + PORT_TOP + FLAG_T + az + ad / 2), 140))
    arm_y1 = Z_CAR_FRONT - L.Z_PLATE_T
    out.append(("drop arm (cut at the lens)", (-10.0, arm_y1 - 20, 10.0, arm_y1, ARM_Z[0], CAM_Z), 60))
    return [(n, tuple(round(v, 2) for v in b), g) for n, b, g in out]


def head_ring_parts(x: float, y: float, lens_z: float, prefix: str, group: str = "head", ring=HEAD_RING) -> list[Part]:
    """The head LED ring (LEDs down) and its leads in their seat, for a lens front at (x, y, lens_z)."""
    face = (x, y, lens_z + HEAD_RING_FACE_DZ)
    return [Part(f"{prefix}head_led_ring", led_ring(ring).translate(face), RING, "purchased", group, note=f"{ring[0]:.1f} mm COB ring, 12 V, LEDs down"),
            Part(f"{prefix}head_ring_leads", ring_leads(ring).translate(face), LEAD, "purchased", group, note="solder pads + the leads' first mm")]


def vac_fitting() -> cq.Workplane:
    """M5 barb elbow envelope, local origin = its seat on the flag tab, on the cup axis: body, plus the barb arm (and the
    first few mm of tube on it) toward +Y."""
    d, h = VAC_FITTING
    ad, reach, az = VAC_BARB
    return cyl((0, 0, 0), d, h).union(cyl((0, 0, az), ad, reach, (0, 1, 0)))


def head_parts(cup_x: float, c: float, compression: float = L.CUP_HANG, ring=HEAD_RING) -> list[Part]:
    """``ring``: the head LED ring fitted (OD, ID, thickness); the seat's ribs are shaved to it."""
    cup_y = L.Y_ROW
    parts: list[Part] = []
    zc_bottom = c + L.Z_CARRIAGE_ABOVE_CUP
    parts.append(Part("z_carriage", mgn12h(cup_x, Z_RAIL_FACE, zc_bottom, "z"), STEEL, "purchased", "head"))
    parts.append(Part("z_plate", z_plate().translate((cup_x, Z_CAR_FRONT, zc_bottom)), PETG, "printed", "head"))
    arm_y1 = Z_CAR_FRONT - L.Z_PLATE_T
    parts.append(Part("drop_arm", box(cup_x - 10, arm_y1 - 20, c + ARM_Z[0], cup_x + 10, arm_y1, c + ARM_Z[1]), ALU, "purchased", "head", note="2020"))
    off = arm_y1 - 10 - cup_y  # = ARM_TO_CUP
    parts.append(Part("camera_bracket", camera_bracket(off, rib_d=max(ring[0], HEAD_RING[0])).translate((cup_x, cup_y, c)), PETG, "printed", "head"))
    parts += occluder_parts(cup_x, cup_y, c, compression)
    zl, zs, ly = c + CAM_Z, c + CAM_Z + HEAD_LENS_PROJ, cup_y + CAM_DY
    cam = cbox(cup_x, ly, zs + 5, 38, 38, 10).union(cbox(cup_x, ly, (zl + 6 + zs) / 2, 16, 16, zs - zl - 6)).union(cyl((cup_x, ly, zl), 14, 6))
    parts.append(Part("head_camera", cam, GREEN, "purchased", "head", note=f"USB 8MP IMX179, M12 3.6 mm; lens {-CAM_DY:.0f} mm toward the label from the cup axis"))
    parts += head_ring_parts(cup_x, ly, zl, "", ring=ring)
    parts += carry_flag_parts(cup_x, c)
    for dx in (-10, 10):
        for dz in (-10, 10):  # MGN12H screws in counterbores on the arm side
            parts.append(head(f"fh_zcar_{dx:+d}{dz:+d}", (cup_x + dx, Z_CAR_FRONT - L.Z_PLATE_T + M3_CBORE[1], zc_bottom + 22.7 + dz), (0, -1, 0), M3_HEAD, "head"))
    for z in Z_PLATE_ARM_BOLTS:  # button heads in 2.5 mm recesses on the carriage side
        parts.append(head(f"fh_arm_{z:+.0f}", (cup_x, Z_CAR_FRONT - 2.5, zc_bottom + z), (0, 1, 0), M5_BUTTON, "head"))
    return parts


def z_plate() -> cq.Workplane:
    """Printed Z carriage plate. Local origin: X = cup axis, Y = Z-carriage front face, Z = carriage bottom.
    Its top edge (Z_PLATE_TOP) is the top hard stop against z_motor_mount. Its back face at the right end, with a 45-deg chamfer
    along the top edge there (ZP_CHAMFER_X, ZP_CHAMFER deep), works the Z top switch."""
    t = L.Z_PLATE_T
    plate = box(-30, -t, -5, ZP_X1, 0, L.Z_PLATE_TOP)
    ch, zt = ZP_CHAMFER, L.Z_PLATE_TOP
    wedge = cq.Workplane("YZ").polyline([(0.01, zt - ch), (0.01, zt + 0.01), (-ch, zt + 0.01)]).close().extrude(ZP_X1 + 1 - ZP_CHAMFER_X)
    plate = plate.cut(wedge.translate((ZP_CHAMFER_X, 0, 0)))
    plate = plate.union(box(-14, -t, -20, 14, 0, -4.99))  # extension below the carriage for the lower arm bolt
    car = [(dx, 22.7 + dz) for dx in (-10, 10) for dz in (-10, 10)]  # MGN12H
    plate = holes_y(plate, car, M3_CLR)
    for x, z in car:  # counterbored: the drop arm covers X +/-10
        plate = plate.cut(cyl((x, -t - 1, z), M3_CBORE[0], 1 + M3_CBORE[1], (0, 1, 0)))
    plate = holes_y(plate, [(0, z) for z in Z_PLATE_ARM_BOLTS], M5_CLR)  # drop arm T-nuts, outside the MGN12H block
    plate = holes_y(plate, CA_EAR_SCREWS, 2.5)  # carry_flag_arm: M3x10 self-tapping pilots
    for z in Z_PLATE_ARM_BOLTS:  # button-head recesses: only 5 mm between the plate back and the Z rail face
        plate = plate.cut(cyl((0, -2.5, z), 10.0, 3.5, (0, 1, 0)))
    sx, sy = L.Z_SCREW_DX, L.Z_SCREW_Y - Z_CAR_FRONT  # lead screw axis in local coords (24, -20)
    r = L.T8_FLANGE_D / 2 + 2
    shelf = box(sx - r, sy - r, 40, sx + r, -t + 0.01, 48)  # carries the whole 22 mm T8 flange
    shelf = shelf.cut(cyl((sx, sy, 30), 10.5, 30))
    k = 8.0 / 2**0.5  # flange holes, 16 mm circle, at 45 deg (nuts below stay clear of the plate)
    shelf = holes_z(shelf, [(sx + a * k, sy + b * k) for a in (-1, 1) for b in (-1, 1)], M3_CLR, z0=30, h=30)
    return plate.union(shelf)


def head_foot(arm_offset: float) -> cq.Workplane:
    """Holds the spring buffer (M10) on the cup axis and the contact probe; bolts to the drop-arm end.
    +X side: the sensor post (endstop board on its -X face, M3 + nuts in vertical slots for +/- PROBE_ADJ of trip
    adjustment) and the flag guide: two fins on the foot top with a GUIDE_GAP slot between them, continued as a slot
    through the foot, in which the flag's blade rides over the whole stroke. The arm socket stays clear (Y >= 25).
    On the label side nothing reaches past Y = -FOOT_LABEL_Y: the head camera looks past it at the card window."""
    z0, z1 = FOOT_Z
    py0, py1 = PROBE_Y - 17.0, PROBE_Y + 17.0  # post covers the 33 mm board
    body = box(-15, -FOOT_LABEL_Y, z0, 15, arm_offset + 10, z1)
    body = body.union(box(-12, arm_offset - 12, z0, 12, arm_offset + 12, z1 + 18))  # sleeve around the arm end
    body = body.union(box(15, py0, z0, SENSOR_POST_X[1], py1, z1))  # foot extension to the sensor post
    body = body.union(box(SENSOR_POST_X[0], py0, z1 - 0.01, SENSOR_POST_X[1], py1, SENSOR_POST_TOP))  # sensor post
    gx0, gx1 = FLAG_X[0] - 1.0, TCST_BASE_X - 0.5  # fins stop short of the board, which slides past their ends
    for y in (PROBE_Y - GUIDE_GAP / 2 - GUIDE_WALL, PROBE_Y + GUIDE_GAP / 2):
        body = body.union(box(gx0, y, z1 - 0.01, gx1, y + GUIDE_WALL, GUIDE_TOP))  # flag guide fins
    # cuts last, so no later union refills them
    for y in (PROBE_Y - PROBE_HOLES / 2, PROBE_Y + PROBE_HOLES / 2):  # board screw slots, M3 clearance
        body = body.cut(box(SENSOR_POST_X[0] - 1, y - M3_CLR / 2, PROBE_BEAM_Z - PROBE_ADJ, SENSOR_POST_X[1] + 1, y + M3_CLR / 2, PROBE_BEAM_Z + PROBE_ADJ))
        body = holes_x(body, [(y, PROBE_BEAM_Z - PROBE_ADJ), (y, PROBE_BEAM_Z + PROBE_ADJ)], M3_CLR, x0=SENSOR_POST_X[0] - 1, h=6)
    body = body.cut(box(gx0, PROBE_Y - GUIDE_GAP / 2, z0 - 1, FLAG_X[1] + 1.0, PROBE_Y + GUIDE_GAP / 2, z1 + 1))  # flag slot through the foot
    body = body.cut(box(-10.2, arm_offset - 10.2, z0 + 3, 10.2, arm_offset + 10.2, z1 + 20))  # arm socket
    body = body.cut(cyl((0, 0, z0 - 1), 10.4, z1 - z0 + 2))  # M10 buffer thread, nuts both sides
    body = holes_x(body, [(arm_offset, z1 + 9)], M5_CLR)
    return body


def probe_flag() -> cq.Workplane:
    """Probe flag at rest, head-local (cup axis, Z above c). A flat plate in the sensor slot's mid-plane (Y = PROBE_Y)
    plus a tab bent 90 deg toward the cup axis, clamped between the buffer's port hex and the M5 vacuum fitting.
    The blade's top edge enters the beam after CUP_HANG of buffer travel and the blade stays in it to full stroke;
    its lower part rides in head_foot's guide. Flat blank and drill dimensions: flag_blank() / build.export_flag_drawing()."""
    y0, y1 = PROBE_Y - FLAG_T / 2, PROBE_Y + FLAG_T / 2
    tx, b, ri, ro = FLAG_TAB_X, FLAG_BEND_Z, FLAG_BEND_R, FLAG_BEND_R + FLAG_T
    plate = box(-tx, y0, FLAG_BAND_Z, tx, y1, b)  # neck under the bend
    plate = plate.union(box(-tx, y0, FLAG_BAND_Z, FLAG_X[1], y1, FLAG_TOP))  # band from the neck to the blade
    plate = plate.union(box(FLAG_X[0], y0, FLAG_BOTTOM, FLAG_X[1], y1, FLAG_TOP))  # blade
    yc = y0 - ri  # bend axis (along X)
    bend = cyl((-tx, yc, b), 2 * ro, 2 * tx, (1, 0, 0)).cut(cyl((-tx - 1, yc, b), 2 * ri, 2 * tx + 2, (1, 0, 0)))
    bend = bend.intersect(box(-tx, yc, b, tx, yc + ro, b + ro))
    tab = box(-tx, FLAG_TAB_END, b + ri, tx, yc, b + ro).cut(cyl((0, 0, b), FLAG_HOLE, 5))
    return plate.union(bend).union(tab)


def flag_blank() -> list[tuple[float, float]]:
    """Flat blank outline of the probe flag, before bending: (u, v) mm, u = along the plate from the neck centre line
    (= the hole centre) toward the sensor, v = up from the bend line. The tab is left long (trim after bending)."""
    tx, top, bot, band = FLAG_TAB_X, FLAG_TOP - FLAG_BEND_Z, FLAG_BOTTOM - FLAG_BEND_Z, FLAG_BAND_Z - FLAG_BEND_Z
    tab = 13.0
    return [(-tx, band), (FLAG_X[0], band), (FLAG_X[0], bot), (FLAG_X[1], bot), (FLAG_X[1], top), (tx, top), (tx, tab), (-tx, tab)]


def probe_sensor() -> cq.Workplane:
    """Optical endstop board + TCST2103, head-local, as mounted on the post (board at the middle of its slots).
    Optical axis along Y; the slot runs through along Z and opens toward the cup axis (-X)."""
    y, z, xb, xt = PROBE_Y, PROBE_BEAM_Z, TCST_BASE_X, TCST_TIP_X
    pl, pw, pt = PROBE_PCB
    pcb = box(xb, y - pl / 2, z - pw / 2, xb + pt, y + pl / 2, z + pw / 2)
    flange = box(xb - TCST_FLANGE_T, y - TCST_L / 2, z - TCST_W / 2, xb, y + TCST_L / 2, z + TCST_W / 2)
    ubody = box(xt, y - TCST_U / 2, z - TCST_W / 2, xb, y + TCST_U / 2, z + TCST_W / 2)
    ubody = ubody.cut(box(xt - 1, y - TCST_GAP / 2, z - TCST_W, TCST_SLOT_X, y + TCST_GAP / 2, z + TCST_W))
    header = box(xb - 8.0, y + TCST_L / 2 + 0.5, z - 4.0, xb, y + pl / 2, z + 4.0)  # [Guessing] 3-pin header
    body = pcb.union(flange).union(ubody).union(header)
    return holes_x(body, [(y - PROBE_HOLES / 2, z), (y + PROBE_HOLES / 2, z)], 3.2, x0=xb - TCST_FLANGE_T - 1, h=TCST_FLANGE_T + pt + 2)


def probe_aperture() -> cq.Workplane:
    """The light path the flag has to block, head-local: the aperture slit (TCST_AP along Z, TCST_AP_DEPTH down from the
    arm tips along X) across the gap."""
    return box(TCST_TIP_X, PROBE_Y - TCST_GAP / 2, PROBE_BEAM_Z - TCST_AP / 2, TCST_TIP_X + TCST_AP_DEPTH, PROBE_Y + TCST_GAP / 2, PROBE_BEAM_Z + TCST_AP / 2)


def _at_angle(shape: cq.Workplane, deg: float) -> cq.Workplane:
    return shape.rotate((0, 0, 0), (0, 0, 1), deg)


def led_ring(ring=HEAD_RING, leds_up: bool = False) -> cq.Workplane:
    """COB LED ring envelope, local origin = its axis at the LED face; the body lies behind the face (+Z for a ring whose
    LEDs face down, -Z facing up)."""
    od, id_, t = ring
    body = cyl((0, 0, 0), od, t).cut(cyl((0, 0, -1), id_, t + 2))
    return body.translate((0, 0, -t)) if leds_up else body


def ring_leads(ring=HEAD_RING, deg: float = HEAD_RING_LEAD_DEG, leds_up: bool = False) -> cq.Workplane:
    """The ring's solder pads (with their joints) on its back face, mid-band at `deg`, and the first RING_LEAD[2] mm of the two
    leads leaving straight out of the back; same local origin as led_ring(). The rest of the leads is routed, not modelled."""
    od, id_, t = ring
    rm = (od + id_) / 4
    pl, pw, ph = RING_PAD
    lw, ld, ll = RING_LEAD
    s = box(rm - pw / 2, -pl / 2, t, rm + pw / 2, pl / 2, t + ph).union(box(rm - ld / 2, -lw / 2, t + ph - 0.01, rm + ld / 2, lw / 2, t + ph + ll))
    s = _at_angle(s, deg)
    return s.mirror("XY") if leds_up else s


def _seat_ribs(face_z: float, back: float, rib_d: float) -> cq.Workplane:
    """The three centring ribs of the head ring seat, from the bore wall in to rib_d, face_z - 1 up to the lip (back)."""
    rib = box(rib_d / 2, -SEAT_RIB_W / 2, face_z - 1.0, HEAD_SEAT_BORE / 2 + 0.5, SEAT_RIB_W / 2, back + 0.01)
    out = _at_angle(rib, HEAD_RIB_DEG[0])
    for d in HEAD_RIB_DEG[1:]:
        out = out.union(_at_angle(rib, d))
    return out


def ring_seat(face_z: float, z_top: float, deg: float = HEAD_RING_LEAD_DEG, rib_d: float = HEAD_RING[0]) -> cq.Workplane:
    """LED-ring seat round a downward lens: a 3 mm tube whose HEAD_SEAT_BORE takes any ring of HEAD_RING_OD, three ribs (to rib_d)
    that centre it, and an inner lip (HEAD_LIP_ID) the ring is pushed up against (LEDs down, LED face at face_z, three dots of glue
    keep it there). A notch in the lip at `deg` lets the solder pads and the leads out of the back. Hung from z_top on four legs at
    0/90/180/270 deg, so the board's 45-deg screw nuts stay clear."""
    t = HEAD_RING[2]
    rid = HEAD_SEAT_BORE
    back = face_z + t  # the ring's back face = the lip's underside
    tube = cyl((0, 0, face_z - 1.0), rid + 6, t + 3.0).cut(cyl((0, 0, face_z - 2.0), rid, t + 5.0))
    tube = tube.union(cyl((0, 0, back), rid + 0.5, 2).cut(cyl((0, 0, back - 1), HEAD_LIP_ID, 4)))
    tube = tube.union(_seat_ribs(face_z, back, rib_d))
    tube = tube.cut(_at_angle(box(HEAD_NOTCH_R0, -RING_PAD[0] / 2 - 0.5, back - 0.01, rid / 2 + 0.3, RING_PAD[0] / 2 + 0.5, back + 2.01), deg))
    if z_top > back + 2:
        r = rid / 2 + 1.5
        for x, y in ((r, 0), (-r, 0), (0, r), (0, -r)):
            sx, sy = (3, 4) if y == 0 else (4, 3)
            tube = tube.union(cbox(x, y, (back + 1.99 + z_top + 0.01) / 2, sx, sy, z_top - back - 1.98))
    return tube


def ring_pocket(face_z: float, z_top: float, deg: float = HEAD_RING_LEAD_DEG, rib_d: float = HEAD_RING[0]) -> cq.Workplane:
    """Cutter for the same seat sunk into a plate's underside (phase0_top): the bore up to the ring's back face (the plate is the
    lip) less the three ribs, and a slot from there through the plate to z_top for the solder pads and the leads."""
    t = HEAD_RING[2]
    back = face_z + t
    bore = cyl((0, 0, face_z - 5.0), HEAD_SEAT_BORE, t + 5.0).cut(_seat_ribs(face_z - 5.0, back + 1.0, rib_d))
    r1 = max((r[0] + r[1]) / 4 for r in HEAD_RING_RANGE) + RING_PAD[1] / 2 + 0.5  # the biggest ring's pads
    slot = box(HEAD_NOTCH_R0, -RING_PAD[0] / 2 - 0.5, back - 0.01, r1, RING_PAD[0] / 2 + 0.5, z_top + 1.0)
    return bore.union(_at_angle(slot, deg))


def station_ring_seat() -> cq.Workplane:
    """Upward LED-ring seat round the station lens, from Z = 0 (the pad top on the machine, the base underside in Phase 0): a
    tube whose bore takes a 60 or a 63 mm ring lying LEDs up on a shelf (its back face at STATION_RING_Z), the shelf on a
    45-deg cone so it prints without support, and a slot down through the shelf at STATION_RING_LEAD_DEG for the pads and
    leads. A 63 mm ring has 0.5 mm of radial play; centre a 60 mm one (2 mm) and fix either with three dots of glue."""
    bore, wall, depth, inner = STATION_SEAT
    zs, rb, ri = STATION_RING_Z, bore / 2, inner / 2
    body = cyl((0, 0, 0), bore + 2 * wall, zs + depth).cut(cyl((0, 0, zs), bore, depth + 1))
    cone = cq.Workplane("XY").add(cq.Solid.makeCone(rb, ri, rb - ri, cq.Vector(0, 0, zs - (rb - ri))))
    body = body.cut(cone).cut(cyl((0, 0, -1), bore, zs - (rb - ri) + 1.01)).cut(cyl((0, 0, zs - 1), inner, 2))
    rm = (STATION_RING[0] + STATION_RING[1]) / 4
    slot = box(rm - RING_PAD[1] / 2 - 2.0, -RING_PAD[0] / 2 - 0.5, zs - (rb - ri) - 1, rb - 0.5, RING_PAD[0] / 2 + 0.5, zs + 0.01)
    return body.cut(_at_angle(slot, STATION_RING_LEAD_DEG))


def camera_bracket(arm_offset: float, rib_d: float = HEAD_RING[0]) -> cq.Workplane:
    """Clamps the drop arm; holds the head camera board level, lens CAM_Z above the cup face and CAM_DY from the cup axis
    (toward the label end). The board sits on the shelf, HEAD_LENS_PROJ above the lens front; the LED ring hangs around
    the lens. Print in matte black, shelf face down."""
    z0, ly = CAM_Z, CAM_DY
    zs = z0 + HEAD_LENS_PROJ  # shelf top = board underside
    shelf = box(-24, ly - 24, zs - 4, 24, arm_offset - 10, zs)
    shelf = shelf.cut(cyl((0, ly, zs - 10), LENS_WINDOW_D, 20))  # lens holder window
    shelf = holes_z(shelf, [(dx, ly + dy) for dx in (-16, 16) for dy in (-16, 16)], 2.2)  # 32 mm board holes, M2 + nuts
    seat = ring_seat(z0 + HEAD_RING_FACE_DZ, zs - 4, rib_d=rib_d).translate((0, ly, 0))
    clamp = box(-12, arm_offset - 12, z0 - 6, 12, arm_offset + 12, zs)
    body = shelf.union(seat).union(clamp)
    body = body.cut(box(-10.2, arm_offset - 10.2, z0 - 7, 10.2, arm_offset + 10.2, zs + 1))  # arm bore, cut last
    body = holes_x(body, [(arm_offset, z0 + 9)], M5_CLR)
    return body


# --------------------------------------------------------------------------- carry-height sensor (Z stall guard)
# The spare TCST2103 endstop board (the BOM's sensors come as two 2-packs) on the Z spine's -X face, in carry_sensor_mount
# (2 x M5x10 button heads into slot-6 T-nuts in the spine's -X slot: slide it along the slot to set the trip). Same board
# orientation as the probe: arms toward -X, hole line along Y, so its slot runs along Z. A flag cut from the 1 mm aluminium
# sheet, on carry_flag_arm (screwed to the z_plate's front face), rises into the slot from below: its top edge crosses the
# beam at c = CARRY_SENSOR_C0 and the flag stays in the beam up to the Z hard top stop. Below CARRY_SENSOR_C0 the slot is
# clear. [Guessing] the board outline and header position, as for the probe board.
CS_PLATE_T = 5.0  # mount plate: the M5 button heads sit on its outer face, 5 mm of wall (>= 2.5) under them
CS_Y = sum(Z_SPINE_Y) / 2  # 76: the spine's -X slot = the sensor slot's mid-plane
CS_FACE_X = L.Z_SPINE_OFFSET_X - 20  # -30: the spine's -X face, X from the cup axis
CS_BASE_X = CS_FACE_X - CS_PLATE_T - PROBE_PCB[2]  # -36.6: sensor base (board front)
CS_TIP_X = CS_BASE_X - TCST_H  # -47.4: arm tips
CS_SCREW_L = 10.0  # M3x10 board screws: heads in pockets on the mount's spine side, washer + nut on the sensor flange
CS_M5_DZ = 17.0  # M5 screws above and below the board
CF_Z_TOP = 20.0  # flag top edge (the trip edge), above the Z carriage bottom (z_plate local Z)
CF_LEN = 36.0  # flag height: blocked from the trip to the hard top stop (15.5 mm) with 20 mm to spare (room to set the mount lower)
CF_X = (-62.0, CS_TIP_X + TCST_AP_DEPTH + 1.5)  # flag outer / inner edge: covers the aperture slit by 1.5 mm, 2.4 short of the slot bottom
CS_BEAM_Z = L.CARRY_SENSOR_C0 + L.Z_CARRIAGE_ABOVE_CUP + CF_Z_TOP  # 561.5: beam height above the pad top (fixed with the carriage)
CA_Z = (-4.0, CF_Z_TOP)  # carry_flag_arm, z_plate local Z
CA_LEG_X = (-64.0, -52.0)  # the arm's leg beside the spine: 4.6 mm outside the sensor's arm tips
CA_EAR_SCREWS = [(-24.0, 2.0), (-24.0, 14.0)]  # M3x10 self-tapping through the arm's ear into the z_plate front face (X, local Z)
CF_SCREWS = [(-58.0, 2.0), (-58.0, 14.0)]  # M3x8 self-tapping through the flag into the arm's leg end (X, local Z)


def carry_sensor_mount() -> cq.Workplane:
    """Plate on the Z spine's -X face that carries the spare endstop board. Local origin: X = cup axis, Y = machine Y,
    Z = the beam height (CS_BEAM_Z). The board's M3 heads sit in pockets on the spine side (fit the board first)."""
    x0, x1 = CS_FACE_X - CS_PLATE_T, CS_FACE_X
    plate = box(x0, CS_Y - 14, -24, x1, CS_Y + 14, 24)
    holes = [(CS_Y - PROBE_HOLES / 2, 0.0), (CS_Y + PROBE_HOLES / 2, 0.0)]
    plate = holes_x(plate, holes, M3_CLR)
    for y, z in holes:  # M3 head pockets on the spine side
        plate = plate.cut(cyl((x1 + 1, y, z), M3_CBORE[0], 1 + 3.2, (-1, 0, 0)))
    return holes_x(plate, [(CS_Y, -CS_M5_DZ), (CS_Y, CS_M5_DZ)], M5_CLR)


def carry_sensor_parts(cup_x: float) -> list[Part]:
    """Fixed to the X carriage: the mount, the board + TCST2103 and the fastener heads that stand proud."""
    zb = CS_BEAM_Z
    parts = [Part("carry_sensor_mount", carry_sensor_mount().translate((cup_x, 0, zb)), PETG, "printed", "carriage"),
             Part("carry_sensor", probe_sensor().translate((cup_x + CS_BASE_X - TCST_BASE_X, CS_Y - PROBE_Y, zb - PROBE_BEAM_Z)), BLACK, "purchased", "carriage",
                  note="spare TCST2103 endstop board: carry-height sensor")]
    fx = cup_x + CS_BASE_X - TCST_FLANGE_T  # flange top: washer + nut, then the screw tip
    for y in (CS_Y - PROBE_HOLES / 2, CS_Y + PROBE_HOLES / 2):
        tip = cup_x + CS_FACE_X - 3.2 - CS_SCREW_L
        nut = cyl((fx, y, zb), M3_WASHER[0], M3_WASHER[1], (-1, 0, 0)).union(cyl((fx - M3_WASHER[1], y, zb), 6.4, 2.4, (-1, 0, 0)))
        if tip < fx - M3_WASHER[1] - 2.4:
            nut = nut.union(cyl((fx - M3_WASHER[1] - 2.0, y, zb), 3.0, fx - M3_WASHER[1] - 2.0 - tip, (-1, 0, 0)))
        parts.append(Part(f"fc_carry_nut_{y:.0f}", nut, STEEL, "fastener", "carriage"))
    for dz in (-CS_M5_DZ, CS_M5_DZ):
        parts.append(head(f"fc_carry_m5_{dz:+.0f}", (cup_x + CS_FACE_X - CS_PLATE_T, CS_Y, zb + dz), (-1, 0, 0), M5_BUTTON, "carriage"))
    return parts


def carry_sensor_aperture(cup_x: float = 0.0) -> cq.Workplane:
    """The carry sensor's light path (as probe_aperture), machine coordinates."""
    return probe_aperture().translate((cup_x + CS_BASE_X - TCST_BASE_X, CS_Y - PROBE_Y, CS_BEAM_Z - PROBE_BEAM_Z))


def carry_sensor_cable(cup_x: float = 0.0) -> cq.Workplane:
    """Envelope of the carry board's 3-core lead: up from the header (board's +Y end, [Guessing]) beside the spine's back
    corner to the spine top, where it joins the 8-core with the Z switch cores. Fixed to the carriage; not a part."""
    return box(cup_x + CS_BASE_X - 6.0, CS_Y + 11.5, CS_BEAM_Z + 4.0, cup_x + CS_BASE_X, CS_Y + 17.5, L.Z_SPINE_TOP)


def carry_flag_arm() -> cq.Workplane:
    """Printed L arm: an ear on the z_plate's front face (2 x M3x10 self-tapping), a bar past the z_plate's -X end, and a leg
    beside the spine whose +Y end face carries the aluminium flag in the sensor slot's mid-plane. Local origin: X = cup axis,
    Y = machine Y, Z = Z carriage bottom (z_plate local Z). Print standing on its bottom face (as exported)."""
    z0, z1 = CA_Z
    yf = Z_CAR_FRONT - L.Z_PLATE_T  # 45: z_plate front face
    ear = box(CA_LEG_X[0], yf - 4.0, z0, -18.0, yf, z1)
    bar = box(CA_LEG_X[0], yf - 4.0, z0, CS_FACE_X - 0.5, Z_CAR_FRONT, z1)  # beside the z_plate's -X end (0.5 mm gap)
    leg = box(CA_LEG_X[0], yf - 4.0, z0, CA_LEG_X[1], CS_Y - FLAG_T / 2, z1)
    body = ear.union(bar).union(leg)
    body = holes_y(body, CA_EAR_SCREWS, M3_CLR)
    for x, z in CF_SCREWS:  # 2.5 mm pilots for the flag screws, 10 deep into the leg's end
        body = body.cut(cyl((x, CS_Y - FLAG_T / 2 + 0.01, z), 2.5, 10.0, (0, -1, 0)))
    return body


def carry_flag() -> cq.Workplane:
    """1 mm aluminium flag (flat, no bend), z_plate local Z: its top edge is the trip edge."""
    body = box(CF_X[0], CS_Y - FLAG_T / 2, CF_Z_TOP - CF_LEN, CF_X[1], CS_Y + FLAG_T / 2, CF_Z_TOP)
    return holes_y(body, CF_SCREWS, M3_CLR)


def carry_flag_parts(cup_x: float, c: float) -> list[Part]:
    """Moves with Z: the arm, the flag and their screw heads."""
    zc = c + L.Z_CARRIAGE_ABOVE_CUP
    yf = Z_CAR_FRONT - L.Z_PLATE_T
    parts = [Part("carry_flag_arm", carry_flag_arm().translate((cup_x, 0, zc)), PETG, "printed", "head"),
             Part("carry_flag", carry_flag().translate((cup_x, 0, zc)), ALU, "made", "head", note="1 mm aluminium, cut to 19.9 x 36")]
    for x, z in CA_EAR_SCREWS:
        parts.append(head(f"fh_carry_arm_{z:.0f}", (cup_x + x, yf - 4.0, zc + z), (0, -1, 0), M3_HEAD, "head"))
    for x, z in CF_SCREWS:
        parts.append(head(f"fh_carry_flag_{z:.0f}", (cup_x + x, CS_Y + FLAG_T / 2, zc + z), (0, 1, 0), M3_HEAD, "head"))
    return parts


# --------------------------------------------------------------------------- homing switches (X home, Z top)
# Bare SPDT hinge-lever microswitches, the common 20 x 6 mm size (BOM 'Homing switches'). [Certain, Omron SS-5GL datasheet, SS
# series] body 19.8 x 10.2 x 6.4 mm; two 2.35 mm mounting holes 9.5 +/- 0.1 mm apart (M2 or M2.3 screws), the first 5.1 from the
# hinge end, their centres 2.9 above the terminal face; operating position OP 8.8 +/- 0.8 and free position FP max 13.6, both
# above the hole line at the lever's operating point (14.5 from the first hole); overtravel OT min 1.2 mm; lever 3.6 wide;
# terminals C, NO, NC 1.6, 10.4 and 17.7 from the hinge end. [Likely] the BOM's generic 10-pack has this body and 9.5 mm holes.
# [Guessing] the lever pivot (read off the drawing), the body's lower top from 9.4 mm out, and the 4.5 mm terminals.
# Switch frame (u, w, v): u along the body from the hinge end, w across it (centred), v up from the hole line (the lever side).
# Each switch is worked by a 45-deg lead-in that slides ACROSS the lever (the axis moves along the lever's pivot axis), then a
# flat that holds the operating point SW_DWELL_OT past OP however far the axis runs on: the hard stops are 4 mm past the trip,
# the lever's overtravel only 1.2 mm, so a striker pushing the lever head-on would make the switch the stop (or break it).
SW_L, SW_T = 19.8, 6.4  # body length (u), thickness (w)
SW_TOP, SW_STEP, SW_BOTTOM = 7.3, (9.4, 6.6), -2.9  # body top over the pivot half; from u 9.4 on it is 6.6; terminal face (v)
SW_HOLES_U, SW_HOLE_D = (5.1, 14.6), 2.35
SW_TABS_U, SW_TAB = (1.6, 10.4, 17.7), (0.5, 3.2, 4.5)  # C, NO, NC; each tab: along u, across w, length out of the terminal face
SW_PIVOT = (3.25, 6.4)  # lever pivot (u, v)
SW_LEVER = (3.6, 0.3, 20.0)  # width (w), thickness, end (u)
SW_OP_U = SW_HOLES_U[0] + 14.5  # 19.6: the operating point, where OP and FP are measured
SW_OP, SW_OP_TOL, SW_FP, SW_OT = 8.8, 0.8, 13.6, 1.2
SW_E = SW_OP - SW_PIVOT[1]  # lever top face above its pivot: the lever lies flat (angle 0) at the nominal OP
SW_DWELL_OT = 0.6  # the striker's flat holds the operating point this far past OP: on for sure, and 0.6 mm short of OT min
SW_U0 = 12.0  # each striker covers the lever from here to past its end, never the pivot end (the lever stands highest there)
SW_CHAMFER = 6.5  # the X finger's 45-deg lead-in: deeper than the free lever (FP max) stands above the flat (5.3) + SW_SLOT
SW_SLOT = 1.0  # the M2 slots let a switch move +/- this toward its striker (covers OP +/- 0.8)
# Longest lever (end from the hinge end, u) fitted as is: 3.2 mm past the body end. [Guessing] which lever the BOM's generic pack
# has: long hinge levers end 25-28 mm out. A longer lever is cut back to SW_LEVER[2] (flush with the body end) before fitting.
# checks.py reports the longest each switch takes (X: the carry flag's screws; Z: the z_plate's lead-in).
SW_LEVER_MAX = 23.0
M2_HEAD, M2_NUT = (3.8, 2.0), (4.6, 1.6)  # M2 socket head (dia, height); M2 nut (across corners, thickness)
M2_SLOT_W = 2.4


def sw_lever_v(u: float, ang: float) -> float:
    """Height (v) of the lever's top face at the lever point that lies at u when the lever is flat, the lever at ang (rad)."""
    pu, pv = SW_PIVOT
    return pv + (u - pu) * math.sin(ang) + SW_E * math.cos(ang)


def sw_lever_u(u: float, ang: float) -> float:
    """Where along the body (u) that lever point lies at ang."""
    pu, _ = SW_PIVOT
    return pu + (u - pu) * math.cos(ang) - SW_E * math.sin(ang)


def sw_angle(v_op: float) -> float:
    """Lever angle (rad) that puts the operating point at height v_op."""
    lo, hi = -0.6, 0.6
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if sw_lever_v(SW_OP_U, mid) < v_op else (lo, mid)
    return (lo + hi) / 2


SW_FREE = sw_angle(SW_FP)  # free lever (FP max: the furthest it can stand out)
SW_DWELL_V = sw_lever_v(SW_U0, sw_angle(SW_OP - SW_DWELL_OT))  # 8.48: the striker's flat above the hole line


def sw_lever_angle(striker, end: float | None = None) -> float:
    """Lever angle (rad) with a striker on it: the highest angle, up to free, at which no point of the lever's top face (from
    the pivot to the end, both edges and the middle) stands above striker(u, w), the striker face's height (v) over the body
    point (u, w), None where it does not reach. Points are passed where they lie at that angle, so the lever's swing counts.
    ``end``: the lever's end (u; None = SW_LEVER's)."""
    pu = SW_PIVOT[0]
    end = SW_LEVER[2] if end is None else end
    pts = [(pu + 0.25 * k, w) for k in range(int((end - pu) / 0.25) + 1) for w in (-SW_LEVER[0] / 2, 0.0, SW_LEVER[0] / 2)]

    def fits(a):
        for u, w in pts:
            s = striker(sw_lever_u(u, a), w)
            if s is not None and sw_lever_v(u, a) > s + 1e-6:
                return False
        return True
    if fits(SW_FREE):
        return SW_FREE
    lo, hi = sw_angle(SW_OP - 4.0), SW_FREE
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if fits(mid) else (lo, mid)
    return lo


def sw_body() -> cq.Workplane:
    """Switch body with its mounting holes and terminals, switch frame (x = u, y = w, z = v)."""
    hw = SW_T / 2
    body = box(0, -hw, SW_BOTTOM, SW_L, hw, SW_TOP).cut(box(SW_STEP[0], -hw - 1, SW_STEP[1], SW_L + 1, hw + 1, SW_TOP + 1))
    body = holes_y(body, [(u, 0.0) for u in SW_HOLES_U], SW_HOLE_D)
    for u in SW_TABS_U:
        body = body.union(box(u, -SW_TAB[1] / 2, SW_BOTTOM - SW_TAB[2], u + SW_TAB[0], SW_TAB[1] / 2, SW_BOTTOM + 0.01))
    return body


def sw_lever(ang: float, end: float | None = None) -> cq.Workplane:
    """The lever at ang (0 = flat at OP, + = up), switch frame. ``end``: the lever's end (u; None = SW_LEVER's)."""
    w, t, e = SW_LEVER
    end = e if end is None else end
    pu, pv = SW_PIVOT
    lev = box(pu - 1.0, -w / 2, SW_OP - t, end, w / 2, SW_OP)
    return lev.rotate((pu, 0, pv), (pu, 1, pv), -math.degrees(ang))


def sw_m2(u: float, w0: float, v: float, nut_side: float) -> tuple[cq.Workplane, cq.Workplane]:
    """(head, nut + tip) of an M2x12 through a mounting hole at u, switch frame: the head sits at w0 (outside the mount), the nut
    on the switch's face at w = nut_side * SW_T / 2."""
    s = 1 if nut_side > 0 else -1
    head = cyl((u, w0, v), M2_HEAD[0], M2_HEAD[1], (0, -s, 0))
    nf = s * SW_T / 2
    tip = w0 + s * 12.0
    nut = cyl((u, nf, v), M2_NUT[0], M2_NUT[1], (0, s, 0))
    if s * (tip - (nf + s * M2_NUT[1])) > 0.01:
        nut = nut.union(cyl((u, nf + s * M2_NUT[1], v), 2.0, s * (tip - nf) - M2_NUT[1], (0, s, 0)))
    return head, nut


# X home switch: under the beam's left end, in front of the left upright, on x_switch_mount (2 x M5x10 button heads into T-nuts in
# the beam's lower front slot, left of x_bumper_L: slide it to set the click). Lever up, pivot end toward the back, worked by a
# finger off the x_bracket's left edge (x_finger(), Y 86-94): its underside's lead-in presses the lever as the carriage moves
# left and its flat holds it to the hard stop. Everything stays behind Y 84: in front of that, the carry flag and its arm (on the
# z_plate's left end) sweep the whole Z travel at the left end of X. Machine frame: X = XS_X + w, Y = XS_Y0 - u, Z = XS_ZH + v.
XF_Y = (BEAM_Y0 - L.MGN12_H - L.X_BRACKET_T, BEAM_Y0 - L.MGN12_H)  # (86, 94): the finger has the x_bracket plate's thickness
XF_Z = (369.5, 378.5)  # finger underside (the flat) and top: under x_bumper_L (Z 380) by 1.5
XS_X = -24.0  # switch centre (w = 0); its nut side ends 4.2 mm left of the x_bracket at the left hard stop
XS_Y0 = XF_Y[1] + SW_U0  # 106: pivot end, so the finger covers the lever from u = SW_U0 on
XS_ZH = XF_Z[0] - SW_DWELL_V  # 361.0: hole line
# finger length off the x_bracket's left edge: at cup X = X_HOME_SWITCH its lead-in stands SW_OP above the hole line over the
# lever's right edge (where it is lowest), so the lever, flat there, is at OP
XF_LEN = L.X_HOME_SWITCH - XB_HALF - (XS_X + SW_LEVER[0] / 2) + SW_DWELL_V + SW_CHAMFER - SW_OP  # 17.4
XSM_T, XSM_FRONT_T = 4.0, 5.0  # side plate (holds the switch, M2 slots) and front plate (on the beam + upright front faces)
XSM_X0 = -55.0  # front plate's left end
XSM_TOP_X1 = L.X_HARD_STOP[0] - XB_HALF - 12.0 - 4.0  # -31: the part above the beam bottom stays 4 mm left of x_bumper_L
XSM_Z = (353.0, 400.0)
XSM_M5_X = (-48.5, -37.0)  # M5 screws, beam's lower front slot (Z = X_BEAM_Z - 10)


def x_finger() -> cq.Workplane:
    """The x_bracket's finger, x_bracket local coordinates (X from the cup axis, Y from the X carriage's front face): a bar off
    the plate's left edge at Z XF_Z, with a 45-deg lead-in on the underside of its left end."""
    x1, x0 = -XB_HALF, -XB_HALF - XF_LEN
    yb = XF_Y[0] - (BEAM_Y0 - L.MGN12_H)  # -8
    bar = box(x0, yb, XF_Z[0], x1 + 0.01, 0, XF_Z[1])
    ch = SW_CHAMFER
    wedge = cq.Workplane("XZ").polyline([(x0 - 0.01, XF_Z[0] - 0.01), (x0 + ch, XF_Z[0] - 0.01), (x0 - 0.01, XF_Z[0] + ch)]).close().extrude(-20)
    return bar.cut(wedge.translate((0, yb - 5, 0)))


def x_finger_striker(cup_x: float):
    """striker(u, w) for sw_lever_angle: the finger's underside over the X switch's lever, the carriage at cup_x."""
    x_end = cup_x - XB_HALF - XF_LEN

    def s(u, w):
        X, Y = XS_X + w, XS_Y0 - u
        if not XF_Y[0] <= Y <= XF_Y[1] or not x_end <= X <= cup_x + XB_HALF:
            return None
        return XF_Z[0] + max(0.0, SW_CHAMFER - (X - x_end)) - XS_ZH
    return s


def _place_x(shape: cq.Workplane) -> cq.Workplane:
    return shape.rotate((0, 0, 0), (0, 0, 1), -90).translate((XS_X, XS_Y0, XS_ZH))


def x_switch_mount() -> cq.Workplane:
    """Printed bracket for the X home switch, machine coordinates (as fitted). A front plate on the beam's and the left upright's
    front faces (Y = BEAM_Y0), 2 x M5x10 button heads into T-nuts in the beam's lower front slot: slide it along the slot to set
    the click. A side plate along the switch's left face carries it on 2 x M2x12 in slots that let it move +/- SW_SLOT up or
    down (toward or away from the finger)."""
    xs = XS_X - SW_T / 2  # switch's left face
    yf = BEAM_Y0
    side = box(xs - XSM_T, XS_Y0 - SW_L - 2.0, XSM_Z[0], xs, yf - XSM_FRONT_T + 1.0, XF_Z[0] - 2.5)
    front = box(XSM_X0, yf - XSM_FRONT_T, XSM_Z[0], xs, yf, Z_BEAM_BOT).union(box(XSM_X0, yf - XSM_FRONT_T, Z_BEAM_BOT - 0.01, XSM_TOP_X1, yf, XSM_Z[1]))
    body = side.union(front)
    for u in SW_HOLES_U:  # M2 slots along Z, and room for the heads where the front plate meets the side plate
        y = XS_Y0 - u
        body = body.cut(box(xs - XSM_T - 1, y - M2_SLOT_W / 2, XS_ZH - SW_SLOT, xs + 1, y + M2_SLOT_W / 2, XS_ZH + SW_SLOT))
        body = holes_x(body, [(y, XS_ZH - SW_SLOT), (y, XS_ZH + SW_SLOT)], M2_SLOT_W, x0=xs - XSM_T - 1, h=XSM_T + 2)
        r = M2_HEAD[0] / 2 + 0.7
        body = body.cut(box(xs - XSM_T - M2_HEAD[1] - 2.0, y - r, XS_ZH - SW_SLOT - r, xs - XSM_T, y + r, XS_ZH + SW_SLOT + r))
    return holes_y(body, [(x, L.X_BEAM_Z - 10) for x in XSM_M5_X], M5_CLR)


def x_switch_parts(cup_x: float | None = None) -> list[Part]:
    """Static: the mount, the switch with its lever posed for the carriage at cup_x (None = free), and the screw heads and nuts."""
    ang = SW_FREE if cup_x is None else sw_lever_angle(x_finger_striker(cup_x))
    parts = [Part("x_switch_mount", x_switch_mount(), PETG, "printed", "static"),
             Part("x_home_switch", _place_x(sw_body().union(sw_lever(ang))), BLACK, "purchased", "static",
                  note="SPDT hinge-lever microswitch, C + NC wired", meta={"lever_deg": math.degrees(ang)})]
    for u in SW_HOLES_U:
        hd, nut = sw_m2(u, -SW_T / 2 - XSM_T, 0.0, 1)  # head on the side plate's outer face (w < 0 = -X), nut on the switch's right face
        parts += [Part(f"fx_xsw_m2_{u:.0f}", _place_x(hd), STEEL, "fastener", "static"),
                  Part(f"fx_xsw_nut_{u:.0f}", _place_x(nut), STEEL, "fastener", "static")]
    for x in XSM_M5_X:
        parts.append(head(f"fx_xsw_m5_{x:.0f}", (x, BEAM_Y0 - XSM_FRONT_T, L.X_BEAM_Z - 10), (0, -1, 0), M5_BUTTON, "static"))
    return parts


def x_switch_cable() -> cq.Workplane:
    """Envelope of the X switch's 2-core lead (W52): down from the terminals, back under the beam below the corner brackets
    (they reach ~40 mm down the upright from the beam), and up behind the beam to its rear lower slot. Static; not a part."""
    x0, x1 = XS_X - SW_TAB[1] / 2 - 0.5, XS_X + SW_TAB[1] / 2 + 0.5
    zl = XS_ZH + SW_BOTTOM - SW_TAB[2]
    z0 = Z_BEAM_BOT - 50.0
    drop = box(x0, XS_Y0 - SW_L, z0, x1, XS_Y0, zl)
    run = box(x0, XS_Y0 - SW_L, z0, x1, BEAM_Y1 + 5, z0 + 4)
    rise = box(x0, BEAM_Y1 + 1, z0, x1, BEAM_Y1 + 5, L.X_BEAM_Z - 7)
    return drop.union(run).union(rise)


# Z top switch: on the Z spine's right (+X) face near the top, on z_switch_mount (2 x M5x10 button heads into T-nuts in that face's
# slot: slide it along the slot to set the click), fixed to the X carriage. Lever toward the z_plate (-Y), pivot end to the right of
# the z_plate's right end: as the head rises, the chamfer along the z_plate's top-back edge (ZP_CHAMFER_X) presses the lever and its
# back face holds it to the top hard stop. Machine frame: X = cup + ZS_X0 - u, Y = ZS_YH - v, Z = ZS_Z - w.
ZP_X1 = 40.0  # z_plate's right end, X from the cup axis
# The chamfer runs from ZP_CHAMFER_X to the right end: a lever under the plate's square top would be hit edge-on, so it covers any
# lever ending up to u = ZS_X0 - ZP_CHAMFER_X = 32 (the CAD's lever is under the plate from X 32). It is ZP_CHAMFER deep (45 deg),
# 0.5 short of the 8 mm plate: a free lever stands into the plate's path up to that far (+ SW_SLOT) and is still caught.
ZP_CHAMFER_X, ZP_CHAMFER = 20.0, 7.5
ZS_X0 = ZP_X1 + SW_U0  # 52: pivot end, X from the cup axis
ZS_YH = Z_CAR_FRONT + SW_DWELL_V  # 61.5: hole line (Y)
# switch centre (w = 0): at c = Z_SWITCH_C the chamfer stands SW_OP above the hole line over the lever's lower edge
ZS_Z = L.Z_SWITCH_C + L.Z_CARRIAGE_ABOVE_CUP + L.Z_PLATE_TOP - (SW_DWELL_V + ZP_CHAMFER - SW_OP) + SW_LEVER[0] / 2  # 605.6
ZSM_T, ZSM_SHELF_T = 5.0, 3.0  # spine plate (M5 wall), shelf under the switch (M2 slots)
ZSM_SHELF = (15.0, 54.0, Z_CAR_FRONT + 2.0, 70.0)  # x0, x1 (from the cup axis), y0, y1: 2 mm behind the z_plate, clear of the Z carriage
ZSM_M5_Z = (582.0, 594.0)


def z_plate_striker(c: float):
    """striker(u, w) for sw_lever_angle: the z_plate's back face and top chamfer under the Z switch's lever, the cup at c."""
    zb = c + L.Z_CARRIAGE_ABOVE_CUP
    z_top = zb + L.Z_PLATE_TOP

    def s(u, w):
        X, Z = ZS_X0 - u, ZS_Z - w
        if not -30.0 <= X <= ZP_X1 or not zb - 5.0 <= Z <= z_top:
            return None
        y = Z_CAR_FRONT - (max(0.0, ZP_CHAMFER - (z_top - Z)) if X >= ZP_CHAMFER_X else 0.0)
        return ZS_YH - y
    return s


def _place_z(shape: cq.Workplane, cup_x: float) -> cq.Workplane:
    return shape.rotate((0, 0, 0), (1, 0, 0), 90).rotate((0, 0, 0), (0, 1, 0), 180).translate((cup_x + ZS_X0, ZS_YH, ZS_Z))


def z_switch_mount() -> cq.Workplane:
    """Printed bracket for the Z top switch. Local origin: X = cup axis, Y = machine Y, Z = machine Z. A plate on the spine's right
    face (2 x M5x10 button heads into T-nuts in its slot), a shelf under the switch (2 x M2x12 from below, in slots that let it
    move +/- SW_SLOT toward or away from the z_plate) and a rib under the shelf's back edge."""
    x0 = L.Z_SPINE_OFFSET_X + 20  # spine's right face
    zt = ZS_Z - SW_T / 2  # shelf top = switch's lower face
    sx0, sx1, sy0, sy1 = ZSM_SHELF
    plate = box(x0, Z_SPINE_Y[0], ZSM_M5_Z[0] - 6.0, x0 + ZSM_T, Z_SPINE_Y[1], zt)
    shelf = box(sx0 - 0.01, sy0, zt - ZSM_SHELF_T, sx1, sy1, zt)
    rib = box(sx0 - 0.01, Z_SPINE_Y[0], zt - ZSM_SHELF_T - 6.0, sx1 - 4.0, sy1, zt - ZSM_SHELF_T + 0.01)
    body = plate.union(shelf).union(rib)
    for u in SW_HOLES_U:  # M2 slots along Y
        x = ZS_X0 - u
        body = body.cut(box(x - M2_SLOT_W / 2, ZS_YH - SW_SLOT, zt - 10, x + M2_SLOT_W / 2, ZS_YH + SW_SLOT, zt + 1))
        body = holes_z(body, [(x, ZS_YH - SW_SLOT), (x, ZS_YH + SW_SLOT)], M2_SLOT_W, z0=zt - 10, h=11)
    return holes_x(body, [(sum(Z_SPINE_Y) / 2, z) for z in ZSM_M5_Z], M5_CLR, x0=x0 - 1, h=ZSM_T + 2)


def z_switch_parts(cup_x: float, c: float | None = None) -> list[Part]:
    """Fixed to the X carriage: the mount, the switch with its lever posed for the cup at c (None = free), screw heads and nuts."""
    ang = SW_FREE if c is None else sw_lever_angle(z_plate_striker(c))
    parts = [Part("z_switch_mount", z_switch_mount().translate((cup_x, 0, 0)), PETG, "printed", "carriage"),
             Part("z_top_switch", _place_z(sw_body().union(sw_lever(ang)), cup_x), BLACK, "purchased", "carriage",
                  note="SPDT hinge-lever microswitch, C + NC wired", meta={"lever_deg": math.degrees(ang)})]
    for u in SW_HOLES_U:
        hd, nut = sw_m2(u, SW_T / 2 + ZSM_SHELF_T, 0.0, -1)  # head under the shelf (w > 0 = down), nut on the switch's top face
        parts += [Part(f"fc_zsw_m2_{u:.0f}", _place_z(hd, cup_x), STEEL, "fastener", "carriage"),
                  Part(f"fc_zsw_nut_{u:.0f}", _place_z(nut, cup_x), STEEL, "fastener", "carriage")]
    for z in ZSM_M5_Z:
        parts.append(head(f"fc_zsw_m5_{z:.0f}", (cup_x + L.Z_SPINE_OFFSET_X + 20 + ZSM_T, sum(Z_SPINE_Y) / 2, z), (1, 0, 0), M5_BUTTON, "carriage"))
    return parts


def z_switch_cable(cup_x: float = 0.0) -> cq.Workplane:
    """Envelope of the Z switch's two cores (8-core cores 4 and 5): back from the terminals past the spine's back face, then up
    behind the z_motor_mount to the spine top, where the 8-core's jacket is opened (WIRING.md sec. 11). Fixed to the carriage."""
    x0, x1 = cup_x + ZS_X0 - SW_L - 0.5, cup_x + ZS_X0 + 0.5
    z0, z1 = ZS_Z - SW_TAB[1] / 2 - 0.5, ZS_Z + SW_TAB[1] / 2 + 0.5
    back = box(x0, ZS_YH - SW_BOTTOM + SW_TAB[2], z0, x1, Z_SPINE_Y[1] + 5, z1)
    rise = box(x0, Z_SPINE_Y[1] + 1, z0, x1, Z_SPINE_Y[1] + 5, L.Z_SPINE_TOP + L.Z_MOTOR_MOUNT_T + 10)
    return back.union(rise)


# --------------------------------------------------------------------------- build tools (printed)


def drill_template() -> cq.Workplane:
    """One-cell drilling jig. Two cone dimples (X +/-40) are touched by the awl adapter on the
    head, which aligns the jig to the machine's own X axis; then the 8 rod holes are drilled
    through the 12 mm tall guide bosses. Neighbouring cells share wall rods, so the jig's
    side holes simply re-enter already drilled holes."""
    t = 4.0
    w = L.PITCH_X + L.ROD_D + 12
    lgt = L.POCKET_L + L.WALL + L.ROD_D + 12
    plate = cbox(0, 0, t / 2, w, lgt, t)
    xs = (-L.PITCH_X / 2, L.PITCH_X / 2)
    y_side = (-(L.POCKET_L / 2 - L.ROD_INSET), L.POCKET_L / 2 - L.ROD_INSET)
    x_fb = (-(L.POCKET_W / 2 - L.ROD_INSET), L.POCKET_W / 2 - L.ROD_INSET)
    y_fb = (-(L.POCKET_L / 2 + L.WALL / 2), L.POCKET_L / 2 + L.WALL / 2)
    pts = [(x, y) for x in xs for y in y_side] + [(x, y) for x in x_fb for y in y_fb]
    for x, y in pts:
        plate = plate.union(cyl((x, y, 0), 16, 12))
    plate = holes_z(plate, pts, L.ROD_D + 0.3)
    for x in (-40, 40):  # alignment dimples on the row centre line
        plate = plate.cut(cq.Workplane("XY").add(cq.Solid.makeCone(0.2, 3.0, 3.0, cq.Vector(x, 0, t - 3.0 + 0.01))))
    plate = plate.cut(cbox(0, 0, t / 2, 50, 90, t + 2))  # window to see the pencil centre line
    return plate


def awl_adapter() -> cq.Workplane:
    """Screws onto the spring buffer in place of the cup; holds a 3 mm steel pin with a sharp point
    on the cup axis (used to align the drill template)."""
    body = cyl((0, 0, 0), 14, 18).cut(cyl((0, 0, 9), 6.4, 10))  # M5 heat-set insert pocket (6.4 mm, e.g. ruthex M5x9.5)
    body = body.cut(cyl((0, 0, -1), 3.1, 12))
    return body


def fill_gauge() -> cq.Workplane:
    """Stand it in a pocket: slabs must not stack above the underside of its top bar (the MAX line); the notches count slabs."""
    g = box(0, 0, 0, 12, 4, L.MAX_LINE)
    for k in range(0, 31, 5):
        g = g.cut(box(-1, -1, k * 6.6, 3, 5, k * 6.6 + 0.8))
    return g.union(box(0, 0, L.MAX_LINE, 30, 4, L.MAX_LINE + 4))


# --------------------------------------------------------------------------- Phase 0 test jig (printed)
# A slab sits on edge ledges with its FRONT 140 mm above the station camera (same mount as the
# machine) and its BACK 140 mm below the head camera, exactly as in the machine. Two 2020 posts
# stand on the base's socket floors; the top bridge rests on the post tops (blind sockets).

P0_POST = 312.0  # 2020 posts (BOM length)
P0_SOCKET_FLOOR = 2.0  # phase0_base socket floor height
# phase0_top: the head ring's pocket comes within 0.33 mm (in plan) of each M2 standoff hole (the board's 32 mm pattern, 22.6 mm
# from the lens axis), so the 4 mm blind holes must stop 2 mm above the pocket's top (the ring's back face, 4.6 above the
# underside): 10.6 thick (was 8, which left 1.23 mm). The bar's underside and the ring stay where they were, relative to the lens.
P0_BAR_T, P0_BAR_SOCKET = 10.6, 5.0  # phase0_top thickness, blind socket depth
P0_M2_DEPTH = 4.0  # blind M2 holes for the standoffs (an M2 standoff's male thread is ~3 mm [Likely])
P0_SLAB_Z = L.STATION_LENS_Z + L.CAM_TO_SLAB  # slab front (bottom face) height = tray ledge top
P0_TOP_Z = P0_SLAB_Z + SLAB_T + L.CAM_TO_SLAB  # head lens front height
P0_BAR_Z0 = P0_SOCKET_FLOOR + P0_POST - P0_BAR_SOCKET  # 309: bridge underside, fixed by the posts
P0_BAR_TOP = P0_BAR_Z0 + P0_BAR_T  # 319.6
P0_TRAY_PLAY = 1.0  # total slab play in the tray recess. Set dims.SLAB_W/H to your LARGEST measured slab (sec. 1.2)
P0_LEDGE = 2.6  # ledge under each slab edge (centred slab); >= 2.1 mm even when shifted by the full play
# The occluder (head_foot + buffer + cup + probe on a 2020 arm stub) hangs under the head camera exactly as on the
# machine at the probe trip: the cup rests on the slab back and the slab pushes it up CUP_HANG, so the foot's underside is
# FOOT_Z[0] above the slab back. Push the cup up by hand to change slabs. For the face-up pass the mount (with the stub)
# slides P0_FACE_UP_LIFT up its post, so the free cup hangs clear of the slab's front.
P0_POST_X = (L.POCKET_W + 2 * 12) / 2 + 11  # jig post centres at X = +/- 65
P0_OCC_C = P0_TOP_Z - CAM_Z  # the jig's "c" = the slab back: every head part sits where it is on the machine, relative to the lens
P0_FACE_UP_LIFT = L.CUP_HANG + 1.0  # the free cup then hangs 1 mm above a face-up slab
P0_STUB = 66.0  # 2020 arm stub, bottoms in head_foot's socket like the drop arm; its top stays under the bridge even lifted
P0_MOUNT_Z = (110.0, 128.0)  # occluder mount band above P0_OCC_C: over the sensor post, under the bridge
# Every printed wall an M5x10 passes into a 2020 T-nut is P0_M5_WALL thick (pads on the 1.8-2.0 mm clamp and socket walls;
# the base sockets are 3.8). With one M5 washer the screw then ends 5 mm inside the profile's face: through the slot-6
# T-nut, short of the profile core. [Guessing] the 2020 slot depth (~6 mm to the core); BUILD_GUIDE 1.5 tests one screw.
P0_M5_WALL = 4.0
P0_M5_PAD = P0_M5_WALL - (24.0 - 20.4) / 2  # on the tray clamps' 1.8 mm outer walls


def phase0_occluder_mount() -> cq.Workplane:
    """Holds the occluder's 2020 arm stub on the drop arm's line (X 0, Y +ARM_TO_CUP) under the head camera.
    A clamp slides on the right jig post (M5x10 into a T-nut in the post's outer slot), a socket holds the stub
    (M5x10 into a T-nut in the stub's +X slot), and a beam joins them outside the camera's view.
    Local origin: jig axis, Z = mount underside."""
    h, px, yc = P0_MOUNT_Z[1] - P0_MOUNT_Z[0], P0_POST_X, L.ARM_TO_CUP
    clamp = box(px - 12, -12, 0, px + 12, 12, h)
    socket = box(-12.2, yc - 12.2, 0, 12.2, yc + 12.2, h)
    beam = box(11.0, 11.0, 0, px, 30.0, 8.0)
    body = clamp.union(socket).union(beam)
    w = P0_M5_WALL  # pads on the two walls the M5 screws pass (1.8 / 2.0 mm walls before)
    body = body.union(box(px + 12 - 0.01, -7, h / 2 - 7, px + 10.2 + w, 7, h / 2 + 7))
    body = body.union(box(12.2 - 0.01, yc - 7, h / 2 - 7, 10.2 + w, yc + 7, h / 2 + 7))
    body = body.cut(box(px - 10.2, -10.2, -1, px + 10.2, 10.2, h + 1))  # post bore
    body = body.cut(box(-10.2, yc - 10.2, -1, 10.2, yc + 10.2, h + 1))  # stub bore
    body = body.cut(cyl((px + 9, 0, h / 2), M5_CLR, 10, (1, 0, 0)))  # clamp screw, outer wall only
    return body.cut(cyl((9, yc, h / 2), M5_CLR, 10, (1, 0, 0)))  # stub screw, +X wall only


def p0_board_spacer(lens_proj: float = HEAD_LENS_PROJ) -> float:
    """M2 standoff height under the head camera board on phase0_top, for a measured board-to-lens-front length."""
    return P0_TOP_Z + lens_proj - P0_BAR_TOP


def p0_tray_opening() -> tuple[float, float]:
    return SLAB_W - 2 * P0_LEDGE, SLAB_H - 2 * P0_LEDGE


def phase0_tray() -> cq.Workplane:
    """Frame that holds one slab flat on edge ledges between the two posts.
    Local origin: slab centre at the ledge top (= slab front face)."""
    ow, ol = L.POCKET_W + 2 * 12, L.POCKET_L + 2 * 6
    rw, rl = SLAB_W + P0_TRAY_PLAY, SLAB_H + P0_TRAY_PLAY  # recess: locates the slab
    aw, al = p0_tray_opening()  # through opening: the station camera looks through it
    frame = box(-ow / 2, -ol / 2, -4, ow / 2, ol / 2, 4)
    frame = frame.cut(box(-aw / 2, -al / 2, -5, aw / 2, al / 2, 5))
    frame = frame.cut(box(-rw / 2, -rl / 2, 0, rw / 2, rl / 2, 5))
    # 1 mm lead-in, 45 deg. The taper starts 0.5 mm below Z 3 and 0.5 mm inset, inside the recess, so its faces cross the recess walls
    # at Z 3; started on the walls it left 0.2 mm sliver faces at the corners (bad STL). Its rounded corners grow by 0.5 mm.
    frame = frame.cut(cq.Workplane("XY").workplane(offset=2.5).rect(rw - 1, rl - 1).extrude(1.51, taper=-45))
    frame = frame.cut(cq.Workplane("XY").workplane(offset=-4.01).rect(aw + 4, al + 4).extrude(2.01, taper=45))  # 45-deg underside chamfer: the 4 mm ledge doesn't shade the label edge
    frame = frame.cut(box(-25, -ol / 2 - 10, 0, 25, -ol / 2 + 10, 5))  # finger notch at the front to lift the slab out
    for sx in (-1, 1):  # clamps onto the 2020 posts; the M5 goes through a pad on the outer wall (P0_M5_WALL in all)
        cx = sx * (ow / 2 + 11)
        clamp = cbox(cx, 0, 6, 24, 24, 20).cut(cbox(cx, 0, 6, 20.4, 20.4, 22))
        clamp = clamp.union(cbox(cx + sx * (12 + P0_M5_PAD / 2 - 0.01), 0, 6, P0_M5_PAD + 0.02, 14, 14))
        clamp = holes_x(clamp, [(0, 6)], M5_CLR)
        frame = frame.union(clamp)
    return frame


P0_M2_HOLES = [(dx, CAM_DY + dy) for dx in (-16, 16) for dy in (-16, 16)]  # head camera board, 32 mm square round the lens


def phase0_top() -> cq.Workplane:
    """Bridge resting on the post tops (blind sockets), carrying the head camera board on M2 standoffs
    (height p0_board_spacer()) and the head LED ring, sunk into its underside so it sits where it does on the machine relative
    to the lens. Local origin: bar underside, centre."""
    ow = L.POCKET_W + 2 * 12
    span = ow + 2 * 11
    ly = CAM_DY  # the head lens sits CAM_DY from the slab (= cup) axis, as on the machine
    bar = box(-(span + 24) / 2, ly - 25, 0, (span + 24) / 2, 25, P0_BAR_T)
    bar = bar.cut(cyl((0, ly, -1), LENS_WINDOW_D, 12))
    for sx in (-1, 1):
        bar = bar.cut(cbox(sx * span / 2, 0, P0_BAR_SOCKET / 2, 20.4, 20.4, P0_BAR_SOCKET))  # blind sockets
    body = bar.cut(ring_pocket(P0_TOP_Z + HEAD_RING_FACE_DZ - P0_BAR_Z0, P0_BAR_T).translate((0, ly, 0)))  # ring as on the machine, rel. to the lens
    return holes_z(body, P0_M2_HOLES, 1.8, z0=P0_BAR_T - P0_M2_DEPTH, h=10)  # blind, for M2 standoffs


def phase0_base() -> cq.Workplane:
    """Base: the same camera mast + LED ring as the machine's station, plus two sockets for 2020 posts."""
    ow = L.POCKET_W + 2 * 12
    px = ow / 2 + 11
    plate = cbox(0, 0, 2, 2 * px + 40, 130, 4)
    body = plate.union(camera_mast(0.0))
    for sx in (-1, 1):
        body = body.union(cbox(sx * px, 0, 12, 28, 28, 24))
    for sx in (-1, 1):  # cut after the union, or the 4 mm plate fills the socket floor
        body = body.cut(cbox(sx * px, 0, P0_SOCKET_FLOOR + 12, 20.4, 20.4, 24))
        body = holes_y(body, [(sx * px, 16)], M5_CLR)
    return body


def phase0_parts(compression: float = L.CUP_HANG, lift: float = 0.0) -> list[Part]:
    """The Phase 0A jig, occluder included; ``compression`` = the occluder buffer's travel (as in head_parts), ``lift`` = how
    far the occluder mount (with the stub and everything on it) is slid up its post (P0_FACE_UP_LIFT for the face-up pass)."""
    ow = L.POCKET_W + 2 * 12
    parts = [Part("p0_base", phase0_base(), PETG, "printed", "static"),
             Part("p0_station_camera", station_camera(0, 0, 0.0), GREEN, "purchased", "static")]
    for sx in (-1, 1):
        parts.append(Part(f"p0_post_{sx}", box(sx * (ow / 2 + 11) - 10, -10, P0_SOCKET_FLOOR, sx * (ow / 2 + 11) + 10, 10, P0_SOCKET_FLOOR + P0_POST), ALU, "purchased", "static"))
    parts.append(Part("p0_tray", phase0_tray().translate((0, 0, P0_SLAB_Z)), PETG, "printed", "static"))
    parts.append(Part("p0_slab", slab(0, 0, P0_SLAB_Z), SLAB, "slab", "static"))
    parts.append(Part("p0_label", slab_label(0, 0, P0_SLAB_Z), LABEL, "slab", "static"))
    parts.append(Part("p0_top", phase0_top().translate((0, 0, P0_BAR_Z0)), PETG, "printed", "static"))
    zs, ly = P0_BAR_TOP + p0_board_spacer(), CAM_DY  # board underside; lens offset as on the machine
    cam = cbox(0, ly, zs + 5, 38, 38, 10).union(cbox(0, ly, (P0_TOP_Z + 6 + zs) / 2, 16, 16, zs - P0_TOP_Z - 6)).union(cyl((0, ly, P0_TOP_Z), 14, 6))
    parts.append(Part("p0_head_camera", cam, GREEN, "purchased", "static"))
    parts += head_ring_parts(0.0, ly, P0_TOP_Z, "p0_", "static") + station_ring_parts(0.0, 0.0, 0.0, "p0_station")
    parts += phase0_occluder(compression, lift)
    return parts


def phase0_occluder(compression: float = L.CUP_HANG, lift: float = 0.0) -> list[Part]:
    """The machine's occluder set under the jig's head camera, on its arm stub and mount (same functions as the machine)."""
    c = P0_OCC_C + lift
    yc, z0 = L.ARM_TO_CUP, c + ARM_Z[0]
    parts = occluder_parts(0.0, 0.0, c, compression, prefix="p0_", group="static")
    parts.append(Part("p0_arm_stub", box(-10, yc - 10, z0, 10, yc + 10, z0 + P0_STUB), ALU, "purchased", "static", note=f"2020 x {P0_STUB:.0f}"))
    parts.append(Part("p0_occluder_mount", phase0_occluder_mount().translate((0, 0, c + P0_MOUNT_Z[0])), PETG, "printed", "static"))
    return parts


# --------------------------------------------------------------------------- slabs


def slab(x, y, z_bottom) -> cq.Workplane:
    return cbox(x, y, z_bottom + SLAB_T / 2, SLAB_W, SLAB_H, SLAB_T)


def slab_label(x, y, z_bottom) -> cq.Workplane:
    ly = y - SLAB_H / 2 + 5 + 10  # label toward the front (-Y)
    return cbox(x, ly, z_bottom + SLAB_T / 2, 70, 20, SLAB_T * 0.6)


def stacks(fill: dict[int, int] | None = None) -> list[Part]:
    """Slab stacks; fill maps pocket index -> count (default: start-of-run state)."""
    out: list[Part] = []
    for p in L.pockets():
        n = (fill or {}).get(p.index, L.STACK_MAX if p.role == "source" else 0)
        if n <= 0:
            continue
        stack = box(p.x - SLAB_W / 2, p.y - SLAB_H / 2, 0, p.x + SLAB_W / 2, p.y + SLAB_H / 2, n * SLAB_T)
        lab = box(p.x - 35, p.y - SLAB_H / 2 + 5, 0.4, p.x + 35, p.y - SLAB_H / 2 + 25, n * SLAB_T - 0.4)
        out.append(Part(f"stack_{p.index}", stack, SLAB, "slab", "static", meta={"count": n}))
        out.append(Part(f"labels_{p.index}", lab, LABEL, "slab", "static"))
    return out


# --------------------------------------------------------------------------- assembly


def machine(cup_x: float, c: float, held_slab: bool = False, fill: dict[int, int] | None = None, with_slabs: bool = True, roof: bool = False, fasteners: bool = True,
            seated: bool = False) -> list[Part]:
    """``seated``: the held slab rests on something (probe tripped, buffer compressed); otherwise the free cup hangs CUP_HANG below c."""
    parts = frame_parts(cup_x) + bed_parts() + carriage_parts(cup_x, c) + head_parts(cup_x, c)
    if not roof:
        parts = [p for p in parts if p.name != "light_roof"]
    if not fasteners:
        parts = [p for p in parts if p.kind != "fastener"]
    if with_slabs:
        parts += stacks(fill)
    if held_slab:
        z0 = c - (0.0 if seated else L.CUP_HANG) - SLAB_T
        parts.append(Part("held_slab", slab(cup_x, L.Y_ROW, z0), SLAB, "slab", "head"))
        parts.append(Part("held_label", slab_label(cup_x, L.Y_ROW, z0), LABEL, "slab", "head"))
    return parts


def _flip_x(shape, deg):
    return shape.rotate((0, 0, 0), (1, 0, 0), deg)


def printed_catalog() -> list[tuple[str, cq.Workplane, int, str]]:
    """(name, shape in print orientation, qty, notes) for every printed part."""
    off = L.ARM_TO_CUP
    return [
        ("station_mount", station_mount(), 1, "PETG black, 3 walls, 25% infill; ribbon slot bridges"),
        ("x_motor_mount", _flip_x(x_motor_mount(), -90), 1, "PETG, beam face down (as exported), 5 walls, 40% infill"),
        ("x_bumper_L", _flip_x(x_bumper(), -90), 1, "PETG, beam face down (as exported), 4 walls, 40% infill"),
        ("x_idler_mount", x_idler_mount(), 1, "PETG, foot down, 5 walls, 40% infill"),
        ("x_idler_slider", x_idler_slider(), 1, "PETG, as exported, 5 walls, 50% infill"),
        ("x_bracket", _flip_x(x_bracket(), 90), 1, "PETG, print flat on its spine face (as exported), 6 walls, 50% infill; the finger off its left edge works the X home switch"),
        ("belt_clamp", belt_clamp(), 2, "PETG, flat, 100% infill"),
        ("z_motor_mount", _flip_x(z_motor_mount(), 180), 1, "PETG, motor face down, tab up, 5 walls, 40% infill"),
        ("z_end_cap", z_end_cap(), 1, "PETG, as exported (lips up), 5 walls, 50% infill"),
        ("z_plate", _flip_x(z_plate(), -90), 1, "PETG, carriage face down, nut shelf up, 6 walls, 50% infill; the switch chamfer at the top right starts at the bed (45 deg)"),
        ("head_foot", head_foot(off), 1, "PETG, foot down (as exported), 5 walls, 40% infill; clear the 1.9 mm flag slot and the board slots with a hacksaw blade"),
        ("camera_bracket", _flip_x(camera_bracket(off), 180), 1, "PETG matte black, shelf face down (as exported); the ring seat bridges ~30 mm between its 4 legs (tree supports there if your printer sags)"),
        ("gate_post_L", gate_post("L"), 1, "PETG, upright on its foot (as exported), 10 mm brim, 4 walls; needs 230 mm Z height, else print lying on its side with supports"),
        ("gate_post_R", gate_post("R"), 1, "PETG, upright on its foot (as exported), 10 mm brim, 4 walls; needs 230 mm Z height, else print lying on its side with supports"),
        ("drill_template", drill_template(), 1, "PLA/PETG, 0.2 mm, 100% infill bosses (build tool)"),
        ("phase0_base", phase0_base(), 1, "PLA/PETG black (Phase 0 test jig)"),
        ("phase0_tray", phase0_tray(), 1, "PLA/PETG (Phase 0 test jig), ledges down"),
        ("phase0_top", _flip_x(phase0_top(), 180), 1, "PLA/PETG (Phase 0 test jig), ring up"),
        ("phase0_occluder_mount", phase0_occluder_mount(), 1, "PLA/PETG (Phase 0 test jig), flat on its beam (as exported), 4 walls, 30% infill"),
        ("carry_sensor_mount", carry_sensor_mount().rotate((0, 0, 0), (0, 1, 0), 90), 1, "PETG, flat on its spine face (as exported), 4 walls, 40% infill"),
        ("carry_flag_arm", carry_flag_arm(), 1, "PETG, standing on its bottom face (as exported), 4 walls, 40% infill"),
        ("x_switch_mount", _flip_x(x_switch_mount(), -90), 1, "PETG, front plate down (as exported), 4 walls, 40% infill; X home switch on 2 x M2x12, 2 x M5x10 button heads"),
        ("z_switch_mount", z_switch_mount().rotate((0, 0, 0), (0, 1, 0), -90), 1, "PETG, spine plate down (as exported), 4 walls, 40% infill; Z top switch on 2 x M2x12, 2 x M5x10 button heads"),
        ("awl_adapter", awl_adapter(), 1, "PETG (build tool) + M5 heat-set insert + 3 mm steel pin"),
        ("fill_gauge", _flip_x(fill_gauge(), 90), 2, "PLA, flat (as exported) (loading tool)"),
    ]
