# Active Web Users Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-controlled, default-off active web users indicator in the top bar using the backend's existing active-client tracking.

**Architecture:** Extend the existing `security` config with a normalized boolean, expose a sanitized presence endpoint separate from the existing admin diagnostics endpoint, and render a compact non-navigation presence strip in the existing static web UI. Reuse `_active_clients_snapshot()` and keep detailed client data available only through `/api/server/active-users`.

**Tech Stack:** Python, FastAPI, unittest/pytest, static HTML/CSS/vanilla JavaScript.

---

## File Structure

- Modify `picorgftp_sql/config.py`: normalize and persist `security.show_active_web_users`.
- Modify `picorgftp_sql/common.py`: add the default security setting with value `False`.
- Modify `picorgftp_sql/web_data.py`: ensure settings snapshot and update path carry the normalized setting through the existing `security` object.
- Modify `picorgftp_sql/web/app.py`: add sanitized presence helpers and `GET /api/server/presence`.
- Modify `picorgftp_sql/web/static/index.html`: add the presence container before `#webImagesButton`.
- Modify `picorgftp_sql/web/static/app.js`: add state, polling, rendering, popover, and settings checkbox wiring.
- Modify `picorgftp_sql/web/static/app.css`: style presence labels and responsive popover.
- Modify `tests/test_web_data_users.py`: config/settings tests.
- Modify `tests/test_web_app_files.py`: direct helper tests for sanitized presence.
- Modify `tests/test_web_smoke_ci.py`: route registration and authenticated API behavior.
- Modify `tests/test_web_ui_integrity.py`: static UI coverage.

## Task 1: Security Setting

**Files:**
- Modify: `picorgftp_sql/common.py`
- Modify: `picorgftp_sql/config.py`
- Test: `tests/test_web_data_users.py`

- [ ] **Step 1: Write failing tests**

Add tests proving default normalization is disabled and update/snapshot preserve the boolean:

```python
def test_security_settings_default_hide_active_web_users(self) -> None:
    normalized = web_data.config._normalize_security_settings({})

    self.assertFalse(normalized["show_active_web_users"])


def test_update_settings_stores_active_web_users_security_flag(self) -> None:
    saved_configs = []
    cfg = {
        web_data.SECURITY_SETTINGS_KEY: {"max_upload_mb": 50},
    }

    def capture_save_config(config_payload, *_args, **_kwargs):
        saved_configs.append(json.loads(json.dumps(config_payload)))

    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "save_config", side_effect=capture_save_config),
        patch.object(web_data.config, "initialize_config", return_value=cfg),
        patch.object(web_data, "settings_snapshot", return_value={}),
    ):
        web_data.update_settings({"security": {"show_active_web_users": True}})

    self.assertTrue(saved_configs[0][web_data.SECURITY_SETTINGS_KEY]["show_active_web_users"])
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_web_data_users.py::WebDataUserTests::test_security_settings_default_hide_active_web_users tests/test_web_data_users.py::WebDataUserTests::test_update_settings_stores_active_web_users_security_flag -q`

Expected: both tests fail because `show_active_web_users` is not normalized or saved.

- [ ] **Step 3: Implement minimal setting support**

Add `"show_active_web_users": False` to `DEFAULT_CONFIG[SECURITY_SETTINGS_KEY]` in `common.py`.

Add this entry to the return dict in `config._normalize_security_settings`:

```python
"show_active_web_users": bool(
    raw.get("show_active_web_users", defaults.get("show_active_web_users", False))
),
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_web_data_users.py::WebDataUserTests::test_security_settings_default_hide_active_web_users tests/test_web_data_users.py::WebDataUserTests::test_update_settings_stores_active_web_users_security_flag -q`

Expected: both tests pass.

## Task 2: Sanitized Presence Backend

**Files:**
- Modify: `picorgftp_sql/web/app.py`
- Test: `tests/test_web_app_files.py`
- Test: `tests/test_web_smoke_ci.py`

- [ ] **Step 1: Write failing helper tests**

Add tests for disabled and enabled sanitized payloads:

