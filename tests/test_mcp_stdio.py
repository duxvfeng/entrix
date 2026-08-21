from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

try:
    import fastmcp  # noqa: F401
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    pytest.skip("MCP optional dependencies are not installed", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]


async def _list_stdio_tools() -> set[str]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "entrix", "serve"],
        cwd=str(ROOT),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.list_tools()
            return {tool.name for tool in response.tools}


@pytest.mark.integration
def test_mcp_stdio_handshake_lists_public_tools() -> None:
    assert asyncio.run(_list_stdio_tools()) == {
        "run_fitness",
        "get_dimension_status",
        "analyze_change_impact",
    }
