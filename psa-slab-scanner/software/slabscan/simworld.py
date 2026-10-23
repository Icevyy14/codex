"""Physics-lite simulator of the whole machine, used to prove the run logic without hardware.

It models stacks of slabs in pockets, the cup + spring-buffer contact sensor, vacuum, a
held slab, and the two cameras (synthetic label images from sim.py; the head camera also sees the
top of the card window, a card back or the card's front, behind the head's own cup, buffer and foot).
It also acts as a
SAFETY MONITOR: any move that would crash the head or a held slab into rods/stacks,
drop a slab, drive the cup past its buffer stroke, seal the cup on a slab's FRONT, or tear
a gripped slab off its stack faster than the slow peel raises ``Crash``.

It also models the carry-height sensor (``SimCarry``: blocked for every head height from
cfg.carry_sensor_c0 up) and can inject faults into it (stuck blocked, stuck clear) and into Z
(``SimWorld.z_lost_steps``: a lift with a slab held ends short, while the controller still
reports the commanded height - a stalled Z motor).

Machine Z (``z``) is the head height at which the probe trips on a surface, as the real
calibration defines it. At the trip the spring buffer is already compressed by
``trigger_compression`` (2 mm), so a gripped slab only leaves its stack once the head has
risen that far above the trip point.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

from .config import Config
from .motion import SafetyViolation
from .sim import HEAD_VIEW_MM, Degrade, _stable_seed, empty_head_view, has_back_code, head_view, slab_view

TRIGGER_COMPRESSION = 2.0  # buffer compression at which the optical sensor trips
HEAD_SIDE_CLEAR = 7.0  # (pocket 84 - head envelope 70) / 2: an empty head may shift this far inside a pocket below the rod tops
PEEL_SLOW_MIN_MM = 0.5  # after the cup leaves the slab the slow peel must go on at least this far


class Crash(SafetyViolation):
    pass


@dataclass
class SimSlab:
    cert: str
    thickness: float = 6.6
    # label era (sim.PSA_ERAS / CGC_ERAS): PSA current | 2017+ (back QR; ITF up to 8 digits, Code128 for 9) | 2016 (back
    # ITF only) | old (front ITF only); CGC 2023+ | og | authentic. BGS and SGC labels carry no code.
    era: str = "2017+"
    grader: str = "PSA"
    face_down: bool = True
    back: str = "pokemon_en"  # card back seen through the slab when face-down: pokemon_en | pokemon_jp (sim.card_back)
    front: str = "art"  # card front seen when face-up: art (sim.card_front) | plain (sim.plain_front, one colour)
    clingy: bool = False  # sticks to the slab above it when that one is lifted (double pick)
    seal_fails: bool = False  # cup cannot seal on this slab


@dataclass
class SimWorld:
    cfg: Config
    stacks: dict[int, list[SimSlab]] = field(default_factory=dict)  # bottom -> top
    held: list[SimSlab] = field(default_factory=list)  # [gripped slab, clinging slab...]
    x: float = 0.0
    y: float = 0.0
    z: float = 250.0  # cup face height = machine Z (pad_trigger_c is 0 in the sim)
    vacuum_on: bool = False
    gripping: bool = False
    seed: int = 1
    events: list[str] = field(default_factory=list)
    rng: random.Random = field(default_factory=lambda: random.Random(1))
    trigger_compression: float = TRIGGER_COMPRESSION  # buffer travel between first touch and the probe trip
    # A clinging slab (double pick) held only by an air film: None = rides to placement; "peel" = falls back
    # onto its own stack during the peel dwell; "transit" = drops off at the end of the first sideways move.
    cling_drop: str | None = None
    peels: list[tuple[float, float]] = field(default_factory=list)  # (feed, slow mm after separation) of every pick
    # the head parts between the head camera and the slab (sim.HEADS): "cad" = the CAD head of today (lens 5 mm toward
    # the label; it leaves face_down_window_mm clear), "cad_r2" = the round-2 head, whose foot hides the card window,
    # "open" = a hypothetical narrow head
    head: str = "cad"
    # FAULT INJECTION, camera aim: the head camera tilted toward the cup by this many degrees (sim.aim_shift_mm). From
    # about 0.47 deg the cup pad comes into face_down_window_mm (the CAD head: about 0.55 deg); BUILD_GUIDE 7.7
    head_tilt_deg: float = 0.0
    # FAULT INJECTION, Z stall: the z_lost_steps_at-th upward Z move of more than 20 mm with a slab held (the lift to
    # travel height) ends z_lost_steps mm short of its target, and the controller still reports the target (SimMotion)
    z_lost_steps: float = 0.0
    z_lost_steps_at: int = 1
    held_lifts: int = 0  # upward Z moves of more than 20 mm with a slab held, so far

    # ---- geometry helpers
    def pocket_at(self, x, y, tol=3.0):
        for p in self.cfg.pockets:
            if abs(p.x - x) <= tol and abs(p.y - y) <= tol:
                return p
        return None

    def at_station(self, x, y, tol=3.0):
        sx, sy = self.cfg.station_xy
        return abs(sx - x) <= tol and abs(sy - y) <= tol

    def stack_top(self, idx) -> float:
        return sum(s.thickness for s in self.stacks.get(idx, []))

    def held_thickness(self) -> float:
        return sum(s.thickness for s in self.held)

    def lowest_point(self) -> float:
        """Lowest point of the moving head: cup face, or the bottom of what it carries."""
        return self.z - self.held_thickness()

    def surface_below(self) -> float | None:
        p = self.pocket_at(self.x, self.y)
        if p is not None:
            return self.stack_top(p.index)
        if self.at_station(self.x, self.y):
            return 30.0  # station camera mast top, well below the read height
        return None

    # ---- safety rules for XY moves
    def check_xy_path(self, x1, y1):
        lp = self.lowest_point() - self.trigger_compression  # in free travel the cup hangs below its trip-calibrated height
        if lp < self.cfg.post_h + 5:
            # only an empty head may shift a few mm inside one pocket (jog / calibration); a held slab has 1.85 mm of play
            p = self.pocket_at(self.x, self.y, tol=HEAD_SIDE_CLEAR)
            if (not self.held and p is not None and abs(p.x - x1) <= HEAD_SIDE_CLEAR and abs(p.y - y1) <= HEAD_SIDE_CLEAR
                    and lp >= self.stack_top(p.index) + 0.5):
                return
            raise Crash(f"XY move from ({self.x:.0f},{self.y:.0f}) to ({x1:.0f},{y1:.0f}) with lowest point at {lp:.1f} mm (rods are {self.cfg.post_h:.0f})")
        tallest = max((self.stack_top(i) for i in self.stacks), default=0.0)
        if lp < tallest + 5:
            raise Crash("XY move would sweep through a stack")

    def check_descent_xy(self, z1, tol=1.5):
        """Any downward motion (plain or probing) below the rod tops must be centred on a pocket or the station
        (within ``tol``: 1.5 mm with a slab, whose play is 1.85; the empty head may be off by IN_POCKET_TOL)."""
        if z1 >= self.z:
            return
        if z1 - self.held_thickness() < self.cfg.post_h + 5:
            if self.pocket_at(self.x, self.y, tol=tol) is None and not self.at_station(self.x, self.y, tol=tol):
                raise Crash(f"descending below rod tops at ({self.x:.1f},{self.y:.1f}) - not over a pocket or the station")

    def check_z(self, z1):
        """Downward motion into a pocket must be centred on it, and must not hit anything (non-probing)."""
        if z1 >= self.z:
            return
        self.check_descent_xy(z1)
        surf = self.surface_below()
        if surf is not None and z1 - self.held_thickness() < surf - 0.01:
            raise Crash(f"fast move down to {z1:.1f} hits the surface at {surf + self.held_thickness():.1f} (no probe)")


def trapezoid_s(dist: float, v_max: float, accel: float) -> float:
    """Time for a point-to-point move that starts and ends at rest (trapezoidal profile)."""
    if dist <= 0:
        return 0.0
    d_acc = v_max * v_max / accel
    if dist < d_acc:
        return 2.0 * (dist / accel) ** 0.5
    return dist / v_max + v_max / accel


class SimMotion:
    ACCEL = {"x": 2000.0, "z": 1200.0}  # mm/s^2, as in firmware/fluidnc/config.yaml
    SETTLE_S = 0.03  # command latency + settle per move

    def __init__(self, world: SimWorld, x_offset: float = 0.0, z_offset: float = 0.0):
        """x_offset / z_offset model an uncalibrated machine: machine coordinate = world + offset.
        A correct calibration then finds offset_x == x_offset and pad_trigger_c == z_offset."""
        self.w = world
        self.x_offset = x_offset
        self.z_offset = z_offset
        self.log: list[str] = []
        self.move_time_s = 0.0
        self.travel_mm = 0.0
        self.homed = False
        self.probe_targets: list[float] = []  # machine Z of every G38.3 target (tests check the soft-limit clamp)
        self.z_slip = 0.0  # mm the Z motor fell short of where the controller thinks it is (z_lost_steps); homing clears it

    def home(self):
        self.w.z = 250.0
        self.w.x, self.w.y = self.w.cfg.x_travel[0] - self.x_offset, 0.0  # FluidNC: X = 22 after homing (mpos_mm)
        self.z_slip = 0.0
        self.homed = True

    def halt(self):
        """Feed hold + soft reset: motion stops where it is and the position must be homed again."""
        self.log.append("HALT")
        self.homed = False

    def _soft_limits(self, x=None, z=None, what="move"):
        """FluidNC soft limits (firmware/fluidnc/config.yaml, machine mm): X 22..1253, Z -8..255.
        A target outside them is an ALARM on the real controller, so the simulator calls it a crash."""
        cfg = self.w.cfg
        lo, hi = cfg.x_travel
        if x is not None and not lo - 1e-6 <= x <= hi + 1e-6:
            raise Crash(f"{what} to machine X {x:.3f} is outside the X soft limits {lo:g}..{hi:g}")
        if z is not None and z < cfg.z_min - 1e-6:
            raise Crash(f"{what} to machine Z {z:.3f} is below the Z soft limit {cfg.z_min:g}")

    def wait_idle(self):
        pass

    def position(self) -> tuple[float, float]:
        """Machine (x, z), like the controller's status report."""
        return self.w.x + self.x_offset, self.w.z + self.z_offset + self.z_slip

    def pins(self) -> str:
        """Active input pins like FluidNC's Pn: field ('P' = probe triggered)."""
        w = self.w
        surf = w.surface_below()
        return "P" if surf is not None and w.z <= surf + w.held_thickness() + 0.01 else ""

    def move(self, feed, x=None, y=None, z=None):
        if not self.homed:
            raise Crash("move before homing")
        self._soft_limits(x, z)
        w = self.w
        x = None if x is None else x - self.x_offset
        y = None if y is None else y
        z = None if z is None else z - self.z_offset - self.z_slip
        if len(w.held) > 1 and w.cling_drop == "peel":
            self._drop_cling("peel")  # an air-film cling lets go right after the separation, still over its own stack
        if z is not None and z != w.z:
            w.check_z(z)
            self._account(abs(z - w.z), feed, "z")
            z0 = w.z
            w.z = z
            if z > z0:
                self._lift(z0, feed)
                if w.held and z - z0 > 20.0:
                    w.held_lifts += 1
                    if w.z_lost_steps > 0 and w.held_lifts == w.z_lost_steps_at:  # the Z motor stalls: the head stops short
                        w.z -= w.z_lost_steps
                        self.z_slip += w.z_lost_steps
                        w.events.append(f"Z lost {w.z_lost_steps:g} mm of steps lifting {w.held[0].cert} (the head is at {w.z:.1f}, the controller says {z:.1f})")
        if x is not None or y is not None:
            x1 = w.x if x is None else x
            y1 = w.y if y is None else y
            if (x1, y1) != (w.x, w.y):
                w.check_xy_path(x1, y1)
                self._account(((x1 - w.x) ** 2 + (y1 - w.y) ** 2) ** 0.5, feed, "x")
                w.x, w.y = x1, y1
                if len(w.held) > 1 and w.cling_drop == "transit":
                    self._drop_cling("end of the first sideways move")
        self.log.append(f"G1 X{w.x:.1f} Y{w.y:.1f} Z{w.z:.1f} F{feed:.0f}")

    def probe(self, z_target, feed):
        if not self.homed:
            raise Crash("probe before homing")
        self._soft_limits(z=z_target, what="probe target")
        self.probe_targets.append(z_target)
        w = self.w
        surf = w.surface_below()
        self.log.append(f"G38.3 Z{z_target:.2f}")
        z_target = z_target - self.z_offset - self.z_slip
        if surf is None:
            raise Crash("probing with nothing below")
        w.check_descent_xy(z_target, tol=1.5 if w.held else HEAD_SIDE_CLEAR - 2.0)
        contact = surf + w.held_thickness()  # head Z at which the probe trips (buffer compressed by trigger_compression)
        if contact > w.z + 0.01:
            raise Crash(f"probe started below the surface (cup {w.z:.1f}, surface {contact:.1f})")
        if contact > w.z - 0.01:
            raise Crash("probe started with the probe already triggered (FluidNC raises ALARM ProbeFailInitial)")
        trip = contact
        if trip >= z_target:
            self._account(w.z - trip, feed, "z")
            w.z = trip
            return trip + self.z_offset + self.z_slip
        # no trigger before z_target: if we passed the surface, the buffer compresses
        if z_target < contact + w.trigger_compression - w.cfg.buffer_stroke + 0.01:  # the cup first touches trigger_compression above the trip
            raise Crash("probe drove the cup past the buffer stroke")
        self._account(w.z - z_target, feed, "z")
        w.z = z_target
        return None

    def _account(self, dist, feed, axis="x"):
        self.travel_mm += dist
        self.move_time_s += trapezoid_s(dist, feed / 60.0, self.ACCEL[axis]) + self.SETTLE_S

    def _lift(self, z0: float, feed: float):
        """Called after an upward Z move from z0: the gripped slab (and any clinging slab) leaves its stack
        once the cup leaves the surface, i.e. trigger_compression above the trip height. That moment must
        happen during a slow move (feed_peel_slow) that goes on for PEEL_SLOW_MIN_MM: a fast tear is what
        drags the next slab along on an air film."""
        w = self.w
        if not (w.gripping and not w.held):
            return
        p = w.pocket_at(w.x, w.y)
        stack = w.stacks[p.index]
        sep = w.stack_top(p.index) + w.trigger_compression  # head Z at which the cup leaves the slab
        if w.z <= sep + 1e-9:
            return  # the spring is only relaxing: the cup still sits on the slab
        slow_after = w.z - max(sep, z0)
        w.peels.append((feed, slow_after))
        if feed > w.cfg.feed_peel_slow + 1e-6:
            raise Crash(f"the gripped slab was torn off its stack at F{feed:.0f} (the slow peel is F{w.cfg.feed_peel_slow:.0f}): "
                        "the peel profile does not cover the buffer compression at the trip")
        if slow_after < PEEL_SLOW_MIN_MM - 1e-9:
            raise Crash(f"the slow peel ended {slow_after:.2f} mm after the cup left the slab (needs {PEEL_SLOW_MIN_MM})")
        top = stack.pop()
        w.held = [top]
        if stack and stack[-1].clingy:
            cling = stack.pop()
            w.held.append(cling)
            w.events.append(f"double pick of {cling.cert} under {top.cert}")

    def _drop_cling(self, when: str):
        """The clinging slab lets go and lands flat on whatever is below the head (its own stack after the peel)."""
        w = self.w
        cling = w.held.pop()
        p = w.pocket_at(w.x, w.y)
        if p is None:
            raise Crash(f"a clinging slab dropped at the {when} with no pocket below (X {w.x:.0f})")
        w.stacks.setdefault(p.index, []).append(cling)
        w.events.append(f"clinging slab {cling.cert} fell into pocket {p.index} at the {when}")

    def close(self):
        pass


