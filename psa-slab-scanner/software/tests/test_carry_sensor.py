"""The carry-height sensor (Z stall guard): a slotted optical switch on the Z spine, blocked by a flag on the Z carriage
for every head height from carry_sensor_c0 up (cad/layout.py CARRY_SENSOR_C0). The runner requires BLOCKED before every
sideways move and before every move with a slab held at travel height, and CLEAR far below that height (every pick).

The simulator injects the faults: Z losing steps while lifting a slab (SimWorld.z_lost_steps; the controller still reports
the commanded height), a sensor stuck blocked (dead emitter, dirt) and one stuck clear (cut lead). SimMotion raises Crash
on any unsafe move, so "no Crash" means the stop and the recovery were safe.
"""

import dataclasses
import json
import sys
from pathlib import Path

import pytest

from slabscan import sim
from slabscan.config import CARRY_BAND_MM, dumps, from_layout, load
from slabscan.factory import sim_hardware
from slabscan.ops import ScriptedConsole, selftest
from slabscan.results import BatchWriter
from slabscan.runner import Runner, Stop, read_journal
from slabscan.simworld import Crash, SimCamera, SimCarry, SimGate, SimLights, SimMotion, SimSlab, SimVacuum, SimWorld

CAD = Path(__file__).resolve().parents[2] / "cad"


def _cfg(**kw):
    return dataclasses.replace(from_layout(), face_down_check="off", **kw)


def _world(cfg, n=3, src=3, **kw) -> SimWorld:
    stacks = {p.index: [] for p in cfg.sources}
    stacks[src] = [SimSlab(str(148069831 + 7919 * i), 6.6) for i in range(n)]
    return SimWorld(cfg, stacks=stacks, **kw)


def _runner(cfg, world, tmp_path, carry="sim", motion=None, batch="b", writer=None):
    return Runner(cfg, motion or SimMotion(world), SimVacuum(world), SimLights(), SimCamera(world, "head"), SimCamera(world, "station"),
                  writer or BatchWriter(tmp_path, batch), gate=SimGate(world), log=lambda *_: None,
                  carry=SimCarry(world) if carry == "sim" else carry)


# ---------------------------------------------------------------------- Z stall
def test_z_losing_steps_while_lifting_a_slab_crashes_without_the_sensor(tmp_path):
    """The fault is real: the head stops 40 mm short of the loaded travel height, and the next sideways move drags the
    slab through the rods."""
    cfg = _cfg()
    world = _world(cfg, z_lost_steps=40.0)
    with pytest.raises(Crash, match="lowest point at 199.4"):
        _runner(cfg, world, tmp_path, carry=None).run()


def test_a_z_stall_while_lifting_a_slab_stops_before_the_sideways_move(tmp_path):
    cfg = _cfg()
    world = _world(cfg, z_lost_steps=40.0)
    top = world.stacks[3][-1].cert
    motion = SimMotion(world)
    r = _runner(cfg, world, tmp_path, motion=motion)
    with pytest.raises(Stop, match=r"Z stall suspected before moving sideways over pocket 3 with a slab in the cup: the carry-height sensor "
                                   r"\(GPIO 6\) reads CLEAR, but the controller has the head at 248\.0 mm") as e:
        r.run()
    assert "lost steps while lifting" in str(e.value) and "lowered straight down onto pocket 3" in str(e.value)
    assert world.events[0].startswith("Z lost 40 mm of steps lifting " + top)
    # the slab never moved sideways: it went straight back down onto its own stack and was let go there
    assert not world.held and not world.gripping and [s.cert for s in world.stacks[3]][-1] == top and len(world.stacks[3]) == 3
    assert world.x == cfg.pocket(3).x and r.w.rows == [] and r.freeze is None
    stop = [e for e in read_journal(r.journal) if "stop" in e][-1]
    assert stop["carry_fault"] == "stall" and any("stall_set_down" in e for e in read_journal(r.journal))
    # resume homes first (the controller's Z is right again) and finishes every slab once
    summary = _runner(cfg, world, tmp_path, motion=motion, writer=BatchWriter.reopen(tmp_path / "b")).resume()
    assert summary["slabs_visited"] == 3 and len(world.stacks[2]) == 3 and not world.stacks[3]


def test_a_z_stall_lifting_from_the_read_station_keeps_the_slab_held(tmp_path):
    """Over the read station there is no stack to set the slab on, and the head height is unknown: nothing moves, the
    pump keeps holding the slab, and the operator takes it (the existing hold rule)."""
    cfg = _cfg(front_photo="always")
    world = _world(cfg, z_lost_steps=50.0, z_lost_steps_at=2)  # lift 1: off the stack; lift 2: from the read height
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match="Z stall suspected before moving sideways over the read station with a slab in the cup") as e:
        r.run()
    assert "still on the cup over the read station" in str(e.value) and "pump keeps holding it" in str(e.value)
    assert len(world.held) == 1 and world.vacuum_on and r.freeze == "hold" and r.slab_on_cup == "pocket 3"
    assert world.at_station(world.x, world.y) and world.z == pytest.approx(cfg.c_safe_loaded - 50.0)


