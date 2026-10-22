"""Regression tests for the slab-safety / software review fixes (simulator; no hardware).

Each test injects the fault the finding describes and checks the machine ends in a safe state. The
simulator raises Crash for unsafe motion, so "no Crash" means the recovery motion was safe too.
"""

import csv
import dataclasses

import numpy as np
import pytest

from slabscan.certs import CodeRead, ItfModel, Verdict, consensus
from slabscan.config import from_layout
from slabscan.hw import SensorFault
from slabscan.motion import MotionError
from slabscan.results import BatchWriter, SlabResult
from slabscan.runner import HardStop, Runner, Stop, read_journal
from slabscan.simworld import Crash, SimCamera, SimGate, SimLights, SimMotion, SimSlab, SimVacuum, SimWorld, _cached_view, make_batch


def _cfg(**kw):
    return dataclasses.replace(from_layout(), **kw)


def _world(cfg, per_pocket=2, sources=1, seed=31, eras=(1.0, 0.0, 0.0)):
    full = make_batch(cfg, per_pocket=per_pocket, seed=seed, eras=eras)
    stacks = {k: (v if k <= sources else []) for k, v in full.items()}
    return SimWorld(cfg, stacks={k: list(v) for k, v in stacks.items()}), stacks


def _runner(cfg, world, tmp_path, motion=None, vacuum=None, head=None, gate="sim", log=None, batch="b"):
    return Runner(cfg, motion or SimMotion(world), vacuum or SimVacuum(world), SimLights(), head or SimCamera(world, "head"),
                  SimCamera(world, "station"), BatchWriter(tmp_path, batch), gate=SimGate(world) if gate == "sim" else gate,
                  log=log or (lambda *_: None))


class HookMotion(SimMotion):
    """SimMotion that counts every command, records every probe, and calls hook(kind, self) after each
    command (the hook may raise to inject a fault after the motion happened)."""

    def __init__(self, world, hook=None):
        super().__init__(world)
        self.hook = hook or (lambda kind, m: None)
        self.commands = 0
        self.probes: list[tuple[float, float, float, bool]] = []  # (z before, target, feed, holding)

    def move(self, feed, x=None, y=None, z=None):
        self.commands += 1
        super().move(feed, x=x, y=y, z=z)
        self.hook("move", self)

    def probe(self, z_target, feed):
        self.commands += 1
        self.probes.append((self.w.z, z_target, feed, bool(self.w.held)))
        r = super().probe(z_target, feed)
        self.hook("probe", self)
        return r


def _over(w, index):
    p = w.pocket_at(w.x, w.y)
    return p is not None and p.index == index


# ---------------------------------------------------------------------- stale Z after an error (software-1, slab-safety-1)
def test_comms_error_after_the_station_descent_lifts_before_moving_sideways(tmp_path):
    """A 'no status report' after the head went down at the station used to leave the old travel height in
    self.z; secure() -> put_back() then moved X with the slab 50 mm below the rod tops."""
    cfg = _cfg(front_photo="always")
    world, stacks = _world(cfg)
    fired = []

    def hook(kind, m):
        w = m.w
        if kind == "probe" and not fired and w.held and w.at_station(w.x, w.y) and w.z < cfg.post_h:
            fired.append(w.z)
            raise MotionError("no status report")

    r = _runner(cfg, world, tmp_path, motion=HookMotion(world, hook))
    with pytest.raises(Stop, match="Unexpected error: MotionError.*put back on top of pocket 1"):
        r.run()
    assert fired and not world.held
    assert [s.cert for s in world.stacks[1]] == [s.cert for s in stacks[1]]


def test_comms_error_on_the_destination_approach_lifts_before_moving_sideways(tmp_path):
    cfg = _cfg()
    world, stacks = _world(cfg)
    fired = []

    def hook(kind, m):
        if kind == "probe" and not fired and m.w.held and _over(m.w, 0):
            fired.append(m.w.z)
            raise MotionError("timeout waiting for ok after 'G38.3'")

    r = _runner(cfg, world, tmp_path, motion=HookMotion(world, hook))
    with pytest.raises(Stop, match="put back on top of pocket 1"):
        r.run()
    assert fired and not world.held and len(world.stacks[1]) == len(stacks[1])


