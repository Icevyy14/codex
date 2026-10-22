"""Real-label check: run the machine's decoding, consensus and face-down rules on photos of YOUR slabs.

Input: an index.json listing the images, one entry per image, for example
    {"file": "psa_27435764_front.jpg", "grader": "PSA", "side": "front", "cert_number": "27435764", "era": "PSA current"}
  file (or path): relative to the index's folder. side: front | back, the label side in the picture. cert_number: the
  printed cert (leading zeros do not matter); leave it out if unknown (the image then only shows what it decodes).
  grader, era: only group the table (optional). An entry with "good": false is skipped unless --all. The images of
  one slab share a "slab_key" (default: grader + cert).
Or --phase0 DIR: the captures of a Phase 0 run (DIR/phase0.csv and DIR/images/), the typed certs as the truth.

Modes:
  native (default)  every image as it is: a phone photo, a scan, a Phase 0 frame.
  --machine         every image rescaled to what the machine's cameras would see: 0.055 mm/px for backs (head camera
                    at 140 mm, plus a hover frame at 147 mm cropped to the pocket, as the runner does), 0.039 mm/px for
                    fronts (station camera), with +/-2 mm offset, +/-1 deg, +/-10 % exposure, blur sigma 1 px, sensor
                    noise, and JPEG for the head camera. The scale comes from the slab's width (80.3 mm); an image
                    coarser than the camera (beyond --max-upscale) is skipped. --glare puts a hot spot on the label of
                    the hover frame and of the second frame of each camera. Flat photos have no slab-plastic
                    reflections, curvature or lens edge effects: the machine will do worse than this.

Per slab it replays the runner's reading order (hover + back frames -> decide; front frames if not 'ok'; front OCR if
nothing or only barcodes were read) through the real Runner._decide, and applies the face-down rule
(certs.face_from_above) to each back seen from above (must give 'down' or 'unknown') and each front seen from above,
i.e. a face-up slab (must give 'up' or 'unknown').

Prints per category: the read rate per frame, slab verdicts, wrong certs, face-down proofs and unparsed payloads. Exit
code 1 if a slab came out 'ok' with a wrong cert or a face-up slab was 'proven' face-down.

Run from software/:
  python -m tools.real_eval /path/to/index.json
  python -m tools.real_eval /path/to/index.json --machine --workers 3
  python -m tools.real_eval --phase0 phase0_results
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import re
import statistics
import sys
import time
import types
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from slabscan.certs import CodeRead, ItfModel, face_from_above  # noqa: E402
from slabscan.decode import decode_frame, label_band, ocr_available, ocr_digits  # noqa: E402

SLAB_W_MM, SLAB_H_MM = 80.3, 135.5
HEAD_WH, STA_WH = (3264, 2448), (4608, 2592)  # head camera (USB, MJPEG) and station camera (Camera Module 3) frames
HEAD_MMPX = 0.055  # held slab, lens 140 mm from its back
HOVER_MMPX = HEAD_MMPX * 147.0 / 140.0  # hover frame: lens 147 mm above the top slab (runner: lens + approach_gap 5 + 2)
STA_MMPX = 0.039
LABEL_CENTRE_MM = 15.0  # label centre below the slab's top edge (about, all graders)
STATUSES = ("ok", "needs_review", "conflict", "no_read", "other_grader")


# ---------------------------------------------------------------------------------------------------- the images
def _truth(cert) -> str | None:
    m = re.search(r"\d{6,}", str(cert or ""))
    return (m.group(0).lstrip("0") or None) if m else None


def load_index(index: Path, root: Path | None = None, include_all: bool = False) -> list[dict]:
    entries = json.loads(Path(index).read_text())
    root = Path(root) if root else Path(index).resolve().parent
    use_good = any("good" in e for e in entries) and not include_all
    items = []
    for e in entries:
        if use_good and not e.get("good"):
            continue
        rel = e.get("path") or e.get("file")
        side = str(e.get("side", "")).lower()
        if not rel or side not in ("front", "back"):
            continue
        grader = str(e.get("grader_detail") or e.get("grader") or "?")
        era = str(e.get("era") or "")
        truth = _truth(e.get("cert_number"))
        items.append({"path": str(root / rel), "rel": rel, "side": side, "grader": grader,
                      "category": era if era.lower().startswith(grader.lower()) else f"{grader} {era}".strip(),
                      "truth": truth, "slab": str(e.get("slab_key") or (f"{grader}-{truth}" if truth else rel))})
    return items


def load_phase0(d: Path) -> list[dict]:
    """A Phase 0 run: slab n's first back and front capture, its typed cert; and the face-up pass frames (head camera,
    face-up slab: a front seen from above)."""
    d = Path(d)
    items = []
    with (d / "phase0.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            n = int(row["n"])
            truth = _truth(row.get("printed_cert_typed"))
            for side in ("back", "front"):
                p = d / "images" / f"{n:03d}_{side}_0.jpg"
                if p.exists():
                    items.append({"path": str(p), "rel": p.name, "side": side, "grader": "?", "category": "phase0", "truth": truth,
                                  "slab": f"phase0-{n}"})
    for p in sorted((d / "images").glob("faceup_*.jpg")):
        items.append({"path": str(p), "rel": p.name, "side": "front", "grader": "?", "category": "phase0 face-up pass", "truth": None,
                      "slab": p.stem, "above_only": True})
    return items


# ---------------------------------------------------------------------------------------------------- machine frames
def slab_bbox(gray: np.ndarray) -> tuple[tuple[int, int, int, int], str]:
    """(x0, y0, x1, y1) of the slab in a product photo: the background is the colour of the outer ring if that is
    uniform; otherwise the slab fills the frame."""
    h, w = gray.shape
    s = 400.0 / max(h, w)
    sm = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA).astype(np.float32)
    H, W = sm.shape
    b = max(2, int(0.01 * max(H, W)))
    ring = np.concatenate([sm[:b].ravel(), sm[-b:].ravel(), sm[:, :b].ravel(), sm[:, -b:].ravel()])
    med, spread = float(np.median(ring)), float(np.percentile(ring, 90) - np.percentile(ring, 10))
    if spread > 40:
        return (0, 0, w, h), "full"
    diff = (np.abs(sm - med) > 30).astype(np.uint8)
    diff = cv2.morphologyEx(diff, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cols = np.where(diff.mean(axis=0) > 0.25)[0]
    rows = np.where(diff.mean(axis=1) > 0.25)[0]
    if len(cols) < W * 0.3 or len(rows) < H * 0.3:
        return (0, 0, w, h), "full?"
    return (int(cols[0] / s), int(rows[0] / s), int((cols[-1] + 1) / s), int((rows[-1] + 1) / s)), "bg"


def mm_per_px(gray: np.ndarray) -> tuple[float, tuple[int, int, int, int]]:
    """Scale of a slab photo from the slab's width (the label scale); from its height when a shadow cut the width."""
    (x0, y0, x1, y1), how = slab_bbox(gray)
    a, b = SLAB_W_MM / max(1, x1 - x0), SLAB_H_MM / max(1, y1 - y0)
    return (b if how == "bg" and abs(a / b - 1) > 0.05 else a), (x0, y0, x1, y1)


