Phase 0A can't be finished from the shopping list as written. The head LED ring has no product to buy. The tray ledges and the occluder need parts that are only in later orders. The limit switches have no mount anywhere in the docs or the CAD. The moving-cable links point to the wrong product.

I made no repo changes and ran no test suites, so I have no test totals to report: this was a read-only pass. I could not open any shop pages (no network for fetching, and a curl check was refused). So every link-versus-spec finding below comes from the BOM's own notes and the listing names, not from the live pages. Docs were read at HEAD (unchanged since b4b2972). Code and CAD were checked at b4b2972 and in the working tree, which has other agents' uncommitted round-4 changes.

## Blocking

**B1. There is no 40 mm head LED ring to buy, and Phase 0A needs it.**
- **Where:** `docs/SHOPPING_LIST.md:40`, `docs/BOM.csv:67`, `docs/BOM.md:51`.
- **Evidence [Certain]:** the line says "NEEDS A BETTER LINK: the eBay listing found has ended; Amazon's 40 mm rings are 12-SMD, not COB. Find one before ordering 1a." The ring seat in `phase0_top` (41 mm bore, `BUILD_GUIDE.md:595`) is built for this ring.
- **Fix:** find a 40 mm, 12 V COB listing and put its URL in `BOM.csv:67` before order 1a. Otherwise state a fallback in the line: "a 40 mm 12-SMD ring is OK if it fits a 41 mm bore; check for glare spots in Phase 0A." [Guessing that an SMD ring lights the label well enough]

**B2. The Phase 0A tray ledges need the pad microfiber and spray adhesive, which are order-2 lines.**
- **Where:** `BUILD_GUIDE.md:248-249` ("Face both tray ledges with a strip of the pad microfiber (spray adhesive)").
- **Evidence [Certain]:** neither part is in the §1.1 table (`BUILD_GUIDE.md:163-178`) or the school-stock note (`SHOPPING_LIST.md:24`). Both are order-2 lines (`SHOPPING_LIST.md:113-114`).
- **Fix:** add to `SHOPPING_LIST.md:24` and `BUILD_GUIDE.md:173`: "a strip of microfiber cloth plus spray adhesive or double-sided tape (school stock, or pull the order-2 Pad facing and Spray adhesive lines forward)".

**B3. The early order covers the cups but not the M-5ALU-4 elbows, and Phase 0B's thread sealant is in order 2.**
- **Where:** `BUILD_GUIDE.md:188-191`, `SHOPPING_LIST.md:24`, `BOM.md:65`.
- **Evidence [Certain]:**
  - All three tell the student to order only the SMC cups early. The elbow is in order 1b (`SHOPPING_LIST.md:62`).
  - The elbow is one of the occluders the jig must reproduce (`checks.txt:123` lists `vac_fitting` and `probe_flag`).
  - The elbow also clamps the flag (§7.6 step 6). So with cups but no elbow, neither the elbow nor the flag can go on the jig.
  - Phase 0B step 1 (`BUILD_GUIDE.md:435-436`) needs thread sealant, but PTFE tape is only in the order-2 reservoir line (`SHOPPING_LIST.md:123`).
- **Fix:**
  - In all three places, say "order the two cups and the two M-5ALU-4 elbows with 1a".
  - Add "PTFE tape" to order 1b.

**B4. The X home switch and Z top switch have no mount.**
- **Where:** `BUILD_GUIDE.md:1001-1005` (§6.8), `:1057-1060` (§7.4), `WIRING.md:497-503`.
- **Evidence [Certain]:** the docs give a trip position but no bracket, screws or method. Searching `cad/*.py` finds no switch part, and `cad/out/printed` (23 STLs) has none either.
- **Fix:** either the CAD owner adds two switch-bracket STLs, or the guide gives a written method. For example: "bend an L bracket from the 1 mm aluminium offcut; fix the switch with 2 × M2 from the M2 kit; fix the bracket with an M5×10 into a T-nut (X: the beam's lower front slot; Z: the spine's right slot above the rail); slide it to set the click point. Instructor: helpful."

## Wrong purchase

**W1. Both moving-cable links go to a 4-core unshielded cable sold by the foot.**
- **Where:** `SHOPPING_LIST.md:146-147`.
- **Evidence [Certain]:**
  - The specs are "4-core 22 AWG shielded, 5 m" and "8-core 24 AWG shielded, 5 m", qty 1 each.
  - Both link to KB-3D's igus CF9-05-04 page. `BOM.csv:112-113` describes that cable as "4 x 0.5 mm2, unshielded, $2.47/ft".
  - Qty 1 on that page buys 1 ft, and the head cable needs twice as many cores.
  - `BOM.csv` marks the URL as "seen:" (a reference only). The shopping-list generator turned it into the Link.
