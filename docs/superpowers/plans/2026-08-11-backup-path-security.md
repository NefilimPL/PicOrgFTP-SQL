# Backup Path Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Secure SQLite backup file selection while supporting explicitly configured archive directories.

**Architecture:** Backup settings persist the optional trusted archive roots. SQLite helpers resolve a selected file and verify containment before restore or diff. The API supplies the trusted roots and maps invalid paths to a client error.

**Tech Stack:** Python, FastAPI, pytest, vanilla HTML/CSS/JavaScript.

## Global Constraints

- A request-supplied path must never access a file outside a resolved trusted root.
- The default `BACKUP` directory remains the only destination for new and retained backups.
- Existing settings without `archive_dirs` continue to work.

---

### Task 1: Trusted backup roots

**Files:**
- Modify: `picorgftp_sql/storage_settings.py`, `picorgftp_sql/sqlite_backup.py`
- Test: `tests/test_sqlite_backup.py`

**Interfaces:**
- Produces `storage_settings.resolve_backup_dirs()` and safe restore/diff helpers accepting trusted roots.

- [ ] Write failing pytest cases for an archive directory that is allowed and an outside file that is rejected.
- [ ] Run `pytest tests/test_sqlite_backup.py -q` and confirm the new expectations fail before implementation.
- [ ] Add normalized archive settings and canonical containment validation.
- [ ] Run `pytest tests/test_sqlite_backup.py -q` and confirm it passes.

### Task 2: API and settings UI

**Files:**
- Modify: `picorgftp_sql/web/app.py`, `picorgftp_sql/web/static/app.js`
- Test: `tests/test_web_smoke_ci.py`

**Interfaces:**
- Consumes `resolve_backup_dirs()`.
- Produces HTTP 400 for an untrusted `backup_path` and persists archive roots from settings.

- [ ] Write failing endpoint tests for an untrusted path and a configured archive path.
- [ ] Run the focused endpoint tests and confirm they fail before implementation.
- [ ] Pass trusted roots to backup operations and add a newline-separated archive-directory field to settings.
- [ ] Run focused endpoint tests and confirm they pass.

### Task 3: Browser diagnostics

**Files:**
- Modify: `picorgftp_sql/web/static/app.css`, `picorgftp_sql/web/static/index.html`
- Test: `tests/test_web_ui_integrity.py`

- [ ] Write a focused integrity test for the checkbox label and compatibility declarations.
- [ ] Run it, then apply the minimal HTML/CSS changes.
- [ ] Run the web UI integrity tests and the complete relevant pytest suite.
