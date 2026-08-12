# Web Runtime Shutdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zatrzymać kontrolowane drzewo runtime panelu WWW i zamykać GUI tylko po potwierdzonym zwolnieniu portu.

**Architecture:** Metadane `.picorg_web.pid` dostaną opcjonalny PID kontrolowanego launchera. Menedżer oraz skrypty kończą najpierw launcher i jego drzewo, weryfikują wynik polecenia systemowego i sprawdzają zwolnienie portu przed usunięciem metadanych.

**Tech Stack:** Python 3, `subprocess`, Windows `taskkill`, PowerShell, pytest.

## Global Constraints

- Zachowaj obsługę metadanych zawierających tylko `pid`.
- Nie kończ procesu wyłącznie po nazwie `powershell.exe`, `python.exe` albo EXE.
- Sukces wymaga zwolnienia skonfigurowanego portu; inaczej zachowaj metadane i zwróć błąd.
- Nie zmieniaj budowania EXE i nie używaj Windows Job Object.

## Task 1: Metadane i zatrzymanie z menedżera Python

**Files:**

- Modify: `picorgftp_sql/web_manager.py:207-228, 610-637, 730-759`
- Test: `tests/test_web_manager.py`

**Interfaces:**

- Consumes: `read_metadata()`, `get_port_listeners(port)`, `_run_command(args, timeout)`.
- Produces: `write_metadata(port, host, *, launcher, launcher_pid: int | None = None)` oraz `stop_web(port) -> ActionResult` potwierdzające zwolnienie portu.

- [ ] Step 1: Write failing tests for metadata and successful tree shutdown.

```python
import json
import os
import subprocess

def test_write_metadata_records_explicit_launcher_pid(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(web_manager, "app_root", lambda: tmp_path)
    web_manager.write_metadata(8010, "0.0.0.0", launcher="service-run", launcher_pid=101)
    assert web_manager.read_metadata(tmp_path)["launcher_pid"] == 101

def test_stop_web_terminates_launcher_tree_after_port_release(tmp_path, monkeypatch) -> None:
    (tmp_path / ".picorg_web.pid").write_text(json.dumps({"pid": 102, "launcher_pid": 101}), encoding="ascii")
    calls = []
    monkeypatch.setattr(web_manager, "app_root", lambda: tmp_path)
    monkeypatch.setattr(web_manager, "end_system_service", lambda: web_manager.ActionResult(True, ""))
    monkeypatch.setattr(web_manager, "get_process_command_line", lambda _pid: "PicOrgFTP-SQL-WEB --service-run")
    monkeypatch.setattr(web_manager, "get_port_listeners", lambda _port: [])
    monkeypatch.setattr(web_manager, "_run_command", lambda args, **_kwargs: calls.append(args) or subprocess.CompletedProcess(args, 0, "", ""))
    assert web_manager.stop_web(8010).ok
    assert calls[0] == ["taskkill", "/PID", "101", "/T", "/F"]
    assert not (tmp_path / ".picorg_web.pid").exists()
```

- [ ] Step 2: Run `pytest tests/test_web_manager.py -k "launcher_pid or terminates_launcher_tree" -v`; expect failure because the production API does not accept or use `launcher_pid`.

- [ ] Step 3: Implement the smallest API change.

```python
def write_metadata(port: int, host: str, *, launcher: str, launcher_pid: int | None = None) -> None:
    payload = {
        "pid": os.getpid(),
        "port": int(port),
        "host": host,
        "launcher": launcher,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    if launcher_pid and launcher_pid > 0:
        payload["launcher_pid"] = int(launcher_pid)

def _service_launcher_pid() -> int | None:
    explicit = _safe_int(os.environ.get("PICORG_WEB_LAUNCHER_PID"))
    if explicit > 0:
        return explicit
    return os.getppid() if getattr(sys, "frozen", False) else None
```

Pass `_service_launcher_pid()` from `run_service_mode()`. Refactor `end_system_service()` to return `ActionResult`. In `stop_web()`, order PIDs as `launcher_pid`, metadata `pid`, then recognized listeners. Invoke `taskkill /PID <pid> /T /F` and accept an attempted termination only when `returncode == 0`.

- [ ] Step 4: Run `pytest tests/test_web_manager.py -k "launcher_pid or terminates_launcher_tree" -v`; expect pass.

- [ ] Step 5: Write and run failing tests for error reporting and preserving the GUI.

