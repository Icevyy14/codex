# SlabRail: design rationale and engineering checks

Confidence tags: **[Certain]** = measured, computed, or checked by the CAD/simulator here.
**[Likely]** = strong inference. **[Guessing]** = needs a real-slab test (see "Phase 0").

## 1. What it does

You load up to **330 slabs**: 11 stacks of up to 30, face-down. The machine reads every one,
unattended, and writes a CSV of cert numbers with a photo of each label.

![storyboard](img/storyboard.png)

The run works like this:

1. The cup lifts the top slab of stack 1 straight up. A camera on the head reads the back of
   the label (QR code / barcode).
2. The cup puts the slab down in the empty pocket next to it.
3. The next slab is now on top, and the cycle repeats.
4. When stack 1 is gone, stack 2 moves into pocket 1, and so on down the row.

Slabs whose back has no readable code (pre-2016 labels, damage, glare) take a detour. They are
held over an **upward camera** in the middle of the row, which reads the front label
(barcode + printed digits). Anything still unreadable, or from a grader other than PSA/CGC,
goes to the **exception pocket** at the right end.

## 2. Why this architecture

| Option | Verdict | Reason |
|---|---|---|
| Buy something | None exists | [Likely] No product feeds 200–300 graded slabs unattended. Raw-card sorters (Roca, PhyzBatch, SortSwift) exclude slabs. Sheet-fed scanners are rated "Slabs: No". See RESEARCH.md. |
| Hands-free 2D presentation scanner (~$350–650) | Best no-build option | [Likely] 20–30 slabs/min by hand, ~10 min per 250. The machine saves that time and adds a photo of every slab. |
| Gravity hopper / friction feeder | Rejected | [Certain, arithmetic] The bottom slab gets dragged out under the whole stack. A 300-slab column is about 2 m tall and 15–18 kg, so that's ~60 N of face-on-face drag across a glossy front. PSA slabs have no stacking ridges. |
| Slotted racks, lift-and-read in place (concept A) | Rejected | [Certain, panel geometry] A straight lift hits the neighbouring slab. It only works if every slab leans at 10°, which leaves 2.2 mm margins. Loading is one slot at a time. |
| Desktop robot arm (concept D) | Rejected | [Likely] Reach covers about 80–160 slabs. The arm that reaches 300 costs about twice the budget. |
| **Short stacks + top pick by vacuum, one-pocket shuffle (concept B)** | **Chosen** | Two research agents and the design panel arrived at it independently. No slab ever slides on another. The cup touches only the back. Loading is fast because you drop in handfuls. |
| B on a 2-D grid (4 motors) vs **one row (2 motors)** | **One row** | You asked for the fewest moving parts. One row removes the whole Y axis: 2 motors, 2 rails and the gantry squaring. Cost: a 1.42 m × 0.32 m footprint. The grid version is in git (`grid-variant-v1`). |

### 2a. What the independent design panel said (and what changed because of it)

Five agents each designed a different concept in depth. Three judges then scored all five,
each through one lens: slab safety, reliability/buildability, and practical value.

**Scores (1–10)**

| Concept | Safety | Buildability | Practical |
|---|---|---|---|
| A, slot racks | 6.5 | 6 | 5.5 |
| B, stacks + vacuum (the parent of this design) | 5 | 6.5 | 4.5 |
| C, shelf modules, pull and read | **8** | 4 | 4 |
| D, robot arm | 3 | 3 | 2.5 |
| E, "flip-through lanes" page-turner | 6 | **7** | **6.5** |

**Why this is still B (as SlabRail), not E.**
- [Likely] E's slab physics is unproven. Its own author says so. It needs 300 hand-loaded slabs
  in a row to peel, pass a 2.6–4.3° balance point, and settle flush, every time.
- Pick-and-place of flat, smooth parts from stacks is what every SMT and packaging line does.
  Its failure modes are known, detectable and simulated here.
- The judges scored the original B, a 4-motor grid. Their main complaints have been fixed in
  SlabRail:

