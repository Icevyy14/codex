REPORT.md was not written: the harness blocks subagents from writing report files, so the full text is below. results.json is written, along with the scripts and raw data.

# SlabRail: the current slabscan code on real slab labels

The flat studio scans make the barcode decoder look better than it will be on the machine. The parser and the decision rules are what fail. They fail on payload formats that are now known from real labels:

1. **[Certain] A silent wrong cert.** The CGC URL regex cuts every 13-digit CGC cert to 12 digits. `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` parses as `140101289312`. The slab cgc-1401012893129 comes out **`ok` with the wrong number**, both at native resolution and in the machine-equivalent frames. Nothing catches it, because the 13-digit front Code128 that would contradict it is thrown away as unparsed.
2. **[Certain] The face-down check stops 43 of the 64 good slabs (67%).** Only a PSA back QR passes. Every face-down CGC slab is stopped with the wrong reason ("a CGC code is visible from above, and those sit on the FRONT label"), because its back QR is a CGC code. The check never touches a face-up slab: 64/64 face-up views stop. So it is safe, but an unattended CGC batch is impossible. The README says the learned mode never becomes active with the CAD head, so this 'stop' behaviour is what the machine actually does. I took that from the README and did not re-run it.
3. **[Certain] `ItfModel` can never learn.** Its evidence stayed `{}` over the whole batch. It only learns from a slab that has both a QR and an odd-length ITF cert, and no such label exists: every QR+ITF label carries an 8-digit cert, 7-digit certs exist only on pre-2016 labels (no QR), and 9-digit certs use Code128. As a result, every pre-2017 PSA slab (10/64) depends on OCR, even when the back ITF and the front ITF agree.
4. **[Certain] CGC OG (2020-23) slabs are mostly `no_read`.** The `cgccomics.com` QR and the 26-28-digit back Code128 are not parsed: 3/4 machine slabs and 4/5 native slabs are `no_read` (native shows 3 `no_read` + 1 `needs_review` with an OCR-invented cert once OCR works).
5. **[Certain] On this loaded box, Tesseract OCR timed out on every frame (0/64 native, 2/58 station).** The cause was OpenMP thread contention: with `OMP_THREAD_LIMIT=1` the same OCR reads a station frame in about 3 s, and the label band alone in about 1.4 s. **[Guessing]** An otherwise idle Pi may suffer less. Only a Pi test settles it.
6. **[Certain] The known phantom Code128 (`09435764` on fc_27435764_0) reproduces at native resolution** and turns that slab into `conflict` when the front is decoded (`--front-photo always`). In the default fallback mode the back QR already gives `ok`, so the front is never read. It did not reproduce at machine scale (one pose tested).

Re-parsing the same decodes with the minimal rules in section 5 (proposed.py) gives these results:

| | ok | needs_review | no_read | wrong cert in ok |
|---|---|---|---|---|
| Native, current | 52 | 7 | 5 | 1 |
| Native, proposed | 58 | 4 | 2 | 0 |
| Machine-equivalent, current | 51 | 4 | 3 | 1 |
| Machine-equivalent, proposed | 56 | 2 | 0 | 0 |

The face-down check would then prove 50/64 slabs face-down, prove 22/64 face-up views face-up, and give zero false proofs.

## 1. Method

- **[Certain] Image set.** realslabs/index.json has 171 entries. The 128 "good" images form 64 slabs, each with a front and a back:
  - PSA: 10 current Code128, 11 lighthouse QR+ITF, 3 from 2016 (back ITF), 7 pre-2016.
  - CGC: 19 2023+ standard, 5 Pristine gold, 2 Authentic, 5 OG blue.
  - 1 BGS and 1 SGC.

  Extras run at native resolution only: the phone photos, the PSA guide photos (including the 7-digit certs 02074012 and 01418255), and the CGC press images and renders, used for payload harvesting. Ground truth is the manifest cert with leading zeros stripped. **[Certain]** All 54 QR payloads that carry a cert agree with the manifest.
