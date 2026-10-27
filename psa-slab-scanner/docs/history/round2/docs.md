The docs now match this round, with two things that matter more than the wording. The learned face-down check still can't work on the current CAD head. And the BOM total went up $69 because I added the cup spares, not optional upgrades.

**Checks I ran today**
- [Certain] I re-ran `cad/checks.py`: 106/106 passed, exit 0, and the output is byte-identical to `cad/out/checks.txt`.
- [Certain] Full software suite: `189 passed in 709.29s`. This includes the fixer's uncommitted 0.55 threshold floor in `config.py`.
- [Certain] 330-slab sim, seed 7: 330/330 ok, 70 s survey, 14.0 s per slab, 78.2 min.
- [Certain] I ray-cast the current head (after the CAD fixer's changes) from the lens at hover to the card window: 0 of 75 points are visible. `head_foot` blocks all of them; the flag and elbow also block some. That backs every "the learned check never becomes active" line in the docs.
- [Certain] An M3×16 board screw tip clears every head part by at least 21.5 mm.
- [Certain] Two product pages loaded today: the M-5ALU-4 elbow is $2.09 in stock, and the sibling cup ZPT25UFK20-N6-A10 is $37.10. automationdistribution has no ZPT25UUK20-B5-A10 page (404). The SMC USA configurator page does exist.

**New BOM totals** (BOM.csv still CRLF, 121 lines, every qty × unit matches its total)

| | Before | Now |
|---|---:|---:|
| Subtotal | $1,655.08 | $1,715.26 |
| 15% allowance | $248.26 | $257.29 |
| Grand total | $1,903.34 | $1,972.55 |
| With school stock | ≈ $1,634 | ≈ $1,703 |
| Lean | ≈ $1,547 | ≈ $1,616 |
| Order 1a (Phase 0A) | ≈ $449 ($285 with a borrowed Pi) | ≈ $457 ($293) |
| Order 1b (Phase 0B) | ≈ $145 | ≈ $198 |
| Order 2 (machine) | ≈ $1,309 | ≈ $1,317 |
| Worst case | ≈ $2,170 | ≈ $2,235 |

- Of the subtotal, $1,089 is [Likely] and $626 is [Guessing].
- If every conditional upgrade triggered at once, the total would be about $3,050.

**What changed per file**
- **BOM.csv**
  - Cup code is now K20 (`ZPT25UUK20-B5-A10`, 20 mm stroke) with the SMC catalog dimensions; the rotating J20 is noted as acceptable.
  - Added: a second SMC cup ($42, replacing the generic $14 backup, which can't match the flag geometry), 2 × M-5ALU-4 elbows ($4.18), a spare MGN12H block ($10), and the 66 mm jig arm stub ($4).
  - The flag stock is now a 25 × 56 mm sheet of soft aluminium, not a strip.
  - Note changes: M3×16 for the probe board, washers on the jig's M5×10 screws, and the HT1 cup needs an adapter.
  - Six qty-0 upgrade lines, each tied to a test: HIWIN rail, Z motor, counterweight, flex USB cable, VXB pump, branded E-stop.
- **BOM.md:** bottom line, order plan, category table, the round-2 change list, an upgrades table, a "not bought" list, tools (2.5 mm ball-end key, needle files), filament (723 cm³ in 23 prints), and the design-gap list. Gaps 5, 6 and 8 are marked resolved; new gaps 9 (card window hidden) and 10 (screw lengths); sources added.
- **BUILD_GUIDE.md**
  - Read this first: removed the flag and occluder gaps, rewrote the buffer gap, and added rows for the bought-part dimensions, the screw lengths and the card window.
  - §0.1 and §0.2: costs and times updated.
  - §1: occluder mount assembly and the 62.0 mm foot height; the face-up pass (mount slid up 3 mm, 15 slabs including a plain and a full-art card); `window_check.jpg`; what GO and HOLD mean.
  - §2, §3.2 (head_foot 1.9 h, occluder mount 0.8 h, total ≈ 40 h), §3.3 (measure-on-arrival table), §4.1.
  - §7.5: lens 142 mm above the free cup face. §7.6 rewritten.
  - §7.8 and §8: the free fixes to try before buying a Z upgrade, and the elbow plumbing.
  - §11.5, §12.3.
  - New §13.8 face-down test: a face-up junk slab must stop; after a head change, an old label must pass as learned. The summary moved to §13.9.
  - §14 and §15 updated.
- **OPERATING.md:** Read-this-first, loading rules, the start-log line, the survey's empty-pocket frame, the `face_down` column, the summary line, 13 new stop rows, a new §8.4 (modes, when it activates, where references come from, `refs`, how to audit, limits), and the quick card.
- **DESIGN.md:** buffer forces updated to the catalog values [Likely]; crash-prevention item 7; a learned-check subsection (descriptor, 8 safety layers, limits); the verification table (106 checks, 189 tests, probe and Phase 0 checks, sim numbers); risks.
- **CONTRACT.md:** probe and buffer lines, binding CAD decisions (check total, lens height, probe, Phase 0 occluder, open card-window item), CLI list, outputs, the face-down paragraph, budget.
- **README.md:** the "older labels stop the run" bullet (49 of 330 with today's head; 1 of 330 in the sim with a clear head, [Guessing] for real card backs), costs, 106 checks, 189 tests.
- **WIRING.md, FIRMWARE.md, software/README.md:** 20 mm stroke and tube slack, flag description, Z free fixes, sim and phase0 flags, output files, test time, new sim timing.

**What I could not reconcile**
- **Card window:** no frustum check exists in `checks.py`, and the CAD fixer didn't change `head_foot`. Every doc says the learned check is inactive with today's head.
- **Simulator head model:** `sim.HEADS["cad"]` and `simworld.BUFFER_STROKE = 25` are still the old buffer. That code isn't mine. The 49-of-330 and 0-references results come from that stale model; my ray cast agrees with them.
- **Screw lengths:** the CAD still models M3×12 board screws and the 1.8–2.0 mm jig walls. I worked around both in the docs (washers, M3×16) and tagged them [Likely]; the CAD wasn't changed.
- **Jig screws:** the jig's post-socket wall thickness is unverified. The docs say to test one screw first.
- **Face-up prompt:** `tools/phase0.py` says "Nothing touches them here" during the face-up pass. That is only true after the 3 mm mount lift, which the docs require.
- **SMC code:** the exact code is [Likely] orderable. Its stroke is [Certain] from the catalog, but I found no listing for this exact code.
- **E-stop upgrade:** I couldn't confirm that ZBE102 blocks fit a generic 22 mm box, so that line is [Guessing].
- **Not re-run by me:** the 1-of-330 open-head figure and the Phase 0 separation numbers come from the face-down reports.

My scratch scripts and run logs are in `scratch/docs/`. The orchestrator's snapshot `8d4e9d9` already committed part of this work (BOM.csv, BOM.md, part of BUILD_GUIDE); my later edits are uncommitted. I ran no git commands that change state.