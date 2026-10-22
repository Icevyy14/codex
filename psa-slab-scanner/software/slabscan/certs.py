"""Cert number parsing, grader and label-side detection, and multi-read consensus.

Every rule below is anchored to a payload decoded from a real label (64 real PSA/CGC/BGS/SGC slabs, Oct 2026; the
payload strings are in tests/test_real_payloads.py). What each label carries:

  PSA current labels (all 9-digit certs, some 8)  back: QR https://www.psacard.com/cert/<n>/ + Code128 <n>   front: Code128 <n>
  PSA 2017+ "lighthouse" labels (8-digit certs)   back: QR http://psacard.com/cert/<n> (or the https form) + ITF   front: ITF
  PSA 2016 labels                                  back: ITF only   front: ITF
  PSA labels before 2016                           back: no code    front: ITF
  CGC 2023+ (10-digit certs, a few 140 + 10)       back: QR https://www.cgccards.com/certlookup/<n>/<grade>/   front: Code128 <n>
  CGC 2020-23 "OG" labels                          back: QR https://www.cgccomics.com/certlookup/<n>/<grade> + Code128 of 26-28
                                                   digits ending in <n>   front: no code
  CGC Certified Authentic                          front: QR .../certlookup/<n>/0_0/ + Code128 <n>   back: no code
  BGS, SGC                                         no machine-readable code: the printed cert only

The PSA ITF payload is always 8 digits, the cert zero-padded (7- and 8-digit certs; 9-digit certs never use ITF), so
there is nothing to learn about it, and an ITF read of any other length is a misread (glare cuts ITF short: a real
'289412' was read from 28941258). Payloads are typed by symbology AND length; a CGC cert keeps all its digits (13-digit
CGC certs exist). ITF and Code128 reads are 1D: one printed symbol can be misread, so a 1D-only 'ok' needs two printed
symbols (back + front label) or OCR of the printed digits to agree. A QR carries its own error correction. OCR finds a
digit run, not a grader: an OCR-only number is never 'ok' and goes to the exception pocket.
Every decoded payload goes through ``parse_payload``.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

MIN_DIGITS = 6  # after stripping leading zeros
MAX_DIGITS = 10  # PSA (and generic) certs; a CGC cert may be 13 digits (140 + 10)
RAW_MIN_DIGITS = 7  # a bare-digit payload shorter than this is treated as a short read

TWO_D = {"QRCode", "MicroQRCode", "RMQRCode", "DataMatrix", "Aztec"}

# PSA back-label QR. The right boundary matters: without it a longer number would be cut, not rejected.
_PSA_URL = re.compile(r"(?:^|[/.])psacard\.com/cert/(\d{6,9})(?=[/?#\s]|$)", re.I)
# CGC QR, both domains (cgccomics.com on the 2020-23 OG labels), any case, grade path optional, slash optional.
# Grade 0_0 = Certified Authentic, printed on the FRONT label; any other grade = the back label of a graded slab.
_CGC_URL = re.compile(r"(?:^|[/.])cgc(?:cards|comics)\.com/certlookup/(140\d{10}|\d{10})(?:/(\d{1,2}_\d))?/?(?=[?#\s]|$)", re.I)
# A CGC QR with no cert in it (press images and mock-ups of back labels): a CGC label, but no number.
_CGC_LABEL_URL = re.compile(r"^(?:https?://)?(?:www\.)?cgc(?:cards|comics)\.com(?:/certlookup|/verify)?/?$", re.I)
_OTHER_URLS = [  # other graders' cert URLs: their slabs go to the exception pocket
    ("BGS", re.compile(r"beckett\.com/\S*?(\d{7,12})", re.I)),
    ("SGC", re.compile(r"gosgc\.com/\S*?(\d{7,12})", re.I)),
    ("TAG", re.compile(r"taggrading\.com/\S*?([A-Z0-9]{6,16})", re.I)),
]
_KEYED_CERT_RE = re.compile(r"cert(?:ificate)?(?:\s*(?:no\.?|number|#))?\s*[/=#:]?\s*(\d{%d,%d})\b" % (MIN_DIGITS, MAX_DIGITS + 1), re.I)
_PSA_ITF_RE = re.compile(r"^\d{8}$")  # the cert zero-padded to 8 digits; anything else is a misread
_CGC_OG_C128_RE = re.compile(r"^\d{16,18}(\d{10})$")  # CGC 2020-23 back: 26-28 digits, the cert is the last 10
_CGC_C128_RE = re.compile(r"^(?:140\d{10}|\d{10})$")  # CGC 2023+ and Authentic front: the cert itself
_PSA_C128_RE = re.compile(r"^\d{7,9}$")  # PSA current labels, front and back: the cert itself
_BARE_DIGITS_RE = re.compile(r"^\d{%d,%d}$" % (RAW_MIN_DIGITS, MAX_DIGITS))
OCR_TOKEN_RE = re.compile(r"(?<!\d)(?:140\d{10}|\d{8,10})(?!\d)")  # PSA 8-9 digits, CGC 10 or 140 + 10

# Lower number = more trustworthy. A machine-readable symbol beats OCR.
SOURCE_RANK = {"back_qr": 0, "front_qr": 0, "front_barcode": 1, "back_barcode": 1, "barcode": 1, "ocr": 5}

# What a code seen on a label proves about the label side it is printed on (kind -> side, certain, words). Only
# certain=True rows may prove a slab face-down or face-up: they held on every real label of that kind (EVAL_REPORT
# section 6). PSA ITF and Code128 are printed on both sides, so they prove nothing. A CGC QR without a cert was seen
# only on back-label press images and mock-ups: a hint, never a proof. Grade 0_0 was seen on both Authentic fronts, and
# on one official render of a back label: a wrong face-UP call only stops the run, which is safe.
SIDE_PROOFS = {
    "psa_qr": ("back", True, "a PSA back-label QR"),
    "cgc_qr": ("back", True, "a CGC back-label QR"),
    "cgc_og_c128": ("back", True, "a CGC 2020-23 back-label barcode"),
    "cgc_auth_qr": ("front", True, "a CGC Authentic front-label QR (grade 0_0)"),
    "cgc_c128": ("front", True, "a CGC front-label barcode"),
    "cgc_label_qr": ("back", False, "a CGC QR without a cert number (seen only on back labels, but not proof)"),
}


def _strip(digits: str, max_len: int = MAX_DIGITS) -> str | None:
    c = digits.lstrip("0")
    return c if MIN_DIGITS <= len(c) <= max_len else None


def canonical(digits: str) -> str | None:
    """Strip leading zeros and range-check. Returns None if it can't be a cert. A 13-digit CGC cert (140 + 10) counts."""
    c = digits.lstrip("0")
    if len(c) == 13 and c.startswith("140"):
        return c
    return _strip(digits)


