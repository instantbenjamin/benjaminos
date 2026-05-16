import sys, os, zipfile, io
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
from pypdf import PdfReader

c = GWSClient()
FOLDER_ID = "15mY0gOkRtprosIFKWP6KREx-mvzTWe0C"
items = c.list_files_in_folder(FOLDER_ID, page_size=50)
gnote = pdf = None
for it in items:
    if "2026-05-05 Notes" in it["name"]:
        if it["name"].endswith(".goodnotes"): gnote = it
        elif it["name"].endswith(".pdf"): pdf = it
print(f"gnote={gnote['id']}  pdf={pdf['id']}")

data = c.download_bytes(gnote["id"])
zf = zipfile.ZipFile(io.BytesIO(data))
print(f"\n=== .goodnotes ({len(data)} bytes, {len(zf.infolist())} entries) ===")
for info in zf.infolist()[:20]:
    print(f"  {info.file_size:>10} {info.filename}")
