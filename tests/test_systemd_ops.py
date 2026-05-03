"""Tests for the systemd tools.

Every test mocks ``subprocess.run`` so the tests are deterministic and
runnable on Windows, macOS, or any CI without systemd. The
platform-detection logic is exercised by patching ``_is_linux``.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from kamino_ops.tools.systemd_ops import (
    MAX_JOURNAL_LINES,
    get_service_status,
    list_systemd_services,
    tail_journal,
)


@pytest.fixture
def force_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kamino_ops.tools.systemd_ops._is_linux", lambda: True)


@pytest.fixture
def force_non_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kamino_ops.tools.systemd_ops._is_linux", lambda: False)


def _proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


# ---------------------------------------------------------------------------
# Platform gate
# ---------------------------------------------------------------------------


def test_list_services_unsupported_on_non_linux(force_non_linux: None) -> None:
    result = list_systemd_services()
    assert result["ok"] is False
    assert result["error"] == "platform_unsupported"


def test_get_service_status_unsupported_on_non_linux(force_non_linux: None) -> None:
    assert get_service_status("ssh.service")["error"] == "platform_unsupported"


def test_tail_journal_unsupported_on_non_linux(force_non_linux: None) -> None:
    assert tail_journal("ssh.service")["error"] == "platform_unsupported"


# ---------------------------------------------------------------------------
# Unit-name validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["ssh.service; rm -rf /", "ssh service", "ssh|service"])
def test_validate_unit_rejects_bad_names(force_linux: None, bad: str) -> None:
    for fn in (get_service_status, tail_journal):
        result = fn(bad)
        assert result["ok"] is False
        assert result["error"] == "invalid_unit"


@pytest.mark.parametrize("good", ["ssh.service", "docker.service", "user@1000.service", "kamino-ops.service"])
def test_validate_unit_accepts_real_names(force_linux: None, good: str) -> None:
    # Must not return invalid_unit; will go on to call subprocess (which we
    # mock out so the test itself is platform-independent).
    with patch("subprocess.run", return_value=_proc(stdout="LoadState=loaded\nActiveState=active\nSubState=running\n")):
        result = get_service_status(good)
    assert result["ok"] is True
    assert result["unit"] == good


# ---------------------------------------------------------------------------
# list_systemd_services
# ---------------------------------------------------------------------------


def test_list_services_happy_path(force_linux: None) -> None:
    sample = json.dumps(
        [
            {"unit": "ssh.service", "load": "loaded", "active": "active", "sub": "running"},
            {"unit": "docker.service", "load": "loaded", "active": "active", "sub": "running"},
        ]
    )
    with patch("subprocess.run", return_value=_proc(stdout=sample)) as mock_run:
        result = list_systemd_services()

    assert result["ok"] is True
    assert result["count"] == 2
    # Verify the argv passed had the right shape
    argv = mock_run.call_args.args[0]
    assert argv[:2] == ["systemctl", "list-units"]


def test_list_services_passes_state_filter(force_linux: None) -> None:
    with patch("subprocess.run", return_value=_proc(stdout="[]")) as mock_run:
        list_systemd_services(state="failed")
    argv = mock_run.call_args.args[0]
    assert "--state" in argv
    assert argv[argv.index("--state") + 1] == "failed"


def test_list_services_rejects_garbage_state(force_linux: None) -> None:
    result = list_systemd_services(state="failed; rm -rf /")
    assert result["ok"] is False
    assert result["error"] == "invalid_argument"


def test_list_services_handles_missing_systemctl(force_linux: None) -> None:
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result = list_systemd_services()
    assert result["error"] == "systemctl_not_found"


def test_list_services_handles_timeout(force_linux: None) -> None:
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=10)):
        result = list_systemd_services()
    assert result["error"] == "systemctl_timeout"


# ---------------------------------------------------------------------------
# get_service_status
# ---------------------------------------------------------------------------


def test_status_parses_systemctl_show_output(force_linux: None) -> None:
    show_output = (
        "LoadState=loaded\n"
        "ActiveState=active\n"
        "SubState=running\n"
        "UnitFileState=enabled\n"
        "Description=OpenSSH server daemon\n"
        "MainPID=1234\n"
        "ExecMainStartTimestamp=Sat 2026-05-03 17:00:00 UTC\n"
    )
    with patch("subprocess.run", return_value=_proc(stdout=show_output)):
        result = get_service_status("ssh.service")

    assert result["ok"] is True
    assert result["active_state"] == "active"
    assert result["sub_state"] == "running"
    assert result["main_pid"] == 1234
    assert result["description"] == "OpenSSH server daemon"


def test_status_returns_unit_not_found_when_load_state_empty(force_linux: None) -> None:
    with patch("subprocess.run", return_value=_proc(stdout="LoadState=not-found\n")):
        result = get_service_status("ghost.service")
    assert result["error"] == "unit_not_found"


def test_status_handles_pid_zero(force_linux: None) -> None:
    """Inactive services have MainPID=0; we should report None, not 0."""
    with patch("subprocess.run", return_value=_proc(stdout="LoadState=loaded\nActiveState=inactive\nMainPID=0\n")):
        result = get_service_status("inactive.service")
    assert result["main_pid"] is None


# ---------------------------------------------------------------------------
# tail_journal
# ---------------------------------------------------------------------------


def test_tail_journal_happy_path(force_linux: None) -> None:
    output = "2026-05-03 line one\n2026-05-03 line two\n2026-05-03 line three\n"
    with patch("subprocess.run", return_value=_proc(stdout=output)) as mock_run:
        result = tail_journal("ssh.service", lines=50)
    assert result["ok"] is True
    assert result["lines_returned"] == 3
    assert result["truncated_by_cap"] is False
    argv = mock_run.call_args.args[0]
    assert argv[0] == "journalctl"
    assert "-u" in argv and "ssh.service" in argv


def test_tail_journal_caps_at_max(force_linux: None) -> None:
    with patch("subprocess.run", return_value=_proc(stdout="")) as mock_run:
        result = tail_journal("ssh.service", lines=99_999)
    assert result["truncated_by_cap"] is True
    argv = mock_run.call_args.args[0]
    assert str(MAX_JOURNAL_LINES) in argv


def test_tail_journal_rejects_invalid_lines(force_linux: None) -> None:
    result = tail_journal("ssh.service", lines=0)
    assert result["error"] == "invalid_argument"
