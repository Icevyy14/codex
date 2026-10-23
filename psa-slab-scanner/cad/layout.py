"""Master layout: the single source of truth for geometry.

CAD (parts + assembly) and the machine software config are both generated from these
numbers, so the robot's idea of where a pocket is always matches the model.

SlabRail layout: ONE straight row of pockets under ONE gantry beam. Only two motors:
X (belt, along the row) and Z (lead screw, up/down). No Y axis.

Coordinate system (all mm):
  X  left -> right along the row (gantry beam direction)
  Y  front -> back (constant for the cup: the pocket row centre line)
  Z  up; Z = 0 is the top surface of the pocket floor pads
  Machine X = position of the suction-cup axis. Machine Z ("c") = height of the cup face.
"""

from __future__ import annotations

from dataclasses import dataclass

from dims import SLAB_H, SLAB_T, SLAB_W

SLAB_T_THICK_MAX = 11.5  # thick-holder class bound (= software t_thick_max; PSA thick holder ~10.25)

# ---- Cells ---------------------------------------------------------------------
POCKET_W = 84.0  # interior, X. PSA 80.3 nominal -> +/-1.85 mm play. CGC/TAG/BGS fit; SGC (86.25) does not.
POCKET_L = 139.0  # interior, Y. PSA 135.5 nominal -> +/-1.75 mm play.
WALL = 8.0  # wall-line spacing = guide rod diameter (8 mm hardwood dowels)
PITCH_X = POCKET_W + WALL  # 92
N_POCKETS = 13  # pocket 0 starts empty, 1..11 hold slabs, 12 = exception pocket
STATION_CELL = 7  # cell index (0-based, left to right) used by the upward read camera
N_CELLS = N_POCKETS + 1
STACK_MAX = 30  # slabs per pocket (PSA standard); CGC-only stacks fill to the line at ~27
POST_H = 218.0  # guide rod height above pad top (30 x 6.9 = 207 + margin)
MAX_LINE = 210.0  # fill line (printed fill gauge + software height check)
GATE_Z = MAX_LINE + 4.0  # overfill light beam along the row centre line, below the rod tops
ROD_D = 8.0
ROD_DOME_R = 2.0  # rod tops are domed to a 2-3 mm radius (BUILD_GUIDE 5.4): the lead-in for an off-centre slab
XY_CAL_RESIDUAL = 0.5  # cup-to-pocket-centre error left after calibrate x
ROD_INSET = 12.0  # rod centre from each cell corner: corners stay free, and the front/back gap (52 mm) fits fingertips for loading
ROD_EMBED = 15.0
PAD_T = 3.0  # EVA + microfiber pad thickness (pad top = Z0)
BED_T = 18.0  # plywood bed

# ---- Read station (upward camera, in a middle cell of the row) ----------------------
CAM_TO_SLAB = 140.0  # both cameras: lens to label distance
STATION_LENS_Z = 23.0  # station camera lens front above pad top
CUP_HANG = 2.0  # the free cup hangs this far below its trip-calibrated height c (buffer compression at the probe trip, = software buffer_trip_mm)
STATION_READ_C = STATION_LENS_Z + CAM_TO_SLAB + SLAB_T + CUP_HANG  # cup height when the held slab's front is 140 mm above the lens

