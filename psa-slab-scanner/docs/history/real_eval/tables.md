### Per-image read rate (good images; a 'read' = decode_frame returned a CodeRead whose cert equals the manifest cert)

| grader | era | side | n | code on this side? | native | machine held1 | held2 | hover (147 mm) | glare on label | station1 | station2 | wrong-cert reads (nat/mach) | images with unparsed payloads (nat/mach) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BGS | BGS silver | back | 1 | no | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |  |  | 0/0 | 0/0 |
| BGS | BGS silver | front | 1 | no | 0/1 |  |  |  | 0/1 | 0/1 | 0/1 | 0/0 | 0/0 |
| CGC | 2020-23 OG blue | back | 5 | yes | 1/5 | 1/4 | 1/4 | 1/4 | 1/4 |  |  | 0/0 | 5/4 |
| CGC | 2020-23 OG blue | front | 5 | no | 0/5 |  |  |  | 0/4 | 0/4 | 0/4 | 0/0 | 0/0 |
| CGC | 2023+ authentic | back | 2 | no | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |  |  | 0/0 | 0/0 |
| CGC | 2023+ authentic | front | 2 | yes | 2/2 |  |  |  | 2/2 | 2/2 | 2/2 | 0/0 | 0/0 |
| CGC | 2023+ pristine gold | back | 5 | yes | 4/5 | 4/5 | 4/5 | 4/5 | 3/5 |  |  | 1/6 | 0/0 |
| CGC | 2023+ pristine gold | front | 5 | yes | 4/5 |  |  |  | 4/5 | 4/5 | 4/5 | 0/0 | 0/1 |
| CGC | 2023+ standard | back | 19 | yes | 19/19 | 19/19 | 19/19 | 19/19 | 17/19 |  |  | 0/0 | 0/0 |
| CGC | 2023+ standard | front | 19 | yes | 16/19 |  |  |  | 16/19 | 16/19 | 16/19 | 0/0 | 0/0 |
| PSA | 2016 (back ITF, no QR) | back | 3 | yes | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |  |  | 0/0 | 0/0 |
| PSA | 2016 (back ITF, no QR) | front | 3 | yes | 3/3 |  |  |  | 3/3 | 3/3 | 3/3 | 0/0 | 0/0 |
| PSA | 2017+ lighthouse (QR+ITF) | back | 11 | yes | 11/11 | 11/11 | 11/11 | 11/11 | 11/11 |  |  | 0/0 | 0/0 |
| PSA | 2017+ lighthouse (QR+ITF) | front | 11 | yes | 11/11 |  |  |  | 7/9 | 9/9 | 9/9 | 0/0 | 0/1 |
| PSA | current (Code128) | back | 10 | yes | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |  |  | 0/0 | 0/0 |
| PSA | current (Code128) | front | 10 | yes | 10/10 |  |  |  | 7/8 | 8/8 | 8/8 | 1/0 | 0/0 |
| PSA | pre-2016 (no back code) | back | 7 | no | 0/7 | 0/7 | 0/7 | 0/7 | 0/7 |  |  | 0/0 | 0/0 |
| PSA | pre-2016 (no back code) | front | 7 | yes | 7/7 |  |  |  | 7/7 | 7/7 | 7/7 | 0/0 | 0/0 |
| SGC | SGC tuxedo | back | 1 | no | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |  |  | 0/0 | 0/0 |
| SGC | SGC tuxedo | front | 1 | no | 0/1 |  |  |  |  |  |  | 0/0 | 0/0 |

### Same decodes, payloads re-parsed with the proposed rules (proposed.py)

| grader | era | side | n | native current | native proposed | machine held1/station1 current | proposed |
|---|---|---|---|---|---|---|---|
| BGS | BGS silver | back | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| BGS | BGS silver | front | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| CGC | 2020-23 OG blue | back | 5 | 1/5 | 5/5 | 1/4 | 4/4 |
| CGC | 2020-23 OG blue | front | 5 | 0/5 | 0/5 | 0/4 | 0/4 |
| CGC | 2023+ authentic | back | 2 | 0/2 | 0/2 | 0/2 | 0/2 |
| CGC | 2023+ authentic | front | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| CGC | 2023+ pristine gold | back | 5 | 4/5 | 5/5 | 4/5 | 5/5 |
| CGC | 2023+ pristine gold | front | 5 | 4/5 | 4/5 | 4/5 | 5/5 |
| CGC | 2023+ standard | back | 19 | 19/19 | 19/19 | 19/19 | 19/19 |
| CGC | 2023+ standard | front | 19 | 16/19 | 16/19 | 16/19 | 16/19 |
| PSA | 2016 (back ITF, no QR) | back | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| PSA | 2016 (back ITF, no QR) | front | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| PSA | 2017+ lighthouse (QR+ITF) | back | 11 | 11/11 | 11/11 | 11/11 | 11/11 |
| PSA | 2017+ lighthouse (QR+ITF) | front | 11 | 11/11 | 11/11 | 9/9 | 9/9 |
| PSA | current (Code128) | back | 10 | 10/10 | 10/10 | 10/10 | 10/10 |
| PSA | current (Code128) | front | 10 | 10/10 | 10/10 | 8/8 | 8/8 |
| PSA | pre-2016 (no back code) | back | 7 | 0/7 | 0/7 | 0/7 | 0/7 |
| PSA | pre-2016 (no back code) | front | 7 | 7/7 | 7/7 | 7/7 | 7/7 |
| SGC | SGC tuxedo | back | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| SGC | SGC tuxedo | front | 1 | 0/1 | 0/1 | - | - |

