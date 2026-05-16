from shared.clients.gws import GWSClient
c = GWSClient()
# Walk up the parent chain for each Notability folder
def chain(fid):
    parts = []
    cur = fid
    for _ in range(8):
        m = c.get_file_metadata(cur)
        parts.append(f"{m['name']} ({cur[:8]}...)")
        if not m.get("parents"):
            break
        cur = m["parents"][0]
    return " <- ".join(parts)

for fid, label in [
    ("1UapqHl6PjZ8iptdS6iyIln9a1458gIoK", "Active #1 (PDFs)"),
    ("1HBtlcs_UZ8I_IowiVv4ahi1hbF1sqr5P", "Active #2 (.ntb)"),
]:
    print(f"\n{label}:")
    print(f"  {chain(fid)}")
