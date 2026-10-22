# SlabRail bill of materials (October 2026)

The line-by-line list with links is in [`BOM.csv`](BOM.csv). This page has the totals, the order
plan, where to save and where not to, the tools, and the design gaps I found while pricing.

Confidence tags: **[Certain]** = primary source, **[Likely]** = several secondary sources or a
dated listing, **[Guessing]** = estimate.

## Bottom line

- **The full list costs about $1,903 with a 15% allowance.** [Likely ±15%] That is close to the
  original $2,000 figure. You have since said $2,500–3,000 is fine if the machine works properly,
  so there is about $600–1,100 of headroom.
- **The worst case fits too.** [Guessing] Add the tools you will probably have to buy
  ($35–40), the conditional lines Phase 0 is designed to trigger (HT1 cups and the light roof,
  about $80 with the allowance), and the [Guessing] lines coming in 20% high (about +$150): about
  **$2,170**, still under $2,500.
- **About $1,634 if the school supplies its usual shop stock** (filament, wire, glue, fuses,
  common screws). [Likely] It is the cheapest headroom: the same worst case then comes to about
  $1,900.
- **About $1,547 lean:** school stock, plus generic direct-acting valves instead of Clippard, plus
  Home Depot plywood instead of Baltic birch. [Likely]
- **Keep a running tally** (a spreadsheet: line, quoted, paid). Order 1 (Phase 0) is quoted at
  ≈ $594 and order 2 at ≈ $1,309. If order 1 comes in more than about 10% over its quote, re-quote
  order 2 before buying it.
- **Spend the headroom only when a test asks for it.** The conditional lines are there for that:
  HT1 cups if Phase 0B leaves a mark, the light roof if Phase 0A shows glare, spares for whatever
  the acceptance tests break. Adding parts before the tests doesn't make the machine work better.
- **Not in any total: junk graded slabs for the acceptance tests** (15–20, some deliberately
  dropped). Take your lowest-value slabs from stock and write off 2–3 of them, or budget
  $150–400 to buy them (BUILD_GUIDE §13).
- **Things that add the most by themselves** (each still fits under $2,500):
  - buying every tool new (about +$400);
  - the genuine HIWIN rail tier (+$330);
  - a drag-chain-rated USB cable (+$150).
- **No price here is a live checkout price.** [Certain] Product pages could not be loaded from this
  session, so every price comes from search-engine extracts of listings dated 2023 to August 2026.
  - Of the $1,655 subtotal, $1,001 is [Likely] and $654 is [Guessing].
  - Misumi extrusion prices, the Z motor, both rails and the SMC cup are the least certain items.
    Get the Misumi quote first, because it moves the total the most.

## Order plan

The design says to pass two Phase 0 gates before buying any motion parts.

| Order | What | Cost incl. 15% |
|---|---|---|
| **1a — Phase 0A, camera test** | Pi 5 with PSU, microSD and cooler, both cameras, the 3 m USB extension, both LED rings, a 12 V wall adapter, M2 screws and standoffs, two 2020 jig posts, the optical endstop board, hookup wire, heat shrink, filament. Rows marked "PHASE 0A" in the CSV. | **≈ $449**; ≈ $285 with a borrowed school Pi; ≈ $216 if the school also supplies filament and wire |
| **1b — Phase 0B, cup bench test** | SMC cup and buffer, spare pads, PU tube, push fittings, IPA, a hand vacuum pump with gauge. No mains wiring, no electronics. Rows marked "PHASE 0B". Buy after 0A passes (the SMC cup may be worth ordering early: lead time). | **≈ $145** |
| **2 — Machine** | Extrusions, rails, motors, belt, brackets, fasteners, bed, dowels, Rodent, valves, pump, reservoir, vacuum sensor and ADC, 24 V PSU, mains inlet and mains box, MOSFET modules, fuses, I/O board, limit switches, laser gate, drag chain, flex cables, E-stop. Add the light-roof lines only if Phase 0 showed glare, and the HT1 cups only if the urethane cup marked. | **≈ $1,309** (+ ≈ $164 for the Pi set if you borrowed one for Phase 0) |

