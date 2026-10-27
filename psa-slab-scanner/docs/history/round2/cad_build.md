The BOM's "1 mm aluminium strip ~6 × 60 mm" can't make this flag. A flag that passes *through* a U-slot over the whole 25 mm stroke has to be a flat plate in the slot's mid-plane, and that plate is 24.3 × 39.25 mm. So the BOM line must change to a sheet offcut. [Certain, from the geometry] The second problem: the flag's fit depends on two purchased-part dimensions I could not look up. The SMC datasheets and the Vishay datasheet failed DNS from here, so the buffer's stopper height above the foot and the TCST2103's slot depth are guesses. If the real stopper sits more than ±2.5 mm off my guess, the student re-cuts the flag. [Guessing on both dimensions]

**Checks:** layout.py `checks: OK`. Before: `77/77 checks passed`. Now: `95/95 checks passed`, exit 0, saved to cad/out/checks.txt. [Certain]
- Every old check still passes. One old value changed: pick-clearance to the neighbouring stack went from 21.35 to 18.95 mm (limit 3.0). The closest part is now the probe board's rear nut, `probe_nut_-2`.
- The 18 new checks, verbatim values:

| Check | Value | Limit |
|---|---|---|
| Trip travel error vs 2.0 mm | 0.0 (trips at 2.00 mm) | ≤ 0.05 |
| Travel before the flag starts to cover the aperture | 1.5 mm (blocked share at rest 0.000) | ≥ 1.0 |
| Beam fully blocked from 3 to 25 mm (min share) | 1.0 | ≥ 0.999 |
| Flag vs sensor over 0–25 mm | 1.0 mm | ≥ 0.5 |
| Flag vs its guide | 0.45 mm | ≥ 0.3 |
| Flag vs nut, screws, arm, camera | 2.0 mm | ≥ 1.0 |
| Buffer stop + fitting vs foot, sensor, arm, camera | 5.97 mm | ≥ 1.0 |
| Blade depth in the guide, worst case | 4.0 mm (at 25 mm travel) | ≥ 3.0 |
| Rotating buffer turned until the guide stops it: sensor clearance | 0.6 mm (stops at +1.33°) | ≥ 0.3 |
| Board at its slot ends vs head_foot overlap | 0.0 mm³ | ≤ 0.5 |
| Flag vs sensor with the board at either slot end | 1.0 mm | ≥ 0.5 |
| Label view, flag + buffer stop over the whole stroke | 0.0 mm³ | ≤ 1.0 |
| Label view, vacuum fitting while reading (0–2 mm) | 0.0 mm³ | ≤ 1.0 |
| Phase 0 label view with the occluder fitted | 0.0 mm³ | ≤ 1.0 |
| Phase 0 cup face above the slab back | 0.5 mm (0.00 mm off the lens axis) | ≥ 0.2 |
| Phase 0 occluder vs machine, relative to the lens | 0.5 mm worst, 14 parts compared | ≤ 1.0 |
| Phase 0 whole-slab view blocked, jig vs machine | 0.09 % (41,938 vs 41,977 mm³) | ≤ 1.0 % |
| Phase 0 parts in that view not in both | 0 | 0 |
| Phase 0 flag, stop, fitting over 0–25 mm vs mount, bridge, camera, stub, post | 3.0 mm | ≥ 1.0 |

The Phase 0 jig interference check is still 0.0.

## What I built

**Gap 1: probe flag, sensor and guide** (heights below are above c; "at rest" means the buffer is fully extended)
- **Sensor (`contact_sensor`)**: TCST2103 board on the post's -X face.
  - The optical axis runs along Y. The slot runs vertically and opens toward the buffer, so the flag passes straight through and can never bottom out.
  - Beam centre at X 17.3, Y +7.5, Z 99. The slot bottom is at X 20.3.
  - Fixed with 2 × M3×12 + washers + nuts through vertical slots (±2.5 mm of trip adjustment) at Y −2 and +17.
  - [Certain] 3.1 mm gap, 1 mm aperture.
  - [Likely] 24.5 mm package with flanges; the board's 19 mm holes are the sensor's own flange holes, with the slot midway between them. TCST1103 is the flangeless 11.9 mm version.
  - [Guessing] Flange 3 mm thick, slot 6.2 mm deep, optical axis 3.2 mm below the arm tips, 3-pin header at the +Y end.
