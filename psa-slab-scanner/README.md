# SlabRail: unattended PSA / CGC slab cert scanner

Load up to **330 graded slabs** (11 stacks of 30) and walk away. About 80 minutes later you have
`certs.csv` with every cert number, where each slab ended up, and a photo of each label.
The machine has **two motors**: one moves the head left and right along a single beam, the
other moves it up and down.

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
  were verified in CAD and in a simulator (below). Real PSA label payloads and real cup
  behaviour still need to be tested. That is why the build starts with **two Phase 0 gates**
  before you buy any motion parts:
  - **0A, camera test:** can the cameras read *your* labels? About $293 with a borrowed school
    Raspberry Pi, about $457 if you buy one. One or two evenings plus printing.
  - **0B, cup test:** does the cup seal on your holders, and does it leave a mark after 24 h? This
    is the only part that touches your inventory. About $198 with a spare SMC cup (its lead time
    can be weeks), a hand vacuum pump on the bench, no mains wiring.
- **[Likely] The budget fits, with headroom.** The full list is about $1,973, and a realistic worst
  case is about $2,235, inside the $2,500–3,000 you said is fine. With the school's shop stock it
  drops to about $1,703 (worst case about $1,965). Upgrades (a genuine HIWIN rail, a stronger Z
  motor, a flex-rated USB cable and others) are listed at qty 0: buy one only when the test it
  names fails. Details below and in [docs/BOM.md](docs/BOM.md).
- **[Certain, code and CAD] Older labels still stop the run.** Before the cup touches a slab, the
  head camera must prove it is face-down: a PSA back-label QR, or (new, the default) a card window
  that matches the card backs of slabs proven earlier. **That learned check cannot work on today's
  head:** the head foot hides the card window from the camera [Certain, CAD ray cast], and the
  software detects that and refuses to learn. So pre-2017 PSA labels and CGC slabs still stop the
  run until you confirm each one, unless you start the run with `--all-face-down` (then a slab
  loaded face-up gets the cup on its front). In the simulator's default mix, 49 of 330 slabs stop.
  A load of mostly old labels is not an unattended run without that flag.
  - With a head that leaves the window clear, the simulator stops at 1 of 330 [Certain, sim;
    Guessing for real card backs, which nobody has measured yet]. That needs a CAD change to the
    head first, then a Phase 0 face-up pass on your slabs.
- **Build effort:** a real mechatronics project, roughly 60–85 hours of hands-on work plus
  printing. Plan to use your school's instructors for the 120 V wiring, crimping and
  calibration.

## How it works

1. You stack slabs **face-down, label toward you**, in pockets 1–11. Pocket 0 (far left) and
   pocket 12 (far right) stay empty.
2. The suction cup lifts the **top** slab of stack 1 straight up. No slab ever slides on
   another.
3. A camera on the head reads the back of the label: the QR code on labels from 2017 on, and
   the barcode on labels from 2016 on.
4. The cup sets the slab down in pocket 0, and the next slab is now on top. When stack 1 is
   empty, stack 2 moves into pocket 1, and so on down the row.
5. Slabs whose back can't be read are held over an **upward camera** in the middle of the row,
   which reads the front label. Anything still unreadable, or from a grader other than PSA or
   CGC, goes to **pocket 12** for you to check by hand.

The full explanation, with the numbers, is in [docs/DESIGN.md](docs/DESIGN.md).

![SlabRail](docs/img/machine_iso.png)

| | |
|---|---|
| Capacity | 330 per load (11 × 30 PSA). CGC reads too. BGS and TAG are detected and set aside, but only load them if they measure ≤ 82.6 mm wide. SGC (≈ 86 mm) does not fit. |
| Footprint | about 1.42 m × 0.32 m × 0.65 m tall (fits a 6 ft bench) |
| Moving parts | X belt axis, Z lead-screw axis, a spring-loaded cup, 2 valves, 1 pump |
| Cycle | about 14 s per slab in the timing simulation: 78 min for a 330-slab load with the default label mix, including homing and the stack survey. Older front-only labels can take up to 30 s more each (OCR on the Pi), and each slab without a back QR stops the run unless you use `--all-face-down`. Real speed will be measured in the acceptance tests. |
| Touches the slab | cup on the **back** only; edges against wooden dowels; slabs rest on each other as in any stack |
| Output | `certs.csv` (cert, grader, status, pocket and position), `certs.txt`, `report.html` with label photos |
| Budget | about **$1,973** expected for everything including a 15% allowance; about **$2,235** worst case (tools, the conditional HT1 cups and light roof, [Guessing] prices 20% high), inside the $2,500–3,000 ceiling. About **$1,703** (worst case about $1,965) if the school supplies filament, wire and common screws. Junk test slabs and the test-triggered upgrades are extra. Details in [docs/BOM.md](docs/BOM.md). |