**If Phase 0A fails, you have spent at most ≈ $449 (≈ $285 with a borrowed Pi). If Phase 0B fails,
≈ $594, and the first fix is the HT1 cup (+ ≈ $41), not abandoning the project.** Nothing from
order 2 has been bought at that point. [Certain, by construction of the tags]

## Totals by category

| Category | Total | Usually at school | Biggest line |
|---|---:|---:|---|
| Frame (extrusion) | $154.00 | — | X beam 4040 × 1416, $42 |
| Motion | $135.00 | $8 | MGN12 1300 rail + block, $48 |
| Fasteners & brackets | $207.00 | $39 | 4040 corner brackets, $18 |
| Bed, rods & light roof | $136.00 | $32 | Baltic birch 12 × 60 in, $56 |
| Controller & compute | $206.00 | — | Raspberry Pi 5 4 GB, $110 |
| Cameras & lighting | $149.50 | — | ELP 8 MP head camera, $66 |
| Vacuum & gripper | $264.32 | $10 | 2 × Clippard EV-2-24 valves, $72 |
| Sensors | $62.00 | $3 | 2 × XGZP6847A, $16 |
| Power & switching | $161.26 | $38 | Mean Well LRS-150-24, $21.51 |
| Wiring & cable management | $144.00 | $68 | 8-core flex cable, $18 |
| Printed parts (filament) | $36.00 | $36 | 2 kg PETG |
| Acceptance tests | $0.00 | — | junk slabs, conditional (qty 0) |
| **Subtotal** | **$1,655.08** | **$234** | |
| Spares, shipping, duties (15%) | $248.26 | | |
| **Grand total** | **$1,903.34** | | |
| Minus school stock (+ its 15%) | −$269 | | **≈ $1,634** |
| Lean swaps (below), with school stock | | | **≈ $1,547** |

**What changed since the first pricing (+$206):** +$112 of parts the review found the design needs
(a closed mains box $20, a Class 2 laser $7, a second E-stop contact block $3, a hand vacuum pump
for Phase 0B $30, a 12 V adapter for Phase 0A $10, separate head (40 mm) and station LED rings
+$12, and M5×25 / M5×16 / M5×20 / button-head screws, M2 standoffs and M3 set screws +$30), and
+$94 of allowance (15% instead of 10%).

**Conditional lines are in the CSV with qty 0 and are not in the total.** Buy them only if a test
fails:
- Schmalz HT1 cups, 2 × $18. Buy if the urethane cup marks slabs.
- Generic buffer backup, $14. Buy if the SMC lead time is long.
- Stepper extension cable, $8. Buy if the X motor's lead is too short.
- Light roof (foam board $8, gaffer tape $12, two 2020 × ~500 mm posts $14). The roof is optional
  (CONTRACT): buy it only if Phase 0 or the first runs show room-light glare on the labels.
- 1N5819 flyback diodes, $6. Only if you swap the Adafruit #5648 modules for ones without an
  on-board diode (for example D4184 modules).
- Junk graded slabs for the acceptance tests (above).

**The allowance is 15%.** [Likely] The US removed the de minimis duty exemption in 2025, so
AliExpress parcels now carry duty, and much of the small stuff comes from AliExpress.

## The 5 biggest cost items

1. **Raspberry Pi 5 4 GB, $110.** [Likely] DRAM costs pushed the list price from $60 to $70 (Dec
   2025), then $85 (Feb 2026), then about $110 (Apr 2026). Street prices may be higher.
2. **Two Clippard EV-2-24 direct-acting NC valves, $72.** [Likely] Distributors list them at
   $34.52 and $37.73.
3. **ELP 8 MP IMX179 USB head camera with the 3.6 mm M12 lens, $66.** [Likely] eBay listings run
   $60–71.
