"""The learned face-down check (slabscan/facedown.py, Runner._check_face_down in "learned" mode), in the simulator.

A slab without a back-label code (PSA or CGC back QR, CGC 2020-23 back barcode) may be picked only when its card window
matches the card backs of proven face-down slabs (back-label code seen, or confirmed by the operator). Most tests use the
hypothetical "open" head (sim.HEADS), whose foot leaves face_down_window_mm clear. Today's CAD head (lens 5 mm toward the
label, trimmed foot) leaves it clear too; with the round-2 CAD head ("cad_r2") the foot hides the window, and the check
must refuse.
"""

import csv
import dataclasses
import json

import cv2
import numpy as np
import pytest

from slabscan import facedown, sim
from slabscan.certs import CodeRead, Verdict
from slabscan.config import from_layout, load
from slabscan.facedown import CardBackRefs, compare, describe, frame_view_mm
from slabscan.results import BatchWriter
from slabscan.runner import Runner, Stop, last_face_down_stop, read_journal, rebuild_state
from slabscan.sim import HEAD_VIEW_MM, Degrade, head_view
from slabscan import simworld
from slabscan.simworld import Crash, SimCamera, SimCarry, SimGate, SimLights, SimMotion, SimSlab, SimVacuum, SimWorld

THRESHOLD = 0.6  # cli.SIM_FACE_DOWN_THRESHOLD: picked on the simulator's synthetic backs
# Test slabs 24..31 (``_slab`` numbering) show no glare spot on the card window, so every QR one becomes a reference;
# about a third of the others carry one, and a frame with glare on the window never becomes a reference.
CLEAN = 24


def _cfg(**kw):
    base = from_layout()
    return dataclasses.replace(base, face_down_threshold=THRESHOLD, face_down_threshold_sig=facedown.threshold_tag(base.face_down_window_mm), **kw)


def _slab(i: int, kind: str) -> SimSlab:
    """kind: qr (2017+ label, back QR), old (no back code), up (old label, loaded FACE-UP), up_plain (the same with a plain
    one-colour card front), jp_qr / jp_old (Japanese card back), cgc (CGC slab face-down), cgc_up (CGC face-up)."""
    cert = str(150000007 + 7919 * i)
    s = SimSlab(cert, 6.6, "2017+" if kind in ("qr", "jp_qr") else "old")
    if kind.startswith("jp"):
        s.back = "pokemon_jp"
    if kind.startswith("up"):
        s.face_down = False
        s.front = "plain" if kind == "up_plain" else "art"
    if kind.startswith("cgc"):
        s.grader, s.cert = "CGC", str(4123456001 + i)
        s.face_down = kind == "cgc"
    return s


def _world(cfg, picks: list[str], head: str = "open", start: int = 0) -> SimWorld:
    """One stack in pocket 1, slabs listed in PICK order (top first)."""
    stack = [_slab(start + i, k) for i, k in enumerate(picks)][::-1]
    return SimWorld(cfg, stacks={1: stack, **{p.index: [] for p in cfg.sources if p.index != 1}}, head=head)


def _runner(cfg, world, tmp_path, refs=None, batch="b", writer=None):
    writer = writer or BatchWriter(tmp_path, batch)
    return Runner(cfg, SimMotion(world), SimVacuum(world), SimLights(), SimCamera(world, "head"), SimCamera(world, "station"), writer,
                  gate=SimGate(world), log=lambda *_: None, refs=refs if refs is not None else CardBackRefs(None, cfg.face_down_window_mm),
                  carry=SimCarry(world))


def _resume(cfg, world, tmp_path, refs, batch="b", **kw):
    r = _runner(cfg, world, tmp_path, refs=refs, writer=BatchWriter.reopen(tmp_path / batch))
    return r, r.resume(**kw)


def _rows(tmp_path, batch="b"):
    return list(csv.DictReader((tmp_path / batch / "certs.csv").open()))


def _kinds(tmp_path, batch="b"):
    return [x["face_down"].split("(")[0] for x in _rows(tmp_path, batch)]


# ---------------------------------------------------------------------- the run
def test_a_face_down_old_label_passes_once_enough_qr_references_exist(tmp_path):
    cfg = _cfg()
    world = _world(cfg, ["qr"] * 6 + ["old", "old"], start=CLEAN)
    r = _runner(cfg, world, tmp_path)
    summary = r.run()
    rows = _rows(tmp_path)
    assert _kinds(tmp_path) == ["qr"] * 6 + ["learned"] * 2
    assert all(float(x["face_down"][8:-1]) >= THRESHOLD for x in rows[6:])
    events = [e for e in read_journal(r.journal) if "face_down_learned" in e]
    assert len(events) == 2 and all(e["score"] >= THRESHOLD and e["refs"] == 6 and e["baseline"] < facedown.BASELINE_MAX for e in events)
    assert all("pos" not in e and e["position"] in (7, 8) for e in events)  # "pos" + "src" is a finished transfer to rebuild_state
    assert summary["face_down"]["counts"] == {"qr": 6, "learned": 2} and len(summary["face_down"]["learned"]) == 2
    assert "learned(" in (tmp_path / "b" / "report.html").read_text()
    frac, n = r.refs.static_fraction()
    # the open head leaves the window clear: under half of STATIC_MAX (on today's 330 mm2 window a few card pixels vote by chance: 3 %)
    assert frac < facedown.STATIC_MAX / 2 and n == 6


def test_a_face_up_old_label_still_stops_in_learned_mode(tmp_path):
    cfg = _cfg()
    world = _world(cfg, ["qr"] * 6 + ["up"], start=CLEAN)
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match=r"could not be confirmed FACE-DOWN .*best match with a known card back 0\.\d\d < threshold 0\.60"):
        r.run()
    assert not world.gripping and not world.held and len(r.w.rows) == 6  # the face-up slab was never touched
    assert world.stacks[1][-1].face_down is False and r.refs.n_refs == 6
    stop = [e for e in read_journal(r.journal) if "stop" in e][-1]
    assert stop["face_down_stop"] == 1 and "best match" in stop["why"]  # journaled with its pocket and reason


def test_a_batch_with_a_learned_acceptance_can_be_resumed(tmp_path):
    """The face_down_learned event used to carry "pos", which rebuild_state() read as a finished transfer (KeyError 'src')."""
    cfg = _cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    world = _world(cfg, ["qr"] * 6 + ["old", "up", "old"], start=CLEAN)
    with pytest.raises(Stop, match="could not be confirmed FACE-DOWN"):
        _runner(cfg, world, tmp_path, refs=refs).run()
    assert _kinds(tmp_path) == ["qr"] * 6 + ["learned"]
    world.stacks[1][-1].face_down = True  # the operator turns the face-up slab over
    _, summary = _resume(cfg, world, tmp_path, refs)
    assert summary["slabs_visited"] == 9 and _kinds(tmp_path) == ["qr"] * 6 + ["learned"] * 3
    # an event with "pos" but no "src" is never taken for a transfer
    st, _, _ = rebuild_state([{"survey": {"1": 50.0}}, {"face_down_learned": 1, "pos": 3}], [], cfg)
    assert st.position == 0


