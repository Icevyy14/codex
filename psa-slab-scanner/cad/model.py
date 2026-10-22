"""SlabStack parametric model (CadQuery).

Everything is built from layout.py. Three groups:
  * frame + bed (static)
  * gantry (moves in Y), carriage (moves in X), head (moves in Z)
  * printed parts (exported individually as STL/STEP in print orientation)

Purchased parts (extrusions, rails, motors, cameras) are simplified envelopes - accurate
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


M3, M3_CLR, M5_CLR = 3.0, 3.4, 5.5
NEMA = 42.3
NEMA_HOLES = 31.0


@dataclass
class Part:
    name: str
    shape: cq.Workplane
    color: tuple[float, float, float, float]
    kind: str  # printed | purchased | slab | wood | foam
    group: str  # static | gantry | carriage | head
    qty: int = 1
    note: str = ""
    print_shape: cq.Workplane | None = None  # print orientation (printed parts only)
    meta: dict = field(default_factory=dict)


ALU = (0.72, 0.74, 0.77, 1.0)
STEEL = (0.55, 0.57, 0.6, 1.0)
BLACK = (0.12, 0.12, 0.13, 1.0)
PETG = (0.95, 0.45, 0.1, 1.0)
PETG2 = (0.2, 0.45, 0.85, 1.0)
WOOD = (0.82, 0.68, 0.48, 1.0)
DOWEL = (0.86, 0.75, 0.55, 1.0)
PAD = (0.25, 0.25, 0.3, 1.0)
SLAB = (0.85, 0.92, 1.0, 0.55)
LABEL = (0.95, 0.95, 0.95, 1.0)
GREEN = (0.1, 0.55, 0.25, 1.0)

# --------------------------------------------------------------------------- frame geometry

GX0, GX1, GY0, GY1 = L.grid_extent()
SX, SY = L.station_xy()
CX_MID = (GX0 + GX1) / 2  # 226
BED_X0, BED_X1 = GX0 - 22, GX1 + 22
BED_Y0, BED_Y1 = SY - L.STATION_BOX[1] / 2 - 25, GY1 + 12
Z_BED_TOP = -L.PAD_T
Z_BED_BOT = Z_BED_TOP - L.BED_T
Z_BASE_TOP = Z_BED_BOT
Z_BASE_BOT = Z_BASE_TOP - 20

T = L.travel_needed()
X_SIDE = 296.0  # Y-beam centre distance from CX_MID
XL, XR = CX_MID - X_SIDE, CX_MID + X_SIDE  # Y-beam / upright centre lines
Y_RAIL_LEN = 550.0
BEAM_Y_MIN = T["y"][0] + L.Y_CUP_TO_BEAM  # beam front face range
BEAM_Y_MAX = T["y"][1] + L.Y_CUP_TO_BEAM
Y_RAIL_Y0 = BEAM_Y_MIN + 10 - L.MGN12H_L / 2 - 15
Y_BEAM_Y0, Y_BEAM_Y1 = min(BED_Y0, Y_RAIL_Y0 - 10), Y_RAIL_Y0 + Y_RAIL_LEN + 70
Z_YBEAM_TOP = L.Y_RAIL_TOP - L.MGN12_RAIL_H
Z_YBEAM_BOT = Z_YBEAM_TOP - 40
UPRIGHT_LEN = Z_YBEAM_BOT - Z_BASE_TOP
X_BEAM_X0, X_BEAM_X1 = XL - 30, XR + 30
X_RAIL_LEN = 450.0
X_RAIL_X0 = CX_MID - X_RAIL_LEN / 2
Z_XBEAM_BOT = L.X_BEAM_BOTTOM
Z_XBEAM_TOP = Z_XBEAM_BOT + 40
Z_XRAIL_C = (Z_XBEAM_BOT + Z_XBEAM_TOP) / 2
CROSS_YS = (BED_Y0 + 20, (BED_Y0 + BED_Y1) / 2, BED_Y1 - 20)
X_MOTOR_X = X_RAIL_X0 + X_RAIL_LEN + 32
X_IDLER_X = X_RAIL_X0 - 22
X_PULLEY_Z = Z_XBEAM_TOP + 9.0  # lower strand 1.9 mm above the beam top
X_BELT_Y = (4.0, 13.0)  # belt width band, measured from the beam front face


def cut_list() -> list[tuple[str, str, float, int]]:
    """(profile, use, length mm, qty) - purchased cut-to-length extrusions."""
    return [
        ("2040", "base side rail (lying flat)", round(Y_BEAM_Y1 - BED_Y0, 0), 2),
        ("2040", "base cross member (lying flat)", round(XR - XL - 40, 0), 3),
        ("2040", "upright", round(UPRIGHT_LEN, 0), 4),
        ("2040", "Y beam (40 tall)", round(Y_BEAM_Y1 - Y_BEAM_Y0, 0), 2),
        ("2040", "X beam (40 tall)", round(X_BEAM_X1 - X_BEAM_X0, 0), 1),
        ("2040", "Z spine", L.Z_SPINE_LEN, 1),
        ("2020", "head drop arm", 180.0, 1),
    ]


# --------------------------------------------------------------------------- static: frame + bed


def frame_parts() -> list[Part]:
    parts: list[Part] = []
    # base: two side rails under the uprights, three cross members under the bed
    for x in (XL, XR):
        parts.append(Part(f"base_side_{'L' if x < CX_MID else 'R'}", box(x - 20, BED_Y0, Z_BASE_BOT, x + 20, Y_BEAM_Y1, Z_BASE_TOP), ALU, "purchased", "static"))
    for i, y in enumerate(CROSS_YS):
        parts.append(Part(f"base_cross_{i}", box(XL + 20, y - 20, Z_BASE_BOT, XR - 20, y + 20, Z_BASE_BOT + 20), ALU, "purchased", "static"))
    # uprights (2040, 20 in X x 40 in Y) at the Y-beam ends
    for x in (XL, XR):
        for y in (Y_BEAM_Y0 + 20, Y_BEAM_Y1 - 20):
            parts.append(Part(f"upright_{'L' if x < CX_MID else 'R'}{'F' if y < 0 else 'B'}", box(x - 10, y - 20, Z_BASE_TOP, x + 10, y + 20, Z_YBEAM_BOT), ALU, "purchased", "static"))
    # Y beams (2040 standing: 20 in X, 40 tall) + MGN12 rails on top
    for x in (XL, XR):
        side = "L" if x < CX_MID else "R"
        parts.append(Part(f"y_beam_{side}", box(x - 10, Y_BEAM_Y0, Z_YBEAM_BOT, x + 10, Y_BEAM_Y1, Z_YBEAM_TOP), ALU, "purchased", "static"))
        parts.append(Part(f"y_rail_{side}", box(x - 6, Y_RAIL_Y0, Z_YBEAM_TOP, x + 6, Y_RAIL_Y0 + Y_RAIL_LEN, L.Y_RAIL_TOP), STEEL, "purchased", "static", note="MGN12 550 mm"))
    # bed
    parts.append(Part("bed_plywood", box(BED_X0, BED_Y0, Z_BED_BOT, BED_X1, BED_Y1, Z_BED_TOP), WOOD, "wood", "static", note="18 mm plywood"))
    return parts


def bed_parts() -> list[Part]:
    parts: list[Part] = []
    for p in L.pockets():
        parts.append(Part(f"pad_{p.index}", cbox(p.x, p.y, -L.PAD_T / 2, L.POCKET_W - 1, L.POCKET_L - 1, L.PAD_T), PAD, "foam", "static", note="EVA + microfiber"))
    rod_h = L.POST_H + L.PAD_T + L.ROD_EMBED  # tops sanded to a dome = lead-in
    for i, (x, y) in enumerate(L.rods()):
        parts.append(Part(f"rod_{i:02d}", cyl((x, y, Z_BED_TOP - L.ROD_EMBED), L.ROD_D, rod_h), DOWEL, "wood", "static"))
    parts.append(Part("station", station_mount().translate((SX, SY, 0)), PETG, "printed", "static"))
    parts.append(Part("station_camera", cbox(SX, SY, 14, 25, 24, 6).union(cyl((SX, SY, 17), 9, 6)), GREEN, "purchased", "static", note="Pi Camera Module 3"))
    return parts


def station_mount() -> cq.Workplane:
    """Upward camera mast: base plate screwed to the bed, camera board at Z~14, LED ring around the lens."""
    base = cbox(0, 0, 2, 90, 110, 4)
    mast = cbox(0, 0, 8, 34, 34, 8).cut(cbox(0, 0, 10, 26, 26, 8))
    ring = cyl((0, 0, 4), 60, 16).cut(cyl((0, 0, 3), 52, 18))  # light ring holder, inner lip
    body = base.union(mast).union(ring)
    body = holes_z(body, [(-38, -48), (38, -48), (-38, 48), (38, 48)], 4.5)  # wood screws
    body = holes_z(body, [(-10.5, -6.25), (10.5, -6.25), (-10.5, 6.25), (10.5, 6.25)], 2.2)  # CM3 holes
    body = body.cut(cbox(0, 18, 9, 18, 10, 8))  # FPC cable exit
    return body


# --------------------------------------------------------------------------- gantry (moves with Y)


def gantry_parts(beam_front_y: float) -> list[Part]:
    """beam_front_y = Y of the X-beam front face (= cup Y + Y_CUP_TO_BEAM)."""
    yb = beam_front_y
    parts: list[Part] = []
    parts.append(Part("x_beam", box(X_BEAM_X0, yb, Z_XBEAM_BOT, X_BEAM_X1, yb + 20, Z_XBEAM_TOP), ALU, "purchased", "gantry"))
    parts.append(Part("x_rail", box(X_RAIL_X0, yb - L.MGN12_RAIL_H, Z_XRAIL_C - 6, X_RAIL_X0 + X_RAIL_LEN, yb, Z_XRAIL_C + 6), STEEL, "purchased", "gantry", note="MGN12 450 mm"))
    for x in (XL, XR):
        side = "L" if x < CX_MID else "R"
        cy = yb + 10
        parts.append(Part(f"y_carriage_{side}", cbox(x, cy, L.Y_RAIL_TOP + 2.5, L.MGN12H_W, L.MGN12H_L, 5), STEEL, "purchased", "gantry"))
        parts.append(Part(f"y_plate_{side}", y_plate(side).translate((x, cy, L.Y_RAIL_TOP + L.MGN12_H - L.MGN12_RAIL_H)), PETG, "printed", "gantry"))
    # X belt: GT2 loop in a vertical plane just above the beam top (belt width along Y),
    # 20T pulley on the X motor (right end, shaft along -Y, body behind the beam), idler at the left end.
    xm, xi = X_MOTOR_X, X_IDLER_X
    pz = X_PULLEY_Z
    parts.append(Part("x_motor", cbox(xm, yb + 20 + 2 + 24, pz, NEMA, 48, NEMA), BLACK, "purchased", "gantry", note="NEMA17 48 mm"))
    parts.append(Part("x_motor_mount", x_motor_mount().translate((xm, yb, Z_XBEAM_TOP)), PETG, "printed", "gantry"))
    parts.append(Part("x_idler_mount", x_idler_mount().translate((xi, yb, Z_XBEAM_TOP)), PETG, "printed", "gantry"))
    for zz in (pz - 6.4, pz + 6.4):
        parts.append(Part(f"x_belt_{'lo' if zz < pz else 'hi'}", box(xi, yb + X_BELT_Y[0], zz - 0.7, xm, yb + X_BELT_Y[1], zz + 0.7), BLACK, "purchased", "gantry"))
    parts.append(Part("x_pulley", cyl((xm, yb + X_BELT_Y[0] - 1, pz), 16, 11, (0, 1, 0)), STEEL, "purchased", "gantry"))
    parts.append(Part("x_idler", cyl((xi, yb + X_BELT_Y[0] - 1, pz), 18, 11, (0, 1, 0)), STEEL, "purchased", "gantry"))
    return parts


def y_plate(side: str) -> cq.Workplane:
    """Sits on a Y carriage, carries one end of the X beam and the Y belt clamp."""
    t = 6.0
    plate = cbox(0, 0, t / 2, 52, 60, t)
    plate = holes_z(plate, [(-10, -10), (10, -10), (-10, 10), (10, 10)], M3_CLR)  # MGN12H 20x20 (countersunk from top)
    plate = holes_z(plate, [(-19, 0), (19, 0)], M5_CLR)  # M5 up into T-nuts in the X-beam bottom slot
    s = -1 if side == "L" else 1
    clamp = cbox(s * 19, 0, -6, 8, 40, 12)  # belt clamp tab hanging down beside the Y beam
    clamp = clamp.cut(cbox(s * 19, 0, -8, 2.2, 42, 9.2))
    return plate.union(clamp)


def x_motor_mount() -> cq.Workplane:
    """L-bracket: foot bolts to the X-beam top, upright face carries the motor (shaft along -Y).
    Local origin: X = motor axis, Y = beam front face, Z = beam top."""
    t = 6.0
    foot = box(-26, 0, 0, 26, 20, t)
    foot = holes_z(foot, [(-16, 10), (16, 10)], M5_CLR)
    face = box(-26, 20, 0, 26, 20 + t, X_PULLEY_Z - Z_XBEAM_TOP + 26)
    face = face.cut(cyl((0, 19, X_PULLEY_Z - Z_XBEAM_TOP), 23, t + 2, (0, 1, 0)))
    face = holes_y(face, [(dx, X_PULLEY_Z - Z_XBEAM_TOP + dz) for dx in (-15.5, 15.5) for dz in (-15.5, 15.5)], M3_CLR)
    rib = box(-3, 0, t, 3, 20, 20)
    return foot.union(face).union(rib)


def x_idler_mount() -> cq.Workplane:
    """Two cheeks on the beam top hold an M5 idler axle (along Y); slotted for belt tension."""
    t = 5.0
    foot = box(-18, 0, 0, 18, 20, t)
    foot = holes_z(foot, [(-12, 10), (12, 10)], M5_CLR)
    cheek_a = box(-10, X_BELT_Y[0] - 5, 0, 10, X_BELT_Y[0] - 2, X_PULLEY_Z - Z_XBEAM_TOP + 12)
    cheek_b = box(-10, X_BELT_Y[1] + 2, 0, 10, X_BELT_Y[1] + 5, X_PULLEY_Z - Z_XBEAM_TOP + 12)
    body = foot.union(cheek_a).union(cheek_b)
    body = body.cut(box(-12, X_BELT_Y[0] - 2, t, 12, X_BELT_Y[1] + 2, 40))  # belt/idler gap
    for dx in (-3, 0, 3):  # slot = row of overlapping holes
        body = holes_y(body, [(dx, X_PULLEY_Z - Z_XBEAM_TOP)], 5.3)
    return body


# --------------------------------------------------------------------------- carriage (moves with X)


def carriage_parts(cup_x: float, beam_front_y: float) -> list[Part]:
    yb = beam_front_y
    parts: list[Part] = []
    parts.append(Part("x_carriage", cbox(cup_x, yb - 10.5, Z_XRAIL_C, L.MGN12H_L, 5, L.MGN12H_W), STEEL, "purchased", "carriage"))
    parts.append(Part("x_bracket", x_bracket().translate((cup_x, yb - L.MGN12_H, 0)), PETG, "printed", "carriage"))
    spine_y1 = yb - L.MGN12_H - L.X_BRACKET_T
    parts.append(Part("z_spine", box(cup_x - 20, spine_y1 - 20, L.Z_SPINE_BOTTOM, cup_x + 20, spine_y1, L.Z_SPINE_BOTTOM + L.Z_SPINE_LEN), ALU, "purchased", "carriage"))
    parts.append(Part("z_rail", box(cup_x - 6, spine_y1 - 20 - L.MGN12_RAIL_H, L.Z_SPINE_BOTTOM + 1, cup_x + 6, spine_y1 - 20, L.Z_SPINE_BOTTOM + L.Z_SPINE_LEN - 9), STEEL, "purchased", "carriage", note="MGN12 290 mm"))
    ztop = L.Z_SPINE_BOTTOM + L.Z_SPINE_LEN
    parts.append(Part("z_motor_mount", z_motor_mount().translate((cup_x, spine_y1 - 20, ztop)), PETG, "printed", "carriage"))
    parts.append(Part("z_motor", cbox(cup_x + 24, spine_y1 - 20 - 23, ztop + 5 + 24, NEMA, NEMA, 48), BLACK, "purchased", "carriage", note="NEMA17 + 300 mm T8x8 integrated lead screw"))
    parts.append(Part("z_leadscrew", cyl((cup_x + 24, spine_y1 - 20 - 23, L.Z_SPINE_BOTTOM + 10), 8, ztop + 5 - L.Z_SPINE_BOTTOM - 10), STEEL, "purchased", "carriage"))
    return parts


def x_bracket() -> cq.Workplane:
    """Plate in the XZ plane: X carriage (MGN12H) on its back, Z spine (2040) on its front.
    Local origin: X = cup axis, Y = X-carriage front face (plate grows toward -Y), Z = machine Z.
    The top tab reaches over the beam to clamp the X belt."""
    t = L.X_BRACKET_T
    zb = Z_XRAIL_C
    plate = box(-30, -t, L.Z_SPINE_BOTTOM + 100, 30, 0, X_PULLEY_Z + 14.4)
    plate = holes_y(plate, [(dx, zb + dz) for dx in (-10, 10) for dz in (-10, 10)], M3_CLR)  # MGN12H
    plate = holes_y(plate, [(-10, z) for z in (L.Z_SPINE_BOTTOM + 115, L.Z_SPINE_BOTTOM + 135)] + [(10, z) for z in (L.Z_SPINE_BOTTOM + 115, L.Z_SPINE_BOTTOM + 135)], M5_CLR)
    # clamp tab reaches over the beam top; the upper belt strand is gripped in a toothed slot
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
CAM_Z = 140.0  # lens face height above cup face
ARM_Z = (FOOT_Z[0], L.Z_CARRIAGE_ABOVE_CUP + 55.0)


def head_parts(cup_x: float, cup_y: float, c: float, beam_front_y: float) -> list[Part]:
    parts: list[Part] = []
    yb = beam_front_y
    zc_bottom = c + L.Z_CARRIAGE_ABOVE_CUP
    zrail_front = yb - L.MGN12_H - L.X_BRACKET_T - 20 - L.MGN12_RAIL_H
    parts.append(Part("z_carriage", box(cup_x - 13.5, zrail_front - 5, zc_bottom, cup_x + 13.5, zrail_front, zc_bottom + L.MGN12H_L), STEEL, "purchased", "head"))
    zp_front = zrail_front - 5 - L.Z_PLATE_T
    parts.append(Part("z_plate", z_plate().translate((cup_x, zrail_front - 5, zc_bottom)), PETG, "printed", "head"))
    arm_y1 = zp_front
    parts.append(Part("drop_arm", box(cup_x - 10, arm_y1 - 20, c + ARM_Z[0], cup_x + 10, arm_y1, c + ARM_Z[1]), ALU, "purchased", "head", note="2020 x 180"))
    arm_cy = arm_y1 - 10
    off = arm_cy - cup_y  # should equal ARM_TO_CUP
    parts.append(Part("head_foot", head_foot(off).translate((cup_x, cup_y, c)), PETG, "printed", "head"))
    parts.append(Part("camera_bracket", camera_bracket(off).translate((cup_x, cup_y, c)), PETG, "printed", "head"))
    parts.append(Part("buffer", cyl((cup_x, cup_y, c + BUFFER_BODY[1]), BUFFER_BODY[0], BUFFER_BODY[2] - BUFFER_BODY[1]).union(cyl((cup_x, cup_y, c + 8), 6, 12)).union(cyl((cup_x, cup_y, c + FOOT_Z[1]), 6, 22)), STEEL, "purchased", "head", note="M10 spring buffer, 25 mm stroke"))
    parts.append(Part("cup", cyl((cup_x, cup_y, c), CUP_D, 8), BLACK, "purchased", "head", note="25 mm non-marking cup"))
    parts.append(Part("head_camera", cbox(cup_x, cup_y, c + CAM_Z + 12, 38, 38, 10).union(cyl((cup_x, cup_y, c + CAM_Z), 14, 7)), GREEN, "purchased", "head", note="USB 8MP IMX179 M12 3.6 mm"))
    parts.append(Part("contact_sensor", cbox(cup_x, cup_y + 21, c + 92, 33, 10.5, 12), BLACK, "purchased", "head", note="slotted optical endstop"))
    return parts


def z_plate() -> cq.Workplane:
    """Printed Z carriage plate. Local origin: X = cup axis, Y = Z-carriage front face, Z = carriage bottom."""
    t = L.Z_PLATE_T
    plate = box(-30, -t, -5, 40, 0, 55)
    plate = holes_y(plate, [(dx, 22.7 + dz) for dx in (-10, 10) for dz in (-10, 10)], M3_CLR)  # MGN12H
    plate = holes_y(plate, [(0, 5), (0, 45)], M5_CLR)  # drop arm (2020) slot bolts
    nut = box(12, -t - 15, 40, 36, 0, 48)  # shelf for the T8 nut, screw at X+24
    nut = nut.cut(cyl((24, -23 + 0, 30), 10.5, 30)).cut(cyl((24, -23, 30), 3.0, 30))
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
    with a 50 mm LED ring around the lens."""
    z0 = CAM_Z
    shelf = box(-24, -24, z0 + 4, 24, arm_offset - 10, z0 + 8)
    shelf = shelf.cut(cyl((0, 0, z0), 16, 20))  # lens hole
    shelf = holes_z(shelf, [(dx, dy) for dx in (-16, 16) for dy in (-16, 16)], 2.2)  # 32 mm board holes
    ring = cyl((0, 0, z0 - 4), 56, 8).cut(cyl((0, 0, z0 - 5), 46, 10))
    clamp = box(-12, arm_offset - 12, z0 - 6, 12, arm_offset + 12, z0 + 24).cut(box(-10.2, arm_offset - 10.2, z0 - 7, 10.2, arm_offset + 10.2, z0 + 25))
    clamp = holes_x(clamp, [(arm_offset, z0 + 9)], M5_CLR)
    return shelf.union(ring).union(clamp)


