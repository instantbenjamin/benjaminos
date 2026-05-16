"""Smoke test: OCR a real Notability PDF and print results."""
import sys, os
sys.path.insert(0, os.path.expanduser("~/benjaminos"))
from ingest.notability_loader import load_notability_pdf

# Use an old-dated note (likely shorter handwritten content)
FILE_ID = "1l20LSf51scfXqG86LUhrq3TtRpJjfp5g"  # Note Jun 5, 2025
s = load_notability_pdf(FILE_ID)
print(f"source_id: {s.source_id}")
print(f"title_hint: {s.title_hint}")
print(f"captured_at: {s.captured_at.isoformat()}")
print(f"transcript_len: {len(s.transcript)}")
print(f"---")
print(s.transcript[:1500])
