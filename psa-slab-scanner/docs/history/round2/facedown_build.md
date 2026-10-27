The task assumes the head camera can see the card window through the slab. With today's CAD head it can't, so on this machine the learned check stops at the same 49 of 330 slabs as before. I built it anyway, it is tested and safe by default, and it detects the blocked view and refuses rather than guessing. It needs a CAD change to the head before it helps.

## The blocking finding
- **[Certain]** I cast rays through `cad/model.py head_parts()` (read-only) from the lens at the hover height (cup face 7 mm above the slab) to the card-window rectangle on the slab: 0 of 75 points are visible, and every one is blocked by `head_foot`. That part is the foot body at X ±15, Y -15..45, 62-75 mm above the cup face, unchanged in the CAD agent's uncommitted working copy. On the label side its shadow starts at about Y -33.5 mm.
- **[Guessing]** The card top sits about 32 mm from the slab's label-end edge, so the head camera sees at most ~2 mm of card.
- **[Certain, sim]** When the foot is in the window, every frame looks the same: face-up slabs scored 0.90-0.99, the same as the backs. A plain threshold would let face-up slabs through. A guard that compares each window with the view over an empty pocket catches this; that is what blocks every reference with the CAD head.

**CAD request (orchestrator / CAD agent):**
- Clear the line of sight from the head lens at hover (lens 147 mm above the slab) to the rectangle X ±28, Y -33..-17 mm from the cup axis (-Y is the label end).
- Today the foot's label-side edge and the M10 nut on top of it are in the way. The simulator's hypothetical "open" head clears it with a foot ≤ ±11 mm wide that reaches ≤ 6 mm toward the label side at 62-75 mm, and no nut in that cone.
- Or define `FACE_DOWN_WINDOW_MM` in `layout.py` for whatever card area the new head leaves clear: at least 300 mm², on the card, not on the label. `from_layout()` already reads it.
- Add a `checks.py` frustum check like `check_head_camera`, at the hover height.

## What I built
**New file `software/slabscan/facedown.py`:**
- `describe`, `compare`, `frame_view_mm`, `image_rects`, `draw_window`.
- `CardBackRefs`: prototypes capped at 6 × 8 newest, an `.npz` file, and a check that the window geometry still matches (otherwise old references are not used).
- `learned_ready`, `learned_match`.

**Runner (`runner.py`):**
- `_check_face_down` now returns how the slab was proven face-down: `qr` / `operator` / `learned(0.93)` / `off`.
- New methods: `_learn`, `_take_baseline` (one head frame over the first empty pocket in the survey), `face_down_status`, `_face_down_summary`. References are saved in `_guarded`'s finally.
- New Runner arguments: `refs=` and `sim_operator=` (the latter is simulator-only).

**Config keys (`config.py`, `machine.toml` regenerated):**
- `face_down_check = "learned"` (default; `"stop"` and `"off"` kept).
- `face_down_threshold` is unset; until it is set, learned mode behaves like "stop".
- `face_down_min_refs = 5`.
- `face_down_window_mm = [[-28, -33, 28, -17]]`.
- Constants in `facedown.py`: 1 px/mm, ±4 mm search, 4 mm high-pass, texture ≥ 3, window ≥ 300 mm², empty-pocket guard 0.5.

**Outputs:**
- `certs.csv` has a new last column, `face_down`.
- `report.html` has a Face-down column.
- `summary.json` has a `face_down` entry, and a summary line prints it.
- Journal events: `face_down_learned` (with scores), `face_down_confirmed` (now with the reference it created), `face_down_baseline`.
- `images/face_down_window.jpg` and `images/face_down_empty.jpg`.

**Reference rules:**
- References come only from QR-confirmed, operator-confirmed or Phase 0 slabs. `add(source="learned")` raises.
- An operator confirmation is not learned if another grader's front code is in view.
- Another grader's code seen from above still stops.

**Where the references live:** `config/card_backs.npz` next to `calibration.toml`, git-ignored. Simulator runs keep them in memory only.

