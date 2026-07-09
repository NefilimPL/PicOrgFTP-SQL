# GitHub Repo Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a no-token GitHub repository status button to the web panel and pulse it when a newer public release is available.

**Architecture:** The FastAPI backend owns all GitHub HTTP calls through a small stdlib-based helper so the browser remains same-origin under the existing CSP. The static frontend adds a compact header button and modal, then reads normalized status from `/api/github/repository`.

**Tech Stack:** Python 3, FastAPI, pytest, static HTML/CSS/JavaScript, GitHub REST API via `urllib.request`.

## Global Constraints

- Repository is fixed to `NefilimPL/PicOrgFTP-SQL`.
- Do not store, request, expose, edit, or read a GitHub token.
- Do not add auto-update or one-click update behavior.
- Treat local version `dev` as older than the latest public release.
- Use semantic comparison only for tags like `v1.2.3` and `1.2.3`; if comparison is unsafe, show release info without claiming an update.
- Return private or unavailable state for GitHub `404`; return temporary unavailable state for other failures.

---

## File Structure

- Create `picorgftp_sql/github_status.py` for fixed repo constants, GitHub API fetching, response normalization, short cache, and version comparison.
- Modify `picorgftp_sql/web/app.py` to expose `GET /api/github/repository`.
- Modify `picorgftp_sql/web/static/index.html` to add the GitHub button and modal.
- Modify `picorgftp_sql/web/static/app.css` to style the button, modal rows, and pulse state.
- Modify `picorgftp_sql/web/static/app.js` to fetch/render GitHub status and apply pulse state.
- Add `tests/test_github_status.py` for pure backend helper behavior.
- Extend `tests/test_web_smoke_ci.py` for route registration and endpoint response.
- Extend `tests/test_web_ui_integrity.py` for static UI wiring.

---

### Task 1: Backend GitHub Status Helper And API

**Files:**
- Create: `picorgftp_sql/github_status.py`
- Modify: `picorgftp_sql/web/app.py`
- Test: `tests/test_github_status.py`
- Test: `tests/test_web_smoke_ci.py`

**Interfaces:**
- Produces: `picorgftp_sql.github_status.github_repository_status(current_version: str | None = None, force_refresh: bool = False) -> dict[str, object]`
- Produces: `picorgftp_sql.github_status.github_update_available(current_version: str, latest_tag: str) -> bool`
- Consumes: `picorgftp_sql.version.get_display_version()`
- Consumes: FastAPI `Request`

- [ ] **Step 1: Write failing pure helper tests**

Add `tests/test_github_status.py`:

