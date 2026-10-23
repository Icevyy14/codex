# SlabRail software

Runs on the Raspberry Pi 5 in the machine. It moves the head through the FluidNC controller,
reads every slab's label, and writes `batches/<id>/certs.csv`. Everything also runs on any PC
against a simulator (`--sim`), so you can learn the commands before the machine exists.

**[Certain] None of this has driven real hardware yet.** It is tested against the simulator,
which raises an error on any unsafe move. Expect to fix small things during the first
supervised runs, with a mechatronics instructor next to you.

## Install

**On the Pi** (Raspberry Pi OS Bookworm 64-bit), from this `software/` folder:

```bash
bash setup_pi.sh          # apt packages, I2C on, venv, config/machine.toml
sudo reboot
source .venv/bin/activate
```

The script installs numpy, OpenCV, picamera2 and gpiozero from **apt**. The venv uses
`--system-site-packages` so it can see them. Do not `pip install numpy` or `opencv-python` on the
Pi. A pip numpy hides the apt one, and picamera2 then breaks. `bash setup_pi.sh --service` also
starts the web page at every boot.

**On a PC** (for the simulator and tests):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests        # 300 tests (1 skipped without SLABRAIL_REAL_IMAGES), about 16-21 minutes
```

## First-time order

Do these in order. Each step depends on the one before it.

| Step | Command | What you do |
|---|---|---|
| 1 | `python -m tools.gen_config` | Writes `config/machine.toml` from `cad/layout.py` (setup_pi.sh already did this). |
| 2 | `python -m slabscan selftest -i` | Checks every part. `-i` adds the hand checks: push the cup up, press a slab on the cup, block the beam. |
| 3 | `python -m slabscan home` | X goes to its left switch, Z to its top switch. Keep a hand on the e-stop the first time. |
| 4 | `python -m slabscan mark` | **Before the rods go in.** Awl adapter on. For each pocket, the awl drops into the drill template's two dimples. You clamp the template and drill 8 rod holes. Pockets 0 and 12 come last, because one of their dimples is past the X travel: two 5/16 in dowel offcuts through the template into the neighbour's holes set them. `--only 0,12` continues after a break. |
| 5 | Glue the rods, lay the pads | |
| 6 | `python -m slabscan calibrate z` | Cup on, pocket 0 empty. Probes the bare pad 4 times and writes `pad_trigger_c`. It also checks that the contact sensor triggers when you push the cup up by hand. |
| 7 | `python -m slabscan calibrate x` | Awl on. First mark the centres of pockets 0 and 12 with a tape cross on each pad (BUILD_GUIDE 12.2). Centre the awl over pocket 0, then over pocket 12: first by eye at the safe height, then low over the tape cross. Writes `offset_x` and prints the scale error across the row. |
| 8 | `python -m slabscan focus head` | One slab face-down in pocket 0, pocket 12 empty. It first checks the camera's aim over pocket 12 (`camera aim: OK` or `FAIL`, picture in `focus/focus_head_empty.jpg`). Then the cup rests on the slab: turn the M12 lens until the score peaks, then lock the lens nut. |
| 9 | `python -m slabscan focus station --save` | One slab in pocket 0. The machine picks it up and holds it over the station camera. It sweeps `LensPosition`, saves the sharpest value that decodes, then puts the slab back. |
| 10 | `python -m slabscan run --name test` | First real batch, on junk slabs, with you watching. |

Calibration values go to `config/calibration.toml`. That file overrides any key in
`machine.toml`, and `gen_config` never overwrites it. Put your own settings there too, for example
`serial_port`, `cam_head`, `custom_regex`, `front_photo` or `lid_switch = true`. Two of them change
what can be `ok`: `custom_regex` types every ITF by your pattern, so the 8-digit ITF rule never
fires and every pre-2016 PSA slab is `needs_review`; and `psa_cert_digits` (lengths without
leading zeros) must include 7 if you have pre-2016 slabs, or every 7-digit cert is `needs_review`.

**Exposure.** The LED rings switch on just before each photo. After switching on, the software
waits `light_settle_s` (0.3 s, **[Guessing]**) so auto exposure can settle. If the first photo of
a slab comes out too bright or too dark, give the station camera a fixed exposure once focus is
set, for example `cam_station = { type = "picamera", index = 0, lens_position = 7.1, exposure_us = 8000, gain = 1.0 }`.
Tune the numbers with `focus station`.

## Commands

All commands are `python -m slabscan <command>`. Add `--sim` to use the simulator, as in
`python -m slabscan --sim jog`.

| Command | Does |
|---|---|
| `selftest [-i] [--motion]` | Checks the controller, the probe pin (a cut wire reads TRIGGERED because the wiring is fail-safe), the vacuum sensor, pump, valves (and, with `-i`, seal, leak and vent), the LED rings, both cameras (saves an image of each), the overfill beam, the lid switch, the carry-height sensor (GPIO 6; with `--motion` it homes, steps the head down past `carry_sensor_c0` over pocket 0 and reports where the sensor trips), tesseract, disk space and, in learned mode, the camera aim the last run measured over an empty pocket (WARN until one has). Exit code 1 if anything fails. |
| `home` | Homes both axes and prints the position. |
| `jog [--no-rods]` | Typed moves, `x 300`, `x +2`, `z -1`, `p 3`, `station`, `up`, `probe`, plus `keys` for arrow keys. `help` lists everything. |
| `calibrate z` / `calibrate x` | See above. |
| `focus head\|station [--save] [--no-motion]` | Live sharpness score (Laplacian variance of the sharpest tiles) plus what decodes. With `--no-motion` you hold the slab in view, for example in the Phase 0 jig (then the camera aim is not checked). |
| `mark [--only 0,12] [--dry-run]` | Drill-template walk (above). `--dry-run` prints the order and positions. |
| `run [--name NAME] [--front-photo always\|fallback] [--all-face-down] [--yes]` | One batch. It refuses to start before `calibrate z` and `calibrate x` have been run. `--yes` skips the start question. `--all-face-down` turns the face-down check off for this batch (below). |
| `resume BATCH_DIR [--accept-heights] [--face-down-ok]` | Continues a stopped batch (below). `--face-down-ok`: you checked the slab the face-down check stopped on. It is refused unless the last stop was that face-down stop, and it confirms that one slab only. |
| `sim [--slabs N] [--mix MIX] [--eras E] [--face-down-check] [--jp-rate R] [--sim-head cad\|cad_r2\|open\|none] [--sim-head-tilt DEG]` | Full simulated batch. Prints the summary and a time estimate. `--mix` sets the label mix per grader and era, e.g. `psa:current=0.6,psa:2017+=0.2,cgc:2023+=0.2` (kinds: `psa:current\|2017+\|2016\|old`, `cgc:2023+\|og\|authentic`, `bgs:`, `sgc:`; default: mostly PSA, some CGC, a few BGS); `--eras` is a PSA-only override. `--face-down-check` keeps the check on and counts the slabs it would stop at (a simulated operator confirms each). `--jp-rate` gives that share of cards the Japanese back. `--sim-head`: `cad` (the default) is today's head (lens 5 mm toward the label, card window clear), `cad_r2` the round-2 head whose foot hides the card window, `open` a hypothetical narrow head. `--sim-head-tilt DEG` tilts the simulated head camera toward the cup (a mis-aimed camera; it works with every command that takes `--sim`). |
| `web [--port 8080]` | Phone page (below). |
| `phase0 [--sim N] [--out DIR] [--face-up N] [--save] [--force]` | The Phase 0 camera test (same as `python -m tools.phase0`): reads 30-50 of your slabs in the Phase 0 jig before you buy any motion parts. The read-rate report is written as soon as you type `q`. The face-up pass is off unless you ask for it (`--face-up` defaults to 0); a GO for the learned face-down check needs 15 face-up slabs. `--save` writes its threshold on a GO. Each run needs its own `--out` folder: one that already holds a `phase0.csv` is refused, and nothing in it changes (`--force` overwrites it). |
| `refs [--drop CERT \| --drop-operator]` | Lists the learned face-down check's card-back references, with the batch, position and cert each came from. `--drop CERT` deletes one slab's reference, for example after a wrong confirmation; `--drop-operator` deletes every reference you confirmed and keeps the back-QR ones. |

**Jog safety rules** (enforced in software):
- Nothing moves before homing.
- Every downward move is a probe move that stops on contact.
- Below the rod tops, the head moves sideways only within ±5 mm of a pocket centre. The head is
  70 mm wide and a pocket is 84 mm.
- A move is never started while the probe already reads triggered.
- No move or probe target goes below machine Z −7.5. The firmware's soft limit is −8, and the CAD keeps
  the Z carriage on its rail down to −12. A probe that would reach further is cut short there.
- After an E-stop the next command homes first (Z straight up, then X) and is not run itself.

`--no-rods` lifts the sideways rule. Use it only while the bed has no rods.

## Running a batch

Loading rules:
- Slabs go **face-down**, **label end toward you**, in pockets 1–11.
- No stack goes above the MAX line on the fill gauge.
- Pocket 0 and pocket 12 stay empty.

**Face-down check** (`face_down_check` in the config). Before the cup touches a slab, the frame from
above must prove the slab is face-down. Otherwise the run stops with nothing touched, and you
confirm it with `resume --face-down-ok`.
- `"stop"`: only a back-label code proves it (a PSA back QR, a graded CGC back QR, the CGC 2020-23
  back barcode). Older PSA labels, CGC Authentic, BGS and SGC stop every time.
- `"learned"` (the default): a back-label code, or a card window that matches the card backs of earlier
  code- or operator-confirmed slabs (`slabscan/facedown.py`). The references live in
  `config/card_backs.npz` (not in git; `refs` lists them, `refs --drop CERT` deletes one, and
  deleting the file starts over). It only becomes active when all of these hold:
  - Phase 0 wrote `face_down_threshold` and `face_down_threshold_sig` (`phase0 --face-up 15 --save`
    on a GO). A threshold measured for another card window, or typed in without its sig, is not used.
    No threshold below 0.55 is accepted.
  - 5 references exist, and 5 slabs proven face-down on this machine showed the card window clear:
    at most 10% of it may look the same on every slab as over an empty pocket.
  - Until then it acts like `"stop"`.
  - Today's CAD head (lens 5 mm toward the label, trimmed foot) leaves the card window clear
    [Certain, in the CAD and the simulator]. A head that hides the window (the round-2 head) is
    detected and refused, and so is one that hides only part of it [Certain, sim: a foot edge 3 mm or
    more inside it; an edge 1 mm inside is not seen, and it lifts face-up scores from 0.37 to 0.52].
  - A slab is accepted only when **two** references (two different slabs) of one back design match it,
    not just the best one [Certain, 64 real slabs: one odd back, a card sitting low in its holder,
    matched a blue Water-type front at 0.56-0.62; no second back came above 0.44]. Blue Water-type
    fronts are the closest real match to a card back: put one in Phase 0's face-up pass.
  - The camera's aim, checked in every run on the view over an empty pocket: only the pad may show
    in the middle of the card window and 1 mm beyond its cup-side edge. A tilt toward the cup brings
    the cup pad and the foot in there. Then the learned check accepts nothing and learns nothing that
    run, and the start line, every stop, the summary and `selftest` say to re-aim the camera
    (BUILD_GUIDE §7.7). `focus head` looks over the empty pocket 12 first and says the same.
    A verdict counts only for the run that took it. A resume looks again over an empty pocket at its
    survey. If no pocket is empty, the learned check accepts nothing and learns nothing until the
    run empties its first source pocket and looks over that one. So a camera knocked while the run
    was stopped is seen. [Certain, sim, round-3 card window: a camera knocked 1° while stopped is
    caught, with and without an empty pocket at the resume.]
    [Certain, sim, round-3 card window: a square camera passes, 0.5° toward the cup is caught; the
    camera-locked check alone let 0.6–1.0° through: only 0–2% of the window was camera-locked.
    With today's smaller window a head part enters at about 1.3°, and the check fires from about
    1.3° (a verifier measured 1.30° and 1.33°).]
  - What the aim check does not see [Certain, sim and geometry]:
    - A head part as dark as the pad shows no edge, and the 10% camera-locked rule does not catch it
      either while it covers a strip of the window (a dark foot over 9–26% of the window read
      0.3–0.9% camera-locked).
    - It checks only a tilt toward the cup. A tilt away from the cup, or a roll along the row, is
      not checked.
    - Its thresholds come from the simulator's flat pad. Lint, dust or glue on a real pad can make
      it fire. That is safe (the learned check stays off), but it needs a real empty-pocket picture
      from Phase 0 to tune.
  - A back design known only from your confirmations (no back-code slab) is used once three of
    your confirmations agree. A code-proven or confirmed slab is learned from only after it was placed:
    not if the read station saw a back-label code from below (it was face-up after all), and a code
    proof only with an 'ok' read of that same cert (a neighbour's back QR in view gives another cert).
- `"off"` (or `run --all-face-down`): no check. A face-up slab gets the cup on its front.

The machine:
- homes,
- probes every pocket,
- then moves stack 1 onto pocket 0, stack 2 onto pocket 1, and so on, reading each slab on the way.

Afterwards each stack sits **one pocket to the left, in reverse order**. Pocket 12 holds the slabs
to check by hand: unreadable ones, numbers read only by OCR (no grader), conflicts, or graders other
than PSA and CGC. Only a `needs_review` row of PSA or CGC may stay in the output stack. A grader
guessed from a barcode's length counts, so another grader's slab whose barcode has a PSA or CGC
format can end up there as `needs_review` too. The same holds for an `ok` from an 8-digit ITF:
another grader's slab with an 8-digit ITF whose printed number OCR reads would come out `ok PSA`
[Guessing that none exists: none was seen in the real set, which has 1 BGS and 1 SGC slab; BGS and
SGC are reported to print some code on some holders, type unknown]. Put any non-PSA slabs you own
through Phase 0 (`python -m tools.real_eval --phase0`) before trusting `ok PSA` on slabs with no
QR.

**What makes an `ok`** (`slabscan/certs.py`):
- A QR carries its own error correction. A barcode (ITF, Code128) needs a second printed code
  (the other label side, or the QR) or OCR of the printed digits to agree.
- Two barcodes alone (no QR) can agree on the same misread, because both sides carry the same
  pattern. So the front OCR also checks every barcode-only `ok`. If it reads other digits, the
  slab is `needs_review`; if it reads nothing, the slab stays `ok`.
- Two frames of one printed code are one source. A thin false read inside a real barcode (a
  phantom) is dropped only when a different code or OCR confirms the other number, and then from
  every frame of that barcode. Only the thin read can be dropped. If the confirmed number is the
  thin one, the slab is a `conflict`.
- The grader must come from a code that names it (a cert URL), from two printed codes in its
  format, or from an 8-digit ITF whose digits OCR confirms. That last rule names PSA: in the real
  set only PSA labels carry ITF (CGC uses Code128; its 1 BGS and 1 SGC slab showed no code). It is what makes a
  pre-2016 PSA slab (front ITF only) `ok`, with the note "barcode confirmed by OCR; grader PSA
  from its 8-digit ITF". An ITF alone, or OCR alone, is never `ok`; an ITF of any other length is
  a misread. A code in no grader's format (a QR or other code with a bare number) never confirms
  a grader, not even beside an ITF. Any other bare number gets its grader from its length
  only, and OCR confirms its digits, not its grader: a slab whose only code is one front Code128
  is `needs_review` even when OCR agrees.
- A PSA Code128 is 8 or 9 digits, and a 10-digit CGC Code128 never starts with 0 (every real one).
  A Code128 outside those formats (a 7-digit number, a BGS cert like 0019865140) is not read as a
  cert; it is listed as unparsed.

**Carry-height sensor (Z stall guard).** Before every sideways move the head must read "at carry
height" on GPIO 6 (and "below it" at every grip, which catches a dark sensor). A Z stall that left
the head more than about 2.5 mm low stops the run ("Z stall suspected …"): a held slab is lowered
straight onto its own pocket, or held on the pump for you. `selftest --motion` measures where it
trips. `jog`, `calibrate` and `mark` do not read it.

**Stopping**
- Ctrl-C once, or Stop on the web page, finishes the current slab and parks with nothing in the
  cup.
- Ctrl-C twice is a hard stop: the motors halt where they are and nothing moves after that. A slab
  in the cup stays held by the pump until you hold it and type `vent`. The next run homes first.
- Use the e-stop for anything dangerous.

**E-stop.** It cuts the 24 V supply: the controller, the motors, the pump and both valves. The
controller's USB port disappears. The software then:
- stops at once and moves nothing more (it can't: the motors have no power),
- shuts the valves from the Pi side, so nothing switches on when the power comes back,
- tells you what to do. If a slab was in the cup, the closed valves keep it there for a while. Hold
  it, pull it off gently and put it face-down on top of the pocket the message names.

Twist the E-stop to release it, then resume (command line or web page). The software reconnects to
the controller and homes before anything else moves. It does not trust the controller's position
after a reboot, because FluidNC's unlock command (`$X`) marks the axes as homed without homing them
(**[Certain]**, FluidNC source `ProcessSettings.cpp`, `disable_alarm_lock`).

**When the machine stops on its own**, it prints what to do. Examples: a cup that won't seal, a
stack taller than expected, lost vacuum, or a full exception pocket. If a slab was still in the
cup, the machine first puts it back on top of the stack it came from, so it gets read again on
resume. If the vacuum was lost, it does not vent and does not move (venting could drop the slab).
It tells you which stack to put the slab back on.

**Resume**: `python -m slabscan resume batches/<id>`.
- The state is rebuilt from `journal.jsonl` and `certs.csv`.
- Every pocket is probed again and compared with what the journal predicts.
- You may empty the exception pocket before resuming. Counting there restarts from what is left.
  An empty pocket also lets the resume check the camera's aim at once. With no empty pocket, the
  learned face-down check accepts nothing until the run empties its first source pocket: every slab
  without a back-label code stops for you until then (the stop says "the head camera's aim is not
  checked this run yet").
- Any other change of more than 4.5 mm (under one slab) stops the resume and lists the pockets. A
  missing or extra slab must be put back first.
- If it looks like one slab moved without being recorded (a power cut mid-move), the message says
  which slab to move back.
- `--accept-heights` takes the new heights instead. The slab-count check at the end then flags the
  difference.

## Output (`batches/<id>/`)

| File | Contents |
|---|---|
| `certs.csv` | One row per slab: cert, grader, status (`ok`, `needs_review`, `no_read`, `conflict`, `other_grader`), which pocket it came from and where it is now (`out_pocket`, `out_index` counted from the bottom), image paths, and `face_down`: how it was proven face-down (`qr` a PSA or CGC back QR, `code` the CGC 2020-23 back barcode, `operator`, `learned(0.93)` or `off`). Written row by row, so a crash loses nothing. |
| `certs.txt` | Only the `ok` certs, one per line, in machine order. Paste it into a spreadsheet or Card Dealer Pro. |
| `report.html` | Every slab with its label photo and a Face-down column (learned rows in bold: check their photos). Opens on a phone. |
| `summary.json` | Counts, duplicates, the per-stack slab count check, `itf_mode` (always `zero_pad`: the ITF is the cert padded to 8 digits) and `itf_evidence` (slabs where QR and ITF agreed), mean cycle time, and `face_down` (mode, counts, every learned row, the references, and in learned mode `camera_aim`: `ok`, the failed check's message, or "not checked this run …" after a resume that never looked over an empty pocket). A failed aim check also prints a `CAMERA AIM:` summary line. |
| `journal.jsonl` | Machine log used by resume, including the face-down events (`face_down_stop` on the stop line, `face_down_confirmed`, `face_down_reference`, `face_down_learned`, `face_down_baseline` with its camera-aim verdict `aim`, `face_down_ok_unused`). |
| `images/` | Back photo of every slab, plus a front photo when the station camera was used. In learned mode also `face_down_window.jpg` (the run's first slab with the card window drawn) and `face_down_empty.jpg` (the view over an empty pocket). |
| `stop.json` | Why the last run stopped (deleted when a run finishes). |

## Web page

`python -m slabscan web` serves `http://<pi-address>:8080/`. On it you can:
- start, stop and resume runs,
- see live counts, the current pocket, the last label photo and the last 10 slabs,
- see the stop message,
- download `certs.csv` and `certs.txt` for every batch.

