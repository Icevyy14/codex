I fixed all six issues, but one gap is left: the software does not detect a head edge about 1 mm inside the card window. **[Certain, sim]** With the foot edge there (y0=-8), the occlusion check reads 0–1% and the highest face-up score rises from 0.37 to 0.52. At a threshold of 0.50, 2 of 300 face-ups were accepted. I raised the threshold floor to 0.55 because of this. The real fix is still the CAD frustum check, which I can't add because cad/ is not mine.

All six issues reproduced on the code as I found it, using the verifier scripts.

## The six issues
1. **Empty-pocket guard (high) – real, fixed.** Switching the guard to pattern similarity alone was not enough. **[Certain, sim]** With y0=-11 (40% of the window hidden), that guard reads only 0.10, while face-up-vs-back scores 0.55. The foot edge has the opposite contrast over an empty pocket.
   - Guard: now pattern similarity only. y0=-13 now reads 0.57 and y0=-15 reads 0.56 (limit 0.5), so both are refused. The open head reads at most 0.44.
   - New occlusion check: across 5 or more slabs proven on this machine, a pixel counts as "moves with the camera" if it matches the empty view in brightness ratio. Learned mode is refused above 10% of the window.
     - In the simulator: open head 0.00; y-10 29%; y-11 41%; y-11 with a foot as dark as the empty pocket 41% (same under ±25% auto-exposure); the CAD head without the nut 100%.
     - Phase 0 jig references alone never activate it.
   - Threshold tag: `face_down_threshold_sig` is a hash of the window and descriptor. A threshold with a missing or different tag is not used.
   - Re-run of the verifier's end-to-end script: y0=-13 gave 0 references and 20/20 face-ups stopped; the CAD head without the nut gave 20/20 stopped (the occlusion check refuses at 100%). Before the fix these were 18 and 16 crashes.
2. **Poisoned reference file (high) – real, fixed.**
   - Face-down stops are journaled with their pocket and reason. `--face-down-ok` (command line and web) is refused unless the last stop was a face-down stop, and it confirms only that pocket's top slab.
   - The web tick only appears for such a batch, and it is cleared after each resume and when you pick another batch.
   - An operator reference is learned only after the slab is placed. It is not learned if the read station sees a PSA back-label QR from below. Its cert and back photo go in the journal.
   - A back design known only from operator confirmations is matched once 3 confirmations agree.
   - New `refs [--drop CERT | --drop-operator]` command to list or delete references.
   - Verifier repro, round 2: the resume is refused and nothing moves. A new test shows a wrong front reference no longer passes the next face-up copy.
3. **Plain front with glare (medium) – real, fixed.**
   - A match now needs at least half the matched back design's own texture (simulator backs 19–26, plain front with glare 7–8).
   - Saturated glare is masked; frames with more than 2% glare never become references.
   - Phase 0 now asks for a plain and a full-art card (the simulator uses a plain one).
   - Result: 0 of 150 plain fronts accepted at 0.60 (was 1).
4. **Phase 0 threshold (medium) – real, fixed.**
   - A back that matches none of the others is named and left out of the threshold and the seed file.
   - A GO now needs 15 face-up slabs, and the threshold is the midpoint but never below 0.55. The config refuses anything lower (0.01 included).
   - The verifier's Japanese-outlier case now gives threshold 0.57 with 0/300 face-ups accepted (was 0.36 and 1/300).
   - Open head, 300 simulated Phase 0 runs (measured with the floor still at 0.50): all GO, thresholds 0.54–0.57, 0 face-ups accepted.
5. **`KeyError: 'src'` on resume (high) – real, fixed.** The learned event now uses `"position"`, and rebuild_state only treats events with both `"pos"` and `"src"` as transfers. The repro (old label learned at 0.97, then a face-up stop) now resumes and finishes all 8 slabs.
6. **Phase 0 report lost on Ctrl-C (medium) – real, fixed.** The read-rate report is written as soon as you type `q`. Ctrl-C or end-of-input during the face-up pass counts as skipping the rest, and `--face-up` now defaults to 0. Repro: the report now exists.

## Verified
- **Full suite:** `189 passed in 617.20s (0:10:17)`. That is the 155 older tests, 33 in test_face_down_learned.py and one new web test.
- **330 slabs, seed 7:**
  - CAD head: 49 stops, 0 learned. Unchanged.
  - Open head: 281 by QR, 48 learned, 1 stop. Unchanged, but the lowest learned score dropped from 0.88 to 0.69 because glare is now masked.
  - Both: 14.0 s per slab, 78.2 min, 991 head frames.
- The web page logic was exercised in node with a stub page. machine.toml did not need regenerating.

## Not verified
- **[Guessing]** The occlusion check assumes the empty pocket looks clearly different from a card and that auto-exposure changes all head parts by one common factor. Neither has been seen on real hardware.
- **[Guessing]** The glare level (245) and the texture ratio (0.5) are tuned on the simulator only.

## For others
- **CAD agent:** add a `checks.py` frustum check at hover. Rays from the lens, 147 mm above the slab, to the window grown by 2 mm (x ±30, y −35 to −15 from the cup axis) must clear every head part. The software cannot see an edge 1 mm inside the window.
- **Next software round:** `sim.HEADS["cad"]` in software/slabscan/sim.py still models the old buffer and foot. The CAD working copy has changed them (20 mm stroke, new nuts). Re-derive it once the head is settled.
- **Docs agent:**
  - BUILD_GUIDE §1.7: change `--face-up 5 --save` to `--face-up 15 --save`, include a plain and a full-art card, and mention the outlier lines. §11.5: add `face_down_threshold_sig`.
  - OPERATING: `--face-down-ok` is for the stopped slab only; the web tick shows only after a face-down stop; operator references are learned after placement and need 3 confirmations; the `refs` command; the new stop reasons.
  - CONTRACT: the `refs` command, `--face-up` defaulting to 0, and the journal events `face_down_stop`, `face_down_reference`, `face_down_ok_unused`, plus `"position"` replacing `"pos"`.
  - DESIGN: update the list of safety layers.

I edited these files under software: slabscan/facedown.py, runner.py, cli.py, config.py, web.py, sim.py, simworld.py, tools/phase0.py, tests/test_face_down_learned.py, tests/test_web.py and README.md. I ran no git commands that change state. The adapted repro scripts and their outputs are in scratch/after/.