"""ClickUp API client — create tasks in lists. Uses ClickUp v2 REST API."""
from __future__ import annotations

import os
from typing import Any

import httpx

CLICKUP_API = "https://api.clickup.com/api/v2"
INBOX_LIST_ID = "901110606974"  # Benjamin HQ list in the Benjamin space (was 901403040568 — inaccessible from this token)


class ClickUpClient:
    """Thin wrapper around the ClickUp v2 REST API."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self.api_key = api_key or os.environ.get("CLICKUP_API_KEY")
        if not self.api_key:
            raise RuntimeError("CLICKUP_API_KEY required")
        self._client = httpx.Client(
            base_url=CLICKUP_API, timeout=timeout,
            headers={"Authorization": self.api_key,
                     "Content-Type": "application/json"},
        )

    def create_task_in_inbox(self, title: str, description: str = "",
                             due_date: str | None = None,
                             tags: list[str] | None = None,
                             priority: int | None = None) -> dict[str, Any]:
        return self.create_task(INBOX_LIST_ID, title, description,
                                due_date, tags, priority)

    def create_task(self, list_id: str, title: str, description: str = "",
                    due_date: str | None = None,
                    tags: list[str] | None = None,
                    priority: int | None = None) -> dict[str, Any]:
        """Create task. Returns ClickUp's task dict (id, url, etc.)."""
        body: dict[str, Any] = {"name": title, "description": description}
        if tags:
            body["tags"] = tags
        if priority is not None:
            body["priority"] = priority
        if due_date:
            body["due_date"] = _to_clickup_timestamp(due_date)
        r = self._client.post(f"/list/{list_id}/task", json=body)
        r.raise_for_status()
        return r.json()


def _to_clickup_timestamp(due_date) -> int:
    """ClickUp wants Unix epoch ms. Accept ISO date string or date object."""
    from datetime import date, datetime
    if isinstance(due_date, str):
        due_date = date.fromisoformat(due_date)
    return int(datetime(due_date.year, due_date.month, due_date.day).timestamp() * 1000)
