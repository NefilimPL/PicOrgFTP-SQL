# Legacy Profile Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the heuristic rebrand importer with a transactional importer for one complete legacy profile.

**Architecture:** A profile scanner owns discovery and accepts files from one directory only. A transaction builds and validates a new SQLite before publication, then archives and removes that exact profile. Desktop and web adapters activate the result once.

**Tech Stack:** Python 3, SQLite, openpyxl, pytest, FastAPI, Tkinter.

**Spec:** `docs/superpowers/specs/2026-09-01-legacy-profile-import-design.md`

## Global Constraints

- Never combine files from different source directories.
- Never log or return password hashes or secrets.
- Activate a target only after import validation and an archive copy succeed.
- Leave pending cleanup state only inside `BACKUP`.

---

### Task 1: Source profile scanner

**Files:** Create `picsyncra/legacy_profile.py`; test `tests/test_legacy_profile.py`.

**Interfaces:** Produces `LegacyProfile`, `LegacyProfileManifest`,
`discover_legacy_profiles`, `load_legacy_profile`.

- [ ] Write a failing real-files test for one complete profile and two separate candidate roots.
- [ ] Run it and confirm profile discovery is missing.
- [ ] Implement direct-child scanning with no cross-root fallback.
- [ ] Run the test and verify every selected source belongs to one root.

### Task 2: Staged importer and semantic validation

**Files:** Create `picsyncra/legacy_profile_import.py`; modify
`picsyncra/legacy_import.py`; test `tests/test_legacy_profile_import.py`.

**Interfaces:** Consumes `LegacyProfile`; produces a validated staged SQLite and
public component counts.

- [ ] Write a failing integration test: old SQLite has no users but JSON has an admin with a valid old password.
- [ ] Run it and confirm the transaction API is missing.
- [ ] Build staging, merge data, and validate account identity, role, enabled flag, and password hash.
- [ ] Add real-data tests for config, lists, history, index, and invalid account input.
- [ ] Run focused tests and verify staging is returned only after validation.

### Task 3: Publish/archive transaction

**Files:** Modify `picsyncra/legacy_migration.py`, `picsyncra/bootstrap.py`, and
`tests/test_legacy_migration.py`.

**Interfaces:** Produces `adopt_legacy_profile`; keeps `adopt_legacy_data` as a
single-profile compatibility adapter and retires automatic `migrate_legacy_data`.

- [ ] Write failing tests for validation rollback and complete profile archiving.
- [ ] Run them against the old heuristic flow.
- [ ] Replace source discovery and publication with the profile transaction.
- [ ] Verify rollback preserves source/settings and success empties the source root.

### Task 4: Activation adapters

**Files:** Modify `picsyncra/app.py`, `picsyncra/web/app.py`,
`picsyncra/web/static/app.js`, `tests/test_web_smoke_ci.py`.

**Interfaces:** Desktop uses one detected profile or selects a source directory;
web accepts an optional path and otherwise allows exactly one profile.

- [ ] Write failing route tests for report response and ambiguous profile errors.
- [ ] Run them and confirm the new contract is absent.
- [ ] Activate once, reset data cache, clear only obsolete session, and show counts.
- [ ] Verify imported accounts work without restarting.

### Task 5: Verification

**Files:** Modify the profile-import and migration tests only as required.

- [ ] Cover SQLite-only, file-only, combined, custom-path, locked cleanup, and ambiguous profiles.
- [ ] Run focused suites, compile changed modules, and check the diff.
