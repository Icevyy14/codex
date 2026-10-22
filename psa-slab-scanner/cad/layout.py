"""Master layout: the single source of truth for geometry.

CAD (parts + assembly) and the machine software config are both generated from
these numbers, so the robot's idea of where a pocket is always matches the model.

Coordinate system (all mm):
  X  left -> right (gantry beam direction)
  Y  front -> back
  Z  up; Z = 0 is the top surface of the pocket floor pads
  Machine X/Y = position of the suction-cup axis. Machine Z ("c") = height of the cup face.
"""

from __future__ import annotations

from dataclasses import dataclass

from dims import SLAB_H, SLAB_T, SLAB_T_MAX, SLAB_W

# ---- Pockets (corrals) -------------------------------------------------------
POCKET_W = 84.0  # interior, X. PSA 80.3 nominal -> +/-1.85 mm play. CGC/TAG/BGS fit; SGC (86.25) does not.
POCKET_L = 139.0  # interior, Y. PSA 135.5 nominal -> +/-1.75 mm play.
WALL = 8.0  # wall-line spacing = guide rod diameter (8 mm hardwood dowels)
PITCH_X = POCKET_W + WALL  # 92
PITCH_Y = POCKET_L + WALL  # 147
COLS = 5
ROWS = 3  # set 4 for 450-slab capacity (frame grows by one PITCH_Y)
STACK_MAX = 25  # slabs per pocket
POST_H = 182.0  # guide rod height above pad top, incl. printed lead-in cap (25 x 6.9 = 172.5 + margin)
MAX_LINE = 175.0  # fill line (printed fill gauge + software height check)
ROD_D = 8.0  # hardwood dowel guide rods, glued into 15 mm deep holes
ROD_INSET = 15.0  # rod centre distance from each pocket corner along the wall (keeps slab corners free)
ROD_EMBED = 15.0
CAP_H = 7.0  # printed bullet cap on each rod top (lead-in)
PAD_T = 3.0  # EVA + microfiber pad thickness (pad top = Z0)
BED_T = 18.0  # plywood bed

# ---- Read station (upward camera, front of the bed) --------------------------
STATION_GAP_Y = 20.0  # gap between station box and first pocket row
STATION_BOX = (110.0, 165.0, 150.0)  # outer X, Y, height (rim at Z=150)
CAM_TO_SLAB = 140.0  # both cameras: lens to label distance
STATION_LENS_Z = 23.0  # station camera lens front above pad top (model.station_mount + CM3 board)
STATION_READ_C = STATION_LENS_Z + CAM_TO_SLAB + SLAB_T  # cup height when the held slab's front is 140 mm above the lens

# ---- Motion envelope -----------------------------------------------------------
CLEAR = 10.0  # vertical clearance over post tops while moving
C_SAFE_EMPTY = POST_H + CLEAR  # 192: cup face height for empty travel
C_SAFE_LOADED = POST_H + CLEAR + SLAB_T_MAX  # 199: slab bottom 10 mm over posts
C_MAX = 210.0  # top of Z travel (cup face)
HEAD_ENVELOPE = (70.0, 116.0)  # X, Y footprint of everything below C+POST_H; must fit in pocket
PROBE_WINDOW = 12.0  # max probing travel past predicted contact (< buffer stroke 25)
BUFFER_STROKE = 25.0


@dataclass(frozen=True)
class Pocket:
    index: int  # serpentine order 0..N-1
    row: int
    col: int
    x: float  # centre, machine coords
    y: float
    role: str  # empty_start | source | exceptions


def grid_origin() -> tuple[float, float]:
    """Machine XY of the front-left inner corner of pocket (row 0, col 0)."""
    return 0.0, 0.0


def pockets() -> list[Pocket]:
    """Serpentine order so every transfer is to the physically adjacent pocket.

    Pocket 0 starts empty; stack k is moved onto pocket k-1. The last pocket is the
    exception pocket (unreadable / double picks / rejects).
    """
    ox, oy = grid_origin()
    out: list[Pocket] = []
    n = 0
    for r in range(ROWS):
        cols = range(COLS) if r % 2 == 0 else range(COLS - 1, -1, -1)
        for c in cols:
            x = ox + WALL / 2 + POCKET_W / 2 + c * PITCH_X - WALL / 2
            y = oy + WALL / 2 + POCKET_L / 2 + r * PITCH_Y - WALL / 2
            out.append(Pocket(n, r, c, round(x, 3), round(y, 3), "source"))
            n += 1
    out[0] = Pocket(0, out[0].row, out[0].col, out[0].x, out[0].y, "empty_start")
    last = out[-1]
    out[-1] = Pocket(last.index, last.row, last.col, last.x, last.y, "exceptions")
    return out


def capacity() -> int:
    return sum(1 for p in pockets() if p.role == "source") * STACK_MAX


def station_xy() -> tuple[float, float]:
    xs = [p.x for p in pockets()]
    cx = (min(xs) + max(xs)) / 2
    cy = grid_origin()[1] - STATION_GAP_Y - STATION_BOX[1] / 2
    return round(cx, 3), round(cy, 3)


def wall_lines() -> tuple[list[float], list[float]]:
    """Centre lines of the walls (rod centres lie on these), X lines and Y lines."""
    ox, oy = grid_origin()
    xs = [ox - WALL / 2 + k * PITCH_X for k in range(COLS + 1)]
    ys = [oy - WALL / 2 + j * PITCH_Y for j in range(ROWS + 1)]
    return xs, ys


