import sys, json, os
from datetime import datetime, UTC
from pathlib import Path
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
from ingest.notability_processor import discover_pdfs

pdfs = discover_pdfs(GWSClient())
state_file = Path.home() / ".pharoah" / "notability-state.json"
state_file.parent.mkdir(exist_ok=True)
now = datetime.now(UTC).isoformat()
state = {"processed": {p["id"]: {"processed_at": now, "envelope_id": "seeded",
    "n_items": 0, "file_name": p["name"], "category": p.get("_category"),
    "note": "Pre-seeded; not actually processed."} for p in pdfs}}
state_file.write_text(json.dumps(state, indent=2))
print(f"Seeded {len(pdfs)} Notability PDFs")
