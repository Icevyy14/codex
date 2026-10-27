I made the real-label fixes, but the full suite does not pass in the repo as it stands now. In the working tree it is **19 failed, 221 passed, 1 skipped**. [Certain] The failures come from the other agent's head redesign in `cad/` (now part of WIP commit 346deca), not from these changes. Run against `cad/` from c8b8126, the same software passes **240 passed, 1 skipped**. One more caveat comes before the good numbers: 0 wrong certs and 0 false face-down proofs were measured on the same 64 slabs the rules were written from. That shows the rules fit those slabs, not that they are safe on new ones.

## Test totals
- **Mirror** (this `software/` plus `cad/` from c8b8126): `240 passed, 1 skipped in 741.67s (0:12:21)`. [Certain]
- **Real tree** (`cad/` as committed in 346deca): `19 failed, 221 passed, 1 skipped in 664.43s (0:11:04)`.
  - The failures are 18 tests in `test_face_down_learned.py` plus `test_tools.py::test_committed_machine_toml_matches_layout` ("config/machine.toml is stale").
  - [Certain] The new `cad/layout.py` exports `FACE_DOWN_WINDOW_MM` measured from the cup axis, and `config.from_layout()` reads it as camera-axis coordinates. The c8b8126 software fails `test_a_face_down_old_label_passes_once_enough_qr_references_exist` against that layout too.
- **Optional real-image test** (`SLABRAIL_REAL_IMAGES` set): `1 passed, 51 deselected in 109.84s`.

## Changes per file
- **`slabscan/certs.py`**
  - PSA QR regex now has a right boundary: a too-long number is rejected, not cut.
  - CGC QR regex covers cgccards and cgccomics, any case, 10-digit or 140+10-digit certs, optional grade, optional slash. The 13-digit cert is no longer cut to 12.
  - Bare digits are typed by symbology and length:
    - ITF of exactly 8 digits is a PSA cert; any other ITF length is a misread.
    - Code128 of 26–28 digits is a CGC OG back; the cert is the last 10.
    - Code128 of 10 or 140+10 digits is a CGC front.
    - Code128 of 7–9 digits is PSA.
  - OCR reads now carry grader `unknown`, and OCR tokens are PSA 8–10 digits or CGC 140+10.
  - New `SIDE_PROOFS`, `label_side`, `side_evidence` and `face_from_above`. Only [Certain] rows prove a side; a CGC QR without a cert is a hint only.
  - `ItfModel` is kept for its callers but fixed: `mode` is always `zero_pad`, and `evidence` counts slabs where QR and ITF agreed. `alt_cert` is removed.
  - `CodeRead` gains `frame` and `box`. New `drop_phantoms` guard in consensus.
  - Consensus rules:
    - Any barcode-only result needs two printed symbols or OCR agreement.
    - A single CGC barcode is never `ok`. I read "a single CGC read" as a single CGC barcode, so a CGC QR alone is `ok`, like a PSA QR.
    - OCR-only and grader-less results are `needs_review` with grader `unknown`.
    - `no_read` now has grader `unknown`, and the order of the sources column is fixed.
- **`slabscan/decode.py`**
  - Process env sets `OMP_THREAD_LIMIT=1` (setdefault).
  - Phantom filter: a barcode read lying inside another read of the same symbology and less than a third of its thickness is dropped. It drops the real `09435764` phantom.
  - Head-camera frames run the CLAHE pass before the early exit when only a barcode was found.
  - `_source_for` follows the label side the payload proves: the CGC Authentic QR is `front_qr`, and a PSA QR is `back_qr` whichever camera reads it.
  - New 0.75x/0.6x downscale pass for station frames (section 9 item 9).
  - `label_band` crops OCR to 3.2 barcode lengths along and 0.6 across the barcode.
- **`slabscan/runner.py`**
  - `_check_face_down` uses `face_from_above` and takes the unparsed payloads.
  - It returns `qr`, or `code` for the OG back barcode.
  - New FACE-UP stop message; back and front codes together, or two different back labels, stop the run.
  - Every back-code proof teaches the learned references (source `qr`, with meta `proof`).
  - Frames are numbered; OCR is cropped to the label band.
  - New `needs_ocr`: OCR runs for any barcode-only `needs_review`.
  - `needs_review` with grader `unknown` always goes to pocket 12.
  - `_settle_reference` vetoes on any certain back proof seen from below.