```python
def test_stop_web_keeps_metadata_when_taskkill_fails(tmp_path, monkeypatch) -> None:
    (tmp_path / ".picorg_web.pid").write_text(json.dumps({"pid": 102}), encoding="ascii")
    monkeypatch.setattr(web_manager, "app_root", lambda: tmp_path)
    monkeypatch.setattr(web_manager, "end_system_service", lambda: web_manager.ActionResult(True, ""))
    monkeypatch.setattr(web_manager, "get_process_command_line", lambda _pid: "PicOrgFTP-SQL-WEB --service-run")
    monkeypatch.setattr(web_manager, "get_port_listeners", lambda _port: [])
    monkeypatch.setattr(web_manager, "_run_command", lambda args, **_kwargs: subprocess.CompletedProcess(args, 5, "", "Access denied"))
    assert not web_manager.stop_web(8010).ok
    assert (tmp_path / ".picorg_web.pid").exists()

def test_finish_close_stop_keeps_gui_open_when_server_stop_fails() -> None:
    app = _app_without_tk()
    app._finish_close_stop(web_manager.ActionResult(False, "Port 8010 nadal dziala."))
    assert not app.root.destroyed
```

- [ ] Step 6: Implement `_wait_for_port_release(port, timeout=8.0)` using `time.monotonic()` and a 0.2-second poll. Delete metadata only after `taskkill` reports no relevant failure and the port has no listener. Return `ActionResult(False, f"Nie udalo sie zatrzymac panelu WWW: {detail}")`, where `detail` is stderr, then stdout, then `"brak szczegolow z Windows"`. Run `pytest tests/test_web_manager.py -v`; expect pass.

- [ ] Step 7: Commit.

```bash
git add picorgftp_sql/web_manager.py tests/test_web_manager.py
git commit -m "fix: verify web runtime shutdown"
```

## Task 2: Kontrolowany launcher w skryptach Windows

**Files:**

- Modify: `tools/web/start_web.ps1:786-799, 903-909`
- Modify: `tools/web/stop_web.ps1:42-70, 127-150`
- Test: `tests/test_web_manager.py`

**Interfaces:**

- Consumes: `.picorg_web.pid` with legacy `pid` and optional `launcher_pid`.
- Produces: marker `launcher_pid` for the starter PowerShell and tree termination in `STOP_WEB.ps1`.

- [ ] Step 1: Write a failing static regression test.

```python
def test_web_scripts_record_and_stop_the_launcher_tree() -> None:
    start_source = (ROOT / "tools" / "web" / "start_web.ps1").read_text(encoding="utf-8")
    stop_source = (ROOT / "tools" / "web" / "stop_web.ps1").read_text(encoding="utf-8")
    assert "launcher_pid = [int]$PID" in start_source
    assert 'taskkill /PID $PidValue /T /F' in stop_source
    assert "$metadata.launcher_pid" in stop_source
```

- [ ] Step 2: Run `pytest tests/test_web_manager.py::test_web_scripts_record_and_stop_the_launcher_tree -v`; expect failure because the scripts omit launcher ownership and tree termination.

- [ ] Step 3: Add `launcher_pid = [int]$PID` and `launcher = "start_web.ps1"` in `Write-RunMetadata`. Replace `Stop-Process` with `taskkill /PID $PidValue /T /F`, use `$LASTEXITCODE -eq 0`, and process `launcher_pid` before legacy `pid` and listener PIDs without duplicates.

```powershell
function Stop-WebPid($PidValue) {
    if (-not (Test-WebProcess $PidValue)) { return $false }
    & taskkill /PID $PidValue /T /F 2>&1 | Out-Null
    return $LASTEXITCODE -eq 0
}

$candidatePids = @()
if ($metadata -and $metadata.launcher_pid) { $candidatePids += [int]$metadata.launcher_pid }
if ($metadata -and $metadata.pid) { $candidatePids += [int]$metadata.pid }
$candidatePids += Get-PortListenerPids
foreach ($pidValue in $candidatePids | Select-Object -Unique) { Stop-WebPid $pidValue }
```

- [ ] Step 4: Run `pytest tests/test_web_manager.py::test_web_scripts_record_and_stop_the_launcher_tree -v`; expect pass.

- [ ] Step 5: Add and run a failing documentation regression test.

```python
def test_web_panel_docs_explain_confirmed_runtime_shutdown() -> None:
    source = (ROOT / "docs" / "web-panel.md").read_text(encoding="utf-8")
    assert "procesy launchera" in source
    assert "nie zwolni portu" in source
```

Run: `pytest tests/test_web_manager.py::test_web_panel_docs_explain_confirmed_runtime_shutdown -v`; expect failure.

Add this Polish paragraph after the `START_WEB.bat` / `STOP_WEB.bat` instructions: `Potwierdzenie zamknięcia w lokalnym menedżerze kończy serwer panelu i kontrolowane procesy launchera. Jeżeli Windows nie zwolni portu, menedżer pozostaje otwarty i pokazuje błąd.` Run the same command again; expect pass.

- [ ] Step 6: Run `pytest tests/test_web_manager.py tests/test_web_smoke_ci.py tests/test_source_integrity.py tests/test_build_exe_workflow.py -v`; expect pass. Then run `git diff --check`, inspect `git status --short`, and commit the scripts, tests, and documentation.
