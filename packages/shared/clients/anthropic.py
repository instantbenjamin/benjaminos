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
