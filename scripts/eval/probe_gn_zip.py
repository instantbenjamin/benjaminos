import sys, os, zipfile, io
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
c = GWSClient()
data = c.download_bytes("1cxTgyNShMjHwlJ1kutniMX4qSZoOp3zB")
zf = zipfile.ZipFile(io.BytesIO(data))
print(f"=== {len(data)} bytes, {len(zf.infolist())} entries ===")
for info in zf.infolist()[:30]:
    print(f"  {info.file_size:>10} {info.filename}")
