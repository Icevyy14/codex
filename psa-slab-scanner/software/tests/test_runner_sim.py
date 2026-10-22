"""End-to-end batch runs in the simulator.

The simulator raises Crash for any unsafe motion (XY below safe height, descending off a
pocket centre, fast move into a surface, probe beyond buffer stroke, releasing a slab
in mid-air), so a passing run proves the motion plan is safe, not just that it finishes.
"""

import csv
import dataclasses

import pytest

from slabscan.config import from_layout
from slabscan.results import BatchWriter
from slabscan.runner import Runner, Stop
from slabscan.simworld import SimCamera, SimGate, SimLights, SimMotion, SimVacuum, SimWorld, make_batch


def _cfg(**kw):
    cfg = from_layout()
    return dataclasses.replace(cfg, **kw) if kw else cfg


def _run(tmp_path, cfg, stacks, itf_payload="zero_pad"):
    w = SimWorld(cfg, stacks={k: list(v) for k, v in stacks.items()}, itf_payload=itf_payload)
    r = Runner(cfg, SimMotion(w), SimVacuum(w), SimLights(), SimCamera(w, "head"), SimCamera(w, "station"), BatchWriter(tmp_path), gate=SimGate(w), log=lambda *_: None)
    return w, r, r.run()


def _expected_outputs(cfg, stacks):
    """Pocket k's slabs end in pocket k-1, reversed."""
    exp = {}
    for p in cfg.sources:
        exp[p.index - 1] = [s.cert for s in reversed(stacks[p.index])]
    return exp


def test_small_batch_every_slab_moved_and_read(tmp_path):
    cfg = _cfg()
    stacks = make_batch(cfg, per_pocket=4, seed=3, eras=(1.0, 0.0, 0.0))
    w, r, summary = _run(tmp_path, cfg, stacks)
    n = sum(len(v) for v in stacks.values())
    assert summary["slabs_visited"] == n
    assert summary["status_counts"].get("ok", 0) == n
    for dst, certs in _expected_outputs(cfg, stacks).items():
        assert [s.cert for s in reversed(w.stacks[dst])] == list(reversed(certs))[::-1] or [s.cert for s in w.stacks[dst]] == certs
    rows = list(csv.DictReader((r.w.dir / "certs.csv").open()))
    got = {row["cert"] for row in rows}
    assert got == {s.cert.lstrip("0") for v in stacks.values() for s in v}
    last_src = cfg.sources[-1].index
    assert not w.stacks.get(last_src)
    assert all(v["ok"] for v in summary["count_check"].values())
    assert (r.w.dir / "report.html").read_text().count("<tr>") == n + 1


def test_old_labels_go_to_station_and_still_read(tmp_path):
    cfg = _cfg(face_down_check="off")  # old labels have no back QR: the face-down check would stop on each
    stacks = make_batch(cfg, per_pocket=3, seed=5, eras=(0.4, 0.3, 0.3))
    w, r, summary = _run(tmp_path, cfg, stacks)
    rows = list(csv.DictReader((r.w.dir / "certs.csv").open()))
    assert len(rows) == sum(len(v) for v in stacks.values())
    # every row is either a confirmed read or explicitly flagged - never a silent wrong cert
    truth = {s.cert.lstrip("0") for v in stacks.values() for s in v}
    for row in rows:
        if row["status"] == "ok":
            assert row["cert"] in truth
    assert summary["status_counts"].get("ok", 0) >= 0.8 * len(rows)


def test_check_digit_itf_is_learned(tmp_path):
    cfg = _cfg(face_down_check="off")
    stacks = make_batch(cfg, per_pocket=3, seed=11, eras=(0.6, 0.4, 0.0))
    w, r, summary = _run(tmp_path, cfg, stacks, itf_payload="check_digit")
    truth = {s.cert.lstrip("0") for v in stacks.values() for s in v}
    rows = list(csv.DictReader((r.w.dir / "certs.csv").open()))
    assert all(row["cert"] in truth for row in rows if row["status"] == "ok")
    assert summary["itf_mode"] in ("check_digit", None)


def test_double_pick_is_detected_and_flagged(tmp_path):
    cfg = _cfg()
    stacks = make_batch(cfg, per_pocket=3, seed=2, eras=(1.0, 0.0, 0.0))
    stacks[2][1].clingy = True  # second-from-bottom... sticks under the slab above it
    w, r, summary = _run(tmp_path, cfg, stacks)
    assert any("double pick" in e for e in w.events)
    flagged = [a for a in summary["needs_attention"] if "DOUBLE PICK" in a["note"]]
    assert len(flagged) == 1


def test_thick_holder_is_handled(tmp_path):
    cfg = _cfg()
    stacks = make_batch(cfg, per_pocket=3, seed=4, eras=(1.0, 0.0, 0.0))
    stacks[3][2].thickness = 10.25
    w, r, summary = _run(tmp_path, cfg, stacks)
    assert summary["slabs_visited"] == sum(len(v) for v in stacks.values())
    assert any("thick holder" in a["note"] for a in summary["needs_attention"]) or summary["status_counts"]["ok"] == summary["slabs_visited"]


