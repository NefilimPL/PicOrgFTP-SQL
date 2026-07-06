# SQL Profiles And Pimcore SQL Placeholders Design

**Date:** 2026-07-06
**Status:** Approved design, awaiting written-spec review
**Target:** PicOrgFTP-SQL web panel on branch `dev`

## Context

The application currently has one global SQL connection and query template. Slot
SQL checks and updates use that global connection, while Pimcore field mappings
support manual values and saved value templates. The Pimcore template engine
already has an extension point for extra data providers, but no SQL provider is
implemented yet.

The requested change adds SQL connection profiles, lets Pimcore mappings execute
per-field SQL queries from selected profiles, records submitted Pimcore data in
SQLite, exports those records, and improves runtime recalculation feedback when
manual values differ from calculated values.

## Goals

1. Add configurable SQL profiles with a permanent default profile.
2. Keep the default SQL profile assigned to slots and show that fact in the UI.
3. Let administrators add extra SQL profiles for Pimcore placeholder queries.
4. Let each Pimcore field mapping enter `SQL` in the existing value-template
   field and enter a separate SQL query below it.
5. Let each SQL-backed Pimcore mapping choose which SQL profile executes the
   query.
6. Execute SQL-backed Pimcore values automatically only when the visible runtime
   field is empty.
7. Support explicit per-field and all-field recalculation.
8. When recalculation finds a value different from the visible value, mark the
   field yellow, show the calculated text next to it, and offer a per-field
   undo/apply-calculated action.
9. Persist data submitted to Pimcore in SQLite and expose an export action.
10. Preserve existing slot, FTP, Pimcore, translation, image, desktop, secret
    redaction, and audit behavior unless directly extended by this design.

## Non-Goals

- Replacing the existing slot SQL query and column mapping model.
- Letting arbitrary SQL modify source databases from Pimcore placeholder
  mappings.
- Building a general ETL engine or multi-row Pimcore import system.
- Changing the Pimcore REST API object model, class selection, parent folder, or
  optimistic conflict behavior.
- Moving existing web history records out of their current table.
- Implementing desktop UI changes for SQL profile management in this project.

## Selected Architecture

Use a backend-owned SQL profile model and a focused SQL value provider for
Pimcore mappings. The browser collects profile settings, mapping SQL settings,
and user-triggered recalculation requests. The backend normalizes, stores,
validates, executes, redacts, audits, and exports the data.

The existing global SQL settings become the `default` profile for compatibility.
Slot workflows continue to read the default profile through the current config
keys, so existing installations keep working. Additional profiles are stored in
a new profile list and are only used by Pimcore SQL mapping execution.

Pimcore field mappings keep the existing `value_template` property. The exact
value `SQL`, case-insensitive after trimming, switches that mapping into SQL
mode. SQL mode uses two extra mapping properties:

```json
{
  "sql_query": "",
  "sql_profile_id": ""
}
```

This matches the requested two-field model: the first field remains the current
placeholder/function field, and the second field stores the SQL query executed
when the first field contains `SQL`.

## SQL Profile Configuration

### Profile Shape

Each normalized SQL profile has:

```json
{
  "id": "stock-db",
  "label": "Stock DB",
  "type": "mysql",
  "host": "sql.example.local",
  "database": "catalog",
  "user": "",
  "password": "",
  "enabled": true,
  "usage": "pimcore_sql"
}
```

The default profile is derived from the existing keys:

- `db_type`
- `mssql.server`, `mssql.database`, `mssql.user`, `mssql.password`
- `mysql.server`, `mysql.database`, `mysql.user`, `mysql.password`
- `sql_query`
- `enable_sql_update`

The default profile has stable ID `default`, label `Domyslny`, and usage
`slots`. It cannot be deleted or disabled through profile management because it
is the source of truth for slots.

Additional profiles are stored under a new top-level configuration key
`sql_profiles`. They must have stable IDs, labels, type `mysql` or `mssql`, host,
database, optional user and password, enabled flag, and usage `pimcore_sql`.

### Secrets

Profile passwords are persisted through the same encrypted secret mechanism used
for existing FTP, SQL, Pimcore, and translation credentials. Public settings
snapshots expose only `password_set` and `user_set` flags. Explicit secret reveal
for administrators includes additional profile secrets under their profile IDs.

Blank submitted profile passwords preserve existing encrypted passwords. Blank
submitted profile users preserve existing users only when the UI sent the field
as a credential-preserve placeholder; otherwise the profile user may be cleared
explicitly through a dedicated clear action.

### UI

The SQL settings tab shows:

- the existing default SQL settings;
- a clear note: `Profil domyslny jest zawsze uzywany przez Sloty`;
- profile cards or rows for additional Pimcore SQL profiles;
- add, rename, test, disable, and remove actions for additional profiles;
- no remove action for `default`;
- a profile usage indicator showing `Sloty` for default and `Pimcore SQL` for
  additional profiles.

