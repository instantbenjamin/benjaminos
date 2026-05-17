"""E2E smoke: voicenote -> classify -> dispatch."""
from __future__ import annotations

import argparse
import json

from ingest.voicenote_loader import load_obsidian_voicenote
from pharoah.classifier.classifier import classify


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--no-dispatch", action="store_true")
    args = ap.parse_args()
    source = load_obsidian_voicenote(args.path)
    print(f"=== source: {source.source_id} ===")
    print(f"  captured_at: {source.captured_at.isoformat()}")
    print(f"  transcript: {len(source.transcript)} chars\n")
    envelope = classify(source)
    print_envelope(envelope)
    if not args.no_dispatch:
        r = dispatch(envelope)
        print("\n=== receipts ===")
        print(json.dumps(r, indent=2, default=str))


def print_envelope(e):
    print(f"=== envelope ===")
    print(f"  overall: {e.overall_category.value} | "
          f"privacy: {e.privacy_flag.value} | triage: {e.needs_triage}")
    for it in e.items:
        print(f"  [{it.item_index}] {it.category.value:18s} "
              f"conf={it.confidence:.2f} -> {it.destination}")
        if it.secondary_destinations:
            print(f"         +sec: {it.secondary_destinations}")
        print(f"         title: {it.title}")
        if it.due_date:
            print(f"         due: {it.due_date}")


def dispatch(envelope, source=None) -> dict:
    """Dispatch each item. Returns {item_index: [receipts]}."""
    receipts: dict = {}
    for item in envelope.items:
        rs = []
        all_dests = [item.destination] + list(item.secondary_destinations)
        for dest in all_dests:
            rs.append(_dispatch_one(item, dest))
        receipts[item.item_index] = rs
    _persist_envelope(envelope, source, receipts)
    return receipts


def _dispatch_one(item, dest: str) -> dict:
    """Dispatch one item to one destination. Returns receipt dict."""
    try:
        if dest.startswith("clickup:"):
            return _to_clickup(item, dest)
        if dest.startswith("linear:"):
            return _to_linear(item, dest)
        if dest.startswith("wiki:"):
            return _to_wiki(item, dest)
        if dest.startswith("supabase:"):
            return _to_supabase(item, dest)
        if dest == "gbrain":
            return _to_gbrain(item, dest)
        # Other sinks not yet wired
        return {"destination": dest, "skipped": "not_implemented"}
    except Exception as e:
        return {"destination": dest, "error": f"{type(e).__name__}: {e}"}


def _to_clickup(item, dest: str) -> dict:
    from shared.clients.clickup import ClickUpClient, INBOX_LIST_ID
    c = ClickUpClient()
    list_id = INBOX_LIST_ID if dest == "clickup:inbox" else dest.split(":", 1)[1]
    due_str = item.due_date.isoformat() if item.due_date else None
    tags = list(item.extracted_entities.tags) + ["pharoah"]
    r = c.create_task(list_id=list_id, title=item.title,
                      description=item.description, due_date=due_str,
                      tags=tags)
    return {"destination": dest, "id": r.get("id"), "url": r.get("url")}



BEN_PROJECT_SLUGS = {
    "benjaminos": "BenjaminOS",
    "financeos": "FinanceOS",
    "personal-life": "Personal-Life",
    "personal": "Personal-Life",
    "pharoah-daily": "Pharoah-Daily",
    "adventureos": "BenjaminOS",
    "inbox": "Inbox",
    "triage": "Inbox",
}

EIR_PROJECT_SLUGS = {
    "expertos": "EIR-ExpertOS",
    "marketing": "EIR-Marketing",
    "financeops": "EIR-Finance+Ops",
    "ecosystem-build": "EIR-Ecosystem-Build",
    "ecosystem-design": "EIR-Ecosystem Design",
    "ecosystem-management": "EIR-Ecosystem-Management",
    "civic": "EIR-CivicOS",
    "civicos": "EIR-CivicOS",
    "speaker-bureau": "EIR-Speaker-Bureau",
    "craig-wing": "EIR-Craig-Wing",
    "craig": "EIR-Craig-Wing",
    "brad-shuck": "EIR-Brad-Shuck",
    "brad": "EIR-Brad-Shuck",
    "steve-cadigan": "EIR-Steve-Cadigan",
    "steve": "EIR-Steve-Cadigan",
    "inbox": "EIR-Inbox",
    "triage": "EIR-Inbox",
}


def _parse_linear_destination(dest: str):
    if not dest.startswith("linear:"):
        raise ValueError(f"Not a linear destination: {dest}")
    rest = dest[len("linear:"):]
    parts = rest.split(":", 1)
    head = parts[0].lower()
    tail = parts[1].lower() if len(parts) > 1 else None
    if head == "ben":
        slug = tail or "inbox"
        return ("Benjamin", BEN_PROJECT_SLUGS.get(slug, "Inbox"))
    if head == "eir":
        slug = tail or "inbox"
        return ("EIR", EIR_PROJECT_SLUGS.get(slug, "EIR-Inbox"))
    if head == "triage":
        return ("Benjamin", "Inbox")
    if head in BEN_PROJECT_SLUGS:
        return ("Benjamin", BEN_PROJECT_SLUGS[head])
    if head in EIR_PROJECT_SLUGS:
        return ("EIR", EIR_PROJECT_SLUGS[head])
    return ("Benjamin", "Inbox")


