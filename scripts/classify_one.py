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


def dispatch(envelope) -> dict:
    """Dispatch each item. Returns {item_index: [receipts]}."""
    receipts: dict = {}
    for item in envelope.items:
        rs = []
        all_dests = [item.destination] + list(item.secondary_destinations)
        for dest in all_dests:
            rs.append(_dispatch_one(item, dest))
        receipts[item.item_index] = rs
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


def _to_linear(item, dest: str) -> dict:
    from shared.clients.linear import LinearClient
    c = LinearClient()
    # destination forms: "linear:benjaminos", "linear:eir:expertos", "linear:triage"
    parts = dest.split(":", 2)
    project = None
    if len(parts) >= 2 and parts[1] != "triage":
        project = parts[1] if parts[1] != "eir" else (parts[2] if len(parts) > 2 else None)
    team = "EIR" if "eir" in dest else "Benjamin"
    issue = c.create_issue(title=item.title, description=item.description,
                           team=team, project=project)
    return {"destination": dest, "id": issue.get("id"),
            "identifier": issue.get("identifier"), "url": issue.get("url")}
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

if __name__ == "__main__":
    main()
