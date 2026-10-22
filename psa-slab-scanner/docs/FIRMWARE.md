# Firmware: FluidNC on the BTT Rodent

This page covers flashing FluidNC, loading `firmware/fluidnc/config.yaml`, checking it, and
testing every motor, switch and the contact probe before the Pi software takes over. Wiring is in
[WIRING.md](WIRING.md). The interface rules are in [CONTRACT.md](CONTRACT.md).

Confidence tags: **[Certain]** = read in a primary source (BTT's files, the FluidNC v4.1.1
source code), **[Likely]** = strong inference or several secondary sources, **[Guessing]** = a
gap I filled.

## Read this first

1. **Check the current-sense resistors before you plug in any motor.** BTT's documents
   disagree, and a wrong value overheats the motors.
   - The Rodent V1.1 manual says 75 mΩ, and a V1.1 owner reports parts marked "R075". [Certain
     that the V1.1 manual says so; Likely for real V1.1 boards]
   - The V1.0 schematic and BTT's `rodent.yaml` say 22 mΩ. [Certain]
   - `config.yaml` ships with `r_sense_ohms: 0.075`. If your board's resistors say "R022", change
     all four lines to `0.022`.
   - The dangerous mistake is setting 0.075 on a 22 mΩ board. The motors then get 3.4 × the set
     current: 3.4 A on X. [Certain, from the driver current formula]
2. **Use FluidNC v4.1.1 or newer.** [Certain] FluidNC puts itself in a config alarm on any key it
   doesn't know, so an older build may reject this file. BTT has shipped Rodents with old
   firmware, so reflash even a new board. [Likely]
3. **Never plug or unplug a motor while the board has 24 V.** It can destroy the driver.
   [Certain, standard for TMC drivers]
