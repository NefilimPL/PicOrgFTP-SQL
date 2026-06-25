# SQLite Data Store Design

## Goal

Add a selectable data mode for both desktop and web: the existing legacy file
mode or a new SQLite mode that stores application data in one database file.
At the same time, restore SQL column detection for web slot settings and keep
desktop and web using the same detection logic.

## Decisions

- `local_settings.json` stays next to the executable/backend as the bootstrap
  file. It continues to host startup-only values such as language, `APP_SECRET`,
  data mode, image directory, database location mode, and optional database
  path.
- Logs stay next to the executable/backend as they do now.
- The old base directory becomes the image directory. It stores processed
  photos and image caches, not necessarily configuration data.
- SQLite mode stores all non-bootstrap application data in one `.sqlite` file:
  app configuration, FTP/SQL settings, slot definitions, SQL column mappings,
  detected SQL columns, Excel list data, product entries, web users, web
  history, and local file index metadata/cache.
- Legacy mode remains supported. In legacy mode, the app reads and writes the
  current files (`config.json`, `lists.xlsx`, `web_users.json`,
  `web_history.json`, `file_index.json`) using existing behavior.
- Migration is explicit. A user can import legacy files into SQLite, review the
  result through normal screens, and switch the active mode to SQLite. The
  import does not delete legacy files.

## Location Model

The settings UI exposes two separate locations:

- Image location: the folder that contains `_ZDJECIA PRZEROBIONE_`, upload
  cache, FTP preview cache, and local file index roots.
- SQLite database location: controlled by a three-option selector:
  `image_dir`, `custom`, or `exe_dir`.

When the database mode is `image_dir`, the database file is stored under the
image location. When the mode is `custom`, the UI enables a path picker. When
the mode is `exe_dir`, the database file is stored next to the executable or
backend launcher area, matching the current local settings/logs location.

## Architecture

Introduce a small data-store layer with a stable interface used by both
desktop and web:

- `LegacyDataStore` wraps the current JSON/Excel helpers.
- `SqliteDataStore` reads and writes equivalent data from SQLite.
- A resolver chooses the active store from `local_settings.json`.
- Existing modules call the resolver instead of directly assuming
  `config.json`, `lists.xlsx`, or web JSON files.

The first implementation keeps the public payloads the same where practical:
`prepare_excel_lists()`, `save_ean_entry()`, web users, web history,
`settings_snapshot()`, and `update_settings()` should return the same shapes
they return today. This limits UI churn and lets tests compare legacy and
SQLite behavior.

## SQLite Schema

The database has versioned migrations and creates these logical groups:

- `app_settings`: key/value JSON records for normalized configuration blocks.
- `slot_definitions`: prefix, label, filename label, sort order.
- `sql_column_map`: slot prefix to database column name.
- `sql_available_columns`: detected SQL columns with source table and timestamp.
- `list_values`: list key and value for names, types, models, colors, extras.
- `product_entries`: product identity and fields currently stored in the
  `ENTRIES` Excel sheet.
- `web_users`: username, password hash, role, lock state, enabled state, and
  extension token version.
- `web_history`: compact event records with JSON details.
- `file_index_cache`: metadata and cached index payload used by local file
  indexing.

Secrets remain encrypted using the existing `APP_SECRET` before being stored in
SQLite, matching the current `config.json` behavior.

## Legacy Import

The import action reads the active legacy locations and writes a SQLite
database:

1. Read `config.json`, normalize it with existing config normalization.
2. Read `lists.xlsx`, list sheets, and `ENTRIES`.
3. Read `web_users.json`, `web_history.json`, and `file_index.json` if present.
4. Write normalized rows into SQLite inside one transaction.
5. Preserve encrypted secret values without decrypting and re-encrypting unless
   the active code already has decrypted values.
6. Report counts and skipped/malformed records to the UI.
7. Offer switching the active data mode to SQLite after a successful import.

Repeated imports are idempotent by natural keys: list key/value, product ID or
EAN where appropriate, username, history ID, and slot prefix.

## SQL Column Detection

Move SQL column detection into `picorgftp_sql.services.sql_service`:

- Build the metadata query using the existing `build_column_detection_query()`.
- Connect using the currently edited/saved database settings.
- Execute `INFORMATION_SCHEMA.COLUMNS`.
- Normalize and deduplicate columns.
- Persist detected columns through the active data store.

The desktop settings dialog keeps its existing button but delegates to the
shared service. The web slot settings tab gets an explicit "Wykryj pola SQL"
button that calls an admin-only API endpoint. The endpoint returns columns,
table name, query preview, and a user-visible status message.

## UI Behavior

Desktop and web settings expose the same conceptual controls:

- Data mode: `Legacy files` or `SQLite`.
- Image location.
- SQLite location mode: image directory, custom path, or exe/backend directory.
- Custom SQLite path picker enabled only for custom mode.
- Import legacy data into SQLite.
- Current active storage summary with config path/database path.

Changing image location updates photo-related paths. Changing SQLite location
requires reopening the SQLite connection and refreshing the active data store.
If the location is invalid, the change is rejected with a clear message and the
previous active data source stays in use.

## Error Handling

SQLite operations use transactions for multi-table writes. A failed import
rolls back the database changes and leaves the active mode unchanged. Database
open errors fall back only when the configured mode is legacy; if SQLite mode
is configured and the database is unavailable, the app shows a startup/settings
error instead of silently writing to legacy files.

Legacy files are not deleted by migration. This keeps rollback simple: switch
the data mode back to legacy.

## Testing

Add focused tests for:

- Database path resolution for all three location modes.
- SQLite schema creation and migration versioning.
- Legacy import from representative `config.json`, `lists.xlsx`, user/history
  JSON, and file index JSON.
- Data-store parity for list loading, entry saving, settings load/save, web
  users, and web history.
- Web SQL column detection endpoint updates detected columns and returns them
  to the slot settings datalist.
- Desktop/web settings snapshots expose the new image/database locations.
- Legacy mode continues to use current files.

## Non-Goals

This change does not remove legacy file support, delete existing user files,
change photo naming rules, or redesign the product form. It also does not move
runtime logs into SQLite.

## Self Review

- The design keeps `local_settings.json` and logs beside the executable/backend.
- Both desktop and web are covered by the shared data-store layer.
- Legacy and SQLite modes are both supported.
- The requested three SQLite database location modes are explicit.
- The SQL column detection regression has a concrete shared-service fix.
- Migration covers configuration, Excel data, users, history, and index cache.
