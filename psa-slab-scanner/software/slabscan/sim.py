"""Synthetic slab label images for testing without real slabs or hardware.

These are NOT pixel copies of real labels. They are stand-ins with realistic size, code size and failure modes
(glare, blur, tilt, low resolution), used to prove the decode pipeline and to size the camera. What each label
CARRIES does follow the real labels, per grader and era (``label_codes``; the payload formats are in certs.py and were
read off 64 real PSA/CGC/BGS/SGC slabs). ``tools/real_eval.py`` runs the same pipeline on real photos.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np
import zxingcpp

PX_PER_MM_RENDER = 40  # render resolution before degradation
LABEL_W_MM, LABEL_H_MM = 70.0, 20.0
SLAB_W_MM, SLAB_H_MM = 80.3, 135.5
LABEL_TOP_MM = 5.0  # label offset from slab top edge (guess - calibrate on real slabs)

# Label eras. PSA: "current" (back QR + Code128, front Code128), "2017+" (a back QR: QR + ITF for certs of up to 8
# digits = the 2017+ "lighthouse" label, QR + Code128 for 9-digit certs = the current label, as on real slabs), "2016"
# (back ITF only; "2015" means the same), "old" (before 2016: front ITF only, nothing on the back). CGC: "2023+" (front
# Code128, back QR with the grade; also used for any non-CGC era string), "og" (2020-23: back QR on cgccomics.com + a
# 26-digit Code128, nothing on the front), "authentic" (front QR with grade 0_0 + Code128, nothing on the back).
# BGS and SGC: no machine-readable code at all, the printed cert only.
PSA_ERAS = ("current", "2017+", "2016", "2015", "old")
CGC_ERAS = ("2023+", "og", "authentic")
_CGC_GRADES = ("10_0", "9_5", "9_0", "8_5", "8_0", "7_0")


def _stable_seed(*parts) -> int:
    return zlib.crc32("|".join(map(str, parts)).encode())


def itf_text(cert: str) -> str:
    """PSA's ITF payload: the cert zero-padded to 8 digits, on every real label. A cert longer than 8 digits never
    appears on an ITF label (9-digit certs use Code128); asked for one anyway, this pads it to an even length, which the
    parser rejects as a misread, as it rejects every ITF that is not 8 digits."""
    if len(cert) <= 8:
        return cert.zfill(8)
    return "0" + cert if len(cert) % 2 else cert


def psa_label(era: str, cert: str) -> str:
    """Which PSA label a slab of this era and cert carries: current | lighthouse | 2016 | old."""
    if era == "current" or (era == "2017+" and len(cert.lstrip("0")) > 8):
        return "current"
    if era == "2017+":
        return "lighthouse"
    if era in ("2016", "2015"):
        return "2016"
    if era == "old":
        return "old"
    raise ValueError(f"unknown PSA era {era!r} (one of {PSA_ERAS})")


def cgc_grade(cert: str) -> str:
    return _CGC_GRADES[_stable_seed("grade", cert) % len(_CGC_GRADES)]


def label_codes(cert: str, side: str, grader: str = "PSA", era: str = "2017+") -> list[tuple[str, str]]:
    """The machine-readable codes printed on one side ('front' | 'back') of a real label: [(symbology, payload)]."""
    if grader == "PSA":
        kind = psa_label(era, cert)
        if kind == "current":
            return [("Code128", cert)] if side == "front" else [("QRCode", f"https://www.psacard.com/cert/{cert}/"), ("Code128", cert)]
        itf = ("ITF", itf_text(cert))
        if side == "front":
            return [itf]
        if kind == "lighthouse":  # both URL forms are on real lighthouse labels
            url = f"http://psacard.com/cert/{cert}" if _stable_seed("url", cert) % 2 else f"https://www.psacard.com/cert/{cert}/"
            return [("QRCode", url), itf]
        return [itf] if kind == "2016" else []
    if grader == "CGC":
        era = era if era in CGC_ERAS else "2023+"
        if era == "og":
            if side == "front":
                return []
            prefix = str(4700000000000000 + _stable_seed("og", cert) % 10**8 * 10**8)[:16]  # 16 digits, then the cert
            return [("QRCode", f"https://www.cgccomics.com/certlookup/{cert}/{cgc_grade(cert)}"), ("Code128", prefix + cert)]
        if era == "authentic":
            return [("QRCode", f"https://www.cgccards.com/certlookup/{cert}/0_0/"), ("Code128", cert)] if side == "front" else []
        return [("Code128", cert)] if side == "front" else [("QRCode", f"https://www.cgccards.com/certlookup/{cert}/{cgc_grade(cert)}/")]
    return []  # BGS, SGC: the printed cert only


def has_back_code(grader: str, era: str, cert: str) -> bool:
    """Does the back label carry a code that proves the slab face-down (certs.SIDE_PROOFS)?"""
    return any(sym == "QRCode" or (grader == "CGC" and len(text) > 13) for sym, text in label_codes(cert, "back", grader, era))


_MODULE_MM = {"QRCode": 0.42, "ITF": 0.25, "Code128": 0.25}  # [Guessing] from photos; CGC codes are drawn smaller below


def _symbol(text: str, fmt: str, module_mm: float, height_mm: float | None = None) -> np.ndarray:
    """Render a symbol with a given module size in mm at PX_PER_MM_RENDER."""
    if fmt == "ITF" and len(text) % 2:
        text = "0" + text  # ITF needs an even digit count
    bc = zxingcpp.create_barcode(text, getattr(zxingcpp.BarcodeFormat, fmt))
    img = np.array(zxingcpp.write_barcode_to_image(bc, scale=1, add_quiet_zones=True))
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    scale = module_mm * PX_PER_MM_RENDER
    w = max(1, int(round(img.shape[1] * scale)))
    if height_mm is None:  # 2D symbol: square modules
        h = max(1, int(round(img.shape[0] * scale)))
    else:  # 1D symbol: stretch bars to the requested height
        img = img[:1, :] if img.shape[0] > 1 else img
        h = int(round(height_mm * PX_PER_MM_RENDER))
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_NEAREST)


def _paste(canvas: np.ndarray, sym: np.ndarray, x_mm: float, y_mm: float) -> None:
    x, y = int(x_mm * PX_PER_MM_RENDER), int(y_mm * PX_PER_MM_RENDER)
    h, w = sym.shape
    h = min(h, canvas.shape[0] - y)
    w = min(w, canvas.shape[1] - x)
    canvas[y:y + h, x:x + w] = np.minimum(canvas[y:y + h, x:x + w], sym[:h, :w])


def _text(canvas: np.ndarray, s: str, x_mm: float, y_mm: float, size_mm: float) -> None:
    scale = size_mm * PX_PER_MM_RENDER / 22.0
    cv2.putText(canvas, s, (int(x_mm * PX_PER_MM_RENDER), int(y_mm * PX_PER_MM_RENDER)), cv2.FONT_HERSHEY_SIMPLEX, scale, 0, max(1, int(scale * 2)), cv2.LINE_AA)


def label_blank(grader: str, era: str, side: str) -> bool:
    """True when that side shows no label at all in the simulator (an old PSA label's back)."""
    return grader == "PSA" and side == "back" and psa_label(era, "1") == "old"


@lru_cache(maxsize=256)
def render_label(cert: str, side: str = "front", grader: str = "PSA", era: str = "2017+", module_mm: float | None = None) -> np.ndarray:
    """Grayscale label at PX_PER_MM_RENDER with the codes ``label_codes`` lists for that side, printed text and the
    printed cert. ``module_mm`` overrides the 1D module size (decode sweeps). Cached: treat the result as read-only."""
    canvas = np.full((int(LABEL_H_MM * PX_PER_MM_RENDER), int(LABEL_W_MM * PX_PER_MM_RENDER)), 245, np.uint8)
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1] - 1, canvas.shape[0] - 1), 120, 6)
    codes = label_codes(cert, side, grader, era)
    qr = [t for s, t in codes if s == "QRCode"]
    bars = [(s, t) for s, t in codes if s != "QRCode"]
    if side == "front":
        tx = 20 if qr else 3  # a CGC Authentic front has its QR at the left end
        _text(canvas, "2023 POKEMON SV151", tx, 5, 2.4)
        _text(canvas, "#199 CHARIZARD EX", tx, 9, 2.4)
        _text(canvas, "SPECIAL ILLUS. RARE", tx, 13, 2.4)
        if not qr:  # an Authentic label carries no grade
            _text(canvas, {"PSA": "GEM MT 10", "CGC": "MINT 9"}.get(grader, "NM-MT 8.5"), 50, 6, 2.6)
    else:
        _text(canvas, grader if grader in ("PSA", "CGC", "BGS", "SGC") else "", 30, 9, 4)
    if qr:  # the QR at the left end: the back label, or a CGC Authentic front
        q = _symbol(qr[0], "QRCode", _MODULE_MM["QRCode"] if grader == "PSA" else 0.38)
        _paste(canvas, q, 2, (LABEL_H_MM - q.shape[0] / PX_PER_MM_RENDER) / 2)
    for sym, text in bars:
        if grader == "CGC":  # short bars: the CGC front Code128 is the weakest symbol on real labels (~1.7 mm bars)
            bar = _symbol(text, sym, module_mm or 0.2, height_mm=1.8 if side == "front" else 3.0)
            _paste(canvas, bar, LABEL_W_MM - 2.5 - bar.shape[1] / PX_PER_MM_RENDER, LABEL_H_MM - 4.5 if side == "front" else 13)
        elif side == "front":
            bar = _symbol(text, sym, module_mm or _MODULE_MM[sym], height_mm=4.5)
            _paste(canvas, bar, LABEL_W_MM - 3 - bar.shape[1] / PX_PER_MM_RENDER, 8.5)
        else:
            bar = _symbol(text, sym, module_mm or _MODULE_MM[sym], height_mm=3.5)
            _paste(canvas, bar, LABEL_W_MM - 2 - bar.shape[1] / PX_PER_MM_RENDER, 12)
    # [Likely, two real pre-2016 labels: OCR read '02074012', '01418255'] PSA prints a 7-digit cert zero-padded to 8; BGS to 10
    printed = cert.zfill(8) if grader == "PSA" else cert.zfill(10) if grader == "BGS" else cert
    if side == "front":
        _text(canvas, printed, 40 if grader == "PSA" else 20 if qr else 3, 18, 2.4)  # printed cert, fully inside the label
    elif grader == "PSA" or qr:
        _text(canvas, printed, 52 if grader == "PSA" else 30, 10 if grader == "PSA" else 12.2, 2.2)
    return canvas


