"""MCP server instance and entrypoint."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("estonian-transport")


def main():
    import estonian_transport_mcp.tools  # noqa: F401 — registers @mcp.tool() handlers
    mcp.run()
