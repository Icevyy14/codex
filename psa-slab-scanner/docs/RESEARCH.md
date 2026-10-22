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
   7680g. [Certain] Get a 2D imager, not a laser scanner. PSA fronts carry an ITF or Code128
   barcode, and PSA and CGC backs a QR (§4). [Certain, real labels]
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
| Front code | 1D barcode with only the cert number: **ITF** (always 8 digits) on 2016-and-older and 2017+ "lighthouse" labels, **Code128** on current labels. | Certain, real labels (§4) |
| Back code | 2016 labels: ITF only. 2017+ lighthouse: **QR** `http://psacard.com/cert/<n>` + ITF. Current labels: **QR** `https://www.psacard.com/cert/<n>/` + Code128. Before 2016: none. | Certain, real labels (§4) |
| Cert format | 8 digits until about Nov 2024, 9 digits since. 2026 certs are about 100M–160M. | Likely |

Consequences for the design:
- **300 slabs = about 2 m of plastic and 15–18 kg.** No single stack can hold them.
- **No slab may be slid out from under a loaded stack.** Face-on-face sliding under load is the main
  scuff mechanism.
- **The ITF is always the cert zero-padded to 8 digits; 9-digit certs never use ITF** (they use
  Code128). The software strips leading zeros before comparing reads and treats an ITF of any other
  length as a misread. [Certain, real labels]
- **ITF can "short read"** (a glare-cut `289412` was seen), so a lone 1D read is never trusted
  without a second agreeing source.

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

## 4. Real label formats (verified on public scans, Oct 2026)

**What was looked at.** [Certain] 171 images of graded Pokémon slabs, listed in a local index (not
in the repository; no image was copied into it). 128 of them are "good": a real Pokémon slab at
800 px or more. They form 64 slabs, each with a front and a back image:
- PSA 31: 10 current labels, 11 2017+ "lighthouse" labels, 3 from 2016, 7 from before 2016;
- CGC 31: 19 2023+ standard, 5 Pristine gold, 5 2020–23 "OG" blue, 2 Certified Authentic;
- 1 BGS and 1 SGC;
- 36 English and 28 Japanese cards.

The good images are 116 studio scans and 12 seller images, from **fanaticscollect.com** (116) and
**myslabs.com** (12). The other 43 images (phone photos, PSA and CGC guide pages, press images,
renders and mock-ups) were used only to collect more payload strings, from **cgccards.com**,
**cgcgrading.com** (guides and news), **allvintagecards.com**, **forums.collectors.com** and
**legitapp.com**. Every code was decoded with the machine's own decoder (zxing-cpp) and parser.

**What each label carries** [Certain for this set; the payload strings are in
`software/tests/test_real_payloads.py`]:

| Label | Back label | Front label |
|---|---|---|
| PSA current (9-digit certs, some 8) | QR `https://www.psacard.com/cert/<n>/` + Code128 `<n>` | Code128 `<n>` |
| PSA 2017+ lighthouse (8-digit) | QR `http://psacard.com/cert/<n>` (some the https form) + ITF | ITF |
| PSA 2016 | ITF only | ITF |
| PSA before 2016 | no code | ITF |
| CGC 2023+ (10 digits; one 13-digit cert, 140 + 10) | QR `https://www.cgccards.com/certlookup/<n>/<grade>/` (any case, slash optional) | short-bar Code128 `<n>` |
| CGC 2020–23 OG | QR on `cgccomics.com/certlookup/<n>/<grade>` + Code128 of 26–28 digits whose last 10 are the cert | no code |
| CGC Certified Authentic | no code | QR `…/certlookup/<n>/0_0/` + Code128 `<n>` |
| BGS, SGC | no code | no code (the printed cert only) |

- **Every one of the 54 QR payloads with a cert agreed with the printed cert.** [Certain]
- **The ITF is the cert zero-padded to 8 digits.** All 48 ITF payloads were 8 digits, including
  three 7-digit certs on guide photos. 9-digit certs never used ITF. [Certain for the set;
  Likely in general: a reholdered 7-digit cert could sit on a QR + ITF label]
- **CGC 2023+ backs never carried a Code128** (0 of 26) and **graded CGC fronts never a QR** (0 of
  26). OG fronts carried no code (0 of 10). [Certain for the set, Likely in general]
- **Grade `0_0` was on both Authentic fronts**, and their backs decoded nothing. One official CGC
  render of a 2023+ back also shows a `0_0` QR (a placeholder cert), so "0_0 = front" is [Likely],
  not certain; calling a slab face-up by mistake only stops the run.
- **A CGC QR without a cert** (`…/certlookup/`, `cgccomics.com/verify`) appeared only on press
  images and mock-ups of back labels [Likely]: a hint, not proof.

**What a code seen from above proves about the slab's side** (the machine's face-down rule uses
only the [Certain] rows): a PSA QR, a graded CGC QR and the CGC 26–28-digit barcode are printed
only on back labels (face-down); a CGC `0_0` QR and a CGC 10- or 13-digit Code128 only on front
labels (face-up); a PSA ITF or Code128 is on both, so it proves nothing. Applied to these images:
50 of 64 backs proven face-down, 22–24 of 64 fronts proven face-up, 0 false proofs either way; the
14 backs left unproven are exactly the slabs with no back-label code. [Certain]

**Failure modes seen on real labels** [Certain]:
- **A phantom Code128:** zxing-cpp returned `09435764` as a thin band inside the real `27435764` at
  full resolution only (absent at 10 other scales from 0.5× to 2×).
- **A glare-truncated ITF:** `289412` read from `28941258`.
- **A silent wrong cert from the old parser:** its CGC rule cut the 13-digit cert to 12 digits and
  called it `ok`; nothing else on the slab contradicted it.
- **OCR misreads:** a first digit 5 read as 9, other digit runs on the label or the card, a BGS
  `0019865140` read as `0079865140`. OCR is never the only evidence.
- **Phone photos through the plastic lost the QR** on both lighthouse backs tried (ITF only): the
  closest thing here to the machine's camera, and the case where the face-down proof fails.
- **Tesseract timeouts came from OpenMP threads:** on a loaded 4-CPU computer every OCR call with
  the default threads timed out at 30 s; with `OMP_THREAD_LIMIT=1` a station frame took about 3 s
  and the label band alone about 1.4 s.

**Where the card sits** [Likely ±1 mm, from image scale]: on 27 PSA backs the card's top edge is
34.8–37.8 mm (median 36.1) from the slab's label-end edge; on 15 CGC backs about 2.5–3 mm further
(about 39–41 mm). The face-down card window is placed from the PSA numbers.

**Read rates at the machine's resolution** [Certain for flat scans]: PSA codes read on every slab;
the CGC 2023+ front Code128 was the weakest symbol (16 of 19 standard labels; very short bars and
a tight quiet zone); a synthetic glare spot on the label cost 2 of 19 standard and 1 of 5 gold CGC
back QRs and some PSA front barcodes.

**Limits.** [Certain] These are studio scans and seller photos, not the machine's cameras: flat,
evenly lit, with no slab-plastic reflections, curvature, defocus or lens-edge effects, so real
read rates will be lower [Likely]. Some groups are small (2 Authentic, 3 PSA 2016, 5 OG, one
13-digit CGC cert), so "never seen" is [Certain] for this set and [Likely] in general. The
machine's parsing and face-down rules were written from these same slabs, so "0 wrong certs and 0
false proofs" here shows the rules fit them, not that they hold on new labels: Phase 0 on your own
slabs, and `python -m tools.real_eval --phase0`, is the test that counts.
