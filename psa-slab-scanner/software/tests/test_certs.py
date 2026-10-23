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
    # OCR of the printed digits agrees: the digits are confirmed, and an 8-digit ITF so confirmed names PSA
    v = consensus([_itf(raw), _r("26275088", "ocr", "OCR", grader="unknown")])
    assert v.status == "ok" and v.grader == "PSA" and "barcode confirmed by OCR" in v.note and "grader PSA from its 8-digit ITF" in v.note
    assert consensus([_itf(raw), _itf(raw, "back_barcode")]).status == "ok"
    # the same for Code128, PSA or CGC, except that OCR confirms only a Code128's digits, never its grader
    assert consensus([_r("148069831", "back_barcode", "Code128")]).status == "needs_review"
    v = consensus([_r("148069831", "front_barcode", "Code128"), _r("148069831", "ocr", "OCR", grader="unknown")])
    assert v.status == "needs_review" and "grader PSA not confirmed" in v.note
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


def test_names_grader_only_for_a_cert_url():
    from slabscan.certs import names_grader

    def rd(sym, payload, camera="back"):
        p = parse_payload(payload, sym)
        return CodeRead(p.cert, "x", sym, payload, camera, p.grader, kind=p.kind)

    assert names_grader(rd("QRCode", "https://www.psacard.com/cert/26275088/"))
    assert names_grader(rd("QRCode", "https://www.cgccards.com/certlookup/6003997046/10_0/"))
    assert names_grader(rd("Code128", "https://www.psacard.com/cert/26275088"))  # a URL in a 1D code names it too
    for sym, payload in (("ITF", "26275088"), ("Code128", "100423658"), ("Code128", "6003997046"), ("Code128", "47140890000000003750599206"),
                         ("QRCode", "148069831"), ("OCR", "148069831")):
        assert not names_grader(rd(sym, payload)), (sym, payload)
    # a read built without its kind is parsed again
    assert not names_grader(CodeRead("6003997046", "front_barcode", "Code128", "6003997046", "front", "CGC"))
    assert names_grader(CodeRead("26275088", "back_qr", "QRCode", "http://psacard.com/cert/26275088", "back", "PSA"))


def test_a_grader_from_one_barcodes_length_is_never_ok():
    """software (round 3): a bare number gets its grader from symbology and length only. A BGS cert as a 10-digit
    Code128 on the front, with OCR agreeing, came out 'ok CGC'. OCR confirms the digits, never the grader."""
    bgs_like = _r("19865140", "front_barcode", "Code128", raw="0019865140", grader="CGC")
    ocr = _r("19865140", "ocr", "OCR", raw="0019865140", grader="unknown")
    v = consensus([bgs_like, ocr])
    assert v.status == "needs_review" and v.cert == "19865140" and "grader CGC not confirmed" in v.note
    # the one exception (round 5): a real pre-2016 PSA front, an 8-digit ITF whose digits OCR confirms -> ok PSA
    v = consensus([_itf("02074012"), _r("2074012", "ocr", "OCR", raw="02074012", grader="unknown")])
    assert v.status == "ok" and v.cert == "2074012" and v.grader == "PSA"
    # a QR with a bare number confirms the digits of a Code128, not its grader
    v = consensus([_r("148069831", "back_qr", "QRCode", raw="148069831", grader="unknown"), _r("148069831", "front_barcode", "Code128")])
    assert v.status == "needs_review" and "grader PSA not confirmed" in v.note
    # a code that names the grader, or a second printed symbol in its format, confirms it
    cgc_qr = _r("6003997046", "back_qr", raw="https://www.cgccards.com/certlookup/6003997046/10_0/", grader="CGC")
    assert consensus([cgc_qr, _r("6003997046", "front_barcode", "Code128", grader="CGC")]).status == "ok"
    assert consensus([_itf("25656882", "back_barcode"), _itf("25656882")]).status == "ok"  # a 2016 label: back + front ITF


def test_no_verdict_is_ok_on_a_grader_guessed_from_one_barcode():
    """Every combination of the reads one slab can give: an 'ok' always has a code naming its grader, two printed
    symbols in its format, or an 8-digit ITF whose digits OCR confirms (PSA only); a grader-unknown verdict is never
    'ok'."""
    from itertools import combinations

    from slabscan.certs import names_grader, psa_itf_confirmed

    c = "26275088"
    pool = [_itf(c, "back_barcode"), _itf(c), _r(c, "front_barcode", "Code128"), _r(c, "back_barcode", "Code128"),
            _r(c, "ocr", "OCR", grader="unknown"), _r(c, "back_qr", raw=c, grader="unknown"), _r(c, "back_barcode", "Code39", grader="unknown"),
            _r(c, "back_qr", raw=f"https://www.psacard.com/cert/{c}/")]
    n_ok = 0
    for k in range(1, len(pool) + 1):
        for reads in combinations(pool, k):
            v = consensus(list(reads))
            if v.status != "ok":
                continue
            n_ok += 1
            machine = [r for r in reads if r.source != "ocr" and r.grader == v.grader]
            assert v.grader != "unknown"
            itf_rule = v.grader == "PSA" and psa_itf_confirmed(list(reads), c)
            assert any(names_grader(r) for r in machine) or len({r.source for r in machine}) >= 2 or itf_rule, [r.raw for r in reads]
            if itf_rule and not any(names_grader(r) for r in machine) and len({r.source for r in machine}) < 2:
                # the ITF rule alone: an ITF-8 plus OCR of its digits, never the ITF by itself, and never a code in no
                # grader's format (a bare-number QR, a Code39) in place of the OCR
                itf = [r for r in machine if r.symbology == "ITF"]
                assert itf and any(r.source == "ocr" and r.cert == c for r in reads), [r.raw for r in reads]
    assert n_ok > 0