- **`slabscan/sim.py` and `simworld.py`**
  - `label_codes` per grader and era, using the real formats; both PSA QR URL forms appear.
  - PSA prints 7-digit certs zero-padded to 8 [Likely]; BGS and SGC carry no code.
  - `SimSlab` eras: PSA `current`, `2017+` (ITF up to 8 digits, Code128 for 9), `2016`/`2015`, `old`; CGC `2023+`, `og`, `authentic`.
  - Default mix `DEFAULT_MIX` [Guessing]: PSA current 55%, 2017+ 15%, 2016 3%, pre-2016 5%; CGC 2023+ 15%, OG 4%, Authentic 1%; BGS 2%. No SGC: it does not fit the pocket.
  - Added `parse_mix`, a fill-line guard and `back_code`; removed `itf_payload` and `other_grader_view`.
  - The `eras=` path keeps the old random stream; 9-digit certs move to 8 digits on ITF-era labels.
- **CLI, factory and messages:** `cli.py` (`sim --mix`, `--eras` is now an optional PSA-only override, label counts, new face-down wording); `factory.py` (`mix`); `config.py`, `facedown.py`, `results.py`, `web.py` wording.
- **`tools/real_eval.py` (new):** works on an index.json or `--phase0 DIR`, at native resolution or `--machine` (with `--glare`, `--json`). It exits 1 on a wrong cert in an `ok` verdict or a false face-down proof.
- **`tools/phase0.py`:** the face-up prompt now says to slide the occluder mount 3 mm up first, change slabs with the cup no more than about 12 mm up, and slide the mount back to 62.0 mm afterwards. The ITF-teaching text is gone; the report has a payload-format check (ITF lengths, unparsed payloads, back-QR count).
- **`tools/decode_sweep.py`:** now uses the real formats.
- **`setup_pi.sh`:** the systemd unit sets `Environment=OMP_THREAD_LIMIT=1`.
- **Tests:** new `test_real_payloads.py` with the real payload strings, the 13-digit case, the phantom, the OG barcode, Authentic `0_0`, the truncated ITF, the side table and the env-gated real-image test. Tests that encoded the old rules were updated in `test_certs`, `test_decode`, `test_runner_sim`, `test_safety_fixes` and `test_face_down_learned`.

## Real-label check (`python3 -m tools.real_eval .../realslabs/index.json`)
Counts are ok / needs_review / no_read, with wrong certs in `ok`.

| run | slabs | ok | needs_review | no_read | wrong in ok |
|---|---|---|---|---|---|
| EVAL native, current software | 64 | 52 | 7 | 5 | 1 |
| EVAL native, proposed rules | 64 | 58 | 4 | 2 | 0 |
| **Now, native** | 64 | **60** | 2 | 2 | **0** |
| EVAL machine, current software | 58 | 51 | 4 | 3 | 1 |
| EVAL machine, proposed rules | 58 | 56 | 2 | 0 | 0 |
| **Now, `--machine`** | 61 (+3 with no usable image) | **60** | 0 | 1 | **0** |
| **Now, `--machine --glare`** (glare also on the hover frame) | 61 | 58 | 3 | 0 | 0 |

- **Slabs not `ok`, native:**
  - Two PSA pre-2016 slabs: one where OCR read 199941033 against the ITF 19802594, and one with an ITF read and no OCR result.
  - BGS and SGC are `no_read`: their labels carry no code.
- **Face-down rule:**
  - Native: 50/64 backs proven down, 24/64 fronts proven up, 0 false proofs in either direction. EVAL proposed 50 and 22; the two extra come from the downscale pass.
  - Machine: 48/61 down, 17/58 up, 0 false. Machine with glare: 47/61 down, 0 false.
- **Unparsed payloads on good images:** none. [Certain]
- **Item 9:**
  - At native resolution the CGC front Code128 now reads 17/19 standard and 5/5 gold.
  - At station scale there is no gain: still 16/19.
  - Painting a white quiet zone around the label read 0 of the 4 failures.
- **Comparability:** the machine-mode slab set and poses differ slightly from EVAL's (`--max-upscale` 1.15 on both sides, different pose seeds), so those rows are close but not the same sample.

## 330-slab sim (default mix, seed 7, `cad/` from c8b8126)
- **Mix:** PSA current 170, 2017+ 56, old 21, 2016 12; CGC 2023+ 49, OG 12, Authentic 5; BGS 5.
- **Result:** `needs_review 6, ok 324`, no `no_read`.
  - 5 BGS slabs were OCR-only and went to pocket 12.
  - 1 PSA slab had OCR disagreeing with its barcode.
