# SlabRail bill of materials (October 2026)

The line-by-line list with links is in [`BOM.csv`](BOM.csv). This page has the totals, the order
plan, where to save and where not to, the tools, and the design gaps I found while pricing.

Confidence tags: **[Certain]** = primary source, **[Likely]** = several secondary sources or a
dated listing, **[Guessing]** = estimate.

## Bottom line

- **The full list costs about $1,705 with the 10% allowance.** [Likely ±15%] That is under the
  $2,000 cap but **above the $1,000–1,400 target.**
- **About $1,470 if the school supplies its usual shop stock** (filament, wire, glue, fuses,
  common screws). [Likely]
- **About $1,380 lean:** school stock, plus generic direct-acting valves instead of Clippard,
  plus Home Depot plywood instead of Baltic birch. [Likely]
- **Nothing on the list pushes the total past $2,000 by itself.** What could:
  - buying every tool new (about +$400);
  - the genuine HIWIN rail tier (+$330);
  - a drag-chain-rated USB cable (+$150).
- **No price here is a live checkout price.** [Certain] Product pages could not be loaded from this
  session, so every price comes from search-engine extracts of listings dated 2023 to August 2026.
  - Of the $1,550 subtotal, $976 is [Likely] and $574 is [Guessing].
  - Misumi extrusion prices, the Z motor, both rails and the SMC cup are the least certain items.
    Get the Misumi quote first, because it moves the total the most.

## Order plan

The design says to run the Phase 0 tests before buying any motion parts.

| Order | What | Cost incl. 10% |
|---|---|---|
| **1 — Phase 0** | Pi 5 and accessories, both cameras, LED rings, the complete vacuum system (pump, valves, cup, sensor, ADC), 24 V PSU, MOSFETs, basic wiring, filament, two 2020 jig posts. Rows marked "PHASE 0" in the CSV. | **≈ $820** |
| **2 — Machine** | Extrusions, rails, motors, belt, brackets, fasteners, bed, dowels, roof, Rodent, endstops, laser gate, drag chain, flex cables, e-stop. | **≈ $885** |

**If Phase 0 fails, nothing from order 2 has been spent.** Failing means the cameras can't read
your labels, or the cup marks slabs. [Certain, by construction]

## Totals by category

| Category | Total | Usually at school | Biggest line |
|---|---:|---:|---|
| Frame (extrusion) | $154.00 | — | X beam 4040 × 1416, $42 |
| Motion | $135.00 | $8 | MGN12 1300 rail + block, $48 |
| Fasteners & brackets | $177.00 | $39 | 4040 corner brackets, $18 |
| Bed, rods & light roof | $172.00 | $32 | Baltic birch 12 × 60 in, $56 |
| Controller & compute | $206.00 | — | Raspberry Pi 5 4 GB, $110 |
| Cameras & lighting | $127.50 | — | ELP 8 MP head camera, $66 |
| Vacuum & gripper | $234.32 | $10 | 2 × Clippard EV-2-24 valves, $72 |
| Sensors | $53.00 | — | 2 × XGZP6847A, $16 |
| Power & switching | $119.51 | $28 | Mean Well LRS-150-24, $21.51 |
| Wiring & cable management | $136.00 | $60 | 8-core flex cable, $18 |
| Printed parts (filament) | $36.00 | $36 | 2 kg PETG |
| **Subtotal** | **$1,550.33** | **$213** | |
| Spares, shipping, duties (10%) | $155.03 | | |
| **Grand total** | **$1,705.36** | | |
| Minus school stock (+ its 10%) | −$234 | | **≈ $1,471** |
| Lean swaps (below), with school stock | | | **≈ $1,383** |

**Conditional lines are in the CSV with qty 0 and are not in the total.** Buy them only if a test
fails:
- Schmalz HT1 cups, 2 × $18. Buy if the urethane cup marks slabs.
- Generic buffer backup, $14. Buy if the SMC lead time is long.
- Stepper extension cable, $8. Buy if the X motor's lead is too short.

**The 10% allowance may be too low.** [Likely] The US removed the de minimis duty exemption in 2025,
so AliExpress parcels now carry duty. Raise the allowance to 15% (about +$78) if most small parts
come from AliExpress.

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

The 10% allowance ($155) is bigger than any single part.

## Where to save

- **Valves.** Generic 24 V direct-acting 2/2 NC micro valves cost about $6 each instead of $36,
  saving about $60.
  - They work if they are truly direct-acting. Test them in Phase 0: hold −60 kPa for 60 s with
    the pump off and watch the sensor.
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
  Count first: about 122 M5 T-nuts and 65 M3 rail screws are needed.
- **Pi 5 2 GB.** It would probably run the software. [Guessing] It saves maybe $30–40, but the
  contract specifies 4 GB, so test memory use in `sim` before switching.

## Where NOT to save

- **The cup and buffer.** Buy a genuine urethane pad and spare pads. The cup is the only part that
  touches your slabs. A cheap silicone cup can leave silicone residue rings on glossy plastic.
  [Likely] Run the 24 h marking test on a junk slab before any real inventory goes in.
- **Valve type.** Never use pilot-operated, "servo-assisted" or diaphragm water valves. They need
  a pressure difference of 0.2–0.5 bar to work, so they won't seal or open reliably on vacuum.
  [Likely] The listing must say "direct acting" and give a vacuum rating, or a "0 bar" minimum.
- **The MOSFET modules.** Use AOD4184-type modules that accept 3.3 V logic. IRF520 modules barely
  switch from a 3.3 V Pi pin. [Likely] Add a flyback diode across the pump and each valve coil.
