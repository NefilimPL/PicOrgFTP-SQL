# PicSyncra Rebrand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the product, executable entry points and Python package to PicSyncra while safely adopting existing local data and applying the supplied icons.

**Architecture:** The `picsyncra` package owns one brand module for current identifiers and one isolated migration module for historical data discovery. All runtime entry points, web assets and build surfaces consume the current identifiers; the migration module copies legacy data only on first launch and never exposes its identifiers to users.

**Tech Stack:** Python 3.10+, Tkinter, FastAPI, vanilla JavaScript, PowerShell, PyInstaller, pytest, Node.js test runner, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-28-picsyncra-rebrand-design.md`

## Global Constraints

- Public text, new files, artifacts and normal runtime paths use `PicSyncra` / `picsyncra` only.
- Historical-name literals may exist only in the isolated data-migration module and migration test fixtures.
- Data migration is idempotent, never overwrites an existing PicSyncra target, preserves its source copy and copies SQLite WAL/SHM sidecars together.
- Keep existing user-provided untracked icon files outside the three supplied `PIC9_*` assets untouched.
- Replace the runtime and build icons with `PIC9_LOCAL.png`, `PIC9_WEB.png`, and `PIC9_WEB-OCR.png` according to build target.
- Work directly on the current Git branch, as requested by the user.

---

## File Structure

- `picsyncra/brand.py` — canonical product, repository, process, web-client and storage identifiers.
- `picsyncra/legacy_migration.py` — isolated, idempotent discovery and copy of existing application data.
- `picsyncra/` — renamed application package, including desktop services, web backend, static client and browser extension.
- `PicSyncra.pyw`, `PicSyncra-WEB.pyw`, `PicSyncra-QtSlots.pyw` — renamed desktop and web entry points.
- `tests/test_brand.py`, `tests/test_legacy_migration.py`, `tests/test_source_integrity.py` — contract tests for branding, data adoption and elimination of obsolete names.
- Existing tests — imports, file paths, build names, API headers, UI assertions and fixtures updated to PicSyncra.
- `Generator exe/*.ps1`, `.github/workflows/*.yml`, `tools/*`, `START_WEB.bat`, `STOP_WEB.bat` — new executable, process, icon and artifact names.
- `README.md`, `docs/*.md`, project policy documents and browser-extension instructions — current product documentation.

### Task 1: Rename the namespace and entry points

**Files:**
- Rename: `picorgftp_sql/` to `picsyncra/`
- Rename: `PicOrgFTP-SQL.pyw`, `PicOrgFTP-SQL-WEB.pyw`, `PicOrgFTP-SQL-QtSlots.pyw` to their `PicSyncra` equivalents
- Modify: every Python module and test importing the application package
- Modify: `tests/test_desktop_smoke_ci.py`, `tests/test_web_manager.py`, `tests/test_module_boundaries.py`

**Interfaces:**
- Produces: importable `picsyncra` package and three PicSyncra launchers.
- Consumes: all internal modules continue to use their current relative-import boundaries.

- [ ] **Step 1: Write the failing namespace contract test**

```python
def test_current_package_and_launchers_exist():
    assert (ROOT / "picsyncra" / "__init__.py").is_file()
    assert (ROOT / "PicSyncra.pyw").is_file()
    assert (ROOT / "PicSyncra-WEB.pyw").is_file()
    assert (ROOT / "PicSyncra-QtSlots.pyw").is_file()
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `pytest tests/test_desktop_smoke_ci.py::test_current_package_and_launchers_exist -v`

Expected: FAIL because the PicSyncra package and launchers do not yet exist.

- [ ] **Step 3: Rename the package and launchers with Git-aware moves**

```powershell
git mv picorgftp_sql picsyncra
git mv PicOrgFTP-SQL.pyw PicSyncra.pyw
git mv PicOrgFTP-SQL-WEB.pyw PicSyncra-WEB.pyw
git mv PicOrgFTP-SQL-QtSlots.pyw PicSyncra-QtSlots.pyw
```

Update absolute imports, dynamic import strings, monkeypatch paths, test paths and PyInstaller entry-point references to `picsyncra` and the new launchers. Do not change relative imports unnecessarily.

- [ ] **Step 4: Run syntax/import smoke checks**

Run: `pytest tests/test_desktop_smoke_ci.py tests/test_module_boundaries.py -q`

Expected: PASS with imports and file paths using only the new package.

- [ ] **Step 5: Commit the namespace rename**

```bash
git add picsyncra PicSyncra.pyw PicSyncra-WEB.pyw PicSyncra-QtSlots.pyw tests
git commit -m "refactor: rename application namespace to picsyncra"
```

### Task 2: Add canonical brand identifiers and safe data migration

**Files:**
- Create: `picsyncra/brand.py`
- Create: `picsyncra/legacy_migration.py`
- Modify: `picsyncra/bootstrap.py`, `picsyncra/common.py`, `picsyncra/settings.py`, `picsyncra/sqlite_store.py`, `PicSyncra.pyw`
- Create: `tests/test_brand.py`, `tests/test_legacy_migration.py`

**Interfaces:**
- Produces: `brand.APP_NAME`, `brand.WEB_APP_NAME`, `brand.GITHUB_REPOSITORY`, `brand.PACKAGE_NAME`, `brand.CSRF_HEADER`, `brand.CLIENT_ID_HEADER`; `migrate_legacy_data(application_root: Path, data_root: Path) -> MigrationResult`.
- Consumes: `bootstrap.initialize_application_runtime(interactive: bool)` calls the migration before settings and the SQLite store are initialised.

- [ ] **Step 1: Write failing brand and migration tests**

```python
def test_brand_identifiers_are_picsyncra():
    assert brand.APP_NAME == "PicSyncra"
    assert brand.GITHUB_REPOSITORY == "NefilimPL/PicSyncra"
    assert brand.CSRF_HEADER == "X-PicSyncra-CSRF"

def test_migration_copies_database_and_sidecars_once(tmp_path):
    result = migrate_legacy_data(tmp_path, tmp_path)
    assert result.migrated
    assert (tmp_path / "picsyncra.sqlite").exists()
    assert (tmp_path / "picsyncra.sqlite-wal").exists()
    assert (tmp_path / "picsyncra.sqlite-shm").exists()
```

Include cases for source preservation, existing target (skip), a second run (skip), and a copy failure (error result, no partial target).

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_brand.py tests/test_legacy_migration.py -q`

Expected: FAIL because the brand and migration modules do not exist.

- [ ] **Step 3: Implement the current-name and migration modules**

```python
@dataclass(frozen=True)
class MigrationResult:
    migrated: bool
    skipped: bool
    copied_paths: tuple[Path, ...]
    error: str | None = None

def migrate_legacy_data(application_root: Path, data_root: Path) -> MigrationResult:
    """Copy recognised historical data only when no PicSyncra target exists."""
```

Keep historical filenames and browser-key mappings private to `legacy_migration.py`. Copy a SQLite database and its `-wal` / `-shm` siblings to a temporary destination, validate all required copies, then atomically publish targets; delete only temporary targets on error. Wire the call into bootstrap before any config or database path is read.

- [ ] **Step 4: Replace runtime identifiers with brand constants**

Use the brand module for lock files, application titles, default database/log/archive names, GitHub repository status, user-agent and all backend HTTP header names. Rename environment variables and process names to `PICSYNCRA_*`; do not preserve an old runtime alias.

- [ ] **Step 5: Run migration and affected persistence tests**

Run: `pytest tests/test_brand.py tests/test_legacy_migration.py tests/test_config.py tests/test_sqlite_lifecycle.py tests/test_github_status.py -q`

Expected: PASS; migration preserves sources and normal runtime names are PicSyncra.

- [ ] **Step 6: Commit the branding and migration layer**

```bash
git add picsyncra tests/test_brand.py tests/test_legacy_migration.py tests/test_config.py tests/test_sqlite_lifecycle.py tests/test_github_status.py
git commit -m "feat: add PicSyncra branding and data migration"
```

### Task 3: Apply PicSyncra icons and desktop/web-manager branding

**Files:**
- Modify: `picsyncra/assets.py`, `PicSyncra.pyw`, `picsyncra/web_manager.py`, `picsyncra/qt_slots_preview.py`
- Modify: `tests/test_desktop_smoke_ci.py`, `tests/test_web_manager.py`, `tests/test_qt_slots_preview.py`
- Add: `pic/PIC9_LOCAL.png`, `pic/PIC9_WEB.png`, `pic/PIC9_WEB-OCR.png`
- Remove: superseded tracked local and web PNG icons

**Interfaces:**
- Produces: `set_tk_window_icon(window, filename)` loading a PicSyncra-provided asset; all desktop titles and tray identifiers use `brand.APP_NAME` / `brand.WEB_APP_NAME`.
- Consumes: `brand.LOCAL_ICON`, `brand.WEB_ICON`, `brand.WEB_OCR_ICON`.

- [ ] **Step 1: Add failing icon-selection and desktop-title assertions**

```python
def test_desktop_entrypoint_uses_picsyncra_local_icon():
    source = (ROOT / "PicSyncra.pyw").read_text(encoding="utf-8")
    assert 'set_tk_window_icon(app, "PIC9_LOCAL.png")' in source

def test_web_manager_uses_picsyncra_branding():
    assert web_manager.TASK_NAME == "PicSyncra Web"
```

- [ ] **Step 2: Run the focused desktop tests to verify failure**

Run: `pytest tests/test_desktop_smoke_ci.py tests/test_web_manager.py tests/test_qt_slots_preview.py -q`

Expected: FAIL because the previous assets and captions are still referenced.

- [ ] **Step 3: Implement asset and desktop changes**

Set the local desktop icon to `PIC9_LOCAL.png`. Use `PIC9_WEB.png` for the web manager and use `PIC9_WEB-OCR.png` when the EXE build includes OCR. Rename task, firewall, tray, lock and process identifiers with brand constants. Stage only the three supplied `PIC9_*` icon files; leave `PIC5.png` through `PIC8.png` unmodified and untracked.

- [ ] **Step 4: Run the desktop and asset tests**

Run: `pytest tests/test_desktop_smoke_ci.py tests/test_web_manager.py tests/test_qt_slots_preview.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the desktop rebrand**

```bash
git add picsyncra/assets.py picsyncra/web_manager.py picsyncra/qt_slots_preview.py PicSyncra.pyw pic/PIC9_LOCAL.png pic/PIC9_WEB.png pic/PIC9_WEB-OCR.png tests
git rm pic/PIC_LOCAL.png pic/PIC_WEB.png
git commit -m "feat: apply PicSyncra desktop and web icons"
```

### Task 4: Update the web application and browser extension protocol

**Files:**
- Modify: `picsyncra/web/app.py`, `picsyncra/web/active_clients.py`, `picsyncra/web/static/index.html`, `picsyncra/web/static/login.html`, `picsyncra/web/static/app.js`, `picsyncra/web/static/*.js`
- Modify: `picsyncra/browser_extension/manifest.json`, `popup.html`, `popup.js`, `defaults.js`, `background.js`, `README.txt`
- Modify: `tests/test_web_ui_integrity.py`, `tests/test_web_smoke_ci.py`, `tests/test_browser_extension_package.py`, `tests/js/*.test.js`

**Interfaces:**
- Produces: FastAPI title `PicSyncra Web`, client headers from the brand module, JavaScript namespace `window.PicSyncra`, and PicSyncra `localStorage` / browser-extension archive names.
- Consumes: backend and frontend use the same `X-PicSyncra-CSRF` and `X-PicSyncra-Client-Id` protocol identifiers.

- [ ] **Step 1: Write failing client/server branding tests**

```python
def test_web_page_has_picsyncra_title():
    assert "<title>PicSyncra Web</title>" in INDEX_HTML.read_text(encoding="utf-8")

def test_browser_extension_archive_has_picsyncra_name(client):
    response = client.get("/api/browser-extension/download")
    assert 'filename="picsyncra-browser-extension.zip"' in response.headers["content-disposition"]
```

Update JavaScript fixtures to initialise `window.PicSyncra` and assert the renamed header and storage-key strings.

- [ ] **Step 2: Run web and extension tests to verify failure**

Run: `pytest tests/test_web_ui_integrity.py tests/test_browser_extension_package.py tests/test_web_smoke_ci.py -q`

Expected: FAIL on legacy page titles, protocol identifiers and archive names.

- [ ] **Step 3: Implement the web and extension rebrand**

Replace visible branding, web API title, headers, archive root/file names, extension display name and JavaScript global namespace. Update all client and server references together. Have `legacy_migration.py` copy browser preferences from old localStorage keys into PicSyncra keys through a one-time client-side migration function that removes neither source key nor existing PicSyncra values.

- [ ] **Step 4: Run Python and JavaScript web tests**

Run: `pytest tests/test_web_ui_integrity.py tests/test_browser_extension_package.py tests/test_web_smoke_ci.py tests/test_web_manager.py -q`

Run: `node --test tests/js/*.test.js`

Expected: PASS with no protocol mismatch or stale JavaScript namespace.

- [ ] **Step 5: Commit the web rebrand**

```bash
git add picsyncra/web picsyncra/browser_extension tests
git commit -m "feat: rebrand PicSyncra web and extension"
```

### Task 5: Rename build, CI, documentation and release artifacts

**Files:**
- Modify: `Generator exe/build_local_exe.ps1`, `Generator exe/build_web_exe.ps1`, `Generator exe/build_common.ps1`, `Generator exe/disable_ocr_runtime.py`
- Modify: `.github/workflows/build-exe.yml`, `.github/workflows/ci.yml`, `tools/generate_windows_version_info.py`, `tools/generate_module_build_manifest.py`, `tools/web/start_web.ps1`, `tools/web/stop_web.ps1`, `START_WEB.bat`, `STOP_WEB.bat`
- Modify: `.gitignore`
- Modify: `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `docs/building-exe.md`, `docs/local-desktop.md`, `docs/pimcore.md`, `docs/web-panel.md`
- Modify: `tests/test_build_exe_workflow.py`, `tests/test_windows_version_info.py`, `tests/test_web_manager.py`

**Interfaces:**
- Produces: PicSyncra-named EXE files, release files and GitHub artifacts with Windows metadata derived from `GITHUB_REPOSITORY` or `PicSyncra`.
- Consumes: build scripts read `PIC9_LOCAL.png`, `PIC9_WEB.png`, and `PIC9_WEB-OCR.png` consistently with their target flags.

- [ ] **Step 1: Add failing build-artifact and icon contracts**

```python
def test_windows_metadata_defaults_to_picsyncra():
    assert version_info.DEFAULT_PRODUCT_NAME == "PicSyncra"

def test_build_workflow_uses_new_icons_and_executables():
    source = BUILD_WORKFLOW.read_text(encoding="utf-8")
    assert "PIC9_LOCAL.png" in source
    assert "PIC9_WEB-OCR.png" in source
    assert "PicSyncra-WEB.exe" in source
```

- [ ] **Step 2: Run build-oriented tests to verify failure**

Run: `pytest tests/test_build_exe_workflow.py tests/test_windows_version_info.py -q`

Expected: FAIL on old executable names and icon files.

- [ ] **Step 3: Implement build and documentation changes**

Rename every build output, PyInstaller `--name`, Windows file description, internal name, artifact label, release asset and script process marker to PicSyncra. Generate separate standard/OCR web ICO files so both web target variants use their intended source image. Rename ignored PID and log files in `.gitignore`. Change developer and user-facing documentation commands to the new launchers and package name.

- [ ] **Step 4: Run workflow and documentation integrity tests**

Run: `pytest tests/test_build_exe_workflow.py tests/test_windows_version_info.py tests/test_desktop_smoke_ci.py -q`

Expected: PASS with all build and launch references resolving to PicSyncra.

- [ ] **Step 5: Commit build and documentation changes**

```bash
git add "Generator exe" .github tools .gitignore START_WEB.bat STOP_WEB.bat README.md CONTRIBUTING.md CODE_OF_CONDUCT.md docs tests
git commit -m "build: publish PicSyncra artifacts"
```

### Task 6: Enforce source integrity and run the complete verification suite

**Files:**
- Create or modify: `tests/test_source_integrity.py`
- Modify: any remaining current source, test or documentation file identified by the integrity scan

**Interfaces:**
- Produces: a maintainable allowlist for historical internal plans/specs and the isolated migration module; all live source and artifacts reject stale names.

- [ ] **Step 1: Write the failing stale-brand scan**

```python
def test_live_files_do_not_use_obsolete_brand_identifiers():
    offenders = find_obsolete_brand_occurrences(ROOT)
    assert offenders == []
```

Configure `find_obsolete_brand_occurrences` to scan source, tests, workflow files and current documentation. Exclude `.git`, caches, SQLite files, user-created files, pre-existing historical `docs/superpowers` records and the isolated migration module/test fixtures.

- [ ] **Step 2: Run the integrity scan to verify failure**

Run: `pytest tests/test_source_integrity.py -q`

Expected: FAIL listing each remaining live stale identifier.

- [ ] **Step 3: Resolve every reported current occurrence**

Replace stale values by a PicSyncra name or, for historical-data detection, move the literal into the migration module. Do not alter the user’s untracked `PIC5.png` through `PIC8.png` files or application databases.

- [ ] **Step 4: Run complete verification**

Run: `pytest -q`

Run: `node --test tests/js/*.test.js`

Run: `python -m compileall picsyncra PicSyncra.pyw PicSyncra-WEB.pyw PicSyncra-QtSlots.pyw`

Run: `git diff --check`

Expected: every command succeeds with no unexpected changed or deleted user files.

- [ ] **Step 5: Commit verification contracts and remaining corrections**

```bash
git add picsyncra tests .github tools docs README.md CONTRIBUTING.md CODE_OF_CONDUCT.md
git commit -m "test: enforce PicSyncra naming integrity"
```