# ---- Motion envelope -----------------------------------------------------------
CLEAR = 10.0  # vertical clearance over rod tops while moving
CARRY_CLEAR = 5.0  # the simulator's rule: the lowest held slab face stays >= POST_H + 5 on XY moves
C_SAFE_LOADED = POST_H + 2 * SLAB_T_THICK_MAX + CARRY_CLEAR + CUP_HANG  # 248: a double pick of two thick holders (2 x 11.5) still clears the rods by 5 mm
# Empty travel runs at the same height. The carry sensor has ONE edge (CARRY_SENSOR_C0), which must sit just under the
# lowest travel height; with empty travel at 236.5 (enough for a thick holder clinging to the 'empty' cup) a head that
# stalled anywhere from 235 up to 248 still read blocked and carried a double pick sideways below the rod tops. With the
# edge just under 248, any loss over ~2.5 mm reads clear before every sideways move. Costs ~0.2 s a slab (simulator).
C_SAFE_EMPTY = C_SAFE_LOADED  # 248
C_MAX = 250.0  # top of Z travel the software uses (cup face)
C_MIN = -12.0  # lowest cup height the design allows (firmware soft limit -8; probing the bare pad trips near -2)
C_HARD_BOTTOM = C_MIN - 2.0  # -14: Z carriage skirts land on the z_end_cap lips (hard stop; the buffer would bottom on the bare pad only at -18)
Z_SWITCH_C = C_MAX + 8.0  # 258: Z home switch trip height (firmware mpos 255 + 3 mm pull-off)
C_HARD_TOP = Z_SWITCH_C + 4.0  # 262: z_plate top meets the z_motor_mount (hard stop, 4 mm past the switch)
HELD_SLAB_CLEAR = 5.0  # held slab back (= cup face) to the lowest part fixed to the X carriage, even at C_HARD_TOP
X_HOME_SWITCH = 19.0  # cup X where the X home switch trips (firmware mpos 22 - 3 mm pull-off)
X_HARD_STOP = (15.0, 1262.0)  # cup X where the x_bracket meets the left / right end bumpers
HEAD_ENVELOPE = (70.0, 116.0)  # X, Y footprint of everything below C+POST_H; must fit in a pocket
PROBE_WINDOW = 12.0  # max probing travel past predicted contact (< buffer stroke 20)
BUFFER_STROKE = 20.0  # SMC ZPT25UUK20-B5-A10. [Certain, SMC ZP catalog Table 2] pads of 10-32 mm come in 10/20/30/40/50 mm only
PROBE_TRIP_TOL = 0.5  # the flag may trip within CUP_HANG +/- this (BUILD_GUIDE 7.6; = software buffer_trip_tol_mm default)
Y_ROW = 0.0  # pocket row centre line = cup Y


@dataclass(frozen=True)
class Pocket:
    index: int
    cell: int
    x: float  # centre, machine coords
    y: float
    role: str  # empty_start | source | exceptions


def cell_x(cell: int) -> float:
    return POCKET_W / 2 + cell * PITCH_X


def pockets() -> list[Pocket]:
    """Left to right, skipping the station cell. Stack k is moved onto pocket k-1."""
    out: list[Pocket] = []
    cells = [c for c in range(N_CELLS) if c != STATION_CELL]
    for i, c in enumerate(cells):
        role = "empty_start" if i == 0 else ("exceptions" if i == N_POCKETS - 1 else "source")
        out.append(Pocket(i, c, round(cell_x(c), 3), Y_ROW, role))
    return out


def capacity() -> int:
    return sum(1 for p in pockets() if p.role == "source") * STACK_MAX


def station_xy() -> tuple[float, float]:
    return round(cell_x(STATION_CELL), 3), Y_ROW


def wall_lines() -> tuple[list[float], list[float]]:
    """Centre lines of the walls (rod centres lie on these): X lines between cells, two Y lines (front/back)."""
    xs = [-WALL / 2 + k * PITCH_X for k in range(N_CELLS + 1)]
    ys = [Y_ROW - POCKET_L / 2 - WALL / 2, Y_ROW + POCKET_L / 2 + WALL / 2]
    return xs, ys


def rods() -> list[tuple[float, float]]:
    """Two rods per cell side, ROD_INSET from each interior corner, shared between neighbouring cells.
    The station cell has rods on its two sides (they belong to its neighbours) but none front/back."""
    xs, ys = wall_lines()
    pts: set[tuple[float, float]] = set()
    y0 = ys[0] + WALL / 2
    for x in xs:
        for y in (y0 + ROD_INSET, y0 + POCKET_L - ROD_INSET):
            pts.add((round(x, 3), round(y, 3)))
    for y in ys:
        for c in range(N_CELLS):
            if c == STATION_CELL:
                continue
            x0 = xs[c] + WALL / 2
            for x in (x0 + ROD_INSET, x0 + POCKET_W - ROD_INSET):
                pts.add((round(x, 3), round(y, 3)))
    return sorted(pts)


