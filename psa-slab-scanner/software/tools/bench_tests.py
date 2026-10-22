"""SlabRail bench tests (docs/BUILD_GUIDE.md sections 7.8 and 13). JUNK SLABS ONLY.

Run from software/ with the venv active. Stop the web service first (sudo systemctl stop slabrail-web):
two programs on one controller are refused. Add --sim to try any test on the simulator first.

  python -m tools.bench_tests cycles 300     300 pick-read-place transfers: the slabs in pocket 1 go to pocket 0, then back (13.2)
  python -m tools.bench_tests rest 24        cup sealed on the top slab of pocket 1 for 24 h, re-held whenever the line rises above -40 kPa (13.2)
  python -m tools.bench_tests lifts 100      100 full-height Z lifts at full speed with a slab held, then re-probe pocket 0's bare pad (7.8)
  python -m tools.bench_tests drop 2         DESTRUCTIVE: pick the top slab of pocket 1, carry it over pocket 2, vent: it DROPS (13.3)
  python -m tools.bench_tests powercut 300   pick the top slab of pocket 1, hold it at carry height, log the vacuum while you press the E-stop (13.4)

Every test runs inside the runner's own guard, like a real run: a Stop or an unexpected error (camera, controller
ALARM, ...) puts a held slab back where it came from, or keeps the pump holding it and asks you to take it. Ctrl-C
halts the motors at once. The program never ends with a slab hanging on shut valves.
"""

from __future__ import annotations

import argparse
import dataclasses
import time
from pathlib import Path

from slabscan.cli import DEFAULT_CONFIG, hand_off_slab
from slabscan.config import Config, load
from slabscan.factory import open_hardware
from slabscan.motion import ControllerLost
from slabscan.ops import Console
from slabscan.results import BatchWriter
from slabscan.runner import NOMINAL_T, Runner, Stop

REHOLD_KPA = -40.0  # rest test: re-hold (pump on, valve open) whenever the closed cup line is above this
REHOLD_S = 2.0
PAD_DRIFT_MAX = 0.1  # lifts test: bare-pad trip height before vs after, mm


class BenchWriter(BatchWriter):
    """The bench tests read the same junk slab again and again on purpose. A real run treats a cert that is
    already in the batch as a conflict (exception pocket); here the runner must not see the earlier rows."""

    @property
    def rows(self):
        return []

    def all_rows(self):
        return list(self._rows)


def _start(r: Runner) -> None:
    r._preflight()
    r._home()
    r._check_gate()


def cycles(r: Runner, cfg: Config, n: int, src: int, con: Console) -> dict:
    _start(r)
    r.survey()  # pocket 0 and pocket 12 must be empty, as for a real run
    here, there, done = src, 0, 0
    while done < n:
        if not r.transfer(here, there):  # source empty: turn round
            here, there = there, here
            if not r.transfer(here, there):
                raise Stop(f"No slab left to move between pocket {src} and pocket 0 (did it go to the exception pocket? see certs.csv).")
        done += 1
    r._z(r.c(cfg.c_safe_empty))
    rows = r.w.all_rows()
    ok = sum(1 for x in rows if x.verdict.status == "ok")
    certs = sorted({x.verdict.cert for x in rows if x.verdict.cert})
    con.say(f"{done} transfers, {ok} read ok, certs seen: {certs}")
    con.say(f"rows in {r.w.csv_path}. Put the slabs back by hand before a real run (pocket 0 must start empty).")
    return {"transfers": done, "ok": ok, "certs": certs}


