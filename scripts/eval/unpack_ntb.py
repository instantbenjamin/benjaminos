import sys, os, zipfile, io
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient

FILE_ID = "1R77BVcLr5nLO1Stun4vSvTY0lDyzQhG8"
gws = GWSClient()
data = gws.download_bytes(FILE_ID)
print(f"downloaded {len(data)} bytes")

zf = zipfile.ZipFile(io.BytesIO(data))
print(f"\n=== contents ({len(zf.infolist())} entries) ===")
for info in zf.infolist():
    print(f"  {info.file_size:>10} bytes  {info.filename}")
