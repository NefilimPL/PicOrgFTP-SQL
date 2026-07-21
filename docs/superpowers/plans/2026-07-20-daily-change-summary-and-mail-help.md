# Daily Change Summary and Mail Help Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one compact daily product-change email and explain mail settings through clickable help popovers.

**Architecture:** SQLite records a retryable report window and the worker claims/delivers it once. `NotificationService` derives compact EAN rows from persisted product history. The settings API stores a normalized schedule; the existing vanilla-JS settings view renders the schedule and reusable popovers.

**Tech Stack:** Python 3.13, SQLite, FastAPI, vanilla JavaScript, pytest.

## Global Constraints

- Default schedule is `16:00` in `Europe/Warsaw` and covers the prior successful report interval.
- No immediate notification intent may be created for `info` operational events.
- A report is sent only when product changes exist; no product-count cap.
- Report contents are limited to EAN, entry creation, PIMcore field names and photo slot numbers.
- Tooltip text must explicitly distinguish Entra Secret Value from Secret ID and Object ID.

---

### Task 1: Durable schedule, report state, and compact mail generator

**Files:**
- Modify: `picorgftp_sql/email_settings.py`
- Modify: `picorgftp_sql/sqlite_store.py`
- Modify: `picorgftp_sql/observability.py`
- Modify: `picorgftp_sql/notification_service.py`
- Test: `tests/test_email_settings.py`
- Test: `tests/test_sqlite_store.py`
- Test: `tests/test_notification_service.py`

**Interfaces:**
- Produces: normalized `daily_summary_time` setting.
- Produces: atomic SQLite claim/finalize methods for one daily summary interval.
- Produces: worker call that builds one compact EAN-grouped report from history.

- [ ] Write failing tests for schedule normalization, disabled immediate info intents, durable claim/retry, consecutive report windows and compact field/slot rows.
- [ ] Run focused tests and confirm missing schedule/report behavior fails.
- [ ] Implement migration, report state, history projection, direct delivery and worker due check.
- [ ] Run focused tests and full suite.

### Task 2: Settings schedule and accessible help popovers

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Modify: `tests/test_source_integrity.py`

**Interfaces:**
- Consumes: public `daily_summary_time` setting.
- Produces: clickable `?` help button/popover and schedule input in mail settings.

- [ ] Write source/UI tests for schedule input and required Entra/severity help text.
- [ ] Run the test and confirm it fails before UI code exists.
- [ ] Implement popovers with Escape/outside-close behavior and persist the schedule in the existing settings form.
- [ ] Run source/UI tests and full suite.

### Task 3: Review and commit

- [ ] Independently review report interval, duplicate prevention, retry behavior, recipient privacy and UI text.
- [ ] Run `python -m pytest -q` and `git diff --check`.
- [ ] Commit code and tests with message `feat: add daily change summary emails`.