- **Flag (`probe_flag`, kind "made")**: 1.0 mm aluminium with one 90° bend.
  - The plate sits in the slot plane at Y +7.5, on the far side from the label.
  - Blade X 12.0–19.3, Z 63.75–97.0 at rest, so its top edge is 2.0 mm below the beam centre. The outer edge stays 1.0 mm off the slot bottom.
  - Web Z 82–88, plus a neck ±5 mm wide.
  - Tab 10 mm wide, bend inner radius ~1 mm, 5.2 mm hole on the cup axis. The tab sits on the buffer's stopper block, under the M5 fitting.
  - The trip is exactly 2.0 mm in CAD (`PROBE_TRIP_TOL = 0.5` added to layout.py, plus two layout checks).
- **Guide (in head_foot)**:
  - Two fins, 2.5 mm thick, X 11–24.4, Z 75–92.75, with a 1.9 mm slot between them (0.45 mm each side of the flag).
  - The slot continues through the foot, where the blade dips at rest.
  - The post grew to X 26.5–30.5, Y −9.5…24.5, Z 75–106; the self-tap holes became slots. The foot extension now reaches Y 24.5.
  - head_foot is now 46 × 64 × 44 mm, 34.8 cm³, about 1.9 h to print.
- **Buffer model, split into fixed and moving parts**:
  - Fixed: body plus top nut (Ø17 × 5, on the foot), body top at 83.
  - Moving: cup, rod Ø6, `buffer_stop` Ø11.5 × 8 (stopper block with the M5 port), `vac_fitting` Ø10 × 15.
  - `head_parts(compression=t)` places the moving parts at buffer travel t; the default is 2 mm (the trip), so all old poses are unchanged.
  - [Guessing] All of these dimensions. I named the part `buffer_stop`, not `rod_end`, because checks.py treats any `rod_*` name as a guide rod.

