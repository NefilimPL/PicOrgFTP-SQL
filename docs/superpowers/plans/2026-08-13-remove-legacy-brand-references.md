# Legacy Brand Reference Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove legacy company-specific URLs and obsolete local review artifacts without changing active integration behavior.

**Architecture:** Pimcore normalization will retain every configured base URL rather than recognizing a historical value. Active tests will use the reserved `.test` domain, while tests tied only to the removed migration and obsolete local artifacts are deleted.

**Tech Stack:** Python, pytest, PowerShell, Git.

## Global Constraints

- Remove the historical company-specific hosts from source and tests.
- Keep active Pimcore integration behavior and replace its test hosts with `pimcore.example.test`.
- Do not modify repository ownership, contributor, license, technology-integration, path-configuration, or Windows Defender discovery code.
- Remove only `.superpowers/sdd` and `REVIEW_WYDAJNOSCI.md`; keep `docs/superpowers`.

---

## File structure

- Modify `picorgftp_sql/pimcore_config.py`: remove legacy URL migration.
- Modify `tests/test_pimcore_config.py`: use neutral fixtures and delete migration-only tests.
- Modify `tests/test_pimcore_web.py`, `tests/test_pimcore_service.py`, and `tests/test_web_ui_integrity.py`: use neutral Pimcore fixtures.
- Modify `tests/test_web_data_users.py`: use a neutral SQL image URL fixture.
- Delete `.superpowers/sdd/`: ignored local task and review archive.
- Delete `REVIEW_WYDAJNOSCI.md`: obsolete review note.

### Task 1: Remove legacy URL migration

**Files:**
- Modify: `picorgftp_sql/pimcore_config.py:30,287-302`
- Modify: `tests/test_pimcore_config.py:11-36,87-99,411-427`

**Interfaces:**
- Consumes: `normalize_pimcore_settings(raw: object) -> dict[str, Any]`.
- Produces: configured `base_url` is normalized structurally but never cleared because it equals a historical host.

- [ ] **Step 1: Write a failing preservation test**

  Replace the first fixture URL in `test_normalize_pimcore_settings_cleans_mappings_and_bounds_timeout` with `http://pimcore.example.test/` and assert the normalized value is `http://pimcore.example.test`.

- [ ] **Step 2: Run the test and verify it fails**

  Run:

  ```powershell
  & 'tmp_pytest\endpoint-verify\Scripts\python.exe' -m pytest tests\test_pimcore_config.py::test_normalize_pimcore_settings_cleans_mappings_and_bounds_timeout -q
  ```

  Expected: FAIL only after the old literal is removed from the fixture before its assertion is updated.

- [ ] **Step 3: Remove the migration and obsolete tests**

  Delete `OLD_EXAMPLE_BASE_URL` and set `settings["base_url"] = raw_base_url`. Delete `test_incomplete_legacy_default_url_is_cleared` and `test_configured_legacy_default_url_is_preserved`, because both test only the removed historical migration. Replace every remaining company-specific fixture in Pimcore tests with `http://pimcore.example.test`.

- [ ] **Step 4: Run Pimcore configuration and service tests**

  Run:

  ```powershell
  & 'tmp_pytest\endpoint-verify\Scripts\python.exe' -m pytest tests\test_pimcore_config.py tests\test_pimcore_service.py tests\test_pimcore_web.py -q
  ```

  Expected: PASS.

- [ ] **Step 5: Commit the migration removal**

  ```powershell
  git add picorgftp_sql/pimcore_config.py tests/test_pimcore_config.py tests/test_pimcore_service.py tests/test_pimcore_web.py tests/test_web_ui_integrity.py
  git commit -m "chore: remove legacy pimcore host migration"
  ```

### Task 2: Remove brand-specific test data and obsolete notes

**Files:**
- Modify: `tests/test_web_data_users.py:631-660`
- Delete: `.superpowers/sdd/`
- Delete: `REVIEW_WYDAJNOSCI.md`

**Interfaces:**
- Consumes: `find_product_photos(...)` SQL-url behavior.
- Produces: neutral fixture URL `https://cdn.example.test/img/5901234567890_03.jpg` with unchanged expected photo semantics.

- [ ] **Step 1: Update the active SQL URL fixture**

  Replace both occurrences of the company-specific image URL in the existing photo test with `https://cdn.example.test/img/5901234567890_03.jpg`.

- [ ] **Step 2: Run the focused photo test**

  Run:

  ```powershell
  & 'tmp_pytest\endpoint-verify\Scripts\python.exe' -m pytest tests\test_web_data_users.py -k "find_product_photos" -q
  ```

  Expected: PASS.

- [ ] **Step 3: Delete requested obsolete artifacts**

  Delete exactly `.superpowers/sdd` and `REVIEW_WYDAJNOSCI.md`. Do not remove `.superpowers` itself or anything under `docs/superpowers`.

- [ ] **Step 4: Verify literal absence and affected tests**

  Run:

  ```powershell
  Search `picorgftp_sql` and `tests` for the removed company-specific hosts.
  & 'tmp_pytest\endpoint-verify\Scripts\python.exe' -m pytest tests\test_web_data_users.py tests\test_web_ui_integrity.py -q
  ```

  Expected: `rg` has exit code 1 with no matches; pytest passes.

- [ ] **Step 5: Commit cleanup**

  ```powershell
  git add -u REVIEW_WYDAJNOSCI.md
  git add tests/test_web_data_users.py
  git commit -m "chore: remove legacy brand references"
  ```

### Task 3: Verify the complete affected surface

**Files:**
- Verify: `picorgftp_sql/pimcore_config.py`
- Verify: `tests/test_pimcore_config.py`
- Verify: `tests/test_pimcore_service.py`
- Verify: `tests/test_pimcore_web.py`
- Verify: `tests/test_web_data_users.py`
- Verify: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Run all directly affected tests**

  Run:

  ```powershell
  & 'tmp_pytest\endpoint-verify\Scripts\python.exe' -m pytest tests\test_pimcore_config.py tests\test_pimcore_service.py tests\test_pimcore_web.py tests\test_web_data_users.py tests\test_web_ui_integrity.py -q
  ```

  Expected: PASS.

- [ ] **Step 2: Inspect final scope**

  Run:

  ```powershell
  git diff HEAD~2..HEAD -- picorgftp_sql/pimcore_config.py tests REVIEW_WYDAJNOSCI.md
  Search `picorgftp_sql` and `tests` for the removed company-specific hosts.
  ```

  Confirm no removed literal remains and no active integration behavior was deleted.