class SimVacuum:
    simulated = True  # the runner skips real-time dwells against the simulator

    def __init__(self, world: SimWorld):
        self.w = world

    def _touching_top(self) -> bool:
        w = self.w
        p = w.pocket_at(w.x, w.y)
        return p is not None and bool(w.stacks.get(p.index)) and w.z <= w.stack_top(p.index) + w.trigger_compression + 0.05

    def hold(self):
        w = self.w
        w.vacuum_on = True
        if not w.held and self._touching_top():
            p = w.pocket_at(w.x, w.y)
            top = w.stacks[p.index][-1]
            if not top.seal_fails and not top.face_down:
                raise Crash(f"the cup sealed on the FRONT of face-up slab {top.cert} in pocket {p.index} (visible damage)")
            w.gripping = not top.seal_fails

    def release(self):
        w = self.w
        w.vacuum_on = False
        w.gripping = False
        if w.held:
            p = w.pocket_at(w.x, w.y)
            if p is None:
                raise Crash("released a slab outside any pocket")
            gap = w.lowest_point() - w.stack_top(p.index)
            if gap > 1.0:
                raise Crash(f"released a slab {gap:.1f} mm above the stack (drop)")
            for s in reversed(w.held):  # clinging slab lands first, gripped slab on top
                w.stacks.setdefault(p.index, []).append(s)
            w.held = []

    def kpa(self) -> float:
        w = self.w
        if not w.vacuum_on:
            return 0.0
        if w.held or w.gripping:
            return -62.0
        return -4.0  # open cup in air, or a cup that cannot seal

    def close(self):
        self.w.vacuum_on = False


