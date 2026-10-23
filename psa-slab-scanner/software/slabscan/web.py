"""Phone-friendly web page: start / stop / resume a run, live progress, downloads.

    python -m slabscan web [--port 8080]          (python -m slabscan web --sim  to try it without hardware)

It binds 0.0.0.0 and has NO LOGIN: anyone on the same network can start the machine. Use it on
your own home/shop LAN only, never port-forward it. POSTs need an ``X-SlabRail: 1`` header (the
page sends it), which stops other web pages in your browser from starting the machine behind
your back, but it is not a password.

One run at a time, in a background thread. Stop = finish the current slab, park with nothing in
the cup, then halt (the same as Ctrl-C once on the command line). If a stop leaves a slab on the
cup, the machine stays open with the pump holding it, and the page offers Vent (hold the slab first).
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from collections import Counter, deque
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

from .config import Config
from .ops import Console
from .results import BatchWriter
from .runner import FACE_DOWN_OK_REFUSED, NOMINAL_T, last_face_down_stop, read_journal

_BATCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_FILE_RE = re.compile(r"^(certs\.csv|certs\.txt|certs_enriched\.csv|report\.html|summary\.json|images/[A-Za-z0-9_.-]+\.jpg)$")


# ---------------------------------------------------------------------- hardware providers
class RealProvider:
    """Opens the real machine once and keeps it open between runs (opening the serial port resets the controller)."""

    sim = False

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.hw = None

    def get(self, fresh: bool):
        from .factory import open_hardware

        if self.hw is None:
            self.hw = open_hardware(self.cfg)
        return self.hw

    def invalidate(self) -> None:
        if self.hw is not None:
            self.hw.close()
        self.hw = None


class SimProvider:
    """A simulated machine. A new start loads a fresh batch of slabs; resume keeps the same simulated bed."""

    sim = True

    def __init__(self, cfg: Config, slabs: int = 22, seed: int = 7, **batch_kw):
        self.cfg = cfg
        self.slabs = slabs
        self.seed = seed
        self.batch_kw = batch_kw  # factory.sim_stacks options, e.g. mix
        self.hw = None
        self.loads = 0

    def get(self, fresh: bool):
        from .factory import sim_hardware

        if fresh or self.hw is None:
            self.loads += 1
            self.hw = sim_hardware(self.cfg, slabs=self.slabs, seed=self.seed + self.loads, **self.batch_kw)
        return self.hw

    def invalidate(self) -> None:
        self.hw = None


# ---------------------------------------------------------------------- run manager
class RunManager:
    def __init__(self, cfg: Config, provider, out_dir: Path | None = None, reload=None, cal_path: Path | None = None):
        self.cfg = cfg
        self.provider = provider
        self.reload = reload  # () -> Config: machine.toml + calibration.toml read again on every start/resume
        self.cal_path = cal_path  # refuse to start/resume until calibrate z and x are in it (real machine)
        self.out_dir = Path(out_dir or cfg.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.stop_flag = threading.Event()
        self.state = "idle"  # idle | running | stopping | finished | stopped | error
        self.message = ""
        self.writer: BatchWriter | None = None
        self.runner = None
        self.summary: dict | None = None
        self.started: float | None = None
        self.ended: float | None = None
        self.log: deque[str] = deque(maxlen=300)

    def _log(self, line: str) -> None:
        self.log.append(time.strftime("%H:%M:%S ") + line)

    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def _fresh_cfg(self) -> Config:
        from .cli import CALIBRATION_MISSING, is_calibrated

        if self.cal_path is not None and not is_calibrated(self.cal_path):
            raise RuntimeError(CALIBRATION_MISSING.format(cal=self.cal_path))
        if self.reload is not None:
            self.cfg = self.reload()
            self.provider.cfg = self.cfg
        if self.slab_on_cup():
            raise RuntimeError(f"A slab is on the cup (from {self.slab_on_cup()}): hold it, press Vent, put it back on its stack first.")
        return self.cfg

    def slab_on_cup(self) -> str | None:
        r = self.runner
        return r.slab_on_cup if (r is not None and not self.busy()) else None

    def vent(self) -> str:
        """The operator holds the slab left on the cup; let it go."""
        with self.lock:
            if self.busy():
                raise RuntimeError("the machine is running")
            r = self.runner
            where = r.slab_on_cup if r is not None else None
            hw = getattr(self.provider, "hw", None)
            if not where or hw is None or hw.vacuum is None:
                raise RuntimeError("nothing to vent")
            if r.freeze == "vent_failed":
                raise RuntimeError("The vent valve failed: pull the vacuum tube off the cup fitting by hand (the slab rests on its stack).")
            hw.vacuum.release()
            r.holding, r.held_from = False, None
            if r.freeze == "hold":
                r.freeze = None
            self._log(f"vented the cup (slab from {where}): put it face-down on top of the pocket it came from")
            if self.state == "error":
                self.provider.invalidate()
            return where

    def start(self, name: str | None = None, front_photo: str | None = None, all_face_down: bool = False) -> str:
        import dataclasses

        from .cli import new_batch_id

        with self.lock:
            if self.busy():
                raise RuntimeError("a run is already going")
            base = self._fresh_cfg()
            cfg = dataclasses.replace(base, front_photo=front_photo) if front_photo in ("always", "fallback") else base
            if all_face_down:
                cfg = dataclasses.replace(cfg, face_down_check="off")
            writer = BatchWriter(self.out_dir, new_batch_id(name, "sim-" if self.provider.sim else ""))
            (writer.dir / "run.json").write_text(json.dumps({"name": name, "front_photo": cfg.front_photo, "face_down_check": cfg.face_down_check,
                                                             "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                                             "sim": self.provider.sim, "via": "web"}, indent=2))
            self._launch(cfg, writer, resume=False, fresh=True)
            return writer.batch_id

    def resume(self, batch_id: str, accept_heights: bool = False, face_down_ok: bool = False) -> str:
        import dataclasses

        from .cli import run_options

        if not _BATCH_RE.match(batch_id or "") or not (self.out_dir / batch_id / "journal.jsonl").exists():
            raise ValueError(f"no such batch: {batch_id}")
        opts = run_options(self.out_dir / batch_id)
        if face_down_ok and last_face_down_stop(read_journal(self.out_dir / batch_id / "journal.jsonl")) is None:
            raise RuntimeError(FACE_DOWN_OK_REFUSED)
        with self.lock:
            if self.busy():
                raise RuntimeError("a run is already going")
            base = self._fresh_cfg()
            cfg = dataclasses.replace(base, front_photo=opts["front_photo"]) if opts.get("front_photo") in ("always", "fallback") else base
            if opts.get("face_down_check") in ("learned", "stop", "off"):
                cfg = dataclasses.replace(cfg, face_down_check=opts["face_down_check"])  # a batch keeps the choice it was started with
            writer = BatchWriter.reopen(self.out_dir / batch_id)
            self._launch(cfg, writer, resume=True, fresh=False, accept_heights=accept_heights, face_down_ok=face_down_ok)
            return batch_id

    def stop(self) -> None:
        if self.busy():
            self.stop_flag.set()
            self.state = "stopping"
            self._log("stop requested: finishing the current slab")

    def _launch(self, cfg, writer, resume, fresh, accept_heights=False, face_down_ok=False) -> None:
        self.stop_flag.clear()
        self.writer, self.summary, self.message, self.runner = writer, None, "", None
        self.state = "running"
        self.started, self.ended = time.time(), None
        self._log(("resuming " if resume else "starting ") + writer.batch_id)
        self.thread = threading.Thread(target=self._work, args=(cfg, writer, resume, fresh, accept_heights, face_down_ok), daemon=True, name="slabrail-run")
        self.thread.start()

    def _work(self, cfg, writer, resume, fresh, accept_heights, face_down_ok=False) -> None:
        from . import cli

        con = Console(out=self._log)
        try:
            hw = self.provider.get(fresh)
        except Exception as e:  # noqa: BLE001
            self.state, self.message, self.ended = "error", f"Could not open the machine: {e}", time.time()
            cli.write_stop(writer.dir, self.message, "error")
            self.provider.invalidate()
            return
        try:
            code, summary, msg = cli.execute_batch(cfg, hw, writer, con, resume=resume, accept_heights=accept_heights, stop_flag=self.stop_flag,
                                                   on_runner=lambda r: setattr(self, "runner", r), cal_path=self.cal_path, face_down_ok=face_down_ok,
                                                   refs_path=None if self.provider.sim else cli.card_backs_path(self.cal_path))
        except Exception as e:  # noqa: BLE001 - never let the worker thread die silently
            code, summary, msg = 1, None, f"{type(e).__name__}: {e}"
        self.ended = time.time()
        if code == 0:
            self.state, self.summary = "finished", summary
            self._log(f"finished: {summary['slabs_visited']} slabs")
        elif code == 2:
            self.state, self.message = "stopped", msg
            self._log("STOPPED: " + msg)
        else:
            self.state, self.message = "error", msg
            self._log("ERROR: " + msg)
            if not (self.runner is not None and self.runner.slab_on_cup):
                self.provider.invalidate()  # with a slab on the cup the pump must keep running: closed after Vent

    # status
    def status(self) -> dict:
        w, r = self.writer, self.runner
        rows = w.rows if w else []
        counts = Counter(x.verdict.status for x in rows)
        bid = w.batch_id if w else None
        expected = None
        if r is not None and r.st.survey_tops:
            expected = sum(round(r.st.survey_tops.get(p.index, 0.0) / NOMINAL_T) for p in self.cfg.sources)
        timings = list(r.timings) if r is not None else []
        mean = sum(timings) / len(timings) if timings else None
        eta = (max(0, expected - len(rows)) * mean) if (expected is not None and mean and self.state in ("running", "stopping")) else None
        last = []
        img = None
        for x in reversed(rows[-10:]):
            v = x.verdict
            pic = x.image_back or x.image_front
            last.append({"position": x.position, "cert": v.cert or "", "grader": v.grader, "status": v.status, "out_pocket": x.out_pocket,
                         "out_index": x.out_index, "note": v.note, "image": f"/batches/{bid}/{pic}" if pic else ""})
        for x in reversed(rows):
            pic = x.image_back or x.image_front
            if pic:
                img = f"/batches/{bid}/{pic}"
                break
        files = [f for f in ("certs.csv", "certs.txt", "report.html", "summary.json", "certs_enriched.csv") if w and (w.dir / f).exists()]
        return {
            "state": self.state,
            "sim": bool(self.provider.sim),
            "batch_id": bid,
            "message": self.message,
            "phase": r.phase if r is not None else None,
            "current": {"src": r.current[0], "dst": r.current[1]} if (r is not None and r.current) else None,
            "done": len(rows),
            "expected": expected,
            "counts": dict(counts),
            "last": last,
            "last_image": img,
            "started": self.started,
            "elapsed_s": round((self.ended or time.time()) - self.started, 1) if self.started else None,
            "mean_cycle_s": round(mean, 2) if mean else None,
            "eta_s": round(eta) if eta is not None else None,
            "summary": self.summary,
            "slab_on_cup": self.slab_on_cup(),
            "files": [{"name": f, "url": f"/batches/{bid}/{f}"} for f in files],
            "log": list(self.log)[-15:],
        }

    def batches(self) -> list[dict]:
        out = []
        for d in sorted((p for p in self.out_dir.iterdir() if p.is_dir() and _BATCH_RE.match(p.name)), key=lambda p: p.name, reverse=True)[:50]:
            csvp = d / "certs.csv"
            n = max(0, sum(1 for _ in csvp.open()) - 1) if csvp.exists() else 0
            stop = d / "stop.json"
            msg = json.loads(stop.read_text()).get("message", "") if stop.exists() else ""
            finished = (d / "summary.json").exists() and not stop.exists()
            resumable = (d / "journal.jsonl").exists() and not finished
            out.append({"id": d.name, "slabs": n, "finished": finished, "stopped": msg, "resumable": resumable,
                        "face_down_stop": last_face_down_stop(read_journal(d / "journal.jsonl")) if resumable else None,
                        "files": [f for f in ("certs.csv", "certs.txt", "report.html", "certs_enriched.csv") if (d / f).exists()]})
        return out


# ---------------------------------------------------------------------- app
def create_app(cfg: Config, provider, out_dir: Path | None = None, reload=None, cal_path: Path | None = None) -> Flask:
    app = Flask(__name__)
    mgr = RunManager(cfg, provider, out_dir, reload=reload, cal_path=cal_path)
    app.config["MANAGER"] = mgr

    def guard():
        if request.headers.get("X-SlabRail") != "1":
            abort(403, "missing X-SlabRail header")

    def body() -> dict:
        return request.get_json(silent=True) or request.form.to_dict() or {}

    @app.get("/")
    def index():
        return INDEX_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.get("/api/status")
    def api_status():
        return jsonify(mgr.status())

    @app.get("/api/batches")
    def api_batches():
        return jsonify(mgr.batches())

    @app.post("/api/start")
    def api_start():
        guard()
        b = body()
        try:
            bid = mgr.start((b.get("name") or "").strip() or None, b.get("front_photo") or None,
                            str(b.get("all_face_down", "")).lower() in ("1", "true", "on", "yes"))
        except RuntimeError as e:
            return jsonify(error=str(e)), 409
        return jsonify(ok=True, batch_id=bid)

    @app.post("/api/stop")
    def api_stop():
        guard()
        mgr.stop()
        return jsonify(ok=True)

    @app.post("/api/resume")
    def api_resume():
        guard()
        b = body()
        yes = lambda k: str(b.get(k, "")).lower() in ("1", "true", "on", "yes")  # noqa: E731
        try:
            bid = mgr.resume(b.get("batch", ""), yes("accept_heights"), yes("face_down_ok"))
        except ValueError as e:
            return jsonify(error=str(e)), 404
        except RuntimeError as e:
            return jsonify(error=str(e)), 409
        return jsonify(ok=True, batch_id=bid)

    @app.post("/api/vent")
    def api_vent():
        guard()
        try:
            where = mgr.vent()
        except RuntimeError as e:
            return jsonify(error=str(e)), 409
        return jsonify(ok=True, slab_from=where)

    @app.get("/batches/<batch_id>/<path:fname>")
    def batch_file(batch_id, fname):
        if not _BATCH_RE.match(batch_id) or not _FILE_RE.match(fname):
            abort(404)
        d = (mgr.out_dir / batch_id).resolve()
        if not d.is_dir():
            abort(404)
        return send_from_directory(str(d), fname, as_attachment=fname in ("certs.csv", "certs_enriched.csv"), max_age=0)

    return app


def lan_address() -> str:
    """This machine's LAN IP (no packet is sent), for the start-up message."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET-1: never routed, just picks the outgoing interface
            return s.getsockname()[0]
    except OSError:
        return socket.gethostname()