4. **Rodent controller, $56, tied with the 18 mm Baltic birch bed blank, $56.** [Likely] The BIQU
   US store listed the Rodent at $56 but showed it sold out, and the EU store lists it at €69.
5. **MGN12 1300 mm rail + MGN12H, $48, tied with the two 2040 × 1416 base rails, 2 × $24.**
   [Guessing]

The 15% allowance ($248) is bigger than any single part.

## Where to save

- **Valves.** Generic 24 V direct-acting 2/2 NC micro valves cost about $6 each instead of $36,
  saving about $60.
  - They work if they are truly direct-acting. Test them when order 2 arrives (BUILD_GUIDE §8.3,
    reservoir test): hold −60 kPa for 60 s with the pump off and watch the sensor.
  - Their orifice is small, so venting is slower. Lengthen `vent_s` if release lags.
- **Plywood.** Use 23/32 in sanded plywood from Home Depot, ripped to 290 mm, about $35–45 instead
  of $56. It has more voids, so drill a test hole away from the pockets first.
- **Rails.** The generic MGN12 rail is enough here. Pockets have ±1.85 mm of play and the slabs sit
  in rods, so you don't need HIWIN precision.
  - Clean the rail.
  - Count the balls in the carriage before installing it, because clones lose balls when the
    carriage slides off the rail.
  - Re-grease it.
- **Extrusions.** Amazon 20-series V-slot in stock lengths, cut at school, costs about the same
  ($130–150). Only do it if the school saw cuts square. Misumi's free cut to ±0.5 mm saves an
  afternoon of squaring.
- **Fasteners.** One large M5 T-nut and screw kit plus one M3 kit can replace the separate packs.
  Count first: about 124 M5 T-nuts and 65 M3 rail screws are needed, and the kit must contain
  M5×12/16/20/25/30, M5×12 button heads and M3×8/12/16/20 (BOM.csv notes say where each goes).
- **Pi 5 2 GB.** It would probably run the software. [Guessing] It saves maybe $30–40, but the
  contract specifies 4 GB, so test memory use in `sim` before switching.

## Where NOT to save

- **The cup and buffer.** Buy a genuine urethane pad and spare pads. The cup is the only part that
  touches your slabs. A cheap silicone cup can leave silicone residue rings on glossy plastic.
  [Likely] Run the 24 h marking test on a junk slab before any real inventory goes in (Phase 0B,
  then again on the machine, BUILD_GUIDE §13.2).
- **Valve type.** Never use pilot-operated, "servo-assisted" or diaphragm water valves. They need
  a pressure difference of 0.2–0.5 bar to work, so they won't seal or open reliably on vacuum.
  [Likely] The listing must say "direct acting" and give a vacuum rating, or a "0 bar" minimum.
- **The MOSFET modules.** Use modules specified for 3.3 V logic. The BOM's Adafruit #5648 is
  listed for 3–20 V logic and has its flyback diode on board (WIRING.md §4). IRF520 modules barely
  switch from a 3.3 V Pi pin. [Likely] If you substitute modules without an on-board diode (D4184
  type), add a flyback diode across the pump and each valve coil (the conditional 1N5819 line).
- **The 24 V PSU and mains side.** Buy a Mean Well, not an unbranded "24 V 10 A" brick, and the
  closed mains box for the IEC inlet: a snap-in inlet on a 6 mm plywood panel leaves live tabs
  open. Have an instructor check the inlet, fuse, box and earth wiring before first power-up.
- **The laser.** Buy a ≤ 1 mW (Class 2) module. The KY-008 that comes with the receiver kit is
  usually sold as 5 mW (Class 3R), and the beam is on whenever the Pi is on, at face height when
  you bend over the stacks. [Likely]
- **The E-stop's second contact block** (about $3). A single block switching the 24 V capacitor
  inrush can weld closed without you noticing (WIRING.md §1.3).
- **The 4040 profile type.** It must be 20-series, slot 6, with two slots per face. Amazon's
  "4040 European standard" is often 40-series slot 8 with one slot per face, and the printed mounts
  won't fit it. [Likely]
