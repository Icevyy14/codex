I moved the head camera 5 mm toward the label end, which reaches past the `head_foot` redesign you scoped. The `head_foot` redesign alone could not meet the 300 mm² requirement, and two facts in the brief were wrong:
- **The real blocker is the elbow, not the foot.** The M5 elbow on the buffer port reaches c+116.8 on the cup axis, 23 mm under the lens. With the lens on the axis it hides a disc of radius 25.6 mm on the slab at hover. [Certain, CAD ray cast]
- **The card top is not 32 mm from the slab edge.** I measured 27 real PSA backs in realslabs: the card top is 34.8–37.8 mm from the label-end edge, median 36.1, so y = -31.7 for a centred slab. [Likely; ±1 mm from image scale]
- **Lens on the axis:** even with the trimmed foot, only 275 mm² of card on the label side is clear with a conservative margin (385 mm² with a looser one), in thin slivers around the disc. That fails 300 mm².
- **Lens 5 mm toward the label:** every part on the axis (elbow, flag tab, port hex, nut) throws its shadow toward +Y instead. 739 mm² is clear; my window uses 632.5 mm² of it.
- **To undo it:** set `HEAD_CAM_DY = 0` in layout.py. The window checks then fail, which is correct.

## Check totals
- `cd cad && python3 checks.py` → `layout checks: OK`, `126/126 checks passed`, exit 0. Saved to cad/out/checks.txt. Before: 106/106.
- I ran it twice; the second run used the final files, and the two outputs are identical.
- All 106 old checks still pass. The only old values that moved:
  - Pick clearance: 18.95 → 14.55 mm (limit 3.0). Cause: the M3×16 screw tip on the probe board's nut side.
  - Probe board key access: front 1.15 → 1.63 mm, rear 1.54 → 2.0 mm (the head now sits on a washer).
  - Head camera half-angle to the label edge: 24.82° → 23.11°.
  - All Phase 0 checks kept their values; the jig matches the machine relative to the lens.

## What changed
**Head camera**
- New `layout.HEAD_CAM_DY = -5.0`: the lens is 5 mm from the cup axis toward the label, still 140 mm above the cup face.
- `camera_bracket`: shelf now runs Y -29..25 (was -24..25). Lens window, the 4 board holes and the ring seat all moved -5. Now 48×76×26 mm, 16.4 cm³.
- `phase0_top`: bridge now runs Y -30..25 (was ±25). Lens window, ring seat and standoff holes moved -5. Now 154×55×11 mm, 61.0 cm³. The jig matches the machine relative to the lens, so every Phase 0 comparison is unchanged.

**head_foot**
- The foot's label-side face moved from Y -15 to Y -9 (`FOOT_LABEL_Y`). That still carries the 14 mm M10 nuts and leaves 3.8 mm of wall round the M10 hole.
- The extension under the sensor post now starts at Y -9.5 (was -16.5).
- 31.0 cm³, was 34.8. The nut, flag, guide, sensor post, elbow and tube are unchanged: with the lens offset none of them is in the view.

**Probe board screws**
- Modelled as M3×16, with a washer under the head and another under the nut; the tip runs 3.9 mm past the nut (`PROBE_SCREW_L`, `M3_WASHER`).
- docs/BUILD_GUIDE.md §7.6 calls these the "board" screws. The head-camera board uses M2 and is unchanged.

**Phase 0 jig walls**
- Every wall an M5×10 passes through is now 4.0 mm (`P0_M5_WALL`), using pads. Before: tray clamps 1.8, mount clamp 1.8, stub socket 2.0. The base sockets were already 3.8 and are unchanged.
- With one M5 washer the tip ends 5 mm inside the profile face. [Guessing: the 2020 slot is about 6 mm to the core]

**New parts:** `carry_sensor_mount`, `carry_flag_arm`, the `carry_flag`, and 2 × 2.5 mm pilot holes in the `z_plate`.

**Exports and renders**
- Re-exported: `build.export_printed`, `write_cut_list` (new flag row), `export_assembly('home')`, the probe flag drawing, and new `cad/out/heads_cad.json`.
- Re-rendered with render_docs.py and render_parts.py, plus two new images:
  - **docs/img/face_down_view.png:** the head camera's view at hover, true projection of the CAD parts, window in red.
  - **docs/img/carry_sensor.png:** the carry sensor clear at c = 233 and blocked at c = 262.
- I looked at head_closeup.png: it renders correctly, but the foot change is too small to see at that scale. Cite face_down_view.png instead.