INDEX_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SlabRail</title>
<style>
:root{--bg:#f6f6f4;--card:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e2e2dc;--ok:#1d7a36;--warn:#9a6400;--bad:#b3261e;--accent:#2457c5}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1e1e1c;--ink:#ecece8;--mute:#a0a09a;--line:#33332f;--ok:#5cc47a;--warn:#e0a640;--bad:#ff7a70;--accent:#7aa2ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.4 system-ui,-apple-system,sans-serif}
main{max-width:720px;margin:0 auto;padding:12px 16px 40px}
h1{font-size:22px;margin:4px 0 12px;display:flex;gap:10px;align-items:center}
.badge{font-size:13px;padding:3px 10px;border-radius:99px;background:var(--line);text-transform:uppercase;letter-spacing:.04em}
.running,.stopping{background:var(--accent);color:#fff}.finished{background:var(--ok);color:#fff}.stopped,.error{background:var(--bad);color:#fff}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:0 0 12px}
.msg{border-color:var(--bad);color:var(--bad);font-weight:600;white-space:pre-wrap}
.big{font-size:30px;font-weight:700}.mute{color:var(--mute);font-size:14px}
.bar{height:10px;background:var(--line);border-radius:99px;overflow:hidden;margin:8px 0}.bar>div{height:100%;background:var(--accent);width:0}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.chip{border:1px solid var(--line);border-radius:99px;padding:2px 10px;font-size:14px}
.chip.ok{border-color:var(--ok);color:var(--ok)}.chip.bad{border-color:var(--bad);color:var(--bad)}
button,select,input{font:inherit;min-height:44px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);padding:0 12px}
button{font-weight:600;cursor:pointer}button.go{background:var(--ok);color:#fff;border:0}button.stop{background:var(--bad);color:#fff;border:0}
button:disabled{opacity:.45}
.row{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}.row>*{flex:1 1 140px}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:6px 4px;border-bottom:1px solid var(--line);vertical-align:top}
td.st-ok{color:var(--ok)}td.st-bad{color:var(--bad);font-weight:600}
img.label{width:100%;max-height:260px;object-fit:contain;border-radius:8px;background:#000}
a{color:var(--accent)}pre{white-space:pre-wrap;font-size:12px;color:var(--mute);margin:0}
.tablewrap{overflow-x:auto}
</style></head><body><main>
<h1>SlabRail <span id="state" class="badge">...</span><span id="sim" class="badge" hidden>SIM</span></h1>
<div id="msg" class="card msg" hidden></div>
<div id="cupcard" class="card msg" hidden><div id="cupmsg"></div><div class="row"><button class="stop" id="vent">I am holding the slab: Vent the cup</button></div></div>
<div class="card">
  <div class="big"><span id="done">0</span><span class="mute" id="of"></span></div>
  <div class="bar"><div id="bar"></div></div>
  <div class="mute" id="where"></div>
  <div class="chips" id="counts"></div>
  <div class="row" id="files"></div>
</div>
<div class="card" id="controls">
  <div class="row"><input id="name" placeholder="batch name (optional)" maxlength="40">
  <select id="fp"><option value="fallback">front photo: only when needed</option><option value="always">front photo: every slab (+3 s)</option></select></div>
  <label class="mute"><input type="checkbox" id="allfd" style="min-height:0"> I loaded every slab face-down: don't stop at slabs the face-down check can't confirm (no back-label code, no match with a known card back)</label>
  <div class="row"><button class="go" id="start">Start run</button><button class="stop" id="stop">Stop after this slab</button></div>
  <div class="row"><select id="resumeSel"></select><button id="resume">Resume</button></div>
  <label class="mute"><input type="checkbox" id="accept" style="min-height:0"> accept changed stack heights on resume</label>
  <label class="mute" id="facedownrow" hidden><input type="checkbox" id="facedown" style="min-height:0"> <span id="facedowntxt">the top slab it stopped on is face-down</span> (I checked; this one slab only)</label>
</div>
<div class="card" id="imgcard" hidden><div class="mute">last label</div><img class="label" id="img" alt="last label photo"></div>
<div class="card"><div class="mute">last 10 slabs</div><div class="tablewrap"><table><thead><tr><th>#</th><th>cert</th><th>status</th><th>now in</th></tr></thead><tbody id="rows"></tbody></table></div></div>
<div class="card"><div class="mute">batches</div><div id="batches"></div></div>
<div class="card"><div class="mute">log</div><pre id="log"></pre></div>
<p class="mute">LAN only, no login. Output: P = pocket, # = position counted from the bottom of that stack.</p>
</main><script>
const $=id=>document.getElementById(id);
function el(tag,txt,cls){const e=document.createElement(tag);if(txt!==undefined)e.textContent=txt;if(cls)e.className=cls;return e}
async function post(url,data){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-SlabRail':'1'},body:JSON.stringify(data||{})});
  const j=await r.json().catch(()=>({}));if(!r.ok)alert(j.error||('failed: '+r.status));refresh();return j}
function fmt(s){if(s==null)return '';s=Math.round(s);const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return h?`${h} h ${m} min`:`${m} min`}
async function refresh(){
  let s;try{s=await (await fetch('/api/status')).json()}catch(e){$('state').textContent='offline';return}
  $('state').textContent=s.state;$('state').className='badge '+s.state;$('sim').hidden=!s.sim;
  $('msg').hidden=!s.message;$('msg').textContent=s.message||'';
  $('cupcard').hidden=!s.slab_on_cup;$('cupmsg').textContent=s.slab_on_cup?`A slab is on the cup (from ${s.slab_on_cup}); the pump is holding it. Hold it with one hand, then press Vent, and put it face-down back on that stack.`:'';
  $('done').textContent=s.done;$('of').textContent=s.expected?` / ~${s.expected} slabs`:' slabs';
  $('bar').style.width=s.expected?Math.min(100,100*s.done/s.expected)+'%':'0';
  let w=[];if(s.batch_id)w.push('batch '+s.batch_id);if(s.phase==='survey')w.push('measuring the stacks');
  if(s.current)w.push(`pocket ${s.current.src} → pocket ${s.current.dst}`);if(s.mean_cycle_s)w.push(s.mean_cycle_s+' s/slab');
  if(s.eta_s!=null)w.push('about '+fmt(s.eta_s)+' left');if(s.elapsed_s&&s.state!=='running')w.push('took '+fmt(s.elapsed_s));
  $('where').textContent=w.join(' · ');
  const c=$('counts');c.replaceChildren();for(const[k,v]of Object.entries(s.counts))c.append(el('span',`${k} ${v}`,'chip '+(k==='ok'?'ok':'bad')));
  const f=$('files');f.replaceChildren();for(const x of s.files){const a=el('a',x.name);a.href=x.url;f.append(a)}
  const busy=s.state==='running'||s.state==='stopping';$('start').disabled=busy;$('resume').disabled=busy;$('stop').disabled=!busy;
  $('imgcard').hidden=!s.last_image;if(s.last_image&&$('img').dataset.src!==s.last_image){$('img').src=s.last_image;$('img').dataset.src=s.last_image}
  const tb=$('rows');tb.replaceChildren();for(const r of s.last){const tr=el('tr');tr.append(el('td',r.position),el('td',r.cert||'-'),
    el('td',r.status+(r.note?' · '+r.note:''),r.status==='ok'?'st-ok':'st-bad'),el('td',`P${r.out_pocket} #${r.out_index}`));tb.append(tr)}
  $('log').textContent=s.log.join('\n');
}
async function batches(){
  let b;try{b=await (await fetch('/api/batches')).json()}catch(e){return}
  const sel=$('resumeSel');const keep=sel.value;sel.replaceChildren();const box=$('batches');box.replaceChildren();
  fdstop={};for(const x of b){if(x.resumable){const o=el('option',`${x.id} (${x.slabs} done)`);o.value=x.id;sel.append(o);fdstop[x.id]=x.face_down_stop}
    const d=el('div');d.append(el('span',`${x.id} · ${x.slabs} slabs · ${x.finished?'finished':(x.stopped?'stopped':'not finished')} `));
    for(const f of x.files){const a=el('a',f+' ');a.href=`/batches/${x.id}/${f}`;d.append(a)}box.append(d)}
  if(!sel.options.length)sel.append(el('option','nothing to resume'));else if(keep)sel.value=keep;
  facedownRow();
}
let fdstop={};
function facedownRow(){const p=fdstop[$('resumeSel').value];const show=p!==undefined&&p!==null;$('facedownrow').hidden=!show;
  if(!show)$('facedown').checked=false;else $('facedowntxt').textContent=`the top slab of pocket ${p}, where the face-down check stopped, is face-down`}
$('resumeSel').onchange=()=>{$('facedown').checked=false;facedownRow()};
$('start').onclick=()=>{if(confirm('Slabs face-down, label toward you, pockets 0 and 12 empty, hands clear?'))post('/api/start',{name:$('name').value,front_photo:$('fp').value,all_face_down:$('allfd').checked})};
$('stop').onclick=()=>post('/api/stop');
$('resume').onclick=()=>{const v=$('resumeSel').value;const fd=$('facedown').checked&&!$('facedownrow').hidden;
  if(v&&confirm('Resume '+v+'? Hands clear?')){post('/api/resume',{batch:v,accept_heights:$('accept').checked,face_down_ok:fd});
    $('facedown').checked=false;$('accept').checked=false}};
$('vent').onclick=()=>{if(confirm('Are you holding the slab? It lets go when the cup vents.'))post('/api/vent')};
refresh();batches();setInterval(refresh,2000);setInterval(batches,10000);
</script></body></html>
"""
