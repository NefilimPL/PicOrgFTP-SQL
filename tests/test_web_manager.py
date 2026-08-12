"""Tests for the web panel manager process launcher."""

from __future__ import annotations

import ast
import builtins
import json
import multiprocessing
import os
from pathlib import Path
import runpy
import subprocess
import sys
import types
from unittest.mock import patch

import pytest

from picorgftp_sql import web_manager


ROOT = Path(__file__).resolve().parents[1]
WEB_ENTRYPOINT = ROOT / "PicOrgFTP-SQL-WEB.pyw"
START_WEB_SCRIPT = ROOT / "tools" / "web" / "start_web.ps1"
STOP_WEB_SCRIPT = ROOT / "tools" / "web" / "stop_web.ps1"


def _run_powershell_harness(path: Path) -> list[str]:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return [line for line in result.stdout.splitlines() if line.strip()]


def test_web_entrypoint_calls_freeze_support_before_importing_manager() -> None:
    tree = ast.parse(WEB_ENTRYPOINT.read_text(encoding="utf-8"))
    freeze_guard = next(
        node
        for node in tree.body
        if isinstance(node, ast.If)
        and any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id == "multiprocessing"
            and child.func.attr == "freeze_support"
            for child in ast.walk(node)
        )
    )
    manager_import = next(
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "picorgftp_sql.web_manager"
    )

    assert tree.body.index(freeze_guard) < tree.body.index(manager_import)


def test_web_entrypoint_runs_freeze_support_before_loading_manager(
    monkeypatch,
) -> None:
    calls: list[str] = []
    fake_manager = types.ModuleType("picorgftp_sql.web_manager")
    fake_manager.main = lambda: calls.append("main")
    monkeypatch.setitem(sys.modules, "picorgftp_sql.web_manager", fake_manager)
    original_import = builtins.__import__

    def track_manager_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "picorgftp_sql.web_manager":
            calls.append("web_manager_import")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", track_manager_import)
    monkeypatch.setattr(
        multiprocessing, "freeze_support", lambda: calls.append("freeze_support")
    )

    runpy.run_path(str(WEB_ENTRYPOINT), run_name="__main__")

    assert calls == ["freeze_support", "web_manager_import", "main"]


@pytest.mark.skipif(os.name != "nt", reason="PowerShell starter scripts are Windows-only")
def test_start_web_script_records_its_own_launcher_pid(tmp_path) -> None:
    """Catches the starter writing only the child server PID to runtime metadata."""
    source = START_WEB_SCRIPT.read_text(encoding="utf-8")
    start = source.index("function Write-RunMetadata")
    end = source.index("\nfunction Test-WebDeps", start)
    write_metadata_function = source[start:end]
    harness_path = tmp_path / "tools" / "web" / "start_web_harness.ps1"
    harness_path.parent.mkdir(parents=True)
    harness_path.write_text(
        """
$Port = 8010
$HostAddress = "0.0.0.0"
$PidFile = Join-Path $PSScriptRoot "..\\..\\.picorg_web.pid"
"""
        + write_metadata_function
        + """
$firewallState = [pscustomobject]@{
    rule_name = ""
    created = $false
    remove_on_stop = $false
}
Write-RunMetadata 4242 $firewallState
[pscustomobject]@{
    metadata = Get-Content -Path $PidFile -Raw | ConvertFrom-Json
    launcher_process_id = [int]$PID
} | ConvertTo-Json -Compress
""",
        encoding="utf-8",
    )

    payload = json.loads(_run_powershell_harness(harness_path)[-1])

    assert payload["metadata"]["pid"] == 4242
    assert payload["metadata"]["launcher"] == "start_web.ps1"
    assert payload["metadata"]["launcher_pid"] == payload["launcher_process_id"]


