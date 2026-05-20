"""Pull Last.fm scrobbles into public.lastfm_scrobbles + public.lastfm_top.

Auth: LASTFM_API_KEY (no OAuth — Last.fm uses simple API key auth for reads).
Username read from LASTFM_USERNAME env (set by wrapper).

Modes:
  lastfm-ingest                # incremental: scrobbles since last_ok_at minus 1h overlap
  lastfm-ingest --backfill     # full historical pull (paginates 200/page backwards)
  lastfm-ingest --top          # snapshot top artists/albums/tracks for all 6 windows
  lastfm-ingest --dry-run      # show what would land, don't write

Self-reports into public.ingest_sources (slug='lastfm') after each run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from typing import Iterable

import httpx

LASTFM_API = "https://ws.audioscrobbler.com/2.0/"
SLUG = "lastfm"

PERIODS = ("7day", "1month", "3month", "6month", "12month", "overall")


def _api(method: str, params: dict, api_key: str) -> dict:
    """Single GET to Last.fm. Retries on 429/5xx with backoff."""
    p = dict(params)
    p.update({"method": method, "api_key": api_key, "format": "json"})
    for attempt in range(4):
        with httpx.Client(timeout=30.0) as client:
            r = client.get(LASTFM_API, params=p)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            wait = 2 ** attempt
            print(f"  {method} HTTP {r.status_code}, retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        # Last.fm returns 200 with an error envelope sometimes — and other
        # status codes for real errors.
        r.raise_for_status()
    raise RuntimeError(f"{method} failed after retries")


def _scrobble_row(rec: dict, username: str) -> dict | None:
    """Normalize a getRecentTracks track into a row.

    Skips currently-playing entries (no @attr.nowplaying handling for ingest).
    """
    if rec.get("@attr", {}).get("nowplaying") == "true":
        return None
    uts = rec.get("date", {}).get("uts")
    if not uts:
        # Skip nowplaying / malformed
        return None
    played_at = dt.datetime.fromtimestamp(int(uts), tz=dt.timezone.utc)

    artist_obj = rec.get("artist") or {}
    # New API returns string for #text in artist, mbid separate
    artist_name = artist_obj.get("#text") or artist_obj.get("name") or ""
    album_obj = rec.get("album") or {}
    album_name = album_obj.get("#text") or ""
    track_name = rec.get("name") or ""

    fingerprint = hashlib.md5(
        f"{artist_name}|{track_name}".lower().encode("utf-8")
    ).hexdigest()[:12]

    return {
        "id": f"{username}:{uts}:{fingerprint}",
        "username": username,
        "played_at": played_at.isoformat(),
        "artist": artist_name,
        "track": track_name,
        "album": album_name or None,
        "artist_mbid": artist_obj.get("mbid") or None,
        "track_mbid": rec.get("mbid") or None,
        "album_mbid": album_obj.get("mbid") or None,
        "raw": rec,
    }


def _pull_recent_streaming(
    api_key: str, username: str, from_ts: int | None, backfill: bool, dry_run: bool
) -> int:
    """Pull recent tracks, streaming upsert every N pages to keep memory bounded.

    Returns total rows upserted. Last.fm pagination: page=1 is newest. We walk
    forward (1..N) and stop when total_pages reached or sanity-capped (incremental).
    """
    FLUSH_EVERY_PAGES = 10        # ~2000 rows per upsert batch
    PROGRESS_EVERY_PAGES = 25     # ~5000 rows per log line

    buffer: list[dict] = []
    total_upserted = 0
    page = 1
    seen_pages = 0
    total_pages_known: int | None = None

    while True:
        params = {"user": username, "limit": 200, "page": page}
        if from_ts and not backfill:
            params["from"] = from_ts
        body = _api("user.getrecenttracks", params, api_key)
        tracks_block = body.get("recenttracks", {})
        attr = tracks_block.get("@attr", {})
        total_pages = int(attr.get("totalPages", 1))
        total_scrobbles = int(attr.get("total", 0))
        if page == 1:
            total_pages_known = total_pages
            print(f"  {username}: {total_scrobbles} total scrobbles · {total_pages} pages",
                  flush=True)

        tracks = tracks_block.get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        for rec in tracks:
            row = _scrobble_row(rec, username)
            if row:
                buffer.append(row)
        seen_pages += 1

        # Flush periodically so we don't hold 220k rows in memory at once
        if seen_pages % FLUSH_EVERY_PAGES == 0 and buffer:
            n = _upsert("lastfm_scrobbles", buffer, dry_run)
            total_upserted += n
            buffer = []

        # Visible progress for long backfills
        if seen_pages % PROGRESS_EVERY_PAGES == 0:
            pct = (page / total_pages_known * 100) if total_pages_known else 0
            print(f"  page {page}/{total_pages_known} ({pct:.1f}%) · {total_upserted} upserted so far",
                  flush=True)

        if page >= total_pages:
            break
        page += 1

        time.sleep(0.25)  # 4 req/s/key cap per Last.fm ToS
        if not backfill and seen_pages > 50:
            print(f"  WARN: stopped at 50 pages on incremental; recheck schedule", file=sys.stderr)
            break

    # Flush remainder
    if buffer:
        n = _upsert("lastfm_scrobbles", buffer, dry_run)
        total_upserted += n
    return total_upserted


def _pull_top(api_key: str, username: str) -> list[dict]:
    """Snapshot top artists/albums/tracks for every period."""
    today = dt.date.today()
    out: list[dict] = []
    for period in PERIODS:
        for ttype, method, list_key, item_key in (
            ("artist", "user.gettopartists", "topartists", "artist"),
            ("album", "user.gettopalbums", "topalbums", "album"),
            ("track", "user.gettoptracks", "toptracks", "track"),
        ):
            body = _api(method, {"user": username, "period": period, "limit": 50}, api_key)
            items = body.get(list_key, {}).get(item_key, [])
            if isinstance(items, dict):
                items = [items]
            for item in items:
                rank = int(item.get("@attr", {}).get("rank", 0)) or len(out) + 1
                name = item.get("name", "")
                artist_field = item.get("artist")
                # For album/track, artist is nested
                if isinstance(artist_field, dict):
                    artist_name = artist_field.get("name") or artist_field.get("#text") or ""
                else:
                    artist_name = artist_field or ""
                out.append({
                    "id": f"{period}:{ttype}:{today.isoformat()}:{rank}",
                    "username": username,
                    "period": period,
                    "type": ttype,
                    "captured_at": today.isoformat(),
                    "rank": rank,
                    "name": name,
                    "artist": artist_name if ttype != "artist" else None,
                    "playcount": int(item.get("playcount", 0) or 0),
                    "mbid": item.get("mbid") or None,
                    "raw": item,
                })
            time.sleep(0.25)
    return out


def _upsert(table: str, rows: list[dict], dry_run: bool) -> int:
    if not rows:
        return 0
    if dry_run:
        print(f"  would upsert {len(rows)} rows to {table}; sample:")
        for r in rows[:3]:
            keys = {k: v for k, v in r.items() if k in ("artist", "track", "played_at", "period", "type", "rank", "name", "playcount")}
            print(f"    {keys}")
        return len(rows)
    url = os.environ["SUPABASE_URL"]
    key = (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_ANON_KEY"])
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    CHUNK = 500
    written = 0
    with httpx.Client(timeout=60.0) as client:
        for i in range(0, len(rows), CHUNK):
            batch = rows[i : i + CHUNK]
            r = client.post(f"{url}/rest/v1/{table}", headers=headers, json=batch)
            if r.status_code >= 400:
                print(f"  upsert error {r.status_code}: {r.text[:200]}", file=sys.stderr)
                r.raise_for_status()
            written += len(batch)
    return written


def _get_last_ok(slug: str = SLUG) -> dt.datetime | None:
    url = os.environ.get("SUPABASE_URL")
    key = (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY"))
    if not url or not key:
        return None
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{url}/rest/v1/ingest_sources?slug=eq.{slug}&select=last_ok_at",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
            )
            if r.status_code == 200:
                rows = r.json()
                if rows and rows[0].get("last_ok_at"):
                    return dt.datetime.fromisoformat(rows[0]["last_ok_at"].replace("Z", "+00:00"))
    except Exception:
        pass
    return None


def _update_catalog(rows_count: int, ok: bool, err: str | None) -> None:
    url = os.environ.get("SUPABASE_URL")
    key = (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY"))
    if not url or not key:
        return
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    body: dict = {
        "slug": SLUG,
        "status": "shipped",
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
                headers=headers, json=[body],
            )
            if r.status_code >= 400:
                print(f"  catalog warn {r.status_code}: {r.text[:120]}", file=sys.stderr)
    except Exception as e:
        print(f"  catalog warn: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="full historical pull")
    ap.add_argument("--top", action="store_true", help="snapshot top artists/albums/tracks")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    api_key = os.environ.get("LASTFM_API_KEY")
    username = os.environ.get("LASTFM_USERNAME")
    if not api_key or not username:
        print("ERROR: LASTFM_API_KEY and LASTFM_USERNAME required", file=sys.stderr)
        return 1

    total = 0
    err: str | None = None
    try:
        if args.top:
            print(f"lastfm-ingest · top snapshot for {username}")
            top_rows = _pull_top(api_key, username)
            print(f"  pulled {len(top_rows)} top items across 6 windows × 3 types")
            total = _upsert("lastfm_top", top_rows, args.dry_run)
            print(f"  total upserted: {total}", flush=True)
        else:
            from_ts = None
            if not args.backfill:
                last_ok = _get_last_ok()
                if last_ok:
                    # 1h overlap to catch late-arriving scrobbles
                    from_ts = int((last_ok - dt.timedelta(hours=1)).timestamp())
                    print(f"lastfm-ingest · incremental since {dt.datetime.fromtimestamp(from_ts, tz=dt.timezone.utc).isoformat()}")
                else:
                    print(f"lastfm-ingest · no last_ok_at, forcing backfill")
                    args.backfill = True
            if args.backfill:
                print(f"lastfm-ingest · BACKFILL for {username}")
            total = _pull_recent_streaming(api_key, username, from_ts=from_ts, backfill=args.backfill, dry_run=args.dry_run)
            # (streaming version reports inside)
            pass
            print(f"  total upserted: {total}", flush=True)
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