def test_a_small_z_loss_on_a_loaded_lift_is_caught_before_the_slab_goes_down(tmp_path):
    """[Certain, arithmetic] one trip height cannot see a loss that leaves the loaded head above it (248 - 10 = 238 >=
    235): the slab is carried over (it still clears the rods by 11 mm). The held descent pauses 1.25 mm above the trip,
    where the sensor must read blocked: the run stops there, before the placement probe would measure a 10 mm wrong step
    (it used to record a DOUBLE PICK and an UNREAD row). Not over its own pocket, so the slab stays held."""
    cfg = _cfg()
    world = _world(cfg, z_lost_steps=10.0)
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match=r"Z stall suspected before a Z move with a slab in the cup over pocket 2: .* head at 236\.\d mm"):
        r.run()
    assert r.w.rows == [] and len(world.held) == 1 and r.freeze == "hold" and world.pocket_at(world.x, world.y).index == 2
    assert world.z == pytest.approx(cfg.carry_sensor_c0 + CARRY_BAND_MM + 0.25 - 10.0)


# ---------------------------------------------------------------------- the sensor itself
def test_a_sensor_stuck_blocked_stops_before_the_first_grip(tmp_path):
    """A dead emitter or dirt in the slot reads blocked, which would let every sideways move through: the pick, far
    below the trip height, must read clear."""
    cfg = _cfg()
    world = _world(cfg)
    with pytest.raises(Stop, match=r"Carry-height sensor fault before gripping the top slab of pocket 3: it reads BLOCKED with the head at 19\.8 mm"):
        _runner(cfg, world, tmp_path, carry=SimCarry(world, stuck="blocked")).run()
    assert not world.gripping and not world.held and len(world.stacks[3]) == 3


def test_a_cut_sensor_lead_stops_before_the_first_sideways_move(tmp_path):
    cfg = _cfg()
    world = _world(cfg)
    with pytest.raises(Stop, match="Z stall suspected before moving sideways near the home position.*Right after homing this is most likely "
                                   "the sensor itself: a cut or unplugged lead"):
        _runner(cfg, world, tmp_path, carry=SimCarry(world, stuck="clear")).run()
    assert world.x == cfg.x_travel[0]  # never left the home position


class CheckingMotion(SimMotion):
    """Asserts the rule on every motion command: a sideways move, and any move with a slab on the cup, comes right after
    a carry-sensor read taken with the head where it is."""

    def __init__(self, world, carry):
        super().__init__(world)
        self.carry, self.seen, self.checked = carry, 0, {"sideways": 0, "held": 0}

    def _assert_read(self, sideways: bool, moves: bool) -> None:
        fresh, self.seen = self.carry.log[self.seen:], len(self.carry.log)
        held = bool(self.w.held or self.w.gripping)
        if self.homed and moves and (sideways or held):
            assert fresh and fresh[-1][:2] == (self.w.x, self.w.z), f"move at ({self.w.x}, {self.w.z}) without a carry-sensor read there"
            self.checked["sideways" if sideways else "held"] += 1

    def move(self, feed, x=None, y=None, z=None):
        sideways = x is not None and abs(x - self.x_offset - self.w.x) > 1e-9
        self._assert_read(sideways, sideways or (z is not None and abs(z - self.z_offset - self.z_slip - self.w.z) > 1e-9))
        super().move(feed, x=x, y=y, z=z)

    def probe(self, z_target, feed):
        self._assert_read(False, True)
        return super().probe(z_target, feed)


def test_the_sensor_is_read_before_every_sideways_move_and_every_held_move(tmp_path):
    cfg = _cfg(front_photo="always")
    world = _world(cfg, n=2)
    world.stacks[4] = [SimSlab("150000007", 6.6, "old"), SimSlab("4123456001", 7.5, "2023+", grader="CGC")]
    carry = SimCarry(world)
    m = CheckingMotion(world, carry)
    summary = _runner(cfg, world, tmp_path, carry=carry, motion=m).run()
    assert summary["slabs_visited"] == 4
    assert m.checked["sideways"] >= 4 * 3 and m.checked["held"] >= 4 * 6  # per slab: to the source, the station, the output; peel, lifts, descents
    assert any(b for _, _, b in carry.log) and any(not b for _, _, b in carry.log)  # both states were seen and agreed


