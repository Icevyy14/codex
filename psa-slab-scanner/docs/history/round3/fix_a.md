The aim issue can't be fixed in CAD. No fixed card window survives the 0.5–2° aim error the verifier guessed, so I only fixed issue 1 in geometry. For issue 2 I added a check that tracks the aim margin, and the actual fix belongs to the software owner. `cad/checks.py` passes **128/128** (5m27s). Four software tests now fail because of my layout change; all need software-side edits.

**Issue 1: carry sensor has one edge at 235 — real, fixed**
- [Certain] Reproduced from the old layout. The trip was at 235 and loaded travel at 248. A head that stalled between about 235 and 248 still read blocked, and a double thick pick at 235 sat 12 mm below the rod tops. The verifier's correction holds: with the ±1 mm band, a single thick holder clears by 2.5 mm, not 3.5.
- Changes in `cad/layout.py`:
  - `C_SAFE_EMPTY = C_SAFE_LOADED` (248).
  - `CARRY_SENSOR_C0 = C_SAFE_LOADED - 1.5` (246.5).
  - New `CARRY_BAND = 1.0`, equal to the software's `CARRY_BAND_MM`.
  - The old `layout.check` rule is replaced by two: the sensor must read blocked at both travel heights, and the highest stall it can miss must still leave a double thick pick at least 2 mm over the rods.
- `cad/model.py`: comments only. The beam now sits at 561.5 and the flag (`CF_LEN` 36) has 20 mm spare. Flag and arm are unchanged, so the cut list is unchanged.
- [Certain] Check results:
  - Trips at 246.50.
  - Clear from −14 to 242, fully blocked from 248 to 262.
  - Flag to sensor 1.05 mm, arm to carriage 4.6 mm, lead 11.0 mm.
  - New check: a head at 245.5 (lowest that may still read blocked) carries a double pick 2.5 mm over the rods.
  - Empty travel clearance rose from 21.9 to 33.4.
- [Certain] The software sim shows the change works. A 10 mm Z loss on a lift is now caught "before moving sideways over pocket 3 … Nothing moved sideways", instead of after the carry.
- A small disagreement: "any loss over ~1.5 mm reads clear" is only nominal. It is guaranteed only for losses over 2.5 mm, because of the band.
- [Likely] The time cost is the verifier's sim figure (14.0 → 14.2 s/slab). I did not re-run the 330-slab sim.

**Issue 2: camera aim — real, not fixable in CAD; instrumented**
- [Certain] My own numbers (frustums turned about the lens, plus the card corners) match the verifier's:
  - Head parts: 0.56° toward the cup (cup pad first); over 4° in every other direction.
  - Card, median slab centred: 1.57° toward the label, 1.59° sideways.
  - Card, worst-case slab: 0.08° toward the label, and **0.34° sideways**. The verifier missed the sideways edges.
- [Certain] Share of the window hidden by head parts, from a ray cast, by aim error toward the cup:

| Aim error | 0.6° | 0.75° | 1.0° | 1.25° | 1.5° | 2.0° |
|---|---|---|---|---|---|---|
| Window hidden | 0% | 0.4% | 5.0% | 11.3% | 17.7% | 28.7% |

- I disagree with "nothing on the machine calibrates that". `facedown.learned_ready` already refuses learned mode when more than `STATIC_MAX` (10%) of the window moves with the camera. That turns aim errors above about 1.2° into a safe refusal.
- The real gap is between about 0.6° and 1.2°. There a head edge covers 0.4–10% of the window and learned mode stays on. `config.py` notes that face-up sim scores reach 0.52 with a head edge 1 mm in, against a 0.55 floor.
- [Certain] Why I did not change the window:
  - The space between the worst-case card top (−27.7 mm) and the cup-pad shadow (−14.59 mm) is 13.1 mm. The window is 11.5 mm tall, so the total slack is 0.62°.
  - A window that tolerates ±1° would be 438 mm², 31% smaller.
  - ±1.5° would give 298 mm², under the 300 mm² `MIN_WINDOW_MM2`.
  - Changing the window would also break the face-down tests tuned to it.
