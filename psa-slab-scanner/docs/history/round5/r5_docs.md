The docs now say a pre-2016 PSA slab can be `ok`, but two code issues behind that rule are still open, and I could only write them up as risks. [Certain] OCR is matched against the ITF after leading zeros are stripped, so an OCR read of `0019865140` confirms an ITF of `19865140`. And when OCR finds two equally long numbers, which one it keeps depends on the hash seed, so the same slab can come out `ok` in one run and `needs_review` in the next. The switch strikers' sideways load on the lever has also never been tested. The docs now ask for a 100-pass bench test before the build.

I ran no tests and no CAD checks. All totals below are copied verbatim from the fixers' logs, and every value was checked against the code, `checks.txt`, `print_list.json` or `model.py`. No git commands, no processes killed, no code edited.

**Totals used in the docs**
- Software, full suite on the final code: `299 passed, 1 skipped in 1135.84s (0:18:55)`.
- Real-image test, run on its own: `1 passed, 61 deselected in 137.29s (0:02:17)`.
- Round-5 full suite with the real-image test, on the code just before the last fix: `300 passed in 1202.90s (0:20:02)`.
- CAD: `177/177 checks passed`, `exit=0`.
- real_eval at machine scale: `TOTAL 61 60/0/0/1/0`, 0 wrong, 0 false proofs.
- real_eval native (round-5 code): `TOTAL 64 60/2/0/2/0`.
- 330-slab sim: `needs_review 6, ok 324`, lowest learned score 0.76.
- Phase 0 sim: 0.81 / 0.57 / threshold 0.69.
- BOM totals are unchanged at $1,897.34 parts and $2,181.94 with the allowance. No line's quantity or price changed, which I asserted when writing the CSV.

**Changes per file** (all under ``)
- **`docs/BUILD_GUIDE.md`**
  - Read-this-first: rows for the switch mounts and lever length, the 39.5–42.5 mm ring range, and the jig needing a board-to-lens length of at least 10 mm. Printer time is now about 45 h; the Phase 0 jig takes about 17 h and the machine parts about 28 h.
  - §1.5: standoff = L − 10.0, 2.0 mm of plastic, the ring goes between the ribs. §1.7: phase0 refuses an existing folder unless `--force` is given. §1.8 and §11.5: `psa_cert_digits` must include 7 (example `[7, 8, 9]`), and `custom_regex` turns the ITF rule off.
  - §2 adds an ordering row for the homing switches and a 6 × M5×10 button-head note.
  - §3.2 print table: new and changed rows, total 801 cm³ in 27 prints, about 44.5 h, plus a note on the overhang under the `z_switch_mount` shelf.
  - §3.3 has the new ring row and a switch row; §3.4 adds the switch and ring test fits; §4.1 drops the dowel caveat.
  - §4.3: the joining plate's beam leg goes on the upper rear slot at the left end. §4.4: 130 T-nuts. §7.1: two T-nuts in the spine's right side face.
  - §6.8 and §7.4 are rewritten:
    - measure the lever and cut anything over 23 mm back to 20 mm;
    - a 100-pass bench test on one switch;
    - set the click, then move the switch about 0.3 mm more at the body. I used 0.3, not the CAD report's 0.6, because the lever ratio is 1.87, which I confirmed from the `model.py` constants;
    - set X with a 4 ± 2 mm gap at the bumper, and Z at c = 258 ± 2;
    - lead routes and the home_switches image.
  - §7.7 covers ring ribs and the resume aim check. §12.2 drops the "pocket centre mark" aside.
  - §13.1, §14 and §15: pre-2016 PSA can be `ok`, plus a new row for a non-PSA slab coming out `ok PSA`. Sources now cite 177/177 and the Omron datasheet.
- **`docs/WIRING.md`**
  - §7: switch type, both mount positions and strikers, the W52 and Z lead routes, and the joining-plate caveat.
  - §9: the 42.8 mm ribbed seat. §11: a W52 entry note. §16: switch mounts marked resolved.