def rods() -> list[tuple[float, float]]:
    """Guide rod centres: two per pocket side, ROD_INSET from each interior corner, shared between pockets."""
    xs, ys = wall_lines()
    pts: set[tuple[float, float]] = set()
    for x in xs:  # rods on vertical walls (run along Y)
        for j in range(ROWS):
            y0 = ys[j] + WALL / 2
            for y in (y0 + ROD_INSET, y0 + POCKET_L - ROD_INSET):
                pts.add((round(x, 3), round(y, 3)))
    for y in ys:  # rods on horizontal walls (run along X)
        for i in range(COLS):
            x0 = xs[i] + WALL / 2
            for x in (x0 + ROD_INSET, x0 + POCKET_W - ROD_INSET):
                pts.add((round(x, 3), round(y, 3)))
    return sorted(pts)


def grid_extent() -> tuple[float, float, float, float]:
    """xmin, xmax, ymin, ymax of the outer rod surfaces."""
    xs, ys = wall_lines()
    return xs[0] - ROD_D / 2, xs[-1] + ROD_D / 2, ys[0] - ROD_D / 2, ys[-1] + ROD_D / 2


def travel_needed() -> dict[str, tuple[float, float]]:
    ps = pockets()
    sx, sy = station_xy()
    return {
        "x": (min(p.x for p in ps), max(p.x for p in ps)),
        "y": (min(sy, min(p.y for p in ps)), max(p.y for p in ps)),
        "c": (0.0, C_MAX),
    }


def check() -> list[str]:
    """Static sanity checks; returns a list of problems (empty = OK)."""
    problems = []
    if SLAB_W + 2 * 1.0 > POCKET_W:
        problems.append("pocket too narrow for slab + 1 mm play per side")
    if SLAB_H + 2 * 1.0 > POCKET_L:
        problems.append("pocket too short for slab + 1 mm play per side")
    if STACK_MAX * SLAB_T_MAX > MAX_LINE:
        problems.append("STACK_MAX x SLAB_T_MAX exceeds the MAX line")
    if HEAD_ENVELOPE[0] > POCKET_W - 2 * 5 or HEAD_ENVELOPE[1] > POCKET_L - 2 * 5:
        problems.append("head envelope leaves < 5 mm to the rods")
    if ROD_INSET < ROD_D / 2 + 5:
        problems.append("rods too close to pocket corners")
    if PROBE_WINDOW >= BUFFER_STROKE:
        problems.append("probe window must be shorter than buffer stroke")
    if C_MAX < C_SAFE_LOADED:
        problems.append("Z travel cannot lift a slab clear of the posts")
    if STATION_BOX[2] + SLAB_T_MAX > C_SAFE_LOADED - SLAB_T_MAX:
        problems.append("station rim too high for loaded travel")
    return problems


if __name__ == "__main__":
    for p in pockets():
        print(p)
    print("station", station_xy(), "capacity", capacity(), "travel", travel_needed())
    print("checks:", check() or "OK", "| nominal slab", SLAB_W, SLAB_H, SLAB_T)


# ---- Gantry stack-up (derived; see docs/DESIGN.md "Side view") ------------------
# Y offsets measured from the cup axis toward the back of the machine.
MGN12_H = 13.0  # rail base to carriage top (MGN12H)
MGN12_RAIL_W, MGN12_RAIL_H = 12.0, 8.0
MGN12H_L, MGN12H_W = 45.4, 27.0
MGN12H_HOLES = (20.0, 20.0)  # M3, across x along
EXT20, EXT40 = 20.0, 40.0
X_BRACKET_T = 8.0  # printed X-carriage-to-Z-spine bracket
Z_PLATE_T = 8.0  # printed Z carriage plate
ARM_TO_CUP = 35.0  # drop-arm centre to cup axis (Y)
# cup axis -> X beam front face:
#   arm half (10) + Z plate (8) + Z carriage (13) + Z spine (20) + X bracket (8) + X carriage (13)
#   + ARM_TO_CUP (35) = 107
Y_CUP_TO_BEAM = ARM_TO_CUP + EXT20 / 2 + Z_PLATE_T + MGN12_H + EXT20 + X_BRACKET_T + MGN12_H
Z_SPINE_BOTTOM = POST_H + 8.0  # 190: lowest rigid gantry part that sweeps over the bed
Z_SPINE_LEN = 300.0
Z_CARRIAGE_ABOVE_CUP = 195.0  # Z carriage bottom edge height above the cup face
Y_RAIL_TOP = 308.0  # Y rail top surface height
X_BEAM_BOTTOM = Y_RAIL_TOP + (MGN12_H - MGN12_RAIL_H) + 6.0  # on 6 mm Y carriage plates
LABEL_TOWARD = "front"  # slabs face-down, label end toward the operator (keeps arm out of camera view)


def gantry_extents() -> dict[str, float]:
    t = travel_needed()
    return {
        "beam_front_y_min": t["y"][0] + Y_CUP_TO_BEAM,
        "beam_front_y_max": t["y"][1] + Y_CUP_TO_BEAM,
        "x_beam_bottom": X_BEAM_BOTTOM,
    }
