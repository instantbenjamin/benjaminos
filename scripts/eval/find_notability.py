from shared.clients.gws import GWSClient
c = GWSClient()
candidates = [
    ("1UapqHl6PjZ8iptdS6iyIln9a1458gIoK", "parent 1BwV4w"),
    ("1ZaEdg422-J35dBTQ-szYkS4wLRQq-m4C", "BenjaminOS root #1"),
    ("1HBtlcs_UZ8I_IowiVv4ahi1hbF1sqr5P", "BenjaminOS root #2"),
    ("1dUOtsNhgwzhOtM_3dFuAoeDlEhJJuc1M", "parent 1mgMP7"),
    ("18zlxBMqL7wMkR8go8KltBK_6ktAFWLHz", "parent 0Bxm3"),
]
for fid, label in candidates:
    try:
        kids = c.list_files_in_folder(fid, page_size=20)
        print(f"\n{label} {fid}: {len(kids)} kids")
        for k in kids[:8]:
            m = k["mimeType"].split(".")[-1]
            t = k.get('modifiedTime','')[:10]
            print(f"  [{m:10s}] {t} {k['name'][:55]}")
    except Exception as e:
        print(f"\n{label}: ERR {str(e)[:80]}")