- **`docs/OPERATING.md`**
  - The ITF rule is in read-this-first, §4 and the quick card.
  - Routing notes: an `ok PSA` from another grader is possible, and codes in no grader's format are not read.
  - §5.2: new `ok` and `needs_review` notes, a paragraph on what `needs_review` means, the `psa_cert_digits` and `custom_regex` caveats, and the ITF assumption with the Phase 0 advice.
  - §5.3: the new `camera_aim` value.
  - §8: the "empty pocket 12 before you resume" tip, and a new stop row for "aim is not checked this run yet".
  - §8.3: new patterns. §8.4: condition 3, and the mid-run `face_down_baseline` note.
- **`docs/DESIGN.md`**
  - Code128 narrowings and a grader rule table. The aim-on-resume text describes only the no-empty-pocket case as new.
  - Verification rows: 177 checks, the switch and ring checks, test totals, the sim and real-label numbers.
  - Risks: the narrowings row is updated, the CGC window row now gives the round-5 trade-off, and new rows cover the ITF premise, the stripped-zeros match, the OCR tie, lever length and side load, and the bore size.
- **`docs/CONTRACT.md`**: 177 checks, ring seat, switch mounts, phase0 `--force`, the grader rule, the stale-aim condition, `camera_aim` values.
- **`docs/RESEARCH.md`**: the simulator now uses per-grader holders; old labels print the cert zero-padded; ITF is seen only on PSA, with the BGS/SGC caveat; the left-out PSA back `fc_18805593` at 96.29 mm.
- **`docs/BOM.csv`** (CRLF kept, 128 lines)
  - 2020 corner brackets: no longer used for the switches. M5 T-nuts: about 130. M5×10 button head: 6 needed, item renamed.
  - M2 kit: plus 4 × M2×12 and 4 nuts. Standoffs: L − 10.0. Head ring: 39.5–42.5 mm.
  - Homing switches: short hinge lever, cut-back rule, mount small parts. Filament: 801 cm³.
- **`docs/BOM.md`**: new "what changed" for this round, order-2 text, 130 T-nuts, filament, tools rows. Gap 7 is closed and replaced by the unknown lever on the 10-pack.
- **`docs/SHOPPING_LIST.md`**: head ring fallback, order-2 intro, the button-head and homing-switch lines, open problems.
- **`README.md`**: the pre-2016 bullet, 177 checks at about 12–15 min, ring range, switch bullet, what is not checked, test totals, real-label 60/64 and 60/61.
- **`software/README.md`**: about 16–21 min for the suite, the `custom_regex` and `psa_cert_digits` caveats, the ITF premise and the Phase 0 advice.

**Could not reconcile**
- **The two code issues above, plus one more** (all three are documented as risks, none fixed): the stripped-zeros match and the OCR tie in DESIGN, and `_take_baseline` with no descriptor leaving the "not checked this run" wording (not documented).
- **Not re-run on the final code** [Likely unchanged]: the native real_eval and both sims are round-5 runs. The last fix only touches reads the real set and the simulator do not produce.
- **CAD time** [Guessing]: no runtime was reported for 177 checks. The docs say 12–15 min, from 173 checks taking 723 s and the verifier's 15 min.
- **CAD-owner items, handled in the docs only:**
  - [Certain] The `checks.py` docstring still says the leads are clear of where BUILD_GUIDE 4.3 puts the plates.
  - [Likely] The `z_switch_mount` print orientation leaves an overhang.
  - [Likely] The 42.8 mm bore is tight for a 42.5 mm ring.
  - [Guessing] The lever's side load is untested.
  - [Certain] `printed_sheet.scad` is stale.
  - [Certain] The verifier's Z up-travel limit (2.58 mm) is now 3.58 mm after the lever fix.
- **Purchases** [Guessing]: which lever the B07YQQ3R7W pack has is unknown. The W52 length of 1.3 m was not rechecked for the new route.
- **Policy point left open:** an ITF plus OCR plus a bare-number code still gives `ok PSA`.
- **Source links:** the Omron datasheet is cited by file name only (`en-ss.pdf`), because I could not confirm its URL. `docs/FIRMWARE.md` needed no change.

Backup of the original CSV: `scratch/BOM.csv.before_round5`