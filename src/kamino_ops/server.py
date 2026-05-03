"""Kamino Ops MCP server — entry point.

This module wires the pure tool implementations in :mod:`kamino_ops.tools`
into a :class:`FastMCP` server that speaks JSON-RPC over stdio.

Why stdio? It's the simplest MCP transport — Claude Code spawns this
process per session and pipes JSON-RPC over stdin/stdout. There's no
network surface and no auth to get wrong. v0.4 will introduce HTTP/SSE
for off-host agents; that's a deliberately later milestone because it
expands the threat model.

Why FastMCP? The lower-level :class:`mcp.server.Server` requires manual
schema construction. ``FastMCP`` introspects type hints and docstrings
to build the tool schema automatically, which keeps the wiring tiny and
puts the interesting design (the tools themselves) in plain view.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from kamino_ops import __version__
from kamino_ops.audit import audited
from kamino_ops.tools import resources, system

logger = logging.getLogger(__name__)

# The instructions string is shown to the agent on connect. Keep it short
# and load-bearing: tell the agent what the server is for and what's safe.
mcp = FastMCP(
    name="kamino-ops",
    instructions=(
        "Read-only operations tools for the Kamino homeserver "
        "(Ubuntu host running Plunder, Caddy, and supporting services). "
        "All tools are non-mutating in v0.x. Every call is recorded to an audit log."
    ),
)


# ---------------------------------------------------------------------------
# System tools
# ---------------------------------------------------------------------------


@mcp.tool()
@audited("get_system_info")
def get_system_info() -> dict:
    """Return hostname, kernel, OS info, architecture, and uptime.

    Use this to verify which host the agent is connected to and how
    long it's been up. Cheap; safe to call on every session start.
    """
    return dict(system.get_system_info())


# ---------------------------------------------------------------------------
# Resource tools
# ---------------------------------------------------------------------------


@mcp.tool()
@audited("get_resource_usage")
def get_resource_usage(disk_path: str = "/") -> dict:
    """Return a snapshot of CPU, memory, swap, disk, and load average.

    Args:
        disk_path: Mount path for disk usage. Defaults to ``/``.

    Use this to answer "is anything under pressure right now?". Blocks
    for ~0.5s to get an accurate CPU sample.
    """
    return dict(resources.get_resource_usage(disk_path=disk_path))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server over stdio. Wired to the ``kamino-ops`` console script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info("starting kamino-ops v%s (stdio transport)", __version__)
    mcp.run()


if __name__ == "__main__":
    main()
