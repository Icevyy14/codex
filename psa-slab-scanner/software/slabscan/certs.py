"""Cert number parsing, grader detection and multi-read consensus.

PSA labels carry the cert number in up to four places:
  * front label 1D barcode - reportedly Interleaved 2 of 5 (ITF), all eras
  * front label printed digits
  * back-of-label 1D barcode (labels made since Dec 2015)
  * back-of-label QR code -> https://www.psacard.com/cert/<n> (labels made since June 2017)

ITF can only hold an even number of digits, and 2025+ certs have 9. PSA does not say
whether it pads with a leading zero or appends a check digit. ``ItfModel`` learns which
one from slabs where the QR and the ITF are both readable, and refuses to trust an
ITF-only read until it has. Every decoded payload goes through ``parse_payload``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

MIN_DIGITS = 6  # after stripping leading zeros
MAX_DIGITS = 10
RAW_MIN_DIGITS = 7  # a bare-digit payload shorter than this is treated as a short read

_URLS = [
    ("PSA", re.compile(r"psacard\.com/cert/(\d{%d,%d})" % (MIN_DIGITS, MAX_DIGITS + 1), re.I)),
    ("CGC", re.compile(r"cgccards\.com/\S*?(\d{7,12})", re.I)),
    ("BGS", re.compile(r"beckett\.com/\S*?(\d{7,12})", re.I)),
    ("SGC", re.compile(r"gosgc\.com/\S*?(\d{7,12})", re.I)),
    ("TAG", re.compile(r"taggrading\.com/\S*?([A-Z0-9]{6,16})", re.I)),
]
_KEYED_CERT_RE = re.compile(r"cert(?:ificate)?(?:\s*(?:no\.?|number|#))?\s*[/=#:]?\s*(\d{%d,%d})\b" % (MIN_DIGITS, MAX_DIGITS + 1), re.I)
_BARE_DIGITS_RE = re.compile(r"^\d{%d,%d}$" % (RAW_MIN_DIGITS, MAX_DIGITS + 1))

# Lower number = more trustworthy. A machine-readable symbol beats OCR.
SOURCE_RANK = {"back_qr": 0, "front_qr": 0, "front_barcode": 1, "back_barcode": 1, "barcode": 1, "ocr": 5}


def canonical(digits: str) -> str | None:
    """Strip leading zeros and range-check. Returns None if it can't be a cert."""
    c = digits.lstrip("0")
    if MIN_DIGITS <= len(c) <= MAX_DIGITS:
        return c
    return None


def itf_check_ok(digits: str) -> bool:
    """Standard ITF/UPC mod-10 check digit (weights 3,1,3,1... from the right, excluding the check)."""
    if len(digits) < 2 or not digits.isdigit():
        return False
    body, check = digits[:-1], int(digits[-1])
    s = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - s % 10) % 10 == check


@dataclass(frozen=True)
class Parsed:
    grader: str  # PSA | CGC | BGS | SGC | TAG | unknown
    cert: str  # canonical (zero-pad interpretation for ITF)
    alt_cert: str | None = None  # ITF only: the "last digit is a check digit" interpretation


def parse_payload(payload: str, symbology: str = "", custom_regex: str | None = None) -> Parsed | None:
    """Extract (grader, cert) from a decoded barcode/QR/OCR payload, or None.

    ``custom_regex`` (one capture group) overrides the built-in rules for PSA. It exists
    because PSA does not document its barcode payload. If calibration shows a prefix or
    suffix, set it in config.yaml.
    """
    if payload is None:
        return None
    text = payload.strip()
    if not text:
        return None
    if custom_regex:
        m = re.search(custom_regex, text)
        c = canonical(m.group(1)) if m else None
        return Parsed("PSA", c) if c else None
    for grader, rx in _URLS:
        m = rx.search(text)
        if m:
            if grader == "PSA":
                c = canonical(m.group(1))
                return Parsed("PSA", c) if c else None
            return Parsed(grader, m.group(1))
    m = _KEYED_CERT_RE.search(text)
    if m:
        c = canonical(m.group(1))
        return Parsed("unknown", c) if c else None
    compact = text.replace(" ", "").replace("-", "")
    if not _BARE_DIGITS_RE.match(compact):
        return None
    c = canonical(compact)
    if not c:
        return None
    if symbology == "ITF":
        alt = canonical(compact[:-1]) if itf_check_ok(compact) else None
        return Parsed("PSA", c, alt)  # PSA's front code is ITF; other graders use QR/Code128
    if symbology == "OCR":
        return Parsed("PSA", c)  # OCR runs only on the PSA label layout
    return Parsed("unknown", c)


def parse_cert(payload: str, custom_regex: str | None = None, symbology: str = "") -> str | None:
    """Convenience: the canonical cert only."""
    p = parse_payload(payload, symbology, custom_regex)
    return p.cert if p else None


@dataclass(frozen=True)
class CodeRead:
    """One decoded symbol (or OCR hit) from one image."""

    cert: str
    source: str  # back_qr | front_barcode | back_barcode | barcode | front_qr | ocr
    symbology: str
    raw: str
    camera: str = ""
    grader: str = "PSA"
    alt_cert: str | None = None


@dataclass(frozen=True)
class Verdict:
    status: str  # ok | needs_review | no_read | conflict | other_grader
    cert: str | None
    sources: tuple[str, ...]
    note: str = ""
    grader: str = "PSA"
    raw: str = ""


