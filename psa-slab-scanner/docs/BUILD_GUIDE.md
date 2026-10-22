# SlabRail build guide

Step by step, from the first camera test to the first batch of real slabs. It is written for a
tech-school student working with mechatronics instructors. Interfaces (pins, axes, paths) come
from [CONTRACT.md](CONTRACT.md). Wiring is in [WIRING.md](WIRING.md), firmware in
[FIRMWARE.md](FIRMWARE.md), parts in [BOM.md](BOM.md), and the software in
[../software/README.md](../software/README.md). Day-to-day use is in [OPERATING.md](OPERATING.md).

Confidence tags: **[Certain]** = read in the CAD, the code, a datasheet, or tested in the
simulator. **[Likely]** = strong inference or several secondary sources. **[Guessing]** = a gap I
filled. Every time estimate is **[Guessing]**.

## Read this first

- **Phase 0 costs about $300, not $100, if you buy the Raspberry Pi.** [Likely] In October 2026 a
  Pi 5 4 GB costs about $110 by itself (BOM.md). Borrow a school Pi 4 or Pi 5 for Phase 0 and it
  drops to about $150. Buy your own Pi only after Phase 0 says GO.
- **The full machine is above your target.** [Likely ±15%] The BOM comes to about $1,697, about
  $1,440 if the school supplies its usual shop stock, and about $1,350 with the lean swaps. The
  target was $1,000–1,400 and the hard cap is $2,000.
- **Nothing here has moved a real slab yet.** [Certain] The CAD passes its clearance checks and the
  software passes its tests against a simulator. Real labels, the real cup and real wiring are
  untested. That is why Phase 0 comes first and section 13 has six tests to pass before you trust
  the machine with inventory.
- **Plan on 60–85 hours of hands-on work over 6–10 weeks**, plus about 30 hours of printer time.
  [Guessing] The project README says 40–60 hours. I think that is low once drilling 82 rod holes,
  the wiring and the acceptance tests are counted.
- **The CAD and BOM have small gaps you fix during the build.** [Certain, from reading the CAD
  and BOM] Each one is handled where it comes up:

| Gap | Where it is handled |
|---|---|
| The gate posts are modelled with their foot at pad-top height, but they stand on the bare plywood, 3 mm lower. The beam would sit at 211 mm instead of 214. | §5.9 |
| The `awl_adapter` insert hole is 5.0 mm. An M5 heat-set insert needs a bigger hole (about 6.4 mm for common inserts). | §3.4 |
| The drop arm is drawn 3 mm into `head_foot`'s socket floor, so its cross holes go at 19 mm and 84 mm from the arm end, not 22 and 87. | §7.5 |
| The probe flag (the tab that moves into the optical sensor) is not in the CAD. BOM.csv has only the strip to make it from. | §7.6 |
| The Phase 0 top bridge's post holes go right through, so nothing sets its height. | §1.5 |
| The CAD has no brackets, and the bed covers the base-rail tops where the upright brackets would go. | §4.3 |
| The SMC buffer in the BOM is the rotating type ("J"). The flag needs the non-rotating type ("K") or an anti-rotation guide. | §2, §7.6 |

## Contents

