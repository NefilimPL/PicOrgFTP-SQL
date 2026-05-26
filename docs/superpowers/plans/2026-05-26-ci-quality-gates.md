# CI Quality Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add non-release GitHub Actions checks for critical web, desktop, UI integrity, and lightweight performance regressions.

**Architecture:** Add a dedicated `.github/workflows/ci.yml` for static checks and pytest. Keep release packaging in `.github/workflows/build-exe.yml`, but remove push-triggered EXE builds so CI and release packaging stay separate.

**Tech Stack:** GitHub Actions, Python 3.11, pytest, FastAPI TestClient/httpx, Node syntax check.

---

### Task 1: Add CI Workflow

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `.github/workflows/build-exe.yml`

- [ ] **Step 1: Create workflow trigger and static checks**

Create `.github/workflows/ci.yml` with `push` and `pull_request` triggers for `main`, `master`, and `dev`. Add a Windows static-check job that runs `compileall` for Python files and `node --check` for `picorgftp_sql/web/static/app.js`.

- [ ] **Step 2: Add pytest job**

In the same workflow, add a Windows test job that installs `pytest`, `httpx`, `requirements-build.txt`, `requirements-web.txt`, and `requirements-qt.txt`, then runs `python -m pytest -q` with headless environment variables.

- [ ] **Step 3: Stop push EXE builds**

Remove the `push` trigger from `.github/workflows/build-exe.yml`, leaving `workflow_dispatch` and `release: published`.

### Task 2: Add Web/UI Smoke Tests

**Files:**
- Create: `tests/test_web_smoke_ci.py`
- Create: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Add FastAPI smoke tests**

Test `/api/health`, `/login`, `/`, `/static/app.js`, `/static/app.css`, and required backend route paths with auth disabled where needed.

- [ ] **Step 2: Add static UI integrity tests**

Parse `index.html` and `login.html` with the standard library and assert required fields, buttons, modals, slot template controls, and JavaScript `#id` selectors exist.

### Task 3: Add Desktop and Performance Smoke Tests

**Files:**
- Create: `tests/test_desktop_smoke_ci.py`
- Create: `tests/test_ci_performance_smoke.py`

- [ ] **Step 1: Add desktop smoke tests**

Compile the `.pyw` entrypoints, import critical modules in headless mode, validate localization JSON files, and assert required image assets exist.

- [ ] **Step 2: Add lightweight performance/load tests**

Run repeated product path/slot helpers and repeated health endpoint calls under conservative timing budgets.

### Task 4: Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add CI badge and note**

Add a CI badge and a short note that CI runs tests on `push` and `pull_request` for `main`, `master`, and `dev`, while EXE generation remains release/manual only.

### Verification

- [ ] Run `python -m compileall -q PicOrgFTP-SQL.pyw PicOrgFTP-SQL-WEB.pyw PicOrgFTP-SQL-QtSlots.pyw picorgftp_sql tests tools`.
- [ ] Run `node --check picorgftp_sql/web/static/app.js`.
- [ ] Run `python -m pytest -q`.
- [ ] If local Python is unavailable, report that local verification was blocked and rely on workflow syntax/code review.
