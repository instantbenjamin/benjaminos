from shared.clients.gws import GWSClient
c = GWSClient()
DAILY_LOG = "176mSHtoMTiBNiPWFL3tapniUah6LA-Zj"
items = c.list_files_in_folder(DAILY_LOG, page_size=200)
print("=== Daily Log children ===")
for it in items:
    mime = it["mimeType"].split(".")[-1]
    print(f"  [{mime:10s}] {it['id']}  {it['name']}")
