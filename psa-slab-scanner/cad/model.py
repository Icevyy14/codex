"""SlabRail parametric model (CadQuery).

Everything is built from layout.py:
  * static: base, bed, guide rods, read station, uprights, X beam + rail, X motor/idler
  * carriage (moves in X): X carriage, X bracket, Z spine + rail, Z motor
  * head (moves in Z): Z carriage, Z plate, drop arm, cup + spring buffer, contact sensor, camera
  * printed parts (exported individually as STL/STEP in print orientation)

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


M3_CLR, M5_CLR = 3.4, 5.5
NEMA = 42.3


@dataclass
class Part:
    name: str
    shape: cq.Workplane
    color: tuple[float, float, float, float]
    kind: str  # printed | purchased | slab | wood | foam
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
X_RAIL_LEN = 1300.0
X_RAIL_X0 = (T["x"][0] + T["x"][1]) / 2 - X_RAIL_LEN / 2
X_MOTOR_X = X_RAIL_X0 + X_RAIL_LEN + 32
X_IDLER_X = X_RAIL_X0 - 22
X_PULLEY_Z = Z_BEAM_TOP + 9.0  # lower belt strand 2.6 mm above the beam top
X_BELT_Y = (4.0, 13.0)  # belt width band, measured from the beam front face
ROOF_Z = 690.0
GATE_X = (GX0 - 12, GX1 + 12)  # overfill light-beam posts, just outside the end rods


def cut_list() -> list[tuple[str, str, float, int]]:
    """(profile, use, length mm, qty) - purchased cut-to-length extrusions."""
    return [
        ("2040", "base rail (lying flat, under the bed)", round(BED_X1 - BED_X0), 2),
        ("4040", "upright", round(Z_BEAM_BOT - Z_BASE_TOP), 2),
        ("4040", "X beam (on top of the uprights)", round(BEAM_X1 - BEAM_X0), 1),
        ("2040", "Z spine", L.Z_SPINE_LEN, 1),
        ("2020", "head drop arm", round(ARM_Z[1] - ARM_Z[0]), 1),
    ]


# --------------------------------------------------------------------------- static


def frame_parts() -> list[Part]:
    parts: list[Part] = []
    for i, y in enumerate(BASE_RAIL_YS):
        parts.append(Part(f"base_rail_{i}", box(BED_X0, y - 20, Z_BASE_BOT, BED_X1, y + 20, Z_BASE_TOP), ALU, "purchased", "static"))
    for x, side in ((XL, "L"), (XR, "R")):
        parts.append(Part(f"upright_{side}", box(x - 20, BEAM_Y0, Z_BASE_TOP, x + 20, BEAM_Y1, Z_BEAM_BOT), ALU, "purchased", "static"))
        parts.append(Part(f"foot_{side}", cbox(x, (BED_Y0 + BED_Y1) / 2, Z_BASE_BOT - 4, 60, BED_Y1 - BED_Y0, 8), BLACK, "purchased", "static", note="rubber foot strip"))
    parts.append(Part("x_beam", box(BEAM_X0, BEAM_Y0, Z_BEAM_BOT, BEAM_X1, BEAM_Y1, Z_BEAM_TOP), ALU, "purchased", "static"))
    parts.append(Part("x_rail", box(X_RAIL_X0, BEAM_Y0 - L.MGN12_RAIL_H, L.X_BEAM_Z - 6, X_RAIL_X0 + X_RAIL_LEN, BEAM_Y0, L.X_BEAM_Z + 6), STEEL, "purchased", "static", note="MGN12 1300 mm"))
    parts.append(Part("bed_plywood", box(BED_X0, BED_Y0, Z_BED_BOT, BED_X1, BED_Y1, Z_BED_TOP), WOOD, "wood", "static", note="18 mm plywood"))
    # X drive: GT2 loop in a vertical plane just above the beam top
    xm, xi, pz = X_MOTOR_X, X_IDLER_X, X_PULLEY_Z
    parts.append(Part("x_motor", cbox(xm, BEAM_Y0 + 40 + 6 + 24, pz, NEMA, 48, NEMA), BLACK, "purchased", "static", note="NEMA17 48 mm"))
    parts.append(Part("x_motor_mount", x_motor_mount().translate((xm, BEAM_Y0, Z_BEAM_TOP)), PETG, "printed", "static"))
    parts.append(Part("x_idler_mount", x_idler_mount().translate((xi, BEAM_Y0, Z_BEAM_TOP)), PETG, "printed", "static"))
    for zz, nm in ((pz - 6.4, "lo"), (pz + 6.4, "hi")):
        parts.append(Part(f"x_belt_{nm}", box(xi, BEAM_Y0 + X_BELT_Y[0], zz - 0.7, xm, BEAM_Y0 + X_BELT_Y[1], zz + 0.7), BLACK, "purchased", "static"))
    parts.append(Part("x_pulley", cyl((xm, BEAM_Y0 + X_BELT_Y[0] - 1, pz), 16, 11, (0, 1, 0)), STEEL, "purchased", "static"))
    parts.append(Part("x_idler", cyl((xi, BEAM_Y0 + X_BELT_Y[0] - 1, pz), 18, 11, (0, 1, 0)), STEEL, "purchased", "static"))
    parts.append(Part("light_roof", box(BED_X0, BED_Y0 - 40, ROOF_Z, BED_X1, BED_Y1 + 20, ROOF_Z + 5), (0.05, 0.05, 0.06, 0.35), "purchased", "static", note="black foam board light roof"))
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
        parts.append(Part(f"gate_post_{side}", gate_post(side).translate((x, L.Y_ROW, 0)), PETG, "printed", "static"))
    parts.append(Part("gate_beam", cyl((GATE_X[0], L.Y_ROW, L.GATE_Z), 1.2, GATE_X[1] - GATE_X[0], (1, 0, 0)), (1.0, 0.1, 0.1, 0.6), "purchased", "static", note="laser beam (not a part)"))
    parts.append(Part("station_camera", cbox(SX, SY, 14, 25, 24, 6).union(cyl((SX, SY, 17), 9, 6)), GREEN, "purchased", "static", note="Pi Camera Module 3"))
    return parts


def station_mount() -> cq.Workplane:
    """Upward camera mount for the station cell: base plate screwed to the bed (sits on the black pad),
    camera board at Z~14, LED ring around the lens."""
    base = cbox(0, 0, -1.5, 80, 130, 3)  # replaces the pad in the station cell (same thickness)
    mast = cbox(0, 0, 8, 34, 34, 13).cut(cbox(0, 0, 10, 26, 26, 12))
    ring = cyl((0, 0, 0), 60, 20).cut(cyl((0, 0, -1), 52, 22))  # LED ring seat, lip at the top
    body = base.union(mast).union(ring)
    body = holes_z(body, [(-34, -58), (34, -58), (-34, 58), (34, 58)], 4.5)  # wood screws
    body = holes_z(body, [(-10.5, -6.25), (10.5, -6.25), (-10.5, 6.25), (10.5, 6.25)], 2.2)  # CM3 holes
    body = body.cut(cbox(0, 18, 9, 18, 10, 9))  # FPC cable exit
    return body


def gate_post(side: str) -> cq.Workplane:
    """Holds the laser module (left) or the laser-receiver module (right) at GATE_Z on the row centre line.
    Local origin: beam axis at (0, 0, GATE_Z) projected to the bed."""
    s = -1 if side == "L" else 1  # posts stand outside the row
    foot = cbox(s * 4, 0, 1.5, 22, 50, 3)
    foot = holes_z(foot, [(s * 4, -18), (s * 4, 18)], 4.5)
    post = cbox(s * 4, 0, L.GATE_Z / 2 + 6, 10, 16, L.GATE_Z + 12)
    post = post.cut(cyl((s * 15, 0, L.GATE_Z), 6.2, 30, (-s, 0, 0)))  # 6 mm laser / receiver barrel
    post = post.cut(cbox(s * 4, 0, L.GATE_Z + 9, 12, 2, 5))  # wire slot
    return foot.union(post)


def x_motor_mount() -> cq.Workplane:
    """L-bracket: foot bolts to the X-beam top, upright face behind the beam carries the motor (shaft along -Y).
    Local origin: X = motor axis, Y = beam front face, Z = beam top."""
    t = 6.0
    foot = box(-26, 0, 0, 26, 40, t)
    foot = holes_z(foot, [(-16, 10), (16, 10), (-16, 30), (16, 30)], M5_CLR)
    face = box(-26, 40, 0, 26, 40 + t, X_PULLEY_Z - Z_BEAM_TOP + 26)
    face = face.cut(cyl((0, 39, X_PULLEY_Z - Z_BEAM_TOP), 23, t + 2, (0, 1, 0)))
    face = holes_y(face, [(dx, X_PULLEY_Z - Z_BEAM_TOP + dz) for dx in (-15.5, 15.5) for dz in (-15.5, 15.5)], M3_CLR)
    rib = box(-3, 0, t, 3, 40, 22)
    return foot.union(face).union(rib)


def x_idler_mount() -> cq.Workplane:
    """Two cheeks on the beam top hold an M5 idler axle (along Y); slotted for belt tension."""
    t = 5.0
    foot = box(-18, 0, 0, 18, 40, t)
    foot = holes_z(foot, [(-12, 30), (12, 30)], M5_CLR)
    cheek_a = box(-10, X_BELT_Y[0] - 5, 0, 10, X_BELT_Y[0] - 2, X_PULLEY_Z - Z_BEAM_TOP + 12)
    cheek_b = box(-10, X_BELT_Y[1] + 2, 0, 10, X_BELT_Y[1] + 5, X_PULLEY_Z - Z_BEAM_TOP + 12)
    body = foot.union(cheek_a).union(cheek_b)
    body = body.cut(box(-12, X_BELT_Y[0] - 2, t, 12, X_BELT_Y[1] + 2, 40))  # belt/idler gap
    for dx in (-3, 0, 3):  # slot = row of overlapping holes
        body = holes_y(body, [(dx, X_PULLEY_Z - Z_BEAM_TOP)], 5.3)
    return body


# --------------------------------------------------------------------------- carriage (moves with X)


def carriage_parts(cup_x: float) -> list[Part]:
    yb = BEAM_Y0
    parts: list[Part] = []
    parts.append(Part("x_carriage", cbox(cup_x, yb - 10.5, L.X_BEAM_Z, L.MGN12H_L, 5, L.MGN12H_W), STEEL, "purchased", "carriage"))
    parts.append(Part("x_bracket", x_bracket().translate((cup_x, yb - L.MGN12_H, 0)), PETG, "printed", "carriage"))
    spine_y1 = yb - L.MGN12_H - L.X_BRACKET_T
    ztop = L.Z_SPINE_BOTTOM + L.Z_SPINE_LEN
    parts.append(Part("z_spine", box(cup_x - 20, spine_y1 - 20, L.Z_SPINE_BOTTOM, cup_x + 20, spine_y1, ztop), ALU, "purchased", "carriage"))
    parts.append(Part("z_rail", box(cup_x - 6, spine_y1 - 20 - L.MGN12_RAIL_H, L.Z_SPINE_BOTTOM + 1, cup_x + 6, spine_y1 - 20, ztop - 9), STEEL, "purchased", "carriage", note="MGN12 330 mm"))
    parts.append(Part("z_motor_mount", z_motor_mount().translate((cup_x, spine_y1 - 20, ztop)), PETG, "printed", "carriage"))
    parts.append(Part("z_motor", cbox(cup_x + 24, spine_y1 - 20 - 23, ztop + 5 + 24, NEMA, NEMA, 48), BLACK, "purchased", "carriage", note="NEMA17 + 400 mm T8x8 integrated lead screw"))
    parts.append(Part("z_leadscrew", cyl((cup_x + 24, spine_y1 - 20 - 23, L.Z_SPINE_BOTTOM + 10), 8, ztop + 5 - L.Z_SPINE_BOTTOM - 10), STEEL, "purchased", "carriage"))
    return parts


def x_bracket() -> cq.Workplane:
    """Plate in the XZ plane: X carriage (MGN12H) on its back, Z spine (2040) on its front.
    Local origin: X = cup axis, Y = X-carriage front face (plate grows toward -Y), Z = machine Z.
    The top tab reaches over the beam to clamp the upper X-belt strand."""
    t = L.X_BRACKET_T
    zb = L.X_BEAM_Z
    plate = box(-30, -t, zb - 70, 30, 0, X_PULLEY_Z + 14.4)
    plate = holes_y(plate, [(dx, zb + dz) for dx in (-10, 10) for dz in (-10, 10)], M3_CLR)  # MGN12H 20x20
    plate = holes_y(plate, [(dx, z) for dx in (-10, 10) for z in (zb - 60, zb - 40)], M5_CLR)  # Z spine T-nuts
    zb_hi = X_PULLEY_Z + 6.4
    tab = box(-30, 0, zb_hi - 6, 30, L.MGN12_H + X_BELT_Y[1] + 4, zb_hi + 8)
    tab = tab.cut(box(-31, L.MGN12_H + X_BELT_Y[0] - 0.5, zb_hi - 1.2, 31, L.MGN12_H + X_BELT_Y[1] + 0.5, zb_hi + 1.2))
    tab = tab.cut(box(-8, -1, zb_hi - 7, 8, L.MGN12_H + X_BELT_Y[1] + 5, zb_hi + 9))  # split: belt ends clamp each side
    return plate.union(tab)


def z_motor_mount() -> cq.Workplane:
    t = 5.0
    plate = box(-22, -48, 0, 47, 0, t)
    plate = plate.cut(cyl((24, -23, -1), 23, t + 2))
    plate = holes_z(plate, [(24 + dx, -23 + dy) for dx in (-15.5, 15.5) for dy in (-15.5, 15.5)], M3_CLR)
    back = box(-22, -2, -30, 22, 0, t)  # tab down the spine front, bolts into the slot
    plate = plate.union(back)
    plate = holes_y(plate, [(-10, -18), (10, -18)], M5_CLR)
    return plate


# --------------------------------------------------------------------------- head (moves with Z)

CUP_D = 25.0
BUFFER_BODY = (16.0, 20.0, 62.0)  # dia, z0, z1 above cup face
FOOT_Z = (62.0, 75.0)
CAM_Z = L.CAM_TO_SLAB  # lens face height above the cup face (= held slab back)
ARM_Z = (FOOT_Z[0], L.Z_CARRIAGE_ABOVE_CUP + 55.0)


def head_parts(cup_x: float, c: float) -> list[Part]:
    cup_y = L.Y_ROW
    parts: list[Part] = []
    zc_bottom = c + L.Z_CARRIAGE_ABOVE_CUP
    zrail_front = BEAM_Y0 - L.MGN12_H - L.X_BRACKET_T - 20 - L.MGN12_RAIL_H
    parts.append(Part("z_carriage", box(cup_x - 13.5, zrail_front - 5, zc_bottom, cup_x + 13.5, zrail_front, zc_bottom + L.MGN12H_L), STEEL, "purchased", "head"))
    zp_front = zrail_front - 5 - L.Z_PLATE_T
    parts.append(Part("z_plate", z_plate().translate((cup_x, zrail_front - 5, zc_bottom)), PETG, "printed", "head"))
    arm_y1 = zp_front
    parts.append(Part("drop_arm", box(cup_x - 10, arm_y1 - 20, c + ARM_Z[0], cup_x + 10, arm_y1, c + ARM_Z[1]), ALU, "purchased", "head", note="2020"))
    off = arm_y1 - 10 - cup_y  # = ARM_TO_CUP
    parts.append(Part("head_foot", head_foot(off).translate((cup_x, cup_y, c)), PETG, "printed", "head"))
    parts.append(Part("camera_bracket", camera_bracket(off).translate((cup_x, cup_y, c)), PETG, "printed", "head"))
    parts.append(Part("buffer", cyl((cup_x, cup_y, c + BUFFER_BODY[1]), BUFFER_BODY[0], BUFFER_BODY[2] - BUFFER_BODY[1]).union(cyl((cup_x, cup_y, c + 8), 6, 12)).union(cyl((cup_x, cup_y, c + FOOT_Z[1]), 6, 22)), STEEL, "purchased", "head", note="M10 spring buffer, 25 mm stroke"))
    parts.append(Part("cup", cyl((cup_x, cup_y, c), CUP_D, 8), BLACK, "purchased", "head", note="25 mm non-marking cup"))
    parts.append(Part("head_camera", cbox(cup_x, cup_y, c + CAM_Z + 12, 38, 38, 10).union(cyl((cup_x, cup_y, c + CAM_Z), 14, 7)), GREEN, "purchased", "head", note="USB 8MP IMX179, M12 3.6 mm"))
    parts.append(Part("contact_sensor", cbox(cup_x, cup_y + 21, c + 92, 33, 10.5, 12), BLACK, "purchased", "head", note="slotted optical endstop"))
    return parts


def z_plate() -> cq.Workplane:
    """Printed Z carriage plate. Local origin: X = cup axis, Y = Z-carriage front face, Z = carriage bottom."""
    t = L.Z_PLATE_T
    plate = box(-30, -t, -5, 40, 0, 55)
    plate = holes_y(plate, [(dx, 22.7 + dz) for dx in (-10, 10) for dz in (-10, 10)], M3_CLR)  # MGN12H
    plate = holes_y(plate, [(0, 5), (0, 45)], M5_CLR)  # drop arm (2020) slot bolts
    nut = box(12, -t - 15, 40, 36, 0, 48)  # shelf for the T8 nut, screw at X+24
    nut = nut.cut(cyl((24, -23, 30), 10.5, 30)).cut(cyl((24, -23, 30), 3.0, 30))
    return plate.union(nut)


def head_foot(arm_offset: float) -> cq.Workplane:
    """Holds the spring buffer (M10) on the cup axis and the contact sensor; bolts to the drop-arm end."""
    z0, z1 = FOOT_Z
    body = box(-15, -15, z0, 15, arm_offset + 10, z1)
    body = body.union(box(-12, arm_offset - 10, z0, 12, arm_offset + 12, z1 + 18))  # sleeve around the arm end
    body = body.cut(box(-10.2, arm_offset - 10.2, z0 + 3, 10.2, arm_offset + 10.2, z1 + 20))
    body = body.cut(cyl((0, 0, z0 - 1), 10.4, z1 - z0 + 2))  # M10 buffer thread, nuts both sides
    body = holes_x(body, [(arm_offset, z1 + 9)], M5_CLR)
    body = body.union(box(-16.5, 26.5, z1, 16.5, 28.5, z1 + 24))  # sensor post on the arm side (+Y)
    body = holes_y(body, [(-9.5, z1 + 17), (9.5, z1 + 17)], 2.9)  # optical endstop board, M3 self-tap
    return body


def camera_bracket(arm_offset: float) -> cq.Workplane:
    """Clamps the drop arm; holds the head camera board level, lens on the cup axis CAM_Z above the cup face,
    with a 50 mm LED ring around the lens. Print in matte black."""
    z0 = CAM_Z
    shelf = box(-24, -24, z0 + 4, 24, arm_offset - 10, z0 + 8)
    shelf = shelf.cut(cyl((0, 0, z0), 16, 20))  # lens hole
    shelf = holes_z(shelf, [(dx, dy) for dx in (-16, 16) for dy in (-16, 16)], 2.2)  # 32 mm board holes
    ring = cyl((0, 0, z0 - 4), 56, 8).cut(cyl((0, 0, z0 - 5), 46, 10))
    clamp = box(-12, arm_offset - 12, z0 - 6, 12, arm_offset + 12, z0 + 24).cut(box(-10.2, arm_offset - 10.2, z0 - 7, 10.2, arm_offset + 10.2, z0 + 25))
    clamp = holes_x(clamp, [(arm_offset, z0 + 9)], M5_CLR)
    return shelf.union(ring).union(clamp)


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
    body = cyl((0, 0, 0), 14, 18).cut(cyl((0, 0, 10), 5.0, 9))  # M5 heat-set insert pocket at the top
    body = body.cut(cyl((0, 0, -1), 3.1, 12))
    return body


def fill_gauge() -> cq.Workplane:
    """Stand it in a pocket: slabs must not stack above its top notch (the MAX line)."""
    g = box(0, 0, 0, 12, 4, L.MAX_LINE)
    for k in range(0, 31, 5):
        g = g.cut(box(-1, -1, k * 6.6, 3, 5, k * 6.6 + 0.8))
    return g.union(box(0, 0, L.MAX_LINE, 30, 4, L.MAX_LINE + 4))


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


def machine(cup_x: float, c: float, held_slab: bool = False, fill: dict[int, int] | None = None, with_slabs: bool = True, roof: bool = False) -> list[Part]:
    parts = frame_parts() + bed_parts() + carriage_parts(cup_x) + head_parts(cup_x, c)
    if not roof:
        parts = [p for p in parts if p.name != "light_roof"]
    if with_slabs:
        parts += stacks(fill)
    if held_slab:
        parts.append(Part("held_slab", slab(cup_x, L.Y_ROW, c - SLAB_T), SLAB, "slab", "head"))
        parts.append(Part("held_label", slab_label(cup_x, L.Y_ROW, c - SLAB_T), LABEL, "slab", "head"))
    return parts


def printed_catalog() -> list[tuple[str, cq.Workplane, int, str]]:
    """(name, shape in print orientation, qty, notes) for every printed part."""
    off = L.ARM_TO_CUP
    return [
        ("station_mount", station_mount(), 1, "PETG black, 3 walls, 25% infill"),
        ("x_motor_mount", x_motor_mount(), 1, "PETG, 5 walls, 40% infill"),
        ("x_idler_mount", x_idler_mount(), 1, "PETG, 5 walls, 40% infill"),
        ("x_bracket", x_bracket().rotate((0, 0, 0), (1, 0, 0), 90), 1, "PETG, print flat on its back face, 6 walls, 50% infill"),
        ("z_motor_mount", z_motor_mount(), 1, "PETG, 5 walls, 40% infill"),
        ("z_plate", z_plate().rotate((0, 0, 0), (1, 0, 0), 90), 1, "PETG, print flat, 6 walls, 50% infill"),
        ("head_foot", head_foot(off), 1, "PETG, 5 walls, 40% infill"),
        ("camera_bracket", camera_bracket(off), 1, "PETG matte black, supports under the ring"),
        ("gate_post_L", gate_post("L"), 1, "PETG, print lying on its side, 4 walls"),
        ("gate_post_R", gate_post("R"), 1, "PETG, print lying on its side, 4 walls"),
        ("drill_template", drill_template(), 1, "PLA/PETG, 0.2 mm, 100% infill bosses (build tool)"),
        ("awl_adapter", awl_adapter(), 1, "PETG (build tool) + M5 heat-set insert + 3 mm steel pin"),
        ("fill_gauge", fill_gauge().rotate((0, 0, 0), (0, 1, 0), 90), 2, "PLA (loading tool)"),
    ]
