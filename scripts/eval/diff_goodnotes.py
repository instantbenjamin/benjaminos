import sys, os, zipfile, io
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient

c = GWSClient()
GNOTE_ID = "1cxTgyNShMjHwlJ1kutniMX4qSZoOp3zB"
m = c.get_file_metadata(GNOTE_ID)
print(f"file: {m['name']}  mtime: {m.get('modifiedTime')}")
data = c.download_bytes(GNOTE_ID)
zf = zipfile.ZipFile(io.BytesIO(data))
infos = sorted(zf.infolist(), key=lambda i: i.file_size, reverse=True)
print(f"\n=== {len(data)} bytes, {len(infos)} entries (top by size) ===")
for info in infos:
    print(f"  {info.file_size:>10} {info.filename}")
