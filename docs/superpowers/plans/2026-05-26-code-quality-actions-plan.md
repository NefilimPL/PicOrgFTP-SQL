# Code Quality Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reliable every-push QA workflow and keep official EXE publishing tied to GitHub releases.

**Architecture:** The new `code-quality.yml` workflow owns all push and pull-request verification. The existing `build-exe.yml` remains the release/manual packaging workflow. A small repository test validates the intended workflow behavior.

**Tech Stack:** GitHub Actions, Windows runner, Python 3.11, pytest, coverage, ruff, bandit, PyInstaller.

---

### Task 1: Workflow Metadata Test

**Files:**
- Create: `tests/test_github_actions_workflows.py`

- [ ] **Step 1: Add tests that describe the desired workflow behavior**

Create a stdlib-only unittest module that reads workflow text and verifies:

- `code-quality.yml` exists;
- it runs on `push`, `pull_request`, and `workflow_dispatch`;
- it does not upload artifacts or publish releases;
- `build-exe.yml` no longer runs on normal push;
- `build-exe.yml` keeps `release` and `workflow_dispatch`.

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/test_github_actions_workflows.py -q`

Expected before implementation: fail because `code-quality.yml` is missing and `build-exe.yml` still has push triggers.

### Task 2: Add Code Quality Workflow

**Files:**
- Create: `.github/workflows/code-quality.yml`

- [ ] **Step 1: Add Windows Python setup**

Use `actions/checkout@v4` and `actions/setup-python@v5` with Python `3.11`.

- [ ] **Step 2: Install project and QA dependencies**

Install pip, `requirements-web.txt`, `requirements-qt.txt`, `requirements-build.txt`, and direct QA tools.

- [ ] **Step 3: Add quality steps**

Add steps for `compileall`, `ruff`, `bandit`, full pytest coverage, web static smoke, FastAPI smoke, focused performance helper tests, and PyInstaller smoke build.

- [ ] **Step 4: Keep QA artifact-free**

Do not use `actions/upload-artifact` and do not call `gh release upload` in this workflow.

### Task 3: Restrict Release Build Workflow

**Files:**
- Modify: `.github/workflows/build-exe.yml`

- [ ] **Step 1: Remove push trigger**

Keep only `workflow_dispatch` and `release: published`.

- [ ] **Step 2: Leave release publishing unchanged**

Do not change release asset preparation or `gh release upload`.

### Task 4: README Badge

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add code quality badge**

Add a badge linking to `.github/workflows/code-quality.yml`.

- [ ] **Step 2: Keep build badge**

Keep the existing build badge as release/manual build status.

### Task 5: Verification

**Files:**
- Read: changed files

- [ ] **Step 1: Check workflow text**

Run text searches proving:

- `code-quality.yml` has `push`, `pull_request`, and `workflow_dispatch`;
- `code-quality.yml` has no `upload-artifact`;
- `build-exe.yml` has no `push`.

- [ ] **Step 2: Run tests if Python is available**

Run: `python -m pytest`

Expected in this local session: Python may be unavailable. If so, record the concrete reason.
