# SQLite Maintenance, SQL Defaults, and Backups Design

## Goal

Make the web panel safer and more maintainable by removing hard-coded default
login and SQL query values, documenting supported SQL placeholders, upgrading
SQLite storage to the current data rules, and adding repair plus backup,
history, restore, and diff controls for the active SQLite database.

## Current State

- The web login page hard-codes `admin` into the username input.
- `common.py` defines a default SQL update template containing a concrete URL
  and table name. `config.py`, `app.py`, `web/app.py`, and
  `services/sql_service.py` also fall back to that template when the saved query
  is empty.
- The web settings SQL tab contains the SQL query field and a SQL connection
  test, but it does not show the placeholders available to a custom query.
- SQLite mode exists and stores configuration, slots, lists, product entries,
  web users, web history, and local file index cache.
- SQLite timestamps are mixed. Some columns already use ISO UTC text, while
  `web_history.ts` is numeric and file index snapshots store `generated_at` as
  `time.time()` floats.
- The local file index cache is currently stored as one snapshot payload. This
  works, but a large index forces broad reads instead of segmented lookup.
- Legacy import exists as `/api/settings/import-legacy`. There is no database
  repair action, backup schedule, backup history, restore flow, or backup diff.

## Scope

This design covers both the web panel and shared backend modules used by web and
desktop code. Repair, backup, restore, and diff apply to the active SQLite
database file only. Legacy files remain supported as an import source and are
not deleted or rewritten by repair or backup features.

The implementation must preserve existing user data in SQLite and legacy files.
It may change future defaults and migrate stored SQLite records to the new
schema, but it must not erase saved SQL queries, saved credentials, users,
history, product entries, list values, slots, or file index cache as part of
normal startup, repair, backup, or restore.

## Decisions

- The login page stores the last successful username in browser `localStorage`.
  The username field starts empty when no previous successful login exists.
- Default SQL query text is removed from new default configuration. New installs
  start with an empty SQL query field.
- Existing saved SQL queries are preserved. This includes queries stored in
  legacy `config.json` and SQLite `app_config_values`.
- SQL services treat an empty query as "not configured" instead of silently
  substituting a built-in production-looking query.
- Placeholder help is visible next to the SQL query field in web settings.
- SQLite schema migrations and the explicit repair action share the same
  maintenance functions so startup and manual repair enforce the same current
  data rules.
- Backup settings are bootstrap/runtime settings stored in `local_settings.json`
  because they must be available before opening the active data store.
- Backup files are stored under `BACKUP` next to the executable or backend
  launcher area, using the same root as `local_settings.json`.
- Restore always creates a pre-restore safety copy of the currently active
  database before replacing it.
- Backup diffs mask secrets and password-like values.

## Login Behavior

`login.html` removes `value="admin"`. `login.js` loads
`picorg-last-login-username` from `localStorage` and fills the username field
only when that value exists. After `/api/login` succeeds, `login.js` writes the
submitted username to the same key before redirecting to `/`.

Failed login attempts do not change the remembered username. The password field
continues to use `autocomplete="current-password"` and keeps autofocus, so the
common case remains fast for repeat users.

## SQL Defaults and Placeholder Help

New default configuration uses an empty `sql_query`. Any code that currently
falls back to `SQL_UPDATE_TEMPLATE` when the query is empty must be changed to
accept the empty string as a real "not configured" state.

The shared SQL service exposes one placeholder metadata helper with these
entries:

- `{ean}`: current product EAN used in `WHERE` clauses.
- `{filename}`: generated or uploaded image filename.
- `{col}`: SQL column selected from the slot-to-column mapping.
- `{column}`: alias for `{col}` for readability in custom queries.

The web SQL settings tab shows this list beside the SQL query field. The help
also states that the update table is detected from the `UPDATE ... SET` target,
which is used by SQL column detection and presence checks.

When no SQL query is configured:

- SQL update is skipped with a clear "query not configured" result.
- SQL column detection returns an explicit message instead of using a hidden
  default template.
- SQL presence lookup is disabled.
- The settings UI still allows the user to save an empty query.

## SQLite Schema Upgrade

The next SQLite schema version introduces normalized timestamp and index-cache
structures while keeping compatibility with older data:

- `web_history` stores ordering time as ISO UTC text, named `created_at`.
- Existing numeric `ts` values are migrated into ISO UTC strings in both the
  table column and each record's JSON payload.
- Each history payload keeps a browser-friendly `time` field for display.
- `file_index_cache` keeps the existing `default` snapshot payload for backward
  compatibility, but new writes also maintain segmented rows.
- New `file_index_segments` rows store `segment_key`, `section`, `lookup_key`,
  `payload_json`, and `updated_at` in ISO UTC text.
- SQLite indexes are added for high-use reads:
  `file_index_segments(segment_key, section, lookup_key)`,
  `file_index_segments(updated_at)`,
  `product_entries(ean)`,
  `product_entries(name, type_name, model)`,
  `web_history(created_at)`, and
  `app_config_values(updated_at)`.

Segment keys are based on the normalized first alphanumeric character of the
product name. Values outside `A-Z` and `0-9` go into `_`. This makes lookup by
name read only one segment instead of decoding a complete all-products snapshot.

The `LocalFileIndex` public API remains the same. Internally, when SQLite mode
is active, it can load and save segment rows through the active store. Legacy
mode continues to read and write `file_index.json`.

## Repair Action

The web settings app/runtime section adds a secondary action beside
"Importuj stare dane do SQLite": "Napraw plik bazy danych".