@dataclass
class Degrade:
    mm_per_px: float = 0.06  # camera resolution on the slab
    blur_px: float = 0.8  # gaussian sigma in output pixels (defocus/motion)
    tilt_deg: float = 4.0  # perspective tilt of the slab vs. sensor
    rotate_deg: float = 1.5  # in-plane rotation (slab not square in slot)
    glare: float = 0.0  # 0..1 strength of a specular hot spot
    glare_pos: tuple[float, float] = (0.5, 0.5)  # hot-spot centre, fraction of label
    noise: float = 3.0  # gaussian sensor noise (8-bit levels)
    jpeg_quality: int = 90
    haze: float = 0.12  # slab plastic lowers contrast


def slab_view(cert: str, side: str, deg: Degrade, grader: str = "PSA", era: str = "2017+", module_mm: float | None = None, seed: int = 0) -> np.ndarray:
    """Camera view of the top ~45 mm of a slab (label + border), degraded. The side with no label (an old PSA back)
    is the bare slab."""
    rng = np.random.default_rng(seed)
    view_w_mm, view_h_mm = SLAB_W_MM + 10, 45.0
    canvas = np.full((int(view_h_mm * PX_PER_MM_RENDER), int(view_w_mm * PX_PER_MM_RENDER)), 40, np.uint8)
    sx, sy = 5.0, 2.0  # slab corner within view
    cv2.rectangle(canvas, (int(sx * PX_PER_MM_RENDER), int(sy * PX_PER_MM_RENDER)), (int((sx + SLAB_W_MM) * PX_PER_MM_RENDER), canvas.shape[0]), 70, -1)
    lx = sx + (SLAB_W_MM - LABEL_W_MM) / 2
    ly = sy + LABEL_TOP_MM
    if not label_blank(grader, era, side):
        label = render_label(cert, side, grader, era, module_mm)
        y0, x0 = int(ly * PX_PER_MM_RENDER), int(lx * PX_PER_MM_RENDER)
        canvas[y0:y0 + label.shape[0], x0:x0 + label.shape[1]] = label
    spots = [((lx + deg.glare_pos[0] * LABEL_W_MM), (ly + deg.glare_pos[1] * LABEL_H_MM), deg.glare)] if deg.glare > 0 else []
    return _degrade(canvas.astype(np.float32), deg, rng, spots)


