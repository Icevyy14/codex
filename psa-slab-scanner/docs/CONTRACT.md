# Interface contract (single source for docs, firmware, wiring and software)

Every document and file must agree with this page. If something here is wrong, fix it here first.

## Machine: SlabRail
- **Layout:** one straight row of 14 cells, 92 mm pitch, centres at X = 42 + 92·cell.
  - Cell 7 (X = 686) is the read station: an upward camera, no stack.
  - The other 13 cells are pockets 0–12, left to right.
    - Pocket 0 starts empty.
    - Pockets 1–11 hold up to 30 slabs each (330 total).
    - Pocket 12 is the exception pocket.
- **Run order:** stack k is moved slab by slab onto pocket k−1, so every stack ends up one pocket to the left. Each slab is read on the way.
- **Loading rules:** slabs go in **face-down**, with the **label end toward the front** (toward the operator).
- **Sizes:** pocket interior 84 × 139 mm.
  - Guide rods are 8 mm hardwood dowels, 218 mm tall above the pad.
  - The fill line (MAX) is 210 mm.
  - An overfill laser beam runs at 214 mm along the row centre line.
- **Axes (only two):**
  - **X:** belt-driven, GT2 20T pulley, 40 mm/rev, 80 steps/mm at 1/16 microstepping, on an MGN12 1300 mm rail on a 4040 beam.
  - **Z:** NEMA17 with an integrated 400 mm T8×8 lead screw, 400 steps/mm at 1/16, on an MGN12 330 mm rail on a 2040 spine.
- **Work coordinates:**
  - X = the cup axis position in layout mm.
  - Z = the cup-face height "c" above the pad top.
  - Key heights: C_SAFE_EMPTY = 228, C_SAFE_LOADED = 243, C_MAX = 250, STATION_READ_C ≈ 169.6.
- **Homing:**
  - X homes to MIN (left end) with a microswitch; then X0 = pocket-0 centre after calibration.
  - Z homes to MAX (top) with a microswitch; Z work zero is set by `calibrate z`.
- **Speeds:**
  - X: 15000 mm/min max, 2000 mm/s².
  - Z: 6000 mm/min, 1200 mm/s².
  - Probe: 1200 mm/min.
  - Motor current: X run 1.0 A, Z run 0.8 A (hold 0.5 A, to keep the head up).
- **Contact probe:** a slotted optical endstop on the cup's spring buffer (M10, 25 mm stroke), wired **fail-safe** so a cut wire reads as TRIGGERED.
  - It is the FluidNC `probe` pin.
  - Probing uses `G38.3` (no alarm on a miss) with a bounded target.

## CAD decisions after the build review (binding)
- **Rails on slots:**
  - The X rail centre is at Z = 410, on the 4040 beam's upper front slot. It is fixed with M3
    screws into M3 T-nuts.
  - The Z spine (2040) sits 10 mm to the LEFT of the cup axis, so the Z rail is in its right
    slot, on the cup axis.
- **Z carriage:** its bottom is 243 mm above the cup face. It stays on its rail down to
  c = −12 mm, which matches the firmware soft limit of Z −8 with margin.
- **Bed:** the plywood has 41 × 41 mm notches at the two upright positions. The uprights pass
  through to the base rail.
- **Drop arm (2020 × 236 mm):** drill two 5.5 mm cross holes, matching the head_foot and
  camera_bracket clamp holes.
- **Light roof:** OPTIONAL. Add it only if Phase 0 or the first runs show room-light glare on
  labels. If you do, it's black foam board on two 2020 posts bolted to the back of the uprights.
  The CAD model leaves it out by default.
- **Guide rods:** 82 dowels at 12 mm from each pocket corner, which leaves a 52 mm finger gap
  front and back.

## Controller
- **Board:** BTT Rodent V1.x (V1.1 assumed) running FluidNC v4.1.1 or newer. BTT's official
  `rodent.yaml` is the base.
  - Set `r_sense_ohms` to the board's resistor marking: R075 → 0.075, R022 → 0.022.
- **Connection:** CH340 USB serial at 115200 baud to the Raspberry Pi: `/dev/ttyUSB0`, by-id
  `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`.
