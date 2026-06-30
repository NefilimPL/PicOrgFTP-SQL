"""Tests for the web panel manager process launcher."""

from __future__ import annotations

from unittest.mock import patch

from picorgftp_sql import web_manager


class _FakeRoot:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


def _app_without_tk() -> web_manager.WebManagerApp:
    app = object.__new__(web_manager.WebManagerApp)
    app.root = _FakeRoot()
    app.tray_icon = None
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


def test_close_window_keeps_running_web_panel_accessible_in_tray(monkeypatch) -> None:
    app = _app_without_tk()
    hidden = []
    stopped = []
    app.minimize_to_tray = lambda: hidden.append(True)

    monkeypatch.setattr(
        web_manager,
        "current_status",
        lambda _port: {"running": True, "web_listeners": [{"Pid": 1234}]},
    )
    monkeypatch.setattr(web_manager, "confirm_close_running_web_panel", lambda: False, raising=False)
    monkeypatch.setattr(
        web_manager,
        "stop_web",
        lambda port: stopped.append(port) or web_manager.ActionResult(True, "Zatrzymano."),
    )

    app.close_window()

    assert hidden == [True]
    assert stopped == []
    assert not app.root.destroyed


def test_close_window_stops_running_web_panel_when_user_confirms(monkeypatch) -> None:
    app = _app_without_tk()
    hidden = []
    stopped = []
    app.minimize_to_tray = lambda: hidden.append(True)

    monkeypatch.setattr(
        web_manager,
        "current_status",
        lambda _port: {"running": True, "web_listeners": [{"Pid": 1234}]},
    )
    monkeypatch.setattr(web_manager, "confirm_close_running_web_panel", lambda: True, raising=False)
    monkeypatch.setattr(
        web_manager,
        "stop_web",
        lambda port: stopped.append(port) or web_manager.ActionResult(True, "Zatrzymano."),
    )

    app.close_window()

    assert stopped == [8010]
    assert hidden == []
    assert app.root.destroyed
