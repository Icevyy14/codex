I could not get the aim tolerance to 1.5°. My CAD change also makes 5 software tests fail until the software side is updated (proven by A/B, details below). Both are worth knowing before anything else.

**Three things you won't like**
1. **1.5° is out of reach** [Certain, exact check]. The cup pad sets the limit, not the foot. Changing the foot or the lens offset moves the limit by 0.35 mm at most. With the window edge on the CGC card, 1.5° leaves 275 mm², under the software's 300 mm² minimum. The best that fits is **1.34°** (was 0.56°).
2. **The CGC problem was worse than reported** [Likely, ±0.5 mm]. I measured 27 real CGC backs (and 22 PSA backs to check the method; the PSA median length came out at exactly 135.5).
   - CGC holders are shorter: about 133.9 mm long, so they have 2.55 mm of play, not 1.75.
   - The card top is 93.8–96.2 mm from the far (non-label) edge.
   - So the old window ran up to **3.74 mm** past a CGC card top, not 0.5–1.5 mm.
3. **The smaller window weakens the learned check, but the old one fails** [Likely: shipped `learned_match` on machine-scale frames made from the real scans].
   - Slabs placed ±2 mm off centre: the highest face-up score rises from 0.415 to 0.527 (the floor is 0.55). Face-down backs accepted drop from 113 to 103 of 126.
   - Every slab at the cup end of its play: the **old** window accepted **12 of 206 face-up slabs**, all CGC fronts. The holder strip above a CGC card looks the same from both sides. The new window accepted 0 (highest 0.492).
   - So the shrink is needed. The cost is more slabs stopping for the operator to confirm, which is the safe direction.

**Changes** (cad/ and docs/img only)
- **`layout.py`**
  - New `HOLDERS` table (per grader: length, width, card top to far edge, number of backs measured).
  - New `card_top_worst()` and `card_side_limit()`.
  - New window: `FACE_DOWN_WINDOW_MM = [[-27.5, -23.5, 27.5, -18.0]]`, 302.5 mm².
  - `check()` now tests the window for both PSA and CGC.
- **`model.py`**
  - **Head ring:** modelled as 40 OD [Likely], 30 ID and 5 mm thick [Guessing], with solder pads and lead stubs coming out of the back through a notch in the seat's lip [Guessing].
    - The LED face now sits 1 mm below the lens front. The old seat put it 4 mm below, which left only 0.75 mm to the barb elbow at the full 20 mm stroke. Now that gap is 3.75 mm.
    - The seat is rewritten (`ring_seat`, legs unchanged).
  - **Jig head ring:** `phase0_top` now has the ring sunk into a pocket on its underside (`ring_pocket`), so it sits exactly where it does on the machine relative to the lens.
  - **Station ring:** the old seat was a plain 52–60 mm tube rim with nothing to locate the ring; a 63 mm ring would only rest on it, hanging 1.5 mm over.
    - New `station_ring_seat`: a 64 mm bore on a 45° cone shelf. It takes a 63 × 47 ring (0.5 mm play) or a 60 mm ring (2.0 mm play). The leads drop through a slot into the camera ribbon's slot.
    - `station_mount` and `phase0_base` share this seat.
  - The rings and leads are now parts of the head, the station and the jig, so every all-pairs check includes them.
- **`checks.py`**
  - The window check now runs per grader.
  - The aim check now covers four card cases (median and worst, PSA and CGC). The head-part floor is raised to 1.25°.
  - New `check_led_rings` adds 21 checks:
    - each ring sits on its seat with zero overlap;
    - clearance to the drop arm, the camera and the buffer parts over the full 20 mm stroke;
    - nothing in the label view or the window views;
    - seat fit for both station ring sizes;
    - ring glare in the window, modelled as a flat mirror (0.0% of the window now; it was 1.0% with the old window);
    - the jig rings match the machine's (0.0 mm offset).
- **`build.py`:** adds a `holders` key to heads_cad.json. HEADS and the PSA `card_top_from_label_edge_mm` are unchanged because a software test reads them.
- **`render_docs.py`:** face_down_view now shows the worst PSA and CGC card tops and the ring's mirror image. I also fixed its caption, which already ran off the image.
- **Re-exported:** `export_printed`, `write_cut_list` (no change), `export_assembly('home')`, heads_cad.json. `render_docs.py` and `render_parts.py` re-run; 12 images in docs/img changed.

**Check totals** (copied from the run output)
- `python3 layout.py` → `checks: OK`
- `python3 checks.py` → `layout checks: OK`, `154/154 checks passed`, exit 0, 5m49.6s. Saved to cad/out/checks.txt.
- Every check that existed before kept its value except the window and aim ones.