```python
from __future__ import annotations

from unittest.mock import patch

from picorgftp_sql import github_status


def test_dev_version_is_older_than_latest_release() -> None:
    assert github_status.github_update_available("dev", "v1.2.3") is True


def test_semantic_release_comparison_detects_newer_release() -> None:
    assert github_status.github_update_available("v1.2.2", "v1.2.3") is True
    assert github_status.github_update_available("v1.2.3", "v1.2.3") is False
    assert github_status.github_update_available("v1.3.0", "v1.2.3") is False


def test_non_semantic_versions_do_not_claim_update() -> None:
    assert github_status.github_update_available("build-local", "release-latest") is False


def test_public_repository_payload_is_normalized() -> None:
    responses = {
        "/repos/NefilimPL/PicOrgFTP-SQL": {
            "full_name": "NefilimPL/PicOrgFTP-SQL",
            "html_url": "https://github.com/NefilimPL/PicOrgFTP-SQL",
            "private": False,
            "description": "Panel",
            "license": {"spdx_id": "MIT", "name": "MIT License"},
            "owner": {
                "login": "NefilimPL",
                "html_url": "https://github.com/NefilimPL",
                "type": "User",
            },
        },
        "/repos/NefilimPL/PicOrgFTP-SQL/releases/latest": {
            "tag_name": "v1.2.3",
            "name": "v1.2.3",
            "html_url": "https://github.com/NefilimPL/PicOrgFTP-SQL/releases/tag/v1.2.3",
            "published_at": "2026-07-01T12:00:00Z",
            "prerelease": False,
            "draft": False,
        },
        "/repos/NefilimPL/PicOrgFTP-SQL/contributors": [
            {"login": "NefilimPL", "html_url": "https://github.com/NefilimPL", "contributions": 10},
            {"login": "Contributor", "html_url": "https://github.com/Contributor", "contributions": 3},
        ],
    }

    def fake_fetch(path: str) -> object:
        return responses[path]

    with patch.object(github_status, "_github_fetch_json", side_effect=fake_fetch):
        payload = github_status.github_repository_status("dev", force_refresh=True)

    assert payload["available"] is True
    assert payload["private"] is False
    assert payload["update_available"] is True
    assert payload["repository"]["full_name"] == "NefilimPL/PicOrgFTP-SQL"
    assert payload["latest_release"]["tag_name"] == "v1.2.3"
    assert payload["license"]["spdx_id"] == "MIT"
    assert payload["owner"]["login"] == "NefilimPL"
    assert [item["login"] for item in payload["contributors"]] == ["Contributor"]


def test_not_found_reports_private_or_unavailable() -> None:
    def fake_fetch(path: str) -> object:
        raise github_status.GitHubStatusError(404, "missing")

    with patch.object(github_status, "_github_fetch_json", side_effect=fake_fetch):
        payload = github_status.github_repository_status("v1.0.0", force_refresh=True)

    assert payload["available"] is False
    assert payload["private"] is True
    assert payload["message"] == "Repozytorium jest prywatne albo niedostepne."
    assert payload["update_available"] is False
```

- [ ] **Step 2: Run helper tests to verify they fail**

Run: `pytest tests/test_github_status.py -q`

Expected: FAIL during import or attribute access because `picorgftp_sql.github_status` does not exist yet.

- [ ] **Step 3: Implement minimal helper**

Create `picorgftp_sql/github_status.py` with:

