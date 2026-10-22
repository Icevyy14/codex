"""Optional enrichment: cert number -> card details via the PSA Public API.

Not needed to produce the cert list. The scan itself never calls the network.

PSA documents 100 calls/day for free accounts, and since mid-2026 many new tokens get
403 "limited to approved customers" until PSA approves them. So lookups are:
  * cached forever in a local SQLite file (a cert's details don't change; population does),
  * metered against a daily budget that persists across runs,
  * resumable: run ``python -m tools.enrich <batch dir>`` again tomorrow to continue.
Get a token at https://www.psacard.com/publicapi and put it in the PSA_API_TOKEN env var.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.psacard.com/publicapi/cert/GetByCertNumber/{cert}"


class QuotaExhausted(Exception):
    pass


class NotApproved(Exception):
    """Since mid-2026 PSA answers some valid tokens with 403 "limited to approved customers".
    Retrying cannot fix it; email collectors-apis@collectors.com."""


class PsaClient:
    def __init__(self, cache_path: Path, token: str | None = None, daily_limit: int = 100, min_interval_s: float = 1.0):
        self.token = token or os.environ.get("PSA_API_TOKEN", "")
        self.daily_limit = daily_limit
        self.min_interval_s = min_interval_s
        self._last_call = 0.0
        self.db = sqlite3.connect(str(cache_path))
        self.db.execute("CREATE TABLE IF NOT EXISTS certs (cert TEXT PRIMARY KEY, fetched_at TEXT, payload TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS quota (day TEXT PRIMARY KEY, used INTEGER)")
        self.db.commit()

    def _used_today(self) -> int:
        row = self.db.execute("SELECT used FROM quota WHERE day=?", (dt.date.today().isoformat(),)).fetchone()
        return row[0] if row else 0

    def _count_call(self) -> None:
        day = dt.date.today().isoformat()
        self.db.execute("INSERT INTO quota(day, used) VALUES(?, 1) ON CONFLICT(day) DO UPDATE SET used = used + 1", (day,))
        self.db.commit()

    def cached(self, cert: str) -> dict | None:
        row = self.db.execute("SELECT payload FROM certs WHERE cert=?", (cert,)).fetchone()
        return json.loads(row[0]) if row else None

    def lookup(self, cert: str) -> dict:
        hit = self.cached(cert)
        if hit is not None:
            return hit
        if not self.token:
            raise RuntimeError("PSA_API_TOKEN not set")
        if self._used_today() >= self.daily_limit:
            raise QuotaExhausted(f"daily PSA API budget of {self.daily_limit} used")
        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(API_URL.format(cert=cert), headers={"Authorization": f"bearer {self.token}", "Accept": "application/json"})
        self._count_call()
        self._last_call = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise QuotaExhausted("PSA API returned 429 (rate limited)") from e
            if e.code == 403:
                raise NotApproved("PSA API 403: account not approved - email collectors-apis@collectors.com") from e
            raise
        self.db.execute("INSERT OR REPLACE INTO certs VALUES(?,?,?)", (cert, dt.datetime.now().isoformat(timespec="seconds"), json.dumps(payload)))
        self.db.commit()
        return payload


def flatten(payload: dict) -> dict:
    """Pick the commonly useful fields; tolerate schema drift by falling back to raw keys."""
    c = payload.get("PSACert", payload) if isinstance(payload, dict) else {}
    keys = ["CertNumber", "Year", "Brand", "Category", "CardNumber", "Subject", "Variety", "CardGrade", "GradeDescription", "TotalPopulation", "PopulationHigher", "LabelType", "ReverseBarCode"]
    return {k: c.get(k, "") for k in keys}
