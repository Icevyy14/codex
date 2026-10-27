You asked for verification totals in the docs. They now say plainly that the software suite is not green: `4 failed, 255 passed, 1 skipped in 710.80s (0:11:50)`, from a full run I did after the last code change [Certain]. The CAD checks pass: `128/128 checks passed` in 5 min 11 s, the same output as `cad/out/checks.txt` [Certain]. An orchestrator commit (2a3eb57, 22:33) caught BOM.csv, BOM.md, SHOPPING_LIST.md and software/README.md partway through; my later edits are uncommitted in the working tree. I ran no git commands that change state.

**Changes per file** (all under )
- **docs/BOM.csv** (CRLF kept, 126 rows)
  - Sourcing links merged into every line that has one. The old search hint stays after the link when the link is [Likely] or [Guessing].
  - Prices are the ones the sourcing run saw on the product pages; estimates stay where it saw none.
  - Spec corrections applied:
    - Bed is now PureBond birch: the Baltic birch blank's link was dead.
    - Dowels are 5/16 in.
    - The 7 mm Class 2 laser needs the gate post hole drilled to 7.2 mm.
    - The VXB pump "upgrade" is probably the same pump as the main line, so it is now an unsourced branded pump.
    - Endstop boards are two 2-packs; the flag sheet is at least 50 × 60 mm.
    - Head lens is F2.8 or faster.
  - New carry-sensor lines: the board, flag, small screws, lead and printed parts cost $0 (they come from packs already bought). The only new purchase is M5×10 button heads ($6).
  - The jig now takes 6 M5 washers, not 12.
- **docs/BOM.md**: rewritten with the new totals, order plan, category table, changes, upgrades, tools (5/16 in bit, 7.2 mm drill) and the gaps still open.
- **docs/SHOPPING_LIST.md** (new): orders 1a, 1b and 2 with links and notes; qty-0 upgrades in their own table; totals; the 15% allowance note listing shipping costs already seen ($86.19); the jig's screws to take from school stock.
- **docs/BUILD_GUIDE.md**
  - Read-this-first table: dropped "foot hides the window" and the old screw-length row; added lens offset, card top, camera aim, carry-sensor trip and laser rows.
  - Costs in §0.2 and §1.1.
  - Phase 0:
    - card top 34.8–37.8 mm;
    - 4 mm jig walls with one washer per screw;
    - asymmetric bridge;
    - no "teach the ITF" step;
    - the face-up pass now expects GO and uses a Water-type card;
    - flipped window `[[-27.5, 11.0, 27.5, 22.5]]`;
    - new `real_eval --phase0` step and gate;
    - new record rows.
  - §2 order notes; §3.2 print table (751 cm³, about 42 h); §3.3 and §3.4; cut list.
  - Bed and dowel steps; §5.9 laser hole.
  - New §7.4a carry-height sensor: fit, set the trip, `selftest --motion`.
  - §7.6: M3×16 with washers, key clearances 1.63 / 2.0 mm.
  - §7.7: lens 5 mm toward the label, aim check and shim.
  - OMP note, config and window, §12.1a, §12.3 crop and window check.
  - §13.6 E (carry-sensor faults), §13.8 (FACE-UP stop, learned test), §14, troubleshooting.
- **docs/OPERATING.md**
  - Face-down now rests on back-label codes (PSA back QR, CGC back QR, CGC 2020–23 back barcode). New FACE-UP and neighbour stops.
  - Carry-sensor stops and what happens to a held slab after a stall.
  - OCR-only and grader-unknown slabs always go to pocket 12.
  - New `sources` and `face_down` values (`code`), new status notes, start-line strings, §8.4 two-reference rule, quick card.
- **docs/DESIGN.md**
  - Real label format table, interpretation rules and the face-down side table.
  - The carry-height sensor as a new crash-prevention layer.
  - Learned check: window, two references, limits.
  - Verification table: CAD, window, carry sensor, suite totals with the 4 failures, the 330-slab sim, `real_eval` with its caveats.
  - New risks.