### Extra images (not 'good': guide photos, phone photos, press images) - native only

| file | side | era | native mm/px | truth | reads (sym:raw) | unparsed | hit |
|---|---|---|---|---|---|---|---|
| cgc/official/unique-identification.png | back | 2023+ standard | 0.079 | n/a | - | QRCode:HTTPS://WWW.CGCCOMICS.COM/CERTLOOKUP/0100000001/0_0 | n/a |
| cgc/official/superior-display.png | front | 2023+ standard | 0.060 | 1400295671845 | - | - | False |
| cgc/official/stackable.png | front | 2023+ standard | 0.308 | n/a | - | - | n/a |
| cgc/official/leader-in-error-card-grading.png | front | 2023+ standard | 0.107 | n/a | - | - | n/a |
| cgc/official/cgc_guide_holder_2023-2025.png | front | 2023+ standard | 0.208 | n/a | - | - | n/a |
| cgc/official/cgc_guide_holder_2025-current.png | front | 2023+ standard | 0.124 | n/a | - | - | n/a |
| cgc/news/cgc_news12803_charizard_1ed_front.png | front | 2023+ standard | 0.243 | 1401025439002 | - | - | False |
| cgc/news/cgc_news12803_charizard_1ed_back.png | back | 2023+ standard | 0.243 | n/a | - | QRCode:https://www.cgccards.com/certlookup/ | n/a |
| cgc/news/cgc_news_jp_base_charizard_4308773015_front.png | front | 2023+ standard | 0.284 | 4308773015 | - | - | False |
| cgc/news/cgc_news_jp_base_charizard_4308773015_back.png | back | 2023+ standard | 0.285 | n/a | - | QRCode:https://www.cgccards.com/certlookup/ | n/a |
| cgc/news/cgc_news_rayquaza_goldstar_6151387001_front.png | front | 2023+ standard | 0.166 | 6151387001 | - | - | False |
| cgc/news/cgc_news_rayquaza_goldstar_6151387001_back.png | back | 2023+ standard | 0.149 | n/a | - | QRCode:https://www.cgccards.com/certlookup/ | n/a |
| cgc/news/cgc_official_2020_OG_holder_mockup_charizard_back.jpg | back | 2020-23 OG blue | 0.154 | n/a | - | QRCode:cgccomics.com | n/a |
| reference/avc_psa_lighthouse_back_label_diagram.jpeg | back | 2017+ lighthouse (QR+ITF) | 0.361 | 27358086 | QRCode:http://psacard.com/cert/27358086, ITF:27358086 | - | True |
| reference/avc_psa_lighthouse_back_qr.jpg | back | 2017+ lighthouse (QR+ITF) | 0.154 | 27358086 | QRCode:http://psacard.com/cert/27358086, ITF:27358086 | - | True |
| reference/avc_psa_lighthouse_front.jpg | front | 2017+ lighthouse (QR+ITF) | 0.135 | 27358086 | ITF:27358086 | - | True |
| reference/avc_psa_lighthouse_front_label_diagram.jpeg | front | 2017+ lighthouse (QR+ITF) | 0.042 | n/a | - | - | n/a |
| reference/avc_psa_type2_back_ryan.jpg | back | pre-2016 (no back code) | 0.097 | 2074012 | - | - | False |
| reference/avc_psa_type2_front_ryan.jpg | front | pre-2016 (no back code) | 0.099 | 2074012 | ITF:02074012 | - | True |
| reference/avc_psa_type3_back.jpg | back | pre-2016 (no back code) | 0.084 | 1418255 | - | - | False |
| reference/avc_psa_type3_front.jpg | front | pre-2016 (no back code) | 0.084 | 1418255 | ITF:01418255 | - | True |
| reference/avc_psa_type4_front_wynn.jpg | front | pre-2016 (no back code) | 0.152 | 2458772 | ITF:02458772 | - | True |
| reference/avc_psa_type5_back.png | back | pre-2016 (no back code) | 0.052 | n/a | - | - | n/a |
| reference/avc_psa_type5_front_batts.jpeg | front | pre-2016 (no back code) | 0.116 | 30033382 | ITF:30033382 | - | True |
| reference/avc_psa_type6_back_wilkins.jpg | back | pre-2016 (no back code) | 0.114 | n/a | - | - | n/a |
| reference/avc_psa_type6_front_ortiz.jpeg | front | pre-2016 (no back code) | 0.052 | 40463597 | ITF:40463597 | - | True |
| reference/avc_psa_type9_back_mikan_barcode.png | back | 2016 (back ITF, no QR) | 0.167 | 26264805 | ITF:26264805 | - | True |
| reference/avc_psa_type9_front_mikan.png | front | 2016 (back ITF, no QR) | 0.175 | 26264805 | ITF:26264805, ITF:26264805 | - | True |
| reference/cgc2020_mockup_front_luckystadium.jpg | front | 2020-23 OG blue | 0.140 | n/a | - | - | n/a |
| reference/cgc2020_screenshot_label_detail_28.jpg | front | 2020-23 OG blue | 0.080 | n/a | - | - | n/a |
| reference/cgc2020_screenshot_label_detail_33.jpg | back | 2020-23 OG blue | 0.080 | n/a | - | QRCode:http://cgccomics.com/verify | n/a |
| reference/cgcnews2023_charizard_a_back.png | back | 2020-23 OG blue | 0.243 | 4188729003 | - | - | False |
| reference/cgcnews2023_charizard_a_front.png | front | 2020-23 OG blue | 0.243 | n/a | - | - | n/a |
| reference/cgcnews2023_charizard_b_back.png | back | 2020-23 OG blue | 0.243 | 4053671007 | - | - | False |
| reference/cgcnews2023_charizard_b_front.png | front | 2020-23 OG blue | 0.243 | n/a | - | - | n/a |
| reference/cgcnews2023_gyarados_back.png | back | 2020-23 OG blue | 0.243 | 4188858010 | - | - | False |
| reference/cgcnews2023_gyarados_front.png | front | 2020-23 OG blue | 0.243 | n/a | - | - | n/a |
| reference/cgcnews2023_no2trainer_back.png | back | 2020-23 OG blue | 0.243 | 4263357001 | - | - | False |
| reference/cgcnews2023_no2trainer_front.png | front | 2020-23 OG blue | 0.243 | n/a | - | - | n/a |
| reference/cu_psa_newlabel_weirdslab_1.jpg | front | 2017+ lighthouse (QR+ITF) | 0.051 | 42276167 | ITF:42276167 | - | True |
| reference/cu_psa_newlabel_weirdslab_2.jpg | back | 2017+ lighthouse (QR+ITF) | 0.051 | 58973271 | ITF:58973271 | - | True |
| reference/cu_psa_newlabel_weirdslab_3.jpg | back | 2017+ lighthouse (QR+ITF) | 0.054 | 42276167 | ITF:42276167 | - | True |
| reference/legitapp_20250819717fa36f212a7e18.png | front | mixed (unverified) | 0.020 | n/a | - | - | n/a |