def _degrade(img: np.ndarray, deg: Degrade, rng, glare_spots=(), occluders=()) -> np.ndarray:
    """Plastic haze, glare hot spots (centre x/y in mm on the canvas, strength), tilt, rotation, camera resolution,
    blur, sensor noise and JPEG: what the camera does to a canvas rendered at PX_PER_MM_RENDER. ``occluders``
    (x0, y0, x1, y1, grey level) in canvas mm are parts of the head between the lens and the slab: drawn after the
    slab's tilt and rotation, because they move with the camera, not with the slab."""
    img = img * (1 - deg.haze) + 255 * deg.haze * 0.5
    if glare_spots:
        xs, ys = np.arange(img.shape[1], dtype=np.float32), np.arange(img.shape[0], dtype=np.float32)
        for gx, gy, strength in glare_spots:  # a Gaussian hot spot is separable: outer product of two 1-D profiles
            ex = np.exp(-(((xs - gx * PX_PER_MM_RENDER) / (14 * PX_PER_MM_RENDER)) ** 2))
            ey = np.exp(-(((ys - gy * PX_PER_MM_RENDER) / (6 * PX_PER_MM_RENDER)) ** 2))
            img = img + np.float32(255 * strength) * np.outer(ey, ex)
    img = np.clip(img, 0, 255).astype(np.uint8)
    h, w = img.shape
    t = np.tan(np.radians(deg.tilt_deg)) * 0.5
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[w * t * 0.3, 0], [w * (1 - t * 0.3), h * t * 0.2], [w, h], [0, h * (1 - t * 0.2)]])
    img = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=40)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg.rotate_deg, 1.0)
    img = cv2.warpAffine(img, m, (w, h), borderValue=40)
    scale = 1.0 / (deg.mm_per_px * PX_PER_MM_RENDER)
    out = cv2.resize(img, (max(8, int(w * scale)), max(8, int(h * scale))), interpolation=cv2.INTER_AREA)
    if occluders:
        out = _draw_occluders(out, occluders, 1.0 / deg.mm_per_px)
    if deg.blur_px > 0:
        out = cv2.GaussianBlur(out, (0, 0), deg.blur_px)
    out = np.clip(out.astype(np.float32) + rng.normal(0, deg.noise, out.shape), 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, deg.jpeg_quality])
    return cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)


