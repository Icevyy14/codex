Phase 0A still can't be built from the docs alone. There is no live link for a 40 mm COB head ring, so the docs now give a 12-SMD fallback. The switch mounts are a written method that nothing has checked. Both need someone to act before order 1a or the frame build. [Certain]

**One thing I did differently from the walkthrough's fix:** it said to regenerate the shopping-list confidence tags from the CSV. For 9 of the 11 mismatched lines the CSV was the wrong side, because their notes say "price not seen" or "price confirmed". So I set both files from that price evidence instead. [Certain]

**Test and check totals**
- I didn't start these runs. Another process ran them on this tree at 05:00, and the code hasn't changed since. [Certain]
  - Software suite: `288 passed, 1 skipped in 1020.95s (0:17:00)`
  - CAD checks: `152/152 checks passed`, `exit=0`
- The fixer's run with the real-image test turned on, quoted in the docs: `289 passed in 862.10s (0:14:22)`.
- My own runs (no repo changes; output only in the scratchpad):
  - **330-slab sim:** `batch sim-20261023-050355: 330 slabs  (needs_review 26, ok 304)`.
    - Face-down: `287 by back QR, 41 by the learned card-back match, 2 confirmed by you; lowest learned score learned(0.77)`. `2 of 330 slabs stopped` (43 with back-label codes only).
    - 14.2 s per slab, 79.4 min, `camera_aim: ok`.
  - **Phase 0 sim:** `lowest back-to-back similarity: 0.81`, `highest face-up similarity: 0.56`, `GO … threshold = 0.69`. In round 3 these were 0.82 / 0.43 / 0.62, so the smaller window narrowed the simulated margin. [Certain, sim]

**BOM totals** (the grand total is unchanged; the order split moved) [Certain, arithmetic]

| Order | Parts | With 15% allowance |
|---|---:|---:|
| 1a (Phase 0A) | $408.90 | $470.23 |
| 1b (Phase 0B) | $135.16 | $155.43 (was $166.51) |
| 2 (machine) | $1,353.28 | $1,556.27 (was $1,545.20) |
| **All three** | **$1,897.34** | **$2,181.94** |

- School-stock total: $1,862.38. Lean: $1,786.60. Phase 0 together: about $626 (was $637).
- Price confidence split: Certain $1,383.37, Likely $174.97, Guessing $339.00.
- Worst case is now about $2,380 (was $2,365), or about $2,050 with school stock (was $2,039). [Guessing]
- Buying every tool new: about $2,640.

**Changes per file** (all under ``)
- **`docs/BOM.csv`** (CRLF kept, now 128 lines):
  - Moved the PTFE tape ($2.36) out of the reservoir set into its own order-1b line.
  - Moved the push fittings kit to order 2.
  - Changed 9 confidence tags to match each line's price evidence.
  - Rewrote the awl pin spec as one spec.
  - Added a fallback to the head ring line, and the 64 mm seat to the station ring line.
  - "Measure before printing" now names the Phase 0 part, which is printed first.
  - Moving cables now link to a search.
  - Filament note: 768 cm³.
  - Added a pointer to the mains colour mapping, the switch-bracket use of the 2020 corner brackets, and "until an adapter is found, a cup that marks means stop and ask" on the HT1 line.
- **`docs/SHOPPING_LIST.md`:**
  - New totals.
  - Order 1a: school-stock items (screws, plain M5 nuts, microfiber strip and adhesive or tape), and order the cups, elbows and PTFE tape early (about $77 at risk).
  - Moving-cable Link cells are now a search, marked NEEDS A BETTER LINK; the igus cable is only in Notes.
  - The printed-parts Link is now "-".
  - Tags match the CSV.
  - Updated the open problems.
- **`docs/BOM.md`:**
  - New bottom line, order plan, and "what changed" for this round.
  - Tools table: separate hand-drill and drill-press rows, a brad-point bit at least 115 mm long, and a new "drills and small items" group.
  - 768 cm³ of filament.
  - Ring gap updated; gap 7 is now the missing switch mounts.
