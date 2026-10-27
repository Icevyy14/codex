# SlabRail reviewer brief

Read this first. It says what SlabRail is, what has been checked and how, where each kind of
information lives, what is missing, and what we would like you to review (§9). The files are
listed in §10.

**Nothing has been built.** Every result below comes from CAD checks, software tests, a simulator
or public label scans. No real slab, camera, cup, motor or wire has been tested yet.

Confidence tags are copied from the doc each number comes from: **[Certain]** = measured, computed,
or checked in the CAD or simulator; **[Likely]** = strong inference; **[Guessing]** = needs a real
test. **[Certain] on a calculation or a CAD check means the arithmetic or the geometry is exact for
the model and its inputs; it is not a test of the real part**, and many inputs are catalog values
or estimates (§8). Units are mm unless stated. "DESIGN §4" is section 4 of `docs/DESIGN.md`;
"D-05" is a drawing sheet (§10.2).

## 1. What it is

SlabRail is designed to read the cert numbers of graded trading-card slabs, PSA and CGC,
unattended. One straight row of 14 cells sits under one 4040 gantry beam: 13 pockets formed by
wooden dowels, and an upward read camera in cell 7. The owner loads up to 330 slabs face-down in
pockets 1–11 (11 stacks of 30). A suction cup lifts the top slab of a stack straight up, a head
camera reads the back label, and the cup sets the slab down in the empty pocket to its left, so
every stack ends up one pocket left. A slab whose back can't be read is held over the upward camera
to read its front label. Anything still unread or doubtful goes to pocket 12, the exception pocket.
The output is `certs.csv` (cert, grader, status, pocket and position) and a photo of every label.

![SlabRail, CAD render](img/machine_iso.png)

The owner is a student building it in a school shop. **[Likely] A \$350–650 hands-free 2D scanner
gets 80% of the way with no build** (README); the machine buys back about 10–15 minutes per batch
and adds a photo of every slab.

## 2. Requirements as the owner gave them

| Requirement | Where written | How the design answers it |
|---|---|---|
| Load 200–300+ slabs, walk away, get every cert number back | README; DESIGN §1–2 | 330 per load, one CSV row per slab, a count check; 79.4 min per load in the simulator. **But** until the learned face-down check is active, every slab without a back-label code stops the run (§5 step 3), and the build guide says not to leave it alone before three clean full runs [Guessing threshold]. |
| PSA first, CGC too | README; CONTRACT | The rules read and stack both. BGS and TAG go to pocket 12 (only if ≤ 82.6 mm wide). SGC (about 86 mm) does not fit the 84 mm pocket. |
| Fewest moving parts | DESIGN §2 | One row, no Y axis: 2 motors, a spring-loaded cup, 2 valves, 1 pump. |
| Budget about \$2,000; \$2,500–3,000 acceptable | CONTRACT | \$2,181.94 with a 15% allowance [Likely ±10%]; worst case about \$2,380 [Guessing] (BOM.md). |
| Built with school-shop tools | CONTRACT; BUILD_GUIDE | Extrusions bought cut (Misumi, ±0.5 mm); printed parts; rod holes drilled through a printed template that the machine positions (BUILD_GUIDE §5B). 65–90 h of hands-on work [Guessing]. |

Design rules: the cup touches only a slab's back and no slab slides on another (DESIGN §2–3); a
wrong cert is worse than none, so the software never guesses (OPERATING).

## 3. Status and evidence

The next step is two bench gates that decide whether it gets built:

- **Phase 0A, camera test** (≈ \$470, ≈ \$281 with a borrowed Pi). Both cameras on a jig that holds
  the machine's head parts where the machine does, on 30–50 of the owner's slabs.
  GO: ≥ 95% read, 0 wrong certs, 0 false face-down proofs (BUILD_GUIDE §1.9).
- **Phase 0B, cup test** (≈ \$155). The real SMC cup on a hand vacuum pump: seal, leak, and a 24 h
  marking test. GO: no mark that survives a dry microfiber wipe (BUILD_GUIDE §1.10).

