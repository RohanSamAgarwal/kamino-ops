"""Tests for the Docker tools.

These tests mock the Docker SDK so they can run anywhere — Windows
laptop, CI runner, anywhere with no daemon. The tests exercise all
three branches of every tool: happy path, container-not-found, and
daemon-unavailable.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from docker.errors import DockerException, NotFound

from kamino_ops.tools.docker_ops import (
    MAX_LOG_LINES,
    get_container_logs,
    get_container_stats,
    list_docker_containers,
)


# ---------------------------------------------------------------------------
# list_docker_containers
# ---------------------------------------------------------------------------


def _fake_container(name: str = "plunder", running: bool = True) -> MagicMock:
    c = MagicMock()
    c.short_id = "abc123def456"
    c.name = name
    c.status = "running" if running else "exited"
    c.image.tags = ["plunder:latest"]
    c.image.short_id = "img789"
    c.attrs = {
        "State": {"Status": c.status},
        "NetworkSettings": {"Ports": {"3000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "3000"}]}},
        "Created": "2026-05-03T17:00:00Z",
    }
    return c


def test_list_containers_happy_path() -> None:
    with patch("kamino_ops.tools.docker_ops._client") as mock_client:
        mock_client.return_value.containers.list.return_value = [_fake_container()]
        result = list_docker_containers()

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["all_containers"] is False
    summary = result["containers"][0]
    assert summary["name"] == "plunder"
    assert summary["status"] == "running"
    assert summary["image"] == "plunder:latest"
    assert "3000/tcp" in summary["ports"]


def test_list_containers_passes_all_flag() -> None:
    with patch("kamino_ops.tools.docker_ops._client") as mock_client:
        mock_client.return_value.containers.list.return_value = []
        list_docker_containers(all_containers=True)
        mock_client.return_value.containers.list.assert_called_once_with(all=True)


def test_list_containers_returns_error_when_daemon_down() -> None:
    with patch(
        "kamino_ops.tools.docker_ops._client",
        side_effect=DockerException("connection refused"),
    ):
        result = list_docker_containers()
    assert result == {
        "ok": False,
        "error": "docker_unavailable",
        "message": "connection refused",
    }


# ---------------------------------------------------------------------------
# get_container_logs
# ---------------------------------------------------------------------------


def test_get_container_logs_happy_path() -> None:
    with patch("kamino_ops.tools.docker_ops._client") as mock_client:
        container = MagicMock()
        container.logs.return_value = b"line one\nline two\nline three\n"
        mock_client.return_value.containers.get.return_value = container

        result = get_container_logs("plunder", tail=50)

    assert result["ok"] is True
    assert result["lines"] == ["line one", "line two", "line three"]
    assert result["lines_returned"] == 3
    assert result["lines_requested"] == 50
    assert result["truncated_by_cap"] is False


def test_get_container_logs_caps_at_max_lines() -> None:
    with patch("kamino_ops.tools.docker_ops._client") as mock_client:
        container = MagicMock()
        container.logs.return_value = b""
        mock_client.return_value.containers.get.return_value = container

        result = get_container_logs("plunder", tail=99_999)
        assert result["truncated_by_cap"] is True
        # Verify the SDK was called with the cap, not the user's number
        container.logs.assert_called_once_with(
            tail=MAX_LOG_LINES, stdout=True, stderr=True
        )


def test_get_container_logs_rejects_invalid_tail() -> None:
    result = get_container_logs("plunder", tail=0)
    assert result["ok"] is False
    assert result["error"] == "invalid_argument"


def test_get_container_logs_returns_error_on_not_found() -> None:
    with patch("kamino_ops.tools.docker_ops._client") as mock_client:
        mock_client.return_value.containers.get.side_effect = NotFound("no such container")
        result = get_container_logs("ghost")
    assert result["ok"] is False
    assert result["error"] == "container_not_found"


# ---------------------------------------------------------------------------
# get_container_stats
# ---------------------------------------------------------------------------


def _stats_sample(cpu_now: int = 200, cpu_prev: int = 100, sys_now: int = 1000, sys_prev: int = 500) -> dict:
    return {
        "cpu_stats": {
            "cpu_usage": {"total_usage": cpu_now},
            "system_cpu_usage": sys_now,
            "online_cpus": 4,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": cpu_prev},
            "system_cpu_usage": sys_prev,
        },
        "memory_stats": {"usage": 1024 * 1024 * 100, "limit": 1024 * 1024 * 1024},
    }


def test_get_container_stats_happy_path() -> None:
    with patch("kamino_ops.tools.docker_ops._client") as mock_client:
        container = MagicMock()
        container.stats.return_value = _stats_sample()
        mock_client.return_value.containers.get.return_value = container

        result = get_container_stats("plunder")

    assert result["ok"] is True
    # cpu_delta=100, sys_delta=500, online=4 → 100/500 * 4 * 100 = 80.0
    assert result["cpu_percent"] == pytest.approx(80.0)
    assert result["memory_used_bytes"] == 1024 * 1024 * 100
    assert result["online_cpus"] == 4


def test_get_container_stats_returns_none_cpu_on_first_sample() -> None:
    """When system_cpu_usage delta is zero, we can't compute CPU%."""
    with patch("kamino_ops.tools.docker_ops._client") as mock_client:
        container = MagicMock()
        container.stats.return_value = _stats_sample(sys_now=500, sys_prev=500)
        mock_client.return_value.containers.get.return_value = container

        result = get_container_stats("plunder")

    assert result["ok"] is True
    assert result["cpu_percent"] is None
