"""Anthropic API client — used by the Pharoah classifier."""
from __future__ import annotations

import os
from typing import Any


class AnthropicClient:
    """Thin wrapper around anthropic-sdk-python for classifier calls."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY required")
        self._sdk = None  # lazy-init in BEN-76

    def classify_voicenote(
        self, system_prompt: str, user_message: str,
        envelope_tool_schema: dict[str, Any], model: str,
    ) -> dict[str, Any]:
        """Make a tool-use call with the produce_envelope tool. Returns tool args."""
        raise NotImplementedError("BEN-76: wire up anthropic-sdk-python")
