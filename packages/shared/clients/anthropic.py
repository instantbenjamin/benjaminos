"""Anthropic API client — classifier LLM calls with tool-use enforcement."""
from __future__ import annotations

import os
from typing import Any


class AnthropicClient:
    """Thin wrapper around anthropic-sdk-python for tool-use classification."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY required")
        self._sdk = None

    def _client(self):
        if self._sdk is None:
            import anthropic
            self._sdk = anthropic.Anthropic(api_key=self.api_key)
        return self._sdk

    def classify_voicenote(
        self, system_prompt: str, user_message: str,
        envelope_tool_schema: dict[str, Any], model: str,
        max_tokens: int = 8192, temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Tool-use call. Returns the produce_envelope tool's input dict."""
        tool = {
            "name": "produce_envelope",
            "description": "Produce a classified Envelope.",
            "input_schema": envelope_tool_schema,
        }
        resp = self._client().messages.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            system=system_prompt, tools=[tool],
            tool_choice={"type": "tool", "name": "produce_envelope"},
            messages=[{"role": "user", "content": user_message}],
        )
        return self._extract_tool_input(resp)

    @staticmethod
    def _extract_tool_input(resp) -> dict[str, Any]:
        """Pull the tool_use input dict from the response.content blocks."""
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "produce_envelope":
                return block.input
        raise RuntimeError(
            f"No produce_envelope tool_use in response. Got stop_reason={resp.stop_reason}, "
            f"content_types={[getattr(b, 'type', '?') for b in resp.content]}"
        )


    def ocr_pdf(self, pdf_bytes: bytes,
                model: str = "claude-sonnet-4-20250514",
                max_tokens: int = 8192) -> str:
        """OCR a PDF via Claude vision. Returns concatenated transcript."""
        import base64
        b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        prompt = (
            "PDF of handwritten/typed Notability notes. Transcribe ALL "
            "content as plain text/markdown. Preserve structure (headings "
            "as #, lists as -). Mark illegible passages [illegible]. "
            "Output ONLY transcript - no preamble."
        )
        return self._do_ocr(b64, prompt, model, max_tokens)

    def _do_ocr(self, b64_pdf: str, prompt: str, model: str,
                max_tokens: int) -> str:
        resp = self._client().messages.create(
            model=model, max_tokens=max_tokens, temperature=0,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document",
                     "source": {"type": "base64",
                                "media_type": "application/pdf",
                                "data": b64_pdf}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return "".join(b.text for b in resp.content
                       if getattr(b, "type", None) == "text")
