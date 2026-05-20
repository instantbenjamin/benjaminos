"""BenjaminOS Morning Brief — shared gather + render core.

One brain, two faces:
  morning_brief.py --json   → panel data as JSON (consumed by the pharoah-mcp
                              tool that feeds the live Cowork artifact)
  morning_brief.py --html   → self-contained styled HTML (written to Drive by
                              the VPS cron; phone-accessible)

Data sources (all server-side on the VPS):
  - Supabase service_role REST: oura_daily, lastfm_scrobbles, lastfm_top,
    trakt_watched, ingest_sources
  - Direct Postgres (psycopg2): pharoah.voicenotes_log  (pharoah schema is not
    REST-exposed, so captures must come via raw SQL)
  - Linear GraphQL: tasks on deck across projects

Calendar is intentionally NOT gathered here — in the live artifact it comes
from the Cowork Calendar MCP; the VPS HTML shows a placeholder until the
service account is granted calendar access.

Each panel is independently wrapped: one failing source never blanks the brief.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as _html
import json
import os
import re
import pathlib
import subprocess
import sys
from typing import Any

import httpx

LISBON = dt.timezone(dt.timedelta(hours=1))  # Europe/Lisbon (BST-equivalent in summer)


# ---------------------------------------------------------------- helpers ----
def _sb_headers() -> dict:
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_ANON_KEY"]
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _sb_get(path: str) -> Any:
    url = os.environ["SUPABASE_URL"]
    with httpx.Client(timeout=20.0) as c:
        r = c.get(f"{url}/rest/v1/{path}", headers=_sb_headers())
        r.raise_for_status()
        return r.json()


def _pg_dsn() -> str:
    """Rebuild the Postgres DSN with the fresh password (same pattern as migrations)."""
    env_file = pathlib.Path.home() / ".gbrain" / ".env"
    env: dict[str, str] = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'([A-Z_][A-Z0-9_]*)=(.*)$', line)
        if m:
            env[m.group(1)] = m.group(2).strip('"\'')
    old_url = os.environ.get("SUPABASE_DATABASE_URL") or env["SUPABASE_DATABASE_URL"]
    pw = subprocess.check_output(
        ["/home/benjaminbot/bin/infisical-self-hosted",
         "secrets", "get", "SUPABASE_PASSWORD", "--env", "dev", "--plain"],
        text=True).strip()
    return re.sub(r'(:)[^@:]+(@)', lambda m: m.group(1) + pw + m.group(2), old_url, count=1)


def _linear(query: str, variables: dict | None = None) -> dict:
    key = os.environ["LINEAR_API_KEY"]
    with httpx.Client(timeout=20.0) as c:
        r = c.post(
            "https://api.linear.app/graphql",
            headers={"Authorization": key, "Content-Type": "application/json"},
            json={"query": query, "variables": variables or {}},
        )
        r.raise_for_status()
        body = r.json()
        if "errors" in body:
            raise RuntimeError(str(body["errors"])[:200])
        return body["data"]


# ---------------------------------------------------------------- panels ----
def panel_sleep() -> dict:
    sleep = _sb_get("oura_daily?type=eq.daily_sleep&select=day,score&order=day.desc&limit=7")
    ready = _sb_get("oura_daily?type=eq.daily_readiness&select=day,score&order=day.desc&limit=7")
    activity = _sb_get("oura_daily?type=eq.daily_activity&select=day,score&order=day.desc&limit=1")
    latest_sleep = sleep[0] if sleep else None
    latest_ready = ready[0] if ready else None
    latest_act = activity[0] if activity else None
    # 7-day sleep trend, oldest→newest for the sparkline
    trend = [s["score"] for s in reversed(sleep) if s.get("score") is not None]
    return {
        "sleep_score": latest_sleep["score"] if latest_sleep else None,
        "sleep_day": latest_sleep["day"] if latest_sleep else None,
        "readiness_score": latest_ready["score"] if latest_ready else None,
        "activity_score": latest_act["score"] if latest_act else None,
        "sleep_trend": trend,
    }


def panel_linear_focus() -> dict:
    q = """
    query Focus {
      issues(
        first: 12,
        filter: {
          state: { type: { in: ["started","unstarted"] } },
          project: { name: { in: ["BenjaminOS","Benjamin-Personal","FinanceOS"] } }
        },
        orderBy: updatedAt
      ) {
        nodes { identifier title priority project { name } state { name } }
      }
    }"""
    data = _linear(q)
    nodes = data.get("issues", {}).get("nodes", [])
    nodes.sort(key=lambda n: (n.get("priority") or 99))
    return {"items": [
        {"id": n["identifier"], "title": n["title"],
         "project": (n.get("project") or {}).get("name", ""),
         "state": (n.get("state") or {}).get("name", ""),
         "priority": n.get("priority") or 0}
        for n in nodes[:8]
    ]}


def panel_eir() -> dict:
    q = """
    query EIR {
      issues(
        first: 8,
        filter: {
          state: { type: { in: ["started","unstarted"] } },
          team: { key: { eq: "EIR" } }
        },
        orderBy: updatedAt
      ) {
        nodes { identifier title priority state { name } }
      }
    }"""
    try:
        data = _linear(q)
        nodes = data.get("issues", {}).get("nodes", [])
        nodes.sort(key=lambda n: (n.get("priority") or 99))
        return {"items": [
            {"id": n["identifier"], "title": n["title"],
             "state": (n.get("state") or {}).get("name", ""),
             "priority": n.get("priority") or 0}
            for n in nodes[:6]
        ], "available": True}
    except Exception as e:
        return {"items": [], "available": False, "note": str(e)[:120]}


def panel_captures() -> dict:
    """Recent captures from public.pharoah_voicenotes_log via direct Postgres.

    (The table lacks a REST grant, so we read it over psycopg2, not PostgREST.)
    The human-readable bit lives in the `envelope` jsonb; we probe common keys.
    """
    import psycopg2
    out: list[dict] = []
    with psycopg2.connect(_pg_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source_type, captured_at, envelope
                FROM public.pharoah_voicenotes_log
                WHERE captured_at >= now() - interval '36 hours'
                  AND lower(COALESCE(privacy_flag::text, '')) NOT IN ('private','true','redact','sensitive')
                ORDER BY captured_at DESC
                LIMIT 10;
            """)
            for st, at, env in cur.fetchall():
                subj = ""
                if isinstance(env, dict):
                    for k in ("subject", "title", "summary", "raw_content", "text", "content"):
                        v = env.get(k)
                        if v:
                            subj = str(v)
                            break
                out.append({"source": st, "subject": subj[:90] or "(no summary)",
                            "at": at.isoformat()})
    return {"items": out, "count": len(out)}


