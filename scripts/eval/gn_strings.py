import sys, os, zipfile, io, re
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
c = GWSClient()
data = c.download_bytes("1cxTgyNShMjHwlJ1kutniMX4qSZoOp3zB")
zf = zipfile.ZipFile(io.BytesIO(data))
# Largest search file
search_files = sorted([(i.file_size, i.filename) for i in zf.infolist()
    if i.filename.startswith("search/")], reverse=True)
print(f"{len(search_files)} search files (top 3 sizes):")
for s, n in search_files[:3]:
    print(f"  {s} {n}")
raw = zf.read(search_files[0][1])
runs = re.findall(rb"[ -~]{4,}", raw)
print(f"\nASCII runs >=4 chars: {len(runs)}")
for r in runs[:40]:
    print(f"  | {r.decode('utf-8','replace')[:120]}")