`python -m slabscan --sim web` runs the page against the simulator.

> **LAN only.** The page has **no login**. Anyone on your Wi-Fi can start or stop the machine. Use it
> on your own home or shop network only, and never port-forward it or expose it to the internet.
> The page sends an `X-SlabRail` header that other websites can't add. That blocks drive-by
> requests from your own browser, but it is not a password.

## Card details (optional)

`python -m tools.enrich batches/<id>` adds year, set, card, grade and population from the PSA
Public API. The result goes to `certs_enriched.csv`. You never need it: `certs.csv` is complete on
its own.

1. Get a token at psacard.com/publicapi.
2. `export PSA_API_TOKEN=...`

How it behaves:
- Free accounts get about 100 calls a day. The tool counts calls and stops at `--daily-limit`.
  Run it again the next day and it continues.
- Answers are cached in `batches/psa_cache.sqlite`.
- New tokens are often refused with "403 limited to approved customers". The tool stops cleanly
  and tells you to email collectors-apis@collectors.com.
- CGC certs are skipped, because the PSA API cannot look them up.

## Simulator and timing

`python -m slabscan sim --slabs 330` runs a full load in about 5 minutes on a PC. It prints:
- the survey time,
- the seconds per slab,
- the total for a full load. The 23 Oct 2026 run (seed 7, default mix, `--face-down-check`, after the 8-digit ITF rule
  and the card position per grader) gave 75 s of homing and survey, then 14.2 s per slab: about 79 min for 330 slabs;
  `ok` 324, `needs_review` 6: 5 BGS slabs read only by OCR (in pocket 12) and one pre-2016 PSA slab whose OCR read
  other digits (in the output stack). The other 20 pre-2016 PSA slabs are `ok` from their front ITF and OCR. No `ok`
  has a wrong cert or grader [Certain, sim: checked against the simulated slabs]. Face-down: 287 by back QR, 41 by the
  learned card-back match (lowest score 0.76), 2 confirmed (the first slabs, before 5 references existed); with
  back-label codes only, 43 would have stopped. Without `--face-down-check` the check is off and the summary says how
  many slabs would have stopped.