def test_learned_acceptances_never_become_references(tmp_path):
    cfg = _cfg()
    refs = CardBackRefs(tmp_path / "card_backs.npz", cfg.face_down_window_mm)
    _runner(cfg, _world(cfg, ["qr"] * 5 + ["old"] * 3, start=CLEAN), tmp_path, refs=refs).run()
    assert refs.n_refs == 5 and refs.sources() == {"qr": 5}
    assert CardBackRefs(tmp_path / "card_backs.npz", cfg.face_down_window_mm).n_refs == 5  # nor in the file
    d = describe(head_view("150000007", "back", Degrade(mm_per_px=0.05), head="open"), facedown.image_rects(cfg.face_down_window_mm), HEAD_VIEW_MM)
    with pytest.raises(ValueError, match="only"):
        refs.add(d, "learned")


def test_a_batch_that_starts_with_old_labels_stops_then_learns_from_the_operator(tmp_path):
    cfg = _cfg()
    path = tmp_path / "card_backs.npz"
    world = _world(cfg, ["old", "qr", "qr", "qr", "qr", "old"], start=CLEAN + 1)
    with pytest.raises(Stop, match="0 of 5 card-back references"):
        _runner(cfg, world, tmp_path, refs=CardBackRefs(path, cfg.face_down_window_mm)).run()
    assert not world.gripping and not world.held
    refs = CardBackRefs(path, cfg.face_down_window_mm)
    r2, summary = _resume(cfg, world, tmp_path, refs, face_down_ok=True)
    assert summary["slabs_visited"] == 6
    stored = CardBackRefs(path, cfg.face_down_window_mm)
    assert stored.sources() == {"operator": 1, "qr": 4}  # the confirmed slab, then the four QR slabs
    assert _kinds(tmp_path) == ["operator", "qr", "qr", "qr", "qr", "learned"]
    ev = read_journal(r2.journal)
    assert any(e.get("face_down_confirmed") == 1 and e.get("reference", "").startswith("pending") for e in ev)
    # learned from only once the slab was placed, with its cert and back photo: each one can be audited and deleted on its own
    first = _rows(tmp_path)[0]
    ref = next(e for e in ev if "face_down_reference" in e)
    assert ref["by"] == "operator" and ref["position"] == 1 and ref["cert"] == first["cert"] and ref["image_back"] == first["image_back"]
    assert ref["result"].startswith("reference 1")
    assert stored.refs[0].meta["cert"] == first["cert"] and stored.drop(cert=first["cert"]) == 1


def test_face_down_ok_is_refused_unless_the_last_stop_was_a_face_down_stop(tmp_path):
    """The Stop button before a face-up slab, then a resume with a stale face-down tick: refused, nothing moves."""
    cfg = _cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    world = _world(cfg, ["up", "qr"], start=CLEAN)
    r = _runner(cfg, world, tmp_path, refs=refs)
    r.should_stop = lambda: True
    with pytest.raises(Stop, match="Stopped on request"):
        r.run()
    assert last_face_down_stop(read_journal(r.journal)) is None
    with pytest.raises(Stop, match="--face-down-ok refused"):
        _resume(cfg, world, tmp_path, refs, face_down_ok=True)
    assert not world.gripping and world.stacks[1][-1].face_down is False and refs.n_refs == 0
    # without it: the run stops at the face-up slab; only now does --face-down-ok have a slab to confirm
    with pytest.raises(Stop, match="could not be confirmed FACE-DOWN"):
        _resume(cfg, world, tmp_path, refs)
    assert last_face_down_stop(read_journal(tmp_path / "b" / "journal.jsonl")) == 1


def test_a_confirmation_is_for_the_stopped_pocket_only(tmp_path):
    cfg = _cfg()
    world = _world(cfg, ["old"], start=CLEAN)
    r = _runner(cfg, world, tmp_path)
    r.face_down_ok_pocket = 5  # confirmed pocket 5, but the next slab checked is in pocket 1
    with pytest.raises(Stop, match="could not be confirmed FACE-DOWN"):
        r.run()
    assert any(e.get("face_down_ok_unused") == 5 and e["pocket"] == 1 for e in read_journal(r.journal))
    assert not world.gripping and r.face_down_ok_pocket is None


def test_one_wrong_confirmation_does_not_teach_a_card_front(tmp_path, monkeypatch):
    """A face-up slab confirmed by mistake (on the machine it is gripped by its front and placed) leaves a reference of
    its FRONT. The next face-up copy of the same card must still stop: a back known only from operator confirmations
    is not matched until OPERATOR_PROTO_MIN of them agree."""
    cfg = _cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    _runner(cfg, _world(cfg, ["qr"] * 6, start=CLEAN), tmp_path, refs=refs, batch="b1").run()
    same = _slab(CLEAN + 10, "up").cert
    real_front = sim.card_front
    monkeypatch.setattr(sim, "card_front", lambda cert: real_front(same))  # every face-up slab shows the same card's front
    wrong = facedown.describe(head_view(same, "front", Degrade(mm_per_px=0.05, blur_px=1.0, glare=0.3), era="old", head="open", seed=5),
                              facedown.image_rects(cfg.face_down_window_mm), HEAD_VIEW_MM)
    proto, why = refs.add(wrong, "operator", {"cert": same}, cluster=THRESHOLD)
    assert proto == 1 and not refs.usable(1) and refs.usable(0)
    world = _world(cfg, ["up"], start=CLEAN + 11)
    with pytest.raises(Stop, match="known only from 1 of your confirmations"):
        _runner(cfg, world, tmp_path, refs=refs, batch="b2").run()
    assert not world.gripping and not world.held


def test_a_back_qr_seen_from_below_vetoes_an_operator_reference(tmp_path):
    cfg = _cfg()
    r = _runner(cfg, _world(cfg, ["qr"], start=CLEAN), tmp_path)
    r.run()
    d = r.refs.refs[0].desc  # a good card-back descriptor
    r.refs = CardBackRefs(None, cfg.face_down_window_mm)
    v = Verdict("ok", "150000007", ("front_qr",))
    r._pending_ref = (d, 1, "operator", {})
    r._settle_reference(1, v, [CodeRead("150000007", "front_qr", "QRCode", "https://www.psacard.com/cert/150000007", "front")], "images/0001_back.jpg")
    assert r.refs.n_refs == 0 and r._pending_ref is None
    r._pending_ref = (d, 1, "operator", {})
    r._settle_reference(2, v, [CodeRead("150000007", "front_barcode", "ITF", "0150000007", "front")], "images/0002_back.jpg")
    assert r.refs.n_refs == 1 and r.refs.refs[0].meta["cert"] == "150000007"
    results = [e["result"] for e in read_journal(r.journal) if "face_down_reference" in e][-2:]  # (the run's own QR slab came first)
    assert "FACE-UP" in results[0] and results[1].startswith("reference 1")


