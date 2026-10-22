# SlabRail: unattended PSA / CGC slab cert scanner

Load up to **330 graded slabs** (11 stacks of 30) and walk away. About an hour later you have
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
  behaviour still need to be tested. That is why the build starts with a **Phase 0** camera
  test (about $150 if you borrow a school Raspberry Pi, about $300 if you buy one) before you buy any motion parts.
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
| Capacity | 330 per load (11 × 30 PSA). CGC reads too. BGS/SGC/TAG are detected and set aside. |
| Footprint | about 1.42 m × 0.32 m × 0.65 m tall (fits a 6 ft bench) |
| Moving parts | X belt axis, Z lead-screw axis, a spring-loaded cup, 2 valves, 1 pump |
| Cycle | about 11–12 s per slab in the timing simulation, so about 1 hour per 330. Real speed will be measured in the acceptance tests. |
| Touches the slab | cup on the **back** only; edges against wooden dowels; slabs rest on each other as in any stack |
| Output | `certs.csv` (cert, grader, status, pocket and position), `certs.txt`, `report.html` with label photos |
| Budget | see [docs/BOM.md](docs/BOM.md), target $1,000–1,400 (hard cap $2,000) |

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
| `cad/out/cut_list.csv` | Aluminium extrusion and dowel cut lengths |
| `software/` | Raspberry Pi software: run loop, decoding, simulator, CLI, web page |

## Verification done so far (no hardware)

- **[Certain] 36/36 geometric checks pass** (`cad/checks.py`).
  - Picking the last slab of every pocket with full neighbours clears the head by ≥ 10 mm.
  - Carried slabs clear the dowels by ≥ 18 mm.
  - The cameras have an unobstructed view of the label.
  - All travel limits stay on the rails.
- **[Certain] Simulated end-to-end batches.** The simulator **raises a crash on any unsafe move**.
  Every slab is moved exactly once and read. It also covers:
  - pre-2016 labels routed to the front camera,
  - learning how PSA encodes 9-digit certs into the barcode,
  - double-pick detection,
  - thick holders,
  - CGC slabs read and BGS rejected,
  - overfill and seal failures stopping safely.
- **[Certain, synthetic labels] Decode sweep.**
  - The back QR reads through blur and strong glare.
  - The front barcode needs 0.05 mm per pixel; the station camera gives 0.039.
  - Not a single wrong cert was produced in any test.

## Build order

1. **Phase 0, about $150–300, one or two evenings.** Build the camera test jig (`docs/img/phase0_jig.png`)
   and run `python -m tools.phase0` on 30–50 of your own slabs. Go ahead only if at least 95%
   read and 0 come out wrong.
2. Order from the BOM. Print the parts in `cad/out/printed/`.
3. Follow `docs/BUILD_GUIDE.md`.
4. Calibrate. Run the acceptance tests on junk slabs, then do a supervised first batch.