**Simulator (`sim.py`, `simworld.py`, `factory.py`):**
- `head_view` shows the label end plus the top of the card window, with ±2 mm offset, ±1° yaw, ±12 % exposure and a glare spot on about 35 % of slabs.
- Card backs `pokemon_en` and `pokemon_jp` (visibly different); random front art per cert; face-up slabs are kept.
- The head's own parts are drawn in front: `HEADS` "cad" / "open" / "none", via `--sim-head`.
- `SimSlab.back`, and `--jp-rate` on its own random stream, so existing batches are unchanged. The station view is unchanged.

**Phase 0 (`tools/phase0.py`):**
- Computes a descriptor for each back image and writes `window_check.jpg`.
- `--face-up 5` adds the face-up pass.
- The report shows the lowest back-to-back score, the highest face-up score, and either GO with a midpoint threshold (needs a gap ≥ 0.10 and ≥ 10 usable backs) or HOLD ("keep `face_down_check = "stop"`").
- Always writes `OUT/card_backs.npz` as the seed. `--save` merges it into `config/` and writes `face_down_threshold`, only on GO; with `--sim` it writes to `OUT/config/` instead.

**CLI and web:**
- `sim --face-down-check` counts the stops: a simulated operator confirms each, and the run uses a simulator threshold of 0.6.
- Help and messages updated for `run --all-face-down`, `resume --face-down-ok`, the sim summary and the web checkboxes.
- `software/README.md` updated.

## The descriptor, and why
- **Region:** only the window rectangles, cropped with a 4 mm margin and box-resampled to 1 px/mm. Only the crop is resized, so a 3264 × 2448 frame costs about as much as a thumbnail. The resampling also removes noise, focus and JPEG differences and about 1° of yaw.
- **Pattern term:** saturated pixels clipped, then the image minus its own blur (σ 4 mm). That removes exposure changes, light fall-off and most of a glare spot. Normalised cross-correlation at every shift within ±4 mm handles the slab sitting off-centre in its pocket.
- **Colour term:** a hue-saturation histogram (blue back against yellow, silver or art fronts). For grey frames it uses the shape of the grey-level histogram.
- **Score:** the lower of the two. A false accept puts the cup on a front; a false reject only stops the run.
- **Speed [Certain, measured here]:** describe 1.9 ms plus 48 comparisons 2.3 ms on this container. **[Guessing]** 10-20 ms on a Pi 5.

**Simulator scores with the open head [Certain, sim]:**

| Comparison | Score |
|---|---|
| Back vs other backs | 0.87-0.98 |
| Japanese back vs English references | ≤ 0.49 |
| Face-up slab | 0.17-0.38 |

## Tests
- **Full suite: 172 passed**, 0 failed, 11 min 48 s (155 existing + 17 in `tests/test_face_down_learned.py`).
- The new file covers every case you asked for. It also covers: CGC face-down learned and face-up CGC stopping; a missing threshold keeps it inactive; the CAD head refusing; "stop" mode ignoring references; colour term; blank windows; prototype caps; config validation; `sim --face-down-check`.
- **Existing tests I changed:**
  - Three dead-camera test doubles failed on the first full run. They counted head frames, and the new survey frame shifted the count. They now fail "while a slab is held", which is what they meant.
  - `test_web` expected `"stop"` as the default.
  - The wide-camera double now reports its real view.

## Sim results (330 slabs, seed 7)

| Run | Face-down stops | s/slab | Total |
|---|---|---|---|
| Before (back QR only) | 49 would stop | 14.0 | 78.2 min |
| Required command, final code (CAD head) `scratch/round2_sim` | 49 (281 by QR, 49 confirmed by the simulated operator, 0 references collected) | 14.0 | 78.2 min |
| Hypothetical open head (scratchpad `sim330_open`) | 1 (281 QR, 48 learned, lowest score 0.88) | 14.0 | 78.2 min |

