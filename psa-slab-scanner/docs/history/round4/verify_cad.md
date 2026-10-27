{
 "verdict": "issues",
 "issues": [
  {
   "severity": "medium",
   "area": "cad",
   "problem": "[Likely] The CGC window margins (+0.26 mm top edge, +0.45 mm side) are not real margins. The checks.py card model leaves out three things, and all three push the window off the card. (1) layout.CARD_W is 63.5, a sports card. The backs were measured and scaled as 63.0 x 88 Pokemon cards. (2) The card corners are rounded, about 2.7 mm radius. (3) The card lies about 3.5 mm under the slab back, but the window is mapped on the slab back. At the window's label-side edge (7 deg off the lens axis) that parallax is 0.3-0.45 mm. In the stacked worst-case CGC slab, about 1-5% of the window lands on the holder instead of 0%.",
   "evidence": "scratchpad/round4/verify_cad/cardedge.py, worst-case CGC slab, card 63.0 mm, corner radius 2.7 mm. In air (upper bound): 13.9 mm2 off the card (4.6%), top edge -0.18 mm, side -0.45 mm. In plastic (n 1.49): 5.1 mm2 (1.7%), top -0.04, side -0.24. With CGC's published 80.0 mm width (CGC_W=80.0): 1.2-4.1%. The CAD model's own numbers come out at +0.26 / +0.45. Corner radius: traced on the card's top-right corner of fc_6048568036_1.jpg (meas/c6048_corner.png); the edge leaves straight about 3 mm from the corner. The real-image A/B used flat studio scans, so it has no parallax either. PSA keeps a positive margin in every case (top +3.24 or more, side 0.0 or more).",
   "fix": "In checks.py check_face_down_window and check_camera_aim, test the window on the card plane: grow the rectangle about the lens foot by (147 + card depth / n) / 147, use a 63.0 mm card, and clip with the corner radius. Report the real worst case. Area does not allow shrinking the window (x +/-27.0 gives 297 mm2), so the docs should say 'about zero margin; up to a few % of the window on the holder for a CGC slab pushed into a pocket corner', not +0.26 / +0.45 mm."
  },
  {
   "severity": "low",
   "area": "cad",
   "problem": "[Certain] The aim tolerance is 1.31 deg by the software's own mapping, not 1.34 deg. check_camera_aim builds its frustum with the apex at lens - 0.5 and the base at the slab + 0.5. So it places the camera-axis window 146 mm from the apex, but runner._hover_mm maps it at 147 mm. The rays at the cup-side edge come out 0.034 deg wider, away from the cup. It still clears the 1.25 deg floor.",
   "evidence": "My own ray cast (scratchpad/round4/verify_cad/rays.py: tessellated parts, Moller-Trumbore, not the frustum code) gives +Y (cup) 1.310 deg with the 147 mm mapping, and 1.344 deg when I map the window at 146 mm the way checks.py does (aim_146.txt). The cup comes into view first in both. Diagonals come in at 1.85 deg. -Y, +X, -X and roll are all past 4 deg.",
   "fix": "In check_camera_aim, put the base rectangle at x*146/147, y*146/147 (or the apex at lens.z and the base at top). Quote 1.31 deg in BUILD_GUIDE, DESIGN and the AIM_HEAD_FLOOR comment."
  },
  {
   "severity": "low",
   "area": "cad",
   "problem": "[Likely] The 0.0% ring-glare figure only holds for a slab back square to the lens. The mirrored band ends 2.97 mm from the window, so the margin past the 2 mm halo is 0.97 mm. A slab tilted 0.45 deg toward the label brings the halo into the window. At about 0.77 deg that slab's frames stop becoming references (over 2%).",
   "evidence": "scratchpad/round4/verify_cad/glare_tilt.py uses the CAD's flat-mirror band (r 7.53-10.03 mm round (0,-5)). The reflection moves H*tan(tilt). Masked share: 0.3% at 0.5 deg, 1.9% at 0.75, 4.2% at 1.0, 10.1% at 1.5, where the saturated core is 1.6%.",
   "fix": "No CAD change needed now. Tag the glare check [Likely, square slab]. Add a Phase 0 step: on a full stack of 30, check how often face-down frames are refused as references because of glare."
  },
  {
   "severity": "low",
   "area": "cad",
   "problem": "[Likely] The head ring seat only takes a ring of 41.0 mm OD or less. No 40 mm COB ring is in hand yet: the only sourced listing has ended, and Amazon's 40 mm rings are 12-SMD. The station ring already shows that 'nominal' ODs can run 5% over (a '60 mm' ring measures 63). A 41-42 mm '40 mm' ring would not fit. The thickness is [Guessing] too. The lip fixes the ring's back face, so an 8 mm ring would sit 3 mm lower and bring the barb clearance back to 0.75 mm.",
   "evidence": "seats.py probes the solids with test cylinders. Head bore: 41.0 mm clear, 41.1 mm cuts camera_bracket by 29.7 mm3. Lip: 33.0 clear, 33.1 cuts. Station bore: 64.0 clear, 64.1 cuts. Sourcing: electronics.json line 65 says 'ring ID not stated'. Web: one forum report gives 40 mm OD / 31 mm ID, which fits the 30 mm ID assumption. The ring is 10.0 mm from the drop arm, so a larger bore has room.",
   "fix": "BUILD_GUIDE 3.3 and BOM item 3: measure the ring's OD, ID and thickness, set model.HEAD_RING, then re-export camera_bracket and phase0_top before printing. Or open the head bore to about 42.5 mm with a crush rib or glue dots, as the station seat does for 60/63 mm rings."
  },
  {
   "severity": "low",
   "area": "cad",
   "problem": "[Certain] phase0_top leaves only a 1.23 mm web between each M2 self-tapping standoff hole and the new ring pocket, over a 2.6 mm height. A self-tapping screw can split it or bulge it into the pocket, and the ring has only 0.5 mm of radial play.",
   "evidence": "model.phase0_top: holes are 1.8 mm diameter at (+/-16, ly+/-16), 22.63 mm from the lens axis, and run from z 2 to 8. ring_pocket's bore is 41 mm diameter up to local z 4.6. 22.63 - 0.9 - 20.5 = 1.23 mm.",
   "fix": "Use heat-set inserts or tap M2 instead of self-tapping. Or move the jig's standoff holes outward (the board allows 32 mm only, so instead thicken: make the pocket blind with 1 mm less depth, or add bosses on top). At minimum, add a BUILD_GUIDE note: drive the M2 screws gently and check the ring still drops in."
  },
  {
   "severity": "low",
   "area": "cad",
   "problem": "[Certain] There are now two sets of PSA card-position data, and they disagree. heads_cad.json still exports card_top_from_label_edge_mm 34.8/36.1/37.8 (CARD_TOP_FROM_EDGE, read by sim.py). The new holders.PSA top_to_far 97.18/98.68/99.95 at 135.5 mm gives 35.55/36.82/38.32 from the label edge: 0.5-0.7 mm different. render_docs face_down_view draws the 'median PSA card' from the old median as a 63.5 x 88.9 card. layout.py's HOLDERS comment says CGC has '2.8 mm of play', but the code and checks give 2.55.",
   "evidence": "layout.py lines 187-197; build.py line 258; render_docs.py line 153; checks_full.txt line 58 ('2.55 mm play').",
   "fix": "When the software test is updated, derive CARD_TOP_FROM_EDGE (and the sim's per-grader range) from HOLDERS. Draw the doc card from HOLDERS at 63 x 88. Fix the comment to 2.55 mm."
  },
  {
   "severity": "low",
   "area": "docs",
   "problem": "[Likely] 'CGC holders are shorter: about 133.9 mm' should not go into the docs as a fact. CGC's FAQ gives about 3.15 x 5.30 in (80.0 x 134.6 mm). Most CGC scans are cropped 3-23 px from the slab edge, cutting the blurred outer rim. So the measured length and width (133.9 x 79.4) probably read short. card_top_worst uses the far edge, so it is unaffected, or conservative if a rim is cut. The real CGC play is likely about 2.2 mm in Y and 2.0 mm in X, not 2.55 / 2.30.",
   "evidence": "dfar_all.txt: far edge found 3-23 px inside the image on most CGC scans. CGC Help Center general holder FAQ: '~3.15 x 5.30 inches'. With CGC width 80.0, the CGC side margin in the CAD model rises from 0.45 to 0.75 mm.",
   "fix": "RESEARCH, BUILD_GUIDE and DESIGN: give the card top's distance from the far edge (93.8-96.2 mm, measured), and say the length and width are from cropped scans, with CGC's published approximate size next to them. Keep HOLDERS' top_to_far as the design input."
  },
  {
   "severity": "low",
   "area": "software",
   "problem": "[Likely] The face-down acceptance numbers (103/126) slightly overstate CGC, and SEARCH_MM no longer covers the play the CAD now reports. The A/B placed slabs +/-2 mm, but HOLDERS gives CGC +/-2.55 mm of Y play and about 2.4 mm of card-in-holder spread. The facedown.SEARCH_MM = 4 comment assumes +/-2 mm per slab. Two face-down CGC slabs can differ by more than 4 mm, so some will only match with fewer aligned references.",
   "evidence": "round4cad/window_ab.py (placement +/-2 mm); slabscan/facedown.py line 74 comment; layout.HOLDERS CGC.",
   "fix": "Software owner: re-run window_ab with CGC placed +/-2.55 mm. Consider SEARCH_MM 5 in Y, or per-axis search, and re-check the face-up maximum against the 0.55 floor."
  },
  {
   "severity": "low",
   "area": "software",
   "problem": "[Certain] The CAD report's software test count is already out of date. On the live tree the two affected files now give 4 failures, not 5. The foot_y-12.35 case has since been re-tuned and passes. The other four failures match the report and still show the stale 632 mm2 default window.",
   "evidence": "cd software && python3 -m pytest -q -p no:cacheprovider tests/test_carry_sensor.py tests/test_face_down_learned.py -> '4 failed, 56 passed in 351.37s (0:05:51)': test_a_face_down_old_label_passes_once_enough_qr_references_exist, test_the_reference_file_persists_across_runner_instances, test_glare_is_masked_and_keeps_a_frame_out_of_the_references, test_phase0_sim_reports_the_separation. The phase0 output shows face_down_window_mm [[-27.5, -22.5, 27.5, -11.0]] = 632 mm2. The CAD report said '5 failed, 44 passed in 346.91s'.",
   "fix": "Software owner: regenerate config.py and machine.toml with gen_config, re-tune the static_fraction and glare asserts, then run the full suite."
  }
 ],
 "checked": "The CAD changes hold up in substance. Rings seated, no interference at any pose, both camera views clear, and the conclusion that 1.5 deg is out of reach is right. Two numbers need correcting before they go into the docs. The CGC \"+0.26 / +0.45 mm\" card margins are really about zero. The aim tolerance is 1.31 deg, not 1.34. Neither one blocks the change.\n\nFull CAD run [Certain]. cd cad && timeout 3000 python3 checks.py gave \"layout checks: OK\", \"154/154 checks passed\", exit 0, real 5m58.052s (round4/verify_cad/checks_full.txt). The output is byte-identical to the CAD agent's checks_final.txt and to cad/out/checks.txt, except for the trailing exit line. Compared with bb25f49's 128/128, every earlier check kept its value except these: the window clearances (0.86->1.74, 1.03->1.94), area (632.5->302.5), label band (7.0->11.0), head aim (0.56->1.34), and the replaced card-edge and aim-on-card rows. Then 26 new ring and window rows. No CAD source changed while I worked (mtimes checked).\n\nAim, exact check [Certain]. I wrote my own ray caster (rays.py: tessellated parts, Moller-Trumbore), separate from the frustum code. Toward the cup it gives 1.310 deg with the software's 147 mm mapping, cup first. It reproduces 1.344 deg when I map at 146 mm the way checks.py does. Diagonals come in at 1.85 deg. -Y, +X, -X and roll are past 4 deg.\n\nThe 1.5 deg claim holds. A shadow map shows head_foot's edge at y = -14.0 across the full width; only the cup dips to about -14.6, at |x| < 4. A three-rectangle window that uses that strip (303.4 mm2) reaches 1.464 deg. At exactly 1.5 deg the most you get is about 298 mm2.\n\nRings in the views [Certain]. With the rings in place, 0 of 3756 window rays are blocked at hover over stacks of 1, 15 and 30. 0 of 7301 label-view rays are blocked at c = 248 with a held slab.\n\nSeats, probed on the solids [Certain]. Head bore 41.0 mm, lip 33.0 mm, station bore 64.0 mm. The shelf supports the band of both a 63 x 47 and a 60 x 46 ring. The jig ring sits 0.0 mm off the machine's. The barb clears the ring by 3.75 mm at 20 mm of stroke. camera_bracket's bounding box is unchanged (48 x 76 x 26), so it keeps clearing the carriage over the Z travel [Likely]. Print list total is 768.3 cm3, which matches the report.\n\nRing sizes vs sourcing. The CAD values match the sourcing notes: head listing \"40MM 24leds COB\" (ended, ID not stated); station Everbright 60 mm, with one listing measuring ~63 x 47. One forum report gives 40 OD / 31 ID [Likely]. I found no thickness data.\n\nReal backs, re-measured [Likely]. I measured every good studio back a second way: d_far = 88 + (card bottom to far edge). I checked edges by eye on crops of fc_6048568036 and fc_6070184051. CGC minimum is 94.18 (CAD: 93.76), so the CAD figure is about 0.4 mm on the safe side. On the Japanese back fc_6070184051, the CAD's card box took in the holder's ridge, putting its d_far 1.3 mm low (safe side). Three tiny CGC values were artefacts: two cropped AUTH scans and one dark-holder saturation. The CAD agent excluded them correctly. PSA minimum is 96.29, on fc_18805593, which the CAD set left out. That would cut the PSA top margin from 3.68 to about 2.8 mm, which is harmless. I confirmed the window formulas: worst card tops -23.76 (CGC) and -27.18 (PSA); side limits 27.95 and 28.4. The A/B logs explain both acceptance figures: 113->103 is the +/-2 mm run, 116->101 is the worst-position run. The A/B frames include the CAD head shadow.\n\nSoftware (two files, live tree) [Certain]: \"4 failed, 56 passed in 351.37s (0:05:51)\". I did not run the full software suite.\n\nAll my scripts and outputs are in scratch/round4/verify_cad/ (rays.py, aim.txt, aim_alt.txt, aim_146.txt, views0.py, seats.py, cardedge.py, glare_tilt.py, dfar_all.py, dfar_all.txt, checks_full.txt, sw_two_files.txt, meas/). Nothing was written to the repo, and no git state changed."
}