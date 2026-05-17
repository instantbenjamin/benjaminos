"""Pharoah Supabase persistence — voicenote envelopes + corrections."""
from __future__ import annotations

import json
import os
from datetime import datetime, UTC

import httpx


class PharoahDB:
    """Wrapper around Supabase REST for pharoah audit tables (in public)."""

    def __init__(self, url=None, key=None, timeout=30.0):
        self.url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.environ.get("SUPABASE_ANON_KEY")
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL + SUPABASE_ANON_KEY required")
        self._client = httpx.Client(
            base_url=f"{self.url}/rest/v1",
            timeout=timeout,
            headers={"apikey": self.key,
                     "Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json"},
        )

    def is_processed(self, source_id):
        r = self._client.get("/pharoah_voicenotes_log",
            params={"source_id": f"eq.{source_id}",
                    "select": "envelope_id", "limit": "1"})
        r.raise_for_status()
        return len(r.json()) > 0

    def get_envelope(self, source_id):
        r = self._client.get("/pharoah_voicenotes_log",
            params={"source_id": f"eq.{source_id}", "limit": "1"})
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def insert_envelope_with_source(self, envelope, source, receipts):
        s_uri = (source.source_uri if source
                 else f"pharoah://{envelope.source_id}")
        c_at = (source.captured_at if source
                else envelope.classified_at)
        row = self._build_row(envelope, s_uri, c_at, receipts)
        return self._upsert(row)

    def _build_row(self, envelope, source_uri, captured_at, receipts):
        return {
            "envelope_id": str(envelope.envelope_id),
            "source_id": envelope.source_id,
            "source_type": envelope.source_type.value,
            "source_uri": source_uri,
            "captured_at": _iso(captured_at),
            "classified_at": _iso(envelope.classified_at),
            "classifier_model": envelope.classifier_model,
            "classifier_version": envelope.classifier_version,
            "envelope": envelope.model_dump(mode="json"),
            "write_receipts": {str(k): v for k, v in receipts.items()},
            "privacy_flag": envelope.privacy_flag.value,
            "needs_triage": envelope.needs_triage,
        }

    def _upsert(self, row):
        r = self._client.post("/pharoah_voicenotes_log", json=row,
            headers={"Prefer": "resolution=merge-duplicates,return=representation"})
        r.raise_for_status()
        data = r.json()
        return data[0]["envelope_id"] if isinstance(data, list) else row["envelope_id"]


def _iso(dt):
    if isinstance(dt, datetime):
        return dt.astimezone(UTC).isoformat()
    return str(dt) if dt else None
