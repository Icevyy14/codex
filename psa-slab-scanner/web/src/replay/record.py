"""Record a simulated SlabRail batch for the animated replay: every head move, every slab pick/place,
every read result, on the simulator's own clock (trapezoid motion model + camera/vacuum dwell)."""

import json
import sys
from pathlib import Path

SW = Path(sys.argv[1])  # .../psa-slab-scanner/software of the commit to run
sys.path.insert(0, str(SW))

from slabscan import simworld  # noqa: E402
from slabscan.cli import execute_batch  # noqa: E402
from slabscan.config import from_layout  # noqa: E402
from slabscan.factory import sim_hardware, sim_stacks  # noqa: E402
from slabscan.ops import ScriptedConsole  # noqa: E402
from slabscan.results import BatchWriter  # noqa: E402

N = int(sys.argv[2]) if len(sys.argv) > 2 else 330
OUT = Path(sys.argv[3])
DWELL = {"head": 0.25, "station": 0.35, "hold": 0.4, "release": 0.3}


class Clock:
    t = 0.0


rec = {"frames": [], "events": []}


def snap(w):
    rec["frames"].append([round(Clock.t, 3), round(w.x, 1), round(w.z, 2), [s.cert for s in w.held]])


def stacks_of(w):
    return {str(k): [s.cert for s in v] for k, v in w.stacks.items()}


class RecMotion(simworld.SimMotion):
    def _account(self, dist, feed, axis="x"):
        before = self.move_time_s
        super()._account(dist, feed, axis)
        Clock.t += self.move_time_s - before

    def move(self, feed, x=None, y=None, z=None):
        n0 = sum(len(v) for v in self.w.stacks.values())
        super().move(feed, x=x, y=y, z=z)
        snap(self.w)
        if sum(len(v) for v in self.w.stacks.values()) != n0:
            rec["events"].append({"t": round(Clock.t, 3), "type": "stacks", "stacks": stacks_of(self.w)})

    def probe(self, z_target, feed):
        r = super().probe(z_target, feed)
        snap(self.w)
        return r

    def home(self):
        super().home()
        snap(self.w)


cfg = from_layout()
cfg = type(cfg)(**{**cfg.__dict__, "face_down_check": "off"}) if hasattr(cfg, "face_down_check") else cfg
stacks = sim_stacks(cfg, N, seed=7, eras=(0.85, 0.1, 0.05), clingy_rate=0.01, thick_rate=0.02)
hw = sim_hardware(cfg, stacks=stacks)
w = hw.world
hw.motion = RecMotion(w, x_offset=cfg.offset_x, z_offset=cfg.pad_trigger_c)

for cam in (hw.head_cam, hw.station_cam):
    orig = cam.capture

    def cap(orig=orig, role=cam.role):
        Clock.t += DWELL[role]
        rec["events"].append({"t": round(Clock.t, 3), "type": "photo", "camera": role})
        return orig()

    cam.capture = cap

vac = hw.vacuum
for name in ("hold", "release"):
    orig = getattr(vac, name)

    def wrapped(orig=orig, name=name):
        Clock.t += DWELL[name]
        snap(w)
        rec["events"].append({"t": round(Clock.t, 3), "type": name})
        r = orig()
        snap(w)
        return r

    setattr(vac, name, wrapped)

OUT.mkdir(parents=True, exist_ok=True)
writer = BatchWriter(OUT, "replay")
orig_add = writer.add


def add(res, *a, **k):
    r = orig_add(res, *a, **k)
    v = res.verdict
    rec["events"].append({"t": round(Clock.t, 3), "type": "read", "position": res.position, "source_pocket": res.source_pocket,
                          "out_pocket": res.out_pocket, "out_index": res.out_index, "cert": v.cert, "grader": v.grader,
                          "status": v.status, "sources": "+".join(v.sources), "note": v.note})
    return r


writer.add = add
initial = stacks_of(w)
slab_info = {s.cert: {"era": s.era, "grader": s.grader, "t": round(s.thickness, 2)} for v in w.stacks.values() for s in v}
con = ScriptedConsole([])
code, summary, msg = execute_batch(cfg, hw, writer, con)
print("exit", code, msg)
data = {
    "pockets": [{"index": p.index, "x": p.x, "role": p.role} for p in cfg.pockets],
    "station_x": cfg.station_xy[0], "post_h": cfg.post_h, "c_safe_loaded": cfg.c_safe_loaded, "c_safe_empty": cfg.c_safe_empty,
    "initial": initial, "slabs": slab_info, "frames": rec["frames"], "events": rec["events"],
    "summary": {k: summary.get(k) for k in ("status_counts", "slabs_visited")} if summary else None,
    "total_s": round(Clock.t, 1),
}
(OUT / "replay.json").write_text(json.dumps(data, separators=(",", ":")))
print("frames", len(rec["frames"]), "events", len(rec["events"]), "sim seconds", round(Clock.t), "json KB", (OUT / "replay.json").stat().st_size // 1024)
