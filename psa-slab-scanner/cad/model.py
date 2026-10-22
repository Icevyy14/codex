"""SlabRail parametric model (CadQuery).

Everything is built from layout.py:
  * static: base, bed, guide rods, read station, uprights, X beam + rail, X motor/idler, X end bumpers
  * carriage (moves in X): X carriage, X bracket + belt clamps, Z spine + rail + end cap, Z motor
  * head (moves in Z): Z carriage, Z plate, drop arm, cup + spring buffer, contact sensor, camera
  * printed parts (exported individually as STL/STEP in print orientation)
  * fastener heads where a head could foul another part (kind "fastener"), so checks.py sees them

Purchased parts (extrusions, rails, motors, cameras) are simplified envelopes: accurate
where they interface with something, not cosmetically detailed.
"""

from __future__ import annotations

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
    kind: str  # printed | purchased | slab | wood | foam | fastener
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
    ]


# --------------------------------------------------------------------------- static


def frame_parts() -> list[Part]:
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
    return parts


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
    ring = cyl((0, 0, 0), 60, 20).cut(cyl((0, 0, -1), 52, 22))  # station LED ring seat, lip at the top
    body = mast.union(ring)
    boss_top = L.STATION_LENS_Z - CM3_H  # 11.5: the CM3 board back rests here
    for x, y in CM3_HOLES:  # M2 standoff bosses rising from the mast floor
        body = body.union(cyl((x, y, CAM_FLOOR_Z - 0.5), 5, boss_top - CAM_FLOOR_Z + 0.5))
    body = holes_z(body, CM3_HOLES, 1.8)  # M2 self-tapping
    body = body.cut(box(-9, 12, CAM_FLOOR_Z + 0.5, 9, 31, 13.5))  # FPC exit through the mast wall AND the ring wall
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
    post = post.cut(cyl((s * 15, 0, hz), 6.2, 30, (-s, 0, 0)))  # 6 mm laser / receiver barrel
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


def carriage_parts(cup_x: float) -> list[Part]:
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
    return parts


XB_CAR_HOLES = [(dx, L.X_RAIL_Z + dz) for dx in (-10, 10) for dz in (-10, 10)]  # MGN12H 20 x 20
XB_SPINE_HOLES = [(L.Z_SPINE_OFFSET_X + dx, z) for dx in (-10, 10) for z in (L.X_RAIL_Z - 70, L.X_RAIL_Z - 45)]
CLAMP_X = 19.0  # belt clamp centres, X from the cup axis
CLAMP_SCREW_Y = (L.MGN12_H + X_BELT_Y[0] - 4, L.MGN12_H + X_BELT_Y[1] + 4)  # x_bracket local Y of the clamp screws (12, 26)


def x_bracket() -> cq.Workplane:
    """Plate in the XZ plane: X carriage (MGN12H) on its back, Z spine (2040) on its front.
    Local origin: X = cup axis, Y = X-carriage front face (plate grows toward -Y), Z = machine Z.
    The top tab reaches back over the beam to clamp both ends of the upper X-belt strand: a GT2 rack on its
    floor, a printed belt_clamp cap on top, 2 x M3 + nut per belt end."""
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
    return plate.union(tab)


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

CUP_D = 25.0
BUFFER_BODY = (16.0, 20.0, 62.0)  # dia, z0, z1 above cup face
FOOT_Z = (62.0, 75.0)
CAM_Z = L.CAM_TO_SLAB  # lens face height above the cup face (= held slab back)
ARM_Z = (FOOT_Z[0] + 3.0, L.Z_CARRIAGE_ABOVE_CUP + 55.0)  # arm bottoms on head_foot's socket floor; top 3 mm under the z_plate top
Z_PLATE_ARM_BOLTS = (-12.0, 51.5)  # z_plate local Z: below and above the MGN12H block (0 .. 45.4)
SENSOR_POST_X = (26.5, 30.5)  # contact-sensor post on the +X side of the buffer (clear of the arm at Y >= 25)
# Head camera (ELP IMX179 board, M12 holder). [Guessing] board underside to lens front; MEASURE yours (BUILD_GUIDE 3.3).
HEAD_LENS_PROJ = 20.0
HEAD_RING_OD = 40.0  # head LED ring: 40 mm COB angel eye (a 60 mm ring would cut into the drop arm)
LENS_WINDOW_D = 25.0  # passes a 16 mm square M12 holder (22.6 mm diagonal)