def test_an_error_mid_move_never_leaves_a_stale_height(tmp_path):
    """The planned height is only taken once the move is done; secure() re-reads the real one and lifts
    straight up from there before any sideways move (with or without a slab in the cup)."""
    cfg = _cfg()
    world, stacks = _world(cfg)
    arm = []

    def hook(kind, m):
        if arm and kind == "probe":
            arm.clear()
            raise MotionError("no status report")

    r = _runner(cfg, world, tmp_path, motion=HookMotion(world, hook))
    r._home()
    p1 = cfg.pocket(1)
    r._go(p1.x, p1.y)
    arm.append(1)
    with pytest.raises(MotionError):
        r._z(r.c(150.0))
    assert r.z is None
    assert r.secure() == "" and r.z == pytest.approx(r.c(cfg.c_safe_empty))

    r.pick_top(1)
    sx, sy = cfg.station_xy
    r._go(sx, sy)
    arm.append(1)
    with pytest.raises(MotionError):
        r._z(r.c(cfg.station_read_c))
    assert r.z is None and world.held
    assert "put back on top of pocket 1" in r.secure()
    assert not world.held and len(world.stacks[1]) == len(stacks[1])


def test_a_crash_during_recovery_is_not_swallowed(tmp_path):
    """software-6: secure() caught SafetyViolation as 'Could not park', muting the simulator's safety
    monitor for every recovery motion."""
    cfg = _cfg()
    world, _ = _world(cfg)
    failed = []

    class DeadCamera(SimCamera):
        def capture(self):
            if self.n + 1 >= 2:  # frame 1 = hover; frame 2 = first back read with the slab held
                failed.append(True)
                raise RuntimeError("camera head returned no frame")
            return super().capture()

    def hook(kind, m):
        if failed and kind == "move" and m.w.held:
            raise Crash("test crash during the put-back")

    r = _runner(cfg, world, tmp_path, motion=HookMotion(world, hook), head=DeadCamera(world, "head"))
    with pytest.raises(Crash, match="test crash"):
        r.run()


# ---------------------------------------------------------------------- Ctrl-C twice (software-2, EF-2, usability-cost-2)
def test_ctrl_c_twice_halts_and_moves_nothing(tmp_path):
    from slabscan.cli import execute_batch
    from slabscan.factory import Hardware
    from slabscan.ops import ScriptedConsole

    cfg = _cfg()
    world, _ = _world(cfg)
    state = {}

    def hook(kind, m):
        if kind == "probe" and "at" not in state and m.w.held and _over(m.w, 0):
            state["at"] = m.commands
            raise KeyboardInterrupt

    m = HookMotion(world, hook)
    r = _runner(cfg, world, tmp_path, motion=m)
    with pytest.raises(HardStop, match="Hard stop.*pocket 1 is on the cup"):
        r.run()
    assert m.commands == state["at"], "nothing may move after Ctrl-C twice"
    assert "HALT" in m.log and not m.homed  # feed hold + reset; the next run homes first
    assert world.held and world.vacuum_on and r.slab_on_cup == "pocket 1"
    ev = read_journal(r.journal)[-1]
    assert ev["stop"].startswith("operator hard stop") and ev["held_from"][0] == 1

    # through the CLI entry point: exit code 130, stop.json kind 'interrupt'
    world2, _ = _world(cfg)
    state.clear()
    hw = Hardware(cfg=cfg, motion=HookMotion(world2, hook), vacuum=SimVacuum(world2), lights=SimLights(), head_cam=SimCamera(world2, "head"),
                  station_cam=SimCamera(world2, "station"), gate=SimGate(world2), world=world2, sim=True)
    code, _, msg = execute_batch(cfg, hw, BatchWriter(tmp_path, "b2"), ScriptedConsole([]))
    assert code == 130 and "Hard stop" in msg
    assert '"interrupt"' in (tmp_path / "b2" / "stop.json").read_text()


