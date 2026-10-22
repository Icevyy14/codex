"""The batch run: move every stack one pocket over, reading each slab on the way.

Pocket k (k = 1..N) is emptied onto pocket k-1. Pocket 0 starts empty, so each source
always lands on the pocket its predecessor just vacated. Unreadable/other-grader slabs
go to the exception pocket. Order within a stack reverses; the CSV records the exact
output position of every slab.

Heights: s = surface height above the pad top (mm). The machine Z (cup face) at probe
trigger on a surface s is  c = s + cfg.pad_trigger_c  (calibrated by probing the bare pad).

Fail-stop rule: anything the machine cannot explain (no vacuum seal, a stack taller than
expected, vacuum lost in transit, contact where none should be) stops the run with the
slab in a safe state and a message saying what to do. ``resume`` continues from the journal.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from .certs import CodeRead, ItfModel, Verdict, consensus
from .config import Config
from .decode import decode_frame
from .results import BatchWriter, SlabResult


class Stop(Exception):
    """Run halted safely; message tells the operator what to do."""


@dataclass
class State:
    tops: dict[int, float] = field(default_factory=dict)  # pocket -> top surface height s
    out_count: dict[int, int] = field(default_factory=dict)  # pocket -> slabs placed there this run
    picked_from: dict[int, int] = field(default_factory=dict)  # source pocket -> slabs removed
    position: int = 0
    done_sources: list[int] = field(default_factory=list)
    thickness_log: list[float] = field(default_factory=list)


class Runner:
    def __init__(self, cfg: Config, motion, vacuum, lights, head_cam, station_cam, writer: BatchWriter, lid=None, log=print):
        self.cfg = cfg
        self.m = motion
        self.vac = vacuum
        self.lights = lights
        self.head_cam = head_cam
        self.station_cam = station_cam
        self.w = writer
        self.lid = lid
        self.log = log
        self.st = State()
        self.itf = ItfModel()
        self.journal = writer.dir / "journal.jsonl"
        self.z = None  # last commanded machine Z
        self.holding = False
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
        c = min(c, self.cfg.c_max)
        self.m.move(feed or self.cfg.feed_z, z=c)
        self.m.wait_idle()
        self.z = c

    def _go(self, x: float, y: float) -> None:
        """XY move, only ever at a safe height."""
        safe = self.cfg.c_safe_loaded if self.holding else self.cfg.c_safe_empty
        if self.z is None or self.z < safe - 0.01:
            self._z(safe)
        mx, my = self.xy(x, y)
        self.m.move(self.cfg.feed_xy, x=mx, y=my)
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

    # ------------------------------------------------------------------ survey
    def survey(self) -> dict[int, float]:
        """Probe every pocket once: start/exception pockets must be empty, sources must be under the fill line."""
        cfg = self.cfg
        for p in cfg.pockets:
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
            self._z(cfg.c_safe_empty)
            if top is None:
                raise Stop(f"Pocket {p.index}: probe never touched anything (not even the pad). Check the contact sensor wiring and calibration.")
            if top > cfg.max_line + 1:
                raise Stop(f"Pocket {p.index} is filled above the MAX line ({top:.0f} mm > {cfg.max_line:.0f}). Remove slabs and restart.")
            if p.role != "source" and top > cfg.t_min / 2:
                raise Stop(f"Pocket {p.index} ({p.role}) must start empty but is {top:.1f} mm tall.")
            self.st.tops[p.index] = max(0.0, top)
            self.log(f"survey pocket {p.index:2d} ({p.role}): top {top:6.1f} mm ~ {round(max(0, top) / 6.6)} slabs")
        return dict(self.st.tops)

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
                self._z(cfg.c_safe_empty)
                raise Stop(f"Pocket {src}: no contact where the stack should be (predicted {s_pred:.1f} mm). Check the contact sensor, then resume.")
        s_top = self.s(hit)
        if s_top - s_pred > cfg.max_surprise:
            self._z(cfg.c_safe_empty)
            raise Stop(f"Pocket {src} is {s_top - s_pred:.1f} mm taller than expected - was a slab added or is one sitting crooked? Fix it, then resume.")
        if s_top < cfg.t_min / 2:
            self.st.tops[src] = 0.0
            self._z(cfg.c_safe_empty)
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
                self._z(cfg.c_safe_empty)
                raise Stop(f"Pocket {src}: cup will not seal on the top slab (dirty cup, warped or face-up slab?). Fix it, then resume.")
        self.holding = True
        self._z(hit + cfg.peel_mm, cfg.feed_peel)  # slow peel so an air-film second slab drops back
        time.sleep(cfg.peel_dwell_s)
        self._check_vacuum("after peel")
        self._z(cfg.c_safe_loaded)
        back = self._frames(self.head_cam, "head", cfg.frames_per_read)
        reads, unparsed = self._read(hover_frames + back, "back")
        verdict = consensus(reads, self.itf, accepted=tuple(cfg.accepted_graders))
        front = None
        if cfg.front_photo == "always" or verdict.status != "ok":
            sx, sy = cfg.station_xy
            self._go(sx, sy)
            self._z(cfg.station_read_c)
            front_frames = self._frames(self.station_cam, "station", cfg.frames_per_read)
            front = front_frames[-1]
            f_reads, f_unparsed = self._read(front_frames, "front")
            reads += f_reads
            unparsed += f_unparsed
            verdict = consensus(reads, self.itf, accepted=tuple(cfg.accepted_graders))
            self._z(cfg.c_safe_loaded)
        to_output = verdict.status == "ok" or (verdict.status == "needs_review" and cfg.needs_review_to == "output")
        target = cfg.pocket(dst) if to_output else pex
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
        self._z(hit + cfg.peel_mm, cfg.feed_peel)
        self._z(cfg.c_safe_empty)
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
        self._journal({"pos": pos, "src": src, "dst": target.index, "cert": verdict.cert, "status": verdict.status, "step": round(step, 2), "s_src": round(self.st.tops[src], 2), "s_dst": round(self.st.tops[target.index], 2), "unparsed": unparsed[:5]})
        self.timings.append(time.monotonic() - t0)
        self.log(f"#{pos:3d} P{src}->P{target.index} {verdict.status:12} {verdict.cert or '-':>10} step {step:4.1f} {verdict.note}")
        return True

    # ------------------------------------------------------------------ whole batch
    def run(self) -> dict:
        if self.lid is not None and not self.lid.closed():
            raise Stop("Close the lid to start.")
        self.m.home()
        self.z = None
        self._z(self.cfg.c_safe_empty)
        self.survey()
        srcs = [p.index for p in self.cfg.sources]
        for k in srcs:
            dst = k - 1
            while self.transfer(k, dst):
                if self.lid is not None and not self.lid.closed():
                    raise Stop("Lid opened - run paused with nothing held. Close the lid and resume.")
            self.st.done_sources.append(k)
            self._journal({"source_done": k})
        self._z(self.cfg.c_safe_empty)
        x, y = self.cfg.station_xy
        self._go(x, y + 120)  # park out of the way
        extra = {
            "itf_mode": self.itf.mode,
            "itf_evidence": dict(self.itf.evidence),
            "mean_cycle_s": round(sum(self.timings) / len(self.timings), 2) if self.timings else None,
            "final_tops_mm": {k: round(v, 1) for k, v in self.st.tops.items()},
        }
        return self.w.finish(extra)