# ---------------------------------------------------------------------- head camera: label end + card window
# Where the card sits in the slab, measured from the slab's label-end edge. [Guessing: from photos, not calipers;
# Phase 0 shows the real one (images/*_window.jpg).] The card is the standard 63.5 x 88.9 mm.
CARD_W_MM, CARD_H_MM = 63.5, 88.9
CARD_TOP_MM = 32.0
CARD_PX_PER_MM = 4  # the card patterns are smooth: rendered coarse, scaled up
# The head camera's synthetic view, in mm on the slab plane relative to the cup axis (= slab centre), image axes:
# x along the pocket row, y along the slab, label end at the top (negative y). It covers the label end and the top
# of the card window, where face_down_window_mm lies (the real lens sees the whole slab; nothing else is used).
HEAD_VIEW_MM = (-(SLAB_W_MM + 10) / 2, -SLAB_H_MM / 2 - 2.0, (SLAB_W_MM + 10) / 2, -12.0)
HOVER_MM = 147.0  # lens to slab back at the hover frame (140 + approach_gap 5 + 2)
CAM_ABOVE_CUP_MM = 140.0  # cad/model.py CAM_Z: head lens above the cup face

# Parts of the head between the lens and the slab: (x0, y0, x1, y1, z0, z1, grey) in mm, x/y from the cup axis
# (+y = toward the drop arm, away from the label), z above the cup face. "cad" = cad/model.py head_parts() and
# head_foot() today; "open" = a hypothetical head whose foot stays out of the card window (narrower, and clear of the
# label side of the buffer), used to test the learned face-down check; "none" = nothing in the way.
HEADS = {
    "cad": [
        (-12.5, -12.5, 12.5, 12.5, 0.0, 8.0, 25),  # 25 mm cup
        (-8.0, -8.0, 8.0, 8.0, 20.0, 62.0, 120),  # M10 spring buffer body
        (-15.0, -15.0, 15.0, 45.0, 62.0, 75.0, 52),  # head_foot body (PETG, matte black, lit by the ring above)
        (15.0, -16.5, 30.5, 16.5, 62.0, 75.0, 52),  # head_foot extension to the sensor post
        (-12.0, 23.0, 12.0, 47.0, 62.0, 93.0, 52),  # sleeve around the drop-arm end
        (-8.5, -8.5, 8.5, 8.5, 75.0, 83.0, 150),  # M10 nut on top of the foot
        (-3.0, -3.0, 3.0, 3.0, 75.0, 97.0, 170),  # buffer rod end
        (26.5, -16.5, 30.5, 16.5, 75.0, 99.0, 52),  # sensor post
        (16.0, -16.5, 26.5, 16.5, 86.0, 98.0, 32),  # optical endstop board
        (-10.0, 25.0, 10.0, 45.0, 65.0, 130.0, 60),  # drop arm
    ],
    "open": [
        (-12.5, -12.5, 12.5, 12.5, 0.0, 8.0, 25),
        (-8.0, -8.0, 8.0, 8.0, 20.0, 62.0, 120),
        (-11.0, -6.0, 11.0, 45.0, 62.0, 75.0, 52),
        (11.0, -6.0, 30.5, 6.0, 62.0, 75.0, 52),
        (-3.0, -3.0, 3.0, 3.0, 75.0, 97.0, 170),
        (-10.0, 25.0, 10.0, 45.0, 65.0, 130.0, 60),
    ],
    "none": [],
}