def grid_extent() -> tuple[float, float, float, float]:
    """xmin, xmax, ymin, ymax of the outer rod surfaces."""
    xs, ys = wall_lines()
    return xs[0] - ROD_D / 2, xs[-1] + ROD_D / 2, ys[0] - ROD_D / 2, ys[-1] + ROD_D / 2


def travel_needed() -> dict[str, tuple[float, float]]:
    ps = pockets()
    return {"x": (min(p.x for p in ps), max(p.x for p in ps)), "y": (Y_ROW, Y_ROW), "c": (0.0, C_MAX)}


# ---- Gantry stack-up (derived; see docs/DESIGN.md "Side view") ------------------
# Y offsets measured from the cup axis toward the back of the machine.
MGN12_H = 13.0  # rail base to carriage top (MGN12H)
MGN12_H1 = 3.0  # rail base to carriage underside (the skirts beside the rail end here)
MGN12_RAIL_W, MGN12_RAIL_H = 12.0, 8.0
MGN12H_L, MGN12H_W = 45.4, 27.0
EXT20, EXT40 = 20.0, 40.0
X_BRACKET_T = 8.0  # printed X-carriage-to-Z-spine bracket
Z_PLATE_T = 8.0  # printed Z carriage plate
ARM_TO_CUP = 35.0  # drop-arm centre to cup axis (Y)
# cup axis -> X beam front face:
#   ARM_TO_CUP (35) + arm half (10) + Z plate (8) + Z carriage (13) + Z spine (20) + X bracket (8) + X carriage (13) = 107
Y_CUP_TO_BEAM = ARM_TO_CUP + EXT20 / 2 + Z_PLATE_T + MGN12_H + EXT20 + X_BRACKET_T + MGN12_H
# The held slab reaches Y +/-67.75 under the cup, so the Z spine (Y 66-86), Z rail (Y 58-66) and lead screw
# all hang over its back half and do NOT rise with Z. Everything fixed to the X carriage therefore starts
# above the highest the slab can ever be pushed (the hard top stop), not just above C_MAX.
Z_END_CAP_T = 8.0  # printed z_end_cap under the spine's bottom end (2 x button-head M5 into the 2040 end bores)
Z_END_CAP_LIP = 6.0  # its lips rise this far above the spine bottom, under the Z carriage skirts
Z_SPINE_BOTTOM = C_HARD_TOP + HELD_SLAB_CLEAR + Z_END_CAP_T  # 275
Z_SPINE_LEN = 340.0
Z_SPINE_TOP = Z_SPINE_BOTTOM + Z_SPINE_LEN  # 615
Z_RAIL_LEN = 330.0
Z_RAIL_BOTTOM = Z_SPINE_BOTTOM + 1.0  # rail top ends 9 mm below the spine top
Z_CARRIAGE_ABOVE_CUP = Z_SPINE_BOTTOM + Z_END_CAP_LIP - C_HARD_BOTTOM  # 295: Z carriage bottom edge above the cup face
Z_PLATE_TOP = Z_SPINE_TOP - Z_CARRIAGE_ABOVE_CUP - C_HARD_TOP  # 58: z_plate top above the Z carriage bottom (top hard stop)
Z_SPINE_OFFSET_X = -10.0  # 2040 spine centre vs cup axis: the Z rail bolts into the spine's +10 slot, on the cup axis
Z_MOTOR_MOUNT_T = 8.0  # printed plate on the spine's top end; the Z motor face sits on it
T8_FLANGE_D = 22.0  # brass T8 nut flange (4 x M3 on a 16 mm circle)
Z_SCREW_DX = 24.0  # lead screw axis, X from the cup axis
Z_SCREW_Y = ARM_TO_CUP + EXT20 / 2 - T8_FLANGE_D / 2 - 1.0  # 33: the nut flange clears the z_plate front face (Y 45)
Z_SCREW_LEN = 340.0  # T8x8 screw length below the motor face: cut the 400 mm screw (311..356 works; a 350 fits as bought)
Z_SCREW_TIP = Z_SPINE_TOP + Z_MOTOR_MOUNT_T - Z_SCREW_LEN  # 283
X_BEAM_Z = 400.0  # X beam (4040) centre height
X_RAIL_Z = X_BEAM_Z + 10.0  # rail bolts into the upper slot of the beam's front face (4040 slots are at +/-10)
X_RAIL_LEN = 1300.0
X_RAIL_X0 = sum(travel_needed()["x"]) / 2 - X_RAIL_LEN / 2  # -10: rail centred on the pocket row
LABEL_TOWARD = "front"  # slabs face-down, label end toward the operator (keeps the arm out of camera view)