def test_a_code_proof_is_learned_only_when_the_slabs_own_read_agrees(tmp_path):
    """A back-label code seen from above is learned from after the placement, and only with an 'ok' read of that same cert."""
    cfg = _cfg()
    r = _runner(cfg, _world(cfg, ["qr"], start=CLEAN), tmp_path)
    r.run()
    d = r.refs.refs[0].desc
    r.refs = CardBackRefs(None, cfg.face_down_window_mm)
    proof = {"proof": "psa_qr", "proof_cert": "150000007"}
    cases = [(Verdict("ok", "150000007", ("back_qr",)), {**proof, "proof_cert": "27720238"}),  # a neighbour's QR proved it
             (Verdict("conflict", None, ("back_qr", "front_barcode")), proof),  # its own read disagrees
             (Verdict("ok", "150000007", ("back_qr",)), proof)]
    for pos, (v, pr) in enumerate(cases, start=1):
        r._pending_ref = (d, 1, "qr", pr)
        r._settle_reference(pos, v, [], f"images/{pos:04d}_back.jpg")
    results = [e["result"] for e in read_journal(r.journal) if "face_down_reference" in e][-3:]
    assert "is not this slab's cert" in results[0] and "not 'ok'" in results[1] and results[2].startswith("reference 1")
    meta = r.refs.refs[0].meta
    assert r.refs.n_refs == 1 and (meta["cert"], meta["proof"], meta["position"], meta["image_back"]) == ("150000007", "psa_qr", 3, "images/0003_back.jpg")


@pytest.mark.parametrize("hover_check", [True, False])
def test_a_neighbours_back_qr_over_a_face_up_slab_teaches_nothing(tmp_path, monkeypatch, hover_check):
    """One false code proof: a neighbour's back QR is the only code read from above a face-UP slab, so it 'proves' the slab
    face-down and the cup takes it by its front. Its card window must not become a reference (it used to, at once, and
    every later face-up copy of that card then passed the learned check): a code proof is learned from only after the
    placement, with an 'ok' read of the same cert. The slab goes to the exception pocket, and the next face-up copy
    of the same card still stops untouched."""
    cfg = _cfg(hover_check=hover_check)
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    same = _slab(CLEAN + 60, "up").cert
    real_front = sim.card_front
    monkeypatch.setattr(sim, "card_front", lambda cert: real_front(same))  # every face-up slab shows the same card's front
    monkeypatch.setattr(simworld, "_VIEW_CACHE", {})
    touched = []
    real_hold = SimVacuum.hold

    def hold(self):  # the machine grips the front (the damage this test is about); the simulator would stop on a Crash
        try:
            real_hold(self)
        except Crash as e:
            touched.append(str(e))
            self.w.gripping = True

    monkeypatch.setattr(SimVacuum, "hold", hold)
    world = _world(cfg, ["qr"] * 12 + ["up"], start=CLEAN)
    neighbour = CodeRead("27720238", "back_qr", "QRCode", "http://psacard.com/cert/27720238", "back", "PSA")
    real_read = Runner._read

    def read(self, frames, camera, distance_mm=None):
        reads, unparsed = real_read(self, frames, camera, distance_mm)
        top = world.stacks[1][-1] if world.stacks[1] else None
        hover = camera == "back" and distance_mm and distance_mm > float(cfg.cam_head["lens_to_label_mm"]) + 1
        if hover and top is not None and not top.face_down:
            return [dataclasses.replace(neighbour, frame=f"back{self._frame_seq}")], []
        return reads, unparsed

    monkeypatch.setattr(Runner, "_read", read)
    r = _runner(cfg, world, tmp_path, refs=refs)
    r.run()
    up = _rows(tmp_path)[-1]
    # (the simulator reads nothing of this face-up front label from above; without hover_check nothing is read at all)
    assert len(touched) == 1 and up["face_down"] == "qr" and up["out_pocket"] == str(cfg.exceptions.index)
    assert (up["status"], "cert 27720238" in up["note"]) == (("conflict", True) if hover_check else ("no_read", False))
    assert len(refs.protos()) == 1 and not any(x.meta.get("cert") in (_slab(CLEAN + 12, "up").cert, "27720238") for x in refs.refs)
    ref = [e for e in read_journal(r.journal) if "face_down_reference" in e][-1]
    assert ref["position"] == 13 and ref["result"].startswith("not used as a reference")
    world2 = _world(cfg, ["up"], start=CLEAN + 30)
    with pytest.raises(Stop, match="could not be confirmed FACE-DOWN"):
        _runner(cfg, world2, tmp_path, refs=refs, batch="b2").run()
    assert len(touched) == 1 and not world2.gripping


def test_one_odd_reference_does_not_let_a_front_through(tmp_path, monkeypatch):
    """A match needs MATCH_K slabs of one back design (on real slabs one odd back matched a blue front at 0.62, the
    second-best never above 0.44). Here a card FRONT is a reference (a false proof): the next copy of that card matches
    it far above the threshold, but no second slab agrees, so it is not accepted; the same slab twice is one slab."""
    cfg = _cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    _runner(cfg, _world(cfg, ["qr"] * 6, start=CLEAN), tmp_path, refs=refs).run()
    same = _slab(CLEAN + 60, "up").cert
    real_front = sim.card_front
    monkeypatch.setattr(sim, "card_front", lambda cert: real_front(same))
    rects, w, tag = facedown.image_rects(cfg.face_down_window_mm), cfg.face_down_window_mm, cfg.face_down_threshold_sig
    deg = Degrade(mm_per_px=0.05, blur_px=1.0)
    # two copies of the card face-up; the first one without a glare spot on the window, so that it can become a reference
    fronts = [facedown.describe(head_view(_slab(CLEAN + 60 + i, "up").cert, "front", deg, era="old", head="open"), rects, HEAD_VIEW_MM)
              for i in range(12)]
    front = next(d for d in fronts if d.glare == 0.0)
    copy = next(d for d in fronts if d is not front)
    for _ in range(2):  # the same slab learned twice
        proto, _ = refs.add(front, "qr", {"cert": same}, cluster=THRESHOLD)
    assert proto == 1 and refs.usable(1) and refs.protos()[1] == 2 and compare(copy, front).score > THRESHOLD + 0.1
    ok, why, m = facedown.learned_match(refs, copy, THRESHOLD, 5, w, tag)
    assert not ok and "only 1 known card back(s) of one design match it" in why and m.proto == 1
    monkeypatch.setattr(facedown, "MATCH_K", 1)  # the old rule: the single best reference
    assert facedown.learned_match(refs, copy, THRESHOLD, 5, w, tag)[0]


