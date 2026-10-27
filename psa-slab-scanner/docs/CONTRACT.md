# Interface contract (single source for docs, firmware, wiring and software)

Every document and file must agree with this page. If something here is wrong, fix it here first.

## Machine: SlabRail
- **Layout:** one straight row of 14 cells, 92 mm pitch, centres at X = 42 + 92·cell.
  - Cell 7 (X = 686) is the read station: an upward camera, no stack.
  - The other 13 cells are pockets 0–12, left to right.
    - Pocket 0 starts empty.
    - Pockets 1–11 hold up to 30 slabs each (330 total).
    - Pocket 12 is the exception pocket.
- **Run order:** stack k is moved slab by slab onto pocket k−1, so every stack ends up one pocket to the left. Each slab is read on the way.
- **Loading rules:** slabs go in **face-down**, with the **label end toward the front** (toward the operator).
- **Sizes:** pocket interior 84 × 139 mm.
  - Guide rods are 8 mm hardwood dowels in the CAD (`ROD_D`); the BOM buys 5/16 in (7.94 mm). They stand 218 mm tall above the pad.
  - The fill line (MAX) is 210 mm.
  - An overfill laser beam runs at 214 mm along the row centre line.
- **Axes (only two):**
  - **X:** belt-driven, GT2 20T pulley, 40 mm/rev, 80 steps/mm at 1/16 microstepping, on an MGN12 1300 mm rail on a 4040 beam.
  - **Z:** NEMA17 (1.5–2.0 A/phase, ≤ 4 mH, ≥ 40 N·cm) with an integrated T8×8 lead screw (8 mm lead), 400 steps/mm at 1/16, on an MGN12 330 mm rail on a 2040 spine.
    - **The screw is cut to 340 mm below the motor face** (311–356 mm works). The screw tip is fixed to the X carriage right over the held slab (X +24, Y 33 from the cup axis). Cut to 340 it ends 283 mm above the pad, above everything the head carries. A 400 mm screw left uncut ends near 223 mm [Likely: integrated screws are usually measured from the motor face], so every lift would drive the held slab's back into its tip, and the tip would pass only 5 mm over the rod tops. [Certain, CAD `Z_SCREW_LEN`, `Z_SCREW_TIP`]
