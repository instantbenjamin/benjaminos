import sys, os, json, io
from datetime import datetime, UTC
from pathlib import Path
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from pypdf import PdfReader
from shared.clients.gws import GWSClient
from ingest.goodnotes_processor import discover_pdfs

gws = GWSClient()
pdfs = discover_pdfs(gws)
now = datetime.now(UTC).isoformat()
nbs = {}
for p in pdfs:
    pb = gws.download_bytes(p["id"])
    n = len(PdfReader(io.BytesIO(pb)).pages)
    nbs[p["id"]] = {"pages_seen": n,
                    "last_processed_at": now,
                    "notebook_name": p["name"]}
    print(f"  {n} pages  {p['name']}")
sf = Path.home() / ".pharoah" / "goodnotes-state.json"
sf.parent.mkdir(exist_ok=True)
sf.write_text(json.dumps({"notebooks": nbs}, indent=2))
print(f"Seeded {len(nbs)}")