def test_a_japanese_back_stops_until_three_confirmations_teach_it(tmp_path):
    cfg = _cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    world = _world(cfg, ["qr"] * 6 + ["jp_old"] * 5, start=CLEAN)
    with pytest.raises(Stop, match=r"best match with a known card back 0\.\d\d < threshold"):
        _runner(cfg, world, tmp_path, refs=refs).run()
    assert len(refs.protos()) == 1
    for _ in range(8):  # the operator confirms each Japanese slab the check stops on
        try:
            _, summary = _resume(cfg, world, tmp_path, refs, face_down_ok=True)
            break
        except Stop as e:
            # it matches the Japanese back, but not enough confirmations yet; or, once they are enough, only one of them
            # (facedown.MATCH_K: here the slab lies a few mm off where two of the three references lay)
            assert "known only from" in str(e) or "only 1 known card back(s) of one design" in str(e)
    assert summary["slabs_visited"] == 11
    jp = [p for p in refs.protos() if p != 0]
    assert len(jp) == 1 and refs.sources()["operator"] >= facedown.OPERATOR_PROTO_MIN and refs.usable(jp[0])
    kinds = _kinds(tmp_path)
    assert kinds[6:6 + facedown.OPERATOR_PROTO_MIN] == ["operator"] * facedown.OPERATOR_PROTO_MIN and kinds[-1] == "learned"


def test_the_reference_file_persists_across_runner_instances(tmp_path):
    cfg = _cfg()
    path = tmp_path / "config" / "card_backs.npz"
    _runner(cfg, _world(cfg, ["qr"] * 6, start=CLEAN), tmp_path, refs=CardBackRefs(path, cfg.face_down_window_mm), batch="b1").run()
    assert path.exists()
    refs = CardBackRefs(path, cfg.face_down_window_mm)
    assert refs.n_refs == 6 and refs.baseline is not None and "loaded 6 references" in refs.note
    assert refs.static_fraction()[0] < facedown.STATIC_MAX / 2 and refs.refs[0].desc.levels  # the levels are stored too
    # a later batch of older labels only: matched against the first batch's references from its first slab
    _runner(cfg, _world(cfg, ["old"] * 3, start=50), tmp_path, refs=refs, batch="b2").run()
    assert _kinds(tmp_path, "b2") == ["learned"] * 3
    # another card window makes the stored references useless: they are not used
    other = CardBackRefs(path, ((-20.0, -33.0, 20.0, -18.0),))
    assert other.n_refs == 0 and "another card window" in other.note


def test_with_todays_cad_head_the_learned_check_works(tmp_path):
    """Today's CAD head (cad/out/heads_cad.json, lens 5 mm toward the label) leaves face_down_window_mm clear: the QR
    slabs become references, old labels are accepted by the card-back match, and a face-up slab still stops untouched."""
    cfg = _cfg()
    world = _world(cfg, ["qr"] * 10 + ["old", "old", "up"], head="cad", start=CLEAN)  # (CLEAN is glare-free for the open head only)
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match=r"could not be confirmed FACE-DOWN .*best match with a known card back 0\.\d\d < threshold 0\.60"):
        r.run()
    assert _kinds(tmp_path) == ["qr"] * 10 + ["learned"] * 2
    assert r.refs.n_refs >= cfg.face_down_min_refs and r.refs.static_fraction()[0] < 0.02  # nothing of the head in the window
    assert not world.gripping and not world.held and world.stacks[1][-1].face_down is False


def test_with_the_round2_cad_head_the_learned_check_refuses(tmp_path):
    """The round-2 CAD head (lens on the cup axis, the wide foot) hides face_down_window_mm: every frame shows the same
    foot, so a face-up slab would 'match'. The empty-pocket baseline catches it: no references are collected and nothing
    is accepted."""
    cfg = _cfg()
    world = _world(cfg, ["qr"] * 6 + ["old"], head="cad_r2")
    r = _runner(cfg, world, tmp_path)
    # (the aim check sees the foot's edge in the view over an empty pocket too, for a card window it reaches)
    with pytest.raises(Stop, match="looks like the view over an empty pocket .* the head hides it|over an empty pocket the head camera sees edges") as e:
        r.run()
    assert r.refs.n_refs == 0 and r.refs.rejected == {"card window looks like the empty-pocket view (the head hides it)": 6}
    assert "becomes a reference" not in str(e.value)  # a confirmation would not teach it anything either
    assert not world.gripping and not world.held


def _foot(y0: float, grey: int = 52):
    """sim.HEADS "open" with the foot's label-side edge at y0 (mm from the cup axis, 62-75 mm above the cup face). Seen
    from the lens (5 mm toward the label), y0 -12.35 hides 47 % of face_down_window_mm and -13.75 hides 73 %."""
    parts = [list(p) for p in sim.HEADS["open"]]
    parts[2] = [-11.0, y0, 11.0, 45.0, 62.0, 75.0, grey]
    parts[3] = [11.0, y0, 30.5, -y0, 62.0, 75.0, grey]
    return [tuple(p) for p in parts]


@pytest.mark.parametrize("name, parts, refused", [
    # the foot hides about 45 % of the window: its edge looks unlike the empty view's (the card is brighter than the foot,
    # the pocket darker), so the pattern guard misses it. The aim check sees its edge in the view over an empty pocket
    # (the level check would see it after 5 proven slabs)
    ("foot_y-12.35", _foot(-12.35), r"over an empty pocket the head camera sees edges where only the pad should show"),
    # the same foot as dark as the empty pocket: no edge in the empty view at all
    ("foot_y-12.35_black", _foot(-12.35, grey=30), r"of the card window shows the same thing on every proven slab as over an empty pocket"),
    # 75 % hidden: the pattern guard sees it on every slab
    ("foot_y-13.75", _foot(-13.75), r"looks like the (view over an empty pocket|empty-pocket view)|over an empty pocket the head camera sees edges"),
    # the round-2 CAD head without the M10 nut and rod end: a plain foot fills the window
    ("cad_r2_no_nut", [p for p in sim.HEADS["cad_r2"] if p[6] not in (150, 170)], r"nothing visible in the card window"),
])
def test_a_head_that_hides_part_of_the_window_is_refused(tmp_path, monkeypatch, name, parts, refused):
    monkeypatch.setitem(sim.HEADS, name, parts)
    cfg = _cfg()
    world = _world(cfg, ["qr"] * 10 + ["up"], head=name, start=CLEAN)
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match=refused):
        r.run()
    assert not world.gripping and not world.held and world.stacks[1][-1].face_down is False  # the face-up slab: untouched
    assert "learned check not active" in r.face_down_status() or r.refs.n_refs < cfg.face_down_min_refs


