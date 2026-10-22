"""Machine configuration (TOML). ``tools/gen_config.py`` writes config/machine.toml from the CAD layout;
calibration values are written to config/calibration.toml so a re-generation never loses them."""

from __future__ import annotations

import json
import re
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
    # defaults = cad/layout.py (machine.toml always sets them; a stale default must never be unsafe)
    c_safe_empty: float = 236.5
    c_safe_loaded: float = 248.0
    c_max: float = 250.0
    post_h: float = 218.0
    stack_max: int = 30
    max_line: float = 210.0
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
    # The probe trips with the spring buffer already compressed (BUILD_GUIDE 7.6: 2.0 +/- 0.5 mm), so the
    # cup only leaves the slab once the head has risen that far again. The slow leg of the peel is placed
    # around that point: measure the trip travel and put buffer_trip_mm (and a smaller tol) in calibration.toml.
    buffer_trip_mm: float = 2.0
    buffer_trip_tol_mm: float = 0.5  # uncertainty of buffer_trip_mm; 0.1 once measured
    peel_slow_mm: float = 1.0  # slow lift AFTER the cup leaves the slab (2 mm/s): air gets between slabs, so the next one doesn't come along
    feed_peel_slow: float = 120.0
    peel_mm: float = 5.0
    peel_dwell_s: float = 0.5  # held low over the source: a slab clinging by an air film falls back a few mm onto its own stack
    feed_rod_band: float = 1200.0  # Z feed while a held slab passes the rod tops (5 mm above to 10 mm below them)
    # vacuum (kPa, negative = vacuum)
    vac_seal_kpa: float = -35.0
    vac_seal_timeout_s: float = 0.4
    vac_transit_alarm_kpa: float = -25.0
    vent_s: float = 0.25
    vent_tol_kpa: float = 0.5  # after a vent the line must be back within this of atmosphere before the head lifts
    vent_timeout_s: float = 1.5
    vac_baseline_kpa: float | None = None  # sensor reading at atmosphere with an empty cup (calibrate z / selftest -i write it)
    # reading
    front_photo: str = "fallback"  # fallback | always  (always = full front photo of every slab, +~3 s/slab)
    needs_review_to: str = "output"  # output | exceptions
    hover_check: bool = True  # use the frame taken from above the top slab as an extra read of its back label
    # Before the cup touches a slab, the frame from above must prove it is face-down:
    # "stop": only a PSA back-label QR proves it; otherwise the run stops untouched and the operator confirms
    #         (resume --face-down-ok).
    # "learned": a PSA back QR, or a card window that matches the card backs of earlier QR- or operator-confirmed
    #         slabs (slabscan/facedown.py). Active only once face_down_threshold is measured (phase0 --save writes
    #         it with face_down_threshold_sig, the card window it was measured for), face_down_min_refs references
    #         exist and the head's view of the window is checked on this machine; until then it behaves like "stop".
    # "off": no check - only the operator's face-down loading protects the fronts.
    face_down_check: str = "learned"
    face_down_threshold: float | None = None  # similarity a card window needs; Phase 0 measures it (phase0 --save writes it)
    face_down_threshold_sig: str | None = None  # facedown.threshold_tag() of the window and check it was measured for
    face_down_min_refs: int = 5  # references (QR- or operator-confirmed card backs) needed before a learned match counts
    # Card-window rectangles [along the row, along the slab, ...] in mm on the slab plane from the head-camera axis,
    # label end negative. They must lie on the card (not the label) and be clear of the head's own cup, buffer and
    # foot in the frame from above. [Guessing] card position in the slab; the CAD head foot of today hides this
    # area (its shadow covers |x| < 34, y > -34 at the hover height), so the learned check refuses to use it.
    face_down_window_mm: tuple = ((-28.0, -33.0, 28.0, -17.0),)
    psa_cert_digits: tuple = ()  # PSA cert lengths seen in Phase 0, e.g. [8, 9]; an 'ok' of another length -> needs_review
    frames_per_read: int = 2
    custom_regex: str | None = None
    accepted_graders: tuple = ("PSA", "CGC")
    allow_ocr: bool = True
    axes: str = "XZ"  # SlabRail has no Y axis; Y words are never sent
    # machine travel the controller allows (soft limits in firmware/fluidnc/config.yaml - keep them equal)
    x_travel: tuple = (22.0, 1253.0)
    z_min: float = -8.0
    gate_z: float = 214.0  # overfill light beam height (MAX line + 4); only valid with the head up
    overfill_gate: bool = True  # GPIO 5 beam receiver fitted
    lid_switch: bool = False  # optional lid/door switch on GPIO 25
    light_settle_s: float = 0.3  # wait after an LED ring switches on, so auto exposure settles before a frame
    # paths
    out_dir: str = "batches"
    # device "auto" = first /dev/v4l/by-id/usb-*-video-index0 (on a Pi 5 the CSI pipeline owns /dev/video0..7)
    # hfov_deg: full field of view across the image width; row_axis: which image axis runs along the pocket row
    # ("x" = image width); lens_to_label_mm: lens to the held slab's back (cad/layout.py CAM_TO_SLAB). Used to crop
    # head-camera frames to the pocket under the cup: the 3.6 mm lens also sees the neighbouring pockets' labels.
    cam_head: dict = field(default_factory=lambda: {"type": "usb", "device": "auto", "width": 3264, "height": 2448, "hfov_deg": 64.0, "row_axis": "x",
                                                         "lens_to_label_mm": 140.0})
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