The existing SQL diagnostic button tests the default profile. Each additional
profile has its own test action that performs `SELECT 1` through that profile.

## Pimcore Mapping Configuration

Each normalized Pimcore field mapping gains backward-compatible properties:

```json
{
  "sql_query": "",
  "sql_profile_id": ""
}
```

Old mappings normalize to empty strings and keep current behavior.

When `value_template` is not `SQL`, the existing template behavior remains
unchanged. When `value_template` is `SQL`:

- `sql_query` is required;
- `sql_profile_id` is required and must refer to an enabled Pimcore SQL profile;
- the field must be compatible with the final parser;
- translation options are ignored for that mapping unless a future project
  explicitly combines SQL and translation;
- normal required-field and parser validation still runs after SQL execution.

The compact and guided Pimcore settings show the existing value-template control
and a separate SQL query control for each mapping. The SQL query control is
enabled only when the template field contains `SQL`. It remains visible or
discoverable enough that users understand why `SQL` has a second field.

## SQL Query Semantics

Pimcore SQL mapping queries are read-only. The executor accepts a single
`SELECT` statement and rejects:

- empty SQL in SQL mode;
- more than one statement;
- comments that hide additional statements;
- `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `TRUNCATE`, `EXEC`,
  stored procedure calls, and other non-select commands;
- query strings above the configured length bound;
- result sets requiring more than the first row and first column.

The first column of the first row becomes the calculated value. No row returns
an empty value and a warning. Multiple rows are allowed only as an implementation
detail; the executor reads the first row and returns a warning that the query
should be made deterministic with `LIMIT 1` for MySQL or `TOP 1` for MSSQL.

Supported placeholders are parameterized, not string-concatenated. Initial
placeholders:

- `{ean}` and `{EAN}` from the current Pimcore/runtime values or product form;
- `{product_id}`;
- `{name}`, `{type}`, `{model}`, `{color1}`, `{color2}`, `{color3}`, `{extra}`;
- `{pimcore:<source>}` for current values in the Pimcore runtime form.

The backend converts placeholders into driver parameters. Missing placeholders
resolve to empty strings. The preview response includes sanitized warnings, not
raw connection secrets.

## Runtime Rendering

The existing `/api/pimcore/render-templates` behavior is extended to render both
standard templates and SQL-mode mappings. The response gains calculated metadata:

```json
{
  "values": {"TITLE": "Manual value"},
  "calculated_values": {"TITLE": "SQL value"},
  "warnings": [],
  "changed": {"TITLE": true}
}
```

`values` remains the value that should be written to the input when automatic
application is allowed. `calculated_values` always reports what recalculation
produced for selected SQL/template mappings. `changed` compares the visible
submitted value with the calculated value as text.

### Automatic Calculation

For create and test forms, SQL-mode mappings calculate automatically only when
the target input is empty at the time rendering runs. If the user typed a value,
automatic rendering preserves that value and returns the calculated value beside
it as metadata.

For edit forms, opening the modal never auto-overwrites values fetched from
Pimcore. Recalculation is explicit through `Przelicz pole` or `Przelicz
wszystkie`.

### Manual Recalculation

`Przelicz pole` recalculates the selected mapping and any dependencies required
for that mapping. `Przelicz wszystkie` recalculates all mappings with either a
standard value template or SQL mode.

If a calculated value differs from the current input:

- the input row receives a yellow warning style;
- the calculated text appears next to the input;
- an action button applies the calculated value to that input;
- applying the calculated value removes the yellow style;
- manual editing after applying can create a new difference on the next
  recalculation.

This is the same user intention as the main window's undo of manual changes: the
operator can return a field to the most recent calculated value without clearing
or rebuilding the whole form.

## Pimcore Submission Persistence

SQLite gains a new table for submitted Pimcore payloads. It is separate from
`web_history`, which remains the compact UI history and existing audit trail.

Proposed table:

```sql
CREATE TABLE IF NOT EXISTS pimcore_submissions (
  id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL DEFAULT '',
  operation_type TEXT NOT NULL,
  username TEXT NOT NULL DEFAULT '',
  ean TEXT NOT NULL DEFAULT '',
  object_id TEXT NOT NULL DEFAULT '',
  object_path TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  values_json TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

Every manual create, manual update, and test-create operation records:

- the visible values submitted by the user;
- the Pimcore REST payload built from those values when available;
- the result or sanitized error;
- calculated-value warnings when present;
- operation type and user;
- object identity when known.

The write happens after payload construction for successful requests and after a
sanitized failure record for failed requests where submitted values are known.
Secrets are redacted before insertion.

When the application is in legacy JSON mode, `web_history` behavior remains as
today. The new detailed submission table is available only when SQLite storage
is active, matching the request to store these details in SQLite.

## Export

The Pimcore history modal gains an export action for SQLite submission records.
Filters mirror the existing history filters where practical:

- operation type;
- status;
- user;
- text query over EAN, object ID, object path, and submitted values;
- date range;
- limit.

Initial export formats are CSV and JSON. CSV flattens common columns and stores
the values/payload/result JSON as escaped columns. JSON returns the full stored
records with secrets already redacted. If an existing XLSX export helper is
preferred during implementation and has no new dependency cost, XLSX may be
added, but CSV and JSON are sufficient for this design.

## API Boundaries

New or extended routes follow existing permission patterns:

- admin-only settings save and snapshot for SQL profiles;
- admin-only profile diagnostic test;
- admin-only unsaved Pimcore template/SQL preview;
- authenticated saved runtime rendering for create/edit;
- authenticated Pimcore create and update;
- admin-only Pimcore submission export.

Ordinary authenticated users may execute only saved SQL-mode mappings from the
active Pimcore configuration. They cannot submit arbitrary SQL text through the
runtime render route. Unsaved SQL preview stays administrator-only.

All responses redact profile passwords, Pimcore API keys, translation keys, and
driver connection strings.

## Error Handling

- Missing profile: block settings save for mappings that reference it.
- Disabled profile: block runtime execution with a clear message naming the
  profile label.
- SQL connection failure: return a warning or error tied to the mapping source,
  depending on whether execution was automatic or explicitly requested.
- SQL syntax or disallowed command: block preview/settings save and return a
  field-specific message.
- Empty result: preserve user-entered value and show an empty calculated value
  with a warning.
- Parser failure after SQL execution: use the existing parser error path for the
  Pimcore mapping label.
- Audit write failure: do not fail a successful Pimcore write, but record a
  sanitized warning in logs and web history.

## Testing Strategy

### SQL Profile Tests

- default profile is derived from existing SQL settings;
- default profile is marked as slot-owned and cannot be deleted;
- additional profiles normalize IDs, labels, types, and enabled state;
- profile secrets are encrypted on save and redacted in settings snapshots;
- blank profile credentials preserve saved secrets where appropriate;
- profile diagnostics use the selected profile rather than the global default.

### SQL Execution Tests

- allowed `SELECT` returns first row, first column;
- no row returns empty calculated value plus warning;
- multiple rows return first value plus deterministic-query warning;
- non-select and multi-statement SQL are rejected;
- supported placeholders become driver parameters for MySQL and MSSQL styles;
- missing placeholders become empty strings;
- connection failures return sanitized mapping-specific errors.

### Pimcore Configuration Tests

- old mappings gain empty `sql_query` and `sql_profile_id`;
- SQL mode requires a query and enabled profile;
- non-SQL template mode ignores empty SQL fields and preserves existing
  behavior;
- field mapping issues include source labels and SQL errors;
- public runtime schema includes SQL-mode metadata without secrets.

### Runtime Tests

- create/test auto-apply calculated SQL only into empty fields;
- create/test preserve non-empty manual values and return calculated metadata;
- edit modal does not auto-overwrite fetched values;
- per-field recalculation returns calculated value and changed flag;
- all-field recalculation marks only fields whose visible value differs;
- apply-calculated action updates one field and clears its warning state.

### SQLite And Export Tests

- schema creates `pimcore_submissions`;
- manual create, manual update, and test-create append detailed records;
- records contain submitted values and sanitized Pimcore payload/result;
- export filters by user, status, operation type, query, and date;
- CSV and JSON exports do not expose secrets.

### UI Integrity Tests

- SQL settings show the default profile slot note;
- additional profile controls exist and do not offer delete for default;
- Pimcore mapping rows show SQL query/profile controls;
- runtime forms render yellow changed state, calculated text, and per-field
  apply action;
- all-field recalculation does not overwrite non-empty differing manual values
  unless the user applies the calculated value;
- asset cache version changes so browsers load the new JS/CSS.

## Acceptance Criteria

- Slot SQL behavior keeps using the default profile.
- UI clearly states that the default profile is always assigned to slots.
- Admins can add additional SQL profiles and select them for Pimcore SQL-mode
  mappings.
- A Pimcore mapping with `value_template` set to `SQL` executes its separate
  `sql_query` through the selected profile.
- SQL values calculate automatically only into empty create/test fields.
- Explicit recalculation shows yellow mismatch styling, calculated text, and a
  per-field apply-calculated action when manual and calculated values differ.
- Data submitted to Pimcore is stored in SQLite with payload/result details and
  can be exported.
- Existing saved Pimcore templates, slot mappings, SQL updates, credential
  encryption, and web history continue to work.

## Spec Self-Review

- Placeholder scan: the document contains no open `TBD`, `TODO`, or incomplete
  implementation placeholders.
- Consistency check: SQL profiles, Pimcore SQL mode, runtime recalculation,
  SQLite persistence, and export all use the same configuration and API model.
- Scope check: the project is broad but cohesive around SQL-backed Pimcore
  mapping values and their audit trail; unrelated desktop and ETL work is
  explicitly out of scope.
- Ambiguity check: the approved assumption is explicit: profiles are full
  `mysql` or `mssql` profiles, and `value_template = SQL` is the switch for the
  second SQL query field.
