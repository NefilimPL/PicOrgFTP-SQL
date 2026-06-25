"""Tests for the web panel manager process launcher."""

from __future__ import annotations

from unittest.mock import patch

from picorgftp_sql import web_manager


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
