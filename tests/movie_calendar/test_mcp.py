"""Check agent tool discovery and that writes require operator enablement."""

import pytest

pytest.importorskip("mcp")

from movie_calendar.mcp_server import create_server  # noqa: E402


@pytest.mark.asyncio
async def test_mcp_defaults_to_preview_and_status(tmp_path):
    server = create_server({"state_dir": str(tmp_path)})
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {"preview_cinemateca", "cinemateca_status"}
    assert all(tool.annotations.readOnlyHint for tool in tools)
    result = await server.call_tool("cinemateca_status", {})
    assert "No run yet" in str(result)


@pytest.mark.asyncio
async def test_mcp_write_tool_has_no_account_arguments(tmp_path):
    server = create_server(
        {"state_dir": str(tmp_path), "mcp_integrations": ["trakt"]}, allow_sync=True
    )
    tools = await server.list_tools()
    sync = next(tool for tool in tools if tool.name == "sync_cinemateca")
    assert not sync.annotations.readOnlyHint
    assert sync.inputSchema["properties"] == {}