| Judge's objection to B | Fix in SlabRail |
|---|---|
| Fingers can't reach slabs in tight corrals | Separate dowels, not walls. There is a 52 mm finger gap at the front and back of every pocket for lowering bundles of 5–10 when loading, and for taking slabs off the top in bundles of up to 5 when unloading. Never lift or flip a whole stack (OPERATING.md §6). |
| Printed posts can lean | Dowels sit in drilled holes, 15 mm deep, drilled through a printed vertical guide. |
| Air-film double picks | The slow leg of the peel (2 mm/s) is placed where the cup really leaves the slab: at the probe trip the spring buffer is already squeezed about 2 mm (`buffer_trip_mm`, measured in BUILD_GUIDE §7.6), so the head first rises that far at 20 mm/s while the cup stays on the slab, then 2 mm/s through the release point and 1 mm past it, then a 0.5 s dwell low over the stack, so a slab clinging by an air film falls back a few mm onto its own stack. Squeeze-film force scales with speed, so it falls about 10× to ~0.1 N, below the slab's weight. Doubles are still detected at placement. |
| Klipper probe macro fragility | FluidNC native `G38.3` with an explicit bounded target. |
| Too many moving parts | 2 motors instead of 4. No gantry squaring. |
| "Flipping and un-reversing costs more time than it saves" | Don't flip anything. Order doesn't matter, because the CSV records each slab's exact pocket and position, and unloading goes top-down in small bundles (OPERATING.md §6). Face-down loading is a hard rule: before the cup touches a slab, the head camera must see a PSA back-label QR or, in the default learned mode, a card back it learned from proven slabs (§5); otherwise the run stops untouched for you to check. Today's head foot hides the card window, so the learned part never activates [Certain, CAD ray cast]: older PSA labels and CGC stop, unless the run is started with `--all-face-down`; then a face-up slab would get the cup on its front. |

- **What we keep from the other concepts:**
  - fail-safe sensor wiring;
  - a pre-run survey (every pocket probed while you are still there);
  - the Phase 0 tests before buying motion parts;
  - a photo of every slab;
  - CSV written incrementally;
  - count reconciliation.
- **Honest residuals:**
  - Every slab is lifted and carried. A vacuum loss drops it at most about 240 mm onto foam or a
    stack.
  - Hands-on time is still ~10 min per 300 for loading and unloading.

## 3. Everything that touches a slab

| Contact | Motion | Force | Worst case |
|---|---|---|---|
| Suction cup on the **back**, centre of the card window | Static. The cup only moves vertically while touching. | Trips at ~1.2 N [Likely, SMC catalog spring force]. Vacuum clamp ~19 N over the 25 mm lip. | A faint cup ring or a grit micro-mark on the **back** (allowed). Mitigations: non-marking PU/HT1 cup, IPA wipe each run, 24 h marking test before use. |
| Slab front resting on the back of the slab below | Static. Pick = straight lift, 2 mm/s through the point where the cup leaves the slab, then 20 mm/s, with a 0.5 s pause just above the stack. Place = probed set-down at 20 mm/s (`G38.3`). | ≤ 2 N at contact. Bottom slab of a 30-stack carries 19 N (1.8 kPa, same as stacking by hand). | Lateral slip at placement if a slab lands crooked. This is the most plausible front-scuff path. [Likely] Mitigated by ±1.75 mm pocket play, rods only at the edges, and slow probed set-down. |
| Bottom slab front on the pocket pad | Static | ≤ 19 N | Grit on the pad. Wipe pads weekly. Microfiber face. |
| Slab edges on 8 mm wooden dowels | Only if the slab is off-centre by > 1.75 mm | < 1 N | Edge rub on wood. The dowels sit 12 mm from every corner, so corner tips never touch. |
| Head / camera / Z parts | None by design | — | [Certain, CAD] ≥ 5 mm at every checked pose, including a held slab at the Z top hard stop and a double pick of two thick holders; much more in normal travel (numbers in `cad/out/checks.txt`, §6). The lead screw is cut so its tip stays above anything the head carries. |

**Drops.** **[Certain, arithmetic]**
- Losing vacuum at carry height means a fall of ≤ about 240 mm, about 0.15 J, onto a stack or
  pad. That is roughly a 25 cm desk drop. A flat landing is very unlikely to crack a slab
  [Likely]. A corner landing on a dowel top could chip one [Guessing].
