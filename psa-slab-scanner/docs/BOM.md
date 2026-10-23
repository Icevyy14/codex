# SlabRail bill of materials (October 2026)

The line-by-line list with links is in [`BOM.csv`](BOM.csv). The same parts, grouped into the three
orders you actually place, are in [SHOPPING_LIST.md](SHOPPING_LIST.md). This page has the totals,
the order plan, where to save and where not to, the tools, and the design gaps found while pricing.

Confidence tags: **[Certain]** = primary source (for a price: the product page itself, opened on
22 Oct 2026), **[Likely]** = several secondary sources or a dated listing, **[Guessing]** = estimate.

## Bottom line

- **The full list costs about $2,182 with a 15% allowance.** [Likely ±10%] You have said
  $2,500–3,000 is fine if the machine works properly, so there is about $300–800 of headroom.
- **The total did not change this round.** The two homing switches now have printed mounts. They
  need 4 more M5×10 button heads, 4 more M5 T-nuts and 4 × M2×12 with nuts, all from packs
  already in the list, and about 33 cm³ more filament. The switch line now says to buy the short
  hinge lever. In round 4 two lines moved between orders and the confidence tags were aligned;
  in round 3 the list went up $209 ($182 of parts plus the allowance), almost all of it real
  product-page prices replacing estimates (below).