# ---------------------------------------------------------------------- fast descents are probes (slab-safety-2)
def test_slabs_added_to_the_output_stack_are_met_by_the_probe_not_a_fast_move(tmp_path):
    cfg = _cfg()
    world, _ = _world(cfg, per_pocket=3)
    added = []

    def log(*_):
        if not added and len(r.w.rows) == 1:  # after the first slab sits on pocket 0: someone adds three
            extra = [SimSlab(f"99000000{i}", 6.6) for i in range(3)]
            world.stacks[0].extend(extra)
            added.extend(extra)

    r = _runner(cfg, world, tmp_path, log=log)
    with pytest.raises(Stop, match="Unexpected contact over pocket 0 .* with a slab in the cup"):
        r.run()
    assert added and not world.held and len(world.stacks[1]) == 2  # the slab in the cup went back on its stack


def test_a_slab_added_to_the_source_is_met_by_the_probe_on_the_hover_descent(tmp_path):
    cfg = _cfg()
    world, _ = _world(cfg, per_pocket=3)
    added = []

    def log(*_):
        if not added and len(r.w.rows) == 1:
            extra = [SimSlab(f"99100000{i}", 6.6) for i in range(2)]
            world.stacks[1].extend(extra)
            added.extend(extra)

    r = _runner(cfg, world, tmp_path, log=log)
    with pytest.raises(Stop, match="Unexpected contact over pocket 1"):
        r.run()
    assert not world.held and not world.gripping


def test_a_held_slab_passes_the_rod_tops_slowly(tmp_path):
    """slab-safety-13: from 5 mm above the rod tops to 10 mm below them a held slab descends at feed_rod_band."""
    cfg = _cfg(front_photo="always")
    world, _ = _world(cfg)
    m = HookMotion(world)
    _runner(cfg, world, tmp_path, motion=m).run()
    lo, hi = cfg.post_h - 10 + cfg.t_min, cfg.post_h + 5 + cfg.t_thick_max
    held_band = [(a, b, f) for a, b, f, held in m.probes if held and b < a and max(lo, b) < min(hi, a) - 1e-6]
    assert held_band, "the station and placement descents cross the band"
    assert all(f <= cfg.feed_rod_band for _, _, f in held_band)


# ---------------------------------------------------------------------- peel (slab-safety-3, software-3)
@pytest.mark.parametrize("trip", [1.5, 2.0, 2.5])
def test_the_slab_leaves_its_stack_only_during_the_slow_peel(tmp_path, trip):
    cfg = _cfg()
    world, stacks = _world(cfg)
    world.trigger_compression = trip  # BUILD_GUIDE 7.6 sets the trip at 2.0 +/- 0.5 mm of buffer travel
    _runner(cfg, world, tmp_path).run()
    assert len(world.peels) == len(stacks[1])
    assert all(f <= cfg.feed_peel_slow for f, _ in world.peels)
    assert min(after for _, after in world.peels) >= 0.5


def test_the_old_peel_profile_tears_the_slab_off_fast(tmp_path):
    """The old profile (1 mm slow from the trip point, then 1200 mm/min) only let the spring relax: the slab
    really left the stack at 20 mm/s. The simulator now models the buffer compression and catches it."""
    cfg = _cfg(buffer_trip_mm=0.0, buffer_trip_tol_mm=0.0)
    world, _ = _world(cfg)
    with pytest.raises(Crash, match="torn off its stack at F1200"):
        _runner(cfg, world, tmp_path).run()


# ---------------------------------------------------------------------- vacuum faults (slab-safety-4/5, EF-1, software-9/12)
class VacWrap:
    """Wraps SimVacuum; subclasses override kpa / release to inject faults."""

    simulated = True

    def __init__(self, world):
        self.w = world
        self.inner = SimVacuum(world)
        self.releases = 0
        self.holds = 0

    def hold(self):
        self.holds += 1
        self.inner.hold()

    def release(self):
        self.releases += 1
        self.inner.release()

    def close(self):
        self.inner.close()

    def kpa(self):
        return self.inner.kpa()


