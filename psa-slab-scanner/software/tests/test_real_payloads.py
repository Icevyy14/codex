"""The parsing, consensus and face-down rules against payload strings decoded from REAL slab labels.

Every string below was decoded by zxing-cpp from a photo of a real PSA or CGC slab (64 slabs, Oct 2026; the photos
themselves are not in the repository). They pin down the label formats certs.py describes. The optional last test runs
tools/real_eval.py on such a folder of photos when SLABRAIL_REAL_IMAGES points to it.
"""

import json
import os
import types
from pathlib import Path

import numpy as np
import pytest

from slabscan import decode
from slabscan.certs import OCR_TOKEN_RE, CodeRead, consensus, face_from_above, label_side, parse_payload

# (symbology, payload, grader, cert, label side the format proves)
REAL = [
    ("QRCode", "http://psacard.com/cert/27720238", "PSA", "27720238", "back"),  # PSA 2017+ lighthouse back, first URL form
    ("QRCode", "https://www.psacard.com/cert/26275088/", "PSA", "26275088", "back"),  # later URL form
    ("QRCode", "https://www.psacard.com/cert/100423658/", "PSA", "100423658", "back"),  # current label, 9-digit cert
    ("ITF", "26275088", "PSA", "26275088", None),  # PSA ITF: front (all eras) and back (2016+)
    ("ITF", "02074012", "PSA", "2074012", None),  # 7-digit cert, zero-padded to 8 (pre-2016 label)
    ("ITF", "01418255", "PSA", "1418255", None),
    ("Code128", "100423658", "PSA", "100423658", None),  # current label: the same Code128 on the front and the back
    ("Code128", "27435764", "PSA", "27435764", None),
    ("Code128", "6003997046", "CGC", "6003997046", "front"),  # CGC 2023+ front
    ("Code128", "1401012893129", "CGC", "1401012893129", "front"),  # 13-digit CGC cert (140 + 10)
    ("QRCode", "https://www.cgccards.com/certlookup/6003997046/10_0/", "CGC", "6003997046", "back"),  # CGC 2023+ back
    ("QRCode", "https://www.cgccards.com/certlookup/6003997046/10_0", "CGC", "6003997046", "back"),
    ("QRCode", "HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/", "CGC", "1401012893129", "back"),
    ("QRCode", "https://www.cgccomics.com/certlookup/3750599206/9_0", "CGC", "3750599206", "back"),  # CGC 2020-23 OG back
    ("QRCode", "https://www.cgccomics.com/certlookup/4067281028/8_5", "CGC", "4067281028", "back"),
    ("QRCode", "https://www.cgccomics.com/certlookup/3805531090/7_0", "CGC", "3805531090", "back"),
    ("Code128", "47140890000000003750599206", "CGC", "3750599206", "back"),  # OG back barcode: 26 digits, the cert last
    ("Code128", "47319985000000004067281028", "CGC", "4067281028", "back"),
    ("Code128", "48298585000000003931864027", "CGC", "3931864027", "back"),
    ("Code128", "47363270956575753805531090", "CGC", "3805531090", "back"),  # non-zero middle digits
    ("Code128", "0047064500000000004190928178", "CGC", "4190928178", "back"),  # 28 digits
    ("QRCode", "https://www.cgccards.com/certlookup/6182652005/0_0/", "CGC", "6182652005", "front"),  # CGC Authentic FRONT
]


@pytest.mark.parametrize("sym,payload,grader,cert,side", REAL)
def test_real_payloads_parse(sym, payload, grader, cert, side):
    p = parse_payload(payload, sym)
    assert p is not None and (p.grader, p.cert, p.side) == (grader, cert, side)
    e = label_side(sym, payload)
    assert (e.side if e else None) == side and (e is None or e.certain)


def test_the_13_digit_cgc_cert_is_never_cut_to_12():
    """Regression: cgccards\\.com/\\S*?(\\d{7,12}) parsed this QR as 140101289312, and the slab came out 'ok' with the
    wrong number; the 13-digit front Code128 that contradicts it was thrown away as unparsed."""
    qr = parse_payload("HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/", "QRCode")
    c128 = parse_payload("1401012893129", "Code128")
    assert qr.cert == c128.cert == "1401012893129"
    assert parse_payload("https://www.cgccards.com/certlookup/140101289312/10_0/", "QRCode") is None  # 12 digits: not a CGC cert
    reads = [CodeRead(qr.cert, "back_qr", "QRCode", "x", "back", "CGC"), CodeRead(c128.cert, "front_barcode", "Code128", "1401012893129", "front", "CGC")]
    v = consensus(reads)
    assert v.status == "ok" and v.cert == "1401012893129" and v.grader == "CGC"


