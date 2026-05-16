"""Load a SourceArtifact from a slice of a GoodNotes PDF companion.

GoodNotes exports paired files for each notebook:
- <name>.goodnotes  (native bundle, contains stroke data + attachments incl audio)
- <name>.pdf        (PDF with OCR'd handwriting as embedded text)

For v1 we just process the .pdf (embedded OCR is free via pypdf, no
API cost). Audio is in .goodnotes attachments — phase 2.

Strategy: page-count dedup. State tracks pages_seen per PDF file_id.
When pages > pages_seen, classify ONLY the new pages.
"""
from __future__ import annotations

import io
from datetime import datetime, UTC

from pypdf import PdfReader

from pharoah.classifier.envelope import SourceArtifact, SourceType
from shared.clients.gws import GWSClient


def get_page_count(pdf_bytes: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def load_pdf_slice(file_id, start_page, end_page=None,
                   file_metadata=None, gws=None):
    """Extract text from PDF pages [start, end) -> SourceArtifact."""
    gws = gws or GWSClient()
    meta = file_metadata or gws.get_file_metadata(file_id)
    pdf_bytes = gws.download_bytes(file_id)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total = len(reader.pages)
    if end_page is None:
        end_page = total
    parts = []
    for i in range(start_page, min(end_page, total)):
        t = (reader.pages[i].extract_text() or "").strip()
        parts.append(f"## Page {i+1}\n\n{t}")
    text = "\n\n".join(parts) or "(no extractable text)"
    return _build_src(meta, pdf_bytes, text, start_page, end_page, total)


def _build_src(meta, pdf_bytes, text, start, end, total):
    name = meta.get("name", "GoodNotes")
    title = name.rsplit(".", 1)[0] if "." in name else name
    return SourceArtifact(
        source_id=f"goodnotes:{meta['id']}:p{start}-p{end}",
        source_type=SourceType.NOTABILITY_OCR,
        source_uri=f"gdrive://{meta['id']}",
        captured_at=_parse_at(meta),
        transcript=text,
        title_hint=f"{title} (pages {start+1}-{end})",
        metadata={"notebook_file_id": meta["id"],
                  "notebook_name": name,
                  "page_start": start, "page_end": end,
                  "total_pages": total,
                  "ocr_source": "goodnotes_pdf_embedded"},
    )


def _parse_at(meta):
    mt = meta.get("modifiedTime")
    if mt:
        return datetime.fromisoformat(mt.replace("Z", "+00:00"))
    return datetime.now(UTC)
