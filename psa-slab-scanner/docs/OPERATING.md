# Operating SlabRail

Weekly use: loading, running, reading the results, unloading, maintenance, and what to do when
it stops. The build and the acceptance tests are in [BUILD_GUIDE.md](BUILD_GUIDE.md). Commands
are run from `~/psa-slab-scanner/software` with the venv active
(`source .venv/bin/activate`).

Confidence tags: **[Certain]** = read in the code (`software/slabscan/`) or the CAD. **[Likely]**
= strong inference. **[Guessing]** = not yet measured on a real machine.

## Read this first

- **Only use it on inventory after every BUILD_GUIDE §13 test has passed.** [Certain that none of
  this has run on real hardware yet] Until then, every batch is a test batch.
- **`certs.csv` has one row per slab the machine *read*, not per slab you loaded.** [Certain,
  `runner.py`] Each DOUBLE PICK row hides one unread slab directly under it (§5.4). Always check
  the count line in the summary.
- **A wrong cert is worse than no cert.** The software refuses to guess: two codes that disagree
  give `conflict`, and an ITF-only read with nothing to confirm it gives `needs_review`. Respect
  those statuses. Don't paste `needs_review` certs into your inventory unchecked.
- **The web page has no login.** [Certain, `web.py`] Use it only on your own home or shop network.
  Never port-forward it.

## Contents

