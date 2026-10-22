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

CERTS = ["148069831", "45210987", "102938475", "07766554", "158084833"]
RES = [0.05, 0.08, 0.11, 0.14, 0.18]
BLUR = [0.6, 1.2, 2.0]
GLARE = [0.0, 0.7, 1.2]
CASES = [("front", "ITF", 0.25), ("front", "ITF", 0.19), ("front", "Code128", 0.25), ("front", "Code39", 0.19), ("back", "ITF", 0.25)]


def run(trials_per_cell: int = len(CERTS)) -> list[tuple]:
    rows = []
    for (side, sym, mod), res, blur, glare in itertools.product(CASES, RES, BLUR, GLARE):
        ok = 0
        for i in range(trials_per_cell):
            cert = CERTS[i % len(CERTS)]
            deg = Degrade(mm_per_px=res, blur_px=blur, glare=glare, glare_pos=(0.2 + 0.15 * i, 0.5), tilt_deg=3 + i, rotate_deg=-2 + i)
            reads, _ = decode_frame(slab_view(cert, side, deg, sym, mod, seed=i), side, allow_ocr=False)
            ok += any(r.cert == canonical(cert) for r in reads)
            assert not any(r.cert != canonical(cert) for r in reads), "misread!"
        rows.append((side, sym, mod, res, blur, glare, ok, trials_per_cell))
    return rows


if __name__ == "__main__":
    rows = run()
    print("side   sym     module_mm mm/px blur glare  decoded")
    for side, sym, mod, res, blur, glare, ok, n in rows:
        print(f"{side:6} {sym:7} {mod:9} {res:5} {blur:4} {glare:5}  {ok}/{n}")
    sys.exit(0)