def test_a_plain_face_up_card_front_with_glare_is_not_accepted(tmp_path):
    """A one-colour front shows only a glare spot in the window. Its texture is above the floor, and the spot can
    correlate with glare on the references, but it carries far less pattern than any card back."""
    cfg = _cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    _runner(cfg, _world(cfg, ["qr"] * 6, start=CLEAN), tmp_path, refs=refs, batch="b1").run()
    deg = Degrade(mm_per_px=0.05, blur_px=1.0, glare=0.3)
    rects, w, tag = facedown.image_rects(cfg.face_down_window_mm), cfg.face_down_window_mm, cfg.face_down_threshold_sig
    textured = []
    for i in range(60):
        cert = str(160000001 + 7907 * i)
        d = facedown.describe(head_view(cert, "front", deg, era="old", head="open", front="plain"), rects, HEAD_VIEW_MM)
        ok, why, m = facedown.learned_match(refs, d, THRESHOLD, 5, w, tag)
        assert not ok, (cert, why, m)
        if d.texture >= facedown.MIN_TEXTURE:
            textured.append((cert, why))
    assert textured and all("nothing visible" not in why for _, why in textured)  # glare gave these some texture
    # end to end: such a slab, face-up, on top of a stack
    world = _world(cfg, ["up_plain"], start=CLEAN + 20)
    world.stacks[1][-1].cert = textured[0][0]
    with pytest.raises(Stop, match="could not be confirmed FACE-DOWN"):
        _runner(cfg, world, tmp_path, refs=refs, batch="b2").run()
    assert not world.gripping


def test_a_face_down_cgc_slab_is_proven_by_its_back_qr_and_a_face_up_one_stops(tmp_path):
    """Regression: a CGC code seen from above always stopped the run ('those sit on the FRONT label'), and in learned
    mode it also blocked the card-window match. Real CGC backs carry a QR with the grade: it proves the slab face-down
    and teaches the learned check like a PSA back QR. A face-up CGC slab shows its front barcode: FACE-UP stop."""
    cfg = _cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    world = _world(cfg, ["qr"] * 5 + ["cgc", "cgc_up"], start=CLEAN)
    with pytest.raises(Stop, match="the top slab is FACE-UP"):
        _runner(cfg, world, tmp_path, refs=refs).run()
    rows = _rows(tmp_path)
    assert rows[5]["grader"] == "CGC" and rows[5]["status"] == "ok" and rows[5]["face_down"] == "qr"
    assert any(r.meta.get("proof") == "cgc_qr" for r in refs.refs)  # a reference, as a PSA back-QR slab is
    assert not world.gripping and world.stacks[1][-1].face_down is False


def test_learned_mode_waits_for_a_measured_threshold_for_this_window(tmp_path):
    cfg = dataclasses.replace(from_layout())  # the default config: learned, but no threshold yet
    assert cfg.face_down_check == "learned" and cfg.face_down_threshold is None
    world = _world(cfg, ["qr"] * 6 + ["old"], start=CLEAN)
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match="face_down_threshold is not measured"):
        r.run()
    assert r.refs.n_refs == 6  # references are collected anyway, for when the threshold is set
    assert "learned check not active yet" in r.face_down_status()
    # a threshold measured for another window (or typed in by hand, without its sig) is not used
    for sig in (None, "0123456789ab"):
        other = dataclasses.replace(_cfg(), face_down_threshold_sig=sig)
        why = facedown.learned_ready(r.refs, other.face_down_threshold, 5, other.face_down_window_mm, other.face_down_threshold_sig)
        assert "was not measured for this card window" in why and "run Phase 0 again" in why
    assert facedown.learned_ready(r.refs, 0.4, 5, cfg.face_down_window_mm, _cfg().face_down_threshold_sig).startswith(
        "learned check not active: face_down_threshold 0.40 is below the floor")


def test_learned_mode_waits_until_the_head_view_is_checked_on_this_machine(tmp_path):
    """References from the Phase 0 jig alone never activate it: the window must be seen clear on proven slabs here."""
    cfg = _cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    _runner(cfg, _world(cfg, ["qr"] * 6, start=CLEAN), tmp_path, refs=refs, batch="b1").run()
    seeded = CardBackRefs(None, cfg.face_down_window_mm)
    seeded.set_baseline(refs.baseline)
    for x in refs.refs:
        seeded.add(x.desc, "phase0")
    assert "checked on 5 slabs proven face-down on this machine" in facedown.learned_ready(seeded, THRESHOLD, 5, cfg.face_down_window_mm,
                                                                                         cfg.face_down_threshold_sig)


def test_stop_mode_ignores_the_references_and_off_mode_is_recorded(tmp_path):
    refs = CardBackRefs(None, from_layout().face_down_window_mm)
    cfg = _cfg()
    _runner(cfg, _world(cfg, ["qr"] * 6, start=CLEAN), tmp_path, refs=refs, batch="b1").run()
    assert refs.n_refs == 6
    stop = _cfg(face_down_check="stop")
    with pytest.raises(Stop, match=r"no back-label code was seen from above \(a PSA QR, a CGC QR or the CGC 2020-23 back barcode\)\)"):  # no learned reason: codes only
        _runner(stop, _world(stop, ["old"], start=40), tmp_path, refs=refs, batch="b2").run()
    off = _cfg(face_down_check="off")
    _runner(off, _world(off, ["old"], start=60), tmp_path, refs=refs, batch="b3").run()
    assert _rows(tmp_path, "b3")[0]["face_down"] == "off" and refs.n_refs == 6


# ---------------------------------------------------------------------- the descriptor
def _desc(img, cfg=None):
    cfg = cfg or from_layout()
    return describe(img, facedown.image_rects(cfg.face_down_window_mm), HEAD_VIEW_MM)


def test_the_descriptor_survives_shift_yaw_glare_and_exposure():
    deg = Degrade(mm_per_px=0.05, blur_px=1.0, glare=0.3)
    # different certs = different +/-2 mm offsets, +/-1 deg yaw, exposure and glare spots (sim.head_view)
    backs = [_desc(head_view(str(150000007 + 7919 * i), "back", deg, head="open")) for i in range(8)]
    fronts = [_desc(head_view(str(150000007 + 7919 * i), "front", deg, head="open")) for i in range(8)]
    jp = _desc(head_view("150000007", "back", deg, back="pokemon_jp", head="open"))
    worst_back = min(max(compare(b, o).score for o in backs if o is not b) for b in backs)
    best_front = max(max(compare(f, o).score for o in backs) for f in fronts)
    assert worst_back > 0.8 and best_front < 0.5 and worst_back - best_front > 0.3
    assert max(compare(jp, o).score for o in backs) < THRESHOLD
    darker = _desc((head_view("150000007", "back", deg, head="open") * 0.7).astype(np.uint8))
    assert compare(darker, next(b for b in backs[1:] if b.glare == 0)).score > 0.8  # exposure