**Numbers you asked for**
- **Aim tolerance** [Certain, exact frustums]: **1.34°** toward the cup, cup pad first. Away from the cup, +X and −X are all past the 4° search.
- **Card margins:**

| Grader | Top-edge margin | Side margin | Aim before leaving the card |
|---|---|---|---|
| PSA | +3.68 mm | 0.9 mm | 0.34° |
| CGC | +0.26 mm | 0.45 mm | 0.10° |

- **New window values:**
  - Cup axis: `[[-27.5, -23.5, 27.5, -18.0]]`
  - **Camera axis (`face_down_window_cam()`): `[[-27.5, -18.5, 27.5, -13.0]]`**
  - Phase 0 flipped version: `[[-27.5, 13.0, 27.5, 18.5]]`

**Software changes needed** (I did not edit software/)
- **5 tests fail, and the window causes them** [Certain]. On an identical snapshot of software/, the old window gave `9 passed in 158.97s` and the new one `5 failed, 4 passed in 75.52s`. On the live tree, `test_carry_sensor.py` plus `test_face_down_learned.py` gave `5 failed, 44 passed in 346.91s`. I did not run the full suite.
  1. Regenerate `config.py`'s default window and `config/machine.toml` with gen_config. The Phase 0 sim used the stale default, so its signature mismatched (`test_phase0_sim_reports_the_separation`).
  2. Retune four tests that were set for the 632 mm² window:
     - two `static_fraction() < 0.02` asserts now see 0.0303 (`test_a_face_down_old_label_passes_once_enough_qr_references_exist`, `test_the_reference_file_persists_across_runner_instances`);
     - the `foot_y-12.35` case of `test_a_head_that_hides_part_of_the_window_is_refused`;
     - the glare `compare > 0.8` assert, now 0.791 (`test_glare_is_masked_and_keeps_a_frame_out_of_the_references`).
- `sim.CARD_TOP_RANGE_MM` should become per grader, using the numbers in heads_cad.json `holders`.
- The window is mapped at the nominal 147 mm. When a stack sits 4.5 mm low (`max_surprise`), the window's label-side edge lands 0.31 mm past the worst CGC card top [Likely]. The software should map the window at the distance it measured, or take the frame again.
- On real images the highest face-up score is 0.53 against the 0.55 floor. The software owner should decide whether that margin is enough.

**Doc changes needed** (they/them, short sentences)
- **BUILD_GUIDE**
  - Read-this-first rows 42–43: the window now fits PSA and CGC (measured on 22 PSA and 27 CGC backs). Aim tolerance is 1.34°, not 0.6°.
  - §1.2: the user measures from the card top to the slab's **far** end. It must be at least 93.5 mm; the real backs gave 93.8–100.0.
  - §1.7: the flipped window is `[[-27.5, 13.0, 27.5, 18.5]]`.
  - §3.2 print table (needs reprint):

| Part | Volume (cm³) | Print time | Note |
|---|---|---|---|
| station_mount | 65.0 | about 3.6 h | 29 mm tall |
| phase0_base | 128.0 | about 7.1 h | |
| phase0_top | 55.7 | about 3.1 h | 8 mm thick; ring pocket faces up |
| camera_bracket | 16.9 | unchanged | |
| **Total** | **768** | **about 43 h** | times are [Guessing], scaled by volume |

  - §3.3: head seat is a 41 mm bore with a 33 mm lip (fits any ring ID up to 37). Station seat is a 64 mm bore and takes a 60 or 63 mm ring.
  - §1.5 step 2 and §7.7: fix each ring with three dots of glue (the bore alone does not hold it). Route the leads through the lip notch (head) or the shelf slot (station).
  - §7.7 and §11.4: 1.34° aim; the new window values.
- **DESIGN** lines 261, 305, 310, 325–326. **CONTRACT** lines 51 and 88–93. **OPERATING** line 507. **README** line 120. Each needs: 154 checks, the new window in both frames, 302.5 mm², 1.34°, the CGC data, and removal of "ring not modelled".
- **BOM.md** item 3 (seat sizes) and item 7 (the ring is now in the CAD; the barb clears it by 3.75 mm). **WIRING** lines 567–568 (seat sizes).
- **RESEARCH** lines 138–139: replace the "15 CGC backs, 2.5–3 mm further" claim with the measured per-grader numbers.

Scripts and logs are in scratch/round4cad/:
- cardpos.py, cardpos.json (card position measurement)
- window_ab.py, window_ab2.txt, window_ab_worst.txt (real-image window A/B)
- snap/old.txt, snap/new.txt (software test A/B)
- checks_final.txt