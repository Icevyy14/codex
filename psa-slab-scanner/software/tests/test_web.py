"""Web page API with the simulated machine (Flask test client)."""

import time

import pytest

pytest.importorskip("flask")

import dataclasses  # noqa: E402

from slabscan.config import from_layout as _layout  # noqa: E402
from slabscan.web import SimProvider, create_app  # noqa: E402


def from_layout():
    """The simulated mix includes older labels without a back QR; the face-down check would stop on each."""
    return dataclasses.replace(_layout(), face_down_check="off")

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
    b = {x["id"]: x for x in c.get("/api/batches").get_json()}
    assert b[bid]["resumable"] and "Stopped on request" in b[bid]["stopped"]
    time.sleep(1.1)  # batch ids have 1 s resolution
    r = c.post("/api/start", json={}, headers=H)  # a fresh start is allowed after a stop (new simulated load)
    assert r.status_code == 200 and r.get_json()["batch_id"] != bid
    assert c.post("/api/start", json={}, headers=H).status_code == 409  # but not while one is running
    assert _wait(c)["state"] == "finished"


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


def test_estop_shows_the_stop_message_and_resume_rehomes(tmp_path):
    """E-stop mid-run (the controller's serial port vanishes): the page shows a clean Stop with what to do;
    Resume on the same (kept-open) machine homes first and finishes every slab once."""
    from slabscan.motion import ControllerLost

    cfg = from_layout()

    class EStopProvider(SimProvider):
        def get(self, fresh):
            hw = super().get(fresh)
            if fresh:
                inner, world = hw.motion, hw.world

                class Cut:
                    fired = False

                    def __getattr__(self, name):
                        return getattr(inner, name)

                    def move(self, feed, **kw):
                        if not Cut.fired and world.held and mgr.writer.rows:
                            Cut.fired = True
                            inner.homed = False
                            raise ControllerLost("Lost the controller: its USB serial port went away (E-stop, test)")
                        inner.move(feed, **kw)

                hw.motion = Cut()
            return hw

    provider = EStopProvider(cfg, slabs=3)
    app = create_app(cfg, provider, out_dir=tmp_path)
    mgr = app.config["MANAGER"]
    c = app.test_client()
    bid = c.post("/api/start", json={}, headers=H).get_json()["batch_id"]
    s = _wait(c)
    assert s["state"] == "stopped" and "lost power" in s["message"] and "homes first" in s["message"], s["message"]
    world = provider.hw.world
    assert world.held  # the slab is still on the cup; the message names its pocket
    src = int(s["message"].split("A slab from pocket ")[1].split()[0])
    assert s["slab_on_cup"] == f"pocket {src}" and world.vacuum_on  # the pump keeps holding it; the page offers Vent
    r = c.post("/api/resume", json={"batch": bid}, headers=H)
    assert r.status_code == 409 and "slab is on the cup" in r.get_json()["error"]  # not before the cup is cleared
    for slab in reversed(world.held):  # operator holds it, presses Vent, puts it back face-down on that pocket
        world.stacks[src].append(slab)
    world.held, world.gripping = [], False
    assert c.post("/api/vent", headers=H).status_code == 200 and not world.vacuum_on
    assert c.get("/api/status").get_json()["slab_on_cup"] is None
    assert c.post("/api/resume", json={"batch": bid}, headers=H).status_code == 200
    s = _wait(c)
    assert s["state"] == "finished", s["message"]
    assert s["done"] == 3 and s["counts"] == {"ok": 3}


def test_web_refuses_an_uncalibrated_machine_and_reloads_the_config(tmp_path):
    """software-10: the web page started runs on an uncalibrated machine and kept the config it booted with."""
    from slabscan.config import write_overrides

    cfg = from_layout()
    cal = tmp_path / "calibration.toml"
    loads = []

    def reload():
        loads.append(1)
        return from_layout()

    app = create_app(cfg, SimProvider(cfg, slabs=2), out_dir=tmp_path / "batches", reload=reload, cal_path=cal)
    c = app.test_client()
    r = c.post("/api/start", json={}, headers=H)
    assert r.status_code == 409 and "calibrate z" in r.get_json()["error"]
    write_overrides(cal, {"pad_trigger_c": 0.0, "offset_x": 0.0})
    assert c.post("/api/start", json={}, headers=H).status_code == 200
    assert _wait(c)["state"] == "finished" and loads == [1]


def test_start_all_face_down_runs_through_slabs_without_a_back_qr(tmp_path):
    cfg = _layout()  # face-down check on, and the simulated mix has older labels without a back QR
    assert cfg.face_down_check == "stop"
    app = create_app(cfg, SimProvider(cfg, slabs=12), out_dir=tmp_path)
    c = app.test_client()
    bid = c.post("/api/start", json={"all_face_down": True}, headers=H).get_json()["batch_id"]
    s = _wait(c)
    assert s["state"] == "finished", s["message"]
    assert (tmp_path / bid / "run.json").read_text().count('"face_down_check": "off"') == 1
