import sys, os
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient

FOLDER_ID = "15mY0gOkRtprosIFKWP6KREx-mvzTWe0C"
c = GWSClient()
items = c.list_files_in_folder(FOLDER_ID, page_size=50)
print(f"=== {len(items)} items in folder ===")
mimes = {}
for it in items[:30]:
    m = it["mimeType"]
    mimes[m] = mimes.get(m, 0) + 1
    print(f"  [{m:35s}] {it.get('modifiedTime','')[:10]} {it['name'][:50]}")
print(f"\nmime breakdown: {mimes}")