- **The 24 V PSU and mains side.** Buy a Mean Well, not an unbranded "24 V 10 A" brick. Have an
  instructor check the IEC inlet, fuse and earth wiring before first power-up.
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
| Jigsaw | 40 × 40 mm notches in the bed for the uprights (see design gaps) | $50 | Likely |
| M5/M3 taps + tap handle; **1/8 NPT tap** | Extrusion end taps; reservoir caps | $8 (NPT) | Taps likely; NPT maybe |
| Dial indicator + magnetic base | Beam-twist check (DESIGN.md) | $25 | Likely (machine shop) |
| Heat gun, clamps, square, level, 120/220 sandpaper | General; doming the rod tops | $25 | Likely |

**Tools you will probably have to buy: about $35–40.** That is the brad-point bit, depth collar,
heat-set tips and NPT tap. **If you had to buy every tool new, the total would pass $2,000**
($1,705 + about $400), so use the school's.

## How the quantities were derived

- **Extrusions.** These are `model.cut_list()` values, plus two 2020 × 312 mm posts for the
  Phase 0 jig and an optional 2020 × 600 mm rear brace:
  - 2040 × 1416 (2)
  - 4040 × 401 (2)
  - 4040 × 1416 (1)
  - 2040 × 340 (1)
  - 2020 × 224 (1)
- **Rods.** `len(layout.rods())` = 82. Each is 218 mm above the pad + 3 mm pad + 15 mm embedded =
  236 mm, so 300 mm stock leaves room to trim. Buy 100 so you can reject bowed ones.
- **Pads.** There are 13 pockets, and each pad is 83 × 138 mm.
- **M3 rail screws.** MGN12 rails have holes at 25 mm pitch: 1300 mm needs 52 and 330 mm needs 13.
  The carriages take 4 × M3 each on a 20 × 20 mm pattern. [Certain]
- **M5 T-nuts, about 122.** That covers:
  - brackets and joining plates (about 80–90 nuts);
  - 14 for the printed mounts on the extrusions: x_motor_mount 4, x_idler_mount 2, x_bracket 4,
    z_motor_mount 2, z_plate 2;
  - 16 bed bolts;
  - 4 feet.
- **Wood screws.** station_mount 4, gate posts 4, roof posts and the electronics panel.
- **Filament.** `printed_catalog()` totals 638 cm³ of solid parts, including the Phase 0 jig,
  the drill template and two fill gauges. That is 810 g of PETG if printed solid, or about 570 g
  at the listed walls and infill. Add a Pi case, electronics trays, cable clips and reprints, and
  it comes to about 1.0–1.3 kg, so the list has 2 kg. [Likely]

## Design gaps found while pricing (for the CAD and wiring owners)

These are not BOM problems, but they decide what gets bought.

1. **[Certain, from CAD and profile geometry] Both MGN12 rails are centred on a 40 mm face, where
   a 20-series profile has no slot.**
   - The 4040 X beam has slots at Z = 390 and 410, and the rail is centred at Z = 400.
   - The 2040 Z spine has slots at cup_x ± 10, and the rail is centred at cup_x.
   - So the M3 T-nuts in this BOM can't reach the rail holes.
   - Fixes:
     - (a) Move each rail 10 mm onto a slot. This is the cheapest fix and needs only CAD changes.
     - (b) Drill and tap 65 M3 holes into the thin face wall. This is weak and slow.
2. **[Certain, CAD] The bed plywood overlaps the upright footprints.** The uprights stand on the
   back base rail inside the bed outline (X −68…−28 and 1308…1348, Y 107…147). Each back corner of
   the bed needs a 40 × 40 mm notch, and the base joint brackets must sit above the plywood.
3. **[Certain, CAD] There are only 18 mm between each rail end and the upright's inner face.** The
   rail starts at X = −10 and ends at 1290. A 40 mm front-face corner bracket won't fit there. Use
   back-face brackets and flat joining plates on the outer ends.
4. **[Certain, CAD] The light roof (Z = 690) has no supports.** The BOM adds four 3/4 in dowel
   posts, which the CAD needs to model.
5. **[Certain, CAD] The M5 cross-bolts in `head_foot` and `camera_bracket` go through the 2020 drop
   arm.** The arm needs 5.5 mm holes drilled through it.
6. **[Likely] The laser receiver module is a 5 V board.** Divide its output before GPIO 5. It is
   also non-modulated, so room light can hold it HIGH. Test it under the roof.
7. **[Likely] Angel-eye LED rings are 12 V parts.** The BOM adds a 24→12 V buck. Measure the ring
   OD and ID before printing the ring seats (head 46–56 mm, station 52–60 mm).
8. **[Guessing] Some mounting patterns in the CAD are not verified.**
   - The head camera board's hole pattern is assumed to be 32 mm square.
   - The optical endstop's hole spacing is assumed to be 19 mm.
   - Measure both parts before printing `camera_bracket` and `head_foot`.
9. **[Likely] The SMC ZPT buffer has an M5 female port on top of its rod, and the rod rises up to
   25 mm on contact.** The vacuum tube needs slack. The optical probe flag must clamp to the rod
   below the fitting.
10. **[Certain, forum report] BTT has shipped Rodents with an old FluidNC build.** Reflash the
    current FluidNC release before loading `firmware/fluidnc/config.yaml`. Also check the Rodent's
    connector types (XH or screw terminal) before buying crimp housings.
11. **The Phase 0 jig posts (2 × 2020 × 312 mm) are not in `cut_list()`.**

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