def test_low_vacuum_in_transit_carries_the_slab_back_and_sets_it_down(tmp_path):
    cfg = _cfg()
    world, stacks = _world(cfg, per_pocket=2)

    class Leaky(VacWrap):
        def kpa(self):
            if self.w.held and _over(self.w, 0) and self.w.z > cfg.post_h:  # weak hold, at carry height over the output
                return -10.0
            return self.inner.kpa()

    vac = Leaky(world)
    r = _runner(cfg, world, tmp_path, vacuum=vac)
    with pytest.raises(Stop, match="Vacuum lost in transit.*carried back slowly and set down on top of pocket 1"):
        r.run()
    assert not world.held and not r.holding and len(world.stacks[1]) == len(stacks[1])
    assert any(e.get("low_vacuum_set_down") == 1 for e in read_journal(r.journal))


def test_a_failed_park_keeps_the_pump_holding_and_says_a_slab_is_on_the_cup(tmp_path):
    from slabscan.cli import hand_off_slab
    from slabscan.ops import ScriptedConsole

    cfg = _cfg()
    world, _ = _world(cfg)
    failed = []

    class DeadCamera(SimCamera):
        def capture(self):
            if self.n + 1 >= 2:
                failed.append(True)
                raise RuntimeError("camera head returned no frame")
            return super().capture()

    def hook(kind, m):
        if failed and kind == "move":
            raise MotionError("'G1 X134.000 F15000' -> ALARM:2")  # the controller refuses to move

    vac = VacWrap(world)
    r = _runner(cfg, world, tmp_path, motion=HookMotion(world, hook), vacuum=vac, head=DeadCamera(world, "head"))
    with pytest.raises(Stop, match="Could not park.*A SLAB from pocket 1 is still on the cup; the pump keeps holding it"):
        r.run()
    assert r.holding and world.held and world.vacuum_on

    # no keyboard (unattended): the pump keeps holding, nothing is vented
    waited = []
    before = vac.releases
    hand_off_slab(ScriptedConsole([]), vac, r, wait=lambda: waited.append(1))
    assert waited and vac.releases == before and world.vacuum_on

    # the operator holds the slab, types vent
    class Operator(ScriptedConsole):
        def _next(self, prompt):
            out = super()._next(prompt)
            if out == "vent":  # they hold it: it is no longer hanging when the cup lets go
                world.stacks[1].extend(reversed(world.held))
                world.held, world.gripping = [], False
            return out

    hand_off_slab(Operator(["", "vent"]), vac, r)
    assert vac.releases == before + 1 and not r.holding and r.slab_on_cup is None


def test_a_dead_vent_valve_stops_without_lifting(tmp_path):
    cfg = _cfg()
    world, _ = _world(cfg)
    state = {}

    class DeadVent(VacWrap):
        def release(self):
            if self.w.held:  # placing: the vent valve does not open, full vacuum stays
                state.setdefault("at", m.commands)
                return
            self.inner.release()

    m = HookMotion(world)
    r = _runner(cfg, world, tmp_path, motion=m, vacuum=DeadVent(world))
    with pytest.raises(Stop, match="Vent failed on pocket 0.*nothing will move"):
        r.run()
    assert m.commands == state["at"], "the head must not lift a slab that is still sealed to the cup"
    assert r.freeze == "vent_failed" and world.held  # resting on pocket 0, sealed to the cup
    assert not world.vacuum_on  # valves shut: the slab is supported by the stack


def test_a_slab_that_comes_up_with_the_vented_cup_is_set_back_down(tmp_path):
    cfg = _cfg()
    world, _ = _world(cfg)

    class Sticky(VacWrap):
        n_after = None

        def release(self):
            if self.w.held:
                self.n_after = 0
            self.inner.release()

        def kpa(self):
            if self.n_after is not None:
                self.n_after += 1
                if self.n_after == 2:  # the read after the first 5 mm of lift: the cup pulls vacuum again
                    return -1.5
            return self.inner.kpa()

    r = _runner(cfg, world, tmp_path, vacuum=Sticky(world))
    with pytest.raises(Stop, match=r"came up with the vented cup on pocket 0 \(.*\)\. It was set back down"):
        r.run()
    assert r.freeze == "vent_failed"