```python
def test_active_presence_payload_is_disabled_by_default(self) -> None:
    with patch.object(web_app.config, "CONFIG", {}):
        payload = web_app._active_presence_payload(
            [
                {"username": "admin", "last_seen": "2026-06-30 10:00:00", "last_seen_epoch": 20},
            ]
        )

    self.assertEqual(payload, {"enabled": False, "users": []})


def test_active_presence_payload_sanitizes_and_deduplicates_users(self) -> None:
    clients = [
        {"username": "admin", "remote_address": "10.0.0.1", "path": "/api/bootstrap", "last_seen": "old", "last_seen_epoch": 10},
        {"username": "operator", "user_agent": "browser", "last_seen": "now", "last_seen_epoch": 30},
        {"username": "admin", "remote_port": 1234, "last_seen": "new", "last_seen_epoch": 40},
        {"username": "niezalogowany", "last_seen": "anon", "last_seen_epoch": 50},
        {"username": "", "last_seen": "blank", "last_seen_epoch": 60},
    ]
    with patch.object(
        web_app.config,
        "CONFIG",
        {web_app.SECURITY_SETTINGS_KEY: {"show_active_web_users": True}},
    ):
        payload = web_app._active_presence_payload(clients)

    self.assertTrue(payload["enabled"])
    self.assertEqual(
        payload["users"],
        [
            {"username": "admin", "last_seen": "new", "last_seen_epoch": 40.0},
            {"username": "operator", "last_seen": "now", "last_seen_epoch": 30.0},
        ],
    )
```

- [ ] **Step 2: Write failing route tests**

Add `/api/server/presence` to the critical route set, then add an authenticated API test that logs in and verifies the default disabled payload:

```python
presence = client.get("/api/server/presence")
self.assertEqual(presence.status_code, 200)
self.assertEqual(presence.json(), {"enabled": False, "users": []})
```

- [ ] **Step 3: Run tests to verify failure**

Run: `python -m pytest tests/test_web_app_files.py::WebAppFileTests::test_active_presence_payload_is_disabled_by_default tests/test_web_app_files.py::WebAppFileTests::test_active_presence_payload_sanitizes_and_deduplicates_users tests/test_web_smoke_ci.py::WebSmokeCiTests::test_critical_backend_routes_remain_registered -q`

Expected: helper tests fail because `_active_presence_payload` does not exist, and route registration fails because `/api/server/presence` is missing.

- [ ] **Step 4: Implement helper and endpoint**

Add `_active_presence_enabled()` and `_active_presence_payload(clients)` near the active-client helpers. The helper must call `_security_settings()` for current normalized config, exclude `""` and `"niezalogowany"`, keep only `username`, `last_seen`, and `last_seen_epoch`, deduplicate by username, sort newest first, and limit to 100.

Add route in `create_app()`:

```python
@app.get("/api/server/presence")
def active_presence_api(request: Request) -> Dict[str, Any]:
    _require_user(request)
    return _active_presence_payload(_active_clients_snapshot())
```

- [ ] **Step 5: Run tests to verify pass**

Run the same focused command from Step 3 and the authenticated login test containing the default presence assertion.

Expected: all focused backend tests pass.

## Task 3: Static UI Skeleton

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Write failing static test**

Add a test verifying the presence container exists before `#webImagesButton` and is not a button:

```python
def test_topbar_contains_non_button_presence_before_web_images(self) -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")
    html = _parse(INDEX_HTML)

    self.assertIn("activeUsersPresence", html.ids)
    self.assertIn("activeUsersList", html.ids)
    self.assertLess(source.index('id="activeUsersPresence"'), source.index('id="webImagesButton"'))
    self.assertNotIn("activeUsersPresence\" type=\"button", source)
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_topbar_contains_non_button_presence_before_web_images -q`

Expected: fails because the presence container is missing.

- [ ] **Step 3: Add minimal markup**

Insert before `#webImagesButton`:

```html
<div id="activeUsersPresence" class="active-users-presence" aria-label="Aktywni uzytkownicy" hidden>
  <div id="activeUsersList" class="active-users-list"></div>
  <button id="activeUsersMoreButton" type="button" class="presence-more-button" aria-expanded="false" hidden>...</button>
  <div id="activeUsersPopover" class="active-users-popover" hidden></div>
</div>
```