@pytest.mark.skipif(os.name != "nt", reason="PowerShell starter scripts are Windows-only")
def test_stop_web_script_terminates_recorded_launcher_tree_first(tmp_path) -> None:
    """Catches STOP_WEB terminating only the server child instead of its launcher tree."""
    source = STOP_WEB_SCRIPT.read_text(encoding="utf-8")
    prefix, separator, suffix = source.partition("\n$stopped = $false\n")
    assert separator
    harness_path = tmp_path / "tools" / "web" / "stop_web_harness.ps1"
    harness_path.parent.mkdir(parents=True)
    harness_path.write_text(
        prefix
        + """
$script:stop_calls = @()
function Read-RunMetadata {
    return [pscustomobject]@{
        pid = 102
        launcher_pid = 101
        launcher = "start_web.ps1"
        port = 8010
        firewall_rule_created = $false
        firewall_remove_on_stop = $false
        firewall_rule_name = ""
    }
}
function Stop-WebPid($PidValue, [switch]$AllowRecordedLauncher) {
    $script:stop_calls += [int]$PidValue
    return [pscustomobject]@{ ok = $true; attempted = $true; message = "" }
}
function Get-PortListenerPids { return @(103) }
function Wait-WebPortRelease { return $true }
function Remove-FirewallRuleFromMetadata($Metadata) { }
"""
        + separator
        + suffix
        + "\n$script:stop_calls | ConvertTo-Json -Compress\n",
        encoding="utf-8",
    )

    calls = json.loads(_run_powershell_harness(harness_path)[-1])

    assert calls == 101


@pytest.mark.skipif(os.name != "nt", reason="PowerShell starter scripts are Windows-only")
def test_stop_web_script_uses_taskkill_tree_option(tmp_path) -> None:
    """Catches replacing tree shutdown with a single-process Stop-Process call."""
    source = STOP_WEB_SCRIPT.read_text(encoding="utf-8")
    start = source.index("function Stop-WebPid")
    end = source.index("\nfunction Read-RunMetadata", start)
    stop_process_function = source[start:end]
    harness_path = tmp_path / "stop_web_tree_harness.ps1"
    harness_path.write_text(
        """
$script:taskkill_args = $null
function Get-Process { return [pscustomobject]@{ ProcessName = "powershell" } }
function Test-WebProcess($PidValue) { return $true }
function Stop-Process { }
function taskkill {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $script:taskkill_args = $Arguments
    $global:LASTEXITCODE = 0
}
"""
        + stop_process_function
        + """
$result = Stop-WebPid 101
[pscustomobject]@{
    ok = $result.ok
    arguments = @($script:taskkill_args)
} | ConvertTo-Json -Compress
""",
        encoding="utf-8",
    )

    payload = json.loads(_run_powershell_harness(harness_path)[-1])

    assert payload["ok"] is True
    assert payload["arguments"] == ["/PID", "101", "/T", "/F"]


class _FakeRoot:
    def __init__(self) -> None:
        self.destroyed = False
        self.after_calls = []

    def destroy(self) -> None:
        self.destroyed = True

    def after(self, delay_ms: int, callback=None) -> None:
        self.after_calls.append(delay_ms)
        if callback is not None:
            callback()


class _FakeStringVar:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class _FakeProgressbar:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    def start(self, _interval_ms: int = 50) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


def _app_without_tk() -> web_manager.WebManagerApp:
    app = object.__new__(web_manager.WebManagerApp)
    app.root = _FakeRoot()
    app.tray_icon = None
    app.status_var = _FakeStringVar()
    app.close_progress = _FakeProgressbar()
    app.closing = False
    app.close_check_in_progress = False
    app._port = lambda: 8010
    return app