- **`docs/BUILD_GUIDE.md`:** every blocking, wrong-purchase and confusing item that was a docs problem, plus the nits.
  - Shopping and parts (B1–B3, W2–W5):
    - New read-this-first rows: ring, window, aim, laser, switches.
    - Phase 0A school-stock rows; cups and elbows with 1a.
    - §1.2 now measures card top to the far end (at least 93.5 mm).
    - Ring glue and lead routing.
    - phase0_top web caution (about 1.2 mm of plastic around each standoff hole).
    - PTFE tape in §1.10.
    - Print table: 768 cm³, about 43 h.
    - §3.3 ring limits.
    - 5/16 in dowels.
  - Switch mounts (B4): §6.8 and §7.4 use a 2020 corner bracket, tagged [Guessing].
  - Walkthrough confusing items:
    - C1: laser row.
    - C2: `resume batches/<id>` everywhere.
    - C3: one Phase 0 command, and a warning that a re-run overwrites.
    - C4: use the meter, not `selftest`, while jogging.
    - C5: sideways belt test with a spring scale.
    - C6: tape cross for the pocket centres; `calibrate x` first.
    - C7: clone plus symlink.
    - C8: plain M5 nuts.
    - C9: "stop and ask" in §1.10 and §13.2.
    - C10: instructor and time flags; total is now 65–90 h.
  - Window, aim and software text:
    - New window values in both frames.
    - 1.3° aim with its blind spots.
    - `focus head` aim check over pocket 12.
    - selftest `camera aim` line.
    - Pre-2016 PSA slabs are `needs_review`.
    - New troubleshooting rows.
    - 152 checks.
- **`docs/OPERATING.md`:**
  - Grader rule and pre-2016 PSA.
  - OCR on two-barcode reads.
  - Routing, including the caveat that a grader guessed from length still goes to the output stack.
  - Aim start line, survey line, summary line and `summary.json` `camera_aim`; journal `aim`.
  - New §8.1 aim row; rows 409 and 470 updated.
  - §8.4: 55 × 5.5 mm window, condition 5, limits.
  - CGC wording, belt row, quick card.
- **`docs/DESIGN.md`:**
  - Grader, OCR and phantom rules.
  - New window and the reason it shrank.
  - Layer 10 (aim check) with four blind spots.
  - Aim, CGC and ring-glare limits.
  - Verification table: 152/152, suite totals, the 330-slab and Phase 0 sims, real_eval 55/7/0/2/0 native and 53/7/0/1/0 machine-scale.
  - Risks.
- **`docs/CONTRACT.md`:** 152 checks, the window in both frames plus the flipped one, the ring seats, the switch-mount note, the grader rule, `--sim-head-tilt`, `camera_aim`, budget.
- **`docs/WIRING.md`:** EU-to-US mains colour mapping in §1.1 (I didn't switch the line: that is the instructor's call), ring seats and lead routing in §9.
- **`docs/RESEARCH.md`:** card position per grader (22 PSA / 27 CGC backs), with a note that the CGC holder size comes from cropped scans.
- **`README.md`:** $155, $1,556, $2,380 and $2,050, 65–90 h, the pre-2016 PSA bullet, 152 checks, new suite totals, the aim limits, real_eval 55 of 64 and 53 of 61.
- **`software/README.md`:**
  - 289 tests.
  - 5/16 in dowel offcuts.
  - `focus head` aim check and `focus_head_empty.jpg`.
  - The 1.3° figure.
  - Routing caveat.
  - OCR reading nothing leaves the slab `ok`.
  - `camera_aim` and journal `aim`.
- **Outside the repo:** I also changed the scratch shopping-list generator (`docs3/shop_gen.py`) so "seen:" reference URLs never become the Link.

**Walkthrough findings that still need code or CAD work**
1. **B4:** the CAD needs two switch-bracket STLs (X home and Z top). The docs method is unverified.
2. **W2:** `cad/build.py:118` still writes "8mm hardwood dowel"; it should say 5/16 in (7.94 mm), then re-export `cut_list.csv`.
3. **B1:** once a real head ring is bought, set `model.HEAD_RING` to its size and re-export `camera_bracket` and `phase0_top`. The 41.0 mm bore rejects a "40 mm" ring that measures over 41; the CAD verifier suggested about a 42.5 mm bore with glue dots or crush ribs.
4. **Nit:** the `cad/model.py` comment "3-pack" should say "two 2-packs".
5. **CAD verifier:** `phase0_top` leaves a 1.23 mm web between each M2 hole and the ring pocket. The docs warn about it; the CAD could thicken the part or use inserts.
6. **Optional (C3, C6):** `phase0` could refuse to overwrite `phase0.csv`, and the `calibrate x` prompt could say "the tape cross (BUILD_GUIDE 12.2)".

**Software and CAD items now documented as risks, not fixed:**
- The aim check is one-sided, misses pad-dark parts, and may fire on pad lint.
- Two 7-digit Code128s still give `ok PSA`.
- A grader guessed from length still goes to the output stack.
- A stale aim verdict can carry over on resume.
- `CARD_TOP_FROM_EDGE` and `HOLDERS` disagree.
- The CGC window margin is about zero.

I ran no git commands that change state and killed no processes. The other process committed my edits partway through, as `6e0aede` and `6217b52`; the rest of my edits are uncommitted in the working tree.

Files are in scratch/round4docs/:
- sim/sim330.txt
- sim/p0sim.txt
- before/ (pre-edit copies of the docs)