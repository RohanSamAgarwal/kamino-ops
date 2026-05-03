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

## Current state (last updated 2026-05-03, end of session 2)

**Shipped at v0.1.0** — repo live at https://github.com/RohanSamAgarwal/kamino-ops, CI green.

- 8 read-only tools across 4 categories:
  - **system**: `get_system_info`
  - **resources**: `get_resource_usage`
  - **docker_ops**: `list_docker_containers`, `get_container_logs`, `get_container_stats`
  - **systemd_ops**: `list_systemd_services`, `get_service_status`, `tail_journal`
- Audit log infrastructure (`@audited` decorator → JSONL on disk) wired into every tool.
- Structured `ok/error` envelope on tools with non-trivial failure modes (docker, systemd).
- 36 passing tests, all subprocess/Docker calls mocked → CI runs anywhere.
- CI matrix: pytest on Ubuntu+Windows × Python 3.11+3.13, plus `ruff check`/`format --check`.
- `.gitattributes` for cross-platform line endings; LICENSE (MIT); README with badges.
- `docs/architecture.md` — layering, threat model, design principles.
- `docs/deployment.md` + `scripts/install-on-kamino.sh` — SSH-installable runbook.

**Not done yet:**

- Run `scripts/install-on-kamino.sh` on Kamino (manual SSH step; Rohan still needs to do this).
- Wire kamino-ops into Claude Code config on Kamino (see `docs/deployment.md`).
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

1. **SSH into Kamino and run `scripts/install-on-kamino.sh`.** Smoke-test will print real hostname/CPU/docker state. This validates the deployment story end-to-end and lets you start collecting "tool calls served from production" numbers for the resume.
2. **Wire into Claude Code on Kamino** (`docs/deployment.md`). Try a real prompt against the agent: *"What's the status of the plunder container and how's CPU looking?"*
3. **v0.2 design discussion** before any code: which mutating tools first? What does the dry-run pattern look like in practice? `restart_service` and `redeploy_from_github` are the obvious starting candidates.
4. **v0.4 stretch** — public dashboard rendering audit-log entries on rohansagarwal.com. This is the artifact a recruiter spends 30 seconds looking at.