- **Native run.** `decode_frame(img, side, allow_ocr=False)`, exactly as `runner._read` calls it. Then a raw zxing-cpp audit at 1.0x and 0.5x, and `ocr_digits` on fronts.
- **Machine-equivalent run.**
  - Scale: mm/px is estimated from the slab width (80.3 mm). Most scans are full-bleed; otherwise the slab bounding box is detected. **[Guessing]** The scale is good to about ±5%; non-PSA slab sizes differ.
  - Head frames: 3264x2448 at 0.055 mm/px (held frame, 140 mm) and 0.0578 mm/px (hover frame, 147 mm). The slab is centred with its long axis along the image y axis, so the label sits at the frame's top edge. Each frame gets ±2 mm offset, ±1° rotation, ±10% exposure, Gaussian blur with sigma 1 px, noise with sigma 3, and JPEG q85 (UVC MJPEG). Frames are then cropped with the runner's own `Runner._head_roi` (pocket ROI).
  - Station frames: 4608x2592 at 0.039 mm/px, label centred, the same degradations, no JPEG.
  - Glare variant: a 95%-saturated spot about 16x10 mm placed at random on the label band.
  - Face-up variant: the front image placed in a hover head frame.
  - Coverage: 58 of 64 slabs. The seller-image fronts (0.050-0.085 mm/px) are coarser than the station camera and were skipped. Four studio fronts at 0.041-0.044 mm/px were upscaled by 12% or less, which is pessimistic.
- **Slab verdicts.** I replayed `runner.transfer`'s read sequence and called the real `Runner._decide` (consensus + run rules) through a stub.
  - Sequence: hover frame + 2 held back frames → decide. If the result is not `ok` (`front_photo="fallback"`): 2 station frames → decide. If `no_read`, or `needs_review` with ITF only: front OCR → decide.
  - One `ItfModel` instance covered the whole batch.
  - The face-down check is the real `Runner._check_face_down` in 'stop' mode.

## 2. Per-image read rate (good images)

A "read" means `decode_frame` returned a CodeRead whose `.cert` equals the manifest cert.

| grader | era | side | n | code on this side? | native | held1 | held2 | hover 147 mm | glare | station1 | station2 | wrong-cert reads (nat/mach frames) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BGS | silver | back / front | 1 / 1 | no | 0/1, 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0 |
| CGC | OG 2020-23 | back | 5 | yes (QR + long C128) | **1/5** | 1/4 | 1/4 | 1/4 | 1/4 | | | 0 |
| CGC | OG 2020-23 | front | 5 | no | 0/5 | | | | 0/4 | 0/4 | 0/4 | 0 |
| CGC | Authentic | back | 2 | no | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | | | 0 |
| CGC | Authentic | front | 2 | yes (QR 0_0 + C128) | 2/2 | | | | 2/2 | 2/2 | 2/2 | 0 |
| CGC | 2023+ gold | back | 5 | yes | 4/5 | 4/5 | 4/5 | 4/5 | 3/5 | | | **1/6** |
| CGC | 2023+ gold | front | 5 | yes | 4/5 | | | | 4/5 | 4/5 | 4/5 | 0 |
| CGC | 2023+ standard | back | 19 | yes | 19/19 | 19/19 | 19/19 | 19/19 | 17/19 | | | 0 |
| CGC | 2023+ standard | front | 19 | yes | 16/19 | | | | 16/19 | 16/19 | 16/19 | 0 |
| PSA | 2016 | back | 3 | yes (ITF) | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | | | 0 |
| PSA | 2016 | front | 3 | yes | 3/3 | | | | 3/3 | 3/3 | 3/3 | 0 |
| PSA | lighthouse | back | 11 | yes | 11/11 | 11/11 | 11/11 | 11/11 | 11/11 | | | 0 |
| PSA | lighthouse | front | 11 | yes | 11/11 | | | | 7/9 | 9/9 | 9/9 | 0 |
| PSA | current C128 | back | 10 | yes | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | | | 0 |
| PSA | current C128 | front | 10 | yes | 10/10 | | | | 7/8 | 8/8 | 8/8 | **1/0** |
| PSA | pre-2016 | back | 7 | no | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 | | | 0 |
| PSA | pre-2016 | front | 7 | yes (ITF) | 7/7 | | | | 7/7 | 7/7 | 7/7 | 0 |
| SGC | tuxedo | back / front | 1 / 1 | no | 0/1, 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | – | – | 0 |