```python
"""GitHub repository status helpers for the web panel."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .version import get_display_version

GITHUB_REPO_OWNER = "NefilimPL"
GITHUB_REPO_NAME = "PicOrgFTP-SQL"
GITHUB_REPO_FULL_NAME = f"{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
GITHUB_API_ROOT = "https://api.github.com"
GITHUB_STATUS_CACHE_SECONDS = 15 * 60

_CACHE: dict[str, object] = {"payload": None, "expires_at": 0.0}


class GitHubStatusError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = int(status_code)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _empty_payload(available: bool, private: bool, message: str, current_version: str) -> dict[str, object]:
    return {
        "available": available,
        "private": private,
        "message": message,
        "repository": {},
        "latest_release": {},
        "license": {},
        "owner": {},
        "contributors": [],
        "current_version": current_version,
        "update_available": False,
        "checked_at": _utc_now(),
    }


def _github_fetch_json(path: str) -> object:
    request = Request(
        f"{GITHUB_API_ROOT}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "PicOrgFTP-SQL-Web",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            raw = response.read()
    except HTTPError as exc:
        raise GitHubStatusError(exc.code, str(exc.reason or exc)) from exc
    except URLError as exc:
        raise GitHubStatusError(0, str(exc.reason or exc)) from exc
    except TimeoutError as exc:
        raise GitHubStatusError(0, str(exc)) from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise GitHubStatusError(0, "GitHub returned invalid JSON.") from exc


def _semantic_tuple(value: str) -> tuple[int, int, int] | None:
    text = str(value or "").strip().lower()
    if text.startswith("v"):
        text = text[1:]
    parts = text.split(".")
    if len(parts) != 3:
        return None
    try:
        numbers = tuple(int(part) for part in parts)
    except ValueError:
        return None
    if any(number < 0 for number in numbers):
        return None
    return numbers


def github_update_available(current_version: str, latest_tag: str) -> bool:
    current = str(current_version or "").strip()
    latest = str(latest_tag or "").strip()
    if not latest:
        return False
    if current.lower() == "dev":
        return True
    current_tuple = _semantic_tuple(current)
    latest_tuple = _semantic_tuple(latest)
    if current_tuple is None or latest_tuple is None:
        return False
    return latest_tuple > current_tuple


def _owner_payload(raw: dict[str, Any]) -> dict[str, object]:
    owner = raw.get("owner") if isinstance(raw.get("owner"), dict) else {}
    return {
        "login": str(owner.get("login") or ""),
        "html_url": str(owner.get("html_url") or ""),
        "type": str(owner.get("type") or ""),
    }


def _license_payload(raw: dict[str, Any]) -> dict[str, object]:
    license_data = raw.get("license") if isinstance(raw.get("license"), dict) else {}
    return {
        "name": str(license_data.get("name") or "Brak informacji"),
        "spdx_id": str(license_data.get("spdx_id") or ""),
    }


def _repository_payload(raw: dict[str, Any]) -> dict[str, object]:
    return {
        "full_name": str(raw.get("full_name") or GITHUB_REPO_FULL_NAME),
        "html_url": str(raw.get("html_url") or f"https://github.com/{GITHUB_REPO_FULL_NAME}"),
        "description": str(raw.get("description") or ""),
    }


def _release_payload(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    return {
        "tag_name": str(raw.get("tag_name") or ""),
        "name": str(raw.get("name") or raw.get("tag_name") or ""),
        "html_url": str(raw.get("html_url") or ""),
        "published_at": str(raw.get("published_at") or ""),
        "prerelease": bool(raw.get("prerelease")),
        "draft": bool(raw.get("draft")),
    }


def _contributors_payload(raw: object, owner_login: str) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    contributors: list[dict[str, object]] = []
    owner_key = owner_login.lower()
    for item in raw:
        if not isinstance(item, dict):
            continue
        login = str(item.get("login") or "")
        if not login or login.lower() == owner_key:
            continue
        contributors.append(
            {
                "login": login,
                "html_url": str(item.get("html_url") or ""),
                "contributions": int(item.get("contributions") or 0),
            }
        )
    return contributors


def _load_uncached_status(current_version: str) -> dict[str, object]:
    try:
        repo_raw = _github_fetch_json(f"/repos/{GITHUB_REPO_FULL_NAME}")
    except GitHubStatusError as exc:
        if exc.status_code == 404:
            return _empty_payload(
                False,
                True,
                "Repozytorium jest prywatne albo niedostepne.",
                current_version,
            )
        return _empty_payload(False, False, "Nie udalo sie pobrac danych GitHub.", current_version)
    if not isinstance(repo_raw, dict):
        return _empty_payload(False, False, "GitHub zwrocil niepoprawne dane repozytorium.", current_version)
    try:
        release_raw = _github_fetch_json(f"/repos/{GITHUB_REPO_FULL_NAME}/releases/latest")
    except GitHubStatusError:
        release_raw = {}
    try:
        contributors_raw = _github_fetch_json(f"/repos/{GITHUB_REPO_FULL_NAME}/contributors")
    except GitHubStatusError:
        contributors_raw = []
    owner = _owner_payload(repo_raw)
    latest_release = _release_payload(release_raw)
    latest_tag = str(latest_release.get("tag_name") or "")
    return {
        "available": True,
        "private": bool(repo_raw.get("private")),
        "message": "",
        "repository": _repository_payload(repo_raw),
        "latest_release": latest_release,
        "license": _license_payload(repo_raw),
        "owner": owner,
        "contributors": _contributors_payload(contributors_raw, str(owner.get("login") or "")),
        "current_version": current_version,
        "update_available": github_update_available(current_version, latest_tag),
        "checked_at": _utc_now(),
    }


def github_repository_status(
    current_version: str | None = None,
    force_refresh: bool = False,
) -> dict[str, object]:
    version = str(current_version or get_display_version() or "dev")
    now = time.time()
    cached = _CACHE.get("payload")
    if not force_refresh and isinstance(cached, dict) and float(_CACHE.get("expires_at") or 0) > now:
        payload = dict(cached)
        payload["current_version"] = version
        latest = payload.get("latest_release") if isinstance(payload.get("latest_release"), dict) else {}
        payload["update_available"] = github_update_available(version, str(latest.get("tag_name") or ""))
        return payload
    payload = _load_uncached_status(version)
    _CACHE["payload"] = dict(payload)
    _CACHE["expires_at"] = now + GITHUB_STATUS_CACHE_SECONDS
    return payload
```

