The expected result "all 7 pre-2016 slabs back to ok" holds only at machine scale. On the native images 5 of 7 come back to ok. The other 2 stay `needs_review`, and that is correct: on one, OCR read other digits (19802594 read as 199941033); on the other, OCR read nothing (20908923). [Certain] The ITF rule also rests on a guess. In the real set ITF appears only on PSA labels, but the set has just 1 BGS and 1 SGC slab. [Guessing] If another grader prints an 8-digit ITF, its slab would come out `ok PSA` with the right digits and the wrong grader, and it would stay in the output stack.

## Results (verbatim)
- **Full suite, default command:** `299 passed, 1 skipped in 998.61s (0:16:38)`. After this run started I made two small edits: the summary text for an unchecked camera aim (runner.py) and comments in facedown.py.
- **Full suite with the real-image test** (`SLABRAIL_REAL_IMAGES=.../realslabs`), on the final code (md5 checked after the run): `300 passed in 1202.90s (0:20:02)`.
- **real_eval native:** `REAL-LABEL CHECK (native, front OCR on): 128 images (0 skipped), 64 slabs, 188 s`, `TOTAL 64  60/2/0/2/0`, `WRONG CERT in an 'ok' verdict: 0`, `FALSE FACE-DOWN proofs (a face-up slab 'proven' face-down): 0`, `EXIT 0`. Pre-2016: `5/2/0/0/0`.
- **real_eval --machine:** `REAL-LABEL CHECK (machine, front OCR on): 128 images (9 skipped), 61 slabs (+3 with no usable image), 281 s`, `TOTAL 61  60/0/0/1/0`, wrong 0, false face-down 0, `EXIT 0`. Pre-2016: `7/0/0/0/0`.
- **330-slab sim** (`sim --slabs 330 --face-down-check`):
  - `batch sim-20261023-055410: 330 slabs  (needs_review 6, ok 324)`
  - `face-down: 287 by back QR, 41 by the learned card-back match, 2 confirmed by you; lowest learned score learned(0.76) at #157`
  - `2 of 330 slabs stopped` (43 with back-label codes only); 14.2 s per slab, 79.4 min; `camera_aim` ok.
  - The 6 `needs_review`: 5 BGS slabs read only by OCR (pocket 12), and 1 pre-2016 slab where OCR read 9 digits. 20 of 21 pre-2016 slabs are ok.
  - [Certain, sim] I checked against the simulated slabs: no 'ok' has a wrong cert or a wrong grader.
- **Phase 0 sim:** lowest back 0.81, highest face-up 0.57, GO at 0.69.
- [Certain] The 3 new resume tests fail on the HEAD versions of runner.py and facedown.py ("DID NOT RAISE Stop"), so they really test the fix.

## Changes (all under software)
1. **ITF rule** (`slabscan/certs.py`):
   - New `psa_itf_confirmed`. An 8-digit ITF names PSA when OCR of the printed number reads the same cert, or a second printed symbol from another source does.
   - The new 'ok' note adds "grader PSA from its 8-digit ITF".
   - It is a separate path from the other grader rules. So an ITF alone stays `needs_review`, even with `min_sources=1`. OCR alone stays unknown grader and goes to pocket 12. An ITF of any other length never parses.
   - Code128 plus OCR stays `needs_review`.
   - The text on a guessed grader now says "(OCR confirms its digits, not its grader)".
   - Tests:
     - New exhaustive ITF test.
     - Updated `test_single_1d_read…` and `test_a_grader_from_one_barcodes_length…`.
     - The all-combinations test now allows the ITF rule.
     - The runner test for old labels is rewritten.
2. **Code128 narrowings:**
   - `_PSA_C128_RE` is now 8–9 digits.
   - A 10-digit CGC Code128 must not start with 0.
   - A Code128 outside these formats is listed as unparsed and proves no label side.
   - Tests: the parse table, plus a decode-level test where two 7-digit Code128s give `no_read`.
   - [Likely] An 8-digit Code128 with a leading zero still parses as a 7-digit PSA cert. The only real one seen is the phantom '09435764', and the phantom tests need it to parse.
