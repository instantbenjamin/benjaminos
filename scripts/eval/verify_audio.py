import sys, os, zipfile, io
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
c = GWSClient()
data = c.download_bytes("1cxTgyNShMjHwlJ1kutniMX4qSZoOp3zB")
zf = zipfile.ZipFile(io.BytesIO(data))
# Check audio + waveform magic bytes
big = zf.read("attachments/E6B31CFC-F156-4BEF-9A2D-9437F257E6C0")
small = zf.read("attachments/CF4A3568-4C79-488A-9CE2-14470FC860B2")
print(f"BIG (6.4MB): magic={big[:12]!r}")
print(f"SMALL (284KB): magic={small[:12]!r}")
# Verify mp4 ftyp
print(f"\nBIG mp4 box: {big[4:8]!r} (should be 'ftyp')")
