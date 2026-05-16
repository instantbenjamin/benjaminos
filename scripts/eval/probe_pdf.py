import sys, os, zipfile, io, subprocess, tempfile
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient

FILE_ID = "1R77BVcLr5nLO1Stun4vSvTY0lDyzQhG8"
data = GWSClient().download_bytes(FILE_ID)
zf = zipfile.ZipFile(io.BytesIO(data))
pdf_name = [n for n in zf.namelist() if n.endswith(".pdf")][0]
pdf_bytes = zf.read(pdf_name)
with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
    f.write(pdf_bytes); pdf_path = f.name
r = subprocess.run(["pdftotext", pdf_path, "-"],
    capture_output=True, text=True, timeout=30)
extracted = r.stdout
print(f"pdftotext exit: {r.returncode}")
print(f"extracted len: {len(extracted)}")
print(f"--- first 800 chars ---")
print(extracted[:800])
print(f"--- end ---")
