**Uncomfortable result first: item 3 as you wrote it takes 'ok' away from every pre-2016 PSA slab.** Their only code is one front ITF. OCR confirms the digits, but it never names a grader, so these slabs are now `needs_review` with grader PSA. They still go to the output stack. [Certain] On the real set at machine scale that is 7 of 61 slabs (`53/7/0/1/0`, was `60/0/0/1/0`). In the 330-slab sim it is 20 more `needs_review`. If you would rather trust ITF-8 as PSA's own format, the fix is one line in `certs.names_grader`. That is a [Guessing]-level bet that no other grader prints 8-digit ITF.

**The full suite is not green in the live tree, and I did not cause the failures.** Another agent has uncommitted edits in `cad/layout.py` that move the card window to `(-27.5,-18.5,27.5,-13.0)`. `config.from_layout()` reads the CAD live, so 5 tests fail. [Certain] The same software against the committed CAD passes everything. The HEAD software against the live CAD fails the same 4 face-down tests. Whoever lands that CAD change must run `python -m tools.gen_config` and retune those 4 tests.

**Results, verbatim**
- Full suite, live tree (run alone; two earlier runs were killed for lack of memory while another process used 13 GB): `5 failed, 278 passed, 1 skipped in 660.38s (0:11:00)`
  - The 5: `test_a_face_down_old_label_passes_once_enough_qr_references_exist`, `test_the_reference_file_persists_across_runner_instances`, `test_glare_is_masked_and_keeps_a_frame_out_of_the_references`, `test_phase0_sim_reports_the_separation`, `test_committed_machine_toml_matches_layout` (`face_down_window_mm: ((-27.5, -18.5, 27.5, -13.0),) != ((-27.5, -22.5, 27.5, -11.0),)`).
- Full suite, my software with the committed CAD: `283 passed, 1 skipped in 726.48s (0:12:06)`
- Optional real-image test (`SLABRAIL_REAL_IMAGES`): `1 passed, 54 deselected in 96.39s (0:01:36)`
- `real_eval` native: `REAL-LABEL CHECK (native, front OCR on): 128 images (0 skipped), 64 slabs, 141 s`, `TOTAL 64  55/7/0/2/0`, `WRONG CERT in an 'ok' verdict: 0`, `FALSE FACE-DOWN proofs (a face-up slab 'proven' face-down): 0`, `EXIT 0`
  - All 7 `needs_review` are pre-2016 PSA. 5 of them read "barcode confirmed by OCR".
- `real_eval --machine`: `REAL-LABEL CHECK (machine, front OCR on): 128 images (9 skipped), 61 slabs (+3 with no usable image), 233 s`, `TOTAL 61  53/7/0/1/0`, wrong 0, false face-down 0, `EXIT 0`
- 330-slab sim (`sim --slabs 330 --face-down-check`): `batch sim-20261023-000613: 330 slabs  (needs_review 26, ok 304)`
  - `face-down: 287 by back QR, 41 by the learned card-back match, 2 confirmed by you`; 14.2 s per slab, 79.4 min; `camera_aim: ok`.
  - The 26: 20 pre-2016 PSA (grader not confirmed), 5 BGS read only by OCR (pocket 12), 1 OCR disagreement.
- 110-slab sim tilted 0.8° (`--sim-head-tilt 0.8`): `batch sim-20261023-001310: 110 slabs  (needs_review 8, ok 102)`
  - `face-down: 95 by back QR, 15 confirmed by you`; 0 learned; `CAMERA AIM:` line printed.
  - 15 of 110 stopped, which is every slab without a back code.
- Web test: [Certain] before the fix, 2 of 12 runs of `test_the_face_down_tick_only_confirms_a_face_down_stop` failed under 6 CPU hogs. After it, 30 of 30 passed under the same load.

**1. Phantom confirmation**
- One printed symbol is now one (source, symbology): the head camera's hover and held frames count as one source, and so do the station's frames.
- A number counts as confirmed only by a different symbol: the QR on the same label, the other side's code, or OCR.
- When one number is confirmed, the phantom is dropped from every frame of that symbol. This fixes the "conflict that hides the true cert" case.
- [Certain] Two reads whose boxes do not overlap are treated as two labels, never as a phantom. The old code dropped a second label's barcode as a phantom when a QR confirmed the other number.
- New tests use the real `27435764`/`09435764` payloads and boxes. 3 of them fail on the old `certs.py`.

**2. Camera aim**
- What it does:
  - The survey's empty-pocket frame is checked with `facedown.aim_problem`. It looks for high-passed edges of at least 4 grey levels over more than 2 mm².
  - Where it looks: the middle ±12 mm of the window along the row, over its full height, plus 1 mm beyond its cup-side edge.
