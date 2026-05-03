# Architecture

This document explains how Kamino Ops is built and — more importantly — *why it's built that way*.

## The big picture

```
┌─────────────────┐     stdio (JSON-RPC)     ┌──────────────────────┐
│  Claude Code    │ ◄─────────────────────► │  kamino-ops process  │
│  (MCP client)   │                          │  (this repo)         │
└─────────────────┘                          └──────────┬───────────┘
                                                        │
                          ┌─────────────────────────────┼─────────────────────────────┐
                          │                             │                             │
                          ▼                             ▼                             ▼
                  ┌───────────────┐             ┌───────────────┐             ┌───────────────┐
                  │ /proc, psutil │             │  Docker SDK   │             │   systemctl   │
                  │  (resources)  │             │  (containers) │             │  journalctl   │
                  └───────────────┘             └───────────────┘             └───────────────┘
                                                        │                             │
                                                        ▼                             ▼
                                                ┌───────────────────────────────────────┐
                                                │      Kamino (Ubuntu homeserver)       │
                                                │  Docker, systemd, Caddy, Plunder app  │
                                                └───────────────────────────────────────┘
```

The MCP server is a single Python process that Claude Code spawns over stdio when a session starts. Stdio is the simplest MCP transport — no networking, no auth — and it's the right choice for v1 because the agent and the server live on the same machine.

When v0.4 introduces HTTP/SSE transport, agents on other machines will be able to call in. That changes the threat model significantly, which is why it lives in a later milestone, not v1.

## Layering

```
src/kamino_ops/
├── server.py          ← MCP wiring (transport, tool registration, audit log)
└── tools/             ← Tool implementations
    ├── system.py      ← Pure stdlib + os calls
    ├── resources.py   ← psutil
    ├── docker_ops.py  ← docker-py SDK
    └── systemd_ops.py ← subprocess on systemctl/journalctl
```

The split between `server.py` and `tools/` is the most important boundary in the codebase. Tool functions take normal Python types and return normal Python types. They know nothing about MCP. The MCP server imports them and wraps them with `@mcp.tool()` decorators.

**Why?** Three reasons:

1. **Testability.** Unit tests in `tests/` import tool functions directly. No need to spin up a JSON-RPC transport to verify `get_resource_usage()` returns the right shape.
2. **Portability.** If a future client (a Slack bot, a CLI, a web dashboard) wants to call the same logic, it imports from `tools/` and skips the MCP layer.
3. **Reasoning.** When a recruiter — or a future me — is reading the code, the tool implementation is decoupled from the protocol plumbing.

## Tool design principles

Every tool in this repo follows four rules:

### 1. Return structured data, not strings.

Bad: `"CPU: 47%, RAM: 12.3GB used"`. Good: `{"cpu_percent": 47.0, "memory": {"used_gb": 12.3, "total_gb": 32.0}}`. The agent will decide how to summarize. Pre-formatting wastes tokens and erases information.

### 2. Bound output size.

`get_container_logs` defaults to 100 lines, hard caps at 5000. `tail_journal` same. An agent that asks for "all logs since boot" should hit a clear limit, not flood its context window. The limit comes back in the response so the agent knows it was truncated.

### 3. Fail loudly with structured errors.

When `docker.errors.NotFound` fires, the response is `{"ok": false, "error": "container_not_found", "message": "..."}` — not a Python traceback wrapped in a string. Agents reason better about typed errors.

### 4. No hidden side effects.

A tool named `get_*` or `list_*` never writes anywhere except the audit log. This makes the read-only/write split visible at a glance — a property that matters when an agent is choosing what to call.

## Audit log

Every tool call appends one JSON line to `audit.log`:

```json
{"ts": "2026-05-03T17:42:08Z", "tool": "get_container_logs", "args": {"name": "plunder", "lines": 200}, "ok": true, "duration_ms": 47}
```

This serves three purposes:

- **Forensics.** When an agent does something unexpected, the log is the source of truth.
- **Demos.** A sanitized version powers the public dashboard in v0.4.
- **Evals.** v0.5's eval harness replays incident scenarios and grades the agent's tool-call sequence against the log.

The log file is append-only; rotation is the operator's job (logrotate). It's intentionally simple — one JSON object per line, parseable with `jq`.

## Threat model (v1)

v1 is read-only and stdio-only, which dramatically narrows the surface:

| Threat | Mitigation in v1 |
| --- | --- |
| Agent reads sensitive container env vars | Don't expose env-vars from `inspect_container`. Filter known-secret keys. |
| Agent floods context with logs | Hard caps on `tail_journal` and `get_container_logs`. |
| Agent runs unbounded shell | No tool runs a user-supplied command. All `subprocess` calls use fixed binaries with allowlisted flags. |
| Local user runs server with sudo | Server documents and enforces non-root operation. Docker access via the `docker` group. |
| Audit log lost on crash | Each line `flush()`ed; one JSON per line so partial writes are detectable. |

Threats that arrive with v0.2 (write tools) and v0.4 (network transport) are deliberately out of scope here and will be addressed in their own design notes.

## What's *not* here, and why

- **No web framework.** v1 is stdio. Adding FastAPI/Starlette before we need it = premature complexity.
- **No SSH/paramiko.** All tools run *on* Kamino, against the local OS. Cross-host operations are a different problem.
- **No LLM calls.** Kamino Ops doesn't talk to any model. It's the *server side* of a model context. The agent (Claude) is the model side.
- **No retries on read tools.** If `docker stats` fails, the tool returns `{ok: false, error: ...}` and lets the agent decide whether to retry. Retries from the tool would hide failure modes from the audit log.