- **$1,383 of the $1,897 subtotal is a price seen on the product page** [Certain, 22 Oct 2026],
  $175 is [Likely] and $339 is [Guessing] (mostly the Misumi extrusions, which block scripts: get
  that quote first, and Amazon lines whose price was not visible). The allowance covers shipping
  already seen but not in the line prices (LiMo DDP $39, Digi-Key Marketplace $28, MakerStock
  $13.49, the endstop boards $5.70) and the ones not shown (ELP express and duty, Proax shipping
  and brokerage, AFT's small-order fee, Misumi).
- **The worst case fits too.** [Guessing] Add the tools you will probably have to buy
  ($45–50), the conditional lines Phase 0 is designed to trigger (HT1 cups and the light roof,
  about $77 with the allowance), and the [Guessing] lines coming in 20% high (about +$78): about
  **$2,380**, still under $2,500.
- **About $1,862 if the school supplies its usual shop stock** (filament, wire, glue, fuses,
  common screws, the flag sheet). [Likely] It is the cheapest headroom: the same worst case then
  comes to about $2,050.
- **About $1,787 lean:** school stock, plus generic direct-acting valves instead of Clippard.
  [Likely] (The bed is already the Home Depot birch panel: the Baltic birch blank is no longer
  listed online.)
- **Keep a running tally** (a spreadsheet: line, quoted, paid). Order 1 (Phase 0) is quoted at
  ≈ $626 and order 2 at ≈ $1,556. If order 1 comes in more than about 10% over its quote, re-quote
  order 2 before buying it.
- **Spend the headroom only when a test asks for it.** The conditional lines are there for that:
  HT1 cups if Phase 0B leaves a mark, the light roof if Phase 0A shows glare, and one upgrade per
  acceptance test that can fail (below). Adding parts before the tests doesn't make the machine work
  better. If every conditional line triggered at once, the total would reach about $3,330; that
  many failed tests would mean the design needs rethinking, not more parts. [Guessing, arithmetic]
- **Not in any total: junk graded slabs for the acceptance tests** (15–20, some deliberately
  dropped). Take your lowest-value slabs from stock and write off 2–3 of them, or budget
  $150–400 to buy them (BUILD_GUIDE §13).
- **Things that add the most by themselves:**
  - buying every tool new (about +$460, total about $2,640: over $2,500, inside $3,000);
  - the genuine HIWIN rail tier (about +$420, conditional line);
  - a branded pump with a flow curve (about +$200 [Guessing], conditional line).
- **Six lines in the total still have only a search hint, no product link:** the 40 mm COB head
  ring (a 12-SMD ring that fits the seat is the fallback), the branch fuse holders, the drag chain,
  the M5×10 button heads and the two shielded moving cables (the igus cable in their notes is
  unshielded, 4-core and sold by the foot). Their estimates stay in the total, and a few
  linked prices were not visible (Amazon blocks scripts): SHOPPING_LIST.md marks each one. Look
  them up before the order they belong to.

## Order plan

The design says to pass two Phase 0 gates before buying any motion parts. Each order, with a link
per line, is in [SHOPPING_LIST.md](SHOPPING_LIST.md).

| Order | What | Cost incl. 15% |
|---|---|---|
| **1a — Phase 0A, camera test** | Pi 5 with PSU, microSD and cooler, both cameras, the 3 m USB extension, both LED rings, a 12 V wall adapter, M2 screws and standoffs, two 2020 jig posts and the 66 mm arm stub, the optical endstop boards, the flag sheet, hookup wire, heat shrink, filament. Rows marked "PHASE 0A" in the CSV. **Plus, from school stock:** a handful of M5/M3 screws (6 × M5×10, 6 M5 washers, 6 M5 T-nuts or plain M5 nuts, 1 × M5×30 + nylock, 2 × M3×16 + 4 washers + 2 nuts) and a strip of microfiber with spray adhesive or double-sided tape for the tray ledges: their packs are order-2 lines. | **≈ $470**; ≈ $281 with a borrowed school Pi; ≈ $202 if the school also supplies filament, wire, heat shrink and the flag sheet |
| **1b — Phase 0B, cup bench test** | Two SMC cups and buffers (one is the spare), spare pads, the M5 barb elbows, PU tube (with its fittings kit), PTFE tape, IPA, a hand vacuum pump with gauge. No mains wiring, no electronics. Rows marked "PHASE 0B". Buy after 0A passes, or order the two cups and the two elbows with 0A: Proax shows the cups back-ordered with no lead time, and cup, buffer and elbow are the jig's real occluder. | **≈ $155** |
| **2 — Machine** | Extrusions, rails and a spare block, motors, belt, brackets, fasteners, bed, dowels, Rodent, valves, pump, reservoir and its push fittings, vacuum sensor and ADC, 24 V PSU, mains inlet and mains box, MOSFET modules, fuses, I/O board, limit switches (short hinge lever), laser gate, drag chain, flex cables, E-stop, and the screws for the carry-height sensor and the two switch mounts (the sensor's board is already in the 0A endstop packs; the switches' M2 screws in the 0A M2 kit). Add the light-roof lines only if Phase 0 showed glare, the HT1 cups only if the urethane cup marked, and an upgrade line only when its test failed. | **≈ $1,556** (+ ≈ $190 for the Pi set if you borrowed one for Phase 0) |

**If Phase 0A fails, you have spent at most ≈ $470 (≈ $281 with a borrowed Pi). If Phase 0B fails,
≈ $626.** The first fix to try would be the HT1 cup (+ ≈ $41), but it needs an M10×1-to-G1/8
adapter nobody has sourced yet: until one is found, a cup that marks means stop and ask.
Nothing from order 2 has been bought at that point. [Certain, by construction of the tags]

## Totals by category

| Category | Total | Usually at school | Biggest line |
|---|---:|---:|---|
| Frame (extrusion) | $158.00 | — | 2 × 2040 × 1416 base rails, $48 |
| Motion | $191.69 | $10.99 | VXB Z motor 3-pack, $99.99 |
| Fasteners & brackets | $268.99 | $49.13 | CNC Kitchen heat-set insert kit, $26.99 |
| Bed, rods & light roof | $158.38 | $35.74 | PureBond birch panel, $60.17 |
| Controller & compute | $225.80 | — | Raspberry Pi 5 4 GB, $110 |
| Cameras & lighting | $137.30 | — | ELP 8 MP head camera, $55 |
| Vacuum & gripper | $294.61 | $12.00 | 2 × Clippard EV-2-24 valves, $77.90 |
| Sensors | $92.42 | $11.99 | 5 × XGZP6847A, $36 |
| Power & switching | $197.28 | $47.12 | AutomationDirect E-stop set, $36.75 |
| Wiring & cable management | $146.09 | $84.13 | 22 AWG hookup wire set, $19.95 |
| Printed parts (filament) | $26.78 | $26.78 | 2 kg PETG |
| Acceptance tests | $0.00 | — | junk slabs, conditional (qty 0) |
| **Subtotal** | **$1,897.34** | **$277.88** | |
| Spares, shipping, duties (15%) | $284.60 | | |
| **Grand total** | **$2,181.94** | | |
| Minus school stock (+ its 15%) | −$319.56 | | **≈ $1,862** |
| Lean swap (generic valves), with school stock | | | **≈ $1,787** |

**What changed in this round ($0.00):**
- **Homing switches:** the CAD now has printed mounts (`x_switch_mount`, `z_switch_mount`), so the
  2020 corner brackets no longer carry the switches. The line now asks for the short hinge lever
  (Omron SS-5GL size, a lever ending at the body's end): the mounts take a lever up to 23 mm from
  the hinge end, and a longer one is cut back to 20 mm (BUILD_GUIDE §6.8).
- **M5×10 button heads:** 6 needed, not 2 (2 per switch mount). Same pack, same price
  [Guessing, a small pack of 10 or more].
- **M5 T-nuts:** about 130 needed, not 126 (2 per switch mount). The 150-pack still covers them
  and the 6 for the Phase 0 jig.
- **M2 kit:** 4 × M2×12 and 4 nuts more, for the switches. No price change.
- **M2 standoffs:** the jig's bridge is now 10.6 mm thick, so a standoff is the board-to-lens
  length minus 10.0 mm, with 2.0 mm of plastic around each hole.
- **Head LED ring:** the seat is now a 42.8 mm bore with three centring ribs: it takes a ring of
  39.5–42.5 mm OD.
- **Filament:** 801 cm³ in 27 prints (was 768 in 25). The 2 kg still cover it.

**What changed in round 4 ($0.00):**
- **Push fittings kit** ($11.99) from order 1b to order 2: its 1/8 NPT fittings go only into the
  reservoir cap. Phase 0B uses the tube and the barb elbow.
- **PTFE tape** ($2.36) split out of the reservoir set ($19.93 → $17.57) into its own order-1b
  line: Phase 0B seals the elbow's M5 thread with it.
- **Confidence tags** now follow each line's price evidence, in the CSV and the shopping list
  alike. In the CSV, six lines whose price was never seen went from [Likely] to [Guessing] (the two
  M2 kits, the M5×12 button heads, the M2.5/M3 standoff kit, the resistor kit, the awl pin) and
  three whose price was seen went to [Certain] (the M-5ALU-4 elbows, the vacuum sensors, the MOSFET
  modules). In the shopping list, the mains inlet and the mains wire went from [Likely] to
  [Guessing], as in the CSV.
- **Specs and notes:** the awl pin is one spec now (steel or stainless, hardened not needed); the
  station ring seat takes a 60 or a 63 mm ring; the head ring line has a fallback; the moving
  cables link to a search, not to the per-foot igus page; "measure before printing" names the
  Phase 0 part, which is printed first.

**What changed in round 3 (+$182.08, +$209.39 with the allowance):**
- **Links and prices from a sourcing run** (22 Oct 2026), spot-checked line by line. Every line
  in the total now carries a product link except the six above. Where the link is [Likely] or
  [Guessing], the old search hint stays after it. Price changes of $10 or more: up, the Z motor
  +$69.99, vacuum sensors +$20.00, E-stop +$19.75, mains and earth wire +$15.00 (still an
  estimate), microSD +$13.95, pad cloth +$13.48, pad foam +$10.99, heat-set inserts +$10.99, check
  valves +$10.60; down, the LiMo rails and block −$23.90, the hand pump −$14.01, the two SMC cups
  −$13.76 (Proax), the head camera −$11.00 (the ELP store), the dowels −$10.00. Every other line
  moved by less than $10.
- **Spec corrections from the sourcing run, applied because they are plainly right:**
  - **Bed:** the Woodcraft 12 × 60 in Baltic birch blank is no longer listed; the line is now a
    Home Depot 3/4 in PureBond birch 2 × 8 ft panel (17.9 mm), one rip and one crosscut.
  - **Dowels:** 5/16 in (7.94 mm) × 12 in, so the brad-point bit and collar are 5/16 in.
  - **Class 2 laser:** the only module found (Quarton VLM-650-03) has a 7 mm body. The left gate
    post now prints with a 7.2 mm barrel hole for it (BUILD_GUIDE §5.9).
  - **Pump "upgrade":** the VXB 10 L/min pump is probably the main pump itself (VXB's SKU is the
    Amazon ASIN) [Likely]. The upgrade line is now an unsourced branded pump, about $200
    [Guessing].
  - **Optical endstop boards:** the 3-pack is out of stock; two 2-packs give 4 boards (probe,
    carry-height sensor, 2 spares). The listing does not name the TCST2103: measure it.
  - **Flag sheet:** at least 50 × 60 mm, for the probe flag and the new carry flag.
- **Not applied:** the sourcing run's igus chainflex cable for both moving cables. It is
  unshielded and 4-core, so the head cable would become two runs with renumbered cores. The
  shielded 8-core line stays [Guessing, price not seen]; the igus cable is listed as a verified
  alternative in the CSV.
- **New lines for the carry-height sensor** (BUILD_GUIDE §7.4a, WIRING.md §6a): the board (the
  second one in the endstop packs, $0), the carry flag (cut from the flag sheet, $0), 2 × M5×10
  button heads ($6, new), the M3 screws, washers, nuts and T-nuts (from the existing packs, $0),
  its 0.2 m lead (the board's own 3-pin cable, $0) and the two printed parts ($0). A 10 kΩ + 20 kΩ
  divider for GPIO 6 comes from the resistor kit.
- **Phase 0 jig:** six M5 washers, not twelve (one under each M5×10: the jig walls are now 4 mm).

**What changed in the earlier rounds (+$266 in all):** the second SMC cup and buffer, the M5 barb
elbows, a spare rail block and the jig's arm stub (+$60), and +$112 of parts the first review found
the design needs (a closed mains box, a Class 2 laser, a second E-stop contact block, a hand vacuum
pump, a 12 V adapter, separate head and station LED rings, more screw sizes, M2 standoffs, set
screws), plus the allowance going from 10% to 15% (+$94).

**Conditional lines are in the CSV with qty 0 and are not in the total.** Buy them only if a test
fails:
- Schmalz HT1 cups, 2 × $18 [Guessing: the price needs a Schmalz login]. Buy if the urethane cup
  marks slabs. The 25 mm HT1 cups are G1/8-threaded and need an M10×1-to-G1/8 adapter nobody has
  sourced yet: find it before Phase 0B. Until then, a cup that marks means stop and ask.
- Stepper extension cable, $8. Buy (or make) it if the X motor's lead is too short.
- Light roof (4 foam boards $5, gaffer tape about $12, two 2020 × ~500 mm posts $14). The roof is
  optional (CONTRACT): buy it only if Phase 0 or the first runs show room-light glare.
- 1N5819 flyback diodes, $6. Only if you swap the Adafruit #5648 modules for ones without an
  on-board diode (for example D4184 modules).
- Junk graded slabs for the acceptance tests (above).

**Upgrades, also qty 0: buy one only when its test fails** (about $920 if all of them).
[Likely for the failure each one removes; prices as tagged]

| Upgrade | About | Buy only if |
|---|---:|---|
| Genuine HIWIN MGNR12 rail + block (replace both) | $420 [Certain in EUR, Guessing on the exchange rate] | The generic X rail fails the §6.1 roll test (notches or binding after cleaning and greasing), or binds in §13.1 |
| Z motor with a published torque curve | $55 [Guessing] | The §7.8 lift test still fails after the free fixes: Z at 3000 mm/min and Z current raised to about 60% of the motor's rating, motor under 50 °C. No off-the-shelf motor with an 8 mm lead and a 311–356 mm screw was found: ask for a custom screw length. |
| Constant-force spring for Z | $20.36 [Likely] | The §7.8 hold test creeps. Its mount is not in the CAD. |
| High-flex USB cable (L-com CAUAAHFX-3M + coupler) | $50 [Likely] | Head-camera dropouts in §13.1, §13.2 or later runs that the spare cable does not cure. It is rated 10,000 flex cycles, not continuous drag-chain duty. |
| Branded 24 V vacuum pump with a flow curve | $200 [Guessing] | The generic pump fails the §8.3 seal or reservoir test although the line holds |
| Schneider Harmony XB5AS8444 E-stop (2 NC) + box | $175 [Likely] | The monthly E-stop check ever finds the 24 V bus live. [Likely] Even these blocks are rated below the capacitor inrush, so keep two in series and the check. |

**Not bought, on purpose:** a closed-loop Z motor (the Rodent has no step/dir header for one, and
FluidNC uses StallGuard only for homing [Likely]); a spare Rodent (a dead board is a safe stop, and
its Y and E driver sockets are already spares [Certain, CONTRACT]); a better head camera (it gives
0.055 mm/px against the 0.14 mm/px the back QR needs [Certain, synthetic labels]; buy one only if
Phase 0A fails on sharpness, not on glare). **The Z stall detector is now in the design** at about
$6: the spare TCST2103 board on the Z spine with a flag on `z_plate` (BUILD_GUIDE §7.4a). It sees a
loaded head that ended more than about 2.5 mm low before any sideways move; it does not make a weak
Z motor strong, so the §7.8 lift test still has to pass.

**The allowance is 15%.** [Likely] The US removed the de minimis duty exemption in 2025, so
parcels from abroad (ELP from China, LiMo, Proax from Canada) carry duty, and several shops add
shipping the line prices leave out (above).

## The 5 biggest cost items

1. **Raspberry Pi 5 4 GB, $110** [Certain, CanaKit, board only]. DRAM costs pushed the list price
   from $60 to $70 (Dec 2025), then $85 (Feb 2026), then about $110 (Apr 2026). [Likely]
2. **VXB NEMA17 + TR8×8 400 mm, 3-pack, $99.99** [Certain, VXB]. 1.7 A, 1.7 Ω, 3.1 mH, 0.44 N·m:
   every number the Z motor rule asks for is on the page. You need one; the other two are spares.
   A single motor with the same published specs would save about $70.
3. **Two Clippard EV-2-24 direct-acting NC valves, $77.90** [Certain, Clippard; AHE listed $25.90
   each on sale].
4. **Two SMC `ZPT25UUK20-B5-A10` cups and buffers, $70.24** [Certain, Proax: CAD 49.34 each,
   back-ordered]. Canadian shipping and brokerage are extra.
5. **The bed panel, $60.17** [Certain, Home Depot], then the Rodent ($56, in stock at BIQU) and the
   ELP head camera ($55, ELP's own store).

The 15% allowance ($285) is bigger than any single part.

## Where to save

- **Valves.** Generic 24 V direct-acting 2/2 NC micro valves cost about $6 each instead of $39,
  saving about $66.
  - They work if they are truly direct-acting. Test them when order 2 arrives (BUILD_GUIDE §8.3,
    reservoir test): hold −60 kPa for 60 s with the pump off and watch the sensor.
  - Their orifice is small, so venting is slower. Lengthen `vent_s` if release lags.
- **The Z motor.** A single motor whose listing gives 1.5–2.0 A, ≤ 4 mH and an 8 mm lead saves about
  $70 over the VXB 3-pack. Measure 1–2 Ω per phase on arrival; reject anything around 10 Ω.
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
  Count first: about 130 M5 T-nuts (plus 6 for the Phase 0 jig) and 69 M3×10 are needed, and the kit
  must contain M5×10/12/16/20/25/30, M5×12 and M5×10 button heads and M3×8/10/12/16/20 (BOM.csv
  notes say where each goes). AFT charges a small-order fee under $75.
- **Small shop items.** The flag sheet ($11.99 + $13.49 delivery for a 12 × 12 in sheet) and the
  wood screws (Parts Express shipping) are cheaper as school offcuts or a local hardware-store pack.
- **Pi 5 2 GB.** It would probably run the software. [Guessing] It saves maybe $30–40, but the
  contract specifies 4 GB, so test memory use in `sim` before switching.

## Where NOT to save

- **The cup and buffer.** Buy a genuine urethane pad and spare pads. The cup is the only part that
  touches your slabs. A cheap silicone cup can leave silicone residue rings on glossy plastic.
  [Likely] Run the 24 h marking test on a junk slab before any real inventory goes in (Phase 0B,
  then again on the machine, BUILD_GUIDE §13.2).
  - Buy exactly `ZPT25UUK20-B5-A10` (or the rotating `J20`). The flag, its guide and the sensor
    post are built on that buffer's catalog heights. [Certain, CAD] A generic AliExpress buffer
    or a Schmalz or Piab spring plunger has other heights, and the Piab bodies are not M10.
    [Likely]
- **The Z motor's specs.** 1.5–2.0 A, ≤ 4 mH, an 8 mm lead. A 0.4–0.6 A "integrated" motor stalls at
  the speed the firmware runs it. The carry-height sensor stops the run after a stall; it does not
  prevent one.
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
- **The E-stop's second contact block.** A single block switching the 24 V capacitor inrush can
  weld closed without you noticing (WIRING.md §1.3). The AutomationDirect set has three.
- **The 4040 profile type.** It must be 20-series, slot 6, with two slots per face. Amazon's
  "4040 European standard" is often 40-series slot 8 with one slot per face, and the printed mounts
  won't fit it; so are Amazon's "4040 brackets". [Likely]
- **Dowel straightness.** Roll every dowel on a flat table and reject bowed ones. A bowed rod
  narrows the pocket at the top, where the cup lifts a full stack.

## Required tools (not in the machine total)

Most of these are standard in a tech-school shop. The "buy" column is the price if the school
doesn't have one.

| Tool | Used for | Buy price if missing | At school? |
|---|---|---:|---|
| Hand drill (cordless) | The 82 rod holes, drilled in place on the assembled machine (§5B), and the bed bolts | $60–100 | Likely |
| Drill press | The rod-hole guide block, the drop arm's and the jig stub's cross holes | — | Likely |
| **5/16 in brad-point bit, new and sharp, at least 4 1/2 in (115 mm) long** | Rod holes, for the BOM's 5/16 in dowels (8 mm if you buy 8 mm dowels). The depth collar sits 57 mm above the cutting lips, and the chuck needs about 30 mm of shank above the collar [Likely] | $10 | **Buy** |
| **Depth-stop collar, 5/16 in** | All rod holes the same 15 mm deep | $5 | **Buy** |
| Drill guide (Milescraft DrillBlock type) or a drill press with long-table support | Holes square to the bed. The printed `drill_template` sets the position, not the angle. | $15–40 | Likely |
| Metric hex keys, 1.5–10 mm, ball end | All socket screws. The probe board's front M3 screw needs the **2.5 mm ball end**, tilted about 20° (BUILD_GUIDE §7.6). | $15 | Likely |
| Digital calipers, 150 mm | Measuring 5 of your slabs (`dims.py`), dowels, ring OD/ID, camera board holes, the switch levers; setting each switch 0.3 mm past its click (§6.8) | $20 | Likely |
| Ferrule crimper (self-adjusting) | Screw-terminal wire ends | $25 | Maybe |
| JST/Dupont crimper (IWISS SN-28B or SN-2549) | Sensor and GPIO connectors | $25 | Maybe |
| Wire stripper, flush cutters | Wiring; cutting a long switch lever back to 20 mm (BUILD_GUIDE §6.8) | $20 | Likely |
| Multimeter | Wiring checks, sensor voltages, beam receiver level, setting the carry-sensor trip | $30 | Likely |
| Temperature-controlled soldering iron | Diodes, divider resistors, LED ring leads | $30–100 | Likely |
| **Heat-set insert tips** (ruthex set fits 900M/T18 irons; TS100-style tips for a Pinecil) | M5 insert in `awl_adapter`, spares | $10–16 | **Buy** unless the shop has them |
| Fine saw + miter box, or a bandsaw | Cutting 82 dowels to 236 mm | $15 | Likely |
| Junior hacksaw or piercing saw, needle files (one about 1.5 mm thick), a vise | The probe flag and the carry flag (BUILD_GUIDE §7.4a, §7.6); clearing the 1.9 mm flag slot in `head_foot` (a standard 12.7 mm hacksaw blade does not fit it) | $15 | Likely |
| 7.2 mm (or 9/32 in) drill | Only if your left gate post was printed from an older STL with a 6.2 mm laser hole | $3 | Likely |
| Jigsaw | 41 × 41 mm notches in the bed for the uprights (CONTRACT) | $50 | Likely |
| M5/M3 taps + tap handle; **1/8 NPT tap** | Extrusion end taps; reservoir caps | $8 (NPT) | Taps likely; NPT maybe |
| Dial indicator + magnetic base | Beam-twist check (DESIGN.md) | $25 | Likely (machine shop) |
| Heat gun, clamps, square, level, 120/220 sandpaper | General; doming the rod tops | $25 | Likely |
| **Drills and small items** | | | |
| Metric drill bits 1.8, 3.4, 5.2 and 5.5 mm | 1.8: new board holes in the jig's bridge (§1.5); 3.4: M3 clearance holes and the carry flag (§3.4, §7.4a); 5.2: the probe flag (§7.6); 5.5: M5 clearance holes and the cross holes (§3.4, §1.5, §7.5) | $15 | Likely |
| 11/32 in drill | Tap drill for the 1/8 NPT reservoir ports (§8.2) | $6 | Maybe |
| Sharp knife and steel rule | Cutting the pads (§5.5), the PU tube square (§8.2) | $10 | Likely |
| Small spring scale, 0–500 g (or 0–5 N) | Belt tension (§6.6) | $8 | Maybe |
| CA glue (superglue) | The awl pin (§3.4) | $5 | Likely |
| Shims (card, thin wood) or a small lab jack | Raising the slab under the cup in Phase 0B (§1.10) | $0–25 | Likely |
| microSD card reader | Flashing Raspberry Pi OS (§11.1) | $10 | Likely |
| M2 flat washers, about 0.3 mm, a few | The camera-aim shim (§7.7): the M2 kit has screws and nuts only | $3 | **Buy** |

**Tools you will probably have to buy: about $45–50.** That is the brad-point bit, depth collar,
heat-set tips, NPT tap, M2 washers and the spring scale. **If you had to buy every tool new, the
total would be about $2,640** ($2,182 + about $460), so use the school's where you can.

## How the quantities were derived

- **Extrusions.** These are `model.cut_list()` values (`cad/out/cut_list.csv`), plus an optional
  2020 × 600 mm rear brace and, only if you build the optional light roof, two 2020 × ~500 mm
  roof posts:
  - 2040 × 1416 (2)
  - 4040 × 401 (2)
  - 4040 × 1416 (1)
  - 2040 × 340, both ends tapped M5 (1)
  - 2020 × 285 (1)
  - Phase 0 jig: 2020 × 312 (2) and the 2020 × 66 arm stub (1)
  - plus the Z lead screw, cut to 340 mm below the motor face, and two 1 mm aluminium flags: the
    probe flag blank, 24.4 × 55 mm, and the carry flag, 19.9 × 36 mm
- **Rods.** `len(layout.rods())` = 82. Each is 218 mm above the pad + 3 mm pad + 15 mm embedded =
  236 mm, so 12 in (305 mm) stock leaves room to trim. Buy 100 so you can reject bowed ones.
- **Pads.** There are 13 pockets, and each pad is 83 × 138 mm.
- **M3 rail screws.** MGN12 rails have holes at 25 mm pitch: 1300 mm needs 52 and 330 mm needs 13.
  The carriages take 4 × M3 each on a 20 × 20 mm pattern. [Certain] The carry sensor adds 4 × M3×10
  and 2 × M3×8.
- **M5 T-nuts, about 130.** That covers:
  - brackets and joining plates (about 80–90 nuts);
  - 20 for the printed mounts on the extrusions: x_motor_mount 4, x_idler_mount 2, x_bracket 4
    (the spine), z_plate 2 (the drop arm), x_bumper_L 1, z_motor_mount tab 1, carry_sensor_mount 2,
    x_switch_mount 2, z_switch_mount 2.
    The z_motor_mount and z_end_cap screw into the spine's tapped end bores instead;
  - 16 bed bolts;
  - 6 feet (both base rails at each end and at midspan; the OpenBuilds feet bring their own).
- **Wood screws.** station_mount 4, gate posts 4 and the electronics panel.
- **Filament.** `print_list.json` totals 801 cm³ of solid parts in 27 prints from 25 STL files,
  including the Phase 0 jig and its occluder mount, the drill template, two fill gauges, the two
  carry-sensor parts and the two switch mounts. That is about 1020 g of PETG if printed solid, or
  about 720 g at the listed walls and infill. Add a Pi case, electronics trays, cable clips and reprints, and it comes to about
  1.0–1.3 kg, so the list has 2 kg. [Likely]

## Design gaps found while pricing (for the CAD and wiring owners)

These are not BOM problems, but they decide what gets bought.

**Resolved since pricing** (the CAD decisions in CONTRACT.md):
- The MGN12 rails sit on slots: the X rail centre is at Z = 410 on the 4040's upper front slot, and
  the Z rail is in the 2040 spine's right slot, on the cup axis. [Certain, `cad/out/checks.txt`]
- The bed has 41 × 41 mm notches at the two upright positions. [Certain, `model.py`]
- The light roof is optional and left out of the CAD (conditional lines in the CSV).
- The 2020 drop arm is 285 mm with two 5.5 mm cross holes, 19 and 84 mm from its lower end.
- The Z machinery sits above the highest point a held slab can reach, and the lead screw is cut to
  340 mm. Printed end bumpers and a `z_end_cap` are hard stops on both axes. [Certain]
- The mains side has a closed box, the laser is Class 2, the E-stop has two contact blocks, and the
  MOSFET modules and limit switches match WIRING.md.
- The buffer code is `ZPT25UUK20-B5-A10` [Certain, SMC ZP catalog Table 2; Proax lists it], the
  probe flag, its guide and the barb elbow are in the CAD, and the jig posts and arm stub are in
  `cut_list.csv`.
- **The head camera now sees the face-down card window** [Certain, CAD frustum check]: the lens
  sits 5 mm toward the label from the cup axis and the foot was trimmed. Nothing to buy; the
  `camera_bracket` and `phase0_top` STLs changed, so print the current ones.
- **Both LED rings are in the CAD** [Certain, `cad/out/checks.txt`; Likely for the ring sizes]. The
  head ring (modelled 40 × 30 × 5 mm) sits in a 42.8 mm bore with three centring ribs, against a
  33 mm lip, its LED face 1 mm under the lens front, and the barb elbow clears it by 3.75 mm at the
  full 20 mm stroke. The seat takes rings of 39.5–42.5 mm OD (shave the ribs for one over 40). The
  station seat is a 64 mm bore on a shelf that takes a 60 or a 63 mm ring. `station_mount`,
  `camera_bracket`, `phase0_base` and `phase0_top` changed: print the current ones.
- **The fastener margins are closed in the CAD**: the probe board takes M3×16 with a washer under
  the head and under the nut, and every Phase 0 jig wall an M5×10 passes through is 4 mm (one washer
  per screw).
- **The Z stall guard is designed** (carry-height sensor, above).
- **The homing switches have printed mounts** (`x_switch_mount`, `z_switch_mount`) [Certain,
  `cad/out/checks.txt`]: a finger on `x_bracket` and a chamfer on `z_plate` slide across each
  lever and hold it 0.6 mm past its click point to the hard stop. Nothing new to buy but the
  screws above (was open gap 7).

**Still open:**
1. **[Certain, CAD] There are only 18 mm between each rail end and the upright's inner face.** Use
   back-face brackets and flat joining plates on the outer ends (BUILD_GUIDE §4.3).
2. **[Likely] The laser receiver module is a 5 V board.** Divide its output before GPIO 5. It is
   also non-modulated, so room light can hold it HIGH. Test it with the room lights on.
3. **[Likely] Angel-eye LED rings are 12 V parts, sold by OD only.** Measure the ring OD, ID and
   thickness before printing the ring seats. Head: OD 39.5–42.5 mm (42.8 mm bore with ribs), ID
   about 24 mm up to OD − 3 (33 mm lip), 5 mm thick or less (each mm thicker takes 1 mm off the
   3.75 mm barb clearance).
   Station: OD 59–63.5 mm (64 mm bore; some "60 mm" rings are 63 mm). No 40 mm COB listing is live:
   a 40 mm 12-SMD ring that fits is the fallback (check it for glare in Phase 0A).
4. **[Guessing] Some mounting patterns in the CAD are not verified.**
   - The head camera board's hole pattern is assumed to be 32 mm square (the ELP board is 38 × 38 mm),
     and its board-to-lens-front length 20 mm (`HEAD_LENS_PROJ`).
   - The optical endstop boards: the TCST2103 itself is from Vishay's drawing (19 mm flange holes,
     symmetric about the slot) [Certain], but the listing does not name the sensor, and the board's
     header position and component heights are unknown. This now matters twice: the probe and the
     carry-height sensor.
   - Measure these parts before printing `camera_bracket`, `phase0_top`, `head_foot` and
     `carry_sensor_mount`.
5. **[Certain, sourcing; resolved in CAD] The only Class 2 laser found is 7 mm**, so the left gate post's
   barrel hole is now 7.2 mm (the right post keeps 6.2 mm for the receiver).
6. **[Certain, forum report] BTT has shipped Rodents with an old FluidNC build.** Reflash the
   current FluidNC release before loading `firmware/fluidnc/config.yaml`. Also check the Rodent's
   limit and motor connector types (XH or other) before buying crimp housings.
7. **[Guessing] Which lever the homing switch 10-pack has.** The switch mounts are now in the
   CAD (resolved above), drawn for the Omron SS-5GL size with a short hinge lever. A lever that
   ends more than 23 mm from the hinge end must be cut back to 20 mm (BUILD_GUIDE §6.8); a roller
   lever does not fit. The listing was not opened: check the photos, or measure on arrival.

## Main sources

- **Sourcing run, 22 Oct 2026:** every product link in BOM.csv; the per-line notes say which pages
  were opened ([Certain]) and which prices come from search text ([Likely]) or the old estimate.
- **Raspberry Pi 2026 prices:** [Liliputing/Heise/TechSpot reports](https://www.techspot.com/news/111165-raspberry-pi-prices-soar-amid-ai-memory-shortage.html),
  [The Register (Feb 2026)](https://www.theregister.com/2026/02/02/raspberry_pi_ram_shortage_price_hike/)
- **Rodent:** [BIQU product page](https://biqu.equipment/products/bigtreetech-rodent)
- **LRS-150-24:** [TRC Electronics](https://www.trcelectronics.com/products/mean-well-lrs-150-24)
- **Clippard EV-2-24:** [Clippard](https://www.clippard.com/part/EV-2-24)
- **SMC ZPT/ZP codes and prices:** [ZPT25UUK20-B5-A10 at Proax](https://proax.ca/en/product/2087750/smczpt25uuk20b5a10),
  [ZP25UU at automationdistribution](https://automationdistribution.com/zp25uu),
  [SMC USA ZPT (J,K) family page with configurator and CAD](https://www.smcusa.com/products/zpt-u-c-d-b-ut-ct(j-k)-suction-cups-vertical-entry-w-buffer~87420)
- **SMC ZP catalog (stroke table, buffer dimensions):** [RS copy of the ZP catalog](https://docs.rs-online.com/f2e4/A700000013408341.pdf),
  pages 13-11-9 (Table 2) and 13-11-12
- **SMC M-5ALU-4 barb elbow:** [automationdistribution](https://automationdistribution.com/m-5alu-4)
- **TCST2103 drawing:** [Vishay doc 81147](https://www.vishay.com/doc?81147), drawing 6.550-5040.01-4
- **VXB Z motor 3-pack:** [VXB](https://vxb.com/products/3-nema-17-stepper-motor-tr8x8-400mm-t8-lead-screw)
- **XGZP6847A100KPGN:** [Digi-Key](https://www.digikey.com/en/products/detail/cfsensor/XGZP6847A100KPGN/22530765)
- **E-stop set:** [AutomationDirect GCX1131](https://www.automationdirect.com/adc/shopping/catalog/pushbuttons_-z-_switches_-z-_indicators/emergency_stop_pushbuttons/gcx1131)
- **Schmalz HT1:** [Schmalz PFG 25 HT1](https://www.schmalz.com/en-us/10.01.01.11164)
- **HIWIN MGN12 price tier:** [DamenCNC MGNR12](https://www.damencnc.com/en/hiwin-profile-rails-narrow-type-mgnr-12-hm/a1945)
- **Laser receiver behaviour:** [Acxico KY-008 listing](https://woodartsupply.com/products/acxico-2sets-laser-sensor-module-for-arduino-avrky-008-laser-transmitter-laser-receiver-sensor-module-non-modulator-tube)
- **D4184 module notes:** [ProtoSupplies](https://protosupplies.com/product/d4184-mosfet-control-module/)
- **FluidNC on Rodent:** [V1E forum thread](https://forum.v1e.com/t/bigtreetech-rodent-cnc-controller-lr-4/46654)
