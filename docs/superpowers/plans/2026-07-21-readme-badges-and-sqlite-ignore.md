# README Badges and SQLite Ignore Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent local SQLite files from entering Git and expose delivery, release, technology, and build information through README badges.

**Architecture:** `.gitignore` receives focused file patterns for SQLite databases and their standard sidecars. The README keeps its workflow badges and adds dynamic GitHub metadata badges plus static badges whose values are drawn from the version-controlled workflow and requirements files.

**Tech Stack:** Git, GitHub Actions, GitHub Releases, shields.io Markdown badges, Python 3.11–3.14, PyInstaller, PySide6, FastAPI, pytest.

## Global Constraints

- Do not ignore application source, documentation, or generic JSON/Excel files beyond the patterns already present.
- SQLite patterns must cover `.sqlite`, `.sqlite3`, and `.db` databases together with WAL, SHM, rollback-journal, and future hyphenated sidecars.
- README badges must link only to the corresponding GitHub page, workflow, documentation, or requirements file.
- Static badges must match repository-controlled facts: CI uses Python 3.11; the EXE build accepts Python 3.11–3.14; PyInstaller is at least 6.17.

---

### Task 1: Ignore local SQLite data safely

**Files:**
- Modify: `.gitignore:18` (immediately after the existing web-data rules)
- Test: Git's ignore matcher through `git check-ignore --no-index`

**Interfaces:**
- Consumes: Git's `.gitignore` pattern semantics.
- Produces: Ignore coverage for local SQLite databases and their journal/WAL/SHM sidecars in every repository directory.

- [ ] **Step 1: Confirm that SQLite files are not ignored yet**

Run:

```powershell
git check-ignore -v --no-index -- 'app.sqlite' 'app.sqlite-wal' 'app.sqlite-shm' 'app.sqlite-journal' 'data.sqlite3' 'data.sqlite3-wal' 'cache.db' 'cache.db-shm'
```

Expected: exit code `1` and no matching output.

- [ ] **Step 2: Add the SQLite patterns**

Insert this exact block after `web_active_clients.json` in `.gitignore`:

```gitignore
# Local SQLite databases and SQLite sidecar files
*.sqlite
*.sqlite-*
*.sqlite3
*.sqlite3-*
*.db
*.db-*
```

- [ ] **Step 3: Verify all database and sidecar patterns**

Run:

```powershell
git check-ignore -v --no-index -- 'app.sqlite' 'app.sqlite-wal' 'app.sqlite-shm' 'app.sqlite-journal' 'data.sqlite3' 'data.sqlite3-wal' 'cache.db' 'cache.db-shm'
```

Expected: exit code `0`, with each path matched by one of the six new lines.

- [ ] **Step 4: Confirm unrelated project files stay visible to Git**

Run:

```powershell
$paths = @('picorgftp_sql/app.py', 'docs/building-exe.md', 'README.md')
foreach ($path in $paths) {
  git check-ignore -q --no-index -- $path
  if ($LASTEXITCODE -ne 1) { throw "An unrelated project file is ignored: $path" }
}
'Project files are not ignored.'
```

Expected: `Project files are not ignored.`

- [ ] **Step 5: Commit the isolated change**

```powershell
git add -- .gitignore
git commit -m "chore: ignore local SQLite data"
```

### Task 2: Add comprehensive, evidence-based README badges

**Files:**
- Modify: `README.md:5-6` (the existing badge block)
- Test: Markdown source inspection with `rg`

**Interfaces:**
- Consumes: `.github/workflows/ci.yml`, `.github/workflows/build-exe.yml`, all three requirement files, and GitHub repository metadata.
- Produces: A README badge block where every badge has a direct, relevant link.

- [ ] **Step 1: Record the existing workflow badges**

Run:

```powershell
rg -n 'Build Windows EXE|\[!\[CI\]\]' README.md
```

Expected: the existing `Build Windows EXE` and `CI` badges are found once each.

- [ ] **Step 2: Replace the badge block with the complete set**

Keep the two existing workflow badges and append this exact Markdown directly after them:

