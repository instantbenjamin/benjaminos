"""ClickUp API client — create tasks in lists."""
from __future__ import annotations

import os
from typing import Any

CLICKUP_API = "https://api.clickup.com/api/v2"
INBOX_LIST_ID = "901403040568"  # Benjamin's personal-task inbox


class ClickUpClient:
    """Thin wrapper around the ClickUp v2 REST API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("CLICKUP_API_KEY")
        if not self.api_key:
            raise RuntimeError("CLICKUP_API_KEY required")

    def create_task_in_inbox(self, title: str, description: str = "",
                             due_date: str | None = None,
                             tags: list[str] | None = None) -> dict[str, Any]:
        return self.create_task(INBOX_LIST_ID, title, description, due_date, tags)

    def create_task(self, list_id: str, title: str, description: str = "",
                    due_date: str | None = None,
                    tags: list[str] | None = None) -> dict[str, Any]:
        """Create a task in list_id. Returns {id, url}."""
        raise NotImplementedError("BEN-76: wire up httpx POST to ClickUp")
