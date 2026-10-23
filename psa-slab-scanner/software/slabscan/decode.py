"""Decode cert numbers from camera frames.

Strategy (cheapest first, stop as soon as something parses):
  1. zxing-cpp over the full frame, all symbologies (QR + every 1D type).
  2. Same, after CLAHE contrast equalisation (rescues glare / washed-out labels). On a head-camera ('back') frame this
     pass also runs when pass 1 read only a barcode: the back-label QR is what proves a slab face-down.
  3. Station-camera ('front') frames only: 0.75x and 0.6x downscales. Real CGC front Code128s with ink-spread bars
     failed at full resolution and read at 0.6-0.75x (2 of 4 failures; painting a white quiet zone around the label
     read none).
  4. Same as 1, on a 2x upscale (rescues barely-resolved 1D bars).
  5. Padded, upscaled bands of the frame (thin 1D codes with little quiet zone).
  6. Optional Tesseract OCR of the printed digits. The result is never 'ok' on its own.
"""

from __future__ import annotations

import math
import os
import shutil

import cv2
import numpy as np
import zxingcpp

from .certs import OCR_TOKEN_RE, TWO_D, CodeRead, parse_payload

# Tesseract's OpenMP threads crawl on a busy CPU: on a loaded 4-core box every OCR call hit the 30 s timeout with the
# default threads, and took 1-3 s with one thread (real labels, Oct 2026). Set before pytesseract starts tesseract,
# which inherits this environment. setup_pi.sh sets it in the systemd unit too.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

_QR_FORMATS = TWO_D
PHANTOM_THICKNESS = 1 / 3  # a 1D read inside another read of its symbology, thinner than this share of it, is a phantom


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _source_for(symbology: str, camera: str, side: str | None = None) -> str:
    """The printed symbol a read comes from: the label side it is printed on + qr/barcode. ``side`` comes from the
    payload when its format proves it (certs.SIDE_PROOFS: a PSA or graded-CGC QR is on the back label; a CGC Authentic
    QR and the CGC 10/13-digit barcode are on the front). Otherwise the camera says it: the head camera ('back') looks
    at the back label of a face-down slab, the station camera ('front') at its front. PSA ITF and Code128 are printed
    on both sides, so for them the camera decides. Two reads of one printed symbol are one source, not two."""
    is_2d = symbology in _QR_FORMATS
    side = side or {"back": "back", "front": "front"}.get(camera)
    if side is None:
        return "back_qr" if is_2d else "barcode"
    return f"{side}_{'qr' if is_2d else 'barcode'}"


def _quad(b) -> tuple[list[tuple[float, float]], float, float]:
    """(corners, length along the scan direction, thickness along the bars) of a zxing-cpp result."""
    p = b.position
    pts = [(p.top_left.x, p.top_left.y), (p.top_right.x, p.top_right.y), (p.bottom_right.x, p.bottom_right.y), (p.bottom_left.x, p.bottom_left.y)]
    d = lambda a, c: math.hypot(a[0] - c[0], a[1] - c[1])  # noqa: E731
    return pts, (d(pts[0], pts[1]) + d(pts[3], pts[2])) / 2, (d(pts[0], pts[3]) + d(pts[1], pts[2])) / 2


def _phantoms(results) -> set[int]:
    """Indexes of linear reads that lie inside another read of the same symbology and are less than a third of its
    thickness. Real case: at full resolution zxing-cpp read Code128 '27435764' (box y 486-547 px) and also '09435764'
    from a 12 px band inside it (y 522-534, the same x span); the phantom then made the slab a conflict."""
    info = []
    for b in results:
        sym = b.format.name if hasattr(b.format, "name") else str(b.format)
        pts, length, thick = _quad(b)
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        info.append((sym, (min(xs), min(ys), max(xs), max(ys)), length, thick))
    out = set()
    for i, (sym, (a0, b0, a1, b1), _, thick) in enumerate(info):
        if sym in _QR_FORMATS:
            continue
        for j, (sym2, (c0, d0, c1, d1), length2, thick2) in enumerate(info):
            if j == i or sym2 != sym or thick >= thick2 * PHANTOM_THICKNESS:
                continue
            tol = 3 + 0.03 * length2
            if a0 >= c0 - tol and a1 <= c1 + tol and b0 >= d0 - tol and b1 <= d1 + tol:
                out.add(i)
                break
    return out


