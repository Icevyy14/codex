from slabscan.certs import CodeRead, consensus, parse_cert


def test_parse_url_payload():
    assert parse_cert("https://www.psacard.com/cert/148069831") == "148069831"
    assert parse_cert("http://psacard.com/cert/07766554/") == "7766554"


def test_itf_padded_payload_matches_qr():
    # ITF holds an even digit count, so a 9-digit cert may be printed as "0" + cert.
    assert parse_cert("0148069831") == parse_cert("https://www.psacard.com/cert/148069831/") == "148069831"


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


def _r(cert, source, symbology="QRCode"):
    return CodeRead(cert=cert, source=source, symbology=symbology, raw=cert)


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


def test_consensus_machine_beats_ocr():
    v = consensus([_r("148069831", "front_barcode"), _r("148069881", "ocr")])
    assert v.status == "ok" and v.cert == "148069831" and "ocr" in v.note


def test_consensus_empty():
    assert consensus([]).status == "no_read"


def test_single_itf_read_needs_confirmation():
    assert consensus([_r("148069831", "front_barcode", "ITF")]).status == "needs_review"
    two = [_r("148069831", "front_barcode", "ITF"), _r("148069831", "front_barcode", "ITF")]
    assert consensus(two).status == "ok"
    itf_plus_ocr = [_r("148069831", "front_barcode", "ITF"), _r("148069831", "ocr", "OCR")]
    assert consensus(itf_plus_ocr).status == "ok"