Same decodes, re-parsed with the proposed rules:

- CGC OG back: 5/5 native, 4/4 machine.
- CGC gold back: 5/5.
- CGC gold front: 4/5 native, 5/5 machine (the 13-digit Code128 now counts).
- Every other cell is unchanged.

What the table shows:

- **[Certain] On flat scans, PSA codes are not the bottleneck.** The QR, ITF and Code128 read at 100% at machine scale.
- **[Certain] The CGC 2023+ front Code128 is the weakest symbol.** It read 16/19 at both scales, but the misses differ between scales: wigglytuff and 25th-anniversary venusaur fail at both, Japanese base venusaur fails only at native, haunter only at machine. **[Likely]** The cause is its very short bars (about 1.7 mm) and a tight quiet zone against the label edge.
- **[Certain] The glare spot costs CGC back QRs.** Standard lost 2/19, gold 1/5. PSA front 1D codes lost 2/9 (lighthouse ITF) and 1/8 (current Code128).
- **[Certain] Real phone photos are harder.** The two phone photos through plastic (reference/cu_psa_newlabel_weirdslab_2/3.jpg, lighthouse backs) give **no QR at all**, natively or at machine scale: ITF only. These are the closest thing in the set to a real camera through a slab, and they are the cases where the QR face-down proof fails.

## 3. Per-slab consensus

Status order in each cell: ok / needs_review / conflict / no_read / other_grader. OCR here is the single-thread re-run (section 7); with the contended OCR, native is 48/10/0/6/0 and machine 47/7/0/4/0.

| grader | era | n | native, current | machine, current | machine + glare | native, proposed | machine, proposed |
|---|---|---|---|---|---|---|---|
| BGS | silver | 1 | 0/0/0/1/0 | 0/1/0/0/0 (OCR only) | 0/1/0/0/0 | 0/0/0/1/0 | 0/1/0/0/0 |
| CGC | OG 2020-23 | 5 (4 machine) | **1/1/0/3/0** | **1/0/0/3/0** | 1/0/0/3/0 | 5/0/0/0/0 | 4/0/0/0/0 |
| CGC | Authentic | 2 | 2/0/0/0/0 | 2/0/0/0/0 | 2/0/0/0/0 | 2/0/0/0/0 | 2/0/0/0/0 |
| CGC | 2023+ gold | 5 | 5/0/0/0/0 (**1 wrong cert**) | 5/0/0/0/0 (**1 wrong cert**) | 4/1/0/0/0 | 5/0/0/0/0 | 5/0/0/0/0 |
| CGC | 2023+ standard | 19 | 19/0/0/0/0 | 19/0/0/0/0 | 17/2/0/0/0 | 19/0/0/0/0 | 19/0/0/0/0 |
| PSA | 2016 | 3 | 1/2/0/0/0 | 1/2/0/0/0 | 1/2/0/0/0 | 3/0/0/0/0 | 3/0/0/0/0 |
| PSA | lighthouse | 11 (9) | 11/0/0/0/0 | 9/0/0/0/0 | 9/0/0/0/0 | 11/0/0/0/0 | 9/0/0/0/0 |
| PSA | current | 10 (8) | 10/0/0/0/0 | 8/0/0/0/0 | 8/0/0/0/0 | 10/0/0/0/0 | 8/0/0/0/0 |
| PSA | pre-2016 | 7 | 3/4/0/0/0 | 6/1/0/0/0 | 6/1/0/0/0 | 3/4/0/0/0 | 6/1/0/0/0 |
| SGC | tuxedo | 1 (0) | 0/0/0/1/0 | – | – | 0/0/0/1/0 | – |

