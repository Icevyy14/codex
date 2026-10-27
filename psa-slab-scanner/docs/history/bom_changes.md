# BOM changes during design

How the bill of materials changed from one design round to the next, moved here from
[BOM.md](../BOM.md) on 27 Oct 2026. **Historical:** the current parts, prices and totals are in
[BOM.md](../BOM.md) and [BOM.csv](../BOM.csv).

Summary: round 5 did not change the total. In round 4 two lines moved between orders and the
confidence tags were aligned; in round 3 the list went up $209 ($182 of parts plus the allowance),
almost all of it real product-page prices replacing estimates. The sourcing data behind round 3 is
[sourcing/links.json](sourcing/links.json).

## Round 5: home-switch mounts ($0.00)

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

## Round 4 ($0.00)

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

## Round 3 (+$182.08, +$209.39 with the allowance)

- **Links and prices from a sourcing run** (22 Oct 2026), spot-checked line by line. Every line
  in the total now carries a product link except the six listed in BOM.md's bottom line. Where the link is [Likely] or
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

## Earlier rounds (+$266 in all)

The second SMC cup and buffer, the M5 barb
elbows, a spare rail block and the jig's arm stub (+$60), and +$112 of parts the first review found
the design needs (a closed mains box, a Class 2 laser, a second E-stop contact block, a hand vacuum
pump, a 12 V adapter, separate head and station LED rings, more screw sizes, M2 standoffs, set
screws), plus the allowance going from 10% to 15% (+$94).
