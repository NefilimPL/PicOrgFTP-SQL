# Offline Legacy SQLite Migrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dostarczyć osobny migrator GUI/EXE, który przekształca wyłącznie
konfigurowaną bazę `picorgftp_sql.sqlite` w `picsyncra.sqlite`, a po udanej
aktywacji przenosi źródłowy zestaw SQLite do BACKUP, bez działania wewnątrz
serwera WEB.

**Architecture:** Czysty moduł domenowy otrzymuje jawne ścieżki pliku
ustawień, źródła i celu; wykonuje kopię SQLite, aktualizację schematu,
walidację i atomową aktywację. Moduł sterowania procesem pracuje wyłącznie na
zweryfikowanych PID-ach spod katalogu aplikacji. Tkinter GUI jest cienką
warstwą uruchamiającą migrację w wątku i wyświetlającą zdarzenia postępu.

**Tech Stack:** Python 3, SQLite stdlib, Tkinter/ttk, ctypes/subprocess Windows,
PyInstaller, pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-offline-legacy-sqlite-migrator-design.md`

## Global Constraints

- Źródło wybiera wyłącznie `local_settings.json` głównej aplikacji; nie wolno
  przeszukiwać katalogów ani używać nazwy `Nowy folder`.
- Źródło musi mieć dokładną nazwę `picorgftp_sql.sqlite`; JSON/XLSX i inne
  pliki legacy nie uczestniczą w migracji.
- Przed udaną aktywacją nigdy nie modyfikować, archiwizować ani usuwać źródła
  wraz z `-wal`/`-shm`; po niej przenosić wyłącznie ten zestaw do BACKUP.
- Nie nadpisywać istniejącego `picsyncra.sqlite`.
- Nie kończyć ogólnych procesów Python ani procesów spoza katalogu aplikacji.
- Raporty i komunikaty nie mogą ujawniać sekretów ani hashy haseł.
- Po udanej aktywacji przenosić wyłącznie migrowany zestaw SQLite do
  `BACKUP/legacy-import`, a usuwać również katalogi robocze utworzone przez
  migrator.

---

### Task 1: Jawne odczytanie konfiguracji i preflight źródła

**Files:**
- Create: `picsyncra/offline_legacy_sqlite_migrator.py`
- Modify: `picsyncra/storage_settings.py`
- Create: `tests/test_offline_legacy_sqlite_migrator.py`

**Interfaces:**
- Produces `MigrationPaths(app_root: Path, settings_path: Path, source: Path, target: Path)`.
- Produces `resolve_offline_migration_paths(app_root: Path) -> MigrationPaths`.
- Produces `OfflineMigrationError(code: str, message: str)`.
- Produces `update_bootstrap_settings_file(settings_path: Path, updates: dict[str, object]) -> dict[str, Any]`.

- [ ] **Step 1: Write the failing source-selection tests**

```python
def test_resolve_paths_reads_only_the_database_referenced_by_local_settings(tmp_path: Path):
    app_root = tmp_path / "application"
    source_root = tmp_path / "current-legacy"
    stale_root = tmp_path / "stale-legacy"
    app_root.mkdir(); source_root.mkdir(); stale_root.mkdir()
    source = source_root / "picorgftp_sql.sqlite"
    SqliteStore(str(source)).initialize()
    SqliteStore(str(stale_root / "picorgftp_sql.sqlite")).initialize()
    (app_root / "local_settings.json").write_text(json.dumps({
        "database_location_mode": "custom", "database_path": str(source)
    }), encoding="utf-8")

    paths = resolve_offline_migration_paths(app_root)

    assert paths.source == source.resolve()
    assert paths.target == source_root / "picsyncra.sqlite"
```

Add tests that missing configuration, a configured path with a different
filename, a missing source and an existing target raise `OfflineMigrationError`
without inspecting sibling directories.

Add a regression case for an actual pre-rebrand payload containing
`database_location_mode="exe_dir"` and `database_path` pointing at
`picorgftp_sql.sqlite`: the explicit legacy path must win.  This preserves the
source selected by the old application's configuration instead of deriving the
new default filename (`picsyncra.sqlite`).

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_offline_legacy_sqlite_migrator.py -q`

Expected: FAIL because `resolve_offline_migration_paths` does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement `storage_settings.load_bootstrap_settings_file(settings_path)`,
`resolve_sqlite_path_for_settings_file(settings_path, payload)` and
`update_bootstrap_settings_file`. Reuse existing normalizers and the
temporary-file + `os.replace` write pattern. For `exe_dir`, resolve relative
to `settings_path.parent`, never the process-global settings object.  The
offline source resolver must first honour a nonempty `database_path` only when
its resolved basename is exactly `picorgftp_sql.sqlite`; otherwise it applies
the configured location mode and then requires that same basename.