def head_shadow(kind: str = "cad", distance_mm: float = HOVER_MM) -> list[tuple[float, float, float, float, int]]:
    """What each head part hides on the slab plane ``distance_mm`` below the lens: (x0, y0, x1, y1, grey), mm from
    the cup axis, nearest part last. A part at height z above the cup face is (CAM_ABOVE_CUP_MM - z) from the lens,
    so it is magnified by distance / (CAM_ABOVE_CUP_MM - z); the box over its height range is the bounding box."""
    out = []
    for x0, y0, x1, y1, z0, z1, g in HEADS[kind]:
        s0, s1 = distance_mm / (CAM_ABOVE_CUP_MM - z0), distance_mm / (CAM_ABOVE_CUP_MM - z1)
        lo = lambda a: a * (s1 if a < 0 else s0)  # noqa: E731
        hi = lambda b: b * (s1 if b > 0 else s0)  # noqa: E731
        out.append((lo(x0), lo(y0), hi(x1), hi(y1), g))
    return out


def _draw_occluders(out: np.ndarray, occluders, px_per_mm: float) -> np.ndarray:
    """Head parts are ~70 mm in front of the focus plane: drawn flat, then defocused, over the slab image."""
    layer = out.copy()
    mask = np.zeros(out.shape, np.float32)
    for x0, y0, x1, y1, g in occluders:
        a, b = int(round(x0 * px_per_mm)), int(round(y0 * px_per_mm))
        c, d = int(round(x1 * px_per_mm)), int(round(y1 * px_per_mm))
        if c <= 0 or d <= 0 or a >= out.shape[1] or b >= out.shape[0]:
            continue
        cv2.rectangle(layer, (a, b), (c, d), int(g), -1)
        cv2.rectangle(mask, (a, b), (c, d), 1.0, -1)
    if not mask.any():
        return out
    sigma = 2.5
    layer = cv2.GaussianBlur(layer, (0, 0), sigma)
    mask = cv2.GaussianBlur(mask, (0, 0), sigma)
    return np.clip(out * (1 - mask) + layer * mask, 0, 255).astype(np.uint8)