- [ ] **Step 4: Run helper tests to verify they pass**

Run: `pytest tests/test_github_status.py -q`

Expected: PASS.

- [ ] **Step 5: Write failing web endpoint tests**

In `tests/test_web_smoke_ci.py`, add `/api/github/repository` to `expected_paths` in `test_critical_backend_routes_remain_registered`.

Add this test to `WebSmokeCiTests`:

```python
    def test_github_repository_endpoint_returns_status_payload(self) -> None:
        client = TestClient(web_app.app)
        payload = {
            "available": True,
            "private": False,
            "repository": {"full_name": "NefilimPL/PicOrgFTP-SQL"},
            "latest_release": {"tag_name": "v1.2.3"},
            "license": {"spdx_id": "MIT"},
            "owner": {"login": "NefilimPL"},
            "contributors": [],
            "current_version": "dev",
            "update_available": True,
            "message": "",
            "checked_at": "2026-07-09T00:00:00Z",
        }

        with patch.object(web_app, "github_repository_status", return_value=payload):
            response = client.get("/api/github/repository")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
```

- [ ] **Step 6: Run endpoint tests to verify they fail**

Run: `pytest tests/test_web_smoke_ci.py::WebSmokeCiTests::test_critical_backend_routes_remain_registered tests/test_web_smoke_ci.py::WebSmokeCiTests::test_github_repository_endpoint_returns_status_payload -q`

Expected: FAIL because the route and imported helper do not exist in `web_app`.

- [ ] **Step 7: Wire backend route**

Modify `picorgftp_sql/web/app.py`:

```python
from ..github_status import github_repository_status
```

Inside `create_app()`, after `/api/bootstrap` or near other read-only API routes:

```python
    @app.get("/api/github/repository")
    def github_repository_api(request: Request) -> Dict[str, Any]:
        _require_user(request)
        return github_repository_status(get_display_version())
```

- [ ] **Step 8: Run endpoint tests to verify they pass**

Run: `pytest tests/test_web_smoke_ci.py::WebSmokeCiTests::test_critical_backend_routes_remain_registered tests/test_web_smoke_ci.py::WebSmokeCiTests::test_github_repository_endpoint_returns_status_payload -q`

Expected: PASS.

- [ ] **Step 9: Commit backend task**

Run:

```bash
git add picorgftp_sql/github_status.py picorgftp_sql/web/app.py tests/test_github_status.py tests/test_web_smoke_ci.py
git commit -m "Add GitHub repository status API"
```

---

### Task 2: Static Header Button And Modal

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.css`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: Frontend IDs `githubStatusButton`, `githubStatusModal`, `githubStatusOutput`, and `githubStatusCheckedAt`.
- Produces: Static DOM elements used by Task 3 JS.

- [ ] **Step 1: Write failing UI integrity tests**

Add this test to `tests/test_web_ui_integrity.py`:

```python
    def test_github_status_button_and_modal_exist(self) -> None:
        html = _parse(INDEX_HTML)
        css = (
            ROOT / "picorgftp_sql" / "web" / "static" / "app.css"
        ).read_text(encoding="utf-8")

        self.assertIn("githubStatusButton", html.button_ids)
        self.assertIn("githubStatusModal", html.ids)
        self.assertIn("githubStatusOutput", html.ids)
        self.assertIn("githubStatusCheckedAt", html.ids)
        self.assertTrue(html.has_tag("button", id="githubStatusButton", type="button"))
        self.assertIn(".github-status-button", css)
        self.assertIn(".github-status-button.update-available", css)
        self.assertIn("@keyframes github-status-pulse", css)