class SimGate:
    def __init__(self, world: SimWorld):
        self.w = world

    def clear(self) -> bool:
        w = self.w
        tallest = max((w.stack_top(i) for i in w.stacks), default=0.0)
        return tallest < w.cfg.gate_z


class SimCarry:
    """The carry-height sensor: a slotted optical switch on the Z spine and a flag on the Z carriage, blocked for every
    head height from cfg.carry_sensor_c0 up (it follows the real head height, so it sees a Z stall). ``stuck``: None =
    working, "blocked" = always blocked (dead emitter, dirt or a card in the slot), "clear" = always clear (cut lead).
    ``trip``: the head height at which it really trips (a mount set wrong), default cfg.carry_sensor_c0. Every read is
    logged with the head position it was taken at (``log``: (x, z, blocked))."""

    def __init__(self, world: SimWorld, stuck: str | None = None, trip: float | None = None):
        self.w = world
        self.stuck = stuck
        self.trip = trip
        self.log: list[tuple[float, float, bool]] = []

    def blocked(self) -> bool:
        w = self.w
        b = self.stuck == "blocked" if self.stuck is not None else w.z >= (w.cfg.carry_sensor_c0 if self.trip is None else self.trip) - 1e-9
        self.log.append((w.x, w.z, b))
        return b


