"""Command line: ``python -m slabscan <command>`` (run it from the software/ folder).

  selftest [-i] [--motion]        check every part (GPIO, vacuum, cameras, controller, beam gate)
  home                            home X and Z
  jog [--no-rods]                 move the head by hand (typed moves or arrow keys)
  calibrate z                     probe the bare pad of pocket 0 -> pad_trigger_c
  calibrate x [--no-rods]         centre the awl on pocket 0 and pocket 12 -> offset_x + scale check
  focus head|station [--save]     sharpness + decode score (station: LensPosition sweep)
  mark [--start N | --only N,M]   walk the awl over every pocket for the drill template
  run [--name NAME] [--front-photo always|fallback] [--all-face-down] [--yes]
  resume BATCH_DIR [--accept-heights] [--face-down-ok] [--yes]
  sim [--slabs N] [--face-down-check]   full simulated batch, no hardware
  refs [--drop CERT | --drop-operator]  list (or delete) the learned face-down check's card-back references
  web [--port 8080]               phone page: start/stop/resume, progress, downloads
  phase0 [--sim N] [--out DIR]    Phase 0 camera read-rate test (tools/phase0.py; its own options)

Add --sim to any hardware command to run it against the simulator.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import signal
import sys
import threading
import time
import tomllib
from pathlib import Path

from .config import Config, from_layout, load
from .facedown import FILE_NAME as CARD_BACKS_FILE
from .facedown import CardBackRefs, threshold_tag
from .motion import ControllerLost, MotionError
from .ops import CalError, Console, calibrate_x, calibrate_z, focus, mark, mark_order, selftest
from .results import BatchWriter
from .runner import FACE_DOWN_OK_REFUSED, HardStop, Runner, Stop, last_face_down_stop, read_journal

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = SOFTWARE_DIR / "config" / "machine.toml"

# Per-frame / per-event times the simulator does not model (used only for the time estimate of `sim`).
T_HEAD_FRAME = 0.25  # [Guessing] USB UVC 8 MP MJPEG frame incl. dropped stale buffers
T_STATION_FRAME = 0.35  # [Guessing] Camera Module 3 full-resolution still from a running stream
T_SEAL = 0.15  # [Guessing] cup reaching the seal threshold
# Learned face-down threshold the simulator uses when none is measured, picked on the simulator's own synthetic card
# backs with the "open" head: `phase0 --sim 30 --face-up 5 --sim-head open` gave lowest back 0.88, highest face-up 0.24
# (midpoint 0.56); 15 face-up slabs reached 0.38. Japanese backs against English references: up to 0.49. Never for a machine.
SIM_FACE_DOWN_THRESHOLD = 0.6


# ---------------------------------------------------------------------- config / batches
def load_config(args) -> tuple[Config, Path]:
    mpath = Path(args.config) if args.config else DEFAULT_CONFIG
    cal = Path(args.calibration) if args.calibration else mpath.parent / "calibration.toml"
    if mpath.exists():
        cfg = load(mpath, cal)
    elif getattr(args, "sim", False) or args.cmd == "sim":
        cfg = from_layout()
    else:
        raise SystemExit(f"{mpath} not found. Generate it first:  python -m tools.gen_config")
    if getattr(args, "out", None):
        cfg = dataclasses.replace(cfg, out_dir=str(args.out))
    return cfg, cal


def is_calibrated(cal: Path) -> bool:
    if not cal.exists():
        return False
    raw = tomllib.loads(cal.read_text())
    return "pad_trigger_c" in raw and "offset_x" in raw


def new_batch_id(name: str | None = None, prefix: str = "") -> str:
    bid = prefix + time.strftime("%Y%m%d-%H%M%S")
    if name:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")[:40]
        if slug:
            bid += "-" + slug
    return bid


def write_stop(batch_dir: Path, message: str, kind: str = "stop") -> None:
    (Path(batch_dir) / "stop.json").write_text(json.dumps({"kind": kind, "message": message, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2))


def clear_stop(batch_dir: Path) -> None:
    p = Path(batch_dir) / "stop.json"
    if p.exists():
        p.unlink()


def run_options(batch_dir: Path) -> dict:
    p = Path(batch_dir) / "run.json"
    return json.loads(p.read_text()) if p.exists() else {}


def face_down_line(fd: dict) -> str:
    """How the batch's slabs were proven face-down (summary.json face_down)."""
    c = fd.get("counts") or {}
    parts = [f"{c[k]} {label}" for k, label in (("qr", "by back QR"), ("learned", "by the learned card-back match"),
                                                  ("operator", "confirmed by you"), ("off", "not checked (check off)")) if c.get(k)]
    line = "face-down: " + (", ".join(parts) if parts else "no slabs")
    learned = fd.get("learned") or []
    if learned:
        low = min(learned, key=lambda a: a["face_down"])
        line += f"; lowest learned score {low['face_down']} at #{low['position']} - check the back photos of the learned ones in report.html"
    return line