def head_parts(cup_x: float, c: float) -> list[Part]:
    cup_y = L.Y_ROW
    parts: list[Part] = []
    zc_bottom = c + L.Z_CARRIAGE_ABOVE_CUP
    parts.append(Part("z_carriage", mgn12h(cup_x, Z_RAIL_FACE, zc_bottom, "z"), STEEL, "purchased", "head"))
    parts.append(Part("z_plate", z_plate().translate((cup_x, Z_CAR_FRONT, zc_bottom)), PETG, "printed", "head"))
    arm_y1 = Z_CAR_FRONT - L.Z_PLATE_T
    parts.append(Part("drop_arm", box(cup_x - 10, arm_y1 - 20, c + ARM_Z[0], cup_x + 10, arm_y1, c + ARM_Z[1]), ALU, "purchased", "head", note="2020"))
    off = arm_y1 - 10 - cup_y  # = ARM_TO_CUP
    parts.append(Part("head_foot", head_foot(off).translate((cup_x, cup_y, c)), PETG, "printed", "head"))
    parts.append(Part("camera_bracket", camera_bracket(off).translate((cup_x, cup_y, c)), PETG, "printed", "head"))
    parts.append(Part("buffer", cyl((cup_x, cup_y, c + BUFFER_BODY[1]), BUFFER_BODY[0], BUFFER_BODY[2] - BUFFER_BODY[1]).union(cyl((cup_x, cup_y, c + 8), 6, 12)).union(cyl((cup_x, cup_y, c + FOOT_Z[1]), 6, 22)), STEEL, "purchased", "head", note="M10 spring buffer, 25 mm stroke"))
    parts.append(Part("cup", cyl((cup_x, cup_y, c), CUP_D, 8), BLACK, "purchased", "head", note="25 mm non-marking cup"))
    zl, zs = c + CAM_Z, c + CAM_Z + HEAD_LENS_PROJ
    cam = cbox(cup_x, cup_y, zs + 5, 38, 38, 10).union(cbox(cup_x, cup_y, (zl + 6 + zs) / 2, 16, 16, zs - zl - 6)).union(cyl((cup_x, cup_y, zl), 14, 6))
    parts.append(Part("head_camera", cam, GREEN, "purchased", "head", note="USB 8MP IMX179, M12 3.6 mm"))
    sx0 = SENSOR_POST_X[0]
    parts.append(Part("contact_sensor", cbox(cup_x + sx0 - 10.5 / 2, cup_y, c + FOOT_Z[1] + 17, 10.5, 33, 12), BLACK, "purchased", "head", note="slotted optical endstop, slot facing the buffer rod"))
    for dx in (-10, 10):
        for dz in (-10, 10):  # MGN12H screws in counterbores on the arm side
            parts.append(head(f"fh_zcar_{dx:+d}{dz:+d}", (cup_x + dx, Z_CAR_FRONT - L.Z_PLATE_T + M3_CBORE[1], zc_bottom + 22.7 + dz), (0, -1, 0), M3_HEAD, "head"))
    for z in Z_PLATE_ARM_BOLTS:  # button heads in 2.5 mm recesses on the carriage side
        parts.append(head(f"fh_arm_{z:+.0f}", (cup_x, Z_CAR_FRONT - 2.5, zc_bottom + z), (0, 1, 0), M5_BUTTON, "head"))
    return parts


