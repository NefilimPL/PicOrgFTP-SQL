# Offline migration of PicOrgFTP-SQL profiles — implementation plan

> **For Codex:** Use the `superpowers:executing-plans` skill to execute this plan task by task.

**Goal:** Move migration of a legacy PicOrgFTP-SQL profile out of PicSyncra web and desktop UI into `PicSyncra-Migrator`, while retaining both existing database backend choices.

**Architecture:** Add an offline adapter that validates an explicitly selected legacy-profile directory, resolves the selected PicSyncra target database, and delegates the atomic import/archive operation to `adopt_legacy_profile`. Extend the standalone migrator UI with an explicit mode selector. Delete the web API, web controls, desktop action, and their behavioral tests.

**Tech stack:** Python 3.11, Tkinter, FastAPI, SQLite, pytest, JavaScript.

## Global constraints

- Work only on branch `feat/offline-legacy-profile-migrator` in its dedicated worktree.
- Write a failing behavioral test before every production behavior change, then make it pass.
- Never infer a source path from a web request. The standalone migrator must require a user-selected source directory.
- Preserve the SQLite/legacy database backend selection in PicSyncra settings.
- Reject every existing target database before starting profile migration, including an empty file.

## Task 1: Create the offline legacy-profile migration adapter

**Files:**
- Create: `picsyncra/offline_legacy_profile_migrator.py`
- Modify: `picsyncra/storage_settings.py`
- Modify: `picsyncra/offline_legacy_sqlite_migrator.py`
- Create: `tests/test_offline_legacy_profile_migrator.py`

1. Add tests that build a minimal legacy profile and target application configuration. Cover path resolution, successful `LEGACY` → PicSyncra SQLite import, profile report, existing-target rejection, and rollback of `local_settings.json` if activation fails.
2. Run the focused test module and confirm it fails because the new adapter does not exist.
3. Add a public `restore_bootstrap_settings_file()` helper in `storage_settings`, using the existing atomic-write primitive. Refactor the existing offline SQLite migrator to use it.
4. Implement `OfflineLegacyProfilePaths`, `OfflineLegacyProfileReport`, path validation, confirmation data, and `run_offline_legacy_profile_migration()`.
5. Reuse `load_legacy_profile()` and `adopt_legacy_profile()`; do not reimplement profile import or archive behavior. Pass the current settings file as a preserved source path when source and target app root coincide.
6. Run `tests/test_offline_legacy_profile_migrator.py` and the existing offline SQLite migrator tests.

## Task 2: Add the second mode to the standalone migrator UI

**Files:**
- Modify: `picsyncra/offline_migrator_gui.py`
- Modify: `tests/test_offline_migrator_gui.py`

1. Add failing controller/message tests for the legacy-profile mode, including a confirmation that shows source directory, SQLite target, and archive location.
2. Run the GUI test module and confirm the new tests fail.
3. Add a mode selector with exactly these choices:
   - `picorgftp_sql.sqlite` → `picsyncra.sqlite`
   - `LEGACY` → SQLite PicSyncra
4. Show the legacy source-directory selector only for the second mode. Route validation, confirmation, worker execution, progress, and success reporting to the selected adapter.
5. Run the GUI tests and both offline migration test modules.

## Task 3: Remove embedded migration entry points and CodeQL data flow

**Files:**
- Modify: `picsyncra/web/app.py`
- Modify: `picsyncra/web/static/app.js`
- Modify: `picsyncra/app.py`
- Modify: `tests/test_web_smoke_ci.py`
- Modify: `tests/test_legacy_profile_import.py`

1. Replace current endpoint expectations with a failing test that posts to `/api/settings/import-legacy` and expects `404`, while the database-mode settings tests remain intact.
2. Run that test and confirm it fails against the current route.
3. Delete the web endpoint and imports used exclusively by it.
4. Delete the web setting field/button/function for selecting and loading the old configuration folder.
5. Delete the desktop “adopt legacy data” action, its button, and associated enable/disable handling. Keep the SQLite/legacy database mode controls.
6. Remove obsolete implementation-detail tests and update the declared web route list.
7. Run affected web, legacy-profile, and UI test modules. Search source to ensure `/api/settings/import-legacy` and `source_directory` no longer appear in web-facing code.

## Task 4: Verify, commit, and publish

**Files:**
- Modify: `docs/superpowers/plans/2026-09-03-offline-migrator-profile-import.md` only if execution reveals a necessary correction.

1. Run `python -m py_compile` for changed Python modules.
2. Run focused pytest modules, then the full suite with an isolated pytest base temporary directory.
3. Run `git diff --check`, inspect the diff and `git status --short` for unintended files.
4. Commit the plan and implementation with clear Conventional Commit messages.
5. Push `feat/offline-legacy-profile-migrator` to `origin` and report the branch link and verification outcome.
