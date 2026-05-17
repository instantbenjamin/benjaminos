"""Pharoah MCP (stdio) — exposes classifier + dispatch to Pharoah Claude AND Pharoah Hermes."""
from __future__ import annotations
import logging, os, sys
from datetime import datetime, timezone, timedelta
from typing import Any
from mcp.server.fastmcp import FastMCP

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
_SCRIPTS = os.path.join(_REPO, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

logging.basicConfig(level=os.environ.get("PHAROAH_MCP_LOG", "INFO"),
    format="%(asctime)s %(levelname)s: %(message)s", stream=sys.stderr)
log = logging.getLogger("pharoah.mcp")

mcp = FastMCP("pharoah")


def _make_source(transcript, source_id, source_type, captured_at, title_hint):
    from pharoah.classifier.envelope import SourceArtifact, SourceType
    from uuid import uuid4
    sid = source_id or f"mcp:{uuid4().hex[:12]}"
    ts = (datetime.fromisoformat(captured_at.replace("Z","+00:00"))
          if captured_at else datetime.now(timezone.utc))
    try:
        stype = SourceType(source_type)
    except ValueError:
        stype = SourceType.MANUAL
    return SourceArtifact(source_id=sid, source_type=stype,
        source_uri=f"pharoah-mcp://{sid}", captured_at=ts,
        transcript=transcript, title_hint=title_hint)


@mcp.tool()
def classify_voicenote(transcript: str, source_id: str | None = None,
                       source_type: str = "manual",
                       captured_at: str | None = None,
                       title_hint: str | None = None) -> dict:
    """Run a transcript through the Pharoah classifier (no dispatch).

    Returns the validated Envelope as a dict. Use dispatch_envelope to write.
    source_type: telegram | voicenote | gdoc | notability | goodnotes | manual
    """
    from pharoah.classifier.classifier import classify
    src = _make_source(transcript, source_id, source_type, captured_at, title_hint)
    env = classify(src)
    return env.model_dump(mode="json")


@mcp.tool()
def dispatch_envelope(envelope: dict) -> dict:
    """Dispatch an already-classified Envelope to its sinks.

    Returns {item_index: [receipts]}. Idempotency / dedup are not enforced here.
    Expect the envelope to come from classify_voicenote.
    """
    from pharoah.classifier.envelope import Envelope
    from classify_one import dispatch
    env = Envelope.model_validate(envelope)
    receipts = dispatch(env, source=None)
    return {str(k): v for k, v in receipts.items()}


@mcp.tool()
def classify_and_dispatch(transcript: str, source_id: str | None = None,
                          source_type: str = "manual",
                          captured_at: str | None = None,
                          title_hint: str | None = None) -> dict:
    """Convenience: classify then immediately dispatch.

    Returns {"envelope": <envelope_dict>, "receipts": {idx: [receipts]}}.
    """
    from pharoah.classifier.classifier import classify
    from classify_one import dispatch
    src = _make_source(transcript, source_id, source_type, captured_at, title_hint)
    env = classify(src)
    receipts = dispatch(env, source=src)
    return {"envelope": env.model_dump(mode="json"),
            "receipts": {str(k): v for k, v in receipts.items()}}


@mcp.tool()
def query_voicenotes_log(limit: int = 20, since_hours: int | None = None) -> list[dict]:
    """Read recent rows from public.pharoah_voicenotes_log via Supabase REST."""
    import httpx
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    qs = f"?select=*&order=captured_at.desc&limit={int(limit)}"
    if since_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        qs += f"&captured_at=gte.{cutoff.isoformat()}"
    r = httpx.get(f"{url}/rest/v1/pharoah_voicenotes_log{qs}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=15)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def list_linear_inbox(team: str = "ben", limit: int = 20) -> list[dict]:
    """List recent open issues in BEN/Inbox (team='ben') or EIR/EIR-Inbox (team='eir')."""
    from shared.clients.linear import LinearClient
    team_key = "Benjamin" if team.lower() == "ben" else "EIR"
    project_name = "Inbox" if team.lower() == "ben" else "EIR-Inbox"
    c = LinearClient()
    q = ("query($team: String!, $limit: Int!) {"
         " issues(filter: { team: { name: { eq: $team } },"
         "                  state: { type: { neq: \"completed\" } } },"
         "       first: $limit, orderBy: updatedAt) {"
         "   nodes { id identifier title url project { name }"
         "           state { name } createdAt } } }")
    d = c._gql(q, {"team": team_key, "limit": int(limit)})
    nodes = d["issues"]["nodes"]
    return [n for n in nodes if (n.get("project") or {}).get("name") == project_name]


@mcp.tool()
def health() -> dict:
    """Sanity check — returns version + tool inventory."""
    from pharoah.classifier.prompts import CLASSIFIER_VERSION
    keys_present = {k: bool(os.environ.get(k))
        for k in ["ANTHROPIC_API_KEY", "LINEAR_API_KEY",
                  "SUPABASE_URL", "SUPABASE_ANON_KEY",
                  "OPENAI_API_KEY", "GROQ_API_KEY"]}
    return {"server": "pharoah-mcp", "classifier_version": CLASSIFIER_VERSION,
            "keys_present": keys_present, "ok": True}


_VALID_RUNTIMES = ("claude", "openclaw", "hermes", "cowork", "paperclip", "system")
_VALID_MSG_TYPES = ("task_request", "task_result", "notification", "briefing", "sync", "heartbeat")
_VALID_PRIORITIES = ("low", "normal", "high", "urgent")


def _supa_headers():
    key = os.environ["SUPABASE_ANON_KEY"]
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "Prefer": "return=representation"}


def _current_surface() -> str:
    """Best-effort identifier for the surface calling pharoah-mcp."""
    return os.environ.get("PHAROAH_SURFACE", "hermes")


@mcp.tool()
def send_pharoah_message(to_surface: str, subject: str, body: str = "",
                          msg_type: str = "notification",
                          priority: str = "normal",
                          correlation_id: str | None = None,
                          payload: dict | None = None) -> dict:
    """Send a message to another Pharoah surface.

    to_surface: cowork | hermes | paperclip | system (must be one of pharoah_runtime enum)
    Stored in public.pharoah_messages. Receiving surface polls via read_pharoah_messages.
    """
    import httpx
    if to_surface not in _VALID_RUNTIMES:
        raise ValueError(f"to_surface must be one of {_VALID_RUNTIMES}")
    if msg_type not in _VALID_MSG_TYPES:
        raise ValueError(f"msg_type must be one of {_VALID_MSG_TYPES}")
    if priority not in _VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {_VALID_PRIORITIES}")
    row = {
        "from_runtime": _current_surface(),
        "to_runtime": to_surface,
        "type": msg_type,
        "priority": priority,
        "subject": subject,
        "payload": {"body": body, **(payload or {})},
        "correlation_id": correlation_id,
    }
    r = httpx.post(f"{os.environ['SUPABASE_URL']}/rest/v1/pharoah_messages",
                   headers=_supa_headers(), json=row, timeout=15)
    r.raise_for_status()
    out = r.json()[0]
    return {"id": out["id"], "to": to_surface, "from": row["from_runtime"],
            "status": out["status"], "created_at": out["created_at"]}


@mcp.tool()
def read_pharoah_messages(unread_only: bool = True, limit: int = 20,
                           to_surface: str | None = None,
                           from_surface: str | None = None) -> list[dict]:
    """Read messages from the Pharoah bus.

    Defaults to unread messages addressed to the current surface.
    Set to_surface to filter by explicit recipient, from_surface to filter by sender.
    """
    import httpx
    to_filter = to_surface or _current_surface()
    parts = [f"to_runtime=eq.{to_filter}",
             "order=created_at.desc",
             f"limit={int(limit)}"]
    if unread_only:
        parts.append("status=eq.pending")
    if from_surface:
        parts.append(f"from_runtime=eq.{from_surface}")
    qs = "&".join(parts)
    r = httpx.get(f"{os.environ['SUPABASE_URL']}/rest/v1/pharoah_messages?{qs}",
                  headers=_supa_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def mark_pharoah_message_read(message_id: str, result: dict | None = None) -> dict:
    """Mark a message as processed (status='completed'). Optional result payload."""
    import httpx
    now_iso = datetime.now(timezone.utc).isoformat()
    body = {"status": "completed", "picked_up_at": now_iso, "completed_at": now_iso}
    if result is not None:
        body["result"] = result
    r = httpx.patch(
        f"{os.environ['SUPABASE_URL']}/rest/v1/pharoah_messages?id=eq.{message_id}",
        headers=_supa_headers(), json=body, timeout=15)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else {"warning": "no row matched", "id": message_id}


@mcp.tool()
def list_active_pharoah_surfaces(within_minutes: int = 60) -> list[dict]:
    """List Pharoah surfaces that have sent or received a message recently.

    Used by an agent to see "who's listening" on the bus right now.
    """
    import httpx
    import urllib.parse
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=int(within_minutes))).isoformat()
    cutoff = urllib.parse.quote(cutoff, safe="")
    qs = f"select=from_runtime,to_runtime,created_at&created_at=gte.{cutoff}&order=created_at.desc&limit=200"
    r = httpx.get(f"{os.environ['SUPABASE_URL']}/rest/v1/pharoah_messages?{qs}",
                  headers=_supa_headers(), timeout=15)
    r.raise_for_status()
    surfaces = {}
    for row in r.json():
        for k, v in (("from", row["from_runtime"]), ("to", row["to_runtime"])):
            surfaces.setdefault(v, {"surface": v, "last_seen": row["created_at"]})
    return list(surfaces.values())