class SimLights:
    def head(self, on):
        pass

    def station(self, on):
        pass


class SimCamera:
    """head: sees the back of the held slab (or the top slab while hovering). station: the front."""

    def __init__(self, world: SimWorld, role: str, deg: Degrade | None = None):
        self.w = world
        self.role = role
        self.deg = deg or Degrade(mm_per_px=0.05 if role == "head" else 0.04, blur_px=1.0, glare=0.3)
        self.n = 0

    def view_half_mm(self, distance_mm: float) -> tuple[float, float]:
        """Half the field of view (image x, image y) in mm on the label plane. The synthetic view is a fixed patch
        around the slab under the cup, whatever the distance: 90 x 45 mm of the label end for the station, and
        sim.HEAD_VIEW_MM (label end and the top of the card window) for the head."""
        x0, y0, x1, y1 = self.view_rect_mm(distance_mm)
        return (x1 - x0) / 2, (y1 - y0) / 2

    def view_rect_mm(self, distance_mm: float) -> tuple[float, float, float, float]:
        """The view's extent on the slab plane in mm from the camera axis (image axes; facedown.frame_view_mm). The head
        camera's axis is sim.lens_dy() from the cup axis: head_view draws the slab there."""
        from .sim import SLAB_W_MM

        if self.role == "head":
            return HEAD_VIEW_MM
        return -(SLAB_W_MM + 10) / 2, -22.5, (SLAB_W_MM + 10) / 2, 22.5

    def _blank(self):
        if self.role == "head":  # over an empty pocket: the dark pad far below, and the head's own parts
            key = ("empty", self.w.head, self.w.head_tilt_deg, repr(self.deg))
            if key not in _VIEW_CACHE:
                _VIEW_CACHE[key] = empty_head_view(self.deg, self.w.head, self.w.head_tilt_deg)
            return _VIEW_CACHE[key]
        return np.full((400, 900), 30, np.uint8)

    def capture(self):
        w = self.w
        self.n += 1
        if self.role == "head":
            if w.held:
                s = w.held[0]
            else:
                p = w.pocket_at(w.x, w.y)
                if p is None or not w.stacks.get(p.index):
                    return self._blank()
                s = w.stacks[p.index][-1]
            side = "back" if s.face_down else "front"
        else:
            if not w.held or not w.at_station(w.x, w.y):
                return self._blank()
            s = w.held[0]
            side = "front" if s.face_down else "back"
        base = _cached_view(s.cert, s.era, s.grader, side, self.role, self.deg, back=s.back, head=w.head, front=s.front,
                            tilt=w.head_tilt_deg if self.role == "head" else 0.0)
        noise = np.random.default_rng(self.n).normal(0, 2.0, base.shape)
        return np.clip(base.astype(np.float32) + noise, 0, 255).astype(np.uint8)