## Card window
- `FACE_DOWN_WINDOW_MM = [[-27.5, -27.5, 27.5, -16.0]]`, in mm from the cup axis. Area 632.5 mm².
- **The software needs the camera-axis version:** `L.face_down_window_cam()` = `[[-27.5, -22.5, 27.5, -11.0]]`. `config.face_down_window_mm` is measured from the head-camera axis.
- Exact frustum checks, against every machine part except the camera and the slab being looked at:
  - At hover over stacks of 1, 15 and 30: 0.0 mm³ in view. Nearest part 0.86 mm (head_foot, stack of 1).
  - Held at c = 236.5 and 248: 0.0 mm³. Nearest part 1.03 mm.
- Where it lies on the slab:
  - Inside the card's top edge by 0.2 mm in the worst case (latest card top measured, plus the slab at the end of its 1.75 + 0.5 mm play). 4.1 mm inside for a median slab sitting centred.
  - 0.9 mm inside the card's sides.
  - 7.0 mm clear of the label band.

## Carry-height sensor
- **Trip height:** `CARRY_SENSOR_C0 = 235.0` (C_SAFE_EMPTY − 1.5).
- **Sensor:** the spare TCST2103 board on the Z spine's left (-X) face. The beam is at Z 550 above the pad top: 275 mm above the spine's bottom end, 65 mm below its top.
  - Arms point away from the spine; the slot runs vertically.
  - Mount (48×28×5 mm, 6.2 cm³): 2 × M5×10 button heads into slot-6 T-nuts in that face's slot. Slide it along the slot to set the trip.
  - Board: 2 × M3×10 with the heads in pockets on the spine side, washer and nut on the sensor flange.