Repair runs only when SQLite mode is active or when a resolvable SQLite database
path exists. It performs these steps:

1. Resolve the SQLite database path.
2. Create a safety backup in `BACKUP` with reason `pre-repair`.
3. Run `PRAGMA integrity_check`.
4. If integrity fails, stop before destructive cleanup and report the error.
5. Run schema migrations to the newest version.
6. Convert old numeric timestamps to ISO UTC text.
7. Rebuild file index segment rows from the current snapshot payload when
   possible.
8. Remove only known obsolete internal tables or records created by earlier
   migrations. User data tables and saved settings are never dropped.
9. Run `ANALYZE`.
10. Run `VACUUM` only after successful integrity and migration steps.
11. Return a structured summary containing backup path, migrations applied,
    timestamps converted, segments rebuilt, cleanup counts, and any warnings.

Repair is exposed as an admin-only API endpoint:
`POST /api/settings/sqlite/repair`.

## Backup Scheduling

Backup settings are stored under a `sqlite_backup` object in
`local_settings.json`:

- `enabled`: boolean.
- `days`: list of weekday keys `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`.
- `hours`: list of integers from `0` to `23`.
- `max_copies`: positive integer, default `10`.
- `last_run_slots`: list of completed schedule slots to prevent repeated
  backups in the same hour.

The settings UI shows a compact weekday/hour grid like the referenced image.
Each selected day and hour combination is a schedule slot. The user can select
multiple days and multiple hours, save the schedule, and set the max copy
count.

The backend checks due backups on startup and through a lightweight background
poller. If the active data mode is not SQLite, the scheduler reports that no
SQLite database is active and does not create copies.

Manual backup is always available from the same settings section and uses reason
`manual`.

## Backup Files

Backup filenames use this format:

`picorgftp_sql-YYYYMMDD-HHMMSS-<reason>.sqlite`

The backup module copies the SQLite database safely using SQLite's online
backup API when the source database can be opened. If the source cannot be
opened as SQLite, it falls back to a raw copy only for pre-repair or
pre-restore safety backups and marks the method in metadata.

Each backup also writes a sidecar JSON metadata file with the same base name:

- source path.
- backup path.
- created_at ISO UTC.
- reason.
- database size.
- schema version when readable.
- integrity_check result when readable.

Retention deletes the oldest scheduled/manual backups beyond `max_copies`.
Pre-repair and pre-restore safety backups are counted in history but are not
deleted by schedule retention unless a separate safety retention limit is added
later.

## Backup History, Restore, and Diff

The web settings panel adds "Historia wersji" for backup files. The modal lists
available backups sorted newest first and shows date, reason, size, schema
version, and integrity status.

Each backup row has:

- "Przywróć": creates a `pre-restore` backup of the active database, replaces
  the active database file atomically, resets the active store cache, reloads
  configuration, and returns a status requiring users to refresh/reload the
  panel.
- "Pokaż różnice": compares the active database with the selected backup.

Diff output is summary-first:

- Table row count changes.
- Added, removed, and changed keys for `app_config_values`, `list_values`,
  `slot_definitions`, `sql_column_map`, `sql_available_columns`, `web_users`,
  `product_entries`, and `file_index_segments`.
- Web history differences by record id.

Secret-like paths and values are masked. Keys containing `password`, `pass`,
`secret`, `token`, `hash`, or `api_key` show only whether a value is empty,
present, added, removed, or changed.

## Error Handling

All mutating SQLite maintenance operations use explicit transactions where the
database remains open. File replacement operations happen through a temporary
file in the destination directory followed by atomic replace.

If backup creation fails, repair and restore stop before changing the active
database. If restore replacement fails after the pre-restore backup succeeds,
the active database path remains unchanged and the error includes the
pre-restore backup path.

The UI reports errors in the existing settings status area and keeps buttons
enabled again after failure.

## Testing

Add focused tests for:

- Login page no longer contains `value="admin"`.
- `login.js` reads and writes the last successful username in `localStorage`.
- New default config has an empty SQL query and no production URL or table name.
- Existing saved SQL queries are preserved by config load/save.
- SQL detection and presence helpers return "not configured" behavior for an
  empty query.
- SQL placeholder metadata is exposed and rendered in the settings SQL tab.
- SQLite migration converts numeric web history timestamps to ISO UTC text.
- File index snapshots save ISO `generated_at` and segmented SQLite rows.
- Repair creates a pre-repair backup, runs integrity checks, applies migrations,
  rebuilds segments, and preserves user/settings data.
- Backup schedule matching selects due day/hour slots and honors `max_copies`.
- Backup history lists metadata and restore creates a pre-restore backup.
- Backup diff masks secret-like values.
- Web API endpoints require admin access.
- Static UI integrity covers the new buttons, schedule grid, history modal, and
  placeholder help.

## Non-Goals

This change does not remove legacy file mode, delete legacy files, migrate logs
into SQLite, expose raw secrets in diffs, redesign the desktop UI, or implement
cloud/off-machine backups.

## Self Review

- No placeholder or incomplete requirements remain.
- The design explicitly preserves existing saved SQLite and legacy data.
- Default SQL query removal is separated from saved query migration.
- Repair and restore are protected by automatic safety backups.
- Backup scope is SQLite-only, with legacy retained as import-only.
- Timestamp conversion covers SQLite history and file index snapshots.
- Index segmentation keeps the existing public lookup API while improving the
  SQLite storage layout.
