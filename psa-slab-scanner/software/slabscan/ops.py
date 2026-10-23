"""Operator tools: jog, calibrate z/x, focus, mark (drill template), selftest.

Safety rules shared by every tool here (the run loop has its own, stricter ones):
  * nothing moves before homing;
  * below the safe travel height the head may only move in X within IN_POCKET_TOL of a pocket
    (or station) centre - it fits between the rods there - unless the operator says the bed has
    no rods yet (``rods=False``: marking the drill template, first calibration);
  * every downward Z jog is a bounded probe move (G38.3), so it stops as soon as the cup or
    awl touches something;
  * a probe move is never started while the probe already reads triggered (FluidNC would alarm);
  * no probe target or move goes below ``z_floor(cfg)`` = Z -7.5 (firmware soft limit -8);
  * after an E-stop (the controller loses power and its USB port) the next jog command reconnects
    and homes again before anything else moves.
"""

from __future__ import annotations

import math
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from .config import Config, write_overrides
from .decode import decode_frame, ocr_available
from .motion import ControllerLost

IN_POCKET_TOL = 5.0  # mm: (pocket 84 - head envelope 70) / 2 = 7 mm per side, minus 2 mm margin
DIMPLE_DX = 40.0  # drill_template alignment dimples at cell centre +/- 40 mm on the row centre line (cad/model.py)
TEMPLATE_HOLES = 8  # drill_template: 2 holes on each side wall line (shared with the neighbour cell) + 2 front + 2 back
SIDE_HOLES = 2
MARK_FEED_X = 1500.0  # mm/min: every sideways move during `mark` (the operator's hands and drill are near the bed)


class CalError(Exception):
    """A calibration/operator step could not be completed; the message says why."""


# ---------------------------------------------------------------------- console
class Console:
    """Terminal I/O. Tests pass ``ScriptedConsole`` instead."""

    def __init__(self, out=print, inp=input):
        self.out = out
        self.inp = inp

    def say(self, *msg) -> None:
        self.out(" ".join(str(m) for m in msg))

    def ask(self, prompt: str) -> str:
        try:
            return self.inp(prompt)
        except EOFError:
            return "q"

    def confirm(self, prompt: str, default: bool = False) -> bool:
        a = self.ask(f"{prompt} [{'Y/n' if default else 'y/N'}] ").strip().lower()
        return default if not a else a in ("y", "yes")

    def can_raw_keys(self) -> bool:
        return self.inp is input and sys.stdin.isatty()


class ScriptedConsole(Console):
    def __init__(self, answers: list[str]):
        self.lines: list[str] = []
        self.answers = list(answers)
        super().__init__(out=self.lines.append, inp=self._next)

    def _next(self, prompt: str) -> str:
        self.lines.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)


def z_floor(cfg: Config) -> float:
    """Lowest machine Z any tool may command or probe toward: 0.5 mm inside the Z soft limit (-8)."""
    return cfg.z_min + 0.5


def machine_x(cfg: Config, x: float, y: float = 0.0) -> float:
    """Bed (layout) X -> machine X with the current calibration (same formula as Runner.xy)."""
    a = math.radians(cfg.rotation_deg)
    return x * math.cos(a) - y * math.sin(a) + cfg.offset_x


def _scratch_runner(cfg: Config, hw, out_dir: Path):
    from .runner import Runner

    out_dir.mkdir(parents=True, exist_ok=True)
    writer = SimpleNamespace(dir=out_dir, batch_id="tools")
    return Runner(cfg, hw.motion, hw.vacuum, hw.lights, hw.head_cam, hw.station_cam, writer, log=lambda *_: None, carry=getattr(hw, "carry", None))


def walk_down(m, z_from: float, floor: float, window: float, feed: float, vac=None, seal_kpa: float | None = None) -> float | None:
    """Probe downward in windows from z_from until contact or ``floor`` (callers keep it >= z_floor(cfg)).
    An open cup that seals on the way down (vacuum on) means the contact sensor missed a touch -> CalError."""
    z = z_from
    if vac is not None:
        vac.hold()
    try:
        while z > floor + 1e-6:
            target = max(floor, z - window)
            hit = m.probe(target, feed)
            if hit is not None:
                return hit
            if vac is not None and seal_kpa is not None and vac.kpa() <= seal_kpa:
                raise CalError("The cup sealed on something but the contact sensor did not trip. Contact sensor fault - check it before going on.")
            z = target
        return None
    finally:
        if vac is not None:
            vac.release()