**Gap 2: Phase 0 occluder**
- `occluder_parts()` is shared: the machine and the jig use the same function. The jig places it at c = lens − 140 + 0.5, so the cup face sits 0.5 mm above the slab back.
- **`phase0_occluder_mount`** (new printed part): 89 × 59 × 18 mm, 14.1 cm³, about 0.8 h.
  - A clamp slides on the right post (M5×10 + T-nut into the post's outer slot).
  - A beam outside the camera's view joins it to a socket at X 0, Y +35.
  - The socket holds a 2020 × 70 mm stub (M5×10 + T-nut into the stub's +X slot). The stub bottoms in head_foot's socket like the drop arm, with a cross hole 19 mm from its end.
  - It sits at Z 280–298 in the jig: above the sensor post, below the bridge.

**Exports**
- Printed STL/STEP now include phase0_occluder_mount and the new head_foot.
- The cut list gains three rows: the flag blank, the 2 × 312 mm jig posts (BOM.md gap 8), and the 70 mm stub.
- I also fixed a CSV bug: the old cut list's base-rail row had an unquoted comma, so it had 5 columns. [Certain]
- New: cad/out/probe_flag_blank.svg (1:1, with a 10 mm check bar) and .dxf.
- Assembly re-exported with export_assembly('home').
- render_docs.py and render_parts.py re-run. New images: docs/img/probe_flag.png (the drawing) and docs/img/probe_closeup.png (cup free vs pushed up 25 mm, beam drawn in red).
- I looked at the images myself:
  - phase0_jig.png shows the mount, stub, foot, board and the cup on the slab centre, and looks right.
  - head_closeup.png: the probe is too small to read among the rods. Use probe_closeup.png in §7.6.

## How the student makes and fits the flag
1. **Measure first.** On the real parts, check:
   - the buffer stop's top above the foot's top face at rest (CAD: 16 mm);
   - the slot depth (CAD: 6.2 mm);
   - that the slot sits midway between the board's holes.
2. **Cut.** Print the SVG at 100 % and check the 10 mm bar. Glue it to 1 mm aluminium sheet. Cut with a hacksaw or piercing saw and file to the line; snips curl the edge. The blade's top edge is the trip edge: file it straight and square.
3. **Bend.** The drawing shows the face that will face the buffer. Clamp the neck in a vise with the jaws at the BEND line. Bend the tab 90° toward you; bent the other way, the blade ends up on the wrong side. Check 90 ± 1° with a square: 1° of lean is 0.6 mm over the blade.
4. **Drill after bending.** Drill 5.2 mm on the neck centre line, 7.0 mm from the plate's inner face. Trim the tab to 2 mm past the hole and deburr.
5. **Fit.**
   - Screw the buffer into the foot with its nuts.
   - Put the tab on the stopper, with an M5 sealing washer under the tab or sealant on the thread.
   - Drop the blade into the 1.9 mm slot.
   - Screw in the M5 fitting, at least 3 threads engaged.
   - With a K buffer, align the blade with the slot before tightening. With a J buffer the guide aligns it.
6. **Board.** Components face the buffer, header toward the arm. Fit M3×12 + washers + nuts, centred in the slots.
7. **Free-run test.** Push the cup by hand through the full stroke. The blade must slide with no rub.
8. **Set the trip.** Put a meter on OUT, find the travel where it jumps, and slide the board until it reads 2.0 ± 0.5 mm. Up = later trip. Record `buffer_trip_mm`.
9. **Full-stroke test.** OUT must stay high from the trip to full compression.

[Likely] The sealing washer is needed: the fitting's own seal now bears on the tab, so air can leak along the thread and out under the tab.

## Doc changes for the docs agent
**Read this first, gap table**
- Remove the "probe flag not in the CAD" row.
- Remove the "nothing mounts the occluder" row.
- Rewrite the K-buffer row: the K code is still unconfirmed, but head_foot now has a flag guide, so a rotating J buffer works too (§2, §7.6).
- Add a row: the buffer's shape above the foot and the TCST2103's slot depth, optical axis and position on the board are CAD guesses. Measure them before cutting the flag; the board slots give ±2.5 mm (§3.3, §7.6).

**§1.1**
- Add phase0_occluder_mount to the printed parts.
- M5×10 screws and slot-6 T-nuts: 4 → 6 of each.
- 2020: 2 × 312 mm plus a 70 mm stub.
- Add an M5×30 + nylock (the foot on the stub), 2 × M3×12 + washers + nuts (the board), and the flag offcut.

**§1.3**
- About 15 h, not 14. Add phase0_occluder_mount to the list.

**§1.5**
- Step 3: slide the occluder mount onto the RIGHT post before the bridge goes on.
- Rewrite step 7:
  1. Match-drill the stub through head_foot and fix it with the M5×30.
  2. Fit the buffer, cup, flag, fitting and board as in §7.6. With the M10-bolt dummy, leave the flag off.
  3. Push the stub up into the socket: arm to the back, sensor post on the right.
  4. With a 0.5 mm gauge on the slab and the buffer at rest, slide the mount and the stub until the cup rests on the gauge. Tighten both M5 screws.
  5. The cup lands on the lens axis by construction. [Likely ±1 mm, print tolerance]
  6. To change slabs, push the cup up by hand.
  7. For the `--face-up` pass, slide the stub up 10 mm first.
  - Cite the check: the jig's occluder is within 0.5 mm of the machine's, and it blocks 0.09 % less of the camera's whole-slab view.

**§3.2**
- head_foot: 1.7 → 1.9 h. Note: clear the flag slot and the board slots with a hacksaw blade.
- New row: phase0_occluder_mount | 1 | PLA/PETG | as exported (flat on its beam) | 4 / 30 % | none | 0.8 h.
- Total ≈ 40 h. After the Phase 0 prints (now ≈ 15 h) it stays ≈ 26 h.

**§3.3** — add rows:
- Buffer stop top 16 mm above the foot top at rest; top nut ≤ 17 mm across corners, ≤ 5 mm thick.
- TCST2103 slot depth 6.2 mm, optical axis 3.2 mm below the arm tips, slot midway between the 19 mm holes.
- No board component taller than 4 mm within 2 mm of the slot line.

**§7.5 step 6**
- The fitting clamps the flag tab: fit the flag first, with the sealing washer.

**§7.6** — rewrite:
- Drop "the flag is not in the CAD" and the 6 mm strip shape.
- Use the steps above, probe_flag.png and probe_closeup.png.
- The guide works with both J and K buffers.
- Step 4 becomes "slide the board in its slots".

**BOM.csv** (keep CRLF)
- Probe flag stock → "1 mm aluminium sheet, ≥ 25 × 40 mm offcut". Note: it is in the CAD now, cut to probe_flag_blank.svg. Optionally mark it PHASE 0A.
- Contact probe note: add the midway-slot and M3-slot assumptions.
- Cup + buffer: the J code `ZPT25UUJ25-B5-A10` is acceptable (built from SMC's pattern [Guessing]). Delete "no anti-rotation guide is needed then" and "a flag guide you make yourself".
- M3 assortment: add 2 × M3×12 + washers + nuts for the probe board.
- Phase 0A: 6 M5×10 + 6 T-nuts, the 70 mm stub, M5×30 + nylock.
- Push fittings: add an M5 sealing washer.

**BOM.md**
- Open gaps 4, 5 and 6 need updating: add the sensor-package guesses, J now works, and the flag sits between the stopper and the fitting, sealed.
- Gap 8 is closed (the jig posts are in the cut list).

## Outside my files
- **Simulator table.** software/slabscan/sim.py `HEADS["cad"]` mirrors head_foot by hand and is now stale. New boxes (x0, y0, x1, y1, z0, z1):
  - extension 15, −16.5, 30.5, 24.5, 62, 75
  - post 26.5, −9.5, 30.5, 24.5, 75, 106
  - board 14.1, −9, 26.5, 24, 93.75, 104.25
  - fins 11, 4.05, 24.4, 10.95, 75, 92.75
  - nut ±8.5, 75–80; body top ±5, 80–83
  - buffer stop ±5.75, 85–93
  - fitting ±5, 94–109
  - flag tab −5, −4.6, 5, 8, 92, 94
  - flag web 7–8 in Y, X −5…12, Z 84–92
  - flag blade 12, 7, 19.3, 8, 65.75, 99
- **The fitting's shadow.** It was missing from the old model. On the slab plane it now projects to about ±23.7 mm, into the face-down card window (Y < −12). [Likely]
- **tools/phase0.py docstring.** "Hold the occluder just above the slab" should become "slide the stub up 10 mm".
- **2 mm camera-distance mismatch (existed before this work).** The CAD puts the head lens 140 mm above the cup at its trip height, but §7.5 sets 140 mm above the free cup. [Certain] The jig check is not affected, because the offset is identical in the jig and the machine.

## Not verified
- No real part was measured, nothing was printed, and no flag was bent.
- Not covered by the CAD: the 1.9 mm slot's print accuracy, the vacuum seal at the tab, the J buffer's radial play and tilt, and whether a slightly twisted blade rubs.
- I did not run the software test suite (not my files). `gen_config --check` reports "up to date".

Files: cad/{layout.py, model.py, checks.py, build.py, render_docs.py}, cad/out/{checks.txt, cut_list.csv, probe_flag_blank.svg, probe_flag_blank.dxf, printed/*, assembly/slabrail_home.step}, docs/img/{probe_flag.png, probe_closeup.png, phase0_jig.png, head_closeup.png, printed_parts.png, and the other re-rendered images}.