- **[Certain]** Every `needs_review` on a PSA slab carries the note "ITF only; padding vs check digit not learned yet". The cert was right every time; the reason it was held back can never go away.
- **[Certain]** Glare-induced `needs_review` on CGC slabs carries the note "grader not confirmed (no PSA QR/ITF)". The front Code128 read the right cert, but the parser gives a bare 10-digit Code128 the grader `unknown`.
- **[Certain]** With `--front-photo always`, native psa-27435764 becomes `conflict` ("codes disagree: 27435764, 9435764") because of the phantom.
- **[Certain] Extra slabs (native only).**
  - The guide-photo 7-digit certs (2074012, 1418255) and the phone-photo lighthouse slab 42276167 (QR unreadable) are ok only through OCR agreement.
  - The CGC press slabs are `no_read`: their QR is the generic `https://www.cgccards.com/certlookup/`.

## 4. Every wrong cert and every unparsed payload (verbatim)

**Wrong certs (current parser):**

| file | where | symbology | raw | parsed | truth |
|---|---|---|---|---|---|
| auctions/fc_27435764_0.jpg | native | Code128 | `09435764` | 9435764 | 27435764 |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img2.jpg | native; machine hover, held1 (x2), held2, held_glare (x2) | QRCode | `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` | 140101289312 | 1401012893129 |

- **[Certain] The phantom sits inside the true barcode.** At full resolution zxing-cpp 3.1.1 returns the true read with box y 486-547 px and the phantom with box y 522-534 px, at the same x span (240-630). The phantom is a thin band within the real symbol. It is absent at 0.75x and 0.5x. The Python binding has no `min_line_count` option (TypeError), so the fix has to be in slabscan.
- **[Certain] One slab verdict carries a wrong number.** Native cgc-3750599206 ends `needs_review` with cert **1995965624**: OCR-only digits taken from the card, not the cert. This happens because the OG back codes were not parsed.

**Unparsed payloads (real slabs):**

- auctions/ms_1926130_1.jpg (native): `QRCode:https://www.cgccomics.com/certlookup/3750599206/9_0`, `Code128:47140890000000003750599206`
- cgc/fanatics/fc_2002_pokemon_expedition_cyndaquil_105_cgc_85_nm_mt_img2.jpg (native + all 4 machine frames): `QRCode:https://www.cgccomics.com/certlookup/4067281028/8_5`, `Code128:47319985000000004067281028`
- cgc/fanatics/fc_2009_pokemon_platinum_holo_palkia_g_12_cgc_85_nm_mt_img2.jpg (native + 4 machine frames): `QRCode:https://www.cgccomics.com/certlookup/3931864027/8_5`, `Code128:48298585000000003931864027`
- cgc/fanatics/fc_2003_pokemon_skyridge_holo_alakazam_h1_cgc_7_nrmt_img2.jpg: `QRCode:https://www.cgccomics.com/certlookup/3805531090/7_0` (native + 4 machine frames); `Code128:47363270956575753805531090` (4 machine frames only; note the non-zero middle digits)
- cgc/fanatics/fc_1999_pokemon_base_set_rattata_61_cgc_10_pristine_img2.jpg (native + 4 machine frames): `Code128:0047064500000000004190928178`. This is 28 digits; its QR is on cgccards.com and parses.
- cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img1.jpg (machine station1, station2, station_glare; native did not decode it): `Code128:1401012893129`
- auctions/fc_28941258_0.jpg (machine station_glare): `ITF:289412`. This is a glare-truncated ITF. It was correctly rejected, which proves that truncated ITF reads happen.

**Unparsed payloads (non-ground-truth images):**

- cgc/official/unique-identification.png: `QRCode:HTTPS://WWW.CGCCOMICS.COM/CERTLOOKUP/0100000001/0_0`
- cgc/news/cgc_news12803_charizard_1ed_back.png, cgc_news_jp_base_charizard_4308773015_back.png, cgc_news_rayquaza_goldstar_6151387001_back.png: `QRCode:https://www.cgccards.com/certlookup/`
- cgc/news/cgc_official_2020_OG_holder_mockup_charizard_back.jpg: `QRCode:cgccomics.com`
- reference/cgc2020_screenshot_label_detail_33.jpg: `QRCode:http://cgccomics.com/verify`

