# Operating SlabRail

Weekly use: loading, running, reading the results, unloading, maintenance, and what to do when
it stops. The build and the acceptance tests are in [BUILD_GUIDE.md](BUILD_GUIDE.md). Commands
are run from `~/psa-slab-scanner/software` (BUILD_GUIDE §11.2 puts the project there) with the
venv active (`source .venv/bin/activate`).

Confidence tags: **[Certain]** = read in the code (`software/slabscan/`) or the CAD. **[Likely]**
= strong inference. **[Guessing]** = not yet measured on a real machine.

## Read this first

- **Only use it on inventory after every BUILD_GUIDE §13 test has passed.** [Certain that none of
  this has run on real hardware yet] Until then, every batch is a test batch.
- **`certs.csv` has one row per slab you loaded.** [Certain, `runner.py`] When two slabs come up
  together (DOUBLE PICK), the read one gets its row and the one underneath gets an extra
  `no_read` row whose note starts `UNREAD:`. That slab is in the **output pocket**, directly under
  the read one, not in pocket 12 (§5.4). Always check the count line in the summary.
- **Slabs without a back-label code stop the run until the learned check is active.** [Certain,
  `runner._check_face_down`] Before the cup touches a slab, the head camera must prove it is
  face-down: a code printed only on the back label (a PSA back QR, a CGC back QR, or the CGC 2020–23
  back barcode), or, in the default `learned` mode, a card window that matches the card backs of
  slabs proven earlier (§8.4). The learned part works only after a Phase 0 GO, 5 references and a
  clear view of the card window on 5 proven slabs; today's head leaves that window clear [Certain,
  CAD]. Until then, PSA 2016 and older labels, CGC Authentic, BGS and SGC slabs stop the run until
  you check each one (§8.1): 14 of 64 real slabs in a public-scan sample [Certain, RESEARCH.md §4].
  CGC 2023+ and 2020–23 slabs no longer stop. For stacks you checked yourself, start with
  `--all-face-down` (§3).
- **A slab whose front code is visible from above is FACE-UP, and the run says so.** A CGC
  front-label barcode or a CGC Authentic QR seen from above stops the run untouched with a
  "FACE-UP" message. A PSA front proves nothing either way (its barcode is printed on both labels).
- **A Z stall stops the run before the head moves sideways.** [Certain, `runner._carry_check`;
  tested in the simulator] The carry-height sensor on the Z spine must read "at carry height"
  before every sideways move, so a stall that left the head more than about 2.5 mm low is caught
  (a smaller one still clears the rods). The run then stops, and a held slab is lowered straight
  onto its own pocket, or held on the pump for you (§8.1).
- **Only the E-stop removes motor power.** Ctrl-C twice halts the motors at once and nothing moves
  afterwards, but they stay powered. [Certain, `runner.hard_stop`]
- **A wrong cert is worse than no cert.** The software refuses to guess: two codes that disagree
  give `conflict`, and a barcode-only read (ITF or Code128, any grader) with nothing to confirm it
  gives `needs_review`. Even two barcodes that agree get their printed digits checked by OCR. An
  `ok` also needs its grader confirmed: a code that names it (a cert URL), two printed codes in
  its format, or an 8-digit ITF whose digits OCR of the printed number confirms (that names PSA).
  So **a pre-2016 PSA slab is `ok` only when OCR agrees with its front ITF**, its only code; when
  OCR reads nothing or other digits it is `needs_review`. Any other single barcode stays
  `needs_review` even when OCR agrees. A number read only by OCR has no grader and always goes to
  pocket 12. Respect those statuses. Don't paste `needs_review` certs into your inventory
  unchecked.
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
- [ ] Nothing in the carry-height sensor's slot on the Z spine (a card or dust there stops the run
      at the first pick).
- [ ] E-stop released. Hands out of the bed.
- [ ] Using the command line? Stop the web service first (`sudo systemctl stop slabrail-web`):
      only one slabscan program may use the machine at a time, and the second one is refused.

## 2. Loading rules

![Loaded](img/storyboard_1_loaded.png)

| Rule | Why |
|---|---|
| **Face-down** (label and card facing the pad, the back facing up). A hard rule. | The cup only touches the back. Before the cup touches a slab, the head camera must see a back-label code, or (learned mode, once active) a card back it knows. If it can't (a face-up slab; a slab with no back-label code: PSA 2016 and older, CGC Authentic, BGS, SGC) the run stops with nothing touched until you check it (§8.1). With `--all-face-down` that check is off and a face-up slab gets the cup on its front. [Certain, `runner.py`] |
| **Label end toward the front** (toward you) | It keeps the arm out of the camera's view of the label. [Certain, CONTRACT] |
| **Remove all sleeves and bags** | A smooth sleeve may well seal under the cup [Guessing], but the slab can then slide out of the sleeve during the 2 m/s² moves, and nothing detects a sleeve. A sleeve also slides on the stack. |
| **Pockets 1–11 only.** Pocket 0 and pocket 12 start empty. | Stack 1 moves into pocket 0. Pocket 12 collects exceptions. [Certain] |
| **Fill to the gauge, never above it.** Stand a `fill_gauge` in the front finger gap, its foot on the bed, against the stack. **The underside of its top bar is the MAX line.** The notches mark 0, 5, 10 … 30 slabs of 6.6 mm; the top notch (198 mm) is *not* the MAX line. | The bar underside is 210 mm above the bed, so 207 mm above the pad: the gauge errs 3 mm on the safe side because the bed sits 3 mm below the pad top. About 30 standard PSA slabs, or about 27 CGC. [Certain, `model.fill_gauge`, `layout.py`] Higher, and the overfill beam blocks the start. |
| **Each slab flat and centred** between the rods. Lower bundles of 5–10 with your fingertips in the front and back gaps (52 mm wide), following the bundle down; let go only when it rests on the stack. Never drop a bundle in. | A slab sitting on a rod stops the run ("taller than expected"). [Certain] |
| **PSA and CGC can be mixed**, in any order and any holder thickness | Both are read and stacked normally. [Certain, `certs.py`] Measure one CGC holder before the first CGC batch: it must be ≤ 82.6 mm wide. CGC 2023+ and 2020–23 "OG" slabs are proven face-down by their back QR. CGC Authentic slabs carry their codes on the front only, so they stop at the face-down check like old PSA labels until the learned check is active. [Likely, CAD card-plane check] The card window has about zero margin on CGC: a CGC slab pushed into a pocket corner can have about 1.5% of the window on the holder (up to about 4.5% at most); PSA slabs stay on the card. Audit learned CGC rows (§8.4). |
| **BGS and TAG: measure one first.** Load them only if the holder is ≤ 82.6 mm wide (the pocket is 84 mm). BGS labels carry no code, so a BGS slab stops at the face-down check (until the learned check is active) and ends in pocket 12 as `no_read` or as an OCR-only `needs_review`; `other_grader` appears only if a BGS, SGC or TAG URL is read. | [Guessing] BGS holders may be wider than PSA's, and no width here has been measured. A wider holder rubs or jams on the dowels at every pick and placement. |
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
- `--all-face-down` turns the face-down check off for this batch (it is remembered on resume).
  Use it only when you loaded every stack yourself and checked it, for example a batch of older
  labels that would otherwise stop at every slab. A slab that is face-up after all then gets the
  cup on its front. The web page has the same choice as a checkbox.
