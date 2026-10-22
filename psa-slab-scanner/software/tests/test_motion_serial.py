"""GcodeMachine against a fake FluidNC on a pseudo-terminal (no hardware).

The fake answers like FluidNC v3/v4 (see firmware/fluidnc/config.yaml and docs/FIRMWARE.md):
banner on connect, 'ok' per line, '?' realtime status with 3 axes (no Y axis is defined, FluidNC
still pads to 3), [PRB:x,y,z:1|0] before 'ok' for G38.3, ALARM:4 when the probe is already
triggered at the start, $# with [G54:...], homing to X 22 / Z 255.
"""

import os
import re
import threading
import time

import pytest

serial = pytest.importorskip("serial")
pty = pytest.importorskip("pty")

from slabscan.motion import GcodeMachine, MotionError  # noqa: E402


class FakeFluidNC(threading.Thread):
    SURFACE_Z = 3.0  # machine Z at which the probe trips over the bed

    def __init__(self):
        super().__init__(daemon=True)
        self.master, slave = pty.openpty()
        self.port = os.ttyname(slave)
        self.slave = slave
        self.x, self.z = 0.0, 100.0
        self.g54 = [0.0, 0.0, 1.5]  # stale offset left by some G-code sender
        self.lines: list[str] = []
        self.alive = True

    def out(self, s: str) -> None:
        try:
            os.write(self.master, (s + "\r\n").encode())
        except OSError:  # the test pulled the plug
            self.alive = False

    def run(self):
        time.sleep(0.3)
        self.out("")
        self.out("Grbl 3.9 [FluidNC v4.1.1 (noradio) '$' for help]")
        self.out("[MSG:INFO: Machine SlabRail]")
        buf = b""
        while self.alive:
            try:
                data = os.read(self.master, 1024)
            except OSError:
                return
            for ch in data:
                c = bytes([ch])
                if c == b"?":
                    pins = "|Pn:P" if self.z <= self.SURFACE_Z + 1e-6 else ""
                    self.out(f"<Idle|MPos:{self.x:.3f},0.000,{self.z:.3f}|FS:0,0{pins}>")
                elif c == b"\n":
                    self.handle(buf.decode().strip())
                    buf = b""
                else:
                    buf += c

    def handle(self, line: str) -> None:
        self.lines.append(line)
        words = dict((w[0], float(w[1:])) for w in line.split()[1:] if re.match(r"^[XYZF]-?[\d.]+$", w))
        if line == "$H":
            self.x, self.z = 22.0, 255.0
        elif line == "$#":
            self.out("[G54:{:.3f},{:.3f},{:.3f}]".format(*self.g54))
            self.out("[G92:0.000,0.000,0.000]")
            self.out("[PRB:0.000,0.000,0.000:0]")
        elif line.startswith("G10 L2 P1"):
            for i, k in ((0, "X"), (2, "Z")):
                if k in words:
                    self.g54[i] = words[k]
        elif line == "$I":
            self.out("[VER:4.1.1 FluidNC v4.1.1:]")
        elif line.startswith("G1 "):
            self.x = words.get("X", self.x) + self.g54[0]
            self.z = words.get("Z", self.z) + self.g54[2]
        elif line.startswith("G38.3"):
            if self.z <= self.SURFACE_Z + 1e-6:
                self.out("ALARM:4")
                return
            target = words["Z"] + self.g54[2]
            if target <= self.SURFACE_Z:
                self.z = self.SURFACE_Z
                self.out(f"[PRB:{self.x:.3f},0.000,{self.z:.3f}:1]")
            else:
                self.z = target
                self.out(f"[PRB:{self.x:.3f},0.000,{self.z:.3f}:0]")
        self.out("ok")

    def kill(self) -> None:
        self.alive = False
        os.close(self.master)


@pytest.fixture
def fake():
    f = FakeFluidNC()
    f.start()
    yield f
    f.alive = False


def test_connect_home_move_probe(fake):
    m = GcodeMachine(fake.port, boot_s=3.0)
    assert "FluidNC" in m.banner
    assert fake.lines[0] == "$X"
    m.home()
    assert fake.g54 == [0.0, 0.0, 0.0]  # the stale G54 offset was zeroed: software calibration is the only offset
    assert "G10 L2 P1 X0 Z0" in fake.lines and "G92.1" in fake.lines
    assert m.position() == pytest.approx((22.0, 255.0))
    assert m.pins() == ""
    m.move(3000, x=134.0)
    m.wait_idle()
    m.move(6000, z=20.0)
    m.wait_idle()
    assert m.position() == pytest.approx((134.0, 20.0))
    assert m.probe(10.0, 1200) is None  # miss: G38.3 stops at its target without an alarm
    assert m.position()[1] == pytest.approx(10.0)
    assert m.probe(-5.0, 1200) == pytest.approx(3.0)
    assert m.pins() == "P"
    with pytest.raises(MotionError, match="ALARM"):
        m.probe(-5.0, 1200)  # FluidNC refuses to start a probe that is already triggered
    m.close()


def test_lost_controller_reports_estop(fake):
    m = GcodeMachine(fake.port, boot_s=3.0)
    fake.kill()  # E-stop cuts the controller's power: the USB serial device goes away
    with pytest.raises(MotionError, match="E-stop"):
        for _ in range(3):
            m.status()
            time.sleep(0.05)
