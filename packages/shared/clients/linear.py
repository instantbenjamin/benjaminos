"""Linear API client — create + update issues."""
from __future__ import annotations

import os
from typing import Any

LINEAR_API = "https://api.linear.app/graphql"


class LinearClient:
    """Thin wrapper around Linear GraphQL API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("LINEAR_API_KEY")
        if not self.api_key:
            raise RuntimeError("LINEAR_API_KEY required")

    def create_issue(
        self, title: str, description: str, team_id: str,
        project_id: str | None = None, priority: int | None = None,
    ) -> dict[str, Any]:
        """Create an issue. Returns {id, identifier, url}."""
        raise NotImplementedError("BEN-76: wire up httpx + GraphQL mutation")

    def get_triage_project_id(self) -> str:
        """Return BEN-94 triage project ID (cached)."""
        raise NotImplementedError("BEN-76")