Implement preflight in the new migrator module: read only
`app_root / "local_settings.json"`, require exact basename
`picorgftp_sql.sqlite`, require a read-only `PRAGMA integrity_check` of `ok`,
and derive a non-existent sibling target named `picsyncra.sqlite`. Do not call
legacy profile discovery or `legacy_import`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_offline_legacy_sqlite_migrator.py tests/test_storage_settings.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picsyncra/offline_legacy_sqlite_migrator.py picsyncra/storage_settings.py tests/test_offline_legacy_sqlite_migrator.py
git commit -m "feat: resolve configured legacy SQLite source offline"
```

### Task 2: Bezpieczne rozpoznanie i zatrzymanie procesu aplikacji

**Files:**
- Create: `picsyncra/offline_migrator_processes.py`
- Create: `tests/test_offline_migrator_processes.py`

**Interfaces:**
- Produces `ManagedProcess(pid: int, executable: Path)`.
- Produces `find_managed_processes(app_root: Path) -> tuple[ManagedProcess, ...]`.
- Produces `stop_managed_processes(app_root: Path, notify: Callable[[str], None]) -> None`.

- [ ] **Step 1: Write the failing process-boundary tests**

```python
def test_stop_refuses_a_matching_name_outside_the_selected_application_root(tmp_path: Path):
    app_root = tmp_path / "application"; app_root.mkdir()
    foreign = tmp_path / "other" / "PicSyncra-WEB.exe"; foreign.parent.mkdir()
    terminated = []

    stop_managed_processes(
        app_root,
        notify=lambda _event: None,
        list_processes=lambda: (ManagedProcess(123, foreign),),
        terminate_process=lambda process, _force: terminated.append(process.pid),
    )

    assert terminated == []
```

Add a passing test for a verified executable directly in `app_root`, and a
test where a process cannot be verified: it must remain running and return a
safe `OfflineMigrationError`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_offline_migrator_processes.py -q`

Expected: FAIL because the process-control module is absent.

- [ ] **Step 3: Write minimal implementation**

Read only PID metadata and known WEB-port records, obtain each candidate image
path, normalize it, and accept it only when it is a descendant of `app_root`
and its filename starts with `PicSyncra` or `PicOrgFTP`. Attempt graceful
termination, poll PID/port release, and force only the same verified PID. Do
not select a process merely because its image is `python.exe`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_offline_migrator_processes.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picsyncra/offline_migrator_processes.py tests/test_offline_migrator_processes.py
git commit -m "feat: stop only verified application processes during migration"
```

### Task 3: Kopia, migracja schematu i pełna walidacja SQLite

**Files:**
- Modify: `picsyncra/offline_legacy_sqlite_migrator.py`
- Modify: `tests/test_offline_legacy_sqlite_migrator.py`

**Interfaces:**
- Produces `MigrationProgress(stage: str, current: int | None, total: int | None, message: str)`.
- Produces `OfflineMigrationReport(source: Path, target: Path, table_counts: dict[str, int], product_count: int, user_count: int)`.
- Produces `build_validated_legacy_sqlite_copy(paths: MigrationPaths, progress: Callable[[MigrationProgress], None]) -> tuple[Path, OfflineMigrationReport]`.

- [ ] **Step 1: Write the failing SQLite-only end-to-end test**

```python
def test_build_validated_copy_preserves_sqlite_without_reading_json_or_xlsx(tmp_path: Path):
    paths = configured_legacy_paths(tmp_path, products=2, users=1)
    (paths.source.parent / "web_users.json").write_text("not valid JSON", encoding="utf-8")
    (paths.source.parent / "lists.xlsx").write_bytes(b"not an xlsx")

    staging, report = build_validated_legacy_sqlite_copy(paths, progress_events.append)

    assert staging.is_file()
    assert report.product_count == 2
    assert report.user_count == 1
```

Add a failing test with schema v15 and all three
`picorg_product_short_grams` triggers; assert schema v17 has no old trigger
and has the three `picsyncra_product_short_grams` triggers. Add a test that
source bytes and source sidecars remain unchanged.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_offline_legacy_sqlite_migrator.py -q`

Expected: FAIL because the copy/migration API is missing.

- [ ] **Step 3: Write minimal implementation**

Create a temporary directory under `paths.target.parent`. Copy source using
`sqlite3.Connection.backup` from a read-only source connection. Record row
counts for every source application table before schema initialization. Open
only staging through `SqliteStore(...).initialize()` so rebrand schema
migrations run on the copy. Emit progress before/after backup, schema
migration and table validation.

