"""Linear API client — create + update issues via GraphQL."""
from __future__ import annotations

import os
from typing import Any

import httpx

LINEAR_API = "https://api.linear.app/graphql"


class LinearClient:
    """Thin wrapper around the Linear GraphQL API."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self.api_key = api_key or os.environ.get("LINEAR_API_KEY")
        if not self.api_key:
            raise RuntimeError("LINEAR_API_KEY required")
        self._client = httpx.Client(
            base_url=LINEAR_API, timeout=timeout,
            headers={"Authorization": self.api_key,
                     "Content-Type": "application/json"},
        )
        self._team_cache: dict[str, str] = {}
        self._project_cache: dict[str, str] = {}

    def _gql(self, query: str, variables: dict[str, Any] | None = None
             ) -> dict[str, Any]:
        r = self._client.post("", json={"query": query,
                                        "variables": variables or {}})
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise RuntimeError(f"Linear GraphQL errors: {data['errors']}")
        return data["data"]

    def get_team_id(self, key_or_name: str) -> str:
        """Resolve a team key ('BEN') or name ('Benjamin') to UUID."""
        if key_or_name in self._team_cache:
            return self._team_cache[key_or_name]
        q = "query { teams { nodes { id key name } } }"
        for t in self._gql(q)["teams"]["nodes"]:
            if t["key"] == key_or_name or t["name"] == key_or_name:
                self._team_cache[key_or_name] = t["id"]
                return t["id"]
        raise ValueError(f"Linear team {key_or_name!r} not found")

    def get_project_id(self, name: str, team_id: str | None = None) -> str | None:
        """Resolve a project name to UUID (within team if given). None if missing."""
        cache_key = f"{team_id or '_'}:{name.lower()}"
        if cache_key in self._project_cache:
            return self._project_cache[cache_key]
        q = "query { projects { nodes { id name } } }"
        for p in self._gql(q)["projects"]["nodes"]:
            if p["name"].lower() == name.lower():
                self._project_cache[cache_key] = p["id"]
                return p["id"]
        return None

    def create_issue(self, title: str, description: str = "",
                     team: str = "Benjamin", project: str | None = None,
                     priority: int | None = None) -> dict[str, Any]:
        """Create issue. team is key/name. Returns {id, identifier, url, title}."""
        team_id = self.get_team_id(team)
        inp: dict[str, Any] = {"teamId": team_id, "title": title,
                               "description": description}
        if project:
            pid = self.get_project_id(project, team_id)
            if pid:
                inp["projectId"] = pid
        if priority is not None:
            inp["priority"] = priority
        return self._do_create(inp)

    def _do_create(self, inp: dict[str, Any]) -> dict[str, Any]:
        m = ("mutation($input: IssueCreateInput!) {"
             " issueCreate(input: $input) {"
             "   success issue { id identifier url title } } }")
        d = self._gql(m, {"input": inp})
        return d["issueCreate"]["issue"]