def z_plate() -> cq.Workplane:
    """Printed Z carriage plate. Local origin: X = cup axis, Y = Z-carriage front face, Z = carriage bottom.
    Its top edge (Z_PLATE_TOP) is the top hard stop against z_motor_mount."""
    t = L.Z_PLATE_T
    plate = box(-30, -t, -5, 40, 0, L.Z_PLATE_TOP)
    plate = plate.union(box(-14, -t, -20, 14, 0, -4.99))  # extension below the carriage for the lower arm bolt
    car = [(dx, 22.7 + dz) for dx in (-10, 10) for dz in (-10, 10)]  # MGN12H
    plate = holes_y(plate, car, M3_CLR)
    for x, z in car:  # counterbored: the drop arm covers X +/-10
        plate = plate.cut(cyl((x, -t - 1, z), M3_CBORE[0], 1 + M3_CBORE[1], (0, 1, 0)))
    plate = holes_y(plate, [(0, z) for z in Z_PLATE_ARM_BOLTS], M5_CLR)  # drop arm T-nuts, outside the MGN12H block
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
    """Holds the spring buffer (M10) on the cup axis and the contact sensor; bolts to the drop-arm end.
    The sensor post stands on the +X side, everything at |Y| <= 16.5, so the arm socket stays clear."""
    z0, z1 = FOOT_Z
    body = box(-15, -15, z0, 15, arm_offset + 10, z1)
    body = body.union(box(-12, arm_offset - 12, z0, 12, arm_offset + 12, z1 + 18))  # sleeve around the arm end
    body = body.union(box(15, -16.5, z0, SENSOR_POST_X[1], 16.5, z1))  # foot extension to the sensor post
    body = body.union(box(SENSOR_POST_X[0], -16.5, z1, SENSOR_POST_X[1], 16.5, z1 + 24))  # sensor post
    body = holes_x(body, [(-9.5, z1 + 17), (9.5, z1 + 17)], 2.9)  # optical endstop board, M3 self-tap
    # cuts last, so no later union refills them
    body = body.cut(box(-10.2, arm_offset - 10.2, z0 + 3, 10.2, arm_offset + 10.2, z1 + 20))  # arm socket
    body = body.cut(cyl((0, 0, z0 - 1), 10.4, z1 - z0 + 2))  # M10 buffer thread, nuts both sides
    body = holes_x(body, [(arm_offset, z1 + 9)], M5_CLR)
    return body


def ring_seat(z_bot: float, z_top: float, ring_od: float) -> cq.Workplane:
    """LED-ring seat: a 6 mm tube (ring pushed up against an inner lip, LEDs down), hung from z_top on four
    legs at 0/90/180/270 deg, so the board's 45-deg screw nuts stay clear."""
    rid = ring_od + 1.0
    tube = cyl((0, 0, z_bot), rid + 6, 6).cut(cyl((0, 0, z_bot - 1), rid, 8))
    tube = tube.union(cyl((0, 0, z_bot + 4), rid + 0.5, 2).cut(cyl((0, 0, z_bot + 3), rid - 8, 4)))
    if z_top > z_bot + 6:
        r = rid / 2 + 1.5
        for x, y in ((r, 0), (-r, 0), (0, r), (0, -r)):
            sx, sy = (3, 4) if y == 0 else (4, 3)
            tube = tube.union(cbox(x, y, (z_bot + 5.99 + z_top + 0.01) / 2, sx, sy, z_top - z_bot - 5.98))
    return tube


