"""Stop a simulated batch part-way (injected faults), resume it from journal.jsonl + certs.csv,
and check that every slab was moved exactly once and ended where the run order says.

The simulator raises Crash on any unsafe move, so these also prove the stop/put-back/resume
motions are safe.
"""

import csv
import dataclasses

import pytest

from slabscan.config import from_layout
from slabscan.results import BatchWriter, SlabResult
from slabscan.runner import Runner, State, Stop, read_journal, rebuild_state
from slabscan.certs import Verdict
from slabscan.motion import ControllerLost, Z_FLOOR
from slabscan.simworld import SimCamera, SimGate, SimLights, SimMotion, SimSlab, SimVacuum, SimWorld, make_batch


def _stacks(cfg, per_pocket=2, sources=3, seed=21):
    full = make_batch(cfg, per_pocket=per_pocket, seed=seed, eras=(1.0, 0.0, 0.0))
    return {k: (v if k <= sources else []) for k, v in full.items()}


class FaultyVacuum:
    """SimVacuum that reports 'vacuum lost' exactly once, while a slab is held, when trigger() says so."""

    def __init__(self, inner, world, trigger):
        self.inner, self.w, self.trigger, self.fired = inner, world, trigger, False

    def hold(self):
        self.inner.hold()

    def release(self):
        self.inner.release()

    def close(self):
        self.inner.close()

    def kpa(self):
        if not self.fired and self.w.held and self.trigger():
            self.fired = True
            return 0.0
        return self.inner.kpa()


def _runner(cfg, world, writer, vacuum=None, should_stop=None):
    m = SimMotion(world, x_offset=cfg.offset_x, z_offset=cfg.pad_trigger_c)
    return Runner(cfg, m, vacuum or SimVacuum(world), SimLights(), SimCamera(world, "head"), SimCamera(world, "station"), writer,
                  gate=SimGate(world), log=lambda *_: None, should_stop=should_stop)


def _check_complete(cfg, world, original, batch_dir, summary):
    rows = list(csv.DictReader((batch_dir / "certs.csv").open()))
    n = sum(len(v) for v in original.values())
    certs = [r["cert"] for r in rows]
    assert sorted(certs) == sorted(s.cert.lstrip("0") for v in original.values() for s in v), "every slab read exactly once"
    assert [int(r["position"]) for r in rows] == list(range(1, n + 1))
    assert summary["slabs_visited"] == n
    for k, stack in original.items():
        if k >= 1 and stack:  # stack k ends in pocket k-1, reversed (all PSA 2017+ here, so no exceptions)
            assert [s.cert for s in world.stacks[k - 1]] == [s.cert for s in reversed(stack)]
    assert all(v["ok"] for v in summary["count_check"].values())


def test_resume_after_seal_failure_finishes_every_slab_once(tmp_path):
    cfg = from_layout()
    original = _stacks(cfg)
    world = SimWorld(cfg, stacks={k: list(v) for k, v in original.items()})
    world.stacks[2][-1].seal_fails = True  # top slab of pocket 2: stops after stack 1 is done
    r1 = _runner(cfg, world, BatchWriter(tmp_path, "b1"))
    with pytest.raises(Stop, match="will not seal"):
        r1.run()
    assert not world.held
    assert len(r1.w.rows) == 2
    world.stacks[2][-1].seal_fails = False  # the operator cleaned the cup
    r2 = _runner(cfg, world, BatchWriter.reopen(tmp_path / "b1"))
    summary = r2.resume()
    _check_complete(cfg, world, original, tmp_path / "b1", summary)
    events = read_journal(tmp_path / "b1" / "journal.jsonl")
    assert [k for k in ("survey", "stop", "resume", "finished") if any(k in e for e in events)] == ["survey", "stop", "resume", "finished"]


def test_vacuum_loss_puts_slab_back_and_resume_reads_it_again(tmp_path):
    cfg = from_layout()
    original = _stacks(cfg)
    world = SimWorld(cfg, stacks={k: list(v) for k, v in original.items()})
    writer = BatchWriter(tmp_path, "b2")
    vac = FaultyVacuum(SimVacuum(world), world, trigger=lambda: len(writer.rows) == 3)
    r1 = _runner(cfg, world, writer, vacuum=vac)
    with pytest.raises(Stop, match="put back on top of pocket 2"):
        r1.run()
    assert not world.held and not r1.holding
    assert [s.cert for s in world.stacks[2]] == [original[2][0].cert]  # 4th slab (top of pocket 2... minus the one moved) is back
    r2 = _runner(cfg, world, BatchWriter.reopen(tmp_path / "b2"))
    summary = r2.resume()
    _check_complete(cfg, world, original, tmp_path / "b2", summary)