- What I added: `check_camera_aim()` in `cad/checks.py`, three records. Head parts and the median card have a 0.5° floor; the worst-case slab is reported for information only.
- Software fix to hand off:
  - Extend the existing camera-locked pixel map to a band of at least 1.5 mm around the window. Refuse learned mode, or shift the window rectangles in pixels, if anything falls in that band.
  - Check the card top on the first proven slabs.
- Mechanical option: the existing bracket can already be shimmed. [Likely] One 0.3 mm M2 washer under one pair of the 32 mm-spaced board holes tilts the board about 0.54°.

**Software suite (snapshot; other agents were editing at the same time)**
- Run 1: `10 failed, 242 passed, 1 skipped in 670.56s`. Run 2: `7 failed, 252 passed, 1 skipped in 733.72s`.
- 4 failures are mine; each passes with the old layout loaded:
  - Three tests in `tests/test_carry_sensor.py` that pin the old numbers: `test_a_small_z_loss_on_a_loaded_lift_is_caught_before_the_slab_goes_down`, `test_selftest_motion_measures_where_the_carry_sensor_trips` (now "trips at about 246.38 mm (set 246.5"), and `test_config_takes_the_sensor_stroke_and_window_from_the_cad` (`carry_sensor_c0=236.0` is now valid; it needs 247.5 and "travel height 248.0 mm").
  - `test_runner_sim.py::test_thick_holder_is_handled`. The survey's probe steps now end at 20.0 mm, 0.008 mm above pocket 9's stack (19.9924), so the sim raises ProbeFailInitial. This is a real edge case in `runner._find_top`: next step needs a small overlap, or an immediate trip must be accepted as contact.
- The other 3 failures in run 2 passed when I re-ran them on the current layout, so they came from concurrent edits.
- Other software follow-ups:
  - `config.py` defaults: `c_safe_empty` 236.5 → 248, `carry_sensor_c0` 235 → 246.5.
  - The `runner._descent_plan` pause (now at 247.75) is redundant, and its docstring is stale.
  - `machine.toml` was already regenerated by another agent at 21:25 with 248/246.5. I did not touch it.
- Docs follow-ups (not my files):
  - `CONTRACT.md:25` still says `C_SAFE_EMPTY = 236.5`.
  - `BUILD_GUIDE.md` has no carry-sensor section, although `config.py` cites §7.4a.
  - `BUILD_GUIDE.md:443` and `DESIGN.md:137` say nothing detects a Z stall.
  - `BUILD_GUIDE` §7.7 says "lens … on the cup axis"; it now sits 5 mm toward the label.
  - `BUILD_GUIDE` §1.7 says "they lie on the foot", and its flipped window `[[-28,17,28,33]]` is stale. [Likely] It should be `[-27.5, 11.0, 27.5, 22.5]`.

**Exports and renders**
- Re-exported `cad/out/heads_cad.json` (`CARRY_SENSOR_C0` 246.5), `cad/out/assembly/slabrail_home.step` and `cad/out/checks.txt`.
- The 23 printed STLs are byte-identical, so I did not re-export them.
- Re-rendered `docs/img/` carry_sensor, storyboard_1–4, storyboard and machine_iso/machine_front. head_closeup and station_read came out unchanged. I fixed the carry_sensor caption, which showed "244" for 244.5.

Files changed, all under ``:
- `cad/layout.py`
- `cad/model.py`
- `cad/checks.py`
- `cad/render_docs.py`
- `cad/out/checks.txt`
- `cad/out/heads_cad.json`
- `cad/out/assembly/slabrail_home.step`
- `docs/img/carry_sensor.png`
- `docs/img/storyboard.png`
- `docs/img/storyboard_1_loaded.png`
- `docs/img/storyboard_2_first_transfer.png`
- `docs/img/storyboard_3_midway.png`
- `docs/img/storyboard_4_done.png`
- `docs/img/machine_iso.png`
- `docs/img/machine_front.png`

Evidence is in `scratch/round3/cadfix/` (`checks_full2.txt`, `suite.txt`, `suite2.txt`, `aim_proto.py`, `aim_card.py`, `aim_fraction.py`).