1. [Before each run](#1-before-each-run)
2. [Loading rules](#2-loading-rules)
3. [Starting a run](#3-starting-a-run)
4. [What the machine does](#4-what-the-machine-does)
5. [Reading the results](#5-reading-the-results)
6. [Unloading](#6-unloading-and-matching-rows-to-slabs)
7. [Maintenance](#7-maintenance-schedule)
8. [When it stops](#8-when-it-stops)
9. [Quick card](#9-quick-card)

---

## 1. Before each run

(2 minutes)

- [ ] **Wipe the cup lip with isopropyl alcohol** on a lint-free wipe, then let it dry for a
      minute. [Certain, DESIGN.md] The cup is the only part that touches your slabs.
- [ ] Pads clean: no grit, no lint. Use a lint roller.
- [ ] **Pocket 0 and pocket 12 are empty.** The run refuses to start otherwise. [Certain,
      `runner.survey`]
- [ ] Nothing is lying on top of the stacks, and nothing is above the fill line.
- [ ] Light roof on, if you fitted one. Lid closed, if you fitted the lid switch.
- [ ] E-stop released. Hands out of the bed.

## 2. Loading rules

![Loaded](img/storyboard_1_loaded.png)

| Rule | Why |
|---|---|
| **Face-down** (label and card facing the pad, the back facing up) | The cup only touches the back. The head camera reads the back QR/barcode. A face-up slab still gets read, but the cup then presses on its front. [Certain, DESIGN.md] |
| **Label end toward the front** (toward you) | It keeps the arm out of the camera's view of the label. [Certain, CONTRACT] |
| **Remove all sleeves and bags** | The cup can't seal through a sleeve, and a sleeve slides on the stack. |
| **Pockets 1–11 only.** Pocket 0 and pocket 12 start empty. | Stack 1 moves into pocket 0. Pocket 12 collects exceptions. [Certain] |
| **Fill to the gauge, never above it.** Stand a `fill_gauge` in the pocket: its top notch is the MAX line, 210 mm above the pad. | About 30 standard PSA slabs, or about 27 CGC. [Certain, `layout.py`] Higher, and the overfill beam blocks the start. |
| **Each slab flat and centred** between the rods. Lower bundles of 5–10 with your fingers in the front and back gaps (52 mm wide). | A slab sitting on a rod stops the run ("taller than expected"). [Certain] |
| **PSA and CGC can be mixed freely**, in any order and any holder thickness | Both are read and stacked normally. [Certain, `certs.py`] |
| **BGS and TAG are fine to load.** They are recognised and moved to pocket 12. | Status `other_grader`. [Certain] |
| **SGC: don't load.** Its holder is about 86 mm wide and the pocket is 84 mm. | [Likely, `layout.py`; measure one of yours] It won't go between the rods. Scan SGC by hand. |
| **Thick PSA holders are OK.** They are read and flagged "thick holder". | Fewer fit under the line, so trust the gauge, not a count. |

You don't need to sort, flip or order anything. The CSV records exactly where every slab ends up
(§6).

## 3. Starting a run

**Command line:**

```bash
python -m slabscan run --name "show-stock-oct"                 # asks one question, then runs
python -m slabscan run --name "high-value" --front-photo always  # also photographs every front (+~3 s/slab)
```

- `--front-photo always` is worth using on expensive slabs. A photo of both faces is your record
  against swapped cards and fake labels. [Likely, RESEARCH.md]
- **The run refuses to start** until `calibrate z` and `calibrate x` have been done. [Certain,
  `cli.py`]

**Web page:**
1. On the Pi, run `python -m slabscan web`, or install the boot service with
   `bash setup_pi.sh --service`.
2. On your phone, open `http://<pi-address>:8080/`. The command prints the address.
3. Type a batch name.
4. Choose **front photo: only when needed** or **every slab (+3 s)**.
5. Press **Start run** and confirm.

The page shows:
- the counts, the current pocket and the last label photo;
- the last 10 slabs;
- the stop message;
- downloads of `certs.csv` and `certs.txt`.

**Stopping on purpose**

| You do | The machine does |
|---|---|
| **Stop after this slab** (web), or Ctrl-C once | It finishes the slab in the cup, parks with nothing held, and halts. Resume later. [Certain] |
| Ctrl-C twice | It stops at once. **A slab may be left in the cup.** |
| **E-stop** | It cuts the 24 V: motors, pump and valves all stop. Use it for anything dangerous. §8.1. |

## 4. What the machine does

1. **Homes:** Z straight up, then X to the left switch.
2. **Survey** (1–3 min): it probes the top of every pocket. [Certain, `runner.survey`; time from
   the simulator]
   - It checks that pockets 0 and 12 are empty and that nothing is above the MAX line.
   - It measures every stack height.
3. **Shuffle one pocket left.** Stack 1 is moved slab by slab onto pocket 0, stack 2 onto pocket 1,
   and so on to stack 11 onto pocket 10.

![First transfer](img/storyboard_2_first_transfer.png)

**For every slab** [Certain, `runner.transfer`]:
1. A look from just above the top slab, which also gives a first read of the back.
2. A slow probe down to it.
3. The cup seals.
4. The first millimetre of lift is very slow (2 mm/s), so the slab underneath stays behind.
5. It lifts to carry height, 243 mm, and takes two more photos of the back.
6. **If the back can't be read** (old label, glare), it carries the slab over the upward camera in
   the middle of the row and reads the front.
7. It probes down onto the destination stack, measures the slab's thickness from the contact
   height, and vents the cup.

**Where each slab goes** [Certain, `runner.transfer`]:
- **`ok` and `needs_review`** go onto the next output stack.
- **`no_read`, `conflict` and `other_grader`** go to **pocket 12**.

![Midway](img/storyboard_3_midway.png)

When a stack is empty, the next stack moves into the pocket it just left.

![Done](img/storyboard_4_done.png)

**At the end:**
- stacks 1–11 sit in pockets 0–10, each one pocket left of where you loaded it;
- pocket 11 is empty;
- pocket 12 holds the slabs to check by hand;
- the head parks over pocket 0.

**Speed:** about 11 s per slab in the simulator, so about 1 hour for a full 330-slab load.
[Guessing until your first runs] BUILD_GUIDE §13.1 measures the real figure, which appears as
`mean cycle` in the summary.

## 5. Reading the results

Everything is in `batches/<batch id>/`:

| File | What it holds |
|---|---|
| `certs.csv` | One row per slab read, written row by row as it runs, so a crash loses nothing. |
| `certs.txt` | Only the `ok` certs, one per line, in machine order. Paste it into a spreadsheet or Card Dealer Pro. |
| `report.html` | Every row with its label photo(s). Opens on a phone. |
| `summary.json` | Counts per status, duplicates, the per-stack count check, `needs_attention`, the ITF format learned, mean cycle time. |
| `images/` | `NNNN_back.jpg` for every slab, plus `NNNN_front.jpg` when the front camera was used. NNNN = `position`. |
| `journal.jsonl`, `run.json`, `stop.json` | Machine log for `resume`, the run options, and why it last stopped. |

### 5.1 `certs.csv` columns

[Certain, `results.COLUMNS`]

| Column | Meaning |
|---|---|
| `batch_id` | Folder name: date-time plus your `--name` |
| `position` | 1, 2, 3 … the order the machine handled the slabs |
| `source_pocket` | The pocket the slab was loaded in (1–11) |
| `source_index` | Its place in that stack when loaded: **1 = top** |
| `out_pocket` | The pocket it is in now (0–10, or 12 for exceptions) |
| `out_index` | Its place in that pocket now: **1 = bottom** |
| `cert` | Cert number, leading zeros stripped |
| `grader` | `PSA`, `CGC`, `BGS`, `SGC`, `TAG` or `unknown` |
| `status` | See 5.2 |
| `sources` | Which codes agreed, joined with `+`: `back_qr`, `back_barcode`, `front_barcode`, `front_qr`, `ocr` |
| `raw_payload` | Exactly what the code said, e.g. the QR's URL |
| `note` | Why it isn't plain `ok`, plus flags like "thick holder", "thin/odd step" and "DOUBLE PICK" |
| `image_front`, `image_back` | Photo paths, relative to the batch folder |
| `scanned_at` | Local time |

### 5.2 Statuses

[Certain, `certs.consensus` and `runner.transfer`]

| Status | Meaning | Where the slab is | What you do |
|---|---|---|---|
| `ok` | A machine-readable code read with confirmation. A QR, or a learned ITF read twice. | output stack | Nothing. It's in `certs.txt`. |
| `needs_review` | A cert was found but isn't trusted. The note says why: "ocr only - verify by eye", "single ITF read - confirm", "ITF only; padding vs check digit not learned yet", "grader not confirmed", or **DOUBLE PICK**. | **output stack** (the default `needs_review_to = "output"`) | Check the photo against the slab, and type the cert in yourself. |
| `no_read` | Nothing decoded on either face | pocket 12 | Scan or type it by hand. Look at the photo: glare? damaged label? |
| `conflict` | Two codes on the slab disagree (e.g. QR ≠ barcode) | pocket 12 | **Check it carefully.** It can be a misread, but it's also what a doctored label looks like. |
| `other_grader` | BGS, SGC, TAG … | pocket 12 | Handle outside SlabRail. |

**`needs_review` slabs stay in the output stack by default.** To send them to pocket 12 instead,
put `needs_review_to = "exceptions"` in `config/calibration.toml`. [Certain, `config.py`]

### 5.3 The summary lines

Shown at the end of the run and in `summary.json`:
- **`duplicates`:** the same cert at two positions. Either you loaded the same slab twice, or a
  fake reuses a real cert number. [Likely, RESEARCH.md] Pull both slabs and compare them.
- **`count check`:** for each stack, the slabs counted against its surveyed height ÷ the measured
  slab thickness. "Every stack matches" means within one slab. Anything else says "check these
  stacks by hand". [Certain, `runner.count_check`]
- **`needs attention`:** every non-`ok` row with its pocket and position counted from the bottom.
  That is your to-do list.

### 5.4 Double picks

Sometimes two slabs cling together and come up as one. The machine can't see the lower one, but
it notices at set-down: the contact step is ≥ 11.6 mm instead of about 6.6. [Certain,
`t_double`]

- The read slab's row gets `needs_review` and the note **"DOUBLE PICK: an unread slab is directly
  under this one in pocket N"**.
- **The slab underneath has no row at all.** It sits at `out_index − 1` in the same pocket. That
  `out_index` number is skipped in the CSV, which is how you spot it.
- **To do:** take that slab out and scan it by hand (or put it in the next batch).
- The count check still matches, because the machine counts a double as two. [Certain, simulator
  run 2026-10-22]

### 5.5 The exception pocket

- **What lands there:** every `no_read`, `conflict` and `other_grader` slab, in the order they
  arrived. Its rows have `out_pocket = 12`; `out_index` 1 is the bottom.
- **When it fills:** it holds about 28 before the machine stops with "Exception pocket 12 is full".
  [Certain, arithmetic: it stops when the next two thick holders would cross the MAX line] Empty
  it and resume (§8). Counting there restarts from what is left.

## 6. Unloading and matching rows to slabs

**Where the stacks are:** stack *k* is now in pocket *k − 1* (stack 1 in pocket 0 … stack 11 in
pocket 10). Pocket 11 is empty and pocket 12 holds the exceptions. **Each stack's order is
reversed:** the slab that was on top is now at the bottom (`out_index` 1). [Certain, by
construction]

**The easy way to unload one pocket:**
1. Lift the whole stack out with your fingers in the front and back gaps.
2. **Turn it over as one block, so it's face-up.**
3. Now the top slab is `out_index` 1, the first slab the machine handled from that stack.
   - Going down the flipped stack follows `certs.csv` sorted by `position` for that `out_pocket`.
   - It's also the same top-to-bottom order you loaded the original stack in.
4. Do pocket 12 the same way.

**To find one slab** (for example a `needs_review` row):
- Look up its `out_pocket` and `out_index`.
- Count up from the bottom of that pocket, or down from the top of the flipped stack. Remember
  that a DOUBLE PICK leaves a gap in the `out_index` numbers.
- Compare the slab with its `image_back` photo in `report.html` before you act on it.

**Next batch:** unload every pocket. The next run needs pocket 0 and pocket 12 empty again.

## 7. Maintenance schedule

| When | Task | Why / how |
|---|---|---|
| **Every run** | Wipe the cup lip with IPA (§1) | Grit on the lip is the main scuff risk. [Certain, DESIGN.md] |
| Every run | Look at the cup lip | Replace it if it's nicked, flattened or hardened |
| Every run | Lint roller over the pads | Grit under a stack's bottom slab |
| **Weekly**, or every ~1,000 slabs | Wipe the pads' microfiber with a slightly damp microfiber cloth, then let them dry | DESIGN.md: pads weekly |
| Weekly | `python -m slabscan selftest -i` | Watch the trends: seal time and the `leak` kPa/s. A creeping leak means a fitting or the cup is going. |
| Weekly | Check the vacuum tube's slack at the cup, and the Z cable loop | The buffer rod rises 25 mm on contact (WIRING.md §11) |
| **Monthly**, or every ~5,000 slabs | **Belt:** deflection check, 100 g lifts the lower strand 13–23 mm (BUILD_GUIDE §6.6). Check the pulley grub screw too. | If you re-tension, re-run `calibrate x`. |
| Monthly | Rails: wipe, then a little lithium/PTFE grease on both | Dry rails get notchy. [Likely] |
| Monthly | Spot-check frame bolts, the gate post screws, the camera bracket and the lens lock nut | Vibration. Re-run `focus head` if the lens moved. |
| Monthly | Contact-sensor check: `selftest -i` probe trigger | The flag can bend in a knock |
| **Replace cup pads** | When the lip is damaged, the seal gets slow, the leak grows, or after any slab shows a mark. Spare SMC ZP25UU pads are in the BOM. | **Re-run `calibrate z` after every pad change**: the new pad's face height differs. [Likely] |
| Replace pad facing | When the microfiber is worn shiny or stained | Re-glue a new facing (BUILD_GUIDE §5.5) |
| After any crash or a knock to the head | `calibrate z`, `calibrate x`, `focus head`, `focus station --save`, `selftest -i --motion` | Positions and focus may have moved |

Keep a copy of `config/calibration.toml` off the Pi.

## 8. When it stops

When the machine stops on its own:
- the message says what happened and what to do;
- it's saved in `batches/<id>/stop.json` and shown on the web page.

If a slab was in the cup and the vacuum is fine, the machine first puts it back on top of the
stack it came from, so it gets read again. [Certain, `runner.secure`]

**After fixing the cause:** `python -m slabscan resume batches/<id>`, or **Resume** on the web
page. Resume:
1. reconnects and homes;
2. probes every pocket again and compares it with what the journal expects;
3. continues.

Every slab still appears exactly once. [Certain, in the simulator: `tests/test_resume.py`, 8
passed when I ran it on 2026-10-22]

### 8.1 The table

Messages are quoted from the code, shortened where marked "…". [Certain]

| Message (start of it) | What happened | What you do |
|---|---|---|
| **Before the start** | | |
| "… has no pad_trigger_c / offset_x yet. Run `calibrate z` and `calibrate x` first" | Not calibrated | BUILD_GUIDE §12.1–12.2 |
| "Close the lid to start." | Lid switch open | Close it |
| "The overfill light beam is blocked: a stack is above the MAX line …" | Something is taller than 214 mm, or the beam is out of line | Check every stack with the fill gauge and look for a slab lying on top. Then `selftest -i` for the beam. |
| "The cup line is holding vacuum (… kPa): a slab may still be stuck to the cup." | A slab is left on the cup from before | Hold the slab, vent (§8.2), put it face-down on top of the stack it came from, then start again |
| **During the survey** | | |
| "Pocket N (empty_start / exceptions) must start empty but is … mm tall." | Something is in pocket 0 or 12 | Empty it and restart |
| "Pocket N is filled above the MAX line …" | Overfilled | Take slabs off and restart |
| "Pocket N: probe never touched anything (not even the pad)." | The contact sensor didn't trip | Check the flag and the sensor (`selftest -i`). **Don't resume until the probe test passes.** |
| "Pocket N: the cup sealed on something but the contact sensor did not trip. Contact sensor fault …" | The second, vacuum-based contact check caught a dead sensor | Same as above |
| **While moving slabs** | | |
| "Pocket N is … mm taller than expected - was a slab added or is one sitting crooked?" | A slab is on a rod, or someone added one | Seat it flat (or take the added slab off), then resume |
| "Pocket N: no contact where the stack should be (predicted … mm). Check the contact sensor, then resume." | The stack is lower than expected: a slab was removed, or the sensor is weak | Count the stack against the CSV. `selftest -i`. Resume. |
| "Pocket N: cup will not seal on the top slab (dirty cup, warped or face-up slab?)." | No seal, even after a second try | Wipe the cup with IPA. Check the slab is face-down, flat and unsleeved. Resume. |
| "Vacuum lost after peel / in transit (… kPa). A slab may have dropped." plus "The head was left where it is with the valves shut. If a slab is still on the cup, hold it and pull it off gently. Put that slab (or the one that fell) face-down on top of pocket N." | Vacuum dropped while holding. It doesn't vent or move, because venting could drop a slab that's still stuck. [Certain] | Do exactly that. Check the dropped slab for damage. Run `selftest -i` (leak) before resuming. |
| "Exception pocket 12 is full. Empty it …, then resume." | About 28 exceptions | Unload pocket 12 (§6) and resume. It recounts from what's left. |
| "Placing onto pocket N: no contact - output stack lower than expected." | The output stack is lower than recorded | Check that stack for a fallen or removed slab, then resume |
| "Placing onto pocket N: contact … above the stack - something is in the way." | An object, or a crooked slab, on the output stack | Clear it, then resume |
| "Lid opened - run paused with nothing held." | Lid opened | Close it and resume |
| "Stopped on request - nothing held. Resume to continue." | You pressed Stop | Resume when ready |
| **Controller and power** | | |
| "The controller lost power or its USB link (E-stop pressed, or the cable came out). The head stopped where it was; the motors are off. [A slab from pocket N is still on the cup …]" | E-stop, or the USB came out. The Pi shut both valves, so a held slab stays sealed for a while. [Certain, `runner.lost_note`] | **Hold the slab, pull it off gently, and put it face-down on top of pocket N.** Twist the E-stop to release it, then resume. It reconnects and homes first: Z straight up, then X. |
| "The controller is still not answering … check the USB cable and the 24 V supply" | The CH340 didn't come back within 15 s | Wait 10 s and resume again. Check the E-stop is released, the 24 V supply, and the USB cable. |
| **Anything else** | | |
| "Interrupted (Ctrl-C twice) in the middle of a move. A slab may be in the cup …" | You stopped it hard | Check the head. If a slab is on it, §8.2. Then resume. |
| "<ErrorType>: … The machine stopped without parking: check the head (a slab may be in the cup), then resume." | An unplanned error, e.g. a camera dropping off USB or a controller ALARM | **Look at the head right away.** Software gap [Certain, code and simulator]: this path doesn't put a held slab back, so it may be hanging on closed valves and will drop when the cup line leaks down. Hold it, vent (§8.2), put it on top of the stack being emptied (the web page's current pocket). Then fix the cause (§8.3) and resume. |
| "Could not park the machine automatically (…). Check the head before touching the bed." | The put-back after a stop failed | Same as the row above |
| **On resume** | | |
| "The stacks changed since the run stopped: pocket N: … mm now, … mm when the run stopped (±n slabs) …" | A slab was added, removed or moved while stopped | Put things back as they were. If it says "It looks like one slab went from pocket A to pocket B …", move that top slab back as told. Or use `resume --accept-heights` if you changed things on purpose: the count check will flag it. |
| "exception pocket 12 was emptied to … mm; counting continues from …" | Info: you emptied pocket 12 | Nothing |
| "resume: the run stopped before the first survey finished - starting it from the beginning" | Info | Nothing |

### 8.2 Venting the cup by hand

If a slab is stuck on the cup and the software isn't running, hold the slab with one hand and
open the vent valve for a second:

```bash
pinctrl set 22 op dh; sleep 1; pinctrl set 22 op dl
```

GPIO 22 is the vent valve. [Certain, CONTRACT] `pinctrl` is the Raspberry Pi OS GPIO tool
WIRING.md §15 uses. [Likely] Don't do this while `slabscan` is still running, because both would
drive the same pin.

### 8.3 Repeated stops of one kind

| Pattern | Look at |
|---|---|
| "cup will not seal" on many slabs | A cup lip worn or dirty; a leak (`selftest -i` → `leak`) |
| "Vacuum lost in transit" more than once | A leak in the cup line; the pump; whether the slab is knocking a rod (watch a carry) |
| "taller than expected" on random pockets | Slabs placed crooked: X calibration (`calibrate x`), belt tension, a leaning rod |
| Camera errors | The head camera's USB extension in the drag chain (WIRING.md §16 risk 4) |
| Many `no_read` | Focus (`focus head`, `focus station --save`), a ring not lighting, glare. Fit the light roof. |
| Many `needs_review` "ITF only … not learned yet" in the first batches | Normal. It learns after 3 slabs where QR and ITF agree, and the setting is kept for that batch. [Certain, `ItfModel`] |

## 9. Quick card

Print this and tape it to the machine.

```
BEFORE   cup wiped (IPA) - pockets 0 and 12 empty - no stack above the gauge - sleeves off
LOAD     face-DOWN, label toward you, pockets 1-11, PSA+CGC mixed OK, BGS/TAG OK (go to 12), NO SGC
START    python -m slabscan run --name NAME        (or the web page: Start run)
STOP     web "Stop after this slab" / Ctrl-C once = clean stop.  E-STOP for anything dangerous.
RESUME   python -m slabscan resume batches/<id>    (or web: Resume)
AFTER    stack k is now in pocket k-1, upside-down order. Flip a stack face-up = CSV order.
         Pocket 12 = check by hand.  needs_review = check by hand (still in its output stack).
         DOUBLE PICK row = one unread slab directly under it, no row of its own.
WEEKLY   pads wiped, selftest -i.   MONTHLY  belt, rails, bolts.   NEW CUP PAD -> calibrate z
```