## What's in this folder

| Path | What it is |
|---|---|
| `docs/BUILD_GUIDE.md` | Step-by-step build, from Phase 0 to the first supervised batch |
| `docs/OPERATING.md` | Weekly use: loading rules, running, reading results, maintenance |
| `docs/BOM.md`, `docs/BOM.csv` | Every part with price and link |
| `docs/WIRING.md`, `docs/img/wiring.svg` | Wiring tables and diagram |
| `docs/FIRMWARE.md`, `firmware/fluidnc/config.yaml` | Motion controller (FluidNC) setup |
| `docs/DESIGN.md` | Why this design, the damage analysis and the calculations |
| `docs/RESEARCH.md` | Existing products, PSA slab and label facts, PSA API limits |
| `cad/` | Parametric CadQuery model. `layout.py` is the master dimensions file. |
| `cad/out/printed/` | **STL + STEP for every 3D-printed part**, plus `print_list.json` |
| `cad/out/assembly/slabrail_home.step` | Full assembly; opens in Fusion 360, Onshape or FreeCAD |
| `cad/out/cut_list.csv`, `cad/out/probe_flag_blank.svg` | Extrusion, dowel and flag-blank cut lengths; the 1:1 drawing of the probe flag |
| `software/` | Raspberry Pi software: run loop, decoding, simulator, CLI, web page |

## Verification done so far (no hardware)

- **[Certain] All 106 CAD checks pass** (`cad/checks.py`, re-run on 22 Oct 2026; every number is
  in `cad/out/checks.txt`, so trust that file over this list).
  - Picking the last slab of every pocket with full neighbours clears the head by ≥ 18.9 mm.
  - Carried slabs clear the dowels by ≥ 21 mm; a double pick of two thick holders by ≥ 5 mm.
  - A held slab clears every part fixed to the X carriage by ≥ 5 mm, even at the Z top hard stop.
  - The cameras have an unobstructed view of the label.
  - The probe flag trips at 2.0 mm of buffer travel and clears its sensor and guide over the full
    20 mm stroke; the buffer is modelled from SMC's catalog.
  - The Phase 0 jig holds the head's foot, buffer and flag exactly where the machine does,
    relative to the lens.
  - Both carriages stay on their rails at every printed hard stop, and no two parts overlap at
    any checked pose.
  - **Not checked:** belt slack, cables and the vacuum tube, the real shapes of bought parts,
    loads or deflection, and the head camera's view of the card window (a ray cast shows it
    hidden).
- **[Certain] Simulated end-to-end batches; 189 software tests pass** (22 Oct 2026). The simulator
  **raises a crash on any unsafe move**. Every slab is moved exactly once and read. It also covers:
  - pre-2016 labels routed to the front camera,
  - learning how PSA encodes 9-digit certs into the barcode,
  - double-pick detection,
  - thick holders,
  - CGC slabs read and BGS rejected,
  - overfill and seal failures stopping safely,
  - unexpected errors with a slab in the cup (the slab is put back or held, never dropped),
  - the learned face-down check: a face-up slab still stops, today's head is refused, and one
    wrong confirmation does not teach it a card front.
- **[Certain, synthetic labels] Decode sweep.**
  - The back QR reads through blur and strong glare.
  - The front barcode needs 0.05 mm per pixel; the station camera gives 0.039.
  - Not a single wrong cert was produced in any test.

## Build order

1. **Phase 0, two gates. Order the machine only if both pass.** (BOM order 1 ≈ $655 in all.)
   - **1a. Camera test, ≈ $293 with a borrowed Pi (≈ $457 buying one), one or two evenings plus
     printing.** Build the camera test jig (`docs/img/phase0_jig.png`) and run
     `python -m tools.phase0` on 30–50 of your own slabs. Go on only if at least 95% read and 0
     come out wrong.
   - **1b. Cup test, ≈ $198 with the spare cup, 3–4 h of hands-on work plus the 24 h test.** Seal, leak and a 24 h
     marking test with a hand vacuum pump on the bench (BUILD_GUIDE §1.10). Go on only if the
     slab shows no mark after a dry wipe. If it does, try the HT1 cup first.
2. Order the rest of the BOM (order 2, ≈ $1,317). Print the parts in `cad/out/printed/`.
3. Follow `docs/BUILD_GUIDE.md`.
4. Calibrate. Run the acceptance tests on junk slabs, then do a supervised first batch.
