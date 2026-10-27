The bigger problem is outside software/: the top-level docs never got the round-5 ITF rule at all. They still say every pre-2016 PSA slab is `needs_review`, but the code makes it `ok PSA` when OCR agrees. The issue's request to drop "or a second printed code" from OPERATING, DESIGN and CONTRACT does nothing, because that wording isn't in them. I don't own those files, so this needs the docs fixer.

**The issue is real and fixed.**
- [Certain] I reproduced it with probe_consensus.py. Before the fix, an ITF-8 plus a bare-digit QR, DataMatrix, EAN-8, Codabar or keyed 'Cert #' QR gave `ok PSA`. After the fix all five give `needs_review PSA "grader PSA not confirmed ..."`. ITF-8 plus OCR still gives `ok PSA`.
- [Certain] The branch could only ever fire on grader-`unknown` reads. Every PSA parse kind returns grader PSA, so any PSA-format second symbol already makes `two_symbols` true. I deleted the branch rather than restricting it to PSA kinds, because the restricted version would be dead code.
- [Certain] It had no effect on the real set. Round 5's machine-scale run decoded 374 payloads and none had grader `unknown`.

**Changes (all in software/):**
- `slabscan/certs.py`: `psa_itf_confirmed` is now `bool(itf) and any(r.source == "ocr" and r.cert == cert for r in reads)`. The module docstring, the `psa_itf_confirmed` and `consensus` docstrings and the `by_itf` comment no longer mention a second printed symbol. They now say a code in no grader's format never confirms a grader.
- `tests/test_certs.py`:
  - The test is renamed to `test_an_8_digit_itf_names_psa_only_once_ocr_confirms_its_digits`.
  - The loop now covers a bare QR, Code39, EAN-8, Codabar, a keyed 'Cert #' QR and a DataMatrix. Each must be `needs_review` without OCR and `ok PSA` with OCR.
  - The test that tries every combination of reads now requires OCR for the ITF rule.
  - [Certain] With the old branch patched back in, both changed tests fail, so they hold the fix in place. The mutation script is `scratch/round5/verify_sw/mutant_old_branch.py`.
- `README.md`: "(or a second printed code)" is removed, and one sentence now says a bare-number code never confirms a grader, even beside an ITF.
- [Certain] The CAD window has not changed: `cad/layout.py` matches HEAD and `python3 -m tools.gen_config --check` printed `up to date`. So I did not regenerate config/machine.toml or retune any tests.

**Results (verbatim):**

| Run | Result |
|---|---|
| Full suite (`SLABRAIL_REAL_IMAGES` unset) | `299 passed, 1 skipped in 1135.84s (0:18:55)`, exit 0 |
| Real-image test | `1 passed, 61 deselected in 137.29s (0:02:17)`, EXIT 0 |
| `real_eval --machine` | `REAL-LABEL CHECK (machine, front OCR on): 128 images (9 skipped), 61 slabs (+3 with no usable image), 312 s`; `TOTAL 61 60/0/0/1/0`; `WRONG CERT in an 'ok' verdict: 0`; `FALSE FACE-DOWN proofs (a face-up slab 'proven' face-down): 0`; `front OCR on 11 slabs`; EXIT 0 |
| `tests/test_certs.py` + `tests/test_real_payloads.py` on the final files | `86 passed, 1 skipped in 0.25s` |

- [Certain] 299 is not 288 because the working tree carries round 5's uncommitted tests; round 5 also got 299/1. I renamed one test and added none.
- [Certain] All 61 slabs match round 5's verdicts exactly: same status, cert, grader and note. The 7 pre-2016 PSA slabs still carry "grader PSA from its 8-digit ITF".
- A few docstring rewraps landed after the full suite had loaded certs.py. They don't change behaviour, which is why I re-ran the two cert test files on the final files.

**Stale docs for the docs fixer [Certain]:** these still describe the round-4 rule.
- `README.md:51`
- `docs/OPERATING.md` lines 43, 259, 487 and 629
- `docs/CONTRACT.md:191`
- `docs/DESIGN.md:208-211`, and the sim row at line 388 ("20 pre-2016 PSA slabs ... grader not confirmed")

**Open policy point [Guessing]:** an ITF plus OCR plus a bare-number code is still `ok PSA`. The extra code counts for nothing either way, which is how the rest of `consensus` treats such codes. If the bare-number code should count as evidence the slab isn't PSA, that is a separate rule I did not add.

