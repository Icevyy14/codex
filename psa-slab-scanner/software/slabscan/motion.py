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

_PRB_RE = re.compile(r"\[PRB:([-\d.]+),([-\d.]+),([-\d.]+)(?:,[-\d.]+)*:(\d)\]")
# FluidNC always reports at least 3 axes (X,Y,Z) even with no Y axis defined (Axes::afterParse).
# MPos or WPos depending on the $10 status mask.
_STATUS_RE = re.compile(r"<(\w+)(?::\d+)?\|(MPos|WPos):([-\d.]+),([-\d.]+),([-\d.]+)(?:,([-\d.]+))?")
_PINS_RE = re.compile(r"\|Pn:([A-Za-z]+)")


class MotionError(Exception):
    pass


@dataclass
class Pose:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    a: float = 0.0  # gripper servo "axis" (mm of jaw travel, mapped to pulse width in FluidNC)


class ControllerLost(MotionError):
    """The controller's USB serial port went away. The E-stop cuts the Rodent's 24 V, so FluidNC
    reboots and the CH340 device disappears (CONTRACT.md "E-stop"). The runner turns this into a
    clean Stop without moving anything; the next command reconnects and must home again."""


# CONTRACT.md: firmware soft limit Z -8; CAD keeps the Z carriage on its rail down to c = -12.
# Every probe target is clamped to Z_FLOOR so a probe can never ask the controller for a target past the limit.
Z_FLOOR = -7.5