def test_resume_refuses_changed_stacks_unless_accepted(tmp_path):
    cfg = from_layout()
    original = _stacks(cfg)
    original[3].append(SimSlab("0012345678", 8.5, grader="BGS"))  # goes to the exception pocket
    world = SimWorld(cfg, stacks={k: list(v) for k, v in original.items()})
    writer = BatchWriter(tmp_path, "b3")
    r1 = _runner(cfg, world, writer, should_stop=lambda: len(writer.rows) >= 5)
    with pytest.raises(Stop, match="Stopped on request"):
        r1.run()
    assert len(world.stacks[cfg.exceptions.index]) == 1
    world.stacks[cfg.exceptions.index].clear()  # operator takes the BGS slab out: allowed
    taken = world.stacks[3].pop()  # ...and also removes a slab from a source: not allowed silently
    r2 = _runner(cfg, world, BatchWriter.reopen(tmp_path / "b3"))
    with pytest.raises(Stop, match="stacks changed.*pocket 3"):
        r2.resume()
    r3 = _runner(cfg, world, BatchWriter.reopen(tmp_path / "b3"))
    summary = r3.resume(accept_heights=True)
    rows = list(csv.DictReader((tmp_path / "b3" / "certs.csv").open()))
    assert len(rows) == sum(len(v) for v in original.values()) - 1
    assert taken.cert.lstrip("0") not in {r["cert"] for r in rows}
    assert summary["count_check"][3]["counted"] == 2  # the BGS slab + the one left
    assert any("out_reset" in e for e in read_journal(tmp_path / "b3" / "journal.jsonl"))


def test_calibration_offsets_are_applied_to_safe_heights(tmp_path):
    """Regression: safe travel heights used to be sent as raw machine Z, ignoring pad_trigger_c.
    With the pad trigger at machine Z +7.5 the head swept 7.5 mm lower than planned (into the rod tops)."""
    cfg = dataclasses.replace(from_layout(), pad_trigger_c=7.5, offset_x=3.0)
    original = _stacks(cfg, per_pocket=1, sources=2)
    world = SimWorld(cfg, stacks={k: list(v) for k, v in original.items()})
    writer = BatchWriter(tmp_path, "b4")
    r1 = _runner(cfg, world, writer, should_stop=lambda: len(writer.rows) >= 1)
    with pytest.raises(Stop, match="Stopped on request"):
        r1.run()
    summary = _runner(cfg, world, BatchWriter.reopen(tmp_path / "b4")).resume()
    _check_complete(cfg, world, original, tmp_path / "b4", summary)


def test_rebuild_state_counts_a_row_the_journal_missed():
    cfg = from_layout()
    events = [
        {"survey": {"0": 0.0, "1": 13.2, "2": 13.2, "12": 0.0}},
        {"pos": 1, "src": 1, "dst": 0, "step": 6.6, "s_src": 6.6, "s_dst": 6.6, "src_index": 1, "out_index": 1, "itf": {"zero_pad": 2}},
    ]
    v = Verdict("ok", "148069831", ("back_qr",))
    rows = [SlabResult(1, 1, 1, 0, 1, v), SlabResult(2, 1, 2, 0, 2, v)]  # row 2 written, then the power went
    st, itf, surveyed = rebuild_state(events, rows, cfg)
    assert surveyed and isinstance(st, State)
    assert st.position == 2 and st.picked_from[1] == 2 and st.out_count[0] == 2
    assert st.tops[1] == pytest.approx(0.0) and st.tops[0] == pytest.approx(13.2)
    assert itf["zero_pad"] == 2


