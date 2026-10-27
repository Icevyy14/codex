The verifiers' fix for the critical buffer issue does not work as written. A push-in M5 elbow on the real 20 mm buffer reaches 3.4 mm past the head lens at full stroke. So the model now uses a barb elbow, and the meaning of its height dimension is only [Likely]. All 7 issues were real. All are fixed in CAD, and the full CAD suite passes. The full software suite fails 15 tests, from software edits another agent is making right now, not from cad/.

**Totals, verbatim**
- CAD: `cd cad && timeout 3000 python3 checks.py` → `layout checks: OK`, `106/106 checks passed`, `exit=0`. Saved to cad/out/checks.txt. [Certain] Before: 95/95. Every check I did not touch kept its old value; I diffed the two runs.
- Software, full suite: `15 failed, 157 passed in 1184.72s (0:19:44)`. A focused rerun of tests/test_face_down_learned.py and tests/test_runner_sim.py gave `14 failed, 15 passed in 571.12s`.
  - The errors include `ImportError: cannot import name 'FACE_DOWN_OK_REFUSED' from 'slabscan.runner'` (raised in cli.py line 39) and `face_down_threshold_sig missing`.
  - [Certain] These come from uncommitted edits another agent is making while the tests ran: facedown.py, sim.py, simworld.py, web.py, tools/phase0.py and test_face_down_learned.py are modified; runner.py and cli.py were saved during my run.
  - [Certain] My layout change does not reach the software. Every value `from_layout()` reads is identical before and after, including a pocket-list hash. `gen_config --check` reports `up to date`.

## Issues

**5 (critical), the buffer: confirmed and fixed.** [Certain] I rendered SMC catalog p.13-11-12 and read the stroke table (Table 2) myself. Pads of ø10-32 mm come only in 10/20/30/40/50 mm stroke. For ø20/25 at 20 mm stroke: E = 44.5, F = 108.5, G = 51, 8 mm hex × 5 on top, nuts 14 mm across flats.
- **Buffer model:** now ZPT25UUK20-B5-A10, `BUFFER_STROKE = 20`. Heights above c:
  - pad Ø28 (outside diameter B) at the face, then its hub, then its own 8 mm hex up to 23 above the pad face;
  - rod Ø6;
  - fixed M10 body from 42.5 to 93.5, with a 14 mm × 3 nut on each face of the foot;
  - neck Ø8 × 8 and port hex 8 × 5; port top at c+106.5 at rest.
  - The free pad face sits 64.0 mm below the foot's underside.
- **Flag:** head_foot, the beam (99), the guide and the blade top (97) are unchanged.
  - Bend line at 105.5; the blade top is 8.5 below it.
  - A band at 91-97 joins the neck to the blade.
  - Blade bottom at 63.25 at rest. Blank 24.4 × 55.25 mm.
- **Fitting:** a push-in elbow is too tall.
  - [Certain, SMC KQ2 catalog] KQ2L04-M5A stands 15.9 mm above its seat, which puts its top at c+143.4 at full stroke; the lens front is at c+140. KQ2VS04-M5A is 15.2.
  - So I modelled the SMC **M-5ALU-4** barb elbow (M5 thread, for 4 × 2.5 mm urethane tube), tube toward +Y. [Likely] SMC's part page lists A 13.3, B 9.3, hex 7. I read B as the height above the port face, because A − B = 4 for every size in that table (the thread length). [Guessing] where the barb arm sits.
  - Its top at full stroke is c+136.8, 3.2 mm under the lens.
- **Rechecked:**
  - trip 2.00 mm;
  - label view while reading 0.0 mm³;
  - stop and fitting vs foot, sensor, arm and camera over 0-20 mm: 3.2 mm (was 5.97);
  - Phase 0 push over 0-20 mm: 3.0 mm.

**1, pad vs buffer body: confirmed and fixed.** My repro on the old model: distance 0.000 at 14.0 mm, overlap 100.5 mm³ at 14.5 mm, 1608.5 mm³ at 25 mm.
- With the real geometry, the pad's hex top (23 above the pad face) is 21.5 mm below the body bottom (44.5), against a 20 mm stroke.
- New check, pad vs buffer body over 0-20 mm: **1.5 mm** at 20 mm.
- The hard-stop check now subtracts CUP_HANG, in both layout.py and checks.py. It reads 4.0 (was 11.0, which over-counted by 2 mm even before).

**2, Phase 0 face-up lift: confirmed and fixed.** Repro: head_foot vs mount overlap 285.4 mm³ at +10.
- The jig now matches a buildable setup: the cup rests on the slab and is pushed up the 2 mm trip travel, so the foot's underside is 62.0 above the slab back. This also removes the old 2 mm gap between the CAD jig and the "free cup on a 0.5 mm gauge" procedure.
- Jig vs machine: offset 0.0 mm and 0.0 % (was 0.5 mm and 0.09 %).
- Face-up pass: slide the **mount**, with the stub clamped in it, up `P0_FACE_UP_LIFT = 3 mm`. The free cup then hangs 1.0 mm above the slab's front.
- The stub is 66 mm, not 70, so its top stays 8.4 mm under the bridge (5.4 mm when lifted). The faces that share Y = 25 never meet.
- New checks:
  - lifted jig, interference: 0.0;
  - free cup above the front: 1.0;
  - pushed 0-12 mm to change a slab: 3.16;
  - pushed to the buffer's end: **0.2 mm**. No contact, but thin, and it depends on the [Likely] 9.3 mm fitting height.
- [Certain] Sliding the stub inside a fixed mount still fails: the sensor post (c+107.5) meets the mount beam (c+110) after 2.5 mm, or 1.75 mm with the board at its top slot end.