def panel_media() -> dict:
    # last-24h scrobbles across both accounts.
    # NOTE: use Z-suffixed UTC, not isoformat() — a literal "+" in a PostgREST
    # filter value is read as a space and 400s.
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent = _sb_get(
        f"lastfm_scrobbles?played_at=gte.{since}&select=artist,track,username,played_at"
        f"&order=played_at.desc&limit=200"
    )
    # overall top artists — dedupe across snapshots (latest captured_at wins)
    top_rows = _sb_get(
        "lastfm_top?period=eq.overall&type=eq.artist&select=name,rank,captured_at"
        "&order=captured_at.desc,rank.asc&limit=50"
    )
    seen: set = set()
    top = []
    for t in top_rows:
        if t["name"] in seen:
            continue
        seen.add(t["name"])
        top.append(t)
        if len(top) >= 5:
            break
    # recent watched titles
    watched = _sb_get(
        "trakt_watched?select=title,type,last_watched_at&order=last_watched_at.desc.nullslast&limit=5"
    )
    import collections
    by_artist = collections.Counter(r["artist"] for r in recent if r.get("artist"))
    return {
        "scrobbles_24h": len(recent),
        "top_recent_artists": [{"artist": a, "n": n} for a, n in by_artist.most_common(3)],
        "top_overall": [t["name"] for t in top],
        "recent_watched": [{"title": w["title"], "type": w["type"]} for w in watched],
    }


