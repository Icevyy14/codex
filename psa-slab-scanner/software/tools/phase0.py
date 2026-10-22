"""Phase 0: prove the cameras read YOUR slabs before buying any motion parts.

Put a slab face-down in the Phase 0 jig (front toward the bottom camera, label end toward you),
type its printed cert, press Enter, repeat for 30-50 slabs (mix old and new PSA labels, and a few
CGC). Scan five 2024+ slabs (9-digit certs, back QR) FIRST: they teach the ITF format, and the
machine learns in the same order.
Every capture is saved, and a CSV records exactly what each camera decoded (symbology + raw
payload), which settles the open questions about PSA's barcode format.

Learned face-down check: every back image also gives a card-window descriptor (slabscan/facedown.py).
The read-rate report is written as soon as you type 'q'. Then, with --face-up N (N >= 15 for a GO), a
face-up pass scans N slabs FACE-UP with the head camera only (nothing touches them in the jig; include a
plain and a full-art card). The report compares the backs with each other and with the face-up slabs. A
back that matches none of the others (a Japanese card, another game, a CGC holder) is named and left out.
GO for face_down_check = "learned" needs the lowest remaining back-to-back similarity at least
FACE_DOWN_MARGIN above the highest face-up similarity; the threshold is the midpoint, never below
the floor (facedown.THRESHOLD_FLOOR). The backs are written as the seed reference file
(OUT/card_backs.npz); --save also merges them into config/card_backs.npz and writes face_down_threshold
and face_down_threshold_sig (the card window it was measured for) to config/calibration.toml (only on GO).

Run on the Pi:   python -m tools.phase0 --out phase0_results --face-up 15 --save
Without cameras (demo with synthetic labels):   python -m tools.phase0 --sim 10
"""

from __future__ import annotations

import argparse
import copy
import csv
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from slabscan.certs import ItfModel, consensus
from slabscan.decode import decode_frame
from slabscan.facedown import (FILE_NAME, MIN_TEXTURE, THRESHOLD_FLOOR, CardBackRefs, compare, describe, draw_window, frame_view_mm, image_rects,
                               threshold_tag, window_area)

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
FACE_DOWN_MARGIN = 0.10  # lowest back minus highest face-up similarity needed for GO [Guessing: a margin, not a measured rule]
FACE_DOWN_MIN_BACKS = 10  # usable back images (outliers left out) needed before the separation means anything
FACE_DOWN_MIN_UP = 15  # face-up slabs needed: 5 say little about the worst face-up case
OUTLIER_GAP = 0.15  # a back whose best match is this far below the median back is another back design, not the rule


def open_cameras(args):
    if args.sim:
        import random

        from slabscan.sim import Degrade, head_view, slab_view

        rng = random.Random(1)

        class _Sim:
            def __init__(self, side):
                self.side, self.cert, self.face_up, self.front = side, "", False, "art"

            def capture(self):
                if self.side == "back":  # the head camera: label end and card window, past the head's own parts
                    img = head_view(self.cert, "front" if self.face_up else "back", Degrade(mm_per_px=0.05, blur_px=1.0, glare=0.3), head=args.sim_head,
                                    front=self.front)
                    noise = np.random.default_rng(rng.randint(0, 10**6)).normal(0, 2.0, img.shape)
                    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
                return slab_view(self.cert, self.side, Degrade(mm_per_px=0.04), seed=rng.randint(0, 999))

            def view_rect_mm(self, distance_mm):
                from slabscan.sim import HEAD_VIEW_MM

                return HEAD_VIEW_MM

        head, station = _Sim("back"), _Sim("front")
        return head, station
    from slabscan.camera import PiCamera, UsbCamera

    head = UsbCamera(args.head_device, "head", size=(3264, 2448))
    station = PiCamera(0, "station", lens_position=args.lens_position)
    return head, station


def load_machine_config(path: str | None):
    """The machine config (card window, head camera geometry); the CAD defaults when there is no machine.toml yet."""
    from slabscan.config import from_layout, load

    p = Path(path) if path else SOFTWARE_DIR / "config" / "machine.toml"
    return load(p, p.parent / "calibration.toml") if p.exists() else from_layout()


