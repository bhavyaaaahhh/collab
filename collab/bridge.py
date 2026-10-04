"""stdio MCP server launched by each agent CLI. Forwards room tool calls to the collab app over HTTP.

Env: COLLAB_URL (app base URL), COLLAB_RUN (run id), COLLAB_AGENT (this agent's name).
"""

import os

import anyio
import httpx
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from collab.room.tools import TOOL_DEFS

URL = os.environ.get("COLLAB_URL", "http://127.0.0.1:4747")
RUN = os.environ.get("COLLAB_RUN", "")
AGENT = os.environ.get("COLLAB_AGENT", "")

# Longer than wait_for_messages blocks, shorter than the CLIs' MCP tool timeouts (120s).
HTTP_TIMEOUT_S = 90


async def list_tools(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[types.Tool.model_validate(t) for t in TOOL_DEFS])


async def call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
            res = await client.post(
                f"{URL}/api/runs/{RUN}/tool",
                json={"agent": AGENT, "name": params.name, "args": params.arguments or {}},
            )
            res.raise_for_status()
            text = res.json()["text"]
    except httpx.HTTPError as e:
        text = f"Error: collab app unreachable ({e.__class__.__name__}: {e})"
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)])


server = Server("room", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