# ---- Head camera and the face-down card window ----------------------------------------------------------------------
# The M5 elbow on the buffer's port sits on the cup axis up to c+116.8 (model.py), only 23 mm under the head lens. With the
# lens ON the cup axis it hides a disc of radius 25.6 mm on the slab at hover, and the card's top edge is only ~31.7 mm
# from the axis, so no shape of head_foot leaves 300 mm2 of card on the label side. The lens therefore sits HEAD_CAM_DY
# toward the label end: every part on the axis (elbow, flag tab, port hex, nut) then casts its shadow toward +Y, away from
# the label-side card. The label also moves 5 mm toward the frame centre.
HEAD_CAM_DY = -5.0  # head-camera axis, Y from the cup axis (negative = toward the label end); X offset 0
# [Likely, measured on 27 real PSA backs in the realslabs set] the card's top edge is 34.8-37.8 mm (median 36.1) from the
# slab's label-end edge; the label insert ends ~26 mm and its compartment ridge ~31 mm from that edge. sim.py guessed 32.
CARD_TOP_FROM_EDGE = (34.8, 36.1, 37.8)  # min, median, max
CARD_W, CARD_L = 63.0, 88.0  # Pokemon / Magic size, the narrowest card in the realslabs set (sports cards: 63.5 x 88.9)
CARD_CORNER_R = 2.7  # [Likely +/-0.3] corner radius, traced on a real Pokemon back (the edge runs straight ~3 mm from the corner)
# The card lies under the slab back, but the window is mapped on the slab back, so a ray at the window's edge meets the
# card further out (checks.py _on_card_plane). [Likely +/-0.5] the card back is ~3.5 mm down: half a 7.0-7.5 mm holder less
# half the card. n: acrylic, the lowest of the usual clear holder plastics (PS 1.59, PC 1.58), so the most parallax; an air
# gap between the shell and the card would add some (all air, 3.5 mm: the upper bound checks.py also reports).
CARD_DEPTH, SLAB_N = 3.5, 1.49
LABEL_BAND = 31.0  # label compartment, from the label-end edge
WINDOW_PLACE_TOL = 1.75 + XY_CAL_RESIDUAL  # slab play in its pocket (Y: (139 - 135.5) / 2) + the cup's X calibration residual
CARD_IN_SLAB_X = 1.0  # card off the slab's centre line in X (measured: up to 0.81 PSA, 0.73 CGC)
# [Likely +/-0.5 mm] Card position per grader, measured on real studio-scan backs in the realslabs set (22 PSA, 27 CGC; scale
# from the card itself, 63 x 88 mm; the PSA median length came out at the nominal 135.5). "top_to_far" is the card top's
# distance to the holder's FAR (non-label) edge: min, median, max. That is what sets the worst case: a slab pushed to the cup
# end of its pocket play has its far edge on the pocket wall, so its card top lies POCKET_L / 2 + XY_CAL_RESIDUAL - top_to_far
# from the cup axis, whatever the holder's length. CGC holders are ~1.6 mm shorter (2.55 mm of play, not 1.75) and their
# card sits ~3.5 mm nearer the far edge, so a CGC card top can come 3.4 mm nearer the cup than a PSA one.
HOLDERS = {
    "PSA": {"length": 135.5, "width": 80.3, "top_to_far": (97.18, 98.68, 99.95), "n": 22},
    "CGC": {"length": 133.9, "width": 79.4, "top_to_far": (93.76, 95.17, 96.21), "n": 27},
}