- **Dowel straightness.** Roll every dowel on a flat table and reject bowed ones. A bowed rod
  narrows the pocket at the top, where the cup lifts a full stack.

## Required tools (not in the machine total)

Most of these are standard in a tech-school shop. The "buy" column is the price if the school
doesn't have one.

| Tool | Used for | Buy price if missing | At school? |
|---|---|---:|---|
| Drill (cordless or drill press) | 82 rod holes, bed bolts | $60–100 | Likely |
| **8 mm brad-point bit, new and sharp** | Rod holes. Match the dowels you bought: use 5/16 in if they are 5/16 in. | $10 | **Buy** |
| **Depth-stop collar, 8 mm** | All rod holes the same 15 mm deep | $5 | **Buy** |
| Drill guide (Milescraft DrillBlock type) or a drill press with long-table support | Holes square to the bed. The printed `drill_template` sets the position, not the angle. | $15–40 | Likely |
| Metric hex keys, 1.5–10 mm, ball end | All socket screws | $15 | Likely |
| Digital calipers, 150 mm | Measuring 5 of your slabs (`dims.py`), dowels, ring OD/ID, camera board holes | $20 | Likely |
| Ferrule crimper (self-adjusting) | Screw-terminal wire ends | $25 | Maybe |
| JST/Dupont crimper (IWISS SN-28B or SN-2549) | Sensor and GPIO connectors | $25 | Maybe |
| Wire stripper, flush cutters | Wiring | $20 | Likely |
| Multimeter | Wiring checks, sensor voltages, beam receiver level | $30 | Likely |
| Temperature-controlled soldering iron | Diodes, divider resistors, LED ring leads | $30–100 | Likely |
| **Heat-set insert tips** (ruthex set fits 900M/T18 irons; TS100-style tips for a Pinecil) | M5 insert in `awl_adapter`, spares | $10–16 | **Buy** unless the shop has them |
| Fine saw + miter box, or a bandsaw | Cutting 82 dowels to 236 mm | $15 | Likely |
| Jigsaw | 41 × 41 mm notches in the bed for the uprights (CONTRACT) | $50 | Likely |
| M5/M3 taps + tap handle; **1/8 NPT tap** | Extrusion end taps; reservoir caps | $8 (NPT) | Taps likely; NPT maybe |
| Dial indicator + magnetic base | Beam-twist check (DESIGN.md) | $25 | Likely (machine shop) |
| Heat gun, clamps, square, level, 120/220 sandpaper | General; doming the rod tops | $25 | Likely |

**Tools you will probably have to buy: about $35–40.** That is the brad-point bit, depth collar,
heat-set tips and NPT tap. **If you had to buy every tool new, the total would be about $2,300**
($1,903 + about $400), so use the school's where you can.

## How the quantities were derived

- **Extrusions.** These are `model.cut_list()` values, plus two 2020 × 312 mm posts for the
  Phase 0 jig, an optional 2020 × 600 mm rear brace and, only if you build the optional light
  roof, two 2020 × ~500 mm roof posts:
  - 2040 × 1416 (2)
  - 4040 × 401 (2)
  - 4040 × 1416 (1)
  - 2040 × 340, both ends tapped M5 (1)
  - 2020 × 285 (1)
  - plus the Z lead screw, cut to 340 mm below the motor face (`cut_list()`)
- **Rods.** `len(layout.rods())` = 82. Each is 218 mm above the pad + 3 mm pad + 15 mm embedded =
  236 mm, so 300 mm stock leaves room to trim. Buy 100 so you can reject bowed ones.
- **Pads.** There are 13 pockets, and each pad is 83 × 138 mm.
- **M3 rail screws.** MGN12 rails have holes at 25 mm pitch: 1300 mm needs 52 and 330 mm needs 13.
  The carriages take 4 × M3 each on a 20 × 20 mm pattern. [Certain]
