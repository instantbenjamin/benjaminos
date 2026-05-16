import sys, os, io
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
from pypdf import PdfReader
c = GWSClient()
data = c.download_bytes("1rZiYjIVyJ6hE5cg3KopivV5S39ZAhRbP")
print(f"PDF size: {len(data)} bytes")
r = PdfReader(io.BytesIO(data))
print(f"pages: {len(r.pages)}")
print(f"metadata: {dict(r.metadata) if r.metadata else 'none'}")
total = 0
for i, page in enumerate(r.pages):
    t = page.extract_text() or ""
    total += len(t)
    if i < 3:
        print(f"\n--- page {i+1} ({len(t)} chars) ---")
        print(t[:600])
print(f"\nTOTAL: {total} chars across {len(r.pages)} pages")