### Per-slab consensus (runner flow: hover + 2 held back frames -> decide; front photo + front OCR only when not ok)

| grader | era | n slabs | native: ok / needs_review / conflict / no_read / other_grader | machine (no glare) | machine + glare | wrong cert in an ok/needs_review verdict (nat/mach) | proposed rules native | proposed rules machine |
|---|---|---|---|---|---|---|---|---|
| BGS | BGS silver | 1 | 0 / 0 / 0 / 1 / 0 | 0 / 1 / 0 / 0 / 0 | 0 / 1 / 0 / 0 / 0 | 0/0 | 0 / 0 / 0 / 1 / 0 | 0 / 1 / 0 / 0 / 0 |
| CGC | 2020-23 OG blue | 5 | 1 / 1 / 0 / 3 / 0 | 1 / 0 / 0 / 3 / 0 | 1 / 0 / 0 / 3 / 0 | 1/0 | 5 / 0 / 0 / 0 / 0 | 4 / 0 / 0 / 0 / 0 |
| CGC | 2023+ authentic | 2 | 2 / 0 / 0 / 0 / 0 | 2 / 0 / 0 / 0 / 0 | 2 / 0 / 0 / 0 / 0 | 0/0 | 2 / 0 / 0 / 0 / 0 | 2 / 0 / 0 / 0 / 0 |
| CGC | 2023+ pristine gold | 5 | 5 / 0 / 0 / 0 / 0 | 5 / 0 / 0 / 0 / 0 | 4 / 1 / 0 / 0 / 0 | 1/1 | 5 / 0 / 0 / 0 / 0 | 5 / 0 / 0 / 0 / 0 |
| CGC | 2023+ standard | 19 | 19 / 0 / 0 / 0 / 0 | 19 / 0 / 0 / 0 / 0 | 17 / 2 / 0 / 0 / 0 | 0/0 | 19 / 0 / 0 / 0 / 0 | 19 / 0 / 0 / 0 / 0 |
| PSA | 2016 (back ITF, no QR) | 3 | 1 / 2 / 0 / 0 / 0 | 1 / 2 / 0 / 0 / 0 | 1 / 2 / 0 / 0 / 0 | 0/0 | 3 / 0 / 0 / 0 / 0 | 3 / 0 / 0 / 0 / 0 |
| PSA | 2017+ lighthouse (QR+ITF) | 11 | 11 / 0 / 0 / 0 / 0 | 9 / 0 / 0 / 0 / 0 | 9 / 0 / 0 / 0 / 0 | 0/0 | 11 / 0 / 0 / 0 / 0 | 9 / 0 / 0 / 0 / 0 |
| PSA | current (Code128) | 10 | 10 / 0 / 0 / 0 / 0 | 8 / 0 / 0 / 0 / 0 | 8 / 0 / 0 / 0 / 0 | 0/0 | 10 / 0 / 0 / 0 / 0 | 8 / 0 / 0 / 0 / 0 |
| PSA | pre-2016 (no back code) | 7 | 3 / 4 / 0 / 0 / 0 | 6 / 1 / 0 / 0 / 0 | 6 / 1 / 0 / 0 / 0 | 0/0 | 3 / 4 / 0 / 0 / 0 | 6 / 1 / 0 / 0 / 0 |
| SGC | SGC tuxedo | 1 | 0 / 0 / 0 / 1 / 0 | - | - | 0/0 | 0 / 0 / 0 / 1 / 0 | - |
| CGC | 2023+ standard (extra) | 2 | 0 / 0 / 0 / 2 / 0 | - | - | 0/0 | 0 / 2 / 0 / 0 / 0 | - |
| PSA | 2016 (back ITF, no QR) (extra) | 1 | 1 / 0 / 0 / 0 / 0 | - | - | 0/0 | 1 / 0 / 0 / 0 / 0 | - |
| PSA | 2017+ lighthouse (QR+ITF) (extra) | 1 | 1 / 0 / 0 / 0 / 0 | - | - | 0/0 | 1 / 0 / 0 / 0 / 0 | - |
| PSA | pre-2016 (no back code) (extra) | 2 | 2 / 0 / 0 / 0 / 0 | - | - | 0/0 | 2 / 0 / 0 / 0 / 0 | - |