**Front OCR runs that were not the cert** (single-thread re-run). These show why OCR can never be the only evidence:

- `94065407` for 54065407 and `95039401` for 55039401: the first digit 5 read as 9.
- `20054106` for 26932317 (station frame and label band), `18802594` for 19802594, and `19994103` for 19802594: other digit runs on the label or card.
- `0079865140` for BGS 0019865140.
- `1401012893` for 1401012893129: `_OCR_TOKEN_RE` is capped at 10 digits.

## 5. certs.py rules against the real formats (rules_check.txt)

| payload (real) | grader/side it implies | current result | verdict |
|---|---|---|---|
| `http://psacard.com/cert/27720238` (3 slabs + guide) | PSA back | PSA 27720238 | OK |
| `https://www.psacard.com/cert/26275088/` | PSA back | PSA 26275088 | OK |
| `https://www.psacard.com/cert/100423658/` | PSA back | PSA 100423658 | OK |
| ITF `26275088` (8-digit cert) | PSA, front (all eras) or back (2016+) | PSA 26275088 | OK, but ItfModel never resolves it |
| ITF `02074012` / `01418255` (7-digit certs, zero-padded) | PSA front (pre-2016) | PSA 2074012 / 1418255, **alt=141825** | cert OK; the check-digit alternative is meaningless |
| Code128 `100423658` / `27435764` | PSA, front **and** back (current labels) | **grader `unknown`** | wrong grader |
| Code128 `6003997046` | CGC 2023+ front | **grader `unknown`** | wrong grader |
| Code128 `1401012893129` | CGC 2023+ front | **unparsed** (13 > MAX_DIGITS+1) | **FAIL** |
| QR `https://www.cgccards.com/certlookup/6003997046/10_0/` (with or without the trailing slash, any case) | CGC back | CGC 6003997046 | OK |
| QR `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` | CGC back | **CGC 140101289312** | **FAIL: wrong cert** |
| QR `https://www.cgccomics.com/certlookup/3750599206/9_0` | CGC OG back | **unparsed** | **FAIL** |
| Code128 `47140890000000003750599206` (26 digits) / `0047064500000000004190928178` (28 digits) | CGC OG back; the cert is the last 10 digits | **unparsed** | **FAIL** |
| QR `https://www.cgccards.com/certlookup/6182652005/0_0/` | CGC Authentic **front** | CGC 6182652005 | cert OK; the front/back meaning is lost (`decode._source_for` says "Front labels have no QR today", which is false for CGC Authentic labels) |
| QR `https://www.cgccards.com/certlookup/`, `http://cgccomics.com/verify`, `cgccomics.com` | a CGC label with no cert | unparsed | OK as no cert, but it is evidence that a CGC back label is in view |

**[Certain] Why the regexes fail:**

- `cgccards\.com/\S*?(\d{7,12})`: the domain is too narrow (no cgccomics), and the digit cap of 12 truncates 13-digit certs.
- `_BARE_DIGITS_RE = ^\d{7,11}$` together with `MAX_DIGITS = 10`: rejects 13- and 26-28-digit payloads.
- The bare-digit branch assigns a grader only to ITF (PSA). Every Code128 becomes `unknown`.
- The PSA URL regex `psacard\.com/cert/(\d{6,11})` has no right boundary, so it would truncate a longer number silently. This is latent; it did not occur in the set.

**[Certain] How ItfModel behaves:**

- `observe()` returns early for even-length reference certs, and every real QR+ITF pair has an 8-digit cert, so the evidence is `{}` after 11 real QR+ITF slabs.
- `resolve()` returns `None` while the mode is unknown, so `consensus` gives `needs_review` even with back ITF + front ITF agreeing: verified on 16870121, 02074012 and 01418255.
- **[Certain] The ITF format is fixed.** The ITF payload is always 8 digits: the cert, zero-padded. That holds for 21 good PSA slabs, 4 guide/phone slabs, and 3 seven-digit guide labels (02074012, 01418255, 02458772). There is nothing left to learn.