def _seed(path: str, tag: str) -> int:
    return int(hashlib.sha256(f"{Path(path).name}|{tag}".encode()).hexdigest()[:8], 16)


def synth(gray, bbox, mmpx, target, frame_wh, top_mm, rng, bg, jpeg=None, glare=False, blur=1.0, noise=3.0) -> np.ndarray:
    """The slab (label end up) placed in a camera frame at ``target`` mm/px: centred, or with its top edge ``top_mm``
    below the frame's top; +/-2 mm offset, +/-1 deg, +/-10 % exposure, blur, a glare spot on the label, noise, JPEG."""
    x0, y0, x1, y1 = bbox
    s = mmpx / target
    small = cv2.resize(gray[y0:y1, x0:x1], None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    sh, sw = small.shape
    W, H = frame_wh
    dx, dy = rng.uniform(-2.0, 2.0, 2) / target
    cx = W / 2 + dx
    cy = (H / 2 if top_mm is None else top_mm / target + sh / 2) + dy
    m = cv2.getRotationMatrix2D((sw / 2, sh / 2), rng.uniform(-1.0, 1.0), 1.0)
    m[0, 2] += cx - sw / 2
    m[1, 2] += cy - sh / 2
    frame = cv2.warpAffine(small, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=bg).astype(np.float32)
    frame *= rng.uniform(0.9, 1.1)
    if blur:
        frame = cv2.GaussianBlur(frame, (0, 0), blur)
    if glare:  # a saturated spot about 16 x 10 mm on the label band
        gx = cx + rng.uniform(-30, 30) / target
        gy = cy - sh / 2 + LABEL_CENTRE_MM / target + rng.uniform(-5, 5) / target
        sig = 5.0 / target
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        a = 0.95 * np.exp(-(((xx - gx) ** 2) / (2 * (1.6 * sig) ** 2) + ((yy - gy) ** 2) / (2 * sig ** 2)))
        frame = frame * (1 - a) + 255 * a
    frame += rng.normal(0, noise, frame.shape).astype(np.float32)
    frame = np.clip(frame, 0, 255).astype(np.uint8)
    if jpeg:
        _, enc = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
        frame = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    return frame


def machine_config(path: str | None = None):
    from slabscan.config import from_layout, load

    p = Path(path) if path else SOFTWARE_DIR / "config" / "machine.toml"
    return load(p, p.parent / "calibration.toml") if p.exists() else from_layout()


def head_roi(cfg, distance_mm: float):
    """The runner's own crop of a head-camera frame to the pocket under the cup (Runner._head_roi)."""
    from slabscan.runner import Runner

    f = types.SimpleNamespace(cfg=cfg, head_cam=object())
    f._row_half_mm = types.MethodType(Runner._row_half_mm, f)
    return Runner._head_roi(f, distance_mm)


def frames_for(item: dict, img: np.ndarray, machine: bool, glare: bool, max_upscale: float, cfg) -> tuple[list[tuple], str]:
    """[(name, camera, frame, roi)] for one image, or ([], why it was skipped). Camera 'back' = the head camera."""
    side = item["side"]
    if not machine:
        return [("native", "back" if side == "back" else "front", img, None)], ""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    mm, bbox = mm_per_px(gray)
    target = HEAD_MMPX if side == "back" else STA_MMPX
    if mm > max_upscale * target:
        return [], f"native {mm:.3f} mm/px is coarser than the camera ({target} mm/px)"
    roi_hover, roi_held = head_roi(cfg, 147.0), head_roi(cfg, 140.0)
    path = item["path"]
    pose, hover_pose = _seed(path, "pose"), _seed(path, "hoverpose")
    out = []

    def add(name, cam, target_, wh, top, bg, jpeg, glare_, roi, pose_seed, extra_noise=None):
        f = synth(gray, bbox, mm, target_, wh, top, np.random.default_rng(pose_seed), bg, jpeg=jpeg, glare=glare_)
        if extra_noise is not None:  # a second capture of the same pose: new sensor noise only
            f = np.clip(f.astype(np.int16) + np.random.default_rng(extra_noise).normal(0, 2.0, f.shape).astype(np.int16), 0, 255).astype(np.uint8)
        out.append((name, cam, f, roi))

    if side == "back" and not item.get("above_only"):
        add("hover", "back", HOVER_MMPX, HEAD_WH, None, 40, 85, glare, roi_hover, hover_pose)  # the frame that proves face-down
        add("held1", "back", HEAD_MMPX, HEAD_WH, None, 40, 85, False, roi_held, pose)
        if glare:
            add("held_glare", "back", HEAD_MMPX, HEAD_WH, None, 40, 85, True, roi_held, pose)
        else:
            add("held2", "back", HEAD_MMPX, HEAD_WH, None, 40, 85, False, roi_held, pose, _seed(path, "held2"))
    else:
        if not item.get("above_only"):
            top = (STA_WH[1] * STA_MMPX) / 2 - LABEL_CENTRE_MM  # the label centre on the station camera's axis
            add("station1", "front", STA_MMPX, STA_WH, top, 30, None, False, None, pose)
            if glare:
                add("station_glare", "front", STA_MMPX, STA_WH, top, 30, None, True, None, pose)
            else:
                add("station2", "front", STA_MMPX, STA_WH, top, 30, None, False, None, pose, _seed(path, "station2"))
        # a face-UP slab under the head camera at the hover height: the head sees the FRONT label
        add("faceup_hover", "back", HOVER_MMPX, HEAD_WH, None, 40, 85, glare, roi_hover, hover_pose)
    return out, ""


def _rd(r: CodeRead) -> dict:
    return dataclasses.asdict(r)


def image_job(item: dict, machine: bool, glare: bool, max_upscale: float, config: str | None) -> dict:
    """Decode every frame of one image (a worker process)."""
    cv2.setNumThreads(1)
    img = cv2.imread(item["path"], cv2.IMREAD_COLOR)
    if img is None:
        return {"error": "unreadable"}
    frames, skipped = frames_for(item, img, machine, glare, max_upscale, machine_config(config) if machine else None)
    if skipped:
        return {"skipped": skipped}
    out = {}
    for name, cam, frame, roi in frames:
        c0 = time.process_time()
        reads, unparsed = decode_frame(frame, cam, None, allow_ocr=False, roi=roi)
        out[name] = {"camera": cam, "reads": [_rd(dataclasses.replace(r, frame=f"{item['rel']}:{name}")) for r in reads], "unparsed": unparsed,
                     "cpu_s": round(time.process_time() - c0, 2)}
    return {"frames": out}


def ocr_job(item: dict, machine: bool, glare: bool, max_upscale: float, config: str | None, frame_name: str, reads: list[dict]) -> list[dict]:
    """Front OCR as the runner does it: the last front frame, cropped to the label around a barcode read from below."""
    cv2.setNumThreads(1)
    img = cv2.imread(item["path"], cv2.IMREAD_COLOR)
    frames, _ = frames_for(item, img, machine, glare, max_upscale, machine_config(config) if machine else None)
    frame = next(f for n, _, f, _ in frames if n == frame_name)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    rs = [CodeRead(**{**r, "box": tuple(r["box"]) if r.get("box") else None}) for r in reads]
    band = label_band(gray.shape, [r for r in rs if r.camera == "front"])
    return [_rd(dataclasses.replace(r, frame=f"{item['rel']}:ocr")) for r in ocr_digits(gray, "front", band=band)]


# ---------------------------------------------------------------------------------------------------- slab replay
def _reads(d: dict | None) -> list[CodeRead]:
    return [CodeRead(**{**r, "box": tuple(r["box"]) if r.get("box") else None}) for r in (d or {}).get("reads", [])]


def replay(slab: list[dict], res: dict, cfg, rows: list, ocr: dict) -> dict:
    """The runner's reading order for one slab, through the real Runner._decide (with the batch's earlier verdicts, so
    the duplicate-cert rule runs too). ``ocr``: front OCR reads by image (None = not run yet)."""
    from slabscan.runner import Runner, needs_ocr

    back = next((i for i in slab if i["side"] == "back" and not i.get("above_only")), None)
    front = next((i for i in slab if i["side"] == "front" and not i.get("above_only")), None)
    bf = res.get(back["rel"], {}).get("frames", {}) if back else {}
    ff = res.get(front["rel"], {}).get("frames", {}) if front else {}
    hover = _reads(bf.get("hover"))
    held = [r for n in ("native", "held1", "held2", "held_glare") for r in _reads(bf.get(n))]
    front_names = [n for n in ("native", "station1", "station2", "station_glare") if n in ff]
    front_reads = [r for n in front_names for r in _reads(ff.get(n))]
    stub = types.SimpleNamespace(cfg=cfg, itf=ItfModel(), w=types.SimpleNamespace(rows=rows))
    reads, heldr = hover + held, list(held)
    stage = "back"
    v = Runner._decide(stub, reads, heldr) if (bf or not ff) else None
    want_ocr = False
    if (v is None or v.status != "ok") and ff:
        reads, heldr = reads + front_reads, heldr + front_reads
        v = Runner._decide(stub, reads, heldr)
        stage = "back+front" if bf else "front"
        if needs_ocr(v, reads):
            want_ocr = True
            o = ocr.get(front["rel"])
            if o:
                o = [CodeRead(**r) for r in o]
                reads, heldr = reads + o, heldr + o
                v = Runner._decide(stub, reads, heldr)
                stage += "+ocr"
    rows.append(types.SimpleNamespace(position=len(rows) + 1, verdict=v))
    return {"verdict": v, "stage": stage, "want_ocr": want_ocr, "front": front, "front_frame": front_names[-1] if front_names else None,
            "front_reads": [_rd(r) for r in front_reads]}


# ---------------------------------------------------------------------------------------------------- report
def _above(item: dict, frames: dict) -> dict | None:
    """The frame showing this label side from above (hover frame; native: the image itself)."""
    if not frames:
        return None
    if item["side"] == "back":
        return frames.get("hover") or frames.get("native")
    return frames.get("faceup_hover") or frames.get("native")


def evaluate(items: list[dict], machine: bool = False, glare: bool = False, ocr: bool = True, workers: int = 2, max_upscale: float = 1.15,
             config: str | None = None, log=print) -> dict:
    cfg = machine_config(config)
    t0 = time.monotonic()
    res: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {it["rel"]: ex.submit(image_job, it, machine, glare, max_upscale, config) for it in items}
        for n, (rel, fu) in enumerate(futs.items(), 1):
            try:
                res[rel] = fu.result()
            except Exception as e:  # noqa: BLE001 - one bad image must not end the run
                res[rel] = {"error": repr(e)}
            if n % 10 == 0 or n == len(futs):
                log(f"  decoded {n}/{len(futs)} images ({time.monotonic() - t0:.0f} s)")
        slabs: dict[str, list[dict]] = defaultdict(list)
        for it in items:
            slabs[it["slab"]].append(it)
        ocr_reads: dict[str, list] = {}
        if ocr and ocr_available():
            rows: list = []
            todo = {}
            for key, slab in slabs.items():
                r = replay(slab, res, cfg, rows, {})
                if r["want_ocr"] and r["front"] is not None:
                    todo[r["front"]["rel"]] = ex.submit(ocr_job, r["front"], machine, glare, max_upscale, config, r["front_frame"], r["front_reads"])
            for rel, fu in todo.items():
                try:
                    ocr_reads[rel] = fu.result()
                except Exception as e:  # noqa: BLE001
                    log(f"  OCR failed on {rel}: {e!r}")
            if todo:
                log(f"  front OCR on {len(todo)} slabs ({time.monotonic() - t0:.0f} s)")
    rows = []
    out_slabs = []
    skipped_slabs = []
    for key, slab in slabs.items():
        if all(i.get("above_only") for i in slab):
            continue  # a face-up pass frame: only the face-down rule looks at it
        if not any(res.get(i["rel"], {}).get("frames") for i in slab if not i.get("above_only")):
            skipped_slabs.append(key)  # no usable image (all too coarse for --machine, or unreadable)
            continue
        r = replay(slab, res, cfg, rows, ocr_reads)
        truth = next((i["truth"] for i in slab if i["truth"]), None)
        v = r["verdict"]
        out_slabs.append({"slab": key, "category": slab[0]["category"], "truth": truth, "status": v.status, "cert": v.cert, "grader": v.grader,
                          "note": v.note, "stage": r["stage"], "wrong": bool(truth and v.cert and v.cert != truth)})
    images = []
    for it in items:
        rr = res.get(it["rel"], {})
        frames = rr.get("frames", {})
        rec = {"image": it["rel"], "category": it["category"], "side": it["side"], "truth": it["truth"], "skipped": rr.get("skipped") or rr.get("error"),
               "frames": {}}
        for name, d in frames.items():
            certs = {r["cert"] for r in d["reads"]}
            rec["frames"][name] = {"truth": it["truth"], "read": bool(it["truth"] and it["truth"] in certs), "wrong": sorted(c for c in certs if it["truth"] and c != it["truth"]),
                                   "unparsed": d["unparsed"], "cpu_s": d["cpu_s"], "payloads": [f"{r['symbology']}:{r['raw']}" for r in d["reads"]]}
        above = _above(it, frames)
        if above is not None:
            face, why, _ = face_from_above(_reads(above), above["unparsed"])
            rec["face"], rec["face_why"] = face, why
        images.append(rec)
    return {"mode": "machine" + ("+glare" if glare else "") if machine else "native", "images": images, "slabs": out_slabs, "skipped_slabs": skipped_slabs,
            "seconds": round(time.monotonic() - t0, 1), "ocr": bool(ocr and ocr_available())}


def summarize(ev: dict) -> dict:
    slabs, images = ev["slabs"], ev["images"]
    st = Counter(s["status"] for s in slabs)
    backs = [i for i in images if i["side"] == "back" and "face" in i]
    fronts = [i for i in images if i["side"] == "front" and "face" in i]
    return {
        "mode": ev["mode"], "images": len(images), "skipped": sum(1 for i in images if i["skipped"]), "slabs": len(slabs),
        "skipped_slabs": len(ev.get("skipped_slabs", [])),
        "status": {k: st.get(k, 0) for k in STATUSES},
        "wrong_ok": [s for s in slabs if s["wrong"] and s["status"] == "ok"],
        "wrong_other": [s for s in slabs if s["wrong"] and s["status"] != "ok"],
        "backs": dict(Counter(i["face"] for i in backs)), "fronts": dict(Counter(i["face"] for i in fronts)),
        "false_down": [i["image"] for i in fronts if i["face"] == "down"],
        "false_up": [i["image"] for i in backs if i["face"] == "up"],
        "seconds": ev["seconds"],
    }


def report(ev: dict) -> list[str]:
    images, slabs = ev["images"], ev["slabs"]
    s = summarize(ev)
    out = [f"REAL-LABEL CHECK ({ev['mode']}, front OCR {'on' if ev['ocr'] else 'off'}): {s['images']} images ({s['skipped']} skipped), "
           f"{s['slabs']} slabs" + (f" (+{s['skipped_slabs']} with no usable image)" if s["skipped_slabs"] else "") + f", {ev['seconds']:.0f} s", "",
           "Per image: a frame 'reads' when a code in it gave the right cert; 'wrong' = frames where a code gave another number"]
    cells: dict[tuple, list] = defaultdict(list)
    for i in images:
        for name, f in i["frames"].items():
            cells[(i["category"], i["side"], name)].append(f)
    w = max([len(c) for c, _, _ in cells] + [20])
    out.append(f"  {'category':{w}} {'side':5} {'frame':13} {'read':>8} {'wrong':>6}")
    for (cat, side, name), fs in sorted(cells.items()):
        known = [f for f in fs if f["truth"]]
        out.append(f"  {cat:{w}} {side:5} {name:13} {sum(f['read'] for f in known):>4}/{len(known):<3} {sum(bool(f['wrong']) for f in known):>6}")
    out += ["", "Per slab (runner reading order): ok / needs_review / conflict / no_read / other_grader; wrong = a wrong cert in the verdict"]
    out.append(f"  {'category':{w}} {'n':>3}  {'ok/rev/conf/none/other':22} {'wrong ok':>8} {'wrong rev':>9}")
    by = defaultdict(list)
    for x in slabs:
        by[x["category"]].append(x)
    for cat, xs in sorted(by.items()):
        c = Counter(x["status"] for x in xs)
        out.append(f"  {cat:{w}} {len(xs):>3}  {'/'.join(str(c.get(k, 0)) for k in STATUSES):22} "
                   f"{sum(x['wrong'] and x['status'] == 'ok' for x in xs):>8} {sum(x['wrong'] and x['status'] != 'ok' for x in xs):>9}")
    tot = s["status"]
    out.append(f"  {'TOTAL':{w}} {len(slabs):>3}  {'/'.join(str(tot[k]) for k in STATUSES):22} {len(s['wrong_ok']):>8} {len(s['wrong_other']):>9}")
    out += ["", "Face-down rule from above: each back should give down/unknown, each front (a face-up slab) up/unknown"]
    out.append(f"  {'category':{w}} backs: {'down':>4} {'unkn':>4} {'up':>3} {'nbr':>3} | fronts: {'up':>3} {'unkn':>4} {'down':>4} {'nbr':>3}")
    fb = defaultdict(Counter)
    for i in images:
        if "face" in i:
            fb[(i["category"], i["side"])][i["face"]] += 1
    for cat in sorted({c for c, _ in fb}):
        b, f = fb[(cat, "back")], fb[(cat, "front")]
        out.append(f"  {cat:{w}}        {b['down']:>4} {b['unknown']:>4} {b['up']:>3} {b['neighbour']:>3} |         {f['up']:>3} {f['unknown']:>4} "
                   f"{f['down']:>4} {f['neighbour']:>3}")
    bt, ft = Counter(s["backs"]), Counter(s["fronts"])
    out.append(f"  {'TOTAL':{w}}        {bt['down']:>4} {bt['unknown']:>4} {bt['up']:>3} {bt['neighbour']:>3} |         {ft['up']:>3} "
               f"{ft['unknown']:>4} {ft['down']:>4} {ft['neighbour']:>3}")
    out += ["", f"WRONG CERT in an 'ok' verdict: {len(s['wrong_ok'])}  <- must be 0"]
    out += [f"  {x['slab']}: {x['status']} {x['cert']} (truth {x['truth']}) {x['note']}" for x in s["wrong_ok"]]
    if s["wrong_other"]:
        out.append(f"wrong number in a needs_review/conflict verdict (goes to you, not into the output): {len(s['wrong_other'])}")
        out += [f"  {x['slab']}: {x['status']} {x['cert']} (truth {x['truth']}) {x['note']}" for x in s["wrong_other"]]
    out.append(f"FALSE FACE-DOWN proofs (a face-up slab 'proven' face-down): {len(s['false_down'])}  <- must be 0")
    out += [f"  {x}" for x in s["false_down"]]
    if s["false_up"]:
        out.append(f"backs called face-UP (a stop, safe, but check the rule): {len(s['false_up'])}")
        out += [f"  {x}" for x in s["false_up"]]
    review = [x for x in slabs if x["status"] != "ok"]
    if review:
        out += ["", "Slabs that were not 'ok':"]
        out += [f"  {x['slab']}: {x['status']} {x['cert'] or '-'} ({x['grader']}, {x['stage']}) {x['note']}" for x in review]
    unparsed = sorted({u for i in images for f in i["frames"].values() for u in f["unparsed"]})
    if unparsed:
        out += ["", f"Unparsed payloads ({len(unparsed)} distinct): decoded, but no rule reads a cert from them"]
        out += [f"  {u}" for u in unparsed]
    skipped = [i for i in images if i["skipped"]]
    if skipped:
        out += ["", f"Skipped images ({len(skipped)}):"] + [f"  {i['image']}: {i['skipped']}" for i in skipped]
    cpu = [f["cpu_s"] for i in images for f in i["frames"].values()]
    if cpu:
        out += ["", f"decode CPU per frame: median {statistics.median(cpu):.2f} s, max {max(cpu):.2f} s (this computer; a Pi 5 core is slower)"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("index", nargs="?", help="index.json describing the images")
    ap.add_argument("--phase0", help="a Phase 0 results folder instead of an index")
    ap.add_argument("--root", help="folder the index's file paths are relative to (default: the index's folder)")
    ap.add_argument("--all", action="store_true", help="also the entries marked good: false")
    ap.add_argument("--machine", action="store_true", help="rescale to the machine cameras' resolution, with blur and noise")
    ap.add_argument("--glare", action="store_true", help="(--machine) a glare spot on the label of the hover frame and of the second frame of each camera")
    ap.add_argument("--max-upscale", type=float, default=1.15, help="(--machine) skip images coarser than this times the camera's mm/px")
    ap.add_argument("--no-ocr", action="store_true", help="no front OCR (faster; the runner would use it)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", help="only images whose path contains this text")
    ap.add_argument("--config", help="machine.toml (default config/machine.toml, or the CAD defaults)")
    ap.add_argument("--json", help="also write the full result here")
    a = ap.parse_args(argv)
    if bool(a.index) == bool(a.phase0):
        ap.error("give an index.json or --phase0 DIR")
    items = load_phase0(Path(a.phase0)) if a.phase0 else load_index(Path(a.index), Path(a.root) if a.root else None, a.all)
    if a.only:
        items = [i for i in items if a.only in i["rel"]]
    if not items:
        print("no images")
        return 2
    if not a.no_ocr and not ocr_available():
        print("(tesseract not installed: front OCR off)")
    ev = evaluate(items, machine=a.machine, glare=a.glare, ocr=not a.no_ocr, workers=a.workers, max_upscale=a.max_upscale, config=a.config)
    print("\n".join(report(ev)))
    s = summarize(ev)
    if a.json:
        Path(a.json).write_text(json.dumps({"summary": s, **ev}, indent=1, default=str))
    return 1 if s["wrong_ok"] or s["false_down"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
