"""CLI commands against the simulator (no hardware)."""

import csv
import tomllib

import pytest

from slabscan.cli import main
from slabscan.config import from_layout
from slabscan.factory import sim_hardware
from slabscan.ops import Jogger, ScriptedConsole, mark_positions, sharpness


def _run(argv, answers=()):
    con = ScriptedConsole(list(answers))
    code = main(argv, console=con)
    return code, "\n".join(con.lines)


def test_sim_command_prints_summary_and_timing(tmp_path):
    code, out = _run(["sim", "--slabs", "4", "--quiet", "--out", str(tmp_path)])
    assert code == 0, out
    assert "4 slabs" in out and "(ok 4)" in out
    assert "timing: homing + survey" in out and "s per slab" in out
    batch = next(tmp_path.iterdir())
    rows = list(csv.DictReader((batch / "certs.csv").open()))
    assert len(rows) == 4 and all(r["status"] == "ok" for r in rows)
    assert (batch / "certs.txt").read_text().count("\n") == 4


def test_run_command_in_sim(tmp_path):
    code, out = _run(["--sim", "--sim-slabs", "2", "run", "--name", "test run", "--out", str(tmp_path)])
    assert code == 0, out
    batch = next(tmp_path.iterdir())
    assert batch.name.startswith("sim-") and batch.name.endswith("-test-run")
    assert (batch / "summary.json").exists() and not (batch / "stop.json").exists()


def test_selftest_sim_passes(tmp_path):
    code, out = _run(["--sim", "selftest", "--images", str(tmp_path)])
    assert code == 0, out
    assert "SELFTEST PASSED" in out


def test_calibrate_z_finds_the_pad(tmp_path):
    cal = tmp_path / "calibration.toml"
    code, out = _run(["--sim", "--sim-z-offset", "3.25", "--calibration", str(cal), "calibrate", "z", "--yes"])
    assert code == 0, out
    raw = tomllib.loads(cal.read_text())
    assert raw["pad_trigger_c"] == pytest.approx(3.25, abs=0.01)
    assert "c_max" not in raw  # full travel available in the sim


def test_calibrate_x_offset_and_low_move_refusal(tmp_path):
    cal = tmp_path / "calibration.toml"
    answers = [
        "x +2.5", "ok",  # pocket 0 coarse: the real centre is 2.5 mm right of nominal
        "z 10", "x +10", "ok",  # fine: lowered; a 10 mm sideways move down there is refused
        "ok",  # pocket 12 coarse: already predicted right
        "z 10", "ok",  # fine
    ]
    code, out = _run(["--sim", "--sim-x-offset", "2.5", "--calibration", str(cal), "calibrate", "x"], answers)
    assert code == 0, out
    assert "Refused" in out
    raw = tomllib.loads(cal.read_text())
    assert raw["offset_x"] == pytest.approx(2.5, abs=0.01)
    assert "error +0.000 mm" in out


def test_jog_rules():
    cfg = from_layout()
    hw = sim_hardware(cfg, slabs=0)
    hw.motion.home()
    con = ScriptedConsole([])
    jog = Jogger(cfg, hw.motion, con)
    jog.execute("x 300")  # between pockets 2 and 3, at the top
    jog.execute("z 50")
    assert "Refused" in con.lines[-2] and jog.z > 200  # no lowering between pockets
    jog.execute("p 3")
    jog.execute("z 20")
    assert jog.z == pytest.approx(20)
    x0 = jog.x
    jog.execute("x +8")
    assert jog.x == pytest.approx(x0)  # refused: would leave the pocket below the rod tops
    jog.execute("x +3")
    assert jog.x == pytest.approx(x0 + 3)
    jog.execute("z -30")  # probe move: stops on the bare pad instead of going through it
    assert jog.z == pytest.approx(0.0) and "contact" in con.lines[-2]
    jog.execute("z -1")
    assert "already reads TRIGGERED" in con.lines[-2]
    jog.execute("up")
    jog.execute("x +40")
    assert jog.x == pytest.approx(x0 + 43)


def test_focus_station_sweep_recommends_the_sharp_lens_position(tmp_path):
    cal = tmp_path / "calibration.toml"
    code, out = _run(["--sim", "--calibration", str(cal), "focus", "station", "--save", "--lens-from", "6", "--lens-to", "8.5", "--lens-step", "0.5", "--images", str(tmp_path)])
    assert code == 0, out
    lp = tomllib.loads(cal.read_text())["cam_station"]["lens_position"]
    assert abs(lp - 1 / 0.14) <= 0.5
    assert (tmp_path / "focus_station_best.jpg").exists()


def test_focus_head_live(tmp_path):
    code, out = _run(["--sim", "focus", "head", "--frames", "2", "--images", str(tmp_path)])
    assert code == 0, out
    assert "READ " in out and "back_qr:148069831" in out


def test_mark_dry_run_lists_every_pocket():
    code, out = _run(["--sim", "mark"])
    assert code == 0
    pos = mark_positions(from_layout())
    assert len(pos) == 13 and pos[7]["cell"] == 8  # the station (cell 7) is skipped
    assert all(p["right"] - p["left"] == pytest.approx(80.0) for p in pos)


def test_sharpness_prefers_focused_image():
    import cv2
    import numpy as np

    rng = np.random.default_rng(0)
    img = (rng.random((200, 300)) > 0.5).astype(np.uint8) * 255
    assert sharpness(img) > sharpness(cv2.GaussianBlur(img, (0, 0), 3))


def test_resume_refuses_sim(tmp_path):
    (tmp_path / "journal.jsonl").write_text("")
    code, out = _run(["--sim", "resume", str(tmp_path)])
    assert code == 1 and "real machine" in out


def test_mark_walks_every_pocket_on_a_bare_bed():
    """mark on a bed with no rods yet: the template lies everywhere at 1 mm. The awl may move sideways
    low, but never while it is down in a dimple, and never past the X travel."""
    from slabscan.factory import Hardware
    from slabscan.ops import mark
    from slabscan.simworld import Crash, SimMotion, SimWorld

    class BareBed(SimWorld):
        def surface_below(self):
            return 1.0

        def check_xy_path(self, x1, y1):
            lo, hi = self.cfg.x_travel
            if not lo <= x1 <= hi:
                raise Crash(f"X {x1} outside the soft limits")
            if self.lowest_point() < 1.0 + 5:
                raise Crash("sideways with the awl in the template")

        def check_z(self, z1):
            if z1 < self.z and z1 < self.surface_below() - 0.01:
                raise Crash("fast move into the template")

    cfg = from_layout()
    world = BareBed(cfg, stacks={})
    hw = Hardware(cfg=cfg, motion=SimMotion(world), world=world, sim=True)
    con = ScriptedConsole(["y"] + [""] * 80)
    done = mark(cfg, hw, con)
    assert sorted(done) == list(range(13)) and done[-2:] == [0, 12]
    assert not any("Refused" in ln for ln in con.lines)
