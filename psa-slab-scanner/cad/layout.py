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

SLAB_T_CARRY_MAX = 7.5  # thickest slab we design the carry clearance for (CGC); PSA standard <= 7.0

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
ROD_INSET = 12.0  # rod centre from each cell corner: corners stay free, and the front/back gap (52 mm) fits fingertips for loading
ROD_EMBED = 15.0
PAD_T = 3.0  # EVA + microfiber pad thickness (pad top = Z0)
BED_T = 18.0  # plywood bed

# ---- Read station (upward camera, in a middle cell of the row) ----------------------
CAM_TO_SLAB = 140.0  # both cameras: lens to label distance
STATION_LENS_Z = 23.0  # station camera lens front above pad top
STATION_READ_C = STATION_LENS_Z + CAM_TO_SLAB + SLAB_T  # cup height when the held slab's front is 140 mm above the lens

# ---- Motion envelope -----------------------------------------------------------
CLEAR = 10.0  # vertical clearance over rod tops while moving
C_SAFE_EMPTY = POST_H + CLEAR  # 228: cup face height for empty travel
C_SAFE_LOADED = POST_H + CLEAR + 2 * SLAB_T_CARRY_MAX  # 243: even a double pick clears the rods by 10 mm
C_MAX = 250.0  # top of Z travel (cup face)
HEAD_ENVELOPE = (70.0, 116.0)  # X, Y footprint of everything below C+POST_H; must fit in a pocket
PROBE_WINDOW = 12.0  # max probing travel past predicted contact (< buffer stroke 25)
BUFFER_STROKE = 25.0
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
MGN12_RAIL_W, MGN12_RAIL_H = 12.0, 8.0
MGN12H_L, MGN12H_W = 45.4, 27.0
EXT20, EXT40 = 20.0, 40.0
X_BRACKET_T = 8.0  # printed X-carriage-to-Z-spine bracket
Z_PLATE_T = 8.0  # printed Z carriage plate
ARM_TO_CUP = 35.0  # drop-arm centre to cup axis (Y)
# cup axis -> X beam front face:
#   ARM_TO_CUP (35) + arm half (10) + Z plate (8) + Z carriage (13) + Z spine (20) + X bracket (8) + X carriage (13) = 107
Y_CUP_TO_BEAM = ARM_TO_CUP + EXT20 / 2 + Z_PLATE_T + MGN12_H + EXT20 + X_BRACKET_T + MGN12_H
Z_SPINE_BOTTOM = POST_H + 8.0  # lowest rigid gantry part that sweeps over the bed
Z_CARRIAGE_ABOVE_CUP = POST_H + 25.0  # Z carriage bottom edge above the cup face: carriage stays on its rail down to c = -12
Z_SPINE_OFFSET_X = -10.0  # 2040 spine centre vs cup axis: the Z rail bolts into the spine's +10 slot, on the cup axis
C_MIN = -12.0  # lowest cup height the rail allows (probing the bare pad trips near -2)
Z_SPINE_LEN = 340.0
X_BEAM_Z = 400.0  # X beam (4040) centre height
X_RAIL_Z = X_BEAM_Z + 10.0  # rail bolts into the upper slot of the beam's front face (4040 slots are at +/-10)
LABEL_TOWARD = "front"  # slabs face-down, label end toward the operator (keeps the arm out of camera view)


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
    if C_MAX < C_SAFE_LOADED:
        problems.append("Z travel cannot lift a slab clear of the rods")
    if STATION_READ_C > C_SAFE_LOADED:
        problems.append("station read height above loaded travel height")
    if not 0 < STATION_CELL < N_CELLS - 1:
        problems.append("station cell must not be at an end")
    if Z_SPINE_BOTTOM + 1 + Z_SPINE_LEN - 10 < Z_CARRIAGE_ABOVE_CUP + C_MAX + MGN12H_L:
        problems.append("Z rail too short for full travel")
    if Z_CARRIAGE_ABOVE_CUP + C_MIN < Z_SPINE_BOTTOM + 1:
        problems.append("Z carriage leaves the bottom of its rail above C_MIN")
    return problems


if __name__ == "__main__":
    for p in pockets():
        print(p)
    print("station", station_xy(), "capacity", capacity(), "travel", travel_needed(), "rods", len(rods()))
    print("checks:", check() or "OK", "| nominal slab", SLAB_W, SLAB_H, SLAB_T, "| C_SAFE_LOADED", C_SAFE_LOADED)
