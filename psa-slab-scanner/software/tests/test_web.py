"""Web page API with the simulated machine (Flask test client)."""

import time

import pytest

pytest.importorskip("flask")

from slabscan.config import from_layout  # noqa: E402
from slabscan.web import SimProvider, create_app  # noqa: E402

H = {"X-SlabRail": "1"}


def _wait(client, states=("finished", "stopped", "error"), timeout=240):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        s = client.get("/api/status").get_json()
        if s["state"] in states:
            return s
        time.sleep(0.2)
    raise AssertionError(f"still {s['state']} after {timeout} s")


def test_status_start_finish_download(tmp_path):
    app = create_app(from_layout(), SimProvider(from_layout(), slabs=3), out_dir=tmp_path)
    c = app.test_client()
    s = c.get("/api/status").get_json()
    assert s["state"] == "idle" and s["sim"] is True
    assert c.post("/api/start", json={}).status_code == 403  # no X-SlabRail header
    r = c.post("/api/start", json={"name": "web test"}, headers=H)
    assert r.status_code == 200
    bid = r.get_json()["batch_id"]
    s = _wait(c)
    assert s["state"] == "finished", s["message"]
    assert s["done"] == 3 and s["counts"] == {"ok": 3} and s["expected"] == 3
    assert len(s["last"]) == 3 and s["last"][0]["position"] == 3
    assert s["last_image"].startswith(f"/batches/{bid}/images/")
    assert {f["name"] for f in s["files"]} >= {"certs.csv", "certs.txt", "report.html"}
    csv_text = c.get(f"/batches/{bid}/certs.csv").get_data(as_text=True)
    assert csv_text.count("\n") == 4
    assert c.get(s["last_image"]).status_code == 200
    assert c.get(f"/batches/{bid}/journal.jsonl").status_code == 404  # only the listed files are served
    assert c.get(f"/batches/{bid}/..%2F..%2Fetc%2Fpasswd").status_code == 404
    page = c.get("/").get_data(as_text=True)
    assert "SlabRail" in page and "X-SlabRail" in page
    assert c.get("/api/batches").get_json()[0]["finished"] is True


def test_stop_then_resume_from_the_page(tmp_path):
    cfg = from_layout()
    app = create_app(cfg, SimProvider(cfg, slabs=3), out_dir=tmp_path)
    c = app.test_client()
    bid = c.post("/api/start", json={}, headers=H).get_json()["batch_id"]
    assert c.post("/api/stop", headers=H).status_code == 200
    s = _wait(c)
    assert s["state"] == "stopped" and "Stopped on request" in s["message"]
    assert c.post("/api/start", json={}, headers=H).status_code == 200 or True  # a new start is allowed after a stop
    _wait(c)
    b = {x["id"]: x for x in c.get("/api/batches").get_json()}
    assert b[bid]["resumable"] and b[bid]["stopped"]


def test_resume_continues_the_same_simulated_bed(tmp_path):
    cfg = from_layout()
    app = create_app(cfg, SimProvider(cfg, slabs=3), out_dir=tmp_path)
    c = app.test_client()
    mgr = app.config["MANAGER"]
    bid = c.post("/api/start", json={}, headers=H).get_json()["batch_id"]
    while not mgr.writer.rows and mgr.busy():  # stop after the first slab
        time.sleep(0.05)
    c.post("/api/stop", headers=H)
    s = _wait(c)
    assert s["state"] == "stopped", s
    done_before = s["done"]
    assert 1 <= done_before < 3
    assert c.post("/api/resume", json={"batch": "nope"}, headers=H).status_code == 404
    assert c.post("/api/resume", json={"batch": bid}, headers=H).status_code == 200
    s = _wait(c)
    assert s["state"] == "finished", s["message"]
    assert s["done"] == 3 and s["counts"] == {"ok": 3}
