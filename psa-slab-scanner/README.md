# SlabRail: unattended PSA / CGC slab cert scanner

Load up to **330 graded slabs** (11 stacks of 30) and walk away. About 80 minutes later you have
`certs.csv` with every cert number, where each slab ended up, and a photo of each label.
The machine has **two motors**: one moves the head left and right along a single beam, the
other moves it up and down.

**Engineers reviewing the design:** start with [docs/REVIEWER_BRIEF.md](docs/REVIEWER_BRIEF.md); the drawing set (PDF) and the CAD bundle are in `package/`.

![How a run works](docs/img/storyboard.png)

## Read this first

- **[Likely] Nothing like this is for sale.** No product at any price takes 200–300 slabs and
  returns cert numbers unattended. Raw-card sorters exclude slabs, and sheet-fed scanners
  can't take them. Details are in [docs/RESEARCH.md](docs/RESEARCH.md).
- **[Likely] A $350–650 hands-free 2D scanner gets you 80% of the way with no build.** It reads
  20–30 slabs per minute by hand, about 10 minutes per 250. This machine buys back those
  10–15 minutes per batch and adds a photo of every slab, which helps catch fake labels and
  swapped cards. Loading and unloading still take you about 10 minutes either way.
- **[Certain] It has not touched a real slab yet.** The geometry, the motion plan and the decoding
  were verified in CAD and in a simulator, and the label rules on public scans of 64 real slabs
  (below). Real cameras through the slab plastic and real cup behaviour still need to be tested.
  That is why the build starts with **two Phase 0 gates** before you buy any motion parts:
  - **0A, camera test:** can the cameras read *your* labels? About $281 with a borrowed school
    Raspberry Pi, about $470 if you buy one. One or two evenings plus printing.
  - **0B, cup test:** does the cup seal on your holders, and does it leave a mark after 24 h? This
    is the only part that touches your inventory. About $155 with a spare SMC cup (the one shop
    that lists the exact code shows it back-ordered), a hand vacuum pump on the bench, no mains
    wiring.
- **[Likely] The budget fits, with headroom.** The full list is about $2,182, and a realistic worst
  case is about $2,380, inside the $2,500–3,000 you said is fine. With the school's shop stock it
  drops to about $1,862 (worst case about $2,050). Upgrades (a genuine HIWIN rail, a stronger Z
  motor, a high-flex USB cable and others) are listed at qty 0: buy one only when the test it
  names fails. Details in [docs/BOM.md](docs/BOM.md); every order with a link per line in
  [docs/SHOPPING_LIST.md](docs/SHOPPING_LIST.md).