def test_glare_is_masked_and_keeps_a_frame_out_of_the_references():
    cfg = from_layout()
    deg = Degrade(mm_per_px=0.05)
    img = head_view(_slab(CLEAN, "qr").cert, "back", deg, head="open")
    clean = _desc(img)
    assert clean.glare == 0.0
    x0, y0, x1, y1 = HEAD_VIEW_MM
    px = img.shape[1] / (x1 - x0)
    (wx0, wy0, wx1, wy1), = cfg.face_down_window_mm
    shiny = img.copy()  # a saturated reflection, 10 x 5 mm, in the middle of the card window
    cv2.ellipse(shiny, (int(((wx0 + wx1) / 2 - x0) * px), int(((wy0 + wy1) / 2 - y0) * px)), (int(5 * px), int(2.5 * px)), 0, 0, 360, 255, -1)
    d = _desc(shiny)
    assert 0.05 < d.glare < 0.3
    assert compare(d, clean).score > 0.75  # the rest of the window still matches (the spot covers a quarter of today's 5.5 mm tall window)
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    assert refs.add(d, "qr") == (None, "glare on the card window") and refs.add(clean, "qr")[0] == 0


def test_the_colour_term_separates_a_blue_back_from_a_yellow_front():
    """Real head frames are colour: same pattern, different colours must not match (hue-saturation histogram)."""
    rng = np.random.default_rng(3)
    pattern = cv2.GaussianBlur(rng.random((480, 640)).astype(np.float32), (0, 0), 10)  # blobs of a few mm
    pattern = (pattern - pattern.min()) / (pattern.max() - pattern.min())

    def frame(bgr):
        img = np.zeros((480, 640, 3), np.float32)
        for c in range(3):
            img[..., c] = bgr[c] * (0.2 + 0.8 * pattern)
        return np.clip(img + rng.normal(0, 2, img.shape), 0, 255).astype(np.uint8)

    view = frame_view_mm((480, 640), 147.0, {"hfov_deg": 64.0})
    rects = facedown.image_rects(from_layout().face_down_window_mm)
    blue, blue2, yellow = describe(frame((160, 60, 30)), rects, view), describe(frame((165, 62, 28)), rects, view), describe(frame((30, 200, 220)), rects, view)
    assert blue.color and compare(blue, blue2).score > 0.8
    assert compare(blue, yellow).ncc > 0.8 and compare(blue, yellow).score < 0.3  # the pattern alone would have matched
    assert compare(blue, describe(cv2.cvtColor(frame((160, 60, 30)), cv2.COLOR_BGR2GRAY), rects, view)).score == 0.0  # grey vs colour never


def test_a_blank_window_never_matches_or_becomes_a_reference():
    blank = np.full((1155, 1806), 70, np.uint8)
    d = _desc(blank)
    refs = CardBackRefs(None, from_layout().face_down_window_mm)
    assert refs.add(d, "qr") == (None, "nothing visible in the card window")
    ok, why, _ = facedown.learned_match(refs, d, THRESHOLD, 1, from_layout().face_down_window_mm, _cfg().face_down_threshold_sig)
    assert not ok and "nothing visible" in why


def test_prototypes_are_capped_and_keep_the_newest(tmp_path):
    deg = Degrade(mm_per_px=0.05)
    descs = [d for d in (_desc(head_view(str(150000007 + 7919 * i), "back", deg, head="open")) for i in range(30)) if d.glare == 0.0]
    descs = descs[:facedown.PER_PROTO + 4]
    refs = CardBackRefs(tmp_path / "r.npz", from_layout().face_down_window_mm)
    for i, d in enumerate(descs):
        refs.add(d, "qr", {"i": i}, cluster=THRESHOLD)
    assert refs.protos() == {0: facedown.PER_PROTO} and refs.refs[0].meta["i"] == 4
    refs.save()
    back = CardBackRefs(tmp_path / "r.npz", from_layout().face_down_window_mm)
    assert [r.meta["i"] for r in back.refs] == list(range(4, facedown.PER_PROTO + 4))
    assert compare(back.refs[0].desc, refs.refs[0].desc).score == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------------- config, Phase 0, sim command, refs command
def test_config_checks_the_face_down_keys(tmp_path):
    from slabscan.config import check_face_down, dumps

    m = tmp_path / "machine.toml"
    m.write_text(dumps(from_layout()))
    cfg = load(m)
    assert cfg.face_down_check == "learned" and cfg.face_down_window_mm == from_layout().face_down_window_mm
    cal = tmp_path / "calibration.toml"
    for bad, msg in (('face_down_check = "learnt"', "face_down_check must be"), ("face_down_threshold = 1.5", "from 0.55 to below 1"),
                     ("face_down_threshold = 0.5", "from 0.55 to below 1"), ("face_down_threshold_sig = 12", "face_down_threshold_sig must be"),
                     ("face_down_window_mm = [[10, 0, 5, 4]]", "x0 < x1")):
        cal.write_text(bad + "\n")
        with pytest.raises(ValueError, match=msg):
            load(m, cal)
    with pytest.raises(ValueError, match="from 0.55"):
        check_face_down({"face_down_threshold": 0.01})
    cal.write_text('face_down_threshold = 0.71\nface_down_threshold_sig = "abc"\n')
    assert load(m, cal).face_down_threshold == 0.71 and load(m, cal).face_down_threshold_sig == "abc"


def test_phase0_sim_reports_the_separation(tmp_path):
    from tools import phase0

    assert phase0.main(["--sim", "12", "--face-up", "15", "--sim-head", "open", "--out", str(tmp_path / "open"), "--save"]) == 0
    rep = (tmp_path / "open" / "phase0_report.txt").read_text()
    assert "lowest back-to-back similarity" in rep and "highest face-up similarity" in rep and "of 15)" in rep
    assert 'GO for face_down_check = "learned": recommended face_down_threshold' in rep
    assert (tmp_path / "open" / "card_backs.npz").exists() and (tmp_path / "open" / "window_check.jpg").exists()
    cal = (tmp_path / "open" / "config" / "calibration.toml").read_text()  # --sim never writes the real config/
    assert "face_down_threshold =" in cal and f'face_down_threshold_sig = "{facedown.threshold_tag(from_layout().face_down_window_mm)}"' in cal
    # the round-2 CAD head: the foot is in the window, face-up slabs match as well as the backs
    assert phase0.main(["--sim", "12", "--face-up", "15", "--sim-head", "cad_r2", "--out", str(tmp_path / "cad_r2"), "--save"]) == 0
    rep = (tmp_path / "cad_r2" / "phase0_report.txt").read_text()
    assert "HOLD for the learned check" in rep and "face-up slabs match the backs" in rep and 'Keep face_down_check = "stop"' in rep
    assert not (tmp_path / "cad_r2" / "config").exists()
    # today's CAD head leaves the window clear: the same GO as the open head
    assert phase0.main(["--sim", "12", "--face-up", "15", "--out", str(tmp_path / "cad"), "--save"]) == 0
    assert 'GO for face_down_check = "learned": recommended face_down_threshold' in (tmp_path / "cad" / "phase0_report.txt").read_text()
    # five face-up slabs are not enough for a GO, and the pass is opt-in
    assert phase0.main(["--sim", "12", "--face-up", "5", "--sim-head", "open", "--out", str(tmp_path / "five")]) == 0
    assert "only 5 face-up slabs (needs 15" in (tmp_path / "five" / "phase0_report.txt").read_text()
    assert phase0.main(["--sim", "3", "--out", str(tmp_path / "default")]) == 0
    assert "only 0 face-up slabs" in (tmp_path / "default" / "phase0_report.txt").read_text()