Totals over good slabs: native {'no_read': 5, 'ok': 52, 'needs_review': 7}; machine {'needs_review': 4, 'ok': 51, 'no_read': 3}; machine+glare {'needs_review': 7, 'ok': 48, 'no_read': 3}; proposed native {'no_read': 2, 'ok': 58, 'needs_review': 4}; proposed machine {'needs_review': 2, 'ok': 56}

### Every slab verdict that is not 'ok' or carries a wrong cert

| slab | era | mode | status | cert | truth | note |
|---|---|---|---|---|---|---|
| other-0019865140 | BGS silver | native | no_read | None | 19865140 | nothing decoded |
| other-0019865140 | BGS silver | native (proposed) | no_read | None | 19865140 |  |
| other-0019865140 | BGS silver | machine | needs_review | 19865140 | 19865140 | ocr only - verify by eye |
| other-0019865140 | BGS silver | machine (proposed) | needs_review | 79865140 | 19865140 | ocr only |
| psa-18805593 | pre-2016 (no back code) | native | needs_review | 18805593 | 18805593 | ITF only; padding vs check digit not learned yet: 18805593 |
| psa-18805593 | pre-2016 (no back code) | native (proposed) | needs_review | 18805593 | 18805593 | 1D 18805593 vs OCR ['20255550'] |
| psa-19802594 | pre-2016 (no back code) | native | needs_review | 19802594 | 19802594 | ITF only; padding vs check digit not learned yet: 19802594 |
| psa-19802594 | pre-2016 (no back code) | native (proposed) | needs_review | 19802594 | 19802594 | 1D 19802594 vs OCR ['18802594'] |
| psa-19802594 | pre-2016 (no back code) | machine | needs_review | 19802594 | 19802594 | ITF only; padding vs check digit not learned yet: 19802594 |
| psa-19802621 | pre-2016 (no back code) | native | needs_review | 19802621 | 19802621 | ITF only; padding vs check digit not learned yet: 19802621 |
| psa-19802621 | pre-2016 (no back code) | native (proposed) | needs_review | 19802621 | 19802621 | 1D 19802621 vs OCR ['1995969899'] |
| psa-23805116 | pre-2016 (no back code) | native | needs_review | 23805116 | 23805116 | ITF only; padding vs check digit not learned yet: 23805116 |
| psa-23805116 | pre-2016 (no back code) | native (proposed) | needs_review | 23805116 | 23805116 | one printed 1D symbol only |
| psa-23805116 | pre-2016 (no back code) | machine (proposed) | needs_review | 23805116 | 23805116 | one printed 1D symbol only |
| psa-25656882 | 2016 (back ITF, no QR) | machine | needs_review | 25656882 | 25656882 | ITF only; padding vs check digit not learned yet: 25656882 |
| psa-25807907 | 2016 (back ITF, no QR) | native | needs_review | 25807907 | 25807907 | ITF only; padding vs check digit not learned yet: 25807907 |
| psa-26932317 | 2016 (back ITF, no QR) | native | needs_review | 26932317 | 26932317 | ITF only; padding vs check digit not learned yet: 26932317 |
| psa-26932317 | 2016 (back ITF, no QR) | machine | needs_review | 26932317 | 26932317 | ITF only; padding vs check digit not learned yet: 26932317 |
| cgc-3750599206 | 2020-23 OG blue | native | needs_review | 1995965624 | 3750599206 | ocr only - verify by eye |
| other-8008367 | SGC tuxedo | native | no_read | None | 8008367 | nothing decoded |
| other-8008367 | SGC tuxedo | native (proposed) | no_read | None | 8008367 |  |
| cgc-4067281028 | 2020-23 OG blue | native | no_read | None | 4067281028 | nothing decoded |
| cgc-4067281028 | 2020-23 OG blue | machine | no_read | None | 4067281028 | nothing decoded |
| cgc-1401012893129 | 2023+ pristine gold | native | ok | 140101289312 | 1401012893129 |  |
| cgc-1401012893129 | 2023+ pristine gold | machine | ok | 140101289312 | 1401012893129 |  |
| cgc-3931864027 | 2020-23 OG blue | native | no_read | None | 3931864027 | nothing decoded |
| cgc-3931864027 | 2020-23 OG blue | machine | no_read | None | 3931864027 | nothing decoded |
| cgc-3805531090 | 2020-23 OG blue | native | no_read | None | 3805531090 | nothing decoded |
| cgc-3805531090 | 2020-23 OG blue | machine | no_read | None | 3805531090 | nothing decoded |
| cgc-4308773015(press) | 2023+ standard | native | no_read | None | 4308773015 | nothing decoded |
| cgc-4308773015(press) | 2023+ standard | native (proposed) | needs_review | None | 4308773015 | CGC label, QR without a cert |
| cgc-6151387001(press) | 2023+ standard | native | no_read | None | 6151387001 | nothing decoded |
| cgc-6151387001(press) | 2023+ standard | native (proposed) | needs_review | None | 6151387001 | CGC label, QR without a cert |

