"""The batch run: move every stack one pocket over, reading each slab on the way.

Pocket k (k = 1..N) is emptied onto pocket k-1. Pocket 0 starts empty, so each source
always lands on the pocket its predecessor just vacated. Unreadable/other-grader slabs
go to the exception pocket. Order within a stack reverses; the CSV records the exact
output position of every slab.

Heights: s = surface height above the pad top (mm). The machine Z (cup face) at probe
trigger on a surface s is  c = s + cfg.pad_trigger_c  (calibrated by probing the bare pad).
Every height in the config (safe travel heights, station read height, c_max) is an "s"
height, so it goes through ``c()`` before it is sent to the controller.

Fail-stop rule: anything the machine cannot explain (no vacuum seal, a stack taller than
expected, vacuum lost in transit, contact where none should be) stops the run with the
slab in a safe state and a message saying what to do. ``secure()`` re-reads the real head
position, lifts straight up, and puts a slab that is still in the cup back on top of the
stack it came from (a weakly held one is carried back slowly and probed down). Faults that
make any motion unsafe - a failed vent, a vacuum sensor fault, a slab hanging on the cup
before a grip, Ctrl-C twice - "freeze" instead: nothing moves, a hanging slab stays held by
the pump, and the operator takes it off (cli.hand_off_slab / the web page's Vent button).
``resume`` rebuilds the State from journal.jsonl (+ certs.csv), re-surveys every pocket,
and continues.

Every downward move is a probing move (G38.3): FluidNC only watches the contact sensor
during G38.x, so a plain G1 would drive into anything unexpected below the head.
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2

from .certs import CodeRead, ItfModel, Verdict, consensus
from .config import Config
from .decode import _to_gray as to_gray
from .decode import decode_frame, ocr_digits
from .facedown import BASELINE_MAX, MIN_TEXTURE, CardBackRefs, describe, draw_window, frame_view_mm, image_rects, learned_match, learned_ready
from .hw import SensorFault
from .motion import ControllerLost, SafetyViolation
from .results import BatchWriter, SlabResult

NOMINAL_T = 6.6  # mm, used only to turn heights into rough slab counts
Z_ACCEL = 1200.0  # mm/s^2, Z acceleration in firmware/fluidnc/config.yaml (probe deceleration overshoot)
SLOW_XY = 3000.0  # mm/min: sideways moves with a weakly held slab
SEAL_CHECK_S = 0.15  # pump on, head still up: a seal within this time = a slab hanging on the cup
ATM_TOL_STORED = 2.0  # kPa: atmosphere tolerance around the stored empty-cup reading (a slab hangs on to about -1.7)
ATM_TOL_UNSTORED = 6.0  # kPa: without a stored reading (ratiometric sensor offset, as selftest allows)
VAC_FLOOR_KPA = -95.0  # below anything the pump (-81 kPa) can pull: a sensor fault, never a 'good seal'
VENT_HELP = ("The slab is resting there, still sealed to the cup; nothing will move. Check the vent valve (GPIO 22 MOSFET module, its coil "
             "and wire). To free the slab: hold it and pull the vacuum tube off the cup fitting (or unscrew the cup) - never slide the slab "
             "sideways. Then run `selftest -i` and resume (the resume survey will show where the slab is).")


class Stop(Exception):
    """Run halted safely; message tells the operator what to do."""


class HardStop(Stop):
    """Ctrl-C twice: the motors were halted at once and nothing moved afterwards."""


@dataclass
class State:
    tops: dict[int, float] = field(default_factory=dict)  # pocket -> top surface height s
    out_count: dict[int, int] = field(default_factory=dict)  # pocket -> slabs placed there this run
    picked_from: dict[int, int] = field(default_factory=dict)  # source pocket -> slabs removed
    position: int = 0
    done_sources: list[int] = field(default_factory=list)
    survey_tops: dict[int, float] = field(default_factory=dict)
    thickness_log: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------- journal / resume
def read_journal(path: Path) -> list[dict]:
    """All events of a batch journal. A torn last line (power cut mid-write) is ignored."""
    events: list[dict] = []
    path = Path(path)
    if not path.exists():
        return events
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def rebuild_state(events: list[dict], rows: list[SlabResult], cfg: Config) -> tuple[State, Counter, bool]:
    """Reconstruct the run State from the journal (primary) and certs.csv rows (crash window).

    Returns (state, itf_evidence, surveyed). ``surveyed`` is False when the run stopped before
    the first survey finished, in which case resume is just a fresh start.
    """
    st = State()
    itf: Counter = Counter()
    surveyed = False
    for e in events:
        if "survey" in e:
            surveyed = True
            st.survey_tops = {int(k): float(v) for k, v in e["survey"].items()}
            st.tops = dict(st.survey_tops)
        elif "resurvey" in e:
            st.tops.update({int(k): float(v) for k, v in e["resurvey"].items()})
        elif "pos" in e:
            src, dst = int(e["src"]), int(e["dst"])
            extra = 1 if float(e.get("step", 0.0)) >= cfg.t_double else 0
            st.picked_from[src] = int(e.get("src_index", st.picked_from.get(src, 0) + 1 + extra))
            st.out_count[dst] = int(e.get("out_index", st.out_count.get(dst, 0) + 1 + extra))
            st.tops[src] = float(e["s_src"])
            st.tops[dst] = float(e["s_dst"])
            st.thickness_log.append(float(e.get("step", NOMINAL_T)))
            st.position = max(st.position, int(e["pos"]))
            if "itf" in e:
                itf = Counter(e["itf"])
        elif "source_done" in e:
            k = int(e["source_done"])
            if k not in st.done_sources:
                st.done_sources.append(k)
        elif "out_reset" in e:
            st.out_count[int(e["out_reset"])] = int(e["count"])
    # A row in certs.csv that the journal does not have: the process died between the two
    # writes. The slab did move, so count it and shift the expected heights by one slab.
    t_est = sum(st.thickness_log) / len(st.thickness_log) if st.thickness_log else NOMINAL_T
    for r in rows:
        if r.position > st.position:
            st.picked_from[r.source_pocket] = max(st.picked_from.get(r.source_pocket, 0), r.source_index)
            st.out_count[r.out_pocket] = max(st.out_count.get(r.out_pocket, 0), r.out_index)
            st.tops[r.source_pocket] = max(0.0, st.tops.get(r.source_pocket, 0.0) - t_est)
            st.tops[r.out_pocket] = st.tops.get(r.out_pocket, 0.0) + t_est
    st.position = max([st.position] + [r.position for r in rows])
    return st, itf, surveyed



class Runner:
    def __init__(self, cfg: Config, motion, vacuum, lights, head_cam, station_cam, writer: BatchWriter, lid=None, gate=None, log=print,
                 should_stop: Callable[[], bool] | None = None, sleep: Callable[[float], None] | None = None,
                 refs: CardBackRefs | None = None, sim_operator: Callable[[int], bool] | None = None):
        self.cfg = cfg
        self.m = motion
        self.vac = vacuum
        self.lights = lights
        self.head_cam = head_cam
        self.station_cam = station_cam
        self.w = writer
        self.lid = lid
        self.gate = gate  # overfill light beam; .clear() is True when nothing is above the MAX line
        self.log = log
        self.should_stop = should_stop  # polled between slabs (web Stop button, Ctrl-C)
        self.st = State()
        self.itf = ItfModel()
        self.journal = writer.dir / "journal.jsonl"
        self.z = None  # machine Z of the head; None while a move is in flight or after an error (secure() re-reads it)
        self.at: tuple[float, float] | None = None  # bed XY of the last completed _go
        self.holding = False
        self.held_from: tuple[int, float] | None = None  # (source pocket, pick height s) of the slab in the cup
        self.homed = False
        # "hold" (a slab may hang on the cup: pump on), "vent_failed" (a slab rests on a stack sealed to the cup:
        # valves shut) or "sensor" (vacuum sensor fault): after such a stop NOTHING may move.
        self.freeze: str | None = None
        self.baseline: float | None = None  # sensor kPa at atmosphere, measured this run before the first grip
        self.face_down_ok_once = False  # the operator confirmed the next top slab is face-down (resume --face-down-ok)
        # learned face-down check: card-back references (a file under config/ on the machine; in memory by default)
        self.refs = refs if refs is not None else CardBackRefs(None, cfg.face_down_window_mm)
        self._refs_dirty = 0
        self._baseline_taken = False
        self._window_saved = False
        self.face_down_stops = 0  # stops (or simulated confirmations) at the face-down check, this run
        # SIMULATOR ONLY (sim command): a simulated operator who looks at a slab the check stopped on and confirms
        # it if it really is face-down. Never set on the machine: there the run stops and waits for you.
        self.sim_operator = sim_operator
        self.phase = "idle"  # idle | survey | transfer | done | stopped (for the web page)
        self.current: tuple[int, int] | None = None  # (source, destination) being worked on
        self.timings: list[float] = []
        if sleep is None:  # real dwell times on the machine; none against the simulator
            sleep = (lambda s: None) if getattr(vacuum, "simulated", False) else time.sleep
        self.sleep = sleep

    # ------------------------------------------------------------------ coordinates
    def xy(self, x: float, y: float) -> tuple[float, float]:
        a = math.radians(self.cfg.rotation_deg)
        return (x * math.cos(a) - y * math.sin(a) + self.cfg.offset_x, x * math.sin(a) + y * math.cos(a) + self.cfg.offset_y)

    def c(self, s: float) -> float:
        return s + self.cfg.pad_trigger_c

    def s(self, c: float) -> float:
        return c - self.cfg.pad_trigger_c

    @property
    def z_floor(self) -> float:
        """Lowest machine Z ever commanded or probed toward: 0.5 mm inside the firmware soft limit
        (Z -8, CONTRACT.md). The CAD keeps the Z carriage on its rail down to c = -12."""
        return self.cfg.z_min + 0.5

    def _where(self) -> str:
        if self.at is None:
            return "near the home position"
        x, y = self.at
        sx, sy = self.cfg.station_xy
        if abs(x - sx) < 1 and abs(y - sy) < 1:
            return "over the read station"
        for p in self.cfg.pockets:
            if abs(p.x - x) < 1 and abs(p.y - y) < 1:
                return f"over pocket {p.index}"
        return f"at bed X {x:.0f}"

    @property
    def slab_on_cup(self) -> str | None:
        """Where the slab on the cup came from, if the run ended with one (or possibly one) on it."""
        if self.holding:
            return f"pocket {self.held_from[0]}" if self.held_from else "an unknown pocket"
        if self.freeze == "hold":
            return "an unknown pocket (check the cup)"
        if self.freeze == "vent_failed":
            return "the stack under the cup (the vent failed)"
        return None

    # ------------------------------------------------------------------ primitives
    def _z(self, c: float, feed: float | None = None, guard: bool = True) -> None:
        """Z move. A downward move is a probing move (G38.3) at the same speed: FluidNC only watches the
        contact sensor during G38.x, so a plain G1 would drive the head - or a held slab - into anything
        unexpected below it. A trip on the way down is a Stop. ``self.z`` is None while a move is in
        flight, so an error mid-move never leaves a stale height behind (secure() reads the real one).
        ``guard=False`` only for the first move after homing (straight down from the top, off the bed)."""
        c = max(min(c, self.c(self.cfg.c_max)), self.z_floor)
        feed = feed or self.cfg.feed_z
        if guard and self.z is not None and c < self.z - 0.01:
            for target, f in self._descent_plan(self.z, c, feed):
                self._down(target, f)
            return
        self.z = None
        self.m.move(feed, z=c)
        self.m.wait_idle()
        self.z = c

    def _descent_plan(self, z0: float, c_to: float, feed: float) -> list[tuple[float, float]]:
        """A held slab passes the rod tops slowly (feed_rod_band) from 5 mm above them (thickest slab) to
        10 mm below them (thinnest): it rides on the cup at whatever offset it had in its source pocket,
        so it may meet a domed rod top with no play left."""
        if not self.holding:
            return [(c_to, feed)]
        cfg = self.cfg
        top = self.c(cfg.post_h + 5 + cfg.t_thick_max)
        bot = self.c(cfg.post_h - 10 + cfg.t_min)
        slow = min(cfg.feed_rod_band, feed)
        pts = [z0] + [e for e in (top, bot) if c_to < e < z0] + [c_to]
        return [(b, slow if bot - 1e-6 <= (a + b) / 2 <= top + 1e-6 else feed) for a, b in zip(pts, pts[1:])]

    def _down(self, c: float, feed: float) -> None:
        self.z = None
        hit = self.m.probe(c, feed)
        if hit is not None:
            self.z = hit
            raise Stop(f"Unexpected contact {self._where()} at {self.s(hit):.1f} mm while moving down to {self.s(c):.1f} mm"
                       + (" with a slab in the cup" if self.holding else "")
                       + ": something is higher than it should be (a crooked, added or dropped slab, or a slab lying on the rods). "
                       "The head stopped on the contact. Look before resuming.")
        self.z = c

    def _go(self, x: float, y: float, feed: float | None = None, check_vacuum: bool = True) -> None:
        """XY move, only ever at a safe height (lifted straight up first)."""
        safe = self.c(self.cfg.c_safe_loaded if self.holding else self.cfg.c_safe_empty)
        if self.z is None or self.z < safe - 0.01:
            self._z(safe)
        mx, my = self.xy(x, y)
        if "Y" in self.cfg.axes:
            self.m.move(feed or self.cfg.feed_xy, x=mx, y=my)
        else:
            self.m.move(feed or self.cfg.feed_xy, x=mx)
        self.m.wait_idle()
        self.at = (x, y)
        if self.holding and check_vacuum:
            self._check_vacuum("in transit")

    def _probe(self, c_from: float, c_to: float) -> float | None:
        """Guarded descent to c_from, then probe down to c_to at probe speed. Returns trigger Z or None.

        Callers choose c_to so the cup can never be driven more than probe_window past the
        surface it is looking for - well inside the 25 mm spring-buffer stroke.
        """
        c_to = max(c_to, self.z_floor)  # never ask for a probe target past the Z soft limit
        self._z(c_from)
        if c_to >= self.z - 0.05:  # already at the floor: nothing left to probe
            return None
        self.z = None
        hit = self.m.probe(c_to, self.cfg.feed_probe)
        self.z = hit if hit is not None else c_to
        return hit

    # ------------------------------------------------------------------ vacuum
    def _kpa(self) -> float:
        """Cup line pressure. A physically impossible reading is a sensor fault, never 'a good seal'."""
        try:
            k = self.vac.kpa()
        except SensorFault as e:
            raise self._sensor_stop(str(e)) from None
        if k < VAC_FLOOR_KPA:
            raise self._sensor_stop(f"it reads {k:.0f} kPa, lower than the pump can pull (about -81): an open sensor wire or a lost 5 V reads like this")
        return k

    def _sensor_stop(self, why: str) -> Stop:
        self.freeze = "sensor"
        return Stop(f"Vacuum sensor fault: {why}. Without it the machine cannot tell whether a slab is held or let go, so nothing moves."
                    + (" A slab is on the cup; the pump keeps holding it." if self.holding else "")
                    + " Fix the sensor wiring (WIRING.md section 5), run `selftest -i`, then resume.")

    def _atm_ref(self) -> tuple[float, float]:
        ref = self.cfg.vac_baseline_kpa
        return (float(ref), ATM_TOL_STORED) if ref is not None else (0.0, ATM_TOL_UNSTORED)

    def _atmosphere(self, where: str) -> float:
        """Before anything is gripped the cup line must read atmosphere. Lower means a slab may still be stuck
        to the cup (one hangs on down to about -1.7 kPa, far above the -25 kPa transit alarm); higher means
        a sensor fault. The empty-cup reading stored by calibrate z / selftest -i is the reference."""
        ks = [self._kpa() for _ in range(3)]
        k = sum(ks) / len(ks)
        ref, tol = self._atm_ref()
        if k < ref - tol:
            self.freeze = "hold"
            raise Stop(f"The cup line holds vacuum {where} ({k:.1f} kPa; an empty cup reads {ref:.1f}): a slab may be stuck to the cup. "
                       "Nothing will move, and the pump is switched on so such a slab cannot fall. Hold the slab, vent the cup (the command "
                       "line asks you; the web page has a Vent button) and put it face-down back on top of the stack it came from. If the cup "
                       "is empty, the sensor zero has drifted: run `selftest -i` to store a new zero. Then start again.")
        if k > ref + tol:
            raise self._sensor_stop(f"it reads {k:.1f} kPa with nothing pumping (an empty cup reads {ref:.1f})")
        self.baseline = k
        return k

    def _check_vacuum(self, where: str) -> None:
        k = self._kpa()
        if k > self.cfg.vac_transit_alarm_kpa:
            raise Stop(f"Vacuum lost {where} ({k:.0f} kPa). A slab may have dropped. Check the bed and the cup, then resume.")

    def _wait_seal(self) -> bool:
        t0 = time.monotonic()
        while time.monotonic() - t0 < self.cfg.vac_seal_timeout_s:
            if self._kpa() <= self.cfg.vac_seal_kpa:
                return True
            time.sleep(0.02)
        return self._kpa() <= self.cfg.vac_seal_kpa

    def _vent(self, where: str) -> None:
        """Vent the cup and wait until the line is back at atmosphere. A dead vent path (one NC coil, MOSFET
        module or wire) leaves full vacuum, and the 'empty' head would carry the slab off at travel height.
        On failure nothing moves: the slab rests where it is, still sealed to the cup."""
        cfg = self.cfg
        ref = self.baseline if self.baseline is not None else self._atm_ref()[0]
        t0 = time.monotonic()
        self.vac.release()
        k = self._kpa()
        while k < ref - cfg.vent_tol_kpa:
            if time.monotonic() - t0 > cfg.vent_timeout_s:
                self._vent_failed()
                raise Stop(f"Vent failed {where}: the cup line still reads {k:.1f} kPa after {cfg.vent_timeout_s:.1f} s (atmosphere {ref:.1f}). " + VENT_HELP)
            self.vac.release()  # vent again (each call opens the vent for vent_s)
            k = self._kpa()

    def _vent_failed(self) -> None:
        self.freeze = "vent_failed"
        try:
            self.vac.close()  # the slab rests on a stack: valves shut, nothing pulls on it
        except SafetyViolation:
            raise
        except Exception:  # noqa: BLE001
            pass

    def _lift_off(self, hit: float, where: str) -> None:
        """After a verified vent: lift the first peel_mm at peel speed, then check nothing came up with the
        cup (a slab stuck to a sealed cup pulls a little vacuum as it hangs), then go to the travel height."""
        cfg = self.cfg
        self._z(hit + cfg.peel_mm, cfg.feed_peel)
        ref = self.baseline if self.baseline is not None else self._atm_ref()[0]
        k = self._kpa()
        if k < ref - cfg.vent_tol_kpa:
            self._probe(self.z, hit - 3.0)  # set it straight back down
            self._vent_failed()
            raise Stop(f"A slab came up with the vented cup {where} ({k:.1f} kPa after the lift). It was set back down. " + VENT_HELP)
        self._z(self.c(cfg.c_safe_empty))

    def _peel(self, hit: float) -> None:
        """Lift a gripped slab off its stack. At the probe trip the spring buffer is already compressed by
        buffer_trip_mm, so the cup only leaves the slab once the head is that far above the trip point:
        the slow leg is placed around that point (+/- buffer_trip_tol_mm, plus the deceleration overshoot)
        and goes on for peel_slow_mm after it. Then the slab is held low over its own stack for
        peel_dwell_s, so a slab clinging by an air film falls back a few mm instead of from travel height."""
        cfg = self.cfg
        over = (cfg.feed_probe / 60.0) ** 2 / (2 * Z_ACCEL)  # head travel past the trip point while it decelerates
        start = cfg.buffer_trip_mm - cfg.buffer_trip_tol_mm - 0.3
        slow_to = hit + cfg.buffer_trip_mm + cfg.buffer_trip_tol_mm + over + cfg.peel_slow_mm
        if start > 0.05:
            self._z(hit + start, cfg.feed_peel)  # the spring relaxes; the cup stays on the slab
        self._z(slow_to, cfg.feed_peel_slow)  # the cup leaves the slab in here
        self._z(max(hit + cfg.peel_mm, slow_to + 0.5), cfg.feed_peel)
        self.sleep(cfg.peel_dwell_s)
        self._check_vacuum("after peel")

    # ------------------------------------------------------------------ cameras
    def _frames(self, cam, light: str, n: int) -> list:
        getattr(self.lights, light)(True)
        try:
            return [cam.capture() for _ in range(n)]
        finally:
            getattr(self.lights, light)(False)

    def _row_half_mm(self) -> float:
        xs = sorted(p.x for p in self.cfg.pockets)
        return min(b - a for a, b in zip(xs, xs[1:])) / 2  # pocket centre to the wall line

    def _head_roi(self, distance_mm: float) -> tuple[float, float, float, float] | None:
        """Crop of a head-camera frame to the pocket under the cup. The 3.6 mm lens sees the neighbouring
        pockets' labels too (they start ~57 mm off-axis); only the slab under the cup may be read."""
        spec = self.cfg.cam_head or {}
        cam = self.head_cam
        if hasattr(cam, "view_half_mm"):
            hx, hy = cam.view_half_mm(distance_mm)
        else:
            hfov = float(spec.get("hfov_deg", 64.0))
            w, h = float(spec.get("width", 4)), float(spec.get("height", 3))
            hx = distance_mm * math.tan(math.radians(hfov / 2))
            hy = hx * h / w
        along_x = str(spec.get("row_axis", "x")) == "x"
        f = self._row_half_mm() / (hx if along_x else hy)
        if f >= 1.0:
            return None
        return (0.5 - f / 2, 0.0, 0.5 + f / 2, 1.0) if along_x else (0.0, 0.5 - f / 2, 1.0, 0.5 + f / 2)

    def _read(self, frames, camera: str, distance_mm: float | None = None) -> tuple[list[CodeRead], list[str]]:
        """Decode frames. Head ('back') frames are cropped to the pocket under the cup. One read per
        (symbology, payload) per frame: overlapping tiles of one frame are not separate evidence.
        No OCR here (see _front_ocr)."""
        roi = self._head_roi(distance_mm) if camera == "back" and distance_mm else None
        reads: list[CodeRead] = []
        unparsed: list[str] = []
        for f in frames:
            r, u = decode_frame(f, camera, self.cfg.custom_regex, allow_ocr=False, roi=roi)
            seen = set()
            for x in r:
                if (x.symbology, x.raw) not in seen:
                    seen.add((x.symbology, x.raw))
                    reads.append(x)
            unparsed += [x for x in u if x not in unparsed]
        return reads, unparsed

    def _front_ocr(self, frames, reads: list[CodeRead]) -> list[CodeRead]:
        """OCR of the printed digits, on the front (station) frame only: it is the one independent check of an
        ITF-only read. Never on the head camera: through the clear slab it sees the card back's own numbers."""
        if not self.cfg.allow_ocr or not frames or any(r.source == "ocr" for r in reads):
            return []
        return ocr_digits(to_gray(frames[-1]), "front")

    def _decide(self, reads: list[CodeRead], held_reads: list[CodeRead]) -> Verdict:
        """consensus() plus the run-level rules: the frame from above the stack alone never makes an 'ok'
        (it can see a neighbour's label), a PSA cert of a length Phase 0 never saw is not 'ok', and a cert
        already recorded in this batch is a conflict (exception pocket), never a second 'ok'."""
        cfg = self.cfg
        v = consensus(reads, self.itf, accepted=tuple(cfg.accepted_graders))
        if v.status == "ok" and v.cert:
            support = {c for r in held_reads for c in (r.cert, r.alt_cert) if c}
            if v.cert not in support:
                v = Verdict("needs_review", v.cert, v.sources, "read only in the frame from above the stack (a neighbour's label?) - verify by eye", v.grader, v.raw)
        if v.status == "ok" and v.grader == "PSA" and cfg.psa_cert_digits and v.cert and len(v.cert) not in tuple(cfg.psa_cert_digits):
            v = Verdict("needs_review", v.cert, v.sources, f"{len(v.cert)}-digit PSA cert, but Phase 0 saw only {'/'.join(map(str, cfg.psa_cert_digits))} digits - verify", v.grader, v.raw)
        if v.cert and v.status in ("ok", "needs_review"):
            earlier = next((r.position for r in getattr(self.w, "rows", []) if r.verdict.cert == v.cert and r.verdict.status in ("ok", "needs_review")), None)
            if earlier is not None:
                v = Verdict("conflict", None, v.sources, f"cert {v.cert} was already recorded at #{earlier} in this batch: a neighbour's label in view, "
                            "or a misread - check this slab by hand", v.grader, v.raw)
        return v

    def _hover_mm(self) -> float:
        return float((self.cfg.cam_head or {}).get("lens_to_label_mm", 140.0)) + self.cfg.approach_gap + 2

    def _fd_describe(self, frame):
        """Card-window descriptor of a frame from the hover height (facedown.describe). The first frame of a run is
        also saved with the window drawn on it (images/face_down_window.jpg), so you can check where it lies."""
        if frame is None:
            return None
        spec = self.cfg.cam_head or {}
        view = frame_view_mm(frame.shape, self._hover_mm(), spec, self.head_cam)
        rects = image_rects(self.cfg.face_down_window_mm, str(spec.get("row_axis", "x")))
        if not self._window_saved:
            self._window_saved = True
            try:
                self._save(draw_window(frame, rects, view), "face_down_window.jpg")
            except Exception:  # noqa: BLE001 - a picture for the operator, never a reason to stop
                pass
        return describe(frame, rects, view)

    def _learn(self, desc, source: str, src: int) -> str:
        """A proven face-down slab (back QR, or the operator) becomes a card-back reference. Never a learned one."""
        cfg = self.cfg
        proto, why = self.refs.add(desc, source, {"batch": self.w.batch_id, "pocket": src, "pos": self.st.position + 1},
                                   cluster=cfg.face_down_threshold)
        if proto is None:
            return f"not used as a reference: {why}"
        self._refs_dirty += 1
        if source != "qr" or self.refs.protos().get(proto, 0) == 1:
            self._save_refs(force=True)  # an operator confirmation or a new back design: on disk at once
        else:
            self._save_refs()
        return f"reference {self.refs.n_refs} (prototype {proto})"

    def _save_refs(self, force: bool = False) -> None:
        if self._refs_dirty and (force or self._refs_dirty >= 10):
            try:
                self.refs.save()
                self._refs_dirty = 0
            except OSError as e:
                self.log(f"could not save the card-back references ({e}); they are kept for this run only")

    def face_down_status(self) -> str:
        """One line for the log: what the face-down check will do."""
        cfg = self.cfg
        if cfg.face_down_check == "off":
            return "face-down check: OFF - a slab loaded face-up gets the cup on its front"
        if cfg.face_down_check == "stop":
            return "face-down check: back QR only - every slab without a PSA back QR stops for you"
        why = learned_ready(self.refs, cfg.face_down_threshold, cfg.face_down_min_refs, cfg.face_down_window_mm)
        if not why:
            return (f"face-down check: learned (threshold {cfg.face_down_threshold:.2f}, {self.refs.summary()}): a slab without a back QR "
                    "is picked only if its card window matches a known card back")
        return f"face-down check: {why}. Until then every slab without a PSA back QR stops for you, as in 'stop' mode"

    def _check_face_down(self, src: int, hover_reads: list[CodeRead], frame=None) -> str:
        """Before the cup touches a slab: the frame from above must show a PSA back-label QR (PSA front labels
        carry no QR), or - in "learned" mode - a card window that matches the card backs of earlier proven slabs.
        Anything else - an older label without a back QR that matches nothing, a face-up slab, another grader's
        code (they sit on the front label) - stops the run untouched until the operator confirms. Returns how the
        slab was proven face-down: qr | operator | learned(score) | off."""
        cfg = self.cfg
        if cfg.face_down_check == "off":
            return "off"
        learned = cfg.face_down_check == "learned"
        desc = self._fd_describe(frame) if learned else None
        if self.face_down_ok_once:
            self.face_down_ok_once = False
            note = self._learn(desc, "operator", src) if learned else ""
            self._journal({"face_down_confirmed": src, "by": "operator", **({"reference": note} if note else {}), "t": round(time.time(), 1)})
            return "operator"
        psa_back = any(r.source == "back_qr" and r.grader == "PSA" for r in hover_reads)
        fronts = sorted({r.grader for r in hover_reads if r.grader not in ("PSA", "unknown")})
        if psa_back and not fronts:
            if learned:
                self._learn(desc, "qr", src)
            return "qr"
        why_learned = ""
        if learned and not fronts:
            ok, why_learned, m = learned_match(self.refs, desc, cfg.face_down_threshold, cfg.face_down_min_refs, cfg.face_down_window_mm)
            if ok:
                self.refs.touch(m.proto)
                self._journal({"face_down_learned": src, "score": round(m.score, 3), "ncc": round(m.ncc, 3), "hist": round(m.hist, 3),
                               "prototype": m.proto, "threshold": cfg.face_down_threshold, "refs": self.refs.n_refs,
                               "baseline": round(self.refs.baseline_score(desc), 3), "pos": self.st.position + 1, "t": round(time.time(), 1)})
                return f"learned({m.score:.2f})"
        why = (f"a {'/'.join(fronts)} code is visible from above, and those sit on the FRONT label" if fronts
               else "no PSA back-label QR was seen from above" + (f"; {why_learned}" if why_learned else ""))
        self.face_down_stops += 1
        if self.sim_operator is not None and self.sim_operator(src):
            note = self._learn(desc, "operator", src) if learned else ""
            self._journal({"face_down_confirmed": src, "by": "simulated operator", "why": why, **({"reference": note} if note else {}),
                           "t": round(time.time(), 1)})
            return "operator"
        teach = learned and not fronts and desc is not None and desc.texture >= MIN_TEXTURE and self.refs.baseline_score(desc) < BASELINE_MAX
        raise Stop(f"Pocket {src}: the top slab could not be confirmed FACE-DOWN before touching it ({why}). The cup must never touch a "
                   f"slab's front, so nothing touched it. Look at the top slab of pocket {src}: if it is face-up, turn it face-down. If it is "
                   "face-down (older labels have no back QR), resume with --face-down-ok (web page: tick 'the top slab is face-down')"
                   + (": its card back then becomes a reference for the learned check." if teach else "."))

    def _save(self, frame, name: str) -> str:
        if frame is None:
            return ""
        p = self.w.dir / "images" / name
        h, w = frame.shape[:2]
        scale = min(1.0, 1600 / max(h, w))
        small = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else frame
        cv2.imwrite(str(p), small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return str(p.relative_to(self.w.dir))

    def _journal(self, event: dict) -> None:
        with self.journal.open("a") as f:
            f.write(json.dumps(event) + "\n")

    def _home(self) -> None:
        self.m.home()
        self.homed = True
        self.z = None
        self.at = None
        self._z(self.c(self.cfg.c_safe_empty), guard=False)  # straight down from the top, at the home end off the bed

    # ------------------------------------------------------------------ survey
    def _find_top(self, p) -> float | None:
        """Walk down over pocket p in probe windows from the travel height until contact.
        Returns the top surface height s (None = never touched). Ends at the empty safe height."""
        cfg = self.cfg
        self._go(p.x, p.y)
        self._atmosphere(f"over pocket {p.index}")
        self.vac.hold()  # an open cup that suddenly seals = contact the optical sensor missed
        self.sleep(SEAL_CHECK_S)
        k = self._kpa()
        if k <= cfg.vac_seal_kpa / 2:
            # sealed before the head moved down: a slab is hanging on the cup. Venting would drop it.
            self.freeze = "hold"
            raise Stop(f"Pocket {p.index}: the cup sealed ({k:.0f} kPa) before the head moved down - a slab is hanging on the cup. Nothing will "
                       "move and the pump keeps holding it. Hold the slab, vent the cup (the command line asks you; the web page has a Vent "
                       "button), put it face-down back on the stack it came from, then start again.")
        top = None
        c = self.z  # the first window starts at the travel height: a slab lying on the rods trips it
        floor = max(self.c(-2), self.z_floor)
        try:
            while c > floor + 0.05:  # walk down in probe windows until contact
                hit = self._probe(c, max(floor, c - cfg.probe_window))
                if hit is not None:
                    top = self.s(hit)
                    break
                if self._kpa() <= cfg.vac_seal_kpa:
                    raise Stop(f"Pocket {p.index}: the cup sealed on something but the contact sensor did not trip. Contact sensor fault - stop and check it.")
                c = self.z
        except BaseException:
            if not self.freeze:
                try:
                    self.vac.release()  # the open cup may be sealed on the stack top: vent before anything lifts
                except SafetyViolation:
                    raise
                except Exception:  # noqa: BLE001
                    pass
            raise
        self._vent(f"on pocket {p.index}")
        safe = self.c(cfg.c_safe_empty)
        if self.z < safe - 0.01:
            self._z(min(self.z + cfg.peel_mm, safe), cfg.feed_peel)
        self._z(safe)
        return top

    def survey(self, expect: dict[int, float] | None = None, accept: bool = False) -> dict[int, float]:
        """Probe every pocket once.

        New run (expect=None): start/exception pockets must be empty, sources must be under the fill line.
        Resume (expect = heights the journal predicts): every pocket must still match, except that the
        exception pocket may have been emptied by hand. ``accept`` takes the measured heights instead.
        """
        cfg = self.cfg
        measured: dict[int, float] = {}
        for p in cfg.pockets:
            top = self._find_top(p)
            if top is None:
                raise Stop(f"Pocket {p.index}: probe never touched anything (not even the pad). Check the contact sensor wiring and calibration.")
            if top > cfg.max_line + 1:
                raise Stop(f"Pocket {p.index} is filled above the MAX line ({top:.0f} mm > {cfg.max_line:.0f}), or something lies on its rods. Remove it and restart.")
            if expect is None and p.role != "source" and top > cfg.t_min / 2:
                raise Stop(f"Pocket {p.index} ({p.role}) must start empty but is {top:.1f} mm tall.")
            measured[p.index] = max(0.0, top)
            self.log(f"survey pocket {p.index:2d} ({p.role}): top {top:6.1f} mm ~ {round(max(0, top) / NOMINAL_T)} slabs")
            if top < cfg.t_min / 2:
                self._take_baseline(p.index)
        if expect is not None:
            self._check_resurvey(measured, expect, accept)
        for k, v in measured.items():
            self.st.tops[k] = v
            if expect is None:
                self.st.survey_tops[k] = v
        return dict(self.st.tops)

    def _take_baseline(self, pocket: int) -> None:
        """Learned mode, once per run: the head camera's view over an empty pocket (head at the empty travel height,
        straight above it). A card window that looks like this view does not show the slab: the head hides it."""
        if self.cfg.face_down_check != "learned" or self._baseline_taken:
            return
        self._baseline_taken = True
        frame = self._frames(self.head_cam, "head", 1)[0]
        d = self._fd_describe(frame)
        if d is not None:
            self.refs.set_baseline(d, {"batch": self.w.batch_id, "pocket": pocket, "t": round(time.time(), 1)})
            self._refs_dirty += 1
            self._journal({"face_down_baseline": pocket})

    def _check_resurvey(self, measured: dict[int, float], expect: dict[int, float], accept: bool) -> None:
        cfg = self.cfg
        ex = cfg.exceptions.index
        t = self._mean_t()
        bad = []
        for k, got in measured.items():
            want = expect.get(k, 0.0)
            if k == ex:
                if got > want + cfg.max_surprise:
                    bad.append((k, got, want))
                elif got < want - cfg.t_min / 2:  # operator took slabs out of the exception pocket
                    n = round(got / t)
                    self.st.out_count[ex] = n
                    self._journal({"out_reset": ex, "count": n})
                    self.log(f"exception pocket {ex} was emptied to {got:.1f} mm (~{n} slabs); counting continues from {n}")
                continue
            if abs(got - want) > cfg.max_surprise:
                bad.append((k, got, want))
        if not bad:
            return
        lines = [f"pocket {k}: {got:.1f} mm now, {want:.1f} mm when the run stopped ({(got - want) / t:+.1f} slabs)" for k, got, want in bad]
        if accept:
            self.log("resume --accept-heights: using the measured heights. " + "; ".join(lines))
            self._journal({"accepted_heights": lines})
            return
        hint = ""
        moved = {k: (got - want) / t for k, got, want in bad}
        lows = [k for k, d in moved.items() if -1.5 < d < -0.5]
        highs = [k for k, d in moved.items() if 0.5 < d < 1.5]
        if len(lows) == 1 and len(highs) == 1:
            hint = (f" It looks like one slab went from pocket {lows[0]} to pocket {highs[0]} without being recorded (power cut or crash mid-move). "
                    f"Put the top slab of pocket {highs[0]} back on top of pocket {lows[0]}, face-down, then resume.")
        raise Stop("The stacks changed since the run stopped: " + "; ".join(lines) + "." + hint
                   + " Put them back the way they were, or resume with --accept-heights to take the new heights (the slab count check will flag the difference).")

    def _mean_t(self) -> float:
        t = sum(self.st.thickness_log) / len(self.st.thickness_log) if self.st.thickness_log else NOMINAL_T
        return min(max(t, self.cfg.t_min), self.cfg.t_std_max)


    # ------------------------------------------------------------------ one slab
    def transfer(self, src: int, dst: int) -> bool:
        """Move the top slab of src to dst (or exceptions). Returns False when src is empty."""
        cfg = self.cfg
        t0 = time.monotonic()
        ps, pex = cfg.pocket(src), cfg.exceptions
        self._go(ps.x, ps.y)
        s_pred = self.st.tops[src]
        if s_pred < cfg.t_min / 2:
            return False
        lens = float((cfg.cam_head or {}).get("lens_to_label_mm", 140.0))
        hover_reads: list[CodeRead] = []
        unparsed: list[str] = []
        face_down = "off"
        if cfg.hover_check or cfg.face_down_check != "off":
            # look before touching anything: the face-down check, and a first read of the back label
            self._z(self.c(s_pred) + cfg.approach_gap + 2)
            hover = self._frames(self.head_cam, "head", 1)
            hover_reads, unparsed = self._read(hover, "back", lens + cfg.approach_gap + 2)
            face_down = self._check_face_down(src, hover_reads, hover[0])
            if not cfg.hover_check:
                hover_reads = []
        # bounded probe for the real top
        hit = self._probe(self.c(s_pred) + cfg.approach_gap, self.c(s_pred) - cfg.probe_window + cfg.approach_gap)
        if hit is None:  # lower than predicted: look further down to the pad
            hit = self._probe(self.z, max(self.c(-2), self.z - cfg.probe_window))
            if hit is None:
                self._z(self.c(cfg.c_safe_empty))
                raise Stop(f"Pocket {src}: no contact where the stack should be (predicted {s_pred:.1f} mm). Check the contact sensor, then resume.")
        s_top = self.s(hit)
        if s_top - s_pred > cfg.max_surprise:
            self._z(self.c(cfg.c_safe_empty))
            raise Stop(f"Pocket {src} is {s_top - s_pred:.1f} mm taller than expected - was a slab added or is one sitting crooked? Fix it, then resume.")
        if s_top < cfg.t_min / 2:
            self.st.tops[src] = 0.0
            self._z(self.c(cfg.c_safe_empty))
            return False
        # grip
        self._atmosphere(f"before gripping the top slab of pocket {src}")
        self.vac.hold()
        if not self._wait_seal():
            self._vent(f"on pocket {src} after a failed seal")
            self._z(hit + 3)
            hit2 = self._probe(hit + 3, hit - 4)
            if hit2 is not None:
                self.vac.hold()
            if hit2 is None or not self._wait_seal():
                self._vent(f"on pocket {src} after a failed seal")
                self._z(self.c(cfg.c_safe_empty))
                raise Stop(f"Pocket {src}: cup will not seal on the top slab (dirty cup, warped slab?). Fix it, then resume.")
            hit = hit2
        self.holding = True
        self.held_from = (src, s_top)
        self._peel(hit)
        self._z(self.c(cfg.c_safe_loaded))
        back = self._frames(self.head_cam, "head", cfg.frames_per_read)
        back_reads, u = self._read(back, "back", lens)
        unparsed += [x for x in u if x not in unparsed]
        reads = hover_reads + back_reads
        held_reads = list(back_reads)
        verdict = self._decide(reads, held_reads)
        front = None
        if cfg.front_photo == "always" or verdict.status != "ok":
            sx, sy = cfg.station_xy
            self._go(sx, sy)
            self._z(self.c(cfg.station_read_c))
            front_frames = self._frames(self.station_cam, "station", cfg.frames_per_read)
            front = front_frames[-1]
            self._check_vacuum("at the read station")
            # Decode with the slab over its planned output stack, not over the bare lens: decoding (and OCR,
            # up to 30 s) is the longest time a slab hangs, and a drop there would land face-first on the camera.
            self._z(self.c(cfg.c_safe_loaded))
            pd = cfg.pocket(dst)
            self._go(pd.x, pd.y)
            f_reads, f_unparsed = self._read(front_frames, "front")
            reads += f_reads
            held_reads += f_reads
            unparsed += [x for x in f_unparsed if x not in unparsed]
            verdict = self._decide(reads, held_reads)
            itf_only = bool(reads) and all(r.symbology == "ITF" for r in reads if r.source != "ocr")
            if verdict.status == "no_read" or (verdict.status == "needs_review" and itf_only):
                o = self._front_ocr(front_frames, reads)
                if o:
                    reads += o
                    held_reads += o
                    verdict = self._decide(reads, held_reads)
        to_output = verdict.status == "ok" or (verdict.status == "needs_review" and cfg.needs_review_to == "output")
        target = cfg.pocket(dst) if to_output else pex
        if target.index == pex.index and self.st.tops.get(pex.index, 0.0) + 2 * cfg.t_thick_max > cfg.max_line:
            raise Stop(f"Exception pocket {pex.index} is full. Empty it (those slabs need a hand check), then resume. The slab in the cup will be read again.")
        self._go(target.x, target.y)
        s_dst = self.st.tops.get(target.index, 0.0)
        # start high enough that even a double pick (two slabs, ~13 mm) is caught by the probe, not a fast move
        hit = self._probe(self.c(s_dst + cfg.t_double + 2 * cfg.approach_gap), self.c(s_dst + cfg.t_min - 2))
        if hit is None:
            hit = self._probe(self.z, self.c(s_dst - 1))
            if hit is None:
                self._check_vacuum("before placing")
                raise Stop(f"Placing onto pocket {target.index}: no contact - output stack lower than expected. Check it, then resume.")
        step = self.s(hit) - s_dst
        if step > 2.5 * cfg.t_std_max:
            raise Stop(f"Placing onto pocket {target.index}: contact {step:.1f} mm above the stack - something is in the way. Check it, then resume.")
        if step < cfg.t_min / 2:
            # The cup itself touched the stack: nothing is in it, whatever the vacuum sensor says.
            self.freeze = "hold"
            raise Stop(f"Placing onto pocket {target.index}: the cup touched {step:.1f} mm above the stack, as if nothing is in the cup. The slab from "
                       f"pocket {src} may have fallen off on the way, or the vacuum sensor reports a seal that is not there. Nothing will move; the "
                       "pump keeps holding whatever is on the cup. Look at the cup and the bed (rods, stacks, read station), then resume.")
        flags = []
        if step >= cfg.t_double:
            flags.append(f"DOUBLE PICK: an unread slab is directly under this one in pocket {target.index}")
        elif step > cfg.t_std_max:
            flags.append(f"thick holder ({step:.1f} mm)")
        elif step < cfg.t_min - 0.5:
            flags.append(f"thin/odd step {step:.1f} mm - check seating")
        self._vent(f"on pocket {target.index}")
        self.holding = False
        self.held_from = None
        self._lift_off(hit, f"on pocket {target.index}")
        # bookkeeping
        self.st.tops[target.index] = self.s(hit)
        self.st.tops[src] = max(0.0, s_top - step)
        self.st.out_count[target.index] = self.st.out_count.get(target.index, 0) + 1 + (1 if step >= cfg.t_double else 0)
        self.st.picked_from[src] = self.st.picked_from.get(src, 0) + 1 + (1 if step >= cfg.t_double else 0)
        self.st.position += 1
        self.st.thickness_log.append(step)
        if flags:
            verdict = Verdict(verdict.status if "DOUBLE" not in flags[0] else "needs_review", verdict.cert, verdict.sources, "; ".join([verdict.note] + flags).strip("; "), verdict.grader, verdict.raw)
        pos = self.st.position
        img_b = self._save(back[-1] if back else None, f"{pos:04d}_back.jpg")
        img_f = self._save(front, f"{pos:04d}_front.jpg") if front is not None else ""
        double = step >= cfg.t_double
        if double:
            # The slab that came along underneath was never seen: give it its own row so nothing is
            # silently missing from the list. It sits directly under the read slab in the output pocket.
            unread = Verdict("no_read", None, (), f"UNREAD: lifted together with #{pos}; it is directly under that slab in pocket {target.index} - scan it by hand")
            self.w.add(SlabResult(pos, src, self.st.picked_from[src], target.index, self.st.out_count[target.index] - 1, unread))
        self.w.add(SlabResult(pos, src, self.st.picked_from[src] - (1 if double else 0), target.index, self.st.out_count[target.index], verdict, img_f, img_b,
                              face_down=face_down))
        self._journal({"pos": pos, "src": src, "dst": target.index, "cert": verdict.cert, "status": verdict.status, "step": round(step, 2),
                       "s_src": round(self.st.tops[src], 2), "s_dst": round(self.st.tops[target.index], 2),
                       "src_index": self.st.picked_from[src], "out_index": self.st.out_count[target.index],
                       "itf": dict(self.itf.evidence), "unparsed": unparsed[:5], "face_down": face_down})
        self.timings.append(time.monotonic() - t0)
        self.log(f"#{pos:3d} P{src}->P{target.index} {verdict.status:12} {verdict.cert or '-':>10} step {step:4.1f} {verdict.note}")
        return True

    # ------------------------------------------------------------------ operator helpers
    def pick_top(self, pocket: int) -> float:
        """Pick up the top slab of a pocket and lift it to the loaded travel height (used by
        ``focus station``). Returns the slab's top height s before the pick."""
        cfg = self.cfg
        p = cfg.pocket(pocket)
        top = self._find_top(p)
        if top is None or top < cfg.t_min / 2:
            raise Stop(f"Pocket {pocket} is empty. Put one slab in it face-down, label toward you.")
        hit = self._probe(self.c(top) + cfg.approach_gap, self.c(top) - cfg.probe_window + cfg.approach_gap)
        if hit is None:
            self._z(self.c(cfg.c_safe_empty))
            raise Stop(f"Pocket {pocket}: lost the slab between two probes. Check the contact sensor.")
        self._atmosphere(f"before gripping the slab in pocket {pocket}")
        self.vac.hold()
        if not self._wait_seal():
            self._vent(f"on pocket {pocket} after a failed seal")
            self._z(self.c(cfg.c_safe_empty))
            raise Stop(f"Pocket {pocket}: cup will not seal on the slab (dirty cup, or slab face-up?).")
        self.holding = True
        self.held_from = (pocket, self.s(hit))
        self._peel(hit)
        self._z(self.c(cfg.c_safe_loaded))
        return self.s(hit)

    def put_back(self) -> int:
        """Set the slab in the cup back down on the stack it came from, at the height it was
        picked from (that stack is unchanged since the pick). Returns the pocket index."""
        cfg = self.cfg
        if not self.holding or self.held_from is None:
            raise Stop("Nothing is in the cup.")
        src, s_pick = self.held_from
        p = cfg.pocket(src)
        self._go(p.x, p.y)
        hit = self._probe(self.c(s_pick) + 2 * cfg.approach_gap, self.c(s_pick) - 4.0)
        if hit is None:
            self._z(self.c(cfg.c_safe_loaded))
            raise Stop(f"Could not find the top of pocket {src} to put the slab back (expected contact at {s_pick:.1f} mm).")
        self._vent(f"on top of pocket {src}")
        self.holding = False
        self.held_from = None
        self._lift_off(hit, f"on top of pocket {src}")
        return src

    def _set_down_weak(self, k: float) -> str:
        """Vacuum is low with a slab in the cup. Never let go in mid-air (over the lens, the rods or a
        neighbour): keep pumping, carry it slowly back over its own pocket, probe down until it (or the
        stack, if it already fell) touches, and vent there."""
        cfg = self.cfg
        src, s_pick = self.held_from
        try:
            self.vac.hold()
        except SafetyViolation:
            raise
        except Exception:  # noqa: BLE001
            pass
        p = cfg.pocket(src)
        self._go(p.x, p.y, feed=SLOW_XY, check_vacuum=False)
        hit = self._probe(self.c(s_pick) + 2 * cfg.approach_gap, self.c(s_pick - cfg.t_thick_max - 2))
        if hit is None:
            self._z(self.c(cfg.c_safe_loaded))
            return (f"Vacuum dropped to {k:.0f} kPa with a slab from pocket {src} in the cup, and nothing was found on top of pocket {src}. "
                    "The head waits at the safe height with the pump on. Look at the cup and the bed before touching anything.")
        s_hit = self.s(hit)
        on_cup = s_hit > s_pick - cfg.t_min / 2
        self._vent(f"on top of pocket {src}")
        self.holding = False
        self.held_from = None
        self._lift_off(hit, f"on top of pocket {src}")
        self._journal({"low_vacuum_set_down": src, "contact_s": round(s_hit, 2), "slab_was_on_cup": on_cup, "t": round(time.time(), 1)})
        if on_cup:
            return (f"Vacuum dropped to {k:.0f} kPa while a slab was held. It was carried back slowly and set down on top of pocket {src}, where it came "
                    "from; it will be read again on resume. Check the cup lip and the vacuum line for a leak first.")
        return (f"Vacuum dropped to {k:.0f} kPa and the slab was NOT on the cup any more: it fell somewhere between pocket {src} and where the "
                f"head was. Find it before resuming (on the rods, the stacks, the read station) and put it face-down on top of pocket {src}.")

    def secure(self) -> str:
        """After a Stop or an unexpected error: leave nothing hanging in the air. Returns a note for the operator.
        The real head height is read first (an error mid-move leaves the planned one unknown), and the head
        only ever goes straight up before it moves sideways."""
        try:
            if self.freeze:
                return self._frozen()
            if not self.homed:
                return ""
            self._resync()
            if self.holding and self.held_from is not None:
                src = self.held_from[0]
                k = self._kpa()
                if k > self.cfg.vac_transit_alarm_kpa:
                    return self._set_down_weak(k)
                self.put_back()
                return f"The slab that was in the cup was put back on top of pocket {src}; it will be read again on resume."
            self._vent("where the head stopped")  # the open cup may be sealed on a stack top (survey)
            safe = self.c(self.cfg.c_safe_empty)
            if self.z is not None and self.z < safe - 0.01:
                self._z(min(self.z + self.cfg.peel_mm, safe), self.cfg.feed_peel)
                self._z(safe)
            return ""
        except SafetyViolation:
            raise  # the simulator's safety monitor: a test must fail loudly, also during recovery
        except ControllerLost:
            return self.lost_note()
        except Stop as e:
            if self.freeze:
                self._frozen()
                return str(e)
            return self._park_failed(e)
        except Exception as e:  # noqa: BLE001 - report, never mask the original Stop
            return self._park_failed(e)

    def _resync(self) -> None:
        """After an error the reply stream may be one behind and the head may still be moving: wait for
        Idle, resync, and take the real Z (so _go() lifts straight up from where the head really is)."""
        rs = getattr(self.m, "resync", None)
        if rs is not None:
            rs()
        if hasattr(self.m, "position"):
            self.z = self.m.position()[1]

    def _frozen(self) -> str:
        """No motion at all. A slab that may hang on the cup stays held (pump on); one resting on a stack after
        a failed vent stays as it is (valves shut); after a sensor fault with nothing held the cup is vented."""
        try:
            if self.freeze == "vent_failed":
                self.vac.close()
            elif self.holding or self.freeze == "hold":
                self.vac.hold()
            else:
                self.vac.release()
        except SafetyViolation:
            raise
        except Exception:  # noqa: BLE001
            pass
        return "Nothing moved after the stop."

    def _park_failed(self, e: Exception) -> str:
        msg = f"Could not park the machine automatically ({e})."
        if self.holding:
            try:
                self.vac.hold()  # never let the valves shut on a hanging slab while the Pi has power
            except SafetyViolation:
                raise
            except Exception:  # noqa: BLE001
                pass
            src = self.held_from[0] if self.held_from else "?"
            msg += (f" A SLAB from pocket {src} is still on the cup; the pump keeps holding it. Hold it, vent the cup (the command line asks you; "
                    f"the web page has a Vent button) and put it face-down on top of pocket {src}.")
        return msg + " Check the head before touching the bed."

    def _face_down_summary(self) -> dict:
        """How every slab of the batch (all runs of it) was proven face-down, from certs.csv, plus the learned ones
        for the audit (check their back photos)."""
        rows = [r for r in getattr(self.w, "rows", []) if r.face_down]
        counts = Counter(r.face_down.split("(")[0] for r in rows)
        learned = [{"position": r.position, "out_pocket": r.out_pocket, "out_index": r.out_index, "face_down": r.face_down, "image_back": r.image_back}
                   for r in rows if r.face_down.startswith("learned")]
        return {"mode": self.cfg.face_down_check, "counts": dict(counts), "learned": learned, "references": self.refs.summary(),
                "stops_this_run": self.face_down_stops}

    def count_check(self) -> dict:
        """Slabs counted per source vs the source's surveyed height / mean measured thickness.
        A mismatch of more than one slab means something was not seen (e.g. an undetected double)."""
        mean_t = self._mean_t()
        out = {}
        for p in self.cfg.sources:
            h = self.st.survey_tops.get(p.index, 0.0)
            est = round(h / mean_t)
            got = self.st.picked_from.get(p.index, 0)
            out[p.index] = {"surveyed_mm": round(h, 1), "estimated": est, "counted": got, "ok": abs(est - got) <= 1}
        return out

    # ------------------------------------------------------------------ whole batch
    def _preflight(self) -> None:
        """Before homing: only checks that are valid wherever the head stopped (the beam is checked after homing)."""
        if self.lid is not None and not self.lid.closed():
            raise Stop("Close the lid to start.")
        self._atmosphere("at the start")

    def _check_gate(self) -> None:
        """After homing (head at the top, nothing of it can cross the beam) and before any sideways move."""
        if self.gate is not None and not self.gate.clear():
            raise Stop("The overfill light beam is blocked with the head at the top: a stack is above the MAX line, something is lying across "
                       "the stacks, or the laser and its receiver are out of line. Take the extra slabs off (or re-aim the laser at the receiver), "
                       "then start again.")

    def _check_pause(self) -> None:
        if self.lid is not None and not self.lid.closed():
            raise Stop("Lid opened - run paused with nothing held. Close the lid and resume.")
        if self.should_stop is not None and self.should_stop():
            raise Stop("Stopped on request - nothing held. Resume to continue.")

    def lost_note(self) -> str:
        """The controller lost power (E-stop) or its USB link: nothing can move. Keep a held slab held from
        the Pi side and tell the operator what to do by hand."""
        self.homed = False
        try:
            if self.holding:
                self.vac.hold()  # the pump keeps it while the Pi has power; closed valves alone hold it only briefly
            else:
                self.vac.close()
        except SafetyViolation:
            raise
        except Exception:  # noqa: BLE001
            pass
        msg = ("The controller lost power or its USB link (E-stop pressed, or the cable came out). The head stopped where it was. "
               "If you did not press the E-stop, the motors may still be powered: press it now before reaching in.")
        if self.holding and self.held_from is not None:
            src = self.held_from[0]
            msg += (f" A slab from pocket {src} is still on the cup. The pump keeps holding it while the Pi has power (if the E-stop also cut the "
                    f"pump, the closed valves hold it for a short while only: take it off now). Hold it, vent the cup (the command line asks you; "
                    f"the web page has a Vent button) and put it face-down on top of pocket {src}; it will be read again.")
        msg += " Twist the E-stop to release it, then resume: the machine reconnects and homes first (Z straight up, then X)."
        return msg

    def hard_stop(self) -> str:
        """Ctrl-C twice: halt the motors at once (feed hold + controller reset) and move nothing afterwards.
        The reply stream and the planned position cannot be trusted after an asynchronous interrupt."""
        halt = getattr(self.m, "halt", None)
        if halt is not None:
            try:
                halt()
            except SafetyViolation:
                raise
            except Exception:  # noqa: BLE001
                pass
        self.homed = False
        try:
            if self.holding:
                self.vac.hold()
            elif not self.freeze:
                self.vac.release()  # nothing was lifted: let go of anything the open cup sealed on
        except SafetyViolation:
            raise
        except Exception:  # noqa: BLE001
            pass
        msg = ("Hard stop (Ctrl-C twice): the motors were halted where they were and nothing moved after that. The controller was reset, "
               "so the next run or resume homes first.")
        if self.holding and self.held_from is not None:
            src = self.held_from[0]
            msg += (f" A slab from pocket {src} is on the cup; the pump keeps holding it. Hold it, vent the cup (the command line asks you; the "
                    f"web page has a Vent button) and put it face-down on top of pocket {src}; it will be read again on resume.")
        else:
            msg += " Nothing is held in the cup. Check the head before touching the bed."
        return msg

    def _guarded(self, body: Callable[[], dict]) -> dict:
        try:
            return self._guarded_inner(body)
        finally:
            try:
                self._save_refs(force=True)
            except Exception:  # noqa: BLE001 - never mask the stop that got us here
                pass

    def _guarded_inner(self, body: Callable[[], dict]) -> dict:
        try:
            return body()
        except ControllerLost as e:
            note = self.lost_note()
            self._journal({"stop": str(e), "lost_controller": True, "secured": note, "t": round(time.time(), 1)})
            self.phase = "stopped"
            raise Stop(note) from None
        except Stop as e:
            note = self.secure()
            self._journal({"stop": str(e), "secured": note, "t": round(time.time(), 1)})
            self.phase = "stopped"
            raise Stop(f"{e} {note}".strip()) from None
        except SafetyViolation:
            raise  # simulator safety monitor: let the test fail loudly
        except KeyboardInterrupt:  # Ctrl-C twice = stop NOW: no automatic motion at all
            note = self.hard_stop()
            self._journal({"stop": "operator hard stop (Ctrl-C twice)", "holding": self.holding,
                           "held_from": list(self.held_from) if self.held_from else None, "secured": note, "t": round(time.time(), 1)})
            self.phase = "stopped"
            raise HardStop(note) from None
        except Exception as e:  # camera died, decoder bug, controller alarm or comms error ...
            # Anything unplanned while a slab is in the cup must still end with the slab put back (after
            # secure() has re-read the real position), never hanging on closed valves.
            note = self.secure()
            self._journal({"stop": f"unexpected {type(e).__name__}: {e}", "secured": note, "t": round(time.time(), 1)})
            self.phase = "stopped"
            raise Stop(f"Unexpected error: {type(e).__name__}: {e}. {note}".strip()) from e

    def run(self) -> dict:
        def body():
            self._preflight()
            self._home()
            self._check_gate()
            self._journal({"start": round(time.time(), 1), "batch": self.w.batch_id})
            self.phase = "survey"
            self.survey()
            self._journal({"survey": {str(k): round(v, 2) for k, v in self.st.survey_tops.items()}})
            self._log_face_down()
            return self._work()

        return self._guarded(body)

    def resume(self, accept_heights: bool = False, face_down_ok: bool = False) -> dict:
        """Continue a stopped batch: rebuild the State from journal.jsonl + certs.csv, re-survey every
        pocket against the heights the journal predicts, then carry on where it stopped.
        ``face_down_ok``: the operator checked that the slab the face-down check stopped on is face-down."""
        self.face_down_ok_once = face_down_ok
        events = read_journal(self.journal)
        st, itf, surveyed = rebuild_state(events, self.w.rows, self.cfg)
        if not surveyed:
            self.log("resume: the run stopped before the first survey finished - starting it from the beginning")
            return self.run()
        self.st = st
        self.itf.evidence.update(itf)
        if any(e.get("finished") for e in events):
            self.log("resume: this batch already finished")

        def body():
            self._preflight()
            self._home()
            self._check_gate()
            self.phase = "survey"
            expect = dict(self.st.tops)
            self.survey(expect=expect, accept=accept_heights)
            self._journal({"resume": round(time.time(), 1), "resurvey": {str(k): round(v, 2) for k, v in self.st.tops.items()}})
            self._log_face_down()
            return self._work()

        return self._guarded(body)

    def _log_face_down(self) -> None:
        if self.refs.note:
            self.log(f"card-back references: {self.refs.note}")
            self.refs.note = ""
        self.log(self.face_down_status())

    def _work(self) -> dict:
        srcs = [p.index for p in self.cfg.sources]
        for k in srcs:
            if k in self.st.done_sources:
                continue
            dst = k - 1
            self.current = (k, dst)
            self.phase = "transfer"
            self._check_pause()
            while self.transfer(k, dst):
                self._check_pause()
            self.st.done_sources.append(k)
            self._journal({"source_done": k})
        self.current = None
        self._z(self.c(self.cfg.c_safe_empty))
        p0 = self.cfg.pocket(0)
        self._go(p0.x, p0.y)  # park over the (now full) first output stack, out of the operator's way
        extra = {
            "count_check": self.count_check(),
            "itf_mode": self.itf.mode,
            "itf_evidence": dict(self.itf.evidence),
            "mean_cycle_s": round(sum(self.timings) / len(self.timings), 2) if self.timings else None,
            "final_tops_mm": {k: round(v, 1) for k, v in self.st.tops.items()},
            "face_down": self._face_down_summary(),
        }
        self._journal({"finished": True})
        self.phase = "done"
        return self.w.finish(extra)