Validate integrity, compare every source table still present in staging by row
count, compare `product_entries` count and stable product identifiers, and
compare every `web_users` record by username, role, enabled flag and password
hash. Reject on any mismatch. Build a report containing only public paths and
table counts.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_offline_legacy_sqlite_migrator.py tests/test_sqlite_store.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picsyncra/offline_legacy_sqlite_migrator.py tests/test_offline_legacy_sqlite_migrator.py
git commit -m "feat: stage and validate legacy SQLite rebrand migration"
```

### Task 4: Atomowa aktywacja konfiguracji bez aktywnego backendu

**Files:**
- Modify: `picsyncra/offline_legacy_sqlite_migrator.py`
- Modify: `tests/test_offline_legacy_sqlite_migrator.py`

**Interfaces:**
- Produces `run_offline_legacy_migration(app_root: Path, progress: Callable[[MigrationProgress], None]) -> OfflineMigrationReport`.
- Consumes `stop_managed_processes`, `build_validated_legacy_sqlite_copy` and `update_bootstrap_settings_file`.

- [ ] **Step 1: Write the failing activation and rollback tests**

```python
def test_successful_offline_migration_publishes_target_and_switches_only_local_settings(tmp_path: Path):
    paths = configured_legacy_paths(tmp_path, products=2, users=1)
    before_source = paths.source.read_bytes()

    report = run_offline_legacy_migration(paths.app_root, progress=lambda _event: None)

    assert report.target == paths.target
    assert paths.target.is_file()
    assert paths.source.read_bytes() == before_source
    settings = json.loads(paths.settings_path.read_text(encoding="utf-8"))
    assert settings["database_path"] == str(paths.target)
    assert settings["data_mode"] == "sqlite"
```

Add a test that an existing target blocks before source access, and a test
that a settings-write failure removes only the newly published target while
keeping original settings and source untouched.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_offline_legacy_sqlite_migrator.py -q`

Expected: FAIL because the orchestration API is missing.

- [ ] **Step 3: Write minimal implementation**

Run process shutdown only after preflight and before copying. Publish staging
with `os.replace` only when target does not exist; update the explicit
settings file atomically with `data_mode=sqlite`,
`database_location_mode=custom`, and the published path. If settings update
raises, remove only the new target and restore captured setting bytes. Always
remove the tool-created temporary directory after SQLite connections close.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_offline_legacy_sqlite_migrator.py tests/test_storage_settings.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picsyncra/offline_legacy_sqlite_migrator.py tests/test_offline_legacy_sqlite_migrator.py
git commit -m "feat: activate offline migrated SQLite atomically"
```

### Task 5: GUI, entry point and progress reporting

**Files:**
- Create: `picsyncra/offline_migrator_gui.py`
- Create: `PicSyncra-Migrator.pyw`
- Create: `tests/test_offline_migrator_gui.py`

**Interfaces:**
- Produces `OfflineMigratorWindow` and `OfflineMigratorController`.
- Consumes `run_offline_legacy_migration` and `MigrationProgress`.

- [ ] **Step 1: Write the failing GUI-controller tests**

```python
def test_controller_schedules_progress_without_updating_tk_from_worker_thread():
    scheduler = RecordingScheduler()
    controller = OfflineMigratorController(scheduler.after)

    controller.receive_progress(MigrationProgress("copy", 10, 100, "Kopia SQLite"))

    assert scheduler.callbacks
```

Add a test that final success exposes only target path and public counts, and
a failure displays only the safe error message.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_offline_migrator_gui.py -q`

Expected: FAIL because the GUI controller is missing.

- [ ] **Step 3: Write minimal implementation**

Create a Tkinter window with application-directory field, browse action,
read-only source/target confirmation labels, explicit `Rozpocznij migrację`
button, `ttk.Progressbar`, stage label and report area. Run the migration in a
worker thread; deliver widget updates through `after`. Require a second
confirmation after preflight has displayed source and target. Do not launch
the main EXE after success; show a short completion dialog.

- [ ] **Step 4: Add the frozen entry point and verify green**

`PicSyncra-Migrator.pyw` must call `multiprocessing.freeze_support()` before
`picsyncra.offline_migrator_gui.main()`.

Run: `python -m pytest tests/test_offline_migrator_gui.py tests/test_offline_legacy_sqlite_migrator.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add picsyncra/offline_migrator_gui.py PicSyncra-Migrator.pyw tests/test_offline_migrator_gui.py
git commit -m "feat: add offline legacy SQLite migrator GUI"
```