# ---------------------------------------------------------------------- jog
class Jogger:
    STEPS = (0.1, 0.5, 1.0, 5.0, 10.0, 50.0)
    HELP = """jog commands (machine coordinates, mm):
  x 120      go to X 120          x +2 / x -0.5   move X by that much
  z 230      go to Z 230          z +1 / z -1     move Z by that much (down = probe move, stops on contact)
  p N        go to pocket N (at the safe height)   station   go to the read station
  up         go to the safe travel height          top       go to the top of Z travel
  probe      probe down from here (bounded)        step N    step size for keys mode
  keys       arrow-key mode (left/right = X, up/down = Z, [ ] = step, Enter = accept, q = leave)
  where      show position     ok   accept this position (calibrate/mark)     q   quit"""

    def __init__(self, cfg: Config, motion, console: Console, rods: bool = True, x_shift: float = 0.0, jog_feed_x: float = 3000.0):
        self.cfg = cfg
        self.m = motion
        self.con = console
        self.rods = rods
        self.x_shift = x_shift  # temporary extra X offset of the pocket centres (calibrate x, coarse stage)
        self.step = 1.0
        self.jog_feed_x = jog_feed_x
        self.refresh()

    # geometry
    def refresh(self) -> None:
        self.x, self.z = self.m.position()

    def centres(self) -> list[tuple[str, float]]:
        out = [(f"pocket {p.index}", machine_x(self.cfg, p.x, p.y) + self.x_shift) for p in self.cfg.pockets]
        sx, sy = self.cfg.station_xy
        out.append(("station", machine_x(self.cfg, sx, sy) + self.x_shift))
        return out

    def nearest(self, x: float) -> tuple[str, float, float]:
        name, cx = min(self.centres(), key=lambda t: abs(t[1] - x))
        return name, cx, x - cx

    def safe(self) -> float:
        return self.cfg.c_safe_empty + self.cfg.pad_trigger_c

    def top(self) -> float:
        return self.cfg.c_max + self.cfg.pad_trigger_c

    def height(self) -> float:
        return self.z - self.cfg.pad_trigger_c

    def low(self) -> bool:
        return self.z < self.safe() - 0.01

    def check_xy(self, x_to: float) -> str | None:
        if not self.rods or not self.low():
            return None
        name, cx, dx = self.nearest(self.x)
        if abs(dx) > IN_POCKET_TOL or abs(x_to - cx) > IN_POCKET_TOL:
            return (f"Refused: the head is below the rod tops (Z {self.z:.1f} < safe {self.safe():.1f}). Down here X may only move within "
                    f"+/-{IN_POCKET_TOL:.0f} mm of {name}'s centre (X {cx:.2f}). Type 'up' first.")
        return None

    def check_down(self, z_to: float) -> str | None:
        if not self.rods or z_to >= self.z or z_to >= self.safe() - 0.01:
            return None
        name, cx, dx = self.nearest(self.x)
        if abs(dx) > IN_POCKET_TOL:
            return (f"Refused: going below the rod tops is only allowed within +/-{IN_POCKET_TOL:.0f} mm of a pocket or station centre; "
                    f"you are {dx:+.1f} mm from {name}. Use 'p N' first.")
        return None

    # moves
    def move_x(self, x_to: float, feed: float | None = None) -> bool:
        lo, hi = self.cfg.x_travel
        if not lo <= x_to <= hi:
            self.con.say(f"X {x_to:.2f} is outside the travel the controller allows ({lo:g} .. {hi:g}); going to the end instead")
            x_to = min(max(x_to, lo), hi)
        reason = self.check_xy(x_to)
        if reason:
            self.con.say(reason)
            return False
        self.m.move(feed or self.jog_feed_x, x=x_to)
        self.m.wait_idle()
        self.refresh()
        return True

    def move_z(self, z_to: float) -> float | None:
        """Up = plain move. Down = probe move. Returns the contact Z if it touched."""
        z_to = min(z_to, self.top())
        if z_to < z_floor(self.cfg):
            self.con.say(f"Z {z_to:.2f} is below the lowest Z the controller allows ({self.cfg.z_min:g}); stopping at {z_floor(self.cfg):g}")
            z_to = z_floor(self.cfg)
        if z_to >= self.z:
            self.m.move(self.cfg.feed_z, z=z_to)
            self.m.wait_idle()
            self.refresh()
            return None
        reason = self.check_down(z_to)
        if reason:
            self.con.say(reason)
            return None
        if hasattr(self.m, "pins") and "P" in self.m.pins():
            self.con.say("Refused: the probe already reads TRIGGERED (touching something, or a cut wire). Go up first.")
            return None
        hit = self.m.probe(z_to, self.cfg.feed_probe)
        self.refresh()
        if hit is not None:
            self.con.say(f"contact at Z {hit:.3f} (height {hit - self.cfg.pad_trigger_c:.2f} above the pad)")
        return hit

    def go_safe(self) -> None:
        if self.z < self.safe():
            self.move_z(self.safe())

    def goto_x(self, x: float) -> bool:
        self.go_safe()
        return self.move_x(x, self.cfg.feed_xy)

    def goto_pocket(self, i: int) -> bool:
        p = self.cfg.pocket(i)
        return self.goto_x(machine_x(self.cfg, p.x, p.y) + self.x_shift)

    def status_line(self) -> str:
        name, _, dx = self.nearest(self.x)
        return f"X {self.x:9.3f} ({name} {dx:+.2f})   Z {self.z:8.3f} (height {self.height():6.1f}, safe {self.safe():.1f})   step {self.step:g}"

    # commands
    def execute(self, line: str) -> str | None:
        """Run one typed command. Returns 'ok' (accept), 'quit', or None."""
        t = line.strip().lower().split()
        if not t:
            return None
        cmd, args = t[0], t[1:]
        try:
            if cmd in ("q", "quit", "exit"):
                return "quit"
            if getattr(self.m, "homed", True) is False and cmd not in ("h", "help", "?"):
                # The controller was reset (E-stop): its position is unknown until it homes again. Homing is
                # safe from anywhere: Z goes straight up first, then X runs to its left switch at the top.
                self.con.say("The controller was reset (E-stop or USB). Homing again first: Z goes straight up, then X to the left end.")
                self.m.home()
                self.refresh()
                self.con.say("Homed. Jog back to where you were (the last command was not run).")
                self.con.say(self.status_line())
                return None
            if cmd in ("ok", "done", "y"):
                return "ok"
            if cmd in ("h", "help", "?"):
                self.con.say(self.HELP)
            elif cmd in ("where", "w"):
                self.refresh()
            elif cmd in ("x", "z") and args:
                a = args[0]
                rel = a[0] in "+-"
                v = float(a)
                if cmd == "x":
                    self.move_x(self.x + v if rel else v)
                else:
                    self.move_z(self.z + v if rel else v)
            elif cmd[:1] in ("x", "z") and cmd[1:2] in ("+", "-") and len(cmd) > 2:  # x+5, z-1
                v = float(cmd[1:])
                if cmd[0] == "x":
                    self.move_x(self.x + v)
                else:
                    self.move_z(self.z + v)
            elif cmd in ("p", "pocket") and args:
                self.goto_pocket(int(args[0]))
            elif cmd == "station":
                sx, sy = self.cfg.station_xy
                self.goto_x(machine_x(self.cfg, sx, sy) + self.x_shift)
            elif cmd in ("up", "safe"):
                self.go_safe()
            elif cmd == "top":
                self.move_z(self.top())
            elif cmd == "probe":
                self.move_z(self.z - self.cfg.probe_window)
            elif cmd == "step" and args:
                self.step = abs(float(args[0]))
            elif cmd in ("k", "keys"):
                return self.keys()
            else:
                self.con.say(f"? {line.strip()}  (type 'help')")
                return None
        except ValueError:
            self.con.say(f"? bad number in {line.strip()!r}")
            return None
        except ControllerLost as e:
            self.con.say(f"STOP: {e}\nTwist the E-stop to release it. The next command reconnects and homes first.")
            return None
        except Exception as e:  # noqa: BLE001 - controller errors are shown, the session goes on
            self.con.say(f"error: {e}")
            self.refresh()
            return None
        self.con.say(self.status_line())
        return None

    def keys(self) -> str | None:
        """Arrow-key mode on a real terminal. Returns 'ok' on Enter, None when left with q/Esc."""
        if not self.con.can_raw_keys():
            self.con.say("keys mode needs an interactive terminal; type commands instead")
            return None
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        self.con.say("keys: left/right = X, up/down = Z, [ / ] = step, Enter = accept, q = back to commands")
        self.con.say(self.status_line())
        try:
            tty.setcbreak(fd)
            while True:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    seq = sys.stdin.read(2)
                    moves = {"[C": ("x", 1), "[D": ("x", -1), "[A": ("z", 1), "[B": ("z", -1)}
                    if seq in moves:
                        axis, sign = moves[seq]
                        if axis == "x":
                            self.move_x(self.x + sign * self.step)
                        else:
                            self.move_z(self.z + sign * self.step)
                    elif seq == "":
                        return None
                elif ch in ("\n", "\r"):
                    return "ok"
                elif ch in ("q", "Q"):
                    return None
                elif ch in ("]", "+", "="):
                    bigger = [s for s in self.STEPS if s > self.step]
                    self.step = bigger[0] if bigger else self.step
                elif ch in ("[", "-", "_"):
                    smaller = [s for s in self.STEPS if s < self.step]
                    self.step = smaller[-1] if smaller else self.step
                self.con.say(self.status_line())
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def interact(self, prompt: str = "jog") -> tuple[float, float] | None:
        """Command loop. Returns (x, z) when the operator accepts ('ok'), None on quit."""
        self.con.say(self.status_line())
        while True:
            r = self.execute(self.con.ask(f"{prompt}> "))
            if r == "ok":
                self.refresh()
                return self.x, self.z
            if r == "quit":
                return None


