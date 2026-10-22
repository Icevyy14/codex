"""The learned face-down check (slabscan/facedown.py, Runner._check_face_down in "learned" mode), in the simulator.

A slab without a PSA back QR may be picked only when its card window matches the card backs of proven face-down
slabs (back QR seen, or confirmed by the operator). Most tests use the hypothetical "open" head (sim.HEADS), whose
foot leaves face_down_window_mm clear; with today's CAD head the foot hides the window, and the check must refuse.
"""

import csv
import dataclasses

import cv2
import numpy as np
import pytest

from slabscan import facedown
from slabscan.config import from_layout, load
from slabscan.facedown import CardBackRefs, compare, describe, frame_view_mm
from slabscan.results import BatchWriter
from slabscan.runner import Runner, Stop, read_journal
from slabscan.sim import HEAD_VIEW_MM, Degrade, head_view
from slabscan.simworld import SimCamera, SimGate, SimLights, SimMotion, SimSlab, SimVacuum, SimWorld

THRESHOLD = 0.6  # cli.SIM_FACE_DOWN_THRESHOLD: picked on the simulator's synthetic backs


def _cfg(**kw):
    return dataclasses.replace(from_layout(), face_down_threshold=THRESHOLD, **kw)


def _slab(i: int, kind: str) -> SimSlab:
    """kind: qr (2017+ label, back QR), old (no back code), up (old label, loaded FACE-UP), jp_qr / jp_old (Japanese
    card back), cgc (CGC slab face-down), cgc_up (CGC face-up)."""
    cert = str(150000007 + 7919 * i)
    s = SimSlab(cert, 6.6, "2017+" if kind in ("qr", "jp_qr") else "old")
    if kind.startswith("jp"):
        s.back = "pokemon_jp"
    if kind == "up":
        s.face_down = False
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


# ---------------------------------------------------------------------- the run
def test_a_face_down_old_label_passes_once_enough_qr_references_exist(tmp_path):
    cfg = _cfg()
    world = _world(cfg, ["qr"] * 6 + ["old", "old"])
    r = _runner(cfg, world, tmp_path)
    summary = r.run()
    rows = _rows(tmp_path)
    assert [x["face_down"].split("(")[0] for x in rows] == ["qr"] * 6 + ["learned"] * 2
    assert all(float(x["face_down"][8:-1]) >= THRESHOLD for x in rows[6:])
    events = [e for e in read_journal(r.journal) if "face_down_learned" in e]
    assert len(events) == 2 and all(e["score"] >= THRESHOLD and e["refs"] == 6 and e["baseline"] < facedown.BASELINE_MAX for e in events)
    assert summary["face_down"]["counts"] == {"qr": 6, "learned": 2} and len(summary["face_down"]["learned"]) == 2
    assert "learned(" in (tmp_path / "b" / "report.html").read_text()


def test_a_face_up_old_label_still_stops_in_learned_mode(tmp_path):
    cfg = _cfg()
    world = _world(cfg, ["qr"] * 6 + ["up"])
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match=r"could not be confirmed FACE-DOWN .*best match with a known card back 0\.\d\d < threshold 0\.60"):
        r.run()
    assert not world.gripping and not world.held and len(r.w.rows) == 6  # the face-up slab was never touched
    assert world.stacks[1][-1].face_down is False and r.refs.n_refs == 6


def test_learned_acceptances_never_become_references(tmp_path):
    cfg = _cfg()
    refs = CardBackRefs(tmp_path / "card_backs.npz", cfg.face_down_window_mm)
    _runner(cfg, _world(cfg, ["qr"] * 5 + ["old"] * 4), tmp_path, refs=refs).run()
    assert refs.n_refs == 5 and refs.sources() == {"qr": 5}
    assert CardBackRefs(tmp_path / "card_backs.npz", cfg.face_down_window_mm).n_refs == 5  # nor in the file
    d = describe(head_view("150000007", "back", Degrade(mm_per_px=0.05), head="open"), facedown.image_rects(cfg.face_down_window_mm), HEAD_VIEW_MM)
    with pytest.raises(ValueError, match="only"):
        refs.add(d, "learned")


