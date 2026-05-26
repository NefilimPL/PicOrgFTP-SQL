"""Tests for the packaged browser extension files."""

from __future__ import annotations

import json
import os
from pathlib import Path
import zipfile


os.environ.setdefault("PICORGFTP_SQL_HEADLESS", "1")
os.environ.setdefault("PICORG_WEB_AUTH", "0")

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "picorgftp_sql" / "browser_extension"


def test_browser_extension_manifest_is_valid_mv3() -> None:
    manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert manifest["action"]["default_popup"] == "popup.html"
    assert "activeTab" in manifest["permissions"]
    assert "scripting" in manifest["permissions"]
    assert "http://*/*" in manifest["host_permissions"]
    assert "https://*/*" in manifest["host_permissions"]


def test_browser_extension_popup_uploads_to_panel_endpoint() -> None:
    popup = (EXTENSION_DIR / "popup.js").read_text(encoding="utf-8")

    assert "/api/browser-extension/upload-cache" in popup
    assert "/api/browser-extension/ping" in popup
    assert "collectImagesFromPage" in popup


def test_browser_extension_download_endpoint_returns_zip() -> None:
    from fastapi.testclient import TestClient

    from picorgftp_sql.web import app as web_app

    client = TestClient(web_app.app)
    response = client.get("/api/browser-extension/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    zip_path = ROOT / "pytest-temp" / "browser-extension-test.zip"
    zip_path.parent.mkdir(exist_ok=True)
    zip_path.write_bytes(response.content)
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert "picorgftp-sql-browser-extension/manifest.json" in names
        assert "picorgftp-sql-browser-extension/popup.js" in names
        defaults = archive.read("picorgftp-sql-browser-extension/defaults.js").decode("utf-8")
    assert "window.PICORG_EXTENSION_DEFAULTS" in defaults
    assert "apiToken" in defaults


def test_web_exe_build_includes_browser_extension_assets() -> None:
    build_script = (ROOT / "Generator exe" / "build_web_exe.ps1").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "build-exe.yml").read_text(encoding="utf-8")

    assert "picorgftp_sql\\browser_extension;picorgftp_sql\\browser_extension" in build_script
    assert "picorgftp_sql/browser_extension;picorgftp_sql/browser_extension" in workflow
