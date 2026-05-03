"""Append-only audit logging for tool calls.

Every tool exposed by Kamino Ops is wrapped with :func:`audited`, which
writes one JSON line per invocation to ``audit.log``. The log is the
source of truth for forensics, demos, and (in v0.5) the eval harness.

Design choices:

- **One JSON object per line** — parseable with ``jq``, resilient to
  partial writes (a half-written line is detectable as invalid JSON).
- **``flush()`` after every write** — we tolerate the I/O cost in
  exchange for surviving an unclean process exit.
- **Errors don't propagate** — a broken audit log must never break a
  tool call. We log at WARNING and continue.
- **Path is configurable via ``KAMINO_OPS_AUDIT_LOG``** — useful for
  tests (point at a tmp file) and for production (point at
  ``/var/log/kamino-ops/audit.log``).
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _audit_log_path() -> Path:
    """Resolve the audit log path at call time (so tests can patch env)."""
    return Path(os.environ.get("KAMINO_OPS_AUDIT_LOG", Path.cwd() / "audit.log"))


def _utc_now_iso() -> str:
    """Return the current UTC time as ``2026-05-03T17:42:08Z``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_entry(entry: dict[str, Any]) -> None:
    """Append one JSON line. Swallow I/O errors after logging them."""
    path = _audit_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
            f.flush()
    except OSError as e:
        logger.warning("audit log write failed (%s): %s", path, e)


def audited(tool_name: str) -> Callable[[F], F]:
    """Decorate a tool function so each call is recorded to ``audit.log``.

    Args:
        tool_name: The name to record. Conventionally matches the MCP
            tool name (which is the function name unless overridden).
    """

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            ok = True
            error_kind: str | None = None
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                ok = False
                error_kind = type(e).__name__
                raise
            finally:
                _write_entry(
                    {
                        "ts": _utc_now_iso(),
                        "tool": tool_name,
                        # We only record kwargs because all MCP tools are called by name.
                        # Positional args would imply an internal caller, which we don't audit.
                        "args": kwargs,
                        "ok": ok,
                        "error_kind": error_kind,
                        "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                    }
                )

        return wrapper  # type: ignore[return-value]

    return decorator