def test_a_batch_that_starts_with_old_labels_stops_then_learns_from_the_operator(tmp_path):
    cfg = _cfg()
    path = tmp_path / "card_backs.npz"
    world = _world(cfg, ["old", "qr", "qr", "qr", "qr", "old"])
    with pytest.raises(Stop, match="0 of 5 card-back references"):
        _runner(cfg, world, tmp_path, refs=CardBackRefs(path, cfg.face_down_window_mm)).run()
    assert not world.gripping and not world.held
    refs = CardBackRefs(path, cfg.face_down_window_mm)
    r2, summary = _resume(cfg, world, tmp_path, refs, face_down_ok=True)
    assert summary["slabs_visited"] == 6
    stored = CardBackRefs(path, cfg.face_down_window_mm)
    assert stored.sources() == {"operator": 1, "qr": 4}  # the confirmed slab, then the four QR slabs
    assert [x["face_down"].split("(")[0] for x in _rows(tmp_path)] == ["operator", "qr", "qr", "qr", "qr", "learned"]
    assert any(e.get("face_down_confirmed") == 1 and "reference 1" in e.get("reference", "") for e in read_journal(r2.journal))


def test_a_japanese_back_stops_with_only_english_references_then_learns_after_confirmation(tmp_path):
    cfg = _cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    world = _world(cfg, ["qr"] * 6 + ["jp_old", "jp_old"])
    with pytest.raises(Stop, match=r"best match with a known card back 0\.\d\d < threshold"):
        _runner(cfg, world, tmp_path, refs=refs).run()
    assert len(refs.protos()) == 1
    _, summary = _resume(cfg, world, tmp_path, refs, face_down_ok=True)
    assert summary["slabs_visited"] == 8
    assert len(refs.protos()) == 2 and refs.sources() == {"qr": 6, "operator": 1}  # the Japanese back is a prototype of its own
    rows = _rows(tmp_path)
    assert rows[6]["face_down"] == "operator" and rows[7]["face_down"].startswith("learned(")


def test_the_reference_file_persists_across_runner_instances(tmp_path):
    cfg = _cfg()
    path = tmp_path / "config" / "card_backs.npz"
    _runner(cfg, _world(cfg, ["qr"] * 6), tmp_path, refs=CardBackRefs(path, cfg.face_down_window_mm), batch="b1").run()
    assert path.exists()
    refs = CardBackRefs(path, cfg.face_down_window_mm)
    assert refs.n_refs == 6 and refs.baseline is not None and "loaded 6 references" in refs.note
    # a later batch of older labels only: matched against the first batch's references from its first slab
    _runner(cfg, _world(cfg, ["old"] * 3, start=50), tmp_path, refs=refs, batch="b2").run()
    assert [x["face_down"].split("(")[0] for x in _rows(tmp_path, "b2")] == ["learned"] * 3
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


def test_another_graders_code_still_stops_and_a_face_down_cgc_slab_is_learned(tmp_path):
    cfg = _cfg()
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    world = _world(cfg, ["qr"] * 5 + ["cgc", "cgc_up"])
    with pytest.raises(Stop, match="CGC code is visible from above, and those sit on the FRONT label"):
        _runner(cfg, world, tmp_path, refs=refs).run()
    rows = _rows(tmp_path)
    assert rows[5]["grader"] == "CGC" and rows[5]["face_down"].startswith("learned(")  # no back QR, but a known card back
    assert not world.gripping and world.stacks[1][-1].face_down is False


def test_learned_mode_waits_for_a_measured_threshold(tmp_path):
    cfg = dataclasses.replace(from_layout())  # the default config: learned, but no threshold yet
    assert cfg.face_down_check == "learned" and cfg.face_down_threshold is None
    world = _world(cfg, ["qr"] * 6 + ["old"])
    r = _runner(cfg, world, tmp_path)
    with pytest.raises(Stop, match="face_down_threshold is not measured"):
        r.run()
    assert r.refs.n_refs == 6  # references are collected anyway, for when the threshold is set
    assert "learned check not active yet" in r.face_down_status()