- **Flag:** cut from the BOM's 1 mm aluminium sheet, flat, 19.9 × 36 mm. Two 3.4 mm holes, 4 mm from the outer edge, 6 and 18 mm below the top edge. The top edge is the trip edge.
- **Flag arm** (46×34.5×24 mm, 17.2 cm³): screwed to the `z_plate` front face with 2 × M3×10 into the new pilots (X -24, 2 and 14 mm above the Z carriage's bottom edge). Its leg runs beside the spine, 4.6 mm outside the sensor arm tips. The flag fixes to the leg's end with 2 × M3×8.
- **Checks:**
  - Trips at c = 235.00 (error 0.0).
  - Beam clear from c = -14 to 234; fully blocked from 236.5 to the top stop at 262. 8.5 mm of flag is left below the beam at 262.
  - Flag to sensor: 1.05 mm.
  - Flag, arm and screws to everything on the X carriage, over the full Z travel: 4.6 mm.
  - The lead's path (header up to the spine top) stays 11.0 mm from anything that moves, and cuts through no part.

## Output for the software agent
`scratch/round3/heads_cad.json` (same file at cad/out/heads_cad.json) contains:
- 21 HEADS boxes (x0, y0, x1, y1, z0, z1, grey), from the cup axis, z above c, cup free (buffer at rest).
- The lens position (0, -5, 140) and the projection formula that includes the offset.
- Both window versions, `CARRY_SENSOR_C0`, and the measured card-top numbers.
- The boxes' shadow covers 100% of the CAD's at hover and held, and is only about 0.5% larger.

The software side needs four changes:
- **`config.from_layout()` must use `L.face_down_window_cam()`.** It currently picks up `FACE_DOWN_WINDOW_MM` in cup-axis coordinates, 5 mm off. `PYTHONPATH=. python3 tools/gen_config.py --check` now reports: `STALE (regenerate): face_down_window_mm: ((-27.5, -27.5, 27.5, -16.0),) != ((-28.0, -33.0, 28.0, -17.0),)`. If it is not fixed, the window lands partly off the card; that causes false stops, not false accepts.
- **sim.py:** `head_shadow` has to project from lens (0, -5). The rendered slab sits 5 mm toward +Y in the frame, and `CARD_TOP_MM` should be 36, not 32.
- **Carry sensor rule:** before every X move, require "blocked". Also require "clear" whenever c < 234, for example at each pick. A dead emitter or a dirty slot reads "blocked" in this geometry, so without the second rule a dead sensor would always allow sideways moves.
- **Not verified by me:** I did not run the software suite. Another agent is editing software/ right now, and test_face_down_learned.py reads `from_layout()`'s window, so its outcomes may change.

## Doc changes for the docs agent
**BUILD_GUIDE.md**
- **"Read this first" table:**
  - Replace the screw-length row: the CAD now models M3×16 + washers, and the jig walls are 4 mm.
  - Add: the lens sits 5 mm toward the label by construction (bracket and jig bridge), and why.
  - Add: card top measured at 34.8–37.8 mm from the label edge on 27 real PSA backs.
  - Add: the carry-sensor trip is set by sliding its mount.
- **§1.2:** the card-top measurement now has values: 34.8–37.8 mm.
- **§1.5:**
  - Step 3: walls are now 4 mm. Use ONE M5 washer per M5×10 (not two) and keep "test the first screw".
  - Step 5: the bridge is asymmetric; fit its wider side toward the tray's label end. The lens sits 5 mm toward the label from the slab centre. Still measure 140 ± 2 mm.
- **§3.2 print table:**
  - head_foot 31.0 cm³, camera_bracket 16.4, phase0_top 61.0, phase0_tray 51.1, phase0_occluder_mount 14.8.
  - New rows: carry_sensor_mount (1, PETG, flat on its spine face, 4 walls 40%, 6.2 cm³, about 0.35 h) and carry_flag_arm (1, PETG, on its bottom face, 4 walls 40%, 17.2 cm³, about 0.95 h). [print times Guessing, scaled by volume]
  - Note that camera_bracket and phase0_top must be reprinted.
- **§3.3:** add the spare endstop board row (same as the probe board: holes 19 mm apart, header assumed at the +Y end [Guessing]).
- **§7.4 or a new §7.4a, "Carry-height sensor"** (image carry_sensor.png):
  1. Fit the board to the mount (M3×10 heads in the pockets, washer and nut on the flange).
  2. Mount it on the spine's left face with 2 × M5×10 button heads and T-nuts, beam about 65 mm below the spine top. Leave the screws loose.
  3. Screw the arm to the z_plate front face with 2 × M3×10.
  4. Cut the flag, file its top edge straight, and fix it with 2 × M3×8, inner edge toward the spine and top edge flush with the arm top.
  5. Run Z through the full travel by hand: no rub, about 1 mm each side in the slot.
  6. Jog to c = 235.0 with a meter on OUT and slide the mount until it just reads blocked. Check: clear at 234, blocked at 236 and 250.
- **§7.5:** the lens is 5 mm toward the label from the cup axis, set by the bracket; there is no adjustment. Fix any text that says "lens on the cup axis". Add face_down_view.png.
- **§7.6 step 7:** delete "The CAD shows M3×12…". Key clearances are now 1.63 mm (ball-end key at 20°) and 2.0 mm (straight key, rear screw).
- **§11 config:** the window now comes from the layout. Once from_layout is fixed, machine.toml should read `[[-27.5, -22.5, 27.5, -11.0]]`.

**BOM**
- Spare endstop board: already in the 3-pack, $0.
- Two new printed parts (PETG).
- 2 × M5×10 button head (ISO 7380) + 2 × slot-6 M5 T-nuts.
- 4 × M3×10: 2 for the board, with 2 washers and 2 nuts; 2 for the arm, threaded into printed pilots.
- 2 × M3×8 for the flag.
- Aluminium sheet line becomes "1 mm, ≥ 50 × 60 mm offcut (probe flag + carry flag)".
- About 0.2 m of 3-core 24–26 AWG from the board to the spine top.
- Phase 0: M5 washers 12 → 6.
- If the sensor goes to the Pi: 10 kΩ + 20 kΩ resistors.

**WIRING.md**
- New row: carry board VCC, GND and OUT spliced at the spine top, where the 8-core is already opened for the Z switch:
  - VCC → core 1 (+5 V, shared with the probe); GND → core 2.
  - OUT → spare core 8 → I/O board divider (10 kΩ series, 20 kΩ to GND) → GPIO6 (pin 31). GPIO6 is unused in docs, software and firmware. [Certain, grep]
  - The cable rides the X drag chain only; it is fixed to the carriage, so it never enters the Z service loop.
  - [Likely] the Pi and the Rodent share a ground over USB.
- **Polarity and failure table:**
  - HIGH = flag in the beam = at carry height.
  - Cut signal wire → the 20 kΩ pulls LOW → sideways moves refused (safe).
  - Dead emitter or dirt → reads HIGH, which is NOT safe. It is caught only by the software rule "must read clear below c 234".
- §8 core 8 is no longer "spare".

Files are in :
- cad/: layout.py, model.py, checks.py, build.py, render_docs.py
- cad/out/: checks.txt, heads_cad.json, cut_list.csv, printed/*, assembly/slabrail_home.step
- docs/img/: face_down_view.png, carry_sensor.png, plus the re-rendered images