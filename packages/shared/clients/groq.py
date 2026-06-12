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

    def classify_voicenote(
        self, system_prompt: str, user_message: str,
        envelope_tool_schema: dict, model: str,
        max_tokens: int = 8192, temperature: float = 0.0,
    ) -> dict:
        """Classify a voicenote into Pharoah's Envelope shape using Groq Llama.

        Mirrors AnthropicClient.classify_voicenote so the caller can swap
        providers transparently. Returns the produce_envelope tool's input dict.

        Groq's OpenAI-compatible chat API doesn't (yet) enforce a JSON
        SCHEMA strictly — it does enforce a JSON OBJECT via response_format.
        We inject the schema as a prompt instruction and parse on return.
        On a parse miss we retry once with a stricter reminder.
        """
        import json as _json
        schema_hint = _json.dumps(envelope_tool_schema, indent=2)
        system = (
            system_prompt + "\n\n"
            "CRITICAL: respond with ONE JSON object that conforms exactly to "
            "this schema. No prose, no markdown fences, no preamble. The JSON "
            "object IS the produce_envelope tool input.\n\n"
            "SCHEMA:\n" + schema_hint
        )

        # Truncate over-long transcripts. Llama has 128K context but Groq's
        # per-request byte cap kicks in well before that on meeting transcripts.
        # Routing decisions only need the first ~6K tokens of content.
        MAX_USER_CHARS = 24000
        u = user_message
        if len(u) > MAX_USER_CHARS:
            u = u[:MAX_USER_CHARS] + "\n\n[... transcript truncated for routing classification ...]"

        import time as _time
        def _call(extra_system: str = "") -> dict:
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system + extra_system},
                    {"role": "user",   "content": u},
                ],
            }
            # Retry on 429 / 5xx with exponential backoff. 4 attempts total.
            # VERBOSE_GROQ_ERR: raise on 4xx with the actual response body
            # so we see what's wrong, not just the bare status code.
            for attempt in range(4):
                r = self._client.post("/chat/completions", json=payload)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    wait = float(r.headers.get("retry-after", 0)) or (2 ** attempt)
                    wait = min(wait, 30.0)
                    _time.sleep(wait)
                    continue
                if r.status_code >= 400:
                    raise RuntimeError(
                        f"Groq {r.status_code}: {r.text[:400]}"
                    )
                content = r.json()["choices"][0]["message"]["content"]
                return _json.loads(content)
            if r.status_code >= 400:
                raise RuntimeError(f"Groq {r.status_code}: {r.text[:400]}")
            content = r.json()["choices"][0]["message"]["content"]
            return _json.loads(content)

        try:
            return _call()
        except Exception as e:
            # One retry with a sharper reminder
            return _call("\n\nRETRY: your previous reply did not parse as "
                         "valid JSON. Return ONLY the JSON object.")
