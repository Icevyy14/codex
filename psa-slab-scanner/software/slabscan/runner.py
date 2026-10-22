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
slab in a safe state and a message saying what to do. ``secure()`` puts a slab that is
still in the cup back on top of the stack it came from. ``resume`` rebuilds the State
from journal.jsonl (+ certs.csv), re-surveys every pocket, and continues.
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
from .decode import decode_frame
from .results import BatchWriter, SlabResult

NOMINAL_T = 6.6  # mm, used only to turn heights into rough slab counts


class Stop(Exception):
    """Run halted safely; message tells the operator what to do."""


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
            st.picked_from[r.source_pocket] = r.source_index
            st.out_count[r.out_pocket] = r.out_index
            st.tops[r.source_pocket] = max(0.0, st.tops.get(r.source_pocket, 0.0) - t_est)
            st.tops[r.out_pocket] = st.tops.get(r.out_pocket, 0.0) + t_est
            st.position = r.position
    return st, itf, surveyed


class Runner:
    def __init__(self, cfg: Config, motion, vacuum, lights, head_cam, station_cam, writer: BatchWriter, lid=None, gate=None, log=print,
                 should_stop: Callable[[], bool] | None = None):
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
        self.z = None  # last commanded machine Z
        self.holding = False
        self.held_from: tuple[int, float] | None = None  # (source pocket, pick height s) of the slab in the cup
        self.homed = False
        self.phase = "idle"  # idle | survey | transfer | done (for the web page)
        self.current: tuple[int, int] | None = None  # (source, destination) being worked on
        self.timings: list[float] = []

    # ------------------------------------------------------------------ coordinates
    def xy(self, x: float, y: float) -> tuple[float, float]:
        a = math.radians(self.cfg.rotation_deg)
        return (x * math.cos(a) - y * math.sin(a) + self.cfg.offset_x, x * math.sin(a) + y * math.cos(a) + self.cfg.offset_y)

    def c(self, s: float) -> float:
        return s + self.cfg.pad_trigger_c

    def s(self, c: float) -> float:
        return c - self.cfg.pad_trigger_c

    # ------------------------------------------------------------------ primitives
    def _z(self, c: float, feed: float | None = None) -> None:
        c = min(c, self.c(self.cfg.c_max))
        self.m.move(feed or self.cfg.feed_z, z=c)
        self.m.wait_idle()
        self.z = c

    def _go(self, x: float, y: float) -> None:
        """XY move, only ever at a safe height."""
        safe = self.c(self.cfg.c_safe_loaded if self.holding else self.cfg.c_safe_empty)
        if self.z is None or self.z < safe - 0.01:
            self._z(safe)
        mx, my = self.xy(x, y)
        if "Y" in self.cfg.axes:
            self.m.move(self.cfg.feed_xy, x=mx, y=my)
        else:
            self.m.move(self.cfg.feed_xy, x=mx)
        self.m.wait_idle()
        if self.holding:
            self._check_vacuum("in transit")

    def _probe(self, c_from: float, c_to: float) -> float | None:
        """Fast to c_from, then probe down to c_to at probe speed. Returns trigger Z or None.

        Callers choose c_to so the cup can never be driven more than probe_window past the
        surface it is looking for - well inside the 25 mm spring-buffer stroke.
        """
        self._z(c_from)
        hit = self.m.probe(c_to, self.cfg.feed_probe)
        self.z = hit if hit is not None else c_to
        return hit

    def _check_vacuum(self, where: str) -> None:
        k = self.vac.kpa()
        if k > self.cfg.vac_transit_alarm_kpa:
            raise Stop(f"Vacuum lost {where} ({k:.0f} kPa). A slab may have dropped. Check the bed and the cup, then resume.")

    def _wait_seal(self) -> bool:
        t0 = time.monotonic()
        while time.monotonic() - t0 < self.cfg.vac_seal_timeout_s:
            if self.vac.kpa() <= self.cfg.vac_seal_kpa:
                return True
            time.sleep(0.02)
        return self.vac.kpa() <= self.cfg.vac_seal_kpa

    def _frames(self, cam, light: str, n: int) -> list:
        getattr(self.lights, light)(True)
        try:
            return [cam.capture() for _ in range(n)]
        finally:
            getattr(self.lights, light)(False)

    def _read(self, frames, camera: str) -> tuple[list[CodeRead], list[str]]:
        reads: list[CodeRead] = []
        unparsed: list[str] = []
        for i, f in enumerate(frames):
            r, u = decode_frame(f, camera, self.cfg.custom_regex, allow_ocr=self.cfg.allow_ocr and i == len(frames) - 1 and not reads)
            reads += r
            unparsed += u
        return reads, unparsed

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
        self._z(self.c(self.cfg.c_safe_empty))

    # ------------------------------------------------------------------ survey
    def _find_top(self, p) -> float | None:
        """Walk down over pocket p in probe windows from above the MAX line until contact.
        Returns the top surface height s (None = never touched). Ends at the empty safe height."""
        cfg = self.cfg
        self._go(p.x, p.y)
        top = None
        c = self.c(cfg.max_line + 6)
        self.vac.hold()  # an open cup that suddenly seals = contact the optical sensor missed
        try:
            while c > self.c(-2):  # walk down in probe windows until contact
                hit = self._probe(c, max(self.c(-2), c - cfg.probe_window))
                if hit is not None:
                    top = self.s(hit)
                    break
                if self.vac.kpa() <= cfg.vac_seal_kpa:
                    raise Stop(f"Pocket {p.index}: the cup sealed on something but the contact sensor did not trip. Contact sensor fault - stop and check it.")
                c -= cfg.probe_window
        finally:
            self.vac.release()
        self._z(self.c(cfg.c_safe_empty))
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
                raise Stop(f"Pocket {p.index} is filled above the MAX line ({top:.0f} mm > {cfg.max_line:.0f}). Remove slabs and restart.")
            if expect is None and p.role != "source" and top > cfg.t_min / 2:
                raise Stop(f"Pocket {p.index} ({p.role}) must start empty but is {top:.1f} mm tall.")
            measured[p.index] = max(0.0, top)
            self.log(f"survey pocket {p.index:2d} ({p.role}): top {top:6.1f} mm ~ {round(max(0, top) / NOMINAL_T)} slabs")
        if expect is not None:
            self._check_resurvey(measured, expect, accept)
        for k, v in measured.items():
            self.st.tops[k] = v
            if expect is None:
                self.st.survey_tops[k] = v
        return dict(self.st.tops)

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
        # hover look before touching anything (also a first read of the back label)
        self._z(self.c(s_pred) + cfg.approach_gap + 2)
        hover_frames = self._frames(self.head_cam, "head", 1) if cfg.hover_check else []
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
        self.vac.hold()
        if not self._wait_seal():
            self.vac.release()
            self._z(hit + 3)
            hit2 = self._probe(hit + 3, hit - 4)
            if hit2 is not None:
                self.vac.hold()
            if hit2 is None or not self._wait_seal():
                self.vac.release()
                self._z(self.c(cfg.c_safe_empty))
                raise Stop(f"Pocket {src}: cup will not seal on the top slab (dirty cup, warped or face-up slab?). Fix it, then resume.")
        self.holding = True
        self.held_from = (src, s_top)
        self._z(hit + cfg.peel_slow_mm, cfg.feed_peel_slow)  # very slow first mm: squeeze-film force ~ speed
        self._z(hit + cfg.peel_mm, cfg.feed_peel)
        time.sleep(cfg.peel_dwell_s)
        self._check_vacuum("after peel")
        self._z(self.c(cfg.c_safe_loaded))
        back = self._frames(self.head_cam, "head", cfg.frames_per_read)
        reads, unparsed = self._read(hover_frames + back, "back")
        verdict = consensus(reads, self.itf, accepted=tuple(cfg.accepted_graders))
        front = None
        if cfg.front_photo == "always" or verdict.status != "ok":
            sx, sy = cfg.station_xy
            self._go(sx, sy)
            self._z(self.c(cfg.station_read_c))
            front_frames = self._frames(self.station_cam, "station", cfg.frames_per_read)
            front = front_frames[-1]
            f_reads, f_unparsed = self._read(front_frames, "front")
            reads += f_reads
            unparsed += f_unparsed
            verdict = consensus(reads, self.itf, accepted=tuple(cfg.accepted_graders))
            self._z(self.c(cfg.c_safe_loaded))
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
        flags = []
        if step >= cfg.t_double:
            flags.append(f"DOUBLE PICK: an unread slab is directly under this one in pocket {target.index}")
        elif step > cfg.t_std_max:
            flags.append(f"thick holder ({step:.1f} mm)")
        elif step < cfg.t_min - 0.5:
            flags.append(f"thin/odd step {step:.1f} mm - check seating")
        self.vac.release()
        self.holding = False
        self.held_from = None
        self._z(hit + cfg.peel_mm, cfg.feed_peel)
        self._z(self.c(cfg.c_safe_empty))
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
        self.w.add(SlabResult(pos, src, self.st.picked_from[src], target.index, self.st.out_count[target.index], verdict, img_f, img_b))
        self._journal({"pos": pos, "src": src, "dst": target.index, "cert": verdict.cert, "status": verdict.status, "step": round(step, 2),
                       "s_src": round(self.st.tops[src], 2), "s_dst": round(self.st.tops[target.index], 2),
                       "src_index": self.st.picked_from[src], "out_index": self.st.out_count[target.index],
                       "itf": dict(self.itf.evidence), "unparsed": unparsed[:5]})
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
        self.vac.hold()
        if not self._wait_seal():
            self.vac.release()
            self._z(self.c(cfg.c_safe_empty))
            raise Stop(f"Pocket {pocket}: cup will not seal on the slab (dirty cup, or slab face-up?).")
        self.holding = True
        self.held_from = (pocket, self.s(hit))
        self._z(hit + cfg.peel_slow_mm, cfg.feed_peel_slow)
        self._z(hit + cfg.peel_mm, cfg.feed_peel)
        self._check_vacuum("after peel")
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
        self.vac.release()
        self.holding = False
        self.held_from = None
        self._z(hit + cfg.peel_mm, cfg.feed_peel)
        self._z(self.c(cfg.c_safe_empty))
        return src

    def secure(self) -> str:
        """After a Stop: leave nothing hanging in the air. Returns a note for the operator."""
        if not self.homed:
            return ""
        try:
            if self.holding and self.held_from is not None:
                src = self.held_from[0]
                k = self.vac.kpa()
                if k > self.cfg.vac_transit_alarm_kpa:
                    # Do not vent and do not move: if the slab is still stuck, venting would drop it.
                    self.vac.close()
                    return (f"Vacuum is low ({k:.0f} kPa) and the slab may have fallen. The head was left where it is with the valves shut. "
                            f"If a slab is still on the cup, hold it and pull it off gently. Put that slab (or the one that fell) face-down on top of pocket {src}.")
                self.put_back()
                return f"The slab that was in the cup was put back on top of pocket {src}; it will be read again on resume."
            self.vac.release()
            if self.z is None or self.z < self.c(self.cfg.c_safe_empty) - 0.01:
                self._z(self.c(self.cfg.c_safe_empty))
            return ""
        except Exception as e:  # noqa: BLE001 - report, never mask the original Stop
            return f"Could not park the machine automatically ({e}). Check the head before touching the bed."

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
        if self.lid is not None and not self.lid.closed():
            raise Stop("Close the lid to start.")
        if self.gate is not None and not self.gate.clear():
            raise Stop("The overfill light beam is blocked: a stack is above the MAX line (or something is lying on the stacks). Fix it, then start again.")
        k = self.vac.kpa()
        if k <= self.cfg.vac_transit_alarm_kpa:
            raise Stop(f"The cup line is holding vacuum ({k:.0f} kPa): a slab may still be stuck to the cup. Take it off by hand, put it back on top of the stack it came from, then start again.")

    def _check_pause(self) -> None:
        if self.lid is not None and not self.lid.closed():
            raise Stop("Lid opened - run paused with nothing held. Close the lid and resume.")
        if self.should_stop is not None and self.should_stop():
            raise Stop("Stopped on request - nothing held. Resume to continue.")

    def _guarded(self, body: Callable[[], dict]) -> dict:
        try:
            return body()
        except Stop as e:
            note = self.secure()
            self._journal({"stop": str(e), "secured": note, "t": round(time.time(), 1)})
            self.phase = "stopped"
            raise Stop(f"{e} {note}".strip()) from None

    def run(self) -> dict:
        def body():
            self._preflight()
            self._home()
            self._journal({"start": round(time.time(), 1), "batch": self.w.batch_id})
            self.phase = "survey"
            self.survey()
            self._journal({"survey": {str(k): round(v, 2) for k, v in self.st.survey_tops.items()}})
            return self._work()

        return self._guarded(body)

    def resume(self, accept_heights: bool = False) -> dict:
        """Continue a stopped batch: rebuild the State from journal.jsonl + certs.csv, re-survey every
        pocket against the heights the journal predicts, then carry on where it stopped."""
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
            self.phase = "survey"
            expect = dict(self.st.tops)
            self.survey(expect=expect, accept=accept_heights)
            self._journal({"resume": round(time.time(), 1), "resurvey": {str(k): round(v, 2) for k, v in self.st.tops.items()}})
            return self._work()

        return self._guarded(body)

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
        }
        self._journal({"finished": True})
        self.phase = "done"
        return self.w.finish(extra)