- Exposure: about 2 s in the air per cycle for a slab whose back reads. A slab that needs the
  station is held longer: the front frames are taken over the lens, then decoding and OCR (up to
  30 s on a Pi) happen with the slab over its planned output stack, not over the camera.
- Both solenoid valves are normally closed, so a power cut (E-stop, mains) seals the cup line.
  **The reservoir does not help then:** it is on the pump side of the closed vacuum valve. The
  slab hangs only as long as the cup line's own leak allows, seconds to minutes. [Certain, the
  plumbing in `hw.py` and BUILD_GUIDE §8.1] Acceptance test 13.4 measures it. While the Pi still
  has power (Ctrl-C twice, a USB cable out, a park that failed) the software keeps the pump holding
  a slab until you take it.

**Crash prevention, layered.**
1. **Height bookkeeping.** Every slab's thickness is measured when it is placed (the probe step).
2. **Every downward move is a probing move.** Each one is a `G38.3`, so an unexpected contact stops
   the head at once instead of driving on; probe windows never go more than 12 mm past the expected
   surface. A trip at full Z speed squeezes the 20 mm buffer about 6 mm (about 1.6 N [Likely]).
3. **Fail-safe contact sensor.** A cut wire reads as "touching", so the machine refuses to
   probe.
4. **Probe hard limit** (firmware). A contact-sensor trip during any move that is not a probe (a
   lift, a traverse) is an immediate critical alarm.
5. **Second contact sensor.** During the start-up survey, a cup that seals without the optical
   sensor tripping stops the run.
6. **Overfill laser beam.** It runs 4 mm above the fill line. If anything is too tall, the
   machine won't start. It cannot see anything above the 218 mm rod tops, such as a slab lying
   across the rods: the survey catches that, because its first probe window starts at travel
   height.
7. **Face-down check.** No PSA back QR seen from above = the cup does not touch the slab, unless
   the learned check (the default mode, §5) matches its card window with the card backs of proven
   slabs. With today's head that never happens: the foot hides the window. Another grader's code
   seen from above always stops. Modes: `learned` (default), `stop` (back QR only), `off` (or
   `run --all-face-down` for one batch).
8. **Plausibility checks.** A stack taller than predicted by > 4.5 mm, a vent that does not reach
   atmosphere, a vacuum sensor reading outside its range, or an exception pocket that's full stops
   the run. After any stop the head re-reads its real position, lifts straight up, and puts a held
   slab back; where that is unsafe, nothing moves and the pump keeps holding it.

## 4. Calculations

| Quantity | Value | Margin |
|---|---|---|
| Cup holding force, Ø25 mm at −50 kPa (78% effective area) | 19.1 N | Slab weighs 0.64 N → **SF 30** vertical [Certain] |
| Lateral grip vs X acceleration 2 m/s² | ~9.5 N vs 0.13 N | **SF 70** [Certain] |
| Z load (0.75 kg head, 1.2 m/s²) | 8.3 N → 0.026 N·m on T8×8 at 40% efficiency | A 1.5–2.0 A NEMA17 at 750 rpm on 24 V gives ≈ 0.15–0.2 N·m at full current, but Z runs at 0.8 A (40–55% of rating) → ≈ 0.06–0.1 N·m, **SF ≈ 2–4** [Likely]. No stall detection, so the 100-lift test (BUILD_GUIDE §7.8) must pass. A high-impedance 0.4–0.6 A "integrated" motor would stall: the BOM excludes it. |
| Z back-drive when unpowered | ~0.005 N·m | NEMA17 detent ≈ 0.015 N·m → holds [Likely]. Hold current is kept on anyway. |
| X drive (1.9 kg moving, 2 m/s² + 2 N friction) | 5.8 N belt → 0.037 N·m | NEMA17 at 375 rpm ≈ 0.3 N·m → **SF ≈ 8** [Likely] |
| X beam sag, 4040 over 1.42 m, 20 N at midspan | 0.18 mm | Pocket play 1.75 mm [Certain, beam formula] |
| X beam twist from the 127 mm head overhang | ≈ 0.8 mm at the cup, worst at midspan [Guessing on J] | Within pocket play. Measure it during build (BUILD_GUIDE §6). Add a rear brace if > 1 mm. |
| Spring buffer force at trip (2 mm) / end of a probe window (14 mm) / bottomed (20 mm) | about 1.2 / 2.4 / 3.0 N [Likely: SMC lists 1.0 N at rest and 3.0 N at full stroke for ø10–32 buffers] | The software never probes more than 12 mm past contact; a trip at 6000 mm/min squeezes about 6 mm. The `ZPT25UUK20-B5-A10` has 20 mm of stroke: SMC sells no 25 mm stroke on a 25 mm pad. [Certain, SMC ZP catalog Table 2] |
| Stack height, 30 PSA slabs at 6.25–6.9 mm | 188–207 mm | MAX line 210, beam at 214, rod tops 218 |
| Carry height (cup) | 248 mm | A **double pick** of two 11.5 mm thick holders still clears the rods by 5 mm, counting the free cup's 2 mm hang below its calibrated height [Certain, CAD] |

