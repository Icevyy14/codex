"""Decode-rate sweep over camera resolution, blur, glare and symbology.

Answers "how good must the camera be?" before any hardware is bought.
Run:  python -m tools.decode_sweep   (from the software/ folder)
"""

from __future__ import annotations

import itertools
import sys

from slabscan.certs import canonical
from slabscan.decode import decode_frame
from slabscan.sim import Degrade, slab_view

# (side, grader, era, module_mm, certs): the codes real labels carry (sim.label_codes); module_mm overrides the 1D module
CERTS = {"current": ["148069831", "102938475", "158084833", "27435764"], "2017+": ["45210987", "26275088", "7766554"],
         "2023+": ["6003997046", "1401012893129", "4123456001"]}
RES = [0.05, 0.08, 0.11, 0.14, 0.18]
BLUR = [0.6, 1.2, 2.0]
GLARE = [0.0, 0.7, 1.2]
CASES = [("front", "PSA", "2017+", 0.25), ("front", "PSA", "2017+", 0.19), ("front", "PSA", "current", 0.25), ("front", "CGC", "2023+", 0.2),
         ("back", "PSA", "2017+", 0.25), ("back", "CGC", "2023+", None)]


def run(trials_per_cell: int = 4) -> list[tuple]:
    rows = []
    for (side, grader, era, mod), res, blur, glare in itertools.product(CASES, RES, BLUR, GLARE):
        ok = 0
        for i in range(trials_per_cell):
            certs = CERTS[era]
            cert = certs[i % len(certs)]
            deg = Degrade(mm_per_px=res, blur_px=blur, glare=glare, glare_pos=(0.2 + 0.15 * i, 0.5), tilt_deg=3 + i, rotate_deg=-2 + i)
            reads, _ = decode_frame(slab_view(cert, side, deg, grader, era, mod, seed=i), side, allow_ocr=False)
            ok += any(r.cert == canonical(cert) for r in reads)
            assert not any(r.cert != canonical(cert) for r in reads), "misread!"
        rows.append((side, f"{grader} {era}", mod, res, blur, glare, ok, trials_per_cell))
    return rows


if __name__ == "__main__":
    rows = run()
    print("side   label         module_mm mm/px blur glare  decoded")
    for side, label, mod, res, blur, glare, ok, n in rows:
        print(f"{side:6} {label:13} {mod or '-':9} {res:5} {blur:4} {glare:5}  {ok}/{n}")
    sys.exit(0)
