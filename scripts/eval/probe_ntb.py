import sys, os, zipfile, io, subprocess, tempfile
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient

FILE_ID = "1R77BVcLr5nLO1Stun4vSvTY0lDyzQhG8"
data = GWSClient().download_bytes(FILE_ID)
zf = zipfile.ZipFile(io.BytesIO(data))
print(f"=== {len(zf.infolist())} entries in archive ===")
for info in zf.infolist():
    print(f"  {info.file_size:>10} {info.filename}")