- **Work coordinates:**
  - X = the cup axis position in layout mm.
  - Z = the cup-face height "c" above the pad top.
  - Key heights: C_SAFE_EMPTY = C_SAFE_LOADED = 248, C_MAX = 250, STATION_READ_C ≈ 171.6,
    CARRY_SENSOR_C0 = 246.5 (the carry-height sensor's trip, read as ± 1 mm, `CARRY_BAND`).
    They include CUP_HANG = 2: the free cup hangs `buffer_trip_mm` below its trip-calibrated
    height. A measured `buffer_trip_mm` above 2 raises both travel heights by the difference
    (`config.load`), and one that would put loaded travel above C_MAX is refused. The carry
    sensor's trip must sit at least 1 mm under both travel heights (`config.check_heights`).
  - Hard stops and switches (CAD): Z bottom hard stop c = −14 (`z_end_cap`), Z top switch trips at c ≈ 258, Z top hard stop c = 262 (`z_plate` meets `z_motor_mount`). X hard stops at cup X 15 (`x_bumper_L`) and 1262 (left end of `x_motor_mount`); the X home switch trips at X 19 ± 2.
- **Homing:**
  - X homes to MIN (left end) with a microswitch and reads X = 22 there, so machine X = layout X
    (pocket 0 at X = 42). `calibrate x` stores the small residual as `offset_x`.
  - Z homes to MAX (top) with a microswitch and reads Z = 255. `calibrate z` stores the pad trip
    height as `pad_trigger_c`. The G54 work offset stays at zero; calibration lives in software.
- **Speeds:**
  - X: 15000 mm/min max, 2000 mm/s².
  - Z: 6000 mm/min, 1200 mm/s².
  - Probe: 1200 mm/min. **Every downward move is a guarded `G38.3`** (fast part at the Z speed, the probe window at 1200 mm/min, a held slab passes the rod tops at 1200 mm/min), so an unexpected contact stops it. A trip at 6000 mm/min squeezes the buffer about 6 mm before the head stops.
  - Halt (Ctrl-C twice): feed hold `!`, then soft reset Ctrl-X. Homing is required afterwards.
  - Motor current: X run 1.0 A, Z run 0.8 A (hold 0.5 A, to keep the head up).
- **Contact probe:** a slotted optical endstop (TCST2103) on the cup's spring buffer (M10, 20 mm stroke), wired **fail-safe** so a cut wire reads as TRIGGERED.
  - It is the FluidNC `probe` pin.
  - Probing uses `G38.3` (no alarm on a miss) with a bounded target.
  - `probe_hard_limit: true`: a probe trip during any move that is not a `G38` (a lift, a traverse, a jog, homing) is a critical alarm that needs a reset and `$H`. It must give zero alarms in the 300-cycle test (BUILD_GUIDE §13.2), or the sensor output gets hysteresis.
  - Buffer: SMC `ZPT25UUK20-B5-A10`, M10 spring buffer, **non-rotating (K)**, **20 mm stroke**. SMC sells no 25 mm stroke on a 25 mm pad. [Certain, SMC ZP catalog Table 2] The rotating `J20` also works, because `head_foot`'s guide holds the flag.
  - Flag: 1 mm aluminium, in the CAD (`probe_flag`), its tab clamped between the buffer's M5 port hex and an SMC `M-5ALU-4` barb elbow (no washer, thread sealant; tube toward +Y). It trips the beam after 2.0 ± 0.5 mm of buffer travel (`buffer_trip_mm`), set with the board's ± 4 mm slots.

## CAD decisions made while checking the build guide (binding)
- **Checks:** `cad/checks.py` runs 177 checks; all 177 pass (re-run on 23 Oct 2026, about 12–15
  min, numbers in `cad/out/checks.txt`). A CAD change is done only when they all pass again.
- **Rails on slots:**
  - The X rail centre is at Z = 410, on the 4040 beam's upper front slot. It is fixed with M3
    screws into M3 T-nuts.
  - The Z spine (2040) sits 10 mm to the LEFT of the cup axis, so the Z rail is in its right
    slot, on the cup axis.
- **Z carriage:** its bottom is 295 mm above the cup face. The `z_end_cap` stops it at c = −14
  (it would leave its rail at c = −19), and at the top hard stop (c = 262) 3.6 mm of carriage is
  still on the rail. The firmware soft limits (Z −8 … 255) sit inside both stops.
- **Z machinery above the held slab:** the Z spine bottom is 275 mm above the pad (the `z_end_cap`
  under it ends at 267) and the lead-screw tip is at 283, so even at the top hard stop a held slab
  clears every part fixed to the X carriage by 5 mm. [Certain, `cad/out/checks.txt`]
- **Bed:** the plywood has 41 × 41 mm notches at the two upright positions. The uprights pass
  through to the base rail.
- **Drop arm (2020 × 285 mm):** drill two 5.5 mm cross holes, 19 mm and 84 mm from the end that
  bottoms in `head_foot`'s socket, matching the head_foot and camera_bracket clamp holes.
- **Light roof:** OPTIONAL. Add it only if Phase 0 or the first runs show room-light glare on
  labels. If you do, it's black foam board on two 2020 posts bolted to the **outer end faces** of
  the uprights (X −68 and X 1348). Not to their back faces: the beam-to-upright joining plates and
  brackets are there (BUILD_GUIDE §4.3). The CAD model leaves it out by default.
- **Guide rods:** 82 dowels at 12 mm from each pocket corner, which leaves a 52 mm finger gap
  front and back.
- **Head lens height:** 140 mm above the cup face at the 2 mm trip (`CAM_TO_SLAB`), so 142 mm above
  the free cup face. The buffer is set on its M10 thread to this (BUILD_GUIDE §7.5); the CAD
  allows ± 3 mm there.
- **Head lens position:** 5 mm from the cup axis toward the label end (`HEAD_CAM_DY = −5`), X on
  the cup axis, set by `camera_bracket` and, in Phase 0, by `phase0_top`. With the lens on the axis
  the M5 elbow 23 mm under it hid the card window.
- **Probe:** the flag, its guide (two fins on `head_foot`, a 1.9 mm slot) and the sensor post with
  ± 4 mm board slots are in the CAD, built on the SMC catalog heights of `ZPT25UUK20-B5-A10` (pad
  face to port top 108.5 mm) and Vishay's TCST2103 drawing. `checks.py` sweeps them over the
  20 mm stroke.
- **Phase 0 occluder:** `phase0_occluder_mount` clamps to the jig's right post and holds
  `head_foot` on a 2020 × 66 mm stub, where the machine has it relative to the lens. For the
  face-up pass the mount slides 3 mm up the post.
- **Card window:** `FACE_DOWN_WINDOW_MM = [[-27.5, -23.5, 27.5, -18.0]]`, mm from the CUP axis (−y =
  the label end; 55 × 5.5 mm = 302.5 mm²). The software's `face_down_window_mm` is measured from the
  head-CAMERA axis: `layout.face_down_window_cam()` = `[[-27.5, -18.5, 27.5, -13.0]]`, which
  `gen_config` writes; the Phase 0 jig's flipped version is `[[-27.5, 13.0, 27.5, 18.5]]`. It is
  placed from `layout.HOLDERS`, the card position measured on 22 PSA and 27 CGC backs (card top to
  the holder's far end: PSA 97.18–99.95 mm, CGC 93.76–96.21 mm). `checks.py` proves it clear of every
  machine part at hover (stacks of 1, 15, 30) and with a slab held, and clear of the label band; on
  the card plane (card 3.5 mm under the back, rounded corners) a slab in a pocket corner has 0.0%
  of it on the holder for PSA and 1.52% for CGC (limit 2%). It also reports the camera-aim
  tolerance: 1.34° toward the cup (1.31° with the software's 147 mm mapping).
- **LED rings:** in the CAD. Head ring modelled 40 × 30 × 5 mm. Its seat on `camera_bracket` (and
  the pocket in `phase0_top`) is a 42.8 mm bore with three centring ribs, printed to fit a 40.0 mm
  ring, and a 33 mm lip: it takes OD 39.5–42.5 mm (shave each rib by half of OD − 40), and
  `checks.py` runs every head ring check at 39.5, 40 and 42.5 mm. Its LED face sits 1 mm under the
  lens front, the leads go out through a notch, and the barb elbow clears it by 3.75 mm at the full
  stroke. Station ring:
  a 64 mm bore on a 45° shelf (`station_mount`, `phase0_base`) that takes a 63 × 47 or a 60 mm ring,
  the leads down a slot into the ribbon slot. Each is fixed with three dots of glue.
- **Switch mounts:** printed, in the CAD, for a bare SPDT hinge-lever switch of the Omron SS-5GL
  size (2 holes 9.5 mm apart, M2×12 through ±1 mm slots). `x_switch_mount` sits under the beam's
  left end (2 × M5×10 button heads into the beam's lower front slot, at X −48.5 and −37) and is
  worked by a 17.4 mm finger on `x_bracket`'s left edge; `z_switch_mount` sits on the Z spine's +X
  face (2 × M5×10 button heads into that face's slot) and is worked by a 45° chamfer, 7.5 mm deep,
  along the `z_plate`'s top back edge from X 20 to its right end. Each striker slides across the
  lever: a 45° lead-in, then a flat that holds the lever 0.6 mm past its operating point (at the
  lever tip) up to the hard stop, under its 1.2 mm overtravel. Trips: cup X 19.00 and c = 258.00.
  Each mount slides about ±3 mm in its slot to set the trip. The lever must end within 23 mm of the
  switch's hinge end (`SW_LEVER_MAX`; a longer one is cut back to 20 mm); the X mount takes up to
  27.24 mm and the Z mount 24.19 mm. Lead paths are modelled (X: under the beam into its lower rear
  slot; Z: behind the `z_motor_mount` to the spine top).
- **Carry-height sensor:** the spare TCST2103 board on the Z spine's −X face (`carry_sensor_mount`,
  2 × M5×10 button heads into slot-6 T-nuts, beam at Z 561.5 above the pad top), and a flat 1 mm
  aluminium flag on `carry_flag_arm` (screwed to the `z_plate` front face). Its beam is clear at
  every cup height up to 242 and fully blocked from 248 to the 262 top stop; it trips at 246.5,
  set by sliding the mount.
- **Head crop:** `head_roi_half_mm = SLAB_W/2 − play = 38.3`, from the CAD: every real code lies
  within ± 33.5 mm of the slab's centre line.

## Controller
- **Board:** BTT Rodent V1.x (V1.1 assumed) running FluidNC v4.1.1 or newer. BTT's official
  `rodent.yaml` is the base.
  - Set `r_sense_ohms` to the board's resistor marking: R075 → 0.075, R022 → 0.022.
    `config.yaml` ships with 0.022 on purpose: the wrong guess then gives weak motors, not 3.4×
    the current. Change all four lines to 0.075 only after reading R075 on your board.
- **Connection:** CH340 USB serial at 115200 baud to the Raspberry Pi: `/dev/ttyUSB0`, by-id
  `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`.
- **Unused features:** no Y axis is defined, and no spindle or coolant pins are used. FluidNC
  still reports three axes (`MPos:x,0.000,z`).
- **Driver sockets:** X motor → socket X, Z motor → socket Z. Sockets Y and E are configured as
  ganged spares for X and Z, because the SPI chain needs all four. Leave them empty.
- **Inputs, all fail-safe (a cut wire reads as triggered):**
  - X home switch (NC) → X-MAX connector, gpio.35.
  - Z top switch (NC) → Z-MAX connector, gpio.33.
  - Optical contact probe → **Y-MAX connector, gpio.34** (not the board's Probe connector).
- **Soft limits (machine mm):** X 22…1253, Z −8…255.
  - After homing: X = 22, Z = 255.
  - Probe targets must stay above Z −8.
  - CAD must keep both carriages on their rails at every hard stop (X 15 / 1262, Z −14 / 262).
- **E-stop:** two NC contact blocks **in series** in the +24 V line. It cuts the Rodent, the pump,
  both valves and the LED buck, so FluidNC reboots and the USB serial device disappears. The
  software must treat a lost port as a stop, then reconnect and home again. A held slab then hangs
  only on the closed cup line until it leaks down: the operator takes it off.
- **Mains:** the IEC inlet sits in a closed ABS box with a cable gland to the LRS; no mains metal is
  exposed with the cord plugged in.
- **Firmware files:** `firmware/fluidnc/config.yaml`. Bring-up steps: `docs/FIRMWARE.md`.
- **Wiring:** `docs/WIRING.md` and `docs/img/wiring.svg`.

## Raspberry Pi 5 (4 GB), Raspberry Pi OS Bookworm 64-bit, Python 3.11
- **GPIO (BCM numbering), each output driving a logic-level MOSFET module:**
  - 17 = vacuum pump (24 V)
  - 27 = vacuum valve, normally-closed 2/2 (24 V)
  - 22 = vent valve, normally-closed 2/2 (24 V)
  - 23 = head LED ring
  - 24 = station LED ring
- **GPIO inputs:**
  - 25 = optional lid/door switch to GND (internal pull-up)
  - 5 = overfill beam receiver output (HIGH = beam received). The laser is a ≤ 1 mW (Class 2)
    650 nm module, fed from the Pi's 5 V, so it is on whenever the Pi is on.
  - 6 (pin 31) = carry-height sensor output through a 10 kΩ / 20 kΩ divider (HIGH = the flag is in
    the beam = the head is at carry height). A cut lead reads LOW, which refuses sideways moves; a
    dead emitter reads HIGH, which the runner catches by requiring LOW at every grip.
- **I2C1 (GPIO 2/3):** ADS1115 at 0x48.
  - Its A0 reads the XGZP6847A vacuum sensor (−100…0 kPa, 0.5–4.5 V at 5 V supply) through a 10k/20k divider.
- **Cameras:**
  - Head: USB UVC 8 MP IMX179 board with an M12 3.6 mm lens (F2.8 or faster), manual focus, looking down at the held slab's back from 140 mm, 5 mm toward the label from the cup axis. Its frames are cropped to the slab under the cup (`head_roi_half_mm`, `cam_head.hfov_deg`, `row_axis`, `lens_to_label_mm`: check them on the real camera).
  - Station: Raspberry Pi Camera Module 3 (standard) on CSI port 0, looking up at the held slab's front from 140 mm.
- **Lighting:** a 40 mm COB LED ring around the head lens (a 60 mm ring cuts into the drop arm; a 40 mm 12-SMD ring that fits the seat is the fallback) and a 60 or 63 mm ring around the station lens, both 12 V. The black foam-board "light roof" is optional (see the CAD decisions above).

## Software (repo folder `psa-slab-scanner/software`)
- **Package:** `slabscan/`
  - `certs`, `decode`, `facedown`, `sim`, `runner`, `simworld`, `motion`, `hw`, `camera`, `config`, `results`, `psa_api`, `ops`, `factory`, `cli`, `web`
- **Config:**
  - `config/machine.toml` is generated by `python -m tools.gen_config` from `cad/layout.py`.
  - `config/calibration.toml` holds the values written by the calibrate commands (and `phase0 --save`).
  - `config/card_backs.npz` holds the learned face-down check's card-back references. Not in git.
- **CLI:** `python -m slabscan <command>`
  - `selftest [-i] [--motion]`: GPIO, vacuum sensor, pump and valves, both cameras, controller connection, beam gate, carry-height sensor (`--motion` measures where it trips).
  - `home`
  - `jog`: interactive.
  - `calibrate z`: probes the bare pad of pocket 0 and writes `pad_trigger_c`.
  - `calibrate x`: operator centres the awl over pocket 0 and pocket 12 and writes `offset_x` plus a scale check.
  - `focus head|station`: live sharpness and decode score to set focus. On the machine `focus head` first checks the camera's aim over the empty pocket 12 and saves `focus/focus_head_empty.jpg`.
  - `mark`: drives the awl to every cell for the drill template.
  - `run [--name NAME] [--front-photo always|fallback] [--all-face-down] [--yes]`
  - `resume BATCH_DIR [--face-down-ok] [--accept-heights] [--yes]`
  - `sim [--slabs N] [--mix MIX] [--eras E] [--face-down-check] [--jp-rate R] [--sim-head cad|cad_r2|open|none] [--sim-head-tilt DEG]`: full simulated batch, no hardware. `--sim-head-tilt` tilts the simulated head camera toward the cup (every command that takes `--sim` accepts it). `--mix` sets the label mix per grader and era (default: mostly PSA, some CGC, a few BGS); `--eras` is a PSA-only override. `--face-down-check` keeps the check on and counts the slabs it would stop at (a simulated operator confirms each). `cad` is today's head, `cad_r2` an earlier head design whose foot hid the card window.
  - Bench tests (not part of the CLI): `python -m tools.bench_tests cycles|rest|lifts|drop|powercut N` (BUILD_GUIDE §7.8, §13).
  - Real-label check (not part of the CLI): `python -m tools.real_eval INDEX.json [--machine] [--glare]` or `--phase0 DIR`: the run's reading order, consensus and face-down rule on photos of real slabs; exit 1 on a wrong cert in an `ok` verdict or a false face-down proof.
  - `web [--port 8080]`: phone-friendly start/stop/progress page and CSV download.
  - `phase0 [--sim N] [--out DIR] [--face-up N] [--save] [--force]`: the Phase 0 camera read-rate test (same as `python -m tools.phase0`). An `--out` folder that already holds a `phase0.csv` is refused (exit 2, nothing changed) unless `--force` is given. The read-rate report is written as soon as the operator types `q`. `--face-up` (default 0) adds the face-up pass for the learned face-down check; a GO needs 15. `--save` writes `face_down_threshold` and `face_down_threshold_sig` and merges the backs into `config/card_backs.npz`, only on a GO.
  - `refs [--drop CERT | --drop-operator]`: list or delete the learned face-down check's references.
- **Outputs:** `batches/<id>/certs.csv`, `certs.txt`, `report.html`, `summary.json`, `journal.jsonl`, `images/` (plus `run.json`, and `stop.json` after a stop).
  - `certs.csv`'s last column is `face_down`: `qr` (a PSA or CGC back QR), `code` (the CGC 2020–23 back barcode), `operator`, `learned(<score>)` or `off`. `report.html` has a Face-down column; `summary.json` a `face_down` entry, plus `itf_mode` (always `zero_pad`) and `itf_evidence`.
  - Learned mode adds `images/face_down_window.jpg` (the run's first slab with the card window drawn) and `images/face_down_empty.jpg` (the view over an empty pocket), and `summary.json`'s `face_down` gets `camera_aim` (`ok`, the failed check's message, "not checked (no view over an empty pocket)", or "not checked this run (…)" after a resume that never looked over an empty pocket); a failed aim check prints a `CAMERA AIM:` summary line.
- **Enrichment (optional, later):** `python -m tools.enrich batches/<id>` (PSA API, quota-metered).
- **Graders:** PSA and CGC are read and stacked normally. An `ok` needs its grader confirmed: a
  code that names it (a cert URL), two printed symbols in its format, or an 8-digit ITF whose
  digits OCR of the printed number confirms (`certs.psa_itf_confirmed`: grader PSA, note "grader
  PSA from its 8-digit ITF"; a pre-2016 PSA slab). Any other one-barcode slab is `needs_review`
  even when OCR agrees (OCR confirms its digits, not its grader), and an ITF alone or OCR alone is
  never `ok`. A code in no grader's format never confirms a grader. A PSA Code128 is 8–9 digits and
  a 10-digit CGC Code128 never starts with 0; any other Code128 is not typed. Every barcode-only
  `ok` also gets the front OCR. Other graders go to pocket 12, and so does every `needs_review` whose grader is
  not an accepted one (`unknown`: an OCR-only number or a code with no grader's format; `PSA/CGC`;
  none), whatever `needs_review_to` says. A grader guessed from a barcode's length counts as
  accepted.
- **Face-down check:** before the cup touches a slab, the frame from above must prove it is
  face-down. `face_down_check` sets how:
  - `"learned"` (the default): a back-label code (`certs.SIDE_PROOFS`: a PSA back QR, a graded CGC
    QR, the CGC 2020–23 back barcode), or a card window that matches two references (two different
    slabs of one back design) among the card backs of code- or operator-proven slabs
    (`slabscan/facedown.py`). It is active only with a Phase 0 threshold (≥ 0.55) and its matching
    `face_down_threshold_sig`, `face_down_min_refs` (5) references, the empty-pocket view, at
    most 10% of the window static on 5 machine-proven slabs, and a clear camera-aim check on that
    view (`facedown.aim_problem`: no edge in the middle of the window or within 1 mm of its cup
    side; a tilt toward the cup only), taken this run (`CardBackRefs.stale`: a resume whose survey
    finds no empty pocket takes the view over the first source pocket it empties, and accepts
    nothing before that). Until then it acts like `"stop"`. A
    code-proven or confirmed slab becomes a reference only after it is placed: never if a
    back-label code is seen from below, and a code proof only with an `ok` read of the same cert.
  - `"stop"`: only a back-label code.
  - `"off"`: no check. `run --all-face-down` (or the web start checkbox) does this for one batch;
    the choice is stored in `run.json` and kept on resume.
  - A front-label code seen from above (a CGC Authentic QR, a CGC front barcode) stops with a
    FACE-UP message. Back and front codes together, two back labels, or codes of two certs in one
    frame stop as "another slab's label is in view". Anything not proven stops untouched until
    the operator confirms with `resume --face-down-ok` (or the web checkbox, shown only then). That
    is refused unless the batch's last stop was a face-down stop, and it confirms only that
    pocket's top slab.
  - Journal events: the stop line carries `face_down_stop` (pocket) and `why`;
    `face_down_confirmed`, `face_down_reference` (a confirmed slab learned after placement, with
    its cert and back photo), `face_down_learned` (score, ncc, hist, prototype, threshold, refs,
    texture, baseline, `position`), `face_down_baseline` (with `aim`), `face_down_ok_unused`; `stall_set_down`
    (the pocket a held slab was lowered onto after a Z stall). Events that are not transfers never
    use the `pos` key: `rebuild_state()` reads `pos` with `src` as a finished transfer.
- **Stops:** Ctrl-C once (or web Stop) = stop after the current slab. Ctrl-C twice = hard stop: the
  motors halt where they are, nothing moves afterwards, a held slab stays on the pump until the
  operator holds it and vents (CLI prompt or the web Vent button).
- **Carry-height sensor:** read before every sideways move (must be blocked), every Z or probe move
  with a slab in the cup, every grip (must be clear), and at a pause just above its trip on every
  loaded descent. A disagreement is a `CarryStop` ("Z stall suspected …" or "Carry-height sensor
  fault …"); after a stall a held slab is never carried sideways (lowered by one probe move over
  its own pocket, else held). Homing clears it. `jog`, `calibrate` and `mark` do not read it.
- **One process:** the machine is locked to one slabscan process (`/run/lock/slabrail.lock`); stop
  `slabrail-web` before running CLI machine commands.

## Budget
The original figure was $2,000; on 22 Oct 2026 the user said $2,500–3,000 is fine as long as the machine works properly and is good quality. The user has school 3D printers and mechatronics instructors.
The current BOM is about $2,182 with a 15% allowance, and the worst case about $2,380 (BOM.md has
the breakdown; SHOPPING_LIST.md the orders with links). Upgrades are qty-0 BOM lines, each bought
only when the test it names fails.
