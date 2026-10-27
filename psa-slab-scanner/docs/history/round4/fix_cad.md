The issue is real, but slightly smaller than reported, and the bigger exposure is camera aim, not parallax. Measured exactly on the card plane, a CGC slab pushed into a pocket corner has 1.52% of the window on the holder (4.48% if the 3.5 mm above the card were all air). The verifier's raster gave 1.7% / 4.6%. The top edge sits 0.03 mm off the card and the side 0.23 mm. The window corner is 1.31 mm outside the card's rounded corner.

The window can't shrink and the CGC worst case can't be brought back to 0%, so I made the checks report the real worst case against a 2% limit. That limit is a judgment I set after the finding; it is not a margin.

**Final checks run:** from `cad/`, `timeout 3000 python3 checks.py`, 357 s, saved to `cad/out/checks.txt`:
```
layout checks: OK
152/152 checks passed
exit=0
```
The working tree was at 154/154 before my change, not the 128/128 of b4b2972. Four old pass/fail records (top edge and side edge, per grader) became two "share on the holder" records. No solids changed, so nothing was re-exported. I re-rendered `docs/img/face_down_view.png` only, which now shows a 63 x 88 card with rounded corners. The software reads none of the changed values. The software fixer has already synced the window in `machine.toml` to `[[-27.5, -18.5, 27.5, -13.0]]`, which matches the CAD.

**What changed in cad/**
- **Card model** [Certain on the size, Likely on the rest] (`layout.py`):
  - The card is now 63.0 x 88 with 2.7 mm corners. The realslabs set is mostly Pokemon cards: 70 Pokemon backs, 9 sports, 1 MTG, no Yu-Gi-Oh.
  - The card back is taken as 3.5 mm under the slab back, refracted through plastic with n 1.49. That is acrylic, the most parallax of the usual clear plastics.
  - I added `card_x_shift()` and fixed a stale comment: CGC play is 2.55 mm, not 2.8.
- **Window check** (`checks.py`):
  - It now maps the window's outline onto the card plane with exact refraction and clips it against the card's rounded outline. I checked the clipping against hand cases and a fine raster.
  - The CGC record reads: 1.52% (limit 2.0); top -0.03, side -0.23, worst point -1.31 mm; all air 4.5%, -1.57 mm. PSA reads 0.0%, with side +0.22 and top +3.39 mm.
- **Aim check:**
  - Median card, centred slab: 1.32 deg (was 1.59), for both graders.
  - Pocket-corner PSA slab: 0.49 deg before more than 2% of the window is on the holder.
  - Pocket-corner CGC slab: 0.01 deg toward the label (was 0.10). That case has essentially no aim margin.

**Why 2% and not 5%** [Likely, real-image emulation]
- **Front-vs-back scores:** I compared each face-up front against the code-proven backs directly, with every slab at the cup end of its play, so the result doesn't depend on how references are grouped. The highest CGC front score rises with holder in the window: 0.473 (card in the back plane), 0.505 (plastic model), 0.543 (all air), against the 0.55 floor. PSA fronts stay at 0.500-0.509. A 5% limit would sit almost at the floor.
- **Full learned check is too noisy here:** the full learned-check A/B can't resolve an effect this small.
  - A 0.5% image shrink alone, with no extra holder, moved face-down accepts from 101 to 89 of 126 and cut references from 34 to 27.
  - Every face-up false accept in the variants, up to 8 of 206 at 0.55, was one PSA front (psa-24023133). PSA has no holder in its window in any variant.
  - Back-to-back raw scores stayed flat across scales, so the swings come from reference grouping (cluster 0.58, at most 6 prototypes), not from the pixels.

**Open items for others**
1. **Docs** (not mine to edit):
   - `DESIGN.md` lines 259-262 still describe the round-3 window (632.5 mm², y -22.5 to -11.0).
   - `BUILD_GUIDE.md` line 42 and `OPERATING.md` line 89 still give the old CGC wording.
   - Suggested text: "About zero margin. A CGC slab pushed into a pocket corner can have about 1.5% of the window on the holder (up to about 4.5% at most). PSA slabs stay on the card."
2. **Software:** the aim guard (`facedown.aim_problem`) only checks the cup side of the window [Certain, code]. A tilt toward the label is what moves the window off a corner-pushed CGC card, and the CAD allows 0.01 deg there.
3. **Software:** the learned-check result swings with reference grouping, as shown by the 0.5% shrink control above. That is worth a look on its own.
4. **Scope:** a 59 mm Yu-Gi-Oh card in a pocket corner would put 3.2% (PSA) or 5.1% (CGC) of the window on the holder [Likely; its card-top position is unmeasured]. It is outside the measured card set.
5. **Cheapest way to gain margin, not taken:** moving y1 to about -17.8 adds about 12 mm² but cuts the head-aim margin from 1.34 to 1.25 deg. It needs a window change in CAD and config.

Files changed:
- cad/layout.py
- cad/checks.py
- cad/render_docs.py
- cad/out/checks.txt
- docs/img/face_down_view.png

Evidence, in scratch/round4/cadfix/:
- parallax_ab.py and parallax_ab.txt (learned-check A/B)
- control_ab.py and control_ab.txt (the shrink and enlarge controls)
- front_diag.py and front_diag.txt (front-vs-back scores)
- scale_diag.py (back-to-back scores; its output was not saved)
- checks_final2.txt (final run)
- face_down_view_before.png (the render before my change)