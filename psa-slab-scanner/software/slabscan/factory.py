"""Build the machine's backends from the config: real hardware on the Pi, or the simulator (--sim).

Every backend has the same small interface, so the runner, the CLI tools and the web page
never care which one they got:

  motion   home() move(feed, x=, z=) wait_idle() probe(z, feed) position() pins() close()
  vacuum   hold() release() kpa() close()
  lights   head(on) station(on)
  cameras  capture() -> BGR or gray ndarray   (+ set_lens_position / lens_range on the Pi camera)
  gate     clear() -> bool      lid  closed() -> bool
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from .config import Config

ALL_PARTS = ("motion", "vacuum", "lights", "head_cam", "station_cam", "gate", "lid")


@dataclass
class Hardware:
    cfg: Config
    motion: Any = None
    vacuum: Any = None
    lights: Any = None
    head_cam: Any = None
    station_cam: Any = None
    gate: Any = None
    lid: Any = None
    world: Any = None  # SimWorld when simulated
    sim: bool = False
    notes: list[str] = field(default_factory=list)

    def close(self) -> None:
        # Vacuum last and with close() (valves shut, no vent): a held slab is not dropped.
        for part in ("head_cam", "station_cam", "lights", "motion", "vacuum"):
            dev = getattr(self, part)
            if dev is not None and hasattr(dev, "close"):
                try:
                    dev.close()
                except Exception:  # noqa: BLE001 - best effort on shutdown
                    pass


# ---------------------------------------------------------------------- real hardware
def find_serial_port(configured: str) -> str:
    """The configured port if it exists, else the first FluidNC-looking serial device."""
    if configured and configured != "auto" and os.path.exists(configured):
        return configured
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyUSB*", "/dev/ttyACM*"):
        found = sorted(glob.glob(pattern))
        if found:
            return found[0]
    raise RuntimeError(f"no controller serial port: {configured} does not exist and no /dev/ttyUSB*, /dev/ttyACM* found. Is the Rodent plugged in and powered?")


def make_camera(spec: dict, name: str):
    from .camera import PiCamera, UsbCamera

    kind = spec.get("type", "usb")
    if kind == "usb":
        return UsbCamera(spec.get("device", "auto"), name, size=(int(spec.get("width", 3264)), int(spec.get("height", 2448))), focus=spec.get("focus"))
    if kind == "picamera":
        return PiCamera(int(spec.get("index", 0)), name, lens_position=spec.get("lens_position"), exposure_us=spec.get("exposure_us"), gain=spec.get("gain"),
                        size=(int(spec.get("width", 4608)), int(spec.get("height", 2592))))
    raise ValueError(f"camera {name}: unknown type {kind!r} (usb | picamera)")


def make_part(cfg: Config, part: str):
    if part == "motion":
        from .motion import GcodeMachine

        return GcodeMachine(find_serial_port(cfg.serial_port))
    if part == "vacuum":
        from .hw import PiVacuum

        return PiVacuum(vent_s=cfg.vent_s)
    if part == "lights":
        from .hw import PiLights

        return PiLights(settle_s=cfg.light_settle_s)
    if part == "head_cam":
        return make_camera(cfg.cam_head, "head")
    if part == "station_cam":
        return make_camera(cfg.cam_station, "station")
    if part == "gate":
        from .hw import PiGate

        return PiGate() if cfg.overfill_gate else None
    if part == "lid":
        from .hw import PiLid

        return PiLid() if cfg.lid_switch else None
    raise ValueError(part)


# ---------------------------------------------------------------------- simulator
class SimLid:
    def __init__(self, closed: bool = True):
        self.is_closed = closed

    def closed(self) -> bool:
        return self.is_closed


class SimLensCamera:
    """Simulated Camera Module 3 focus: blur grows with distance from the in-focus lens position."""

    def __init__(self, base, best: float = 1 / 0.14, blur_per_dioptre: float = 1.6, lens_position: float = 7.1):
        self.base = base
        self.best = best
        self.k = blur_per_dioptre
        self.lp = lens_position
        self.name = getattr(base, "role", "station")

    def lens_range(self):
        return (0.0, 15.0, 1.0)

    def set_lens_position(self, dioptres: float) -> None:
        self.lp = float(dioptres)

    def capture(self) -> np.ndarray:
        img = self.base.capture()
        sigma = 0.05 + self.k * abs(self.lp - self.best)
        return cv2.GaussianBlur(img, (0, 0), sigma) if sigma > 0.1 else img

    def close(self) -> None:
        pass


def sim_stacks(cfg: Config, slabs: int, seed: int = 7, eras=(0.85, 0.1, 0.05), clingy_rate: float = 0.0, thick_rate: float = 0.0):
    """``slabs`` simulated slabs spread as evenly as possible over the source pockets."""
    from .simworld import make_batch

    n_src = len(cfg.sources)
    if slabs > cfg.capacity:
        raise ValueError(f"{slabs} slabs > capacity {cfg.capacity}")
    full = make_batch(cfg, per_pocket=cfg.stack_max, seed=seed, eras=eras, clingy_rate=clingy_rate, thick_rate=thick_rate)
    stacks = {}
    for i, p in enumerate(cfg.sources):
        k = slabs // n_src + (1 if i < slabs % n_src else 0)
        stacks[p.index] = full[p.index][:k]
    return stacks


def sim_hardware(cfg: Config, slabs: int = 22, seed: int = 7, world=None, stacks=None, **batch_kw) -> Hardware:
    """Simulated machine. Calibration offsets in cfg become the simulator's built-in offsets, so a
    calibrated config drives the simulated machine exactly as it would drive the real one."""
    from .simworld import SimCamera, SimGate, SimLights, SimMotion, SimVacuum, SimWorld

    if world is None:
        if stacks is None:
            stacks = sim_stacks(cfg, slabs, seed, **batch_kw)
        world = SimWorld(cfg, stacks={k: list(v) for k, v in stacks.items()})
    return Hardware(
        cfg=cfg,
        motion=SimMotion(world, x_offset=cfg.offset_x, z_offset=cfg.pad_trigger_c),
        vacuum=SimVacuum(world),
        lights=SimLights(),
        head_cam=SimCamera(world, "head"),
        station_cam=SimCamera(world, "station"),
        gate=SimGate(world) if cfg.overfill_gate else None,
        lid=SimLid() if cfg.lid_switch else None,
        world=world,
        sim=True,
    )


def open_hardware(cfg: Config, sim: bool = False, parts=ALL_PARTS, log=print, **sim_kw) -> Hardware:
    """Open the requested parts. On failure every part opened so far is closed again."""
    if sim:
        hw = sim_hardware(cfg, **sim_kw)
        for p in ALL_PARTS:
            if p not in parts:
                setattr(hw, p, None)
        return hw
    hw = Hardware(cfg=cfg)
    try:
        for p in parts:
            setattr(hw, p, make_part(cfg, p))
    except Exception:
        hw.close()
        raise
    return hw