@pytest.mark.parametrize("sym,payload", [
    ("ITF", "289412"),  # glare cut a real ITF (28941258) short
    ("ITF", "0148069831"),  # 10 digits: no real PSA ITF has them
    ("QRCode", "https://www.cgccards.com/certlookup/"),  # CGC QR without a cert (press images)
    ("QRCode", "http://cgccomics.com/verify"),
    ("QRCode", "cgccomics.com"),
    ("QRCode", "https://www.psacard.com/cert/012345678901/"),  # too long: rejected, not cut
    ("Code128", "12345678901"),  # 11 digits: no grader's format
])
def test_payloads_that_are_not_a_cert(sym, payload):
    assert parse_payload(payload, sym) is None


def test_a_cgc_qr_without_a_cert_is_a_hint_never_a_proof():
    e = label_side("QRCode", "https://www.cgccards.com/certlookup/")
    assert e.side == "back" and not e.certain
    face, why, _ = face_from_above([], ["QRCode:https://www.cgccards.com/certlookup/"])
    assert face == "unknown" and "CGC QR without a cert" in why


def _read(sym, payload, camera="back", frame=""):
    p = parse_payload(payload, sym)
    return CodeRead(p.cert, decode._source_for(sym, camera, p.side), sym, payload, camera, p.grader, frame)


@pytest.mark.parametrize("reads,unparsed,face", [
    ([("QRCode", "https://www.psacard.com/cert/26275088/")], [], "down"),
    ([("QRCode", "https://www.cgccards.com/certlookup/6003997046/10_0/")], [], "down"),
    ([("QRCode", "https://www.cgccomics.com/certlookup/3750599206/9_0")], [], "down"),
    ([("Code128", "47140890000000003750599206")], [], "down"),  # the OG back barcode alone (QR lost in glare)
    ([("QRCode", "https://www.cgccards.com/certlookup/6182652005/0_0/")], [], "up"),  # a face-up CGC Authentic
    ([("Code128", "6003997046")], [], "up"),  # a face-up CGC 2023+ slab
    ([("Code128", "1401012893129")], [], "up"),
    ([("ITF", "26275088")], [], "unknown"),  # PSA ITF: front of every era and back of 2016+ labels
    ([("Code128", "100423658")], [], "unknown"),  # PSA Code128: identical on the front and the back
    ([], [], "unknown"),  # pre-2016 PSA backs, CGC Authentic backs, BGS, SGC
    ([("QRCode", "https://www.psacard.com/cert/26275088/"), ("Code128", "6003997046")], [], "neighbour"),
    ([("QRCode", "https://www.psacard.com/cert/26275088/"), ("QRCode", "https://www.psacard.com/cert/27720238")], [], "neighbour"),
])
def test_face_from_above_side_table(reads, unparsed, face):
    got, why, _ = face_from_above([_read(s, p) for s, p in reads], unparsed)
    assert got == face, why


def test_source_follows_the_label_side_the_payload_proves():
    # the CGC Authentic QR is printed on the FRONT label: read by the station camera it is the front QR
    assert _read("QRCode", "https://www.cgccards.com/certlookup/6182652005/0_0/", "front").source == "front_qr"
    # a PSA QR is always on the back label, whichever camera reads it (from below: the slab was face-up)
    assert _read("QRCode", "https://www.psacard.com/cert/26275088/", "front").source == "back_qr"
    # PSA ITF/Code128 sit on both sides: the camera decides
    assert _read("Code128", "100423658", "back").source == "back_barcode"
    assert _read("Code128", "100423658", "front").source == "front_barcode"


def test_phantom_read_is_dropped_when_another_frame_confirms_the_real_number():
    """Real: at full resolution zxing-cpp also read '09435764' from a thin band inside the Code128 '27435764', and the
    slab became a conflict ('codes disagree: 27435764, 9435764')."""
    real, phantom = _read("Code128", "27435764", "front", "f1"), _read("Code128", "09435764", "front", "f1")
    qr = _read("QRCode", "https://www.psacard.com/cert/27435764/", "back", "b1")
    v = consensus([qr, real, phantom])
    assert v.status == "ok" and v.cert == "27435764" and "phantom" in v.note
    # nothing confirms either number: never guess
    assert consensus([real, phantom]).status == "conflict"
    # both numbers in two frames of the same pose: still a conflict, nothing is dropped
    assert consensus([real, phantom, _read("Code128", "27435764", "front", "f2"), _read("Code128", "09435764", "front", "f2")]).status == "conflict"


def _zx(text, pts, fmt="Code128"):
    P = types.SimpleNamespace
    tl, tr, br, bl = (P(x=x, y=y) for x, y in pts)
    return P(format=P(name=fmt), text=text, position=P(top_left=tl, top_right=tr, bottom_right=br, bottom_left=bl))


