The BOM's cup code is wrong, and it is not a search problem: SMC sells no 25 mm buffer stroke on 25 mm pads. Order **SMC ZPT25UUK20-B5-A10**, which has a 20 mm stroke. Three other findings matter more than any upgrade.
- The real buffer is probably taller than the CAD part, and it may hit the head lens.
- The BOM's fallback cup (Schmalz HT1) probably does not fit the SMC buffer.
- A closed-loop Z motor is not a drop-in on the Rodent.

**Limits of this research.** [Certain] WebFetch failed on every host (DNS "ENOTFOUND", Wikipedia included), and curl got 403 from the proxy. Every fact below comes from search-engine extracts, not from a loaded page. The extracts sometimes contradicted each other, and I note where. I saw no live price and no stock check.

---

## 1. Cup and spring buffer

### 1a. The correct SMC code

- [Likely] The code pattern is: ZPT, pad diameter, pad shape (U = flat), material (U = urethane), J/K, stroke, port, thread.
  - [Certain] K = non-rotating and J = rotating ([Rubix listing "K (Non-Rotating)"](https://uk.rubix.com/en/zpt-vacuum-pad/p-G1324038032)).
  - [Certain] B5 = M5×0.8 female port on top; A10 = M10×1 male body thread.
  - [Certain] SMC's ZP25UU is the matching replacement pad (25 mm flat, urethane), already in the BOM.
- [Likely] For ø10–32 pads, buffer strokes are 10, 20, 30, 40 and 50 mm only ([SMC ZP catalogue PDF](https://www.smcpneumatics.com/metric/vacuum/ZP_Series_Vacuum_Pads.pdf), [SMC vertical-entry PDF](https://content2.smcetech.com/pdf/ZP_ZP2AdapterandCupVertical.pdf)).
  - [Likely] A 25 mm stroke exists only on small pads, for example ZPT06UNJ25-B5-A8 on RS. That is probably why "K25" looked plausible.
- **Exact code: `ZPT25UUK20-B5-A10`** (25 mm flat urethane pad, non-rotating buffer, 20 mm stroke, M5 female vertical port, M10×1 body).
  - [Likely] It exists. A Proax page for ZPT25UUJ10-06-A10 lists ZPT25UUK10-, K20- and K30-B5-A10 as related products ([Proax](https://proax.ca/en/product/2087744/smczpt25uuj1006a10)).
  - [Likely] One search extract says SMC's US product index also lists K20-06 and K40-B5. I could not confirm that independently.
  - [Certain] I found no product page with this exact code.
- **Why K20, not K30 or K10:**
  - [Certain, `layout.check`] K10 fails the check, because `PROBE_WINDOW` (12 mm) must be shorter than the stroke.
  - [Certain, arithmetic] K20 passes. The software uses at most about 14 mm (2 mm trip plus 12 mm window). The buffer bottoms on the bare pad at c = −20, so the −14 hard stop still leaves 6 mm.
  - [Likely] K30 adds body length, and length is the problem in 1d.

### 1b. Price, lead time and URLs

- **Where to order:**
  - [Certain] SMC USA's family page, which has the configurator and a free 3D CAD download: [smcusa.com ZPT (J,K) w/buffer](https://www.smcusa.com/products/zpt-u-c-d-b-ut-ct)(j-k-suction-cups-vertical-entry-w-buffer~87420).
  - [Guessing] Probable direct URLs, built from patterns other codes on these sites use (none of them loaded):
    - `https://us.misumi-ec.com/vona2/detail/221006500657/?HissuCode=ZPT25UUK20-B5-A10`
    - `https://www.smcpneumatics.com/ZPT25UUK20-B5-A10.html`
    - `https://automationdistribution.com/zpt25uuk20-b5-a10`
- **Price:** [Likely] about $35–50 each. I found no price for this code; these are its siblings:
  - [ZPT25UFK20-N6-A10](https://automationdistribution.com/zpt25ufk20-n6-a10): $37.10, "factory stock" (FKM, non-rotating, 20 mm).
  - ZPT25CSJ20-B5-A10: $27.80 with 0 in stock ([SMC index page](https://www.smcpneumatics.com/prodindex_smc/smc_product_index80.html)).
  - One extract said ZPT20UUK20-B5-A10 costs $44; another found no such listing.
- **Lead time:** unknown for this code.
  - [Likely] Misumi US showed **53 days to ship** for a sibling, ZPT16CSJ10-B5-A10 at $21.76 ([Misumi](https://us.misumi-ec.com/vona2/detail/221006500657/?HissuCode=ZPT16CSJ10-B5-A10)).
  - [Likely] An RS UK sibling showed a ship date of 9 Nov 2026.
  - Plan for 2–8 weeks, and get the lead time in writing.

### 1c. Alternatives

- **Schmalz FSTIm M5-IG M5-IG A 20 VG-IN, part 10.01.02.01483** ([Schmalz](https://www.schmalz.com/en-at/vacuum-technology-for-automation/vacuum-components/mounting-elements/spring-plungers/spring-plungers-fstim-307028/10.01.02.01483), [TME](https://www.tme.eu/en/details/smz.10.01.02.01483/vacuum-products/schmalz/fstim-m5-ig-m5-ig-a-20-vg-in/)).
  - [Certain, per extract] Specs:
    - M10×1 male housing, 20 mm stroke, anti-rotation guard, M5 female at both ends;
    - H 79.4 mm, H2 29 mm, LG3 41 mm, SW1 14 mm, SW2 8 mm;
    - spring preload 0.5 N, rate 0.05 N/mm.
  - [Certain] I found no price: TME says "contact us". A non-VG sibling showed $31.44 on Octopart, and that listing is stale.
  - **Downsides:**
    - [Likely] It needs a cup with an M5 male thread. Schmalz's 25 mm HT1 cups are listed with G1/8 threads.
    - [Guessing] The 0.5 N preload may not push the rod back against the tube and fitting. A flag that stays near the slot leads to ALARM:4 stops.
- **Piab** ([LC16-M1820, 0124952](https://www.piab.com/ko-kr/suction-cups-and-soft-grippers/accessories-for-suction-cups/mounting-elements/0124952); [KSPH, 02.08.901](https://www.piab.com/suction-cups-and-soft-grippers/accessories-for-suction-cups/level-compensators/0208901)):
  - [Certain] LC16-M1820 has a 20 mm stroke and a "non-rotational design", with G1/8 connections. KSPH is non-rotating with 25, 50 or 75 mm strokes and G1/8.
  - [Guessing] Neither body is M10, so `head_foot`'s 10.4 mm hole would have to change.
- **AliExpress / Amazon:** [Certain] I found no listing that states anti-rotation, an M10 body and a 20–25 mm stroke. Don't buy one as the primary part.
- **Safest to order: two of the SMC ZPT25UUK20-B5-A10.**
  - It is one part number that matches the CAD's M10 foot, the M5 top port, the urethane plan and the ZP25UU spare pads.
  - Have the distributor confirm the code in writing, or check that SMC's configurator accepts it. The configurator also gives you the STEP file.
- **The BOM's HT1 fallback probably doesn't fit.** [Likely] The 25 mm HT1 cups I found (SFF 25 HT1-60 G1/8-AG, FSG 25 HT1-60 G1/8-IG) are G1/8. The M5-AG HT1 cup I found is only 12 mm. The BOM line ("~25 mm, M5") is unverified. Find the cup-to-buffer adapter before Phase 0B, not after the urethane cup fails.

### 1d. Real buffer geometry, and what it means for the CAD

**What I found:**
- [Likely] SMC's spring force for ø10–32 buffers is 1.0 N at 0 stroke and 3.0 N at full stroke ([SMC ZP catalogue](https://ca01.smcworld.com/catalog/VacuumPad-en/mpv/VPad-p026-130-ZP_en/data/VPad-p026-130-ZP_en.pdf)).
  - On a 20 mm stroke that is about 1.2 N at the 2 mm trip, 2.2 N at 12 mm and 3.0 N bottomed.
  - DESIGN.md §4 says 1.4 / 3.4 / 6.0 N.
- [Likely] The bare buffer, ZPB2K20-B5, is listed as "non-rotating, 89 mm" high, 20 mm stroke, A10 thread, M5×0.8 female vacuum end ([Zoro](https://www.zoro.com/smc-vacuum-buffer-non-rotating-89mm-zpb2k20-b5/i/G4872061/), [Octopart](https://octopart.com/part/smc/ZPB2K20-B5)).
  - [Guessing] Its pad end is listed as "M5×1.0". That pitch looks wrong; check it on arrival. `awl_adapter` assumes an M5 male stud there.
- [Guessing] The SMC table row for ø20–32 "…20-B5-A10" reads 44.5 / 108.5 / 45 (an older edition reads 42.5 / 106.5 / 43 / 107). The column labels were lost in the extract.
  - My reading: about 108 mm overall (pad lip to rod top at rest) and about 44 mm body. That is consistent with an 89 mm buffer plus about 19 mm of pad and adapter.
- [Certain] I did not find the rod diameter, the M10 thread length, the nut size, or the anti-rotation play.

**Consequences for the CAD owner:**
1. [Certain, code] Change `BUFFER_STROKE` from 25 to 20 in `cad/layout.py:65` and `software/slabscan/simworld.py:26`.
   - `checks.py:346` then reports 6.0 mm against its 2.0 mm minimum.
   - Also update the "25 mm" text in `model.py:492`, BUILD_GUIDE §7.5 step 6 and the WIRING tube-slack note.
2. **[Guessing, needs the STEP file] The fitting may hit the lens.**
   - The lens front sits 140 mm above the cup face, on the cup axis. The CAD's buffer ends at c + 97.
   - If the real rod top is about 108 mm up, an M5 push fitting (about 13–19 mm tall, Guessing) reaches about 122–128 mm at rest, 134–140 at 12 mm compression and 142–148 at full stroke. That is at or into the lens.
   - [Certain, DESIGN §6] `checks.py` does not model the rising rod, the fitting, the tube or the flag.
   - Download SMC's STEP, add an elbow fitting and the tube, sweep the rod through 20 mm, and check it against `camera_bracket`, the ring and the lens.
3. [Certain, BUILD_GUIDE §7.6] The flag design (a washer tab clamped under the M5 fitting on the rod top) still works, and the rod diameter doesn't matter for it.
   - [Guessing] SMC publishes no anti-rotation play that I could find. Check the flag's clearance in the 3.1 mm slot by hand over the full stroke.
4. Phase 0A's occluder should be the real buffer with its fitting, not an M10 bolt dummy.

---

## 2. Upgrades for $2,500–3,000, ranked by value per dollar

**First, Z stalls get free fixes before any purchase:**
- [Certain, config] Z runs at 0.8 A, which is 40–53% of a 1.5–2.0 A motor. BUILD_GUIDE §7.8 allows 50–70%.
- If the 100-lift test fails, try 3000 mm/min and 1.0–1.2 A, and keep the motor under 50 °C.
- [Guessing, needs CAD, wiring and software work, $0 in parts] A cheaper stall detector than closed loop: mount the spare TCST2103 from the 3-pack on the Z spine. A flag on `z_plate` must sit in its slot before every traverse. A stall while lifting then becomes a stop instead of a held slab dragged across the rods.

| Upgrade | Cost | Failure it removes | Evidence | Verdict |
|---|---|---|---|---|
| Second ZPT25UUK20-B5-A10 | ~$40–50 | One commissioning crash (bent rod, torn flag mount) stops the build for weeks | [Likely] 53-day sibling lead time; no stock seen for this code | **Buy now**, with order 1b |
| 2 spare MGN12H blocks, same seller as the rails | ~$16–24 | Balls lost at install (BUILD_GUIDE §6.1), then weeks of waiting for a new block | [Likely] clone and genuine HIWIN parts don't mix, ball sizes differ ([Duet3D forum](https://forum.duet3d.com/post/92856)) | **Buy now**, in the same order |
| E-stop with branded, datasheet-rated blocks (e.g. Schneider ZBE102) | +$25–45 over the $17 box | Turns WIRING open risk 3 (unknown DC rating) into a datasheet number | [Likely] ZBE102 is rated 10 A thermal ([Steiner](https://steinerelectric.com/Catalog/MotorControlsCampaign/PilotDevices/Telemecanique-Harmony-XB4-XB5-Contact-Block22-mm1NC600-VAC-10-A-Contact-RatingSilver-Alloy-ContactBlack-Red-33094)). The older ZB2BE102 lists 65 W DC-13 at 24 V, about 2.7 A ([Steiner](https://steinerelectric.com/Product/Schneider-Electric-Harmony-ZB2BE102-ZB2-Slow-Break-Contact-Block1-Poles1NC10-A-at-600-VACFor-Use-With-XACA-XAPS2-XB4-XB5-Head-Signaling-Units-32602)). Still not 5 A, so keep two blocks and the monthly check | **Buy now** (cheap). It narrows the weld risk but doesn't remove it |
| Tools: multimeter, calipers, JST and ferrule crimpers, dial indicator | ~$100–125 | Skipped §14 checks, §7.6 trip measurement, §6.7 twist check; intermittent hand-crimped signals | [Likely] general practice | **Buy now only** what you can't borrow for the days you build at home |
| Genuine HIWIN rail tier | +$330–400 | Clone rail binding, which leads to an undetected X stall | [Likely] X safety factor about 8 and ±1.85 mm pocket play; [Certain] DamenCNC €245/m ([link](https://www.damencnc.com/en/hiwin-profile-rails-narrow-type-mgnr-12-hm/a1945)) | **Only if** the §6.1 roll test (notches or binding after cleaning and greasing) or 13.1 fails. Replace rail and block as a set |
| Drag-chain USB cable | +$100–170 | WIRING risk 4: camera dropouts at about 4 m | [Likely] a dropout is a safe stop; the software keeps holding the slab | **Only if** dropouts show in 13.1, 13.2 or later runs; the $11 spare covers the first one |
| Z motor with a datasheet torque curve | +$15–40 | Z stall margin (FIRMWARE open issue 5) | [Likely] safety factor 2–4 | **Only if** §7.8's lift test still fails after the free fixes |
| Counterweight or constant-force spring | ~$15–30 | Z drops when unpowered (FIRMWARE open issue 4) | [Guessing] detent torque should hold | **Only if** the §7.8 hold test creeps |
| VXB pump | +$38 | A weak generic pump (a [Guessing] BOM line) | none | **Only if** the §8.3 reservoir or seal test fails |
| Better head camera | ~$50–100 | Nothing named | [Certain, synthetic labels only] reads at ≤ 0.14 mm/px, and the ELP gives 0.055 mm/px | **Only if** the Phase 0A gate fails on sharpness, not on glare or payload |
| Closed-loop or encoder NEMA17 for Z | $33–42 (BTT S42C) + $100–200 for a new controller | A stall while lifting | [Likely] the Rodent has only on-board TMC2160s and no documented step/dir header ([BIQU](https://biqu.equipment/products/bigtreetech-rodent)). [Likely] FluidNC uses StallGuard for homing only ([V1E forum](https://forum.v1e.com/t/catching-missed-steps-and-stopping/49497?page=2)). [Guessing] an S42C in step mode doesn't report a stall back to FluidNC | **Skip**. The free fixes plus the carry-height sensor cover it |
| Spare Rodent | $56–70 | Board death | [Certain] the Y/E driver sockets are the built-in spare; a dead board is a safe stop | **Skip**, but buy the one you need early (sold out at BIQU US) |
| Buying junk slabs | $150–400 | — | They buy hundreds of slabs a week | **Skip**; use the lowest-value stock |

**Budget effect.** [Guessing, arithmetic]
- The buy-now items cost $115–230 with the 15% allowance. The planned total becomes about $2,020–2,135, and the BOM's worst case about $2,285–2,400.
- If every conditional upgrade triggers at once, the total reaches about $3,100–3,300. That many failed tests would mean the design needs rethinking, not more parts.

**I disagree with the reflex upgrade.** The genuine HIWIN rail and the closed-loop Z don't remove a failure that the tests or free fixes can't catch first. Here's what I'd do instead: put the money into two cups and spares on the critical path, and spend the rest only when a named test fails. The risk in buying them now is $400–600 spent while the real single points of failure stay open: the cup's lead time, the possible lens clash and the HT1 fit.