def card_top_worst(grader: str) -> float:
    """Nearest the cup (mm from the cup axis, label end negative) a card top of this grader can be: the measured card top
    nearest the far edge, the slab at the cup end of its play, plus the calibration residual."""
    return round(POCKET_L / 2 + XY_CAL_RESIDUAL - HOLDERS[grader]["top_to_far"][0], 3)


def card_x_shift(grader: str) -> float:
    """Furthest the card's centre line can lie from the cup axis (mm, X) for this grader's slab anywhere in its pocket."""
    return round((POCKET_W - HOLDERS[grader]["width"]) / 2 + XY_CAL_RESIDUAL + CARD_IN_SLAB_X, 3)


def card_side_limit(grader: str) -> float:
    """Largest |x| (mm from the cup axis) that stays on the card for this grader's slab anywhere in its pocket (card edge
    in the slab-back plane, square corners; checks.py adds the corners and the card's depth)."""
    return round(CARD_W / 2 - card_x_shift(grader), 3)


# Card-window rectangles [x0, y0, x1, y1] on the slab plane, mm from the CUP axis (X along the row, Y along the slab, label
# end negative). The software's face_down_window_mm is measured from the head-CAMERA axis: use face_down_window_cam().
# y0: the worst CGC card top (card_top_worst, -23.76) + 0.26 mm in the slab-back plane; PSA's is at -27.18. x: 0.2 mm inside
# card_side_limit (CGC 27.70). Seen on the card plane (checks.py: the card's depth and rounded corners) that is about zero
# margin: a CGC slab pushed into a pocket corner has ~1.5 % of the window on the holder (4.5 % if the 3.5 mm were all air),
# a PSA slab none. Area rules out pulling the edges in (x +/-27.0 alone leaves 297 mm2).
# y1: 2 mm short of the free cup's pad shadow (it ends at -16.0 at 0.56 deg of aim error); every mm here is ~0.39 deg of
# camera tilt toward the cup before the pad is in view (checks.py check_camera_aim: 1.34 deg). The ring light's reflection
# in the slab back ends ~11 mm from the camera axis. 1.5 deg would need y1 = -18.5, which leaves 275 mm2, under the
# software's 300 (facedown.MIN_WINDOW_MM2).
# [Likely, the shipped learned_match on machine-scale frames made from the realslabs scans] with every slab at the cup end
# of its play, the old window (y0 -27.5, y1 -16) let 12 of 206 face-up slabs through at threshold 0.55, all CGC fronts:
# the strip of holder above a CGC card looks the same from both sides. This one let none (highest face-up 0.49; 0.53 with
# the slabs placed +/-2 mm), and accepts ~101 of 126 face-down backs (old: 116).
FACE_DOWN_WINDOW_MM = [[-27.5, -23.5, 27.5, -18.0]]


def face_down_window_cam() -> list[list[float]]:
    """FACE_DOWN_WINDOW_MM measured from the head-camera axis (what software config face_down_window_mm means)."""
    return [[x0, round(y0 - HEAD_CAM_DY, 3), x1, round(y1 - HEAD_CAM_DY, 3)] for x0, y0, x1, y1 in FACE_DOWN_WINDOW_MM]


def window_area() -> float:
    return sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in FACE_DOWN_WINDOW_MM)


# ---- Carry-height sensor (Z stall guard) ------------------------------------------------------------------------------
# The spare TCST2103 endstop board sits on the Z spine (fixed to the X carriage), a flag on the z_plate (moves with Z): the
# beam is blocked for every cup height from CARRY_SENSOR_C0 up to the Z hard top stop and clear below it. The software
# reads it before every sideways move, so a Z stall while lifting stops the run instead of dragging a slab over the rods.
# Within CARRY_BAND of the trip it may read either way, so a head as low as CARRY_SENSOR_C0 - CARRY_BAND (245.5) may still
# move sideways: there even a double pick of two thick holders clears the rod tops by 2.5 mm.
CARRY_BAND = 1.0  # = software CARRY_BAND_MM (trip setting +/-0.5 mm, flag edge); the selftest allows the same
CARRY_SENSOR_C0 = C_SAFE_LOADED - 1.5  # 246.5: lowest cup height with the beam blocked (the flag's top edge on the beam)