**Minimal correct rules** (implemented and evaluated in proposed.py). The 10-digit and 13-digit Code128 tests must run before the PSA length test.

```
PSA QR      ^https?://(www\.)?psacard\.com/cert/(\d{7,9})/?$                                        -> PSA, BACK
CGC QR      ^https?://(www\.)?cgc(cards|comics)\.com/certlookup/(\d{10}|140\d{10})/(\d{1,2}_\d)/?$  (re.I)
                                                       -> CGC; grade 0_0 = Authentic FRONT, else BACK
CGC no-cert ^(https?://)?(www\.)?cgc(cards|comics)\.com(/certlookup|/verify)?/?$                    -> CGC BACK, no cert
ITF         ^\d{8}$ -> PSA, cert = lstrip('0') (6+ digits), no alternative; any other ITF length = misread
Code128     ^\d{16,18}(\d{10})$        -> CGC OG BACK, cert = last 10 digits
            ^(\d{10}|140\d{10})$       -> CGC 2023+ FRONT
            ^\d{7,9}$                  -> PSA (front or back)
```

**[Guessing] Residual risk.** A future BGS or SGC label with a bare 10-digit Code128 would be typed CGC. Because 1D-only reads still need two sources (or OCR) to reach `ok`, it would land in `needs_review`, never in a wrong `ok`.

## 6. Face-down: what a code seen FROM ABOVE proves

| code seen by the head camera | proves | evidence |
|---|---|---|
| PSA QR (`psacard.com/cert/`) | **face-down** | [Certain] 35 PSA front images: never a QR. All 2017+ backs have one. |
| CGC certlookup QR, grade ≠ `0_0` (cgccards or cgccomics) | **face-down** | [Certain] 0/26 CGC graded fronts have a QR; all 24 2023+ backs and the OG backs have one |
| CGC no-cert QR (`…/certlookup/`, `cgccomics.com/verify`) | face-down | [Likely] seen only on back labels (press images and mock-ups) |
| CGC 26-28-digit Code128 | **face-down** | [Certain] OG backs only; OG fronts carry no code (0/10) |
| CGC certlookup QR with grade `0_0` | **face-up** | [Certain] both Authentic slabs carry it on the front; their backs decode nothing. [Likely] for all Authentic labels. |
| bare 10-digit or `140`+10-digit Code128 | **face-up** (CGC front) | [Certain] in this set: 2023+ backs never carry a Code128 (0/26); fronts do. The head camera read it on 20 of 26 CGC fronts at hover scale. |
| PSA ITF | **ambiguous** | [Certain] It is on fronts of every era and on 2016+ backs. ITF without a QR can mean a pre-2016 front, a 2016 back, or a 2017+ back whose QR failed (both phone photos). |
| PSA Code128 (7-9 digits) | **ambiguous** | [Certain] Identical payload on the front and back of current labels |
| nothing | ambiguous | PSA pre-2016 backs, CGC Authentic backs, CGC OG fronts, BGS and SGC both sides |

**[Certain] The current rule** (`runner._check_face_down`):

- `psa_back = any PSA back_qr`. Separately, `fronts` is every grader other than PSA or unknown, treated as front-label evidence.
- Measured on real labels:

  | | passes | stops |
  |---|---|---|
  | face-down slabs, native | 21/64 (all PSA QR) | 43/64 |
  | face-down slabs, machine | 17/58 | 41/58 |
  | face-up views | 0 | 64/64 |

- Of the stops on face-down slabs:
  - 24 2023+ CGC slabs get the wrong reason "CGC code … sit on the FRONT label". So does the one OG slab whose QR is on cgccards.com.
  - In learned mode, any CGC code also blocks the card-window match and the reference learning (`if learned and not fronts`). CGC slabs would therefore stop forever, even if learned mode were active.

**Proposed rule** (`proposed.face_from_above`, evaluated on the same reads):

| | proven face-down | proven face-up | unknown |
|---|---|---|---|
| face-down slabs, native | 50/64 | 0 | 14 (10 PSA pre-2017, 2 Authentic, BGS, SGC) |
| face-down slabs, machine | 45/58 | 0 | 13 |
| face-up views, native | 0 | 22/64 (CGC Code128 or Authentic QR) | 42 |
| face-up views, machine | 0 | 20/58 | 38 |