4. **The CAD needs a change before you build Z** (see [Open issues](#open-issues)). The Z
   carriage reaches the bottom of its rail at c = −4 mm, and probing needs about −8 mm.

## Why this board

The Rodent fits the job: [Certain, BTT manual and schematic]
- four TMC2160 drivers on SPI;
- 24–56 V motor input;
- optocoupled limit inputs with on-board 10 kΩ pull-ups;
- a USB-C port with a CH340K USB-serial chip;
- an official FluidNC config from BTT.

Two axes only need two drivers, so the extra drivers become plug-in spares (see below). I found no
reason to switch boards.

The cheaper MKS DLC32 would also run FluidNC, but its plug-in stepstick drivers and 3.3 V GPIO
endstops would need more parts for the same fail-safe wiring. [Likely]

## Board facts used by the config

| Item | Value | Source |
|---|---|---|
| MCU | ESP32 (V1.0: bare ESP32-D0WD-V3, V1.1: ESP32-WROOM-32U module with external antenna) | BTT manual [Certain] |
| Motor power input | **24–56 V DC**, screw terminal "GND / VCC" | BTT manual [Certain] |
| Driver sockets | Labelled X, Y, Z, E. STEP/DIR/EN go through an I2S shift register. | BTT manual table, `rodent.yaml` [Certain] |
| X socket | STEP I2SO.2, DIR I2SO.1, EN I2SO.0 | [Certain] |
| Y socket | STEP I2SO.5, DIR I2SO.4, EN I2SO.7 | [Certain] |
| Z socket | STEP I2SO.10, DIR I2SO.9, EN I2SO.8 | [Certain] |
| E socket | STEP I2SO.13, DIR I2SO.12, EN I2SO.15 | [Certain] |
| SPI chain | One chip-select (gpio.5). MOSI gpio.23, MISO gpio.19, SCK gpio.18. Chain order from MOSI: X, Y, Z, E. | `rodent.yaml` [Certain]; order also stated in a Marlin port PR [Likely] |
| Limit inputs (3-pin: signal, GND, V-Lim) | X-MAX gpio.35, Y-MAX gpio.34, Z-MAX gpio.33, E0-MAX gpio.32, **E1-MAX gpio.37 on V1.0 but gpio.39 on V1.1** | manual images V1.0 and V1.1, V1.0.2 schematic [Certain] |
| Probe input | gpio.36, "V-probe / GND / P-36" | manual [Certain] |
| Pull-ups | 10 kΩ to 3.3 V on GPIO 32–37 (V1.0.2 schematic). GPIO 34–39 have no internal pull resistor. | schematic [Certain]; ESP32 [Certain] |
| Limit input circuit | 1 kΩ from V-Lim to an EL357N opto LED, whose cathode is the signal pin. **Pulling the signal to GND turns the LED on, and the GPIO reads LOW.** Open = HIGH. | schematic [Certain] |
| Probe input circuit | The other way round. The signal pin drives the opto LED through 1 kΩ to GND, so the signal must be HIGH to read LOW. Optional 10 kΩ pull-up ("NPN" jumper). | schematic [Certain] |
| V-Lim / V-Probe voltage | Jumper: 5 V, 12 V or VCC. VCC is banned above 24 V. | manual [Certain] |
| VUSB jumper | Ties USB 5 V to the board's 5 V rail. **"Do not insert the jumper when the device is in use."** Only for flashing with no 24 V. | manual V1.0 image [Certain] |
| USB serial | CH340K, powered from the board's 3.3 V. It appears as `/dev/ttyUSB0`, by-id `usb-1a86_USB_Serial-if00-port0`. | schematic [Certain]; by-id name from a V1.1 Klipper port [Likely] |
| V-MOS outputs | gpio.12, gpio.2, gpio.4 (12–36 V, own input). **Not used.** The Pi switches the vacuum and lights. | manual [Certain] |

## What `config.yaml` sets

| | X | Z |
|---|---|---|
| Driver socket | **X** (motor0, chain 1) | **Z** (motor0, chain 3) |
| Spare socket, ganged | Y (motor1, chain 2) | E (motor1, chain 4) |
| steps/mm | 80 (GT2 20T, 1/16) | 400 (T8×8, 1/16) |
| Max rate / accel | 15000 mm/min, 2000 mm/s² | 6000 mm/min, 1200 mm/s² |
| Run / hold current | 1.0 A / 0.5 A | 0.8 A / 0.5 A |
| Homing | cycle 2, toward min, `$HX` alone blocked | cycle 1 (first), toward max |
| Position after homing | X = 22 (switch trips at about 19) | Z = 255 (switch trips at about 258) |
| Soft limits (machine mm) | **22 … 1253** | **−8 … 255** |
| Home / limit switch | X-MAX connector, gpio.35, NC, hard limit on | Z-MAX connector, gpio.33, NC, hard limit on |
| Contact probe | — | Y-MAX connector, gpio.34, active high, fail-safe |

**Other choices:**
- No Y axis is defined. FluidNC still reports three numbers (`MPos:x,0.000,z`), because it pads
  the axis count to 3 "since senders might assume 3 axes". [Certain, `Axes.cpp`] The software's
  status and `[PRB:]` parsers rely on that.
- No spindle, coolant, user outputs, OLED or SD card section.
- `idle_ms: 255` means the motors are never switched off, so Z cannot drift down.
- `must_home: true` keeps the machine in alarm until `$H` has run.

**Why the spare sockets are configured.** [Certain, FluidNC source comment on `spi_index`:
"every physical position in the chain must be represented by a motor entry, even unused ones, or
the chain's data alignment breaks"]
- FluidNC reads a TMC chip by clocking data through every chip behind it. It works out how many
  chips there are from the highest `spi_index` it knows.
- So the Y and E chips are given entries, as second motors (`motor1`) on X and Z. They step
  together with X and Z.
- **Leave them empty.** If the X or Z driver dies, move that motor's plug to Y or E and nothing
  else changes.
- **Never plug a second motor into Y or E.** It would move with X or Z.

**Where the travel numbers come from** (cad/layout.py and cad/model.py, October 2026):
- Pocket centres run from X = 42 to 1238.
- The X carriage leaves its rail when the cup is below X 12.7 or above 1267. The X bracket hits the
  idler and motor mounts at X 8 and 1266. [Certain, computed from the CAD]
- Z's top of travel is 250 (C_MAX). The Z carriage runs off the top of its rail at c = 280.6.
- If the rail lengths or pocket count change, recompute `max_travel_mm` and `mpos_mm` with the same
  margins.

## Step 0: board set-up (power off)

1. Read the board version on the silkscreen (V1.0 or V1.1). Read the marking on the big resistors
   next to each driver (R075 or R022), then set `r_sense_ohms` to match.
2. Set the jumpers:
   - SW_VCC (limit voltage): **5V**.
   - V-Probe: **5V**. The Probe connector is unused, but 5 V is the safe setting.
   - **NPN EN: off.**
   - **VUSB: off.**
   - **No DIAG jumpers.** They tie driver stall outputs onto the limit pins.
3. Fit the Wi-Fi antenna (V1.1 has a u.FL connector) only if you plan to use the web UI.

## Step 1: flash FluidNC

You need a laptop with Chrome or Edge, which have Web Serial. [Likely]

1. Power the Rodent from 24 V, or fit the VUSB jumper with 24 V **off**. Remove the jumper again
   after flashing.
2. Connect USB-C to the laptop. Windows may need the CH340 driver. [Likely]
3. Open the FluidNC web installer at `https://installer.fluidnc.com`. Pick the latest stable
   release (v4.1.1 or newer) and the **ESP32 "wifi"** build. Choose a fresh install, which erases
   the flash. [Likely]
4. If the installer can't connect, hold **BOOT**, tap **RESET**, release BOOT, then retry. Both
   buttons are on the board. [Certain]
5. Open a serial terminal at 115200 baud and tap RESET. You should see the FluidNC banner and
   startup messages. [Certain, FluidNC default baud]

## Step 2: load `config.yaml`

Use any one of these. All of them store the file in the ESP32's internal flash as `config.yaml`,
which is the default config name (`$Config/Filename`). [Certain]

**A. FluidTerm, on the laptop (easiest).** FluidTerm comes in the FluidNC release zip.
1. Run it and pick the Rodent's COM port.
2. Press **Ctrl+U**, pick `firmware/fluidnc/config.yaml`, and keep the destination name
   `config.yaml`. Ctrl+U sends the file over XMODEM. [Certain, `fluidterm.py`]
3. Press **Ctrl+R** to reset the board.

**B. Web UI over Wi-Fi.**
1. Join the board's access point: SSID `FluidNC`, password `12345678`. [Certain, defaults in the
   v4.1.1 source]
2. Browse to `http://192.168.0.1`.
3. Upload `config.yaml` with the flash file manager, then restart.

**C. From the Pi, headless** (later updates, without a laptop).
1. Install the tools: `pip install pyserial xmodem`.
2. Stop the slabscan software, then run:

```python
# upload_config.py  -  run on the Pi:  python3 upload_config.py /dev/ttyUSB0 firmware/fluidnc/config.yaml
import sys, time, serial
from xmodem import XMODEM
port, path = sys.argv[1], sys.argv[2]
s = serial.Serial(port, 115200, timeout=1)
time.sleep(3)                      # the ESP32 resets when the port opens; let it boot
s.reset_input_buffer()
s.write(b"$Xmodem/Receive=config.yaml\n")
time.sleep(0.5)
getc = lambda n, timeout=1: s.read(n) or None
putc = lambda data, timeout=1: s.write(data)
with open(path, "rb") as f:
    print("sent OK" if XMODEM(getc, putc).send(f) else "XMODEM FAILED")
s.write(b"$Bye\n")                 # restart FluidNC so it loads the new file
```

The command `$Xmodem/Receive` exists in v4.1.1 and is what FluidTerm sends. [Certain] The
script itself has not been run against a board. [Guessing]

**Once the config is in:**
- Turn the radio off: `$WiFi/Mode=Off`. [Certain, setting name] The default mode falls back to an
  open-to-anyone access point with a published password. Anyone in range could jog the machine.
- **Do not run `$CD=config.yaml`.** It overwrites the commented file with a bare dump. Plain `$CD`
  only prints the config.
- Runtime edits like `$/axes/x/soft_limits=false` last until the next restart. [Certain]

## Step 3: check that the config loaded

Send each command and compare with the expected result.

| Command | Expect | If not |
|---|---|---|
| `$SS` (startup log) | No `[MSG:ERR:` lines. An "Axis count 3" line. Four driver lines, each followed by "driver test passed". The I2SO and SPI bus lines. | "Ignored key …" means the key is unknown to your FluidNC version: update FluidNC. "TMC driver not detected" on all four means an SPI or 24 V problem. On one only, that driver is damaged. |
| `$CD` | Your values come back, e.g. `steps_per_mm: 80.000` under `x`. | Wrong file loaded: check `$Config/Filename` and `$LocalFS/List`. |
| `?` | `<Alarm\|MPos:0.000,0.000,0.000\|...>` before homing. Alarm is normal: `must_home`. | `<Idle` before homing means `must_home` was not read. |
| `$Limits` (send `!` to stop it) | A live line of active limit pins and `P` for the probe. **Nothing active at rest.** | See Step 5. |

The exact wording of startup lines varies by version, so check the meaning, not the exact text.
[Likely]

## Step 4: motor direction (one axis at a time)

Before homing, FluidNC's position is a made-up 0, which is outside the X soft range (22…1253). With
soft limits on, it would stretch or clip your test jogs. [Certain, `Cartesian::constrain_jog`]
Turn them off just for this test.

1. Power off. Move the carriage to the middle of the beam by hand, slowly. Turn the Z lead screw
   by hand until the cup is about 100 mm above an empty pad.
2. Power on. Keep a hand on the E-stop. Send:
   ```
   $/axes/x/soft_limits=false
   $/axes/z/soft_limits=false
   $X
   $J=G91 G21 X10 F600
   ```
   **The carriage must move 10 mm to the RIGHT**, toward the X motor end.
3. Send `$J=G91 G21 Z10 F300`. **The head must move UP 10 mm.**
4. If an axis runs backwards, power off and fix it one of two ways:
   - swap the two wires of ONE coil (A1↔A2) at the motor plug; or
   - add `:low` to that axis's `direction_pin` on **both** of its motors (for example
     `I2SO.1:low` and `I2SO.4:low` for X).
   Upload the file again.
5. Check distance: jog X +100 and measure. It must be 100 mm ± 0.5. If it's off by 2× or 0.5×,
   the pulley or microstep setting is wrong.
6. Restart (`$Bye` or the RESET button). The soft limits come back on.

## Step 5: switches and probe

Run `$Limits` and watch the live line while you do each step.

| Action | Expected | Why |
|---|---|---|
| Nothing touched | No X, no Z, no P | NC switches closed, probe slot clear |
| Press the X home switch | `X` appears in NegLimitPins | Switch opens, input goes high |
| Unplug the X switch at the board | `X` stays on | **Fail-safe check:** a broken wire must look like "pressed" |
| Press / unplug the Z top switch | `Z` appears in PosLimitPins | Same |
| Push the cup up about 3 mm by hand | `P` appears | Flag enters the slot |
| Unplug the probe at the board | `P` stays on | **Fail-safe check** |
| Cover the sensor's emitter side, or cut its 5 V | `P` stays on | **Fail-safe check** |

If any fail-safe row shows the pin as not active, **stop**. The switch or sensor is wired the
wrong way, or the module's LED circuit is feeding the input. Fix the wiring before you home.
WIRING.md, sections 6 and 7, shows the right way. The `?` report also lists active pins as
`|Pn:XZP` (standard Grbl). [Likely]

## Step 6: first homing

1. Put the head about halfway up, over an empty area. Hand on the E-stop.
2. Send `$H`.
   - **Z must go up first**, touch the switch, back off 3 mm and touch again slowly.
   - **Then X goes left** and does the same.
   - Then `?` shows `<Idle|MPos:22.000,0.000,255.000|...>`.
3. Repeat `$H` five times. After each one, jog to the same spot (`G90 G0 X42 Z240`) and check the
   cup lands on the same point (a pencil mark on the pad). Spread must be under 0.2 mm.
4. **Check that the switch positions match the numbers in the config.**
   - Jog until the cup is centred over pocket 0 at about Z 240. `?` should show X ≈ 42 ± 3.
   - If not, move the X switch, not the config. `calibrate x` corrects only the small remainder,
     and a large offset eats into the soft-limit margins.
   - Do the same for Z after `calibrate z`: `pad_trigger_c` must be between −4 and 0.

Homing takes up to about 40 s in the worst case. The software allows 60 s per command. [Certain,
arithmetic: 1354 mm at 50 mm/s plus 289 mm at 25 mm/s]

## Step 7: probe test with `G38.3`

Over the empty pocket 0, after homing:

```
G90 G21
G0 X42 Z30
G38.3 Z-6 F1200
```

**Expected:**
- the cup touches the pad and stops;
- `[PRB:42.000,0.000,<z>:1]`, then `ok`;
- `<z>` is about −2. That is the buffer squeezed 2 mm at the trip point.
- Repeat ten times. The spread of `<z>` should be under 0.1 mm. [Guessing on the spread; it
  depends on the flag and the pad]

**Other checks:**
- **Miss test:** `G0 Z30`, then `G38.3 Z25 F1200`. This ends with `[PRB:…:0]` and `ok`. G38.3
  does not alarm on a miss. [Certain, FluidNC `mc_probe_cycle`]
- **Fail-safe test:** unplug the probe and send `G38.3 Z20 F600`. You must get `ALARM:4` (probe
  already tripped at start), and nothing moves. [Certain, FluidNC `mc_probe_cycle`]
- **Soft-limit test:** `G38.3 Z-20 F600` must be refused, because −20 is below the −8 soft limit.
  [Likely: soft-limit alarm or error, depending on state]

## How the software talks to FluidNC

`software/slabscan/motion.py` (`GcodeMachine`) is a plain line-by-line Grbl sender.

**Connection**
- Opens the CH340 port at 115200 baud. Prefer `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`
  in `machine.toml`, because `ttyUSB0` can renumber.
- Waits 2 s, because opening the port resets the ESP32.
- Sends `$X`. The machine stays unhomed until `$H`.

**Commands**

| Purpose | Sent | FluidNC answers |
|---|---|---|
| Home | `$H`, then `G90`, `G21`, `G54`, `G92.1`. If `$#` shows a G54 offset, it also sends `G10 L2 P1 X0 Z0`. | `ok` after both homing cycles |
| Move | `G1 X… F…` or `G1 Z… F…`. Never Y. Moves are machine-frame numbers because G54 is zero. | `ok` when queued |
| Wait for done | `G4 P0`, then `?` polled until `<Idle\|MPos:x,y,z…>` | `Idle`. `Alarm` or `Door` raises MotionError. |
| Probe | `G38.3 Z<target> F1200` | `[PRB:x,y,z:1]` (hit) or `:0` (miss), then `ok` |
| Work offset | `$#` (reads `[G54:…]`) | All zeros after `home()` |

The probe report prints machine coordinates. [Certain, `report_probe_parameters`]

**What the software does not use**
- The vacuum, valves and lights are on the Pi's GPIO, not FluidNC. There are no `user_outputs`,
  so the `M64`/`M65` method in motion.py must not be called.
- Any `error:` or `ALARM:` reply raises `MotionError`, and the runner stops with the cup in a safe
  state.

**What the software must handle** (for the software owners):
- **E-stop = controller power off.** The E-stop cuts the Rodent's 24 V (WIRING.md §1), and the
  CH340 is powered from the board. So the serial device **disappears**, and pyserial raises
  `SerialException` rather than `MotionError`.
  - Catch that and stop with the message "controller lost power (E-stop?)".
  - After release, reconnect, wait for the FluidNC banner, and home again.
- **Boot time.** A fixed 2 s wait can be too short while FluidNC boots. Waiting for the startup
  banner (or retrying `$X` until `ok`) is more robust. [Likely]
- **Probe targets** must stay above Z = −8 (machine). `calibrate z` must not probe lower than
  about −7.
- `[PRB:…]` has three numbers before `:1`/`:0`, so the existing regex matches. [Certain]

## Open issues

1. **[Certain, CAD] The Z rail is too short at the bottom for probing.**
   - In `layout.py`, the Z carriage's lower edge meets the rail end at c = −4. That is
     `Z_SPINE_BOTTOM + 1 − Z_CARRIAGE_ABOVE_CUP` = 227 − 231.
   - Probing the bare pad trips at about c = −2, and the software probes up to 2 mm past that.
   - Fix in CAD before building: raise `Z_CARRIAGE_ABOVE_CUP` by about 12 mm (longer drop arm),
     or extend the rail lower. The carriage then stays on the rail to c = −12.
   - Top of travel still clears: 258 + 243 + 45.4 = 546 mm < 557 rail top.
   - Until then, the −8 soft limit lets a failed probe push the carriage up to 4 mm off the rail
     end.
2. **[Likely] Sense resistor value by board version.** See "Read this first". If BTT publishes a
   V1.1 config, compare it with this file.
3. **[Likely] Optical endstop boards differ.** Some have an indicator LED circuit that can hold
   the Rodent's opto on. The Step 5 fail-safe rows catch this, so never skip them.
4. **[Guessing] Z hold when unpowered.** DESIGN.md estimates the head stays put on E-stop
   (detent torque > back-drive). Test it: E-stop with the head at 240 and 200 g on the cup, then
   watch for 1 minute. If it creeps, add a friction brake or counterweight before unattended use.
