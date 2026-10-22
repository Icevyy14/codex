"""Decode pipeline against synthetic labels that carry the codes real labels carry (sim.label_codes).

Design point = what the machine's camera + cross-polarised lighting must deliver:
<= 0.05 mm/px on the label, blur <= 1.2 px, residual glare <= 0.7.
"""

import pytest

from slabscan.certs import canonical
from slabscan.decode import decode_frame, ocr_available, ocr_digits
from slabscan.sim import Degrade, label_codes, slab_view

# (grader, era, cert): PSA current (Code128), lighthouse (QR + ITF), 2016 (ITF), pre-2016 with a 7-digit cert (ITF),
# CGC 2023+ (10 and 13 digits), CGC 2020-23 OG, CGC Authentic
LABELS = [("PSA", "current", "148069831"), ("PSA", "2017+", "45210987"), ("PSA", "2016", "25656882"), ("PSA", "old", "7766554"),
          ("CGC", "2023+", "6003997046"), ("CGC", "2023+", "1401012893129"), ("CGC", "og", "3750599206"), ("CGC", "authentic", "6182652005")]


@pytest.mark.parametrize("grader,era,cert", LABELS)
@pytest.mark.parametrize("side", ["front", "back"])
def test_design_point_decodes(grader, era, cert, side):
    deg = Degrade(mm_per_px=0.05, blur_px=1.2, glare=0.7, tilt_deg=6, rotate_deg=2)
    reads, unparsed = decode_frame(slab_view(cert, side, deg, grader, era), side, allow_ocr=False)
    if not label_codes(cert, side, grader, era):
        assert reads == [] and unparsed == []  # nothing printed there (an old PSA back, an OG front, an Authentic back)
        return
    assert reads, "nothing decoded at design point"
    assert all(r.cert == canonical(cert) and r.grader == grader for r in reads)


def test_back_qr_survives_coarse_camera():
    deg = Degrade(mm_per_px=0.12, blur_px=1.2, glare=1.0)
    reads, _ = decode_frame(slab_view("148069831", "back", deg), "back", allow_ocr=False)
    assert any(r.source == "back_qr" and r.cert == "148069831" for r in reads)


def test_itf_zero_padded_front_matches_back_qr():
    deg = Degrade(mm_per_px=0.04)
    front, _ = decode_frame(slab_view("7766554", "front", deg, era="2017+"), "front", allow_ocr=False)
    back, _ = decode_frame(slab_view("7766554", "back", deg, era="2017+"), "back", allow_ocr=False)
    assert {r.cert for r in front} == {r.cert for r in back} == {"7766554"}
    assert any(r.raw == "07766554" and r.symbology == "ITF" for r in front)


def test_blank_frame_gives_no_read_not_garbage():
    import numpy as np

    reads, unparsed = decode_frame(np.full((600, 1500), 60, np.uint8), "front", allow_ocr=False)
    assert reads == [] and unparsed == []


@pytest.mark.skipif(not ocr_available(), reason="tesseract not installed")
def test_ocr_fallback_reads_printed_digits():
    deg = Degrade(mm_per_px=0.03, blur_px=0.6, glare=0.0, tilt_deg=0, rotate_deg=0)
    img = slab_view("148069831", "front", deg)
    reads = ocr_digits(img, "front")
    assert reads and reads[0].source == "ocr" and reads[0].grader == "unknown"