- **The run refuses to start** until `calibrate z` and `calibrate x` have been done. [Certain,
  `cli.py`]
- **The start line `face-down check: …` says what the check does this run** [Certain,
  `runner.face_down_status`]:
  - `back-label codes only - every slab without one (a PSA back QR, a CGC back QR or the CGC
    2020-23 back barcode) stops for you` (`face_down_check = "stop"`);
  - `learned check not active yet: <why>. Until then every slab without a back-label code (…)
    stops for you, as in 'stop' mode` (the default mode, not ready yet: normal in the first batches
    after Phase 0);
  - `learned check not active: over an empty pocket the head camera sees edges where only the pad
    should show … Re-aim the head camera (BUILD_GUIDE 7.7) …` (the camera-aim check failed, §8.4;
    the same in every stop of that run);
  - `learned check not active: the head camera's aim is not checked this run yet …` (a resume whose
    survey found no empty pocket: §8);
  - `learned (threshold 0.56, 23 references in 1 prototype(s) …): a slab without a back-label code
    is picked only if its card window matches a known card back` (§8.4);
  - `OFF - a slab loaded face-up gets the cup on its front` (`--all-face-down`, or
    `face_down_check = "off"`).

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
| Ctrl-C twice | **Hard stop.** The motors halt where they are (feed hold, then a controller reset) and **nothing moves after that**. They stay powered. A slab in the cup stays on it, held by the pump; the program asks you to hold it and type `vent` (web: the Vent button), and you put it face-down on top of the pocket it names. The next run or resume homes first. [Certain, `runner.hard_stop`, `cli.hand_off_slab`] |
| **E-stop** | It cuts the 24 V: motors, pump and valves all stop. **The only stop that also removes motor power**: use it for anything dangerous. A held slab then hangs on the closed cup line for seconds to minutes only: take it off right away. §8.1. |

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
1. A look from just above the top slab: the face-down check (a back-label code must be visible, or
   in learned mode a card window that matches a known card back) and a first read of the back. In
   learned mode the survey also takes one head frame over the first empty pocket
   (`images/face_down_empty.jpg`): every card window is compared with it, so a head part in the
   way is noticed, and the camera's aim is checked on it. A failed aim check logs a
   `CAMERA AIM (pocket N, …)` line and turns the learned check off for that run. [Certain,
   `runner._take_baseline`] A resume whose survey finds no empty pocket takes that view over the
   first source pocket it empties instead (§8).
2. A slow probe down to it. Every downward move is a probing move, so anything unexpected in the
   way stops the head.
3. The cup line must read atmosphere, then the cup seals.
4. The lift is slow (2 mm/s) through the point where the cup leaves the slab, then pauses 0.5 s
   just above the stack, so the slab underneath stays behind.
5. It lifts to carry height, 248 mm, and takes two more photos of the back. Before it moves
   sideways, the carry-height sensor must confirm the head really is up there (a stalled Z motor
   would leave it low). [Certain, `runner._go`]
6. **If the back can't be read** (old label, glare), or the read is barcode-only (no QR), it
   carries the slab over the upward camera in the middle of the row and photographs the front,
   then decodes it and runs OCR on the printed digits, with the slab over its output stack. OCR
   that reads other digits makes the slab `needs_review`. For a pre-2016 PSA slab (front ITF
   only), OCR that agrees is what makes it `ok`. [Certain, `runner.needs_ocr`,
   `certs.psa_itf_confirmed`]
7. It probes down onto the destination stack (slowly past the rod tops), measures the slab's
   thickness from the contact height, vents the cup and checks the vent worked before it lifts.

**Where each slab goes** [Certain, `runner.transfer`]:
- **`ok`, and `needs_review` with grader PSA or CGC,** go onto the next output stack.
- **`needs_review` with any other grader** (`unknown`: OCR only, or a number with no grader's
  format; two graders, `PSA/CGC`; none) goes to **pocket 12**, whatever `needs_review_to` says: it
  may not even be PSA or CGC.
- **A grader guessed from a barcode's length** (note "grader … not confirmed") counts as PSA or
  CGC, so that slab stays in the output stack. Another grader's slab whose barcode has a PSA or CGC
  format can therefore end up there too. [Certain, `runner.transfer`] Check every `needs_review`.
- **The same goes for an `ok` from the 8-digit ITF rule.** Another grader's slab with an 8-digit
  ITF whose printed number OCR reads would come out `ok PSA`, with the right digits and the wrong
  grader, in the output stack. [Guessing that such a slab exists: none of the 64 real slabs had
  one] See §5.2.
- **A code in no grader's format is not read as a cert:** a 7-digit Code128, a 10-digit one
  starting with 0 (a BGS-style number), or an ITF of any length but 8. It is listed as unparsed,
  so a slab with nothing else readable ends `no_read` (or OCR-only) in pocket 12. [Certain,
  `certs.parse_payload`]
- **`no_read`, `conflict` and `other_grader`** go to **pocket 12**, except the `UNREAD` row of a
  double pick: that slab came along under a read one and sits in the output pocket (§5.4).

![Midway](img/storyboard_3_midway.png)

When a stack is empty, the next stack moves into the pocket it just left.

![Done](img/storyboard_4_done.png)

**At the end:**
- stacks 1–11 sit in pockets 0–10, each one pocket left of where you loaded it;
- pocket 11 is empty;
- pocket 12 holds the slabs to check by hand;
- the head parks over pocket 0.

**Speed:** about 14 s per slab, so about 79 minutes for a full 330-slab load in the timing
simulation (`sim --slabs 330`). [Guessing until your first runs] Slabs that need the front camera and OCR take up
to 30 s longer, and every face-down-check stop waits for you. BUILD_GUIDE §13.1 measures the real
figure, which appears as `mean cycle` in the summary.

## 5. Reading the results

Everything is in `batches/<batch id>/`:

