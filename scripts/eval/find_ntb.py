import sys, os
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
c = GWSClient()
ROOT = "1UapqHl6PjZ8iptdS6iyIln9a1458gIoK"
subs = c.list_files_in_folder(ROOT,
    mime_type="application/vnd.google-apps.folder")
total_zips = 0
sample = None
for s in subs:
    zips = c.list_files_in_folder(s["id"], page_size=200)
    for f in zips:
        m = f["mimeType"]
        if "zip" in m.lower() or f["name"].endswith((".zip", ".ntb")):
            total_zips += 1
            if not sample:
                sample = (s["name"], f)
            print(f"[{s['name']:11s}] {m:30s} {f.get('modifiedTime','')[:10]} {f['name']}")
print(f"\nTotal zips/ntb across all subfolders: {total_zips}")
if sample:
    cat, f = sample
    print(f"\nSAMPLE: {cat}/{f['name']} id={f['id']}")
