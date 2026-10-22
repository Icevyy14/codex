"""The learned face-down check (slabscan/facedown.py, Runner._check_face_down in "learned" mode), in the simulator.

A slab without a back-label code (PSA or CGC back QR, CGC 2020-23 back barcode) may be picked only when its card window
matches the card backs of proven face-down slabs (back-label code seen, or confirmed by the operator). Most tests use the hypothetical "open" head (sim.HEADS), whose
foot leaves face_down_window_mm clear; with today's CAD head the foot hides the window, and the check must refuse.
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
from slabscan.simworld import SimCamera, SimGate, SimLights, SimMotion, SimSlab, SimVacuum, SimWorld

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
                  gate=SimGate(world), log=lambda *_: None, refs=refs if refs is not None else CardBackRefs(None, cfg.face_down_window_mm))


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
    assert frac < 0.02 and n == 6  # the open head leaves the window clear


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
    r._pending_ref = (d, 1, "operator")
    r._settle_reference(1, v, [CodeRead("150000007", "front_qr", "QRCode", "https://www.psacard.com/cert/150000007", "front")], "images/0001_back.jpg")
    assert r.refs.n_refs == 0 and r._pending_ref is None
    r._pending_ref = (d, 1, "operator")
    r._settle_reference(2, v, [CodeRead("150000007", "front_barcode", "ITF", "0150000007", "front")], "images/0002_back.jpg")
    assert r.refs.n_refs == 1 and r.refs.refs[0].meta["cert"] == "150000007"
    results = [e["result"] for e in read_journal(r.journal) if "face_down_reference" in e]
    assert "FACE-UP" in results[0] and results[1].startswith("reference 1")


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
            assert "known only from" in str(e)  # it matches the Japanese back, but not enough confirmations yet
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
    assert refs.static_fraction()[0] < 0.02 and refs.refs[0].desc.levels  # the levels are stored too
    # a later batch of older labels only: matched against the first batch's references from its first slab
    _runner(cfg, _world(cfg, ["old"] * 3, start=50), tmp_path, refs=refs, batch="b2").run()
    assert _kinds(tmp_path, "b2") == ["learned"] * 3
    # another card window makes the stored references useless: they are not used
    other = CardBackRefs(path, ((-20.0, -33.0, 20.0, -18.0),))
    assert other.n_refs == 0 and "another card window" in other.note


def test_with_todays_cad_head_the_learned_check_refuses(tmp_path):
    """The CAD head foot hides face_down_window_mm: every frame shows the same foot, so a face-up slab would 'match'.
    The empty-pocket baseline catches it: no references are collected and nothing is accepted."""
    cfg = _cfg()
    world = _world(cfg, ["qr"] * 6 + ["old"], head="cad")
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match="looks like the view over an empty pocket .* the head hides it") as e:
        r.run()
    assert r.refs.n_refs == 0 and r.refs.rejected == {"card window looks like the empty-pocket view (the head hides it)": 6}
    assert "becomes a reference" not in str(e.value)  # a confirmation would not teach it anything either
    assert not world.gripping and not world.held


def _foot(y0: float, grey: int = 52):
    """sim.HEADS "open" with the foot's label-side edge at y0 (mm from the cup axis, 62-75 mm above the cup face)."""
    parts = [list(p) for p in sim.HEADS["open"]]
    parts[2] = [-11.0, y0, 11.0, 45.0, 62.0, 75.0, grey]
    parts[3] = [11.0, y0, 30.5, -y0, 62.0, 75.0, grey]
    return [tuple(p) for p in parts]


@pytest.mark.parametrize("name, parts, refused", [
    # the foot hides about 40 % of the window: its edge looks unlike the empty view's (the card is brighter than the foot,
    # the pocket darker), so only the level check sees it
    ("foot_y-11", _foot(-11.0), r"of the card window shows the same thing on every proven slab as over an empty pocket"),
    # the same foot as dark as the empty pocket: no edge in the empty view at all
    ("foot_y-11_black", _foot(-11.0, grey=30), r"of the card window shows the same thing on every proven slab as over an empty pocket"),
    # 75 % hidden: the pattern guard sees it on every slab
    ("foot_y-13", _foot(-13.0), r"looks like the (view over an empty pocket|empty-pocket view)"),
    # today's CAD head without the M10 nut and rod end: a plain foot fills the window
    ("cad_no_nut", [p for p in sim.HEADS["cad"] if p[6] not in (150, 170)], r"nothing visible in the card window"),
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
    shiny = img.copy()  # a saturated reflection, 10 x 5 mm, on the card window
    cv2.ellipse(shiny, (int((0 - x0) * px), int((-25 - y0) * px)), (int(5 * px), int(2.5 * px)), 0, 0, 360, 255, -1)
    d = _desc(shiny)
    assert 0.05 < d.glare < 0.3
    assert compare(d, clean).score > 0.8  # the rest of the window still matches
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
    # today's CAD head: the foot is in the window, face-up slabs match as well as the backs
    assert phase0.main(["--sim", "12", "--face-up", "15", "--out", str(tmp_path / "cad"), "--save"]) == 0
    rep = (tmp_path / "cad" / "phase0_report.txt").read_text()
    assert "HOLD for the learned check" in rep and "face-up slabs match the backs" in rep and 'Keep face_down_check = "stop"' in rep
    assert not (tmp_path / "cad" / "config").exists()
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
    assert lo > 0.8 and threshold is not None and threshold >= max(0.5, lo - 0.3)  # midpoint of the English backs, not of the outlier
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
