"""Raspberry Pi I/O: vacuum pump + valves, LED rings, vacuum sensor.

Wiring (see docs/WIRING.md): each load is switched by a logic-level MOSFET module from a Pi GPIO.
The vacuum sensor (XGZP6847A, -100..0 kPa, 0.5-4.5 V out at 5 V supply) feeds an ADS1115 ADC
through a 10k/20k divider, so the ADC never sees more than ~3 V.

Valve logic is fail-safe: both solenoid valves are normally closed. On power loss the cup
stays sealed by the check valve + reservoir, so a held slab is not dropped instantly.
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

ADS_ADDR = 0x48
DIVIDER = 2.0 / 3.0  # 20k/(10k+20k)
SENSOR_V0, SENSOR_V1 = 0.5, 4.5  # volts at -100 kPa .. 0 kPa (XGZP6847A "negative" range)


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
        v = raw * 4.096 / 32768 / DIVIDER
        return -100.0 + (v - SENSOR_V0) / (SENSOR_V1 - SENSOR_V0) * 100.0

    def close(self) -> None:
        self.valve.off()
        self.pump.off()
        self.vent.off()


class PiLights:
    def __init__(self):
        from gpiozero import OutputDevice

        self._head = OutputDevice(PIN_LED_HEAD, initial_value=False)
        self._station = OutputDevice(PIN_LED_STATION, initial_value=False)

    def head(self, on: bool) -> None:
        self._head.value = on

    def station(self, on: bool) -> None:
        self._station.value = on


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
