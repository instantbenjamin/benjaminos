"""GoodNotes pickup cron entrypoint.

Lists .pdf companion files in the canonical GoodNotes folder. For each
notebook, tracks pages_seen in local state. When a notebook's page count
grows, classifies just the NEW pages (incremental dedup).

.goodnotes archives + audio deferred to phase 2 (need page-UUID → page
mapping reverse-engineered).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, UTC
from pathlib import Path

GOODNOTES_FOLDER_ID = "15mY0gOkRtprosIFKWP6KREx-mvzTWe0C"
STATE_FILE = Path("/home/benjaminbot/.pharoah/goodnotes-state.json")
LOG_FILE = Path("/home/benjaminbot/.pharoah/goodnotes-processor.log")


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"notebooks": {}}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"notebooks": {}}


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
    """List .pdf files in the canonical GoodNotes folder."""
    files = gws.list_files_in_folder(
        GOODNOTES_FOLDER_ID, page_size=200)
    return [f for f in files if f["name"].endswith(".pdf")]


def _summarize(receipts):
    counts = {}
    for irs in receipts.values():
        for r in irs:
            dest = r.get("destination", "?").split(":")[0]
            key = f"{dest}_{'err' if 'error' in r else 'ok'}"
            counts[key] = counts.get(key, 0) + 1
    return counts


def process_notebook(meta, state, gws):
    sys.path.insert(0, "/home/benjaminbot/benjaminos")
    from pypdf import PdfReader
    import io
    from ingest.goodnotes_loader import load_pdf_slice
    from pharoah.classifier.classifier import classify
    from scripts.classify_one import dispatch
    fid = meta["id"]
    prev = state.setdefault("notebooks", {}).get(fid, {})
    seen = prev.get("pages_seen", 0)
    pdf_bytes = gws.download_bytes(fid)
    total = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    if total <= seen:
        return False, f"no new pages ({seen}/{total})"
    return _classify_slice(meta, state, gws, seen, total)


def _classify_slice(meta, state, gws, seen, total):
    from ingest.goodnotes_loader import load_pdf_slice
    from pharoah.classifier.classifier import classify
    from scripts.classify_one import dispatch
    try:
        source = load_pdf_slice(meta["id"], seen, total, meta, gws)
        env = classify(source)
        receipts = dispatch(env)
        _record(state, meta, total, env, receipts)
        return True, f"pages {seen+1}-{total} -> {len(env.items)} items {_summarize(receipts)}"
    except Exception as e:
        _log(f"  ERROR: {type(e).__name__}: {e}")
        return False, f"{type(e).__name__}: {e}"


def _record(state, meta, total, env, receipts):
    state["notebooks"][meta["id"]] = {
        "pages_seen": total,
        "last_processed_at": datetime.now(UTC).isoformat(),
        "notebook_name": meta["name"],
        "last_envelope_id": str(env.envelope_id),
        "last_n_items": len(env.items),
        "last_receipts_summary": _summarize(receipts),
    }


def main(limit=10):
    sys.path.insert(0, "/home/benjaminbot/benjaminos")
    from shared.clients.gws import GWSClient
    state = _load_state()
    gws = GWSClient()
    pdfs = discover_pdfs(gws)
    _log(f"GoodNotes: {len(pdfs)} notebooks total")
    todo = _filter_changed(pdfs, state)[:limit]
    _log(f"  {len(todo)} need processing (limit={limit})")
    ok = err = 0
    for meta in todo:
        _log(f"-> {meta['name'][:55]}")
        good, msg = process_notebook(meta, state, gws)
        _log(f"   {'OK' if good else 'SKIP'}: {msg}")
        ok += int(good); err += int(not good)
        _save_state(state)
    _log(f"Done OK={ok} SKIP={err}")
    return 0


def _filter_changed(pdfs, state):
    out = []
    for p in pdfs:
        st = state.get("notebooks", {}).get(p["id"], {})
        last_proc = st.get("last_processed_at", "")
        mt = p.get("modifiedTime", "")
        # If never seen, or mtime > last_processed, include
        if not last_proc or (mt and mt > last_proc):
            out.append(p)
    return out


if __name__ == "__main__":
    sys.exit(main())