def test_phase0_leaves_an_outlier_back_out_of_the_threshold(tmp_path):
    """One Japanese card among the English backs must not drag the threshold down to the face-up slabs."""
    from tools import phase0

    cfg = from_layout()
    deg = Degrade(mm_per_px=0.05, blur_px=1.0, glare=0.3)

    class Cam:
        def view_rect_mm(self, d):
            return HEAD_VIEW_MM

    fd = phase0.FaceDown(cfg, Cam())
    for i in range(14):
        fd.backs.append((i + 1, fd.describe(head_view(str(150000007 + 7919 * i), "back", deg, era="old", head="open"))))
    fd.backs.append((15, fd.describe(head_view("150999999", "back", deg, era="old", back="pokemon_jp", head="open"))))
    for k in range(15):
        fd.face_up.append((k + 1, fd.describe(head_view(str(170000003 + 7907 * k), "front", deg, era="old", head="open"))))
    lines, threshold, outliers = phase0.face_down_report(fd, cfg)
    text = "\n".join(lines)
    assert outliers == {15} and "slab 15 matches none of the other backs" in text
    lo = float(text.split("lowest back-to-back similarity: ")[1][:4])
    # midpoint of the English backs (each one's 2nd-best match, facedown.MATCH_K), not of the outlier
    assert lo > 0.7 and threshold is not None and threshold >= max(0.5, lo - 0.3)
    seed = phase0.save_seed(fd, cfg, tmp_path / "seed.npz", outliers)
    assert all(r.meta["phase0_slab"] != 15 for r in seed.refs)


def test_phase0_writes_the_read_rate_report_before_the_face_up_pass(tmp_path, monkeypatch):
    """Ctrl-C at a face-up prompt must not lose the read-rate result of the slabs typed before it."""
    import builtins

    from tools import phase0

    from slabscan.sim import slab_view

    class Cam:
        def __init__(self, side):
            self.side = side

        def capture(self):
            return slab_view("148069831", self.side, Degrade(mm_per_px=0.05), seed=1)

    monkeypatch.setattr(phase0, "open_cameras", lambda a: (Cam("back"), Cam("front")))
    answers = iter(["148069831", "q"])

    def fake_input(prompt=""):
        try:
            return next(answers)
        except StopIteration:
            raise KeyboardInterrupt from None  # at the first face-up prompt

    monkeypatch.setattr(builtins, "input", fake_input)
    assert phase0.main(["--out", str(tmp_path), "--frames", "1", "--face-up", "15"]) == 0
    rep = (tmp_path / "phase0_report.txt").read_text()
    assert "slabs: 1" in rep and "only 0 face-up slabs" in rep


def test_sim_command_counts_the_face_down_stops(tmp_path):
    from slabscan.cli import main
    from slabscan.ops import ScriptedConsole

    con = ScriptedConsole([])
    assert main(["sim", "--slabs", "8", "--eras", "0.5,0,0.5", "--seed", "3", "--quiet", "--face-down-check", "--sim-head", "open",
                 "--out", str(tmp_path)], console=con) == 0
    out = "\n".join(con.lines)
    assert "face-down check (learned):" in out and "slabs stopped for you" in out and "face-down:" in out


def test_refs_command_lists_and_deletes_references(tmp_path):
    from slabscan.cli import main
    from slabscan.config import dumps
    from slabscan.ops import ScriptedConsole

    cfg = _cfg()
    (tmp_path / "machine.toml").write_text(dumps(from_layout()))
    path = tmp_path / facedown.FILE_NAME
    refs = CardBackRefs(path, cfg.face_down_window_mm)
    _runner(cfg, _world(cfg, ["qr"] * 3, start=CLEAN), tmp_path, refs=refs).run()
    certs = [x["cert"] for x in _rows(tmp_path)]
    con = ScriptedConsole([])
    assert main(["refs", "--config", str(tmp_path / "machine.toml")], console=con) == 0
    out = "\n".join(con.lines)
    assert "3 references in 1 prototype(s) (qr 3)" in out and all(c in out for c in certs)
    assert main(["refs", "--config", str(tmp_path / "machine.toml"), "--drop", certs[1]], console=con) == 0
    left = CardBackRefs(path, cfg.face_down_window_mm)
    assert left.n_refs == 2 and certs[1] not in [r.meta.get("cert") for r in left.refs]


def test_cli_resume_refuses_face_down_ok_after_another_stop(tmp_path):
    from slabscan.cli import main
    from slabscan.config import dumps
    from slabscan.ops import ScriptedConsole

    cfg = _cfg()
    world = _world(cfg, ["up"], start=CLEAN)
    r = _runner(cfg, world, tmp_path)
    r.should_stop = lambda: True
    with pytest.raises(Stop):
        r.run()
    (tmp_path / "machine.toml").write_text(dumps(from_layout()))
    (tmp_path / "calibration.toml").write_text("pad_trigger_c = 0.0\noffset_x = 0.0\n")
    con = ScriptedConsole([])
    assert main(["resume", str(tmp_path / "b"), "--face-down-ok", "--yes", "--config", str(tmp_path / "machine.toml")], console=con) == 2
    assert any("--face-down-ok refused" in ln for ln in con.lines)
    assert not (tmp_path / "b" / "stop.json").exists() or "refused" not in json.loads((tmp_path / "b" / "stop.json").read_text())["message"]


# ---------------------------------------------------------------------- camera aim (BUILD_GUIDE 7.7)
AIM_WINDOW = ((-27.5, -22.5, 27.5, -11.0),)  # the round-3 window: the CAD cup pad 1.4 mm (0.56 deg) beyond its cup-side edge


def _aim_cfg():
    base = from_layout()
    return dataclasses.replace(base, face_down_window_mm=AIM_WINDOW, face_down_threshold=THRESHOLD,
                               face_down_threshold_sig=facedown.threshold_tag(AIM_WINDOW))


