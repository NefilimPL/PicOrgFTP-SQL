"""Tests for the web panel manager process launcher."""

from __future__ import annotations

import ast
import builtins
import multiprocessing
from pathlib import Path
import runpy
import sys
import types
from unittest.mock import patch

from picorgftp_sql import web_manager


ROOT = Path(__file__).resolve().parents[1]
WEB_ENTRYPOINT = ROOT / "PicOrgFTP-SQL-WEB.pyw"


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