I ran no git commands that change state and stopped no processes. Logs are in `scratch/round6/sw/`: `suite_full.txt`, `real_test.txt`, `real_machine.txt` and `real_machine.json`.

=====

The issue was half right, and its optional CAD fix would not have worked. A 25-28 mm lever does fail on the Z switch, but not for the reason given. Starting the chamfer at X 20 alone would still have jammed it. The X switch claim is wrong for anything up to 27 mm.

**What I measured** (scratch sweep, then the new checks)
- **X switch** [Certain, CAD]: nothing moving comes near "Y 84". The nearest parts are the carry flag at Y 75.5-76.5 and its screw heads at Y 76.5-79.5. Clearance is 3.14 mm for a 25 mm lever and 0.27 mm for a 28 mm lever. The longest lever with 1 mm clear is **27.24 mm**; the flag screw at cup X 30, c 78 limits it. The finger only presses the lever up to u = 20, so a longer lever does not change the trip point.
- **Z switch** [Certain, CAD]: two limits, not one.
  - The lever tip must sit over the chamfer. With the chamfer starting at X 30, that allowed a lever ending at u = 22.
  - The free tip must not stand deeper than the chamfer, allowing for the switch's 1 mm adjustment toward the plate. A 25 mm lever stands 6.74 mm into the plate's path, deeper than the 6.5 mm chamfer. That depth limit allowed only about 20.9 mm. Past it, the plate's square top strip hits the lever edge-on.
- **Gap in the old checks** [Certain]: the Z striker model treated the square top as if it could press the lever. A long lever would therefore have passed every existing check.

**What I changed** (cad/ only, nothing committed)
- **`cad/model.py`**:
  - `sw_lever()` and `sw_lever_angle()` take an `end` (lever length).
  - New `SW_LEVER_MAX = 23.0`: the longest lever fitted without cutting.
  - The z_plate chamfer now runs from X 20 and is 7.5 mm deep (`ZP_CHAMFER_X, ZP_CHAMFER = 20.0, 7.5`), leaving 0.5 mm of the 8 mm top.
  - `ZS_Z` follows the new depth, so the Z switch and its mount sit 1 mm lower (605.6). The trip stays at c = 258.
- **`cad/checks.py`**: four new checks.
  - The longest lever each switch takes: X 27.24 and Z 24.19, both against a limit of 23.
  - A 23 mm lever against the moving head: 15.49 mm clear.
  - A 23 mm lever against the parts fixed to the X carriage: 1.91 mm clear.
  - On the old geometry the Z check would have failed (20.9 < 23).
- **Re-exported and re-rendered**: `cad/out/printed/*`, `cad/out/assembly/*`, `cad/out/checks.txt`, and every image in `docs/img/` (including `home_switches.png` and `printed_parts.png`).
  - z_plate volume went from 41.3 to 40.9 cm3, and z_switch_mount is 1 mm shorter (27.4 to 26.4 mm, 5.0 to 4.9 cm3).
  - `heads_cad.json` and `cut_list.csv` did not change.
  - The other switch values are unchanged: trips at 19.00 and 258.00, 0.6 mm past the operating point at the hard stop, top hard stop gap 0.0.
  - The head's clearance to the Z mount is still 1.49 mm; I checked it at the old height too.

**Totals** (full `python3 checks.py`): `177/177 checks passed`, `exit=0`. That is 173 before my four new checks.

**Software** [Certain]: X_HOME_SWITCH, Z_SWITCH_C and the CAD window did not change, so there is no gen_config run and no test retune.

**For the docs owner** (BOM and BUILD_GUIDE are not mine to edit):
- **BOM "Homing switches"**: name a bare SPDT hinge-lever microswitch with a 20 x 10 x 6.4 mm body (Omron SS-5GL or equal). The lever must end within 23 mm of the hinge end, or be cut back. The CAD only models a flat hinge lever, not a roller lever [Certain]. [Guessing] which lever B07YQQ3R7W has; I did not look it up again.
- **Build step before fitting each switch**: "Measure the lever from the hinge end of the switch body to the lever tip. Up to 23 mm: fit it as it is. Longer: cut it flush with the far end of the body, 20 mm from the hinge end. Use side cutters, then file the cut smooth."
- **Stale text**: BUILD_GUIDE §6.8 and §7.4 still say "The CAD has no mount for it". The CAD now has `x_switch_mount` and `z_switch_mount`.

The repro script is at `scratch/lever/repro.py`.