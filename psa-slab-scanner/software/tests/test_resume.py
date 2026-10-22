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