def summary_lines(summary: dict, batch_dir: Path) -> list[str]:
    counts = ", ".join(f"{k} {v}" for k, v in sorted(summary.get("status_counts", {}).items()))
    out = [f"batch {summary['batch_id']}: {summary['slabs_visited']} slabs  ({counts or 'none'})"]
    if summary.get("face_down"):
        out.append(face_down_line(summary["face_down"]))
    dups = summary.get("duplicates") or {}
    out.append("duplicates: " + (", ".join(f"{c} at #{'/#'.join(map(str, p))}" for c, p in dups.items()) if dups else "none"))
    cc = summary.get("count_check") or {}
    bad = {k: v for k, v in cc.items() if not v["ok"]}
    out.append("count check: " + ("every stack matches its surveyed height" if not bad else
               "; ".join(f"pocket {k}: ~{v['estimated']} by height, {v['counted']} counted" for k, v in bad.items()) + "  <- check these stacks by hand"))
    for a in summary.get("needs_attention", [])[:30]:
        out.append(f"  #{a['position']:3d}  pocket {a['out_pocket']} position {a['out_index']} from the bottom  {a['status']:12} {a.get('cert') or '-':>10}  {a.get('note', '')}")
    if len(summary.get("needs_attention", [])) > 30:
        out.append(f"  ... {len(summary['needs_attention']) - 30} more in report.html")
    if summary.get("mean_cycle_s"):
        out.append(f"mean cycle {summary['mean_cycle_s']} s/slab")
    out.append(f"files: {batch_dir}/certs.csv  certs.txt  report.html  summary.json")
    out.append("unload: each stack now sits one pocket to the LEFT (stack 1 is in pocket 0 ...), order reversed; pocket 12 holds the slabs to check by hand")
    return out


CALIBRATION_MISSING = ("{cal} has no pad_trigger_c / offset_x yet. Run `calibrate z` and `calibrate x` first: an uncalibrated X offset "
                       "larger than the 1.85 mm pocket play lowers held slabs onto the rods.")


def card_backs_path(cal_path: Path | None) -> Path | None:
    """The learned face-down check's references live next to calibration.toml (config/card_backs.npz)."""
    return None if cal_path is None else Path(cal_path).parent / CARD_BACKS_FILE


def execute_batch(cfg: Config, hw, writer: BatchWriter, con: Console, resume: bool = False, accept_heights: bool = False,
                  stop_flag: threading.Event | None = None, on_runner=None, cal_path: Path | None = None,
                  face_down_ok: bool = False, refs_path: Path | None = None, sim_operator=None) -> tuple[int, dict | None, str]:
    """Run or resume one batch. Returns (exit code, summary or None, message). Writes stop.json on a halt.
    ``on_runner(runner)`` is called before the run starts (the web page reads live progress from it).
    ``cal_path``: refuse to move unless that calibration.toml has calibrate z and x in it (every real
    entry point passes it: CLI run/resume and the web page). ``refs_path``: the card-back references of the
    learned face-down check (config/card_backs.npz on the machine; None = kept in memory, as in the simulator).
    ``sim_operator``: simulator only, see Runner."""
    if cal_path is not None and not is_calibrated(cal_path):
        msg = CALIBRATION_MISSING.format(cal=cal_path)
        write_stop(writer.dir, msg, "error")
        return 1, None, msg
    stop_flag = stop_flag or threading.Event()
    refs = CardBackRefs(refs_path, cfg.face_down_window_mm)
    runner = Runner(cfg, hw.motion, hw.vacuum, hw.lights, hw.head_cam, hw.station_cam, writer, lid=hw.lid, gate=hw.gate, log=con.say, should_stop=stop_flag.is_set,
                    refs=refs, sim_operator=sim_operator)
    if on_runner is not None:
        on_runner(runner)
    try:
        summary = runner.resume(accept_heights, face_down_ok=face_down_ok) if resume else runner.run()
        clear_stop(writer.dir)
        return 0, summary, ""
    except HardStop as e:
        write_stop(writer.dir, str(e), "interrupt")
        return 130, None, str(e)
    except Stop as e:
        write_stop(writer.dir, str(e))
        return 2, None, str(e)
    except KeyboardInterrupt:
        msg = ("Interrupted (Ctrl-C) during the stop itself. The head may have stopped anywhere and a slab may be in the cup: check the head "
               "before touching the bed. Then resume (it homes first).")
        write_stop(writer.dir, msg, "interrupt")
        return 130, None, msg
    except Exception as e:  # noqa: BLE001 - controller / camera failure: record it for resume and the web page
        msg = f"{type(e).__name__}: {e}. The machine stopped without parking: check the head (a slab may be in the cup), then resume."
        write_stop(writer.dir, msg, "error")
        return 1, None, msg


