"""Supabase client wrapper — Pharoah schema reads + writes."""
from __future__ import annotations

import os
from typing import Any


class SupabaseClient:
    """Thin wrapper around supabase-py for the Pharoah schema."""

    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = url or os.environ.get("SUPABASE_URL")
        self.key = key or os.environ.get("SUPABASE_SERVICE_KEY")
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
        self._client = None  # lazy-init in BEN-76

    def insert_voicenote_log(self, envelope: dict[str, Any]) -> str:
        raise NotImplementedError("BEN-76: wire up supabase-py")

    def insert_habit(self, item: dict[str, Any]) -> str:
        raise NotImplementedError("BEN-76")