```markdown
[![Latest release](https://img.shields.io/github/v/release/NefilimPL/PicOrgFTP-SQL?display_name=tag)](https://github.com/NefilimPL/PicOrgFTP-SQL/releases/latest)
[![Release date](https://img.shields.io/github/release-date/NefilimPL/PicOrgFTP-SQL)](https://github.com/NefilimPL/PicOrgFTP-SQL/releases/latest)
[![License](https://img.shields.io/github/license/NefilimPL/PicOrgFTP-SQL)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/NefilimPL/PicOrgFTP-SQL)](https://github.com/NefilimPL/PicOrgFTP-SQL/commits/main)
[![Repository size](https://img.shields.io/github/repo-size/NefilimPL/PicOrgFTP-SQL)](https://github.com/NefilimPL/PicOrgFTP-SQL)
[![Open issues](https://img.shields.io/github/issues/NefilimPL/PicOrgFTP-SQL)](https://github.com/NefilimPL/PicOrgFTP-SQL/issues)
[![Top language](https://img.shields.io/github/languages/top/NefilimPL/PicOrgFTP-SQL)](https://github.com/NefilimPL/PicOrgFTP-SQL)
[![CI Python](https://img.shields.io/badge/CI%20Python-3.11-3776AB?logo=python&logoColor=white)](https://github.com/NefilimPL/PicOrgFTP-SQL/blob/main/.github/workflows/ci.yml)
[![EXE build Python](https://img.shields.io/badge/EXE%20build%20Python-3.11%E2%80%933.14-3776AB?logo=python&logoColor=white)](https://github.com/NefilimPL/PicOrgFTP-SQL/blob/main/.github/workflows/build-exe.yml)
[![Build requirements](https://img.shields.io/badge/build%20requirements-requirements--build.txt-3776AB?logo=python&logoColor=white)](requirements-build.txt)
[![PyInstaller](https://img.shields.io/badge/PyInstaller-%3E%3D%206.17-FF6F00?logo=python&logoColor=white)](requirements-build.txt)
[![PySide6](https://img.shields.io/badge/PySide6-desktop%20UI-41CD52?logo=qt&logoColor=white)](requirements-qt.txt)
[![FastAPI](https://img.shields.io/badge/FastAPI-LAN%20web-009688?logo=fastapi&logoColor=white)](requirements-web.txt)
[![pytest](https://img.shields.io/badge/pytest-test%20suite-0A9EDC?logo=pytest&logoColor=white)](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/ci.yml)
```

- [ ] **Step 3: Check every badge is present exactly once**

Run:

```powershell
$labels = @('Build Windows EXE', 'CI', 'Latest release', 'Release date', 'License', 'Last commit', 'Repository size', 'Open issues', 'Top language', 'CI Python', 'EXE build Python', 'Build requirements', 'PyInstaller', 'PySide6', 'FastAPI', 'pytest')
foreach ($label in $labels) {
  $count = (rg -F -- "[![$label]" README.md | Measure-Object).Count
  if ($count -ne 1) { throw "Badge '$label' occurs $count times." }
}
```

Expected: exit code `0` with no thrown error.

- [ ] **Step 4: Commit the README change**

```powershell
git add -- README.md
git commit -m "docs: expand repository status badges"
```

### Task 3: Validate the final repository state

**Files:**
- Verify: `.gitignore`, `README.md`

**Interfaces:**
- Consumes: the patterns and badge definitions from Tasks 1 and 2.
- Produces: a clean, whitespace-valid patch with confirmed ignore coverage.

- [ ] **Step 1: Run the full targeted verification**

Run:

```powershell
git diff --check HEAD
git check-ignore -v --no-index -- 'app.sqlite' 'app.sqlite-wal' 'app.sqlite-shm' 'app.sqlite-journal' 'data.sqlite3' 'data.sqlite3-wal' 'cache.db' 'cache.db-shm'
rg -n '^\[!\[' README.md
git status --short
```

Expected: no `git diff --check` output; all sample database paths are ignored; the README output contains 16 badge lines; and `git status --short` shows only intentional worktree changes.

- [ ] **Step 2: Review rendered-link targets in source**

Run:

```powershell
rg -n 'github\.com/NefilimPL/PicOrgFTP-SQL|requirements-(build|qt|web)\.txt|\]\(LICENSE\)' README.md
```

Expected: every badge link points to a GitHub resource, a requirement file, or `LICENSE`; no placeholder URLs are present.

- [ ] **Step 3: Commit any remaining verification-only adjustment**

```powershell
git status --short
```

Expected: no further content adjustments are needed. Do not create an empty commit.