def _ocr(digits):
    return CodeRead(digits.lstrip("0"), "ocr", "OCR", digits, "front", "unknown", kind="ocr")


def test_an_8_digit_itf_names_psa_only_once_ocr_confirms_its_digits():
    """Round 5: in the real set ITF is printed only on PSA labels (CGC uses Code128; BGS and SGC print no code), and a
    pre-2016 PSA label's only code is its front ITF. So an 8-digit ITF names grader PSA once OCR of the printed number
    confirms its digits. A second printed symbol in no grader's format does not: no PSA label carries one. Everything
    else keeps the round-4 rule."""
    from slabscan.certs import psa_itf_confirmed

    old = _itf("02074012")  # a real pre-2016 front ITF: the 7-digit cert zero-padded to 8
    # ITF-8 + OCR of the same printed number: ok PSA, and the note says why
    v = consensus([old, old, _ocr("02074012")])
    assert (v.status, v.cert, v.grader, v.sources) == ("ok", "2074012", "PSA", ("front_barcode", "ocr"))
    assert "barcode confirmed by OCR" in v.note and "grader PSA from its 8-digit ITF" in v.note
    # ITF-8 alone, however often it is read: needs_review (one printed barcode, its digits unconfirmed)
    for reads in ([old], [old, old, old]):
        v = consensus(reads)
        assert v.status == "needs_review" and v.grader == "PSA" and "one printed barcode only" in v.note
        assert not psa_itf_confirmed(reads, "2074012")
    # ... even if the batch asked for one source only: the ITF rule wants its digits confirmed, not a count
    assert consensus([old], min_sources=1).status == "needs_review"
    # OCR that reads other digits: needs_review; OCR alone: needs_review, grader unknown (the exception pocket)
    v = consensus([old, _ocr("02074013")])
    assert v.status == "needs_review" and "OCR read 2074013" in v.note
    v = consensus([_ocr("02074012")])
    assert v.status == "needs_review" and v.grader == "unknown"
    # a second printed symbol in no grader's format does NOT confirm it: a bare-number QR, a Code39, an EAN-8, a
    # Codabar or a keyed 'Cert #' QR of the same cert is on no PSA label (the same rule as a bare-number QR beside a
    # Code128). A PSA-format second symbol is two printed symbols (below); another grader's is a conflict (last line).
    for second in (_r("2074012", "back_qr", raw="2074012", grader="unknown"), _r("2074012", "back_barcode", "Code39", raw="2074012", grader="unknown"),
                   _r("2074012", "back_barcode", "EAN8", raw="02074012", grader="unknown"), _r("2074012", "back_barcode", "Codabar", raw="02074012", grader="unknown"),
                   _r("2074012", "back_qr", raw="Cert #02074012", grader="unknown"), _r("2074012", "back_qr", "DataMatrix", raw="02074012", grader="unknown")):
        v = consensus([old, second])
        assert v.status == "needs_review" and v.grader == "PSA" and "grader PSA not confirmed" in v.note, second
        assert not psa_itf_confirmed([old, second], "2074012"), second
        # ... and with OCR agreeing as well it is the ITF + OCR rule, as without the second symbol
        v = consensus([old, second, _ocr("02074012")])
        assert v.status == "ok" and v.grader == "PSA" and "grader PSA from its 8-digit ITF" in v.note, second
    # ... and two ITFs (a 2016 label, back + front) were already two printed symbols in PSA's format
    v = consensus([_itf("25656882", "back_barcode"), _itf("25656882")])
    assert v.status == "ok" and "8-digit ITF" not in v.note
    # an ITF of any other length is a misread: it never parses, so it confirms nothing and names nothing
    for raw in ("2074012", "289412", "123456789", "0148069831", "00000000"):
        assert parse_payload(raw, "ITF") is None, raw
    # a read typed PSA some other way (not the ITF-8 rule) gets nothing from it: here a 7-digit ITF built by hand
    odd = CodeRead("2074012", "front_barcode", "ITF", "2074012", "front", "PSA")
    v = consensus([odd, _ocr("02074012")])
    assert v.status == "needs_review" and "grader PSA not confirmed" in v.note
    # the rule is ITF's only: one Code128 with OCR agreeing stays needs_review, PSA or CGC
    for c128 in (_r("100423658", "front_barcode", "Code128"), _r("6003997046", "front_barcode", "Code128", grader="CGC")):
        v = consensus([c128, _ocr(c128.cert)])
        assert v.status == "needs_review" and f"grader {c128.grader} not confirmed" in v.note
    # a CGC code beside the ITF with the same number is two graders: a conflict, as before
    assert consensus([old, _r("2074012", "back_qr", raw="https://www.cgccards.com/certlookup/2074012/", grader="CGC"), _ocr("02074012")]).status == "conflict"
