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


def _itf(raw, source="front_barcode"):
    p = parse_payload(raw, "ITF")
    return CodeRead(cert=p.cert, source=source, symbology="ITF", raw=raw, alt_cert=p.alt_cert, grader=p.grader)


def _with_check(body):
    for d in "0123456789":
        if itf_check_ok(body + d):
            return body + d


def test_other_graders_detected():
    assert parse_payload("https://www.cgccards.com/certlookup/4123456001/").grader == "CGC"
    assert parse_payload("https://www.beckett.com/grading/card-lookup?item_id=0012345678").grader == "BGS"
    assert parse_payload("148069831", "Code128").grader == "unknown"
    assert parse_payload("0148069831", "ITF").grader == "PSA"
    v = consensus([_r("4123456001", "front_qr", grader="CGC")])
    assert v.status == "ok" and v.grader == "CGC" and v.cert == "4123456001"
    v = consensus([_r("0012345678", "front_qr", grader="BGS")])
    assert v.status == "other_grader" and v.grader == "BGS"
    v = consensus([_r("0012345678", "front_qr", grader="BGS")], accepted=("PSA", "CGC", "BGS"))
    assert v.status == "ok"


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
    # a 2015-2017 label with ITF only: back barcode + front barcode are two independent sources
    raw = _with_check("014806983")  # payload whose last digit happens to be a valid check digit
    v = consensus([_itf(raw, "back_barcode"), _itf(raw)], m)
    assert v.status == "ok" and v.cert == raw.lstrip("0")


def test_itf_model_learns_check_digit_mode():
    m = ItfModel()
    for cert in ["148069831", "151234567", "160000123"]:
        raw = _with_check(cert)  # 10 digits = 9-digit cert + check digit
        v = consensus([_r(cert, "back_qr"), _itf(raw)], m)
        assert v.status == "ok" and v.cert == cert, v
    assert m.mode == "check_digit"
    raw = _with_check("172345678")
    v = consensus([_itf(raw, "back_barcode"), _itf(raw)], m)
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


def _learned(mode="zero_pad"):
    m = ItfModel()
    m.evidence[mode] = 3
    return m


def test_single_itf_read_needs_confirmation():
    raw = "0148069831"
    assert not itf_check_ok(raw)
    assert consensus([_itf(raw)]).status == "needs_review"
    assert consensus([_itf(raw), _r("148069831", "ocr", "OCR")]).status == "ok"  # OCR of the printed digits agrees
    m = _learned()
    assert consensus([_itf(raw)], m).status == "needs_review"
    assert consensus([_itf(raw), _itf(raw, "back_barcode")], m).status == "ok"


def test_itf_only_is_never_trusted_before_the_format_is_learned():
    """Regression (software-4): with the mode unlearned, a payload whose last digit is not a valid check
    digit was taken as zero-padded and two reads gave 'ok'. ITF has no checksum: one misread digit of a
    check-digit payload looks exactly like that. 0452109870 misread as 0453109870 became cert 453109870."""
    bad = "0453109870"
    assert not itf_check_ok(bad)
    v = consensus([_itf(bad, "back_barcode"), _itf(bad)], ItfModel())
    assert v.status == "needs_review" and "not learned" in v.note


def test_repeated_reads_of_one_source_are_not_independent():
    """Two frames from one pose (or two overlapping tiles of one frame) are one source, not two."""
    raw = "0148069831"
    v = consensus([_itf(raw), _itf(raw), _itf(raw)], _learned())
    assert v.status == "needs_review" and "one source" in v.note


def test_ocr_that_disagrees_with_an_itf_only_read_is_not_ignored():
    """Regression (software-14): two agreeing ITF reads + a different OCR read used to be 'ok' with
    'ocr disagreed (ignored)'; the OCR is the only independent evidence there."""
    raw = "0148069831"
    v = consensus([_itf(raw, "back_barcode"), _itf(raw), _r("148069881", "ocr", "OCR")], _learned())
    assert v.status == "needs_review" and "OCR" in v.note and v.cert == "148069831"


def test_other_grader_code_vs_a_different_psa_code_is_a_conflict():
    """Regression (software-8): a CGC QR plus a PSA QR/ITF with another number gave 'ok' for the CGC cert."""
    cgc = _r("4123456001", "back_qr", grader="CGC")
    v = consensus([cgc, _r("148069831", "back_qr")])
    assert v.status == "conflict"
    v = consensus([cgc, _itf("0148069831", "back_barcode")])
    assert v.status == "conflict"
    v = consensus([cgc, _r("4123456001", "barcode", "Code128", grader="unknown")])  # CGC's own 1D code, same number
    assert v.status == "ok" and v.grader == "CGC"


def test_custom_regex_keeps_other_graders_and_the_itf_check_digit():
    """Regression (software-7): a custom_regex replaced every rule, so a CGC URL it matched became a PSA cert
    and ITF reads lost their check-digit interpretation (ItfModel could never learn 'check_digit')."""
    rx = r"(\d{7,10})"
    p = parse_payload("https://www.cgccards.com/certlookup/4024847001/", "QRCode", rx)
    assert p.grader == "CGC" and p.cert == "4024847001"
    raw = _with_check("172345678")
    p = parse_payload(raw, "ITF", rx)
    assert p.grader == "PSA" and p.alt_cert == "172345678"
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