### Task 6: Pakowanie migratora i wycofanie ryzykownej akcji WEB

**Files:**
- Create: `Generator exe/build_migrator_exe.ps1`
- Create: `Generator exe/BUILD_MIGRATOR_EXE.bat`
- Modify: `Generator exe/build_all_exe.ps1`
- Modify: `picsyncra/web/app.py`
- Modify: `picsyncra/web/static/app.js`
- Modify: `picsyncra/app.py`
- Modify: `tests/test_build_exe_workflow.py`
- Modify: `tests/test_legacy_profile_import.py`
- Modify: `tests/test_web_smoke_ci.py`

**Interfaces:** Produces `Generator exe/PicSyncra-Migrator.exe` and removes
live WEB/desktop access to `adopt_legacy_profile` in favor of the standalone
migrator.

- [ ] **Step 1: Write failing packaging and deprecation tests**

```python
def test_migrator_build_is_a_onefile_gui_artifact():
    source = MIGRATOR_BUILD.read_text(encoding="utf-8")
    assert "--name PicSyncra-Migrator" in source
    assert "--noconsole" in source
    assert "PicSyncra-Migrator.pyw" in source

def test_live_web_import_route_is_not_available():
    assert "/api/settings/import-legacy" not in web_app_source()
```

Add a static desktop test that settings UI opens no legacy-adoption
transaction and instead explains that migration must use the separate tool.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_exe_workflow.py tests/test_legacy_profile_import.py tests/test_web_smoke_ci.py -q`

Expected: FAIL because migrator build files and deprecation changes are absent.

- [ ] **Step 3: Write minimal implementation**

Follow `build_local_exe.ps1` packaging conventions, use the existing web icon,
collect required `picsyncra` modules, and include the artifact in
`build_all_exe.ps1`. Remove the WEB route and UI handler that invoke the old
profile transaction; replace desktop/web help text with a path to
`PicSyncra-Migrator.exe`.

- [ ] **Step 4: Run focused tests and build artifact**

Run: `python -m pytest tests/test_build_exe_workflow.py tests/test_legacy_profile_import.py tests/test_web_smoke_ci.py -q`

Run: `& 'Generator exe\\build_migrator_exe.ps1'`

Expected: tests PASS and `Generator exe/PicSyncra-Migrator.exe` exists.

- [ ] **Step 5: Commit**

```powershell
git add "Generator exe" picsyncra/app.py picsyncra/web/app.py picsyncra/web/static/app.js tests/test_build_exe_workflow.py tests/test_legacy_profile_import.py tests/test_web_smoke_ci.py
git commit -m "feat: ship offline legacy SQLite migrator"
```

### Task 7: Pełna weryfikacja i sprzątnięcie danych testowych

**Files:**
- Modify only test files if verification exposes a missing regression.
- Remove: `Generator exe/Recovered profile 2026-09-01 1034` after all migration verification succeeds.

- [ ] **Step 1: Run all migration-focused and build tests**

Run:
`python -m pytest tests/test_offline_legacy_sqlite_migrator.py tests/test_offline_migrator_processes.py tests/test_offline_migrator_gui.py tests/test_sqlite_store.py tests/test_storage_settings.py tests/test_build_exe_workflow.py tests/test_web_smoke_ci.py -q`

Expected: PASS.

- [ ] **Step 2: Run full suite and compile changed modules**

Run: `python -m pytest -q`

Run: `python -m py_compile picsyncra/offline_legacy_sqlite_migrator.py picsyncra/offline_migrator_processes.py picsyncra/offline_migrator_gui.py PicSyncra-Migrator.pyw`

Expected: PASS; any pre-existing platform-specific failures must be reported
separately from this migration work.

- [ ] **Step 3: Delete only the explicitly approved recovery directory**

Verify the resolved absolute target is exactly
`C:\\_GitHub_\\PicOrgFTP-SQL\\Generator exe\\Recovered profile 2026-09-01 1034`.
Then remove that directory. Do not remove `Generator exe\\Nowy folder`, its
contents, or any other user-created data directory.

- [ ] **Step 4: Final checks**

Run: `git diff --check`

Run: `git status --short`

Run: `Get-FileHash -Algorithm SHA256 'Generator exe\\PicSyncra-Migrator.exe'`

Record test output and artifact hash in the handoff.

- [ ] **Step 5: Commit final test corrections if any**

```powershell
git add tests/test_offline_legacy_sqlite_migrator.py tests/test_offline_migrator_processes.py tests/test_offline_migrator_gui.py
git commit -m "test: cover offline legacy SQLite migrator regressions"
```