| Evidence | What it shows | What it does not show |
|---|---|---|
| **CAD checks** `cad/checks.py`: **177/177 pass** [Certain], 23 Oct 2026; numbers in `cad/out/checks.txt` | Clearance and interference of the model at every pick, place, travel, station, hard-stop and Phase 0 pose (last-slab pick 14.55 from full neighbours, loaded travel 21.4 over the rods, a double pick of two 11.5 holders 5.33); sight lines; switch and sensor trips. | Loads, deflection, belt slack, cables and tube, real shapes of bought parts, switch-lever side load, frame brackets (not in the CAD), print accuracy. |
| **Software tests**: **299 passed, 1 skipped** (23 Oct 2026; the skip is the real-image test, which passes alone) [Certain] | Parsing of real PSA and CGC payload strings, grader and face-down rules, carry-sensor logic, the stop paths with a slab in the cup. | Real cameras, GPIO electrics, serial timing. The bench-test tool has run only on the simulator. |
| **Simulator**: 330 slabs, seed 7, default mix [Certain, sim]; raises `Crash` on any unsafe move | `ok` 324, `needs_review` 6, no wrong cert or grader in an `ok`. Face-down: 287 by back QR, 41 learned, 2 confirmed. Double pick, seal failure, overfill, Z stall and sensor faults end without a simulated crash. | Real physics (air films, slip, leaks, stalls). The mix is [Guessing]. Every simulated slab is face-down. |
| **Real labels**: `tools/real_eval.py` on public scans of 64 real slabs [Certain for these images]; a decode sweep on synthetic labels | **0 wrong certs in an `ok`, 0 false face-down proofs.** Native: 60 `ok`, 2 `needs_review`, 2 `no_read` (BGS and SGC carry no code); at machine-camera scale 60 of 61 `ok`. Back QR reads at ≤ 0.14 mm/px through blur and glare. | The rules were written from these 64 slabs. Flat scans have no slab-plastic reflections. |
| **Hardware** | Nothing. | Everything physical. |

## 4. The machine at a glance

| Parameter | Value | Source |
|---|---|---|
| Overall size | **1436 × 289.5 × 720** (X × Y × Z): X −78 … 1358 over the feet, Y −117.5 … 172 (the bed), Z −49 (feet underside) … 671 (Z motor top); the same in every pose [Certain, CAD bounding box of the assembly STEP] | `cad/out/assembly/*.step`; D-01 |
| Frame | Bed 1416 × 289.5 (18 mm plywood) on two 2040 × 1416 base rails; one portal: two 4040 × 401 uprights on the back base rail and a 4040 × 1416 X beam, centre 400 above the pad; 2040 × 340 Z spine; 2020 × 285 drop arm; joints not in the CAD | `cut_list.csv`, `layout.py`, BUILD_GUIDE §4 |
| Pockets, slab | 92 pitch, centres X = 42 + 92·cell; inside 84 × 139: ±1.85 / ±1.75 play on an 80.3 × 135.5 × 6.6 slab (design max 82.6 × 136.5 × 7.0, ≤ 65 g; thick holders 11.5); 82 dowels (5/16 in). | `layout.py`, `dims.py` |
| Heights | MAX fill line 210, overfill laser 214, rod tops 218; travel c = 248 (empty and loaded); station read c ≈ 171.6 | `layout.py`, `machine.toml` |
| X axis | NEMA17, GT2 20T belt, 80 steps/mm; one MGN12H block on a 1300 rail; soft limits 22…1253, printed hard stops at cup X 15 and 1262; 15000 mm/min, 2000 mm/s²; 1.0 A | CONTRACT, FIRMWARE |
| Z axis | NEMA17 (1.5–2.0 A, ≤ 4 mH), integrated T8×8 screw cut to 340; one MGN12H block on a 330 rail; c = −12…250 used, hard stops c = −14 and 262; 6000 mm/min, 1200 mm/s²; run 0.8 A, hold 0.5 A | CONTRACT, FIRMWARE |
| Drivers | TMC2160, 1/16 microstepping, spreadCycle, no StallGuard, never switched off; `must_home: true`. `r_sense_ohms` ships at 0.022 until the board's resistors are read: the wrong value gives 3.4 × or 0.29 × the set current. | FIRMWARE "Read this first", "What config.yaml sets" |
| Cup, vacuum | SMC `ZPT25UUK20-B5-A10`: Ø25 urethane cup, M10 spring buffer, 20 mm stroke; probe trips at 2.0 ± 0.5 of travel (about 1.2 N [Likely]). 19.1 N at −50 kPa, SF 30 on a 0.64 N slab; 13.4 N, SF 21 at the −35 kPa seal level (reached within 0.4 s) [Certain, arithmetic; the 78% effective area is an estimate]. Pump, reservoir, valves: BUILD_GUIDE §8.1. | DESIGN §4, `config.py`, BUILD_GUIDE §8.1 |
| Sensors | Fail-safe optical contact probe (Rodent input); carry-height sensor (Pi GPIO 6, blocked from c = 246.5 up); vacuum sensor; overfill laser gate (GPIO 5); X home and Z top NC microswitches; optional lid switch (GPIO 25) | CONTRACT, WIRING §5–8 |
| Cameras | Head: ELP 8 MP USB, 3.6 mm lens, 140 above the held slab, 5 toward the label from the cup axis, 0.055 mm/px. Station: Pi Camera Module 3, 140 below, 0.039 mm/px. The LED rings' mirror image misses the label band, so no polarisers [Certain, mirror geometry; real glare untested until Phase 0A]. | CONTRACT, DESIGN §5 |
| Control, power | BTT Rodent (FluidNC v4.1.1+) over USB to a Raspberry Pi 5 4 GB, which switches the pump, valves and rings. LRS-150-24 at 24.5 V behind a fused IEC inlet; E-stop in the +24 V line; fuses 5 / 3 / 1 A; Pi on its own supply. | CONTRACT, WIRING §1, `img/wiring.svg` |
| Cycle, cost, prints | 14.2 s per slab, 79.4 min for 330 [Certain, sim; Guessing until measured]. Parts \$1,897.34, **\$2,181.94 with 15%** [Likely ±10%]. 25 printed parts (27 prints, 801 cm³, PETG, ≈ 44.5 h). | DESIGN §6, BOM.md, `print_list.json` |