# --------------------------------------------------------------------------- slabs


def slab(x, y, z_bottom, face_down=True, label_toward="front") -> cq.Workplane:
    s = cbox(x, y, z_bottom + SLAB_T / 2, SLAB_W, SLAB_H, SLAB_T)
    return s


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
        stack = None
        for k in range(n):
            s = slab(p.x, p.y, k * SLAB_T)
            stack = s if stack is None else stack.union(s)
        lab = None
        for k in range(n):
            l_ = slab_label(p.x, p.y, k * SLAB_T)
            lab = l_ if lab is None else lab.union(l_)
        out.append(Part(f"stack_{p.index}", stack, SLAB, "slab", "static", meta={"count": n}))
        out.append(Part(f"labels_{p.index}", lab, LABEL, "slab", "static"))
    return out


# --------------------------------------------------------------------------- assembly


def machine(cup_x: float, cup_y: float, c: float, held_slab: bool = False, fill: dict[int, int] | None = None, with_slabs: bool = True) -> list[Part]:
    yb = cup_y + L.Y_CUP_TO_BEAM
    parts = frame_parts() + bed_parts() + gantry_parts(yb) + carriage_parts(cup_x, yb) + head_parts(cup_x, cup_y, c, yb)
    if with_slabs:
        parts += stacks(fill)
    if held_slab:
        parts.append(Part("held_slab", slab(cup_x, cup_y, c - SLAB_T), SLAB, "slab", "head"))
        parts.append(Part("held_label", slab_label(cup_x, cup_y, c - SLAB_T), LABEL, "slab", "head"))
    return parts