- **Zero false proofs in either direction.** "Unknown" keeps today's behaviour (stop, or a learned match).
- A front proof gets its own message ("the slab is face-UP"). A back proof together with a front proof means a neighbour's label is in view: stop.

## 7. Timing (x86 VM, 4 CPUs shared with other agents' tests; load average 7-23)

CPU seconds come from `time.process_time` (zxing-cpp runs in-process). Wall times are inflated 2-5x by contention.

| frame | pixels decoded | CPU median / p90 / max | CPU, frames with a read | CPU, frames with no read |
|---|---|---|---|---|
| head hover / held (ROI) | 1632-1718 x 2448 | 0.1 / 1.7 / 1.9 s | 0.1 s | 1.6-1.7 s |
| station | 4608 x 2592 | 0.4-0.7 / 8-9 / 9.8 s | 0.3-0.7 s | **8-9 s** |
| native scan | ~2900 x 4900 | 0.7 / 10 / 13 s | 0.6 s | 9.4-9.8 s |

- **[Certain]** `decode_frame` is fast whenever pass 1 reads something. It costs up to 4 passes (with a 2x upscale and padded tiles) when nothing reads. On a 12 MP station frame the 2x pass decodes 48 MP.
- **[Guessing]** A Pi 5 core is about 2-3x slower. That puts a no-code front at about 20 s per station frame, and the runner decodes two.

Per-slab decode CPU in the replayed runner flow (machine-equivalent):

| slab type | CPU per slab |
|---|---|
| PSA / CGC with a back QR | 0.3 s |
| CGC Authentic (needs the front) | 6 s |
| PSA 2016 | 5 s + OCR |
| PSA pre-2016 | 10.5 s, OCR included |
| BGS / CGC OG with the current parser (nothing parses) | about 25 s |

**[Certain] Early exit hides QRs.** `decode_frame` stops at the first pass that parses anything. In fc_54065407_1 (held frame with glare), it returned only the ITF, while the QR `https://www.psacard.com/cert/54065407/` decodes on the plain CLAHE pass. On a hover frame that difference is a face-down stop.

## 8. OCR (`ocr_digits`, the only independent check of a single ITF read)

| setting | native full image | station frame (what the runner OCRs) | label band only (the change I suggest) |
|---|---|---|---|
| default OpenMP (contended box) | 0/64 hits, ~33 s each (30 s timeout) | 2/58 hits, ~31 s each | 0/13 (90 s timeout) |
| `OMP_THREAD_LIMIT=1` | 44/64 hits, median 10 s, max 33 s | 47/58 hits, median 3.3 s, max 5.1 s | 48/58 hits, median 1.4 s, max 2.9 s |
| PSA pre-2016, single thread | 3/7 | 6/7 | 6/7 |

- **[Certain] Threads, not resolution, cause the timeouts.** With default OpenMP threads, Tesseract 5.3.4 on a loaded 4-CPU machine timed out at 30 s on essentially every frame. Single-threaded, the same call reads a station frame in about 3 s.
- **[Certain] What goes wrong in a full frame.** CLAHE + Otsu on the full frame turns the slab plastic into about 2000 specks for `--psm 11`. A label-band crop removes them.
- **[Likely] OCR misreads that collide with a correct ITF are rejected.** The consensus rule "OCR disagrees with ITF → needs_review" caught every one of those in this set.

## 9. What must change, in priority order

1. **certs.py `_URLS["CGC"]`** → `cgc(?:cards|comics)\.com/certlookup/(\d{10}|140\d{10})(?:/(\d{1,2}_\d))?/?(?:$|[?#\s])` (re.I).
   - It fixes the wrong cert (13-digit truncation) and the OG `cgccomics.com` QRs.
   - Keep the grade: `0_0` means Authentic, front label.
   - Also give the PSA regex a right boundary: `psacard\.com/cert/(\d{6,9})(?:/|$)`.