# ---------------------------------------------------------------------- calibrate z
def calibrate_z(cfg: Config, hw, con: Console, cal_path: Path, yes: bool = False, extra_depth: float = 12.0) -> dict:
    """Probe the bare pad of pocket 0 from the top of Z travel -> pad_trigger_c (and c_max if travel is short)."""
    m, vac = hw.motion, hw.vacuum
    con.say("calibrate z: pocket 0 must be EMPTY (bare pad). The cup (not the awl) must be fitted.")
    if not yes and not con.confirm("Pocket 0 is empty and the cup is fitted?"):
        raise CalError("cancelled")
    m.home()
    if hasattr(m, "pins") and "P" in m.pins():
        raise CalError("The probe reads TRIGGERED with the head at the top. The sensor is wired fail-safe, so this means a cut wire, "
                       "an unplugged sensor or a blocked slot. Fix it first (selftest -i helps).")
    if not yes and not hw.sim:
        con.ask("Sensor check: push the cup UP about 5 mm by hand and keep holding it, then press Enter ")
        if "P" not in m.pins():
            raise CalError("The probe did not trigger when the cup was pushed up. Check the slotted sensor and its flag before probing.")
        con.ask("Now let go of the cup and press Enter ")
        if "P" in m.pins():
            raise CalError("The probe stays triggered after letting go. Check the spring buffer moves freely.")
        con.say("sensor OK")
    _, z_top = m.position()
    p0 = cfg.pocket(0)
    m.move(cfg.feed_xy, x=machine_x(cfg, p0.x, p0.y))
    m.wait_idle()
    floor = max(z_top - cfg.c_max - extra_depth, z_floor(cfg))  # never ask for a target past the Z soft limit
    con.say(f"probing down from Z {z_top:.1f} to at most Z {floor:.1f} at {cfg.feed_probe:.0f} mm/min (first time: keep a hand near the e-stop)")
    hit = walk_down(m, z_top, floor, cfg.probe_window, cfg.feed_probe, vac, cfg.vac_seal_kpa)
    if hit is None:
        m.move(cfg.feed_z, z=z_top)
        m.wait_idle()
        raise CalError(f"No contact down to Z {floor:.1f}. Either the head sits higher than the CAD (check the Z home switch and the "
                       f"head foot: the cup face must reach the pad before Z {cfg.z_min:g}, the controller's lower limit), or the sensor is not working.")
    hits = []
    for _ in range(3):
        m.move(cfg.feed_z, z=hit + 5)
        m.wait_idle()
        h = m.probe(max(hit - 3, z_floor(cfg)), cfg.feed_probe)  # a low pad must not push the target past the soft limit
        if h is None:
            raise CalError("Lost contact on a repeat probe - is the pad loose or the cup wobbling?")
        hits.append(h)
    pad = sum(hits) / len(hits)
    spread = max(hits) - min(hits)
    travel = z_top - pad
    m.move(cfg.feed_z, z=min(z_top, pad + cfg.c_safe_empty))
    m.wait_idle()
    updates: dict = {"pad_trigger_c": round(pad, 3)}
    notes = [f"calibrate z {time.strftime('%Y-%m-%d %H:%M')}: pad trigger at Z {pad:.3f} (repeat spread {spread:.3f} mm), Z travel above the pad {travel:.1f} mm"]
    if vac is not None:
        # The cup is known empty and vented here: this is the sensor's atmosphere reading. The run compares
        # against it before every grip (a slab still stuck to the cup reads only a little below it).
        vac.release()
        k_atm = sum(vac.kpa() for _ in range(5)) / 5
        if -6.0 <= k_atm <= 6.0:
            updates["vac_baseline_kpa"] = round(k_atm, 2)
            notes.append(f"vacuum sensor zero (empty cup, vented) {k_atm:.2f} kPa")
        else:
            con.say(f"WARNING: the vacuum sensor reads {k_atm:.1f} kPa with an empty, vented cup (expect about 0). Not stored: check its 5 V supply and the 10k/20k divider (selftest).")
    if travel < cfg.c_max:
        if travel - 1.0 < cfg.c_safe_loaded + 1.0:
            raise CalError(f"Z travel above the pad is only {travel:.1f} mm; the machine needs {cfg.c_safe_loaded + 2:.0f} mm to carry a slab over the rods. "
                           "Raise the head on the Z plate (or the Z home switch) and calibrate again. Nothing was written.")
        updates["c_max"] = round(travel - 1.0, 1)
        notes.append(f"c_max lowered to {updates['c_max']} (the Z switch is lower than the CAD's {cfg.c_max})")
    write_overrides(cal_path, updates, "\n".join(notes))
    for n in notes:
        con.say(n)
    if spread > 0.3:
        con.say(f"WARNING: repeat spread {spread:.2f} mm is large (expect < 0.1). Check the cup is tight and the pad lies flat.")
    con.say(f"wrote {cal_path}")
    return {"pad_trigger_c": pad, "spread": spread, "travel": travel, **updates}


# ---------------------------------------------------------------------- calibrate x
def calibrate_x(cfg: Config, hw, con: Console, cal_path: Path, rods: bool = True) -> dict:
    """Operator centres the awl on pocket 0 and pocket 12 -> offset_x and a scale check."""
    m = hw.motion
    con.say("calibrate x: fit the AWL adapter in place of the cup. You will centre the awl point over pocket 0, then over pocket 12.\n"
            "Each pocket: first centre it by eye at the safe height (X moves only), type ok; then lower it to just above the pad\n"
            "(z -10, z -1 ...; a downward move stops if the point touches), centre it exactly on the pocket centre mark, type ok.")
    m.home()
    jog = Jogger(cfg, m, con, rods=rods)
    p0, p12 = cfg.pocket(0), cfg.exceptions
    base = {p.index: machine_x(cfg, p.x, p.y) - cfg.offset_x for p in (p0, p12)}  # rotation applied, no offset
    measured: dict[int, float] = {}
    shift = 0.0
    for p in (p0, p12):
        jog.x_shift = shift
        jog.goto_pocket(p.index)
        con.say(f"--- pocket {p.index}: coarse (by eye, safe height)")
        r = jog.interact(f"pocket {p.index} coarse")
        if r is None:
            raise CalError("cancelled")
        jog.x_shift = r[0] - machine_x(cfg, p.x, p.y)  # this X is now 'the pocket centre' for the low-height rule
        con.say(f"--- pocket {p.index}: fine (lower the awl, centre exactly)")
        r = jog.interact(f"pocket {p.index} fine")
        if r is None:
            raise CalError("cancelled")
        measured[p.index] = r[0]
        shift = r[0] - machine_x(cfg, p.x, p.y)
        jog.go_safe()
    m0, m12 = measured[p0.index], measured[p12.index]
    off0, off12 = m0 - base[p0.index], m12 - base[p12.index]
    offset_x = (off0 + off12) / 2
    expected = base[p12.index] - base[p0.index]
    got = m12 - m0
    err = got - expected
    scale = got / expected - 1
    steps_now = 80.0  # CONTRACT: X 80 steps/mm (GT2 20T, 1/16)
    lines = [
        f"calibrate x {time.strftime('%Y-%m-%d %H:%M')}: pocket 0 at machine X {m0:.3f}, pocket {p12.index} at {m12:.3f}",
        f"distance {got:.3f} mm vs {expected:.3f} expected -> error {err:+.3f} mm ({scale * 100:+.3f} %)",
        f"offset_x = {offset_x:.3f} (mean of {off0:.3f} and {off12:.3f}; worst pocket off by {abs(err) / 2:.2f} mm)",
    ]
    write_overrides(cal_path, {"offset_x": round(offset_x, 3)}, "\n".join(lines))
    for ln in lines:
        con.say(ln)
    if abs(err) > 1.5:
        con.say(f"WARNING: the row is {abs(err):.1f} mm longer/shorter than the machine thinks. Pocket play is +/-1.85 mm, so fix this:\n"
                f"  check belt tension and the pulley grub screws first. If the bed holes were laid out by hand (not with `mark`),\n"
                f"  set X steps/mm in firmware/fluidnc/config.yaml to {steps_now * got / expected:.3f} (now {steps_now:g}) and calibrate again.")
    con.say(f"wrote {cal_path}")
    return {"offset_x": offset_x, "error_mm": err, "scale": scale, "m0": m0, "m12": m12}


