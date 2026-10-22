from slabscan.certs import CodeRead, ItfModel, consensus, itf_check_ok, parse_cert, parse_payload


def test_parse_url_payload():
    assert parse_cert("https://www.psacard.com/cert/148069831") == "148069831"
    assert parse_cert("http://psacard.com/cert/07766554/") == "7766554"


def test_itf_padded_payload_matches_qr():
    # ITF holds an even digit count, so a 9-digit cert may be printed as "0" + cert.
    assert parse_cert("0148069831", symbology="ITF") == parse_cert("https://www.psacard.com/cert/148069831/") == "148069831"


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


def _r(cert, source, symbology="QRCode", raw=None, alt=None, grader="PSA"):
    return CodeRead(cert=cert, source=source, symbology=symbology, raw=raw or cert, alt_cert=alt, grader=grader)


def _itf(raw):
    p = parse_payload(raw, "ITF")
    return CodeRead(cert=p.cert, source="front_barcode", symbology="ITF", raw=raw, alt_cert=p.alt_cert, grader=p.grader)


def _with_check(body):
    for d in "0123456789":
        if itf_check_ok(body + d):
            return body + d


def test_other_graders_detected():
    assert parse_payload("https://www.cgccards.com/certlookup/4123456001/").grader == "CGC"
    assert parse_payload("https://www.beckett.com/grading/card-lookup?item_id=0012345678").grader == "BGS"
    assert parse_payload("148069831", "Code128").grader == "unknown"
    assert parse_payload("0148069831", "ITF").grader == "PSA"
    v = consensus([_r("4123456001", "back_qr", grader="CGC")])
    assert v.status == "other_grader" and v.grader == "CGC"


def test_itf_model_learns_zero_pad_and_resolves_itf_only():
    m = ItfModel()
    # three slabs with readable QR and ITF teach the model
    for cert in ["148069831", "151234567", "160000123"]:
        raw = "0" + cert
        if itf_check_ok(raw):
            raw = raw  # rare: the padded payload also passes a check-digit test; still zero-pad evidence
        v = consensus([_r(cert, "back_qr"), _itf(raw), _itf(raw)], m)
        assert v.status == "ok" and v.cert == cert
    assert m.mode == "zero_pad"
    # a pre-2017 label with ITF only
    raw = _with_check("014806983")  # payload whose last digit happens to be a valid check digit
    v = consensus([_itf(raw), _itf(raw)], m)
    assert v.status == "ok" and v.cert == raw.lstrip("0")


def test_itf_model_learns_check_digit_mode():
    m = ItfModel()
    for cert in ["148069831", "151234567", "160000123"]:
        raw = _with_check(cert)  # 10 digits = 9-digit cert + check digit
        v = consensus([_r(cert, "back_qr"), _itf(raw)], m)
        assert v.status == "ok" and v.cert == cert, v
    assert m.mode == "check_digit"
    raw = _with_check("172345678")
    v = consensus([_itf(raw), _itf(raw)], m)
    assert v.status == "ok" and v.cert == "172345678"


def test_itf_only_ambiguous_until_learned():
    raw = _with_check("172345678")
    v = consensus([_itf(raw), _itf(raw)], ItfModel())
    assert v.status == "needs_review" and "not learned" in v.note


def test_qr_vs_wrong_itf_is_conflict():
    v = consensus([_r("148069831", "back_qr"), _itf("0148069839")])
    assert v.status == "conflict"


def test_consensus_agreeing_codes_ok():
    v = consensus([_r("148069831", "back_qr"), _r("148069831", "front_barcode")])
    assert v.status == "ok" and v.cert == "148069831"
    assert v.sources[0] == "back_qr"


def test_consensus_conflict_never_guesses():
    v = consensus([_r("148069831", "back_qr"), _r("148069832", "front_barcode")])
    assert v.status == "conflict" and v.cert is None


def test_consensus_ocr_only_needs_review():
    v = consensus([_r("148069831", "ocr")])
    assert v.status == "needs_review" and v.cert == "148069831"


def test_consensus_qr_ignores_ocr():
    v = consensus([_r("148069831", "back_qr"), _r("148069881", "ocr", "OCR")])
    assert v.status == "ok" and v.cert == "148069831"


def test_consensus_empty():
    assert consensus([]).status == "no_read"


def test_single_itf_read_needs_confirmation():
    raw = "0148069831"
    assert not itf_check_ok(raw)  # unambiguous payload
    assert consensus([_itf(raw)]).status == "needs_review"
    assert consensus([_itf(raw), _itf(raw)]).status == "ok"
    assert consensus([_itf(raw), _r("148069831", "ocr", "OCR")]).status == "ok"