## 5. One slab's trip

Once per run: home (Z up, then X left), refuse to start if the overfill beam is blocked, survey
every pocket with the probe (repeated and compared on resume), and in learned mode take one head
frame over an empty pocket to check the camera's aim. Then for every slab (`runner.transfer`):

| # | Step | Guarded by |
|---|---|---|
| 1 | Move over the source pocket at c = 248. | **Carry-height sensor** must read blocked before any sideways move. |
| 2 | Drop to just above the predicted stack top (`G38.3`). | **Contact probe** stops any downward move on contact. |
| 3 | One head frame: face-down check, first read of the back. | **Head camera.** Not proven face-down: stop untouched. Front code seen: FACE-UP stop. |
| 4 | Probe to the real top, at most 12 past the prediction. | Fail-safe probe (a cut wire reads as touching). > 4.5 taller than predicted stops the run. |
| 5 | Grip: seal at −35 kPa within 0.4 s, one retry. | **Carry-height sensor** must read clear; **vacuum sensor**. |
| 6 | Peel at 2 mm/s through release, 0.5 s low over the stack; lift to c = 248; two head frames. | **Probe hard limit**; a Z stall over about 2.5 stops before any sideways move; vacuum alarm above −25 kPa. |
| 7 | If needed, front frames over the station (c ≈ 171.6); decode and OCR over the output stack. | **Station camera**; rules in `slabscan/certs.py`. |
| 8 | Probed set-down (1200 mm/min through the rod tops) on the output pocket or pocket 12. | Step ≥ 11.6: DOUBLE PICK; far too big: obstruction; under half a slab: cup empty. |
| 9 | Vent 0.25 s; back within 0.5 kPa of atmosphere within 1.5 s; write CSV row, photos, journal. | Failed vent: nothing moves. Count check at the end. |

## 6. Safety and failure handling

No safety standard, safety category or performance level is claimed in any doc, and no risk
assessment exists. What the docs have:

| Hazard | What the design does | Gap | Source |
|---|---|---|---|
| **Mains** (120 V) | Fused IEC inlet (T3.15A [Likely]) and rocker in a closed ABS box; 115/230 selector set first; PE to the frame; pre-power checks (PE < 0.5 Ω); instructor check. | Fuse not checked against the LRS inrush. Anodised joints may not carry the earth [Likely]. | WIRING §1.1, §12, §14 |
| **E-stop** | Two latching NC blocks in series in the +24 V line: cuts the Rodent, pump, valves and LED buck, not the Pi, sensors or laser. Motors go limp; Z holds on detent [Likely]. | Blocks rated DC-13 1.5 A at 24 V [Certain, BOM.csv]; WIRING §1.3 asks ≥ 5 A at 24 V DC; peak load ≈ 3.4 A [Guessing], capacitive. A weld shows only in the monthly check. **On release the pump and vacuum valve restart by themselves** (the Pi still drives them); motion needs `$H` first. | WIRING §1.3; OPERATING §8.1; BUILD_GUIDE §13.4 |
| **Pinch points** | Downward moves are probing moves: contact that lifts the cup should stop the head (about 1.2 N at the trip, 1.6 N after a full-speed trip [Likely; never tested against a hand]). A "hands clear?" prompt on resume. | **No guard, enclosure or pinch analysis.** Not sensed: other head parts, the X axis, the open belt and pulleys at the beam ends, the X carriage at its bumpers, the Z carriage at its stops, the drag chain. | BUILD_GUIDE §14; DESIGN §3 |
| **Remote start** | Start, Stop and Vent on the web page; Ctrl-C twice halts the motors but leaves them powered. | **The web page has no login and can start a run from a phone** [Certain, `web.py`]. The lid switch is a software check between slabs, not a power interlock [Certain, `runner._check_pause`]. | OPERATING §3 |
| **Laser** | ≤ 1 mW Class 2 650 nm, 4 above the MAX line; the KY-008 (usually 5 mW, Class 3R [Likely]) excluded by name; labels. | On whenever the Pi is on, E-stop included, at about face height for someone bent over the stacks. | WIRING §8 |
| **Held slab, power cut** | Both valves normally closed: the cup line stays sealed; the reservoir is on the pump side and does not help. | Hold time is the line's leak; ≥ 60 s is a [Guessing] target. | DESIGN §3; BUILD_GUIDE §13.4 |
| **Heat** | Motors kept under about 50 °C. | No PETG temperature limit or check. | FIRMWARE step 6 |

| Failure | Detected by | What happens | Designed / tested (bare § = BUILD_GUIDE) |
|---|---|---|---|
| **Vacuum loss** | Vacuum sensor | Carries the slab back slowly and probes it down. A slab is in the air about 2 s per cycle; a fall from carry height: ≤ about 240 mm, ≈ 0.15 J [Certain, arithmetic]; a corner on a dowel could chip [Guessing]. | DESIGN §3 / simulator; BUILD_GUIDE §13.3, §13.4 |
| **Double pick** | Placement step ≥ 11.6 | `needs_review` "DOUBLE PICK" plus an "UNREAD" row; two 11.5 holders clear the rods by 5.33 [Certain, CAD]. | DESIGN §2a / simulator; §13.5 |
| **Z stall** | Carry sensor clear at travel height | Stops before any sideways move; a held slab is lowered onto its own pocket, or held. Does not prevent a stall. | WIRING §6a / simulator; §7.8 |
| **Misread, face-up** | Consensus rules; hover frame | Doubtful reads go to pocket 12; a slab not proven face-down is not touched. | DESIGN §5 / unit tests, real labels; §13.1, §13.8 |
| **Sensor fault, error** | Fail-safe probe wiring; the run's guard | FluidNC refuses to probe (`ALARM:4`); the slab is put back, or the pump holds it. | WIRING §6 / simulator; §13.6 |

## 7. What a reviewer will look for, and where it is