def panel_ingest_health() -> dict:
    rows = _sb_get("ingest_sources?status=eq.shipped&select=slug,cadence,last_ok_at&order=last_ok_at.desc.nullslast")
    now = dt.datetime.now(dt.timezone.utc)
    healthy, stale, not_reporting = [], [], []
    # never-run sources are "not self-reporting yet" (only oura/trakt/lastfm
    # write last_ok_at today) — distinct from genuinely stale ones that DID
    # report but have gone quiet past their cadence.
    for r in rows:
        ok = r.get("last_ok_at")
        if not ok:
            not_reporting.append({"slug": r["slug"]})
            continue
        age_h = (now - dt.datetime.fromisoformat(ok.replace("Z", "+00:00"))).total_seconds() / 3600
        label = f"{int(age_h)}h" if age_h < 48 else f"{int(age_h/24)}d"
        (stale if age_h > 36 else healthy).append({"slug": r["slug"], "age": label})
    return {"healthy": healthy, "stale": stale,
            "not_reporting": not_reporting, "total": len(rows)}


def gather() -> dict:
    panels: dict[str, Any] = {
        "generated_at": dt.datetime.now(LISBON).isoformat(),
        "panels": {},
        "errors": {},
    }
    for name, fn in [
        ("sleep", panel_sleep),
        ("linear_focus", panel_linear_focus),
        ("eir", panel_eir),
        ("captures", panel_captures),
        ("media", panel_media),
        ("ingest_health", panel_ingest_health),
    ]:
        try:
            panels["panels"][name] = fn()
        except Exception as e:
            panels["errors"][name] = f"{type(e).__name__}: {e}"[:200]
    return panels


# ---------------------------------------------------------------- render ----
def _spark(values: list[int], w: int = 120, h: int = 28) -> str:
    if not values or len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    step = w / (len(values) - 1)
    pts = " ".join(
        f"{i*step:.1f},{h - (v-lo)/rng*(h-4) - 2:.1f}" for i, v in enumerate(values)
    )
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="#6b8f71" stroke-width="2" points="{pts}"/></svg>')


def _esc(s: Any) -> str:
    return _html.escape(str(s if s is not None else ""))


