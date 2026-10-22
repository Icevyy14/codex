"""Decode PSA cert numbers from camera frames.

Strategy (cheapest first, stop as soon as something parses):
  1. zxing-cpp over the full frame, all symbologies (QR + every 1D type).
     PSA does not publish its barcode symbology, so nothing is assumed.
  2. Same, after CLAHE contrast equalisation (rescues glare / washed-out labels).
  3. Same, on a 2x upscale (rescues barely-resolved 1D bars).
  4. Optional Tesseract OCR of the printed digits. The result is flagged needs_review.
"""

from __future__ import annotations

import re
import shutil

import cv2
import numpy as np
import zxingcpp

from .certs import CodeRead, parse_payload

_QR_FORMATS = {"QRCode", "MicroQRCode", "RMQRCode", "DataMatrix", "Aztec"}


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _source_for(symbology: str, camera: str) -> str:
    is_2d = symbology in _QR_FORMATS
    if camera == "back":
        return "back_qr" if is_2d else "back_barcode"
    if camera == "front":
        # Front labels have no QR today. Keep a 2D read anyway and tag it honestly.
        return "front_qr" if is_2d else "front_barcode"
    return "back_qr" if is_2d else "barcode"


def _zxing_pass(gray: np.ndarray, camera: str, custom_regex: str | None) -> tuple[list[CodeRead], list[str]]:
    reads: list[CodeRead] = []
    unparsed: list[str] = []
    for b in zxingcpp.read_barcodes(gray):
        sym = b.format.name if hasattr(b.format, "name") else str(b.format)
        p = parse_payload(b.text, sym, custom_regex)
        if p:
            reads.append(CodeRead(cert=p.cert, source=_source_for(sym, camera), symbology=sym, raw=b.text, camera=camera, grader=p.grader, alt_cert=p.alt_cert))
        else:
            unparsed.append(f"{sym}:{b.text}")
    return reads, unparsed


_clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))


def decode_frame(img: np.ndarray, camera: str = "", custom_regex: str | None = None, allow_ocr: bool = True) -> tuple[list[CodeRead], list[str]]:
    """Return (cert reads, unparsed payloads) for one frame.

    ``unparsed`` holds decoded symbols that did not look like a cert. They are logged
    so that calibration can reveal PSA's real payload format.
    """
    gray = _to_gray(img)
    all_unparsed: list[str] = []
    passes = (
        lambda g: [g],
        lambda g: [_clahe.apply(g)],
        lambda g: [cv2.resize(g, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)],
        _padded_tiles,
    )
    for prep in passes:
        reads: list[CodeRead] = []
        for img in prep(gray):
            r, unparsed = _zxing_pass(img, camera, custom_regex)
            reads.extend(r)
            all_unparsed.extend(u for u in unparsed if u not in all_unparsed)
        if reads:
            return reads, all_unparsed
    if allow_ocr:
        return ocr_digits(gray, camera), all_unparsed
    return [], all_unparsed


def _padded_tiles(gray: np.ndarray) -> list[np.ndarray]:
    """Overlapping horizontal bands, upscaled and given a white quiet zone.

    A thin ITF code sits among label text with almost no quiet zone. Full-frame decoding of
    real PSA labels has been reported to fail where padded crops succeed.
    """
    h, w = gray.shape
    out = []
    band = max(24, h // 4)
    for y0 in range(0, max(1, h - band // 2), band // 2):
        crop = gray[y0:y0 + band, :]
        crop = cv2.resize(_clahe.apply(crop), None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        out.append(cv2.copyMakeBorder(crop, 40, 40, 60, 60, cv2.BORDER_CONSTANT, value=255))
    return out


_OCR_TOKEN_RE = re.compile(r"\d{8,10}")
OCR_MIN_STD = 8.0  # grey-level spread below this = nothing printed in view (blank label back, empty frame)
OCR_TIMEOUT_S = 30.0  # tesseract on a noisy frame can run for minutes; a real label takes ~4 s on a PC, more on a Pi


def ocr_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return True


def ocr_digits(gray: np.ndarray, camera: str = "") -> list[CodeRead]:
    """Last-resort OCR: the longest 8-10 digit run on the label is the cert.

    Years ("2023"), card numbers ("#025") and grades are all shorter, so length is
    a good filter. OCR is never trusted on its own: these reads become needs_review.
    """
    if not ocr_available():
        return []
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
    tokens = sorted(set(_OCR_TOKEN_RE.findall(text)), key=len, reverse=True)
    out = []
    for t in tokens[:1]:
        p = parse_payload(t, "OCR")
        if p:
            out.append(CodeRead(cert=p.cert, source="ocr", symbology="OCR", raw=t, camera=camera))
    return out
