from shared.clients.gws import GWSClient
c = GWSClient()
targets = [
    ("1UapqHl6PjZ8iptdS6iyIln9a1458gIoK", "Notability #1"),
    ("1HBtlcs_UZ8I_IowiVv4ahi1hbF1sqr5P", "Notability #2"),
]
for fid, label in targets:
    print(f"\n=== {label} {fid} ===")
    kids = c.list_files_in_folder(fid, page_size=20)
    for k in kids:
        if k["name"].endswith("Notes"):
            files = c.list_files_in_folder(k["id"], page_size=20)
            print(f"  Notes/ ({k['id']}): {len(files)} files")
            for f in sorted(files, key=lambda x: x.get('modifiedTime',''), reverse=True)[:5]:
                m = f['mimeType'].split('.')[-1]
                print(f"    [{m:8s}] {f.get('modifiedTime','')[:19]} {f['name'][:55]}")
            break