@dataclass(frozen=True)
class Parsed:
    grader: str  # PSA | CGC | BGS | SGC | TAG | unknown
    cert: str  # leading zeros stripped
    side: str | None = None  # the label side the symbol is printed on, when its format proves it: back | front
    kind: str = ""  # the rule that matched (SIDE_PROOFS keys, psa_itf, psa_c128, ocr, ...)


def parse_payload(payload: str, symbology: str = "", custom_regex: str | None = None) -> Parsed | None:
    """Extract (grader, cert) from a decoded barcode/QR/OCR payload, or None.

    URLs are typed by their domain; bare digits by symbology and length (section above). ``custom_regex`` (one capture
    group) replaces the built-in PSA rules for machine-read symbols, as an escape hatch if Phase 0 shows a PSA payload
    these rules do not know. The CGC and other graders' rules still run first (a CGC code the regex happens to match is
    never taken for PSA), and OCR digit runs are not passed through it.
    """
    if payload is None:
        return None
    text = payload.strip()
    if not text:
        return None
    two_d = symbology in TWO_D
    m = _CGC_URL.search(text)
    if m:
        cert = _strip(m.group(1), 13)
        if not cert:
            return None
        grade = m.group(2)
        if not two_d:
            return Parsed("CGC", cert, None, "cgc_url")
        if grade is None:
            return Parsed("CGC", cert, None, "cgc_qr_nograde")
        return Parsed("CGC", cert, "front", "cgc_auth_qr") if grade == "0_0" else Parsed("CGC", cert, "back", "cgc_qr")
    for grader, rx in _OTHER_URLS:
        m = rx.search(text)
        if m:
            return Parsed(grader, m.group(1), None, grader.lower() + "_url")
    compact = text.replace(" ", "").replace("-", "")
    if symbology == "Code128" and compact.isdigit():
        m = _CGC_OG_C128_RE.match(compact)
        if m:
            c = _strip(m.group(1))
            return Parsed("CGC", c, "back", "cgc_og_c128") if c else None
        if _CGC_C128_RE.match(compact):
            c = _strip(compact, 13)
            return Parsed("CGC", c, "front", "cgc_c128") if c else None
    if symbology == "OCR":
        if not OCR_TOKEN_RE.fullmatch(compact):
            return None
        c = _strip(compact, 13)
        return Parsed("unknown", c, None, "ocr") if c else None  # a digit run says nothing about the grader
    if custom_regex:
        m = re.search(custom_regex, text)
        if not m:
            return None
        c = _strip(re.sub(r"\D", "", m.group(1)))
        return Parsed("PSA", c, None, "custom") if c else None
    m = _PSA_URL.search(text)
    if m:
        c = _strip(m.group(1))
        if not c:
            return None
        return Parsed("PSA", c, "back", "psa_qr") if two_d else Parsed("PSA", c, None, "psa_url")
    m = _KEYED_CERT_RE.search(text)
    if m:
        c = _strip(m.group(1))
        return Parsed("unknown", c, None, "keyed") if c else None
    if symbology == "ITF":
        if not _PSA_ITF_RE.match(compact):
            return None  # every real PSA ITF is exactly 8 digits: a shorter or longer one is a misread
        c = _strip(compact)
        return Parsed("PSA", c, None, "psa_itf") if c else None
    if symbology == "Code128":
        if not _PSA_C128_RE.match(compact):
            return None
        c = _strip(compact)
        return Parsed("PSA", c, None, "psa_c128") if c else None
    if not _BARE_DIGITS_RE.match(compact):
        return None
    c = _strip(compact)
    return Parsed("unknown", c, None, "digits") if c else None  # bare digits in a symbology no grader uses