- **Fix:**
  - Change the Link cells to "search: 'TRVVP 4 core 22AWG shielded drag chain cable 5 m'" and "search: '… 8 core 24AWG …'", with NEEDS A BETTER LINK.
  - Keep igus only in the Notes: "alternative: 9 ft for Z, 2 × 9 ft for the head, then renumber the cores in WIRING.md §11".
  - Fix the generator (scratchpad `docs3/shop_gen.py`) so "seen:" URLs never become the Link.

**W2. Some docs say 8 mm dowels; the BOM buys 5/16 in.**
- **Where:** `BUILD_GUIDE.md:98` ("8 mm dowels"), `BUILD_GUIDE.md:662` ("8 mm (or 5/16 in)"), `cad/out/cut_list.csv:12` ("8mm hardwood dowel", written by `cad/build.py:118`).
- **Evidence:**
  - [Certain] The BOM buys 5/16 in = 7.94 mm (`BOM.csv:47`, `SHOPPING_LIST.md:111`: "Drill 5/16 in, not 8 mm").
  - [Likely] A student going by the cut list buys an 8 mm bit, and the dowel then isn't the "firm push fit" that §5.4 step 5 asks for.
- **Fix:**
  - `BUILD_GUIDE.md:98`: "5/16 in (7.94 mm) dowels".
  - `BUILD_GUIDE.md:662`: "5/16 in (7.94 mm) hardwood dowel".
  - `build.py:118` label: "5/16 in (7.94 mm) hardwood dowel", then re-export the cut list. The template's 8.3 mm guide holes (`model.py:1005`) take either bit.

**W3. The awl pin spec contradicts itself.**
- **Where:** `SHOPPING_LIST.md:109`, `BOM.csv:45`, `BUILD_GUIDE.md:622`.
- **Evidence [Certain]:** the item says "3 mm hardened dowel pin", the notes say "Stainless, not hardened", and the guide says "hardened pin".
- **Fix:** "3 × 30 mm steel or stainless dowel pin (hardened not needed), or a 3 mm drill-bit shank".

**W4. "Measure before printing" names the machine part, but the Phase 0 part is printed first.**
- **Where:** `SHOPPING_LIST.md:41` ("measure before printing station_mount") and `SHOPPING_LIST.md:38` ("…before printing camera_bracket").
- **Evidence [Certain]:**
  - `phase0_base` has the same ring seat as `station_mount` (a 6.5 h print, `BUILD_GUIDE.md:545`).
  - `phase0_top` uses the ELP board's hole pattern before `camera_bracket` does.
  - The b4b2972 station "seat" is a 20 mm tube, OD 60 / ID 52, and the ring rests on its rim (model.py:241 at b4b2972). "52–60 mm" doesn't tell the student that.
- **Fix:**
  - Write "before printing phase0_base (and later station_mount)" and "before printing phase0_top and camera_bracket".
  - Explain the seat: "a ring with ID under 52 and OD over 52 sits on it". [Likely, from the CAD]

**W5. The push-fittings kit is bought before it is needed.**
- **Where:** `SHOPPING_LIST.md:58`.
- **Evidence [Certain]:** it is tagged Phase 0B, but its 1/8 NPT fittings are only used in the reservoir (`BUILD_GUIDE.md:1295`, order 2). Phase 0B uses only the tube and the barb (`:433-437`).
- **Fix:** move it to order 2. That saves $11.99 if 0B fails.

**W6. The mains wire is the EU colour code.**
- **Where:** `SHOPPING_LIST.md:137`.
- **Evidence [Certain]:** the line is brown/blue/green-yellow, "variants not confirmed". Its own note says US black/white/green is easier to buy.
- **Fix:** switch the line to US 18 AWG MTW in black/white/green and update the WIRING tables, or give the colour mapping in WIRING §1.1. This is the instructor's call.

**W7. The brad-point bit may be too short.**
- **Where:** `BOM.md:254`.
- **Evidence:** the depth collar sits 57 mm above the cutting lips (`BUILD_GUIDE.md:833`). [Guessing] A short bit may not have that much flute plus room for the collar.
- **Fix:** "5/16 in brad-point, at least 4 1/2 in (115 mm) long".

## Confusing