```

- [ ] **Step 2: Run UI test to verify it fails**

Run: `pytest tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_github_status_button_and_modal_exist -q`

Expected: FAIL because the button/modal and CSS do not exist yet.

- [ ] **Step 3: Add static HTML**

In `picorgftp_sql/web/static/index.html`, replace the topbar title block:

```html
      <div>
        <strong>PicOrgFTP-SQL Web</strong>
        <span id="versionInfo"></span>
        <span id="serverInfo"></span>
      </div>
```

with:

```html
      <div class="topbar-brand">
        <div>
          <strong>PicOrgFTP-SQL Web</strong>
          <span id="versionInfo"></span>
          <span id="serverInfo"></span>
        </div>
        <button id="githubStatusButton" type="button" class="github-status-button" title="Informacje o repozytorium GitHub" aria-label="Informacje o repozytorium GitHub">
          <svg aria-hidden="true" viewBox="0 0 16 16" width="18" height="18" focusable="false">
            <path fill="currentColor" d="M8 .2a8 8 0 0 0-2.5 15.6c.4.1.5-.2.5-.4v-1.4c-2.1.5-2.5-.9-2.5-.9-.3-.8-.8-1-.8-1-.7-.5.1-.5.1-.5.7.1 1.1.8 1.1.8.7 1.1 1.7.8 2.1.6.1-.5.3-.8.5-1-1.7-.2-3.4-.8-3.4-3.6 0-.8.3-1.5.8-2-.1-.2-.3-1 .1-2 0 0 .6-.2 2.1.8a7 7 0 0 1 3.8 0c1.5-1 2.1-.8 2.1-.8.4 1 .2 1.8.1 2 .5.5.8 1.2.8 2 0 2.8-1.7 3.4-3.4 3.6.3.2.5.7.5 1.4v2.1c0 .2.1.5.5.4A8 8 0 0 0 8 .2Z"/>
          </svg>
        </button>
      </div>
```

Add this modal near the other top-level modals:

```html
    <div id="githubStatusModal" class="modal-view">
      <section class="modal-panel compact-modal">
        <div class="section-heading">
          <h1>Repozytorium GitHub</h1>
          <button type="button" class="ghost-button modal-close" data-close-github-status>Zamknij</button>
        </div>
        <div id="githubStatusOutput" class="github-status-output empty-state">Brak danych repozytorium.</div>
        <span id="githubStatusCheckedAt" class="github-status-checked"></span>
      </section>
    </div>
```

- [ ] **Step 4: Add CSS**

Add to `picorgftp_sql/web/static/app.css` near topbar styles:

```css
.topbar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.github-status-button {
  display: inline-grid;
  width: 34px;
  min-width: 34px;
  height: 34px;
  min-height: 34px;
  place-items: center;
  border-color: var(--line);
  background: var(--surface);
  color: var(--text);
  padding: 0;
}

.github-status-button:hover {
  border-color: var(--accent);
  background: var(--surface-2);
}

.github-status-button.update-available {
  border-color: var(--warn);
  color: var(--warn);
  animation: github-status-pulse 1.1s ease-in-out infinite;
}

.github-status-output {
  display: grid;
  gap: 10px;
}

.github-status-row {
  display: grid;
  gap: 3px;
  border-bottom: 1px solid var(--surface-2);
  padding-bottom: 8px;
}

