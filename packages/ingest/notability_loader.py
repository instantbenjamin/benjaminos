"""Load a SourceArtifact from a Notability PDF on Drive.

Downloads the PDF via gws.GWSClient + OCRs via Claude vision. Returns
a SourceArtifact ready for classify(). Handles only PDFs in v1; .zip/.ntb
(audio-rich notes) deferred to phase 2.
"""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from pharoah.classifier.envelope import SourceArtifact, SourceType
from shared.clients.gws import GWSClient
from shared.clients.anthropic import AnthropicClient


def load_notability_pdf(file_id: str, file_metadata: dict | None = None,
                        gws: GWSClient | None = None,
                        anthropic: AnthropicClient | None = None,
                        ) -> SourceArtifact:
    """Download + OCR a Notability PDF → SourceArtifact.

    file_metadata is the dict from gws.list_files_in_folder. If not provided,
    we'll fetch it ourselves.
    """
    gws = gws or GWSClient()
    anthropic = anthropic or AnthropicClient()
    meta = file_metadata or gws.get_file_metadata(file_id)
    pdf_bytes = gws.download_bytes(file_id)
    transcript = anthropic.ocr_pdf(pdf_bytes)
    return _build_source(meta, transcript, pdf_bytes)


def _build_source(meta: dict, transcript: str, pdf_bytes: bytes) -> SourceArtifact:
    captured_at = _parse_captured_at(meta)
    title_hint = _strip_extension(meta.get("name", "Notability note"))
    return SourceArtifact(
        source_id=f"notability:{meta['id']}",
        source_type=SourceType.NOTABILITY_OCR,
        source_uri=f"gdrive://{meta['id']}",
        captured_at=captured_at,
        transcript=transcript,
        title_hint=title_hint,
        metadata={
            "file_name": meta.get("name"),
            "drive_modified_time": meta.get("modifiedTime"),
            "pdf_size_bytes": len(pdf_bytes),
            "ocr_model": "claude-sonnet-4-20250514",
        },
    )


def _parse_captured_at(meta: dict) -> datetime:
    """Captured-at: parse from filename 'Note Sep 14, 2024.pdf' else mtime."""
    import re
    name = meta.get("name", "")
    m = re.match(r"Note (\w+) (\d{1,2}),?\s+(\d{4})", name)
    if m:
        try:
            return datetime.strptime(
                f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y"
            ).replace(tzinfo=UTC)
        except ValueError:
            pass
    mt = meta.get("modifiedTime")
    if mt:
        return datetime.fromisoformat(mt.replace("Z", "+00:00"))
    return datetime.now(UTC)


def _strip_extension(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else name
