from __future__ import annotations

from mcp.server import Server
from mcp.server.stdio import stdio_server

from evidence_gate.mcp_server.tools import register_tools

app = Server("evidence_gate")
register_tools(app)


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
