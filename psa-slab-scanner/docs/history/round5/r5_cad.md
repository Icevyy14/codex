**Item 5 is not doable.** The CGC window can't get a +0.5 mm margin without breaking the head-camera aim check, so I left the window unchanged. The software needs nothing regenerated. [Certain] The other four items are done, and the full checks pass: `173/173 checks passed`, `exit=0`, 723 s. [Certain]

**Before you act on this:**
- **The switch overtravel is 1.2 mm, not "about 2 mm".** The Omron SS-5GL datasheet gives OT min 1.2 mm and OP 8.8 ± 0.8 mm. The hard stops are 4 mm past each trip. So no mount that hits the lever head-on can meet your requirement. I used a striker that slides across the lever instead. [Certain, Omron en-ss.pdf]
- **The switch mounts assume the short hinge lever**, the kind that ends at the body's end (Omron SS-5GL). I couldn't open the BOM listing (B07YQQ3R7W) to check which lever it has. A long or roller lever must be trimmed to about 20 mm from the pivot end. Otherwise its tip reaches the carry-flag sweep (X) or the untouched part of the z_plate top (Z). [Guessing on the BOM part]
- **The Phase 0 jig now needs a camera board-to-lens length of at least 10.0 mm (was 7.4).** A 2 mm web and a 42.5 mm ring can't both fit in the 8 mm bar. I replaced the old "8 mm camera" check with "shortest length ≤ 12". This is a check change, not only a geometry change. [Certain]
- **`checks.py` now takes about 12 min (was about 6).** The extra time is the switch sweeps and running the ring checks three times. [Certain]

**1. Limit-switch mounts** [Certain, CAD and checks unless tagged]
- **How they work:** each striker has a 45° lead-in that slides across the lever, then a flat. The flat holds the lever 0.6 mm past OP all the way to the hard stop, so the lever never bottoms.
- **X home switch:**
  - New printed `x_switch_mount` sits under the beam's left end.
  - It takes 2 × M5x10 button heads into T-nuts in the beam's lower front slot, at X −48.5 and −37, left of `x_bumper_L`.
  - The switch hangs on 2 × M2x12 through ±1 mm vertical slots. Lever up, pivot end toward the back.
  - A new 17.4 mm finger on `x_bracket`'s left edge (Z 369.5–378.5) presses it.
  - Trips at cup X 19.00 and holds 0.6 mm past OP from 18.68 to 15. The lever is free above cup X 23.9.
  - Everything sits behind Y 84. The carry flag and its arm sweep the area in front of that. An earlier layout collided with the flag, and the checks caught it.
- **Z top switch:**
  - New printed `z_switch_mount` goes on the Z spine's right (+X) face, with 2 × M5x10 button heads into that face's slot.
  - The switch lies on a 3 mm shelf, on 2 × M2x12 through ±1 mm slots. Nuts go on top.
  - The `z_plate` gained a 6.5 mm 45° chamfer along its top back edge, X +30 to +40 from the cup axis.
  - Trips at c = 258.00 and holds 0.6 mm past OP from 258.32 to 262. The lever is free below c 253.1.
- **Hole spacing:** the datasheet gives 9.5 ± 0.1 mm with 2.35 mm holes. [Certain, Omron SS-5GL] The generic 10-pack matching it is [Likely].
- **Adjustment:** each mount slides about ±3 mm in its slot. The M2 slots (±1 mm) cover OP ± 0.8.
- **New checks** cover:
  - the trip point and the travel past OP up to each hard stop;
  - that the lever is free in normal travel;
  - nothing but the striker near the switch, mount or screws (cup X 15–55 and full Z for the X switch, full Z for the Z switch);
  - the finger clear over the whole X travel;
  - a path for each lead.
- **Lead paths:**
  - X: down to Z 330 (below the corner brackets), back under the beam, then up into the beam's rear lower slot.
  - Z: back past the spine, then up behind the `z_motor_mount` to the spine top.
  - The corner brackets themselves are not modelled. [Guessing on their extent]
- **New image:** `docs/img/home_switches.png`.

**2. LED ring seats** [Certain]
- **Head seat:** 42.8 mm bore with 3 centring ribs printed to fit a 40.0 mm ring, plus a 33 mm lip.
  - It takes rings from 39.5 to 42.5 mm.
  - For a bigger ring, shave each rib by half of (OD − 40). A ring under 40 sits up to 0.25 mm loose: centre it and glue.
  - All head ring checks now run at 39.5, 40 and 42.5 mm (views, glare, arm, camera, moving buffer parts) and pass. The glare share is 0.0.