def test_service_environment_resets_pyinstaller_for_frozen_child_process() -> None:
    with (
        patch.object(web_manager.sys, "frozen", True, create=True),
        patch.dict(web_manager.os.environ, {"_PYI_APPLICATION_HOME_DIR": "C:/Temp/_MEI123"}, clear=True),
    ):
        env = web_manager.service_environment(8010, "0.0.0.0")

    assert env["PICORGFTP_SQL_HEADLESS"] == "1"
    assert env["PICORG_WEB_PORT"] == "8010"
    assert env["PICORG_WEB_HOST"] == "0.0.0.0"
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_write_metadata_records_explicit_launcher_pid(tmp_path, monkeypatch) -> None:
    """Catches dropping the PID that owns the controlled runtime tree."""
    monkeypatch.setattr(web_manager, "app_root", lambda: tmp_path)

    web_manager.write_metadata(
        8010,
        "0.0.0.0",
        launcher="service-run",
        launcher_pid=101,
    )

    metadata = web_manager.read_metadata(tmp_path)
    assert metadata["pid"] == os.getpid()
    assert metadata["launcher_pid"] == 101


def test_stop_web_terminates_launcher_tree_after_port_release(tmp_path, monkeypatch) -> None:
    """Catches stopping only the server child and leaving its launcher alive."""
    (tmp_path / ".picorg_web.pid").write_text(
        json.dumps({"pid": 102, "launcher_pid": 101}),
        encoding="ascii",
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(web_manager, "app_root", lambda: tmp_path)
    monkeypatch.setattr(
        web_manager,
        "end_system_service",
        lambda: web_manager.ActionResult(True, ""),
    )
    monkeypatch.setattr(
        web_manager,
        "get_process_command_line",
        lambda _pid: "PicOrgFTP-SQL-WEB --service-run",
    )
    monkeypatch.setattr(web_manager, "get_port_listeners", lambda _port: [])
    monkeypatch.setattr(
        web_manager,
        "_run_command",
        lambda args, **_kwargs: commands.append(args)
        or subprocess.CompletedProcess(args, 0, "", ""),
    )

    result = web_manager.stop_web(8010)

    assert result.ok
    assert commands[0] == ["taskkill", "/PID", "101", "/T", "/F"]
    assert not (tmp_path / ".picorg_web.pid").exists()


def test_stop_web_terminates_recorded_launcher_when_cim_hides_command_line(
    tmp_path, monkeypatch
) -> None:
    """Catches leaving the launcher alive when Windows denies CIM command-line access."""
    (tmp_path / ".picorg_web.pid").write_text(
        json.dumps({"pid": 102, "launcher_pid": 101, "launcher": "start_web.ps1"}),
        encoding="ascii",
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(web_manager, "app_root", lambda: tmp_path)
    monkeypatch.setattr(
        web_manager,
        "end_system_service",
        lambda: web_manager.ActionResult(True, ""),
    )
    monkeypatch.setattr(web_manager, "get_process_command_line", lambda _pid: "")
    monkeypatch.setattr(web_manager, "get_port_listeners", lambda _port: [])
    monkeypatch.setattr(
        web_manager,
        "_run_command",
        lambda args, **_kwargs: commands.append(args)
        or subprocess.CompletedProcess(args, 0, "", ""),
    )

    assert web_manager.stop_web(8010).ok

    assert commands == [["taskkill", "/PID", "101", "/T", "/F"]]


def test_stop_web_terminates_recorded_server_when_cim_hides_command_line(
    tmp_path, monkeypatch
) -> None:
    """Catches leaving a non-frozen service process alive after CIM access fails."""
    (tmp_path / ".picorg_web.pid").write_text(
        json.dumps({"pid": 102, "launcher": "service-run"}),
        encoding="ascii",
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(web_manager, "app_root", lambda: tmp_path)
    monkeypatch.setattr(
        web_manager,
        "end_system_service",
        lambda: web_manager.ActionResult(True, ""),
    )
    monkeypatch.setattr(web_manager, "get_process_command_line", lambda _pid: "")
    monkeypatch.setattr(web_manager, "get_port_listeners", lambda _port: [])
    monkeypatch.setattr(
        web_manager,
        "_run_command",
        lambda args, **_kwargs: commands.append(args)
        or subprocess.CompletedProcess(args, 0, "", ""),
    )

    assert web_manager.stop_web(8010).ok

    assert commands == [["taskkill", "/PID", "102", "/T", "/F"]]


def test_frozen_service_records_its_pyinstaller_parent_as_launcher(tmp_path, monkeypatch) -> None:
    """Catches a frozen server persisting only its child PID."""
    metadata_calls = []
    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = lambda *_args, **_kwargs: None
    fake_web_app = types.ModuleType("picorgftp_sql.web.app")
    fake_web_app.app = object()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_manager, "app_root", lambda: tmp_path)
    monkeypatch.setattr(web_manager.os, "getppid", lambda: 123)
    monkeypatch.setattr(
        web_manager,
        "write_metadata",
        lambda _port, _host, **kwargs: metadata_calls.append(kwargs),
    )
    monkeypatch.setattr(web_manager, "remove_metadata_for_current_process", lambda: None)
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setitem(sys.modules, "picorgftp_sql.web.app", fake_web_app)
    monkeypatch.setattr(web_manager.sys, "frozen", True, raising=False)

    assert web_manager.run_service_mode(8010, "0.0.0.0") == 0

    assert metadata_calls == [{"launcher": "service-run", "launcher_pid": 123}]


def test_stop_web_keeps_metadata_when_taskkill_fails(tmp_path, monkeypatch) -> None:
    """Catches reporting shutdown success after Windows rejected taskkill."""
    pid_path = tmp_path / ".picorg_web.pid"
    pid_path.write_text(json.dumps({"pid": 102}), encoding="ascii")
    monkeypatch.setattr(web_manager, "app_root", lambda: tmp_path)
    monkeypatch.setattr(
        web_manager,
        "end_system_service",
        lambda: web_manager.ActionResult(True, ""),
    )
    monkeypatch.setattr(
        web_manager,
        "get_process_command_line",
        lambda _pid: "PicOrgFTP-SQL-WEB --service-run",
    )
    monkeypatch.setattr(web_manager, "get_port_listeners", lambda _port: [])
    monkeypatch.setattr(
        web_manager,
        "_run_command",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 5, "", "Access denied"),
    )

    result = web_manager.stop_web(8010)

    assert not result.ok
    assert "Access denied" in result.message
    assert pid_path.exists()


def test_end_system_service_reports_scheduler_error(monkeypatch) -> None:
    """Catches silently discarding a failed request to stop the SYSTEM task."""
    monkeypatch.setattr(web_manager, "task_exists", lambda: True)
    monkeypatch.setattr(
        web_manager,
        "_run_command",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 1, "", "Access denied"),
    )

    result = web_manager.end_system_service()

    assert not result.ok
    assert "Access denied" in result.message


