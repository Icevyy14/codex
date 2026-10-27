The report's main findings hold up. Its glare numbers are too optimistic for the face-down QR, and its "zero false proofs" result for the new face-down rule is tested only on the 64 slabs the rules were written from.

Scripts and raw outputs are in `scratch/real_eval/check/`. Everything ran from `software/` with `PYTHONPATH` set to it.

`runner.py` was edited by someone else while I was running (mtime 15:15:55). `_check_face_down` now has `face_down_ok_pocket` and `_defer_reference`, so my stub had to be updated. The part the claims depend on (`psa_back` and `fronts`) is unchanged.

## Verdicts on the report's claims

1. **Wrong 13-digit CGC cert: CONFIRMED [Certain].**
   - `rules.py`: `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` parses as `CGC 140101289312`; the 13-digit Code128 returns `None`.
   - `native_analyze.py`: cgc-1401012893129 gives `fallback=ok 140101289312, always=ok 140101289312 <-- WRONG CERT`.
   - `machine_check.py` (hover, 2 held and 2 station frames): `verdict_always ['ok','140101289312']`, and the station frames show `Code128:1401012893129` only as unparsed. Nothing catches it.

2. **Face-down 'stop' rule: CONFIRMED [Certain], one wording error.**
   - `native_facedown.py`, which calls the real `Runner._check_face_down`:
     - face-down views: `qr: 21`, `STOP(a CGC code is visible…FRONT): 25`, `STOP(no PSA back-label QR): 18`
     - face-up views: 64 of 64 stop
   - The 5 random slabs at machine scale agree: 2 PSA pass with `qr`, 3 CGC stop with the FRONT-label reason.
   - Wording error: "every face-down CGC slab gets the wrong reason" is false. It is 25 of 31. The 4 OG slabs with a cgccomics QR and the 2 Authentic slabs get the generic reason.
   - I did not check the README claim that learned mode never becomes active with the CAD head. The README does say it.

3. **`ItfModel` never learns: CONFIRMED in practice, PARTLY as stated.**
   - After 5 QR+ITF pairs with 8-digit certs, the evidence is `{}` and the mode is `None`.
   - Back ITF and front ITF agreeing still gives `needs_review 'padding vs check digit not learned yet'`. I confirmed this on the real PSA 2016 slab 25656882 at machine scale.
   - The report's examples are wrong: 16870121, 02074012 and 01418255 are pre-2016 labels with no back code, so its back+front test was synthetic.
   - All 48 ITF payloads in the set are 8 digits, including the three zero-padded 7-digit certs.
   - "Can never learn" is too strong [Likely]: PSA reholders keep the cert number, so a 7-digit cert on a QR+ITF label can exist. It would still need 3 such slabs in one run.

4. **CGC OG slabs mostly `no_read`: CONFIRMED.**
   - Natively without OCR: 4 `no_read` and 1 `ok`. The `ok` one is cgc-4190928178, whose QR is on cgccards.com.
   - Machine scale: cgc-3750599206 is `no_read`.
   - The unparsed list matches the report exactly.
   - OCR on the native front of ms_1926130_0 gives `1995965624`, the invented cert, confirmed.

5. **OCR timeouts come from OpenMP threads: CONFIRMED [Certain]** (`ocr_time.py`).
   - Default threads: 5 of 5 calls timed out at 30.5–31.5 s, at load 4–8.
   - `OMP_THREAD_LIMIT=1`: 1.0–2.2 s per station frame (`25656882` ✓, `16870121` ✓) and about 6 s per native image.
   - Nothing in the repo sets `OMP_THREAD_LIMIT`.

6. **Phantom Code128: CONFIRMED** (`phantom.py`).
   - At 1.0x: `('Code128','27435764',(240,633),(486,547))` and `('Code128','09435764',(240,630),(522,534))`.
   - The phantom is absent at all 10 other scales tried, from 0.5x to 2.0x, including the 1.105x that matches the station camera.
   - It gives `conflict 'codes disagree: 27435764, 9435764'` in always mode and `ok` in fallback mode. At machine scale both station frames read only 27435764.

