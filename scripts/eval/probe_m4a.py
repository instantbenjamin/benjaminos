import sys, os, zipfile, io, tempfile
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from shared.clients.gws import GWSClient
from mutagen.mp4 import MP4

FILE_ID = "1R77BVcLr5nLO1Stun4vSvTY0lDyzQhG8"
data = GWSClient().download_bytes(FILE_ID)
zf = zipfile.ZipFile(io.BytesIO(data))
m4as = sorted(n for n in zf.namelist() if n.endswith(".m4a"))
print(f"=== {len(m4as)} m4a files ===")
for m_name in m4as[:3]:
    audio_bytes = zf.read(m_name)
    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
        f.write(audio_bytes); path = f.name
    a = MP4(path)
    print(f"\n--- {os.path.basename(m_name)} ({len(audio_bytes)} bytes) ---")
    print(f"  length: {a.info.length:.1f}s, codec: {a.info.codec}")
    print(f"  tags: {dict(a.tags) if a.tags else '(none)'}")
    print(f"  keys: {list(a.keys())}")