_VIEW_CACHE: dict = {}


def _cached_view(cert, era, grader, side, role, deg, back="pokemon_en", head="cad", front="art", tilt=0.0):
    key = (cert, era, grader, side, role, back, head, front, repr(deg)) + ((tilt,) if tilt else ())
    if key not in _VIEW_CACHE:
        if role == "head":
            _VIEW_CACHE[key] = head_view(cert, side, deg, era=era, grader=grader, back=back, head=head, front=front, tilt_deg=tilt)
        else:
            # a stable seed: hash() of a str tuple changes with every process (PYTHONHASHSEED), so runs were not repeatable
            _VIEW_CACHE[key] = render_slab_side(SimSlab(cert, era=era, grader=grader), side, deg, seed=_stable_seed(*key) & 0xFFFF)
    return _VIEW_CACHE[key]


def render_slab_side(s: SimSlab, side: str, deg: Degrade, seed: int):
    """The station camera's view of one side of a slab: its label with what the grader and era print there."""
    return slab_view(s.cert, side, deg, grader=s.grader, era=s.era, seed=seed)


def back_code(s: SimSlab) -> bool:
    """Does this slab's back label carry a code that proves it face-down (a PSA or CGC back QR, the CGC OG barcode)?"""
    return has_back_code(s.grader, s.era, s.cert)


