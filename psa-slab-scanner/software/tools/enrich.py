"""Optional: add card details (year, set, card, grade, population) to a batch from the PSA Public API.

    python -m tools.enrich batches/<id>            ->  batches/<id>/certs_enriched.csv

Never required: certs.csv is complete without it. Get a token at https://www.psacard.com/publicapi
and export it as PSA_API_TOKEN (or pass --token).

Limits it respects (see docs/RESEARCH.md):
  * free accounts get about 100 calls/day: calls are counted in a local SQLite file and the tool
    stops at --daily-limit; run it again tomorrow and it continues where it stopped;
  * found certs are cached forever (a cert's card never changes), so re-runs cost nothing; "no data"
    and error answers are asked again after --retry-days (PSA may not have indexed a new cert yet);
  * since mid-2026 many new tokens get 403 "limited to approved customers": the tool stops, keeps
    what it has, and tells you to email collectors-apis@collectors.com.
Only PSA certs are looked up (the PSA API cannot look up CGC certs).
"""

from __future__ import annotations

import argparse
import csv
import sys
import urllib.error
from pathlib import Path

from slabscan.psa_api import NotApproved, PsaClient, QuotaExhausted, classify, flatten

PSA_FIELDS = ["CertNumber", "Year", "Brand", "Category", "CardNumber", "Subject", "Variety", "CardGrade", "GradeDescription", "TotalPopulation", "PopulationHigher", "LabelType", "ReverseBarCode"]
EXTRA = ["enrich_status", "enrich_note"] + [f"psa_{k}" for k in PSA_FIELDS]


__all__ = ["classify", "enrich", "main"]  # classify now lives in slabscan.psa_api (the cache needs it)


def enrich(batch_dir: Path, token: str | None = None, daily_limit: int = 100, cache: Path | None = None, include_review: bool = False,
           max_calls: int | None = None, interval_s: float = 1.0, log=print, retry_days: float = 7.0) -> dict:
    batch_dir = Path(batch_dir)
    src = batch_dir / "certs.csv"
    if not src.exists():
        raise FileNotFoundError(f"{src} not found")
    with src.open(newline="") as f:
        reader = csv.DictReader(f)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    wanted_status = {"ok", "needs_review"} if include_review else {"ok"}
    todo: list[str] = []
    for r in rows:
        if r.get("cert") and r.get("status") in wanted_status and r.get("grader", "PSA") in ("PSA", "unknown") and r["cert"] not in todo:
            todo.append(r["cert"])
    client = PsaClient(cache or batch_dir.parent / "psa_cache.sqlite", token=token, daily_limit=daily_limit, min_interval_s=interval_s, retry_days=retry_days)
    results: dict[str, tuple[str, str, dict]] = {}
    blocked = ""
    calls = 0
    errors_in_row = 0
    for cert in todo:
        hit = client.cached(cert)
        if hit is not None:
            st, note = classify(hit)
            results[cert] = (st, note or "cached", hit)
            continue
        if blocked:
            stale = client.cached(cert, stale_ok=True)  # an old 'not found' is still the best answer we have
            results[cert] = (classify(stale)[0], "cached, could not re-check: " + blocked, stale) if stale is not None else ("pending", blocked, {})
            continue
        if max_calls is not None and calls >= max_calls:
            blocked = f"stopped at --max {max_calls} calls"
            results[cert] = ("pending", blocked, {})
            continue
        try:
            calls += 1
            payload = client.lookup(cert)
            st, note = classify(payload)
            results[cert] = (st, note, payload)
            errors_in_row = 0
        except QuotaExhausted as e:
            blocked = f"daily quota reached ({e}); run again tomorrow"
            results[cert] = ("pending", blocked, {})
        except NotApproved:
            blocked = "PSA API 403: token not approved yet - email collectors-apis@collectors.com"
            results[cert] = ("pending", blocked, {})
        except RuntimeError as e:  # no token
            blocked = str(e) + " - get one at https://www.psacard.com/publicapi and export PSA_API_TOKEN"
            results[cert] = ("pending", blocked, {})
        except urllib.error.HTTPError as e:
            errors_in_row += 1
            why = {401: "token rejected (401)", 404: "not found (404)", 500: "HTTP 500 - PSA uses this for invalid credentials, or its server failed"}.get(e.code, f"HTTP {e.code}")
            results[cert] = ("not_found" if e.code == 404 else "error", why, {})
            if e.code in (401, 500) and errors_in_row >= 2:
                blocked = why
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            blocked = f"no connection to api.psacard.com ({e}); the scan itself never needs the network"
            results[cert] = ("pending", blocked, {})
    out = batch_dir / "certs_enriched.csv"
    tmp = out.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns + EXTRA)
        for r in rows:
            cert = r.get("cert", "")
            if cert in results:
                st, note, payload = results[cert]
                flat = flatten(payload) if st == "ok" else {}
            else:
                why = "not looked up: " + ("CGC/other grader" if r.get("grader") not in ("PSA", "unknown", None) else f"status {r.get('status')}" if r.get("status") not in wanted_status else "no cert")
                st, note, flat = "skipped", why, {}
            w.writerow([r.get(c, "") for c in columns] + [st, note] + [flat.get(k, "") for k in PSA_FIELDS])
    tmp.replace(out)
    counts: dict[str, int] = {}
    for st, _, _ in results.values():
        counts[st] = counts.get(st, 0) + 1
    summary = {"file": str(out), "certs": len(todo), "counts": counts, "api_calls": calls, "used_today": client._used_today(), "daily_limit": daily_limit, "blocked": blocked}
    log(f"{out}: {len(todo)} PSA certs - " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f"; {calls} API calls this run, {summary['used_today']}/{daily_limit} today")
    if blocked:
        log(f"stopped early: {blocked}")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch_dir", type=Path)
    ap.add_argument("--token", help="PSA API token (default: $PSA_API_TOKEN)")
    ap.add_argument("--daily-limit", type=int, default=100)
    ap.add_argument("--max", dest="max_calls", type=int, default=None, help="at most this many API calls this run")
    ap.add_argument("--cache", type=Path, default=None, help="SQLite cache (default: batches/psa_cache.sqlite, shared by all batches)")
    ap.add_argument("--include-review", action="store_true", help="also look up needs_review certs (OCR-only reads)")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between calls")
    ap.add_argument("--retry-days", type=float, default=7.0, help="ask again about certs PSA answered 'no data' (or an error) for after this many days")
    a = ap.parse_args(argv)
    try:
        s = enrich(a.batch_dir, a.token, a.daily_limit, a.cache, a.include_review, a.max_calls, a.interval, retry_days=a.retry_days)
    except FileNotFoundError as e:
        print(e)
        return 1
    return 0 if not s["blocked"] and not s["counts"].get("pending") else 1


if __name__ == "__main__":
    sys.exit(main())