- **[Certain, code and CAD] Slabs without a back-label code stop the run until the learned check
  takes over.** Before the cup touches a slab, the head camera must prove it is face-down: a code
  printed only on the back label (a PSA back QR, a CGC back QR or the CGC 2020–23 back barcode),
  or a card window that matches two card backs of slabs proven earlier. **The head camera now sees
  that window** (its lens sits 5 mm toward the label) [Certain, CAD frustum check], so after a
  Phase 0 GO and the first 5 code-proven slabs the learned check works: in the simulator's default
  mix 2 of 330 slabs stopped, against 43 with back-label codes only [Certain, sim; Guessing for real
  card backs through the plastic, which the machine's camera has not seen yet]. Until then PSA 2016
  and older labels, CGC Authentic, BGS and SGC stop until you confirm each one, unless you start
  the run with `--all-face-down` (then a slab loaded face-up gets the cup on its front). CGC 2023+
  and 2020–23 slabs no longer stop: their back QR proves them. A CGC slab loaded face-up stops with
  a "FACE-UP" message.
- **[Certain, CAD and simulator] A Z stall stops the run before the head moves sideways.** A second
  optical sensor on the Z spine checks that the head really is at carry height before every
  sideways move. It catches a lift that ended more than about 2.5 mm low; it does not make a weak
  Z motor strong, so the 100-lift test still has to pass.
- **[Certain, code] A pre-2016 PSA slab is `ok` only when OCR confirms its barcode.** Its only
  code is one front ITF. An 8-digit ITF whose printed number OCR reads the same names PSA; when OCR
  reads nothing or other digits, the slab is `needs_review` and stays in the output stack for you
  to check. Real set: 5 of 7 `ok` on the images as they are, 7 of 7 at machine scale; 20 of 21 in
  the simulator's default mix. **[Guessing] The rule assumes only PSA prints an 8-digit ITF.** If
  another grader does, its slab would come out `ok PSA` with the right digits and the wrong
  grader. Put any BGS or SGC slabs you own through Phase 0 first (docs/OPERATING.md §5.2).
- **Build effort:** a real mechatronics project, roughly 65–90 hours of hands-on work plus
  printing. Plan to use your school's instructors for the 120 V wiring, crimping and
  calibration.

## How it works

1. You stack slabs **face-down, label toward you**, in pockets 1–11. Pocket 0 (far left) and
   pocket 12 (far right) stay empty.
2. The suction cup lifts the **top** slab of stack 1 straight up. No slab ever slides on
   another.
3. A camera on the head reads the back of the label: the QR code on PSA labels from 2017 on and
   on CGC labels, and the barcode on PSA labels from 2016 on.
4. The cup sets the slab down in pocket 0, and the next slab is now on top. When stack 1 is
   empty, stack 2 moves into pocket 1, and so on down the row.
5. Slabs whose back can't be read, or that carry only barcodes (no QR), are held over an
   **upward camera** in the middle of the row, which reads the front label and checks the printed
   digits with OCR. Anything still unreadable, read only by OCR, or from a grader other than PSA or
   CGC, goes to **pocket 12** for you to check by hand.

The full explanation, with the numbers, is in [docs/DESIGN.md](docs/DESIGN.md).

![SlabRail](docs/img/machine_iso.png)

| | |
|---|---|
| Capacity | 330 per load (11 × 30 PSA). CGC reads too. BGS (its label has no code) and TAG go to pocket 12, but only load them if they measure ≤ 82.6 mm wide. SGC (≈ 86 mm) does not fit. |
| Footprint | about 1.42 m × 0.32 m × 0.65 m tall (fits a 6 ft bench) |
| Moving parts | X belt axis, Z lead-screw axis, a spring-loaded cup, 2 valves, 1 pump |
| Cycle | about 14 s per slab in the timing simulation: 79 min for a 330-slab load with the default label mix, including homing and the stack survey. Older front-only labels can take up to 30 s more each (OCR on the Pi), and each slab without a back-label code stops the run until the learned check is active, unless you use `--all-face-down`. Real speed will be measured in the acceptance tests. |
| Touches the slab | cup on the **back** only; edges against wooden dowels; slabs rest on each other as in any stack |
| Output | `certs.csv` (cert, grader, status, pocket and position), `certs.txt`, `report.html` with label photos |
| Budget | about **$2,182** expected for everything including a 15% allowance; about **$2,380** worst case (tools, the conditional HT1 cups and light roof, [Guessing] prices 20% high), inside the $2,500–3,000 ceiling. About **$1,862** (worst case about $2,050) if the school supplies filament, wire and common screws. Junk test slabs and the test-triggered upgrades are extra. Details in [docs/BOM.md](docs/BOM.md) and [docs/SHOPPING_LIST.md](docs/SHOPPING_LIST.md). |

## What's in this folder

| Path | What it is |
|---|---|
| `docs/BUILD_GUIDE.md` | Step-by-step build, from Phase 0 to the first supervised batch |
| `docs/OPERATING.md` | Weekly use: loading rules, running, reading results, maintenance |
| `docs/BOM.md`, `docs/BOM.csv` | Every part with price and link |
| `docs/SHOPPING_LIST.md` | The same parts as the three orders you place (Phase 0A, Phase 0B, machine), with links |
| `docs/WIRING.md`, `docs/img/wiring.svg` | Wiring tables and diagram |
| `docs/FIRMWARE.md`, `firmware/fluidnc/config.yaml` | Motion controller (FluidNC) setup |
| `docs/DESIGN.md` | Why this design, the damage analysis and the calculations |
| `docs/RESEARCH.md` | Existing products, PSA slab facts, the real PSA and CGC label formats, PSA API limits |
| `cad/` | Parametric CadQuery model. `layout.py` is the master dimensions file. |
| `cad/out/printed/` | **STL + STEP for every 3D-printed part**, plus `print_list.json` |
| `cad/out/assembly/slabrail_home.step` | Full assembly; opens in Fusion 360, Onshape or FreeCAD |
| `cad/out/cut_list.csv`, `cad/out/probe_flag_blank.svg` | Extrusion, dowel and flag-blank cut lengths; the 1:1 drawing of the probe flag |
| `software/` | Raspberry Pi software: run loop, decoding, simulator, CLI, web page, and `tools/real_eval.py` (the real-label check) |

## Verification done so far (no hardware)

- **[Certain] All 177 CAD checks pass** (`cad/checks.py`, re-run on 23 Oct 2026, about 12–15 min;
  every number is in `cad/out/checks.txt`, so trust that file over this list).
  - Picking the last slab of every pocket with full neighbours clears them by ≥ 14.5 mm.
  - Carried slabs clear the dowels by ≥ 21 mm; a double pick of two thick holders by ≥ 5 mm.
  - A held slab clears every part fixed to the X carriage by ≥ 5 mm, even at the Z top hard stop.
  - The cameras have an unobstructed view of the label, and the head camera of the face-down card
    window: no part in view at hover over stacks of 1, 15 and 30, or with a slab held.
  - Both LED rings are modelled and seated; the head seat takes rings of 39.5–42.5 mm (every head
    ring check runs at both ends), and the barb elbow clears the head ring by 3.75 mm at the full
    stroke.
  - The X home and Z top switches sit on printed mounts: each clicks where the firmware expects
    (cup X 19, c = 258), and its striker holds the lever 0.6 mm past the click to the hard stop,
    inside the switch's 1.2 mm overtravel. A lever up to 23 mm from the hinge end fits.
  - The card window is checked on the card plane for PSA and CGC slabs pushed into a pocket corner:
    PSA keeps it all on the card, CGC has about 1.5% of it on the holder (limit 2%) [Likely].
  - The probe flag trips at 2.0 mm of buffer travel and clears its sensor and guide over the full
    20 mm stroke; the buffer is modelled from SMC's catalog.
  - The carry-height sensor trips at c = 246.5 mm: clear at every height up to 242, blocked from
    248 to the top stop, its flag 1.05 mm from the sensor.
  - The Phase 0 jig holds the head's foot, buffer and flag exactly where the machine does,
    relative to the lens.
  - Both carriages stay on their rails at every printed hard stop, and no two parts overlap at
    any checked pose.
  - **Not checked:** belt slack, cables and the vacuum tube, the real shapes of bought parts
    (which lever the BOM's switches have, among them), loads or deflection, the sideways push the
    switch strikers put on the lever, and the frame's corner brackets and plates. A camera tilt
    over about 1.3° toward the cup puts the cup pad in the card window (1.34° in the CAD check). The
    software checks a tilt toward the cup on every learned run; it does not see a tilt away from
    the cup, a roll along the row, or a head part as dark as the pad.
- **[Certain] Software tests: `299 passed, 1 skipped in 1135.84s (0:18:55)`** (full suite,
  23 Oct 2026; the skipped test runs the rules on the real image set when it is pointed at it:
  on its own it gave `1 passed, 61 deselected in 137.29s (0:02:17)`). The simulator **raises a crash on any unsafe move**. Every
  slab is moved exactly once and read. The tests also cover:
  - the real payload strings of PSA and CGC labels (QR forms, ITF, Code128, the 13-digit CGC cert,
    the phantom read, which can no longer confirm itself or drop the real number),
  - the grader rule (a one-barcode slab is `ok` only when it is an 8-digit ITF that OCR confirms;
    a code in no grader's format never confirms one) and the OCR check of two-barcode reads,
  - the camera-aim check over an empty pocket (a tilt toward the cup turns the learned check off),
    also on a resume, with and without an empty pocket,
  - pre-2016 labels routed to the front camera,
  - double-pick detection, thick holders, overfill and seal failures stopping safely,
  - CGC slabs read, BGS to the exception pocket,
  - unexpected errors with a slab in the cup (the slab is put back or held, never dropped),
  - a Z stall caught before the sideways move, and a stuck or cut carry sensor,
  - the face-down check: a FACE-UP stop on a CGC front, a neighbour's label cropped out, a
    face-up slab still stops in learned mode, one wrong confirmation or one false code proof does
    not teach it a card front.
- **[Certain for these images] Real-label check** (`python -m tools.real_eval`, public scans of 64
  real slabs, RESEARCH.md §4): **0 wrong certs in an `ok` verdict and 0 false face-down proofs**,
  both on the images as they are (60 of 64 `ok`; 2 pre-2016 PSA `needs_review` because OCR read
  other digits on one and nothing on the other, the BGS and SGC unread: their labels have no code)
  and rescaled and degraded to what the machine's cameras would see (60 of 61 `ok`, the BGS
  unread). The old rules gave one silent wrong cert on
  the same images. **Limits:** the rules were written from these same 64 slabs, and flat
  studio scans have no slab-plastic reflections; Phase 0 on your own slabs is the real test.
- **[Certain, synthetic labels in the real formats] Decode sweep.**
  - The back QR reads through blur and strong glare.
  - The front barcode needs 0.05 mm per pixel; the station camera gives 0.039.
  - Not a single wrong cert was produced in any test.

## Build order

1. **Phase 0, two gates. Order the machine only if both pass.** (BOM order 1 ≈ $626 in all.)
   - **1a. Camera test, ≈ $281 with a borrowed Pi (≈ $470 buying one), one or two evenings plus
     printing.** Build the camera test jig (`docs/img/phase0_jig.png`) and run
     `python -m tools.phase0` on 30–50 of your own slabs. Go on only if at least 95% read, 0 come
     out wrong, and `python -m tools.real_eval --phase0 phase0_results` shows 0 wrong certs and 0
     false face-down proofs.
   - **1b. Cup test, ≈ $155 with the spare cup, 3–4 h of hands-on work plus the 24 h test.** Seal,
     leak and a 24 h marking test with a hand vacuum pump on the bench (BUILD_GUIDE §1.10). Go on
     only if the slab shows no mark after a dry wipe. If it does, stop and ask: the HT1 fallback
     cup needs an adapter nobody has sourced yet.
2. Order the rest of the BOM (order 2, ≈ $1,556; [docs/SHOPPING_LIST.md](docs/SHOPPING_LIST.md)).
   Print the parts in `cad/out/printed/`.
3. Follow `docs/BUILD_GUIDE.md`.
4. Calibrate. Run the acceptance tests on junk slabs, then do a supervised first batch.
