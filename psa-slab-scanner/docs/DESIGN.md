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
| Fingers can't reach slabs in tight corrals | Separate dowels, not walls. There is a 52 mm finger gap at the front and back of every pocket for lowering and lifting bundles of 5–10. |
| Printed posts can lean | Dowels sit in drilled holes, 15 mm deep, drilled through a printed vertical guide. |
| Air-film double picks | Very slow first millimetre of peel (2 mm/s) plus a dwell. Squeeze-film force scales with speed, so it falls about 10× to ~0.1 N, below the slab's weight. Doubles are still detected at placement. |
| Klipper probe macro fragility | FluidNC native `G38.3` with an explicit bounded target. |
| Too many moving parts | 2 motors instead of 4. No gantry squaring. |
| "Flipping and un-reversing costs more time than it saves" | Flip **bundles**, not single slabs. Order doesn't matter, because the CSV records each slab's exact pocket and position. A slab loaded the wrong way up is still read (both faces are imaged). It just gets cup contact on its front. |

- **What we keep from the other concepts:**
  - fail-safe sensor wiring;
  - a pre-run survey (every pocket probed while you are still there);
  - the Phase 0 tests before buying motion parts;
  - a photo of every slab;
  - CSV written incrementally;
  - count reconciliation.
- **Honest residuals:**
  - Every slab is lifted and carried. A vacuum loss drops it at most 236 mm onto foam or a stack.
  - Hands-on time is still ~10 min per 300 for loading and unloading.

## 3. Everything that touches a slab

| Contact | Motion | Force | Worst case |
|---|---|---|---|
| Suction cup on the **back**, centre of the card window | Static. The cup only moves vertically while touching. | Trips at ~1.4 N. Vacuum clamp ~19 N over the 25 mm lip. | A faint cup ring or a grit micro-mark on the **back** (allowed). Mitigations: non-marking PU/HT1 cup, IPA wipe each run, 24 h marking test before use. |
| Slab front resting on the back of the slab below | Static. Pick = straight 5 mm lift at 20 mm/s. Place = probed set-down at 20 mm/s. | ≤ 2 N at contact. Bottom slab of a 30-stack carries 19 N (1.8 kPa, same as stacking by hand). | Lateral slip at placement if a slab lands crooked. This is the most plausible front-scuff path. [Likely] Mitigated by ±1.75 mm pocket play, rods only at the edges, and slow probed set-down. |
| Bottom slab front on the pocket pad | Static | ≤ 19 N | Grit on the pad. Wipe pads weekly. Microfiber face. |
| Slab edges on 8 mm wooden dowels | Only if the slab is off-centre by > 1.75 mm | < 1 N | Edge rub on wood. The dowels sit 12 mm from every corner, so corner tips never touch. |
| Head / camera / Z parts | None by design | — | [Certain, CAD] ≥ 8 mm clearance at every checked pose (see §6). |

**Drops.** **[Certain, arithmetic]**
- Losing vacuum at carry height means a fall of ≤ 236 mm, about 0.15 J, onto a stack or pad.
  That is roughly a 25 cm desk drop. A flat landing is very unlikely to crack a slab [Likely]. A
  corner landing on a dowel top could chip one [Guessing].
- Exposure is short: a slab is in the air ~2 s per cycle.
- Both solenoid valves are normally closed. With the check valve and reservoir, a **power cut
  does not drop the slab instantly**. Acceptance test 13.4 in BUILD_GUIDE verifies this.

**Crash prevention, layered.**
1. **Height bookkeeping.** Every slab's thickness is measured when it is placed (the probe step).
2. **Bounded probing.** `G38.3` never drives the cup more than 12 mm past the expected
   surface. The spring buffer has 25 mm of stroke, so the worst-case push is ~3.4 N.
3. **Fail-safe contact sensor.** A cut wire reads as "touching", so the machine refuses to
   probe.
4. **Second contact sensor.** During the start-up survey, a cup that seals without the optical
   sensor tripping stops the run.
5. **Overfill laser beam.** It runs 4 mm above the fill line. If anything is too tall, the
   machine won't start.