- The learned check adds no frames per slab, only one per run (991 head frames against 990).
- **Not caused by this change, but visible in the results:** the required run shows 6 needs_review, and earlier runs showed 1-2. Each of those slabs is an old front-only label that took 35-36 s, against 4-8 s for the old labels whose front OCR succeeded. That is the 30 s tesseract timeout. **[Likely]** it was CPU load from other processes. The same images OCR correctly in 0.6-17 s afterwards. This could also happen on a busy Pi.
- Phase 0 sim with the open head: GO, backs 0.88 against face-up 0.24, threshold 0.56. With the CAD head: HOLD, "face-up slabs match the backs".

## Doc changes for the docs agent
**OPERATING.md:**
- "Read this first" bullet: learned is the default. It is active only after a Phase 0 GO plus 5 references. With today's head it never becomes active, and every slab without a back QR stops as before.
- §2 Face-down and CGC rows.
- §3: the start log line "face-down check: …".
- §4 step 1: QR, or a card-window match; one extra head frame over an empty pocket during the survey.
- §5.1: new `face_down` column.
- §5.3: the face-down summary line; `report.html` Face-down column; `summary.json` `face_down`.
- §8.1: one row per new stop reason ("threshold not measured", "N of 5 references", "best match … < threshold", "looks like the view over an empty pocket: the head hides it", "nothing visible in the card window") and what to do for each.
- New §8.4 on the learned check:
  - References are learned only from QR- and operator-confirmed slabs.
  - They live in `config/card_backs.npz`; delete the file to reset, for example after a wrong `--face-down-ok`.
  - Audit learned rows with their back photos and the `face_down_learned` journal events.
- §8.3 row and §9 quick card.

**BUILD_GUIDE.md:**
- §1.2: also measure from the slab's label-end edge to the card's top edge.
- §1.7: run with `--face-up 5 --save`. Use junk slabs for the face-up pass, or hold the cup/foot assembly just above so the cup never touches a front. Check `window_check.jpg`; if the label appears at the bottom, negate the y values of `face_down_window_mm`.
- §1.8: rows for the separation numbers.
- §1.9: a learned-check HOLD does not block the build. Expect HOLD with today's head.
- §11.5: commented `face_down_threshold` / `face_down_check` lines in the calibration.toml example.
- §12.3: check `images/face_down_window.jpg` after the first run.
- §13.1: the old-label stop sentence needs updating.
- New §13.x learned-check acceptance test, for after a head change: put junk slabs face-up on top of a few stacks. They must stop untouched.
- §14 and §15: check the back photos of learned rows; update the troubleshooting row.

**DESIGN.md:**
- Row at line 68, item 7: the three modes, the safety layers (references only from proven slabs, texture floor, empty-pocket guard, measured threshold, min refs), and the CAD limit.
- Verification table: new tests and the sim numbers above.
- Limits row: older labels still stop with today's head.

**CONTRACT.md:**
- CLI list: `sim --face-down-check`, `phase0 --face-up N --save`.
- Rewrite the face-down check paragraph: modes, default, references file, journal events, CSV column, new images.

**README.md:** keep the "Older labels stop the run" warning (49 of 330). Add: the learned check exists but cannot work until the head foot is changed. With an unobstructed view the simulator shows 1 of 330 **[Certain, sim; Guessing for real backs]**. Cycle numbers are unchanged.

## Honest limits
- **[Guessing]** Real separation. Full-art fronts, holo glare, Japanese and other-game backs, sleeves and stickers are untested. Five face-up slabs in Phase 0 say little about the worst face-up case; the midpoint threshold leaves some room.
- **[Guessing]** CGC card position: the window may miss the CGC card. That is safe; those slabs just stop.
- **[Guessing]** Image orientation: label at the image top on the real camera. `window_check.jpg` shows it.
- **[Likely]** The colour term is tested only on synthetic colour images; the simulator is grey.
- **[Certain]** A wrong `--face-down-ok` becomes a reference unless a front code is in view.
- **[Certain]** On resume with no empty pocket, the empty-pocket reference saved by an earlier run is used.

I ran no git commands that change state. All edits are inside `software/` (17 files; the new ones are `facedown.py` and `tests/test_face_down_learned.py`).