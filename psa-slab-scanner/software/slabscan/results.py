"""Batch results: one CSV row per slab position, plus a JSON summary.

Columns are stable so the CSV can be imported into a spreadsheet or an inventory
database (e.g. a Supabase table) without editing.
"""

from __future__ import annotations

import csv
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .certs import Verdict

COLUMNS = ["batch_id", "position", "rack", "row", "slot", "cert", "status", "sources", "note", "image_front", "image_back", "scanned_at"]


@dataclass
class SlabResult:
    position: int  # 1-based order the machine visited
    rack: int
    row: int
    slot: int
    verdict: Verdict
    image_front: str = ""
    image_back: str = ""
    scanned_at: float = field(default_factory=time.time)


class BatchWriter:
    """Appends rows as the machine runs, so a crash or power cut loses nothing."""

    def __init__(self, out_dir: Path, batch_id: str | None = None):
        self.batch_id = batch_id or time.strftime("%Y%m%d-%H%M%S")
        self.dir = Path(out_dir) / self.batch_id
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "images").mkdir(exist_ok=True)
        self.csv_path = self.dir / "certs.csv"
        self._rows: list[SlabResult] = []
        with self.csv_path.open("w", newline="") as f:
            csv.writer(f).writerow(COLUMNS)

    def add(self, r: SlabResult) -> None:
        self._rows.append(r)
        v = r.verdict
        with self.csv_path.open("a", newline="") as f:
            csv.writer(f).writerow([
                self.batch_id, r.position, r.rack, r.row, r.slot, v.cert or "", v.status,
                "+".join(v.sources), v.note, r.image_front, r.image_back,
                time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(r.scanned_at)),
            ])

    def duplicates(self) -> dict[str, list[int]]:
        seen: dict[str, list[int]] = {}
        for r in self._rows:
            if r.verdict.cert and r.verdict.status in ("ok", "needs_review"):
                seen.setdefault(r.verdict.cert, []).append(r.position)
        return {c: p for c, p in seen.items() if len(p) > 1}

    def finish(self, extra: dict | None = None) -> dict:
        counts = Counter(r.verdict.status for r in self._rows)
        summary = {
            "batch_id": self.batch_id,
            "slabs_visited": len(self._rows),
            "status_counts": dict(counts),
            "duplicates": self.duplicates(),
            "needs_attention": [
                {"position": r.position, "rack": r.rack, "row": r.row, "slot": r.slot, **asdict(r.verdict)}
                for r in self._rows
                if r.verdict.status != "ok"
            ],
            **(extra or {}),
        }
        (self.dir / "summary.json").write_text(json.dumps(summary, indent=2))
        # Plain list for pasting into PSA / spreadsheets: one cert per line, machine order.
        certs = [r.verdict.cert for r in self._rows if r.verdict.cert and r.verdict.status == "ok"]
        (self.dir / "certs.txt").write_text("\n".join(certs) + ("\n" if certs else ""))
        return summary