# ---------------------------------------------------------------------- mark (drill template)
def mark_positions(cfg: Config) -> list[dict]:
    """Every pocket cell with the machine X of its centre and of the template's two dimples.
    The station cell needs no holes of its own: its side rods belong to its neighbours."""
    xs = [p.x for p in cfg.pockets]
    pitch = min(b - a for a, b in zip(xs, xs[1:]))
    out = []
    for p in cfg.pockets:
        cx = machine_x(cfg, p.x, p.y)
        out.append({"pocket": p.index, "cell": round((p.x - xs[0]) / pitch), "bed_x": p.x, "centre": cx, "left": cx - DIMPLE_DX, "right": cx + DIMPLE_DX})
    return out


def mark_order(cfg: Config, start: int | None = None, only: list[int] | None = None) -> list[dict]:
    """Pockets to mark, in order: those whose two dimples are both inside the X travel first, then the
    end pockets (one dimple is past the travel limit), so their neighbour's shared holes exist by then.

    ``start``: continue from that pocket IN THIS ORDER (after a break). The end pockets 0 and 12 come
    last in the order, so `--start 6` still ends with 0 and 12. ``only``: just these pockets."""
    lo, hi = cfg.x_travel
    rows = mark_positions(cfg)
    for r in rows:
        r["reach"] = [k for k in ("left", "right") if lo <= r[k] <= hi]
    order = [r for r in rows if len(r["reach"]) == 2] + [r for r in rows if len(r["reach"]) < 2]
    if only is not None:
        return [r for r in order if r["pocket"] in only]
    if start is not None:
        i = next((n for n, r in enumerate(order) if r["pocket"] == start), None)
        if i is None:
            raise CalError(f"--start {start}: there is no pocket {start}")
        return order[i:]
    return order


def shared_sides(cfg: Config, pocket: int) -> dict[str, int]:
    """Side wall lines of this pocket's cell whose two holes belong to the neighbour pocket that comes
    EARLIER in the full marking order (so they are already drilled when this one is marked).
    {'left': 4} = the left-hand side holes are pocket 4's. The station cell has no pocket, so the
    pockets beside it share nothing on that side."""
    order = mark_order(cfg)
    rank = {r["pocket"]: n for n, r in enumerate(order)}
    by_cell = {r["cell"]: r["pocket"] for r in order}
    me = next(r for r in order if r["pocket"] == pocket)
    out = {}
    for side, dc in (("left", -1), ("right", 1)):
        nb = by_cell.get(me["cell"] + dc)
        if nb is not None and rank[nb] < rank[pocket]:
            out[side] = nb
    return out


def drill_instruction(cfg: Config, pocket: int) -> str:
    """What to drill through the template on this pocket: never the bosses over a neighbour's holes."""
    shared = shared_sides(cfg, pocket)
    if not shared:
        return f"Drill all {TEMPLATE_HOLES} rod holes square to the bed (drill guide)."
    new = TEMPLATE_HOLES - SIDE_HOLES * len(shared)
    skip = " and ".join(f"the {SIDE_HOLES} {side.upper()}-hand side bosses (over pocket {nb}'s holes)" for side, nb in shared.items())
    return (f"Drill only the {new} NEW rod holes, square to the bed (drill guide). Skip {skip}: those holes are already drilled, and "
            "drilling them again through this template would re-cut them oval (the template is placed by its dimples, a few tenths "
            "of a mm off the neighbour's) and the dowels would lean.")


