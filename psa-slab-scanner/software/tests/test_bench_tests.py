"""tools/bench_tests.py (BUILD_GUIDE 7.8 and 13) against the simulator: every subcommand runs, keeps the
runner's guard, and never ends with a slab on the cup."""

import pytest

from slabscan.factory import sim_hardware
from slabscan.ops import ScriptedConsole
from slabscan.simworld import Crash, SimSlab
from tools import bench_tests


def _stacks(cfg, n=3, src=1):
    return {**{p.index: [] for p in cfg.pockets}, src: [SimSlab(str(148069831 + 7919 * i), 6.6) for i in range(n)]}


def _run(tmp_path, argv, answers=(), hw_fn=None):
    con = ScriptedConsole(list(answers))
    from slabscan.cli import DEFAULT_CONFIG
    from slabscan.config import load

    cfg = load(DEFAULT_CONFIG, DEFAULT_CONFIG.parent / "calibration.toml")
    hw = (hw_fn or (lambda c: sim_hardware(c, stacks=_stacks(c))))(cfg)
    code = bench_tests.main(argv + ["--sim", "--out", str(tmp_path)], console=con, hw=hw)
    return code, "\n".join(con.lines), hw


def test_cycles_ping_pong_reads_the_same_slab_ok_every_time(tmp_path):
    code, out, hw = _run(tmp_path, ["cycles", "8"])
    assert code == 0, out
    assert "8 transfers, 8 read ok" in out  # the duplicate-cert rule of a real run must not apply
    assert not hw.world.held and len(hw.world.stacks[12]) == 0


def test_rest_reports_vacuum_statistics_and_lifts_off(tmp_path):
    code, out, hw = _run(tmp_path, ["rest", "0.01", "--poll", "6"])
    assert code == 0, out
    assert "rest test: hours" in out and "pump_duty_pct" in out and "simulator: its cup line has no leak model" in out
    assert not hw.world.held and len(hw.world.stacks[1]) == 3


def test_lifts_finds_no_drift_on_the_simulator(tmp_path):
    code, out, hw = _run(tmp_path, ["lifts", "5"])
    assert code == 0, out
    assert "Z lift test: PASS" in out
    assert not hw.world.held and len(hw.world.stacks[1]) == 3


def test_drop_needs_the_typed_word_and_the_simulator_calls_a_drop_a_crash(tmp_path):
    code, out, hw = _run(tmp_path, ["drop", "2"], answers=["no"])
    assert code == 0 and "not dropped" in out, out
    assert len(hw.world.stacks[1]) == 3
    with pytest.raises(Crash, match="drop"):
        _run(tmp_path, ["drop", "2"], answers=["DROP"])


def test_powercut_without_a_cut_puts_the_slab_back(tmp_path):
    code, out, hw = _run(tmp_path, ["powercut", "3"])
    assert code == 0, out
    assert "putting the slab back" in out
    assert not hw.world.held and len(hw.world.stacks[1]) == 3


def test_an_unexpected_error_with_a_slab_held_puts_it_back(tmp_path):
    def broken(cfg):
        hw = sim_hardware(cfg, stacks=_stacks(cfg))
        real = hw.head_cam.capture
        calls = {"n": 0}

        def capture():
            calls["n"] += 1
            if calls["n"] == 3:  # hover frame, then the first frame with the slab held
                raise RuntimeError("camera dropped off USB")
            return real()

        hw.head_cam.capture = capture
        return hw

    code, out, hw = _run(tmp_path, ["cycles", "2"], hw_fn=broken)
    assert code == 2 and "Unexpected error: RuntimeError: camera dropped off USB" in out, out
    assert "put back on top of pocket 1" in out
    assert not hw.world.held and len(hw.world.stacks[1]) == 3