@pytest.mark.parametrize("fault", ["exception", "impossible"])
def test_a_vacuum_sensor_fault_stops_without_motion_and_keeps_holding(tmp_path, fault):
    """EF-1 / software-9: an open sensor wire reads -112.5 kPa (a 'perfect seal'); PiVacuum now raises
    SensorFault outside the sensor's range, and the runner refuses impossible readings."""
    cfg = _cfg()
    world, _ = _world(cfg)
    state = {}

    class Broken(VacWrap):
        def kpa(self):
            if self.w.held:
                state.setdefault("at", m.commands)
                if fault == "exception":
                    raise SensorFault("vacuum sensor input 0.00 V is outside its 0.33-3.0 V range")
                return -112.5
            return self.inner.kpa()

    m = HookMotion(world)
    r = _runner(cfg, world, tmp_path, motion=m, vacuum=Broken(world))
    with pytest.raises(Stop, match="Vacuum sensor fault"):
        r.run()
    assert m.commands == state["at"] and r.holding and world.vacuum_on and r.freeze == "sensor"


def test_an_empty_cup_at_placement_stops_instead_of_looping(tmp_path):
    """software-9: a sensor that reports a seal that is not there + a slab that will not seal used to loop
    forever on that slab, writing 'ok' rows with a 0 mm step."""
    cfg = _cfg()
    world, _ = _world(cfg)
    world.stacks[1][-1].seal_fails = True

    class SealLiar(VacWrap):
        def kpa(self):  # after the survey: reports a seal whenever the pump runs
            return -62.0 if (self.w.vacuum_on and r.phase == "transfer") else self.inner.kpa()

    r = _runner(cfg, world, tmp_path, vacuum=SealLiar(world))
    with pytest.raises(Stop, match="as if nothing is in the cup"):
        r.run()
    assert r.w.rows == [] and r.freeze == "hold"


def test_pi_vacuum_rejects_readings_outside_the_sensor_range():
    from slabscan.hw import PiVacuum

    class Bus:
        raw = 0

        def write_i2c_block_data(self, *a):
            pass

        def read_i2c_block_data(self, *a):
            return [(self.raw >> 8) & 0xFF, self.raw & 0xFF]

    v = object.__new__(PiVacuum)
    v.bus = Bus()
    v.bus.raw = 0  # 0 V: open OUT wire / lost 5 V (used to read -112.5 kPa)
    with pytest.raises(SensorFault):
        v.kpa()
    v.bus.raw = round(3.0 / 4.096 * 32768)  # 4.5 V sensor output = atmosphere
    assert v.kpa() == pytest.approx(0.0, abs=0.1)


# ---------------------------------------------------------------------- slab left on the cup (slab-safety-7, software-16)
def test_preflight_refuses_a_closed_line_holding_a_slab_and_keeps_it_held(tmp_path):
    cfg = _cfg(vac_baseline_kpa=0.3)
    world, _ = _world(cfg)

    class ClosedLine(VacWrap):
        def kpa(self):
            return -10.0 if not self.holds else -60.0  # a slab hanging on the leaking closed line

    m = HookMotion(world)
    vac = ClosedLine(world)
    r = _runner(cfg, world, tmp_path, motion=m, vacuum=vac)
    with pytest.raises(Stop, match="holds vacuum at the start"):
        r.run()
    assert m.commands == 0 and vac.releases == 0  # no homing, no vent
    assert vac.holds == 1 and r.slab_on_cup  # the pump is switched on so it cannot fall


def test_a_cup_that_seals_before_the_survey_probes_is_not_vented(tmp_path):
    cfg = _cfg()
    world, _ = _world(cfg)

    class Hanging(VacWrap):
        def kpa(self):
            return -40.0 if self.holds else 0.0  # reads atmosphere (leaked to it) until the pump re-seals the hanging slab

    vac = Hanging(world)
    r = _runner(cfg, world, tmp_path, vacuum=vac)
    with pytest.raises(Stop, match="sealed .* before the head moved down"):
        r.run()
    assert vac.releases == 0 and r.freeze == "hold"