- **docs/CONTRACT.md**: heights 248/248 with trip 246.5, 128 checks, lens offset, window in both coordinate frames, carry sensor, head crop 38.3, GPIO 6 on pin 31, CLI, `face_down` values, routing, budget.
- **docs/WIRING.md**: new §6a (circuit, polarity, failure table, a level check), W48 and W55, core 8 = carry sensor OUT, splice at the spine top, pre-power and first power-up checks, open risks.
- **docs/FIRMWARE.md**: open issue 5 now mentions the stall guard.
- **docs/RESEARCH.md**: new §4 "Real label formats (verified on public scans, Oct 2026)". It covers index counts and site names only, the formats, the side proofs, failure modes, card position and limits. PSA facts corrected: the ITF is always 8 digits, and current labels use Code128.
- **README.md**: budget, the face-down bullet rewritten, a Z-stall bullet, 128 checks, suite totals, a real-label check bullet with its limits, build-order costs.
- **software/README.md**: test count, `sim --mix/--eras`, carry sensor, `face_down`/`itf_*` values, sim results, `real_eval` and `bench_tests` in the tools table.

**BOM totals** (from BOM.csv) [Certain arithmetic; prices tagged per line]
- Subtotal $1,897.34, 15% allowance $284.60, **total $2,181.94**. It was $1,972.55, so +$209.39 including the allowance.

| | Parts | With 15% |
|---|---:|---:|
| Order 1a (Phase 0A) | $408.90 | $470.23 |
| Order 1a, borrowed Pi | | $280.66 |
| Order 1b (Phase 0B) | $144.79 | $166.51 |
| Order 2 (machine) | $1,343.65 | $1,545.20 |

- With school stock: $1,862.38. Lean (also generic valves): $1,786.60.
- Worst case about $2,365; with school stock about $2,039. All upgrades together: $920.36.
- Of the subtotal, $1,323.44 is a price seen on the product page, $287.90 is [Likely] and $286.00 is [Guessing].

**Fresh runs I did** [Certain]
- 330-slab sim with the default mix:
  - `needs_review 6, ok 324`
  - 287 by back QR, 41 learned (lowest 0.80), 2 confirmed by you
  - 14.2 s/slab, 79.4 min
- Phase 0 sim: GO at threshold 0.62 (lowest back-to-back 0.82, highest face-up 0.43).
- I did not re-run `real_eval`. The machine-scale numbers come from the fixer's final run; the native and glare numbers are older runs, labelled as such.

**Could not reconcile**
1. The 4 failing tests:
   - 3 in `test_carry_sensor.py` still expect the old heights.
   - `test_runner_sim.py::test_thick_holder_is_handled` is a real simulator crash (ProbeFailInitial during the survey).
   - The defaults in `config.py` are also still 236.5 and 235.0, while `machine.toml` has 248 and 246.5.
   - The software owner needs to fix these.
2. Open items from the verifiers, documented as risks but not fixed:
   - On CGC holders the card window can reach 0.5–1.5 mm past the card top [Likely]; there is no CAD check for it.
   - Camera aim between about 0.6° and 1.2° toward the cup puts a head part in the window and nothing in software catches it; the docs give a manual check and a shim instead.
   - A phantom read from a second frame of the same camera can count as confirmation.
   - Bare barcodes are assigned a grader by length only.
   - One web test is flaky.
   - The head LED ring is not in the CAD.
3. Decisions you may want to reverse:
   - **igus cable:** I did not adopt it for the moving cables. It is unshielded 4-core, so the head cable would need two runs and renumbered cores in WIRING.md.
   - **Z motor:** I did adopt the VXB 3-pack (+$70). It is the only listing that shows every spec; a single motor whose listing gives the same specs would save about $70.
4. Six lines in the total still have only a search hint, no product link: the 40 mm COB head ring, the branch fuses, the drag chain, the M5×10 button heads and the two moving cables. The Misumi prices were never checked on a live page.
5. **WIRING §6a level check:** I added a check that GPIO 6 reads at least 2.5 V high, plus advice to add a 2.2 kΩ pull-up at the board if not. That is my inference [Likely], not from the reports, and untested.

Scratch scripts and run logs are in scratch/docs3/:
- suite_run.txt
- checks_run.txt
- sim330.txt
- p0sim.txt
- bom_update.py
- shop_gen.py