"""Pull Trakt watched-movies and watched-shows into public.trakt_watched.

Auth: OAuth user token + client_id (both from env, set by the wrapper).
Idempotent — safe to run repeatedly. Upserts by (type, trakt_id).

Also writes its own row in pharoah.ingest_sources with last_run_at / last_ok_at
so the ingest catalog stays self-reporting.

Usage:
  trakt-ingest                 # full pull
  trakt-ingest --dry-run       # show what would be written
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import Any

import httpx

TRAKT_BASE = "https://api.trakt.tv"
SLUG = "trakt"


def _trakt_get(path: str, token: str, client_id: str) -> Any:
    """Single GET to Trakt API with both headers."""
    with httpx.Client(timeout=30.0) as client:
        r = client.get(
            f"{TRAKT_BASE}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "trakt-api-version": "2",
                "trakt-api-key": client_id,
            },
        )
        r.raise_for_status()
        return r.json()


def _movie_row(rec: dict) -> dict:
    movie = rec.get("movie") or {}
    tid = (movie.get("ids") or {}).get("trakt")
    if not tid:
        return {}
    return {
        "id": f"movie:{tid}",
        "type": "movie",
        "trakt_id": tid,
        "title": movie.get("title"),
        "year": movie.get("year"),
        "plays": rec.get("plays"),
        "last_watched_at": rec.get("last_watched_at"),
        "raw": rec,
    }


def _show_row(rec: dict) -> dict:
    show = rec.get("show") or {}
    tid = (show.get("ids") or {}).get("trakt")
    if not tid:
        return {}
    # Sum plays across all episodes for a comparable "plays" number
    plays = 0
    last_w = None
    for season in rec.get("seasons", []) or []:
        for ep in season.get("episodes", []) or []:
            plays += ep.get("plays") or 0
            ts = ep.get("last_watched_at")
            if ts and (last_w is None or ts > last_w):
                last_w = ts
    return {
        "id": f"show:{tid}",
        "type": "show",
        "trakt_id": tid,
        "title": show.get("title"),
        "year": show.get("year"),
        "plays": plays,
        "last_watched_at": last_w or rec.get("last_watched_at"),
        "raw": rec,
    }


def _upsert(rows: list[dict], dry_run: bool) -> int:
    if not rows:
        return 0
    if dry_run:
        for r in rows[:3]:
            print(f"  would upsert: {r['type']} {r['title']} ({r['year']}) plays={r['plays']}")
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
    # Batch in chunks of 500 to avoid request size limits
    CHUNK = 500
    written = 0
    with httpx.Client(timeout=60.0) as client:
        for i in range(0, len(rows), CHUNK):
            batch = rows[i : i + CHUNK]
            r = client.post(
                f"{url}/rest/v1/trakt_watched",
                headers=headers,
                json=batch,
            )
            if r.status_code >= 400:
                print(f"  upsert error {r.status_code}: {r.text[:200]}", file=sys.stderr)
                r.raise_for_status()
            written += len(batch)
    return written


def _update_catalog(rows_count: int, ok: bool, err: str | None) -> None:
    """Self-report into pharoah.ingest_sources."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        return
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    body = {
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
                # ingest_sources is in the pharoah schema; PostgREST exposes
                # public by default. If this 404s we just warn and move on.
                print(f"  catalog self-report warn {r.status_code}: {r.text[:120]}", file=sys.stderr)
    except Exception as e:
        print(f"  catalog self-report failed: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("TRAKT_ACCESS_TOKEN")
    client_id = os.environ.get("TRAKT_CLIENT_ID")
    if not token or not client_id:
        print("ERROR: TRAKT_ACCESS_TOKEN and TRAKT_CLIENT_ID env vars required", file=sys.stderr)
        return 1

    total = 0
    err: str | None = None
    try:
        print("trakt-ingest · pulling watched movies + shows")
        movies = _trakt_get("/sync/watched/movies", token, client_id)
        shows = _trakt_get("/sync/watched/shows", token, client_id)
        print(f"  /sync/watched/movies: {len(movies)} titles")
        print(f"  /sync/watched/shows:  {len(shows)} series")

        movie_rows = [r for r in (_movie_row(m) for m in movies) if r]
        show_rows = [r for r in (_show_row(s) for s in shows) if r]
        all_rows = movie_rows + show_rows

        n = _upsert(all_rows, dry_run=args.dry_run)
        total = n
        print(f"  upserted: {n} (movies={len(movie_rows)} shows={len(show_rows)})")
    except httpx.HTTPError as e:
        err = f"HTTPError: {e}"
        print(f"  ERROR: {err}", file=sys.stderr)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"  ERROR: {err}", file=sys.stderr)

    if not args.dry_run:
        _update_catalog(rows_count=total, ok=(err is None), err=err)
    return 0 if err is None else 1


if __name__ == "__main__":
    sys.exit(main())