def test_selftest_does_not_vent_a_line_that_holds_vacuum(tmp_path):
    from slabscan.factory import sim_hardware
    from slabscan.ops import ScriptedConsole, selftest

    cfg = _cfg()
    hw = sim_hardware(cfg, slabs=0)

    class SlabOnCup(VacWrap):
        def kpa(self):
            return -20.0

    hw.vacuum = SlabOnCup(hw.world)
    con = ScriptedConsole([])
    assert selftest(cfg, con, hw=hw, sim=True, out_dir=tmp_path) == 1
    assert hw.vacuum.releases == 0
    assert any("holds vacuum" in ln and "Not vented" in ln for ln in con.lines)


# ---------------------------------------------------------------------- face-down check (slab-safety-6, software-17)
def test_a_face_up_slab_is_never_touched(tmp_path):
    cfg = _cfg()
    world, _ = _world(cfg)
    world.stacks[1][-1].face_down = False
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match="could not be confirmed FACE-DOWN"):
        r.run()
    assert not world.gripping and not world.held and r.w.rows == []
    # without the check the simulator itself catches the cup sealing on the front
    world2, _ = _world(cfg)
    world2.stacks[1][-1].face_down = False
    with pytest.raises(Crash, match="FRONT of face-up slab"):
        _runner(_cfg(face_down_check="off"), world2, tmp_path, batch="b2").run()


def test_a_face_up_cgc_slab_shows_its_front_code_and_stops(tmp_path):
    cfg = _cfg()
    world, _ = _world(cfg)
    top = world.stacks[1][-1]
    top.grader, top.cert, top.face_down = "CGC", "4123456001", False
    with pytest.raises(Stop, match="CGC code is visible from above, and those sit on the FRONT label"):
        _runner(cfg, world, tmp_path).run()


def test_an_old_label_stops_until_the_operator_confirms_it_face_down(tmp_path):
    cfg = _cfg()
    world, stacks = _world(cfg, per_pocket=2)
    world.stacks[1][-1].era = "old"  # no back code at all
    r1 = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match="no PSA back-label QR"):
        r1.run()
    r2 = _runner(cfg, world, tmp_path)
    r2.w = BatchWriter.reopen(tmp_path / "b")
    r2.journal = r2.w.dir / "journal.jsonl"
    summary = r2.resume(face_down_ok=True)
    assert summary["slabs_visited"] == 2
    assert any(e.get("face_down_confirmed") == 1 for e in read_journal(r2.journal))


# ---------------------------------------------------------------------- read station (slab-safety-8)
def test_front_frames_are_decoded_over_the_output_pocket_not_over_the_lens(tmp_path):
    cfg = _cfg(front_photo="always")
    world, _ = _world(cfg)
    r = _runner(cfg, world, tmp_path)
    where = []
    real_read = r._read

    def spy(frames, camera, distance_mm=None):
        if camera == "front":
            where.append((r.at, world.z, bool(world.held)))
        return real_read(frames, camera, distance_mm)

    r._read = spy
    r.run()
    p0 = cfg.pocket(0)
    assert where and all(at == (p0.x, p0.y) and held and z > cfg.post_h for at, z, held in where)


# ---------------------------------------------------------------------- slab on the rods, gate order (slab-safety-10/17, software-18)
def test_a_slab_lying_on_the_rods_trips_the_first_survey_window(tmp_path):
    """The survey's first window used to start with a plain move to 216, under the 218 rod tops. It now starts
    at the empty travel height (here raised to 236, the CAD change slab-safety-10 asks for)."""
    cfg = _cfg(c_safe_empty=236.0)
    world, _ = _world(cfg)
    world.stacks[3] = [SimSlab("190000001", 224.6)]  # stands in for a slab lying across pocket 3's rod tops
    r = _runner(cfg, world, tmp_path, gate=None)  # the beam (214) cannot see above the rods anyway
    with pytest.raises(Stop, match="Pocket 3 is filled above the MAX line .* or something lies on its rods"):
        r.run()


def test_the_overfill_beam_is_checked_after_homing(tmp_path):
    """After an E-stop the head can stop low with its foot across the beam; the gate was read before
    homing and refused with 'a stack is above the MAX line'."""
    cfg = _cfg()
    world, _ = _world(cfg)
    m = SimMotion(world)

    class HeadInBeam:
        def clear(self):
            return m.homed  # blocked by the head until it has homed (Z straight up)

    summary = _runner(cfg, world, tmp_path, motion=m, gate=HeadInBeam()).run()
    assert summary["slabs_visited"] == 2


