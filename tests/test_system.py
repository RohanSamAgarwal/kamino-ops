"""Smoke tests for the system tool.

These tests are deliberately minimal — they verify that the function
returns the expected shape, not that any specific value is correct
(uptime varies, hostname depends on the machine, etc.). The audit-log
test does check a concrete invariant: that calling the tool writes
exactly one JSON line.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kamino_ops.audit import audited
from kamino_ops.tools.system import get_system_info


def test_get_system_info_returns_expected_keys() -> None:
    info = get_system_info()
    expected = {
        "hostname",
        "os_name",
        "os_release",
        "os_version",
        "architecture",
        "python_version",
        "boot_time_unix",
        "uptime_seconds",
    }
    assert set(info.keys()) == expected
    assert isinstance(info["hostname"], str) and info["hostname"]
    assert info["uptime_seconds"] > 0


def test_audited_decorator_writes_one_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "audit.log"
    monkeypatch.setenv("KAMINO_OPS_AUDIT_LOG", str(log))

    @audited("test_tool")
    def my_tool(x: int) -> int:
        return x * 2

    assert my_tool(x=21) == 42

    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["tool"] == "test_tool"
    assert entry["args"] == {"x": 21}
    assert entry["ok"] is True
    assert entry["error_kind"] is None
    assert entry["duration_ms"] >= 0


def test_audited_decorator_records_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "audit.log"
    monkeypatch.setenv("KAMINO_OPS_AUDIT_LOG", str(log))

    @audited("failing_tool")
    def boom() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        boom()

    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["ok"] is False
    assert entry["error_kind"] == "ValueError"
