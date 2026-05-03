"""Tool implementations grouped by domain.

Each module exposes pure(ish) functions that are wired into the MCP server in
``kamino_ops.server``. Keeping the wiring separate from the implementations
makes the tools easy to unit-test without spinning up an MCP transport.
"""