# ---------------------------------------------------------------------- double picks that let go (slab-safety-11)
@pytest.mark.parametrize("drop", ["peel", "transit"])
def test_a_clinging_slab_that_lets_go_is_accounted_for(tmp_path, drop):
    cfg = _cfg()
    world, stacks = _world(cfg, per_pocket=3, sources=2)
    world.stacks[2][1].clingy = True
    world.cling_drop = drop
    summary = _runner(cfg, world, tmp_path).run()
    rows = list(csv.DictReader((tmp_path / "b" / "certs.csv").open()))
    assert len(rows) == sum(len(v) for v in stacks.values()), "every physical slab has a row"
    assert any(("at the peel" if drop == "peel" else "end of the first sideways move") in e for e in world.events)
    flagged = [x for x in rows if "DOUBLE PICK" in x["note"]]
    if drop == "peel":  # fell back onto its own stack: simply read next
        assert not flagged and all(x["status"] == "ok" for x in rows)
    else:  # dropped into the output pocket just before the placement: caught as a double pick
        assert len(flagged) == 1 and sum(x["note"].startswith("UNREAD") for x in rows) == 1
    assert all(v["ok"] for v in summary["count_check"].values())
    assert sorted(len(v) for k, v in world.stacks.items() if k in (0, 1)) == sorted(len(stacks[k]) for k in (1, 2))


# ---------------------------------------------------------------------- neighbour labels in view (software-5)
class WideHeadCamera(SimCamera):
    """Head camera with the real lens' field of view: +/-92 mm along the row, so the next pocket's top label
    (from 57 mm off-axis) is in the frame, as it is on the machine."""

    MM_PER_PX = 0.05
    HALF_ROW_MM = 92.0

    def view_half_mm(self, distance_mm):
        return self.HALF_ROW_MM, 22.5

    def view_rect_mm(self, distance_mm):  # the top 900 rows of each pasted head view: the label end
        from slabscan.sim import HEAD_VIEW_MM

        return -self.HALF_ROW_MM, HEAD_VIEW_MM[1], self.HALF_ROW_MM, HEAD_VIEW_MM[1] + 900 * self.MM_PER_PX

    def capture(self):
        w = self.w
        self.n += 1
        width = int(2 * self.HALF_ROW_MM / self.MM_PER_PX)
        canvas = np.full((900, width), 30, np.uint8)
        p = w.pocket_at(w.x, w.y)
        own = w.held[0] if w.held else (w.stacks[p.index][-1] if p is not None and w.stacks.get(p.index) else None)

        def paste(slab, cx):
            img = _cached_view(slab.cert, slab.era, slab.grader, "back" if slab.face_down else "front", "head", w.itf_payload, self.deg)
            h, wd = img.shape
            x0 = int(round(cx - wd / 2))
            a, b = max(0, x0), min(width, x0 + wd)
            canvas[:min(h, 900), a:b] = img[:min(h, 900), a - x0:b - x0]

        if own is not None:
            paste(own, width / 2)
        if p is not None and w.stacks.get(p.index + 1):
            pitch_px = (w.cfg.pocket(p.index + 1).x - w.cfg.pocket(p.index).x) / self.MM_PER_PX
            paste(w.stacks[p.index + 1][-1], width / 2 + pitch_px)
        return canvas


def test_the_neighbour_pockets_label_is_cropped_out_of_head_frames(tmp_path):
    cfg = _cfg(face_down_check="off")
    world, stacks = _world(cfg, per_pocket=2, sources=2, seed=41)
    old = world.stacks[1][-1]
    old.era = "old"  # no back code: before the crop the neighbour's QR became this slab's 'ok' cert
    neighbour = world.stacks[2][-1].cert
    r = _runner(cfg, world, tmp_path, head=WideHeadCamera(world, "head"))
    assert r._head_roi(145.0) == pytest.approx((0.25, 0.0, 0.75, 1.0))
    r.run()
    rows = list(csv.DictReader((tmp_path / "b" / "certs.csv").open()))
    first = rows[0]
    assert first["cert"] != neighbour.lstrip("0")
    assert first["cert"] in ("", old.cert.lstrip("0"))
    oks = [x["cert"] for x in rows if x["status"] == "ok"]
    assert len(oks) == len(set(oks))