- [ ] **Step 4: Run test to verify pass**

Run the focused static test again.

Expected: pass.

## Task 4: Frontend Rendering and Settings Control

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Write failing source integrity test**

Add assertions that `app.js` and `app.css` contain the presence rendering, polling, endpoint, and settings checkbox:

```python
def test_app_js_renders_active_user_presence(self) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    css = (ROOT / "picorgftp_sql" / "web" / "static" / "app.css").read_text(encoding="utf-8")

    self.assertIn("function renderActiveUsersPresence", source)
    self.assertIn("function refreshActiveUsersPresence", source)
    self.assertIn("/api/server/presence", source)
    self.assertIn("show_active_web_users", source)
    self.assertIn("Pokaz aktywnych uzytkownikow", source)
    self.assertIn(".active-users-presence", css)
    self.assertIn(".presence-user-label", css)
    self.assertIn(".presence-more-button", css)
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_web_ui_integrity.py::WebUiIntegrityTests::test_app_js_renders_active_user_presence -q`

Expected: fails because rendering and styles are missing.

- [ ] **Step 3: Implement frontend logic**

Add state keys:

```javascript
activeUsers: [],
activeUsersEnabled: false,
activeUsersPollTimer: 0,
activeUsersFailureCount: 0,
```

Query elements:

```javascript
const activeUsersPresence = document.querySelector("#activeUsersPresence");
const activeUsersList = document.querySelector("#activeUsersList");
const activeUsersMoreButton = document.querySelector("#activeUsersMoreButton");
const activeUsersPopover = document.querySelector("#activeUsersPopover");
```

Implement:

- `renderActiveUsersPresence(payload)`;
- `refreshActiveUsersPresence()`;
- `scheduleActiveUsersPoll(delay = 15000)`;
- `toggleActiveUsersPopover(force)`;
- document click and Escape handlers to close the popover.

Call `refreshActiveUsersPresence().catch(() => {})` from `loadBootstrap()` and `startBackgroundPollers()` or schedule it from `loadBootstrap()` after successful login bootstrap.

Add the Security settings checkbox:

```javascript
checkField(
  "show_active_web_users",
  "Pokaz aktywnych uzytkownikow",
  Boolean(security.show_active_web_users),
  "Uzytkownicy zobacza nazwy kont obecnie aktywnych w panelu WWW."
)
```

Include `show_active_web_users: data.has("show_active_web_users")` in the security save payload.

- [ ] **Step 4: Implement CSS**

Add compact, non-navigation styles for:

- `.active-users-presence`;
- `.active-users-list`;
- `.presence-user-label`;
- `.presence-user-dot`;
- `.presence-more-button`;
- `.active-users-popover`;
- `.active-users-popover-row`.

Ensure `.presence-more-button` does not inherit `.nav-button` visual treatment.

- [ ] **Step 5: Run test to verify pass**

Run the focused UI integrity tests from this task and Task 3.

Expected: pass.

## Task 5: Final Verification

**Files:**
- All modified implementation and test files.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
python -m pytest tests/test_web_data_users.py tests/test_web_app_files.py tests/test_web_smoke_ci.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run focused UI tests**

Run:

```powershell
python -m pytest tests/test_web_ui_integrity.py -q
```

Expected: all UI integrity tests pass.

- [ ] **Step 3: Run source integrity smoke if fast enough**

Run:

```powershell
python -m pytest tests/test_source_integrity.py -q
```

Expected: pass or report exact unrelated failures.

- [ ] **Step 4: Inspect diff**

Run:

```powershell
git diff -- picorgftp_sql/common.py picorgftp_sql/config.py picorgftp_sql/web_data.py picorgftp_sql/web/app.py picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_data_users.py tests/test_web_app_files.py tests/test_web_smoke_ci.py tests/test_web_ui_integrity.py
```

Expected: changes match the approved spec and do not expose detailed active-client data to non-admin users.