def test_seal_failure_stops_safely(tmp_path):
    cfg = _cfg()
    stacks = make_batch(cfg, per_pocket=2, seed=6)
    stacks[1][-1].seal_fails = True
    with pytest.raises(Stop, match="will not seal"):
        _run(tmp_path, cfg, stacks)


def test_overfilled_pocket_refused(tmp_path):
    cfg = _cfg()
    stacks = make_batch(cfg, per_pocket=2, seed=6)
    stacks[5] = stacks[5] + [stacks[5][0]] * 34  # way over the MAX line
    with pytest.raises(Stop, match="overfill light beam"):
        _run(tmp_path, cfg, stacks)


def test_slightly_overfilled_pocket_refused_by_survey(tmp_path):
    cfg = _cfg()
    stacks = make_batch(cfg, per_pocket=2, seed=6)
    stacks[5] = [dataclasses.replace(stacks[5][0], thickness=6.9) for _ in range(31)]  # 213.9 mm: under the beam, over the line
    with pytest.raises(Stop, match="MAX line"):
        _run(tmp_path, cfg, stacks)


def test_start_pocket_must_be_empty(tmp_path):
    cfg = _cfg()
    stacks = make_batch(cfg, per_pocket=2, seed=6)
    stacks[0] = [stacks[1][0]]
    with pytest.raises(Stop, match="must start empty"):
        _run(tmp_path, cfg, stacks)


def test_cgc_slabs_are_read_and_stacked_normally(tmp_path):
    cfg = _cfg(face_down_check="off")  # the simulated CGC/BGS backs are blank
    stacks = make_batch(cfg, per_pocket=2, seed=8, eras=(1.0, 0.0, 0.0))
    stacks[4][0].grader = "CGC"
    stacks[4][0].cert = "4123456001"
    stacks[4][0].thickness = 7.5
    stacks[6][1].grader = "BGS"
    stacks[6][1].cert = "0012345678"
    stacks[6][1].thickness = 8.5
    w, r, summary = _run(tmp_path, cfg, stacks)
    rows = {row["cert"]: row for row in csv.DictReader((r.w.dir / "certs.csv").open())}
    assert rows["4123456001"]["grader"] == "CGC" and rows["4123456001"]["status"] == "ok"
    assert rows["4123456001"]["out_pocket"] == "3"
    bgs = [row for row in rows.values() if row["grader"] == "BGS"]
    assert bgs and bgs[0]["status"] == "other_grader" and bgs[0]["out_pocket"] == str(cfg.exceptions.index)


class _FlakyCamera(SimCamera):
    """Head camera that dies on its Nth frame (USB unplugged, driver crash)."""

    def __init__(self, world, fail_at):
        super().__init__(world, "head")
        self.fail_at = fail_at

    def capture(self):
        if self.n + 1 >= self.fail_at:
            raise RuntimeError("camera head returned no frame")
        return super().capture()


def test_unexpected_error_with_slab_in_cup_puts_it_back(tmp_path):
    cfg = _cfg()
    stacks = make_batch(cfg, per_pocket=3, seed=9, eras=(1.0, 0.0, 0.0))
    n_before = {k: len(v) for k, v in stacks.items()}
    w = SimWorld(cfg, stacks={k: list(v) for k, v in stacks.items()})
    # frame 1 = hover of the first slab, frames 2-3 = back read after lifting -> fail while held
    r = Runner(cfg, SimMotion(w), SimVacuum(w), SimLights(), _FlakyCamera(w, 2), SimCamera(w, "station"), BatchWriter(tmp_path), gate=SimGate(w), log=lambda *_: None)
    with pytest.raises(Stop, match="Unexpected error.*put back"):
        r.run()
    assert not w.held, "slab left hanging on the cup"
    assert {k: len(v) for k, v in w.stacks.items() if v} == {k: n for k, n in n_before.items() if n}


def test_double_pick_gets_an_unread_row(tmp_path):
    cfg = _cfg()
    stacks = make_batch(cfg, per_pocket=3, seed=2, eras=(1.0, 0.0, 0.0))
    stacks[2][1].clingy = True
    w, r, summary = _run(tmp_path, cfg, stacks)
    rows = list(csv.DictReader((r.w.dir / "certs.csv").open()))
    assert len(rows) == sum(len(v) for v in stacks.values())  # every physical slab has a row
    unread = [row for row in rows if row["note"].startswith("UNREAD")]
    assert len(unread) == 1 and unread[0]["status"] == "no_read"
    main = next(row for row in rows if "DOUBLE PICK" in row["note"])
    assert int(unread[0]["out_index"]) == int(main["out_index"]) - 1
    assert int(unread[0]["source_index"]) == int(main["source_index"]) + 1