@lru_cache(maxsize=8)
def card_back(kind: str = "pokemon_en") -> np.ndarray:
    """Procedural stand-in for a card back (NOT the real artwork), at CARD_PX_PER_MM: one fixed image per back type,
    so every card of that type shows the same back. 'pokemon_en' (dark border, swirl, a bright logo near the top) and
    'pokemon_jp' (lighter border, stripes and rings) are visibly different, as the real English and Japanese backs are."""
    s = CARD_PX_PER_MM
    h, w = int(round(CARD_H_MM * s)), int(round(CARD_W_MM * s))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) / s
    if kind == "pokemon_en":
        cx, cy = 0.62 * CARD_W_MM, 0.30 * CARD_H_MM
        r, th = np.hypot(xx - cx, yy - cy), np.arctan2(yy - cy, xx - cx)
        img = 95 + 45 * np.sin(0.45 * r + 2.0 * th) + 20 * np.sin(0.13 * xx + 0.21 * yy)
        img += 110 * np.exp(-(((xx - 24) / 14) ** 2 + ((yy - 16) / 5) ** 2))  # the logo
        border, level = 4.0, 55
    elif kind == "pokemon_jp":
        cx, cy = 0.30 * CARD_W_MM, 0.70 * CARD_H_MM
        r = np.hypot(xx - cx, yy - cy)
        img = 150 + 35 * np.sin(0.9 * yy) * np.cos(0.35 * xx) + 30 * np.cos(0.6 * r)
        border, level = 3.0, 175
    else:
        raise ValueError(f"unknown card back {kind!r}")
    edge = (xx < border) | (xx > CARD_W_MM - border) | (yy < border) | (yy > CARD_H_MM - border)
    img[edge] = level
    return np.clip(img, 0, 255).astype(np.uint8)