### Every wrong-cert read (per frame, current parser)

| file | mode/frame | symbology | raw payload | parsed cert | truth |
|---|---|---|---|---|---|
| auctions/fc_27435764_0.jpg | native | Code128 | `09435764` | 9435764 | 27435764 |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img2.jpg | native | QRCode | `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` | 140101289312 | 1401012893129 |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img2.jpg | machine/hover | QRCode | `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` | 140101289312 | 1401012893129 |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img2.jpg | machine/held1 | QRCode | `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` | 140101289312 | 1401012893129 |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img2.jpg | machine/held1 | QRCode | `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` | 140101289312 | 1401012893129 |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img2.jpg | machine/held2 | QRCode | `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` | 140101289312 | 1401012893129 |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img2.jpg | machine/held_glare | QRCode | `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` | 140101289312 | 1401012893129 |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img2.jpg | machine/held_glare | QRCode | `HTTPS://WWW.CGCCARDS.COM/CERTLOOKUP/1401012893129/10_0/` | 140101289312 | 1401012893129 |

### Every unparsed payload (verbatim, symbology:text)

| file | mode/frame | unparsed |
|---|---|---|
| auctions/fc_28941258_0.jpg | machine/station_glare | `ITF:289412` |
| auctions/ms_1926130_1.jpg | native | `QRCode:https://www.cgccomics.com/certlookup/3750599206/9_0` ; `Code128:47140890000000003750599206` |
| cgc/official/unique-identification.png | native | `QRCode:HTTPS://WWW.CGCCOMICS.COM/CERTLOOKUP/0100000001/0_0` |
| cgc/news/cgc_news12803_charizard_1ed_back.png | native | `QRCode:https://www.cgccards.com/certlookup/` |
| cgc/news/cgc_news_jp_base_charizard_4308773015_back.png | native | `QRCode:https://www.cgccards.com/certlookup/` |
| cgc/news/cgc_news_rayquaza_goldstar_6151387001_back.png | native | `QRCode:https://www.cgccards.com/certlookup/` |
| cgc/news/cgc_official_2020_OG_holder_mockup_charizard_back.jpg | native | `QRCode:cgccomics.com` |
| cgc/fanatics/fc_1999_pokemon_base_set_rattata_61_cgc_10_pristine_img2.jpg | native | `Code128:0047064500000000004190928178` |
| cgc/fanatics/fc_1999_pokemon_base_set_rattata_61_cgc_10_pristine_img2.jpg | machine/hover | `Code128:0047064500000000004190928178` |
| cgc/fanatics/fc_1999_pokemon_base_set_rattata_61_cgc_10_pristine_img2.jpg | machine/held1 | `Code128:0047064500000000004190928178` |
| cgc/fanatics/fc_1999_pokemon_base_set_rattata_61_cgc_10_pristine_img2.jpg | machine/held2 | `Code128:0047064500000000004190928178` |
| cgc/fanatics/fc_1999_pokemon_base_set_rattata_61_cgc_10_pristine_img2.jpg | machine/held_glare | `Code128:0047064500000000004190928178` |
| cgc/fanatics/fc_2002_pokemon_expedition_cyndaquil_105_cgc_85_nm_mt_img2.jpg | native | `QRCode:https://www.cgccomics.com/certlookup/4067281028/8_5` ; `Code128:47319985000000004067281028` |
| cgc/fanatics/fc_2002_pokemon_expedition_cyndaquil_105_cgc_85_nm_mt_img2.jpg | machine/hover | `QRCode:https://www.cgccomics.com/certlookup/4067281028/8_5` ; `Code128:47319985000000004067281028` |
| cgc/fanatics/fc_2002_pokemon_expedition_cyndaquil_105_cgc_85_nm_mt_img2.jpg | machine/held1 | `QRCode:https://www.cgccomics.com/certlookup/4067281028/8_5` ; `Code128:47319985000000004067281028` |
| cgc/fanatics/fc_2002_pokemon_expedition_cyndaquil_105_cgc_85_nm_mt_img2.jpg | machine/held2 | `QRCode:https://www.cgccomics.com/certlookup/4067281028/8_5` ; `Code128:47319985000000004067281028` |
| cgc/fanatics/fc_2002_pokemon_expedition_cyndaquil_105_cgc_85_nm_mt_img2.jpg | machine/held_glare | `QRCode:https://www.cgccomics.com/certlookup/4067281028/8_5` ; `Code128:47319985000000004067281028` |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img1.jpg | machine/station1 | `Code128:1401012893129` |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img1.jpg | machine/station2 | `Code128:1401012893129` |
| cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img1.jpg | machine/station_glare | `Code128:1401012893129` |
| cgc/fanatics/fc_2009_pokemon_platinum_holo_palkia_g_12_cgc_85_nm_mt_img2.jpg | native | `QRCode:https://www.cgccomics.com/certlookup/3931864027/8_5` ; `Code128:48298585000000003931864027` |
| cgc/fanatics/fc_2009_pokemon_platinum_holo_palkia_g_12_cgc_85_nm_mt_img2.jpg | machine/hover | `QRCode:https://www.cgccomics.com/certlookup/3931864027/8_5` ; `Code128:48298585000000003931864027` |
| cgc/fanatics/fc_2009_pokemon_platinum_holo_palkia_g_12_cgc_85_nm_mt_img2.jpg | machine/held1 | `QRCode:https://www.cgccomics.com/certlookup/3931864027/8_5` ; `Code128:48298585000000003931864027` |
| cgc/fanatics/fc_2009_pokemon_platinum_holo_palkia_g_12_cgc_85_nm_mt_img2.jpg | machine/held2 | `QRCode:https://www.cgccomics.com/certlookup/3931864027/8_5` ; `Code128:48298585000000003931864027` |
| cgc/fanatics/fc_2009_pokemon_platinum_holo_palkia_g_12_cgc_85_nm_mt_img2.jpg | machine/held_glare | `QRCode:https://www.cgccomics.com/certlookup/3931864027/8_5` ; `Code128:48298585000000003931864027` |
| cgc/fanatics/fc_2003_pokemon_skyridge_holo_alakazam_h1_cgc_7_nrmt_img2.jpg | native | `QRCode:https://www.cgccomics.com/certlookup/3805531090/7_0` |
| cgc/fanatics/fc_2003_pokemon_skyridge_holo_alakazam_h1_cgc_7_nrmt_img2.jpg | machine/hover | `QRCode:https://www.cgccomics.com/certlookup/3805531090/7_0` ; `Code128:47363270956575753805531090` |
| cgc/fanatics/fc_2003_pokemon_skyridge_holo_alakazam_h1_cgc_7_nrmt_img2.jpg | machine/held1 | `QRCode:https://www.cgccomics.com/certlookup/3805531090/7_0` ; `Code128:47363270956575753805531090` |
| cgc/fanatics/fc_2003_pokemon_skyridge_holo_alakazam_h1_cgc_7_nrmt_img2.jpg | machine/held2 | `QRCode:https://www.cgccomics.com/certlookup/3805531090/7_0` ; `Code128:47363270956575753805531090` |
| cgc/fanatics/fc_2003_pokemon_skyridge_holo_alakazam_h1_cgc_7_nrmt_img2.jpg | machine/held_glare | `QRCode:https://www.cgccomics.com/certlookup/3805531090/7_0` ; `Code128:47363270956575753805531090` |
| reference/cgc2020_screenshot_label_detail_33.jpg | native | `QRCode:http://cgccomics.com/verify` |