# The default batch: what the label mix of a buyer of mostly low-end Pokemon slabs might look like. [Guessing: not
# counted from a real batch; set your own with `sim --mix`.] SGC is left out: its 86.25 mm holder does not fit the
# 84 mm pockets (cad/layout.py).
DEFAULT_MIX = {"psa:current": 0.55, "psa:2017+": 0.15, "psa:2016": 0.03, "psa:old": 0.05,
               "cgc:2023+": 0.15, "cgc:og": 0.04, "cgc:authentic": 0.01, "bgs:": 0.02}


def parse_mix(text: str) -> dict[str, float]:
    """'psa:current=0.6,cgc:2023+=0.4' -> {kind: share}; the shares are normalised."""
    mix = {}
    for part in text.split(","):
        k, _, v = part.strip().partition("=")
        if k:
            mix[k.strip().lower()] = float(v)
    for k in mix:
        g, _, era = k.partition(":")
        if g not in ("psa", "cgc", "bgs", "sgc") or (g == "psa" and era not in ("current", "2017+", "2016", "2015", "old")) or (
                g == "cgc" and era not in ("2023+", "og", "authentic")):
            raise ValueError(f"unknown label kind {k!r}: psa:current|2017+|2016|old, cgc:2023+|og|authentic, bgs:, sgc:")
    total = sum(mix.values())
    if total <= 0:
        raise ValueError("the mix shares must add up to more than 0")
    return {k: v / total for k, v in mix.items()}