def test_stop_web_keeps_metadata_when_panel_port_stays_open(tmp_path, monkeypatch) -> None:
    """Catches removing runtime metadata before the web listener actually exits."""
    pid_path = tmp_path / ".picorg_web.pid"
    pid_path.write_text(json.dumps({"pid": 102}), encoding="ascii")
    listener = {
        "Pid": 102,
        "ProcessName": "PicOrgFTP-SQL-WEB",
        "CommandLine": "PicOrgFTP-SQL-WEB --service-run",
    }
    listener_queries = 0
    slept = []

    def listeners(_port: int):
        nonlocal listener_queries
        listener_queries += 1
        return [] if listener_queries == 1 else [listener]

    monkeypatch.setattr(web_manager, "app_root", lambda: tmp_path)
    monkeypatch.setattr(
        web_manager,
        "end_system_service",
        lambda: web_manager.ActionResult(True, ""),
    )
    monkeypatch.setattr(
        web_manager,
        "get_process_command_line",
        lambda _pid: "PicOrgFTP-SQL-WEB --service-run",
    )
    monkeypatch.setattr(web_manager, "get_port_listeners", listeners)
    monkeypatch.setattr(
        web_manager,
        "_run_command",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "", ""),
    )
    monkeypatch.setattr(web_manager.time, "monotonic", lambda: 0 if not slept else 10)
    monkeypatch.setattr(web_manager.time, "sleep", lambda seconds: slept.append(seconds))

    result = web_manager.stop_web(8010)

    assert not result.ok
    assert "8010" in result.message
    assert slept == [0.2]
    assert pid_path.exists()


