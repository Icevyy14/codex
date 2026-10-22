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

from .certs import CodeRead, parse_cert

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
        cert = parse_cert(b.text, custom_regex)
        if cert:
            reads.append(CodeRead(cert=cert, source=_source_for(sym, camera), symbology=sym, raw=b.text, camera=camera))
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
        lambda g: g,
        lambda g: _clahe.apply(g),
        lambda g: cv2.resize(g, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC),
    )
    for prep in passes:
        reads, unparsed = _zxing_pass(prep(gray), camera, custom_regex)
        all_unparsed.extend(u for u in unparsed if u not in all_unparsed)
        if reads:
            return reads, all_unparsed
    if allow_ocr:
        return ocr_digits(gray, camera), all_unparsed
    return [], all_unparsed


_OCR_TOKEN_RE = re.compile(r"\d{8,10}")


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
    import pytesseract

    _, bw = cv2.threshold(_clahe.apply(gray), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(bw, config="--psm 11 -c tessedit_char_whitelist=0123456789")
    tokens = sorted(set(_OCR_TOKEN_RE.findall(text)), key=len, reverse=True)
    return [CodeRead(cert=t, source="ocr", symbology="OCR", raw=t, camera=camera) for t in tokens[:1]]
