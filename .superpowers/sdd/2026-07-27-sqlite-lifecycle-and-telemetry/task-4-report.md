# Task 4 report — SQLite store invalidation

## Changes

- Added `invalidate_sqlite_store(database_path=None)` under the shared registry `RLock`; a targeted call removes only that canonical SQLite store and clears the active adapter only when it targets the active path.
- `save_bootstrap_settings` uses a local import and resets the active cache only after `write_text` completes.
- Successful restore and repair invalidate their affected path after the completed file/database mutation. Failed restore, failed repair, and failed settings writes retain the cached store.
- Removed unconditional endpoint cache resets after repair/restore: success is now handled by the lower mutation layer and failed repair keeps the cache intact.
- The web shutdown hook clears the store registry after stopping runtime components.

The `web/app.py` and `tests/test_observability_api.py` changes are an intentional, minimal expansion beyond the brief's file table: the binding specification requires failure-safe API paths and application-close invalidation.

## TDD (RED → GREEN)

1. `test_invalidate_sqlite_store_replaces_only_target`
   - RED: import failed because `invalidate_sqlite_store` did not exist.
   - GREEN: targeted invalidation creates a new target instance while retaining the other instance.
2. `test_restore_backup_invalidates_the_replaced_store`
   - RED: the store object remained identical after restore.
   - GREEN: restore invalidates only after `os.replace` succeeds.
3. `test_repair_invalidates_the_mutated_store`
   - RED: the store object remained identical after repair.
   - GREEN: repair invalidates after its successful mutation sequence.
4. `test_successful_storage_settings_change_resets_store_cache`
   - RED: changing persisted storage settings retained the old store registry entry.
   - GREEN: successful bootstrap write resets the cache.
5. `test_failed_sqlite_repair_api_preserves_the_cached_store`
   - RED: the endpoint's unconditional reset replaced the cached store after an `ok=False` repair result.
   - GREEN: endpoint delegates invalidation to the lower layer and keeps the failed-repair cache.
6. `test_resource_monitor_lifecycle_runs_once_and_in_runtime_order`
   - RED: closing the application retained the registered SQLite store.
   - GREEN: shutdown clears the registry.

Regression tests also cover failed restore, failed repair, failed settings write, successful repair API invalidation, and targeted invalidation retaining an unrelated path.

## Verification

The environment's `python` alias was inaccessible and system `C:\Python314\python.exe` requires `PYTHONHOME=C:\Users\k.bober\AppData\Local\Programs\Python\Python314`. All commands below used that environment prefix.

```text
python -m pytest tests/test_sqlite_lifecycle.py::test_invalidate_sqlite_store_replaces_only_target -v
RED: ImportError: cannot import name 'invalidate_sqlite_store'

python -m pytest tests/test_sqlite_backup.py::test_restore_backup_invalidates_the_replaced_store -v
RED: assertion failed; stale store instance remained cached

python -m pytest tests/test_sqlite_maintenance.py::test_repair_invalidates_the_mutated_store -v
RED: assertion failed; stale store instance remained cached

python -m pytest tests/test_sqlite_lifecycle.py::test_successful_storage_settings_change_resets_store_cache -v
RED: assertion failed; old store registry entry remained cached

python -m pytest tests/test_observability_api.py::test_failed_sqlite_repair_api_preserves_the_cached_store -v
RED: assertion failed; endpoint reset replaced the cached store

python -m pytest tests/test_observability_api.py::test_resource_monitor_lifecycle_runs_once_and_in_runtime_order -v
RED: assertion failed; shutdown retained the registered store

python -m pytest tests/test_sqlite_lifecycle.py tests/test_sqlite_backup.py tests/test_sqlite_maintenance.py tests/test_observability_api.py -q --basetemp=pytest-temp\task4-final
82 passed, 9 warnings in 28.56s

git diff --check
exit 0 (no whitespace errors)
```

## Files

- `picorgftp_sql/data_store.py`
- `picorgftp_sql/storage_settings.py`
- `picorgftp_sql/sqlite_backup.py`
- `picorgftp_sql/sqlite_maintenance.py`
- `picorgftp_sql/web/app.py`
- `tests/test_sqlite_lifecycle.py`
- `tests/test_sqlite_backup.py`
- `tests/test_sqlite_maintenance.py`
- `tests/test_observability_api.py`

## Self-review and concerns

- Reviewed lock usage: all registry mutations occur under `_STORE_REGISTRY_LOCK`; invalidation is called only after success points, avoiding a cache discard on failed writes/mutations.
- Reviewed imports: the storage-settings reset import is local to avoid the `storage_settings -> data_store -> storage_settings` cycle.
- `git diff --check` is clean. `black --check` could not run because Black is not installed in this environment.
- The final test run reports only existing FastAPI/TestClient deprecation warnings (9 warnings); no test failures.