def test_the_runner_without_a_sensor_or_with_it_switched_off_does_not_read_it(tmp_path):
    cfg = _cfg(carry_sensor=False)
    world = _world(cfg, n=1)
    carry = SimCarry(world, stuck="clear")
    assert _runner(cfg, world, tmp_path, carry=carry).run()["slabs_visited"] == 1 and carry.log == []


# ---------------------------------------------------------------------- selftest
def test_selftest_motion_measures_where_the_carry_sensor_trips(tmp_path):
    cfg = _cfg()
    hw = sim_hardware(cfg, slabs=0)
    con = ScriptedConsole([])
    assert selftest(cfg, con, hw=hw, sim=True, do_motion=True, out_dir=tmp_path) == 0
    line = next(x for x in con.lines if "carry sensor" in x)
    assert line.startswith("[PASS] carry sensor: blocked at the top, trips at about 234.88 mm (set 235.0")
    assert hw.world.z == 250.0 and hw.world.x == cfg.x_travel[0]  # back where homing left it
    # a mount that slid 3 mm up: still blocked at the top, but clear at the empty travel height
    hw = sim_hardware(cfg, slabs=0)
    hw.carry = SimCarry(hw.world, trip=238.0)
    con = ScriptedConsole([])
    assert selftest(cfg, con, hw=hw, sim=True, do_motion=True, out_dir=tmp_path) == 1
    assert any(x.startswith("[FAIL] carry sensor: must read blocked from 236.0 mm up and clear from 234.0 mm down; it read CLEAR at 237.75")
               and "Slide the sensor mount" in x for x in con.lines)
    # without --motion it only reads the input
    con = ScriptedConsole([])
    selftest(cfg, con, hw=sim_hardware(cfg, slabs=0), sim=True, out_dir=tmp_path)
    assert any(x.startswith("[PASS] carry sensor: reads BLOCKED on GPIO 6") for x in con.lines)


# ---------------------------------------------------------------------- config / CAD sync
def test_config_takes_the_sensor_stroke_and_window_from_the_cad(tmp_path):
    if str(CAD) not in sys.path:
        sys.path.insert(0, str(CAD))
    import layout as L

    cfg = from_layout()
    assert (cfg.carry_sensor, cfg.carry_sensor_c0, cfg.buffer_stroke) == (True, L.CARRY_SENSOR_C0, L.BUFFER_STROKE)
    assert [list(r) for r in cfg.face_down_window_mm] == L.face_down_window_cam()  # from the camera axis, not the cup axis
    assert cfg.carry_sensor_c0 + CARRY_BAND_MM <= cfg.c_safe_empty
    bad = tmp_path / "m.toml"
    bad.write_text(dumps(dataclasses.replace(cfg, carry_sensor_c0=236.0)))
    with pytest.raises(ValueError, match="carry sensor must read blocked at the travel height 236.5 mm"):
        load(bad)
    bad.write_text(dumps(dataclasses.replace(cfg, probe_window=20.0)))
    with pytest.raises(ValueError, match="smaller than the buffer stroke 20.0"):
        load(bad)


def test_sim_head_matches_the_cad_export():
    """sim.HEADS["cad"] and the lens offset are cad/out/heads_cad.json (cad/model.py occluder_boxes()); the window it
    must leave clear is the CAD's, and it does at hover and held."""
    exp = json.loads((CAD / "out" / "heads_cad.json").read_text())
    assert [list(b) for b in sim.HEADS["cad"]] == exp["HEADS"]
    assert (sim.HEAD_CAM_DY, exp["lens"]["x"], exp["lens"]["z"]) == (exp["HEAD_CAM_DY"], 0.0, sim.CAM_ABOVE_CUP_MM)
    assert sim.CARD_TOP_RANGE_MM == (exp["card_top_from_label_edge_mm"]["min"], exp["card_top_from_label_edge_mm"]["max"])
    (x0, y0, x1, y1), = from_layout().face_down_window_mm
    assert [x0, y0, x1, y1] == exp["face_down_window_mm_from_camera_axis"][0]
    for distance in (exp["hover_lens_to_slab_mm"], exp["held_lens_to_slab_mm"]):
        for a, b, c, d, _ in sim.head_shadow("cad", distance):
            assert a >= x1 or c <= x0 or b >= y1 or d <= y0, f"a head part's shadow ({a:.1f}, {b:.1f}, {c:.1f}, {d:.1f}) is in the window"
    hidden = [p for p in sim.head_shadow("cad_r2") if not (p[0] >= x1 or p[2] <= x0 or p[1] >= y1 or p[3] <= y0)]
    assert hidden  # the round-2 head's foot is in it