.github-status-row:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.github-status-row strong {
  font-size: 13px;
}

.github-status-row span,
.github-status-row a,
.github-status-checked {
  color: var(--muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.github-status-row a {
  color: var(--accent-strong);
}

@keyframes github-status-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(164, 95, 33, 0);
  }
  50% {
    background: color-mix(in srgb, var(--warn) 16%, var(--surface));
    box-shadow: 0 0 0 4px rgba(164, 95, 33, 0.22);
  }
}
```

- [ ] **Step 5: Run UI test to verify it passes**

Run: `pytest tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_github_status_button_and_modal_exist -q`

Expected: PASS.

- [ ] **Step 6: Commit static UI task**

Run:

```bash
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
git commit -m "Add GitHub repository status modal"
```

---

### Task 3: Frontend Data Flow And Update Pulse

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: `/api/github/repository` from Task 1.
- Consumes: DOM IDs from Task 2.
- Produces: `refreshGithubStatus(options = {})`, `renderGithubStatus(payload = {})`, and update pulse class on `githubStatusButton`.

- [ ] **Step 1: Write failing JS integrity test**

Add this test to `tests/test_web_ui_integrity.py`:

```python
    def test_app_js_loads_and_renders_github_status(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn('const githubStatusButton = document.querySelector("#githubStatusButton")', source)
        self.assertIn('const githubStatusModal = document.querySelector("#githubStatusModal")', source)
        self.assertIn('const githubStatusOutput = document.querySelector("#githubStatusOutput")', source)
        self.assertIn('function renderGithubStatus', source)
        self.assertIn('async function refreshGithubStatus', source)
        self.assertIn('requestJson("/api/github/repository"', source)
        self.assertIn('githubStatusButton.classList.toggle("update-available"', source)
        self.assertIn('document.querySelectorAll("[data-close-github-status]")', source)
```

- [ ] **Step 2: Run JS integrity test to verify it fails**

Run: `pytest tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_app_js_loads_and_renders_github_status -q`

Expected: FAIL because JS does not reference the GitHub status UI yet.

- [ ] **Step 3: Add JS selectors and state**

In `picorgftp_sql/web/static/app.js`, add state:

```javascript
  githubStatus: null,
  githubStatusLoading: false,
```

Add selectors near the topbar selectors:

```javascript
const githubStatusButton = document.querySelector("#githubStatusButton");
const githubStatusModal = document.querySelector("#githubStatusModal");
const githubStatusOutput = document.querySelector("#githubStatusOutput");
const githubStatusCheckedAt = document.querySelector("#githubStatusCheckedAt");
```

- [ ] **Step 4: Add render and fetch functions**

Add these functions near other modal/render helpers:

```javascript
function githubRow(label, value, url = "") {
  const row = document.createElement("div");
  row.className = "github-status-row";
  const title = document.createElement("strong");
  title.textContent = label;
  if (url) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = value || url;
    row.append(title, link);
  } else {
    const text = document.createElement("span");
    text.textContent = value || "Brak informacji";
    row.append(title, text);
  }
  return row;
}