def parse_cert(payload: str, custom_regex: str | None = None, symbology: str = "") -> str | None:
    """Convenience: the canonical cert only."""
    p = parse_payload(payload, symbology, custom_regex)
    return p.cert if p else None


@dataclass(frozen=True)
class SideEvidence:
    """What one payload seen by a camera says about the label side facing it (SIDE_PROOFS)."""

    side: str  # back | front
    certain: bool
    kind: str
    what: str
    cert: str | None
    raw: str


def label_side(symbology: str, raw: str) -> SideEvidence | None:
    """The label side a payload is printed on, if its format says so (SIDE_PROOFS), else None."""
    text = (raw or "").strip()
    if symbology in TWO_D and _CGC_LABEL_URL.match(text):
        side, certain, what = SIDE_PROOFS["cgc_label_qr"]
        return SideEvidence(side, certain, "cgc_label_qr", what, None, text)
    p = parse_payload(text, symbology)
    if p is None or p.kind not in SIDE_PROOFS:
        return None
    side, certain, what = SIDE_PROOFS[p.kind]
    return SideEvidence(side, certain, p.kind, what, p.cert, text)


def side_evidence(reads: list, unparsed: list[str] | tuple = ()) -> list[SideEvidence]:
    """SideEvidence of every machine read and every unparsed payload ("Symbology:text", as decode_frame lists them),
    one per distinct payload."""
    pairs = [(r.symbology, r.raw) for r in reads if r.source != "ocr"]
    pairs += [tuple(u.split(":", 1)) for u in unparsed if ":" in u]
    out, seen = [], set()
    for sym, raw in pairs:
        if (sym, raw) in seen:
            continue
        seen.add((sym, raw))
        e = label_side(sym, raw)
        if e is not None:
            out.append(e)
    return out


def _words(ev: list[SideEvidence]) -> str:
    parts = []
    for e in ev:
        w = e.what + (f" ({e.cert})" if e.cert else "")
        if w not in parts:
            parts.append(w)
    return " and ".join(parts)


