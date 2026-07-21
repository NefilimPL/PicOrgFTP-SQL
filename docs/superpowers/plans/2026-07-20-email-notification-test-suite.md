# Email Notification Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send and report five direct, simulated notification scenarios through the configured severity rules.

**Architecture:** `NotificationService` will create deterministic-shaped but randomly worded in-memory test scenarios, resolve their saved recipients, and reuse `_deliver_claimed`. A new admin-only API route projects only safe aggregate results; the mail settings UI triggers it and renders one compact row per scenario.

**Tech Stack:** Python 3.13, FastAPI, vanilla JavaScript, pytest.

## Global Constraints

- Preserve the existing single-recipient transport test unchanged.
- Never persist a test-suite event, incident, intent, or delivery.
- Use saved recipients for the scenario severity; do not add a fictional actor address.
- Include information, warning, error, critical, and critical Entra Client Secret-expiry scenarios.
- Reuse existing selected-channel and fallback behavior.

---

### Task 1: Service, API, UI, and regression tests

**Files:**

- Modify: `picorgftp_sql/notification_service.py:828-921`
- Modify: `picorgftp_sql/web/app.py:5577-5671`
- Modify: `picorgftp_sql/web/static/app.js:10910-11198`
- Modify: `tests/test_notification_service.py`
- Modify: `tests/test_observability_api.py`
- Modify: `tests/test_web_smoke_ci.py`
- Modify: `tests/test_source_integrity.py`

**Interfaces:**

- Produces: `NotificationService.send_test_notification_suite(channel: str, use_fallback: bool = False) -> dict[str, object]`
- Produces: `POST /api/settings/email/test-suite`
- Consumes: `resolve_recipients`, `_deliver_claimed`, current selected-channel/fallback settings.

- [ ] **Step 1: Write failing tests**

Add tests asserting five scenarios, severity routing, a skipped disabled/no-recipient rule, direct transport with fallback, no store writes, a safe API projection, and the UI endpoint/button identifiers.

- [ ] **Step 2: Run targeted tests**

Run: `python -m pytest tests/test_notification_service.py tests/test_observability_api.py tests/test_web_smoke_ci.py tests/test_source_integrity.py -q`

Expected: failures because the suite service and API route do not exist.

- [ ] **Step 3: Implement the direct suite**

Add the service method and module-level wrapper. It generates the five stated scenarios, resolves recipients with an empty username, reports a skipped scenario when no recipient resolves, and calls `_deliver_claimed` for every deliverable scenario. Add the admin-only route with selected channel/fallback validation and redacted per-scenario projection. Add the second mail-settings button and compact result rows.

- [ ] **Step 4: Verify tests**

Run: `python -m pytest tests/test_notification_service.py tests/test_observability_api.py tests/test_web_smoke_ci.py tests/test_source_integrity.py -q; python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run: `git add picorgftp_sql/notification_service.py picorgftp_sql/web/app.py picorgftp_sql/web/static/app.js tests/test_notification_service.py tests/test_observability_api.py tests/test_web_smoke_ci.py tests/test_source_integrity.py && git commit -m "feat: test every notification severity"`