- **M5 T-nuts, about 124.** That covers:
  - brackets and joining plates (about 80–90 nuts);
  - 14 for the printed mounts on the extrusions: x_motor_mount 4, x_idler_mount 2, x_bracket 4
    (the spine), z_plate 2 (the drop arm), x_bumper_L 1, z_motor_mount tab 1. The z_motor_mount
    and z_end_cap screw into the spine's tapped end bores instead;
  - 16 bed bolts;
  - 6 feet (both base rails at each end and at midspan).
- **Wood screws.** station_mount 4, gate posts 4 and the electronics panel.
- **Filament.** `print_list.json` totals 705 cm³ of solid parts in 22 prints, including the
  Phase 0 jig, the drill template and two fill gauges. That is 895 g of PETG if printed solid, or
  about 630 g at the listed walls and infill. Add a Pi case, electronics trays, cable clips and
  reprints, and it comes to about 1.0–1.3 kg, so the list has 2 kg. [Likely]

## Design gaps found while pricing (for the CAD and wiring owners)

These are not BOM problems, but they decide what gets bought.

**Resolved since pricing** (the CAD decisions in CONTRACT.md):
- The MGN12 rails now sit on slots: the X rail centre is at Z = 410 on the 4040's upper front slot,
  and the Z rail is in the 2040 spine's right slot, on the cup axis. The M3 T-nuts in this BOM
  reach every rail hole. [Certain, `cad/out/checks.txt`: both rails 0.0 mm off a slot]
- The bed has 41 × 41 mm notches at the two upright positions, so the uprights pass through to the
  back base rail. [Certain, `model.py`]
- The light roof is optional and left out of the CAD. If you build it, it goes on two 2020 posts
  bolted to the uprights' outer end faces (X −68 and 1348), clear of the joining plates and the X
  motor (conditional lines in the CSV).
- The 2020 drop arm is 285 mm and gets two 5.5 mm cross holes for the `head_foot` and
  `camera_bracket` M5 bolts, 19 and 84 mm from its lower end (BUILD_GUIDE §7.5).
- The Z machinery now sits above the highest point a held slab can reach (the Z top hard stop),
  and the lead screw is cut to 340 mm, so nothing fixed to the X carriage can touch a held slab or
  a stack. Printed end bumpers and a `z_end_cap` are hard stops on both axes. [Certain,
  `cad/out/checks.txt`]
- The mains side has a closed box, the laser is Class 2, and the E-stop has two contact blocks.
- The MOSFET modules and limit switches now match WIRING.md: Adafruit #5648 (diode on board) and
  bare SPDT lever microswitches wired C/NC.

**Still open:**
1. **[Certain, CAD] There are only 18 mm between each rail end and the upright's inner face.** The
   rail starts at X = −10 and ends at 1290; the uprights' inner faces are at −28 and 1308. A 40 mm
   front-face corner bracket won't fit there, and on the right the `x_motor_mount` plate covers
   the beam's front face anyway. Use back-face brackets and flat joining plates on the outer ends.
2. **[Likely] The laser receiver module is a 5 V board.** Divide its output before GPIO 5. It is
   also non-modulated, so room light can hold it HIGH. Test it with the room lights on.
3. **[Likely] Angel-eye LED rings are 12 V parts.** The BOM adds a 24→12 V buck. Measure the ring
   OD and ID before printing the ring seats (head: 40 mm ring, seat bore 41 mm; station 52–60 mm).
4. **[Guessing] Some mounting patterns in the CAD are not verified.**
   - The head camera board's hole pattern is assumed to be 32 mm square, and its
     board-to-lens-front length 20 mm (`HEAD_LENS_PROJ`).
   - The optical endstop's hole spacing is assumed to be 19 mm.
   - Measure these parts before printing `camera_bracket`, `phase0_top` and `head_foot`.
5. **[Guessing] The non-rotating SMC buffer code is not confirmed.** The BOM line is
   `ZPT25UUK25-B5-A10`, built from SMC's code pattern (K = non-rotating). I could not find it in a
   distributor listing. Ask the SMC configurator or a distributor before ordering; if only a
   rotating (J) buffer is offered, you have to make an anti-rotation guide for the probe flag
   yourself (BUILD_GUIDE §7.6), because the CAD has none.
