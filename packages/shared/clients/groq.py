"""Groq client — Whisper STT (and optionally cheap LLM access).

Groq exposes an OpenAI-compatible API at api.groq.com/openai/v1, so we
just point httpx at the right base_url. Whisper-V3-Large-Turbo is fast +
cheap (~$0.04/hour of audio).
"""
from __future__ import annotations

import os
from typing import Any

import httpx

GROQ_API = "https://api.groq.com/openai/v1"
DEFAULT_WHISPER_MODEL = "whisper-large-v3-turbo"


class GroqClient:
    """Thin wrapper around Groq's OpenAI-compatible API."""

    def __init__(self, api_key: str | None = None, timeout: float = 120.0):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY required")
        self._client = httpx.Client(
            base_url=GROQ_API, timeout=timeout,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def transcribe_audio(
        self, audio_bytes: bytes, filename: str = "audio.m4a",
        model: str = DEFAULT_WHISPER_MODEL, language: str | None = None,
        prompt: str | None = None,
    ) -> str:
        """Transcribe audio via Groq Whisper. Returns the transcript text."""
        # Derive mime type from the filename extension. Groq Whisper accepts:
        # flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm.
        _MIME = {
            ".m4a": "audio/m4a", ".mp4": "audio/mp4",
            ".wav": "audio/wav", ".mp3": "audio/mpeg",
            ".aac": "audio/aac", ".flac": "audio/flac",
            ".ogg": "audio/ogg", ".webm": "audio/webm",
        }
        import os as _os
        _ext = _os.path.splitext(filename)[1].lower()
        files = {"file": (filename, audio_bytes, _MIME.get(_ext, "audio/m4a"))}
        data: dict[str, Any] = {"model": model, "response_format": "text"}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt
        r = self._client.post("/audio/transcriptions", files=files, data=data)
        r.raise_for_status()
        return r.text.strip()
