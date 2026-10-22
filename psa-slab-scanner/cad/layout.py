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
WALL = 4.0  # post arm thickness = gap between neighbouring pockets
PITCH_X = POCKET_W + WALL  # 88
PITCH_Y = POCKET_L + WALL  # 143
COLS = 5
ROWS = 3  # set 4 for 450-slab capacity (frame grows by one PITCH_Y)
STACK_MAX = 25  # slabs per pocket
POST_H = 182.0  # post height above pad top (25 x 6.9 = 172.5 + margin)
MAX_LINE = 175.0  # molded fill line on posts
POST_ARM = 14.0  # how far each post arm runs along a pocket wall
CORNER_RELIEF = 3.0  # notch so slab corner tips never touch a post
PAD_T = 3.0  # EVA + microfiber pad thickness (pad top = Z0)
BED_T = 18.0  # plywood bed

# ---- Read station (upward camera, front of the bed) --------------------------
STATION_GAP_Y = 20.0  # gap between station box and first pocket row
STATION_BOX = (110.0, 165.0, 150.0)  # outer X, Y, height (rim at Z=150)
CAM_TO_SLAB = 140.0  # both cameras: lens to label distance

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


def grid_extent() -> tuple[float, float, float, float]:
    """xmin, xmax, ymin, ymax of the pocket grid outer post faces."""
    ox, oy = grid_origin()
    return ox - WALL / 2, ox - WALL / 2 + COLS * PITCH_X, oy - WALL / 2, oy - WALL / 2 + ROWS * PITCH_Y


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
        problems.append("head envelope leaves < 5 mm to the posts")
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
