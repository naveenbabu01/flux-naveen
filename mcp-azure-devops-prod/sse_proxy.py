#!/usr/bin/env python3
"""
MCP SSE Proxy — Bridges stdio (Claude Desktop) ↔ HTTP/SSE (AKS MCP Server).

This uses the official MCP SDK's SSE client transport to connect to the
remote MCP server, while exposing a stdio interface to Claude Desktop.

Usage in claude_desktop_config.json:
{
  "mcpServers": {
    "azure-devops-prod": {
      "command": "python",
      "args": ["C:/Git_Reops/flux-naveen-1/mcp-azure-devops-prod/sse_proxy.py"]
    }
  }
}
"""

import asyncio
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Remote MCP server on AKS
REMOTE_SSE_URL = "http://48.206.129.154/sse"

# Local proxy server (stdio for Claude Desktop)
proxy = Server("mcp-sse-proxy")


@proxy.list_tools()
async def list_tools() -> list[Tool]:
    """Fetch tool list from remote AKS MCP server."""
    async with sse_client(REMOTE_SSE_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return result.tools


@proxy.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Forward tool call to remote AKS MCP server."""
    async with sse_client(REMOTE_SSE_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            return result.content


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await proxy.run(read_stream, write_stream, proxy.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
