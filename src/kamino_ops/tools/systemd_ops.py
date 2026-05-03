"""Read-only systemd tools.

These tools shell out to ``systemctl`` and ``journalctl``. Both are
Linux-only — on Windows or macOS the tools return a structured
``platform_unsupported`` error rather than crashing. This lets the
same code path run during local Windows iteration: a developer (or an
agent) sees a clear error instead of a misleading traceback.

Safety properties:

- ``shell=False`` — every subprocess call passes ``argv`` as a list,
  so user-supplied unit names can never be interpreted as shell.
- **Validated unit names** — names must match ``UNIT_RE``
  (``[A-Za-z0-9._@-]+``) before any subprocess call. systemd would
  reject malformed names anyway, but failing fast keeps the audit log
  clean and makes the failure mode explicit.
- **Allowlisted flags** — every flag passed to ``systemctl``/
  ``journalctl`` is hard-coded here; nothing flows through from the
  caller except the validated unit name and a numeric line count.
- **Fixed timeouts** — every subprocess call has a timeout so a hung
  systemd can't wedge the MCP server.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any

# Linux systemd unit names: alphanumeric, dot, dash, underscore, '@'.
UNIT_RE = re.compile(r"^[A-Za-z0-9._@-]+$")

# Hard cap on lines from a single ``journalctl`` invocation. Same
# rationale as ``MAX_LOG_LINES`` in ``docker_ops``: an agent that asks
# for "all logs since boot" should hit a limit, not flood its context.
MAX_JOURNAL_LINES = 5000


def _is_linux() -> bool:
    """Indirected so tests can patch the platform check without touching ``sys``."""
    return sys.platform.startswith("linux")


def _error(error: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": error, "message": message}


def _require_linux() -> dict[str, Any] | None:
    if not _is_linux():
        return _error(
            "platform_unsupported",
            f"systemd tools require Linux; current platform is {sys.platform}",
        )
    return None


def _validate_unit(unit: str) -> dict[str, Any] | None:
    if not UNIT_RE.match(unit):
        return _error(
            "invalid_unit",
            f"unit name {unit!r} contains illegal characters; expected [A-Za-z0-9._@-]+",
        )
    return None


def _run(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Thin wrapper around subprocess.run with sensible defaults."""
    return subprocess.run(  # noqa: S603 — argv is allowlisted upstream
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# ---------------------------------------------------------------------------
# list_systemd_services
# ---------------------------------------------------------------------------


def list_systemd_services(state: str | None = None) -> dict[str, Any]:
    """List systemd ``.service`` units, optionally filtered by state.

    Args:
        state: One of systemd's load/active states (e.g. ``"running"``,
            ``"failed"``). When None, all services are returned.
    """
    if (err := _require_linux()) is not None:
        return err

    argv = [
        "systemctl",
        "list-units",
        "--type=service",
        "--all",
        "--output=json",
        "--no-pager",
    ]
    if state:
        if not re.match(r"^[a-z-]+$", state):
            return _error("invalid_argument", f"state {state!r} contains illegal characters")
        argv.extend(["--state", state])

    try:
        proc = _run(argv, timeout=10)
    except FileNotFoundError:
        return _error("systemctl_not_found", "systemctl binary not found in PATH")
    except subprocess.TimeoutExpired:
        return _error("systemctl_timeout", "systemctl list-units timed out after 10s")

    if proc.returncode != 0:
        return _error("systemctl_failed", proc.stderr.strip() or f"exit code {proc.returncode}")

    try:
        units = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return _error("parse_error", f"could not parse systemctl JSON: {e}")

    return {
        "ok": True,
        "count": len(units),
        "state_filter": state,
        "services": units,
    }


# ---------------------------------------------------------------------------
# get_service_status
# ---------------------------------------------------------------------------


_STATUS_PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "UnitFileState",
    "Description",
    "MainPID",
    "ExecMainStartTimestamp",
)


def get_service_status(unit: str) -> dict[str, Any]:
    """Return load/active/sub state and metadata for a single unit.

    Uses ``systemctl show`` (key=value output) rather than ``status``
    (free-form text) because the former is parseable.
    """
    if (err := _require_linux()) is not None:
        return err
    if (err := _validate_unit(unit)) is not None:
        return err

    argv = [
        "systemctl",
        "show",
        unit,
        f"--property={','.join(_STATUS_PROPERTIES)}",
    ]
    try:
        proc = _run(argv, timeout=10)
    except FileNotFoundError:
        return _error("systemctl_not_found", "systemctl binary not found in PATH")
    except subprocess.TimeoutExpired:
        return _error("systemctl_timeout", "systemctl show timed out after 10s")

    if proc.returncode != 0:
        return _error("systemctl_failed", proc.stderr.strip() or f"exit code {proc.returncode}")

    props: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k] = v

    # systemctl returns LoadState=not-found rather than a non-zero exit
    # when the unit doesn't exist, so we have to check explicitly.
    load_state = props.get("LoadState") or ""
    if load_state in ("", "not-found"):
        return _error("unit_not_found", f"no such unit: {unit}")

    main_pid_raw = props.get("MainPID", "0")
    main_pid = int(main_pid_raw) if main_pid_raw.isdigit() and main_pid_raw != "0" else None

    return {
        "ok": True,
        "unit": unit,
        "load_state": load_state,
        "active_state": props.get("ActiveState"),
        "sub_state": props.get("SubState"),
        "unit_file_state": props.get("UnitFileState"),
        "description": props.get("Description"),
        "main_pid": main_pid,
        "started_at": props.get("ExecMainStartTimestamp") or None,
    }


# ---------------------------------------------------------------------------
# tail_journal
# ---------------------------------------------------------------------------


def tail_journal(unit: str, lines: int = 100) -> dict[str, Any]:
    """Return the last N journal lines for a systemd unit.

    Args:
        unit: systemd unit name (must validate).
        lines: number of trailing lines (capped at ``MAX_JOURNAL_LINES``).
    """
    if (err := _require_linux()) is not None:
        return err
    if (err := _validate_unit(unit)) is not None:
        return err
    if lines < 1:
        return _error("invalid_argument", f"lines must be >= 1; got {lines}")

    capped = min(lines, MAX_JOURNAL_LINES)
    argv = [
        "journalctl",
        "-u",
        unit,
        "-n",
        str(capped),
        "--output=short-iso",
        "--no-pager",
    ]
    try:
        proc = _run(argv, timeout=15)
    except FileNotFoundError:
        return _error("journalctl_not_found", "journalctl binary not found in PATH")
    except subprocess.TimeoutExpired:
        return _error("journalctl_timeout", "journalctl timed out after 15s")

    if proc.returncode != 0:
        return _error("journalctl_failed", proc.stderr.strip() or f"exit code {proc.returncode}")

    out_lines = proc.stdout.splitlines()
    return {
        "ok": True,
        "unit": unit,
        "lines_requested": lines,
        "lines_returned": len(out_lines),
        "truncated_by_cap": lines > MAX_JOURNAL_LINES,
        "max_lines": MAX_JOURNAL_LINES,
        "lines": out_lines,
    }
