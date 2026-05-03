"""Read-only resource-usage tools.

CPU, memory, swap, disk, and load average for the host running this
server. All values come from ``psutil`` so the surface is consistent
across Linux (production target) and Windows/macOS (dev iteration).

Where the platform genuinely differs — e.g. ``getloadavg()`` on Windows
returns ``(0.0, 0.0, 0.0)`` because Windows has no equivalent metric —
the tool returns ``None`` rather than a misleading zero.
"""

from __future__ import annotations

import sys
from typing import TypedDict

import psutil


class CpuStats(TypedDict):
    """CPU utilization and topology."""

    percent_total: float
    count_logical: int | None
    count_physical: int | None


class MemoryStats(TypedDict):
    """Virtual or swap memory snapshot."""

    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent_used: float


class DiskStats(TypedDict):
    """Disk usage for a single mount path."""

    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent_used: float


class ResourceUsage(TypedDict):
    """All resource metrics rolled into one snapshot."""

    cpu: CpuStats
    memory: MemoryStats
    swap: MemoryStats
    disk: DiskStats
    load_average_1_5_15: list[float] | None


def _load_average() -> list[float] | None:
    """Return 1/5/15-minute load average, or None on Windows.

    psutil emulates ``getloadavg`` on Windows by returning zeros after
    a 5-second sampling window. That's misleading for an agent, so we
    explicitly return None there.
    """
    if sys.platform.startswith("win"):
        return None
    try:
        one, five, fifteen = psutil.getloadavg()
        return [round(one, 2), round(five, 2), round(fifteen, 2)]
    except (AttributeError, OSError):
        return None


def get_resource_usage(disk_path: str = "/") -> ResourceUsage:
    """Return a snapshot of CPU, memory, swap, disk, and load.

    Args:
        disk_path: Mount path to report disk usage for. Defaults to ``/``;
            use ``"C:\\"`` on Windows for sanity-checking during dev.

    Notes:
        - ``percent_total`` blocks for 0.5s to get a meaningful CPU sample.
          A non-blocking read returns the percent since the last call,
          which is close to zero on the first call and useless to an
          agent.
        - On Windows, ``disk_path`` defaults to ``/`` which resolves to
          the current drive root; agents should pass an explicit path.
    """
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    du = psutil.disk_usage(disk_path)

    return ResourceUsage(
        cpu=CpuStats(
            percent_total=psutil.cpu_percent(interval=0.5),
            count_logical=psutil.cpu_count(logical=True),
            count_physical=psutil.cpu_count(logical=False),
        ),
        memory=MemoryStats(
            total_bytes=vm.total,
            used_bytes=vm.used,
            available_bytes=vm.available,
            percent_used=vm.percent,
        ),
        swap=MemoryStats(
            total_bytes=sw.total,
            used_bytes=sw.used,
            available_bytes=max(sw.total - sw.used, 0),
            percent_used=sw.percent,
        ),
        disk=DiskStats(
            path=disk_path,
            total_bytes=du.total,
            used_bytes=du.used,
            free_bytes=du.free,
            percent_used=du.percent,
        ),
        load_average_1_5_15=_load_average(),
    )