7. **Five random natively-ok slabs at machine scale: CONFIRMED.**
   - The slabs were psa-69677740, cgc-6127216011, psa-27720238, cgc-6087467008 and cgc-6022056070 (seed 20261022).
   - All 5 came out `ok` with the right cert, in both fallback and always modes.

8. **Proposed face-down table: CONFIRMED on the same data.**
   - Re-parsing my native decodes with `proposed.face_from_above`:
     - back images: 50 `down`, 14 `unknown`
     - front images: 22 `up`, 42 `unknown`
     - 0 false proofs in either direction
   - The proposed `parse2` still turns the phantom into `PSA 9435764`. Only the phantom-drop rule in `consensus2` removes it.

9. **The CGC front Code128 is the weakest symbol: CONFIRMED, but it depends on pose** (`station_sweep.py`, 3 poses per slab).
   - 65 of 72 station frames read it; 22 of 24 slabs read at least once.
   - Wigglytuff and 25th-anniversary Venusaur read 0 of 3.
   - In my full machine replay, cgc-6022056070 failed on both station frames and the face-up hover frame, but read 3 of 3 in the sweep. The report's 16/19 is a single-pose estimate.

10. **Early exit hides QRs: NOT REPRODUCED** (`early_exit.py`).
    - In 24 held frames with a glare spot on the QR, the QR was lost in 5. The CLAHE pass recovered it in none of them, so early exit hid nothing.
    - The mechanism is real in the code; the evidence for it is one frame.

11. **PSA URL regex truncates silently: PARTLY.**
    - `cert/1234567890123` gives `None`, so a longer number is not truncated.
    - It truncates only when there are leading zeros: `cert/012345678901/` gives `1234567890`. The risk is low.

12. **The 54 QR certs agree with the manifest: CONFIRMED.** There are 55 QR payloads with a number; the one that disagrees is the 0100000001 placeholder.

13. **Phone photos give no QR: CONFIRMED natively.** weirdslab_2 and weirdslab_3 read the ITF only. I did not test them at machine scale.

## What the report missed

1. **The glare column hides QR loss on PSA backs.** The per-image "read" counts the ITF, so lighthouse backs show "11/11 glare" even when the QR is gone. The QR is what proves face-down. I lost it in 5 of 24 frames when the spot sat on it, and each of those becomes a face-down stop on a hover frame.

2. **OCR labels every hit as PSA.** `parse_payload(t, "OCR")` always returns grader PSA. `needs_review_to = "output"` is set in `config/machine.toml`. So BGS, SGC and CGC OG slabs that end on OCR only are sent to the output stack, not the exception pocket. They also carry wrong numbers there: `0079865140` (BGS) and `1995965624` (CGC OG).

3. **Grade 0_0 does not mean a front label.** `cgc/official/unique-identification.png` is CGC's official render of the 2023+ label back, and its QR is `HTTPS://WWW.CGCCOMICS.COM/CERTLOOKUP/0100000001/0_0`. The proposed rule would call that back face-up. That error is safe (it stops), but the rule rests on just 2 Authentic slabs.
   - The unsafe direction is resting on thin evidence too. The generic CGC QR counts as proof of face-down on [Likely] evidence only (press images and mock-ups).
   - Only rules rated [Certain] should be allowed to prove face-down.

4. **The proposed results are tested on their own training set.**
   - The rules were written from these same 64 slabs, so "0 wrong certs" is not evidence for new slabs.
   - `consensus2` is not the real `_decide`: it leaves out the batch-duplicate rule and the `psa_cert_digits` rule.

5. **The CGC OG slab at machine scale was upscaled from a coarser photo.** ms_1926130 is about 0.071 mm/px, so my result there is pessimistic. The report skipped such images.