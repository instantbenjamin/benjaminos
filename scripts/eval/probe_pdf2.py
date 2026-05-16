import sys, os, zipfile, io
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
from pypdf import PdfReader

FILE_ID = "1R77BVcLr5nLO1Stun4vSvTY0lDyzQhG8"
data = GWSClient().download_bytes(FILE_ID)
zf = zipfile.ZipFile(io.BytesIO(data))
pdf_name = [n for n in zf.namelist() if n.endswith(".pdf")][0]
pdf_bytes = zf.read(pdf_name)
r = PdfReader(io.BytesIO(pdf_bytes))
print(f"pages: {len(r.pages)}")
print(f"metadata: {dict(r.metadata) if r.metadata else 'none'}")
total = 0
for i, page in enumerate(r.pages):
    t = page.extract_text() or ""
    total += len(t)
    if i < 3:
        print(f"--- page {i+1} ({len(t)} chars) ---\n{t[:200]}")
print(f"\nTOTAL embedded text: {total} chars")