- **Timing:** 13.9 s per slab, 77.6 min for the load (homing + survey 66 s).
- **With `--face-down-check` and the CAD head:** 287 slabs proven by back QR, 43 stops. The 43 are exactly the slabs with no back-label code.

## Open risks
1. [Certain] The rules are validated only on the slabs they were derived from. A 10-digit Code128 from another grader would be typed CGC; it would then need two sources, so it lands in `needs_review`, not `ok`.
2. [Certain] Integration with the head redesign is still to do (all in `software/`, which this task owns, but it depends on a design still in flux):
   - `config.from_layout()` should use `layout.face_down_window_cam()`, if that is the intended meaning.
   - `sim.HEADS["cad"]`, `CARD_TOP_MM` (36.1 per the new layout) and `HEAD_CAM_DY` need to follow the new head.
   - `config/machine.toml` must then be regenerated with `python -m tools.gen_config`.
3. [Likely] The machine-equivalent frames are optimistic: flat scans, no plastic reflections. The real phone photos through plastic lost the QR.
4. [Certain] "Grade 0_0 means front" rests on 2 slabs and is contradicted by one official render of a back. A wrong call only stops the run, which is safe.
5. [Certain] A PSA slab with one barcode and no OCR confirmation still goes to the output stack (`needs_review_to = "output"`).
6. [Certain] `tools/enrich.py --include-review` will look up OCR-only `unknown` certs at PSA. That could return an unrelated card. Not changed.
7. [Likely] The phantom thresholds are fitted to a single real case.
8. [Certain] `test_web` and `test_runner_sim` need Tesseract installed, as some already did.
9. [Guessing] Pi timing: a front with no code still costs about 9 s of decode CPU per frame on this PC, and the downscale pass adds about 0.3–0.6 s.

## Doc changes the docs agent must make
- **OPERATING.md**
  - Top bullets (§1):
    - "without a PSA back-label QR" becomes "without a back-label code": a PSA back QR, a CGC back QR (cgccards or cgccomics, with a grade) or the CGC 2020-23 back barcode.
    - CGC 2023+ and OG slabs no longer stop. Still stopping: PSA 2016 and older, CGC Authentic, BGS, SGC (14 of 64 real slabs).
    - "an ITF-only read" becomes "a barcode-only read (ITF or Code128, any grader)".
  - Loading table:
    - Remove "CGC slabs have no PSA back QR, so each one stops".
    - BGS has no code: it reaches pocket 12 as `no_read` or OCR-only `needs_review`. `other_grader` appears only if a BGS/SGC/TAG URL is read.
  - Start-line strings:
    - `face-down check: back-label codes only - every slab without one (a PSA back QR, a CGC back QR or the CGC 2020-23 back barcode) stops for you`
    - `... Until then every slab without a back-label code (...) stops for you, as in 'stop' mode`
    - learned mode: "a slab without a back-label code is picked only if ...".
  - §5.3 `face_down` values: add `code`; the summary line now reads "N by back QR, M by a back-label barcode".
  - `sources`: the tag follows the label side the payload proves. `back_qr` is a PSA or graded-CGC QR from either camera; `front_qr` is the CGC Authentic QR.
  - `summary.json`: `itf_mode` is always `zero_pad`; `itf_evidence` counts QR/ITF agreements.
  - Status table:
    - `ok` = "a QR, or a barcode on two printed symbols, or a barcode confirmed by OCR".
    - New notes: "one printed barcode only (no QR) - confirm", "barcode N but OCR read M - verify by eye", "OCR only (no barcode or QR read), grader unknown - check by hand", "grader not confirmed (a code with no grader's format)", "dropped a phantom read Code128:...".
    - Remove the "padding vs check digit", "ITF from one source only" and "ocr only - verify by eye" notes.
    - OCR-only and grader-unknown slabs always go to pocket 12, whatever `needs_review_to` says.
  - Stop-message table:
    - Replace the not-confirmed message with "...(no back-label code was seen from above (a PSA QR, a CGC QR or the CGC 2020-23 back barcode)[; a CGC QR without a cert number ...][; learned check: ...]) ... If it is face-down (older PSA labels, CGC Authentic, BGS and SGC slabs have no back-label code), resume with --face-down-ok ...".
    - New: "Pocket N: the top slab is FACE-UP (a CGC front-label barcode (…) / a CGC Authentic front-label QR (grade 0_0) … is visible from above, and that code is printed on the FRONT label). … Turn the top slab of pocket N face-down, label end toward you, then resume. Only if it already is face-down, resume with --face-down-ok …".
    - New: "… are both in view: another slab's label is in view" and "two different back labels are in view (A, B) …".
    - Delete the "CGC code … sit on the FRONT label" row.
    - Reference veto note: "the read station saw <a PSA back-label QR | a CGC back-label QR | a CGC 2020-23 back-label barcode> from below".
  - Troubleshooting: remove "ITF only … not learned yet". Add: pre-2016 "one printed barcode only" means OCR did not confirm; check Tesseract and focus.
  - §8.4 learned check: replace "back QR" with "back-label code"; stop mode no longer stops every CGC slab.
  - Quick card: update to the new wording.
