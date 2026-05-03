"""Read-only system-identification tools.

These tools are intentionally cross-platform so we can iterate on Windows
during development. The production target is Ubuntu (the Kamino server),
but anything that depends on Linux-specific surfaces lives in
``systemd_ops`` rather than here.
"""

from __future__ import annotations

import platform
import socket
import time
from typing import TypedDict

import psutil


class SystemInfo(TypedDict):
    """Identification + uptime for the host running this server."""

    hostname: str
    os_name: str
    os_release: str
    os_version: str
    architecture: str
    python_version: str
    boot_time_unix: float
    uptime_seconds: float


def get_system_info() -> SystemInfo:
    """Return hostname, OS, architecture, Python version, and uptime.

    The fields are deliberately granular (separate ``os_release`` and
    ``os_version`` rather than a pre-formatted string) so the calling
    agent can reason about them — e.g. compare kernel version against a
    known-good baseline.
    """
    uname = platform.uname()
    boot_time = psutil.boot_time()

    return SystemInfo(
        hostname=socket.gethostname(),
        os_name=uname.system,
        os_release=uname.release,
        os_version=uname.version,
        architecture=uname.machine,
        python_version=platform.python_version(),
        boot_time_unix=boot_time,
        uptime_seconds=time.time() - boot_time,
    )
