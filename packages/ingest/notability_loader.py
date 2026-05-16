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


def load_notability_pdf(file_id, file_metadata=None,
                        gws=None, anthropic=None, groq=None):
    """Routes to load_notability_file (handles PDF or .zip/.ntb)."""
    return load_notability_file(file_id, file_metadata,
                                gws, anthropic, groq)


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


def load_notability_file(file_id, file_metadata=None,
                          gws=None, anthropic=None, groq=None):
    """Dispatch by file type. Handles PDF (handwriting only) or .ntb/.zip
    (handwriting via PDF inside + audio transcription via Groq Whisper).
    """
    gws = gws or GWSClient()
    anthropic = anthropic or AnthropicClient()
    meta = file_metadata or gws.get_file_metadata(file_id)
    name = meta.get("name", "")
    mime = meta.get("mimeType", "")
    file_bytes = gws.download_bytes(file_id)
    if name.lower().endswith((".zip", ".ntb")) or "zip" in mime.lower():
        from shared.clients.groq import GroqClient
        groq = groq or GroqClient()
        return _load_from_zip(meta, file_bytes, anthropic, groq)
    return _load_from_pdf(meta, file_bytes, anthropic)


def _load_from_pdf(meta, pdf_bytes, anthropic):
    transcript = anthropic.ocr_pdf(pdf_bytes)
    return _build_source(meta, transcript, pdf_bytes)


def _load_from_zip(meta, zip_bytes, anthropic, groq):
    import zipfile, io
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    pdf_names = [n for n in zf.namelist() if n.endswith(".pdf")]
    handwriting = ""
    if pdf_names:
        handwriting = anthropic.ocr_pdf(zf.read(pdf_names[0]))
    m4as = sorted(n for n in zf.namelist() if n.endswith(".m4a"))
    audio_transcripts = []
    for m_name in m4as:
        ab = zf.read(m_name)
        try:
            t = groq.transcribe_audio(ab,
                filename=m_name.rsplit("/",1)[-1])
        except Exception as e:
            t = f"[transcription failed: {e}]"
        audio_transcripts.append((m_name, t))
    return _build_combined(meta, zip_bytes, handwriting,
                           audio_transcripts)


def _build_combined(meta, zip_bytes, handwriting, audio_transcripts):
    """SourceArtifact combining handwriting OCR + audio transcripts."""
    parts = []
    if handwriting:
        parts.append("## Handwriting\n\n" + handwriting)
    for m_name, t in audio_transcripts:
        short = m_name.rsplit("/", 1)[-1]
        parts.append(f"## Audio: {short}\n\n{t}")
    combined = "\n\n".join(parts) or "(no extractable content)"
    return _build_from_combined(meta, zip_bytes, combined,
                                len(audio_transcripts))


def _build_from_combined(meta, zip_bytes, combined, n_audio):
    captured_at = _parse_captured_at(meta)
    title_hint = _strip_extension(meta.get("name", "Notability note"))
    return SourceArtifact(
        source_id=f"notability:{meta['id']}",
        source_type=SourceType.NOTABILITY_OCR,
        source_uri=f"gdrive://{meta['id']}",
        captured_at=captured_at,
        transcript=combined,
        title_hint=title_hint,
        metadata={
            "file_name": meta.get("name"),
            "drive_modified_time": meta.get("modifiedTime"),
            "zip_size_bytes": len(zip_bytes),
            "audio_count": n_audio,
            "ocr_model": "claude-sonnet-4-20250514",
            "stt_model": "groq:whisper-large-v3-turbo",
        },
    )
