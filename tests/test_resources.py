"""Smoke tests for the resources tool.

These tests assert *shape*, not values — the actual numbers depend on
the host. The platform-aware load-average behavior is the one
exception: we can deterministically assert it's ``None`` on Windows.
"""

from __future__ import annotations

import sys
from pathlib import Path

from kamino_ops.tools.resources import get_resource_usage


def _disk_path_for_platform() -> str:
    # On Windows, "/" resolves to the current drive root, but being
    # explicit makes the test less surprising if it ever fails.
    return "C:\\" if sys.platform.startswith("win") else "/"


def test_get_resource_usage_returns_expected_shape() -> None:
    usage = get_resource_usage(disk_path=_disk_path_for_platform())

    assert set(usage.keys()) == {"cpu", "memory", "swap", "disk", "load_average_1_5_15"}

    assert set(usage["cpu"].keys()) == {"percent_total", "count_logical", "count_physical"}
    assert 0.0 <= usage["cpu"]["percent_total"] <= 100.0
    assert (usage["cpu"]["count_logical"] or 0) >= 1

    for slot in ("memory", "swap"):
        assert set(usage[slot].keys()) == {
            "total_bytes",
            "used_bytes",
            "available_bytes",
            "percent_used",
        }

    disk = usage["disk"]
    assert disk["path"] == _disk_path_for_platform()
    assert disk["total_bytes"] >= disk["used_bytes"]
    assert 0.0 <= disk["percent_used"] <= 100.0


def test_load_average_is_none_on_windows() -> None:
    if not sys.platform.startswith("win"):
        return  # Linux/macOS load average is platform-dependent; covered by shape test.
    usage = get_resource_usage(disk_path=_disk_path_for_platform())
    assert usage["load_average_1_5_15"] is None


def test_get_resource_usage_default_disk_path_does_not_crash() -> None:
    # On Windows, "/" becomes the current drive root and psutil handles it.
    # Just ensuring the default doesn't blow up; we already shape-test above.
    usage = get_resource_usage()
    assert isinstance(usage["disk"]["total_bytes"], int)