# ---------------------------------------------------------------------- hardware
def _hw(args, cfg: Config, parts, stacks=None):
    from .factory import open_hardware, sim_hardware

    if args.sim:
        hw = sim_hardware(cfg, slabs=args.sim_slabs, stacks=stacks, head=getattr(args, "sim_head", None) or "cad")
        if args.sim_x_offset is not None:
            hw.motion.x_offset = args.sim_x_offset
        if args.sim_z_offset is not None:
            hw.motion.z_offset = args.sim_z_offset
        return hw
    return open_hardware(cfg, parts=parts)


def _one_slab_on_pocket0(cfg: Config):
    from .simworld import SimSlab

    return {0: [SimSlab("148069831", 6.6)], **{p.index: [] for p in cfg.sources}}


# ---------------------------------------------------------------------- commands
def cmd_selftest(args, con):
    cfg, cal = load_config(args)
    hw = _hw(args, cfg, ()) if args.sim else None
    return selftest(cfg, con, hw=hw, sim=args.sim, interactive=args.interactive, do_motion=args.motion, out_dir=Path(args.images), cal_path=cal)


def cmd_home(args, con):
    cfg, _ = load_config(args)
    hw = _hw(args, cfg, ("motion",))
    try:
        hw.motion.home()
        x, z = hw.motion.position()
        con.say(f"homed: X {x:.3f}  Z {z:.3f}")
        return 0
    finally:
        hw.close()


def cmd_jog(args, con):
    from .ops import Jogger

    cfg, _ = load_config(args)
    hw = _hw(args, cfg, ("motion",))
    try:
        hw.motion.home()
        jog = Jogger(cfg, hw.motion, con, rods=not args.no_rods)
        con.say("type 'help' for commands, 'keys' for arrow keys, 'q' to quit" + ("" if jog.rods else "   (NO-RODS mode: low sideways moves allowed)"))
        while True:
            r = jog.interact()
            if r is None:
                return 0
            con.say(f"position: X {r[0]:.3f}  Z {r[1]:.3f}")
    finally:
        hw.close()


def cmd_calibrate(args, con):
    cfg, cal = load_config(args)
    parts = ("motion", "vacuum") if args.axis == "z" else ("motion",)
    hw = _hw(args, cfg, parts)
    try:
        if args.axis == "z":
            calibrate_z(cfg, hw, con, cal, yes=args.yes, extra_depth=args.extra_depth)
        else:
            calibrate_x(cfg, hw, con, cal, rods=not args.no_rods)
        return 0
    except CalError as e:
        con.say(f"calibrate {args.axis}: {e}")
        return 1
    finally:
        hw.close()


def cmd_focus(args, con):
    from .factory import SimLensCamera

    cfg, cal = load_config(args)
    cam_part = "head_cam" if args.camera == "head" else "station_cam"
    parts = ("lights", cam_part) if args.no_motion else ("motion", "vacuum", "lights", cam_part)
    hw = _hw(args, cfg, parts, stacks=_one_slab_on_pocket0(cfg) if args.sim else None)
    if args.sim and args.camera == "station":
        hw.station_cam = SimLensCamera(hw.station_cam, lens_position=float(cfg.cam_station.get("lens_position") or 7.1))
    try:
        res = focus(cfg, hw, con, args.camera, Path(args.images), motion=not args.no_motion, frames=args.frames, save=args.save, cal_path=cal,
                    lens_from=args.lens_from, lens_to=args.lens_to, lens_step=args.lens_step)
        con.say(json.dumps({k: v for k, v in res.items() if k != "sweep"}, default=str))
        return 0
    except (CalError, Stop) as e:
        con.say(f"focus {args.camera}: {e}")
        return 1
    finally:
        hw.close()


def cmd_mark(args, con):
    cfg, _ = load_config(args)
    only = [int(x) for x in args.only.split(",")] if args.only else None
    if args.dry_run or args.sim:
        con.say("order pocket cell   bed X   machine X   left dimple  right dimple")
        for n, r in enumerate(mark_order(cfg, args.start, only), 1):
            reach = lambda k: f"{r[k]:12.2f}" if k in r["reach"] else f"{'(no reach)':>12}"  # noqa: E731
            con.say(f"{n:5d} {r['pocket']:6d} {r['cell']:4d} {r['bed_x']:7.1f} {r['centre']:11.2f} {reach('left')} {reach('right'):>13}")
        con.say("(dry run - nothing moved; the station cell needs no holes of its own; end pockets come last: pins in the neighbour's holes set them)")
        return 0
    hw = _hw(args, cfg, ("motion",))
    try:
        mark(cfg, hw, con, start=args.start, only=only)
        return 0
    except CalError as e:
        con.say(f"mark: {e}")
        return 1
    finally:
        hw.close()


def _hold_until_interrupt() -> None:
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass


def hand_off_slab(con, vac, runner, wait=None) -> None:
    """A stop left a slab (or maybe one) on the cup. Keep the pump holding it while this process runs, and
    vent only when the operator says they hold it. Never just exit: hw.close() shuts the valves and the
    slab then hangs on the closed cup line only until it leaks off (seconds to tens of seconds)."""
    where = getattr(runner, "slab_on_cup", None) if runner is not None else None
    if not where or vac is None:
        return
    if runner.freeze == "vent_failed":
        con.say("THE VENT FAILED: a slab rests on the stack under the cup, still sealed to it, with both valves shut. It is supported, so it "
                "cannot fall. Hold it and pull the vacuum tube off the cup fitting (or unscrew the cup) to free it; never slide it sideways.")
        return
    try:
        vac.hold()
    except Exception:  # noqa: BLE001
        pass
    con.say(f"A SLAB IS (OR MAY BE) ON THE CUP - from {where}. The pump keeps holding it while this program runs: do not close it yet.")
    while True:
        a = con.ask("Hold the slab with one hand, then type 'vent' and press Enter (the cup lets go): ").strip().lower()
        if a == "vent":
            vac.release()
            runner.holding, runner.held_from = False, None
            if runner.freeze == "hold":
                runner.freeze = None
            con.say("Vented. Put the slab face-down on top of the pocket it came from; it is read again on resume.")
            return
        if a == "q":  # 'q' or no keyboard (end of input)
            con.say("No answer: the pump keeps holding the slab until you press Ctrl-C here. Hold the slab first - after Ctrl-C the valves "
                    "shut and it hangs on the closed line for a short while only.")
            (wait or _hold_until_interrupt)()
            return
        con.say("Type vent (or press Ctrl-C to quit with the valves shut).")


def _sigint_stop(con, stop_flag):
    def handler(sig, frame):
        if stop_flag.is_set():
            raise KeyboardInterrupt
        stop_flag.set()
        con.say("Stopping after this slab (nothing will be left in the cup). Ctrl-C again = halt the motors NOW, where they are "
                "(nothing moves after that; a slab in the cup stays on it, held by the pump, and you take it off).")

    if threading.current_thread() is threading.main_thread():
        return signal.signal(signal.SIGINT, handler)
    return None