def mark(cfg: Config, hw, con: Console, start: int | None = None, only: list[int] | None = None) -> list[int]:
    """Walk the awl over every pocket so the printed drill_template is aligned to the machine's own X axis:
    the awl drops into the template's left dimple, then its right dimple (centre +/- 40 mm), the operator
    clamps the template and drills the 8 rod holes. Holes drilled this way sit exactly where the machine
    thinks the pockets are, whatever the belt or switch position.

    Pocket 0's left dimple and pocket 12's right dimple are outside the X travel. Those two pockets are
    done last: two 8 mm pins through the template's shared-side holes into the neighbour's holes set it,
    and the one reachable dimple checks it.

    Every template is placed by its own dimples (referenced to the machine), so a side whose holes a
    neighbour already drilled is never drilled again (see drill_instruction). The head only moves on to
    the next pocket after the operator types 'clear' (drill and hands off the bed), and every sideways
    move is slow (MARK_FEED_X): the motors stay energised (Z must hold), the drill is right there."""
    allpos = mark_positions(cfg)
    rows = mark_order(cfg, start, only)
    con.say("mark: for drilling the rod holes. The bed must have NO rods and nothing taller than the template on it -\n"
            "the awl moves sideways just above the template. Fit the awl adapter in place of the cup; set its pin so\n"
            "the point is level with where the cup face was (within 2 mm).")
    con.say("order: " + ", ".join(str(r["pocket"]) for r in rows))
    if not con.confirm("The bed has no rods and the awl is fitted?"):
        raise CalError("cancelled")
    m = hw.motion
    m.home()
    jog = Jogger(cfg, m, con, rods=False)
    z_touch = None
    done: list[int] = []
    lowest = z_floor(cfg)

    def touch(what: str) -> float:
        floor = max(lowest, (z_touch - 4.0) if z_touch is not None else cfg.pad_trigger_c - 6.0)
        if z_touch is not None and jog.move_z(z_touch + 15.0) is not None:
            raise CalError(f"The awl touched something 15 mm above the template. Clear the bed and run `mark --start {r['pocket']}`.")
        hit = walk_down(m, jog.z, floor, cfg.probe_window, cfg.feed_probe)
        jog.refresh()
        if hit is None:
            raise CalError(f"The awl never touched the {what} down to Z {floor:.1f}. Check the probe sensor, the awl pin length, and that the template is under the awl.")
        return hit

    for r in rows:
        i = r["pocket"]
        con.say(f"=== pocket {i} (cell {r['cell']}, bed X {r['bed_x']:.1f}, machine X {r['centre']:.2f}, dimples at {r['left']:.2f} / {r['right']:.2f})")
        jog.move_z(jog.top())
        if len(r["reach"]) == 2:
            jog.move_x(r["left"], MARK_FEED_X)
            con.ask("Put the template on this cell with its LEFT dimple under the awl point. Press Enter - the awl comes down until it touches ")
            hit = touch("template")
            if z_touch is None:
                z_touch = hit
            con.ask("Nudge the template until the point sits IN the left dimple. Press Enter ")
            jog.move_z(z_touch + 15.0)
            jog.move_x(r["right"], MARK_FEED_X)
            jog.move_z(z_touch - 4.0)  # probe move: stops in (or on) the right dimple
            con.ask("Swing the template (pivot on the left dimple) until the RIGHT dimple is under the point. Clamp it. Press Enter ")
        elif len(r["reach"]) == 1:
            side = r["reach"][0]
            nb = i + 1 if side == "right" else i - 1
            shared = "right" if side == "right" else "left"
            jog.move_x(r[side], MARK_FEED_X)
            con.ask(f"Put the template on this cell. Push two 8 mm pins (drill bits) through its {shared.upper()}-hand guide holes into pocket {nb}'s "
                    f"already-drilled {'left' if shared == 'right' else 'right'}-hand holes. Press Enter - the awl comes down onto the {side} dimple ")
            hit = touch(f"{side} dimple")
            if z_touch is None:
                z_touch = hit
            con.ask(f"The point should sit in the {side} dimple. If it is off by more than 1 mm, stop: pocket {nb} was drilled off, or X lost steps. "
                    "Otherwise clamp the template and press Enter ")
        else:
            con.say(f"pocket {i}: neither dimple is reachable - skipped")
            continue
        jog.move_z(jog.top())
        away = [q for q in allpos if abs(q["pocket"] - i) >= 3]
        if away:  # park the head 3 pockets away so the drill has room
            jog.move_x(min(away, key=lambda q: abs(q["pocket"] - i))["centre"], MARK_FEED_X)
        con.say(drill_instruction(cfg, i))
        answer = ""
        while answer not in ("clear", "s", "q"):
            answer = con.ask("When the drill and your hands are OFF the bed, type 'clear' - the head then moves to the next pocket "
                             "(s = drilled, stop here; q = stop): ").strip().lower()
            if answer not in ("clear", "s", "q"):
                con.say("The head does not move until you type 'clear'.")
        if answer == "q":  # also end of input: nobody confirmed the bed is clear, so nothing moves any more
            con.say(f"stopped at pocket {i} (not recorded as drilled: if you did drill it, do not mark it again)")
            break
        done.append(i)
        if answer == "s":
            break
    left = [r["pocket"] for r in rows if r["pocket"] not in done]
    if left:
        con.say(f"not marked yet: {left}; continue with: python -m slabscan mark --start {left[0]}  (or --only {','.join(map(str, left))})")
    con.say(f"marked pockets {done}. The station cell needs no holes of its own.")
    return done


