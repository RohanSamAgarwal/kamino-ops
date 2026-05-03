#!/usr/bin/env bash
# install-on-kamino.sh — clone, install, and smoke-test Kamino Ops on a
# fresh Ubuntu server. Idempotent; safe to re-run.
#
# Usage (from any SSH session on Kamino):
#   curl -fsSL https://raw.githubusercontent.com/RohanSamAgarwal/kamino-ops/main/scripts/install-on-kamino.sh | bash
#
# Or (recommended — review before piping shell scripts to bash):
#   git clone https://github.com/RohanSamAgarwal/kamino-ops.git
#   cd kamino-ops
#   bash scripts/install-on-kamino.sh

set -euo pipefail

REPO_URL="https://github.com/RohanSamAgarwal/kamino-ops.git"
INSTALL_DIR="${KAMINO_OPS_HOME:-$HOME/kamino-ops}"

echo "==> Kamino Ops installer"
echo "    target dir: $INSTALL_DIR"
echo

# 1. Clone or update the repo.
if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "==> Repo exists; pulling latest"
    git -C "$INSTALL_DIR" pull --ff-only
else
    echo "==> Cloning repo"
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# 2. Create / refresh virtualenv.
if [[ ! -d .venv ]]; then
    echo "==> Creating virtualenv"
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 3. Install package.
echo "==> Installing package"
pip install --upgrade pip --quiet
pip install -e ".[dev]" --quiet

# 4. Smoke-test.
echo "==> Running tests"
pytest -q

echo "==> Verifying real-system access"
python3 - <<'PY'
from kamino_ops.tools import docker_ops, resources, system, systemd_ops

info = system.get_system_info()
print(f"  host      : {info['hostname']} ({info['os_name']} {info['os_release']})")
print(f"  uptime    : {info['uptime_seconds']:.0f} seconds")

cpu = resources.get_resource_usage()['cpu']['percent_total']
print(f"  cpu       : {cpu:.1f}%")

containers = docker_ops.list_docker_containers()
if containers["ok"]:
    print(f"  docker    : {containers['count']} running containers")
else:
    print(f"  docker    : unavailable ({containers['error']})")

ssh = systemd_ops.get_service_status('ssh.service')
if ssh["ok"]:
    print(f"  ssh       : {ssh['active_state']}/{ssh['sub_state']}")
else:
    print(f"  ssh       : {ssh['error']}")
PY

echo
echo "==> Done. Binary installed at: $INSTALL_DIR/.venv/bin/kamino-ops"
echo "    To wire into Claude Code, see: $INSTALL_DIR/docs/deployment.md"
