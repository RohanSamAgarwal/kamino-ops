# CLAUDE.md — Kamino Ops project context

This file is auto-loaded by Claude Code when working in this repo. It captures
**why** the project exists, the **decisions** that have been made, and the
**current state** so any future Claude Code session (on any machine) can pick
up immediately.

## Why this project exists

Portfolio anchor for Microsoft software-developer applications (Rohan, target
applications May–June 2026). Specifically demonstrates:

- **MCP-server authoring** — Anthropic's Model Context Protocol, supported
  across Claude Code, Cursor, VS Code agent mode, Codex, Gemini CLI, and the
  emerging Microsoft agent stack.
- **Real production operation** — agent operates the live homeserver
  (Kamino, Ubuntu) that hosts [rohansagarwal.com/plunder](https://rohansagarwal.com/plunder).
  Not a toy demo against mocks.
- **Engineering judgment** — read-only-first, audited, threat-modelled.

## Key decisions (locked)

| Decision | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11+ | Largest MCP ecosystem; fastest path to ship; Microsoft AI roles want Python. |
| MCP framework | `FastMCP` from `mcp` SDK | Decorator API, auto-generates schema from type hints. Lower-level `Server` would be busywork. |
| Transport (v1) | stdio | Simplest; no network surface, no auth. HTTP/SSE comes in v0.4. |
| Project layout | src-layout | Catches packaging bugs early; standard for modern Python OSS. |
| Build backend | hatchling | Modern, lightweight; standard in 2026. |
| Dev workflow | Hybrid — code on Windows, test on Kamino via SSH | psutil/docker tools return Linux data only; iterate locally for type-check, smoke-test on Kamino. |
| v1 scope | Read-only tools only | Smallest blast radius; demoable in 1–2 sessions; v2 adds writes behind dry-run. |
| Audit log | Day-one, append-only JSONL | "Audited from day one" is a stronger interview answer than "added later." |

## Current state (last updated 2026-05-03)

**Working / tested:**

- Full scaffold: `pyproject.toml`, `README.md`, `docs/architecture.md`, `.gitignore`, `.python-version`.
- venv at `.venv/`, `pip install -e ".[dev]"` succeeds. `mcp 1.27.0`, `docker 7.1.0`, `psutil 7.2.2`.
- `audit.py` — `@audited(name)` decorator; writes one JSONL line per call to `audit.log`. Path overridable via `KAMINO_OPS_AUDIT_LOG` env var.
- `tools/system.py` — `get_system_info()`, returns `SystemInfo` TypedDict (hostname, OS, kernel, uptime).
- `server.py` — FastMCP server named `kamino-ops`, one registered tool (`get_system_info`).
- `tests/test_system.py` — 3 tests, all passing (`pytest -q` clean in 0.13s).

**Not done yet:**

- Resource-usage tool (CPU%, memory, disk, load avg via psutil).
- Docker tools (list, logs, stats).
- systemd tools (list units, status, tail journal).
- Live test on Kamino (clone repo there, install, wire into Claude Code MCP config).
- v0.2 onward (write tools, dry-run pattern, GitHub integration, HTTP transport, dashboard, evals).

## How to resume

```bash
cd C:/Users/rohan/Desktop/CodingProjects/Kamino/kamino-ops
.venv/Scripts/activate                 # Windows
# source .venv/bin/activate             # Linux (Kamino)
pytest -q                                # confirm clean baseline
kamino-ops                               # spawns the MCP server (stdio; will hang waiting for input — Ctrl+C to exit)
```

To connect Claude Code to the local server, add to `~/.claude/mcp_servers.json`:

```json
{
  "mcpServers": {
    "kamino-ops": {
      "command": "C:/Users/rohan/Desktop/CodingProjects/Kamino/kamino-ops/.venv/Scripts/kamino-ops.exe",
      "args": []
    }
  }
}
```

(On Kamino: drop the `.exe`, point at `.venv/bin/kamino-ops`.)

## Conventions to keep

- **Tool naming.** Read tools start with `get_*` or `list_*`. Mutating tools (v0.2+) start with action verbs (`restart_*`, `redeploy_*`).
- **Tool returns.** Always structured (TypedDict / dict), never pre-formatted strings. The agent decides how to summarize.
- **Tool size limits.** Anything that returns logs or lists must accept a `limit` argument and document the default and hard cap.
- **No hidden side effects in `get_*` / `list_*` tools** (other than the audit log).
- **Tests.** Each tool category gets a `tests/test_<category>.py`. Use `monkeypatch` to swap subprocess/docker calls.

## What to do next

1. Implement `tools/resources.py` with `get_resource_usage()` — `psutil.cpu_percent(interval=0.5)`, `virtual_memory()`, `disk_usage('/')`, `getloadavg()` (Linux only — fall back to `None` on Windows so dev-time iteration still works).
2. Wire into `server.py` with `@mcp.tool()` + `@audited(...)`.
3. Add `tests/test_resources.py` with shape assertions only (values vary).
4. Then move to docker, then systemd. Each is its own commit.
