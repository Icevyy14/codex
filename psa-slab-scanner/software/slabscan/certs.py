"""PSA cert number parsing, validation and multi-read consensus.

PSA labels carry the cert number in up to four places:
  * front label 1D barcode (all eras)
  * front label printed digits
  * back-of-label 1D barcode (labels made since Dec 2015)
  * back-of-label QR code linking to cert verification (labels made since June 2017)

Every decoded payload goes through ``parse_cert``. Several reads of the same slab
are reconciled by ``consensus``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# PSA went from 8 to 9 digits around late 2024. Forum reports say the front barcode is
# Interleaved 2 of 5 (ITF), which only holds an even digit count, so a 9-digit cert is
# printed as "0" + cert. Certs are therefore canonicalised by stripping leading zeros
# (the QR URL and the ITF payload then compare equal). The raw payload is always kept.
MIN_DIGITS = 6  # after stripping leading zeros
MAX_DIGITS = 10
RAW_MIN_DIGITS = 7  # a bare-digit payload shorter than this is treated as a short read

_URL_CERT_RE = re.compile(r"psacard\.com/cert/(\d{%d,%d})" % (MIN_DIGITS, MAX_DIGITS + 1), re.I)
_KEYED_CERT_RE = re.compile(r"cert(?:ificate)?(?:\s*(?:no\.?|number|#))?\s*[/=#:]?\s*(\d{%d,%d})\b" % (MIN_DIGITS, MAX_DIGITS + 1), re.I)
_BARE_DIGITS_RE = re.compile(r"^\d{%d,%d}$" % (RAW_MIN_DIGITS, MAX_DIGITS + 1))

# Lower number = more trustworthy. A machine-readable symbol beats OCR.
SOURCE_RANK = {
    "back_qr": 0,
    "front_qr": 0,
    "front_barcode": 1,
    "back_barcode": 1,
    "barcode": 1,
    "ocr": 5,
}


def canonical(digits: str) -> str | None:
    """Strip leading zeros and range-check. Returns None if it can't be a cert."""
    c = digits.lstrip("0")
    if MIN_DIGITS <= len(c) <= MAX_DIGITS:
        return c
    return None


def parse_cert(payload: str, custom_regex: str | None = None) -> str | None:
    """Extract a canonical PSA cert number from a decoded barcode/QR/OCR payload.

    ``custom_regex`` (one capture group) overrides the built-in rules. It exists
    because PSA does not document the barcode payload. If calibration shows the
    payload has a prefix or suffix, set it in config.yaml.
    """
    if payload is None:
        return None
    text = payload.strip()
    if not text:
        return None
    if custom_regex:
        m = re.search(custom_regex, text)
        return canonical(m.group(1)) if m else None
    m = _URL_CERT_RE.search(text)
    if m:
        return canonical(m.group(1))
    m = _KEYED_CERT_RE.search(text)
    if m:
        return canonical(m.group(1))
    compact = text.replace(" ", "").replace("-", "")
    if _BARE_DIGITS_RE.match(compact):
        return canonical(compact)
    return None


@dataclass(frozen=True)
class CodeRead:
    """One decoded symbol (or OCR hit) from one image."""

    cert: str
    source: str  # back_qr | front_barcode | back_barcode | barcode | ocr
    symbology: str
    raw: str
    camera: str = ""


@dataclass(frozen=True)
class Verdict:
    status: str  # ok | needs_review | no_read | conflict
    cert: str | None
    sources: tuple[str, ...]
    note: str = ""


def consensus(reads: list[CodeRead], min_itf_reads: int = 2) -> Verdict:
    """Combine all reads of one slab into a single verdict.

    * no reads                         -> no_read
    * machine reads disagree           -> conflict (never guess between two codes)
    * only OCR                         -> needs_review
    * only ITF, fewer than min_itf_reads agreeing reads -> needs_review
      (ITF has no mandatory check digit and is prone to "short reads")
    * machine reads agree              -> ok (OCR disagreement is noted, not fatal)
    """
    if not reads:
        return Verdict("no_read", None, (), "nothing decoded")
    machine = [r for r in reads if r.source != "ocr"]
    ocr = [r for r in reads if r.source == "ocr"]
    if machine:
        certs = Counter(r.cert for r in machine)
        if len(certs) > 1:
            listing = ", ".join(f"{c} x{n}" for c, n in certs.most_common())
            return Verdict("conflict", None, tuple(sorted({r.source for r in machine})), f"codes disagree: {listing}")
        cert = next(iter(certs))
        sources = tuple(sorted({r.source for r in machine}, key=lambda s: SOURCE_RANK.get(s, 9)))
        only_itf = all(r.symbology == "ITF" for r in machine)
        if only_itf and len(machine) < min_itf_reads and not any(r.cert == cert for r in ocr):
            return Verdict("needs_review", cert, sources, "single ITF read - confirm")
        note = ""
        if ocr and any(r.cert != cert for r in ocr):
            note = "ocr disagreed (ignored)"
        return Verdict("ok", cert, sources, note)
    certs = Counter(r.cert for r in ocr)
    cert, _ = certs.most_common(1)[0]
    note = "ocr only - verify by eye or PSA lookup"
    if len(certs) > 1:
        note = "ocr only and inconsistent - verify by eye"
    return Verdict("needs_review", cert, ("ocr",), note)