def render_html(data: dict) -> str:
    p = data["panels"]
    errs = data.get("errors", {})
    gen = data["generated_at"][:16].replace("T", " ")

    def err_or(name: str, body: str) -> str:
        if name in errs:
            return f'<p class="err">couldn\'t load — {_esc(errs[name])}</p>'
        return body

    # Sleep
    sp = p.get("sleep", {})
    sleep_body = (
        f'<div class="big">{_esc(sp.get("sleep_score","–"))}<span>sleep</span></div>'
        f'<div class="big">{_esc(sp.get("readiness_score","–"))}<span>readiness</span></div>'
        f'<div class="big">{_esc(sp.get("activity_score","–"))}<span>activity</span></div>'
        f'<div class="spark">{_spark(sp.get("sleep_trend", []))}<span>7-day sleep</span></div>'
    ) if sp else ""

    # Linear focus
    lf = p.get("linear_focus", {})
    pr = {0:"", 1:"🔴", 2:"🟠", 3:"🟡", 4:"⚪"}
    focus_rows = "".join(
        f'<li><span class="tag">{_esc(i["project"][:3])}</span> {pr.get(i["priority"],"")} '
        f'<b>{_esc(i["id"])}</b> {_esc(i["title"][:70])} <span class="st">{_esc(i["state"])}</span></li>'
        for i in lf.get("items", [])
    ) or "<li class='muted'>nothing on deck</li>"

    # EIR
    eir = p.get("eir", {})
    if eir.get("available") is False:
        eir_body = '<p class="muted">EIR team not connected here</p>'
    else:
        eir_body = "<ul>" + ("".join(
            f'<li>{pr.get(i["priority"],"")} <b>{_esc(i["id"])}</b> {_esc(i["title"][:60])}</li>'
            for i in eir.get("items", [])
        ) or "<li class='muted'>clear</li>") + "</ul>"

    # Captures
    cap = p.get("captures", {})
    cap_rows = "".join(
        f'<li><span class="tag">{_esc(c["source"])}</span> {_esc(c["subject"])}</li>'
        for c in cap.get("items", [])
    ) or "<li class='muted'>no captures in last 36h</li>"

    # Media
    md = p.get("media", {})
    top_recent = ", ".join(f'{_esc(a["artist"])} ({a["n"]})' for a in md.get("top_recent_artists", [])) or "quiet"
    watched = ", ".join(_esc(w["title"]) for w in md.get("recent_watched", [])) or "—"
    media_body = (
        f'<p><b>{_esc(md.get("scrobbles_24h",0))}</b> scrobbles last 24h</p>'
        f'<p class="muted">recent: {top_recent}</p>'
        f'<p class="muted">watching: {watched}</p>'
    ) if md else ""

    # Ingest health
    ih = p.get("ingest_health", {})
    healthy = ih.get("healthy", []); stale = ih.get("stale", []); nr = ih.get("not_reporting", [])
    health_body = (
        f'<p><b>{len(healthy)}</b> self-reporting &amp; fresh: '
        + _esc(", ".join(s["slug"] for s in healthy)) + '</p>'
        + (f'<p class="warn">⚠ stale: ' + ", ".join(f'{_esc(s["slug"])} ({s["age"]})' for s in stale) + '</p>' if stale else '')
        + (f'<p class="muted">not self-reporting yet ({len(nr)}): ' + _esc(", ".join(s["slug"] for s in nr)) + '</p>' if nr else '')
    ) if ih else ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Morning Brief — {gen}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#f6f5f1; color:#2a2a28;
         font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; line-height:1.45; }}
  .wrap {{ max-width:880px; margin:0 auto; padding:24px 18px 60px; }}
  header h1 {{ font-size:22px; margin:0 0 2px; font-weight:700; letter-spacing:-.01em; }}
  header p {{ margin:0 0 20px; color:#8a8a84; font-size:13px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
  .card {{ background:#fff; border:1px solid #e7e5df; border-radius:12px; padding:16px 18px; }}
  .card h2 {{ font-size:12px; text-transform:uppercase; letter-spacing:.06em;
             color:#9a9a92; margin:0 0 12px; font-weight:700; }}
  .row {{ display:flex; gap:18px; flex-wrap:wrap; align-items:flex-end; }}
  .big {{ font-size:30px; font-weight:700; color:#3a5a40; line-height:1; }}
  .big span {{ display:block; font-size:11px; font-weight:500; color:#9a9a92; margin-top:4px; text-transform:uppercase; letter-spacing:.04em; }}
  .spark span {{ display:block; font-size:11px; color:#9a9a92; margin-top:2px; }}
  ul {{ list-style:none; margin:0; padding:0; }}
  li {{ font-size:13px; padding:5px 0; border-bottom:1px solid #f0eee8; }}
  li:last-child {{ border-bottom:none; }}
  .tag {{ display:inline-block; background:#eef1ec; color:#5a7a60; font-size:10px;
         padding:1px 6px; border-radius:5px; font-weight:600; text-transform:uppercase; }}
  .st {{ color:#b0b0a8; font-size:11px; }}
  .muted {{ color:#b0b0a8; }}
  .warn {{ color:#b5651d; font-size:13px; }}
  .ok {{ color:#3a5a40; font-size:13px; }}
  .err {{ color:#b04a3a; font-size:12px; font-style:italic; }}
  .cal-note {{ color:#9a9a92; font-size:13px; font-style:italic; }}
  p {{ margin:4px 0; font-size:13px; }}
</style></head>
<body><div class="wrap">
<header>
  <h1>Good morning, Benjamin</h1>
  <p>Morning brief · generated {gen} Lisbon</p>
</header>
<div class="grid">
  <div class="card"><h2>Sleep &amp; Readiness</h2><div class="row">{err_or("sleep", sleep_body)}</div></div>
  <div class="card"><h2>Today's Calendar</h2><p class="cal-note">Live in the desktop version. VPS calendar access pending.</p></div>
  <div class="card"><h2>On Deck · Linear</h2>{err_or("linear_focus", f"<ul>{focus_rows}</ul>")}</div>
  <div class="card"><h2>EIR Triage</h2>{err_or("eir", eir_body)}</div>
  <div class="card"><h2>Yesterday's Captures</h2>{err_or("captures", f"<ul>{cap_rows}</ul>")}</div>
  <div class="card"><h2>Media</h2>{err_or("media", media_body)}</div>
  <div class="card"><h2>Ingest Health</h2>{err_or("ingest_health", health_body)}</div>
</div>
</div></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--out", help="write HTML to this path")
    args = ap.parse_args()

    data = gather()
    if args.json or not (args.html or args.out):
        print(json.dumps(data, indent=2, default=str))
        return 0
    html_doc = render_html(data)
    if args.out:
        pathlib.Path(args.out).write_text(html_doc)
        print(f"wrote {len(html_doc)} bytes → {args.out}")
        if data.get("errors"):
            print(f"panel errors: {list(data['errors'])}", file=sys.stderr)
    else:
        print(html_doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