def camera_bracket(arm_offset: float) -> cq.Workplane:
    """Clamps the drop arm; holds the head camera board level, lens on the cup axis CAM_Z above the cup face.
    The board sits on the shelf, HEAD_LENS_PROJ above the lens front; the LED ring hangs around the lens.
    Print in matte black, shelf face down."""
    z0 = CAM_Z
    zs = z0 + HEAD_LENS_PROJ  # shelf top = board underside
    shelf = box(-24, -24, zs - 4, 24, arm_offset - 10, zs)
    shelf = shelf.cut(cyl((0, 0, zs - 10), LENS_WINDOW_D, 20))  # lens holder window
    shelf = holes_z(shelf, [(dx, dy) for dx in (-16, 16) for dy in (-16, 16)], 2.2)  # 32 mm board holes, M2 + nuts
    seat = ring_seat(z0 - 4, zs - 4, HEAD_RING_OD)
    clamp = box(-12, arm_offset - 12, z0 - 6, 12, arm_offset + 12, zs)
    body = shelf.union(seat).union(clamp)
    body = body.cut(box(-10.2, arm_offset - 10.2, z0 - 7, 10.2, arm_offset + 10.2, zs + 1))  # arm bore, cut last
    body = holes_x(body, [(arm_offset, z0 + 9)], M5_CLR)
    return body


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
    """Stand it in a pocket: slabs must not stack above its top notch (the MAX line)."""
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
P0_BAR_T, P0_BAR_SOCKET = 8.0, 5.0  # phase0_top thickness, blind socket depth
P0_SLAB_Z = L.STATION_LENS_Z + L.CAM_TO_SLAB  # slab front (bottom face) height = tray ledge top
P0_TOP_Z = P0_SLAB_Z + SLAB_T + L.CAM_TO_SLAB  # head lens front height
P0_BAR_Z0 = P0_SOCKET_FLOOR + P0_POST - P0_BAR_SOCKET  # 309: bridge underside, fixed by the posts
P0_BAR_TOP = P0_BAR_Z0 + P0_BAR_T  # 317
P0_TRAY_PLAY = 1.0  # total slab play in the tray recess. Set dims.SLAB_W/H to your LARGEST measured slab (sec. 1.2)
P0_LEDGE = 2.6  # ledge under each slab edge (centred slab); >= 2.1 mm even when shifted by the full play


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
    frame = frame.cut(cq.Workplane("XY").workplane(offset=3.0).rect(rw, rl).extrude(1.01, taper=-45))  # 1 mm lead-in
    frame = frame.cut(cq.Workplane("XY").workplane(offset=-4.01).rect(aw + 4, al + 4).extrude(2.01, taper=45))  # 45-deg underside chamfer: the 4 mm ledge doesn't shade the label edge
    frame = frame.cut(box(-25, -ol / 2 - 10, 0, 25, -ol / 2 + 10, 5))  # finger notch at the front to lift the slab out
    for sx in (-1, 1):  # clamps onto the 2020 posts
        clamp = cbox(sx * (ow / 2 + 11), 0, 6, 24, 24, 20).cut(cbox(sx * (ow / 2 + 11), 0, 6, 20.4, 20.4, 22))
        clamp = holes_x(clamp, [(0, 6)], M5_CLR)
        frame = frame.union(clamp)
    return frame


def phase0_top() -> cq.Workplane:
    """Bridge resting on the post tops (blind sockets), carrying the head camera board on M2 standoffs
    (height p0_board_spacer()) and the head LED ring. Local origin: bar underside, centre."""
    ow = L.POCKET_W + 2 * 12
    span = ow + 2 * 11
    bar = cbox(0, 0, P0_BAR_T / 2, span + 24, 50, P0_BAR_T)
    bar = bar.cut(cyl((0, 0, -1), LENS_WINDOW_D, 12))
    for sx in (-1, 1):
        bar = bar.cut(cbox(sx * span / 2, 0, P0_BAR_SOCKET / 2, 20.4, 20.4, P0_BAR_SOCKET))  # blind sockets
    seat = ring_seat(P0_TOP_Z - 4 - P0_BAR_Z0, 0.0, HEAD_RING_OD)
    body = bar.union(seat)
    return holes_z(body, [(dx, dy) for dx in (-16, 16) for dy in (-16, 16)], 1.8, z0=P0_BAR_T - 6, h=10)  # blind, for M2 standoffs


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


