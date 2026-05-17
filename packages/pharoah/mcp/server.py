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


if __name__ == "__main__":
    mcp.run()