def test_batchwriter_reopen_drops_torn_row(tmp_path):
    w = BatchWriter(tmp_path, "b5")
    w.add(SlabResult(1, 1, 1, 0, 1, Verdict("ok", "148069831", ("back_qr", "back_barcode"), "", "PSA", "x")))
    with (tmp_path / "b5" / "certs.csv").open("a") as f:
        f.write("b5,2,1,2,0")  # power cut mid-row
    w2 = BatchWriter.reopen(tmp_path / "b5")
    assert [r.position for r in w2.rows] == [1]
    assert w2.rows[0].verdict.sources == ("back_qr", "back_barcode")
    assert (tmp_path / "b5" / "certs.csv").read_text().count("\n") == 2


class EStopMotion:
    """SimMotion whose controller loses power (E-stop) at the first motion command for which ``when()``
    is true: that command raises ControllerLost and the controller comes back reset (unhomed), like
    FluidNC after its 24 V returns. ``after`` counts motion commands issued after the loss."""

    def __init__(self, inner, when):
        self.inner, self.when, self.fired, self.after = inner, when, False, 0

    def _tick(self):
        if self.fired:
            self.after += 1
        elif self.when():
            self.fired = True
            self.inner.homed = False
            raise ControllerLost("Lost the controller: its USB serial port went away (E-stop, test)")

    def home(self):
        self.after += self.fired
        self.inner.home()

    def move(self, feed, **kw):
        self._tick()
        self.inner.move(feed, **kw)

    def probe(self, z, feed):
        self._tick()
        return self.inner.probe(z, feed)

    def wait_idle(self):
        pass

    def position(self):
        return self.inner.position()

    def pins(self):
        return self.inner.pins()

    @property
    def homed(self):
        return self.inner.homed

    @property
    def probe_targets(self):
        return self.inner.probe_targets


def test_estop_with_a_slab_in_the_cup_stops_cleanly_and_resume_rehomes(tmp_path):
    """CONTRACT.md E-stop: the serial port vanishes mid-transfer. The run must become a clean Stop that
    moves nothing more, tell the operator which pocket the held slab goes back on, and the next run
    must home first; every slab is then moved exactly once."""
    cfg = from_layout()
    original = _stacks(cfg)
    world = SimWorld(cfg, stacks={k: list(v) for k, v in original.items()})
    writer = BatchWriter(tmp_path, "b6")
    motion = EStopMotion(SimMotion(world), when=lambda: bool(world.held) and len(writer.rows) == 2)
    r1 = Runner(cfg, motion, SimVacuum(world), SimLights(), SimCamera(world, "head"), SimCamera(world, "station"), writer,
                gate=SimGate(world), log=lambda *_: None)
    with pytest.raises(Stop, match="lost power") as e:
        r1.run()
    assert "pocket 2" in str(e.value) and "homes first" in str(e.value)
    assert motion.fired and motion.after == 0  # nothing tried to move after the loss (no put-back, no park)
    assert not world.vacuum_on  # Pi side shut the valves
    events = read_journal(tmp_path / "b6" / "journal.jsonl")
    assert events[-1].get("lost_controller") is True
    # operator: slab off the cup, face-down back on top of pocket 2
    assert world.held
    for slab in reversed(world.held):
        world.stacks[2].append(slab)
    world.held, world.gripping = [], False
    r2 = Runner(cfg, motion, SimVacuum(world), SimLights(), SimCamera(world, "head"), SimCamera(world, "station"),
                BatchWriter.reopen(tmp_path / "b6"), gate=SimGate(world), log=lambda *_: None)
    summary = r2.resume()  # SimMotion raises Crash on any move before homing, so this proves resume homes first
    _check_complete(cfg, world, original, tmp_path / "b6", summary)


def test_low_pad_never_probes_past_the_z_soft_limit(tmp_path):
    """Regression: with the pad trigger at machine Z -7.4 (head lower than the CAD's -2, still inside the
    calibration window), lifting the last slab of a stack probed toward c(s - 7) = Z -8.01, past the -8
    soft limit (an ALARM on the real controller, a Crash in the simulator). Targets are now clamped to -7.5."""
    cfg = dataclasses.replace(from_layout(), pad_trigger_c=-7.4)
    original = _stacks(cfg, per_pocket=1, sources=2)
    world = SimWorld(cfg, stacks={k: list(v) for k, v in original.items()})
    r = _runner(cfg, world, BatchWriter(tmp_path, "b7"))
    summary = r.run()
    _check_complete(cfg, world, original, tmp_path / "b7", summary)
    assert min(r.m.probe_targets) >= Z_FLOOR - 1e-9
