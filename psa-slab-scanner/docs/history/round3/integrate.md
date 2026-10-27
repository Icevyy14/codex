The CAD head is integrated and the carry-height sensor is wired in, but the sensor does not fully protect a held slab. [Certain, arithmetic plus a sim test] It trips at a single height, c = 235. A stall that leaves a loaded head anywhere between 235 and 248 still reads "blocked", so the slab moves sideways. A single slab of any thickness still clears the rods at 235 (by 3.5 mm or more). A double pick of two thick holders would not: 235 − 2 − 23 = 210, below the 218 mm rod tops. Software cannot close this. It needs a second flag edge, or a trip height near C_SAFE_LOADED, on the CAD side.

Nothing here has touched hardware. `PiCarry` is untested on a real Pi.

## Test totals (verbatim)
- **Final full suite**, after every edit: `252 passed, 1 skipped in 746.48s (0:12:26)`. The previous total was 240 passed; I added 12 tests.
- **An earlier full run**, before the last runner change: `252 passed, 1 skipped in 817.02s (0:13:37)`.
- `python3 -m tools.gen_config --check` → `up to date`.
- pyflakes is clean on every file I touched.

## 1. Sim and config synced with the new CAD
- **`sim.HEADS["cad"]`** now holds the 21 boxes from `heads_cad.json` exactly; a test compares them with `cad/out/heads_cad.json`.
- **Old head kept** as `cad_r2`, with its lens on the cup axis.
- **Lens offset:** `HEAD_CAM_DY = -5`. `head_shadow` now projects from the lens and returns camera-axis coordinates. Parts that reach the lens plane, like the drop arm at z 140, are cut 1 mm below it.
- **`HEAD_VIEW_MM`** is now in camera-axis coordinates, (−45.15, −64.75, 45.15, −7.0). That is the same slab area as before, with the slab drawn 5 mm toward +y.
- **Card top:** each slab now gets its own value between 34.8 and 37.8 mm (median 36.1, the CAD's measurement). It was a fixed 32.
- **Window clearance:** checked with an exact rectangle test against the CAD window. Nothing is in it; the nearest box is 1.13 mm away at hover and 1.17 mm held.
- **`config.from_layout()`:**
  - The window now comes from `L.face_down_window_cam()`, giving `[[-27.5, -22.5, 27.5, -11.0]]`. The dataclass default is the same.
  - New keys `buffer_stroke = L.BUFFER_STROKE` (20) and `carry_sensor_c0 = L.CARRY_SENSOR_C0` (235).
  - New `check_heights()`: the probe window must be smaller than the stroke, and c0 + 1 must not exceed either travel height.
- **simworld** uses `cfg.buffer_stroke`; the old 25 mm constant is gone.
- **`config/machine.toml`** is regenerated. It adds `buffer_stroke`, `carry_sensor = true` and `carry_sensor_c0 = 235.0`, and has the new window.

## 2. Carry-height sensor
- **Pin:** GPIO 6 (pin 31), HIGH = blocked. [Certain, grep] Nothing else in the repo uses GPIO 6.
  - `hw.PiCarry` uses gpiozero with `pull_up=False` and takes the majority of 3 reads 1 ms apart.
  - There is a new `carry` hardware part. run, resume, focus, the web page, `bench_tests` and the focus/pick tool all pass it to the runner.
- **Config:** `carry_sensor: bool = True` and `carry_sensor_c0`. The sensor may read either way within 1.0 mm of c0 (`CARRY_BAND_MM`).
- **When the runner checks it:**
  - Before every sideways move, after the lift to travel height. Moves to the spot the head is already at are skipped.
  - Before every Z move, descent leg and probe move while a slab is in the cup.
  - Before every grip (`transfer` and `pick_top`). The cup is low there, so the sensor must read clear; that rule catches a dead emitter.
  - At a pause just above the trip height (c0 + 1.25) on every descent with a slab held. This catches a loss too small to take the loaded head below the trip, before the slab goes down. It costs 0.1 s per slab.
- **Stop messages (`CarryStop`):**
  - "Z stall suspected …" when it reads clear at travel height. Right after homing, the message blames the sensor lead instead.
  - "Carry-height sensor fault …" when it reads blocked far below the trip height.
- **What happens to a held slab after a stall:**
  - Over its own pocket: one probe move straight down from where the head is, then vent. The probe stops on contact whatever the real height is.
  - Anywhere else: `freeze="hold"`. The pump keeps holding it and the operator vents it with the existing hand-off.
  - A "stuck" fault uses the normal put-back rules. Homing clears the fault.
- **Selftest:**
  - Without `--motion` it reports what the sensor reads.
  - With `--motion` it checks for "blocked" at the top. Then, over pocket 0, it steps down from c0 + 3 to c0 − 3 in 0.25 mm probe moves and reports where the sensor trips. It fails if the sensor reads wrong outside the ±1 mm band.
- **Sim:**
  - `SimCarry(world, stuck=None|"blocked"|"clear", trip=None)` is blocked whenever the real head is at or above c0, and logs every read.
  - `SimWorld.z_lost_steps` / `z_lost_steps_at` injects lost steps on the Nth lift of more than 20 mm with a slab held. `SimMotion.z_slip` keeps the controller reporting the commanded height; homing clears it.
- **New `tests/test_carry_sensor.py` (11 tests):**
  - A 40 mm loss crashes the sim without the sensor. With it, the run stops before the sideways move, the slab goes back on its stack, and a resume completes.
  - A stall at the read station keeps the slab held.
  - A 10 mm loss is caught at the descent pause. Before I added the pause it recorded a fake DOUBLE PICK and an UNREAD row.
  - A sensor stuck blocked stops the run before the first grip; a cut lead stops it before the first sideways move.
  - A wrapper motion checks that the sensor is read before every sideways move and every move with a slab held.
  - Selftest PASS, and FAIL with the mount 3 mm off.
  - Config validation, and the CAD-export sync test.
- **Existing tests now run with the sensor:** I added `SimCarry` to the runner helpers in `test_safety_fixes`, `test_resume`, `test_runner_sim` and `test_face_down_learned`.

## 3. Runs
330-slab sim, default mix, seed 7, `--face-down-check`, final code:

| head | result | face-down proofs | s/slab |
|---|---|---|---|
| `cad` (new) | `needs_review 6, ok 324` | 226 PSA QR, 61 CGC QR (49 2023+, 12 OG), 41 learned (31 PSA, 5 CGC Authentic, 5 BGS), 2 operator | 14.0 (78.2 min) |
| `cad_r2` (old) | `needs_review 6, ok 324` | 287 QR, 43 operator, 0 learned | 14.0 (78.2 min) |

- New head: `face-down check (learned): 2 of 330 slabs stopped for you`, and the lowest learned score was 0.84. The 2 stops are the first two slabs, which came before 5 references existed.
- Old head: `43 of 330`. Every confirmation was refused as a reference with "card window looks like the empty-pocket view (the head hides it)".

`real_eval --machine` on the real slab images (this run also places the head frames 5 mm off the camera axis):
- `REAL-LABEL CHECK (machine, front OCR on): 128 images (9 skipped), 61 slabs (+3 with no usable image)`
- Totals: `TOTAL 61  60/0/0/1/0`
- `WRONG CERT in an 'ok' verdict: 0`
- `FALSE FACE-DOWN proofs (a face-up slab 'proven' face-down): 0`
- Face-down: 48 backs proven down, 19 fronts proven up (17 before). The one slab not `ok` is BGS `no_read`.

Phase 0 sim, `--sim 30 --face-up 15`, new head: lowest back-to-back 0.82, highest face-up 0.46, GO, recommended threshold 0.64.

## Remaining issues
1. **Partial stall at loaded travel** (see the top). [Certain]
2. **Face-up margin is smaller.** [Certain, sim] The highest face-up similarity went from 0.24 to 0.46. Most of that comes from the new, smaller window sitting closer to the card top: the open head with a fixed card top gives 0.39, with the spread 0.43, and the new CAD head 0.46. The simulator's threshold of 0.6 still separates them, but the margin is synthetic.
3. **The 41 learned acceptances prove nothing about face-up safety.** [Certain] Every slab in the sim is face-down; only the unit tests and the Phase 0 sim test face-up slabs.
4. **Operator tools don't read the sensor.** [Certain] Jog, calibrate and mark move sideways at their own risk.
5. **Bug fixed along the way.** [Certain] The sim seeded the station-camera images with `hash()`, which changes with every process, so runs were not repeatable. That is why one BGS slab came out `no_read` on one run and OCR-only on another. It now uses a stable seed.
6. **Sim simplification.** [Likely] Held frames still use the hover-distance shadow (142 vs 147 mm), as before.
7. **Docs (docs agent):**
   - WIRING: the sensor goes to GPIO 6, pin 31.
   - OPERATING: the two new stop messages and the hold behaviour after a stall.
   - BUILD_GUIDE 7.4a: `selftest --motion` reports the trip height.
   - DESIGN: the new totals and timing.
   - I updated `software/README.md` myself.

Changed files are all under `software/`: `slabscan/{sim,simworld,config,runner,hw,factory,ops,cli}.py`, `tools/{real_eval,phase0,bench_tests}.py`, `config/machine.toml`, `README.md`, the four test helpers, `tests/test_face_down_learned.py`, and the new `tests/test_carry_sensor.py`.

Logs are in `scratch/r3int/`:
- suite_final2.txt
- sim330_cad_3.txt
- sim330_cad_r2_3.txt
- machine_r3.txt
- p0_cad/phase0_report.txt

No git commands that change state were run.