| Item | Where | State |
|---|---|---|
| System block diagram | Electrical and control: `docs/img/wiring.svg`, WIRING §1. Vacuum: BUILD_GUIDE §8.1. Software: CONTRACT. Sequence: §5. | No single system diagram. |
| Moving-mass breakdown | DESIGN §4: CAD roll-up, 0.40 kg head and 1.62 kg X carriage, centre of mass 77 in front of the beam centre; the calculations use 0.75 / 1.9 kg | Heaviest items only, several masses [Guessing]; no full per-part list. |
| Motor and driver settings | FIRMWARE "What config.yaml sets"; `config.yaml` | Complete on paper; no torque curve for the BOM Z motor. |
| Power budget | WIRING §1.2 | [Guessing] until parts are measured. |
| Failure modes | §6; DESIGN §3, §7; OPERATING §8.1 (every stop message) | No FMEA with severity or occurrence. |
| Acceptance criteria | BUILD_GUIDE §1.9, §1.10, §6.7, §7.8, §13.9 | Some limits are judgments [Guessing]. |
| Mains, fusing, E-stop | WIRING §1, §12, §14; OPERATING §8.1 | See §6. |
| Guarding, pinch points | Nowhere | **Missing.** |
| Laser class, eye safety | WIRING §8 | Class 2, labelled, no beam stop. |
| Structural loads | DESIGN §4 (beam sag, twist); BUILD_GUIDE §4.3 (joint plan) | **Missing:** joints, rail moments, drop arm, spine, PETG parts. |
| Tolerances; cables and tube | D-00 note 6, BUILD_GUIDE §4.1, §4.5; WIRING §11 | Several PROPOSED, no stack-up; cables and tube not in the CAD. |

## 8. Key assumptions

| Input | Value used | Tag, source | Feeds |
|---|---|---|---|
| Slab mass | ≤ 65 g (0.64 N) | `dims.py` | Cup SF, drop |
| Cup area, lip friction | 78% of Ø25 effective; friction coefficient about 0.5 | an estimate; a guess (DESIGN §4) | Hold 19.1 / 13.4 / 9.6 N; lateral SF |
| Buffer spring | SMC: 1.0 N at rest, 3.0 N at full stroke → about 1.2 / 2.4 / 3.0 N at 2 / 14 / 20 mm | [Likely], DESIGN §4 | Trip, contact force |
| Moving masses | 0.75 / 1.9 kg assumed (head / X carriage); CAD roll-up 0.40 / 1.62 kg, about 0.53 / 1.94 kg with allowances and a slab | DESIGN §4; allowances [Guessing] | Torque, twist |
| Screw, rotor | T8×8 at 40% efficiency (50–65% [Likely]); 2 N X friction; 60–80 g·cm² rotor | DESIGN §4; rotor [Guessing] | Torque |
| Motor torque | Z ≈ 0.15–0.2 N·m at 750 rpm at full current; X ≈ 0.15–0.3 N·m at 375 rpm at the 1.0 A run current | [Likely], DESIGN §4; no curve read | SF ≈ 2–4 (Z), ≈ 4–8 (X) |
| Detent, back-drive | ≈ 0.015 vs ≈ 0.005 N·m | [Likely], DESIGN §4 | Z hold unpowered |
| Beam torsion | J 1.0–2.5 cm⁴, G 26 GPa, both ends fixed | [Guessing on J], DESIGN §4 | ≈ 0.5 mm twist |
| Belt tension | 15–25 N | [Guessing], BUILD_GUIDE §6.6 | PETG loads |
| Load current | ≈ 1.2 A typical, ≈ 3.4 A peak | [Guessing], WIRING §1.2 | Fuses, E-stop |
| Bought parts | Catalog or listing envelopes; head camera 32 mm hole pattern and 20 mm board-to-lens | [Guessing] for the camera, BUILD_GUIDE | Clearances |
| Printed holes | 0.1–0.3 small | [Likely], DESIGN §7 | Fits |
| Label mix, card-window limit | The simulator's default mix; 2% on the holder | [Guessing]; a judgment (DESIGN §6, §7) | Sim results, face-down check |

## 9. What we'd like you to review

A short answer with the question number is enough. Label and face-down risks are left to Phase 0
(DESIGN §7 has the full risk table).

1. **Frame joints.** The CAD has no brackets. BUILD_GUIDE §4.3 proposes [Guessing on the layout] two
   4040 L brackets in each beam-to-upright corner, a back plate (none in front: the X rail ends
   18 mm from each upright), and uprights held by L brackets bolted M5×30 through the 18 mm plywood
   into the back base rail. These joints react the head's overhang, and the twist estimate (Q2)
   assumes they fix the beam ends in torsion; nothing calculates their stiffness. Enough, or
   end-tap and bolt the uprights? (D-01, D-02)