### Front OCR (ocr_digits, the runner's only independent check of an ITF-only read)

| era | n fronts | native: hit / other digits / nothing | median s | machine station2: hit / other / nothing | median s | max s |
|---|---|---|---|---|---|---|
| BGS BGS silver | 1 | 0 / 0 / 1 | 34.4 | 0 / 0 / 1 | 38.7 | 38.7 |
| CGC 2020-23 OG blue | 5 | 0 / 0 / 5 | 32.7 | 0 / 0 / 4 | 30.6 | 31.6 |
| CGC 2023+ authentic | 2 | 0 / 0 / 2 | 35.6 | 0 / 0 / 2 | 30.4 | 30.4 |
| CGC 2023+ pristine gold | 5 | 0 / 0 / 5 | 33.4 | 0 / 0 / 5 | 31.1 | 32.7 |
| CGC 2023+ standard | 19 | 0 / 0 / 19 | 32.9 | 1 / 0 / 18 | 30.6 | 32.5 |
| PSA 2016 (back ITF, no QR) | 3 | 0 / 0 / 3 | 34.9 | 0 / 0 / 3 | 30.7 | 31.7 |
| PSA 2017+ lighthouse (QR+ITF) | 11 | 0 / 0 / 11 | 32.8 | 1 / 0 / 8 | 30.7 | 31.9 |
| PSA current (Code128) | 10 | 0 / 0 / 10 | 32.4 | 0 / 0 / 8 | 31.2 | 34.2 |
| PSA pre-2016 (no back code) | 7 | 0 / 0 / 7 | 33.2 | 0 / 0 / 7 | 31.1 | 33.1 |
| SGC SGC tuxedo | 1 | 0 / 0 / 1 | 30.6 | 0 / 0 / 0 | - | 0.0 |

#### Same OCR re-run with OMP_THREAD_LIMIT=1 (tesseract single-threaded), used for the slab verdicts above