@mcp.tool()
def infisical_get_secret(key: str, project: str = "pharoah",
                          env: str = "dev") -> dict:
    """Fetch a secret on-demand from self-hosted Infisical.

    project: pharoah | platform-agents | expert-os (machine identity scoped accordingly).
    env: dev | prod (etc).
    Returns {"key": ..., "value": ..., "project": ...}. Don't paste the value into chat
    unless explicitly asked — keep it scoped to the tool call that needs it.
    """
    import subprocess
    cmd = ["/home/benjaminbot/bin/infisical-self-hosted",
           "--project", project,
           "secrets", "get", key, "--env", env, "--plain"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError(f"infisical-self-hosted failed: {r.stderr.strip() or r.stdout.strip()}")
    value = r.stdout.strip()
    if not value:
        raise RuntimeError(f"Secret {key!r} not found in {project}/{env}")
    return {"key": key, "value": value, "project": project, "env": env}




# ─── Transport selection ────────────────────────────────────────────────
# PHAROAH_MCP_TRANSPORT=stdio (default, for Hermes child) | http (Cowork via Cloudflare)
# PHAROAH_MCP_HOST=127.0.0.1   PHAROAH_MCP_PORT=8765
# PHAROAH_MCP_BEARER=<token>   required when transport=http; rejects unauthenticated calls.


def _build_http_app():
    """Wrap FastMCP's streamable_http_app with bearer-token auth middleware."""
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    expected = os.environ.get("PHAROAH_MCP_BEARER", "")
    if not expected:
        raise RuntimeError("PHAROAH_MCP_BEARER env var required for http transport")

    class BearerAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            # Health probe path is unauthenticated for monitoring.
            if request.url.path in ("/health", "/_health"):
                return JSONResponse({"ok": True, "server": "pharoah-mcp"})
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer "):
                return JSONResponse({"error": "missing bearer token"}, status_code=401)
            if auth[len("Bearer "):].strip() != expected:
                return JSONResponse({"error": "invalid bearer token"}, status_code=403)
            return await call_next(request)

    mcp.settings.host = os.environ.get("PHAROAH_MCP_HOST", "127.0.0.1")
    mcp.settings.port = int(os.environ.get("PHAROAH_MCP_PORT", "8765"))
    app = mcp.streamable_http_app()
    # Inject middleware into the Starlette app
    app.user_middleware.insert(0, Middleware(BearerAuth))
    app.middleware_stack = app.build_middleware_stack()
    return app


def _main():
    transport = os.environ.get("PHAROAH_MCP_TRANSPORT", "stdio").lower()
    if transport in ("http", "streamable-http"):
        import uvicorn
        log.info(f"pharoah-mcp HTTP mode on {mcp.settings.host if False else os.environ.get('PHAROAH_MCP_HOST','127.0.0.1')}:{os.environ.get('PHAROAH_MCP_PORT','8765')}")
        app = _build_http_app()
        uvicorn.run(app, host=mcp.settings.host, port=mcp.settings.port,
                    log_level="info")
    else:
        log.info("pharoah-mcp stdio mode")
        mcp.run()


if __name__ == "__main__":
    _main()