- **Unused features:** no Y axis is defined, and no spindle or coolant pins are used. FluidNC
  still reports three axes (`MPos:x,0.000,z`).
- **Driver sockets:** X motor → socket X, Z motor → socket Z. Sockets Y and E are configured as
  ganged spares for X and Z, because the SPI chain needs all four. Leave them empty.
- **Inputs, all fail-safe (a cut wire reads as triggered):**
  - X home switch (NC) → X-MAX connector, gpio.35.
  - Z top switch (NC) → Z-MAX connector, gpio.33.
  - Optical contact probe → **Y-MAX connector, gpio.34** (not the board's Probe connector).
- **Soft limits (machine mm):** X 22…1253, Z −8…255.
  - After homing: X = 22, Z = 255.
  - Probe targets must stay above Z −8.
  - CAD must keep the Z carriage on its rail down to c = −12.
- **E-stop:** cuts the Rodent's 24 V, so FluidNC reboots and the USB serial device disappears.
  The software must treat a lost port as a stop, then reconnect and home again.
- **Firmware files:** `firmware/fluidnc/config.yaml`. Bring-up steps: `docs/FIRMWARE.md`.
- **Wiring:** `docs/WIRING.md` and `docs/img/wiring.svg`.

## Raspberry Pi 5 (4 GB), Raspberry Pi OS Bookworm 64-bit, Python 3.11
- **GPIO (BCM numbering), each output driving a logic-level MOSFET module:**
  - 17 = vacuum pump (24 V)
  - 27 = vacuum valve, normally-closed 2/2 (24 V)
  - 22 = vent valve, normally-closed 2/2 (24 V)
  - 23 = head LED ring
  - 24 = station LED ring
- **GPIO inputs:**
  - 25 = optional lid/door switch to GND (internal pull-up)
  - 5 = overfill beam receiver output (HIGH = beam received)
- **I2C1 (GPIO 2/3):** ADS1115 at 0x48.
  - Its A0 reads the XGZP6847A vacuum sensor (−100…0 kPa, 0.5–4.5 V at 5 V supply) through a 10k/20k divider.
- **Cameras:**
  - Head: USB UVC 8 MP IMX179 board with an M12 3.6 mm lens, manual focus, looking down at the held slab's back from 140 mm.
  - Station: Raspberry Pi Camera Module 3 (standard) on CSI port 0, looking up at the held slab's front from 140 mm.
- **Lighting:** both cameras use a ≈50 mm LED ring around the lens, plus a black foam-board "light roof" over the machine.

## Software (repo folder `psa-slab-scanner/software`)
- **Package:** `slabscan/`
  - `certs`, `decode`, `sim`, `runner`, `simworld`, `motion`, `hw`, `camera`, `config`, `results`, `psa_api`
- **Config:**
  - `config/machine.toml` is generated by `python -m tools.gen_config` from `cad/layout.py`.
  - `config/calibration.toml` holds the values written by the calibrate commands.
- **CLI:** `python -m slabscan <command>`
  - `selftest`: GPIO, vacuum sensor, pump and valves, both cameras, controller connection, beam gate.
  - `home`
  - `jog`: interactive.
  - `calibrate z`: probes the bare pad of pocket 0 and writes `pad_trigger_c`.
  - `calibrate x`: operator centres the awl over pocket 0 and pocket 12 and writes `offset_x` plus a scale check.
  - `focus head|station`: live sharpness and decode score to set focus.
  - `mark`: drives the awl to every cell for the drill template.
  - `run [--name NAME] [--front-photo always|fallback]`
  - `resume BATCH_DIR`
  - `sim [--slabs N]`: full simulated batch, no hardware.
  - `web [--port 8080]`: phone-friendly start/stop/progress page and CSV download.
- **Outputs:** `batches/<id>/certs.csv`, `certs.txt`, `summary.json`, `journal.jsonl`, `images/`.
- **Enrichment (optional, later):** `python -m tools.enrich batches/<id>` (PSA API, quota-metered).
- **Graders:** PSA and CGC are read and stacked normally. Other graders go to pocket 12.

## Budget
Hard cap $2,000 total. Target $1,000–1,400 including about 10% spares and shipping. The user has school 3D printers and mechatronics instructors.