def test_decode_drops_a_thin_linear_read_inside_another():
    real = _zx("27435764", [(240, 486), (633, 486), (633, 547), (240, 547)])  # the real boxes, px
    phantom = _zx("09435764", [(240, 522), (630, 522), (630, 534), (240, 534)])
    assert decode._phantoms([real, phantom]) == {1}
    other = _zx("27435764", [(240, 700), (633, 700), (633, 760), (240, 760)])  # a second full code elsewhere: kept
    assert decode._phantoms([real, other]) == set()
    qr = _zx("https://www.psacard.com/cert/27435764/", [(250, 500), (300, 500), (300, 530), (250, 530)], "QRCode")
    assert decode._phantoms([real, qr]) == set()  # other symbologies are never phantoms of a barcode


def test_head_frame_with_only_a_barcode_gets_the_clahe_pass(monkeypatch):
    """A back-label QR lost in glare on the plain pass but readable after CLAHE (real: fc_54065407_1 with a glare spot)
    is what proves a slab face-down: a head-camera frame does not stop at a barcode-only first pass."""
    calls = []
    itf = CodeRead("54065407", "back_barcode", "ITF", "54065407", "back")
    qr = CodeRead("54065407", "back_qr", "QRCode", "https://www.psacard.com/cert/54065407/", "back")

    def fake(img, camera, custom_regex, to_frame=None):
        calls.append(camera)
        return ([itf], []) if len(calls) == 1 else ([qr], [])

    monkeypatch.setattr(decode, "_zxing_pass", fake)
    reads, _ = decode.decode_frame(np.full((60, 80), 128, np.uint8), "back", allow_ocr=False)
    assert len(calls) == 2 and {r.symbology for r in reads} == {"ITF", "QRCode"}
    calls.clear()
    reads, _ = decode.decode_frame(np.full((60, 80), 128, np.uint8), "front", allow_ocr=False)
    assert len(calls) == 1 and [r.symbology for r in reads] == ["ITF"]  # the station camera stops at the first read


def test_ocr_tokens_and_typing():
    # cert-shaped runs only: PSA 8-9 digits, CGC 10 or 140 + 10; never the first 10 digits of a longer run
    assert OCR_TOKEN_RE.findall("GEM MT 10 2023 1401012893129 #025 20054106 123456789012 0019865140") == ["1401012893129", "20054106", "0019865140"]
    p = parse_payload("1401012893129", "OCR")
    assert p.grader == "unknown" and p.cert == "1401012893129"  # OCR names no grader


def test_ocr_runs_with_one_thread():
    assert os.environ.get("OMP_THREAD_LIMIT") == "1"  # set when slabscan.decode is imported, before tesseract runs


def test_real_ocr_misreads_never_make_an_ok():
    """Real front OCR misreads: '94065407' for 54065407 (5 read as 9), and an OCR-only number with no code at all."""
    itf = CodeRead("54065407", "front_barcode", "ITF", "54065407", "front", "PSA")
    ocr = CodeRead("94065407", "ocr", "OCR", "94065407", "front", "unknown")
    v = consensus([itf, ocr])
    assert v.status == "needs_review" and v.cert == "54065407"
    v = consensus([CodeRead("1995965624", "ocr", "OCR", "1995965624", "front", "unknown")])  # a number off a CGC OG card
    assert v.status == "needs_review" and v.grader == "unknown"


def test_label_band_crops_around_the_barcode():
    # a PSA or CGC front: the barcode at one end of the label, the printed cert on the same line
    r = CodeRead("26275088", "front_barcode", "ITF", "26275088", "front", box=(1500, 500, 2000, 560))
    a, c, b, d = decode.label_band((2592, 4608), [r])
    assert a == 0 and b == 3600 and c < 500 and d > 560 and (d - c) < 700
    assert decode.label_band((2592, 4608), []) is None


REAL_IMAGES = os.environ.get("SLABRAIL_REAL_IMAGES")


@pytest.mark.skipif(not REAL_IMAGES, reason="set SLABRAIL_REAL_IMAGES to a folder of real slab photos with an index.json")
def test_real_images_give_no_wrong_cert_and_no_false_face_down_proof(tmp_path):
    """Slow (minutes): every image at its own resolution through the whole pipeline (tools/real_eval.py)."""
    from tools import real_eval

    out = tmp_path / "real.json"
    code = real_eval.main([str(Path(REAL_IMAGES) / "index.json"), "--workers", "3", "--json", str(out)])
    s = json.loads(out.read_text())["summary"]
    assert s["wrong_ok"] == [] and s["false_down"] == [], s
    assert s["false_up"] == [], s
    assert code == 0