def rest(r: Runner, cfg: Config, hours: float, src: int, con: Console, poll_s: float = 5.0, clock=time.monotonic, sleep=time.sleep) -> dict:
    """Cup sealed on a supported slab (it rests on its stack, the buffer at its trip point) for `hours`.
    The closed cup line leaks, so it is re-held for REHOLD_S whenever it rises above REHOLD_KPA."""
    _start(r)
    p = cfg.pocket(src)
    top = r._find_top(p)
    if top is None or top < cfg.t_min / 2:
        raise Stop(f"Pocket {src} is empty. Put the junk slab in it face-down.")
    hit = r._probe(r.c(top) + cfg.approach_gap, r.c(top) - 3.0)
    if hit is None:
        raise Stop(f"Pocket {src}: lost the slab between two probes. Check the contact sensor.")
    vac = r.vac
    vac.hold()
    sleep(REHOLD_S)
    vac.close()  # pump off, both valves shut: the cup line stays sealed on its own
    pump_s, reholds, n, below, ksum, kmin = REHOLD_S, 0, 0, 0, 0.0, 0.0
    t0 = clock()
    t_end, t_log = t0 + hours * 3600.0, t0
    while clock() < t_end:
        sleep(poll_s)
        k = r._kpa()
        n += 1
        ksum += k
        kmin = min(kmin, k)
        below += k <= REHOLD_KPA
        if k > REHOLD_KPA:
            vac.hold()
            sleep(REHOLD_S)
            vac.close()
            pump_s += REHOLD_S
            reholds += 1
        if clock() - t_log >= 600.0:
            t_log = clock()
            el = (t_log - t0) / 3600.0
            con.say(f"{time.strftime('%H:%M')}  {el:5.2f} h  now {k:6.1f} kPa  mean {ksum / n:6.1f}  min {kmin:6.1f}  re-holds {reholds}")
    total = max(clock() - t0, 1e-9)
    mean = ksum / n if n else 0.0
    stats = {"hours": round(total / 3600.0, 3), "samples": n, "mean_kpa": round(mean, 1), "min_kpa": round(kmin, 1),
             "pct_below_40": round(100.0 * below / n, 1) if n else 0.0, "reholds": reholds,
             "reholds_per_h": round(reholds / (total / 3600.0), 1), "pump_duty_pct": round(100.0 * pump_s / total, 2)}
    r._vent(f"on pocket {src} after the rest test")
    r._lift_off(hit, f"on pocket {src} after the rest test")
    con.say("rest test: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    if getattr(vac, "simulated", False):
        con.say("(simulator: its cup line has no leak model, so these numbers mean nothing)")
    elif mean <= REHOLD_KPA:
        con.say(f"vacuum: PASS (mean {mean:.1f} kPa <= {REHOLD_KPA:.0f}). Now inspect the slab under raking light before touching the contact spot.")
    else:
        con.say(f"vacuum: FAIL (mean {mean:.1f} kPa > {REHOLD_KPA:.0f}): the clamp was not held for most of the test. Fix the leak "
                "(BUILD_GUIDE 8.3) and repeat; the marking result of this run does not count.")
    return stats


def _pad_height(r: Runner, cfg: Config) -> float:
    p0 = cfg.pocket(0)
    r._go(p0.x, p0.y)
    hit = r._probe(r.c(5.0), r.c(-4.0))
    if hit is None:
        raise Stop("No contact on pocket 0's bare pad between +5 and -4 mm: Z lost steps, or calibrate z is out of date.")
    r._z(r.c(cfg.c_safe_empty))
    return r.s(hit)


def lifts(r: Runner, cfg: Config, n: int, src: int, con: Console) -> dict:
    """Z stall check (BOM Z motor line, BUILD_GUIDE 7.8): a stall while lifting a slab leaves the head lower
    than the software thinks. Probe the bare pad, do n full-height lifts at feed_z with a slab held, put it
    back, probe the pad again without homing. A difference means lost steps."""
    _start(r)
    top0 = r._find_top(cfg.pocket(0))
    if top0 is None or top0 > cfg.t_min / 2:
        raise Stop("Pocket 0 must be empty: its bare pad is the reference.")
    before = _pad_height(r, cfg)
    s_pick = r.pick_top(src)
    low, high = r.c(s_pick + 10.0), r.c(cfg.c_max)
    for i in range(n):
        r._z(high)
        r._z(low)
        r._check_vacuum(f"during lift {i + 1}")
    r._z(r.c(cfg.c_safe_loaded))
    r.put_back()
    after = _pad_height(r, cfg)
    drift = after - before
    con.say(f"{n} lifts of {cfg.c_max - s_pick - 10.0:.0f} mm at {cfg.feed_z:.0f} mm/min with a slab held. Bare pad of pocket 0: "
            f"{before:+.2f} mm before, {after:+.2f} mm after (difference {drift:+.2f}; calibration says 0.00).")
    if abs(drift) <= PAD_DRIFT_MAX:
        con.say(f"Z lift test: PASS (within {PAD_DRIFT_MAX} mm).")
    else:
        con.say(f"Z lift test: FAIL - Z lost steps. Lower feed_z and the firmware's Z max_rate_mm_per_min to 3000 and repeat; check the Z motor "
                "is the specified 1.5-2.0 A, <= 4 mH type (BOM) and run_amps is 50-70 % of its rating.")
    return {"before": round(before, 3), "after": round(after, 3), "drift": round(drift, 3)}


def drop(r: Runner, cfg: Config, into: int, src: int, con: Console) -> dict:
    """DESTRUCTIVE on purpose: vents a held slab over a pocket so it falls (worst case: onto the bare pad)."""
    _start(r)
    over = cfg.pocket(into)
    below = r._find_top(over)
    if below is None:
        raise Stop(f"Pocket {into}: the probe never touched anything.")
    r.pick_top(src)
    r._go(over.x, over.y)
    fall = r.s(r.z) - NOMINAL_T - below
    a = con.ask(f"The slab will DROP about {fall:.0f} mm into pocket {over.index}. Hands clear, then type DROP and press Enter "
                "(anything else puts it back): ").strip().lower()
    if a != "drop":
        r.put_back()
        con.say("not dropped: the slab is back on its stack.")
        return {"dropped": False}
    r.vac.release()
    r.holding, r.held_from = False, None
    con.say("dropped. Inspect the corners and faces of the dropped slab and the top slab below it.")
    return {"dropped": True, "fall_mm": round(fall)}


def powercut(r: Runner, cfg: Config, seconds: float, src: int, con: Console, clock=time.monotonic, sleep=time.sleep) -> dict:
    """Holds a slab at carry height and logs the cup vacuum (the Pi keeps its own power) while you cut the
    machine power. The slab falls when the line leaks to about -1.7 kPa: the test is how long that takes."""
    _start(r)
    r.pick_top(src)
    con.say(f"Holding a slab {r.s(r.z):.0f} mm above the pad over pocket {src}. PRESS THE E-STOP NOW (or pull the machine's mains cord). "
            f"Logging for {seconds:.0f} s.")
    t0, t_cut, held_s = clock(), None, None
    while clock() - t0 < seconds:
        if t_cut is None and hasattr(r.m, "status"):
            try:
                r.m.status()
            except ControllerLost:
                t_cut = clock()
                con.say("controller gone (the power cut works). Watching the cup vacuum:")
        k = r.vac.kpa()
        since = f"{clock() - t_cut:5.0f} s after the cut" if t_cut is not None else "before the cut"
        con.say(f"  {since}: {k:6.1f} kPa")
        if t_cut is not None and k > -3.0:
            held_s = clock() - t_cut
            con.say(f"vacuum gone {held_s:.0f} s after the cut: the slab drops (or has dropped) here.")
            break
        sleep(1.0)
    if t_cut is None:
        con.say("The controller never went away (was the E-stop pressed?): putting the slab back.")
        r.put_back()
        return {"cut": False, "held_s": None}
    if held_s is None:
        held_s = clock() - t_cut
        con.say(f"still holding {held_s:.0f} s after the cut.")
    con.say("Release the E-stop (the pump comes back and holds the slab), then follow the prompt to take the slab off. "
            "Then `python -m slabscan home`.")
    return {"cut": t_cut is not None, "held_s": None if held_s is None else round(held_s)}


def main(argv=None, console: Console | None = None, hw=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("test", choices=["cycles", "rest", "lifts", "drop", "powercut"])
    ap.add_argument("n", type=float, help="cycles/lifts: count | rest: hours | drop: pocket to drop into | powercut: seconds to log")
    ap.add_argument("--src", type=int, default=1, help="pocket the junk slabs start in (default 1)")
    ap.add_argument("--poll", type=float, default=5.0, help="rest: seconds between vacuum readings (default 5)")
    ap.add_argument("--face-down-check-off", action="store_true",
                    help="cycles: skip the face-down check (only for a junk slab with a pre-2017 label that you checked is face-down)")
    ap.add_argument("--sim", action="store_true", help="simulator instead of the machine")
    ap.add_argument("--out", default=None, help="output folder (default: the config's out_dir)")
    a = ap.parse_args(argv)
    con = console or Console()
    cfg = load(DEFAULT_CONFIG, DEFAULT_CONFIG.parent / "calibration.toml")
    if a.face_down_check_off:
        cfg = dataclasses.replace(cfg, face_down_check="off")
    if hw is None:
        kw = {}
        if a.sim:
            from slabscan.simworld import SimSlab

            kw["stacks"] = {**{p.index: [] for p in cfg.pockets}, a.src: [SimSlab(str(148069831 + 7919 * i), 6.6) for i in range(3)]}
        hw = open_hardware(cfg, sim=a.sim, **kw)
    w = BenchWriter(Path(a.out or cfg.out_dir), f"bench-{a.test}-" + time.strftime("%Y%m%d-%H%M%S"))
    r = Runner(cfg, hw.motion, hw.vacuum, hw.lights, hw.head_cam, hw.station_cam, w, lid=hw.lid, gate=hw.gate, log=con.say)
    sim = bool(getattr(hw, "sim", False))
    tests = {
        "cycles": lambda: cycles(r, cfg, int(a.n), a.src, con),
        "rest": lambda: rest(r, cfg, a.n, a.src, con, poll_s=a.poll, sleep=(lambda s: None) if sim else time.sleep,
                             clock=_SimClock(a.poll) if sim else time.monotonic),
        "lifts": lambda: lifts(r, cfg, int(a.n), a.src, con),
        "drop": lambda: drop(r, cfg, int(a.n), a.src, con),
        "powercut": lambda: powercut(r, cfg, a.n, a.src, con, sleep=(lambda s: None) if sim else time.sleep,
                                     clock=_SimClock(1.0) if sim else time.monotonic),
    }
    code = 0
    try:
        try:
            r._guarded(tests[a.test])
        except Stop as e:  # HardStop is a Stop too: the motors were halted and nothing moved after that
            con.say(f"STOPPED: {e}")
            code = 2
        hand_off_slab(con, hw.vacuum, r)  # a slab still on the cup: the pump holds it until you take it
    finally:
        hw.close()
    return code


class _SimClock:
    """Simulated time for --sim: each reading advances it by one poll interval."""

    def __init__(self, step: float):
        self.t, self.step = 0.0, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


if __name__ == "__main__":
    raise SystemExit(main())