6. **[Likely] The SMC ZPT buffer has an M5 female port on top of its rod, and the rod rises up to
   25 mm on contact.** The vacuum tube needs slack. The optical probe flag must clamp to the rod
   below the fitting.
7. **[Certain, forum report] BTT has shipped Rodents with an old FluidNC build.** Reflash the
   current FluidNC release before loading `firmware/fluidnc/config.yaml`. Also check the Rodent's
   limit and motor connector types (XH or other) before buying crimp housings.
8. **The Phase 0 jig posts (2 × 2020 × 312 mm) are not in `cut_list()`.** Their length sets the
   head-camera distance in the jig, so they must be cut square to 312.0 ± 0.5 mm.

## Main sources

- **Raspberry Pi 2026 prices:** [Liliputing/Heise/TechSpot reports](https://www.techspot.com/news/111165-raspberry-pi-prices-soar-amid-ai-memory-shortage.html),
  [The Register (Feb 2026)](https://www.theregister.com/2026/02/02/raspberry_pi_ram_shortage_price_hike/)
- **Rodent:** [BIQU product page](https://biqu.equipment/products/bigtreetech-rodent)
- **LRS-150-24:** [TRC Electronics](https://www.trcelectronics.com/products/mean-well-lrs-150-24),
  [Jameco](https://www.jameco.com/z/LRS-150-24-Mean-Well-156W-24V-6-5A-Single-Output-Switchable-Power-Supply_2257740.html)
- **Pi 5 camera cable 500 mm:** [Adafruit 5820](https://www.adafruit.com/products/5820)
- **Clippard EV-2-24:** [Wilson Co.](https://www.wilson-company.com/product/ev-2-24/2-way-wire-leads-side-radial-valve-ev-series),
  [AHE](https://aheinfo.com/product/clippard-ev-2-24-elec-valve)
- **SMC ZPT/ZP codes and prices:** [ZP25UU on Octopart](https://octopart.com/part/smc/ZP25UU),
  [ZPT20CNJ20-B5-A10](https://automationdistribution.com/zpt20cnj20-b5-a10)
- **Schmalz HT1 "non-marking":** [Schmalz SAB HT1](https://www.schmalz.com/en/vacuum-technology-for-automation/vacuum-components/vacuum-suction-cups/suction-cups-for-handling-glass/bellows-suction-cups-sab-ht1-1-5-folds)
- **XGZP6847A100KPGN:** [Flux/LCSC listing](https://www.flux.ai/lcsc/gzp6847a001mpp50k.md)
- **Baltic birch 12 × 60:** [Woodcraft](https://www.woodcraft.com/products/baltic-birch-plywood-18mm-3-4-x-12-x-60-nominal-finished-2-sides)
- **HIWIN MGN12 price tier:** [DamenCNC MGNR12](https://www.damencnc.com/en/hiwin-profile-rails-narrow-type-mgnr-12-hm/a1945)
- **Iverntech 400 mm Tr8x8 motor:** [Newegg listing](https://www.newegg.com/p/298-00MU-00184)
- **VXB vacuum pump:** [VXB 10 L/min −81 kPa](https://vxb.com/products/tiny-10-liters-per-minute-dc-vacuum-pump-with-81-k)
- **Laser receiver behaviour:** [Acxico KY-008 listing](https://woodartsupply.com/products/acxico-2sets-laser-sensor-module-for-arduino-avrky-008-laser-transmitter-laser-receiver-sensor-module-non-modulator-tube)
- **D4184 module notes:** [ProtoSupplies](https://protosupplies.com/product/d4184-mosfet-control-module/)
- **FluidNC on Rodent:** [V1E forum thread](https://forum.v1e.com/t/bigtreetech-rodent-cnc-controller-lr-4/46654)
