from slabscan.certs import CodeRead, ItfModel, consensus, parse_cert, parse_payload


def test_parse_url_payload():
    assert parse_cert("https://www.psacard.com/cert/148069831") == "148069831"
    assert parse_cert("http://psacard.com/cert/07766554/") == "7766554"


def test_itf_payload_is_the_cert_zero_padded_to_8_digits():
    # every real PSA ITF is 8 digits; 7-digit certs are zero-padded, 9-digit certs never use ITF
    assert parse_cert("26275088", symbology="ITF") == parse_cert("https://www.psacard.com/cert/26275088/") == "26275088"
    assert parse_cert("02074012", symbology="ITF") == "2074012"
    assert parse_cert("0148069831", symbology="ITF") is None  # 10 digits: the old 'padded 9-digit cert' guess, never seen


def test_parse_bare_digits_canonical():
    assert parse_cert("07766554") == "7766554"
    assert parse_cert(" 158084833 ") == "158084833"


def test_short_read_rejected():
    assert parse_cert("148069") is None  # 6 raw digits: looks like an ITF short read
    assert parse_cert("000000000") is None


def test_parse_rejects_non_certs():
    assert parse_cert("2023") is None
    assert parse_cert("GEM MT 10") is None
    assert parse_cert("12345678901") is None  # 11 digits
    assert parse_cert("") is None


def test_custom_regex_override():
    assert parse_cert("PSA-148069831-X", custom_regex=r"PSA-(\d+)-") == "148069831"


def _r(cert, source, symbology="QRCode", raw=None, grader="PSA", camera="", frame=""):
    return CodeRead(cert=cert, source=source, symbology=symbology, raw=raw or cert, camera=camera, grader=grader, frame=frame)


def _itf(raw, source="front_barcode"):
    p = parse_payload(raw, "ITF")
    return CodeRead(cert=p.cert, source=source, symbology="ITF", raw=raw, grader=p.grader)


def test_other_graders_detected():
    assert parse_payload("https://www.cgccards.com/certlookup/4123456001/", "QRCode").grader == "CGC"
    assert parse_payload("https://www.beckett.com/grading/card-lookup?item_id=0012345678").grader == "BGS"
    assert parse_payload("148069831", "Code128").grader == "PSA"  # PSA current labels: the cert as Code128, front and back
    assert parse_payload("4123456001", "Code128").grader == "CGC"  # CGC 2023+ front: 10 digits
    assert parse_payload("26275088", "ITF").grader == "PSA"
    v = consensus([_r("4123456001", "back_qr", grader="CGC")])
    assert v.status == "ok" and v.grader == "CGC" and v.cert == "4123456001"
    v = consensus([_r("0012345678", "front_qr", grader="BGS")])
    assert v.status == "other_grader" and v.grader == "BGS"
    v = consensus([_r("0012345678", "front_qr", grader="BGS")], accepted=("PSA", "CGC", "BGS"))
    assert v.status == "ok"


def test_itf_model_is_fixed_and_counts_agreements():
    m = ItfModel()
    assert m.mode == "zero_pad"
    for cert in ["26275088", "27720238", "48277665"]:
        v = consensus([_r(cert, "back_qr"), _itf(cert, "back_barcode"), _itf(cert)], m)
        assert v.status == "ok" and v.cert == cert
    assert m.evidence["zero_pad"] == 3


def test_2016_label_back_and_front_itf_is_ok_without_learning():
    """Regression: back ITF + front ITF (two printed symbols) stayed needs_review 'padding vs check digit not learned
    yet' forever, because no real label could teach the ITF model."""
    v = consensus([_itf("25656882", "back_barcode"), _itf("25656882")], ItfModel())
    assert v.status == "ok" and v.cert == "25656882" and v.sources == ("back_barcode", "front_barcode")


def test_qr_vs_wrong_itf_is_conflict():
    v = consensus([_r("26275088", "back_qr"), _itf("26275089")])
    assert v.status == "conflict"


def test_consensus_agreeing_codes_ok():
    v = consensus([_r("148069831", "back_qr"), _r("148069831", "front_barcode", "Code128")])
    assert v.status == "ok" and v.cert == "148069831"
    assert v.sources[0] == "back_qr"


