"""Motion control: G-code over USB serial to a FluidNC controller, plus a simulator.

FluidNC (ESP32 firmware, grbl-compatible) was chosen because it:
  * drives the steppers and the gripper servo from one config file (servo = an RC-servo "axis"),
  * homes with plain microswitches,
  * reports position/state on "?" so the Pi can wait for real completion.
Any grbl-compatible controller works if its config gives the same axis letters.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

_STATUS_RE = re.compile(r"<(\w+)(?::\d+)?\|MPos:([-\d.]+),([-\d.]+),([-\d.]+)(?:,([-\d.]+))?")


class MotionError(Exception):
    pass


@dataclass
class Pose:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    a: float = 0.0  # gripper servo "axis" (mm of jaw travel, mapped to pulse width in FluidNC)


class GcodeMachine:
    """Blocking, line-by-line G-code sender (one command, wait for 'ok')."""

    def __init__(self, port: str, baud: int = 115200, timeout_s: float = 60.0):
        import serial  # pyserial

        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.timeout_s = timeout_s
        time.sleep(2.0)  # ESP32 resets when the port opens
        self.ser.reset_input_buffer()
        self.send("$X")  # clear alarm lock after reset (homing still required)

    def _readline(self) -> str:
        return self.ser.readline().decode("ascii", "replace").strip()

    def send(self, line: str) -> list[str]:
        self.ser.write((line.strip() + "\n").encode("ascii"))
        deadline = time.monotonic() + self.timeout_s
        replies: list[str] = []
        while time.monotonic() < deadline:
            r = self._readline()
            if not r:
                continue
            if r == "ok":
                return replies
            if r.startswith("error") or r.startswith("ALARM"):
                raise MotionError(f"{line!r} -> {r}")
            replies.append(r)
        raise MotionError(f"timeout waiting for ok after {line!r}")

    def status(self) -> tuple[str, Pose]:
        self.ser.write(b"?")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            m = _STATUS_RE.search(self._readline())
            if m:
                a = float(m.group(5)) if m.group(5) else 0.0
                return m.group(1), Pose(float(m.group(2)), float(m.group(3)), float(m.group(4)), a)
        raise MotionError("no status report")

    def wait_idle(self) -> Pose:
        self.send("G4 P0")  # planner barrier: 'ok' only after all queued motion is done
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            state, pose = self.status()
            if state == "Idle":
                return pose
            if state in ("Alarm", "Door"):
                raise MotionError(f"controller state {state}")
            time.sleep(0.05)
        raise MotionError("timeout waiting for Idle")

    def home(self) -> None:
        self.send("$H")
        self.wait_idle()
        self.send("G90")  # absolute
        self.send("G21")  # mm

    def move(self, feed: float, **axes: float) -> None:
        words = " ".join(f"{k.upper()}{v:.3f}" for k, v in axes.items())
        self.send(f"G1 {words} F{feed:.0f}")

    def output(self, pin: int, on: bool) -> None:
        """Immediate digital output (FluidNC user_outputs): M64 = on, M65 = off."""
        self.send(f"{'M64' if on else 'M65'} P{pin}")

    def close(self) -> None:
        self.ser.close()


@dataclass
class SimMachine:
    """Records every motion so the run loop can be tested with no hardware."""

    pose: Pose = field(default_factory=Pose)
    log: list[str] = field(default_factory=list)
    outputs: dict[int, bool] = field(default_factory=dict)
    travel_mm: float = 0.0
    move_time_s: float = 0.0

    def home(self) -> None:
        self.log.append("$H")
        self.pose = Pose()

    def move(self, feed: float, **axes: float) -> None:
        old = self.pose
        new = Pose(**{**old.__dict__, **{k.lower(): v for k, v in axes.items()}})
        d = ((new.x - old.x) ** 2 + (new.y - old.y) ** 2 + (new.z - old.z) ** 2) ** 0.5
        self.travel_mm += d
        self.move_time_s += d / (feed / 60.0) if feed > 0 else 0.0
        self.pose = new
        self.log.append("G1 " + " ".join(f"{k.upper()}{v:.2f}" for k, v in axes.items()) + f" F{feed:.0f}")

    def wait_idle(self) -> Pose:
        return self.pose

    def output(self, pin: int, on: bool) -> None:
        self.outputs[pin] = on
        self.log.append(f"{'M64' if on else 'M65'} P{pin}")

    def close(self) -> None:
        pass