@lru_cache(maxsize=512)
def card_front(cert: str) -> np.ndarray:
    """Procedural card FRONT for one cert: a border, a name bar with 'letters', random art and a text box (or a
    full-art card), at CARD_PX_PER_MM. Different for every cert, as face-up slabs show their own card."""
    rng = np.random.default_rng(_stable_seed("front", cert))
    s = CARD_PX_PER_MM
    h, w = int(round(CARD_H_MM * s)), int(round(CARD_W_MM * s))
    noise = rng.normal(0, 1, (max(2, h // 10), max(2, w // 10))).astype(np.float32)
    art = cv2.resize(noise, (w, h), interpolation=cv2.INTER_CUBIC)
    img = rng.uniform(70, 180) + 45 * art
    if rng.random() < 0.8:  # framed card: border, name bar, art window, text box
        img[: int(10 * s), :] = 222
        for x in np.arange(5, rng.uniform(25, 45), 2.2):  # the name
            a, b = int(x * s), int((x + 1.5) * s)
            img[int(5 * s):int(8.5 * s), a:b] = rng.uniform(20, 70)
        img[int(52 * s):int(82 * s), :] = 212
        b = int(3 * s)
        level = rng.choice([200, 172, 150])  # yellow, silver, dark border (grey levels)
        img[:b, :], img[-b:, :], img[:, :b], img[:, -b:] = level, level, level, level
    return np.clip(img, 0, 255).astype(np.uint8)


def plain_front(cert: str) -> np.ndarray:
    """A plain card FRONT (one colour, nothing printed in the card window): the hardest face-up case for the learned
    check, because the window then shows only what the light does (a glare spot)."""
    level = 60 + _stable_seed("plain", cert) % 150
    return np.full((int(round(CARD_H_MM * CARD_PX_PER_MM)), int(round(CARD_W_MM * CARD_PX_PER_MM))), level, np.uint8)


def _paste_clip(canvas: np.ndarray, img: np.ndarray, x_mm: float, y_mm: float) -> None:
    """Copy ``img`` (at PX_PER_MM_RENDER) onto the canvas with its corner at (x_mm, y_mm), clipped to the canvas."""
    x, y = int(round(x_mm * PX_PER_MM_RENDER)), int(round(y_mm * PX_PER_MM_RENDER))
    h, w = img.shape[:2]
    a, b = max(0, x), min(canvas.shape[1], x + w)
    c, d = max(0, y), min(canvas.shape[0], y + h)
    if a < b and c < d:
        canvas[c:d, a:b] = img[c - y:d - y, a - x:b - x]


def _card_layer(card: np.ndarray, rows_mm: float) -> np.ndarray:
    """The top ``rows_mm`` of a card image, scaled from CARD_PX_PER_MM to PX_PER_MM_RENDER."""
    k = PX_PER_MM_RENDER / CARD_PX_PER_MM
    top = card[: max(1, int(np.ceil(rows_mm * CARD_PX_PER_MM)))]
    return cv2.resize(top, (int(round(top.shape[1] * k)), int(round(top.shape[0] * k))), interpolation=cv2.INTER_LINEAR)


def head_view(cert: str, side: str, deg: Degrade, era: str = "2017+", grader: str = "PSA", back: str = "pokemon_en",
              head: str = "cad", seed: int | None = None, front: str = "art") -> np.ndarray:
    """What the head camera sees of one slab from above: HEAD_VIEW_MM of it. ``side`` is the slab side facing up:
    'back' (face-down: the back label with what it carries for this grader and era, none on old PSA labels, and the
    card BACK in the card window) or 'front' (face-up: the front label and the card's own front). The slab lies up to
    +/-2 mm off centre and up to 1 deg off square in its pocket, the exposure differs by up to 12 %, and about a third of
    the slabs carry a glare spot on the card window. The head's own parts (``head``, see HEADS) are drawn in front of
    it. ``front``: "art" (card_front) or "plain" (plain_front)."""
    rng = np.random.default_rng(_stable_seed(cert, side, era, grader, back, head) if seed is None else seed)
    x0v, y0v, x1v, y1v = HEAD_VIEW_MM
    W, H = x1v - x0v, y1v - y0v
    dx, dy = rng.uniform(-2.0, 2.0, 2)
    canvas = np.full((int(round(H * PX_PER_MM_RENDER)), int(round(W * PX_PER_MM_RENDER))), 40, np.uint8)
    sx, sy = -SLAB_W_MM / 2 - x0v + dx, -SLAB_H_MM / 2 - y0v + dy  # slab corner on the canvas (mm)
    cv2.rectangle(canvas, (int(sx * PX_PER_MM_RENDER), int(sy * PX_PER_MM_RENDER)), (int((sx + SLAB_W_MM) * PX_PER_MM_RENDER), canvas.shape[0]), 70, -1)
    cx, cy = sx + (SLAB_W_MM - CARD_W_MM) / 2, sy + CARD_TOP_MM
    card = card_back(back) if side == "back" else (plain_front(cert) if front == "plain" else card_front(cert))
    _paste_clip(canvas, _card_layer(card, H - cy + 1), cx, cy)
    lx, ly = sx + (SLAB_W_MM - LABEL_W_MM) / 2, sy + LABEL_TOP_MM
    if not label_blank(grader, era, side):
        _paste_clip(canvas, render_label(cert, side, grader, era), lx, ly)
    spots = [(lx + deg.glare_pos[0] * LABEL_W_MM, ly + deg.glare_pos[1] * LABEL_H_MM, deg.glare)] if deg.glare > 0 else []
    if rng.random() < 0.35:
        spots.append((cx + rng.uniform(10, CARD_W_MM - 10), cy + rng.uniform(2, 16), rng.uniform(0.15, 0.35)))
    gain = rng.uniform(0.88, 1.12)
    import dataclasses

    d = dataclasses.replace(deg, rotate_deg=deg.rotate_deg + rng.uniform(-1.0, 1.0))
    occ = [(a - x0v, b - y0v, c - x0v, e - y0v, g) for a, b, c, e, g in head_shadow(head)]
    return _degrade(canvas.astype(np.float32) * gain, d, rng, spots, occ)


def empty_head_view(deg: Degrade, head: str = "cad") -> np.ndarray:
    """The head camera over an empty pocket: the dark pad far below, and the head's own parts."""
    x0v, y0v, x1v, y1v = HEAD_VIEW_MM
    px = 1.0 / deg.mm_per_px
    out = np.full((int(round((y1v - y0v) * px)), int(round((x1v - x0v) * px))), 30, np.uint8)
    occ = [(a - x0v, b - y0v, c - x0v, e - y0v, g) for a, b, c, e, g in head_shadow(head)]
    return _draw_occluders(out, occ, px)
