# Deploying Kamino Ops to Kamino

This guide walks through installing and running Kamino Ops on the
Ubuntu homeserver it was designed for. Total wall-clock time on a
warm server: **~60 seconds**.

> **Why this doc exists.** A portfolio project that runs only on the
> author's laptop is a demo. A portfolio project that runs in
> production is a credential. The procedure below is what makes the
> README's "runs daily against rohansagarwal.com/plunder" claim true.

---

## Prerequisites

On Kamino:

- Python 3.11 or newer (`python3 --version`)
- Git
- The user running the server is in the `docker` group (so the
  Docker SDK can talk to the daemon without root)
- `systemctl` and `journalctl` available (default on Ubuntu)

---

## One-shot install

Copy-paste from a fresh SSH session:

```bash
cd ~
git clone https://github.com/RohanSamAgarwal/kamino-ops.git
cd kamino-ops
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
pytest -q                     # expect 36 passed
which kamino-ops              # expect /home/<you>/kamino-ops/.venv/bin/kamino-ops
```

If pytest is green and `which` finds the binary, the server is ready.

---

## Smoke-test against real systemd / Docker

Run the tools directly (without an MCP client) to confirm they return
real Kamino state:

```bash
python3 - <<'PY'
from kamino_ops.tools import resources, system, docker_ops, systemd_ops

print("system    :", system.get_system_info()["hostname"], system.get_system_info()["os_release"])
print("resources :", resources.get_resource_usage()["cpu"]["percent_total"], "% CPU")
print("docker    :", docker_ops.list_docker_containers()["count"], "containers")
print("systemd   :", systemd_ops.get_service_status("ssh.service")["active_state"])
PY
```

Expected output (yours will differ):

```
system    : kamino 6.8.0-31-generic
resources : 4.7 % CPU
docker    : 3 containers
systemd   : active
```

---

## Wire it into Claude Code on Kamino

If you run Claude Code directly on Kamino, add this to
`~/.config/claude/mcp_servers.json` (or wherever your client expects
MCP server config):

```json
{
  "mcpServers": {
    "kamino-ops": {
      "command": "/home/rohan/kamino-ops/.venv/bin/kamino-ops",
      "args": []
    }
  }
}
```

Restart Claude Code. The tools appear under the `kamino-ops`
namespace. Try asking the agent: *"What's the status of the plunder
container and how's CPU looking?"* — it should call
`list_docker_containers` and `get_resource_usage`.

---

## Run as a systemd user service (optional)

To keep the server warm across sessions (preview of the v0.4 HTTP
transport story), create
`~/.config/systemd/user/kamino-ops.service`:

```ini
[Unit]
Description=Kamino Ops MCP server
After=network.target docker.service

[Service]
Type=simple
ExecStart=%h/kamino-ops/.venv/bin/kamino-ops
Restart=on-failure
Environment=KAMINO_OPS_AUDIT_LOG=%h/kamino-ops/audit.log

[Install]
WantedBy=default.target
```

Then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now kamino-ops
systemctl --user status kamino-ops      # should be 'active (running)'
```

> **Note.** stdio transport assumes a parent process consumes the
> server's stdout. As a long-running unit it'll exit immediately on
> the first read of stdin — that's expected. The unit file is here as
> a placeholder for v0.4 when the server gains an HTTP transport. For
> now, Claude Code spawns it on demand.

---

## Verify the audit log

After any tool call:

```bash
tail -n 5 ~/kamino-ops/audit.log
```

Expect one JSON object per line:

```json
{"ts": "2026-05-03T17:42:08Z", "tool": "get_system_info", "args": {}, "ok": true, "error_kind": null, "duration_ms": 1.83}
```
