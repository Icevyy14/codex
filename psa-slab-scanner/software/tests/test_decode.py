"""Decode pipeline against synthetic PSA-style labels.

Design point = what the machine's camera + cross-polarised lighting must deliver:
<= 0.05 mm/px on the label, blur <= 1.2 px, residual glare <= 0.7.
"""

import pytest

from slabscan.certs import canonical
from slabscan.decode import decode_frame, ocr_available, ocr_digits
from slabscan.sim import Degrade, slab_view

CERTS = ["148069831", "45210987", "07766554"]


@pytest.mark.parametrize("cert", CERTS)
@pytest.mark.parametrize("side", ["front", "back"])
@pytest.mark.parametrize("symbology", ["ITF", "Code128", "Code39"])
def test_design_point_decodes(cert, side, symbology):
    deg = Degrade(mm_per_px=0.05, blur_px=1.2, glare=0.7, tilt_deg=6, rotate_deg=2)
    module = 0.19 if symbology == "Code39" else 0.25
    reads, _ = decode_frame(slab_view(cert, side, deg, symbology, module), side, allow_ocr=False)
    assert reads, "nothing decoded at design point"
    assert all(r.cert == canonical(cert) for r in reads)


def test_back_qr_survives_coarse_camera():
    deg = Degrade(mm_per_px=0.12, blur_px=1.2, glare=1.0)
    reads, _ = decode_frame(slab_view("148069831", "back", deg), "back", allow_ocr=False)
    assert any(r.source == "back_qr" and r.cert == "148069831" for r in reads)


def test_itf_zero_padded_front_matches_back_qr():
    deg = Degrade(mm_per_px=0.04)
    front, _ = decode_frame(slab_view("148069831", "front", deg, "ITF"), "front", allow_ocr=False)
    back, _ = decode_frame(slab_view("148069831", "back", deg, "ITF"), "back", allow_ocr=False)
    assert {r.cert for r in front} == {r.cert for r in back} == {"148069831"}
    assert any(r.raw == "0148069831" for r in front)


def test_blank_frame_gives_no_read_not_garbage():
    import numpy as np

    reads, unparsed = decode_frame(np.full((600, 1500), 60, np.uint8), "front", allow_ocr=False)
    assert reads == [] and unparsed == []


@pytest.mark.skipif(not ocr_available(), reason="tesseract not installed")
def test_ocr_fallback_reads_printed_digits():
    deg = Degrade(mm_per_px=0.03, blur_px=0.6, glare=0.0, tilt_deg=0, rotate_deg=0)
    img = slab_view("148069831", "front", deg)
    reads = ocr_digits(img, "front")
    assert reads and reads[0].source == "ocr"