- The simulated card sits where it does in real holders, per grader (`sim.HOLDERS`, from the CAD's `layout.HOLDERS`):
  a PSA card top 34.8–38.3 mm from the label-end edge, a CGC one 37.7–40.1 mm from the edge of its shorter holder,
  so about 3.4 mm nearer the cup. Other graders use PSA's [Guessing].

Motion uses a trapezoid acceleration model. Camera frame times and the Pi's decode speed are
**[Guessing]** values, listed at the top of `slabscan/cli.py`. Phase 0 measures the real ones.

## Code map

| Module | Role |
|---|---|
| `runner.py` | The batch: survey, transfer one slab, stop/secure, resume (State rebuilt from the journal). |
| `certs.py`, `decode.py` | Payload parsing, multi-read consensus, zxing and OCR decoding. |
| `motion.py` | G-code sender for FluidNC (`G38.3` probing, status parsing). |
| `hw.py`, `camera.py` | Pi GPIO (vacuum, valves, LEDs, beam, lid, carry-height sensor), ADS1115, USB and Pi cameras. |
| `factory.py` | Builds real or simulated backends from the config. |
| `ops.py` | jog, calibrate, focus, mark, selftest. |
| `cli.py`, `web.py` | Command line and web page. |
| `facedown.py` | Learned face-down check: card-window descriptor, card-back references, the accept rule. |
| `simworld.py`, `sim.py` | Simulator with a crash monitor, synthetic labels, card backs and fronts, and the head parts in the head camera's view. |
| `config.py`, `results.py`, `psa_api.py` | Config TOML, batch output files, PSA API client. |
| `tools/gen_config.py`, `tools/enrich.py`, `tools/phase0.py`, `tools/decode_sweep.py`, `tools/bench_tests.py`, `tools/real_eval.py` | Config generator, PSA enrichment, Phase 0 camera test, decode sweep, the acceptance bench tests, and the real-label check: the run's reading order, consensus and face-down rule on photos of real slabs (`index.json` or `--phase0 DIR`; `--machine` rescales them to the machine's cameras); exit 1 on a wrong cert in an `ok` verdict or a false face-down proof. |
