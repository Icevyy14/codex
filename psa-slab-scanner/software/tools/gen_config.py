"""Write config/machine.toml from the CAD layout (cad/layout.py), then prove it loads back identically.

Run from the software/ folder:   python -m tools.gen_config            (writes config/machine.toml)
                                 python -m tools.gen_config --check    (only compare an existing file)

machine.toml is generated: never edit it. Your own values (calibration, serial port, camera
settings, a custom barcode regex) go in config/calibration.toml, which overrides any key and is
never touched by this tool.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

from slabscan.config import CALIBRATION_KEYS, Config, dumps, from_layout, load

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "config" / "machine.toml"


def differences(a: Config, b: Config, ignore=CALIBRATION_KEYS) -> list[str]:
    out = []
    for f in dataclasses.fields(Config):
        if f.name in ignore:
            continue
        va, vb = getattr(a, f.name), getattr(b, f.name)
        if va != vb:
            out.append(f"{f.name}: {va!r} != {vb!r}")
    return out


def generate(out: Path) -> Config:
    cfg = from_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".toml.tmp")
    tmp.write_text(dumps(cfg))
    back = load(tmp)
    diff = differences(cfg, back)
    if diff:
        tmp.unlink()
        raise SystemExit("machine.toml does not round-trip (nothing written):\n  " + "\n  ".join(diff))
    tmp.replace(out)
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="compare the existing file with the CAD layout; exit 1 if it is stale")
    a = ap.parse_args(argv)
    if a.check:
        if not a.out.exists():
            print(f"{a.out} missing - run python -m tools.gen_config")
            return 1
        diff = differences(from_layout(), load(a.out))
        print("up to date" if not diff else "STALE (regenerate):\n  " + "\n  ".join(diff))
        return 1 if diff else 0
    cfg = generate(a.out)
    cal = a.out.parent / "calibration.toml"
    print(f"wrote {a.out}: {len(cfg.pockets)} pockets (x {cfg.pockets[0].x}..{cfg.pockets[-1].x}), station at x {cfg.station_xy[0]}, "
          f"capacity {cfg.capacity}, safe heights {cfg.c_safe_empty}/{cfg.c_safe_loaded}, read height {cfg.station_read_c}")
    print(f"round-trip OK. Calibration overrides: {cal} ({'present' if cal.exists() else 'not yet - run calibrate z / calibrate x'})")
    if cal.exists():
        load(a.out, cal)  # raises on an unknown key in calibration.toml
    return 0


if __name__ == "__main__":
    sys.exit(main())