| era | n fronts | native full image: hit / other / nothing | median s | station frame (runner): hit / other / nothing | median s | max s | label band only: hit / other / nothing | median s |
|---|---|---|---|---|---|---|---|---|
| BGS BGS silver | 1 | 0 / 0 / 1 | 12.5 | 1 / 0 / 0 | 3.3 | 3.3 | 0 / 1 / 0 | 1.8 |
| CGC 2020-23 OG blue | 5 | 0 / 2 / 3 | 8.8 | 0 / 0 / 4 | 3.2 | 3.6 | 0 / 0 / 4 | 1.4 |
| CGC 2023+ authentic | 2 | 1 / 0 / 1 | 7.8 | 2 / 0 / 0 | 2.4 | 2.8 | 2 / 0 / 0 | 0.9 |
| CGC 2023+ pristine gold | 5 | 4 / 1 / 0 | 6.2 | 4 / 1 / 0 | 2.3 | 3.6 | 4 / 1 / 0 | 1.3 |
| CGC 2023+ standard | 19 | 17 / 2 / 0 | 9.0 | 18 / 0 / 1 | 2.9 | 4.0 | 19 / 0 / 0 | 1.3 |
| PSA 2016 (back ITF, no QR) | 3 | 1 / 2 / 0 | 16.5 | 1 / 1 / 1 | 3.6 | 4.6 | 1 / 1 / 1 | 1.7 |
| PSA 2017+ lighthouse (QR+ITF) | 11 | 9 / 2 / 0 | 21.9 | 8 / 1 / 0 | 3.2 | 4.5 | 9 / 0 / 0 | 1.5 |
| PSA current (Code128) | 10 | 9 / 1 / 0 | 9.3 | 7 / 0 / 1 | 4.2 | 5.1 | 7 / 0 / 1 | 1.4 |
| PSA pre-2016 (no back code) | 7 | 3 / 3 / 1 | 24.8 | 6 / 1 / 0 | 4.2 | 4.5 | 6 / 0 / 1 | 1.8 |
| SGC SGC tuxedo | 1 | 0 / 0 / 1 | 3.0 | 0 / 0 / 0 | - | 0.0 | 0 / 0 / 0 | - |

OCR (OMP_THREAD_LIMIT=1) digit runs that were not the cert (verbatim): auctions/fc_0019865140_0.jpg station_label: ['0079865140'] (truth 19865140); auctions/fc_18805593_0.jpg native_full: ['20255550'] (truth 18805593); auctions/fc_19802594_0.jpg native_full: ['18802594'] (truth 19802594); auctions/fc_19802594_0.jpg station_full: ['19994103'] (truth 19802594); auctions/fc_19802621_0.jpg native_full: ['1995969899'] (truth 19802621); auctions/fc_25807907_0.jpg native_full: ['19952000'] (truth 25807907); auctions/fc_26932317_0.jpg native_full: ['20054106'] (truth 26932317); auctions/fc_26932317_0.jpg station_full: ['20054106'] (truth 26932317); auctions/fc_26932317_0.jpg station_label: ['20054106'] (truth 26932317); auctions/fc_54065407_0.jpg native_full: ['94065407'] (truth 54065407); auctions/fc_55039401_0.jpg native_full: ['95039401'] (truth 55039401); auctions/fc_55039401_0.jpg station_full: ['95039401'] (truth 55039401); auctions/ms_1926114_0.jpg native_full: ['1995969899'] (truth 112637770); auctions/ms_1926130_0.jpg native_full: ['1995965624'] (truth 3750599206); cgc/fanatics/fc_1999_pokemon_base_set_holo_venusaur_15_cgc_9_mint_img1.jpg native_full: ['1509500005'] (truth 3993936006); cgc/fanatics/fc_1999_pokemon_base_set_rattata_61_cgc_10_pristine_img1.jpg native_full: ['19959698'] (truth 4190928178); cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img1.jpg native_full: ['1401012893'] (truth 1401012893129); cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img1.jpg station_full: ['1401012893'] (truth 1401012893129); cgc/fanatics/fc_2016_pokemon_japanese_xy_pokekyun_collection_1st_ed_pikachu_10_cgc_10__img1.jpg station_label: ['1401012893'] (truth 1401012893129); cgc/fanatics/fc_2000_pokemon_japanese_neo_2_holo_dark_raichu_26_cgc_9_mint_img1.jpg native_full: ['204421945'] (truth 6009697083)

OCR digit runs that were not the cert (verbatim): 

### decode_frame time per frame (wall s / CPU s; machine shared with other jobs, load average 8-23 on 4 CPUs)

