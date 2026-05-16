import sys, os, zipfile, io
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
from pypdf import PdfReader

c = GWSClient()
FOLDER_ID = "15mY0gOkRtprosIFKWP6KREx-mvzTWe0C"
items = c.list_files_in_folder(FOLDER_ID, page_size=50, mime_type=None)
gns = [it for it in items if it["name"].endswith(".goodnotes")]
pdfs = [it for it in items if it["name"].endswith(".pdf")]
print(f"goodnotes={len(gns)} pdfs={len(pdfs)}")
if gns: print(f"first goodnotes: {gns[0]['name']} id={gns[0]['id']}")
if pdfs: print(f"first pdf: {pdfs[0]['name']} id={pdfs[0]['id']}")
