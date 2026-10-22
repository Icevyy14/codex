# Research summary

Confidence tags: **[Certain]** = primary source, **[Likely]** = strong inference or several
secondary sources, **[Guessing]** = filling a gap. Research date: October 2026. Many sites
blocked direct page fetches, so most facts come from search-engine extracts of the cited pages.

## 1. Does this machine already exist?

**No.** [Likely] No product at any price takes 200–300 graded slabs, feeds them itself, and
returns cert numbers.

- **Raw-card sorters are built for raw cards only.** TCGplayer Roca Sorter/Sifter, PhyzBatch,
  SortSwift, CardMill and the open-source mault all exclude slabs. Roca's FAQ says no toploaders,
  and PhyzBatch says unsleeved cards only. [Certain]
- **Sheet-fed scanners don't take slabs.** Ricoh/Fujitsu advises against feeding slabs, and Card
  Dealer Pro lists the fi-8170 as "Slabs: No". [Certain]
- **Every slab-aware tool needs a person to present slabs one at a time or lay them out for a
  photo.** This covers the PSA app, Courtyard, CollX, Kronozio, Card Ladder, Card Dealer Pro,
  Misprint and Slabox. [Certain]
- **The closest mechanical precedent is graded-slab vending machines.** VMFS advertises "elevator
  delivery". That proves one-slab-at-a-time handling can be built, but it isn't a scanner. [Likely]

### The no-build option, about $350–$650

1. Buy a hands-free 2D presentation scanner: Zebra DS9308 (about $320–440) or Honeywell Genesis XP
   7680g. [Certain] Get a 2D imager, not a laser scanner. PSA's front barcode is reportedly ITF, and
   other graders use QR. [Likely]
2. Configure it to send Enter after each scan.
3. Scan into a spreadsheet, or into Card Dealer Pro's "Search Cert Numbers" field.
4. Realistic speed is 20–30 slabs/min, so 250 slabs is about 8–13 minutes. [Likely] Handling is the
   bottleneck, not the scanner.

**What the machine buys you**
- Those 10–15 minutes per 250 slabs, plus a front and back photo of every slab.
- The photos matter. Fake labels reuse real cert numbers, and swapped-card slabs still pass a cert
  check. [Likely]

## 2. PSA slab physical facts (design inputs)

| Item | Value | Confidence |
|---|---|---|
| Outer size | 80.3 W × 135.5 H × 6.25–6.9 T mm. PSA published 80.3 × 135.1 × 6.86 for its "thinner holder for thicker cards". The 2024 holder has an "identical exterior". | Certain/Likely |
| Design max | 82.6 × 136.5 × 7.0 mm (PSA). CGC 7.5 T, BGS/SGC 8.5 T, PSA thick 10.25 T. | Likely |
| Mass | 42–45 g (old holder), 50–60 g (2024+ holder). Design max 65 g. | Likely |
| Surface | Flat, glossy, **no stacking ridges** (slabs slide on each other). Scuffs easily. Edges smooth and sonically welded. Corners chip on impact. | Certain/Likely |
| Label | About 70 × 20 mm at the top of the front, above the card window. | Likely |
| Front code | 1D barcode, reportedly **Interleaved 2 of 5**. It encodes only the cert number. | Likely |
| Back code | Since Dec 2015: second barcode + cert number on the label back. Since June 2017: **QR code** → `psacard.com/cert/<n>`. | Certain |
| Cert format | 8 digits until about Nov 2024, 9 digits since. 2026 certs are about 100M–160M. | Likely |

Consequences for the design:
- **300 slabs = about 2 m of plastic and 15–18 kg.** No single stack can hold them.
- **No slab may be slid out from under a loaded stack.** Face-on-face sliding under load is the main
  scuff mechanism.
- **ITF has an even digit count**, so a 9-digit cert is printed zero-padded. The software strips
  leading zeros before comparing reads.
- **ITF can "short read"**, so a lone ITF read is never trusted without a second agreeing read.

## 3. Cert → card details (optional)

- **Endpoint:** `GET https://api.psacard.com/publicapi/cert/GetByCertNumber/{cert}` with an
  `Authorization: bearer <token>` header. [Certain, from the Swagger spec]
- **Quota:** documented as **100 calls/day** on free accounts. [Certain]
- **Approval gate:** since about July 2026, several developers report valid tokens refused with
  `403 "Access to this API is limited to approved customers"`. The fix is to email
  collectors-apis@collectors.com. [Certain that it happened, Likely general]
- **Bulk alternatives:** Card Hedge API (1,000+ cert lookups/day, 100 per call, from about
  $49/mo). [Likely] Card Dealer Pro's paste-a-list-of-certs import. [Certain]
- **The machine never needs the network.** The cert list comes straight from the barcodes.
  `tools/enrich.py` is a separate, resumable, quota-metered step.