class FaceDown:
    """Card-window descriptors of the Phase 0 head images (the jig: slab back 140 mm from the head lens)."""

    def __init__(self, cfg, cam):
        self.cfg, self.cam = cfg, cam
        spec = cfg.cam_head or {}
        self.distance = float(spec.get("lens_to_label_mm", 140.0))
        self.rects = image_rects(cfg.face_down_window_mm, str(spec.get("row_axis", "x")))
        self.backs: list[tuple[int, object]] = []  # (slab n, descriptor or None)
        self.face_up: list[tuple[int, object]] = []

    def describe(self, img):
        return describe(img, self.rects, frame_view_mm(img.shape, self.distance, self.cfg.cam_head, self.cam))

    def window_picture(self, img, path: Path) -> None:
        """The frame with face_down_window_mm drawn on it: check that the boxes lie on the card, not on the label or the head."""
        view = frame_view_mm(img.shape, self.distance, self.cfg.cam_head, self.cam)
        cv2.imwrite(str(path), draw_window(img, self.rects, view), [cv2.IMWRITE_JPEG_QUALITY, 90])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="phase0_results")
    ap.add_argument("--config", default=None, help="machine.toml for the card window and the head camera geometry (default config/machine.toml)")
    ap.add_argument("--face-up", type=int, default=0,
                    help=f"slabs to scan FACE-UP after the others, for the learned face-down check (default 0 = skip; a GO needs {FACE_DOWN_MIN_UP})")
    ap.add_argument("--save", action="store_true",
                    help="on a learned-check GO: merge the backs into config/card_backs.npz and write face_down_threshold and "
                         "face_down_threshold_sig to config/calibration.toml (with --sim: into OUT/config/ instead)")
    ap.add_argument("--sim-head", choices=["cad", "open", "none"], default="cad", help="(--sim) head parts in the head camera's view (sim.HEADS)")
    ap.add_argument("--head-device", type=lambda v: int(v) if v.isdigit() else v, default="auto",
                    help="USB head camera: auto (first /dev/v4l/by-id/usb-*; on a Pi 5 /dev/video0 is the CSI pipeline), a number, or a path")
    ap.add_argument("--lens-position", type=float, default=7.1, help="Camera Module 3 dioptres; 1/0.14 m = 7.1")
    ap.add_argument("--frames", type=int, default=2)
    ap.add_argument("--sim", type=int, default=0, help="run N synthetic slabs instead of real cameras")
    a = ap.parse_args(argv)
    out = Path(a.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    cfg = load_machine_config(a.config)
    head, station = open_cameras(a)
    fd = FaceDown(cfg, head)
    itf = ItfModel()
    rows = []
    f = (out / "phase0.csv").open("w", newline="")
    w = csv.writer(f)
    w.writerow(["n", "printed_cert_typed", "back_reads", "front_reads", "verdict", "cert", "note", "back_ms", "front_ms"])
    n = 0
    sim_certs = [str(148069831 + 7919 * i) for i in range(a.sim)]
    while True:
        n += 1
        if a.sim:
            if n > a.sim:
                break
            typed = sim_certs[n - 1]
            head.cert = station.cert = typed
        else:
            typed = input(f"\nSlab {n}: place it, type the printed cert (or just Enter to skip typing, 'q' to finish): ").strip()
            if typed.lower() == "q":
                break
        res = {}
        for name, cam, side in (("back", head, "back"), ("front", station, "front")):
            t0 = time.monotonic()
            reads, unparsed = [], []
            for k in range(a.frames):
                img = cam.capture()
                cv2.imwrite(str(out / "images" / f"{n:03d}_{name}_{k}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if name == "back" and k == 0:
                    fd.backs.append((n, fd.describe(img)))
                    if n == 1:
                        fd.window_picture(img, out / "window_check.jpg")
                r, u = decode_frame(img, side)
                reads += r
                unparsed += u
            res[name] = (reads, unparsed, (time.monotonic() - t0) * 1000)
        allreads = res["back"][0] + res["front"][0]
        v = consensus(allreads, itf)
        fmt = lambda rs, us: "; ".join([f"{r.symbology}:{r.raw}" for r in rs] + [f"?{u}" for u in us])  # noqa: E731
        row = [n, typed, fmt(*res["back"][:2]), fmt(*res["front"][:2]), v.status, v.cert or "", v.note, round(res["back"][2]), round(res["front"][2])]
        w.writerow(row)
        f.flush()
        rows.append((typed, v, res))
        match = "" if not typed else (" MATCH" if v.cert == typed.lstrip("0") else f" MISMATCH (typed {typed})")
        print(f"  back: {row[2] or '-'}\n  front: {row[3] or '-'}\n  => {v.status} {v.cert or ''} {v.note}{match}")
    f.close()
    total = len(rows)
    if not total:
        return 0
    report = phase0_report(rows, itf)
    # written now: the face-up pass below waits for you, and Ctrl-C there must not lose the read-rate result
    (out / "phase0_report.txt").write_text("\n".join(report + ["(learned face-down check: not evaluated yet - the face-up pass did not finish)"]) + "\n")
    face_up_pass(a, head, fd, out)
    # a slab whose BACK label faced the station camera (a PSA QR read from below) was face-up: its window shows a front
    face_up_by_mistake = {n for n, (_, _, res) in enumerate(rows, start=1) if any(r.source == "front_qr" and r.grader == "PSA" for r in res["front"][0])}
    fd_lines, threshold, outliers = face_down_report(fd, cfg, face_up_by_mistake)
    report += fd_lines
    seed = save_seed(fd, cfg, out / FILE_NAME, outliers | face_up_by_mistake)
    report.append(f"seed reference file: {out / FILE_NAME} ({seed.summary()})" + ("" if threshold is not None else "; HOLD: do not copy it to config/"))
    if a.save:
        report += save_face_down(a, fd, cfg, out, threshold, outliers | face_up_by_mistake)
    (out / "phase0_report.txt").write_text("\n".join(report) + "\n")
    print("\n" + "\n".join(report))
    return 0


def face_up_pass(a, head, fd: FaceDown, out: Path) -> None:
    """Scan a few slabs FACE-UP with the head camera only: what the learned check must never accept."""
    if a.face_up <= 0:
        return
    if not a.sim:
        print(f"\nFace-up pass: {a.face_up} slabs FACE-UP in the jig (label end toward you), for the learned face-down check. Nothing touches "
              "them here. Use different cards, and include at least one plain card (one colour, little print) and one full-art card: "
              "they are the hardest to tell from a card back.")
    try:
        for k in range(1, a.face_up + 1):
            if a.sim:  # the first one is a plain card front: the hardest case
                head.cert, head.face_up, head.front = str(190000001 + 7907 * k), True, "plain" if k == 1 else "art"
            else:
                ans = input(f"Face-up slab {k}/{a.face_up}: place it face-UP, then Enter ('s' = skip the rest): ").strip().lower()
                if ans == "s":
                    break
            img = head.capture()
            cv2.imwrite(str(out / "images" / f"faceup_{k:02d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            fd.face_up.append((k, fd.describe(img)))
    except (KeyboardInterrupt, EOFError):  # = 's': the slabs scanned so far still count
        print(f"\nface-up pass ended after {len(fd.face_up)} slab(s)")
    if a.sim:
        head.face_up, head.front = False, "art"


def separation(fd: FaceDown, exclude: set | frozenset = frozenset()) -> dict:
    """Each usable back against all other backs (the machine's references are other slabs' backs), and each face-up slab
    against all backs. A usable descriptor shows enough texture in the window. A back whose best match lies far below
    the others' (OUTLIER_GAP below the median, or 4 robust sigmas) is another back design: it is listed in "outliers"
    and left out of "main", so that one Japanese card or CGC holder cannot drag the threshold down to the face-up slabs.
    ``exclude``: slabs that were face-up by mistake (a PSA back QR seen from below)."""
    backs = [(n, d) for n, d in fd.backs if d is not None and d.texture >= MIN_TEXTURE and n not in exclude]
    ups = [(k, d) for k, d in fd.face_up if d is not None]
    back_scores = []
    for i, (n, d) in enumerate(backs):
        others = [e for j, (_, e) in enumerate(backs) if j != i]
        back_scores.append((max((compare(d, e).score for e in others), default=0.0), n))
    outliers: list[tuple[float, int]] = []
    if len(back_scores) >= 3:
        v = np.array([x for x, _ in back_scores])
        med = float(np.median(v))
        mad = float(np.median(np.abs(v - med)))
        cut = med - max(OUTLIER_GAP, 4 * 1.4826 * mad)
        outliers = [(x, n) for x, n in back_scores if x < cut]
    main = [(x, n) for x, n in back_scores if (x, n) not in outliers]
    # against every usable back, outliers too: one may become a reference on the machine later
    up_scores = [(max((compare(d, e).score for _, e in backs), default=0.0), k) for k, d in ups]
    return {"backs": backs, "back_scores": back_scores, "main": main, "outliers": outliers, "up_scores": up_scores,
            "n_backs": len(fd.backs), "n_up": len(fd.face_up)}


def face_down_report(fd: FaceDown, cfg, exclude: set | frozenset = frozenset()) -> tuple[list[str], float | None, set]:
    """The learned face-down check's GO / HOLD lines, the recommended threshold (None on HOLD) and the outlier backs
    (slab numbers, left out of the threshold and of the references)."""
    sep = separation(fd, exclude)
    area = window_area(cfg.face_down_window_mm)
    out = [f"learned face-down check: card window face_down_window_mm {[list(r) for r in cfg.face_down_window_mm]} = {area:.0f} mm2 "
           "(see window_check.jpg: the red boxes must lie on the card back, clear of the label and of the cup/foot)"]
    nb, nu = len(sep["main"]), len(sep["up_scores"])
    out.append(f"  usable back images: {len(sep['backs'])} of {sep['n_backs']}" + ("" if len(sep["backs"]) == sep["n_backs"] else
               "  (the rest show nothing in the window - blank, dark or outside the frame - or were face-up: a PSA back QR read from below)"))
    for n in sorted(exclude):
        out.append(f"  slab {n}: the station camera read a PSA back-label QR from below, so it was FACE-UP in the jig: left out")
    for x, n in sorted(sep["outliers"], key=lambda t: t[1]):
        out.append(f"  slab {n} matches none of the other backs ({x:.2f}): another back design (a Japanese card, another game) or a CGC "
                   "holder? Left out of the threshold and of the references. On the machine such slabs stop until a back-QR slab or "
                   "three of your confirmations teach that back.")
    hold = []
    lo = hi = None
    if sep["main"]:
        lo, lo_n = min(sep["main"])
        out.append(f"  lowest back-to-back similarity: {lo:.2f} (slab {lo_n})")
    if sep["up_scores"]:
        hi, hi_k = max(sep["up_scores"])
        out.append(f"  highest face-up similarity: {hi:.2f} (face-up slab {hi_k} of {nu})")
    if area <= 0:
        hold.append("face_down_window_mm is empty")
    if nb < FACE_DOWN_MIN_BACKS:
        hold.append(f"only {nb} usable back images (needs {FACE_DOWN_MIN_BACKS})")
    if nu < FACE_DOWN_MIN_UP:
        hold.append(f"only {nu} face-up slabs (needs {FACE_DOWN_MIN_UP}: run Phase 0 with --face-up {FACE_DOWN_MIN_UP})")
    if lo is not None and hi is not None and lo - hi < FACE_DOWN_MARGIN:
        why = f"backs and face-up slabs do not separate: {lo:.2f} - {hi:.2f} = {lo - hi:.2f} < {FACE_DOWN_MARGIN:.2f}"
        if hi > 0.8:
            why += " (face-up slabs match the backs: the window probably shows the head - cup, buffer, foot - not the card)"
        hold.append(why)
    threshold = None
    if lo is not None and hi is not None:
        threshold = round(max((lo + hi) / 2, THRESHOLD_FLOOR), 2)
        if threshold > lo - FACE_DOWN_MARGIN / 2:
            hold.append(f"the backs match each other too weakly ({lo:.2f}) for the threshold floor {THRESHOLD_FLOOR:.2f}")
    if len(sep["outliers"]) > max(1, nb // 5):
        hold.append(f"{len(sep['outliers'])} backs match none of the others: too many to call them exceptions (check window_check.jpg)")
    if hold:
        out.append('  HOLD for the learned check: ' + "; ".join(hold) + '. Keep face_down_check = "stop" (set it in calibration.toml): '
                   "every slab without a back QR then stops for you to check.")
        return out, None, {n for _, n in sep["outliers"]}
    out.append(f'  GO for face_down_check = "learned": recommended face_down_threshold = {threshold:.2f} (midpoint of {lo:.2f} and {hi:.2f}, '
               f"floor {THRESHOLD_FLOOR:.2f}; margin {lo - hi:.2f} >= {FACE_DOWN_MARGIN:.2f}). {nu} face-up slabs were seen: the true highest "
               "face-up similarity can be higher, which the midpoint leaves room for. On the machine the check also verifies that the head "
               "leaves the card window clear before it accepts anything. Check the back photo of every learned acceptance in the first "
               "batches (report.html).")
    return out, threshold, {n for _, n in sep["outliers"]}


def save_seed(fd: FaceDown, cfg, path: Path, exclude: set | frozenset = frozenset()) -> CardBackRefs:
    refs = CardBackRefs(None, cfg.face_down_window_mm)
    refs.path = path
    for n, d in fd.backs:
        if n not in exclude:
            refs.add(d, "phase0", {"phase0_slab": n})
    refs.save()
    return refs


def save_face_down(a, fd: FaceDown, cfg, out: Path, threshold: float | None, exclude: set | frozenset = frozenset()) -> list[str]:
    """--save: merge the backs into the machine's reference file and write the threshold with the tag of the card window
    it was measured for, only on GO."""
    from slabscan.config import write_overrides

    if threshold is None:
        return ["--save: nothing written (the learned check is HOLD)"]
    cdir = out / "config" if a.sim else SOFTWARE_DIR / "config"
    refs = CardBackRefs(cdir / FILE_NAME, cfg.face_down_window_mm)
    for n, d in fd.backs:
        if n not in exclude:
            refs.add(d, "phase0", {"phase0_slab": n}, cluster=threshold)
    refs.save()
    cal = cdir / "calibration.toml"
    tag = threshold_tag(cfg.face_down_window_mm)
    write_overrides(cal, {"face_down_threshold": threshold, "face_down_threshold_sig": tag},
                    f"phase0 {time.strftime('%Y-%m-%d %H:%M')}: learned face-down threshold (sig = the card window it was measured for)")
    return [f"--save: wrote face_down_threshold = {threshold:.2f} (sig {tag}) to {cal} and {refs.summary()} to {cdir / FILE_NAME}"]


def phase0_report(rows: list, itf: ItfModel) -> list[str]:
    """The GO / HOLD decision. ``rows`` = [(typed cert, verdict in scan order, {side: (reads, unparsed, ms)})]."""
    total = len(rows)
    ok = sum(1 for _, v, _ in rows if v.status == "ok")
    # the same reads scored again with the ITF format as finally learned (the machine itself learns in order,
    # so the in-order number is the one that predicts a run; the second shows what scan order cost)
    learned = copy.deepcopy(itf)
    ok_after = sum(1 for _, _, res in rows if consensus(res["back"][0] + res["front"][0], copy.deepcopy(learned)).status == "ok")
    back_any = sum(1 for _, _, r in rows if r["back"][0])
    front_any = sum(1 for _, _, r in rows if r["front"][0])
    syms = Counter(r.symbology for _, _, res in rows for side in ("back", "front") for r in res[side][0])
    typed_rows = [(t, v) for t, v, _ in rows if t]
    untyped = total - len(typed_rows)
    wrong = sum(1 for t, v in typed_rows if v.cert and v.cert != t.lstrip("0"))
    n = len(typed_rows)
    bound = (f"0 wrong in {n} only shows the true wrong-read rate is below about {300 / n:.0f}% (95% confidence, rule of three): "
             f"at 1% a 330-slab batch would hold ~3 silent wrong certs. Cross-check 'ok' certs with tools.enrich (PSA API: the card "
             "must match the photo), and keep testing: several hundred typed slabs before trusting unattended output."
             if n and wrong == 0 else "")
    go = ok >= 0.95 * total and wrong == 0 and untyped == 0 and n > 0
    report = [
        f"slabs: {total}",
        f"confident read (ok), in scan order: {ok}/{total} = {100 * ok / total:.0f}%   (with the ITF format learned from the start: {ok_after}/{total})",
        f"back camera read something: {back_any}/{total}; front camera: {front_any}/{total}",
        f"symbologies seen: {dict(syms)}",
        f"ITF format learned: {itf.mode} (evidence {dict(itf.evidence)})",
        f"WRONG certs vs what you typed: {wrong} of {n} typed  <- must be 0" + (f"; {untyped} NOT typed (every slab must be typed)" if untyped else ""),
    ]
    if bound:
        report.append(bound)
    report.append(("GO" if go else "HOLD") + ": GO needs every slab typed, ok >= 95% in scan order, and wrong == 0.")
    if not go:
        report.append("Before building: re-focus (focus head / focus station), move the LED ring or add the light roof against glare, and re-scan "
                      "the failed slabs. Still failing? Show your instructor phase0.csv and the images/ folder, or open an issue in the "
                      "project repository with both attached.")
    return report


if __name__ == "__main__":
    raise SystemExit(main())
