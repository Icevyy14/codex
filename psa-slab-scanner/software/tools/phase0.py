"""Phase 0: prove the cameras read YOUR slabs before buying any motion parts.

Put a slab face-down in the Phase 0 jig (front toward the bottom camera, label end toward you),
press Enter, repeat for 30-50 slabs (mix old and new PSA labels, and a few CGC).
Every capture is saved, and a CSV records exactly what each camera decoded (symbology + raw
payload), which settles the open questions about PSA's barcode format.

Run on the Pi:   python -m tools.phase0 --out phase0_results
Without cameras (demo with synthetic labels):   python -m tools.phase0 --sim 10
"""

from __future__ import annotations

import argparse
import csv
import time
from collections import Counter
from pathlib import Path

import cv2

from slabscan.certs import ItfModel, consensus
from slabscan.decode import decode_frame


def open_cameras(args):
    if args.sim:
        import random

        from slabscan.sim import Degrade, slab_view

        rng = random.Random(1)

        class _Sim:
            def __init__(self, side):
                self.side, self.cert = side, ""

            def capture(self):
                return slab_view(self.cert, self.side, Degrade(mm_per_px=0.05 if self.side == "back" else 0.04), seed=rng.randint(0, 999))

        head, station = _Sim("back"), _Sim("front")
        return head, station
    from slabscan.camera import PiCamera, UsbCamera

    head = UsbCamera(args.head_device, "head", size=(3264, 2448))
    station = PiCamera(0, "station", lens_position=args.lens_position)
    return head, station


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="phase0_results")
    ap.add_argument("--head-device", type=int, default=0)
    ap.add_argument("--lens-position", type=float, default=7.1, help="Camera Module 3 dioptres; 1/0.14 m = 7.1")
    ap.add_argument("--frames", type=int, default=2)
    ap.add_argument("--sim", type=int, default=0, help="run N synthetic slabs instead of real cameras")
    a = ap.parse_args(argv)
    out = Path(a.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    head, station = open_cameras(a)
    itf = ItfModel()
    rows = []
    f = (out / "phase0.csv").open("w", newline="")
    w = csv.writer(f)
    w.writerow(["n", "printed_cert_typed", "back_reads", "front_reads", "verdict", "cert", "note", "back_ms", "front_ms"])
    n = 0
    sim_certs = [str(148069831 + 7919 * i) for i in range(a.sim)]
    while True:
        n += 1
        if a.sim:
            if n > a.sim:
                break
            typed = sim_certs[n - 1]
            head.cert = station.cert = typed
        else:
            typed = input(f"\nSlab {n}: place it, type the printed cert (or just Enter to skip typing, 'q' to finish): ").strip()
            if typed.lower() == "q":
                break
        res = {}
        for name, cam, side in (("back", head, "back"), ("front", station, "front")):
            t0 = time.monotonic()
            reads, unparsed = [], []
            for k in range(a.frames):
                img = cam.capture()
                cv2.imwrite(str(out / "images" / f"{n:03d}_{name}_{k}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                r, u = decode_frame(img, side)
                reads += r
                unparsed += u
            res[name] = (reads, unparsed, (time.monotonic() - t0) * 1000)
        allreads = res["back"][0] + res["front"][0]
        v = consensus(allreads, itf)
        fmt = lambda rs, us: "; ".join([f"{r.symbology}:{r.raw}" for r in rs] + [f"?{u}" for u in us])  # noqa: E731
        row = [n, typed, fmt(*res["back"][:2]), fmt(*res["front"][:2]), v.status, v.cert or "", v.note, round(res["back"][2]), round(res["front"][2])]
        w.writerow(row)
        f.flush()
        rows.append((typed, v, res))
        match = "" if not typed else (" MATCH" if v.cert == typed.lstrip("0") else f" MISMATCH (typed {typed})")
        print(f"  back: {row[2] or '-'}\n  front: {row[3] or '-'}\n  => {v.status} {v.cert or ''} {v.note}{match}")
    f.close()
    total = len(rows)
    if not total:
        return 0
    ok = sum(1 for _, v, _ in rows if v.status == "ok")
    back_any = sum(1 for _, _, r in rows if r["back"][0])
    front_any = sum(1 for _, _, r in rows if r["front"][0])
    syms = Counter(r.symbology for _, _, res in rows for side in ("back", "front") for r in res[side][0])
    typed_rows = [(t, v) for t, v, _ in rows if t]
    wrong = sum(1 for t, v in typed_rows if v.cert and v.cert != t.lstrip("0"))
    report = [
        f"slabs: {total}",
        f"confident read (ok): {ok}/{total} = {100 * ok / total:.0f}%",
        f"back camera read something: {back_any}/{total}; front camera: {front_any}/{total}",
        f"symbologies seen: {dict(syms)}",
        f"ITF format learned: {itf.mode} (evidence {dict(itf.evidence)})",
        f"WRONG certs vs what you typed: {wrong} of {len(typed_rows)} typed  <- must be 0",
        "GO if: ok >= 95% and wrong == 0. Otherwise send phase0.csv + images for tuning before building.",
    ]
    (out / "phase0_report.txt").write_text("\n".join(report) + "\n")
    print("\n" + "\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