function renderGithubStatus(payload = {}) {
  state.githubStatus = payload || {};
  if (githubStatusButton) {
    githubStatusButton.classList.toggle("update-available", Boolean(payload.update_available));
    githubStatusButton.title = payload.update_available
      ? "Dostepna jest nowsza wersja na GitHub"
      : "Informacje o repozytorium GitHub";
  }
  if (!githubStatusOutput) return;
  githubStatusOutput.textContent = "";
  if (!payload.available) {
    githubStatusOutput.classList.add("empty-state");
    githubStatusOutput.appendChild(
      githubRow("Status", payload.message || "Repozytorium jest prywatne albo niedostepne.")
    );
  } else {
    githubStatusOutput.classList.remove("empty-state");
    const repo = payload.repository || {};
    const release = payload.latest_release || {};
    const license = payload.license || {};
    const owner = payload.owner || {};
    const contributors = Array.isArray(payload.contributors) ? payload.contributors : [];
    githubStatusOutput.append(
      githubRow("Repozytorium", repo.full_name || "PicOrgFTP-SQL", repo.html_url || ""),
      githubRow("Wersja lokalna", payload.current_version || "dev"),
      githubRow(
        payload.update_available ? "Aktualizacja" : "Najnowszy release",
        release.tag_name
          ? `${release.tag_name}${release.published_at ? ` (${release.published_at})` : ""}`
          : "Brak publicznego release",
        release.html_url || ""
      ),
      githubRow("Licencja", license.spdx_id || license.name || "Brak informacji"),
      githubRow("Wlasciciel", owner.login || "Brak informacji", owner.html_url || ""),
      githubRow(
        "Contributors",
        contributors.length
          ? contributors.map((item) => `${item.login} (${item.contributions || 0})`).join(", ")
          : "Brak dodatkowych contributors"
      )
    );
  }
  if (githubStatusCheckedAt) {
    githubStatusCheckedAt.textContent = payload.checked_at ? `Sprawdzono: ${payload.checked_at}` : "";
  }
}

async function refreshGithubStatus(options = {}) {
  if (state.githubStatusLoading) return state.githubStatus;
  state.githubStatusLoading = true;
  try {
    const payload = await requestJson("/api/github/repository", options);
    renderGithubStatus(payload);
    return payload;
  } catch (error) {
    const payload = {
      available: false,
      private: false,
      message: error.message || "Nie udalo sie pobrac danych GitHub.",
      update_available: false,
    };
    renderGithubStatus(payload);
    return payload;
  } finally {
    state.githubStatusLoading = false;
  }
}

function openGithubStatusModal() {
  closeAutocompletePanels();
  githubStatusModal?.classList.add("active");
  if (!state.githubStatus) {
    if (githubStatusOutput) githubStatusOutput.textContent = "Pobieranie danych GitHub...";
    refreshGithubStatus().catch(() => {});
  }
}
```

- [ ] **Step 5: Wire events and bootstrap refresh**

Near other close listeners:

```javascript
document.querySelectorAll("[data-close-github-status]").forEach((button) => {
  button.addEventListener("click", () => {
    githubStatusModal?.classList.remove("active");
  });
});
```

Near other top-level event handlers:

```javascript
githubStatusButton?.addEventListener("click", () => {
  openGithubStatusModal();
  refreshGithubStatus().catch(() => {});
});
```

Inside `loadBootstrap`, after the existing background refresh calls:

```javascript
  refreshGithubStatus().catch(() => {});
```

- [ ] **Step 6: Run JS integrity test to verify it passes**

Run: `pytest tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_app_js_loads_and_renders_github_status -q`

Expected: PASS.

- [ ] **Step 7: Run relevant full tests**

Run:

```bash
pytest tests/test_github_status.py tests/test_web_smoke_ci.py::WebSmokeCiTests::test_public_pages_and_static_assets_are_served tests/test_web_smoke_ci.py::WebSmokeCiTests::test_critical_backend_routes_remain_registered tests/test_web_smoke_ci.py::WebSmokeCiTests::test_github_repository_endpoint_returns_status_payload tests/test_web_ui_integrity.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit frontend data flow task**

Run:

```bash
git add picorgftp_sql/web/static/app.js tests/test_web_ui_integrity.py
git commit -m "Render GitHub repository update status"
```

---

## Final Verification

- [ ] Run `pytest tests/test_github_status.py tests/test_web_smoke_ci.py tests/test_web_ui_integrity.py -q`
- [ ] Confirm no GitHub token setting, field, or secret path exists in changed files.
- [ ] Confirm `/api/github/repository` returns a safe unavailable payload when helper raises `GitHubStatusError(404, ...)`.
- [ ] Confirm local `dev` plus public latest release produces `update_available: true`.