def _to_linear(item, dest: str) -> dict:
    from shared.clients.linear import LinearClient
    team, project = _parse_linear_destination(dest)
    c = LinearClient()
    issue = c.create_issue(title=item.title, description=item.description,
                           team=team, project=project)
    return {"destination": dest, "team": team, "project": project,
            "id": issue.get("id"),
            "identifier": issue.get("identifier"),
            "url": issue.get("url")}


def _to_wiki(item, dest: str) -> dict:
    """Dispatch wiki:<path>/<file>.md. Creates file w/ unique stamped name."""
    from shared.clients.gws import GWSClient, WIKI_FOLDER_ID
    from datetime import datetime
    path = dest[len("wiki:"):]
    if path.endswith("/"):
        path = path + _slugify(item.title) + ".md"
    parts = path.split("/")
    folder_parts, filename = parts[:-1], parts[-1]
    c = GWSClient()
    folder_id = c.resolve_folder_path(WIKI_FOLDER_ID, *folder_parts)
    base, _, ext = filename.rpartition(".")
    ext = ext or "md"; base = base or filename
    unique = f"{base}-{datetime.now().strftime('%H%M')}-pharoah.{ext}"
    content = _format_wiki_content(item)
    r = c.create_text_file(folder_id, unique, content)
    return {"destination": dest, "id": r["id"], "name": r["name"],
            "url": r.get("webViewLink")}


def _slugify(text: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "entry"


def _format_wiki_content(item) -> str:
    """Markdown content for a wiki entry from an Item."""
    from datetime import datetime, UTC
    lines = ["---",
             f"title: {item.title}",
             f"created: {datetime.now(UTC).isoformat()}",
             "source: pharoah_classifier",
             f"category: {item.category.value}"]
    if item.subcategory:
        lines.append(f"subcategory: {item.subcategory}")
    if item.extracted_entities.tags:
        lines.append(f"tags: [{', '.join(item.extracted_entities.tags)}]")
    lines.append(f"confidence: {item.confidence}")
    lines.append("---\n")
    lines.append(f"# {item.title}\n")
    if item.description:
        lines.append(item.description + "\n")
    if item.reasoning:
        lines.append(f"_Classifier reasoning: {item.reasoning}_")
    return "\n".join(lines) + "\n"



def _to_supabase(item, dest: str) -> dict:
    """supabase:* destinations -> public.notes for v1."""
    import os, httpx
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    payload = {
        "source": "voice_memo",
        "title": item.title,
        "raw_text": item.description,
        "summary": item.reasoning or item.title,
        "tags": list(item.extracted_entities.tags) + [item.category.value],
        "metadata": {"destination": dest,
                     "subcategory": item.subcategory,
                     "confidence": item.confidence,
                     "pharoah_source": "voicenote_classifier"},
    }
    return _post_to_supabase(url, key, "notes", payload, dest)


def _post_to_supabase(url, key, table, payload, dest):
    import httpx
    r = httpx.post(f"{url}/rest/v1/{table}",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Prefer": "return=representation"},
        json=payload, timeout=30)
    r.raise_for_status()
    row = r.json()[0] if isinstance(r.json(), list) else r.json()
    return {"destination": dest, "table": f"public.{table}",
            "id": row.get("id"), "title": row.get("title")}


def _to_gbrain(item, dest: str) -> dict:
    """Dispatch to gbrain via CLI subprocess."""
    lines = ["---", f"title: {item.title}",
             f"source: pharoah_classifier",
             f"category: {item.category.value}",
             f"confidence: {item.confidence}", "---\n",
             f"# {item.title}\n"]
    if item.description:
        lines.append(item.description + "\n")
    if item.reasoning:
        lines.append(f"_Classifier reasoning: {item.reasoning}_")
    body = "\n".join(lines) + "\n"
    return _exec_gbrain_put(item, body, dest)


def _exec_gbrain_put(item, body, dest):
    import subprocess, tempfile, os
    GBRAIN = "/home/benjaminbot/.bun/bin/gbrain"
    env = os.environ.copy()
    env["PATH"] = "/home/benjaminbot/.bun/bin:" + env.get("PATH", "")
    gb_env = "/home/benjaminbot/.gbrain/.env"
    if os.path.exists(gb_env):
        for line in open(gb_env):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env.setdefault(k, v)
    return _run_gbrain(GBRAIN, body, env, dest, item)


def _run_gbrain(bin_path, body, env, dest, item):
    """gbrain put requires --content flag and inline-embeds (needs OpenAI key)."""
    import subprocess, re
    slug = "pharoah/voicenotes/" + (
        re.sub(r"[^a-zA-Z0-9-]+", "-", item.title.lower()).strip("-")[:50]
        or "entry"
    )
    try:
        r = subprocess.run(
            [bin_path, "put", slug, "--content", body],
            env=env, capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return {"destination": dest, "slug": slug,
                "error": "gbrain put timed out (OpenAI embed likely)"}
    if r.returncode != 0:
        return {"destination": dest, "slug": slug,
                "error": (r.stderr or r.stdout)[:300]}
    return {"destination": dest, "slug": slug,
            "stdout": r.stdout[:200].strip()}

def _persist_envelope(envelope, source, receipts):
    """Write envelope to pharoah.voicenotes_log. Fail-soft."""
    try:
        from shared.clients.pharoah_db import PharoahDB
        db = PharoahDB()
        # If we have a SourceArtifact, use its captured_at; else fall back
        if source is not None:
            envelope.transcript_excerpt = source.transcript[:200]
        db.insert_envelope_with_source(envelope, source, receipts)
    except Exception as e:
        import sys
        print(f"[pharoah_db] persist failed: {type(e).__name__}: {e}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
