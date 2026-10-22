"""Optional enrichment: cert number -> card details via the PSA Public API.

Not needed to produce the cert list. The scan itself never calls the network.

PSA documents 100 calls/day for free accounts, and since mid-2026 many new tokens get
403 "limited to approved customers" until PSA approves them. So lookups are:
  * cached in a local SQLite file: found certs and invalid numbers forever (a cert's details don't
    change; population does), "no data" and error answers only for ``retry_days`` (a cert PSA has not
    indexed yet, or a passing server message, is asked again later),
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


def classify(payload) -> tuple[str, str]:
    """PSA answers 200 even when nothing matched; the body says which (PSA API documentation)."""
    if not isinstance(payload, dict):
        return "error", "unexpected answer"
    cert = payload.get("PSACert")
    if isinstance(cert, dict) and cert:
        return "ok", ""
    msg = str(payload.get("ServerMessage", ""))
    if payload.get("IsValidRequest") is False:
        return "invalid", msg or "invalid cert number"
    if "no data" in msg.lower():
        return "not_found", msg
    return "error", msg or json.dumps(payload)[:120]


FINAL = ("ok", "invalid")  # answers that never change; the others are asked again after retry_days


class PsaClient:
    def __init__(self, cache_path: Path, token: str | None = None, daily_limit: int = 100, min_interval_s: float = 1.0, retry_days: float = 7.0):
        self.token = token or os.environ.get("PSA_API_TOKEN", "")
        self.daily_limit = daily_limit
        self.min_interval_s = min_interval_s
        self.retry_days = retry_days
        self._last_call = 0.0
        self.db = sqlite3.connect(str(cache_path))
        self.db.execute("CREATE TABLE IF NOT EXISTS certs (cert TEXT PRIMARY KEY, fetched_at TEXT, payload TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS quota (day TEXT PRIMARY KEY, used INTEGER)")
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(certs)")}
        if "status" not in cols:  # cache files from before the status column: classified on read
            self.db.execute("ALTER TABLE certs ADD COLUMN status TEXT")
        self.db.commit()

    def _used_today(self) -> int:
        row = self.db.execute("SELECT used FROM quota WHERE day=?", (dt.date.today().isoformat(),)).fetchone()
        return row[0] if row else 0

    def _count_call(self) -> None:
        day = dt.date.today().isoformat()
        self.db.execute("INSERT INTO quota(day, used) VALUES(?, 1) ON CONFLICT(day) DO UPDATE SET used = used + 1", (day,))
        self.db.commit()

    def cached(self, cert: str, stale_ok: bool = False) -> dict | None:
        """The cached answer, or None. A 'not found' / error answer older than retry_days counts as
        missing (so it is looked up again), unless ``stale_ok``."""
        row = self.db.execute("SELECT payload, fetched_at, status FROM certs WHERE cert=?", (cert,)).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        status = row[2] or classify(payload)[0]
        if status in FINAL or stale_ok:
            return payload
        try:
            age = (dt.datetime.now() - dt.datetime.fromisoformat(row[1])).total_seconds() / 86400
        except (TypeError, ValueError):
            age = float("inf")
        return payload if age < self.retry_days else None

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
        self.db.execute("INSERT OR REPLACE INTO certs (cert, fetched_at, payload, status) VALUES(?,?,?,?)",
                        (cert, dt.datetime.now().isoformat(timespec="seconds"), json.dumps(payload), classify(payload)[0]))
        self.db.commit()
        return payload


def flatten(payload: dict) -> dict:
    """Pick the commonly useful fields; tolerate schema drift by falling back to raw keys."""
    c = payload.get("PSACert", payload) if isinstance(payload, dict) else {}
    keys = ["CertNumber", "Year", "Brand", "Category", "CardNumber", "Subject", "Variety", "CardGrade", "GradeDescription", "TotalPopulation", "PopulationHigher", "LabelType", "ReverseBarCode"]
    return {k: c.get(k, "") for k in keys}