def _mix_slab(kind: str, rng: random.Random) -> tuple[str, str, str, float]:
    """(grader, era, cert, thickness) of one slab of a label kind, with certs and holders as real ones of that kind."""
    g, _, era = kind.partition(":")
    if g == "psa":
        if era == "current":
            cert = str(rng.randint(100_000_000, 199_999_999)) if rng.random() < 0.9 else str(rng.randint(20_000_000, 99_999_999))
        elif era == "2017+":
            cert = str(rng.randint(20_000_000, 79_999_999))
        elif era in ("2016", "2015"):
            cert = str(rng.randint(15_000_000, 29_999_999))
        else:
            cert = str(rng.randint(1_000_000, 9_999_999)) if rng.random() < 0.4 else str(rng.randint(10_000_000, 19_999_999))
        return "PSA", era, cert, rng.uniform(6.25, 6.9)
    if g == "cgc":
        lo, hi = {"2023+": (4_000_000_000, 6_999_999_999), "og": (3_700_000_000, 4_299_999_999), "authentic": (6_100_000_000, 6_199_999_999)}[era]
        cert = "140" + str(rng.randint(1_000_000_000, 9_999_999_999)) if era == "2023+" and rng.random() < 0.05 else str(rng.randint(lo, hi))
        return "CGC", era, cert, rng.uniform(7.3, 7.7)
    if g == "bgs":
        return "BGS", "", "00" + str(rng.randint(10_000_000, 99_999_999)), rng.uniform(7.5, 7.8)  # [Guessing] BGS holder thickness
    return "SGC", "", str(rng.randint(1_000_000_000, 9_999_999_999)), rng.uniform(7.0, 7.5)


def make_batch(cfg: Config, per_pocket: int | None = None, seed: int = 7, eras=None, clingy_rate=0.0, thick_rate=0.0,
               jp_rate: float = 0.0, mix: dict[str, float] | None = None) -> dict[int, list[SimSlab]]:
    """Simulated stacks, deterministic for a seed. ``mix`` ({"psa:current": share, ...}, DEFAULT_MIX when neither it nor
    ``eras`` is given) draws each slab's grader and label era. ``eras`` = (2017+, 2016, old) shares of a PSA-only batch
    (80 % of the 2017+ ones with 9-digit certs, which carry Code128; older labels get 7-8 digit certs, as on real ones).
    A pocket is never filled above its MAX line: a thick slab that would cross it becomes a standard PSA one."""
    rng = random.Random(seed)
    rng_back = random.Random(seed * 7919 + 1)  # its own stream: the rest of the batch is the same with or without JP backs
    kinds = None if eras is not None else sorted((mix or DEFAULT_MIX).items())
    stacks: dict[int, list[SimSlab]] = {}
    for p in cfg.sources:
        k = per_pocket if per_pocket is not None else cfg.stack_max
        stack = []
        height = 0.0
        for _ in range(k):
            if kinds is None:
                cert = str(rng.randint(100_000_000, 179_999_999)) if rng.random() < 0.8 else str(rng.randint(10_000_000, 99_999_999))
                r = rng.random()
                era = "2017+" if r < eras[0] else ("2016" if r < eras[0] + eras[1] else "old")
                if era != "2017+" and len(cert) > 8:
                    cert = cert[1:]  # 9-digit certs exist only on current labels (Code128)
                t = 10.25 if rng.random() < thick_rate else rng.uniform(6.25, 6.9)
                grader = "PSA"
            else:
                x, kind = rng.random(), kinds[-1][0]
                for name, share in kinds:
                    if x < share:
                        kind = name
                        break
                    x -= share
                grader, era, cert, t = _mix_slab(kind, rng)
                if rng.random() < thick_rate:
                    t = 10.25
                if height + t > cfg.max_line - 1.0:
                    grader, era, cert, t = _mix_slab("psa:current", rng)
            back = "pokemon_jp" if jp_rate > 0 and rng_back.random() < jp_rate else "pokemon_en"
            stack.append(SimSlab(cert, t, era, grader=grader, clingy=rng.random() < clingy_rate, back=back))
            height += t
        stacks[p.index] = stack
    return stacks