6. **Plausibility checks.** A stack taller than predicted by > 4.5 mm, or an exception pocket
   that's full, stops the run with the cup empty.

## 4. Calculations

| Quantity | Value | Margin |
|---|---|---|
| Cup holding force, Ø25 mm at −50 kPa (78% effective area) | 19.1 N | Slab weighs 0.64 N → **SF 30** vertical [Certain] |
| Lateral grip vs X acceleration 2 m/s² | ~9.5 N vs 0.13 N | **SF 70** [Certain] |
| Z load (0.75 kg head, 1.2 m/s²) | 8.3 N → 0.026 N·m on T8×8 at 40% efficiency | NEMA17 at 750 rpm, 24 V gives ≈0.15–0.2 N·m → **SF ≈ 6** [Likely] |
| Z back-drive when unpowered | ~0.005 N·m | NEMA17 detent ≈ 0.015 N·m → holds [Likely]. Hold current is kept on anyway. |
| X drive (1.9 kg moving, 2 m/s² + 2 N friction) | 5.8 N belt → 0.037 N·m | NEMA17 at 375 rpm ≈ 0.3 N·m → **SF ≈ 8** [Likely] |
| X beam sag, 4040 over 1.42 m, 20 N at midspan | 0.18 mm | Pocket play 1.75 mm [Certain, beam formula] |
| X beam twist from the 127 mm head overhang | ≈ 0.8 mm at the cup, worst at midspan [Guessing on J] | Within pocket play. Measure it during build (BUILD_GUIDE §6). Add a rear brace if > 1 mm. |
| Spring buffer force at trip / at 12 mm / bottomed (25 mm) | 1.4 / 3.4 / 6.0 N | The software never asks for more than 12 mm. |
| Stack height, 30 PSA slabs at 6.25–6.9 mm | 188–207 mm | MAX line 210, beam at 214, rod tops 218 |
| Carry height (cup) | 243 mm | A **double pick** (2 × 7.5 mm CGC) still clears the rods by 10 mm [Certain] |

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
    digit.** The software learns which from slabs where QR and ITF both read. It refuses to
    trust an ITF-only read until it has learned this, or until OCR of the printed digits agrees.
  - **A lone ITF read** must be confirmed by a second agreeing frame.
  - **Codes that disagree** produce `conflict` and the slab goes to the exception pocket. The
    machine never guesses.
  - **CGC** (`cgccards.com` QR) is read and stacked like PSA. **BGS/SGC/TAG** are recognised
    and sent to the exception pocket.

## 6. Verification done here (no real hardware)

| Check | Tool | Result |
|---|---|---|
| Geometry: 36 exact min-distance / line-of-sight checks at every pick, place, travel, station and extreme pose | `cad/checks.py` (OpenCascade) | **36/36 pass** [Certain] |
| Unit tests: cert parsing, grader detection, ITF learning, decode at the design point, OCR fallback | `software/tests` | pass [Certain] |
| End-to-end batches in a simulator that **raises Crash on any unsafe move** | `software/tests/test_runner_sim.py` | pass [Certain]. Scenarios: every slab moved and read; pre-2016 labels via the station; check-digit ITF learned; double pick detected; thick holder; seal failure stops; overfill refused; CGC read, BGS rejected. |
| Real slabs, real cameras, real cup | — | **Not done.** Phase 0 + acceptance tests in BUILD_GUIDE are mandatory before trusting it with your inventory. |

## 7. Known risks and what retires them

| Risk | Retired by |
|---|---|
| Real PSA barcode/QR payloads differ from the assumptions | Phase 0: scan 30–50 of your slabs with the real cameras and `slabscan focus`. `custom_regex` in config handles a prefix or suffix. |
| Cup leaves visible marks | 300-cycle + 24 h marking test on a junk slab. Swap cup material if needed (BOM lists two). |
| Beam twist larger than estimated | Dial-indicator check during the build. A rear diagonal brace is in the guide. |
| Double picks (slabs clinging) | Peel dwell. Detected at placement (step ≥ 11.6 mm) and flagged with the exact position. |
| Mixed weird holders (SGC 86 mm wide doesn't fit; sleeves) | Loading rules in OPERATING.md. SGC is too wide for the pockets. |