- What happens on a fail:
  - The verdict is stored in `card_backs.npz` and the journal (`face_down_baseline` now carries `aim`).
  - Learned acceptances are refused and no references are learned that run.
  - The start line, every stop, the summary (`CAMERA AIM:`), `summary.json` `camera_aim`, `selftest` ("camera aim", from the stored view), `focus head` (a live check over the empty pocket 12) and `refs` all say to re-aim the camera (BUILD_GUIDE 7.7).
- Simulator: `--sim-head-tilt DEG` on every command that takes `--sim`.
- [Certain, sim, round-3 window] A square camera passes, and 0.5° toward the cup is caught. Without the check, 0.6–1.0° passed because only 0–2% of the window was camera-locked.
- Limits:
  - [Certain, CAD geometry] Over an empty pocket at travel height, the outer window also sees this pocket's rods (15.9–18.9 mm) and the neighbouring pockets. Those parts cannot be checked, which is why only the middle is.
  - [Certain] A head part as dark as the pad shows no edge and is not seen. The 10% camera-locked rule is the only guard then.
  - [Likely] On the machine the 1 mm band could refuse a tilt of about 0.2–0.4° if the cup pad contrasts with the pad. That is safe, but strict.
  - [Certain, sim] With the new CAD window the check fires only from about 1.4°.

**3. Grader**
- An 'ok' now needs a code that names its grader (a cert URL), or two different printed symbols in its format.
- Only an accepted grader's `needs_review` may go to the output stack. `unknown`, `PSA/CGC`, an empty grader and BGS go to pocket 12.
- Tests: an exhaustive combination test, a runner-level BGS-style Code128 test, and a routing test with 6 cases.
- [Certain] Still open: two 7-digit Code128s still give 'ok PSA'. The verifier's narrowings (CGC 10-digit must not start with 0; PSA Code128 must be 8–9 digits) are not applied.

**Changes per file** (all under `software/`)
- `slabscan/certs.py`: `CodeRead.kind`, `NAMED_KINDS`, `names_grader`, `_one_symbol`, `drop_phantoms` rewritten, grader rule in `consensus`.
- `slabscan/decode.py`: sets `kind` on every read.
- `slabscan/runner.py`: aim check in `_take_baseline`, `_aim`, `camera_aim` in the summary, routing by accepted grader, `needs_ocr` docstring.
- `slabscan/facedown.py`: `AIM_*` constants, `aim_problem`, region-masked `_highpass`, `_aim_refusal` checked first in `learned_ready` and `learned_match`, references refused while the aim is bad.
- `slabscan/sim.py`: `aim_shift_mm`, `tilt_deg` on both head views.
- `slabscan/simworld.py`: `head_tilt_deg`.
- `slabscan/factory.py`: `head_tilt_deg` passed through.
- `slabscan/cli.py`: `--sim-head-tilt`, summary line, `refs` output.
- `slabscan/ops.py`: `aim_over_empty_pocket`, `stored_aim`.
- `slabscan/web.py`: `SimProvider` takes `**batch_kw`.
- `README.md`.
- Tests: `test_certs.py`, `test_real_payloads.py`, `test_safety_fixes.py`, `test_runner_sim.py` (old-labels test rewritten), `test_face_down_learned.py` (aim tests; 3 expected messages widened to accept the aim refusal), `test_web.py`.
- The web test fix: `HeldProvider` holds the run until Stop is in. Three web tests now use an all-QR label mix (`QR_MIX`), because a pre-2016 label is no longer 'ok'.

**Doc changes needed**
- OPERATING:
  - New stop and start-line text: "learned check not active: over an empty pocket the head camera sees edges … Re-aim the head camera (BUILD_GUIDE 7.7) … Dirt on that pocket's pad looks the same: clean it".
  - New survey log line "CAMERA AIM (pocket N…)" and summary line "CAMERA AIM: …".
  - New `needs_review` note "grader PSA not confirmed: no code names it…".
  - Pre-2016 labels are always `needs_review`.
  - Routing: only accepted graders' `needs_review` stays in the output stack.
  - Phantom note: dropped only when another code or OCR confirms; otherwise `conflict`.
  - Troubleshooting rows 409 and 470; §8.4 conditions.
  - `summary.json` `camera_aim`; journal `aim`.
- BUILD_GUIDE:
  - Read-this-first row: "in between nothing catches it" is no longer true.
  - §7.7 and §12.3: `focus head` checks over pocket 12, which must be empty, and writes `focus_head_empty.jpg`.
  - §12.6: the selftest "camera aim" line.
  - §12 window paragraph.
- DESIGN:
  - The aim check as a guard layer, with its two blind spots (dark parts, outer window).
  - The grader and phantom rules.
  - New verification numbers.

I ran no git commands that change state. I killed only my own pytest processes (8167, 8168, 10955). Logs are in `scratch/round4b/` (`suite_live.txt`, `suite_t1.txt`, `real_native_final.txt`, `real_machine_final.txt`, `sim330.txt`, `simtilt_0.8.txt`).