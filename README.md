# Kamino Ops

**A Model Context Protocol (MCP) server that lets AI agents safely operate a real production homeserver.**

[![CI](https://github.com/RohanSamAgarwal/kamino-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/RohanSamAgarwal/kamino-ops/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/protocol-MCP%201.x-7c3aed)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Kamino Ops exposes my Ubuntu homeserver — codenamed **Kamino** — to Claude Code (and any other MCP-compatible agent: Cursor, Codex, Gemini CLI, VS Code Copilot agents) through a small, auditable, read-first toolset. It runs every day to operate the production deployment of [rohansagarwal.com/plunder](https://rohansagarwal.com/plunder), a multiplayer board game that serves real users.

> **Why this exists.** Most "AI ops" demos are toys against mocks. This one runs against a live server, with a deliberate read-only-first design and an audit log. The goal is to demonstrate that AI agents can be safely given operational authority over real infrastructure when the tool surface is designed for it.

---

## What it does

| Tool | Surface | Purpose |
| --- | --- | --- |
| `get_system_info` | `/proc`, `os` | Hostname, kernel, uptime, OS version |
| `get_resource_usage` | `psutil` | CPU%, memory, disk, load average |
| `list_docker_containers` | Docker SDK | All containers with status, image, ports |
| `get_container_logs` | Docker SDK | Tail the last N lines from any container |
| `get_container_stats` | Docker SDK | Live CPU/mem stats for a container |
| `list_systemd_services` | `systemctl` | Unit name, state, sub-state, description |
| `get_service_status` | `systemctl` | Detailed status for one unit |
| `tail_journal` | `journalctl` | Last N lines from a service's journal |

**v1 is read-only by design.** Mutating actions (`restart_service`, `redeploy_from_github`) land in v2 behind a dry-run/confirmation pattern. This sequencing reflects a deliberate threat-modelling decision — see [`docs/architecture.md`](docs/architecture.md).

---

## Why MCP, why now

[Model Context Protocol](https://modelcontextprotocol.io/) is the open protocol Anthropic introduced in late 2024 for connecting AI assistants to data sources and tools. By mid-2026 it's supported across Claude Code, Cursor, VS Code's agent mode, Gemini CLI, OpenAI Codex, and Microsoft's emerging agent stack. Building an MCP server — rather than a single-vendor plugin — means the same code serves every AI client I (or a recruiter evaluating this project) might want to use.

The interesting design problem is **not** "how do I call subprocess from Python." It's:

1. **Tool surface design** — what's the smallest, sharpest set of tools that lets an agent answer real operational questions?
2. **Output design** — agents pay tokens for every byte you return. How do you give them enough context to act, without flooding them?
3. **Safety** — read-only first; later, dry-runs and confirmations on writes; always an audit log.
4. **Observability** — when an agent does something surprising, can you reconstruct *why* from the tool calls alone?

This repo is my answer to those four questions.

---

## Installation

```bash
git clone https://github.com/RohanSamAgarwal/kamino-ops.git
cd kamino-ops
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Wire it into Claude Code by adding to `~/.claude/mcp_servers.json`:

```json
{
  "mcpServers": {
    "kamino-ops": {
      "command": "kamino-ops",
      "args": []
    }
  }
}
```

Restart Claude Code. The tools appear under the `kamino-ops` namespace.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the long version. In one paragraph:

The server is a stdio-transport MCP process spawned per Claude Code session. Tool implementations live in `src/kamino_ops/tools/` grouped by surface (system, resources, docker, systemd) and are wired into the MCP server in `server.py`. Every tool call is recorded to an append-only audit log (`audit.log`) with timestamp, tool name, arguments, and outcome. v2 will add HTTP/SSE transport so agents running off-server can call in over Tailscale.

---

## Roadmap

- **v0.1** (this repo) — Read-only tools over a stdio transport. Audit log to disk.
- **v0.2** — Mutating tools (`restart_service`, `redeploy_from_github`) with dry-run mode and required-confirmation argument.
- **v0.3** — GitHub integration (`open_issue_for_failure`, `link_run_to_pr`).
- **v0.4** — HTTP/SSE transport with Tailscale-only auth, public dashboard rendering audit log entries (sanitized) on rohansagarwal.com.
- **v0.5** — Eval harness: synthetic incident scenarios, measure agent resolution rate.

---

## License

MIT.