def phase0_parts() -> list[Part]:
    ow = L.POCKET_W + 2 * 12
    parts = [Part("p0_base", phase0_base(), PETG, "printed", "static"),
             Part("p0_station_camera", station_camera(0, 0, 0.0), GREEN, "purchased", "static")]
    for sx in (-1, 1):
        parts.append(Part(f"p0_post_{sx}", box(sx * (ow / 2 + 11) - 10, -10, P0_SOCKET_FLOOR, sx * (ow / 2 + 11) + 10, 10, P0_SOCKET_FLOOR + P0_POST), ALU, "purchased", "static"))
    parts.append(Part("p0_tray", phase0_tray().translate((0, 0, P0_SLAB_Z)), PETG, "printed", "static"))
    parts.append(Part("p0_slab", slab(0, 0, P0_SLAB_Z), SLAB, "slab", "static"))
    parts.append(Part("p0_label", slab_label(0, 0, P0_SLAB_Z), LABEL, "slab", "static"))
    parts.append(Part("p0_top", phase0_top().translate((0, 0, P0_BAR_Z0)), PETG, "printed", "static"))
    zs = P0_BAR_TOP + p0_board_spacer()  # board underside
    cam = cbox(0, 0, zs + 5, 38, 38, 10).union(cbox(0, 0, (P0_TOP_Z + 6 + zs) / 2, 16, 16, zs - P0_TOP_Z - 6)).union(cyl((0, 0, P0_TOP_Z), 14, 6))
    parts.append(Part("p0_head_camera", cam, GREEN, "purchased", "static"))
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
    parts = frame_parts() + bed_parts() + carriage_parts(cup_x) + head_parts(cup_x, c)
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
        ("x_bracket", _flip_x(x_bracket(), 90), 1, "PETG, print flat on its spine face (as exported), 6 walls, 50% infill"),
        ("belt_clamp", belt_clamp(), 2, "PETG, flat, 100% infill"),
        ("z_motor_mount", _flip_x(z_motor_mount(), 180), 1, "PETG, motor face down, tab up, 5 walls, 40% infill"),
        ("z_end_cap", z_end_cap(), 1, "PETG, as exported (lips up), 5 walls, 50% infill"),
        ("z_plate", _flip_x(z_plate(), -90), 1, "PETG, carriage face down, nut shelf up, 6 walls, 50% infill"),
        ("head_foot", head_foot(off), 1, "PETG, 5 walls, 40% infill"),
        ("camera_bracket", _flip_x(camera_bracket(off), 180), 1, "PETG matte black, shelf face down (as exported); the ring seat bridges ~30 mm between its 4 legs (tree supports there if your printer sags)"),
        ("gate_post_L", gate_post("L"), 1, "PETG, upright on its foot (as exported), 10 mm brim, 4 walls; needs 230 mm Z height, else print lying on its side with supports"),
        ("gate_post_R", gate_post("R"), 1, "PETG, upright on its foot (as exported), 10 mm brim, 4 walls; needs 230 mm Z height, else print lying on its side with supports"),
        ("drill_template", drill_template(), 1, "PLA/PETG, 0.2 mm, 100% infill bosses (build tool)"),
        ("phase0_base", phase0_base(), 1, "PLA/PETG black (Phase 0 test jig)"),
        ("phase0_tray", phase0_tray(), 1, "PLA/PETG (Phase 0 test jig), ledges down"),
        ("phase0_top", _flip_x(phase0_top(), 180), 1, "PLA/PETG (Phase 0 test jig), ring up"),
        ("awl_adapter", awl_adapter(), 1, "PETG (build tool) + M5 heat-set insert + 3 mm steel pin"),
        ("fill_gauge", _flip_x(fill_gauge(), 90), 2, "PLA, flat (as exported) (loading tool)"),
    ]