def test_consensus_conflict_never_guesses():
    v = consensus([_r("148069831", "back_qr"), _r("148069832", "front_barcode", "Code128")])
    assert v.status == "conflict" and v.cert is None


def test_consensus_ocr_only_needs_review_and_names_no_grader():
    v = consensus([_r("148069831", "ocr", "OCR", grader="unknown")])
    assert v.status == "needs_review" and v.cert == "148069831" and v.grader == "unknown"


def test_consensus_qr_ignores_ocr():
    v = consensus([_r("148069831", "back_qr"), _r("148069881", "ocr", "OCR")])
    assert v.status == "ok" and v.cert == "148069831"


def test_consensus_empty():
    assert consensus([]).status == "no_read"


def test_single_1d_read_needs_confirmation():
    raw = "26275088"
    assert consensus([_itf(raw)]).status == "needs_review"
    assert consensus([_itf(raw), _r("26275088", "ocr", "OCR", grader="unknown")]).status == "ok"  # OCR of the printed digits agrees
    assert consensus([_itf(raw), _itf(raw, "back_barcode")]).status == "ok"
    # the same for Code128, PSA or CGC
    assert consensus([_r("148069831", "back_barcode", "Code128")]).status == "needs_review"
    assert consensus([_r("148069831", "back_barcode", "Code128"), _r("148069831", "front_barcode", "Code128")]).status == "ok"
    v = consensus([_r("6003997046", "front_barcode", "Code128", grader="CGC")])
    assert v.status == "needs_review" and v.grader == "CGC"  # a single CGC barcode is never 'ok' alone


def test_repeated_reads_of_one_source_are_not_independent():
    """Two frames from one pose (or two overlapping tiles of one frame) are one source, not two."""
    v = consensus([_itf("26275088"), _itf("26275088"), _itf("26275088")])
    assert v.status == "needs_review" and "one printed barcode" in v.note


def test_ocr_that_disagrees_with_a_1d_only_read_is_not_ignored():
    """Regression (software-14): two agreeing ITF reads + a different OCR read used to be 'ok' with
    'ocr disagreed (ignored)'; the OCR is the only independent evidence there."""
    v = consensus([_itf("26275088", "back_barcode"), _itf("26275088"), _r("26275888", "ocr", "OCR", grader="unknown")])
    assert v.status == "needs_review" and "OCR" in v.note and v.cert == "26275088"


def test_other_grader_code_vs_a_different_psa_code_is_a_conflict():
    """Regression (software-8): a CGC QR plus a PSA QR/ITF with another number gave 'ok' for the CGC cert."""
    cgc = _r("4123456001", "back_qr", grader="CGC")
    v = consensus([cgc, _r("148069831", "back_qr")])
    assert v.status == "conflict"
    v = consensus([cgc, _itf("26275088", "back_barcode")])
    assert v.status == "conflict"
    v = consensus([cgc, _r("4123456001", "front_barcode", "Code128", grader="CGC")])  # CGC's own front barcode, same number
    assert v.status == "ok" and v.grader == "CGC"


def test_custom_regex_keeps_other_graders():
    """Regression (software-7): a custom_regex replaced every rule, so a CGC URL it matched became a PSA cert."""
    rx = r"(\d{7,10})"
    p = parse_payload("https://www.cgccards.com/certlookup/4024847001/", "QRCode", rx)
    assert p.grader == "CGC" and p.cert == "4024847001"
    p = parse_payload("4024847001", "Code128", rx)
    assert p.grader == "CGC"  # CGC's own barcode format runs before the custom PSA rule
    assert parse_payload("148069831", "OCR", r"PSA-(\d+)-") is not None  # OCR digit runs are not forced through it


def test_custom_regex_is_validated(tmp_path):
    import pytest

    from slabscan.config import check_custom_regex, dumps, from_layout, load

    check_custom_regex(r"PSA-(\d+)-")
    for bad in (r"PSA-\d+-", r"(PSA)-(\d+)", r"(\d+"):
        with pytest.raises(ValueError):
            check_custom_regex(bad)
    (tmp_path / "m.toml").write_text(dumps(from_layout()))
    (tmp_path / "c.toml").write_text('custom_regex = "cert=\\\\d+"\n')
    with pytest.raises(ValueError, match="capture group"):
        load(tmp_path / "m.toml", tmp_path / "c.toml")
