import sys, os
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
gws = GWSClient()
ids = ["11_5ZKjHZ_fAp1xTYEZan6FMen_Pgup5r",
       "1DCGpnoVEAmUgiH7lTs-BX0umwZn23c-i",
       "1EHkRpxwSTzf1ia-6r4CEZ8n0Y0PDGILr",
       "1IWn7Ib2EfgK8IvvB-VFnYpJ-ZRtmYC6M",
       "1N5xcWs_1tXRO2HHtkdKBIOJ1auBvcsDL"]
for fid in ids:
    m = gws._drive_service().files().get(fileId=fid,
        fields="id,name,size",
        supportsAllDrives=True).execute()
    print(f"{int(m.get('size',0)):>12}  {fid}  {m['name']}")