def face_from_above(reads: list, unparsed: list[str] | tuple = ()) -> tuple[str, str, list[SideEvidence]]:
    """What the codes the head camera sees from above prove about the slab under it, using only the certain rows of
    SIDE_PROOFS: ('down' | 'up' | 'neighbour' | 'unknown', why, the certain back proofs).

    * down: a back-label code, and no front-label code
    * up: a front-label code, and no back-label code
    * neighbour: back and front codes together, two different back labels, or two different certs among all the codes
      (a back QR of one cert beside an ITF of another): another slab's label is in view
    * unknown: no proof either way (PSA ITF/Code128 sit on both sides; older PSA labels, CGC Authentic backs, BGS and
      SGC carry no back code)
    """
    ev = side_evidence(reads, unparsed)
    backs = [e for e in ev if e.certain and e.side == "back"]
    fronts = [e for e in ev if e.certain and e.side == "front"]
    hints = [e for e in ev if not e.certain]
    if backs and fronts:
        return "neighbour", f"{_words(backs)} and {_words(fronts)} are both in view: another slab's label is in view", backs
    certs = sorted({e.cert for e in backs if e.cert})
    if len(certs) > 1:
        return "neighbour", f"two different back labels are in view ({', '.join(certs)}): another slab's label is in view", backs
    # One label carries one cert on every code (0 wrong-cert reads in 448 degraded real-label frames): two certs = two labels
    every = sorted({r.cert for r in reads if r.source != "ocr" and r.cert})
    if len(every) > 1:
        return "neighbour", f"codes of two different certs are in view ({', '.join(every)}): another slab's label is in view", backs
    if backs:
        return "down", _words(backs), backs
    if fronts:
        return "up", f"{_words(fronts)} is visible from above, and that code is printed on the FRONT label", backs
    why = "no back-label code was seen from above (a PSA QR, a CGC QR or the CGC 2020-23 back barcode)"
    if hints:
        why += f"; {_words(hints)}"
    return "unknown", why, backs


@dataclass(frozen=True)
class CodeRead:
    """One decoded symbol (or OCR hit) from one image."""

    cert: str
    source: str  # the printed symbol: back_qr | back_barcode | front_qr | front_barcode | barcode | ocr
    symbology: str
    raw: str
    camera: str = ""  # back = head camera, front = station camera
    grader: str = "PSA"
    frame: str = ""  # which frame it came from (the runner numbers them); "" = not known
    box: tuple | None = None  # (x0, y0, x1, y1) in the pixels of the image given to decode_frame


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
    """The PSA ITF payload format. It is fixed - the cert zero-padded to 8 digits, on every real label - so there is
    nothing left to learn. Kept for its callers: ``evidence`` counts slabs whose QR and ITF agreed (a check on the
    format, journaled per slab), and ``mode`` is always "zero_pad"."""

    evidence: Counter = field(default_factory=Counter)

    def observe(self, reference_cert: str, itf_reads: list[CodeRead]) -> None:
        if any(r.cert == reference_cert for r in itf_reads):
            self.evidence["zero_pad"] += 1

    @property
    def mode(self) -> str:
        return "zero_pad"

    def resolve(self, r: CodeRead) -> str:
        return r.cert


ACCEPTED_GRADERS = ("PSA", "CGC")  # read and stacked normally; others go to the exception pocket


def drop_phantoms(reads: list[CodeRead]) -> tuple[list[CodeRead], list[str]]:
    """Two different numbers from ONE frame and ONE 1D symbology: zxing-cpp can return a thin band inside a real
    barcode as a second, wrong read (real: Code128 '09435764' inside '27435764'). decode.py drops those by position;
    this is the second guard. When exactly one of the numbers is confirmed by a read from another frame or another
    symbology, the others are dropped. Otherwise nothing is dropped, and consensus() says conflict."""
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in reads:
        if r.source != "ocr" and r.symbology not in TWO_D and r.frame:
            groups[(r.frame, r.symbology)].add(r.cert)
    drop: set[tuple[str, str, str]] = set()
    for key, certs in groups.items():
        if len(certs) < 2:
            continue
        others = {r.cert for r in reads if r.source != "ocr" and (r.frame, r.symbology) != key}
        keep = certs & others
        if len(keep) == 1:
            drop |= {(key[0], key[1], c) for c in certs - keep}
    if not drop:
        return reads, []
    kept = [r for r in reads if (r.frame, r.symbology, r.cert) not in drop]
    return kept, sorted({f"{s}:{r.raw}" for r in reads for f, s, c in drop if (r.frame, r.symbology, r.cert) == (f, s, c)})


