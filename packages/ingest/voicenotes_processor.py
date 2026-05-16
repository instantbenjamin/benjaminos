"""Voicenote pickup cron entrypoint.

Scans ~/wiki/voicenotes/ for new markdown files (Obsidian-plugin voicenotes),
skips files already in local state JSON, classifies + dispatches each new
one, appends to state. Designed for cron invocation every 30 min.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, UTC
from pathlib import Path

VN_DIR = Path("/home/benjaminbot/wiki/voicenotes")
STATE_FILE = Path("/home/benjaminbot/.pharoah/voicenote-state.json")
LOG_FILE = Path("/home/benjaminbot/.pharoah/voicenote-processor.log")


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


def _is_already_processed(state: dict, path: Path) -> bool:
    return str(path) in state.get("processed", {})


def _mark_processed(state: dict, path: Path,
                    envelope_id: str, n_items: int,
                    receipts: dict):
    state.setdefault("processed", {})[str(path)] = {
        "processed_at": datetime.now(UTC).isoformat(),
        "envelope_id": envelope_id,
        "n_items": n_items,
        "receipts_summary": _summarize(receipts),
    }


def _summarize(receipts: dict) -> dict:
    """Compact summary of receipts: {destination_prefix: count_ok/count_err}."""
    counts = {}
    for item_receipts in receipts.values():
        for r in item_receipts:
            dest = r.get("destination", "?").split(":")[0]
            key = f"{dest}_{'err' if 'error' in r else 'ok'}"
            counts[key] = counts.get(key, 0) + 1
    return counts


def process_file(path: Path, state: dict) -> tuple[bool, str]:
    """Classify + dispatch one voicenote. Returns (ok, message)."""
    sys.path.insert(0, "/home/benjaminbot/benjaminos")
    from ingest.voicenote_loader import load_obsidian_voicenote
    from pharoah.classifier.classifier import classify
    from scripts.classify_one import dispatch
    try:
        source = load_obsidian_voicenote(path)
        envelope = classify(source)
        receipts = dispatch(envelope)
        _mark_processed(state, path, str(envelope.envelope_id),
                        len(envelope.items), receipts)
        return True, f"{len(envelope.items)} items {_summarize(receipts)}"
    except Exception as e:
        _log(f"  ERROR on {path.name}: {type(e).__name__}: {e}")
        return False, f"{type(e).__name__}: {e}"


def main():
    state = _load_state()
    files = sorted(VN_DIR.glob("*.md"))
    if not files:
        _log(f"No voicenotes in {VN_DIR}"); return 0
    new = [p for p in files if not _is_already_processed(state, p)]
    _log(f"Processor: {len(files)} total, {len(new)} new")
    if not new:
        return 0
    ok = err = 0
    for path in new:
        _log(f"-> {path.name}")
        good, msg = process_file(path, state)
        _log(f"   {'OK' if good else 'FAIL'}: {msg}")
        if good: ok += 1
        else: err += 1
        _save_state(state)
    _log(f"Done. OK={ok} FAIL={err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
