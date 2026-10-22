from slabscan.certs import CodeRead, consensus, parse_cert


def test_parse_url_payload():
    assert parse_cert("https://www.psacard.com/cert/148069831") == "148069831"
    assert parse_cert("http://psacard.com/cert/07766554/") == "07766554"


def test_parse_bare_digits_keeps_leading_zero():
    assert parse_cert("07766554") == "07766554"
    assert parse_cert(" 158084833 ") == "158084833"


def test_parse_rejects_non_certs():
    assert parse_cert("2023") is None
    assert parse_cert("GEM MT 10") is None
    assert parse_cert("12345678901") is None  # 11 digits
    assert parse_cert("") is None


def test_custom_regex_override():
    assert parse_cert("PSA-148069831-X", custom_regex=r"PSA-(\d+)-") == "148069831"


def _r(cert, source):
    return CodeRead(cert=cert, source=source, symbology="x", raw=cert)


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