- **DESIGN.md**
  - Reading section: replace the ITF padding / check-digit bullets with the real format table (the `certs.py` docstring). Also cover: ITF is exactly 8 digits; the barcode-only two-source rule for any grader; QR alone is `ok`; OCR has no grader and goes to the exception pocket; phantom guard in decode and consensus; CLAHE before the early exit on head frames; station downscale pass; OCR on one thread with the label-band crop.
  - Face-down: the side table with only [Certain] proofs, face-UP and neighbour stops, CGC-proven slabs teach the references.
  - Verification table:
    - 240 passed / 1 skipped.
    - New row for `tools/real_eval.py` with the numbers above, and the caveat that they come from the training set.
    - 330-sim row: ok 324 / needs_review 6, 13.9 s/slab, 43 face-down stops.
  - Risks: "Older labels stop the run" now means slabs without a back-label code.
- **RESEARCH.md** — real-label facts:
  - PSA front codes: ITF on lighthouse, 2016 and pre-2016 labels; Code128 on current labels. PSA back codes: QR + ITF on lighthouse, QR + Code128 on current, ITF only on 2016, nothing before 2016.
  - QR URL forms: `http://psacard.com/cert/N` and `https://www.psacard.com/cert/N/`.
  - The ITF is the cert zero-padded to 8 digits; 9-digit certs never use ITF. The printed 7-digit cert is zero-padded too [Likely].
  - CGC certs are 10 digits or 140+10. The 2023+ back QR carries the grade, and the front has a short-bar Code128 (no Code128 on 0/26 backs).
  - The OG QR is on cgccomics.com, with a 26–28-digit back barcode ending in the cert and nothing on the front.
  - Authentic: `0_0` QR plus Code128 on the front, nothing on the back.
  - BGS and SGC carry no codes.
  - Observed failure modes: the phantom Code128 and a glare-truncated ITF.
  - Tesseract timeouts come from OpenMP threads.
- **README.md** (top level)
  - The "Older labels still stop … and CGC" line: CGC 2023+ and OG now pass.
  - BGS goes to pocket 12 as no-code, not `other_grader`.
  - Cycle time: 13.9 s per slab and 77.6 min with the new mix.
  - Remove "learning how PSA encodes 9-digit certs".
  - Mention `tools.real_eval` and its results.
- **`software/README.md`** (not in my owned list, so I left it): fix "stop: only a PSA back-label QR … CGC stop every time", the `summary.json` ITF wording and the `sim --mix/--eras` options, and add `tools/real_eval.py` to the tools table.
- **BUILD_GUIDE.md**
  - Phase 0:
    - Drop "Scan five 2024+ slabs first: they teach the ITF format".
    - Replace the record rows "Digits in the front barcode for a 9-digit cert" and "ITF format learned" with the new report lines: payload formats, ITF payload lengths (all 8), payloads no rule reads, slabs whose back QR the head read.
    - Add CGC 2023+, OG and Authentic slabs to the scan mix.
    - Note that the face-up prompt now gives the 3 mm occluder instructions.
    - Add a step: `python -m tools.real_eval --phase0 phase0_results` (and on phone photos via an index.json); 0 wrong certs and 0 false face-down proofs required.
  - §11.3 setup: the `--service` unit sets `OMP_THREAD_LIMIT=1`, and `decode.py` sets it for CLI runs.

Result files are in scratch/sw_check:
- native3.txt
- machine3.txt
- glare3.txt
- sim330c.txt
- sim330fd.txt
- suite_mirror3.txt
- suite_realtree2.txt