| File | What it holds |
|---|---|
| `certs.csv` | One row per slab, written row by row as it runs, so a crash loses nothing. |
| `certs.txt` | Only the `ok` certs, one per line, in machine order. Paste it into a spreadsheet or Card Dealer Pro. |
| `report.html` | Every row with its label photo(s). Opens on a phone. |
| `summary.json` | Counts per status, duplicates, the per-stack count check, `needs_attention`, `itf_mode` (always `zero_pad`: the ITF is the cert padded to 8 digits) and `itf_evidence` (slabs where QR and ITF agreed), mean cycle time, and `face_down` (§5.3), which in learned mode holds `camera_aim`. |
| `images/` | `NNNN_back.jpg` for every slab, plus `NNNN_front.jpg` when the front camera was used. NNNN = `position`. In learned mode also `face_down_window.jpg` (the run's first slab with the card window drawn in red) and `face_down_empty.jpg` (the view over an empty pocket). |
| `journal.jsonl`, `run.json`, `stop.json` | Machine log for `resume` (including the face-down events, §8.4), the run options, and why it last stopped. |

### 5.1 `certs.csv` columns

[Certain, `results.COLUMNS`]

| Column | Meaning |
|---|---|
| `batch_id` | Folder name: date-time plus your `--name` |
| `position` | 1, 2, 3 … the order the machine handled the slabs |
| `source_pocket` | The pocket the slab was loaded in (1–11) |
| `source_index` | Its place in that stack when loaded: **1 = top** |
| `out_pocket` | The pocket it is in now (0–10, or 12 for exceptions) |
| `out_index` | Its place in that pocket now: **1 = bottom**, so the top slab has the highest number |
| `cert` | Cert number, leading zeros stripped |
| `grader` | `PSA`, `CGC`, `BGS`, `SGC`, `TAG` or `unknown` (an OCR-only number, or a code with no grader's format) |
| `status` | See 5.2 |
| `sources` | Which codes agreed, joined with `+`: `back_qr`, `back_barcode`, `front_barcode`, `front_qr`, `ocr`. A QR's tag follows the label side its payload proves, whichever camera read it: `back_qr` is a PSA or graded CGC QR, `front_qr` the CGC Authentic QR. |
| `raw_payload` | Exactly what the code said, e.g. the QR's URL |
| `note` | Why it isn't plain `ok`, plus flags like "thick holder", "thin/odd step" and "DOUBLE PICK" |
| `image_front`, `image_back` | Photo paths, relative to the batch folder |
| `scanned_at` | Local time |
| `face_down` | How the slab was proven face-down before the cup touched it: `qr` (a PSA or CGC back QR seen from above), `code` (the CGC 2020–23 back barcode), `operator` (your `--face-down-ok`), `learned(0.93)` (card-window match, with its score: check its photo, §8.4) or `off` (check off). Empty on a double pick's `UNREAD` row. |

### 5.2 Statuses

[Certain, `certs.consensus` and `runner.transfer`]

| Status | Meaning | Where the slab is | What you do |
|---|---|---|---|
| `ok` | A machine-readable code read with confirmation, and its grader confirmed: a QR, or a barcode on two printed symbols (back and front label) or confirmed by OCR of the printed digits, plus a code that names the grader (a cert URL), two printed codes in its format, or an 8-digit ITF whose digits OCR confirms (grader PSA; note "barcode confirmed by OCR; grader PSA from its 8-digit ITF": a pre-2016 PSA slab). A two-barcode `ok` has had its digits checked by OCR too; if OCR read nothing, it stays `ok`. | output stack | Nothing. It's in `certs.txt`. |
| `needs_review` | A cert was found but isn't trusted. The note says why: "grader PSA not confirmed: no code names it and only one printed barcode has its format (OCR confirms its digits, not its grader) - check it is a PSA slab" (one Code128 only, often after "barcode confirmed by OCR"), "one printed barcode only (no QR) - confirm" (for example a pre-2016 PSA slab whose OCR read nothing), "barcode N but OCR read M - verify by eye" (OCR read other digits), "OCR only (no barcode or QR read), grader unknown - check by hand", "grader not confirmed (a code with no grader's format)", "read only in the frame from above the stack (a neighbour's label?)", "N-digit PSA cert, but Phase 0 saw only … digits", or **DOUBLE PICK**. Any note can start "dropped a phantom read Code128:…": a thin false read inside a real barcode, dropped only when a different code or OCR confirms the other number. If the confirmed number is the thin read itself, the slab is a `conflict` instead. | **output stack** (the default `needs_review_to = "output"`) if the grader is PSA or CGC; **pocket 12** otherwise | Check the photo against the slab, and type the cert in yourself. |
| `no_read` | Nothing decoded on either face | pocket 12. **Exception:** a row whose note starts `UNREAD:` is the hidden slab of a double pick; it is in the output pocket the row names (§5.4) | Scan or type it by hand. Look at the photo: glare? damaged label? |
| `conflict` | Two codes on the slab disagree (e.g. QR ≠ barcode), the cert was already recorded earlier in this batch, or the back-label code that proved it face-down before the pick was another cert ("… this slab may have been FACE-UP and the cup may have touched its front - check it by hand") | pocket 12 | **Check it carefully.** It can be a misread or a neighbour's label in view, but it's also what a doctored label or a reused cert number looks like. For the last kind, also look at the slab's front for a cup mark. |
| `other_grader` | A BGS, SGC or TAG URL was read | pocket 12 | Handle outside SlabRail. |

**`needs_review` slabs with grader PSA or CGC stay in the output stack by default.** To send them to
pocket 12 too, put `needs_review_to = "exceptions"` in `config/calibration.toml`. [Certain,
`config.py`, `runner.transfer`]

**What `needs_review` means.** The machine found a number, but one piece of the evidence it needs
for an `ok` is missing or disagrees: a second printed code or OCR for the digits, or a code that
confirms the grader. The note names which. On the 64 real slabs only 2 pre-2016 PSA slabs ended
there on the images as they are (OCR read nothing on one and other digits on the other), and none
at the machine's resolution. [Certain for that set; `tools.real_eval`]

**Two settings change what can be `ok`** (BUILD_GUIDE §11.5) [Certain, `runner._decide`,
`certs.parse_payload`]:
- `psa_cert_digits`: a PSA cert of a length not in the list is `needs_review`. Lengths count
  without leading zeros, so **include 7** if you have pre-2016 slabs: a cert printed `02074012` has
  7 digits. Leave it out, and every 7-digit pre-2016 cert becomes `needs_review`.
- `custom_regex`: with it set, every ITF is typed by your pattern, so the 8-digit ITF rule never
  fires and every pre-2016 PSA slab is `needs_review` ("grader PSA not confirmed"). Safe, but set
  it only if Phase 0 found a prefix or suffix around the cert.

**The 8-digit ITF rule rests on one assumption** [Guessing]: that only PSA prints an 8-digit ITF.
In the real set only PSA labels carry ITF, but that set has just 1 BGS and 1 SGC slab, and neither
showed a code. BGS and SGC are reported to print a barcode or a QR on some holders, of unknown
type [Likely, second-hand]. If you deal other graders, put a few of their slabs through Phase 0
(or photograph them and check the photos with `python -m tools.real_eval`, BUILD_GUIDE §1.7)
before you trust `ok PSA` on slabs with no QR: an `ok PSA` on a BGS or SGC slab means the rule is
wrong for them. Tell the software owner.

### 5.3 The summary lines

Shown at the end of the run and in `summary.json`:
- **Repeated certs:** the second slab with a cert already in the batch becomes a `conflict` row
  (note "cert … was already recorded at #N in this batch") and goes to pocket 12. Either you
  loaded the same slab twice, the camera saw a neighbour's label, or a fake reuses a real cert
  number. [Likely, RESEARCH.md] Pull both slabs and compare them. The `duplicates` line counts what
  is left after that rule and is normally "none".
- **`count check`:** for each stack, the slabs counted against its surveyed height ÷ the measured
  slab thickness. "Every stack matches" means within one slab. Anything else says "check these
  stacks by hand". [Certain, `runner.count_check`]
- **`needs attention`:** every non-`ok` row with its pocket and position counted from the bottom.
  That is your to-do list.
- **`face-down:`** how the batch's slabs were proven face-down, e.g. `face-down: 287 by back QR,
  41 by the learned card-back match, 2 confirmed by you` (a CGC 2020–23 back barcode adds "N by a
  back-label barcode"). If any were learned, it adds the lowest learned score and its position:
  check the back photos of the learned ones. In `report.html` the Face-down column shows the same
  per slab, with learned rows in bold. `summary.json`'s `face_down` holds the mode, the counts,
  every learned row (position, pocket, score, back photo), the references, this run's stops and
  `camera_aim`: `ok`, what was wrong, "not checked" when no view over an empty pocket exists yet,
  or "not checked this run (the resume survey found no empty pocket, and no source pocket was
  emptied after it)".
  [Certain, `cli.face_down_line`, `runner._face_down_summary`]
- **`CAMERA AIM: …`** (only when the aim check failed): "The learned check accepted nothing this
  run. Re-aim the head camera (BUILD_GUIDE 7.7)". [Certain, `cli.summary_lines`]

### 5.4 Double picks

Sometimes two slabs cling together and come up as one. The machine can't see the lower one, but
it notices at set-down: the contact step is ≥ 11.6 mm instead of about 6.6. [Certain,
`t_double`]

- The read slab's row gets `needs_review` and the note **"DOUBLE PICK: an unread slab is directly
  under this one in pocket N"**.
- **The slab underneath gets its own row:** status `no_read`, the note starting
  **`UNREAD: lifted together with #position`**, the same `position` number as the read slab, the
  same `out_pocket`, and `out_index` one lower. [Certain, `runner.transfer`]
- **It is in the output pocket, not in pocket 12**, directly under the read slab.
- **To do:** take that slab out and scan it by hand (or put it in the next batch).
- The count check still matches, because the machine counts a double as two. [Certain, simulator]

### 5.5 The exception pocket

- **What lands there:** every `no_read`, `conflict` and `other_grader` slab (except the `UNREAD`
  rows of double picks), in the order they arrived. Its rows have `out_pocket = 12`; `out_index` 1
  is the bottom.
- **When it fills:** it holds about 28 before the machine stops with "Exception pocket 12 is full".
  [Certain, arithmetic: it stops when the next two thick holders would cross the MAX line] Empty
  it and resume (§8). Counting there restarts from what is left.

## 6. Unloading and matching rows to slabs

**Where the stacks are:** stack *k* is now in pocket *k − 1* (stack 1 in pocket 0 … stack 11 in
pocket 10). Pocket 11 is empty and pocket 12 holds the exceptions. **Each stack's order is
reversed:** the slab that was on top is now at the bottom (`out_index` 1), and the **top slab of
every pocket has that pocket's highest `out_index`**. [Certain, by construction]

**Never lift a whole stack out or turn it over.** A full pocket is about 200 mm and 2 kg of slick
slabs, and fingertips in the gaps only reach their top ends: slabs slip out of the middle, and
their fronts slide across each other's backs.

**How to unload one pocket:**
1. Have a tray or box ready next to the machine.
2. Take slabs off the **top**, **at most 5 at a time**, fingertips in the front and back gaps.
3. Put each bundle in the tray **face-down, as it came out**, each new bundle behind (or under)
   the previous one, so the order is kept.
4. The first slab you take is that pocket's highest `out_index`; count down from there. In
   `certs.csv`, sort that pocket's rows by `out_index` from high to low: that is the order you
   unload them in.
5. Do pocket 12 the same way.

**To find one slab** (for example a `needs_review` row):
- Look up its `out_pocket` and `out_index`.
- Count up from the bottom of that pocket (`out_index` 1), or down from the top (the highest
  `out_index`). A DOUBLE PICK's `UNREAD` row has its own `out_index` (one below the read slab),
  so there are no gaps.
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
| Weekly | Check the vacuum tube's slack at the cup elbow, and the Z cable loop | The buffer rod rises up to 20 mm on contact (WIRING.md §11) |
| **Monthly**, or every ~5,000 slabs | **Belt:** deflection check, a 100 g sideways pull at mid-span moves the lower strand 13–23 mm (BUILD_GUIDE §6.6). Check the pulley grub screw too. | If you re-tension, re-run `calibrate x`. |
| Monthly | Rails: wipe, then a little lithium/PTFE grease on both | Dry rails get notchy. [Likely] |
| Monthly | Spot-check frame bolts, the gate post screws, the camera bracket and the lens lock nut | Vibration. Re-run `focus head` if the lens moved. |
| Monthly | Contact-sensor check: `selftest -i` probe trigger; push the cup up by hand and feel for the flag rubbing in its guide | The flag can bend in a knock (BUILD_GUIDE §7.6) |
| Monthly | Carry-height sensor: blow its slot clear, then `selftest --motion` → `carry sensor … trips at about 246.x mm` | Dust in the slot reads "blocked" and stops the run; a mount that slid moves the trip (BUILD_GUIDE §7.4a) |
| Monthly | **E-stop check:** machine idle, press the E-stop. The software must report the controller lost, and a meter on the 24 V switched bus must read 0 V. Release, `home`. | The contact switches the 24 V capacitor inrush and can weld closed without any sign (WIRING.md §1.3). If the bus stays live, stop using the machine and replace the contact blocks. |
| **Replace cup pads** | When the lip is damaged, the seal gets slow, the leak grows, or after any slab shows a mark. Spare SMC ZP25UU pads are in the BOM. | **Re-run `calibrate z` after every pad change**: the new pad's face height differs. [Likely] |
| Replace pad facing | When the microfiber is worn shiny or stained | Re-glue a new facing (BUILD_GUIDE §5.5) |
| After any crash or a knock to the head | `calibrate z`, `calibrate x`, `focus head`, `focus station --save`, `selftest -i --motion` | Positions and focus may have moved |

Keep a copy of `config/calibration.toml` off the Pi.

## 8. When it stops

When the machine stops on its own:
- the message says what happened and what to do;
- it's saved in `batches/<id>/stop.json` and shown on the web page.

What happens to a slab in the cup [Certain, `runner.secure`, `cli.hand_off_slab`]:
- **After a planned stop or an unexpected error** (a camera dropping off USB, a decoder bug, a
  controller error), the head first re-reads its real position, lifts straight up, and puts the
  slab back on top of the stack it came from, so it gets read again. If the vacuum is low, it
  carries the slab back slowly and probes it down.
- **After a Z stall** (the carry-height sensor read clear at travel height), the head may be lower
  than the controller thinks, so the slab is never carried sideways. Over its own pocket the head
  goes straight down in one probe move (it stops on contact, whatever the real height) and vents
  the slab there. Anywhere else nothing moves, and the pump holds the slab for you. [Certain,
  `runner._set_down_after_stall`]
- **When moving is unsafe**, nothing moves at all: Ctrl-C twice, the controller lost (E-stop or
  USB), a controller ALARM, a failed vent, a vacuum sensor fault, a slab already hanging on the
  cup. The pump keeps holding the slab while the Pi has power. The command line then asks you to
  hold the slab and type `vent` (the web page shows a **Vent** button); put it face-down on top of
  the pocket the message names. Never just close the program with a slab on the cup: the valves
  then shut and it hangs only until the line leaks down.

**After fixing the cause:** `python -m slabscan resume batches/<id>`, or **Resume** on the web
page. Resume asks "hands clear?" first (skip it with `--yes`). Resume:
1. reconnects and homes;
2. probes every pocket again and compares it with what the journal expects;
3. continues.

**In learned mode, empty pocket 12 before you resume.** The camera's aim verdict counts only for
the run that took it, because the camera could have been knocked while the run was stopped. The
resume survey checks the aim over an empty pocket. If no pocket is empty (normal mid-run, unless
you emptied pocket 12), the learned check accepts nothing and learns nothing until the run has
emptied its next source pocket and looked over it: until then every slab without a back-label
code stops for you ("… the head camera's aim is not checked this run yet …"). [Certain,
`runner.survey`, `runner._work`; tested in the simulator]

Every slab still appears exactly once. [Certain, in the simulator: `tests/test_resume.py`, 8
passed when I ran it on 2026-10-22]

### 8.1 The table

Messages are quoted from the code, shortened where marked "…". [Certain]

| Message (start of it) | What happened | What you do |
|---|---|---|
| **Before the start** | | |
| "… has no pad_trigger_c / offset_x yet. Run `calibrate z` and `calibrate x` first" | Not calibrated | BUILD_GUIDE §12.1–12.2 |
| "Close the lid to start." | Lid switch open | Close it |
| "The overfill light beam is blocked with the head at the top: a stack is above the MAX line, something is lying across the stacks, or the laser and its receiver are out of line …" | Something is taller than 214 mm, or the beam is out of line | Check every stack with the fill gauge and look for a slab lying on top. Then `selftest -i` for the beam. |
| "The cup line holds vacuum … (… kPa; an empty cup reads …): a slab may be stuck to the cup. Nothing will move, and the pump is switched on …" | A slab is left on the cup, or the sensor zero drifted | Hold the slab, vent (the prompt, or the web Vent button), put it face-down on top of the stack it came from, then start again. If the cup is empty: `selftest -i` stores a new zero. |
| "Another slabscan process is using the machine … (stop it with: sudo systemctl stop slabrail-web) …" | The web service or a second window has the machine | Stop the other one first |
| **During the survey** | | |
| "Pocket N (empty_start / exceptions) must start empty but is … mm tall." | Something is in pocket 0 or 12 | Empty it and restart |
| "Pocket N is filled above the MAX line …" | Overfilled | Take slabs off and restart |
| "Pocket N: probe never touched anything (not even the pad)." | The contact sensor didn't trip | Check the flag and the sensor (`selftest -i`). **Don't resume until the probe test passes.** |
| "Pocket N: the cup sealed on something but the contact sensor did not trip. Contact sensor fault …" | The second, vacuum-based contact check caught a dead sensor | Same as above |
| "Pocket N: the cup sealed (… kPa) before the head moved down - a slab is hanging on the cup. Nothing will move …" | A slab stuck to the cup from before | Hold it, vent (prompt / Vent button), put it face-down back on the stack it came from, start again |
| **While moving slabs** | | |
| "Pocket N: the top slab could not be confirmed FACE-DOWN before touching it (no back-label code was seen from above (a PSA QR, a CGC QR or the CGC 2020-23 back barcode)[; a CGC QR without a cert number …][; learned check: …]). … If it is face-down (older PSA labels, CGC Authentic, BGS and SGC slabs have no back-label code), resume with --face-down-ok …" | A face-up PSA slab (its front barcode proves nothing), or a slab with no back-label code that the learned check could not match (the reason after "learned check:" is in the rows below) | Look at the top slab of pocket N. Face-up: turn it face-down, then `resume`. Face-down: `resume --face-down-ok` (web: tick "the top slab of pocket N, where the face-down check stopped, is face-down"; the tick only shows after a face-down stop). It confirms that one slab only, and only right after this stop. For a batch of older labels you checked, start it with `--all-face-down`. |
| "Pocket N: the top slab is FACE-UP (a CGC front-label barcode (…) / a CGC Authentic front-label QR (grade 0_0) (…) is visible from above, and that code is printed on the FRONT label). … Turn the top slab of pocket N face-down, label end toward you, then resume. Only if it already is face-down, resume with --face-down-ok …" | A CGC slab lies face-up | Turn it face-down and resume. If it really is face-down, confirm it: it is picked, but never learned from. |
| "… a … back-label QR … and a … front-label … are both in view: another slab's label is in view", "… two different back labels are in view (A, B): another slab's label is in view" or "… codes of two different certs are in view …" | A neighbour's label is inside the head camera's crop | Look at the top slab of pocket N and its neighbours. If it is face-down, confirm it. If this happens often, check `cam_head.hfov_deg` (BUILD_GUIDE §12.3). |
| "… learned check not active yet: face_down_threshold is not measured (Phase 0 measures it)" | No Phase 0 GO saved | Phase 0 with `--face-up 15 --save` (BUILD_GUIDE §1.7), or set `face_down_check = "stop"`. |
| "… learned check not active: face_down_threshold was not measured for this card window (face_down_threshold_sig …)" | The card window changed since Phase 0, or the threshold was typed in by hand | Run Phase 0 again with `--save` |
| "… learned check not active yet: N of 5 card-back references" or "… checked on 5 slabs proven face-down on this machine …, N so far" | The first batches: not enough code-proven (or confirmed) slabs placed yet | Normal. Every back-code slab whose read is `ok` adds one once it is placed. |
| "… learned check not active: over an empty pocket the head camera sees edges where only the pad should show, in the card window or within 1 mm of its cup side (… mm2 …): a part of the head is in the window, or about to be. The head camera is tilted toward the cup, or something lies on the pad there (lint, dust, a tag): look at the picture first. Re-aim the head camera (BUILD_GUIDE 7.7), then compare images/face_down_empty.jpg (pocket N) with images/face_down_window.jpg. Dirt on that pocket's pad looks the same: clean it" | The camera-aim check failed on this run's view over an empty pocket: the camera is tilted toward the cup (with today's head a part enters the window at about 1.3°), or something lies on that pad. The learned check accepts nothing and learns nothing this run. [Certain, `facedown.aim_problem`] | Confirm the slab as above. Open `images/face_down_empty.jpg`: clean the pad if it shows lint or a tag; otherwise shim the camera board (BUILD_GUIDE §7.7) and run `focus head`. The next run checks again. |
| "… learned check not active: the head camera's aim is not checked this run yet: its last check is from before (a resume whose survey found no empty pocket), and a knock since then would not be seen. It is checked over the first source pocket this run empties; until then every slab without a back-label code stops for you" | A resume found no empty pocket at its survey, so it could not check the camera's aim yet. The learned check accepts nothing and learns nothing until the run has emptied its next source pocket and looked over it (journal `face_down_baseline`). [Certain, `runner.AIM_STALE`] | Confirm the slab as above. To avoid more of these stops, empty pocket 12 before that resume (§5.5): its survey then checks the aim at once. |
| "… N% of the card window shows the same thing on every proven slab as over an empty pocket (allowed 10%): a part of the head is in the way" or "… the card window looks like the view over an empty pocket (…): the head hides it" | A head part is in the camera's view of the card window: a camera tilted toward the cup (with today's head a part enters at about 1.3°), or a tube or cable hanging in the view [Certain, CAD aim check] | Confirm the slab as above. Compare `images/face_down_window.jpg` with `face_down_empty.jpg`; shim the camera board (BUILD_GUIDE §7.7, §12.3). |
| "… only N known card back(s) of one design match it (0.xx); a match needs 2 slabs of that design at the threshold 0.yy (one odd reference, or a card front that looks like one, is not enough)" | One reference matched, a second did not: one odd back (a card sitting low in its holder), or a front that looks like one | Look at it. Face-down: confirm it. |
| "… best match with a known card back 0.xx < threshold 0.yy" | A face-up slab, a card back the machine has not learned (Japanese, another game), or a sleeve or sticker over the window | Look at it. Face-down: confirm it. |
| "… it matches a card back (0.xx) known only from N of your confirmations; it is used once 3 confirm it" | A back design taught only by your confirmations | Confirm it if it is face-down; after 3 agreeing confirmations that back is used |
| "… the card window shows far less pattern (texture …) than that card back …: a plain card front, or glare" | Very likely a face-up plain card, or a glare spot | Look at it carefully before confirming |
| "… nothing visible in the card window (blank, dark or washed out)", "… glare covers N% of the card window" or "… the card window is not inside the frame" | Head ring off or glare on the window; or `cam_head` / `face_down_window_mm` wrong | Check the head ring and `face_down_window.jpg` (BUILD_GUIDE §12.3) |
| "Z stall suspected \<where>: the carry-height sensor (GPIO 6) reads CLEAR, but the controller has the head at … mm, where the flag on the Z carriage must block its beam (from 246.5 mm up). Nothing moved sideways. …" plus "The slab that was in the cup was lowered straight down onto pocket N, where it came from …" or "The slab from pocket N is still on the cup … it was not carried anywhere: nothing moves, and the pump keeps holding it …" | The Z motor lost steps while lifting (a bind, a heavy pull, too little current). Right after homing, the message blames the sensor lead instead: a cut or unplugged lead, a bent or missing flag, a mount that slid. [Certain, `runner._carry_check`] | If a slab is still on the cup: hold it, vent (prompt / Vent button), put it face-down on top of pocket N. Then, power off, move the head up and down by hand and feel for a bind; check the Z current (BUILD_GUIDE §7.8); `python -m tools.bench_tests lifts 20`; `selftest --motion`. Resume homes first. |
| "Carry-height sensor fault \<where>: it reads BLOCKED with the head at … mm, far below its trip height (246.5 mm). …" | Dirt or a card in the sensor's slot, a dead emitter LED or a bent flag: then a Z stall could not be seen | Clean the slot, check the flag (BUILD_GUIDE §7.4a), `selftest --motion` (clear below 245.5, blocked above 247.5), resume. |
| "Unexpected contact over pocket N at … mm while moving down to … mm [with a slab in the cup]: something is higher than it should be …" | A crooked, added or dropped slab, or a slab lying on the rods | Look before you touch anything. Fix it, then resume. |
| "Pocket N is … mm taller than expected - was a slab added or is one sitting crooked?" | A slab is on a rod, or someone added one | Seat it flat (or take the added slab off), then resume |
| "Pocket N: no contact where the stack should be (predicted … mm). Check the contact sensor, then resume." | The stack is lower than expected: a slab was removed, or the sensor is weak | Count the stack against the CSV. `selftest -i`. Resume. |
| "Pocket N: cup will not seal on the top slab (dirty cup, warped slab?)." | No seal, even after a second try | Wipe the cup with IPA. Check the slab is face-down, flat and unsleeved. Resume. |
| "Vacuum lost after peel / in transit / at the read station (… kPa). A slab may have dropped." plus one of: "… It was carried back slowly and set down on top of pocket N …", "… the slab was NOT on the cup any more: it fell somewhere between pocket N and where the head was …", or "… nothing was found on top of pocket N. The head waits at the safe height with the pump on." | Vacuum dropped while holding. The machine never lets go in mid-air: it carries the slab back slowly over its own pocket and probes it down. [Certain, `runner._set_down_weak`] | Do what the second part says. Find and check any dropped slab. Run `selftest -i` (leak) before resuming. |
| "Vent failed …: the cup line still reads … kPa …" or "A slab came up with the vented cup …" | The vent path (GPIO 22 module, coil or wire) did not let go. The slab rests on the stack, still sealed to the cup; nothing moves. | Hold the slab and pull the vacuum tube off the cup fitting (or unscrew the cup). Never slide the slab sideways. Fix the vent, `selftest -i`, resume. |
| "Vacuum sensor fault: … Without it the machine cannot tell whether a slab is held or let go, so nothing moves." | The sensor reads outside its range (an open wire, a lost 5 V) | If a slab is on the cup, hold it and vent. Fix the sensor wiring (WIRING.md §5), `selftest -i`, resume. |
| "Exception pocket 12 is full. Empty it …, then resume." | About 28 exceptions | Unload pocket 12 (§6) and resume. It recounts from what's left. |
| "Placing onto pocket N: no contact - output stack lower than expected." | The output stack is lower than recorded | Check that stack for a fallen or removed slab, then resume |
| "Placing onto pocket N: contact … above the stack - something is in the way." | An object, or a crooked slab, on the output stack | Clear it, then resume |
| "Placing onto pocket N: the cup touched … mm above the stack, as if nothing is in the cup. The slab from pocket N may have fallen off on the way …" | The slab fell off, or the vacuum sensor reports a seal that isn't there | Look at the cup and the bed (rods, stacks, read station). Find the slab, then resume. |
| "Lid opened - run paused with nothing held." | Lid opened | Close it and resume |
| "Stopped on request - nothing held. Resume to continue." | You pressed Stop | Resume when ready |
| **Controller and power** | | |
| "The controller lost power or its USB link (E-stop pressed, or the cable came out). The head stopped where it was. If you did not press the E-stop, the motors may still be powered: press it now before reaching in. [A slab from pocket N is still on the cup …]" | E-stop, or the USB came out. The Pi keeps the pump and valve switched on; after an E-stop they have no power, so the slab hangs on the closed cup line only for a short while. [Certain, `runner.lost_note`] | Press the E-stop if you didn't. **Take the slab now** (after an E-stop the vent has no power either: hold it and pull it off gently), or vent at the prompt / Vent button if the pump still runs. Put it face-down on top of pocket N. Release the E-stop, then resume. It reconnects and homes first: Z straight up, then X. |
| "The controller is still not answering … check the USB cable and the 24 V supply" | The CH340 didn't come back within 15 s | Wait 10 s and resume again. Check the E-stop is released, the 24 V supply, and the USB cable. |
| **Anything else** | | |
| "Hard stop (Ctrl-C twice): the motors were halted where they were and nothing moved after that. … [A slab from pocket N is on the cup; the pump keeps holding it …]" | You stopped it hard | Hold the slab, type `vent` at the prompt (web: Vent), put it face-down on top of pocket N. Resume homes first. |
| "Interrupted (Ctrl-C) during the stop itself. The head may have stopped anywhere and a slab may be in the cup …" | Ctrl-C while the machine was putting a slab back | Check the head. If a slab is on it, the prompt asks you to vent. Then resume. |
| "Unexpected error: \<ErrorType>: …. The slab that was in the cup was put back on top of pocket N; it will be read again on resume." | An unplanned error, e.g. a camera dropping off USB or a decoder bug. The slab was parked. | Fix the cause (§8.3), then resume. |
| "… Could not park the machine automatically (…). A SLAB from pocket N is still on the cup; the pump keeps holding it …" | The put-back failed, or the controller is in ALARM (for example "Probe Hard Limit") | Hold the slab, vent (prompt / Vent button), put it face-down on top of pocket N. Check the head, fix the cause, resume. A probe hard-limit alarm during a lift means the flag chatters or something touched the cup: BUILD_GUIDE §13.2. |
| "\<ErrorType>: … The machine stopped without parking …" | Rare now: an error before the run's own guard started (for example while opening the hardware) | Check the head anyway, then resume. |
| **On resume** | | |
| "The stacks changed since the run stopped: pocket N: … mm now, … mm when the run stopped (±n slabs) …" | A slab was added, removed or moved while stopped | Put things back as they were. If it says "It looks like one slab went from pocket A to pocket B …", move that top slab back as told. Or use `resume --accept-heights` if you changed things on purpose: the count check will flag it. |
| "exception pocket 12 was emptied to … mm; counting continues from …" | Info: you emptied pocket 12 | Nothing |
| "resume: the run stopped before the first survey finished - starting it from the beginning" | Info | Nothing |
| "--face-down-ok refused: the batch did not stop at the face-down check last time, so there is no slab for it to confirm. Nothing moved. …" | The last stop was not a face-down stop | Resume without it. If a slab the check can't confirm comes next, the run stops there and you confirm that one. |
| "--face-down-ok was for the top slab of pocket N, but the next slab is in pocket M: not used" (log line) | Info: the confirmation is only for the slab it stopped on | Nothing; if pocket M's slab can't be confirmed either, the run stops there |