def check() -> list[str]:
    """Static sanity checks; returns a list of problems (empty = OK)."""
    problems = []
    if SLAB_W + 2 * 1.0 > POCKET_W:
        problems.append("pocket too narrow for slab + 1 mm play per side")
    if SLAB_H + 2 * 1.0 > POCKET_L:
        problems.append("pocket too short for slab + 1 mm play per side")
    if STACK_MAX * 6.9 > MAX_LINE:
        problems.append("STACK_MAX x 6.9 mm exceeds the MAX line")
    if HEAD_ENVELOPE[0] > POCKET_W - 2 * 5 or HEAD_ENVELOPE[1] > POCKET_L - 2 * 5:
        problems.append("head envelope leaves < 5 mm to the rods")
    if ROD_INSET < ROD_D / 2 + 5:
        problems.append("rods too close to pocket corners")
    if PROBE_WINDOW >= BUFFER_STROKE:
        problems.append("probe window must be shorter than buffer stroke")
    if CUP_HANG - PROBE_TRIP_TOL < 1.0:
        problems.append("the probe flag must sit >= 1 mm of buffer travel below the beam at rest, or a bump trips it")
    if CUP_HANG + PROBE_TRIP_TOL + PROBE_WINDOW > BUFFER_STROKE - 5:
        problems.append("a late trip plus the probe window leaves < 5 mm of buffer stroke")
    if C_MAX < C_SAFE_LOADED:
        problems.append("Z travel cannot lift a slab clear of the rods")
    if C_SAFE_LOADED - CUP_HANG - 2 * SLAB_T_THICK_MAX < POST_H + CARRY_CLEAR:
        problems.append("a double pick of two thick holders does not clear the rods by CARRY_CLEAR at C_SAFE_LOADED")
    if C_SAFE_EMPTY - CUP_HANG - SLAB_T_THICK_MAX < POST_H + CARRY_CLEAR:
        problems.append("a thick holder clinging to the 'empty' cup does not clear the rods by CARRY_CLEAR at C_SAFE_EMPTY")
    # A slab rides on the cup at the offset it had in its source pocket (up to the full play), and the cup misses
    # both pocket centres by up to XY_CAL_RESIDUAL, so it can meet a destination rod by 2 x XY_CAL_RESIDUAL.
    # The rod's dome must turn that into a lead-in (the held descent through the rod band is slow and guarded).
    if 2 * XY_CAL_RESIDUAL > ROD_DOME_R - 0.5:
        problems.append("an off-centre held slab overlaps a rod by more than the domed rod top can lead in")
    if C_SAFE_EMPTY - CUP_HANG < POST_H + CLEAR:
        problems.append("the empty cup does not clear the rods by CLEAR at C_SAFE_EMPTY")
    if STATION_READ_C > C_SAFE_LOADED:
        problems.append("station read height above loaded travel height")
    if not 0 < STATION_CELL < N_CELLS - 1:
        problems.append("station cell must not be at an end")
    if not C_MAX < Z_SWITCH_C < C_HARD_TOP:
        problems.append("Z switch must trip between C_MAX and the hard top stop")
    if not -(BUFFER_STROKE - CUP_HANG) + 2 <= C_HARD_BOTTOM < C_MIN:  # on the bare pad the buffer is compressed CUP_HANG - c
        problems.append("Z bottom hard stop must lie below C_MIN and >= 2 mm before the buffer bottoms on the bare pad")
    lowest_fixed = min(Z_SPINE_BOTTOM - Z_END_CAP_T, Z_SCREW_TIP, Z_RAIL_BOTTOM)
    if lowest_fixed < C_HARD_TOP + HELD_SLAB_CLEAR:
        problems.append("a held slab at the Z hard top stop reaches the spine / rail / lead screw")
    if Z_CARRIAGE_ABOVE_CUP + C_HARD_BOTTOM < Z_RAIL_BOTTOM + 2:
        problems.append("Z carriage is not >= 2 mm on its rail at the bottom hard stop")
    if Z_CARRIAGE_ABOVE_CUP + C_HARD_TOP + MGN12H_L > Z_RAIL_BOTTOM + Z_RAIL_LEN - 2:
        problems.append("Z carriage is not >= 2 mm on its rail at the top hard stop")
    if Z_RAIL_BOTTOM + Z_RAIL_LEN > Z_SPINE_TOP - 1:
        problems.append("Z rail longer than the spine")
    nut_low = Z_CARRIAGE_ABOVE_CUP + C_HARD_BOTTOM + 36.0  # T8 nut body bottom (flange on the shelf at z_plate local Z 48)
    if Z_SCREW_TIP > nut_low - 5:
        problems.append("lead screw too short: the T8 nut runs off it near the bottom hard stop")
    if not X_RAIL_X0 + MGN12H_L / 2 + 2 <= X_HARD_STOP[0] < X_HOME_SWITCH - 1:
        problems.append("left X bumper must stop the carriage >= 2 mm on its rail and below the home switch")
    if not travel_needed()["x"][1] + 15 + 2 <= X_HARD_STOP[1] <= X_RAIL_X0 + X_RAIL_LEN - MGN12H_L / 2 - 2:
        problems.append("right X bumper must lie beyond the soft limit and stop the carriage >= 2 mm on its rail")
    # face-down card window: area, and on the card (not the label) wherever a PSA or CGC slab lies in its pocket. Flat model
    # (square corners, card in the slab-back plane); checks.py check_face_down_window measures it on the card plane.
    edge = -SLAB_H / 2
    if window_area() < 300.0:
        problems.append("face-down card window under 300 mm2 (software facedown.MIN_WINDOW_MM2)")
    for x0, y0, x1, y1 in FACE_DOWN_WINDOW_MM:
        if not (x0 < x1 and y0 < y1 < 0):
            problems.append("face-down window rectangles must be [x0, y0, x1, y1] on the label side (y < 0)")
        for g in HOLDERS:
            if y0 < card_top_worst(g) or max(abs(x0), abs(x1)) > card_side_limit(g):
                problems.append(f"face-down window reaches off the card for a {g} slab at the edge of its pocket play")
        if y0 < edge + LABEL_BAND + WINDOW_PLACE_TOL:
            problems.append("face-down window reaches the label band")
    if CARRY_SENSOR_C0 + CARRY_BAND > min(C_SAFE_EMPTY, C_SAFE_LOADED):
        problems.append("the carry sensor must read blocked at both travel heights: trip at least CARRY_BAND below them")
    # the highest stall the sensor may miss: a double thick pick there must still pass over the rod tops (2 mm covers the
    # rods' cut length and a buffer measured to trip up to 0.5 mm late)
    if CARRY_SENSOR_C0 - CARRY_BAND - CUP_HANG - 2 * SLAB_T_THICK_MAX < POST_H + 2.0:
        problems.append("a Z stall the carry sensor cannot see leaves a double pick less than 2 mm over the rod tops")
    return problems


if __name__ == "__main__":
    for p in pockets():
        print(p)
    print("station", station_xy(), "capacity", capacity(), "travel", travel_needed(), "rods", len(rods()))
    print("checks:", check() or "OK", "| nominal slab", SLAB_W, SLAB_H, SLAB_T, "| C_SAFE_LOADED", C_SAFE_LOADED)
    print("Z: spine", Z_SPINE_BOTTOM, "..", Z_SPINE_TOP, "| carriage above cup", Z_CARRIAGE_ABOVE_CUP, "| hard stops", C_HARD_BOTTOM, C_HARD_TOP,
          "| screw tip", Z_SCREW_TIP, "| rail", Z_RAIL_BOTTOM, "..", Z_RAIL_BOTTOM + Z_RAIL_LEN)