def test_a_neighbours_qr_does_not_confirm_a_slab_face_down(tmp_path):
    cfg = _cfg()
    world, _ = _world(cfg, per_pocket=2, sources=2, seed=41)
    world.stacks[1][-1].era = "old"
    with pytest.raises(Stop, match="FACE-DOWN"):
        _runner(cfg, world, tmp_path, head=WideHeadCamera(world, "head")).run()


def test_a_cert_already_recorded_in_the_batch_becomes_a_conflict(tmp_path):
    cfg = _cfg()
    world, _ = _world(cfg)
    r = _runner(cfg, world, tmp_path)
    qr = CodeRead("148069831", "back_qr", "QRCode", "https://www.psacard.com/cert/148069831")
    assert r._decide([qr], [qr]).status == "ok"
    r.w.add(SlabResult(1, 1, 1, 0, 1, Verdict("ok", "148069831", ("back_qr",))))
    v = r._decide([qr], [qr])
    assert v.status == "conflict" and "already recorded at #1" in v.note
    # the frame from above the stack alone never makes an 'ok'
    other = CodeRead("151234567", "back_qr", "QRCode", "https://www.psacard.com/cert/151234567")
    assert r._decide([other], []).status == "needs_review"


def test_one_frame_counts_each_code_once(tmp_path, monkeypatch):
    """software-4: the overlapping tile pass decoded one ITF twice in one frame, meeting min_itf_reads alone."""
    import slabscan.runner as runner_mod

    itf = CodeRead("148069831", "front_barcode", "ITF", "0148069831")
    monkeypatch.setattr(runner_mod, "decode_frame", lambda *a, **k: ([itf, itf], []))
    cfg = _cfg()
    world, _ = _world(cfg)
    r = _runner(cfg, world, tmp_path)
    reads, _ = r._read([object(), object()], "front")
    assert len(reads) == 2  # one per frame
    m = ItfModel()
    m.evidence["zero_pad"] = 3
    assert consensus(reads, m).status == "needs_review"  # two frames of one pose are one source


def test_the_head_camera_is_never_ocr_d(tmp_path, monkeypatch):
    """software-13: head-camera OCR read the card back's printed numbers through the slab."""
    import slabscan.decode as decode_mod
    import slabscan.runner as runner_mod

    seen = []
    real = runner_mod.ocr_digits

    def front_only(gray, camera=""):
        seen.append(camera)
        return real(gray, camera)

    def never(*a, **k):
        raise AssertionError("decode_frame ran OCR")

    monkeypatch.setattr(runner_mod, "ocr_digits", front_only)
    monkeypatch.setattr(decode_mod, "ocr_digits", never)
    cfg = _cfg(face_down_check="off")
    world, _ = _world(cfg, per_pocket=1)
    world.stacks[1][-1].era = "old"
    _runner(cfg, world, tmp_path).run()
    assert seen and set(seen) == {"front"}


def test_free_cup_hang_is_in_travel_heights_and_follows_measured_buffer_trip(tmp_path):
    # the free cup hangs buffer_trip_mm below c: a double pick of two thick holders must still clear the rods by 5 mm
    cfg = from_layout()
    hang = cfg.buffer_trip_mm
    assert cfg.c_safe_loaded - hang - 2 * cfg.t_thick_max >= cfg.post_h + 5
    assert cfg.c_safe_empty - hang - cfg.t_thick_max >= cfg.post_h + 5
    from slabscan.config import dumps, load

    machine = tmp_path / "machine.toml"
    machine.write_text(dumps(cfg))
    cal = tmp_path / "calibration.toml"
    cal.write_text("buffer_trip_mm = 2.6\n")
    late = load(machine, cal)
    assert late.c_safe_loaded == pytest.approx(cfg.c_safe_loaded + 0.6) and late.c_safe_empty == pytest.approx(cfg.c_safe_empty + 0.6)
    cal.write_text("buffer_trip_mm = 4.5\n")
    with pytest.raises(ValueError, match="c_max"):
        load(machine, cal)
