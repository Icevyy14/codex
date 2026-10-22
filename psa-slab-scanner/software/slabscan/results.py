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

COLUMNS = ["batch_id", "position", "source_pocket", "source_index", "out_pocket", "out_index", "cert", "grader", "status", "sources", "raw_payload", "note", "image_front", "image_back", "scanned_at",
           "face_down"]  # how the slab was proven face-down before the cup touched it: qr | operator | learned(score) | off


@dataclass
class SlabResult:
    position: int  # 1-based order the machine visited
    source_pocket: int  # pocket the slab was picked from
    source_index: int  # 1 = top of the source stack at pick time
    out_pocket: int  # pocket it was placed in (exception pocket for rejects)
    out_index: int  # 1 = bottom of the output stack
    verdict: Verdict
    image_front: str = ""
    image_back: str = ""
    scanned_at: float = field(default_factory=time.time)
    face_down: str = ""  # qr | operator | learned(0.93) | off ("" = not known, e.g. an unread slab under a double pick)


def _row_values(batch_id: str, r: SlabResult) -> list:
    v = r.verdict
    return [
        batch_id, r.position, r.source_pocket, r.source_index, r.out_pocket, r.out_index,
        v.cert or "", v.grader, v.status, "+".join(v.sources), v.raw, v.note, r.image_front, r.image_back,
        time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(r.scanned_at)), r.face_down,
    ]


def read_rows(csv_path: Path) -> list[SlabResult]:
    """Parse a certs.csv back into SlabResults. A torn last row (power cut mid-write) is dropped."""
    out: list[SlabResult] = []
    with Path(csv_path).open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                pos = int(row["position"])
                sources = tuple(s for s in (row.get("sources") or "").split("+") if s)
                verdict = Verdict(row["status"], row["cert"] or None, sources, row.get("note") or "", row.get("grader") or "PSA", row.get("raw_payload") or "")
                try:
                    at = time.mktime(time.strptime(row["scanned_at"], "%Y-%m-%dT%H:%M:%S"))
                except (TypeError, ValueError):
                    at = time.time()
                out.append(SlabResult(pos, int(row["source_pocket"]), int(row["source_index"]), int(row["out_pocket"]), int(row["out_index"]), verdict,
                                      row.get("image_front") or "", row.get("image_back") or "", at, row.get("face_down") or ""))
            except (KeyError, TypeError, ValueError):
                continue
    return out


class BatchWriter:
    """Appends rows as the machine runs, so a crash or power cut loses nothing.

    ``resume=True`` reopens an existing batch folder: the rows already in certs.csv are loaded
    (and the file rewritten cleanly, dropping a torn last line) so new rows append after them.
    """

    def __init__(self, out_dir: Path, batch_id: str | None = None, resume: bool = False):
        self.batch_id = batch_id or time.strftime("%Y%m%d-%H%M%S")
        self.dir = Path(out_dir) / self.batch_id
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "images").mkdir(exist_ok=True)
        self.csv_path = self.dir / "certs.csv"
        self._rows: list[SlabResult] = []
        if resume and self.csv_path.exists():
            self._rows = read_rows(self.csv_path)
        tmp = self.csv_path.with_suffix(".csv.tmp")
        with tmp.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            for r in self._rows:
                w.writerow(_row_values(self.batch_id, r))
        tmp.replace(self.csv_path)

    @classmethod
    def reopen(cls, batch_dir: Path) -> "BatchWriter":
        batch_dir = Path(batch_dir)
        if not batch_dir.is_dir():
            raise FileNotFoundError(f"no batch folder {batch_dir}")
        return cls(batch_dir.parent, batch_dir.name, resume=True)

    @property
    def rows(self) -> list[SlabResult]:
        return list(self._rows)

    def add(self, r: SlabResult) -> None:
        self._rows.append(r)
        with self.csv_path.open("a", newline="") as f:
            csv.writer(f).writerow(_row_values(self.batch_id, r))

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
                {"position": r.position, "out_pocket": r.out_pocket, "out_index": r.out_index, **asdict(r.verdict)}
                for r in self._rows
                if r.verdict.status != "ok"
            ],
            **(extra or {}),
        }
        (self.dir / "summary.json").write_text(json.dumps(summary, indent=2))
        (self.dir / "report.html").write_text(self.html(summary))
        # Plain list for pasting into PSA / spreadsheets: one cert per line, machine order.
        certs = [r.verdict.cert for r in self._rows if r.verdict.cert and r.verdict.status == "ok"]
        (self.dir / "certs.txt").write_text("\n".join(certs) + ("\n" if certs else ""))
        return summary

    def html(self, summary: dict) -> str:
        """One self-contained page: counts, then every slab with its label photo. Open it on any device."""
        import html as h

        css = ("body{font:14px system-ui,sans-serif;margin:16px;background:#fafafa;color:#222}"
               "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}"
               ".ok{color:#176b2c}.bad{color:#a8231a;font-weight:600}img{max-width:240px;border-radius:4px}")
        rows = []
        for r in self._rows:
            v = r.verdict
            cls = "ok" if v.status == "ok" else "bad"
            imgs = "".join(f'<img loading="lazy" src="{h.escape(p)}">' for p in (r.image_back, r.image_front) if p)
            fd = h.escape(r.face_down)
            fd = f"<b>{fd}</b> - check the photo" if r.face_down.startswith("learned") else fd
            rows.append(f"<tr><td>{r.position}</td><td>P{r.out_pocket} #{r.out_index}</td><td>{h.escape(v.cert or '')}</td><td>{h.escape(v.grader)}</td>"
                        f"<td class={cls}>{h.escape(v.status)}</td><td>{h.escape(v.note)}</td><td>{fd}</td><td>{imgs}</td></tr>")
        counts = ", ".join(f"{k}: {n}" for k, n in summary.get("status_counts", {}).items())
        return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Batch {h.escape(self.batch_id)}</title>"
                f"<style>{css}</style><h1>Batch {h.escape(self.batch_id)}</h1><p>{summary.get('slabs_visited', 0)} slabs. {h.escape(counts)}</p>"
                "<p>Output position: P = pocket, # = position counted from the bottom of that stack. Face-down: how the slab was proven "
                "face-down before the cup touched it (qr = back-label QR, operator = you confirmed it, learned = its card window matched "
                "the card backs of proven slabs, with the score; off = no check).</p>"
                "<table><tr><th>#</th><th>Where</th><th>Cert</th><th>Grader</th><th>Status</th><th>Note</th><th>Face-down</th><th>Label</th></tr>"
                + "".join(rows) + "</table>")