def test_stop_mode_ignores_the_references_and_off_mode_is_recorded(tmp_path):
    refs = CardBackRefs(None, from_layout().face_down_window_mm)
    cfg = _cfg()
    _runner(cfg, _world(cfg, ["qr"] * 6), tmp_path, refs=refs, batch="b1").run()
    assert refs.n_refs == 6
    stop = _cfg(face_down_check="stop")
    with pytest.raises(Stop, match=r"no PSA back-label QR was seen from above\)"):  # no learned reason: QR only
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
    assert compare(darker, backs[1]).score > 0.8  # exposure


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
    ok, why, _ = facedown.learned_match(refs, d, THRESHOLD, 1, from_layout().face_down_window_mm)
    assert not ok and "nothing visible" in why


def test_prototypes_are_capped_and_keep_the_newest(tmp_path):
    deg = Degrade(mm_per_px=0.05)
    refs = CardBackRefs(tmp_path / "r.npz", from_layout().face_down_window_mm)
    for i in range(facedown.PER_PROTO + 4):
        refs.add(_desc(head_view(str(150000007 + 7919 * i), "back", deg, head="open")), "qr", {"i": i}, cluster=THRESHOLD)
    assert refs.protos() == {0: facedown.PER_PROTO} and refs.refs[0].meta["i"] == 4
    refs.save()
    back = CardBackRefs(tmp_path / "r.npz", from_layout().face_down_window_mm)
    assert [r.meta["i"] for r in back.refs] == list(range(4, facedown.PER_PROTO + 4))
    assert compare(back.refs[0].desc, refs.refs[0].desc).score == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------------- config, Phase 0, sim command
def test_config_checks_the_face_down_keys(tmp_path):
    from slabscan.config import dumps

    m = tmp_path / "machine.toml"
    m.write_text(dumps(from_layout()))
    cfg = load(m)
    assert cfg.face_down_check == "learned" and cfg.face_down_window_mm == from_layout().face_down_window_mm
    cal = tmp_path / "calibration.toml"
    for bad, msg in (('face_down_check = "learnt"', "face_down_check must be"), ("face_down_threshold = 1.5", "between 0 and 1"),
                     ("face_down_window_mm = [[10, 0, 5, 4]]", "x0 < x1")):
        cal.write_text(bad + "\n")
        with pytest.raises(ValueError, match=msg):
            load(m, cal)
    cal.write_text("face_down_threshold = 0.71\n")
    assert load(m, cal).face_down_threshold == 0.71


def test_phase0_sim_reports_the_separation(tmp_path):
    from tools import phase0

    assert phase0.main(["--sim", "10", "--face-up", "3", "--sim-head", "open", "--out", str(tmp_path / "open"), "--save"]) == 0
    rep = (tmp_path / "open" / "phase0_report.txt").read_text()
    assert "lowest back-to-back similarity" in rep and "highest face-up similarity" in rep
    assert 'GO for face_down_check = "learned": recommended face_down_threshold' in rep
    assert (tmp_path / "open" / "card_backs.npz").exists() and (tmp_path / "open" / "window_check.jpg").exists()
    cal = (tmp_path / "open" / "config" / "calibration.toml").read_text()  # --sim never writes the real config/
    assert "face_down_threshold" in cal
    # today's CAD head: the foot is in the window, face-up slabs match as well as the backs
    assert phase0.main(["--sim", "10", "--face-up", "3", "--out", str(tmp_path / "cad"), "--save"]) == 0
    rep = (tmp_path / "cad" / "phase0_report.txt").read_text()
    assert "HOLD for the learned check" in rep and "face-up slabs match the backs" in rep and 'Keep face_down_check = "stop"' in rep
    assert not (tmp_path / "cad" / "config").exists()


def test_sim_command_counts_the_face_down_stops(tmp_path):
    from slabscan.cli import main
    from slabscan.ops import ScriptedConsole

    con = ScriptedConsole([])
    assert main(["sim", "--slabs", "8", "--eras", "0.5,0,0.5", "--seed", "3", "--quiet", "--face-down-check", "--sim-head", "open",
                 "--out", str(tmp_path)], console=con) == 0
    out = "\n".join(con.lines)
    assert "face-down check (learned):" in out and "slabs stopped for you" in out and "face-down:" in out