class GcodeMachine:
    """Blocking, line-by-line G-code sender (one command, wait for 'ok').

    Safety rules kept here, below every caller:
      * no move or probe before ``home()`` on this connection. FluidNC's ``$X`` (sent on connect)
        marks every axis as homed (FluidNC ProcessSettings.cpp, disable_alarm_lock), so the
        controller itself would accept moves from an unknown position after an E-stop reboot;
      * probe targets are clamped to ``z_floor`` (-7.5, inside the Z -8 soft limit), plain moves
        below it are refused;
      * a lost serial port raises ``ControllerLost``; the next command reopens the port (it may come
        back under a new /dev/ttyUSB* name, so ``find_port`` is asked again) and homing is required.
    """

    LOST = ("Lost the controller: its USB serial port went away. The E-stop cuts the controller's power, so this "
            "usually means the E-stop was pressed (or the USB cable came out). Release it, then home again and resume.")

    def __init__(self, port: str, baud: int = 115200, timeout_s: float = 60.0, boot_s: float = 8.0, find_port=None,
                 z_floor: float = Z_FLOOR, reconnect_s: float = 15.0):
        import serial  # pyserial

        self._serial = serial
        self._serial_errors = (serial.SerialException, OSError)
        self.port = port
        self.baud = baud
        self.boot_s = boot_s
        self.find_port = find_port  # callable -> port path, asked again on every reconnect
        self.z_floor = z_floor
        self.reconnect_s = reconnect_s
        self.timeout_s = timeout_s
        self.ser = None
        self.lost = False
        self.homed = False
        self.reconnects = 0
        self.banner = ""
        try:
            self._connect()
        except Exception:
            self.close()
            raise

    def _connect(self) -> None:
        self.ser = self._serial.Serial(self.port, self.baud, timeout=0.2)
        self.lost = False
        self.homed = False
        self._wco = None
        self.banner = ""
        # Opening the port resets the ESP32 (CH340 auto-reset). Wait for FluidNC's start-up banner
        # instead of a fixed sleep: boot time varies with the config and the WiFi/BT setup.
        deadline = time.monotonic() + self.boot_s
        while time.monotonic() < deadline:
            line = self._readline()
            if "Grbl" in line or "FluidNC" in line:
                self.banner = line
                time.sleep(0.3)  # the rest of the boot messages
                break
        try:
            self.ser.reset_input_buffer()
        except self._serial_errors as e:
            self._lose(e)
        for attempt in range(5):  # clear the alarm lock after reset; our own homed flag still demands $H
            try:
                self._send("$X", timeout_s=3.0)
                break
            except ControllerLost:
                raise
            except MotionError:
                if attempt == 4:
                    raise MotionError(f"controller on {self.port} does not answer $X (is FluidNC running? baud {self.baud}?)")
                time.sleep(1.0)

    def _lose(self, e: Exception | str) -> None:
        self.lost = True
        self.homed = False
        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:  # noqa: BLE001 - the device is already gone
            pass
        raise ControllerLost(f"{self.LOST} ({e})")

    def reconnect(self) -> None:
        """Reopen the port after a loss (waits up to reconnect_s for it to come back). Homing is required afterwards."""
        deadline = time.monotonic() + self.reconnect_s
        while True:
            try:
                if self.find_port is not None:
                    self.port = self.find_port()
                self._connect()
                self.reconnects += 1
                return
            except (MotionError, RuntimeError, *self._serial_errors) as e:
                self.lost = True
                self.close()  # a half-open port must not block the next attempt ("device busy")
                if time.monotonic() >= deadline:
                    raise ControllerLost(f"The controller is still not answering ({e}). Twist the E-stop to release it, check the "
                                         "USB cable and the 24 V supply, then try again.") from None
                time.sleep(1.0)

    def _ensure(self) -> None:
        if self.lost:
            self.reconnect()

    def _port_gone(self) -> bool:
        import os

        return isinstance(self.port, str) and self.port.startswith("/dev/") and not os.path.exists(self.port)

    def _readline(self) -> str:
        try:
            return self.ser.readline().decode("ascii", "replace").strip()
        except self._serial_errors as e:
            self._lose(e)

    def _write(self, data: bytes) -> None:
        try:
            self.ser.write(data)
        except self._serial_errors as e:
            self._lose(e)

    def _send(self, line: str, timeout_s: float) -> list[str]:
        old, self.timeout_s = self.timeout_s, timeout_s
        try:
            return self.send(line)
        finally:
            self.timeout_s = old

    def send(self, line: str) -> list[str]:
        self._ensure()
        self._write((line.strip() + "\n").encode("ascii"))
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
        if self._port_gone():
            self._lose(f"{self.port} disappeared")
        raise MotionError(f"timeout waiting for ok after {line!r}")

    def status(self) -> tuple[str, Pose]:
        """(state, machine position). A WPos report is converted with the G54 offset."""
        self._ensure()
        self._write(b"?")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            line = self._readline()
            m = _STATUS_RE.search(line)
            if m:
                self.last_status = line
                a = float(m.group(6)) if m.group(6) else 0.0
                pose = Pose(float(m.group(3)), float(m.group(4)), float(m.group(5)), a)
                if m.group(2) == "WPos":
                    ox, oy, oz = self.work_offset
                    pose = Pose(pose.x + ox, pose.y + oy, pose.z + oz, a)
                return m.group(1), pose
        if self._port_gone():
            self._lose(f"{self.port} disappeared")
        raise MotionError("no status report")

    def pins(self) -> str:
        """Active input pins from the status report's Pn: field. 'P' = probe triggered, X/Z = limit switch pressed."""
        self.status()
        m = _PINS_RE.search(getattr(self, "last_status", ""))
        return m.group(1) if m else ""

    def position(self) -> tuple[float, float]:
        """Work (x, z) - the coordinates G1/G38.3 use."""
        _, pose = self.status()
        ox, _, oz = self.work_offset
        return pose.x - ox, pose.z - oz

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
        # Z (263 mm at 1500 mm/min seek) then X (1231 mm at 3000 mm/min) is ~40 s before the slow
        # second touches; allow well beyond that so a long first homing is not reported as a failure.
        old, self.timeout_s = self.timeout_s, max(self.timeout_s, 180.0)
        try:
            self.send("$H")
            self.wait_idle()
        finally:
            self.timeout_s = old
        self.send("G90")  # absolute
        self.send("G21")  # mm
        self.send("G54")
        self.send("G92.1")  # clear any G92 offset
        # Calibration lives in software (offset_x, pad_trigger_c), so work coordinates must equal
        # machine coordinates. A G54 offset left by a G-code sender would silently shift everything.
        ox, _, oz = self.work_offset
        if abs(ox) > 1e-6 or abs(oz) > 1e-6:
            self.send("G10 L2 P1 X0 Z0")
            self._wco = None
        self.homed = True

    def _need_home(self, what: str) -> None:
        if not self.homed:
            raise MotionError(f"refusing to {what} before homing on this connection (after a reset or E-stop the position is unknown): home first")

    def move(self, feed: float, **axes: float) -> None:
        self._need_home("move")
        z = axes.get("z", axes.get("Z"))
        if z is not None and z < self.z_floor - 1e-6:
            raise MotionError(f"refusing Z {z:.3f}: below the lowest allowed Z {self.z_floor:g} (firmware soft limit -8)")
        words = " ".join(f"{k.upper()}{v:.3f}" for k, v in axes.items())
        self.send(f"G1 {words} F{feed:.0f}")

    def probe(self, z_target: float, feed: float) -> float | None:
        """Bounded probe: move down toward z_target, stop when the contact sensor trips.

        G38.3 = probe toward workpiece, no alarm if nothing is touched. Returns the work-Z of the
        trigger point, or None if z_target was reached without contact.
        """
        self._need_home("probe")
        z_target = max(z_target, self.z_floor)  # never past the Z soft limit (CONTRACT.md)
        replies = self.send(f"G38.3 Z{z_target:.3f} F{feed:.0f}")
        for r in replies:
            m = _PRB_RE.search(r)
            if m:
                if m.group(4) != "1":
                    return None
                # PRB reports machine coordinates; convert with the active work offset
                return float(m.group(3)) - self.work_offset_z
        raise MotionError("probe finished without a [PRB:] report")

    @property
    def work_offset(self) -> tuple[float, float, float]:
        """G54 offset (x, y, z) from '$#', cached until home() changes it."""
        if getattr(self, "_wco", None) is None:
            self._wco = (0.0, 0.0, 0.0)
            for r in self.send("$#"):
                if r.startswith("[G54:"):
                    v = [float(t) for t in r[5:].rstrip("]").split(",")]
                    v += [0.0] * (3 - len(v))
                    self._wco = (v[0], v[1], v[2])
        return self._wco

    @property
    def work_offset_z(self) -> float:
        return self.work_offset[2]

    def output(self, pin: int, on: bool) -> None:
        """Immediate digital output (FluidNC user_outputs): M64 = on, M65 = off."""
        self.send(f"{'M64' if on else 'M65'} P{pin}")

    def close(self) -> None:
        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:  # noqa: BLE001
            pass


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
