"""Machine configuration (TOML). ``tools/gen_config.py`` writes config/machine.toml from the CAD layout;
calibration values are written to config/calibration.toml so a re-generation never loses them."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class PocketCfg:
    index: int
    x: float
    y: float
    role: str  # empty_start | source | exceptions


@dataclass
class Config:
    pockets: list[PocketCfg]
    station_xy: tuple[float, float]
    station_read_c: float
    c_safe_empty: float = 192.0
    c_safe_loaded: float = 199.0
    c_max: float = 210.0
    post_h: float = 182.0
    stack_max: int = 25
    max_line: float = 175.0
    # slab thickness classes (mm), measured as the placement contact step
    t_min: float = 6.0
    t_std_max: float = 7.9  # PSA standard 6.25-6.9, TAG ~7.25, CGC ~7.5
    t_thick_max: float = 11.5  # PSA thick holder ~10.25
    t_double: float = 11.6  # >= this step on placement = two slabs came together
    # motion (mm/min)
    feed_xy: float = 15000.0
    feed_z: float = 6000.0
    feed_probe: float = 1200.0
    feed_peel: float = 1200.0
    probe_window: float = 12.0  # must stay < buffer stroke (25)
    approach_gap: float = 5.0  # fast Z stops this far above the predicted contact
    max_surprise: float = 4.5  # |measured - predicted| above this aborts the stack
    peel_slow_mm: float = 1.0  # first mm of the lift at 2 mm/s: air gets between slabs, so the next one doesn't come along
    feed_peel_slow: float = 120.0
    peel_mm: float = 5.0
    peel_dwell_s: float = 0.15
    # vacuum (kPa, negative = vacuum)
    vac_seal_kpa: float = -35.0
    vac_seal_timeout_s: float = 0.4
    vac_transit_alarm_kpa: float = -25.0
    vent_s: float = 0.25
    # reading
    front_photo: str = "fallback"  # fallback | always  (always = full front photo of every slab, +~3 s/slab)
    needs_review_to: str = "output"  # output | exceptions
    hover_check: bool = True  # look at the top slab before touching it (face-down check)
    frames_per_read: int = 2
    custom_regex: str | None = None
    accepted_graders: tuple = ("PSA", "CGC")
    allow_ocr: bool = True
    axes: str = "XZ"  # SlabRail has no Y axis; Y words are never sent
    gate_z: float = 214.0  # overfill light beam height (MAX line + 4); only valid with the head up
    overfill_gate: bool = True  # GPIO 5 beam receiver fitted
    lid_switch: bool = False  # optional lid/door switch on GPIO 25
    light_settle_s: float = 0.3  # wait after an LED ring switches on, so auto exposure settles before a frame
    # paths
    out_dir: str = "batches"
    # device "auto" = first /dev/v4l/by-id/usb-*-video-index0 (on a Pi 5 the CSI pipeline owns /dev/video0..7)
    cam_head: dict = field(default_factory=lambda: {"type": "usb", "device": "auto", "width": 3264, "height": 2448})
    cam_station: dict = field(default_factory=lambda: {"type": "picamera", "index": 0, "lens_position": 7.1})
    serial_port: str = "/dev/ttyUSB0"  # if missing, /dev/serial/by-id, ttyUSB*, ttyACM* are tried
    # calibration: machine = bed + offset (bed coords come from the CAD layout)
    offset_x: float = 0.0
    offset_y: float = 0.0
    rotation_deg: float = 0.0
    pad_trigger_c: float = 0.0  # machine Z at which the probe trips on the bare pad of pocket 0

    def pocket(self, index: int) -> PocketCfg:
        return self.pockets[index]

    @property
    def sources(self) -> list[PocketCfg]:
        return [p for p in self.pockets if p.role == "source"]

    @property
    def exceptions(self) -> PocketCfg:
        return next(p for p in self.pockets if p.role == "exceptions")

    @property
    def capacity(self) -> int:
        return len(self.sources) * self.stack_max


_TUPLE_FIELDS = ("station_xy", "accepted_graders")


def load(path: Path, calibration: Path | None = None) -> Config:
    """machine.toml, then calibration.toml on top (any key may be overridden there)."""
    raw = tomllib.loads(Path(path).read_text())
    if calibration and Path(calibration).exists():
        raw.update(tomllib.loads(Path(calibration).read_text()))
    pockets = [PocketCfg(**p) for p in raw.pop("pockets")]
    known = {f.name for f in fields(Config)}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValueError(f"unknown config keys {unknown} in {path}" + (f" or {calibration}" if calibration else "") + " - typo, or a file from another version?")
    for k in _TUPLE_FIELDS:
        if k in raw:
            raw[k] = tuple(raw[k])
    return Config(pockets=pockets, **raw)


def from_layout() -> Config:
    """Build a config straight from cad/layout.py (used by tests and gen_config)."""
    import sys

    cad = Path(__file__).resolve().parents[2] / "cad"
    if str(cad) not in sys.path:
        sys.path.insert(0, str(cad))
    import layout as L

    return Config(
        pockets=[PocketCfg(p.index, p.x, p.y, p.role) for p in L.pockets()],
        station_xy=L.station_xy(),
        station_read_c=round(L.STATION_READ_C, 2),
        c_safe_empty=L.C_SAFE_EMPTY,
        c_safe_loaded=L.C_SAFE_LOADED,
        c_max=L.C_MAX,
        post_h=L.POST_H,
        stack_max=L.STACK_MAX,
        max_line=L.MAX_LINE,
        probe_window=L.PROBE_WINDOW,
        gate_z=L.GATE_Z,
    )


def toml_value(v) -> str:
    """One TOML value. Strings use JSON escaping, which is valid TOML basic-string escaping."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (tuple, list)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(x)}" for k, x in v.items() if x is not None) + " }"
    raise TypeError(f"cannot write {type(v).__name__} to TOML")


CALIBRATION_KEYS = ("offset_x", "offset_y", "rotation_deg", "pad_trigger_c")


def dumps(cfg: Config) -> str:
    """TOML writer for the generated machine.toml (flat keys + pockets array)."""
    lines = ["# Generated by tools/gen_config.py from cad/layout.py - edit calibration.toml, not this file.",
             "# Any key below can be overridden in calibration.toml (the calibrate commands write there).", ""]
    skip = {"pockets", *CALIBRATION_KEYS}
    for k, v in cfg.__dict__.items():
        if k in skip or v is None:
            continue
        lines.append(f"{k} = {toml_value(v)}")
    lines.append("")
    for p in cfg.pockets:
        lines += ["[[pockets]]", f"index = {p.index}", f"x = {p.x!r}", f"y = {p.y!r}", f'role = "{p.role}"', ""]
    return "\n".join(lines)


def write_overrides(path: Path, updates: dict, comment: str = "") -> dict:
    """Merge ``updates`` into a calibration/override TOML file (keeps every other key). Returns the merged dict."""
    path = Path(path)
    current = tomllib.loads(path.read_text()) if path.exists() else {}
    current.update(updates)
    known = {f.name for f in fields(Config)}
    bad = sorted(set(current) - known)
    if bad:
        raise ValueError(f"refusing to write unknown config keys {bad}")
    lines = ["# Written by `python -m slabscan calibrate ...` / `focus --save`. Overrides machine.toml.", "# Safe to edit by hand."]
    if comment:
        lines += [f"# {c}" for c in comment.splitlines()]
    lines.append("")
    lines += [f"{k} = {toml_value(v)}" for k, v in current.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(path)
    return current
