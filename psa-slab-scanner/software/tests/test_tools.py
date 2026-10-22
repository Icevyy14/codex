"""tools.gen_config round-trip and tools.enrich (PSA API mocked - never touches the network)."""

import csv
import dataclasses
import io
import json
import urllib.error

import pytest

from slabscan import psa_api
from slabscan.config import dumps, from_layout, load, write_overrides
from tools import enrich, gen_config


def test_gen_config_round_trip(tmp_path):
    out = tmp_path / "machine.toml"
    assert gen_config.main(["--out", str(out)]) == 0
    cfg = load(out)
    assert gen_config.differences(from_layout(), cfg) == []
    assert cfg.accepted_graders == ("PSA", "CGC") and isinstance(cfg.station_xy, tuple)
    assert gen_config.main(["--out", str(out), "--check"]) == 0
    out.write_text(out.read_text().replace("stack_max = 30", "stack_max = 25"))
    assert gen_config.main(["--out", str(out), "--check"]) == 1


def test_committed_machine_toml_matches_layout():
    assert gen_config.main(["--check"]) == 0, "config/machine.toml is stale: run python -m tools.gen_config"


def test_toml_writer_escapes_strings(tmp_path):
    cfg = dataclasses.replace(from_layout(), custom_regex=r'cert[:=]"?(\d{9})', accepted_graders=("PSA", "CGC", "TAG"))
    (tmp_path / "m.toml").write_text(dumps(cfg))
    back = load(tmp_path / "m.toml")
    assert back.custom_regex == cfg.custom_regex and back.accepted_graders == ("PSA", "CGC", "TAG")


def test_calibration_overrides(tmp_path):
    m = tmp_path / "machine.toml"
    gen_config.main(["--out", str(m)])
    cal = tmp_path / "calibration.toml"
    write_overrides(cal, {"pad_trigger_c": -2.125, "offset_x": 1.5}, "test")
    write_overrides(cal, {"cam_station": {"type": "picamera", "index": 0, "lens_position": 7.25}})
    cfg = load(m, cal)
    assert (cfg.pad_trigger_c, cfg.offset_x, cfg.cam_station["lens_position"]) == (-2.125, 1.5, 7.25)
    with pytest.raises(ValueError):
        write_overrides(cal, {"pad_triger_c": 1.0})
    cal.write_text(cal.read_text() + "\nofset_x = 2\n")
    with pytest.raises(ValueError, match="ofset_x"):
        load(m, cal)


# ---------------------------------------------------------------------- enrich
def _batch(tmp_path):
    d = tmp_path / "b1"
    d.mkdir()
    rows = [
        {"batch_id": "b1", "position": 1, "cert": "148069831", "grader": "PSA", "status": "ok"},
        {"batch_id": "b1", "position": 2, "cert": "4123456001", "grader": "CGC", "status": "ok"},
        {"batch_id": "b1", "position": 3, "cert": "45210987", "grader": "PSA", "status": "ok"},
        {"batch_id": "b1", "position": 4, "cert": "", "grader": "PSA", "status": "no_read"},
        {"batch_id": "b1", "position": 5, "cert": "102938475", "grader": "PSA", "status": "ok"},
    ]
    with (d / "certs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return d


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(behaviour):
    calls = []

    def urlopen(req, timeout=20):
        cert = req.full_url.rsplit("/", 1)[-1]
        calls.append(cert)
        b = behaviour(cert, len(calls))
        if isinstance(b, int):
            raise urllib.error.HTTPError(req.full_url, b, "err", {}, io.BytesIO(b"{}"))
        return _Resp(json.dumps(b).encode())

    return urlopen, calls


def _ok(cert):
    return {"PSACert": {"CertNumber": cert, "Year": "2023", "Brand": "POKEMON SV151", "Subject": "CHARIZARD EX", "CardGrade": "GEM MT 10"},
            "IsValidRequest": True, "ServerMessage": "Request successful"}


def _read(d):
    return {r["position"]: r for r in csv.DictReader((d / "certs_enriched.csv").open())}


def test_enrich_ok_not_found_and_cache(tmp_path, monkeypatch):
    d = _batch(tmp_path)
    urlopen, calls = _fake_urlopen(lambda cert, n: _ok(cert) if cert != "45210987" else {"IsValidRequest": True, "ServerMessage": "No data found"})
    monkeypatch.setattr(psa_api.urllib.request, "urlopen", urlopen)
    s = enrich.enrich(d, token="t", interval_s=0, log=lambda *_: None)
    rows = _read(d)
    assert rows["1"]["enrich_status"] == "ok" and rows["1"]["psa_Subject"] == "CHARIZARD EX"
    assert rows["2"]["enrich_status"] == "skipped" and "CGC" in rows["2"]["enrich_note"]  # PSA API can't look up CGC
    assert rows["3"]["enrich_status"] == "not_found"
    assert rows["4"]["enrich_status"] == "skipped"
    assert s["api_calls"] == 3 and not s["blocked"]
    enrich.enrich(d, token="t", interval_s=0, log=lambda *_: None)
    assert len(calls) == 3  # second run: everything from the cache


def test_enrich_not_approved_stops_cleanly(tmp_path, monkeypatch):
    d = _batch(tmp_path)
    urlopen, calls = _fake_urlopen(lambda cert, n: _ok(cert) if n == 1 else 403)
    monkeypatch.setattr(psa_api.urllib.request, "urlopen", urlopen)
    s = enrich.enrich(d, token="t", interval_s=0, log=lambda *_: None)
    rows = _read(d)
    assert rows["1"]["enrich_status"] == "ok"
    assert rows["3"]["enrich_status"] == "pending" and "collectors-apis@collectors.com" in rows["3"]["enrich_note"]
    assert rows["5"]["enrich_status"] == "pending"
    assert len(calls) == 2 and "approved" in s["blocked"]


def test_enrich_daily_quota_and_resume_next_day(tmp_path, monkeypatch):
    d = _batch(tmp_path)
    urlopen, calls = _fake_urlopen(lambda cert, n: _ok(cert))
    monkeypatch.setattr(psa_api.urllib.request, "urlopen", urlopen)
    s = enrich.enrich(d, token="t", daily_limit=2, interval_s=0, log=lambda *_: None)
    assert s["counts"] == {"ok": 2, "pending": 1} and "quota" in s["blocked"]
    assert enrich.main([str(d), "--token", "t", "--daily-limit", "2", "--interval", "0"]) == 1  # still blocked today, nothing called
    assert len(calls) == 2
    s = enrich.enrich(d, token="t", daily_limit=3, interval_s=0, log=lambda *_: None)  # "tomorrow": more budget
    assert s["counts"] == {"ok": 3} and len(calls) == 3


def test_enrich_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("PSA_API_TOKEN", raising=False)
    d = _batch(tmp_path)
    s = enrich.enrich(d, token=None, interval_s=0, log=lambda *_: None)
    assert "PSA_API_TOKEN" in s["blocked"] and s["counts"] == {"pending": 3}
    assert (d / "certs_enriched.csv").exists()


def test_ocr_skips_frames_with_nothing_printed():
    """Regression: tesseract --psm 11 on a blank, noisy frame ran for ~100 s and found nothing."""
    import time

    import numpy as np

    from slabscan.decode import ocr_digits

    blank = np.clip(40 + np.random.default_rng(1).normal(0, 2.0, (900, 1800)), 0, 255).astype(np.uint8)
    t0 = time.monotonic()
    assert ocr_digits(blank, "back") == []
    assert time.monotonic() - t0 < 2.0