2. **Beam twist.** ≈ 0.5 mm in Y at the cup at midspan (0.3–0.8 for J 2.5–1.0 cm⁴) [Guessing on
   J]: θ = T·L/(4GJ), ends fixed, T 1.46 N·m from the CAD centre of mass, G 26 GPa; brackets and
   rail-block play not included (DESIGN §4). The build check hangs 0.75 kg on the cup over pocket 6
   (0.93 N·m [arithmetic: 0.75 kg × g × 127 mm], about 64% of the carriage's own 1.46 N·m), so its
   reading is not directly the estimate; a rear brace goes on above 1.0 mm (BUILD_GUIDE §6.7). Twist
   also tilts the head camera in the plane of the aim limits (Q11) and varies along X, while the aim
   check looks over one pocket (an inference; no doc relates them). Credible? Measure angle? (D-04)
3. **Rail loads.** Each axis runs on one MGN12H block (generic rails; the X listing states no
   preload). The X block carries the 1.62 kg carriage (CAD; about 1.94 kg with hardware and a slab),
   centre of mass 77 in front of the beam centre, Z motor top at Z 671. No moment-load, deflection
   or life check exists. One block enough? (D-04, D-05)
4. **Z torque at 0.8 A.** 0.026 N·m on the T8×8 for 0.75 kg at 1.2 m/s² without rotor inertia;
   with the CAD's 0.53 kg plus inertia, 0.025–0.027 N·m (DESIGN §4). At 0.8 A (40–55% of rating)
   SF ≈ 2–4 [Likely]; no torque curve. The test passes if a
   bare-pad probe agrees within 0.1 mm after 100 full-speed lifts; the fixes are 3000 mm/min, then
   about 60% of rated current (BUILD_GUIDE §7.8). More margin from the start? Is 100 lifts enough
   for a 330-slab run? (D-05)
5. **Z hold, power off.** Back-drive about 0.005 N·m (0.003–0.005 with the CAD mass) against about
   0.015 N·m detent [Likely]. The
   test hangs 200 g on the cup, presses the E-stop and watches 1 minute; any creep means a brake or
   counterweight, whose mount is not in the CAD (BUILD_GUIDE §7.8). Design it in now? (D-05)
6. **Switch side load.** Each home switch is worked by a striker sliding across its hinge lever (a
   45° lead-in, then a flat holding it 0.6 mm past the click, inside the 1.2 mm overtravel). The
   lead-in pushes the lever sideways about as hard as down; the datasheet rates only a straight
   push [Guessing that it holds]. Acceptable, or a roller on a cam? (BUILD_GUIDE §6.8; D-09, D-11)
7. **PETG parts.** The load-bearing parts (5–6 walls, 40–50% infill) carry the Z motor, the head
   and the belt (15–25 N [Guessing]) beside motors allowed about 50 °C. No doc gives a PETG
   temperature limit; nothing checks creep or stiffness. Which would you change? (D-08
   `x_motor_mount`, D-09 `x_bracket`, D-10 `z_plate`, `z_motor_mount`, D-12 `head_foot`)
8. **Cup margin, marking, power-cut hold.** At the software's thresholds: 13.4 N, SF 21 at the
   −35 kPa seal; 9.6 N, SF 15 at the −25 kPa transit alarm; lateral SF 49 / 34 on a guessed
   friction coefficient of 0.5 [Certain, arithmetic; 78% area an estimate] (DESIGN §4). Marking:
   24 h on a hand pump, then 300 cycles + 24 h at mean ≤ −40 kPa (BUILD_GUIDE §1.10, §13.2). After
   a power cut the slab hangs on the closed cup line only, ≥ 60 s [Guessing target], with a
   cup-side reservoir as the fallback (BUILD_GUIDE §8.2). Is the marking plan enough for slab
   plastic, and the hold for unattended runs? (D-17)
9. **E-stop and mains.** The blocks are rated DC-13 1.5 A at 24 V [Certain, BOM.csv]; WIRING §1.3
   asks for ≥ 5 A at 24 V DC, and the bus feeds capacitive inputs at up to ≈ 3.4 A [Guessing]. A
   weld is found only monthly; the pump restarts on release. The T3.15A fuse [Likely] is not
   checked against inrush; one earth bond crosses anodised joints [Likely]. Acceptable, or the
   E-stop in the mains feed (the WIRING §1.3 alternative) or a force-guided safety relay (linked
   contacts that reveal a weld)?
10. **Sensor fail-safety.** The carry sensor's "OK to move" state is dark, so a dead emitter or cut
    GND is caught only at the next grip [Certain] (WIRING §6a). The probe flag may chatter during
    the slow peel; the fix is a Schmitt stage [Guessing] (WIRING §6). Acceptable? (D-05, D-06, D-11)
11. **Head camera aim.** The learned check needs the camera within 1.34° toward the cup [Certain,
    CAD]; on a CGC slab in a pocket corner, about 0.01° toward the label puts over 2% of the card
    window on the holder [Likely]. The only adjustment is an M2 washer shim (about 0.5° [Likely]).
    What can the `camera_bracket` / drop-arm stack-up hold, and how would you measure it? (DESIGN
    §5; D-05, D-12)
12. **Guarding and remote start.** An optional lid switch that pauses between slabs and removes no
    power; a web page with no login that can start a run. What minimum guard and interlock before
    unattended runs, and should a start need someone at the machine? (§6)
13. **Tolerances.** D-00 note 6d marks these PROPOSED (no doc states them): printed parts ±0.3,
    plywood outline ±0.5, sheet-metal outlines ±0.2, dowel cut length ±0.5. The design's own fits:
    pocket play ±1.85 / ±1.75, rod holes drilled by the machine, Misumi cuts ±0.5 mm, printed holes
    0.1–0.3 mm small [Likely]. Right, and holdable in a school shop? (D-00; D-03, D-06, D-07–D-17)
14. **Cables and tube.** Not in the CAD: the 1 m drag chain, the 350 mm Z loop, the vacuum tube
    (about 1 mm under the head ring at full stroke [Guessing]), about 4 m of head USB [Guessing].
    Any routing or flex-life problem? (WIRING §11, §16; D-05)

## 10. How to read this package

### 10.1 Start here

| Where | What it is |
|---|---|
| `package/SlabRail_Design_Review.pdf` | The review PDF. Start here. |
| `package/SlabRail_Complete_Documentation.pdf` | All the docs in one PDF. |
| `package/SlabRail_CAD.zip` | The CAD files in §10.4: exactly the list in `package/cad_manifest.txt`. |
| `web/slabrail.html` | One-page overview, as of 23 Oct 2026; where it disagrees with the docs, the docs win. |
| `web/slabrail_3d.html` | Interactive 3D model generated from the CAD: rotate, click a part to see what it is, hide groups. |
| `web/slabrail_replay.html` | Animated replay of a simulated 330-slab batch, run by the real machine software, with synthetic labels. |
| `docs/history/` | Design-round reports (rounds 2–5), the real-label evaluation and its independent check, sourcing data. **Historical: their numbers may be out of date.** |

GitHub shows HTML as source: download a `web/` file and open it in a browser (online, for the
fonts and the 3D library).

**Documents.** The README's "What's in this folder" table lists every doc. For review: DESIGN
(architecture §2, crash layers §3, calculations §4, verification §6, risks §7), CONTRACT (the
binding interface), WIRING, FIRMWARE, BUILD_GUIDE (Phase 0 §1, acceptance tests §13), OPERATING
(every stop message §8.1) and `cad/layout.py` (the master dimensions).

### 10.2 Drawing set

`cad/out/drawings/SlabRail_drawings.pdf`, 18 sheets, Rev A: a draft for design review, not
released for fabrication. Previews are in `cad/out/drawings/png/`; `dims.json` beside them lists
every dimension shown and its source, and `cad/drawings.py` re-measures each one on the model.

| Sheet | Title | Sheet | Title |
|---|---|---|---|
| D-00 | Index and general notes | D-09 | Printed parts: X carriage |
| D-01 | General arrangement | D-10 | Printed parts: Z carriage plate, Z motor mount |
| D-02 | Frame and extrusion cut list | D-11 | Printed parts: Z end cap, Z switch mount, carry-height sensor |
| D-03 | Bed, pockets and guide rods | D-12 | Printed parts: head |
| D-04 | X axis | D-13 | Printed parts: station mount, drill template |
| D-05 | Z axis and head stack-up | D-14 | Printed parts: awl adapter, fill gauge |
| D-06 | Flat parts (probe flag, carry flag) | D-15 | Printed parts: Phase 0 jig (base, tray) |
| D-07 | Printed parts: gate posts | D-16 | Printed parts: Phase 0 jig (top, occluder mount) |
| D-08 | Printed parts: X drive | D-17 | Phase 0 test jig |

### 10.3 Coordinates

`cad/README.md` and D-00 note 3: X left to right along the row (machine X is the cup axis), Y front
(−) to back (+) with Y = 0 on the row centre line, Z up with **Z = 0 at the top of the pocket floor
pads**; c is the cup-face height above it.

### 10.4 CAD files

The CAD zip holds the 64 files in `package/cad_manifest.txt`:

| File | What it is |
|---|---|
| `cad/README.md` | Units, coordinates, poses, part names, how to open and regenerate the files |
| `cad/out/assembly/slabrail_<pose>.step` (4) | Full assembly: `home` (head over pocket 1 at c = 248, stacks as loaded), `pick_bottom` (cup at c = 6.6 on the last slab of pocket 11), `carry` (held slab at c = 248 between pockets 1 and 0), `station` (held slab at c ≈ 171.6). Measure on these. |
| `cad/out/assembly/slabrail_home.glb`, `slabrail_carry.glb` | The same assemblies as binary glTF meshes for any glTF viewer (metres, Y up, as glTF expects); for looking, not measuring |
| `cad/out/printed/`: 25 STEP, 25 STL, `print_list.json` | Printed parts in print orientation, with sizes and print notes. The `station_mount`, `phase0_base` and `phase0_tray` STLs are not clean meshes: check them in the slicer preview (`cad/README.md`). |
| `cad/out/cut_list.csv`, `probe_flag_blank.dxf`, `.svg` | Stock cut lengths (extrusions, lead screw, flags, 82 dowels); the probe flag blank at 1:1 |
| `cad/out/checks.txt`, `cad/out/drawings/SlabRail_drawings.pdf`, `docs/BOM.csv` | All 177 check results; the drawing set; every bought part with price and link |

In the repo only: the CadQuery source `cad/*.py`. Bought parts are envelopes, accurate where they
meet other parts. Not in the CAD: frame brackets, cables, the vacuum tube, the electronics panel,
the optional light roof and rear brace.

## 11. Glossary

| Term | Meaning |
|---|---|
| **c, c_safe** | Cup-face height above the pad top, the machine's Z; the free cup hangs 2 below it (`CUP_HANG`). Travel height c_safe = 248: rod tops 218 + two 11.5 holders + 5 + 2. |
| **Cell, pocket, station** | 14 positions along the row: cell 7 is the station (upward camera), the rest are pockets 0–12; pocket 12 is the exception pocket. |
| **Contact probe, probe window** | Fail-safe optical sensor tripped by a flag on the spring buffer at 2.0 ± 0.5 of travel; a probing move goes at most 12 past the predicted contact. |
| **Probe hard limit** | FluidNC `probe_hard_limit`: a probe trip during a move that is not a probing move is a critical alarm. |
| **Carry sensor** | Carry-height sensor on the Z spine, blocked from c = 246.5 up. |
| **Double pick** | Two slabs lifted together, found by a placement step ≥ 11.6. |
| **Back-label code** | A code printed only on the back label (PSA back QR, graded CGC QR, CGC 2020–23 back barcode). |
| **Face-down check, learned** | Before the cup touches a slab, a head frame must prove it face-down: a back-label code, or (learned mode) its card window, a 55 × 5.5 mm strip of card back, matching references from two proven slabs. Active after a Phase 0 GO (threshold ≥ 0.55), 5 references and a clear camera-aim check over an empty pocket. |
| **Statuses** | `ok` (cert and grader confirmed), `needs_review` (a read the rules can't confirm), `conflict` (codes disagree), `no_read`, `other_grader` (a BGS, SGC or TAG cert URL). |
| **QR, Code128, ITF** | A 2D code and two 1D barcodes; ITF (interleaved 2 of 5) is on PSA labels. |
| **J** | The torsion constant of the beam section, used for the twist estimate. |
| **Rodent, TMC2160, FluidNC** | BTT controller board; its stepper drivers (StallGuard is sensorless stall detection, off here); the CNC firmware on it, driven by G-code over USB. |
| **G38.3, `ALARM:4`** | A probing move that stops on contact and does not alarm on a miss; FluidNC's alarm when the probe already reads tripped at the start (a cut fail-safe wire). |
| **DC-13** | IEC category for DC contacts switching electromagnets (the E-stop blocks' rating). |