def consensus(reads: list[CodeRead], itf: ItfModel | None = None, min_sources: int = 2, accepted: tuple[str, ...] = ACCEPTED_GRADERS) -> Verdict:
    """Combine all reads of one slab into a single verdict.

    * no reads                                         -> no_read
    * a phantom 1D read is dropped first (drop_phantoms)
    * machine reads name two certs or two graders      -> conflict (never guess between two codes)
    * a non-accepted grader's code (BGS/SGC/TAG URL)   -> other_grader (exception pocket)
    * a QR (2D) names the cert                         -> ok: a QR carries its own error correction
    * 1D only (ITF, Code128; any grader)               -> ok only with >= min_sources DIFFERENT printed symbols (back +
      front label barcode) or OCR of the printed digits agreeing. Repeated reads of one symbol (two frames from one
      pose, overlapping tiles) are not independent and count once. OCR that disagrees -> needs_review.
    * a code with no grader evidence (bare digits)     -> needs_review, grader unknown
    * only OCR                                          -> needs_review, grader unknown (the runner sends it to the
      exception pocket: OCR finds a digit run, not a grader, and it reads card numbers too)
    """
    itf = itf if itf is not None else ItfModel()
    if not reads:
        return Verdict("no_read", None, (), "nothing decoded", grader="unknown")
    reads, phantoms = drop_phantoms(reads)
    pnote = f"dropped a phantom read {', '.join(phantoms)}" if phantoms else ""

    def srt(rs):
        return tuple(sorted({r.source for r in rs}, key=lambda s: (SOURCE_RANK.get(s, 9), s)))

    def note(*parts):
        return "; ".join(p for p in (pnote,) + parts if p)

    machine = [r for r in reads if r.source != "ocr"]
    ocr = [r for r in reads if r.source == "ocr"]
    ocr_certs = {r.cert for r in ocr}
    if not machine:
        cert = Counter(r.cert for r in ocr).most_common(1)[0][0]
        return Verdict("needs_review", cert, ("ocr",), note("OCR only (no barcode or QR read), grader unknown - check by hand"
                       + (" (OCR inconsistent)" if len(ocr_certs) > 1 else "")), grader="unknown", raw=ocr[0].raw)
    certs = Counter(r.cert for r in machine)
    graders = sorted({r.grader for r in machine if r.grader != "unknown"})
    if len(certs) > 1:
        desc = ", ".join(f"{r.grader} {r.symbology} {r.raw}" for r in {(r.grader, r.symbology, r.raw): r for r in machine}.values())
        return Verdict("conflict", None, srt(machine), note(f"codes disagree: {desc}"), grader="/".join(graders) or "unknown", raw=machine[0].raw)
    if len(graders) > 1:
        return Verdict("conflict", None, srt(machine), note(f"one number, two graders: {graders}"), grader="/".join(graders), raw=machine[0].raw)
    cert = next(iter(certs))
    grader = graders[0] if graders else "unknown"
    two_d = [r for r in machine if r.symbology in TWO_D]
    raw = (two_d or machine)[0].raw
    if grader not in accepted and grader != "unknown":
        return Verdict("other_grader", cert, srt(machine), note(f"{grader} slab"), grader=grader, raw=raw)
    if two_d:
        itf.observe(cert, [r for r in machine if r.symbology == "ITF"])
        if grader == "unknown":
            return Verdict("needs_review", cert, srt(machine), note("grader not confirmed (a code with no grader's format)"), grader="unknown", raw=raw)
        return Verdict("ok", cert, srt(machine), note(), grader=grader, raw=raw)
    # 1D only: ITF or Code128, any grader
    if ocr and cert not in ocr_certs:
        # a 1D symbol has a weak or no checksum and repeated reads of it are not independent: the printed digits are
        # the independent evidence here, so a disagreement is never ignored
        return Verdict("needs_review", cert, srt(machine) + ("ocr",), note(f"barcode {cert} but OCR read {'/'.join(sorted(ocr_certs))} - verify by eye"),
                       grader=grader, raw=raw)
    if cert in ocr_certs:
        status, srcs, why = "ok", srt(machine) + ("ocr",), "barcode confirmed by OCR"
    elif len({r.source for r in machine}) >= min_sources:
        status, srcs, why = "ok", srt(machine), ""
    else:
        status, srcs, why = "needs_review", srt(machine), "one printed barcode only (no QR) - confirm"
    if status == "ok" and grader == "unknown":
        return Verdict("needs_review", cert, srcs, note("grader not confirmed (a code with no grader's format)"), grader="unknown", raw=raw)
    return Verdict(status, cert, srcs, note(why), grader=grader, raw=raw)