## 5. Reading the label

- **Glare geometry.** Each camera sits on the slab's centre axis with a small LED ring around
  the lens. **[Certain, mirror geometry]** The mirror reflection of a ring of radius r lands
  within r/2 of the axis, so within ~12 mm. The label band sits 45–65 mm off-axis, so it is
  glare-free without polarisers. That avoids the slab plastic's stress-birefringence
  "rainbow" risk that cross-polarisation has. [Likely] Room lights reflecting off the slab
  plastic are a minor effect. The LED ring is several times brighter on the label than a
  ceiling light's reflection, so contrast drops a little but nothing saturates. If Phase 0
  shows glare anyway, add the optional black foam-board light roof.
- **Resolution.**
  - Head camera (8 MP IMX179, 3.6 mm lens, 140 mm away): 0.055 mm/px.
  - Station (Camera Module 3): 0.039 mm/px.
- **Decode sweep on synthetic PSA-style labels** (`software/tools/decode_sweep.py`):
  - **[Certain for the synthetic labels]** The back QR + barcode reads at ≤ 0.14 mm/px through
    blur and strong glare.
  - The front ITF barcode needs ≤ 0.05–0.08 mm/px and low glare.
  - **No misreads occurred in any cell of the sweep.**
  - [Guessing] Real labels may differ, which is why Phase 0 exists.
- **Interpretation rules** (`slabscan/certs.py`, tested):
  - **Back QR → `psacard.com/cert/<n>`:** authoritative.
  - **PSA ITF holds an even digit count, so 9-digit certs may carry a leading zero or a check
    digit.** The software learns which from slabs where QR and ITF both read. Until it has
    learned this, an ITF-only read is `needs_review` unless OCR of the printed digits agrees.
  - **An ITF-only read needs a second, independent source:** the back and front barcodes
    agreeing, or OCR agreeing. Two frames of the same barcode count once. OCR that disagrees
    makes it `needs_review`. Old front-only labels therefore need Tesseract (up to 30 s per slab on
    a Pi) or end up `needs_review`.
  - **Head frames are cropped to the pocket under the cup,** because the 3.6 mm lens also sees the
    neighbours' labels. The frame taken from above the stack alone never makes an `ok`, and a cert
    already recorded in the batch becomes `conflict` (exception pocket).
  - **`psa_cert_digits`** (set from Phase 0): a PSA cert of a length Phase 0 never saw is
    `needs_review`.
  - **Codes that disagree** produce `conflict` and the slab goes to the exception pocket. The
    machine never guesses.
  - **CGC** (`cgccards.com` QR) is read and stacked like PSA. **BGS/SGC/TAG** are recognised
    and sent to the exception pocket.

### The learned face-down check

