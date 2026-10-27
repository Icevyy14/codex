# SlabRail reviewer brief

Read this first if you received the SlabRail design-review package. It says what the machine is,
what has and has not been verified, and the questions we would most like an engineer to answer.

**Nothing has been built.** Every result below comes from CAD checks, software tests, a simulator
or public label scans. No real slab, camera, cup, motor or wire has been tested. The next step is
the two Phase 0 bench tests (§3).

Confidence tags are the ones the other docs use: **[Certain]** = measured, computed, or checked in
the CAD or the simulator; **[Likely]** = strong inference; **[Guessing]** = needs a real test.
A tag is copied from the doc the number comes from. Units are mm unless stated. "DESIGN §4" means
section 4 of `docs/DESIGN.md`; "D-05" is a sheet of the drawing set (§9.2).

## Contents

1. [What it is](#1-what-it-is)
2. [Requirements as the owner gave them](#2-requirements-as-the-owner-gave-them)
3. [Status and evidence](#3-status-and-evidence)
4. [The machine at a glance](#4-the-machine-at-a-glance)
5. [One slab's trip](#5-one-slabs-trip)
6. [Safety and failure handling](#6-safety-and-failure-handling)
7. [What we'd like you to review](#7-what-wed-like-you-to-review)
8. [Top risks](#8-top-risks)
9. [How to read this package](#9-how-to-read-this-package)
10. [Glossary](#10-glossary)

## 1. What it is

SlabRail reads the cert numbers of graded trading-card slabs (PSA and CGC) without anyone
watching. One straight row of 14 cells sits under one 4040 gantry beam: 13 pockets formed by
wooden dowels, and an upward-looking read camera in cell 7. The owner loads up to 330 slabs
face-down in pockets 1–11 (11 stacks of 30). A suction cup on the head lifts the top slab of a
stack straight up, a camera on the head reads the back label, and the cup sets the slab down in
the empty pocket to its left. Stack by stack, every stack ends up one pocket to the left. A slab
whose back cannot be read is held over the upward camera, which reads the front label. Anything
still unread or doubtful goes to pocket 12, the exception pocket. The result is `certs.csv` (cert,
grader, status, and the pocket and position each slab ended up in) with a photo of every label.
There are two motors: X moves the head along the row on a belt, Z moves it up and down on a lead
screw.

![SlabRail, CAD render](img/machine_iso.png)

The owner is a student building it in a school shop with the help of mechatronics instructors.
README.md states the alternative plainly: **[Likely] a $350–650 hands-free 2D scanner gets you 80%
of the way with no build** (20–30 slabs per minute by hand). The machine buys back about 10–15
minutes per batch and adds a photo of every slab. Loading and unloading still take about 10
minutes either way.

## 2. Requirements as the owner gave them

| Requirement | Where it is written | How the design answers it |
|---|---|---|
| Load 200–300+ slabs, walk away, get every cert number back | README.md: "Load up to 330 graded slabs (11 stacks of 30) and walk away. About 80 minutes later you have `certs.csv` with every cert number"; DESIGN §1–2 | 330 per load. One CSV row per slab loaded, with a count check. Simulated batch time 79.4 min (§4). **Caveat:** until the learned face-down check is active, every slab without a back-label code (PSA 2016 and older, CGC Authentic, BGS, SGC) stops the run for the operator (§5 step 3). The build guide says not to leave it unattended until three full runs have had no unexplained stop and no wrong cert [Guessing threshold] (BUILD_GUIDE §14). |
| PSA first, CGC too | README.md title; CONTRACT "Graders" | Both are read and stacked normally. BGS and TAG go to pocket 12, and only if their holder is ≤ 82.6 mm wide. SGC (about 86 mm) does not fit the 84 mm pocket. |
| Fewest moving parts | DESIGN §2 ("You asked for the fewest moving parts") | One row instead of a grid removes the Y axis: 2 motors, not 4. Moving parts: X belt axis, Z lead-screw axis, a spring-loaded cup, 2 valves, 1 pump (README). |
| Budget about $2,000; $2,500–3,000 acceptable if it works properly | CONTRACT "Budget" | $2,181.94 with a 15% allowance [Likely ±10%]; worst case about $2,380 [Guessing] (BOM.md). |
| Built with school-shop tools | CONTRACT "Budget": school 3D printers and mechatronics instructors; BUILD_GUIDE intro | Extrusions bought cut to length (Misumi, ±0.5 mm), 25 printed PETG/PLA parts, rod holes drilled by the machine itself through a printed template (BUILD_GUIDE §5B). Tools likely to be bought: about $45–50 (BOM.md). 65–90 h of hands-on work [Guessing]. |

The docs also treat these as hard rules: the cup touches only the back of a slab (DESIGN §3); no
slab ever slides on another (DESIGN §2); a wrong cert is worse than no cert, so the software never
guesses (OPERATING "Read this first"); and nothing for the motion system is bought until both
Phase 0 gates pass (BOM.md order plan).

## 3. Status and evidence

**Nothing has been built.** The design is drawn, checked in CAD and simulated. The next step is
two bench tests that decide whether the machine gets built at all:

- **Phase 0A, camera test** (≈ $470, ≈ $281 with a borrowed Pi): both cameras and LED rings on a
  printed jig that holds the machine's own head parts where the machine holds them, on 30–50 of
  the owner's slabs. GO needs at least 95% read, 0 wrong certs, and 0 wrong certs and 0 false
  face-down proofs when the machine's rules are replayed on the captures (BUILD_GUIDE §1.9).
- **Phase 0B, cup test** (≈ $155): the real SMC cup on a hand vacuum pump. Seal, leak, and a
  24 h marking test on a junk slab. GO needs no mark that survives a dry microfiber wipe
  (BUILD_GUIDE §1.10).

| Evidence | What it shows | What it does not show |
|---|---|---|
| **CAD checks**: `cad/checks.py`, **177/177 pass** [Certain], re-run 23 Oct 2026; every number in `cad/out/checks.txt` | Exact minimum distances and all-pairs interference at every pick, place, travel, station, hard-stop and Phase 0 pose. Picking the last slab next to full neighbours clears them by 14.55 mm; loaded travel clears the rods by 21.4 mm; a double pick of two 11.5 mm holders by 5.33 mm; a held slab at the Z top hard stop clears the carriage parts by 5.0 mm. Camera lines of sight, the face-down card window, switch trip points, the carry-height sensor trip (c = 246.50), the probe trip (2.00 mm of buffer travel), the Phase 0 jig matching the machine. | Loads, stresses or deflection; belt slack; cables and the vacuum tube; the real shapes of bought parts (buffer, elbow, rings, switches are modelled from catalog or listing dimensions); the side load on the switch levers; the frame's corner brackets and joining plates (not in the CAD); print accuracy and tolerance stack-up. |
| **Software tests**: `software/tests`, **299 passed, 1 skipped** in 1135.84 s (full suite, 23 Oct 2026); the skipped real-image test passed on its own [Certain] | Cert parsing on the real payload strings of PSA and CGC labels, the grader and face-down rules, phantom-read handling, the learned face-down check and the camera-aim check, the carry-height sensor logic, every stop path with a slab in the cup, config checks. | Real cameras, real GPIO electrical behaviour, real serial timing with FluidNC. The bench-test tool (`tools/bench_tests.py`) has run only against the simulator. |
| **Simulator**: 330-slab batch, seed 7, default label mix, face-down check on [Certain, sim, 23 Oct 2026]. The simulator raises `Crash` on any unsafe move. | `ok` 324, `needs_review` 6; no `ok` with a wrong cert or grader. Face-down: 287 by back QR, 41 learned, 2 confirmed by the operator (43 would have stopped with back-label codes only). 14.2 s per slab, 79.4 min for the load. Scenarios: double pick, seal failure, overfill, Z stall (40 mm and 10 mm losses), stuck or cut carry sensor, Ctrl-C hard stop, unexpected error with a slab in the cup. | Real physics (air films, slip, vacuum leak rates, motor stalls). The label mix is [Guessing]. Every simulated slab is face-down, so the learned acceptances say nothing about face-up safety. The face-up score margin is synthetic. |
| **Real-label evaluation**: `tools/real_eval.py` on public scans of 64 real slabs [Certain for these images] | Native scans: 60 `ok`, 2 `needs_review`, 2 `no_read` (BGS and SGC carry no code); **0 wrong certs in an `ok`, 0 false face-down proofs**. Rescaled and degraded to the machine's cameras: 60 of 61 `ok`, 0 wrong, 0 false. | The rules were written from these same 64 slabs, so this shows they fit them, not that they hold on new ones. Flat studio scans have no slab-plastic reflections. Not the machine's cameras. |
| **Decode sweep**: synthetic labels in the real formats (`tools/decode_sweep.py`) [Certain for the synthetic labels] | The back QR reads at ≤ 0.14 mm/px through blur and strong glare; the front barcode needs ≤ 0.05–0.08 mm/px (the station camera gives 0.039). No misread in any cell. | Real labels through real slab plastic. |
| **Hardware** | Nothing. | Everything physical: camera reads through the plastic, cup sealing and marking, motor margins, frame stiffness, wiring, cycle time. Phase 0A/0B come next; the acceptance tests (BUILD_GUIDE §13) follow the build. |

## 4. The machine at a glance

| Parameter | Value | Source |
|---|---|---|
| Envelope | Bed 1416 × 289.5 mm (18 mm plywood on two 2040 base rails). Overall about 1.42 m × 0.32 m × 0.65 m tall, fits a 6 ft bench (README; not a CAD bounding-box measurement). | BUILD_GUIDE §4.1, `cad/out/cut_list.csv`, README |
| Frame | 2 × 2040 × 1416 base rails, 2 × 4040 × 401 uprights, 4040 × 1416 X beam (centre 400 above the pad top), 2040 × 340 Z spine, 2020 × 285 drop arm. The joints are not in the CAD. | `cut_list.csv`, `layout.py`, BUILD_GUIDE §4.3 |
| Pockets | 13 pockets and 1 station cell in one row, 92 pitch, cell centres X = 42 + 92·cell. Pocket interior 84 × 139: ±1.85 / ±1.75 play for an 80.3 × 135.5 PSA slab. 82 dowels, 5/16 in (7.94; 8 in the CAD), 218 above the pad, 12 from each pocket corner, leaving a 52 mm finger gap front and back. | `layout.py`, CONTRACT |
| Capacity | 330: pockets 1–11 × 30. Pocket 0 starts empty; pocket 12 is the exception pocket (the run stops when it holds about 28). | `layout.py`, OPERATING §5.5 |
| Slab | 80.3 × 135.5 × 6.6 nominal; design maximum 82.6 × 136.5 × 7.0; up to 65 g. Thick holders up to 11.5. | `cad/dims.py`, `layout.py` |
| Heights | MAX fill line 210, overfill laser 214, rod tops 218. 30 PSA slabs stand 188–207. | `layout.py`, DESIGN §4 |
| X axis | NEMA17 on a GT2 belt (20T pulley, 40 mm/rev, 80 steps/mm at 1/16). MGN12 rail, 1300 long, on the beam's upper front slot. Soft limits 22…1253; printed hard stops at cup X 15 and 1262; home switch at X 19. 15000 mm/min, 2000 mm/s². Run current 1.0 A. | CONTRACT, FIRMWARE, `layout.py` |
| Z axis | NEMA17 (1.5–2.0 A, ≤ 4 mH) with an integrated T8×8 lead screw, cut to 340 below the motor face; 400 steps/mm. MGN12 rail, 330 long, on the 2040 spine. Software range c = −12…250; firmware soft limits −8…255; printed hard stops at c = −14 and 262; top switch at c = 258. 6000 mm/min, 1200 mm/s². Run 0.8 A, hold 0.5 A. | CONTRACT, FIRMWARE, `layout.py` |
| Travel heights | Empty and loaded travel at c = 248. Station read at c ≈ 171.6. A probe never goes more than 12 past the predicted contact. | `layout.py`, `software/config/machine.toml` |
| Cup and buffer | SMC `ZPT25UUK20-B5-A10`: Ø25 urethane cup on an M10 spring buffer, 20 mm stroke, non-rotating. The probe trips at 2.0 ± 0.5 mm of buffer travel (about 1.2 N [Likely]). Holding force 19.1 N at −50 kPa, SF 30 on a 0.64 N slab [Certain]. The software accepts a seal at −35 kPa within 0.4 s. | CONTRACT, DESIGN §4, `slabscan/config.py` |
| Vacuum | 24 V diaphragm pump; two Clippard EV-2-24 direct-acting normally-closed 2/2 valves (vacuum, vent); a reservoir (about 300 mL) and check valve on the pump side; an XGZP6847A sensor (−100…0 kPa) read through an ADS1115 on the cup side. | BUILD_GUIDE §8.1, CONTRACT |
| Sensors | Optical contact probe (TCST2103 board, flag on the buffer, fail-safe, Rodent input); carry-height sensor (second TCST2103 on the Z spine, Pi GPIO 6, blocked from c = 246.5 up); vacuum sensor; overfill laser gate (receiver on GPIO 5); X home and Z top NC microswitches (Omron SS-5GL size); optional lid switch (GPIO 25). | CONTRACT, WIRING §5–8 |
| Cameras | Head: ELP 8 MP IMX179 USB board, 3.6 mm M12 lens, 140 above the held slab's back, 5 toward the label end from the cup axis, 0.055 mm/px. Station: Raspberry Pi Camera Module 3 in cell 7 (X 686), 140 below the held slab's front, 0.039 mm/px. | CONTRACT, DESIGN §5 |
| Lighting | 12 V COB LED rings around each lens: 40 mm at the head (the seat takes 39.5–42.5 OD), 60 or 63 mm at the station. The ring's mirror image lands within about 12 of the lens axis and the label band sits 40–65 off it, so no polarisers [Certain, mirror geometry]. A black foam-board light roof is optional. | DESIGN §5, CONTRACT |
| Controller and computer | BTT Rodent V1.x (ESP32, four TMC2160 drivers) running FluidNC v4.1.1 or newer, on USB serial to a Raspberry Pi 5 4 GB (Raspberry Pi OS Bookworm, Python 3.11). The Pi switches the pump, valves and rings through five logic-level MOSFET modules. | CONTRACT, FIRMWARE |
| Power | IEC C14 inlet with a T3.15A fuse and rocker in a closed ABS box; Mean Well LRS-150-24 (6.5 A) set to 24.5 V; E-stop with two NC blocks in series in the +24 V line; branch fuses F1 5 A (Rodent), F2 3 A (pump and valves), F3 1 A (24→12 V buck for the rings). Load about 1.2 A typical, 3.4 A peak [Guessing]. The Pi runs on its own 27 W USB-C supply. | WIRING §1 |
| Cycle and batch time | 14.2 s per slab; 79.4 min for 330 slabs, including 75 s of homing and survey [Certain, sim; Guessing until measured on the machine]. Slabs that need the front camera and OCR take up to 30 s more each. | DESIGN §6, README, OPERATING §4 |
| Parts cost | $1,897.34 of parts; **$2,181.94 with a 15% allowance** [Likely ±10%]; worst case about $2,380 [Guessing]; about $1,862 if the school supplies its shop stock. The Phase 0 orders (≈ $470 and ≈ $155) are inside that total. Junk test slabs ($150–400) are not. | BOM.md, SHOPPING_LIST.md |
| Printed parts | 25 STL files, 27 prints, 801 cm³; PETG for machine parts. About 44.5 h of printing. | `print_list.json`, BUILD_GUIDE §3.2 |

## 5. One slab's trip

Before the first slab, the run homes (Z up to its top switch, then X left to its home switch),
refuses to start if the overfill laser beam is blocked, and surveys every pocket with the contact
probe: pockets 0 and 12 must be empty and nothing may be above the MAX line. In learned mode it
also takes one head-camera frame over an empty pocket, for the camera-aim check. Then, for every
slab (`runner.transfer`, OPERATING §4):

| # | Step | Guarded by |
|---|---|---|
| 1 | Move over the source pocket at travel height c = 248. | **Carry-height sensor** must read blocked before any sideways move; **vacuum sensor** checked on every move while a slab is held. |
| 2 | Drop to just above the predicted top of the stack. | Every downward move is a guarded `G38.3`: the **optical contact probe** stops it on any contact. |
| 3 | Take one head frame: the face-down check and a first read of the back label. | **Head camera.** No back-label code and no learned card-back match: the run stops before the cup touches the slab. A front-label code seen from above: stops as FACE-UP. |
| 4 | Probe down to the real top, at most 12 past the predicted contact. A top more than 4.5 taller than predicted stops the run. | **Contact probe** (fail-safe: a cut wire or dead emitter reads as touching, so FluidNC refuses to probe). |
| 5 | Grip: the cup line must read atmosphere, then pump and vacuum valve on; seal at −35 kPa within 0.4 s, one retry. | **Carry-height sensor** must read clear here (a dark sensor would read blocked); **vacuum sensor**. |
| 6 | Peel: the head rises the 2 mm the buffer was squeezed at 20 mm/s, then 2 mm/s through the point where the cup leaves the slab and 1 mm past it, then waits 0.5 s low over the stack, so a slab clinging by an air film falls back. | **Probe hard limit** in the firmware: a probe edge outside a `G38` move is a critical alarm. |
| 7 | Lift to c = 248 and take two head frames of the back. Decide the read. | **Carry-height sensor** must read blocked before the next sideways move: a Z stall that left the head more than about 2.5 low stops the run. **Vacuum sensor**: transit alarm above −25 kPa. |
| 8 | If the back gave no confident read, or only barcodes: carry the slab to cell 7, lower it to c ≈ 171.6, take station frames, lift, and move over the output stack before decoding and OCR (up to 30 s on the Pi). | **Station camera**; vacuum check at the station; carry-height sensor before each sideways move. |
| 9 | Route it: `ok`, or `needs_review` with grader PSA or CGC, goes to the output pocket (the next pocket left); everything else goes to pocket 12. A full pocket 12 stops the run. | Decision rules in `slabscan/certs.py` (DESIGN §5). |
| 10 | Probed set-down onto the target stack, slow (1200 mm/min) through the rod tops. The contact step is the slab's thickness. | **Contact probe.** A step of 11.6 or more is a DOUBLE PICK; a step far too large means something in the way; a step under half a slab means the cup is empty. Each stops or flags. |
| 11 | Vent (0.25 s); the line must be back within 0.5 kPa of atmosphere within 1.5 s before the head lifts. | **Vacuum sensor.** A failed vent: nothing moves. |
| 12 | Write the CSV row, the photos and the journal entry. A code-proven slab whose read agrees becomes a reference for the learned face-down check, only now that it is placed. | Count check at the end of the run. |

A slab whose back reads is in the air about 2 s per cycle (DESIGN §3).

## 6. Safety and failure handling

### 6.1 Power chain and E-stop

The mains side is an IEC C14 inlet with a built-in T3.15A fuse [Likely: still to be checked
against the LRS-150 datasheet's input current and inrush] and a rocker switch, in a closed ABS box
with a cable gland. No mains metal may be exposed with the cord plugged in; an instructor checks it
before first power-up (WIRING §1.1, §14). The frame is earthed by one bond to the base 2040; the
only 0 V-to-earth bond is at the supply (WIRING §12).

The E-stop is a latching 22 mm mushroom with **two NC contact blocks in series** in the +24 V line
right after the supply (WIRING §1.3). It cuts the Rodent (both motors and the controller logic),
the pump, both valves and the 12 V buck. It does not cut the Pi, which keeps its own supply, sees
the controller's USB port vanish, and stops the run. Two blocks are required because releasing the
E-stop charges the Rodent's and buck's input capacitors through the contacts, and that inrush can
weld one closed [Likely]; a welded NC contact is invisible. The block ratings may be AC only
[Guessing]. A monthly check (press it; the 24 V bus must read 0 V) is the only detection.

On an E-stop or a mains cut the motors go limp. Z is expected to hold on detent torque [Likely],
and both NC valves close, so a held slab hangs only as long as the cup line's own leak allows. The
reservoir does not help: it is on the pump side of the closed vacuum valve (DESIGN §3). Acceptance
test 13.4 asks for at least 60 s [Guessing target]. Ctrl-C twice halts the motors but leaves them
powered; only the E-stop removes motor power (OPERATING).

### 6.2 Laser

The overfill gate is a ≤ 1 mW (Class 2) 650 nm module in the left gate post, aimed at a receiver
in the right post, 4 mm above the MAX line (214 above the pad). It is fed from the Pi's 5 V, so it
is on whenever the Pi is on, at about the height of a face bent over the stacks while loading. The
KY-008 laser sold with the receiver kit is usually 5 mW (Class 3R) and is excluded by name
[Likely]. Both posts carry a Class 2 warning label (WIRING §8).

### 6.3 Pinch points and guarding

No document analyses pinch points, and the CAD has no guard or enclosure. What exists:

- Every downward head move is a probing move, so contact that pushes the cup up should stop the
  head: the buffer pushes about 1.2 N at the trip and about 1.6 N after a trip at full Z speed
  (DESIGN §3, §4) [Likely; nobody has tested it against a hand]. Contact with any other head part
  (foot, camera bracket, drop arm) is not sensed.
- No sensor watches the X path, and FluidNC has no stall detection here (FIRMWARE open issue 5).
- Moving parts from the CAD layout: the GT2 belt loop over the beam top with the motor at the right
  end and the idler at the left; the X carriage against its end bumpers; the head descending
  between the dowels into each pocket; the Z carriage closing on the `z_motor_mount` at the top
  stop and on the `z_end_cap` at the bottom; the drag chain on the beam.
- Procedure: "hands out of the bed" before each run (OPERATING §1), a "hands clear?" prompt on
  resume, the `mark` command waits for `clear` (BUILD_GUIDE §5B), an optional lid switch that
  pauses the run with nothing held, and "keep it where nobody can reach into the bed" for unattended
  use (BUILD_GUIDE §14). The web page has no login: use it only on a private network.

### 6.4 Failure handling

| Failure | Detected by | What the machine does | Designed in | Tested in |
|---|---|---|---|---|
| **Vacuum loss or drop** | Vacuum sensor: transit alarm above −25 kPa | Never lets go in mid-air: carries the slab back slowly over its own pocket and probes it down; if it is gone, the message says where it may have fallen. A fall from carry height is ≤ about 240 mm, about 0.15 J [Certain, arithmetic]; a corner landing on a dowel top could chip a slab [Guessing]. | DESIGN §3 "Drops"; `runner._set_down_weak` | Simulator (seal failure stops). On hardware: §13.3 drop test (destructive), §13.4 power cut. Not run. |
| **Double pick** | Contact step at placement ≥ 11.6 (`t_double`) | Places the pair; the read slab is `needs_review` with "DOUBLE PICK", and the slab under it gets its own `no_read` row ("UNREAD"). A pair of two 11.5 holders clears the rods by 5.33 at c = 248 [Certain, CAD]. Prevention: the slow peel and 0.5 s dwell. | DESIGN §2a, §4; `runner.transfer` | Simulator (`--clingy-rate 0.15`); §13.5 with taped and untaped pairs. |
| **Z stall** | Carry-height sensor reads clear at travel height | Stops before any sideways move. A held slab is lowered by one probe move over its own pocket, otherwise held on the pump. It does not prevent a stall: the Z motor must still pass the 100-lift test. | DESIGN §3 layer 8; WIRING §6a; `runner._carry_check` | Simulator (40 mm and 10 mm losses, stuck or cut sensor); §13.6E; §7.8 lift test (bare pad re-probed within 0.1 mm after 100 lifts). |
| **Misread** | Consensus rules: a QR names its cert; a barcode-only read needs a second printed symbol or OCR to agree, and its grader confirmed; codes that disagree are a `conflict` | `conflict`, `no_read`, `other_grader` and grader-less `needs_review` go to pocket 12. The machine never guesses. | DESIGN §5; `slabscan/certs.py` | Unit tests on the real payload strings; real-label evaluation (0 wrong of 64); decode sweep (0 misreads); Phase 0A gate (0 wrong); §13.1. |
| **Face-up slab, or one it cannot prove face-down** | Head frame from above: a back-label code, or (learned mode) a card-window match with two references; a front-label code means FACE-UP | Stops before the cup touches it. The operator turns it over, or confirms that one slab with `resume --face-down-ok`. With `--all-face-down` the check is off and a face-up slab gets the cup on its front. | DESIGN §3 layer 7, §5; `runner._check_face_down` | Simulator; real-label evaluation (0 false face-down proofs); §13.8 A and B. |
| **Overfill** | Laser beam 4 above the MAX line, checked at start with the head up; the survey measures every stack | Refuses to start. A slab lying across the rod tops is above the beam; the survey catches it because its first probe window starts at travel height. | DESIGN §3 layer 6; WIRING §8 | Simulator ("overfill refused"); `selftest` with the beam blocked. |
| **Contact sensor fault** | Fail-safe wiring (cut wire, dead emitter, dirt read as triggered); a cup that seals without a probe trip | FluidNC refuses to probe (ALARM:4); the survey stops. | WIRING §6; DESIGN §3 layers 3–5 | §13.6 A–C. |
| **Unexpected error with a slab in the cup** | The run's guard (camera off USB, decoder bug, controller error) | Re-reads its position, lifts straight up, puts the slab back on its stack. Where moving is unsafe, nothing moves and the pump holds the slab for the operator. | OPERATING §8; `runner.secure` | Simulator; §13.6D. |

## 7. What we'd like you to review

Each question can be answered from the package. A short answer with the question number is
enough.

1. **Frame joints.** The CAD has no brackets or joining plates. BUILD_GUIDE §4.3 recommends
   [Guessing on the layout]: two 4040 L brackets inside each beam-to-upright corner and one flat L
   plate on the back face (none on the front, where the X rail ends only 18 mm from each upright),
   and the uprights fixed to the back base rail by L brackets bolted with M5×30 through the 18 mm
   plywood into T-nuts. Is that stiff and square enough for a 1.9 kg carriage at 2 m/s², or should
   the uprights be end-tapped and bolted to the base rail from the start? (D-01, D-02)
2. **Beam twist.** DESIGN §4 estimates ≈ 0.8 mm of twist at the cup at midspan from the 127 mm
   head overhang [Guessing on J], against ±1.75 pocket play and a 0.5 calibration residual
   (`XY_CAL_RESIDUAL`). Sag is 0.18 mm under 20 N [Certain, beam formula]. BUILD_GUIDE §6.7 adds a
   rear brace only if a 0.75 kg load moves the cup more than 1.0 mm. Is the estimate credible for
   a 4040 loaded on one face, and is 1.0 mm the right trigger? (D-04, D-01)
3. **Z torque margin at 0.8 A.** Z lifts a 0.75 kg head at 1.2 m/s² (8.3 N, 0.026 N·m on the
   T8×8 at 40% efficiency) with the motor at 0.8 A, 40–55% of its rating: SF ≈ 2–4 [Likely]
   (DESIGN §4). The BOM motor (1.7 A, 0.44 N·m) has no published torque curve. Would you start at a
   higher current or a lower speed, and is the 100-lift test in BUILD_GUIDE §7.8 a sufficient
   acceptance test? (D-05; FIRMWARE open issue 5)
4. **Z hold with power off.** Back-drive ~0.005 N·m against ~0.015 N·m detent, so it holds
   [Likely] (DESIGN §4); the test is BUILD_GUIDE §7.8 (200 g on the cup, E-stop, 1 minute). The
   margin rests on a detent figure, not a measurement. Should a constant-force spring or brake be
   designed in now? The BOM lists one as a conditional line, but its mount is not in the CAD.
   (D-05; FIRMWARE open issue 4)
5. **Homing switch side load.** Both home switches are worked by a striker that slides across a
   hinge lever: a 45° lead-in, then a flat that holds the lever 0.6 mm past its click, under its
   1.2 mm overtravel; the hard stops are 4 mm past each click. The lead-in pushes the lever
   sideways about as hard as down, and the datasheet rates only a straight push [Guessing that it
   holds]. Acceptable, or would you use a roller lever on a cam or a different switch?
   (BUILD_GUIDE §6.8, §7.4; printed-part sheets for `x_switch_mount`, `z_switch_mount`,
   `x_bracket`, `z_plate`)
6. **PETG parts near motors and under load.** Every machine part is PETG; the load-bearing ones
   (`x_bracket`, `z_plate`, `z_motor_mount`, `x_motor_mount`, `head_foot`) print with 5–6 walls and
   40–50% infill. They carry the Z motor, the head and the belt tension (target 15–25 N
   [Guessing], BUILD_GUIDE §6.6), next to motors allowed to reach about 50 °C. No doc checks their
   creep, stiffness or temperature. Which would you make in aluminium or another plastic, and is
   the belt tension target right? (BUILD_GUIDE §3; printed-part sheets D-07 on)
7. **Cup holding margin and marking.** DESIGN §4 gives 19.1 N at −50 kPa (SF 30 vertical, SF 70
   lateral at 2 m/s²) [Certain]. The software accepts a seal at −35 kPa and alarms in transit only
   above −25 kPa (`config.py`); the margin at those thresholds is not computed. Marking is screened
   by a 24 h hand-pump test (Phase 0B), then 300 cycles and 24 h at a mean ≤ −40 kPa on the machine
   (BUILD_GUIDE §13.2). Is that enough to rule out marks on slab plastic, and what would you add?
   (DESIGN §3, §7; Phase 0 test jig sheet)
8. **Drop exposure and power-cut hold.** A drop from carry height is ≤ about 240 mm, 0.15 J
   [Certain, arithmetic]; a corner on a dowel top could chip [Guessing]. On power loss the slab
   hangs only on the closed cup line (§6.1). BUILD_GUIDE §8.2 keeps a cup-side reservoir as the
   fallback if §13.4 fails. Is relying on the cup line's leak rate acceptable for unattended runs?
   (DESIGN §3)
9. **E-stop and mains.** Is a DC-side E-stop with two NC blocks in series, AC-only ratings
   possible [Guessing], a monthly check, a T3.15A inlet fuse not yet checked against the supply's
   inrush [Likely], and one frame earth bond across anodised joints [Likely: they may need
   serrated washers] acceptable for this machine? Or would you move the E-stop to the mains side
   or add a force-guided safety relay (WIRING §1.3: an ordinary relay can weld the same way)?
   (WIRING §1, §12)
10. **Sensor fail-safety.** The contact probe fails safe. The carry-height sensor does not: its
    "OK to move" state is dark, so a dead emitter, dirt or a cut GND reads "at height" and is
    caught only at the next grip [Certain] (WIRING §6a, open risk 8). The probe flag may chatter at
    the slot edge during the slow peel; the proposed fix is a Schmitt stage [Guessing] (WIRING §6).
    Is a once-per-slab check enough for the stall guard, and is the hysteresis fix sound?
    (D-05, D-06)
11. **Head camera aim.** The learned face-down check needs the head camera within 1.34° toward
    the cup (CAD aim check). On a CGC slab pushed into a pocket corner, about 0.01° toward the label
    puts more than 2% of the card window on the holder [Likely]. The camera board sits on
    `camera_bracket` on the 2020 drop arm, and the only adjustment is an M2 washer shim (about 0.5°
    [Likely]). What aim can that stack-up hold, and how would you measure it? (DESIGN §5 "Limits";
    BUILD_GUIDE §7.7; D-05)
12. **Guarding.** There is no guard, enclosure or interlock beyond an optional lid switch (§6.3).
    What is the minimum guarding you would require before the owner leaves it running unattended
    in a home or a school?
13. **Tolerances.** Some tolerances on the drawings are marked as proposed. The design's own fits
    are the pocket play (±1.85 / ±1.75), rod holes drilled by the machine itself (so the beam's
    alignment to the bed does not set rod positions), Misumi cuts at ±0.5 mm, printed holes that
    come out 0.1–0.3 mm small [Likely], and squareness targets in BUILD_GUIDE §4.5 tagged
    [Guessing]. Are the proposed tolerances right for the function, and can a school shop hold
    them? (D-00 general notes, D-02, D-03, D-06, printed-part sheets)
14. **Cables and tube.** None are in the CAD: the X drag chain (15 × 30 mm inside, 1 m, R38 or
    larger [Guessing on the sizes sold]), the Z service loop (about 350 mm, no bend under 40 mm
    radius), the vacuum tube (about 1 mm under the head ring at full buffer stroke [Guessing]) and
    the head camera's USB at about 4 m [Guessing], the weakest cable. Do you see a routing,
    clearance or flex-life problem? (WIRING §11, §16; D-01, D-05)

## 8. Top risks

The full table, with what retires each risk, is DESIGN §7.

| Risk | Retired by |
|---|---|
| The owner's labels carry payloads unlike the 64 real slabs seen | Phase 0A on 30–50 of the owner's slabs: 0 wrong certs, ≥ 95% read |
| The cup leaves visible marks | Phase 0B (24 h, hand pump), then 300 cycles + 24 h on the machine. The fallback HT1 cup needs an M10×1-to-G1/8 adapter nobody has sourced: a cup that marks means stop and ask. |
| Slabs without a back-label code stop the run | The learned check after a Phase 0 GO and 5 references: 2 stops in 330 in the simulator [Certain, sim; Guessing for real backs through plastic] |
| A real face-up front is accepted as a card back | Two references per match; a blue Water-type card in Phase 0's face-up pass; audit of every learned row in the first batches; any face-up pick in §13.8 turns the learned check off |
| Head camera aimed off, or a CGC slab in a pocket corner, puts a head part or the holder in the card window | The camera-aim check (a tilt toward the cup only, from about 1.3°); the owner's look at `face_down_window.jpg`. The 2% holder limit is a judgment, not a margin. |
| A Z stall drags a slab sideways below the rod tops | The carry-height sensor, plus the §7.8 100-lift test |
| A homing switch lever is too long, or wears under the side push | Measure and cut back past 23 mm; a 100-pass bench test before the build |
| Beam twist larger than estimated | Dial-indicator check in the build; rear brace |
| Another grader prints an 8-digit ITF that OCR reads, giving `ok PSA` [Guessing that one exists] | Put any non-PSA slabs the owner has through Phase 0 or `tools.real_eval` |

## 9. How to read this package

### 9.1 Documents

| File | What's in it | Read it if |
|---|---|---|
| `README.md` | One-page overview, verification summary, build order | You want the short version |
| `docs/DESIGN.md` | Why this architecture (§2), everything that touches a slab and the crash-prevention layers (§3), calculations (§4), label reading and the face-down check (§5), verification (§6), risks (§7) | You review mechanics, margins or the reading logic |
| `docs/CONTRACT.md` | The binding interface: layout, axes, heights, pins, CAD decisions, software commands | You need an exact number or pin |
| `docs/BUILD_GUIDE.md` | Phase 0 (§1), printing (§3), frame (§4), bed (§5), X and Z axes (§6–7), vacuum (§8), electronics (§9), calibration (§12), acceptance tests (§13) | You review buildability or test coverage |
| `docs/WIRING.md`, `docs/img/wiring.svg` | Power chain, E-stop, fuses, every wire, fail-safe sensor logic, pre-power checklist, open risks (§16) | You review electrical safety |
| `docs/FIRMWARE.md`, `firmware/fluidnc/config.yaml` | FluidNC on the Rodent: currents, speeds, limits, homing, probing | You review motion control |
| `docs/OPERATING.md` | Loading rules, the run sequence (§4), statuses, the stop table (§8.1) | You want to know what the operator sees |
| `docs/BOM.md`, `docs/BOM.csv`, `docs/SHOPPING_LIST.md` | Parts, prices, the order plan, test-triggered upgrades | You review cost or part choices |
| `docs/RESEARCH.md` | Existing products, slab dimensions, real label formats | You question the need or the label rules |
| `software/README.md`, `software/slabscan/`, `software/tests/` | Run loop, decoding, simulator, tests | You review the software |
| `cad/layout.py`, `cad/dims.py` | Master dimensions; everything else is generated from them | You check a dimension at its source |
| `cad/out/checks.txt` | All 177 CAD check results with their numbers | You check a clearance claim |

### 9.2 Drawing set

The PDFs are in `package/`. The index on D-00 is authoritative for sheet numbers.

| Sheet | Title |
|---|---|
| D-00 | Index and general notes |
| D-01 | General arrangement |
| D-02 | Frame and extrusion cut list |
| D-03 | Bed, pockets and guide rods |
| D-04 | X axis |
| D-05 | Z axis and head stack-up |
| D-06 | Flat parts (probe flag, carry flag) |
| D-07 onward | Printed parts, 2–4 parts per sheet |
| Last sheet | Phase 0 test jig |

### 9.3 CAD files

| File | What it is |
|---|---|
| `cad/out/assembly/slabrail_home.step` | Full assembly: head over pocket 1 at c = 248, no slab, full stacks |
| `cad/out/assembly/slabrail_pick_bottom.step` | Cup at c = 6.6 over pocket 11, picking its last slab, neighbours full |
| `cad/out/assembly/slabrail_carry.step` | A held slab at c = 248, between pockets 1 and 0 |
| `cad/out/assembly/slabrail_station.step` | A held slab over the read station, c ≈ 171.6 |
| `cad/out/printed/*.step`, `*.stl`, `print_list.json` | The 25 printed parts in print orientation, with sizes, volumes and print notes |
| `cad/out/probe_flag_blank.dxf`, `.svg` | The probe flag blank at 1:1 (24.4 × 55, 1 mm aluminium) |
| `cad/out/cut_list.csv` | Extrusions, lead screw, flag blanks, 82 dowels |
| GLB files (in the CAD zip in `package/`) | The assemblies for viewing without CAD software (any glTF viewer) |
| `cad/*.py` | The parametric CadQuery source. `build.py` exports; `checks.py` re-runs the 177 checks (about 12–15 min). |

Bought parts (extrusions, rails, motors, cameras) are simplified envelopes in the CAD, accurate
where they meet something else (`model.py`). Not in the CAD: frame brackets and joining plates,
cables, the vacuum tube, the electronics panel, the optional light roof and the optional rear
brace.

### 9.4 Coordinates

From `cad/layout.py`, in mm:

- **X** runs left to right along the row (the beam direction). Machine X is the position of the
  cup axis. Cell centres are at X = 42 + 92·cell: pocket 0 at 42, the station (cell 7) at 686,
  pocket 12 at 1238.
- **Y** runs front (−) to back (+). Y = 0 is the pocket row centre line, which is also the cup's Y:
  the cup never moves in Y. The label end of every slab points to −Y (toward the operator).
- **Z** is up. **Z = 0 is the top surface of the pocket floor pads.** The bed top is at Z = −3 and
  the base rails' underside at Z = −41.
- **c** is the machine's Z: the height of the cup face above the pad top, at the probe-trip
  calibration (the free cup hangs `CUP_HANG` = 2 below it).
- Card-window rectangles are given from the cup axis, −y toward the label end; the software's
  `face_down_window_mm` is the same window measured from the head-camera axis, 5 toward the label.

## 10. Glossary

| Term | Meaning |
|---|---|
| **c** | Cup-face height above the pad top: the machine's Z coordinate. Set by the probe trip, so the free cup hangs 2 below it. |
| **c_safe** | Travel height, c = 248 (`C_SAFE_EMPTY` = `C_SAFE_LOADED`): rod tops 218 + two 11.5 thick holders + 5 clearance + the 2 cup hang. |
| **C_MAX** | 250, the top of the Z range the software uses. |
| **Cell** | One of the 14 positions along the row, 92 apart. Cell 7 is the station; the others are pockets. |
| **Pocket** | A cell bounded by dowels, two per side, 12 from each corner (side rods are shared with the neighbour), 84 × 139 inside. Pockets 0–12, left to right. |
| **Source / output pocket** | Stack k is moved slab by slab onto pocket k−1, its output pocket. |
| **Exception pocket** | Pocket 12. Slabs that are `no_read`, `conflict`, `other_grader` or `needs_review` without a PSA or CGC grader go there for a hand check. |
| **Station** | The read station in cell 7: the upward Camera Module 3 that reads the front label of a held slab. |
| **Survey** | The start-of-run pass that probes every pocket: stack heights, pockets 0 and 12 empty, nothing above the MAX line. A resume repeats it and compares with the journal. |
| **MAX line** | The fill line, 210 above the pad, shown by the printed `fill_gauge`. |
| **Overfill gate** | The Class 2 laser beam at 214, 4 above the MAX line. Blocked means the run will not start. |
| **Contact probe / probe flag** | The optical sensor on the head foot. A 1 mm aluminium flag on the spring buffer enters its slot when the cup is pushed up 2.0 ± 0.5 mm (`buffer_trip_mm`). Wired fail-safe. |
| **Probe window** | How far a probing move may go past the predicted contact: at most 12, inside the buffer's 20 mm stroke. |
| **G38.3** | The FluidNC probing move that stops on contact. Every downward move uses it. |
| **Probe hard limit** | A firmware alarm when the probe trips during any move that is not a probe. |
| **Carry sensor (carry-height sensor)** | The second optical sensor, on the Z spine, read by the Pi. Its flag blocks it from c = 246.5 up. It must read blocked before every sideways move (Z stall guard) and clear at every grip. |
| **Peel** | The slow lift right after the grip (2 mm/s through the release point, then a 0.5 s dwell) that lets an air-film-clinging slab fall back. |
| **Double pick** | Two slabs lifted together; detected at placement by a contact step of 11.6 or more. The unseen slab gets an "UNREAD" row. |
| **Hover frame / held frames** | The head-camera frame taken just above the stack before the grip, and the two taken at carry height with the slab in the cup. |
| **Face-down check** | Before the cup touches a slab, the hover frame must prove it face-down. Modes: `learned` (default), `stop` (back-label codes only), `off` (`--all-face-down`). |
| **Back-label code** | A code printed only on the back label: a PSA back QR, a graded CGC QR, or the CGC 2020–23 back barcode. Seeing one proves the slab is face-down. |
| **FACE-UP stop** | A front-label code seen from above (a CGC front barcode or Authentic QR): the run stops untouched. |
| **Card window** | A 55 × 5.5 mm (302.5 mm²) strip of the card back, between the label and the cup, that the learned check compares. |
| **Learned face-down check** | Accepts a slab with no back-label code when its card window matches card backs of two different slabs already proven face-down on this machine. Active only after a Phase 0 GO (threshold ≥ 0.55), 5 references, and a clear camera-aim check this run. |
| **Reference** | A stored card-window descriptor from a slab proven face-down by its own code or by the operator, added only after the slab is placed and its read agrees. |
| **Camera-aim check** | One head frame over an empty pocket per run; edges where only the pad should show mean a tilt toward the cup, and the learned check is off for that run. |
| **`ok`** | A cert and grader the rules confirm: a QR, two printed symbols, or an 8-digit ITF that OCR confirms. |
| **`needs_review`** | A read the rules cannot confirm (one barcode, OCR disagreement, OCR only, a double pick). Stays in the output stack only with grader PSA or CGC; otherwise pocket 12. |
| **`no_read`, `conflict`, `other_grader`** | Nothing readable; codes that disagree; a BGS, SGC or TAG URL. All go to pocket 12. |
| **ITF rule** | A pre-2016 PSA slab's only code is one front ITF; an 8-digit ITF whose printed digits OCR reads the same is `ok` with grader PSA. |
| **Phase 0A / 0B** | The bench gates before any motion parts are bought: 0A reads the owner's labels with the real cameras on a jig; 0B tests the real cup for sealing and marking. |
| **Rodent, FluidNC** | The BTT motion controller board and the firmware on it. |
| **Thick holder** | A slab whose contact step is over 7.9 (PSA thick holders are about 10.25); flagged, and fewer fit under the MAX line. |
