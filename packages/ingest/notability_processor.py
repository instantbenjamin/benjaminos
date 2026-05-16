"""Notability pickup cron entrypoint.

Walks the canonical Notability folder (and its 5 category subfolders) for new
PDFs, dedupes via state JSON, OCRs via Claude vision, classifies + dispatches
each new note. Designed for cron invocation.

.zip / .ntb files (audio-rich notes) are skipped in v1 (phase 2: STT pipeline).
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, UTC
from pathlib import Path

NOTABILITY_FOLDER_ID = "1UapqHl6PjZ8iptdS6iyIln9a1458gIoK"
STATE_FILE = Path("/home/benjaminbot/.pharoah/notability-state.json")
LOG_FILE = Path("/home/benjaminbot/.pharoah/notability-processor.log")


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"processed": {}}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"processed": {}}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def _log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat()
    with open(LOG_FILE, "a") as f:
        f.write(f"{stamp} {msg}\n")
    print(msg, flush=True)


def discover_pdfs(gws):
    """Walk Notability + 5 subfolders. Prefer .zip/.ntb over .pdf."""
    files_by_base = {}
    subfolders = gws.list_files_in_folder(NOTABILITY_FOLDER_ID,
        mime_type="application/vnd.google-apps.folder", page_size=50)
    for sf in subfolders:
        kids = gws.list_files_in_folder(sf["id"], page_size=400)
        for f in kids:
            nm = f["name"]
            if not nm.endswith((".pdf", ".zip", ".ntb")):
                continue
            base = nm.rsplit(".", 1)[0]
            key = (sf["id"], base)
            f["_category"] = sf["name"]
            ex = files_by_base.get(key)
            if not ex or (nm.endswith((".zip", ".ntb"))
                          and not ex["name"].endswith((".zip", ".ntb"))):
                files_by_base[key] = f
    return list(files_by_base.values())


def _summarize(receipts: dict) -> dict:
    counts: dict = {}
    for item_receipts in receipts.values():
        for r in item_receipts:
            dest = r.get("destination", "?").split(":")[0]
            key = f"{dest}_{'err' if 'error' in r else 'ok'}"
            counts[key] = counts.get(key, 0) + 1
    return counts


def process_file(meta, state, gws, anth):
    sys.path.insert(0, "/home/benjaminbot/benjaminos")
    from ingest.notability_loader import load_notability_pdf
    from pharoah.classifier.classifier import classify
    from scripts.classify_one import dispatch
    try:
        s = load_notability_pdf(meta["id"], file_metadata=meta,
                                gws=gws, anthropic=anth)
        env = classify(s)
        receipts = dispatch(env)
        _record(state, meta, env, receipts)
        return True, f"{len(env.items)} items {_summarize(receipts)}"
    except Exception as e:
        _log(f"  ERROR: {type(e).__name__}: {e}")
        return False, f"{type(e).__name__}: {e}"


def _record(state, meta, env, receipts):
    state.setdefault("processed", {})[meta["id"]] = {
        "processed_at": datetime.now(UTC).isoformat(),
        "envelope_id": str(env.envelope_id),
        "n_items": len(env.items),
        "file_name": meta.get("name"),
        "category": meta.get("_category"),
        "receipts_summary": _summarize(receipts),
    }


def main(limit: int = 10):
    sys.path.insert(0, "/home/benjaminbot/benjaminos")
    from shared.clients.gws import GWSClient
    from shared.clients.anthropic import AnthropicClient
    state = _load_state()
    gws = GWSClient()
    anth = AnthropicClient()
    pdfs = discover_pdfs(gws)
    new = [p for p in pdfs if p["id"] not in state.get("processed", {})]
    _log(f"Notability: {len(pdfs)} total, {len(new)} new (limit={limit})")
    new = new[:limit]
    if not new:
        return 0
    ok = err = 0
    for meta in new:
        _log(f"-> [{meta.get('_category','?')}] {meta['name'][:55]}")
        good, msg = process_file(meta, state, gws, anth)
        _log(f"   {'OK' if good else 'FAIL'}: {msg}")
        ok += int(good); err += int(not good)
        _save_state(state)
    _log(f"Done OK={ok} FAIL={err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