**Why.** Pre-2017 PSA labels and CGC slabs have no back QR, so the plain check stops at every one
of them (49 of 330 in the simulator's default mix). Most of them show the same card back through
the plastic, and a face-up slab shows a card front there instead.

**The descriptor** (`slabscan/facedown.py`) [Certain, code]:
- Only the card window, `face_down_window_mm` (x −28 … 28, y −33 … −17 mm from the cup axis, −y =
  the label end; 896 mm², at least 300 mm² required). Not the label, and not the head's own parts.
- Each rectangle is cropped with a 4 mm margin and box-resampled to 1 px/mm. That removes noise,
  focus and JPEG differences and about 1° of yaw, and costs about as much as a thumbnail.
- Glare (a 1 mm average at grey level 245 or more, grown by 2 mm) is masked everywhere.
- Pattern term: the window minus its own blur (σ 4 mm), so exposure and light fall-off drop out;
  normalised cross-correlation at every shift within ± 4 mm (the slab's play in its pocket).
- Colour term: a hue-saturation histogram (a grey-level histogram on grey frames).
- **Score = the lower of the two.** A false accept puts the cup on a front; a false reject only
  stops the run.
- Cost [Certain, measured on the development container]: about 2 ms to describe a full 3264 × 2448
  frame and about 2 ms to compare it with 48 references. [Guessing] 10–20 ms on a Pi 5. It adds one
  head frame per run (the empty-pocket view), none per slab.

**Safety layers** [Certain, code; tested in the simulator]:
1. **References only from proven slabs:** a back QR seen from above; your `--face-down-ok`, learned
   only after the slab is placed and vetoed by a PSA back-label QR seen from below or another
   grader's code seen from above; the Phase 0 seed. A learned acceptance never becomes one. A back
   design known only from your confirmations is used once 3 agree.
2. **`--face-down-ok` confirms one slab:** only after a face-down stop, only the top slab of that
   pocket. The web tick appears only then and is cleared after each resume.
3. **A texture floor**, and a match needs at least half the matched back design's own texture
   (a plain front with a glare spot has some texture, far less than a back).
4. **Glare:** a window with more than 2% glare never becomes a reference; more than 30% is not
   matched.
5. **The empty-pocket guard:** one head frame over an empty pocket per run. A window whose pattern
   looks like it (similarity ≥ 0.5) shows the head, not the slab: it neither matches nor teaches.
6. **The occlusion check:** on the newest 5 or more slabs proven on this machine, a pixel that
   tracks the empty-pocket view by the frame's exposure ratio moves with the camera. More than 10%
   of the window like that: the mode is not active.
7. **A measured threshold:** Phase 0 compares at least 10 usable backs with each other and with
   at least 15 face-up slabs; a back that matches none of the others is left out. GO needs a gap of
   0.10; the threshold is the midpoint, never below 0.55. It is stored with a tag of the window and
   descriptor it was measured for (`face_down_threshold_sig`) and refused without it.
8. **At least 5 references** (`face_down_min_refs`).

**Limits.**
- [Certain, CAD ray cast] **Today's head hides the whole window** (0 of 75 points visible; the
  foot blocks all of them, the flag and elbow some). Layers 5 and 6 then refuse everything, so the
  check acts like `stop`. It needs a `head_foot` change plus a `checks.py` frustum check: rays from
  the lens at hover (about 147–149 mm above the slab) to the window grown by 2 mm must clear every
  head part.
- [Certain, sim] A head edge about 1 mm inside the window is not detected and lifts face-up scores
  from 0.37 to 0.52 (2 of 300 accepted at a threshold of 0.50). Hence the 0.55 floor; the frustum
  check is the real fix.
- [Guessing] Real separation: full-art fronts, holo glare, Japanese and other-game backs, sleeves
  and stickers are untested. The colour term is tested only on synthetic colour images (the
  simulator is grey). The CGC card may sit outside the window (safe: those slabs stop). The glare
  level (245) and texture ratio (0.5) are tuned on the simulator only.

## 6. Verification done here (no real hardware)

| Check | Tool | Result |
|---|---|---|
| Geometry: exact min-distance, all-pairs interference (including modelled fastener heads), held-slab sweep, hard-stop, rail-margin and line-of-sight checks at every pick, place, travel, station, hard-stop and Phase 0 pose | `cad/checks.py` (OpenCascade) | **106/106 pass** (re-run on 22 Oct 2026; the numbers are in `cad/out/checks.txt`) [Certain]. **Not checked:** belt slack, cables and the vacuum tube, the real shapes of bought parts (the buffer and elbow are modelled from catalog dimensions), loads and deflection, and the face-down card window (no frustum check yet). |
| Probe flag, guide and sensor over the buffer's 20 mm stroke | `cad/checks.py` `check_probe` | [Certain] trip at 2.00 mm; beam clear for 1.5 mm, fully blocked from 3 to 20 mm; flag 1.05 mm from the sensor and 0.45 mm from its guide; 8 mm guide engagement at full stroke; a rotating (J) buffer stopped at 1.32°, 0.6 mm from the sensor; buffer ± 3 mm on its thread still covered by the ± 4 mm board slots; pad 1.5 mm clear of the buffer body at full stroke; nothing in the label view while reading; a ball-end key reaches the front board screw. |
| Phase 0 jig vs machine | `cad/checks.py` `check_phase0` | [Certain] the occluder (foot, buffer, flag, elbow, board) sits 0.0 mm from the machine's relative to the lens and blocks the same share of the slab view; the face-up pass (mount 3 mm up) leaves the free cup 1.0 mm above the slab's front. |
| Unit tests: cert parsing, grader detection, ITF learning, decode at the design point, OCR fallback, the learned face-down descriptor, config checks | `software/tests` | **189 passed** (full suite, 11 min 49 s, 22 Oct 2026) [Certain] |
| End-to-end batches in a simulator that **raises Crash on any unsafe move** | `software/tests/test_runner_sim.py`, `test_safety_fixes.py`, `test_bench_tests.py`, `test_face_down_learned.py` | pass [Certain]. Scenarios: every slab moved and read; pre-2016 labels via the station; check-digit ITF learned; double pick detected; thick holder; seal failure stops; overfill refused; CGC read, BGS rejected; face-down check; an unexpected error with a slab in the cup; failed vent; vacuum sensor fault; Ctrl-C hard stop. Learned check: an old label passes once QR references exist; a face-up slab still stops; a plain face-up front with glare is refused; today's CAD head and a partly hidden window are refused; one wrong confirmation does not teach a front; a back QR seen from below vetoes a confirmation; a Japanese back needs 3 confirmations; `--face-down-ok` is refused after another stop; a batch with a learned acceptance resumes; Phase 0 leaves an outlier back out. |
| Learned face-down check, 330-slab simulated batch (seed 7) | `sim --slabs 330 --face-down-check` | [Certain, sim] Today's head: 49 stops, 0 references (unchanged from back-QR only). A hypothetical head that leaves the window clear: 281 by back QR, 48 learned (lowest score 0.69), 1 stop. Both 14.0 s per slab, 78.2 min, 991 head frames. With the clear head, 300 simulated Phase 0 runs all said GO (thresholds 0.54–0.57) and no face-up slab was accepted; 0 of 150 plain fronts with glare were accepted. [Guessing for real slabs] |
| Real slabs, real cameras, real cup | — | **Not done.** Phase 0 + acceptance tests in BUILD_GUIDE are mandatory before trusting it with your inventory. |

## 7. Known risks and what retires them

| Risk | Retired by |
|---|---|
| Real PSA barcode/QR payloads differ from the assumptions | Phase 0: scan 30–50 of your slabs with the real cameras and `slabscan focus`. `custom_regex` in config handles a prefix or suffix: it is checked when the config loads (it must compile and have one capture group) and applied after the other graders' URL rules. |
| Cup leaves visible marks | Phase 0B 24 h marking test with a hand pump, then the 300-cycle + 24 h test on the machine with the vacuum re-held all the time (BUILD_GUIDE §13.2). Swap cup material if needed (BOM lists two). |
| Older labels stop the run | Each slab without a PSA back QR stops at the face-down check. The learned check could remove most of these stops (1 of 330 in the simulator with a clear view [Certain, sim; Guessing for real backs]), but today's head hides the card window, so it never activates. A `head_foot` change plus a frustum check comes first. Until then use `run --all-face-down` only for stacks you checked yourself. |
| The buffer and elbow differ from their catalog dimensions | Measure them on arrival (BUILD_GUIDE §3.3) before cutting the flag; the board slots give ± 4 mm of trip adjustment. |
| Beam twist larger than estimated | Dial-indicator check during the build. A rear diagonal brace is in the guide. |
| Double picks (slabs clinging) | Peel dwell. Detected at placement (step ≥ 11.6 mm) and flagged with the exact position. |
| Mixed weird holders (SGC 86 mm wide doesn't fit; BGS/TAG widths unmeasured; sleeves) | Loading rules in OPERATING.md. SGC is too wide for the pockets. Measure one BGS, TAG and CGC holder before loading them: anything wider than 82.6 mm is "do not load". |
