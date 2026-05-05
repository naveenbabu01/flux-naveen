#!/usr/bin/env python3
"""
MCP SSE Proxy — Bridges stdio (Claude Desktop) to HTTP/SSE (AKS MCP Server).
Claude Desktop spawns this script locally, and it forwards all MCP traffic
to the remote server running on AKS.
"""

import asyncio
import sys
import json
import httpx


MCP_SERVER_URL = "http://48.206.129.154"


async def forward_to_server(request: dict) -> dict:
    """Send a JSON-RPC request to the remote MCP server and return the response."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{MCP_SERVER_URL}/messages/",
            json=request,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


async def main():
    """Read JSON-RPC from stdin, forward to AKS server, write response to stdout."""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    while True:
        line = await reader.readline()
        if not line:
            break

        line = line.decode().strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = await forward_to_server(request)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": str(e)},
                "id": request.get("id") if 'request' in dir() else None,
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