def test_finish_close_stop_keeps_gui_open_when_server_stop_fails() -> None:
    """Catches closing the manager after an unconfirmed server shutdown."""
    app = _app_without_tk()

    app._finish_close_stop(web_manager.ActionResult(False, "Port 8010 nadal dziala."))

    assert not app.root.destroyed
    assert app.status_var.value == "Port 8010 nadal dziala."


def test_close_window_starts_background_check_and_shows_spinner(monkeypatch) -> None:
    app = _app_without_tk()
    thread_targets = []
    thread_starts = []

    class FakeThread:
        def __init__(self, *, target, daemon: bool) -> None:
            thread_targets.append((target, daemon))

        def start(self) -> None:
            thread_starts.append(True)

    monkeypatch.setattr(web_manager.threading, "Thread", FakeThread)

    app.close_window()

    assert app.close_check_in_progress
    assert app.close_progress.started == 1
    assert app.status_var.value == "Sprawdzam, czy panel WWW dziala..."
    assert len(thread_targets) == 1
    assert thread_targets[0][1] is True
    assert thread_starts == [True]
    assert not app.root.destroyed


def test_finish_close_check_keeps_running_web_panel_accessible_in_tray(monkeypatch) -> None:
    app = _app_without_tk()
    hidden = []
    stopped = []
    app.minimize_to_tray = lambda: hidden.append(True)

    monkeypatch.setattr(web_manager, "confirm_close_running_web_panel", lambda: False, raising=False)
    monkeypatch.setattr(
        web_manager,
        "stop_web",
        lambda port: stopped.append(port) or web_manager.ActionResult(True, "Zatrzymano."),
    )
    app.close_check_in_progress = True
    app.close_progress.start()

    app._finish_close_check(True)

    assert hidden == [True]
    assert stopped == []
    assert not app.root.destroyed
    assert not app.close_check_in_progress
    assert app.close_progress.stopped == 1


def test_finish_close_check_stops_running_web_panel_in_background_when_user_confirms(monkeypatch) -> None:
    app = _app_without_tk()
    hidden = []
    stopped = []
    thread_targets = []
    thread_starts = []
    app.minimize_to_tray = lambda: hidden.append(True)

    class FakeThread:
        def __init__(self, *, target, daemon: bool) -> None:
            thread_targets.append((target, daemon))

        def start(self) -> None:
            thread_starts.append(True)

    monkeypatch.setattr(web_manager.threading, "Thread", FakeThread)
    monkeypatch.setattr(web_manager, "confirm_close_running_web_panel", lambda: True, raising=False)
    monkeypatch.setattr(
        web_manager,
        "stop_web",
        lambda port: stopped.append(port) or web_manager.ActionResult(True, "Zatrzymano."),
    )
    app.close_check_in_progress = True
    app.close_progress.start()

    app._finish_close_check(True)

    assert stopped == []
    assert hidden == []
    assert not app.root.destroyed
    assert app.close_check_in_progress
    assert app.status_var.value == "Zatrzymuje panel WWW..."
    assert len(thread_targets) == 1
    assert thread_targets[0][1] is True
    assert thread_starts == [True]

    thread_targets[0][0]()

    assert stopped == [8010]
    assert app.root.destroyed
    assert not app.close_check_in_progress
    assert app.close_progress.stopped == 2