def _zxing_pass(gray: np.ndarray, camera: str, custom_regex: str | None, to_frame=None) -> tuple[list[CodeRead], list[str]]:
    """Decode one prepared image. ``to_frame(x, y)`` maps its pixels back to the frame given to decode_frame (for
    CodeRead.box)."""
    reads: list[CodeRead] = []
    unparsed: list[str] = []
    results = list(zxingcpp.read_barcodes(gray))
    phantom = _phantoms(results)
    for k, b in enumerate(results):
        if k in phantom:
            continue
        sym = b.format.name if hasattr(b.format, "name") else str(b.format)
        p = parse_payload(b.text, sym, custom_regex)
        if p:
            pts, _, _ = _quad(b)
            if to_frame is not None:
                pts = [to_frame(x, y) for x, y in pts]
            box = (int(min(x for x, _ in pts)), int(min(y for _, y in pts)), int(max(x for x, _ in pts)), int(max(y for _, y in pts)))
            reads.append(CodeRead(cert=p.cert, source=_source_for(sym, camera, p.side), symbology=sym, raw=b.text, camera=camera, grader=p.grader, box=box,
                                  kind=p.kind))
        else:
            unparsed.append(f"{sym}:{b.text}")
    return reads, unparsed


_clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))


def roi_px(shape, roi: tuple[float, float, float, float] | None) -> tuple[int, int, int, int] | None:
    """``roi`` = (x0, y0, x1, y1) as fractions of the width/height -> pixel bounds (a, c, b, d) = x0, y0, x1, y1, or
    None for the whole frame (also when the crop would be under 8 px)."""
    if roi is None:
        return None
    h, w = shape[:2]
    x0, y0, x1, y1 = roi
    a, b = max(0, int(round(x0 * w))), min(w, int(round(x1 * w)))
    c, d = max(0, int(round(y0 * h))), min(h, int(round(y1 * h)))
    if b - a < 8 or d - c < 8:
        return None
    return a, c, b, d


def crop_roi(img: np.ndarray, roi: tuple[float, float, float, float] | None) -> np.ndarray:
    """Crop to ``roi`` = (x0, y0, x1, y1) as fractions of the width/height (None = whole frame)."""
    px = roi_px(img.shape, roi)
    if px is None:
        return img
    a, c, b, d = px
    return img[c:d, a:b]


def decode_frame(img: np.ndarray, camera: str = "", custom_regex: str | None = None, allow_ocr: bool = True,
                 roi: tuple[float, float, float, float] | None = None) -> tuple[list[CodeRead], list[str]]:
    """Return (cert reads, unparsed payloads) for one frame.

    ``unparsed`` holds decoded symbols that did not look like a cert ("Symbology:text"). They are logged so that
    calibration can reveal a payload format the rules do not know, and the face-down check reads them too (a CGC
    label QR without a cert). ``roi`` crops the frame first (the head camera also sees the neighbouring pockets'
    labels; only the slab under the cup may be read). Read boxes are in the pixels of ``img``.
    """
    full = _to_gray(img)
    px = roi_px(full.shape, roi)
    ox, oy = (px[0], px[1]) if px else (0, 0)
    gray = full[px[1]:px[3], px[0]:px[2]] if px else full
    all_unparsed: list[str] = []
    found: list[CodeRead] = []
    passes = [
        ("raw", lambda g: [(g, 1.0, 0.0, 0.0, 0.0)]),
        ("clahe", lambda g: [(_clahe.apply(g), 1.0, 0.0, 0.0, 0.0)]),
        ("x2", lambda g: [(cv2.resize(g, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC), 2.0, 0.0, 0.0, 0.0)]),
        ("tiles", _padded_tiles),
    ]
    if camera == "front":
        passes.insert(2, ("down", lambda g: [(cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), s, 0.0, 0.0, 0.0) for s in (0.75, 0.6)]))
    for name, prep in passes:
        for im, scale, pad_x, pad_y, y_off in prep(gray):
            def to_frame(x, y, s=scale, px_=pad_x, py_=pad_y, yo=y_off):
                return (x - px_) / s + ox, (y - py_) / s + yo + oy

            r, unparsed = _zxing_pass(im, camera, custom_regex, to_frame)
            have = {(x.symbology, x.raw) for x in found}
            found.extend(x for x in r if (x.symbology, x.raw) not in have)
            all_unparsed.extend(u for u in unparsed if u not in all_unparsed)
        if found:
            # A head-camera frame that showed only a barcode gets the CLAHE pass too: a QR lost in glare there is
            # what turns a face-down slab into a stop.
            if not (camera == "back" and name == "raw" and not any(x.symbology in _QR_FORMATS for x in found)):
                return found, all_unparsed
    if found:
        return found, all_unparsed
    if allow_ocr:
        return ocr_digits(gray, camera), all_unparsed
    return [], all_unparsed


