"""Local stdio MCP adapter. No public listener or model-specific business logic."""

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .cli import run


def create_server(config: dict, *, allow_sync: bool = False) -> FastMCP:
    server = FastMCP("BenjaminOS Cinemateca")
    integrations = config.get("mcp_integrations", [])
    if not set(integrations).issubset({"trakt", "google"}):
        raise ValueError("Unknown MCP integration")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    def preview_cinemateca() -> dict:
        """Refresh programming and preview configured list/calendar changes; no list or event writes."""
        return run(config, use_trakt="trakt" in integrations, use_google="google" in integrations)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def cinemateca_status() -> dict:
        """Read the last local plan; it may be stale. Includes fetched_at."""
        path = Path(config["state_dir"]).expanduser() / "plan.json"
        return json.loads(path.read_text()) if path.exists() else {"status": "No run yet"}

    if allow_sync:

        @server.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
            )
        )
        def sync_cinemateca() -> dict:
            """Add reviewed films and upsert screenings for configured personal accounts. Requires user-authorized sync scope."""
            return run(
                config,
                apply=True,
                use_trakt="trakt" in integrations,
                use_google="google" in integrations,
            )

    return server


def main() -> None:
    path = Path(os.environ["CINEMATECA_CONFIG"]).expanduser()
    server = create_server(
        json.loads(path.read_text()), allow_sync=os.environ.get("CINEMATECA_ALLOW_SYNC") == "1"
    )
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
