import sys, os, zipfile, io, re
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
c = GWSClient()
data = c.download_bytes("1cxTgyNShMjHwlJ1kutniMX4qSZoOp3zB")
zf = zipfile.ZipFile(io.BytesIO(data))

# 1) Verify audio file magic bytes
audio = zf.read("attachments/E6B31CFC-F156-4BEF-9A2D-9437F257E6C0")
print(f"audio: {len(audio)} bytes, magic: {audio[:12]!r}")

# 2) Try to find readable text in the .pb files that grew
for name in ["index.events.pb", "index.search.pb", "index.attachments.pb"]:
    raw = zf.read(name)
    runs = re.findall(rb"[ -~]{8,}", raw)  # min 8 chars for meaningful text
    print(f"\n=== {name} ({len(raw)} bytes, {len(runs)} text runs >=8 chars) ===")
    for r in runs[:25]:
        print(f"  | {r.decode('utf-8','replace')[:140]}")