3. **Resume and camera aim:**
   - `CardBackRefs.stale` (not saved to the file) is set when a survey starts and cleared by a view over an empty pocket.
   - While it is set, the learned check accepts nothing and learns nothing, the same as a failed aim check.
   - If no pocket was empty at the resume survey, `_work` takes the view over the first source pocket it empties.
   - The summary's `camera_aim` then says "not checked this run (…)".
   - Tests: a knocked camera with an empty pocket; no empty pocket, square vs knocked; and a unit test.
   - Files: `slabscan/runner.py`, `slabscan/facedown.py`.
4. **Card position in the sim** (`slabscan/sim.py`):
   - Per grader `HOLDERS`, the same as the CAD's heads_cad.json `holders`.
   - PSA card top is 34.8–38.32 mm from the label-end edge, covering both PSA measurements. CGC is 37.69–40.14 mm on a 133.9 mm holder, with ±2.55 mm play.
   - [Certain, test] The sim's worst card top is within the CAD's `card_top_worst` minus its calibration allowance.
   - `tests/test_carry_sensor.py` now checks this against heads_cad.json.
   - The card is still 63.5 × 88.9 mm; the CAD uses 63 × 88. [Likely] That is minor.
5. **Small items:**
   - `tools/phase0.py` refuses an `--out` folder that already has a `phase0.csv` (exit 2, nothing changed), and `--force` overwrites. Tested.
   - The `calibrate x` prompt now names the tape cross (BUILD_GUIDE 12.2). Checked in `test_cli`.
   - The `cli.py` threshold comment now has the new Phase 0 sim numbers.
   - `README.md` is updated: 300 tests, the ITF and Code128 rules, resume aim, phase0 `--force`, tape cross, sim numbers.

## Doc changes needed (not my files)
- **README.md:**
  - Line 51: a pre-2016 slab is `ok` when OCR confirms its ITF. It is `needs_review` only when OCR reads nothing or other digits. Real set: 5 of 7 native, 7 of 7 machine scale.
  - Lines 132–134: the totals above.
  - Line 150: native 60 of 64 ok, machine scale 60 of 61.
- **OPERATING.md:**
  - Lines 43, 259, 487 and 629: same pre-2016 change. Add the 'ok' note text, and the new wording of the guessed-grader text.
  - Resume: a new stop reason, "the head camera's aim is not checked this run yet". Tip: empty pocket 12 before resuming so the aim is checked at once. `face_down_baseline` can now come mid-run. Add the new `camera_aim` value.
  - A 7-digit Code128, or a 10-digit one starting with 0, now goes to unparsed, then pocket 12.
  - Add: if the user sets `psa_cert_digits`, include 7, or every 7-digit pre-2016 cert becomes `needs_review`. [Certain, `Runner._decide`]
- **BUILD_GUIDE.md:**
  - Line 335: phase0 now refuses to overwrite; `--force` overwrites.
  - Line 1648: drop the "pocket centre mark" aside.
  - Lines 1796, 2047 and 2100: pre-2016 can now be `ok`.
- **DESIGN.md:**
  - Lines 210–211: grader rule.
  - Lines 388–389: new numbers.
  - Line 406 risk row: the narrowings are now applied. New risk: another grader's 8-digit ITF with OCR agreeing gives `ok PSA`. [Guessing]
  - Remove the "stale aim on resume" and "CARD_TOP_FROM_EDGE vs HOLDERS" risks.
- **CONTRACT.md lines 190–191:** grader rule.
- **RESEARCH.md line 146:** the simulator now uses the per-grader holder numbers, not CARD_TOP_FROM_EDGE alone.
- **For the CAD owner:** another process has uncommitted edits in cad/ (model.py, checks.py, render_docs.py, build.py; layout.py is unchanged). If heads_cad.json is exported again, `sim.HEADS` and `sim.HOLDERS` must match it. Also, the round-4 CAD verifier found a PSA back (fc_18805593, 96.29 mm from the card top to the far edge) that the CAD's numbers leave out.

Evidence (round 5) is in scratch/round5/:
- suite_full.txt
- suite_real.txt
- real_native_final.txt
- real_machine_final.txt
- sim330.txt
- p0sim/phase0_report.txt

I ran no git commands that change state, and I killed no processes.