**C1. The read-this-first table still says the laser hole is 6.2 mm.**
- **Where:** `BUILD_GUIDE.md:45` ("the gate post's barrel hole is 6.2 mm. Drill it out.").
- **Evidence [Certain]:** the CAD has `bore = 7.2 if side == "L"` (`model.py:284`), and `gate_post_L.step` has r = 3.6 circles. `BUILD_GUIDE.md:890-893` and `BOM.md:351` already say 7.2 mm.
- **Fix:** "The only Class 2 laser found is 7 mm across: the left gate post now prints with a 7.2 mm hole. Drill only a post printed from an older STL. | §5.9".

**C2. `resume --face-down-ok` is missing its batch folder.**
- **Where:** `BUILD_GUIDE.md:1681`, `:1879-1885`, `:1931`, `:1973`.
- **Evidence [Certain]:** `batch_dir` is a required argument (`cli.py:723-724`), so the command as written fails with "the following arguments are required: batch_dir". `OPERATING.md:375` and `:591` use the full form.
- **Fix:** at the first use (`:1681`), write `python -m slabscan resume batches/<id> --face-down-ok` and add "the stop message prints the exact resume line" (`cli.py:413`). Use `resume batches/<id>` everywhere else.

**C3. The two Phase 0 commands look like steps, but the second run overwrites the first.**
- **Where:** `BUILD_GUIDE.md:312-313`.
- **Evidence [Certain]:** `phase0.py:162` opens `phase0.csv` with "w", and both commands use the same `--out`. A student who runs both re-types 30–50 certs and loses the first CSV.
- **Fix:** show one command, with `--face-up 15 --save`. Add: "Without the face-up pass, leave out `--face-up 15 --save`. A re-run with the same `--out` overwrites `phase0.csv`, so use a new folder."

**C4. §7.4a step 6.1 suggests watching `selftest` while jogging, which can't work.**
- **Where:** `BUILD_GUIDE.md:1094-1095`.
- **Evidence [Certain]:**
  - `jog` holds the machine lock (`factory.py:260`), and `selftest` also takes it (`ops.py:889-891`).
  - Restarting `jog` homes the machine (`cli.py:236`), so the head loses the 246.5 height.
- **Fix:** "Use the meter on OUT (about 5 V blocked, about 0 V clear). `selftest` cannot run while `jog` has the machine."

**C5. The belt-tension test can't be done as written.**
- **Where:** `BUILD_GUIDE.md:969-971` ("hook a 100 g mass … under the lower strand and lift … rise 13–23 mm").
- **Evidence [Likely, geometry]:**
  - The lower strand is 12.9 mm above the beam top (`:961`), so the beam stops a downward deflection before 13 mm.
  - With a 20T pulley the upper strand is about 12.7 mm above the lower one, so it blocks an upward deflection too.
- **Fix:** "Park the carriage at one end. Pull the lower strand sideways (in Y) at mid-span with a spring or luggage scale at 1 N (100 g): it should move 13–23 mm." Add the scale to the tools table.