- **Station seat:** already takes 60–63 mm (64 mm bore). No change.

**3. `phase0_top`:** the bar is now 10.6 mm thick (was 8), with 4 mm deep M2 holes. The web is now 2.03 mm (was 1.23). The ring and lens positions are unchanged; all Phase 0 checks pass, with the jig-vs-machine ring offset at 0.0. [Certain]

**4. Cut list and comment:** `cut_list.csv` now says "5/16 in (7.94 mm) hardwood dowel". The `model.py` comment now says "two 2-packs". [Certain]

**5. CGC window trade-off** [Certain, checks functions]
- Edge margins of +0.5 with one rectangle leave 266 mm², under the software's 300 mm².
- The best 3-rectangle window gets a +0.53 worst point at 300.0 mm². But it moves y1 to −17.05, which cuts the head-aim margin to 0.97° (floor 1.25°).
- Window kept at [[-27.5, -23.5, 27.5, -18.0]]. `heads_cad.json` is byte-identical, `layout.py` is unchanged, and the software only imports `layout`.

**Exports and renders**
- `layout.py`: OK.
- Printed parts: 27 prints, 801 cm³ (was 25 prints, 768 cm³).
- Changed STLs: `x_bracket`, `z_plate`, `camera_bracket`, `phase0_top`.
- New STLs: `x_switch_mount`, `z_switch_mount`.
- Unchanged parts' STEP files and the flag DXF differ only in timestamps.
- The cut list and `slabrail_home.step` were re-exported. `cad/out/checks.txt` was updated. All `docs/img` renders were redone.

**Doc changes needed** (I edited no docs)
- **BUILD_GUIDE read-this-first table, line 47:** the switches now have printed mounts.
- **§1.5:** standoff = L − 10.0 (10.0 mm for L = 20). The bridge is 10.6 mm thick. Drop the 1.2 mm caution; there is now 2.0 mm of plastic. The ring presses between ribs (shave the ribs if needed).
- **§3.2 print table:**
  - New rows: `x_switch_mount` (6.8 cm³, front plate down, 0.4 h) and `z_switch_mount` (5.0 cm³, spine plate down, 0.3 h).
  - Reprint `x_bracket` (70.7 cm³), `z_plate` (41.3 cm³, chamfer starts at the bed at 45°), `camera_bracket` (17.3 cm³) and `phase0_top` (75.7 cm³, 4.2 h).
  - Total: 801 cm³ in 27 prints, about 44.5 h (about 27.8 h after the Phase 0 prints).
- **§3.3 head ring row:** 42.8 mm bore, ribs, OD 39.5–42.5, ID up to OD − 3.
- **§3.4 test-fit list:** add each switch on its M2x12s, and the ring in the ribbed seat.
- **§4.1:** delete the "still says 8 mm" note.
- **§6.8:** replace the corner-bracket method:
  1. Put 2 T-nuts in the lower front slot and fit the mount.
  2. Carriage on the left bumper: slide the switch up in its slots until it clicks, then 0.6 mm more. At the bumper the lever should still give a little.
  3. Slide the mount until the click is at cup X 19 ± 2.
  4. Route the lead as above. Add `home_switches.png`.
- **§7.1:** drop 2 T-nuts into the spine's right slot as well.
- **§7.4:** the same steps for the Z switch: at the top stop, click + 0.6 mm, then c = 258 ± 2.
- **WIRING §7:** update both switch positions and strikers and the W52 route. **WIRING §9, line 573:** the ring seat is now 42.8 mm with ribs.
- **BOM.csv and SHOPPING_LIST:**
  - "Homing switches": mounts are now printed, and say to buy the short hinge lever.
  - 2020 corner brackets: drop the switch use.
  - M5x10 button heads: 6 needed (was 2).
  - M5 T-nuts: +4.
  - M2 kit: +4 × M2x12 and 4 nuts.
  - M2 standoff line: "− 10.0 mm", 2.0 mm of plastic.
  - Head ring line: 42.8 mm bore with ribs, takes 39.5–42.5 mm.
- **BOM.md:** lines 359, 374 and 393; close open gap 7.
- **CONTRACT, DESIGN, README:** 152 → 173 checks and about 12 min. Update the ring seat and switch-mount text in CONTRACT lines 97 and 103.

Files are in ``:
- `cad/model.py`
- `cad/checks.py`
- `cad/build.py`
- `cad/render_docs.py`
- `cad/out/checks.txt`
- `cad/out/printed/`
- `docs/img/home_switches.png`

The window analysis scripts are in `scratch/sw/`.