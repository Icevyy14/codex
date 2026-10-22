"""Raspberry Pi I/O: vacuum pump + valves, LED rings, vacuum sensor, beam gate, lid, carry-height sensor.

Wiring (see docs/WIRING.md): each load is switched by a logic-level MOSFET module from a Pi GPIO.
The vacuum sensor (XGZP6847A, -100..0 kPa, 0.5-4.5 V out at 5 V supply) feeds an ADS1115 ADC
through a 10k/20k divider, so the ADC never sees more than ~3 V.

Valve logic: both solenoid valves are normally closed. On power loss (or ``close()``) both close,
so the cup line stays sealed and a held slab is not dropped instantly. But the reservoir sits on
the PUMP side of the vacuum valve (BUILD_GUIDE 8.1), so once that valve closes only the few cm3 of
cup-side tubing hold the slab: it hangs for seconds to tens of seconds, depending on the leak, not
minutes. The software therefore never calls ``close()`` while a slab hangs on the cup and the Pi
still has power: it keeps the pump running (``hold()``) until the operator vents it by hand.
(Re-plumbing the reservoir to the cup side of the valve would make a power cut survivable too.)

A sensor reading outside the sensor's own 0.5-4.5 V output range is a wiring/supply fault (an open
OUT wire or a lost 5 V reads as a perfect vacuum): ``kpa()`` raises ``SensorFault`` instead.
"""

from __future__ import annotations

import time

# BCM pin numbers (match docs/WIRING.md)
PIN_PUMP = 17
PIN_VAC_VALVE = 27  # NC 2/2 valve between reservoir and cup
PIN_VENT_VALVE = 22  # NC 2/2 valve from cup line to atmosphere
PIN_LED_HEAD = 23
PIN_LED_STATION = 24
PIN_LID = 25  # lid interlock switch (closed = lid shut), input with pull-up
PIN_GATE = 5  # overfill light-beam receiver: HIGH = beam received (nothing above the MAX line)
PIN_CARRY = 6  # carry-height sensor (TCST2103 board on the Z spine) through a 10k/20k divider: HIGH = flag in the beam = head at travel height

class SensorFault(RuntimeError):
    """The vacuum sensor reading is physically impossible (broken wire, lost supply, bad divider)."""


ADS_ADDR = 0x48
DIVIDER = 2.0 / 3.0  # 20k/(10k+20k)
SENSOR_V0, SENSOR_V1 = 0.5, 4.5  # volts at -100 kPa .. 0 kPa (XGZP6847A "negative" range)
A0_MIN_V, A0_MAX_V = 0.25, 3.25  # ADC input outside this = outside the sensor's 0.5..4.5 V (x 2/3 = 0.33..3.0 V)


class PiVacuum:
    def __init__(self, vent_s: float = 0.25):
        from gpiozero import OutputDevice
        from smbus2 import SMBus

        self.pump = OutputDevice(PIN_PUMP, initial_value=False)
        self.valve = OutputDevice(PIN_VAC_VALVE, initial_value=False)
        self.vent = OutputDevice(PIN_VENT_VALVE, initial_value=False)
        self.bus = SMBus(1)
        self.vent_s = vent_s

    def hold(self) -> None:
        self.vent.off()
        self.pump.on()
        self.valve.on()

    def release(self) -> None:
        self.valve.off()
        self.pump.off()
        self.vent.on()
        time.sleep(self.vent_s)
        self.vent.off()

    def kpa(self) -> float:
        """Gauge pressure in kPa (0 = atmosphere, negative = vacuum)."""
        # ADS1115 single-shot, AIN0 vs GND, +/-4.096 V, 860 SPS
        cfg = 0x8000 | 0x4000 | 0x0200 | 0x0100 | 0x00E0 | 0x0003
        self.bus.write_i2c_block_data(ADS_ADDR, 0x01, [cfg >> 8, cfg & 0xFF])
        time.sleep(0.002)
        hi, lo = self.bus.read_i2c_block_data(ADS_ADDR, 0x00, 2)
        raw = (hi << 8) | lo
        if raw > 0x7FFF:
            raw -= 0x10000
        a0 = raw * 4.096 / 32768
        if not A0_MIN_V <= a0 <= A0_MAX_V:
            raise SensorFault(f"vacuum sensor input {a0:.2f} V is outside its 0.33-3.0 V range: sensor OUT wire, 10k/20k divider "
                              "or the sensor's 5 V supply is broken (an open input reads as a perfect vacuum)")
        v = a0 / DIVIDER
        return -100.0 + (v - SENSOR_V0) / (SENSOR_V1 - SENSOR_V0) * 100.0

    def close(self) -> None:
        self.valve.off()
        self.pump.off()
        self.vent.off()


class PiLights:
    """LED rings. ``settle_s``: after a ring switches ON, wait so camera auto exposure adapts
    before the first frame (otherwise the first frame is exposed for the dark scene)."""

    def __init__(self, settle_s: float = 0.3):
        from gpiozero import OutputDevice

        self._head = OutputDevice(PIN_LED_HEAD, initial_value=False)
        self._station = OutputDevice(PIN_LED_STATION, initial_value=False)
        self.settle_s = settle_s

    def _set(self, dev, on: bool) -> None:
        was = bool(dev.value)
        dev.value = on
        if on and not was and self.settle_s > 0:
            time.sleep(self.settle_s)

    def head(self, on: bool) -> None:
        self._set(self._head, on)

    def station(self, on: bool) -> None:
        self._set(self._station, on)

    def close(self) -> None:
        self._head.off()
        self._station.off()


class PiLid:
    def __init__(self):
        from gpiozero import Button

        self._sw = Button(PIN_LID, pull_up=True)

    def closed(self) -> bool:
        return self._sw.is_pressed


class PiGate:
    """Laser module at one end of the row, photodiode receiver module at the other, beam along the
    row centre line 4 mm above the MAX line. Blocked beam = something is stacked too high."""

    def __init__(self):
        from gpiozero import DigitalInputDevice

        self._rx = DigitalInputDevice(PIN_GATE, pull_up=False)

    def clear(self) -> bool:
        return bool(self._rx.value)


class PiCarry:
    """Carry-height sensor: the spare TCST2103 endstop board on the Z spine's left face, a flag on the z_plate. Its OUT
    reaches GPIO 6 (pin 31) through the I/O board's 10k series / 20k to GND divider (5 V board, 3.3 V input).
    HIGH = the flag is in the beam = the head is at least carry_sensor_c0 high. A cut lead reads LOW (the 20k pulls it
    down): sideways moves are refused, which is safe. A dead emitter or dirt in the slot reads HIGH, which is not: the
    runner therefore also requires LOW whenever the head is well below the trip height (every pick)."""

    SAMPLES = 3

    def __init__(self):
        from gpiozero import DigitalInputDevice

        self._rx = DigitalInputDevice(PIN_CARRY, pull_up=False)

    def blocked(self) -> bool:
        """Majority of three reads 1 ms apart: one noise spike on the 0.2 m lead must not stop (or pass) a check."""
        n = 0
        for i in range(self.SAMPLES):
            if i:
                time.sleep(0.001)
            n += bool(self._rx.value)
        return n * 2 > self.SAMPLES

    def close(self) -> None:
        self._rx.close()