def cmd_run(args, con):
    cfg, cal = load_config(args)
    if args.front_photo:
        cfg = dataclasses.replace(cfg, front_photo=args.front_photo)
    if args.all_face_down:
        cfg = dataclasses.replace(cfg, face_down_check="off")
    if not args.sim and not is_calibrated(cal) and not args.uncalibrated:
        con.say(f"{cal} has no pad_trigger_c / offset_x yet. Run `calibrate z` and `calibrate x` first (or --uncalibrated if you really mean it).")
        return 1
    if not args.yes and not args.sim:
        con.say("Before starting: slabs FACE-DOWN, label end toward you, in pockets 1-11, none above the MAX line.\n"
                "Pocket 0 and pocket 12 empty. Cup wiped. Hands out (light roof on, if fitted).")
        if args.all_face_down:
            con.say("--all-face-down: slabs the face-down check cannot confirm (no back QR, no match with a known card back) are picked\n"
                    "without stopping. A slab loaded face-up would get the cup on its front, so check every stack before you walk away.")
        if not con.confirm("Start the run?"):
            return 1
    hw = _hw(args, cfg, ("motion", "vacuum", "lights", "head_cam", "station_cam", "gate", "lid"))
    writer = BatchWriter(Path(cfg.out_dir), new_batch_id(args.name, "sim-" if args.sim else ""))
    (writer.dir / "run.json").write_text(json.dumps({"name": args.name, "front_photo": cfg.front_photo, "face_down_check": cfg.face_down_check,
                                                     "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "sim": bool(args.sim)}, indent=2))
    con.say(f"batch {writer.batch_id} -> {writer.dir}   (Ctrl-C = stop after the current slab)")
    return _execute_and_hand_off(cfg, hw, writer, con, cal_path=None if (args.sim or args.uncalibrated) else cal,
                                 refs_path=None if args.sim else card_backs_path(cal))


def _execute_and_hand_off(cfg, hw, writer, con, **kw) -> int:
    """execute_batch with Ctrl-C handling; then, if the stop left a slab on the cup, the operator takes it
    before the hardware is closed."""
    stop_flag = threading.Event()
    runners: list = []
    try:
        old = _sigint_stop(con, stop_flag)
        try:
            code, summary, msg = execute_batch(cfg, hw, writer, con, stop_flag=stop_flag, on_runner=runners.append, **kw)
        finally:
            if old is not None:
                signal.signal(signal.SIGINT, old)
        _report(con, code, summary, msg, writer)
        if runners:
            hand_off_slab(con, hw.vacuum, runners[0])
    finally:
        hw.close()
    return code


def _report(con, code, summary, msg, writer) -> int:
    if code == 0:
        for ln in summary_lines(summary, writer.dir):
            con.say(ln)
    else:
        con.say(f"STOPPED: {msg}")
        con.say(f"resume with:  python -m slabscan resume {writer.dir}")
    return code


def cmd_resume(args, con):
    cfg, cal = load_config(args)
    bdir = Path(args.batch_dir)
    if not (bdir / "journal.jsonl").exists() and not (bdir / "certs.csv").exists():
        con.say(f"{bdir} is not a batch folder (no journal.jsonl)")
        return 1
    if args.sim:
        con.say("resume needs the real machine: the simulator does not keep its slabs between commands. Try stop/resume in `web --sim`.")
        return 1
    opts = run_options(bdir)
    if opts.get("front_photo"):
        cfg = dataclasses.replace(cfg, front_photo=opts["front_photo"])
    if opts.get("face_down_check") in ("learned", "stop", "off"):
        cfg = dataclasses.replace(cfg, face_down_check=opts["face_down_check"])  # a batch keeps the choice it was started with
    if (bdir / "stop.json").exists():
        con.say("last stop: " + json.loads((bdir / "stop.json").read_text()).get("message", ""))
    fd_pocket = last_face_down_stop(read_journal(bdir / "journal.jsonl"))
    if args.face_down_ok and fd_pocket is None:
        con.say(FACE_DOWN_OK_REFUSED)
        return 2
    if not is_calibrated(cal):
        con.say(CALIBRATION_MISSING.format(cal=cal))
        return 1
    if not args.yes:
        con.say("Before resuming: hands out of the machine (light roof on, if fitted). Any slab you took off the cup is back face-down on top of\n"
                "the pocket it came from." + (f"\n--face-down-ok: you checked that the top slab of pocket {fd_pocket}, where the face-down check stopped,\n"
                                               "IS face-down. It confirms that one slab only." if args.face_down_ok else ""))
        if not con.confirm("Resume the run?"):
            return 1
    hw = _hw(args, cfg, ("motion", "vacuum", "lights", "head_cam", "station_cam", "gate", "lid"))
    writer = BatchWriter.reopen(bdir)
    con.say(f"resuming {writer.batch_id}: {len(writer.rows)} slabs already done")
    return _execute_and_hand_off(cfg, hw, writer, con, resume=True, accept_heights=args.accept_heights, cal_path=cal, face_down_ok=args.face_down_ok,
                                 refs_path=card_backs_path(cal))


class _Count:
    """Counts frames / switch-ons for the time estimate."""

    def __init__(self, inner):
        self.inner = inner
        self.n = 0

    def capture(self):
        self.n += 1
        return self.inner.capture()

    def close(self):
        pass

    def __getattr__(self, name):  # everything else (e.g. the camera's view_half_mm, used for the crop) from the wrapped part
        return getattr(self.inner, name)


class _CountLights:
    def __init__(self, inner):
        self.inner = inner
        self.ons = 0

    def head(self, on):
        self.ons += bool(on)
        self.inner.head(on)

    def station(self, on):
        self.ons += bool(on)
        self.inner.station(on)

    def __getattr__(self, name):  # everything else (e.g. the camera's view_half_mm, used for the crop) from the wrapped part
        return getattr(self.inner, name)


class _CountVac:
    def __init__(self, inner):
        self.inner = inner
        self.releases = 0

    def hold(self):
        self.inner.hold()

    def release(self):
        self.releases += 1
        self.inner.release()

    def kpa(self):
        return self.inner.kpa()

    def close(self):
        self.inner.close()

    def __getattr__(self, name):  # everything else (e.g. the camera's view_half_mm, used for the crop) from the wrapped part
        return getattr(self.inner, name)


def cmd_sim(args, con):
    from .factory import sim_hardware, sim_stacks

    cfg, _ = load_config(args)
    if args.front_photo:
        cfg = dataclasses.replace(cfg, front_photo=args.front_photo)
    eras = tuple(float(x) for x in args.eras.split(","))
    stacks = sim_stacks(cfg, args.slabs, seed=args.seed, eras=eras, clingy_rate=args.clingy_rate, thick_rate=args.thick_rate, jp_rate=args.jp_rate)
    unconfirmable = sum(1 for v in stacks.values() for sl in v if sl.era != "2017+" or sl.grader != "PSA")
    n_slabs = sum(len(v) for v in stacks.values())
    if cfg.face_down_check != "off" and not args.face_down_check:
        # Every simulated slab is face-down. On the machine, each slab the check cannot confirm stops the run until you
        # confirm it (resume --face-down-ok): here that is reported instead, so the timing is for a full run.
        cfg = dataclasses.replace(cfg, face_down_check="off")
        con.say(f"(sim: face-down check off. On the machine {unconfirmable} of these {n_slabs} slabs have no PSA back-label QR. With "
                "face_down_check = \"stop\" each one stops the run until you confirm it is face-down (resume --face-down-ok). With \"learned\" "
                "(the default) they are first compared with the card backs of QR-confirmed slabs: `sim --face-down-check` shows how many "
                "would still stop.)")
    if args.face_down_check and cfg.face_down_check == "learned" and cfg.face_down_threshold is None:
        cfg = dataclasses.replace(cfg, face_down_threshold=SIM_FACE_DOWN_THRESHOLD, face_down_threshold_sig=threshold_tag(cfg.face_down_window_mm))
        con.say(f"(sim: face_down_threshold {SIM_FACE_DOWN_THRESHOLD}, picked on the simulator's synthetic card backs; on the machine Phase 0 "
                "measures it on yours. Head parts in view: " + ("today's CAD head" if args.sim_head == "cad" else f"'{args.sim_head}' (hypothetical)") + ")")
    hw = sim_hardware(cfg, stacks=stacks, head=args.sim_head)

    def look(src: int) -> bool:  # the simulated operator looks at the slab the check stopped on
        return hw.world.stacks[src][-1].face_down

    sim_operator = look if args.face_down_check and cfg.face_down_check != "off" else None
    hw.head_cam, hw.station_cam = _Count(hw.head_cam), _Count(hw.station_cam)
    hw.lights, hw.vacuum = _CountLights(hw.lights), _CountVac(hw.vacuum)
    writer = BatchWriter(Path(cfg.out_dir), new_batch_id(args.name, "sim-"))
    quiet = Console(out=lambda *_: None) if args.quiet else con
    survey = {}

    def watch(r):  # note the motion time spent before the first slab moves (homing + survey)
        survey["runner"] = r
        inner = r.transfer

        def transfer(src, dst):
            survey.setdefault("motion_s", hw.motion.move_time_s)
            return inner(src, dst)

        r.transfer = transfer

    t0 = time.monotonic()
    code, summary, msg = execute_batch(cfg, hw, writer, quiet, on_runner=watch, sim_operator=sim_operator)
    wall = time.monotonic() - t0
    if code != 0:
        con.say(f"SIM STOPPED: {msg}")
        return code
    for ln in summary_lines(summary, writer.dir):
        con.say(ln)
    n = max(1, summary["slabs_visited"])
    motion_s = hw.motion.move_time_s
    survey_s = survey.get("motion_s", motion_s)
    survey_vents = len(cfg.pockets)  # the survey vents the open cup once per pocket
    other = (n * (cfg.peel_dwell_s + T_SEAL) + max(0, hw.vacuum.releases - survey_vents) * cfg.vent_s + hw.head_cam.n * T_HEAD_FRAME
             + hw.station_cam.n * T_STATION_FRAME + hw.lights.ons * cfg.light_settle_s)
    per_slab = (motion_s - survey_s + other) / n
    total = survey_s + survey_vents * cfg.vent_s + per_slab * n
    full = survey_s + survey_vents * cfg.vent_s + per_slab * cfg.capacity
    con.say(f"timing: homing + survey {survey_s:.0f} s once per batch, then {per_slab:.1f} s per slab "
            f"(motion from the trapezoid model + cameras/vacuum/lights) -> {total / 60:.1f} min for these {n} slabs, "
            f"about {full / 60:.0f} min for a full {cfg.capacity}-slab load"
            + ("" if n >= cfg.capacity * 0.8 else " (extrapolated: short stacks cost more per slab than full ones; `sim --slabs 330` gives the real number)"))
    con.say(f"        frames: head {hw.head_cam.n}, station {hw.station_cam.n}; per-frame times {T_HEAD_FRAME}/{T_STATION_FRAME} s and decode time on the Pi are guesses - Phase 0 measures them")
    con.say(f"        this simulation took {wall:.1f} s of wall time on this computer")
    if sim_operator is not None:
        stops = survey["runner"].face_down_stops
        con.say(f"face-down check ({cfg.face_down_check}): {stops} of {n_slabs} slabs stopped for you (the simulated operator confirmed each; "
                f"checking only the back QR, {unconfirmable} would have). On the machine every stop waits for you, and resume homes and "
                f"re-surveys first (~{survey_s + survey_vents * cfg.vent_s:.0f} s), so the time above is for an unbroken run.")
    return 0


def cmd_refs(args, con):
    """The learned face-down check's card-back references (config/card_backs.npz): list them, or delete some. Every
    operator-confirmed reference carries the batch, position, cert and back photo it came from (journal:
    face_down_reference), so a wrong confirmation can be found and removed on its own."""
    cfg, cal = load_config(args)
    path = card_backs_path(cal)
    refs = CardBackRefs(path, cfg.face_down_window_mm)
    if refs.note and not refs.note.startswith("loaded"):
        con.say(refs.note)
    if args.drop or args.drop_operator:
        n = refs.drop(cert=args.drop) if args.drop else refs.drop(source="operator")
        if n:
            refs.save()
        con.say(f"removed {n} reference(s) from {path}" + ("" if n else " (nothing matched)"))
    con.say(f"{path}: {refs.summary()}")
    for i, r in enumerate(refs.refs):
        m = r.meta
        where = f"batch {m.get('batch', '-')} #{m.get('position', '-')}" if "batch" in m else (f"phase0 slab {m['phase0_slab']}" if "phase0_slab" in m else "-")
        con.say(f"  {i + 1:3d}  prototype {r.proto}  {r.source:8}  {where:32}  cert {m.get('cert') or '-':>10}  {m.get('image_back', '')}")
    if refs.baseline is not None:
        con.say(f"  empty-pocket view: batch {refs.baseline_meta.get('batch', '-')}, pocket {refs.baseline_meta.get('pocket', '-')}")
    for p, n in sorted(refs.protos().items()):
        if not refs.usable(p):
            con.say(f"  prototype {p} ({n} operator confirmation(s)) is not matched yet: it needs more confirmations or a back-QR slab")
    return 0


def run_phase0(argv: list[str]) -> int:
    """``python -m slabscan phase0 ...`` = ``python -m tools.phase0 ...`` (the camera test before any motion parts)."""
    if str(SOFTWARE_DIR) not in sys.path:
        sys.path.insert(0, str(SOFTWARE_DIR))
    from tools import phase0

    return int(phase0.main(argv) or 0)


def cmd_phase0(args, con):
    # Only reached as `python -m slabscan --sim phase0`; `phase0 ...` with options is handed to tools.phase0 in main().
    return run_phase0(["--sim", "10"] if args.sim else [])


def cmd_web(args, con):
    from .web import RealProvider, SimProvider, create_app, lan_address

    cfg, cal = load_config(args)
    provider = SimProvider(cfg, slabs=args.sim_slabs) if args.sim else RealProvider(cfg)
    # the real page reloads machine.toml + calibration.toml on every start/resume (calibrate z/x while the
    # service runs must take effect) and refuses to move an uncalibrated machine
    app = create_app(cfg, provider, reload=None if args.sim else (lambda: load_config(args)[0]), cal_path=None if args.sim else cal)
    con.say(f"SlabRail web page on http://{lan_address()}:{args.port}/  (LAN only - there is no login; anyone on this network can start the machine)")
    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
    return 0


# ---------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    def common(parser, suppress: bool):
        d = (lambda v: argparse.SUPPRESS) if suppress else (lambda v: v)
        parser.add_argument("--config", default=d(None), help=f"machine.toml (default {DEFAULT_CONFIG})")
        parser.add_argument("--calibration", default=d(None), help="calibration.toml (default: next to machine.toml)")
        parser.add_argument("--out", default=d(None), help="batches folder (default from config: batches)")
        parser.add_argument("--sim", action="store_true", default=d(False), help="use the simulator instead of hardware")
        parser.add_argument("--sim-slabs", type=int, default=d(22), help="slabs in the simulated machine (--sim)")
        parser.add_argument("--sim-head", choices=["cad", "open", "none"], default=d("cad"),
                            help="head parts in the simulated head camera's view: cad = today's CAD head (its foot hides the card window), "
                                 "open = a hypothetical head that leaves face_down_window_mm clear")
        parser.add_argument("--sim-x-offset", type=float, default=d(None), help=argparse.SUPPRESS)
        parser.add_argument("--sim-z-offset", type=float, default=d(None), help=argparse.SUPPRESS)

    ap = argparse.ArgumentParser(prog="python -m slabscan", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common(ap, suppress=False)
    shared = argparse.ArgumentParser(add_help=False)
    common(shared, suppress=True)  # the same options are accepted after the command name too
    sub = ap.add_subparsers(dest="cmd", required=True)
    _add = sub.add_parser
    sub.add_parser = lambda *a, **k: _add(*a, parents=[shared], **k)  # type: ignore[method-assign]

    p = sub.add_parser("selftest", help="check GPIO, vacuum, cameras, controller, beam gate")
    p.add_argument("-i", "--interactive", action="store_true", help="also tests that need your hands (probe, seal, beam block, LED blink)")
    p.add_argument("--motion", action="store_true", help="also home the machine")
    p.add_argument("--images", default="selftest", help="folder for the test images")
    p.set_defaults(fn=cmd_selftest)

    p = sub.add_parser("home", help="home X and Z")
    p.set_defaults(fn=cmd_home)

    p = sub.add_parser("jog", help="move the head by hand")
    p.add_argument("--no-rods", action="store_true", help="the bed has no rods yet: allow sideways moves below the rod-top height")
    p.set_defaults(fn=cmd_jog)

    p = sub.add_parser("calibrate", help="calibrate z | calibrate x")
    p.add_argument("axis", choices=["z", "x"])
    p.add_argument("--no-rods", action="store_true", help="(x) the bed has no rods yet")
    p.add_argument("--yes", action="store_true", help="(z) skip the questions and the hand sensor check")
    p.add_argument("--extra-depth", type=float, default=12.0, help="(z) how far below the CAD pad height to keep probing (limited by the Z soft limit)")
    p.set_defaults(fn=cmd_calibrate)

    p = sub.add_parser("focus", help="focus head | focus station")
    p.add_argument("camera", choices=["head", "station"])
    p.add_argument("--no-motion", action="store_true", help="do not move: you hold a slab in view (Phase 0 jig)")
    p.add_argument("--frames", type=int, default=60, help="live frames (head / USB cameras)")
    p.add_argument("--save", action="store_true", help="(station) write the recommended LensPosition to calibration.toml")
    p.add_argument("--lens-from", type=float, default=None)
    p.add_argument("--lens-to", type=float, default=None)
    p.add_argument("--lens-step", type=float, default=0.25)
    p.add_argument("--images", default="focus", help="folder for the best frames")
    p.set_defaults(fn=cmd_focus)

    p = sub.add_parser("mark", help="walk the awl over every pocket for the drill template")
    p.add_argument("--start", type=int, default=None, help="continue from this pocket in the marking order (the 'order:' line; pockets 0 and 12 always come last)")
    p.add_argument("--only", help="comma-separated pockets, e.g. 0,12 (to continue after a break)")
    p.add_argument("--dry-run", action="store_true", help="only print the positions")
    p.set_defaults(fn=cmd_mark)

    p = sub.add_parser("run", help="run a batch")
    p.add_argument("--name", help="added to the batch folder name")
    p.add_argument("--front-photo", choices=["always", "fallback"], help="always = photograph every front (+~3 s/slab)")
    p.add_argument("--all-face-down", action="store_true",
                   help="you loaded every slab face-down: don't stop at slabs the face-down check cannot confirm "
                        "(no back QR, and no match with a known card back)")
    p.add_argument("--yes", action="store_true", help="no start question (unattended start)")
    p.add_argument("--uncalibrated", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("resume", help="continue a stopped batch")
    p.add_argument("batch_dir")
    p.add_argument("--accept-heights", action="store_true", help="take the re-surveyed stack heights even if they changed")
    p.add_argument("--face-down-ok", action="store_true",
                   help="you checked the top slab the face-down check stopped on: it IS face-down. Only after a face-down stop; it "
                        "confirms that one slab (once it is placed, its card back becomes a reference)")
    p.add_argument("--yes", action="store_true", help="no 'hands clear?' question")
    p.set_defaults(fn=cmd_resume)

    p = sub.add_parser("sim", help="full simulated batch, no hardware")
    p.add_argument("--slabs", type=int, default=22)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--eras", default="0.85,0.1,0.05", help="share of 2017+ / 2015-2017 / pre-2015 labels")
    p.add_argument("--clingy-rate", type=float, default=0.0, help="share of slabs that stick to the one above (double picks)")
    p.add_argument("--thick-rate", type=float, default=0.0, help="share of thick holders")
    p.add_argument("--front-photo", choices=["always", "fallback"])
    p.add_argument("--name")
    p.add_argument("--quiet", action="store_true", help="no per-slab lines")
    p.add_argument("--jp-rate", type=float, default=0.0, help="share of cards with the Japanese card back")
    p.add_argument("--face-down-check", action="store_true",
                   help="keep the face-down check on and count the slabs it would stop at (a simulated operator confirms each; "
                        "learned mode uses a simulator threshold unless one is set)")
    p.set_defaults(fn=cmd_sim)

    sub.add_parser("phase0", help="Phase 0 camera read-rate test, see `phase0 --help` (same as python -m tools.phase0)").set_defaults(fn=cmd_phase0)

    p = sub.add_parser("refs", help="list or delete the learned face-down check's card-back references")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--drop", metavar="CERT", help="delete the references taken from the slab with this cert")
    g.add_argument("--drop-operator", action="store_true", help="delete every reference you confirmed (keeps the back-QR ones)")
    p.set_defaults(fn=cmd_refs)

    p = sub.add_parser("web", help="phone-friendly web page")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--host", default="0.0.0.0")
    p.set_defaults(fn=cmd_web)
    return ap


def main(argv=None, console: Console | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["phase0"]:  # its options belong to tools/phase0.py (it has its own --sim N and --out)
        return run_phase0(argv[1:])
    args = build_parser().parse_args(argv)
    con = console or Console()
    try:
        return int(args.fn(args, con) or 0)
    except BrokenPipeError:  # output piped into `head`
        return 0
    except ControllerLost as e:
        con.say(f"STOP: {e}\nNothing will move until the controller is back and homed: twist the E-stop to release it, then `python -m slabscan home`.")
        return 1
    except (MotionError, Stop, CalError) as e:
        con.say(f"error: {e}")
        return 1
    except (OSError, RuntimeError, ValueError) as e:
        con.say(f"error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