_TUPLE_FIELDS = ("station_xy", "accepted_graders", "x_travel", "psa_cert_digits")
FACE_DOWN_MODES = ("learned", "stop", "off")
FACE_DOWN_THRESHOLD_FLOOR = 0.5  # facedown.THRESHOLD_FLOOR: no measured threshold below it is used [Guessing: sim face-up scores reach 0.38-0.51]


def check_face_down(raw: dict) -> None:
    mode = raw.get("face_down_check", "learned")
    if mode not in FACE_DOWN_MODES:
        raise ValueError(f"face_down_check must be one of {', '.join(repr(m) for m in FACE_DOWN_MODES)}, not {mode!r}")
    t = raw.get("face_down_threshold")
    if t is not None and not (isinstance(t, (int, float)) and not isinstance(t, bool) and FACE_DOWN_THRESHOLD_FLOOR <= float(t) < 1.0):
        raise ValueError(f"face_down_threshold must be a number from {FACE_DOWN_THRESHOLD_FLOOR} to below 1 (Phase 0 measures it), not {t!r}")
    sig = raw.get("face_down_threshold_sig")
    if sig is not None and not isinstance(sig, str):
        raise ValueError(f"face_down_threshold_sig must be the text phase0 --save wrote, not {sig!r}")
    n = raw.get("face_down_min_refs", 1)
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"face_down_min_refs must be a whole number >= 1, not {n!r}")
    for r in raw.get("face_down_window_mm", ()):
        if len(r) != 4 or not (r[0] < r[2] and r[1] < r[3]):
            raise ValueError(f"face_down_window_mm: each rectangle is [x0, y0, x1, y1] with x0 < x1 and y0 < y1, not {list(r)!r}")


def check_custom_regex(rx: str | None) -> None:
    """A custom cert regex must compile and have exactly one capture group (the digits)."""
    if not rx:
        return
    try:
        n = re.compile(rx).groups
    except re.error as e:
        raise ValueError(f"custom_regex {rx!r} is not a valid regular expression: {e}") from None
    if n != 1:
        raise ValueError(f"custom_regex {rx!r} must have exactly one capture group (the cert digits), it has {n}")


DESIGN_CUP_HANG = 2.0  # = cad/layout.py CUP_HANG


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
    check_custom_regex(raw.get("custom_regex"))
    if "face_down_window_mm" in raw:
        raw["face_down_window_mm"] = tuple(tuple(float(v) for v in r) for r in raw["face_down_window_mm"])
    check_face_down(raw)
    cfg = Config(pockets=pockets, **raw)
    # The travel heights assume the free cup hangs DESIGN_CUP_HANG below its trip height (cad/layout.py CUP_HANG).
    # A buffer measured to trip later hangs lower, so both travel heights go up by the difference.
    excess = cfg.buffer_trip_mm - DESIGN_CUP_HANG
    if excess > 0:
        cfg.c_safe_empty = round(cfg.c_safe_empty + excess, 3)
        cfg.c_safe_loaded = round(cfg.c_safe_loaded + excess, 3)
        if cfg.c_safe_loaded > cfg.c_max:
            raise ValueError(f"buffer_trip_mm = {cfg.buffer_trip_mm} puts loaded travel at {cfg.c_safe_loaded} mm, above c_max {cfg.c_max}: "
                             "set the probe flag to trip after 1.5-2.5 mm of buffer travel (BUILD_GUIDE 7.6) and measure again")
    return cfg


def from_layout() -> Config:
    """Build a config straight from cad/layout.py (used by tests and gen_config)."""
    import sys

    cad = Path(__file__).resolve().parents[2] / "cad"
    if str(cad) not in sys.path:
        sys.path.insert(0, str(cad))
    import layout as L

    ps = L.pockets()
    return Config(
        pockets=[PocketCfg(p.index, p.x, p.y, p.role) for p in ps],
        x_travel=(round(ps[0].x - 20.0, 3), round(ps[-1].x + 15.0, 3)),  # = firmware soft limits 22 .. 1253
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
        **({"face_down_window_mm": tuple(tuple(float(v) for v in r) for r in L.FACE_DOWN_WINDOW_MM)} if hasattr(L, "FACE_DOWN_WINDOW_MM") else {}),
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


CALIBRATION_KEYS = ("offset_x", "offset_y", "rotation_deg", "pad_trigger_c", "vac_baseline_kpa", "buffer_trip_mm", "buffer_trip_tol_mm")


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
