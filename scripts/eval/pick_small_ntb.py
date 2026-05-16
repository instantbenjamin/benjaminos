import sys, os
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
from ingest.notability_processor import discover_pdfs
gws = GWSClient()
files = discover_pdfs(gws)
zips = [f for f in files if f["name"].endswith((".zip", ".ntb"))]
print(f"{len(zips)} zip/ntb files. Smallest 5:")
sizes = []
for f in zips:
    m = gws.get_file_metadata(f["id"])
    # size is in metadata under 'size'... actually we need a fresh fetch
    sizes.append((int(m.get("size", 0)) if m.get("size") else 0, f["id"], f["name"]))
sizes.sort()
for sz, fid, nm in sizes[:5]:
    print(f"  {sz:>12} bytes  {fid}  {nm}")