2. **certs.py bare digits**: assign the grader by symbology and length, using the table in section 5.
   - Route 13-digit and OG 26-28-digit CGC payloads around `canonical()` / `MAX_DIGITS`.
   - Reject any ITF that is not exactly 8 digits. Truncated ITF reads exist (`ITF:289412`).
3. **ItfModel**: delete the check-digit hypothesis, or make `mode` constantly `"zero_pad"` with no `alt_cert`.
   - Keep the safety rule that a 1D-only `ok` needs two printed symbols (back + front) or OCR agreement.
   - Effect: the 3 PSA 2016 slabs go to `ok`. Pre-2016 slabs still need OCR, which is correct, since they have one symbol only.
4. **consensus()**: a 1D-only result (ITF or Code128, any grader) needs two physical sources or OCR agreement.
   - This replaces the `unknown`-grader / "grader not confirmed (no PSA QR/ITF)" path. Its note is also wrong for CGC.
   - The CGC branch currently returns `ok` on any single CGC read. Once Code128 is typed CGC, it must not accept one 1D read alone.
5. **decode.py phantom**: in `_zxing_pass`, drop a linear read whose position box lies inside another read of the same format and covers less than about 1/3 of its height (here 12 px vs 61 px).
   - Alternative in consensus: two different certs from one camera and one symbology, where another source confirms one of them, → drop the other.
6. **runner._check_face_down**: replace `fronts = graders other than PSA/unknown` with the side table in section 6.
   - Pass and learn on any back proof (PSA QR, CGC QR ≠ 0_0, CGC no-cert QR, CGC long Code128).
   - Stop with a face-UP message on a front proof.
   - Pass `unparsed` in too: the no-cert CGC QR is only visible there.
   - Fix the README line "Older labels and CGC stop every time": the CGC part becomes false.
7. **decode_frame early exit**: on 'back' frames (hover especially), if no 2D symbol was found yet, run the CLAHE pass before returning.
8. **OCR**:
   - Set `OMP_THREAD_LIMIT=1` for Tesseract (in the process environment before pytesseract runs, or in the systemd unit / setup_pi.sh).
   - Crop to the label band before `ocr_digits`.
   - Extend `_OCR_TOKEN_RE` to `\d{8,10}|140\d{10}`.
   - **[Likely]** Then the 30 s timeout never triggers.
9. **[Likely] CGC front Code128** (16/19): add a padded crop of the label's bottom strip as a decode pass. It matters only when the CGC back QR fails, as in 3/24 glare frames.

## 10. What this does NOT show

- **[Certain] The machine-equivalent frames are optimistic.** They are flat studio scans, rescaled and degraded. They have no slab-plastic specular highlights except the synthetic spot, no curvature or perspective, no defocus between label and card, and no lens distortion or vignetting at the frame edge, which is where the head camera puts the back label (top 25 mm of a 134.6 mm field). The only real through-plastic photos (2 phone photos) lost the QR entirely.
- **[Likely] The 100% PSA read rates will not survive the real machine.** The relative findings will: the parser, ItfModel and face-down bugs are format bugs, independent of image quality.
- **[Guessing] Timing on the Pi** is a scaled estimate. The OCR thread issue must be re-measured on the Pi itself.
- **Sample size.** It is small for some eras: 2 Authentic, 3 PSA 2016, 5 OG, and one 13-digit CGC slab. "Never seen" claims (no QR on PSA fronts, no Code128 on CGC 2023+ backs) are **[Certain] for this set** and **[Likely]** in general.

## Files

Everything is in scratch/real_eval/:
- results.json – per image: native and machine reads, unparsed payloads, timings, OCR. Per slab: runner verdicts in fallback / always / glare / contended-OCR modes, face-down results, proposed verdicts.
- tables.md – the full generated tables.
- rules_check.txt
- native.jsonl, machine.jsonl, ocr_redo.jsonl – raw per-frame data.
- run_images.py, analyze.py, tables.py, proposed.py, rules_check.py, ocr_redo.py, ocr_exp.py, geom.py – the scripts.