# ---------------------------------------------------------------------- focus
def sharpness(img: np.ndarray) -> float:
    """Focus score: mean Laplacian variance of the sharpest 10% of tiles (ignores empty background)."""
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(g, cv2.CV_64F)
    h, w = g.shape
    t = max(16, min(h, w) // 10)
    vals = sorted((float(lap[y:y + t, x:x + t].var()) for y in range(0, h - t + 1, t) for x in range(0, w - t + 1, t)), reverse=True)
    if not vals:
        return float(lap.var())
    k = max(1, len(vals) // 10)
    return float(np.mean(vals[:k]))


def _decoded(cfg: Config, img, side: str) -> list[str]:
    reads, _ = decode_frame(img, side, cfg.custom_regex, allow_ocr=False)
    return sorted({f"{r.source}:{r.cert}" for r in reads})


def aim_over_empty_pocket(cfg: Config, r, con: Console, out_dir: Path) -> str:
    """The head camera's aim, from its view over the empty exception pocket, checked as a learned run checks it
    (Runner._take_baseline, facedown.aim_problem): the head goes over pocket 12, probes it (it must be empty) and looks
    from the empty travel height. Returns "ok", what is wrong, or why it was not checked. The picture, with the card
    window drawn in, goes to out_dir/focus_head_empty.jpg."""
    from .facedown import describe, draw_window, frame_view_mm, image_rects

    ex = cfg.exceptions
    top = r._find_top(ex)
    if top is None or top >= cfg.t_min / 2:
        msg = f"not checked: pocket {ex.index} is not empty (the aim is checked on the view over an empty pocket)"
        con.say(f"camera aim: {msg}")
        return msg
    frame = r._frames(r.head_cam, "head", 1)[0]
    spec = cfg.cam_head or {}
    view = frame_view_mm(frame.shape, r._hover_mm(), spec, r.head_cam)
    rects = image_rects(cfg.face_down_window_mm, str(spec.get("row_axis", "x")))
    pic = out_dir / "focus_head_empty.jpg"
    cv2.imwrite(str(pic), draw_window(frame, rects, view))
    why = r._aim(describe(frame, rects, view))
    if why:
        con.say(f"camera aim: FAIL - {why}. Shim the camera board (BUILD_GUIDE 7.7) and run focus head again. Picture: {pic}")
        return why
    con.say(f"camera aim: OK - over the empty pocket {ex.index} the card window shows only the pad (red boxes in {pic})")
    return "ok"


def stored_aim(cfg: Config, refs_path: Path | None) -> tuple[str, str]:
    """(status, detail) of the camera aim the last learned run measured (its view over an empty pocket, kept in
    card_backs.npz): PASS, FAIL, or WARN when there is none yet."""
    from .facedown import CardBackRefs

    if refs_path is None or not Path(refs_path).exists():
        return "WARN", "not checked yet: the first run in learned mode checks it over an empty pocket (or run focus head)"
    refs = CardBackRefs(refs_path, cfg.face_down_window_mm)
    meta = refs.baseline_meta
    if refs.baseline is None or "aim" not in meta:
        return "WARN", f"not checked yet ({refs.note or 'no view over an empty pocket in ' + str(refs_path)}): the next learned run checks it"
    where = f"batch {meta.get('batch', '-')}, pocket {meta.get('pocket', '-')}"
    if meta["aim"]:
        return "FAIL", f"{meta['aim']} ({where}). The learned face-down check accepts nothing until it is re-aimed (BUILD_GUIDE 7.7)"
    return "PASS", f"the card window over an empty pocket showed only the pad ({where})"


def focus(cfg: Config, hw, con: Console, which: str, out_dir: Path, motion: bool = True, frames: int = 30, save: bool = False,
          cal_path: Path | None = None, lens_from: float | None = None, lens_to: float | None = None, lens_step: float = 0.25, settle_s: float | None = None) -> dict:
    """Live sharpness + decode for one camera. The station camera (Pi Camera Module 3) is swept
    over LensPosition and the best value recommended (``save`` writes it to calibration.toml)."""
    if which not in ("head", "station"):
        raise CalError("focus head|station")
    out_dir.mkdir(parents=True, exist_ok=True)
    side = "back" if which == "head" else "front"
    cam = hw.head_cam if which == "head" else hw.station_cam
    light = getattr(hw.lights, which)
    settle = (0.0 if hw.sim else 0.4) if settle_s is None else settle_s
    r = _scratch_runner(cfg, hw, out_dir) if motion else None
    result: dict = {"camera": which}
    try:
        if motion:
            con.say("Put ONE slab face-down on the bare pad of pocket 0, label end toward you.")
            r._home()
            if which == "head":
                result["camera_aim"] = aim_over_empty_pocket(cfg, r, con, out_dir)
                top = r._find_top(cfg.pocket(0))
                if top is None or top < cfg.t_min / 2:
                    raise CalError("Pocket 0 is empty: put one slab face-down on it.")
                r._probe(r.c(top) + cfg.approach_gap, r.c(top) - 3.0)  # cup resting on the slab = the held-slab distance
            else:
                r.pick_top(0)
                sx, sy = cfg.station_xy
                r._go(sx, sy)
                r._z(r.c(cfg.station_read_c))
        light(True)
        if settle:
            time.sleep(settle)
        if which == "station" and hasattr(cam, "set_lens_position"):
            check = (lambda: r._check_vacuum("during the focus sweep")) if r is not None and r.holding else None
            result.update(_lens_sweep(cfg, cam, con, side, out_dir, lens_from, lens_to, lens_step, settle, check))
            if save and cal_path is not None:
                spec = {**cfg.cam_station, "lens_position": round(result["recommended"], 2)}
                write_overrides(cal_path, {"cam_station": spec}, f"focus station {time.strftime('%Y-%m-%d %H:%M')}: LensPosition {spec['lens_position']}")
                con.say(f"wrote cam_station.lens_position = {spec['lens_position']} to {cal_path}")
        else:
            if which == "head":
                if not motion:
                    con.say("camera aim: not checked without motion (it needs the view over an empty pocket: run focus head on the machine)")
                con.say("Turn the M12 lens slowly; watch the score climb, go past the peak, come back to it. Lock the lens nut. Ctrl-C ends.")
            best = (-1.0, None, [])
            try:
                for i in range(frames):
                    img = cam.capture()
                    s = sharpness(img)
                    dec = _decoded(cfg, img, side)
                    if s > best[0]:
                        best = (s, img, dec)
                    bar = "#" * int(min(40, 40 * s / max(best[0], 1e-9)))
                    con.say(f"{i + 1:3d}  sharpness {s:9.1f}  best {best[0]:9.1f}  {bar:40s} {'READ ' + ', '.join(dec) if dec else 'no read'}")
            except KeyboardInterrupt:
                pass
            if best[1] is not None:
                p = out_dir / f"focus_{which}_best.jpg"
                cv2.imwrite(str(p), best[1])
                result.update(best_sharpness=best[0], best_decoded=best[2], image=str(p))
    finally:
        light(False)
        # after a lost controller (E-stop) nothing may move: the error that got us here is reported instead
        if r is not None and getattr(hw.motion, "homed", True) and not getattr(hw.motion, "lost", False):
            if r.holding or r.freeze:
                note = r.secure()  # puts the slab back (or sets a weakly held one down) - or, after a fault, moves nothing
                if note:
                    con.say(note)
            elif r.homed:
                r._z(r.c(cfg.c_safe_empty))
    return result


def _lens_sweep(cfg, cam, con, side, out_dir, lens_from, lens_to, lens_step, settle, check=None) -> dict:
    rng = cam.lens_range() if hasattr(cam, "lens_range") else None
    centre = float(cfg.cam_station.get("lens_position") or 1 / 0.14)
    lo = lens_from if lens_from is not None else centre - 2.0
    hi = lens_to if lens_to is not None else centre + 2.0
    if rng:
        lo, hi = max(lo, rng[0]), min(hi, rng[1])
    n = int(round((hi - lo) / lens_step)) + 1
    rows = []
    con.say(f"sweeping LensPosition {lo:.2f} .. {hi:.2f} dioptres in {lens_step} steps (1/0.14 m = 7.14)")
    for i in range(max(1, n)):
        if check is not None:
            check()  # the slab hangs over the bare lens for the whole sweep: stop (and put it back) if the vacuum drops
        lp = round(lo + i * lens_step, 3)
        cam.set_lens_position(lp)
        if settle:
            time.sleep(settle)
            cam.capture()  # one frame may still be from the old lens position
        imgs = [cam.capture() for _ in range(2)]
        s = max(sharpness(im) for im in imgs)
        dec = sorted({d for im in imgs for d in _decoded(cfg, im, side)})
        rows.append((lp, s, dec, imgs[-1]))
        con.say(f"  LensPosition {lp:6.2f}  sharpness {s:9.1f}  {'READ ' + ', '.join(dec) if dec else 'no read'}")
    reading = [row for row in rows if row[2]]
    pool = reading or rows
    best = max(pool, key=lambda row: row[1])
    window = (min(row[0] for row in reading), max(row[0] for row in reading)) if reading else None
    cam.set_lens_position(best[0])
    p = out_dir / "focus_station_best.jpg"
    cv2.imwrite(str(p), best[3])
    con.say(f"recommended LensPosition {best[0]:.2f} (sharpest{' that decoded' if reading else ' - NOTHING DECODED, check lighting/label position'})"
            + (f"; it decodes from {window[0]:.2f} to {window[1]:.2f}" if window else ""))
    return {"recommended": best[0], "decode_window": window, "sweep": [(lp, s, dec) for lp, s, dec, _ in rows], "image": str(p)}


# ---------------------------------------------------------------------- selftest
class SelfTest:
    def __init__(self, con: Console):
        self.con = con
        self.results: list[tuple[str, str, str]] = []

    def rec(self, name: str, status: str, detail: str) -> None:
        self.results.append((name, status, detail))
        self.con.say(f"[{status:4}] {name}: {detail}")

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for _, s, _ in self.results)


CARRY_SWEEP_MM = 3.0  # selftest --motion: the carry sensor is read from carry_sensor_c0 + this down to carry_sensor_c0 - this
CARRY_SWEEP_STEP = 0.25


def carry_sweep(cfg: Config, m, carry, t: SelfTest) -> float | None:
    """Selftest of the carry-height sensor, with the machine homed (head at the top): it must read blocked there; then,
    over pocket 0, the head steps down from carry_sensor_c0 + 3 mm to carry_sensor_c0 - 3 mm in probe moves (they stop
    on any contact) and the trip height is where it turns clear. It must read blocked from carry_sensor_c0 + CARRY_BAND_MM
    up and clear from carry_sensor_c0 - CARRY_BAND_MM down (the run's rule). The head goes back up to where homing left
    it. Returns the measured trip height (s, mm), or None."""
    from .config import CARRY_BAND_MM

    c0, pad = cfg.carry_sensor_c0, cfg.pad_trigger_c
    x_top, z_top = m.position()
    if not carry.blocked():
        t.rec("carry sensor", "FAIL", f"reads CLEAR with the head at the top (Z {z_top:.1f}): its flag must block the beam there. Cut or "
                                      "unplugged lead (GPIO 6, WIRING.md), flag missing or bent, or the sensor mount slid down")
        return None
    p0 = cfg.pocket(0)
    m.move(cfg.feed_xy, x=machine_x(cfg, p0.x, p0.y))  # at the top: nothing on the bed reaches up here
    m.wait_idle()
    readings: list[tuple[float, bool]] = []
    h = c0 + CARRY_SWEEP_MM
    try:
        while h >= c0 - CARRY_SWEEP_MM - 1e-9:
            hit = m.probe(h + pad, cfg.feed_probe)
            if hit is not None:
                t.rec("carry sensor", "FAIL", f"the cup touched something at {hit - pad:.1f} mm over pocket 0 while stepping down: clear the bed")
                return None
            readings.append((round(h, 3), bool(carry.blocked())))
            h -= CARRY_SWEEP_STEP
    finally:
        m.move(cfg.feed_z, z=z_top)
        m.wait_idle()
        m.move(cfg.feed_xy, x=x_top)
        m.wait_idle()
    bad = [(hh, b) for hh, b in readings if (hh >= c0 + CARRY_BAND_MM and not b) or (hh <= c0 - CARRY_BAND_MM and b)]
    lowest_blocked = min((hh for hh, b in readings if b), default=None)
    trip = None if lowest_blocked is None else round(lowest_blocked - CARRY_SWEEP_STEP / 2, 2)
    seen = "; ".join(f"{hh:.2f} {'B' if b else 'c'}" for hh, b in readings[:: max(1, len(readings) // 8)])
    if bad:
        t.rec("carry sensor", "FAIL", f"must read blocked from {c0 + CARRY_BAND_MM:.1f} mm up and clear from {c0 - CARRY_BAND_MM:.1f} mm down; "
                                      f"it read {'BLOCKED' if bad[0][1] else 'CLEAR'} at {bad[0][0]:.2f} mm (trip near {trip} mm). Slide the "
                                      f"sensor mount along its slot until it just reads blocked at {c0:.1f} mm (BUILD_GUIDE 7.4a); if it never "
                                      "changes, clean the slot and check the emitter. Readings (B = blocked): " + seen)
        return trip
    t.rec("carry sensor", "PASS", f"blocked at the top, trips at about {trip} mm (set {c0:.1f}, allowed +/-{CARRY_BAND_MM:g}); clear below")
    return trip


def selftest(cfg: Config, con: Console, hw=None, sim: bool = False, interactive: bool = False, do_motion: bool = False, out_dir: Path = Path("selftest"),
             cal_path: Path | None = None) -> int:
    """Check every part on its own; a failing part does not stop the others. Exit code 1 if anything FAILs.
    ``cal_path``: with -i, the empty-cup vacuum reading can be stored there as the sensor zero."""
    from .factory import MachineLock, make_part

    t = SelfTest(con)
    out_dir.mkdir(parents=True, exist_ok=True)
    opened = []
    lock = None
    if hw is None and not sim:
        lock = MachineLock()
        lock.acquire()  # raises MachineBusy if the web service or another command has the machine

    def part(name):
        if hw is not None:
            return getattr(hw, name)
        try:
            dev = make_part(cfg, name)
            opened.append(dev)
            return dev
        except Exception as e:  # noqa: BLE001
            t.rec(name, "FAIL", f"cannot open: {e}")
            return False

    # config
    n_src = len(cfg.sources)
    t.rec("config", "PASS" if len(cfg.pockets) == 13 and n_src == 11 else "WARN", f"{len(cfg.pockets)} pockets, {n_src} sources, capacity {cfg.capacity}, station X {cfg.station_xy[0]}")
    if cfg.pad_trigger_c == 0.0 and cfg.offset_x == 0.0 and not sim:
        t.rec("calibration", "WARN", "not calibrated yet: run `calibrate z` and `calibrate x`")
    else:
        t.rec("calibration", "PASS", f"pad_trigger_c {cfg.pad_trigger_c}, offset_x {cfg.offset_x}")
    t.rec("ocr", "PASS" if ocr_available() else "WARN", "tesseract found" if ocr_available() else "tesseract missing: OCR fallback off (apt install tesseract-ocr)")

    # controller
    m = part("motion")
    if m:
        try:
            if hasattr(m, "send"):
                ver = [ln for ln in m.send("$I") if "VER" in ln]
                state, _ = m.status()
                t.rec("controller", "PASS", f"{ver[0] if ver else 'connected'}; state {state}")
            else:
                t.rec("controller", "PASS", "simulated")
            pins = m.pins() if hasattr(m, "pins") else ""
            if "P" in pins:
                t.rec("probe", "FAIL", "reads TRIGGERED at rest. Wired fail-safe, so: cut wire, unplugged sensor, blocked slot - or the cup is resting on something.")
            else:
                t.rec("probe", "PASS", "not triggered at rest" + (f" (other active pins: {pins})" if pins else ""))
            if interactive and hasattr(m, "send"):
                con.ask("Push the cup UP ~5 mm by hand and hold it, then press Enter ")
                t.rec("probe trigger", "PASS" if "P" in m.pins() else "FAIL", "triggers when pushed" if "P" in m.pins() else "did NOT trigger when the cup was pushed up")
                con.ask("Let go, press Enter ")
            if do_motion:
                m.home()
                x, z = m.position()
                t.rec("homing", "PASS", f"homed: X {x:.2f}, Z {z:.2f}")
        except Exception as e:  # noqa: BLE001
            t.rec("controller", "FAIL", str(e))

    # vacuum
    vac = part("vacuum")
    if vac:
        try:
            # Read BEFORE venting: after a stop that left a slab sealed on the cup, a vent would drop it.
            k_pre = sum(vac.kpa() for _ in range(5)) / 5
            ref = cfg.vac_baseline_kpa
            low = k_pre < (ref - 2.0 if ref is not None else -6.0)
            if low and not (interactive and con.confirm(f"The cup line reads {k_pre:.1f} kPa, below an empty cup. Is the cup EMPTY (no slab on it)?")):
                raise CalError(f"the cup line holds vacuum ({k_pre:.1f} kPa): a slab may be on the cup. Not vented. Hold the slab, then vent by hand "
                               "(OPERATING.md 8.2); run selftest again with the cup empty")
            vac.release()
            k0 = sum(vac.kpa() for _ in range(5)) / 5
            if -6 <= k0 <= 6:
                t.rec("vacuum sensor", "PASS", f"{k0:.1f} kPa at atmosphere")
            elif k0 < -90:
                t.rec("vacuum sensor", "FAIL", f"{k0:.0f} kPa at atmosphere = 0 V input: sensor unpowered, ADS1115 A0 not connected, or divider open")
            else:
                t.rec("vacuum sensor", "WARN", f"{k0:.1f} kPa at atmosphere (expect about 0): check the sensor supply is 5 V and the divider is 10k/20k")
            if interactive and cal_path is not None and -6 <= k0 <= 6 and con.confirm(f"Store {k0:.2f} kPa as the empty-cup sensor zero (the cup is empty and vented)?", default=True):
                write_overrides(cal_path, {"vac_baseline_kpa": round(k0, 2)}, f"selftest {time.strftime('%Y-%m-%d %H:%M')}: empty-cup vacuum sensor zero {k0:.2f} kPa")
                t.rec("vacuum zero", "PASS", f"stored vac_baseline_kpa = {k0:.2f} in {cal_path}")
            vac.hold()
            time.sleep(0.8)
            k1 = vac.kpa()
            vac.release()
            t.rec("pump + valve (open cup)", "PASS" if k1 < k0 - 0.5 or sim else "WARN", f"{k1:.1f} kPa with the cup open (a small vacuum shows the pump and valve work)")
            if interactive:
                con.ask("Press a slab flat against the cup and KEEP holding it, then press Enter ")
                vac.hold()
                t0 = time.monotonic()
                while time.monotonic() - t0 < 2.0 and vac.kpa() > cfg.vac_seal_kpa:
                    time.sleep(0.02)
                ks = vac.kpa()
                t.rec("seal", "PASS" if ks <= cfg.vac_seal_kpa else "FAIL", f"{ks:.0f} kPa after {time.monotonic() - t0:.2f} s (need <= {cfg.vac_seal_kpa:.0f})")
                vac.close()  # valves shut, pump off: does the cup hold?
                a = vac.kpa()
                time.sleep(2.0)
                b = vac.kpa()
                rate = (b - a) / 2
                hang = f"; a slab would hang about {(-1.7 - b) / rate:.0f} s on the closed line (it falls near -1.7 kPa)" if rate > 0.01 and b < -1.7 else ""
                t.rec("leak", "PASS" if b - a < 5 else "WARN", f"{rate:.1f} kPa/s with the valves shut (cup, check valve and fittings){hang}")
                con.ask("Keep holding the slab; press Enter to vent (it will let go) ")
                vac.release()
                kv = vac.kpa()
                # the slab only lets go near -1.7 kPa (at -5 kPa the cup still holds ~3x its weight): the vent must
                # bring the line back to atmosphere, not just 'mostly'
                t.rec("vent valve", "PASS" if kv > k0 - 1.0 else "FAIL", f"{kv:.1f} kPa after venting (atmosphere {k0:.1f}; must be within 1 kPa)")
        except CalError as e:
            t.rec("vacuum", "FAIL", str(e))
        except Exception as e:  # noqa: BLE001
            t.rec("vacuum", "FAIL", str(e))

    # lights + cameras
    lights = part("lights")
    if lights:
        try:
            for _ in range(3):
                for on in (True, False):
                    lights.head(on)
                    lights.station(on)
                    time.sleep(0.0 if sim else 0.3)
            ok = (not interactive) or con.confirm("Did both LED rings blink 3 times?", default=True)
            t.rec("LED rings", "PASS" if ok else "FAIL", "blinked" if ok else "operator saw no blink: check GPIO 23/24 MOSFET modules and 24 V")
        except Exception as e:  # noqa: BLE001
            t.rec("LED rings", "FAIL", str(e))
    for name, light_name, side in (("head_cam", "head", "back"), ("station_cam", "station", "front")):
        cam = part(name)
        if not cam:
            continue
        try:
            dark = cam.capture()
            if lights:
                getattr(lights, light_name)(True)
                time.sleep(0.0 if sim else cfg.light_settle_s)
            lit = cam.capture()
            if lights:
                getattr(lights, light_name)(False)
            cv2.imwrite(str(out_dir / f"{name}.jpg"), lit)
            d, b = float(np.mean(dark)), float(np.mean(lit))
            dec = _decoded(cfg, lit, side)
            detail = f"{lit.shape[1]}x{lit.shape[0]}, brightness {d:.0f} -> {b:.0f} with the ring on, sharpness {sharpness(lit):.0f}" + (f", READ {', '.join(dec)}" if dec else "")
            t.rec(name, "PASS" if (b - d > 5 or sim) else "WARN", detail + ("" if (b - d > 5 or sim) else " (ring barely changes the image: is it on? is the light roof fitted?)"))
        except Exception as e:  # noqa: BLE001
            t.rec(name, "FAIL", str(e))

    # camera aim: what the last learned run saw over an empty pocket (focus head looks again)
    if cfg.face_down_check == "learned":
        from .facedown import FILE_NAME

        status, detail = stored_aim(cfg, None if cal_path is None else Path(cal_path).parent / FILE_NAME)
        t.rec("camera aim", status, detail)

    # beam gate + lid
    if cfg.overfill_gate:
        gate = part("gate")
        if gate:
            try:
                if gate.clear():
                    t.rec("overfill beam", "PASS", "beam received")
                    if interactive:
                        con.ask("Block the beam with your hand and press Enter ")
                        t.rec("overfill beam blocked", "PASS" if not gate.clear() else "FAIL", "sees the block" if not gate.clear() else "still reads clear: receiver sees ambient light or is wired to the wrong pin")
                else:
                    t.rec("overfill beam", "FAIL", "blocked or misaligned: nothing may stick out above the MAX line; aim the laser at the receiver")
            except Exception as e:  # noqa: BLE001
                t.rec("overfill beam", "FAIL", str(e))
    if cfg.lid_switch:
        lid = part("lid")
        if lid:
            t.rec("lid switch", "PASS" if lid.closed() else "WARN", "closed" if lid.closed() else "reads OPEN")

    # carry-height sensor (Z stall guard)
    if cfg.carry_sensor:
        carry = part("carry")
        if carry:
            try:
                if do_motion and m and getattr(m, "homed", True):
                    carry_sweep(cfg, m, carry, t)
                else:
                    t.rec("carry sensor", "PASS", f"reads {'BLOCKED' if carry.blocked() else 'CLEAR'} on GPIO 6; selftest --motion checks that it "
                                                  f"trips at carry_sensor_c0 = {cfg.carry_sensor_c0:.1f} mm")
            except Exception as e:  # noqa: BLE001
                t.rec("carry sensor", "FAIL", str(e))

    # disk
    du = shutil.disk_usage(Path(cfg.out_dir) if Path(cfg.out_dir).exists() else Path.cwd())
    t.rec("disk", "PASS" if du.free > 2e9 else "WARN", f"{du.free / 1e9:.1f} GB free (a 330-slab batch with photos is ~0.3 GB)")

    for dev in opened:
        if hasattr(dev, "close"):
            try:
                dev.close()
            except Exception:  # noqa: BLE001
                pass
    if lock is not None:
        lock.release()
    bad = [n for n, s, _ in t.results if s == "FAIL"]
    con.say("SELFTEST " + ("FAILED: " + ", ".join(bad) if bad else "PASSED") + f" (images in {out_dir}/)")
    return 1 if bad else 0