### 8.2 Venting the cup by hand

If the software is running and asks you to type `vent` (or the web page shows **Vent**), use
that. Only if a slab is stuck on the cup and the software isn't running, hold the slab with one
hand and open the vent valve for a second:

```bash
pinctrl set 22 op dh; sleep 1; pinctrl set 22 op dl
```

GPIO 22 is the vent valve. [Certain, CONTRACT] `pinctrl` is the Raspberry Pi OS GPIO tool
WIRING.md §15 uses. [Likely] Don't do this while `slabscan` is still running, because both would
drive the same pin. With the E-stop pressed the vent valve has no power: release the E-stop first,
or hold the slab and pull the vacuum tube off the cup fitting.

### 8.3 Repeated stops of one kind

| Pattern | Look at |
|---|---|
| "cup will not seal" on many slabs | A cup lip worn or dirty; a leak (`selftest -i` → `leak`) |
| "Vacuum lost in transit" more than once | A leak in the cup line; the pump; whether the slab is knocking a rod (watch a carry) |
| "taller than expected" on random pockets | Slabs placed crooked: X calibration (`calibrate x`), belt tension, a leaning rod |
| Camera errors | The head camera's USB extension in the drag chain (WIRING.md §16 risk 4) |
| Many `no_read` | Focus (`focus head`, `focus station --save`), a ring not lighting, glare. Fit the light roof. |
| Many pre-2016 PSA labels `needs_review`: "one printed barcode only (no QR) - confirm" or "barcode N but OCR read M" | Their front ITF is their only code, and it is `ok` only when OCR of the printed number agrees. OCR read nothing or other digits: the `tesseract` line of `selftest`, `focus station --save`, the station ring. [Certain, `certs.consensus`] |
| Every pre-2016 PSA label `needs_review` "… grader PSA not confirmed …", or "N-digit PSA cert, but Phase 0 saw only …" | `custom_regex` is set (it turns off the 8-digit ITF rule), or `psa_cert_digits` leaves out 7 (§5.2) |
| After a resume, every slab without a back-label code stops ("… aim is not checked this run yet …") | No pocket was empty at the resume survey. Empty pocket 12 before resuming (§8). |
| A BGS, SGC or other non-PSA slab reads `ok PSA` | The 8-digit ITF rule is wrong for that grader (§5.2). Treat its `ok PSA` rows as `needs_review` and tell the software owner. |
| `CAMERA AIM:` on every run | The head camera is tilted toward the cup, or a pocket pad has lint or a tag on it: BUILD_GUIDE §7.7, §12.3 |
| A face-down-check stop at every older PSA label (and CGC Authentic, BGS) | Expected until the learned check is active (the start line says why). Check the stacks yourself and start such batches with `--all-face-down`. |
| "Z stall suspected" more than once | The Z axis: a bind (lead screw, nut, rail), the motor current, the motor itself (BUILD_GUIDE §7.8 lift test). Not the sensor, if `selftest --motion` passes. |
| Learned acceptances with scores just above the threshold | Open their back photos (§8.4). If one shows a card front, set `face_down_check = "stop"` and check that slab: the cup touched its front. |
| Every slab goes to the front camera (slow runs, many "confirmed by OCR") | The head crop is wrong: `cam_head.hfov_deg` / `row_axis` don't match the real camera, so the label is cut off (BUILD_GUIDE §12.3) |
| "Probe Hard Limit" alarms | The probe flag chatters at the slot edge during the slow lift, or something touched the cup: BUILD_GUIDE §13.2, WIRING.md §6 |

