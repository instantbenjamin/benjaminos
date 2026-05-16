import sys, os, zipfile, io
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
from shared.clients.groq import GroqClient

NTB_ID = "1R77BVcLr5nLO1Stun4vSvTY0lDyzQhG8"
data = GWSClient().download_bytes(NTB_ID)
zf = zipfile.ZipFile(io.BytesIO(data))
m4as = sorted([(i.file_size, i.filename) for i in zf.infolist()
               if i.filename.endswith(".m4a")])
smallest = m4as[0]
print(f"transcribing {smallest[1]} ({smallest[0]} bytes)...")
audio = zf.read(smallest[1])
t = GroqClient().transcribe_audio(audio,
    filename=smallest[1].rsplit("/",1)[-1])
print(f"=== transcript ({len(t)} chars) ===")
print(t[:2000])