def _empty_view_aim(cfg, head="cad", tilt=0.0):
    world = SimWorld(cfg, stacks={}, head=head, head_tilt_deg=tilt)
    cam = SimCamera(world, "head")
    frame = cam.capture()
    rects = facedown.image_rects(cfg.face_down_window_mm, "x")
    return facedown.aim_problem(describe(frame, rects, frame_view_mm(frame.shape, 147.0, cfg.cam_head, cam)), rects, "y")


@pytest.mark.parametrize("head,tilt,bad", [("cad", 0.0, False), ("cad", 0.3, False), ("open", 1.2, False),
                                           ("cad", 0.6, True), ("cad", 0.8, True), ("cad", 1.0, True), ("cad", 1.2, True), ("cad_r2", 0.0, True)])
def test_the_view_over_an_empty_pocket_shows_a_head_part_in_the_card_window(head, tilt, bad):
    """A tilt toward the cup slides the card window (fixed in the image) toward the cup pad and the foot. On the view over
    an empty pocket only the pad may show there: a square camera passes, 0.6 deg toward the cup does not."""
    why = _empty_view_aim(_aim_cfg(), head, tilt)
    assert bool(why) == bad, why
    if bad:
        assert "tilted toward the cup" in why
    assert "not inside" in facedown.aim_problem(None, facedown.image_rects(AIM_WINDOW, "x"))


def test_a_head_camera_tilted_toward_the_cup_turns_the_learned_check_off(tmp_path, monkeypatch):
    """software (round 3): a tilt of about 0.6-1.2 deg toward the cup puts the cup pad and the foot into the card window.
    That is too little of the window for the camera-locked check (STATIC_MAX), so learned acceptances went on. The view
    over an empty pocket shows it: the learned check accepts nothing and learns nothing that run, every slab without a
    back-label code stops untouched, and the stop and the start line say to re-aim the camera."""
    import slabscan.runner as runner_mod

    cfg = _aim_cfg()
    world = _world(cfg, ["qr"] * 10 + ["old"], head="cad", start=CLEAN)
    world.head_tilt_deg = 0.8
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match=r"could not be confirmed FACE-DOWN .*learned check not active: over an empty pocket the head camera sees "
                                   r"edges .*Re-aim the head camera \(BUILD_GUIDE 7\.7\)"):
        r.run()
    assert _kinds(tmp_path) == ["qr"] * 10 and r.refs.n_refs == 0  # nothing learned (a few were glare anyway)
    assert r.refs.rejected.get("the head camera's aim puts a part of the head in the card window", 0) >= 5
    ev = [e for e in read_journal(r.journal) if "face_down_baseline" in e]
    assert len(ev) == 1 and ev[0]["aim"] != "ok" and r.refs.baseline_meta["aim"] == ev[0]["aim"]
    assert "learned check not active" in r.face_down_status() and "Re-aim the head camera" in r.face_down_status()
    assert r._face_down_summary()["camera_aim"] == ev[0]["aim"]
    assert not world.gripping and not world.held and world.stacks[1][-1].face_down  # the old label: untouched
    # without the aim check the same head is let through: the window is mostly clear, so the camera-locked check is quiet
    monkeypatch.setattr(runner_mod, "aim_problem", lambda *a, **k: "")
    world2 = _world(cfg, ["qr"] * 10 + ["old"], head="cad", start=CLEAN)
    world2.head_tilt_deg = 0.8
    r2 = _runner(cfg, world2, tmp_path, batch="b2")
    r2.run()
    assert _kinds(tmp_path, "b2") == ["qr"] * 10 + ["learned"]
    assert r2.refs.static_fraction()[0] < facedown.STATIC_MAX


def test_a_square_camera_on_the_next_run_turns_the_learned_check_back_on(tmp_path):
    cfg = _aim_cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    world = _world(cfg, ["qr"] * 6, head="cad", start=CLEAN)
    world.head_tilt_deg = 1.0
    _runner(cfg, world, tmp_path, refs=refs, batch="b1").run()
    assert refs.baseline_meta["aim"] and refs.n_refs == 0
    r = _runner(cfg, _world(cfg, ["qr"] * 6 + ["old"], head="cad", start=CLEAN + 6), tmp_path, refs=refs, batch="b2")
    r.run()
    assert refs.baseline_meta["aim"] == "" and _kinds(tmp_path, "b2") == ["qr"] * 6 + ["learned"]


def test_sim_selftest_and_focus_head_report_the_camera_aim(tmp_path):
    from slabscan.cli import main
    from slabscan.ops import ScriptedConsole

    def run(argv):
        con = ScriptedConsole([])
        code = main(argv, console=con)
        return code, "\n".join(con.lines)

    # the sim command: a camera tilted 2.5 deg toward the cup (with any card window), the learned check accepts nothing
    code, out = run(["sim", "--slabs", "8", "--eras", "0.5,0,0.5", "--seed", "3", "--quiet", "--face-down-check", "--sim-head-tilt", "2.5",
                     "--out", str(tmp_path / "sim")])
    assert code == 0 and "the head camera is tilted 2.5 deg toward the cup" in out and "CAMERA AIM:" in out and "by the learned" not in out
    # focus head looks over the empty exception pocket first
    code, out = run(["--sim", "focus", "head", "--frames", "1", "--images", str(tmp_path / "f1")])
    assert code == 0 and "camera aim: OK" in out and (tmp_path / "f1" / "focus_head_empty.jpg").exists()
    code, out = run(["--sim", "--sim-head-tilt", "2.5", "focus", "head", "--frames", "1", "--images", str(tmp_path / "f2")])
    assert code == 0 and "camera aim: FAIL" in out and "BUILD_GUIDE 7.7" in out
    # selftest reports what the last learned run saw (card_backs.npz next to calibration.toml)
    from slabscan.config import dumps

    cfg = _aim_cfg()
    cal = tmp_path / "cfg" / "calibration.toml"
    cal.parent.mkdir()
    (cal.parent / "machine.toml").write_text(dumps(cfg))
    code, out = run(["--sim", "--config", str(cal.parent / "machine.toml"), "--calibration", str(cal), "selftest", "--images", str(tmp_path / "s1")])
    assert "[WARN] camera aim: not checked yet" in out
    refs = CardBackRefs(cal.parent / facedown.FILE_NAME, cfg.face_down_window_mm)
    world = _world(cfg, ["qr"], head="cad", start=CLEAN)
    world.head_tilt_deg = 1.0
    _runner(cfg, world, tmp_path, refs=refs, batch="b3").run()
    refs.save()
    code, out = run(["--sim", "--config", str(cal.parent / "machine.toml"), "--calibration", str(cal), "selftest", "--images", str(tmp_path / "s2")])
    assert code == 1 and "[FAIL] camera aim: over an empty pocket the head camera sees edges" in out and "batch b3, pocket" in out