### 8.4 The learned face-down check

[Certain for how it works, from `slabscan/facedown.py` and `runner.py`; Guessing for how well it
works on real slabs: it has only run in the simulator]

**What it does.** Most slabs without a back-label code show the same card back through the plastic
(every English Pokémon card has the same back). The machine compares the card window
(`face_down_window_mm`, a 55 × 5.5 mm strip on the card next to the label) with the card backs of
slabs it has seen proven face-down. A match lets the cup pick the slab without stopping. A face-up
slab shows its card front there instead.

**The three modes** (`face_down_check` in `config/calibration.toml`):
- `"learned"` (the default): a back-label code, or a card-window match. Until the check is active it
  acts exactly like `"stop"`.
- `"stop"`: only a back-label code proves it. PSA 2016 and older labels, CGC Authentic, BGS and SGC
  slabs stop every time.
- `"off"`, or `run --all-face-down` for one batch: no check. A face-up slab gets the cup on its
  front.

**When it is active.** All of these must hold; the start line says which one is missing.
[Certain, `facedown.learned_ready`]
1. Phase 0 measured a threshold on your slabs and said GO, and `--save` wrote it with its
   `face_down_threshold_sig` (BUILD_GUIDE §1.7). No threshold below 0.55 is used.
2. At least 5 card-back references exist.
3. The view over an empty pocket was taken this run: during the survey, or, on a resume whose
   survey found no empty pocket, over the first source pocket it empties.