**3, washer vs sealant: confirmed and fixed.** I chose sealant only, which is the CAD as built.
- The tab sits directly on the port hex and the elbow sits on the tab, with the elbow's own gasket on top of the tab.
- Thread: 4.0 mm [Likely], so 3.0 mm (3.75 turns) is engaged through the 1 mm tab. The stack needs at least 3.4 mm of M5 thread.

**4, the lens-setting budget: confirmed and fixed.**
- Blade lengthened downward: guide depth at full stroke is 8.0 (was 4.0). Below the foot the blade stays hidden from the camera and clear of the buffer.
- Board slots ±2.5 → ±4.0; post top 107.5; fin tops 91.25.
- New sweep: buffer moved ±3 mm on its thread, board re-slid to keep the trip, lens following the cup:
  - slot travel spare: 0.5 mm;
  - guide depth at the +3 shift: 5.0 mm;
  - worst flag margin over its limits: 0.15 mm (the guide slot);
  - stop, fitting and pad clearance: 1.5 mm.

**6, TCST2103 dimensions: confirmed and fixed.** [Certain, Vishay doc 81147 p.5, drawing 6.550-5040.01-4, rendered myself]
- Optical axis 2.6 below the arm tips, slot 7.7 deep, flange 3.1.
- The aperture is modelled as a 1.0 mm slit (along the travel) running 3.8 mm down from the tips.
- Blade outer edge 19.4: that covers the slit with 1.5 mm to spare and clears the slot bottom (X 21.8) by 2.4 mm.

**7, key access: confirmed.** Old repro: a straight key hits vac_fitting (44.5 mm³).
- With the new parts, a straight key into the front screw hits the buffer's neck and hex (33.2 mm³).
- Tilted toward the label: 10° clears by 0.24 mm, 15° by 1.24, 20° by 1.15.
- The holes cannot move: they are the sensor's own flange holes, 19 mm apart and symmetric about the slot. So the fix is a 2.5 mm ball-end key.
- New checks: front screw, ball-end key at 20°: 1.15 mm; rear screw, straight key: 1.54 mm.

**Check semantics I changed.** The label-view checks now follow when the camera reads. [Likely, runner.py around lines 744-788] it reads at hover and with the slab held, buffer extended.
- Every moving part over 0-2.5 mm: 0.0 mm³.
- Flag and stop to the end of a probe, 0-14.5 mm: 0.0 mm³.
- The old "whole stroke" version would now fail. [Likely, my hand estimate] the port hex enters the label view past about 17 mm and the elbow past about 9 mm.

## For the docs agent
- **BOM.csv** (CRLF):
  - cup + buffer: ZPT25UUK20-B5-A10. Delete the K25/J25 codes and the "fallback K20" wording. [Certain] ZPT25UUJ20-B5-A10 also works with the guide.
  - Buffer-port fitting: SMC M-5ALU-4 barb elbow on 4 × 2.5 mm PU tube, no sealing washer, thread sealant on the fitting's thread.
  - Flag stock: 1 mm sheet, at least 25 × 56 mm.
  - Phase 0 stub: 66 mm.
- **§3.3 measure-first rows** (replace the "16 mm above the foot" row):
  - pad face to port top 108.5;
  - pad face to body bottom 44.5;
  - body 51;
  - free gap between the pad hex and the body: 21.5;
  - port top 31.5 above the foot top at rest;
  - fitting at most 9.3 mm above the tab, with a thread of at least 3.4 mm.
  - Drop the TCST guess rows. Keep the board-layout rows.
- **§7.5:**
  - The 140 mm is from the lens to the pad face pushed up 2 mm (142 to the free pad face).
  - Do the flag fitting and trip setting after step 5.
- **§7.6:**
  - tab on the port hex, no washer, sealant on the thread;
  - tube toward +Y;
  - use the new probe_flag.png and probe_closeup.png;
  - step 8: ball-end key at 15-20° from the label side for the front screw.
- **§1.5:**
  - set the foot's underside 62.0 mm above the slab back (or lower until the probe trips);
  - for the face-up pass, slide the mount, not the stub, 3 mm up the post;
  - push the cup only as far as a slab change needs (up to about 12 mm).

## Outside my files (software)
- simworld.py `BUFFER_STROKE = 25.0` → 20, and the config.py comment "(25)" → 20.
- tools/phase0.py docstring: the face-up pass slides the mount up 3 mm.
- sim.py `HEADS["cad"]` is stale. New boxes, above c at the trip:
  - pad ±14, 0-4 / hub ±7, 4-14 / pad hex ±4.6, 14-23;
  - rod ±3, 23-42.5;
  - body ±5, 42.5-93.5;
  - nuts ±8.1 at 59-62 and 75-78;
  - neck ±4, 95.5-103.5 / port hex ±4.6, 103.5-108.5;
  - fitting ±4.04, 109.5-118.8, with arm (X ±2.25, Y 0-12, Z 112.75-117.25);
  - sensor post (26.5, −9.5, 30.5, 24.5, 75, 107.5);
  - fins (11, 4.05, 24.4, 10.95, 75, 91.25).

## Not verified
- No real part was measured.
- Which M-5ALU-4 dimension is the height is [Likely] only.
- [Guessing] that the neck rises with the rod, the rod and hub diameters, and the barb arm's layout.
- [Guessing] the tube on the barb runs about 1 mm under the LED ring at full stroke. Not modelled, since flexible parts are not checked.

Files (all under ):
- cad/: layout.py, model.py, checks.py, build.py, render_docs.py
- cad/out/: checks.txt, cut_list.csv, probe_flag_blank.svg, probe_flag_blank.dxf, printed/*, assembly/slabrail_home.step
- docs/img/*.png: every image re-rendered; probe_closeup.png, probe_flag.png and phase0_jig.png checked by eye