**C6. `calibrate x` asks for a pocket-centre mark that nothing tells the student to make, and §12 swaps the cup and awl back and forth.**
- **Where:** `BUILD_GUIDE.md:1551-1553`; `ops.py:442` asks to "centre it exactly on the pocket centre mark". By §12 the pads cover the plywood.
- **Order problem [Certain]:** §12.1 runs with the cup, §12.2 swaps to the awl, §12.3 needs the cup again, and `:1540` says to re-run `calibrate z` after any pad change.
- **Fix:**
  - In §5.9, before laying the pads: "mark the centres of pockets 0 and 12 (halfway between the left and right rod rows) and copy the marks onto those two pads".
  - Run §12.2 before §12.1, or add "refit the cup pad and re-run `calibrate z`". [Likely safe either way: before `calibrate z`, `pad_trigger_c = 0`, which only makes jog's safe height higher (`ops.py:158`, `config.py:129`).]

**C7. The repository path is wrong after a `git clone`.**
- **Where:** `BUILD_GUIDE.md:1444`.
- **Evidence [Certain]:** the project is a subfolder of the git repo (origin `Icevyy14/codex`). A clone gives `~/codex/psa-slab-scanner`, so every `cd ~/psa-slab-scanner/software` fails (`BUILD_GUIDE.md:298`, `:1451`, `:1454`, and the opening of `OPERATING.md`).
- **Fix:** give the exact commands: `git clone <repo> ~/codex && ln -s ~/codex/psa-slab-scanner ~/psa-slab-scanner`, or copy only the `psa-slab-scanner` folder by USB.

**C8. The Phase 0 screws come from order-2 packs, and schools rarely stock slot-6 T-nuts.**
- **Where:** `SHOPPING_LIST.md:24`, `BUILD_GUIDE.md:173`.
- **Fix:** add "no slot-6 T-nuts? a plain M5 hex nut slid in from the open end of the post or stub works for the jig" [Likely]. Or pull the KB-3D M5 T-nuts and the AFT M5×10 forward (about $19).

**C9. The fallback for a Phase 0B mark is a dead end.**
- **Where:** `BUILD_GUIDE.md:461-462`, `BOM.md:134-136`, `SHOPPING_LIST.md:173`.
- **Evidence [Certain]:** the docs say to try the HT1 cup, but it "needs an M10x1-to-G1/8 adapter nobody has sourced". A student whose cup marks has nothing to buy.
- **Fix:** source the adapter before Phase 0B. Until then, write "if the urethane cup marks, stop and ask".

**C10. Instructor and time flags are off.**
- **Where:** `BUILD_GUIDE.md:110`, `BUILD_GUIDE.md:125`.
- **Evidence:**
  - [Certain] Phase 0A says "Instructor: no", but it includes drill-press match-drilling (§1.5 step 7.1) and sawing and bending the flag.
  - [Certain] §14 is listed as "2 h", but it covers 30 slabs, then 100, then a full load (79 min of machine time alone).
- **Fix:**
  - Phase 0A: "for power-tool rules".
  - §14: "2 h for the first 30, then two more sessions of 2–3 h". [Guessing on the session lengths]

**C11. The tools table offers a drill press for the rod holes.**
- **Where:** `BOM.md:253` ("cordless or drill press").
- **Evidence [Certain]:** the rod holes are drilled in place on the assembled machine (`BUILD_GUIDE.md:806-837`), where a drill press can't reach.
- **Fix:** "a hand drill for the rod holes; the drill press for the guide block and the cross holes".

**C12. The tools table is missing items the steps use.**
- **Where:** `BOM.md:251-271`.
- **Missing [Certain]:**
  - Metric drill bits:
    - 1.8 mm (bridge holes, `:263`);
    - 3.4 mm (`:616`, `:1088`);
    - 5.2 mm (flag hole, `:1180`);
    - 5.5 mm (cross holes, `:274`, `:1110`).
  - An 11/32 in tap drill for 1/8 NPT (`:1295`).
  - A knife and steel rule (`:786`).
  - A spring scale (`:969`).
  - CA glue (`:623`).
  - Shims or a lab jack for Phase 0B (`:440`).
  - A microSD reader to flash Bookworm (`:1436`).
  - M2 washers for the aim shim (`:1238`; the M2 kit is screws and nuts only).
- **Fix:** add a "drills and small items" group to the table.

## Nits

- **Confidence tags don't match:** 11 differ between `BOM.csv` and `SHOPPING_LIST.md`. For example, `SHOPPING_LIST.md:30` says Guessing where `BOM.csv:37` says Likely, and `:125` says Certain where `BOM.csv:86` says Likely. Fix: regenerate the tags from the CSV.
- **`SHOPPING_LIST.md:156`:** the Link is "search: cad/out/printed/" for a printed part. Change it to "-".
- **`BUILD_GUIDE.md:235`:** "M2 self-tapping screws", but the kit is machine screws. Write "M2×6 machine screws, turned into the printed bosses".
- **`BUILD_GUIDE.md:1455`:** the `i2cdetect` "48" check runs in Phase 0 (via §1.4), where there is no ADS1115 yet. Add "(Phase 0: no 48, that's fine)".
- **`BUILD_GUIDE.md:1537`:** explain the formula as "Z after homing 255 − c_max 250 − the 12 mm `--extra-depth`".
- **`BUILD_GUIDE.md:442`:** add inHg next to the kPa (5 kPa ≈ 1.5 inHg), because brake-bleeder gauges read inHg.
- **`BUILD_GUIDE.md:842`:** "two pins of the hole size (drill bits)", but the student owns one bit. Write "two 5/16 in dowel offcuts".
- **`BUILD_GUIDE.md:1262`:** "Raise Z run_amps" should name the Z motor0 line (`config.yaml:239`), not the spare motor1 line (`:267`).
- **`BUILD_GUIDE.md:724`:** "about 124 M5" against 126 in `BOM.md:204`. Write "about 126 (2 go in the Z spine in §7.1)".
- **`cad/model.py:887`:** the comment "the BOM's sensors come as a 3-pack" should be "two 2-packs".

## What the student has to measure on arrival

- **Slabs:** five of their own (W × L × T); one CGC, BGS and TAG holder each, if they deal them (each must be ≤ 82.6 mm wide); and label-end-to-card-top on 2 PSA and 1 CGC (§1.2).
- **ELP head camera board:** the hole pattern (CAD assumes 32 mm), the board-to-lens-front length L (CAD assumes 20 mm, which sets the standoff height L − 7.4), and the lens-holder footprint (16 mm).
- **Both endstop boards:** a 3.1 mm slot, holes 19 mm apart with the slot midway, where the header is, and nothing taller than 4 mm within 2 mm of the slot line.
- **LED rings:** OD, ID and thickness of both. Head ring thickness 4 mm or less (`BOM.md` gap 7).
- **Camera Module 3:** holes 21 × 12.5 mm.
- **SMC buffer:**
  - 108.5 mm from pad face to port top, 44.5 mm from pad face to body end;
  - a 51 mm body with 14 mm A/F nuts;
  - a 21.5 mm free gap;
  - a K or J rod;
  - and the pad's M5 stud (the awl adapter assumes it).
- **M-5ALU-4 elbow:** 9.3 mm tall or less, with at least 3.4 mm of thread.
- **M5 heat-set insert:** against the 6.4 mm pocket. The 9.5 mm insert sits 0.5 mm proud of the 9.0 mm pocket.
- **Extrusions and screws:**
  - the 4040 is 20-series slot 6 with two slots per face;
  - both bores of the Z spine are tapped;
  - test the T-nut slot depth with the first M5×10 in the jig and with an M5×25/M5×30 on a rail offcut.
- **Motors and motion:**
  - the Z lead screw is 8 mm lead;
  - Z motor phase resistance is 1–2 Ω;
  - the screw length from the motor face (cut it to 340 mm);
  - the X motor shaft is at least 22.5 mm long;
  - the GT2 idlers are toothed;
  - count the balls in each MGN12 block and do the roll test.
- **Rodent:** read the sense-resistor marking (R075 or R022), check the connector types, and reflash FluidNC.
- **Wood:** a test hole for each dowel and bit pair; roll every dowel; check the plywood's actual thickness and voids (and that the brad spur does not break through).
- **Gate post parts:** the laser body is 7 mm, and the receiver must fit the 6.2 mm hole (never measured [Guessing]).
- **Electrical and pneumatic:**
  - the mains inlet's wall thickness against the Hammond box;
  - whether the hand pump reaches −60 kPa, and its hose ID against the 4 mm tube;
  - the main pump's inlet size;
  - the Clippard inlet/outlet marks;
  - about 10 kΩ SIG-to-GND on each MOSFET module;
  - the carry sensor's high level at GPIO 6 (at least 2.5 V);
  - how the laser receiver's OUT behaves.
- **During calibration:** the probe trip travel (`buffer_trip_mm`), the station lens height (23 ± 1 mm), the head camera's `hfov_deg`, and the carry-sensor trip (246.5 ± 1).

## Docs that the uncommitted round-4 work will make stale

- **Card window:** `layout.py` now has `[[-27.5, -23.5, 27.5, -18.0]]`, and `gen_config --check` says `machine.toml` is STALE. When it lands, update:
  - `BUILD_GUIDE.md:210-212` (the "40 to 52 mm" range and both frames);
  - the flipped window at `:366` and `:1490`;
  - `:1473`;
  - the "1.4 mm clear" at `:1595`;
  - "55 × 11.5 mm" in `OPERATING.md` §8.4;
  - the CGC caveat at `BUILD_GUIDE.md:42` and `:214-216`;
  - the "27 PSA / 15 CGC backs" counts (`layout.py` now says 22 PSA, 27 CGC);
  - the aim tolerance at `BUILD_GUIDE.md:43`, `:1236-1239` and `README.md:120` (the layout comment says 1.34°).
- **Print list:** it now totals 768.3 cm³ instead of 750.6. `station_mount`, `camera_bracket`, `phase0_base` and `phase0_top` changed. Update `BUILD_GUIDE.md:547`, `:560`, `:567`, `BOM.md:304` and the `BOM.csv:124` notes.
- **Ring seats:** the station seat is now a 64 mm bore that takes a 60 or 63 mm ring. Update `SHOPPING_LIST.md:41`, `BOM.csv:68`, `BOM.md:341` and `BUILD_GUIDE.md:596`. `BOM.md` gap 7 (the 0.75 mm barb clearance) looks resolved.
- **CLI:** `cli.py` gains `--sim-head-tilt` and a "CAMERA AIM:" summary line, which no doc mentions yet.

Evidence notes are in `scratch/round4/walkthrough/evidence_notes.txt`.