4. On the newest 5 or more slabs proven on this machine, at most 10% of the card window looked
   the same as over the empty pocket. More means a part of the head is in the view.
5. The camera-aim check found no edge in the middle of the card window, or within 1 mm of its cup
   side, on this run's view over an empty pocket (the verdict is stored with that view in
   `card_backs.npz`). [Certain, `facedown.aim_problem`]
- **Today's head leaves the window clear** [Certain, CAD frustum check: nothing in view at hover
  over stacks of 1, 15 and 30 or with a slab held]. In the 330-slab simulation the check became
  active after the first slabs and stopped for 2 of 330 (43 without it) [Certain, sim].
- [Certain, CAD aim check] Camera aim: a tilt of more than about 1.3° toward the cup puts the cup
  pad into the window (1.34° in the CAD check, 1.31° with the software's own mapping). Condition 5
  catches that tilt from about 1.3° in the simulator [Certain, sim]. It does **not** see:
  - a head part as dark as the pad (no edge against it; condition 4 missed such a part over 9–26%
    of the window in the simulator);
  - a tilt away from the cup, or a roll along the row: they move the window toward the card top or
    off its side. On a CGC slab pushed into a pocket corner about 0.01° toward the label already
    puts over 2% of the window on the holder [Likely, CAD card-plane check].
  Its thresholds were set on the simulator's flat pad, so lint or dust on a real pad can make it
  fire on a square camera: that is safe (the check stays off). A head edge about 1 mm inside the
  window raised face-up scores in the simulator from 0.37 to 0.52 (hence the 0.55 floor). Check
  `face_down_window.jpg` on your first run (BUILD_GUIDE §12.3).

**A match needs two references.** A slab is accepted only when two references from two different
slabs of the same back design reach the threshold, not just the best one. [Certain, real slabs: one
odd back, a card sitting low in its holder, matched a real blue Water-type front at up to 0.62
under glare; with the second reference no face-up front came above 0.44, at the cost of about 6%
more face-down slabs stopping]

**Where the references come from.**
- Slabs proven by a back-label code seen from above, but only after the slab is placed, only if
  its read is `ok` with the same cert as that code (a neighbour's QR in view gives another cert),
  and never if the read station saw a back-label code from below. Each refusal is logged: "not used
  as a reference: the read station saw <a PSA back-label QR | a CGC back-label QR | a CGC 2020-23
  back-label barcode> from below, so this slab was FACE-UP", "… its read is '…', not 'ok' …" or
  "… the back-label code seen from above (cert …) is not this slab's cert …".
- Slabs you confirmed with `--face-down-ok`, after the same placement checks, and never if a
  front-label code was in view from above.
- A back design known only from your confirmations is used once 3 of them agree. One wrong
  confirmation alone teaches nothing.
- The Phase 0 backs, if Phase 0 said GO and you used `--save`.
- **Never from a learned acceptance**, so the check cannot teach itself a wrong appearance. Never
  from a window with glare on more than 2% of it, with too little pattern, or that looks like the
  empty-pocket view.
- A new back design starts with one slab, so it matches nothing until a second slab joins it: one
  odd reference can only ever be one of the two votes.
- Up to 6 back designs (prototypes) with the newest 8 references each are kept.

**Where they live:** `config/card_backs.npz`, next to `calibration.toml`. Not in git.
```bash
python -m slabscan refs                    # list: prototype, source, batch and position, cert, back photo
python -m slabscan refs --drop 12345678    # delete the references taken from the slab with this cert
python -m slabscan refs --drop-operator    # delete every reference you confirmed (keeps the back-QR ones)
```
Deleting the file starts over, including the empty-pocket view. A file written for another card
window is not used. [Certain, `facedown.CardBackRefs`]

**Auditing learned acceptances.** Do it for every learned row in the first batches.
- `certs.csv`: `face_down` = `learned(0.93)`; `report.html` shows those rows in bold in the
  Face-down column. Open each back photo: it must show a card **back**.
- The summary line names the lowest learned score.
- `journal.jsonl`, one line per event:
  - `face_down_learned`: score, its pattern (`ncc`) and colour (`hist`) parts, prototype,
    threshold, references, texture, and similarity to the empty-pocket view;
  - `face_down_reference`: each reference taken from a slab you confirmed (position, cert, back
    photo, result);
  - `face_down_confirmed`: your confirmation and what became of it;
  - the stop line carries `face_down_stop` (the pocket) and why;
  - `face_down_baseline`: the empty-pocket view, with its camera-aim verdict (`aim`). After a
    resume with no empty pocket it comes mid-run, when the first source pocket is emptied;
    `face_down_ok_unused`: a confirmation that did not apply.
- **After a wrong `--face-down-ok`** (you confirmed a slab that was face-up): the cup touched its
  front, so check that slab. Then delete what it taught: `refs --drop <its cert>` (the cert is in
  its `face_down_reference` line).

**Limits.** [Certain, round-3 window] On studio scans of 63 real slabs, placed where the
machine's camera would see them, clean frames gave 0 face-up fronts accepted and all 14 no-code
backs accepted (with one reference); glare raised the scores of some fronts, which is why a match
now needs two. With two, 223 of 252 face-down frames (glare included) and 0 of 332 face-up frames
were accepted at 0.55. [Likely, CAD emulation of the same scans] Today's smaller window accepts
about 101–103 of 126 face-down backs and 0 of 206 face-up slabs (highest face-up 0.49–0.53, under
the 0.55 floor). The larger round-3 window let 12 of 206 face-up CGC fronts through with every slab
at the cup end of its play: the strip of holder above a CGC card looks the same from both sides.
[Guessing] The real camera, through slab plastic, under your lights, has not been measured; nor
have sleeves and stickers, and 15 face-up slabs in Phase 0 say little about the worst face-up slab.
Japanese backs need their own references (two back-code slabs with that back, or 3 of your
confirmations).

## 9. Quick card

Print this and tape it to the machine.

```
BEFORE   cup wiped (IPA) - pockets 0 and 12 empty - nothing above the gauge's top bar - sleeves off
LOAD     face-DOWN (hard rule), label toward you, pockets 1-11, bundles of 5-10 lowered by hand
         PSA+CGC mixed OK.  BGS/TAG only if <= 82.6 mm wide (go to 12).  NO SGC.
START    python -m slabscan run --name NAME   (web: Start run)
         start line "face-down check: ..." = what the check does (learned, or back-label codes only)
         slabs without a back-label code (PSA 2016 and older, CGC Authentic, BGS) stop the run until
         the learned check is active: check, then resume --face-down-ok (only right after that stop;
         that one slab), or start a checked batch with --all-face-down
         "FACE-UP" stop = a CGC front code seen from above: turn that slab face-down, resume
         "Z stall suspected" = head low: take a held slab as told, check Z, selftest --motion
         "CAMERA AIM" / "sees edges where only the pad should show" = re-aim the head camera or clean that pad
STOP     web "Stop after this slab" / Ctrl-C once = clean stop.
         Ctrl-C twice = motors halt NOW, nothing moves; a held slab stays on the pump -> hold it, type vent.
         E-STOP = the only stop that cuts motor power. Use it for anything dangerous.
RESUME   python -m slabscan resume batches/<id>    (or web: Resume)
         learned mode: empty pocket 12 first, so the camera aim is checked at once
AFTER    stack k is now in pocket k-1, order reversed: top slab = highest out_index.
         Unload from the TOP, max 5 at a time, face-down into a tray. Never lift or flip a stack.
         Pocket 12 = check by hand (incl. OCR-only rows).  needs_review = check by hand
         (a pre-2016 PSA slab is ok only when OCR confirms its front ITF).
         DOUBLE PICK = an extra UNREAD row: that slab is in the OUTPUT pocket, under the read one.
         face_down = learned(0.xx) -> open its back photo.  refs / refs --drop CERT = references.
WEEKLY   pads wiped, selftest -i.   MONTHLY  belt, rails, bolts, E-stop check, carry sensor (selftest --motion)
NEW CUP PAD -> calibrate z
```