def _padded_tiles(gray: np.ndarray) -> list[tuple[np.ndarray, float, float, float, float]]:
    """Overlapping horizontal bands, upscaled and given a white quiet zone: (image, scale, pad x, pad y, band top).

    A thin 1D code sits among label text with almost no quiet zone. Full-frame decoding of real labels has been
    reported to fail where padded crops succeed.
    """
    h, w = gray.shape
    out = []
    band = max(24, h // 4)
    for y0 in range(0, max(1, h - band // 2), band // 2):
        crop = gray[y0:y0 + band, :]
        crop = cv2.resize(_clahe.apply(crop), None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        out.append((cv2.copyMakeBorder(crop, 40, 40, 60, 60, cv2.BORDER_CONSTANT, value=255), 2.0, 60.0, 40.0, float(y0)))
    return out


OCR_MIN_STD = 8.0  # grey-level spread below this = nothing printed in view (blank label back, empty frame)
OCR_TIMEOUT_S = 30.0  # tesseract on a noisy frame can run for minutes; a label band takes ~1.5 s on a PC (one thread), more on a Pi


def ocr_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return True


def label_band(shape, reads: list[CodeRead]) -> tuple[int, int, int, int] | None:
    """Pixel crop (x0, y0, x1, y1) of the label around the barcodes read in a frame: 3.2 barcode lengths either side
    along it (the label is about 4 lengths wide, and the barcode may sit at either end), 0.6 of its length across. On
    real PSA and CGC fronts the printed cert is on the barcode's own line. OCR of the whole frame turns the slab plastic
    and the card into thousands of specks; the label alone is faster and cleaner. None when no barcode was read."""
    boxes = [r.box for r in reads if r.box and r.symbology not in _QR_FORMATS and r.source != "ocr"]
    if not boxes:
        return None
    h, w = shape[:2]
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    length = max(x1 - x0, y1 - y0)
    along, across = (3.2 * length, 0.6 * length)
    ex, ey = (along, across) if x1 - x0 >= y1 - y0 else (across, along)
    a, b = max(0, int(x0 - ex)), min(w, int(x1 + ex))
    c, d = max(0, int(y0 - ey)), min(h, int(y1 + ey))
    if b - a < 16 or d - c < 16:
        return None
    return a, c, b, d


def ocr_digits(gray: np.ndarray, camera: str = "", band: tuple[int, int, int, int] | None = None) -> list[CodeRead]:
    """Last-resort OCR: the longest cert-shaped digit run on the label (PSA 8-9 digits, CGC 10 or 140 + 10).

    Years ("2023"), card numbers ("#025") and grades are all shorter, so length is a good filter. ``band`` crops to
    the label first (label_band). OCR is never trusted on its own: it names no grader, and it reads other digit runs
    on the card too, so an OCR-only number is needs_review. Its reads have grader 'unknown'.
    """
    if not ocr_available():
        return []
    if band is not None:
        a, c, b, d = band
        gray = gray[c:d, a:b]
    if float(np.std(gray)) < OCR_MIN_STD:
        # Otsu would turn pure sensor noise into thousands of specks, and tesseract --psm 11 then
        # takes minutes (measured: 100 s for one blank 900x1800 frame) to find nothing.
        return []
    import pytesseract

    _, bw = cv2.threshold(_clahe.apply(gray), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    try:
        text = pytesseract.image_to_string(bw, config="--psm 11 -c tessedit_char_whitelist=0123456789", timeout=OCR_TIMEOUT_S)
    except RuntimeError:  # pytesseract raises RuntimeError on timeout
        return []
    tokens = sorted(set(OCR_TOKEN_RE.findall(text)), key=len, reverse=True)
    out = []
    for t in tokens[:1]:
        p = parse_payload(t, "OCR")
        if p:
            out.append(CodeRead(cert=p.cert, source="ocr", symbology="OCR", raw=t, camera=camera, grader=p.grader, kind=p.kind))
    return out