@dataclass
class ItfModel:
    """Learns how PSA maps an odd-length cert into an even-length ITF payload."""

    evidence: Counter = field(default_factory=Counter)
    min_evidence: int = 3

    def observe(self, reference_cert: str, itf_reads: list[CodeRead]) -> None:
        if len(reference_cert) % 2 == 0:
            return  # even-length certs fit ITF unpadded: no information
        for r in itf_reads:
            if r.cert == reference_cert:
                self.evidence["zero_pad"] += 1
            elif r.alt_cert == reference_cert:
                self.evidence["check_digit"] += 1

    @property
    def mode(self) -> str | None:
        zp, cd = self.evidence["zero_pad"], self.evidence["check_digit"]
        if zp >= self.min_evidence and cd == 0:
            return "zero_pad"
        if cd >= self.min_evidence and zp == 0:
            return "check_digit"
        return None

    def resolve(self, r: CodeRead) -> str | None:
        """Cert for an ITF read, or None while the interpretation is still ambiguous."""
        if r.alt_cert is None:  # last digit is not a valid check digit -> it is part of the cert
            return r.cert if self.mode != "check_digit" else None
        m = self.mode
        if m == "zero_pad":
            return r.cert
        if m == "check_digit":
            return r.alt_cert
        return None


ACCEPTED_GRADERS = ("PSA", "CGC")  # read and stacked normally; others go to the exception pocket


def consensus(reads: list[CodeRead], itf: ItfModel | None = None, min_itf_reads: int = 2, accepted: tuple[str, ...] = ACCEPTED_GRADERS) -> Verdict:
    """Combine all reads of one slab into a single verdict.

    * no reads                                   -> no_read
    * a CGC QR (or another accepted grader)      -> ok, grader recorded
    * any read says a non-accepted grader        -> other_grader (goes to the exception pocket)
    * machine reads disagree                     -> conflict (never guess between two codes)
    * QR present: QR wins; ITF reads must match one of their two interpretations
    * ITF only: needs the learned ITF mode (or OCR agreement) and >= min_itf_reads reads
    * only OCR                                   -> needs_review
    """
    itf = itf if itf is not None else ItfModel()
    if not reads:
        return Verdict("no_read", None, (), "nothing decoded")
    others = [r for r in reads if r.grader not in ("PSA", "unknown")]
    if others:
        graders = {r.grader for r in others}
        certs = {r.cert for r in others}
        r = others[0]
        if len(graders) > 1 or len(certs) > 1:
            return Verdict("conflict", None, (r.source,), f"codes disagree: {sorted(graders)} {sorted(certs)}", grader=r.grader, raw=r.raw)
        if r.grader in accepted:
            return Verdict("ok", r.cert, tuple(sorted({o.source for o in others})), "", grader=r.grader, raw=r.raw)
        return Verdict("other_grader", r.cert, (r.source,), f"{r.grader} slab", grader=r.grader, raw=r.raw)
    machine = [r for r in reads if r.source != "ocr"]
    ocr = [r for r in reads if r.source == "ocr"]
    ocr_certs = {r.cert for r in ocr}

    def srt(rs):
        return tuple(sorted({r.source for r in rs}, key=lambda s: SOURCE_RANK.get(s, 9)))

    if not machine:
        cert = Counter(r.cert for r in ocr).most_common(1)[0][0]
        note = "ocr only - verify by eye" + (" (inconsistent)" if len(ocr_certs) > 1 else "")
        return Verdict("needs_review", cert, ("ocr",), note, raw=ocr[0].raw)

    qr = [r for r in machine if r.symbology != "ITF"]
    itf_reads = [r for r in machine if r.symbology == "ITF"]
    if qr:
        qr_certs = Counter(r.cert for r in qr)
        if len(qr_certs) > 1:
            return Verdict("conflict", None, srt(qr), "codes disagree: " + ", ".join(qr_certs))
        cert = next(iter(qr_certs))
        bad = [r for r in itf_reads if cert not in (r.cert, r.alt_cert)]
        if bad:
            return Verdict("conflict", None, srt(machine), f"QR {cert} vs ITF {bad[0].raw}")
        itf.observe(cert, itf_reads)
        unconfirmed = all(r.grader == "unknown" for r in qr) and not itf_reads
        if unconfirmed:
            return Verdict("needs_review", cert, srt(machine), "grader not confirmed (no PSA QR/ITF)", grader="unknown", raw=qr[0].raw)
        return Verdict("ok", cert, srt(machine), "", raw=qr[0].raw)

    # ITF only (pre-2017 labels, or the QR was unreadable)
    resolved = {itf.resolve(r) for r in itf_reads}
    raw = itf_reads[0].raw
    if None in resolved:
        cands = {c for r in itf_reads for c in (r.cert, r.alt_cert) if c}
        hit = cands & ocr_certs
        if len(hit) == 1:
            return Verdict("ok", hit.pop(), srt(machine) + ("ocr",), "ITF interpretation confirmed by OCR", raw=raw)
        return Verdict("needs_review", itf_reads[0].cert, srt(machine), "ITF only; padding vs check digit not learned yet: " + "/".join(sorted(cands)), raw=raw)
    if len(resolved) > 1:
        return Verdict("conflict", None, srt(machine), "ITF reads disagree")
    cert = resolved.pop()
    if len(itf_reads) < min_itf_reads and cert not in ocr_certs:
        return Verdict("needs_review", cert, srt(machine), "single ITF read - confirm", raw=raw)
    note = "ocr disagreed (ignored)" if ocr and cert not in ocr_certs else ""
    return Verdict("ok", cert, srt(machine), note, raw=raw)