def printed_catalog() -> list[tuple[str, cq.Workplane, int, str]]:
    """(name, shape in print orientation, qty, notes) for every printed part."""
    off = L.ARM_TO_CUP
    cat = [
        ("station_mount", station_mount(), 1, "PETG, 3 walls, 25% infill"),
        ("y_plate_L", y_plate("L"), 1, "PETG, 100% infill, print flat"),
        ("y_plate_R", y_plate("R"), 1, "PETG, 100% infill, print flat"),
        ("x_motor_mount", x_motor_mount(), 1, "PETG, 5 walls, 40% infill"),
        ("x_idler_mount", x_idler_mount(), 1, "PETG, 5 walls, 40% infill"),
        ("x_bracket", x_bracket().rotate((0, 0, 0), (1, 0, 0), 90), 1, "PETG, print flat on its back face, 6 walls, 50% infill"),
        ("z_motor_mount", z_motor_mount(), 1, "PETG, 5 walls, 40% infill"),
        ("z_plate", z_plate().rotate((0, 0, 0), (1, 0, 0), 90), 1, "PETG, print flat, 6 walls, 50% infill"),
        ("head_foot", head_foot(off), 1, "PETG, 5 walls, 40% infill"),
        ("camera_bracket", camera_bracket(off), 1, "PETG, supports for the ring, matte black filament preferred"),
    ]
    return cat