0. [What you're building](#0-what-youre-building)
1. [Phase 0: camera and cup test](#1-phase-0-camera-and-cup-test-go--no-go)
2. [Ordering](#2-ordering)
3. [Printing](#3-printing)
4. [Frame](#4-frame)
5. [Bed and guide rods](#5-bed-and-guide-rods)
6. [X axis](#6-x-axis)
7. [Z axis and head](#7-z-axis-and-head)
8. [Vacuum plumbing](#8-vacuum-plumbing)
9. [Electronics](#9-electronics)
10. [Firmware](#10-firmware)
11. [Software install](#11-software-install)
12. [Calibration](#12-calibration)
13. [Acceptance tests](#13-acceptance-tests-before-real-slabs)
14. [First real batch](#14-first-real-batch-supervised)
15. [Troubleshooting](#15-troubleshooting)

---

## 0. What you're building

SlabRail is one straight row of 14 cells under one gantry beam.

- **Cells:** 92 mm apart, centres at X = 42 + 92·cell.
  - Cell 7 (X = 686) is the read station, an upward camera.
  - The other 13 cells are pockets 0–12, left to right.
- **Loading:** pockets 1–11 hold up to 30 slabs each, face-down. Pocket 0 starts empty. Pocket 12
  is the exception pocket.
- **Run:** a suction cup on a two-motor gantry moves every stack one pocket to the left, one slab
  at a time. It reads each slab's label on the way and writes `certs.csv`.

![SlabRail, isometric](img/machine_iso.png)

![SlabRail, front](img/machine_front.png)

**How a run looks:** loaded, then the first transfer. The whole sequence, with all four frames, is
in [OPERATING.md §4](OPERATING.md#4-what-the-machine-does).

![Loaded](img/storyboard_1_loaded.png)

![First transfer](img/storyboard_2_first_transfer.png)

| Item | Value | Source |
|---|---|---|
| Footprint | 1416 × 290 mm bed, about 0.65 m tall | `cad/model.py` [Certain] |
| Motors | X: NEMA17 on a GT2 belt. Z: NEMA17 with a 400 mm T8×8 lead screw. | CONTRACT [Certain] |
| Rails | X: MGN12 1300 mm on a 4040 beam. Z: MGN12 330 mm on a 2040 spine. | CONTRACT [Certain] |
| Pocket | 84 × 139 mm inside, made by 8 mm dowels 218 mm tall | `cad/layout.py` [Certain] |
| Capacity | 11 × 30 = 330 PSA slabs | [Certain] |
| Cycle time | about 11 s per slab in the simulator, so about 1 hour for 330 | software README [Guessing until measured] |

### 0.1 Build order and time

The section numbers follow the parts of the machine, but the real order is different in one
place. The rod holes are drilled *by the machine itself* (the head carries an awl that aligns the
drill template), so §5 is split: 5A now, 5B after the machine moves (§12).

| # | Step | Section | Hands-on | Printer / waiting | Instructor needed |
|---|---|---|---|---|---|
| 1 | Phase 0A: camera test | §1 | 5 h | 9 h print | no |
| 2 | Phase 0B: cup bench test | §1.10 | 6–8 h | 24 h test | **yes: mains wiring** |
| 3 | Order the machine parts | §2 | 1 h | 1–4 weeks delivery | no |
| 4 | Print the machine parts | §3 | 3 h | about 22 h | no |
| 5 | Frame | §4 | 4–6 h | | **yes: squaring** |
| 6 | Bed, part A (cut, notch, bolt down, cut pads) | §5A | 3–4 h | | for power-tool rules |
| 7 | X axis | §6 | 4–5 h | | helpful for the dial indicator |
| 8 | Z axis and head | §7 | 4–6 h | | no |
| 9 | Vacuum plumbing (finish) | §8 | 2–3 h | | no |
| 10 | Electronics | §9 | 10–15 h | | **yes: mains, crimp review, first power-up** |
| 11 | Firmware | §10 | 2–3 h | | first homing: yes |
| 12 | Software | §11 | 1–2 h | | no |
| 13 | Bed, part B: mark, drill, glue rods, pads | §5B | 8–12 h | 24 h glue cure | for power-tool rules |
| 14 | Calibration | §12 | 2–3 h | | no |
| 15 | Acceptance tests | §13 | 6–8 h | about 3 days elapsed | first E-stop test: yes |
| 16 | First real batch | §14 | 2 h | | no |
| | **Total** | | **about 60–85 h** | | |

### 0.2 Cost

From [BOM.md](BOM.md). No price is a live checkout price. [Certain that they are search-extract
prices dated 2023 to August 2026]

| | Cost |
|---|---:|
| Order 1: Phase 0 parts (Pi, cameras, rings, the whole vacuum system, PSU, switching) | ≈ $860 |
| Order 2: the machine (frame, motion, bed, controller, sensors, cables) | ≈ $840 |
| **Full list incl. 10% allowance** | **≈ $1,697** |
| With school shop stock (filament, wire, glue, fuses, screws) | ≈ $1,440 |
| Lean (also generic valves and Home Depot plywood) | ≈ $1,352 |
| Optional light roof, only if Phase 0 shows glare (conditional BOM lines) | + ≈ $37 |

**Split order 1 further than the BOM does:** buy the Phase 0A camera parts first (about $300, or
about $150 with a borrowed Pi). Buy the vacuum half only after the cameras pass. [Guessing on the
saving; the arithmetic is in §1.1]

---

## 1. Phase 0: camera and cup test (go / no-go)

**Why:** the two riskiest unknowns are (a) whether the cameras read *your* labels, and (b)
whether the cup marks a slab. Both can be tested on a bench for a fraction of the machine's cost.
If either fails, you have not bought any motion parts.

### 1.1 What Phase 0A needs

| Part | From | Cost |
|---|---|---:|
| Raspberry Pi 5 4 GB, 27 W PSU, 64 GB microSD, Active Cooler | BOM, or borrow a school Pi | $143 (or $0) |
| Camera Module 3 (standard) + 500 mm Pi 5 cable | BOM | $27.50 |
| ELP 8 MP IMX179 USB camera, 3.6 mm M12 lens | BOM | $66 |
| Two 12 V COB LED rings, about 60 mm | BOM | $12 |
| 12 V DC wall adapter, 1 A or more (not in the BOM) | any | about $10 [Guessing] |
| Two 2020 × 312 mm extrusion posts | BOM (or school scrap) | $12 |
| M2 screw kit; 4 × M5×10 screws + 4 × M5 slot-6 T-nuts | BOM / school stock | $8 |
| Printed: `phase0_base`, `phase0_tray`, `phase0_top` | §3 | school filament |
| **Total** | | **≈ $280 + 10% ≈ $300**, or **≈ $150** with a borrowed Pi |

- **Why the 12 V adapter:** it powers the LED rings without any mains wiring, because the
  `phase0` tool leaves the lights on and never switches them. [Certain, `tools/phase0.py`] The
  rings and the cameras are the only powered parts in Phase 0A.
- **With a Pi 4:** use the 15-pin camera cable that ships with the Camera Module 3, not the Pi 5
  cable. [Likely]

### 1.2 Measure five of your slabs (15 min)

The CAD's slab size is in `cad/dims.py`: 80.3 × 135.5 × 6.6 mm nominal, design maximum
82.6 × 136.5 × 7.0. Use calipers to measure five slabs from your stock, including the newest and
the oldest holders.

- **Width over 83.0 mm** or **length over 137.0 mm:** stop. The pockets (84 × 139) are too tight for
  them, so the CAD must change before anything is printed. [Certain, from `layout.py` play of
  ±1.85 / ±1.75 mm]
- **SGC holders are about 86 mm wide and do not fit at all.** [Likely, `layout.py` comment] Measure
  one if you deal SGC.

### 1.3 Print the jig (about 9 h printer time)

Print `phase0_base`, `phase0_tray` and `phase0_top` in black PLA or PETG (settings in §3). Black
matters around the station camera, because it cuts stray light.

### 1.4 Set up the Pi (1–1.5 h)

Do §11.1–11.4 now: the operating system, copying the repository, and `setup_pi.sh`. Phase 0 uses
the same software as the machine.

### 1.5 Assemble the jig (1 h)

![Phase 0 jig](img/phase0_jig.png)

1. Screw the Camera Module 3 to the base's camera mast with four M2 screws. Lead the ribbon out of
   the cable slot. Use the 500 mm cable to the Pi's CAM/DISP 0 port, fitted with the Pi off.
2. Put one LED ring in the base's ring seat around the lens.
3. Push the two 2020 posts into the base sockets. Fix each with an M5×10 screw through the socket's
   cross hole into a T-nut in the post's slot.
4. Slide the tray onto the posts. Set the **tray ledge top 140 mm above the station lens front**
   (± 2 mm), then fix both clamps with M5 screws and T-nuts. [Certain, `model.py`: slab front at
   lens + 140]
5. Fit the ELP camera board to the top bridge with four M2 screws.
   - The CAD assumes a 32 mm square hole pattern. Measure your board first; if it differs,
     drill new holes. [Guessing in the CAD]
   - Put the second LED ring in the bridge's ring seat.
6. **The top bridge has no stop.** [Certain, CAD: its post holes go right through] Slide it down
   the posts until the head lens front is **140 mm above the top face of a slab lying in the tray**
   (± 2 mm). Hold it there with a spring clamp or a 2020 corner bracket under each end.
7. Plug the ELP camera into a black USB 2.0 port. Power both rings from the 12 V adapter (ring +
   to adapter +).

### 1.6 Focus both cameras (30 min)

Put one slab in the tray **face-down, label end toward you** (the finger-notch side), exactly as it
will sit in the machine.

```bash
cd ~/psa-slab-scanner/software && source .venv/bin/activate
python -m slabscan focus head --no-motion              # turn the M12 lens; watch the score peak; lock the lens nut
python -m slabscan focus station --no-motion --save    # sweeps LensPosition, saves the best one to config/calibration.toml
```

- **Head:** turn the lens slowly past the peak and come back to it. The line shows `READ …` when
  something decodes. Lock the lens nut once you are at the peak.
- **Station:** note the recommended LensPosition. The machine's station uses the same 140 mm
  distance, so the value carries over. [Certain, CAD]

### 1.7 Scan 30–50 of your own slabs (1–2 h)

```bash
python -m slabscan phase0 --out phase0_results --lens-position 7.1   # use the value focus station printed
```

For each slab the tool asks you to type the printed cert number, then saves both images and what
each camera decoded. **Type the cert every time.** The typed number is how it catches a *wrong*
read, which is the failure that matters.

**Include in the 30–50:**
- new labels (2024+, 9-digit certs) and old ones (8-digit);
- at least 3 labels from before 2017 (no back QR) and, if you have them, from before December 2015
  (no back barcode) [Certain, RESEARCH.md label eras];
- the 2024+ holder and the older holder;
- 3–5 CGC slabs;
- scratched or scuffed labels and holders;
- one slab with a visible ceiling-light reflection, to check the light-roof question.

### 1.8 Record what the labels actually encode

Open `phase0_results/phase0.csv` and `phase0_report.txt`. Fill this in and keep it with the
machine: it settles the open questions in RESEARCH.md.

| Question | Where to look | Your answer |
|---|---|---|
| Back QR payload format (e.g. `https://www.psacard.com/cert/<n>`) | `back_reads` column, `QRCode:` entries | |
| Front barcode symbology (ITF expected) | `front_reads`, the part before `:` | |
| Digits in the front barcode for a 9-digit cert (10 = padded or check digit) | `front_reads` | |
| ITF format learned | report line `ITF format learned:` (`zero_pad` or `check_digit`) | |
| CGC QR payload | `back_reads` for CGC slabs | |
| Any prefix or suffix around the cert | raw payloads | if yes, set `custom_regex` (§11.5) |
| Time per side (`back_ms`, `front_ms`) | CSV | replaces the [Guessing] frame times in `cli.py` |

### 1.9 The gate

| Result | Decision |
|---|---|
| `WRONG certs vs what you typed` is **0**, and `confident read (ok)` is **≥ 95 %** | **GO** [Certain: the tool's own criteria] |
| Any wrong cert at all | **NO-GO.** One silent misread is worse than 20 unread slabs. Send `phase0.csv` and the images for tuning before buying anything else. |
| ok below 95 % but no wrong certs | **Hold.** Look at the failing images. Typical fixes: refocus, move the ring, block room light. Then run again. |
| Back camera fails on most post-2017 labels | **Hold.** Every one of those would need the station detour (+3–5 s each). Fix the head image first. [Likely] |
| Glare spots over the label in the head images | Plan to build the optional light roof (CONTRACT). |

### 1.10 Phase 0B: cup bench test (after 0A passes)

**What it proves:** the cup seals on your holders, the valves hold, and the cup leaves no mark.
**Parts:** the rest of order 1, i.e. the vacuum system, the XGZP6847A sensor, the ADS1115, the
MOSFET modules and the 24 V supply.

**Instructor:** yes. This is the first mains wiring (IEC inlet → Mean Well LRS-150-24). Have it
checked before the first plug-in (WIRING.md §1.1 and §14 steps 1–4).

1. **Build the bench subset of the electronics** from WIRING.md:
   - power: §1.1 mains, F2 fuse, and the 24 V load bus;
   - switching: Q1–Q3, the pump and both valves (§4);
   - the I/O board with the sensor and ADS1115 (§5).
   Every wire goes into the machine later unchanged. (4–6 h)
2. **Plumb it** as in §8, with the cup and buffer held in a bench vise. (2 h)
3. In `config/calibration.toml` add `overfill_gate = false` for now (no beam yet). Then:
   ```bash
   python -m slabscan selftest -i
   ```
   - The controller line FAILS here. That's expected: the Rodent is in order 2. So does the LED
     ring line if Q4/Q5 aren't wired yet.
   - It walks you through pressing a slab on the cup: **seal**, **leak** (valves shut) and **vent**.
4. **Pass:**
   - `seal` PASS: −35 kPa or better, reached in the time shown. [Certain: `vac_seal_kpa`]
   - `leak` below 1 kPa/s. selftest passes anything under 2.5 kPa/s, but §13.4 needs the slab to
     hang on for a minute. [Guessing on the target]
   - `vent` PASS.
   - Do it on 5 different slabs, both holder generations.
5. **24 h static mark test on a junk slab:**
   1. Photograph the junk slab's back under raking light: a phone torch held almost flat to the
      surface, about 10–20°, in a dim room.
   2. Lay the slab face-down on a soft cloth on a block under the vise. Bring the cup (held in the
      vise, pointing down) onto the slab's back centre until the buffer is pushed in about 2 mm.
   3. Seal it and shut the valves, so it stays sealed with the pump off:
      ```bash
      pinctrl set 22 op dl; pinctrl set 17 op dh; pinctrl set 27 op dh; sleep 3; pinctrl set 27 op dl; pinctrl set 17 op dl
      ```
   4. Leave it 24 h.
   5. Vent: `pinctrl set 22 op dh; sleep 1; pinctrl set 22 op dl`. Photograph the same spot the
      same way.
   - `pinctrl` is the Bookworm GPIO tool WIRING.md §15 uses. [Likely] Pins: 17 pump, 27 vacuum
     valve, 22 vent valve. [Certain, CONTRACT]
6. **Gate:**
   - **No ring, haze or residue that survives a dry microfiber wipe → GO.** Order the machine.
   - Anything that needs more than a dry wipe → try the Schmalz HT1 cup (BOM conditional line)
     and repeat.

---

## 2. Ordering

Use [BOM.md](BOM.md) and [BOM.csv](BOM.csv). Order 2 is everything not marked "PHASE 0". Get the
Misumi extrusion quote first, because it moves the total most (BOM.md).

BOM.csv already has the parts this guide uses: the 236 mm drop arm, the Adafruit #5648 MOSFET
modules, bare SPDT microswitches, the 1 A / 3 A / 5 A branch fuses, 2.2 kΩ resistors and 100 nF
capacitors, the I/O perfboard, mains and earth wire, and the probe-flag strip. [Certain, BOM.csv]

**Check these lines when you order:**

| BOM line | What to do | Why |
|---|---|---|
| SMC cup + buffer `ZPT25UUJ25-B5-A10` | Ask the SMC configurator for the **non-rotating** buffer, the same code with **K** in place of **J**, if it exists with a 25 mm stroke | Distributor listings decode J = rotating and K = non-rotating. [Certain for the letters; Guessing whether that exact code is orderable] A rotating rod lets the probe flag swing into the sensor (§7.6). |
| Light roof (foam board, tape, 2 × 2020 posts, qty 0) | Buy only if Phase 0 showed glare (§1.9) | The roof is optional (CONTRACT). |
| 12 V wall adapter | Optional, for Phase 0A. Not in the BOM. | §1.1 |

**Lead times** [Guessing]: Amazon 2–5 days, Misumi about 1 week, AliExpress 2–4 weeks, the SMC
buffer can be weeks. The Rodent showed sold out at BIQU US (BOM.md); check the BIQU AliExpress
and Amazon stores.

**When the parts arrive:**
- check that the 4040 profile is 20-series slot 6 with **two slots per face**;
- check that the Z motor's lead screw is **T8×8** (8 mm lead), not T8×2;
- count the balls in the MGN12 carriages before you slide them anywhere (§6.1).

---

## 3. Printing

### 3.1 Printer and material

- **Bed size:** ≥ 230 mm in one direction (or diagonally), for the 226 mm gate posts and the
  214 mm fill gauge. [Certain, `print_list.json` sizes]
- **PETG**, 0.4 mm nozzle, 0.2 mm layers. Prusa's PETG settings are 230 °C nozzle on the first
  layer and 240 °C after, with the bed at 85 °C then 90 °C, on a powder-coated or textured sheet.
  [Certain, Prusa knowledge base as quoted in search results] Use your filament maker's numbers if
  they differ.
- **Don't print PETG on a bare smooth PEI sheet.** It can bond hard enough to tear the sheet.
  [Certain, Prusa] Use a textured sheet, or a glue-stick release layer.
- **Part cooling:** 30–50 % for PETG. [Likely]
- **Colour:**
  - matte black for `camera_bracket`, `station_mount` and the Phase 0 jig, to cut stray light near
    the cameras;
  - any colour for the rest.

### 3.2 Parts

STL files are in `cad/out/printed/`. Times are for a classic 0.2 mm printer (Prusa MK3-class,
Ender 3) running about 5 mm³/s, estimated from each part's volume. Fast printers (Bambu, MK4) take
roughly half. [Guessing]

| STL | Qty | Material | Orientation | Walls / infill | Supports | Time |
|---|---:|---|---|---|---|---:|
| `phase0_base` | 1 | PLA/PETG black | as exported (plate down) | 3 / 25 % | none | 5 h |
| `phase0_tray` | 1 | PLA/PETG | as exported | 3 / 25 % | none | 2 h |
| `phase0_top` | 1 | PLA/PETG | as exported (ring up) | 3 / 25 % | none | 2 h |
| `station_mount` | 1 | PETG black | as exported (base plate down) | 3 / 25 % | none; the cable slot bridges | 2.7 h |
| `x_motor_mount` | 1 | PETG | as exported (foot down) | 5 / 40 % | none | 1.4 h |
| `x_idler_mount` | 1 | PETG | as exported (foot down) | 5 / 40 % | none | 0.5 h |
| `x_bracket` | 1 | PETG | as exported: flat plate down, belt-clamp tab up | 6 / 50 % | none | 3.7 h |
| `z_motor_mount` | 1 | PETG | as exported: motor face down, tab up | 5 / 40 % | none | 1 h |
| `z_plate` | 1 | PETG | as exported: carriage face down, nut shelf up | 6 / 50 % | none | 1.9 h |
| `head_foot` | 1 | PETG | as exported | 5 / 40 % | none | 1.3 h |
| `camera_bracket` | 1 | PETG matte black | as exported | 4 / 40 % | **yes**: under the ring and shelf; brim | 1.1 h |
| `gate_post_L`, `gate_post_R` | 1 + 1 | PETG | **see note** | 4 / 30 % | see note | 1.7 h each |
| `drill_template` | 1 | PETG (or PLA) | as exported (plate down) | 4 walls, 50 %, bosses solid | none | 3.6 h |
| `awl_adapter` | 1 | PETG | as exported | 100 % | none | 0.2 h |
| `fill_gauge` | 2 | PLA | **rotate to lie flat** (4 mm tall) | 3 / 20 % | none | 0.4 h each |
| **Total** | | | | | | **≈ 31 h** (≈ 22 h without Phase 0) |

**Notes**
- **Gate posts:** the exported orientation leaves the long bar floating 17 mm above the bed (the
  foot hangs below it), so it needs supports along its whole length. [Certain, measured on the
  STL] It's better to stand each post upright on its foot if your printer has ≥ 230 mm of Z
  height. Use a 5 mm brim and slow down the last 50 mm. If you can't, print as exported with tree
  supports from the build plate.
- **Fill gauge:** exported standing on its 4 mm edge, as a thin fin. Lying flat it prints in a
  third of the time and the notches still go through. [Certain, from the STL]
- **`camera_bracket`:** it touches the bed with only 1.6 cm² and has 24 cm² of overhang. [Certain,
  measured] Use a brim and supports.

![Printed parts](img/printed_parts.png)

### 3.3 Check before you print the head and camera parts

Measure the real parts first, because the CAD guessed these [Guessing in the CAD, BOM.md open gap 4]:

| Part | CAD value | Fits into |
|---|---|---|
| ELP camera board hole pattern | 32 × 32 mm, M2 | `camera_bracket`, `phase0_top` |
| Optical endstop board hole spacing | 19 mm, M3 self-tapping | `head_foot` sensor post |
| Head LED ring OD/ID | seat 46–56 mm | `camera_bracket`, `phase0_top` |
| Station LED ring OD/ID | seat 52–60 mm | `station_mount`, `phase0_base` |
| Camera Module 3 holes | 21 × 12.5 mm, M2 | `station_mount`, `phase0_base` |

If anything differs, fix the CAD and re-export (`cd cad && python build.py` on a PC with
CadQuery), or drill new holes by hand.

### 3.4 After printing

- **Clearance holes:** run a 3.4 mm drill through every M3 clearance hole and a 5.5 mm drill
  through every M5 hole by hand. Printed holes come out undersize. [Likely]
- **`awl_adapter`:**
  - **The insert hole is drawn 5.0 mm, too small for an M5 heat-set insert.** [Certain, CAD]
    Drill it to the size your insert's maker gives (about 6.4 mm for common M5 inserts [Likely])
    before you set the insert with the iron.
  - Press a 3 mm hardened pin (or a 3 mm drill-bit shank, ground to a point) into the 3.1 mm
    bottom hole with a drop of CA glue.
  - The point must be on the cup axis within 0.3 mm. Spin the adapter on the buffer and watch the
    tip: it should not wobble visibly.
  - **Check how your cup pad attaches to the buffer.** The adapter assumes an M5 male stud where
    the pad goes. [Guessing] If your buffer differs, make an equivalent: a sleeve that fits where
    the pad goes, carrying a 3 mm point on the axis.
- **Test-fit before assembly:**
  - each MGN12 carriage's four M3 screws through `x_bracket` and `z_plate`;
  - the T8 nut in the `z_plate` shelf;
  - the M10 buffer body through `head_foot`;
  - both LED rings in their seats.

---

## 4. Frame

### 4.1 Cut list

From `cad/out/cut_list.csv` [Certain]. Misumi cuts to ±0.5 mm with square ends (BOM.md).

| Profile | Use | Length | Qty |
|---|---|---:|---:|
| 2040 | base rail, lying flat under the bed | 1416 | 2 |
| 4040 | upright | 401 | 2 |
| 4040 | X beam, on top of the uprights | 1416 | 1 |
| 2040 | Z spine | 340 | 1 |
| 2020 | head drop arm | 236 | 1 |
| 2020 | Phase 0 jig posts (not in `cut_list()`) | 312 | 2 |
| 2020 | optional rear brace stock (§6.7) | 600 | 1 |
| 8 mm hardwood dowel | guide rod | 236 | 82 |
| 18 mm plywood | bed | 1416 × 289.5 | 1 |

### 4.2 Where everything sits

Machine coordinates in mm, from `cad/model.py` [Certain]:
- X runs left to right along the row; Y runs front (−) to back (+); Z = 0 is the pad top surface.
- The bed top is at Z = −3, and the base rails' bottom is at Z = −41.

| Part | X | Y | Z |
|---|---|---|---|
| Front base rail (2040 lying flat) | −68 … 1348 | −87.5 … −47.5 (30 mm in from the bed's front edge) | −41 … −21 |
| Back base rail | −68 … 1348 | 107 … 147 | −41 … −21 |
| Bed plywood | −68 … 1348 | −117.5 … 172 | −21 … −3 |
| Left upright (4040) | −68 … −28 | 107 … 147 (on the back base rail) | −21 … 380 |
| Right upright | 1308 … 1348 | 107 … 147 | −21 … 380 |
| X beam (4040) | −68 … 1348 | 107 … 147 | 380 … 420 |
| X rail (MGN12) | −10 … 1290 | front face of the beam | centre 410, upper front slot |

The uprights stand **on** the back base rail and pass through 41 × 41 mm notches in the bed. The
beam sits **on top of** the uprights, flush with their outer faces.

### 4.3 Joints (the CAD has none; this is my recommendation)

[Guessing on the exact layout; Certain that the CAD and BOM leave it open]

**Beam to upright (×2):**
- two 4040 L brackets in the inside corner, on the upright's inner face and the beam's bottom
  face, one in each slot pair;
- one flat L joining plate on the back face, across the upright and the beam.
- **No brackets on the front faces.** The X rail ends only 18 mm from each upright (BOM.md open gap 1).

**Upright to back base rail (×2):**
- The bed covers the base-rail top all round the notch, so an L bracket can't reach the rail
  directly.
- Use two L brackets on the upright's **inner face**, sitting on top of the plywood.
- Bolt each one down with an M5×30 screw through its foot, the 18 mm plywood and a T-nut in the
  base rail's top slot (slots at Y = 117 and 137).
  - Check that the screw pulls the bracket down hard before it bottoms in the slot. If it
    bottoms, use M5×25.
- The plywood then acts as part of the joint. Fit these after the bed (§5A).
- If it still racks, end-tap the upright bottom M5 (4 corner holes) and bolt up through drilled
  holes in the base rail.

**Bed to base rails:**
- 16 × M5×30 into T-nuts, 8 per rail, in the rail's **outer** slot:
  - front rail at Y = −77.5, which is 40 mm from the front edge;
  - back rail at Y = 137, which is 35 mm from the back edge.
- Put the front-rail bolts on the cell wall lines (X = −4 + 92·k). That keeps them 16 mm clear of
  the nearest front rod hole and outside the pads. [Certain, CAD arithmetic]
- **Feet:** four rubber feet into the base rails' bottom slots.

### 4.4 Assembly steps (4–6 h, with the instructor for squaring)

1. Slide T-nuts into every slot you will need **before** you close any joint. Drop-in T-nuts can
   be added later, but sliding ones can't. Count them per the BOM: about 122 M5 and 65 M3.
2. Lay both base rails on a flat bench, 194.5 mm apart centre to centre (Y = −67.5 and 127).
3. Bed part A (§5A) goes on now, because the upright brackets bolt through it.
4. Stand the uprights in the notches on the back rail. Brackets snug, not tight.
5. Lift the beam onto the uprights. Brackets and back plates snug.
6. Square everything (below), then tighten from the bottom up and re-check.

### 4.5 Squareness checks (instructor)

**Why these tolerances are loose:** the machine drills its own rod holes (§5B), so it doesn't
matter if the beam sits a little skewed to the bed. These checks keep the motion axes straight and
the rods vertical. [Certain, by construction of the drill-template method]

| Check | How | Target |
|---|---|---|
| Base rails parallel | centre-to-centre at both ends | 194.5 ± 0.5 mm |
| Base rectangle square | the two diagonals between rail ends | equal within 1 mm |
| Bed flat | straightedge along the row centre line (Y = 0) | gap ≤ 0.5 mm per metre [Guessing] |
| Bed not twisted | level, or winding sticks, across the depth at both ends | ≤ 0.5 mm across 290 mm [Guessing] |
| Uprights plumb, in X and in Y | machinist square on the bed plus feeler gauge, or a digital level | ≤ 0.5 mm over 400 mm (≈ 0.07°) [Guessing] |
| Upright spacing | inner faces at the bottom and at the top | 1336 ± 0.5 mm, equal top and bottom [Certain, CAD] |
| Gantry not racked | diagonals of the back face: beam top corner to the opposite base-rail bottom corner | equal within 1 mm |
| Beam height | bed top to beam bottom, at each upright | 383 ± 0.5 mm, equal both ends [Certain, CAD] |
| Beam sag | same, at midspan | within 0.3 mm of the ends (DESIGN: 0.18 mm under 20 N) |
| Beam front face straight | string line or a 1.5 m straightedge along the rail face | ≤ 0.5 mm bow [Guessing] |

---

## 5. Bed and guide rods

### 5A. Now, before the X axis (3–4 h)

**5.1 Cut the bed.**
- Cut 1416 × 289.5 mm from the 18 mm Baltic birch blank (305 × 1524). One rip and one crosscut.
- If you used Home Depot plywood instead, drill a test hole away from the pockets first: voids
  ruin rod holes. (BOM.md)

**5.2 Cut the two upright notches** at the back corners, one at each end.
- Each notch is 41 mm along X (open to the end) by 41 mm along Y.
- It runs from **24.5 mm to 65.5 mm in from the back edge** (Y 106.5 … 147.5). [Certain, CAD]
- Jigsaw or bandsaw, then file to fit. The upright must drop in without forcing.

**5.3 Bolt the bed to the base rails** (§4.3), with the frame square.

**5.4 Prepare the rods** (do this while the printers run):
1. Roll every dowel on a flat table. Reject bowed ones. Buy 100 so you can.
2. Cut 82 to **236 mm**: 15 mm in the plywood + 3 mm of pad + 218 mm above the pad. [Certain,
   CAD]
3. **Dome one end now.** Chuck the dowel in a cordless drill, spin it against 120 then 220 grit,
   and round the top to a 2–3 mm radius. This is the lead-in for slabs going in by hand.
   Thirty seconds each.
4. Lightly chamfer the other (bottom) end so the glue isn't scraped off on insertion.
5. **Test hole in scrap plywood:** drill 8 mm × 15 mm deep with the brad-point bit. A dowel must
   be a firm push fit.
   - Too loose: use a fresh bit, or a 5/16 in bit with 5/16 in dowels.
   - Too tight: sand the dowel end.

**5.5 Cut the pads:**
- 13 pads of **83 × 138 mm**: 2 mm black EVA, faced with tight-weave microfiber, bonded with spray
  adhesive. Total thickness about 3 mm. [Certain, CAD `PAD_T`]
- Cut with a sharp knife and a steel rule, corners square.
- **Don't lay them yet.** The template sits on bare plywood.

### 5B. After §11, once the machine homes and jogs

**Order:** §6–§11 first. You need X and Z moving, the probe working (FIRMWARE.md step 7), and the
software installed. The bed must be bare: no rods, no pads.

**5.6 Mark and drill, one cell at a time** (4–6 h for 13 cells).

What the template does:
- `drill_template` is a one-cell jig with two cone dimples, 40 mm either side of the cell centre,
  on the row centre line, plus 8 drill-guide bosses. [Certain, `model.py`]
- The awl on the head drops into both dimples, so the template lines up with the machine's *own*
  X axis and cup path. Belt stretch, the switch position and beam skew are therefore all built
  into the holes.

Set-up:
- Fit the `awl_adapter` in place of the cup.
- Set its point level with where the cup face was, within 2 mm (`mark` asks for this).
- Make a **drill guide block**: drill an 8 mm hole straight through a 30 mm hardwood block on the
  school's drill press.
  - The printed template sets each hole's *position*, not its *angle*. [Certain, BOM.md] The
    block sets the angle.
  - Why it matters: a rod leaning 0.5° puts its top 1.9 mm off at 218 mm, and the slab has only
    ±1.85 mm of play. [Certain, arithmetic]

```bash
python -m slabscan mark --dry-run     # prints the order and every dimple position
python -m slabscan mark               # the real thing
```

For each pocket the software:
1. Drives the awl over the left dimple and lowers it until it touches (a bounded probe).
2. Asks you to nudge the template until the point sits in the left dimple.
3. Moves to the right dimple. You swing the template on the left dimple until the right one is
   under the point, then **clamp the template** (two small clamps, or double-sided tape plus a
   clamp).
4. Parks the head three pockets away and waits while you drill.

Drilling each hole:
1. Hold the guide block on top of the template boss, hole over hole.
2. Drill through boss and block with the 8 mm brad-point bit.
3. **Depth collar at 57 mm from the bit's cutting lips:** 30 mm block + 12 mm boss + 15 mm into the
   plywood. [Certain, CAD for the boss and the 15 mm] The collar stops on the top of the block.
   - The brad point's centre spur goes 1–2 mm deeper than the lips, and the plywood is only
     18 mm. Check on the §5.4 scrap test hole that it doesn't break through the bottom. If it
     does, drill 14 mm: the rod tops end 1 mm higher, which is harmless. [Likely]
4. Vacuum the chips out of each hole.

Order and the end pockets:
- The order is pockets 1–11 first, then 0 and 12. [Certain, `mark --dry-run`]
- One dimple of each end pocket is past the X travel. For those, push two 8 mm pins (drill bits)
  through the template's shared-side holes into the neighbour's finished holes. The one dimple
  you can reach is then a check: **more than 1 mm off means stop.** Either the neighbour was
  drilled off, or X lost steps.
- The station cell (7) needs no holes of its own: its side rods belong to pockets 6 and 7.
  [Certain]
- Neighbouring cells share side holes. The template's side bosses simply re-enter holes already
  drilled.
- Break: `python -m slabscan mark --only 0,12` (or `--start N`) carries on.

**5.7 Glue the rods** (2 h + 24 h cure).
1. Put a drop of Titebond II in each hole and spread it with a cotton swab.
2. Push the rod to the bottom with a twist, domed end up.
3. Wipe the squeeze-out with a damp cloth.
4. Hold a small square against the rod in X and in Y. Over 200 mm it must be within 1 mm.
   [Guessing target, from the play budget]
5. Do one pocket wall at a time, and check rods against their neighbours by eye along the row.
- Titebond II: about 3–5 min open time, clamp 30–60 min, no load for 24 h. [Likely, Franklin
  guidance via secondary sources] Longer if the shop is cold.

**5.8 Rod check: the slab drop test.** After 24 h, lower a junk slab flat between the rods of every
pocket, from the rod tops to the plywood. Do it both ways round (rotated 180°). It must drop
freely and never catch. If it catches, the rod at fault leans. Either pull it now, before the
glue's full strength, or ream the hole and re-glue.

**5.9 Lay the pads, the station mount and the gate posts.**
- **Pads:** spray adhesive on the pad backs and the plywood, then press them in.
  - 0.5 mm clearance to the rods each side. [Certain, 83 vs 84 mm]
  - Use 3M Super 77 outdoors or in a ventilated room, and let it cure overnight before use.
    [Likely]
- **Station mount:** in cell 7, in place of a pad.
  - It has its own 3 mm base plate. Fix it with four #8 wood screws.
  - The camera ribbon exits toward the back.
  - Measure the station lens front height above the pad tops. It should be 23 ± 1 mm. If it
    isn't, set `station_read_c = <your height> + 146.6` in `calibration.toml`. [Certain:
    `STATION_READ_C = 23 + 140 + 6.6`]
- **Gate posts:**
  - Left post at X = −20 (laser), right post at X = 1300 (receiver), both on Y = 0. [Certain,
    `model.py`]
  - **Put a 3 mm shim under each foot** (plywood or a printed plate). The CAD puts the foot at
    pad-top height (Z 0), but the posts stand on the bare bed (Z −3). Without the shim the beam
    sits at 211 mm, only 1 mm above the MAX line. [Certain, CAD]
  - Fix each post with two wood screws.
  - Final beam alignment is in §12.5.

---

## 6. X axis

**6.1 Rail prep** (30 min). Generic MGN12 rails ship with storage oil and sometimes missing balls.
(BOM.md)
- **Never slide the carriage off the rail** without a holder against its open end (a short scrap
  of rail, or a printed plug), or the balls fall out. [Likely]
- Clean the rail and carriage with IPA.
- Count the balls through the end seals if you can.
- Grease with lithium or PTFE grease.
- The carriage must roll the full length with an even, slightly sticky feel, and no notches.

**6.2 Mount the rail** on the beam's **upper front slot** (centre Z = 410). [Certain, CONTRACT]
- 52 × M3×10 screws into M3 T-nuts.
- Rail ends at X −10 and 1290, which is **58 mm in from each end of the beam**. [Certain, CAD]
1. Put all screws in finger tight.
2. **Align the rail to the beam's top face:** with a caliper depth rod at every screw, the beam top
   to the rail's top edge must read **4.00 ± 0.1 mm**. [Certain, CAD: rail top edge Z 416, beam top
   Z 420]
   - Better, if the shop has one: clamp a dial indicator to the carriage, put the tip on the beam's
     top face, and slide the carriage along. Adjust until the reading varies by ≤ 0.1 mm.
3. Tighten from the middle outward to about **1 N·m**: a firm squeeze on a short hex key, not a
   full-hand torque.
   - The M3 T-nuts are in aluminium. A third-party rail installation table gives 0.98 N·m for M3
     into aluminium. [Likely]

**6.3 Carriage and X bracket.**
- Bolt `x_bracket` to the MGN12H carriage with 4 × M3×10 (20 × 20 mm pattern).
- The belt-clamp tab reaches back over the beam top.
- The carriage must still roll freely end to end. If it binds near the ends, a screw head is
  touching.

**6.4 Motor and idler.**
- `x_motor_mount` goes on the beam top at the **right** end, motor axis at X = 1322: 4 × M5 into
  the beam's two top slots.
  - The motor sits behind the beam, its shaft pointing forward.
  - The GT2 20T pulley goes on the shaft, and the grub screw must sit on the shaft's flat. Use
    blue threadlocker.
- `x_idler_mount` goes on the beam top at the **left** end, axle at X = −32. Toothed idler on an
  M5×30 axle through the slotted cheeks. [Certain, CAD]

**6.5 Belt.**
1. Route the GT2 belt as a closed loop in a vertical plane just above the beam top: around the
   motor pulley and the idler.
2. Clamp both ends in the `x_bracket` tab's split clamp, one end each side, teeth into the
   clamp's grooves.
3. The lower strand runs **2.6 mm above the beam top** and must not rub it anywhere. [Certain, CAD]
4. Check pulley and idler alignment: the belt runs centred on both flanges, and the lower strand
   sits at the same height above the beam at both ends.

**6.6 Belt tension.** I found no maker's figure for 6 mm GT2. [Certain that the searches came up
empty] Use this as a starting point and check it works:
- **Target 15–25 N.** [Guessing; one third-party calculator suggests 10–15 N, but this span is
  long]
- **Measure by deflection:** hook a 100 g mass (1 N), or a spring scale reading 100 g, under the
  middle of the lower strand and lift.
  - The strand should rise **13–23 mm**, which corresponds to 15–25 N.
  - The formula is T = F·L / (4·d), with L = 1.35 m, the pulley-to-idler distance. [Certain,
    statics]
  - Tighten by pulling more belt through the clamp. Fine-tune with the idler's ±3 mm slot.
- **Functional checks** (after §10):
  - no tooth skips on full-speed moves end to end;
  - homing repeats within 0.2 mm (FIRMWARE.md step 6);
  - `calibrate x` reports a scale error under 0.5 mm across the row (§12.2).
- Too tight shows up as a motor that runs hot or a pulley that wears. Too loose shows as lost
  position.

**6.7 Beam twist check, and the brace.** DESIGN.md estimates 0.8 mm of twist at the cup at
midspan from the head's 127 mm overhang. [Guessing in DESIGN] Measure it once the head is on
(§7):
1. Park the head over pocket 6 (midspan) with the cup about 20 mm above the pad.
2. Put a dial indicator on the bed with its tip against the side of the buffer body, reading in Y
   (front–back).
3. Hang a 0.75 kg weight (a water bottle) from the cup, about the head's own weight. Read the
   movement.
- **Up to 1.0 mm: fine.**
- **More than 1.0 mm: fit the brace** (DESIGN.md's threshold). [Guessing: no CAD for it]
  - Cut a vertical 2020 post (about 401 mm, from the 600 mm stock) and stand it behind the
    pockets at X ≈ 600, under the beam's rear bottom slot.
  - Fix it to the beam with two 2020 corner brackets, and to the bed with corner brackets bolted
    through into the back base rail's T-nuts.
  - Keep it clear of the drag chain and of the station camera ribbon (X ≈ 686).
  - Repeat the measurement.

**6.8 X home switch** (WIRING.md §7):
- Mount it at the left end of the beam so it clicks when the cup axis is at **X ≈ 19 mm**, about
  23 mm left of pocket 0's centre (± 3 mm).
- Add a printed or rubber bumper as a hard stop at X ≈ 14. The carriage leaves its rail at 12.7.
  [Certain, FIRMWARE.md]

---

## 7. Z axis and head

![Head close-up](img/head_closeup.png)

All heights below are from `cad/layout.py` and `cad/model.py`. [Certain]

**7.1 Z spine to X bracket.**
- Bolt the 2040 × 340 spine to `x_bracket` with 4 × M5×12 into T-nuts in **both** of the spine's
  slots (bracket holes at Z 340 and 365).
- The spine sits **10 mm left of the cup axis**, so the Z rail in its right slot lands on the cup
  axis. (CONTRACT)
- **Set the spine's bottom end 226 ± 1 mm above the pad top.** That's 229 above the bare
  plywood; measure from a rod top + 8 if rods are in.
  - The spine bottom sweeps over the rod tops with only 8 mm to spare. [Certain, `checks.txt`]

**7.2 Z rail.**
- MGN12 330 mm in the spine's right slot, 13 × M3×10 into T-nuts. Its bottom is 1 mm above the
  spine bottom, its top 9 mm below the spine top.
- Align it parallel to the spine edge with the caliper (as in §6.2).
- **Plumb:** ≤ 0.5 mm over the rail length, in X and in Y. Check with a square from the bed, or a
  digital level at 0.1°. [Guessing target: the cup's position must not drift across its 250 mm of
  travel]

**7.3 Z motor and nut.**
- `z_motor_mount` on the spine top: 2 × M5 into the two slots.
- NEMA17 with its integrated 400 mm T8×8 screw, screw pointing down (4 × M3×8).
- `z_plate` on the Z carriage (4 × M3, 20 × 20).
- The brass T8 nut sits on the plate's nut shelf (4 × M3×16 + nuts). Leave those screws loose.
  Run the plate up and down the full travel by turning the screw by hand, then tighten. The nut
  then centres itself.
- **The screw must not whip or push the carriage sideways at any height.**

**7.4 Z top switch** (WIRING.md §7):
- On the spine top, hit by the Z plate.
- It must click at c ≈ 258 mm: the cup face 258 above the pad top, ± 2 mm.

**7.5 Drop arm, foot and cup.**
1. **Drill the two 5.5 mm cross holes in the 2020 × 236 drop arm**, through the centres of two
   opposite faces.
   - **The CAD draws the arm 3 mm into the floor of `head_foot`'s socket** (arm from 62 mm, socket
     floor at 65 mm above the cup face). Measured from an arm end that bottoms in the socket, the
     holes are at **19 mm** (for `head_foot`) and **84 mm** (for `camera_bracket`), not the 22 and
     87 the drawn arm suggests. [Certain, `model.py`: foot hole at 84, camera hole at 149, socket
     floor at 65]
   - **Match-drill the foot hole:** push `head_foot` onto the arm until it bottoms, clamp it
     square, and drill through the printed hole and the arm together on the drill press.
   - Then mark the second hole **65 mm above the first**, centre to centre, and drill it.
   - Deburr both.
2. Fit `head_foot` with an M5×30 cross bolt and a nylock nut.
3. **Spring buffer:** the M10×1 body goes through the foot's 10.4 mm hole, with a nut each side.
   Fit the cup pad (SMC ZP25UU) on the buffer.
4. Bolt the arm to `z_plate` with 2 × M5×12 into T-nuts in the arm's slot. The arm can still slide.
5. **Set the height chain in this order** (buffer at rest, steel rule):
   1. With the camera bracket on (§7.7), move the buffer on its M10 nuts until the **head lens
      front is 140 ± 1 mm above the cup face**.
   2. Then slide the arm in its T-nuts until **the Z carriage's bottom edge is 243 ± 2 mm above
      the cup face**. [Certain, CONTRACT: with this the carriage stays on its rail down to
      c = −12, and `calibrate z` lands in −4 … 0]
6. Vacuum tube from the buffer's top port (M5 female, via an M5 push fitting). Leave **30 mm of
   slack**, because the rod rises up to 25 mm on contact. (WIRING.md §11)

**7.6 Contact sensor and flag (set it to trip at about 2 mm).** The sensor is a slotted optical
endstop (TCST2103: 3.1 mm gap, 1 mm aperture [Certain, Vishay datasheet via distributors]) on the
foot's sensor post. The flag is a tab on the buffer rod that moves up into the slot as the cup is
pushed up.

**The flag is not in the CAD.** [Certain] BOM.csv has a strip of flag stock. Make it:
- **Material:** 1 mm aluminium or steel strip, about 6 mm wide.
  - Not thin black PETG: IR sensors can see through thin plastic. [Likely]
- **Shape:**
  - one end is a washer tab with a 5.2 mm hole, clamped between the M5 push fitting and the rod
    top (check the fitting still engages at least 3 threads);
  - it runs sideways to the sensor;
  - its tip turns up into the slot's path.
- **Clearance:** the tip must pass through the 3.1 mm gap with ≥ 0.5 mm to each arm over the full
  25 mm stroke.
- **Rotation:** with the BOM's rotating ("J") buffer, the rod and flag can turn. Add a guide (a
  slot in a printed tab on the foot that the flag rides in) or use the non-rotating "K" buffer
  (§2).

**Wiring:** fail-safe (WIRING.md §6). **At rest the slot must be clear**; contact pushes the flag
in.

**Adjust the trip point to 2.0 ± 0.5 mm of buffer travel** (the simulator assumes 2 mm [Certain,
`simworld.TRIGGER_COMPRESSION`]):
1. Power the sensor from 5 V and put a meter on OUT: about 0 V with the slot clear, about 5 V
   blocked (WIRING.md §6).
2. With a caliper depth rod, measure the buffer rod's top above the foot's top face at rest.
3. Push the cup up slowly by hand until OUT jumps. Measure again.
4. The difference is the trip travel. Bend the flag tip, or file the sensor holes into short
   slots so the board can move, until it reads 1.5–2.5 mm.
5. Push the cup through the full stroke. The flag must never touch the sensor, and OUT must stay
   high all the way up.

Re-check after any knock. `calibrate z` (§12.1) also checks it in software: the probe must trigger
when you push the cup up by hand, and release when you let go.

**7.7 Camera bracket and LED ring.**
- `camera_bracket` clamps the arm with the second cross bolt.
- **The head lens front is 140 ± 1 mm above the cup face.** [Certain, CAD `CAM_TO_SLAB`] That is
  the held slab's back. Set it with the buffer nuts (§7.5 step 5).
- Fit the ELP board (4 × M2) and the LED ring in the ring seat around the lens.
- The lens looks straight down on the cup axis.
- Run the camera USB and the ring wires along the arm in clips every 50 mm (WIRING.md §11).

**7.8 Z hold test** (FIRMWARE.md open issue 4, after §10):
1. With the head at Z 240 and a 200 g weight hanging on the cup, press the E-stop.
2. Watch for 1 minute.
- **Any creep means a friction brake or counterweight is needed before unattended use.**
  [Guessing in DESIGN: detent torque should hold]

---

## 8. Vacuum plumbing

(2–3 h, most of it already done in Phase 0B)

**8.1 Order of parts, from the pump to the cup** [Certain, BOM + `hw.py` + WIRING.md §5]:

```
 pump exhaust → room
 pump inlet ◄── check valve (arrow toward pump) ◄── reservoir (2 in PVC, ~300 mL)
                                                       │
                                     vacuum valve Q2 (NC, GPIO 27)
                                                       │  cup side
                                     tee ── 2 mm silicone ── XGZP6847A sensor (on the I/O board)
                                                       │
                                     tee ── vent valve Q3 (NC, GPIO 22) ── room
                                                       │
                          4 mm PU tube through the drag chain and the Z loop
                                                       │
                                     M5 push fitting ── buffer top port ── cup
```

**8.2 Steps**
1. **Reservoir:**
   - 2 in Sch 40 PVC, 6 in long, two caps solvent-welded on.
   - Drill and tap one cap 1/8 NPT twice (in and out). Push fittings go in with PTFE tape.
   - Let the PVC cement cure for the time on its label before pulling vacuum on it. [Likely]
   - Don't use a PET bottle: it collapses at −80 kPa. (BOM.md)
2. **Check valve** between reservoir and pump inlet, arrow toward the pump.
3. **Valves (Clippard EV-2-24, 10-32 ports, 10-32 → 4 mm fittings).**
   - Put the **inlet** on the side that is at the higher pressure when the valve is closed:
     - vacuum valve: inlet on the **cup side**;
     - vent valve: inlet **open to the room**.
   - [Likely: the inlet pressure normally helps a direct-acting poppet seal. Check the inlet/outlet
     marks on Clippard's drawing; I could not open it from here. The leak test decides.]
4. **Sensor tee** on the cup side of the vacuum valve, so the Pi reads the cup line, not the
   reservoir. Keep the silicone tube short. (WIRING.md §5)
5. **Pump:**
   - on rubber feet, not hard-mounted;
   - a short silicone hose section at its inlet so vibration doesn't fatigue the fittings;
   - check its polarity (WIRING.md W23).
6. **Cup line:** cut the PU tube square with a knife and push it fully into every fitting until it
   bottoms, then tug it.

**8.3 Leak test** [Certain for the selftest thresholds, Guessing for my tighter targets]

| Test | How | Pass |
|---|---|---|
| Seal | `python -m slabscan selftest -i`, press a slab on the cup | `seal` reaches −35 kPa |
| Cup line holds | same run: the `leak` line (valves shut, pump off) | < 1 kPa/s (selftest's own pass is < 2.5) |
| Vent | same run: the `vent` line | > −6 kPa after venting |
| Reservoir holds | block the cup with a slab, pump down with the valve open, shut both valves, and watch `kpa` | holds −60 kPa for 60 s with the pump off (BOM.md valve test) |

**Finding a leak:**
- Pinch the tube shut at points along the line, moving from the cup toward the valve. The leak is
  on the cup side of the first pinch point where the vacuum starts to hold.
- Usual culprits: a tube not fully seated, the M5 fitting on the buffer, a cup lip with grit on it,
  the vent valve's seat.

---

## 9. Electronics

(10–15 h. **Instructor: mains wiring, crimp review, first power-up.**)

Follow [WIRING.md](WIRING.md) section by section. The block diagram:

![Wiring](img/wiring.svg)

**Order of work**
1. **Panel** (1/4 in plywood behind the machine, Pi centred near X ≈ 690). It holds:
   - the PSU;
   - the E-stop feed;
   - the Wago buses and fuse holders;
   - the Rodent;
   - the Pi;
   - the I/O board and the five MOSFET modules.
2. **Mains:** inlet → PSU, and PE to the frame (WIRING.md §1.1, §12). **Instructor checks it
   before the first plug-in.** Set the LRS-150's 115/230 V switch to your mains (115 V in the US).
   [Certain, WIRING.md]
3. **24 V side:**
   - E-stop in the +24 V line;
   - fuses F1 5 A (Rodent), F2 3 A (pump/valves), F3 1 A (buck);
   - the 12 V buck.
4. **Rodent:**
   - jumpers per WIRING.md §2;
   - **check the sense-resistor marking first** (FIRMWARE.md step 0: R075 or R022);
   - X motor to socket X, Z motor to socket Z. **Nothing in sockets Y or E.**
5. **Inputs:**
   - X home switch (NC) → X-MAX;
   - Z top switch (NC) → Z-MAX;
   - optical probe → **Y-MAX** (not the Probe connector).
   - All three are fail-safe: a cut wire reads as triggered. (CONTRACT)
6. **Pi side:** MOSFET modules on GPIO 17/27/22/23/24, the I/O board (ADS1115 at 0x48 and the
   sensor divider), and the laser gate on GPIO 5 with its 2.2 kΩ pull-up **at the receiver**.
7. **Moving cables:** the drag chain (fixed end at the beam's top-back, X ≈ 640) and the Z service
   loop (WIRING.md §11). The 8-core cable's colours go in WIRING.md's table.
8. **Strain relief and labels on both ends of every cable** (WIRING.md §13).

**Crimping:** JST-XH and Dupont crimps with the proper tool (BOM.md tools). **Pull-test each one,
and have the instructor look at the first ten.** Or buy pre-crimped leads.

**Pre-power checklist:** do all 15 steps of WIRING.md §14 with a meter, mains unplugged. The ones
that bite:
- **24 V bus to the Pi 5 V pin: open.** 0 V bus to Pi GND: < 1 Ω.
- **E-stop pressed:** PSU +V to the 24 V switched bus open.
- **Motor coils** 1–4 Ω each, coil to coil open, and **Y and E empty**.
- **Sense resistor value in `config.yaml` matches the board.** A 0.075 setting on a 22 mΩ board
  gives 3.4× the motor current. [Certain, FIRMWARE.md]

**First power-up:** WIRING.md §15, in its order:
1. Pi alone: I2C `48`, sensor ≈ 3.0 V at A0, gate ≈ 3 V clear and < 0.4 V blocked.
2. PSU set to 24.5 V with no load.
3. Release the E-stop and check the voltages, and that nothing warms up.
4. One load at a time with `pinctrl`.

---

## 10. Firmware

(2–3 h. Follow [FIRMWARE.md](FIRMWARE.md) steps 0–7.)

| Step | What | The check that matters |
|---|---|---|
| 0 | Board set-up, power off | Resistor marking → `r_sense_ohms`. Jumpers 5V / 5V / NPN off / VUSB off / no DIAG. |
| 1 | Flash FluidNC v4.1.1+ (web installer) | The banner appears at 115200 baud |
| 2 | Load `firmware/fluidnc/config.yaml` | Then `$WiFi/Mode=Off`. **Never `$CD=config.yaml`.** |
| 3 | `$SS`, `$CD`, `?`, `$Limits` | No `ERR`; 4 drivers pass; Alarm until homed; nothing active at rest |
| 4 | Motor direction, soft limits off for this test only | +X moves **right**, +Z moves **up**; 100 mm jog = 100 ± 0.5 mm |
| 5 | Switches and probe, fail-safe rows | **Unplugging any switch or the probe must read as triggered.** If not, stop and fix it. |
| 6 | First homing, hand on the E-stop (instructor present) | Z up first, then X left; `MPos:22.000,0.000,255.000`; repeat within 0.2 mm; cup over pocket 0 at X ≈ 42 ± 3 |
| 7 | `G38.3` probe test over pocket 0 | Trips at about −2; spread < 0.1 mm; unplugged probe gives `ALARM:4` and no motion |

Then do the Z hold test (§7.8) and the beam twist check (§6.7).

---

## 11. Software install

(1–2 h)

**11.1 Operating system.**
- Use Raspberry Pi Imager. **The contract says Bookworm, but Imager now offers Trixie (Debian 13)
  by default.** [Certain, raspberrytips.com]
- Pick **Raspberry Pi OS (other) → Raspberry Pi OS (Legacy, 64-bit)**, which is Bookworm with
  Python 3.11. [Certain, same source]
- In Imager's settings: hostname `slabrail`, your user, Wi-Fi, and **SSH on**.
- The software's tests also pass on Python 3.13 [Likely: the software agent's report], but
  `setup_pi.sh` has only been written for Bookworm's apt packages. [Certain]

**11.2 Copy the whole repository** to the Pi, e.g. `~/psa-slab-scanner`, by `git clone` or USB
stick. `gen_config` reads `cad/layout.py`, so the `cad/` folder must be there too. [Certain,
`config.from_layout`]

**11.3 Install:**

```bash
cd ~/psa-slab-scanner/software
bash setup_pi.sh            # or: bash setup_pi.sh --service   (web page starts at boot)
sudo reboot
cd ~/psa-slab-scanner/software && source .venv/bin/activate
i2cdetect -y 1                       # 48 = ADS1115
rpicam-hello --list-cameras          # the Camera Module 3
v4l2-ctl --list-devices              # the USB head camera (not /dev/video0 on a Pi 5)
```

**Don't `pip install` numpy or OpenCV into the venv.** A pip numpy hides the apt one and breaks
picamera2. [Certain, software README]

**11.4 Machine config.** `setup_pi.sh` already ran `python -m tools.gen_config`. Run it again
whenever `cad/layout.py` changes. It writes `config/machine.toml` and never touches
`config/calibration.toml`. [Certain]

**11.5 Your own settings** go in `config/calibration.toml`. It overrides `machine.toml`, and the
calibrate commands write there too.

```toml
serial_port = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"   # stable name for the Rodent's CH340 (CONTRACT)
# lid_switch = true          # only if you fitted the optional lid switch on GPIO 25
# custom_regex = "..."       # only if Phase 0 found a prefix/suffix around the cert (one capture group)
```

**11.6 Check everything:** `python -m slabscan selftest -i --motion`. It must end `SELFTEST PASSED`
(exit code 0). The gate posts go on in §5.9, so keep `overfill_gate = false` from Phase 0B in
`calibration.toml` until §12.5, or the `overfill beam` line fails. A `calibration` WARN is
normal before §12.

**11.7 Learn the commands on the simulator** before touching the machine:
`python -m slabscan sim --slabs 330` and `python -m slabscan --sim web`.

---

## 12. Calibration

(2–3 h, after 5B: rods glued, pads down.)

**12.1 `calibrate z`.** Cup fitted, pocket 0 empty.

```bash
python -m slabscan calibrate z
```

What it does:
1. Homes.
2. Asks you to push the cup up by hand (the probe must trigger) and let go (it must release).
3. Probes the bare pad of pocket 0 four times and writes `pad_trigger_c`.
- Probing never goes below Z −7.5. [Certain, `ops.z_floor`]

Pass:
- `pad_trigger_c` between −4 and 0 (FIRMWARE.md step 6);
- repeat spread < 0.1 mm (it warns above 0.3).

If it is off:
- **Outside −4 … 0:** re-check the 243 mm carriage-to-cup height (§7.5) before going on.
- **"No contact down to Z −7.0":** the head sits too high. (−7.0 = 255 − 250 − 12, the default
  `--extra-depth`; it is never lower than −7.5.)

**Re-run it whenever you change the cup pad.**

**12.2 `calibrate x`.** Awl fitted.

```bash
python -m slabscan calibrate x
```

1. Centre the awl over pocket 0's centre: first by eye at the safe height, `ok`.
2. Then low, just above the pad: `z -10`, `z -1`, and so on. Downward moves stop on contact.
   Centre it exactly, `ok`.
3. Repeat for pocket 12.
- It writes `offset_x` and prints the distance error across the row.

Pass:
- **error under 0.5 mm** [Guessing target; the software only warns above 1.5 mm];
- `offset_x` within ± 1 mm. The holes came from `mark`, so the residual should be tiny.

Larger means the belt or a pulley grub screw slipped. Fix that, don't paper over it. [Certain,
`ops.calibrate_x` message]

**12.3 `focus head`.** One slab face-down in pocket 0, label toward you.

```bash
python -m slabscan focus head
```

- The cup comes down and rests on the slab: the same 140 mm as a held slab.
- Turn the M12 lens to the peak score and lock the nut.
- The best frame is saved in `focus/`. Open it: the QR and barcode must look crisp, with no glare
  spot on the label.

**12.4 `focus station --save`.**

```bash
python -m slabscan focus station --save
```

The machine picks the slab out of pocket 0 and holds it over the station camera at
c = 169.6. It sweeps LensPosition, writes the sharpest value that decodes, then puts the slab
back.

![Station read](img/station_read.png)

**12.5 Overfill beam.**
1. Measure the beam height at both ends and in the middle (a card held in the beam, then a ruler):
   **214 ± 1 mm above the pad top.** That is above the 210 MAX line and below the 218 rod tops.
   [Certain, CONTRACT] Shim the posts (§5.9) if it's low.
2. Aim the laser dot at the centre of the receiver.
3. With the room lights on, turn the receiver's trimmer until a hand in the beam reads blocked.
   (WIRING.md §8: non-modulated receivers can be fooled by room light.)
4. If you added `overfill_gate = false` in Phase 0B, delete that line from `calibration.toml` now.
   Then `python -m slabscan selftest -i` → `overfill beam` PASS and `overfill beam blocked` PASS.
5. Stand a `fill_gauge` in a pocket. Its top notch is the MAX line; the beam must pass just above
   it.

**12.6 Check the whole set.** `python -m slabscan selftest -i --motion` → PASSED. Keep a copy of
`config/calibration.toml` somewhere off the Pi.

---

## 13. Acceptance tests before real slabs

**Use junk slabs only:** cheap graded cards you can afford to scuff. Get 15–20, including at least
one CGC, one BGS or TAG, one thick holder, and one old label if you can. **All six tests must pass
before your inventory goes in.**

### 13.0 The bench test script

The CLI has no command to cycle the cup 300 times on one slab, drop a slab on purpose, or log the
vacuum through an E-stop. Save this as `software/bench_tests.py`.

- It uses the runner's own pick, carry and place code, so the cycle is a real one.
- **[Certain] I ran `cycles`, `rest` and `powercut` against the simulator on 2026-10-22.** `drop`
  correctly ends in the simulator's "dropped slab" crash, because the simulator treats any drop as
  a fault.
- **Not yet run on hardware.**
- It uses private runner methods (`_home`, `_go`, `_probe`), so re-test it with `--sim` after any
  software update.

```python
"""SlabRail bench tests (docs/BUILD_GUIDE.md section 13). Save as software/bench_tests.py and run it
from software/ with the venv active. JUNK SLABS ONLY. Add --sim to try any test on the simulator first.

  python bench_tests.py cycles 300            move the stack in pocket 1 to pocket 0 slab by slab, then back, 300 transfers
  python bench_tests.py rest 24               cup sealed on the top slab of pocket 1 for 24 hours (re-sealed every 30 min)
  python bench_tests.py drop 2                pick the top slab of pocket 1, carry it over pocket 2, vent: it DROPS
  python bench_tests.py powercut 300          pick the top slab of pocket 1, hold it high, log the vacuum while you press the E-stop
"""

import argparse
import time
from pathlib import Path

from slabscan.cli import DEFAULT_CONFIG
from slabscan.config import load
from slabscan.factory import open_hardware
from slabscan.motion import ControllerLost
from slabscan.results import BatchWriter
from slabscan.runner import Runner, Stop


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("test", choices=["cycles", "rest", "drop", "powercut"])
    ap.add_argument("n", type=float, help="cycles: transfers | rest: hours | drop: pocket to drop into | powercut: seconds to log")
    ap.add_argument("--src", type=int, default=1, help="pocket the junk slabs start in (default 1)")
    ap.add_argument("--sim", action="store_true", help="simulator instead of the machine")
    a = ap.parse_args()
    cfg = load(DEFAULT_CONFIG, DEFAULT_CONFIG.parent / "calibration.toml")
    kw = {}
    if a.sim:
        from slabscan.simworld import SimSlab

        kw["stacks"] = {**{p.index: [] for p in cfg.pockets}, a.src: [SimSlab(str(148069831 + 7919 * i), 6.6) for i in range(3)]}
    hw = open_hardware(cfg, sim=a.sim, **kw)
    w = BatchWriter(Path(cfg.out_dir), f"bench-{a.test}-" + time.strftime("%Y%m%d-%H%M%S"))
    r = Runner(cfg, hw.motion, hw.vacuum, hw.lights, hw.head_cam, hw.station_cam, w, log=print)
    vac, src = hw.vacuum, cfg.pocket(a.src)
    try:
        r._home()
        if a.test == "cycles":
            r.survey()  # pocket 0 and pocket 12 must be empty, like a real run
            here, there, done = a.src, 0, 0
            while done < a.n:
                if not r.transfer(here, there):  # source empty: turn round
                    here, there = there, here
                    if not r.transfer(here, there):
                        raise SystemExit("no slabs left to move (did they all go to the exception pocket?)")
                done += 1
            rows = w.rows
            ok = sum(1 for x in rows if x.verdict.status == "ok")
            print(f"{done} transfers, {ok} read ok, certs seen: {sorted({x.verdict.cert for x in rows if x.verdict.cert})}")
            print(f"rows in {w.csv_path}. Put the slabs back by hand before a real run (pocket 0 must start empty).")
        elif a.test == "rest":
            top = r._find_top(src)
            if top is None or top < cfg.t_min / 2:
                raise SystemExit(f"pocket {src.index} is empty")
            r._probe(r.c(top) + cfg.approach_gap, r.c(top) - 3.0)  # cup resting on the slab, buffer at its trip point
            t_end = time.monotonic() + a.n * 3600
            while True:
                vac.hold()
                time.sleep(2.0)
                k = vac.kpa()
                vac.close()  # pump off, both valves shut: the cup stays sealed
                print(f"{time.strftime('%H:%M')}  sealed at {k:.0f} kPa")
                left = t_end - time.monotonic()
                if left <= 0:
                    break
                time.sleep(min(1800.0, left))
                print(f"{time.strftime('%H:%M')}  {vac.kpa():.0f} kPa after waiting (leak check)")
            vac.release()
            r._z(r.c(cfg.c_safe_empty))
            print("done: the cup is up. Inspect the slab under raking light before touching the contact spot.")
        elif a.test == "drop":
            over = cfg.pocket(int(a.n))
            below = r._find_top(over) or 0.0
            r.pick_top(src.index)
            r._go(over.x, over.y)
            input(f"The slab will DROP about {r.s(r.z) - 6.6 - below:.0f} mm into pocket {over.index}. Hands clear, press Enter ")
            vac.release()
            r.holding, r.held_from = False, None
            r._z(r.c(cfg.c_safe_empty))
            print("dropped. Inspect corners and faces of the dropped slab and the top slab below it.")
        else:  # powercut
            r.pick_top(src.index)
            print(f"Holding a slab {r.s(r.z):.0f} mm above the pad over pocket {src.index}. PRESS THE E-STOP NOW. Logging for {a.n:.0f} s.")
            t0, t_cut, lost = time.monotonic(), None, False
            while time.monotonic() - t0 < a.n:
                if not lost:
                    try:
                        hw.motion.status() if hasattr(hw.motion, "status") else None
                    except ControllerLost:
                        lost, t_cut = True, time.monotonic()
                        print("controller gone (E-stop works). Watching the cup vacuum:")
                k = vac.kpa()
                since = f"{time.monotonic() - t_cut:5.0f} s after the cut" if t_cut else "before the cut"
                print(f"  {since}: {k:6.1f} kPa")
                if t_cut and k > -3.0:
                    print("vacuum gone: the slab drops (or has dropped) here.")
                    break
                time.sleep(1.0)
            print("Take the slab off by hand, release the E-stop, then `python -m slabscan home`.")
    except (Stop, KeyboardInterrupt) as e:
        print(f"stopped: {e}")
        note = r.secure()
        if note:
            print(note)
    finally:
        hw.close()


if __name__ == "__main__":
    main()
```

### 13.1 Dry run: 100 cycles with 10 junk slabs

(about 1.5 h)

1. Put one junk slab in each of pockets 1–10, face-down, label toward you. Write down their certs.
2. `python -m slabscan run --name dry1`. Every slab moves one pocket left and gets read.
3. Move each slab back one pocket to the right by hand (pocket 9 → 10 first, then 8 → 9, … 0 → 1),
   and run again.
4. Ten runs = 100 transfers.
- Make one of the ten runs `--front-photo always`, so the station path gets exercised too.
- If you have them, swap in the BGS/TAG and the old-label slab for two of the runs.

**Pass:**
- 100/100 transfers with no unexplained stop;
- every PSA/CGC slab `ok` with the **right** cert (check `certs.txt` against your list);
- BGS/TAG lands in pocket 12 as `other_grader`;
- `count check: every stack matches` in every summary;
- no visible marks.
- Note `mean cycle` from the summary: that's your real speed.

### 13.2 Cup marking test: 300 cycles + 24 h on one junk slab

(1.5 h of machine time + 24 h)

1. Photograph the junk slab's back under raking light (§1.10).
2. Put it in pocket 1, with pockets 0 and 12 empty.
3. `python bench_tests.py cycles 300`. The slab ping-pongs between pockets 1 and 0, one full pick,
   read and place each time. The CSV also gives you 300 reads of one cert.
4. `python bench_tests.py rest 24`. The cup sits sealed on the same slab for 24 h, re-sealed every
   30 min. The log also shows how fast the cup line leaks.
5. Inspect under the same raking light. Then wipe with a dry microfiber cloth and inspect again.

**Pass:**
- no ring, haze or residue after a dry wipe;
- 300/300 reads `ok` with the same cert;
- the cup lip is undamaged.

**Fail:** switch to the Schmalz HT1 cup (BOM conditional line), re-run `calibrate z`, and repeat.

### 13.3 Drop test from carry height

(30 min)

1. Pocket 1: two junk slabs. Pocket 2: a stack of about 10 junk slabs. Pocket 0: empty.
2. `python bench_tests.py drop 2`. The script says how far the slab will fall (about 170 mm here).
3. Put the dropped slab back in pocket 1. Then `python bench_tests.py drop 0`, onto the bare pad:
   about 236 mm, the worst case. [Certain, DESIGN.md: ≤ 236 mm]

**Inspect:** corners, edges, both faces, and the top slab of the stack it hit.

**Pass:**
- no crack, chip or new scuff;
- the slab lands flat inside the rods, not hung on a rod top.

**If a corner chips:** you've found DESIGN.md's [Guessing] risk. Slow the X moves while loaded
before going on: there is no config key for that yet, so it's a software change.

### 13.4 Power-cut test while holding a slab (valve fail-safe)

(30 min, **instructor present for the first E-stop**)

1. Pocket 1: three junk slabs.
2. `python bench_tests.py powercut 300`. The machine lifts the top slab to carry height.
3. **Press the E-stop.**
   - The script logs the cup vacuum every second, using the Pi's own sensor (still powered).
   - It stops logging when the vacuum rises above −3 kPa. The slab falls off at about −1.7 kPa.
     [Certain, arithmetic: 65 g over 78 % of a 25 mm cup]
4. Repeat two more ways:
   - **pull the Pi's USB-C power** with the controller on: the Pi's GPIOs stop driving, so the
     modules' 10 kΩ pull-downs must switch the pump off and let both valves close;
   - **pull the machine's mains cord** with the Pi on its own supply.
   - Time these two with a stopwatch.

**Pass:**
- **the slab stays on the cup for at least 60 s in every case** [Guessing target: long enough to
  reach in and take it];
- nothing moves after the cut;
- after releasing the E-stop, `home` works.

**Fail cases:**
- the pump keeps running when the Pi is unplugged: the 10 kΩ SIG pull-downs are missing (WIRING.md
  §4);
- the slab drops in seconds: there's a leak in the cup line (§8.3).

### 13.5 Double-pick test

(20 min)

1. Make a clinging pair: two junk slabs with two small loops of painter's tape (sticky side out)
   between them, so they lift as one. The pair is about 13–14 mm thick.
2. Put the pair on top of a 5-slab junk stack in pocket 1.
3. `python -m slabscan run --name double`.

**Pass:**
- The pair is carried over the rods without touching. Carry height 243 mm is set so even a 15 mm
  double clears the rods by 10 mm. [Certain, CONTRACT]
- The pair is placed without a stop.
- The row shows `needs_review` with the note **`DOUBLE PICK: an unread slab is directly under this
  one in pocket 0`**.
- `count check` still matches.

This is exactly what the simulator does with `sim --clingy-rate 0.15`. [Certain, run on
2026-10-22] Note that the lower slab of the pair has **no row** in `certs.csv` (OPERATING.md §5.4).

### 13.6 Sensor-fault test: the machine must refuse to probe

(20 min)

**A. Probe unplugged, machine idle.** Unplug the optical sensor at the Rodent's Y-MAX connector,
then try each command. [Certain for the messages, from `ops.py`, `runner.py` and FluidNC as
documented in FIRMWARE.md]

| Command | Expected |
|---|---|
| `python -m slabscan selftest` | `[FAIL] probe: reads TRIGGERED at rest …` |
| `python -m slabscan calibrate z` | refuses: "The probe reads TRIGGERED with the head at the top …" |
| `python -m slabscan jog`, then `probe` | "Refused: the probe already reads TRIGGERED …" |
| `python -m slabscan run`, with junk slabs loaded | It homes, goes to pocket 0 and drops to 216 mm, the start of the first probe window, which is above the MAX line where nothing can be. The first `G38.3` is then refused by FluidNC (`ALARM:4`) and the run stops with a `MotionError … ALARM:4` message. **No probe move happens.** [Certain, `runner._find_top`] |

**B. Flag blocked from entering the slot** (tape it back), probe plugged in:
- `run` → the survey of pocket 0 stops with **"Pocket 0: probe never touched anything (not even the
  pad)"**.
- Or, if the cup happens to seal on the pad: "the cup sealed on something but the contact sensor
  did not trip".
- The probe target is bounded, so the buffer is squeezed a few mm at most. [Certain, `runner.py`]

**C. Cut the sensor's 5 V or cover its emitter:** same as A (FIRMWARE.md step 5's fail-safe rows).

**Pass:**
- no probe move in A or C: the cup never goes below 216 mm;
- a clean stop in B.

Plug back in and run `selftest -i`.

**Known gap** [Certain, from code; reproduced in the simulator with a camera fault]:
- An error that isn't a planned stop arrives **while a slab is in the cup**. Examples: an
  `ALARM:4` during placement, or a camera that returns no frame.
- The run then stops **without putting the slab back**: "The machine stopped without parking".
- The pump and valves are left as they were, then shut when the program exits. The slab hangs
  until the cup line leaks down.
- Until the software sends these errors through its normal secure step, treat that message as
  "catch the slab now" (OPERATING.md §8).

### 13.7 Stop, E-stop and resume

(30 min, extra but worth it)

1. 20 junk slabs across pockets 1–4. Start a run from the web page.
2. Press **Stop after this slab** mid-stack. Expect a park with nothing held, then **Resume**.
3. Press the **E-stop** while a slab is being carried.
   - Do what the message says: take the slab off, put it face-down on top of the pocket it names.
   - Release the E-stop and resume. The machine reconnects and homes first.
4. During a stop, take one slab off a stack and resume. It must refuse with "The stacks changed
   since the run stopped …". Put it back and resume.

**Pass:**
- every slab appears **exactly once** in `certs.csv` (no repeated `position`, no repeated cert);
- the count check matches.

### 13.8 Summary

| Test | Pass criterion | Result |
|---|---|---|
| 13.1 Dry run | 100/100, all certs right, count check OK | |
| 13.2 Marking | no mark after dry wipe; 300/300 reads | |
| 13.3 Drop | no damage, lands in the pocket | |
| 13.4 Power cut | holds ≥ 60 s in all three cases | |
| 13.5 Double pick | flagged, carried clear, no crash | |
| 13.6 Sensor fault | refuses to probe; clean stop | |
| 13.7 Resume | every slab exactly once | |

---

## 14. First real batch, supervised

1. **Start small:** 30 low-value slabs in one pocket.
   - Before loading, record their certs another way: a phone app, a hand scanner, or by typing.
   - Then you can check the machine against something independent.
2. **Watch the whole run.**
   - Hand near the E-stop for the first ten cycles.
   - Listen for scraping (a rod touched) and watch each set-down.
3. **Check every row:**
   - `certs.txt` against your list;
   - `report.html` photos against the slabs;
   - the slabs themselves under raking light for any mark.
   - **Any wrong cert at all → stop and investigate before the next batch.**
4. **Then 100 slabs** across 4 pockets, supervised.
5. **Then a full load**, staying in the room for the first hour.
6. **Don't leave it unattended** until you have three full runs with no unexplained stop and no
   wrong cert. [Guessing threshold]
   - Even then, keep it where nobody can reach into the bed.
   - Use the web page only on your own network: it has no login. [Certain, software README]

---

## 15. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `selftest`: probe reads TRIGGERED at rest | Cut wire, sensor unplugged, flag sitting in the slot, or a board with an LED circuit that holds the input | Check the flag is clear at rest; FIRMWARE.md step 5; WIRING.md §6 fallback (bare TCST2103) |
| Probe never triggers when the cup is pushed | Flag misses the slot, a rotating buffer turned the flag away, or the sensor is mounted the wrong way round | §7.6; guide the flag or use the K buffer |
| `calibrate z`: no contact down to Z −7.0 | Head sits too high: carriage-to-cup > 245 mm, or the Z switch is low | Re-set 243 ± 2 mm (§7.5), re-check the Z switch position (§7.4) |
| `calibrate z`: spread > 0.3 mm | Loose cup or buffer nuts; pad not flat; flag loose | Tighten the M10 nuts; re-glue pad 0; tighten the flag |
| `calibrate x`: error > 1.5 mm | Belt slipping, pulley grub screw loose, or the holes weren't drilled with `mark` | Grub screw on the flat with threadlocker; re-tension (§6.6) |
| Positions drift during a run | Lost steps: belt too loose, X current too low, or carriage binding | Tension; roll the carriage by hand power-off; check `run_amps` |
| Stop: "cup will not seal" | Dirty cup lip, slab face-up, warped holder, sleeve left on | Wipe the cup with IPA, remove sleeves, check orientation, then resume |
| Seal is slow or fails on every slab | Leak: tube not seated, cracked fitting, vent valve seat | Leak test §8.3, pinch method |
| Stop: "Vacuum lost in transit" | Leak, pump weak, slab knocked a rod | Leak test; watch the next carry; check rods near that pocket |
| Stop: "taller than expected" on a pocket you didn't touch | A slab sitting crooked on a rod; double-placed slab | Seat the slab flat; resume |
| Stop: "contact … above the stack - something is in the way" | Slab crooked in the output pocket, or a rod leaning in | Fix the slab; slab drop test on that pocket (§5.8) |
| Head camera vanishes or errors mid-run | USB extension through the drag chain (about 4 m) | Re-seat; check bend radius ≥ 40 mm; drag-chain-rated USB cable (BOM note). **A slab may be hanging: §13.6 known gap.** |
| Station camera not found | Ribbon backwards or not latched; wrong port | Power off, re-seat per the Raspberry Pi camera guide, CAM/DISP 0 |
| Labels read on the bench but fail on the machine | Focus moved; ring not on; glare from room lights | `focus head` / `focus station --save`; fit the light roof |
| Many `needs_review` "ITF only; padding vs check digit not learned yet" | Not enough slabs yet where QR and ITF both read | Normal on the first batches; it learns from 3 agreeing slabs |
| Overfill beam reads blocked with nothing there | Misaligned laser, receiver trimmer, a receiver wire cut (reads blocked by design) | §12.5; WIRING.md §8 |
| Overfill beam reads clear when blocked | Room light swamps the receiver, or its GND wire is cut | Trimmer under room light; check the GND wire; light roof |
| Controller lost (E-stop) and resume says "still not answering" | The CH340 is slow to come back | Wait 10 s and press resume again; check the USB cable and the 24 V supply |
| Motors hot (> 60 °C) | `r_sense_ohms` doesn't match the board | Power off. FIRMWARE.md step 0. |
| Z drops when the E-stop is pressed | Detent torque too low with the head's weight | Brake or counterweight before unattended use (§7.8) |
| Scraping as the head crosses the row | Spine bottom below 226 mm, a tall rod, a loose cable loop | §7.1 height; trim that rod; re-tie the Z loop (WIRING.md §11) |
| `run` says calibration missing | `calibration.toml` lacks `pad_trigger_c` / `offset_x` | §12.1–12.2 |

---

## Sources

- **Repository files (primary for every [Certain] tag above):**
  - `cad/layout.py`, `cad/model.py`, `cad/out/cut_list.csv`, `cad/out/checks.txt`,
    `cad/out/printed/print_list.json`;
  - `software/slabscan/*.py`, `software/tools/phase0.py`;
  - [CONTRACT.md](CONTRACT.md), [WIRING.md](WIRING.md), [FIRMWARE.md](FIRMWARE.md),
    [BOM.md](BOM.md), [DESIGN.md](DESIGN.md).
- **Prusa PETG settings and the smooth-PEI warning:**
  [help.prusa3d.com/article/petg_2059](https://help.prusa3d.com/en/article/petg_2059)
- **TCST2103 gap and aperture:**
  [Vishay datasheet](https://wwwlegacy.vishay.com/docs/81147/tcst2103.pdf),
  [Farnell listing](https://uk.farnell.com/vishay/tcst2103/sensor-optical-phototransistor/dp/1470060)
- **SMC buffer letters (J rotating, K non-rotating; B5 = M5 female, A10 = M10×1):**
  [Proax ZPT25BNJ10-B5-A10](https://proax.ca/en/product/811689/smczpt25bnj10b5a10),
  [Proax ZPT25BSK20-04-A10](https://proax.ca/en/product/811703/smczpt25bsk2004a10)
- **M3 screw torque into aluminium (0.98 N·m):**
  [AL Motion installation & lubrication PDF](https://www.almotion.nl/wp-content/uploads/2021/09/Installation_lubrication.pdf)
- **GT2 tension, third-party range only:**
  [everycalculators GT2 calculator](https://everycalculators.com/gt2-belt-tension-calculator.html),
  [printpal belt tension wiki](https://printpal.io/wiki/belt-tension-and-calibration)
- **M5 heat-set insert hole (generic 6.4 mm):**
  [heat-set insert spec sheet](https://www.albanycountyfasteners.com/media/64/3d/5a/1764619189/heat-set-insert-specs.pdf)
- **Titebond II times:**
  [woodworkingadvisor glue chart](https://woodworkingadvisor.com/wood-glue-types-comparison-chart-strength-dry-time/),
  [Dictum Titebond II Extend](https://www.dictum.com/en/titebond-ii-extend-wood-glue-473-g/450387)
- **Raspberry Pi OS Trixie default, Bookworm as Legacy:**
  [raspberrytips: Trixie released](https://raspberrytips.com/raspberry-pi-os-trixie-released/),
  [raspberrytips: which version](https://raspberrytips.com/raspberry-pi-os-versions/)
- **Clippard EV-2 (10-32 in-line, 28 inHg vacuum in the 2005 catalogue):**
  [EV-2-24 datasheet](https://www.clippard.com/part/datasheet/EV-2-24.pdf); I could not open it
  from here.