| frame | pixels decoded | n | wall median | wall p90 | wall max | CPU median | CPU p90 | CPU max | frames with a read: CPU median | frames with no read: CPU median |
|---|---|---|---|---|---|---|---|---|---|---|
| machine faceup_hover | 1632x2448 (ROI) | 58 | 0.3 | 2.1 | 8.5 | 0.1 | 1.6 | 1.8 | 0.1 | 1.6 |
| machine held1 | 1718x2448 (ROI) | 63 | 0.2 | 3.6 | 7.4 | 0.1 | 1.7 | 1.9 | 0.1 | 1.7 |
| machine held2 | 1718x2448 (ROI) | 63 | 0.2 | 5.2 | 8.3 | 0.1 | 1.7 | 1.9 | 0.1 | 1.7 |
| machine held_glare | 1718x2448 (ROI) | 63 | 0.2 | 5.5 | 7.9 | 0.1 | 1.7 | 1.8 | 0.1 | 1.7 |
| machine hover | 1632x2448 (ROI of 3264x2448) | 63 | 0.2 | 3.5 | 8.7 | 0.1 | 1.6 | 1.8 | 0.1 | 1.6 |
| machine station1 | 4608x2592 | 58 | 1.0 | 11.1 | 22.0 | 0.4 | 8.0 | 8.7 | 0.3 | 8.1 |
| machine station2 | 4608x2592 | 58 | 1.7 | 12.9 | 23.9 | 0.7 | 8.9 | 9.8 | 0.7 | 8.9 |
| machine station_glare | 4608x2592 | 58 | 0.9 | 10.4 | 32.4 | 0.5 | 7.9 | 9.3 | 0.4 | 7.8 |
| native back | ~2900x4900 | 64 | 3.5 | 48.7 | 62.0 | 0.7 | 10.3 | 13.0 | 0.6 | 9.8 |
| native front | ~2900x4900 | 64 | 3.6 | 44.8 | 53.8 | 0.7 | 9.4 | 10.3 | 0.6 | 9.4 |

### Face-down check from above (runner._check_face_down, 'stop' mode = before any learned reference exists)

| grader | era | n | face-DOWN slab (head sees back label): current | face-UP slab (head sees front label): current | proposed rule, face-down | proposed rule, face-up |
|---|---|---|---|---|---|---|
| BGS | BGS silver (machine) | 1 | 1x STOP: no PSA back-label QR was seen from above | 1x STOP: no PSA back-label QR was seen from above | 1x unknown | 1x unknown |
| CGC | 2020-23 OG blue (machine) | 4 | 3x STOP: no PSA back-label QR was seen from above; 1x STOP: a CGC code is visible from above, and those sit on the FRONT label | 4x STOP: no PSA back-label QR was seen from above | 4x down | 4x unknown |
| CGC | 2023+ authentic (machine) | 2 | 2x STOP: no PSA back-label QR was seen from above | 2x STOP: a CGC code is visible from above, and those sit on the FRONT label | 2x unknown | 2x up |
| CGC | 2023+ pristine gold (machine) | 5 | 5x STOP: a CGC code is visible from above, and those sit on the FRONT label | 5x STOP: no PSA back-label QR was seen from above | 5x down | 4x up; 1x unknown |
| CGC | 2023+ standard (machine) | 19 | 19x STOP: a CGC code is visible from above, and those sit on the FRONT label | 19x STOP: no PSA back-label QR was seen from above | 19x down | 14x up; 5x unknown |
| PSA | 2016 (back ITF, no QR) (machine) | 3 | 3x STOP: no PSA back-label QR was seen from above | 3x STOP: no PSA back-label QR was seen from above | 3x unknown | 3x unknown |
| PSA | 2017+ lighthouse (QR+ITF) (machine) | 9 | 9x pass:qr | 9x STOP: no PSA back-label QR was seen from above | 9x down | 9x unknown |
| PSA | current (Code128) (machine) | 8 | 8x pass:qr | 8x STOP: no PSA back-label QR was seen from above | 8x down | 8x unknown |
| PSA | pre-2016 (no back code) (machine) | 7 | 7x STOP: no PSA back-label QR was seen from above | 7x STOP: no PSA back-label QR was seen from above | 7x unknown | 7x unknown |
| SGC | SGC tuxedo (native) | 1 | 1x STOP: no PSA back-label QR was seen from above | 1x STOP: no PSA back-label QR was seen from above | 1x unknown | 1x unknown |
| CGC | 2023+ standard (extra) (native) | 2 | 2x STOP: no PSA back-label QR was seen from above | 2x STOP: no PSA back-label QR was seen from above | 2x down | 2x unknown |
| PSA | 2016 (back ITF, no QR) (extra) (native) | 1 | 1x STOP: no PSA back-label QR was seen from above | 1x STOP: no PSA back-label QR was seen from above | 1x unknown | 1x unknown |
| PSA | 2017+ lighthouse (QR+ITF) (extra) (native) | 1 | 1x STOP: no PSA back-label QR was seen from above | 1x STOP: no PSA back-label QR was seen from above | 1x unknown | 1x unknown |
| PSA | pre-2016 (no back code) (extra) (native) | 2 | 2x STOP: no PSA back-label QR was seen from above | 2x STOP: no PSA back-label QR was seen from above | 2x unknown | 2x unknown |

ItfModel evidence after the whole batch: {'native': {}, 'machine': {}, 'native_mode': None, 'machine_mode': None}

QR cross-check of manifest certs: 54 images agree; disagreements: cgc/official/unique-identification.png: DISAGREE qr=['100000001'] manifest=None

### Symbols zxing-cpp finds in the native image (raw audit at 1.0x/0.5x) that decode_frame did not return


### Machine frames: symbols raw zxing-cpp decodes in the frame (plain or CLAHE) that decode_frame did not return (early exit)

- auctions/fc_54065407_1.jpg held_glare: QRCode:`https://www.psacard.com/cert/54065407/`  (decode_frame returned: ITF:54065407)
- auctions/ms_1926138_1.jpg hover: Code128:`102978964`  (decode_frame returned: QRCode:https://www.psacard.com/cert/102978964/)
