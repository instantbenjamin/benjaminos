"""Pull Oura daily metrics into public.oura_daily on Supabase.

Reads OURA_TOKEN, SUPABASE_URL, SUPABASE_ANON_KEY from env (set by the wrapper).
Pulls last N days (default 7) from four endpoints, upserts each record by id.
Idempotent — safe to run repeatedly.

After a successful run, self-reports into public.ingest_sources (slug='oura')
so the catalog stays fresh — last_run_at / last_ok_at / rows_count.

Usage:
  oura-ingest                 # last 7 days
  oura-ingest --days 30       # custom window
  oura-ingest --days 365      # backfill
  oura-ingest --dry-run       # show what would be written
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import Iterable

import httpx

OURA_BASE = "https://api.ouraring.com/v2/usercollection"
ENDPOINTS = ("daily_sleep", "daily_readiness", "daily_activity", "daily_stress")
SLUG = "oura"


def _oura_get(endpoint: str, token: str, start: str, end: str) -> list[dict]:
    """Pull all pages for one endpoint over a date window."""
    out: list[dict] = []
    next_token: str | None = None
    with httpx.Client(timeout=20.0) as client:
        while True:
            params = {"start_date": start, "end_date": end}
            if next_token:
                params["next_token"] = next_token
            r = client.get(
                f"{OURA_BASE}/{endpoint}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            r.raise_for_status()
            body = r.json()
            out.extend(body.get("data", []))
            next_token = body.get("next_token")
            if not next_token:
                break
    return out


def _to_row(endpoint: str, record: dict) -> dict:
    """Normalize an Oura record into our oura_daily row shape."""
    rid = record.get("id")
    day = record.get("day")
    if not rid or not day:
        return {}
    contributors = record.get("contributors") or {}
    return {
        "id": f"{endpoint}:{rid}",
        "type": endpoint,
        "day": day,
        "score": record.get("score"),
        "contributors": contributors,
        "raw": record,
        "source_ts": record.get("timestamp"),
    }


def _upsert(rows: list[dict], dry_run: bool) -> int:
    """Upsert rows into public.oura_daily via Supabase REST."""
    if not rows:
        return 0
    if dry_run:
        for r in rows[:3]:
            print(f"  would upsert: {r['type']} day={r['day']} score={r['score']}")
        if len(rows) > 3:
            print(f"  ... +{len(rows) - 3} more")
        return len(rows)
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    # Chunk to avoid request size limits when backfilling years
    CHUNK = 500
    written = 0
    with httpx.Client(timeout=30.0) as client:
        for i in range(0, len(rows), CHUNK):
            batch = rows[i : i + CHUNK]
            r = client.post(
                f"{url}/rest/v1/oura_daily",
                headers=headers,
                json=batch,
            )
            if r.status_code >= 400:
                print(f"  upsert error {r.status_code}: {r.text[:200]}", file=sys.stderr)
                r.raise_for_status()
            written += len(batch)
    return written


def _update_catalog(rows_count: int, ok: bool, err: str | None) -> None:
    """Self-report into public.ingest_sources."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        return
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    body: dict = {
        "slug": SLUG,
        "status": "shipped",            # required by NOT NULL; safe — if we're reporting, we're shipped
        "last_run_at": now,
        "rows_count": rows_count,
    }
    if ok:
        body["last_ok_at"] = now
        body["last_error"] = None
    elif err:
        body["last_error"] = err[:500]
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"{url}/rest/v1/ingest_sources?on_conflict=slug",
                headers=headers,
                json=[body],
            )
            if r.status_code >= 400:
                print(f"  catalog self-report warn {r.status_code}: {r.text[:120]}", file=sys.stderr)
    except Exception as e:
        print(f"  catalog self-report failed: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("OURA_TOKEN") or os.environ.get("Oura_Pharoah")
    if not token:
        print("ERROR: OURA_TOKEN or Oura_Pharoah env var required", file=sys.stderr)
        return 1

    end = dt.date.today()
    start = end - dt.timedelta(days=args.days)
    start_s, end_s = start.isoformat(), end.isoformat()

    print(f"oura-ingest · window {start_s} → {end_s}")
    total_pulled = 0
    total_upserted = 0
    err: str | None = None
    for endpoint in ENDPOINTS:
        try:
            records = _oura_get(endpoint, token, start_s, end_s)
        except httpx.HTTPError as e:
            print(f"  /{endpoint}: ERROR {e}", file=sys.stderr)
            err = f"{endpoint}: {e}"
            continue
        rows = [r for r in (_to_row(endpoint, rec) for rec in records) if r]
        total_pulled += len(records)
        try:
            n = _upsert(rows, dry_run=args.dry_run)
        except Exception as e:
            err = f"{endpoint} upsert: {e}"
            print(f"  /{endpoint}: upsert FAILED {e}", file=sys.stderr)
            continue
        total_upserted += n
        print(f"  /{endpoint}: {len(records)} pulled · {n} upserted")
    print(f"done · pulled {total_pulled} · upserted {total_upserted}")

    if not args.dry_run:
        _update_catalog(rows_count=total_upserted, ok=(err is None), err=err)
    return 0


if __name__ == "__main__":
    sys.exit(main())
