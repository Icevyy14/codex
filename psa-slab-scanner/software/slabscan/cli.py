"""Command line: ``python -m slabscan <command>`` (run it from the software/ folder).

  selftest [-i] [--motion]        check every part (GPIO, vacuum, cameras, controller, beam gate)
  home                            home X and Z
  jog [--no-rods]                 move the head by hand (typed moves or arrow keys)
  calibrate z                     probe the bare pad of pocket 0 -> pad_trigger_c
  calibrate x [--no-rods]         centre the awl on pocket 0 and pocket 12 -> offset_x + scale check
  focus head|station [--save]     sharpness + decode score (station: LensPosition sweep)
  mark [--start N]                walk the awl over every pocket for the drill template
  run [--name NAME] [--front-photo always|fallback] [--yes]
  resume BATCH_DIR [--accept-heights]
  sim [--slabs N]                 full simulated batch, no hardware
  web [--port 8080]               phone page: start/stop/resume, progress, downloads

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
from .ops import CalError, Console, calibrate_x, calibrate_z, focus, mark, mark_order, selftest
from .results import BatchWriter
from .runner import Runner, Stop

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = SOFTWARE_DIR / "config" / "machine.toml"

# Per-frame / per-event times the simulator does not model (used only for the time estimate of `sim`).
T_HEAD_FRAME = 0.25  # [Guessing] USB UVC 8 MP MJPEG frame incl. dropped stale buffers
T_STATION_FRAME = 0.35  # [Guessing] Camera Module 3 full-resolution still from a running stream
T_SEAL = 0.15  # [Guessing] cup reaching the seal threshold


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


def summary_lines(summary: dict, batch_dir: Path) -> list[str]:
    counts = ", ".join(f"{k} {v}" for k, v in sorted(summary.get("status_counts", {}).items()))
    out = [f"batch {summary['batch_id']}: {summary['slabs_visited']} slabs  ({counts or 'none'})"]
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


def execute_batch(cfg: Config, hw, writer: BatchWriter, con: Console, resume: bool = False, accept_heights: bool = False,
                  stop_flag: threading.Event | None = None, on_runner=None) -> tuple[int, dict | None, str]:
    """Run or resume one batch. Returns (exit code, summary or None, message). Writes stop.json on a halt.
    ``on_runner(runner)`` is called before the run starts (the web page reads live progress from it)."""
    stop_flag = stop_flag or threading.Event()
    runner = Runner(cfg, hw.motion, hw.vacuum, hw.lights, hw.head_cam, hw.station_cam, writer, lid=hw.lid, gate=hw.gate, log=con.say, should_stop=stop_flag.is_set)
    if on_runner is not None:
        on_runner(runner)
    try:
        summary = runner.resume(accept_heights) if resume else runner.run()
        clear_stop(writer.dir)
        return 0, summary, ""
    except Stop as e:
        write_stop(writer.dir, str(e))
        return 2, None, str(e)
    except KeyboardInterrupt:
        msg = "Interrupted (Ctrl-C twice) in the middle of a move. A slab may be in the cup: check the head before touching the bed. Then resume."
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
        hw = sim_hardware(cfg, slabs=args.sim_slabs, stacks=stacks)
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
    cfg, _ = load_config(args)
    hw = _hw(args, cfg, ()) if args.sim else None
    return selftest(cfg, con, hw=hw, sim=args.sim, interactive=args.interactive, do_motion=args.motion, out_dir=Path(args.images))


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


def _sigint_stop(con, stop_flag):
    def handler(sig, frame):
        if stop_flag.is_set():
            raise KeyboardInterrupt
        stop_flag.set()
        con.say("Stopping after this slab (nothing will be left in the cup). Ctrl-C again = stop NOW.")

    if threading.current_thread() is threading.main_thread():
        return signal.signal(signal.SIGINT, handler)
    return None


def cmd_run(args, con):
    cfg, cal = load_config(args)
    if args.front_photo:
        cfg = dataclasses.replace(cfg, front_photo=args.front_photo)
    if not args.sim and not is_calibrated(cal) and not args.uncalibrated:
        con.say(f"{cal} has no pad_trigger_c / offset_x yet. Run `calibrate z` and `calibrate x` first (or --uncalibrated if you really mean it).")
        return 1
    if not args.yes and not args.sim:
        con.say("Before starting: slabs FACE-DOWN, label end toward you, in pockets 1-11, none above the MAX line.\n"
                "Pocket 0 and pocket 12 empty. Cup wiped. Hands out, roof on.")
        if not con.confirm("Start the run?"):
            return 1
    hw = _hw(args, cfg, ("motion", "vacuum", "lights", "head_cam", "station_cam", "gate", "lid"))
    writer = BatchWriter(Path(cfg.out_dir), new_batch_id(args.name, "sim-" if args.sim else ""))
    (writer.dir / "run.json").write_text(json.dumps({"name": args.name, "front_photo": cfg.front_photo, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "sim": bool(args.sim)}, indent=2))
    con.say(f"batch {writer.batch_id} -> {writer.dir}   (Ctrl-C = stop after the current slab)")
    stop_flag = threading.Event()
    old = _sigint_stop(con, stop_flag)
    try:
        code, summary, msg = execute_batch(cfg, hw, writer, con, stop_flag=stop_flag)
    finally:
        if old is not None:
            signal.signal(signal.SIGINT, old)
        hw.close()
    return _report(con, code, summary, msg, writer)


def _report(con, code, summary, msg, writer) -> int:
    if code == 0:
        for ln in summary_lines(summary, writer.dir):
            con.say(ln)
    else:
        con.say(f"STOPPED: {msg}")
        con.say(f"resume with:  python -m slabscan resume {writer.dir}")
    return code


def cmd_resume(args, con):
    cfg, _ = load_config(args)
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
    if (bdir / "stop.json").exists():
        con.say("last stop: " + json.loads((bdir / "stop.json").read_text()).get("message", ""))
    hw = _hw(args, cfg, ("motion", "vacuum", "lights", "head_cam", "station_cam", "gate", "lid"))
    writer = BatchWriter.reopen(bdir)
    con.say(f"resuming {writer.batch_id}: {len(writer.rows)} slabs already done")
    stop_flag = threading.Event()
    old = _sigint_stop(con, stop_flag)
    try:
        code, summary, msg = execute_batch(cfg, hw, writer, con, resume=True, accept_heights=args.accept_heights, stop_flag=stop_flag)
    finally:
        if old is not None:
            signal.signal(signal.SIGINT, old)
        hw.close()
    return _report(con, code, summary, msg, writer)


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


def cmd_sim(args, con):
    from .factory import sim_hardware, sim_stacks

    cfg, _ = load_config(args)
    if args.front_photo:
        cfg = dataclasses.replace(cfg, front_photo=args.front_photo)
    eras = tuple(float(x) for x in args.eras.split(","))
    stacks = sim_stacks(cfg, args.slabs, seed=args.seed, eras=eras, clingy_rate=args.clingy_rate, thick_rate=args.thick_rate)
    hw = sim_hardware(cfg, stacks=stacks)
    hw.head_cam, hw.station_cam = _Count(hw.head_cam), _Count(hw.station_cam)
    hw.lights, hw.vacuum = _CountLights(hw.lights), _CountVac(hw.vacuum)
    writer = BatchWriter(Path(cfg.out_dir), new_batch_id(args.name, "sim-"))
    quiet = Console(out=lambda *_: None) if args.quiet else con
    survey = {}

    def watch(r):  # note the motion time spent before the first slab moves (homing + survey)
        inner = r.transfer

        def transfer(src, dst):
            survey.setdefault("motion_s", hw.motion.move_time_s)
            return inner(src, dst)

        r.transfer = transfer

    t0 = time.monotonic()
    code, summary, msg = execute_batch(cfg, hw, writer, quiet, on_runner=watch)
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
    return 0


def cmd_web(args, con):
    from .web import RealProvider, SimProvider, create_app, lan_address

    cfg, _ = load_config(args)
    provider = SimProvider(cfg, slabs=args.sim_slabs) if args.sim else RealProvider(cfg)
    app = create_app(cfg, provider)
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
    p.add_argument("--start", type=int, default=0, help="skip pockets below this one")
    p.add_argument("--only", help="comma-separated pockets, e.g. 0,12 (to continue after a break)")
    p.add_argument("--dry-run", action="store_true", help="only print the positions")
    p.set_defaults(fn=cmd_mark)

    p = sub.add_parser("run", help="run a batch")
    p.add_argument("--name", help="added to the batch folder name")
    p.add_argument("--front-photo", choices=["always", "fallback"], help="always = photograph every front (+~3 s/slab)")
    p.add_argument("--yes", action="store_true", help="no start question (unattended start)")
    p.add_argument("--uncalibrated", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("resume", help="continue a stopped batch")
    p.add_argument("batch_dir")
    p.add_argument("--accept-heights", action="store_true", help="take the re-surveyed stack heights even if they changed")
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
    p.set_defaults(fn=cmd_sim)

    p = sub.add_parser("web", help="phone-friendly web page")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--host", default="0.0.0.0")
    p.set_defaults(fn=cmd_web)
    return ap


def main(argv=None, console: Console | None = None) -> int:
    args = build_parser().parse_args(argv)
    con = console or Console()
    try:
        return int(args.fn(args, con) or 0)
    except BrokenPipeError:  # output piped into `head`
        return 0
    except (OSError, RuntimeError, ValueError) as e:
        con.say(f"error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
