"""Read-only Docker tools.

These tools follow the structured-error pattern called out in
``docs/architecture.md``: every response is a dict with an ``ok`` key.
On success, the rest of the dict is the data. On failure, ``ok`` is
``False`` and ``error``/``message`` describe what went wrong.

Why this pattern here (and not in ``system.py`` / ``resources.py``)?
Docker has well-defined, frequent failure modes — daemon not running,
container not found, image not pulled — that an agent should reason
about, not catch as an exception. Structuring them as data makes the
agent's job tractable. The cross-platform stdlib tools have lower
failure rates and use plain returns + bubbled exceptions.
"""

from __future__ import annotations

from typing import Any

import docker
from docker.errors import DockerException, NotFound

# Hard cap on log lines an agent can request in one call. Anything
# larger should be paginated by repeated calls with different ``tail``
# values, not a single firehose. Documented in the README and enforced
# here so the limit is in one place.
MAX_LOG_LINES = 5000


def _client() -> docker.DockerClient:
    """Return a Docker client connected to the local daemon."""
    return docker.from_env()


def _error(error: str, message: str) -> dict[str, Any]:
    """Shorthand for the structured-error envelope."""
    return {"ok": False, "error": error, "message": message}


def _summarize_container(c: Any) -> dict[str, Any]:
    """Project a Docker container object down to the fields agents care about."""
    image_tags = getattr(c.image, "tags", None) or []
    return {
        "id": c.short_id,
        "name": c.name,
        "status": c.status,
        "state": c.attrs.get("State", {}).get("Status"),
        "image": image_tags[0] if image_tags else c.image.short_id,
        "ports": c.attrs.get("NetworkSettings", {}).get("Ports") or {},
        "created": c.attrs.get("Created"),
    }


def list_docker_containers(all_containers: bool = False) -> dict[str, Any]:
    """List Docker containers on the local daemon.

    Args:
        all_containers: Include stopped containers when True. Defaults
            to False (running only).
    """
    try:
        client = _client()
        containers = client.containers.list(all=all_containers)
    except DockerException as e:
        return _error("docker_unavailable", str(e))

    summaries = [_summarize_container(c) for c in containers]
    return {
        "ok": True,
        "count": len(summaries),
        "all_containers": all_containers,
        "containers": summaries,
    }


def get_container_logs(name_or_id: str, tail: int = 100) -> dict[str, Any]:
    """Tail recent logs from a single container.

    Args:
        name_or_id: Container name or short ID.
        tail: Number of trailing lines. Capped at ``MAX_LOG_LINES``;
            the response indicates whether the cap was applied.
    """
    if tail < 1:
        return _error("invalid_argument", f"tail must be >= 1; got {tail}")

    capped = min(tail, MAX_LOG_LINES)
    try:
        client = _client()
        container = client.containers.get(name_or_id)
        raw = container.logs(tail=capped, stdout=True, stderr=True)
    except NotFound:
        return _error("container_not_found", f"no container named {name_or_id!r}")
    except DockerException as e:
        return _error("docker_unavailable", str(e))

    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    lines = text.splitlines()
    return {
        "ok": True,
        "container": name_or_id,
        "lines_requested": tail,
        "lines_returned": len(lines),
        "truncated_by_cap": tail > MAX_LOG_LINES,
        "max_lines": MAX_LOG_LINES,
        "lines": lines,
    }


def get_container_stats(name_or_id: str) -> dict[str, Any]:
    """Return a one-shot CPU%/memory snapshot for a container.

    Docker's ``stats`` API streams continuously; we use ``stream=False``
    to take a single sample. CPU% is computed from the delta between
    the current and previous samples (Docker tracks the previous one
    internally), so the very first call after a container starts may
    return ``cpu_percent=None`` if the kernel hasn't accumulated enough
    history yet.
    """
    try:
        client = _client()
        container = client.containers.get(name_or_id)
        stats = container.stats(stream=False)
    except NotFound:
        return _error("container_not_found", f"no container named {name_or_id!r}")
    except DockerException as e:
        return _error("docker_unavailable", str(e))

    cpu_percent = _compute_cpu_percent(stats)
    mem = stats.get("memory_stats", {}) or {}

    return {
        "ok": True,
        "container": name_or_id,
        "cpu_percent": cpu_percent,
        "memory_used_bytes": mem.get("usage"),
        "memory_limit_bytes": mem.get("limit"),
        "online_cpus": stats.get("cpu_stats", {}).get("online_cpus"),
    }


def _compute_cpu_percent(stats: dict[str, Any]) -> float | None:
    """Compute CPU% from a single ``container.stats(stream=False)`` sample.

    Returns None if the deltas can't be computed (e.g. first sample,
    Windows containers without these fields).
    """
    try:
        cpu_now = stats["cpu_stats"]["cpu_usage"]["total_usage"]
        cpu_prev = stats["precpu_stats"]["cpu_usage"]["total_usage"]
        sys_now = stats["cpu_stats"]["system_cpu_usage"]
        sys_prev = stats["precpu_stats"].get("system_cpu_usage", 0)
        online = stats["cpu_stats"].get("online_cpus", 1) or 1

        cpu_delta = cpu_now - cpu_prev
        sys_delta = sys_now - sys_prev
        if sys_delta <= 0 or cpu_delta < 0:
            return None
        return round((cpu_delta / sys_delta) * online * 100.0, 2)
    except (KeyError, TypeError, ZeroDivisionError):
        return None
