# Pimcore REST Product Creation Design

## Goal

Add an optional Pimcore integration to the web panel so a user can create a missing Pimcore product object directly from the photo workflow. The first implementation target is Pimcore 6.6.x REST Webservice API, authenticated with the existing per-user API key from Pimcore admin.

The integration must not require PHP changes on the Pimcore server for the first version. Direct writes into Pimcore SQL tables are out of scope because Pimcore objects require metadata, parent placement, generated class storage, versioning, permissions, and cache handling that raw SQL would bypass.

Official Pimcore 6.6.11 references:

- REST Webservice API: https://github.com/pimcore/pimcore/blob/v6.6.11/doc/Development_Documentation/24_Web_Services/README.md
- Query filters: https://github.com/pimcore/pimcore/blob/v6.6.11/doc/Development_Documentation/24_Web_Services/01_Query_Filters.md
- PHP API and external interaction guidance: https://github.com/pimcore/pimcore/blob/v6.6.11/doc/Development_Documentation/05_Objects/05_External_System_Interaction.md

## Current Context

The existing web panel already has:

- product form and configurable product fields in `picorgftp_sql/web_workflow.py`;
- local product entry save/search in `picorgftp_sql/web_data.py`;
- SQL photo URL update in `picorgftp_sql/web/app.py`;
- SQL table and WHERE extraction from the configured update query in `picorgftp_sql/services/sql_service.py`;
- settings persistence through `config.json` or the active SQLite store.

The current SQL configuration updates image columns on `object_query_1` for an existing Pimcore row:

```sql
UPDATE object_query_1
SET {col} = 'https://xml.wipmebgroup.pl/img/{filename}'
WHERE EAN = '{ean}' OR Towar_powiazany_z_SKU = '{ean}'
```

That remains the photo-update path. Creating a missing product uses Pimcore REST instead.

## Configuration Model

Add a new normalized `pimcore` settings object:

```json
{
  "enabled": false,
  "base_url": "http://10.10.0.5",
  "api_key": "",
  "class_name": "Product",
  "parent_id": "",
  "published": true,
  "object_key_template": "{SKU}",
  "existence_fields": ["EAN", "Towar_powiazany_z_SKU"],
  "timeout_seconds": 10,
  "verify_tls": true,
  "field_mappings": []
}
```

Secrets follow the existing config pattern: the API key is encrypted at rest and is never returned by normal settings snapshots. The UI only exposes `api_key_set: true/false` unless an explicit admin reveal action is added later.

`field_mappings` describes how form/CSV-style values become Pimcore REST object elements:

```json
{
  "source": "SKU",
  "label": "SKU",
  "pimcore_field": "SKU",
  "type": "input",
  "language": null,
  "required": true,
  "default": "",
  "parser": "text"
}
```

Supported parsers in the first version:

- `text`: trim string;
- `integer`: parse whole number;
- `decimal_comma`: parse Polish CSV decimals such as `62,5`;
- `boolean`: accept `1/0`, `true/false`, `yes/no`, `tak/nie`;
- `empty_to_null`: trim and send `null` when empty.

The mapping UI can be prefilled from the uploaded CSV headers, including the sample headers such as `SKU`, `EAN`, `Manufacturer_Name`, `Article_Group`, `CN CODE`, parcel dimensions, `TOTAL WEIGHT`, and `TOTAL VOLUME [m2]`.

## Settings UI

Add a Pimcore section in web settings near the existing database settings.

Required controls:

- enabled toggle;
- base URL;
- API key input with saved/unsaved status;
- class name, default `Product`;
- parent object/folder ID for `Produkty`;
- published toggle;
- object key template, default `{SKU}`, fallback to `{EAN}`;
- existence fields list, default `EAN` and `Towar_powiazany_z_SKU`;
- timeout and TLS verification;
- editable mapping table for CSV source field -> Pimcore field -> REST element type -> language -> required -> parser -> default.
- `Sprawdz konfiguracje` button for the read-only validation checklist;
- `Testowo dodaj obiekt` button for an explicit real write test.

The mapping table must support importing headers from a CSV file without importing data. This lets the administrator align the web panel fields with the same columns currently used in Pimcore CSV import configuration.

## Full Settings Test

Settings must include a full test button that validates the integration before users can rely on it. The result is a checklist with one row per check, not a single generic failure.

Required read-only checks:

1. `base_url` is present and has `http` or `https`.
2. `api_key` is present when Pimcore integration is enabled.
3. `GET /webservice/rest/server-info` succeeds with `X-API-Key`.
4. The response identifies a compatible Pimcore 6.x server when version data is available.
5. `GET /webservice/rest/classes` succeeds.
6. `class_name` exists in the returned classes list.
7. The class definition can be fetched and contains every configured `pimcore_field`.
8. Every mapping has a source, target field, supported element type, and compatible parser.
9. Required fields include at least `EAN` and one stable key source such as `SKU` or `EAN`.
10. `parent_id` resolves to an existing object/folder through REST.
11. `object-list` can query the configured class with a test EAN filter.
12. The empty manual-test form schema can be built from the configured mappings, in mapping order, with required fields identified.

The read-only test never creates, updates, or deletes a Pimcore object. It must label create permission as "not verified" until an administrator completes the separate manual write test.

## Manual Write Test From Settings

`Testowo dodaj obiekt` opens a dedicated working modal above the settings view. It is independent of the main product form and does not copy EAN, SKU, defaults, or any other product values from an existing local or Pimcore record.

The modal uses a stable two-column layout:

- left side: one initially empty input for every configured mapping, in mapping order;
- right side: a live operation log with timestamps, severity, stage status, and elapsed time;
- footer: cleanup choice, `Wyslij`, `Wyczysc formularz`, and `Zamknij` controls.

Technical connection values such as `base_url`, API key, class, and parent ID come from saved settings and are not editable in the test modal. The object key is built from the configured template after the administrator supplies its source values. Missing key sources and required mapped fields are reported before any REST write.

Before each run, the administrator must explicitly choose one cleanup policy; there is no remembered choice from the previous run:

- `Usun po tescie`: create an unpublished object, fetch it back, then delete it;
- `Pozostaw w Pimcore`: create an unpublished object, fetch it back, and retain it for manual inspection.

The confirmation shown before `Wyslij` states the target URL, class, parent ID, generated object key, and cleanup policy. It never includes the API key.

Submitting starts a new operation with a unique `operation_id`. It does not close the modal. `Wyslij` is disabled only while that operation is active, and the entered values remain in the inputs after success or failure. `Wyczysc formularz` explicitly clears the inputs and current on-screen log but does not delete the persisted audit record. Only `Zamknij` or the close icon closes the modal; submitting, clearing, backdrop clicks, and successful completion do not close it.

The write test executes these stages:

1. Validate saved integration settings, mapping definitions, required values, parsers, and object key.
2. Build and log a sanitized payload summary.
3. Create the unpublished object below `parent_id`.
4. Fetch the returned object ID and verify the submitted mapped values.
5. Delete the object only when `Usun po tescie` was selected.
6. Persist the final operation report and cleanup result.

If creation succeeds but fetch or deletion fails, the result is a partial failure. The modal and persisted report show the object ID, key, path when available, Pimcore response, and exact manual cleanup action.

## Live Operation Log

The browser receives live progress through short polling instead of requiring WebSocket infrastructure. Starting a run returns `operation_id`; the UI requests events newer than its last sequence number approximately every 500 ms until the operation reaches a terminal state. Sequence numbers prevent duplicate lines and allow the UI to resume after a transient request failure.

Each live event includes:

- monotonically increasing sequence number;
- server timestamp and milliseconds since operation start;
- stage key and Polish stage label;
- severity: `info`, `success`, `warning`, or `error`;
- concise message;
- HTTP method, endpoint, and status when applicable;
- stage elapsed time when the stage finishes.

The log shows validation, payload construction, REST create, response parsing, verification fetch, optional deletion, and final persistence as separate stages. It auto-scrolls while the user remains at the bottom; manual scrolling up pauses auto-scroll so diagnostic lines can be inspected.

## Error Reporting

Every failed settings test item returns:

- check key;
- severity: `error`, `warning`, or `info`;
- human message in Polish;
- endpoint or local validation area;
- HTTP status code when present;
- Pimcore response message or a short response-body excerpt;
- suggested fix.

Manual and test create operations additionally return `operation_id`, operation type, start and finish timestamps, total elapsed time, every completed stage with its elapsed time, object ID/key/path when available, cleanup policy, and cleanup result.

Examples:

- API key invalid: "Pimcore odrzucil klucz API dla `/webservice/rest/server-info` (HTTP 401/403). Sprawdz klucz uzytkownika i uprawnienia."
- REST disabled: "Endpoint Webservice API nie odpowiada poprawnie. Sprawdz `Settings > System Settings > Web Service API`."
- Class missing: "Nie znaleziono klasy `Product` w `/webservice/rest/classes`."
- Field missing: "Pole `TOTAL_WEIGHT` nie istnieje w klasie `Product`; popraw mapowanie kolumn."
- Parent missing: "Nie znaleziono obiektu/folderu parentId `123`; ustaw ID folderu `Produkty`."
- Write permission missing: "Uzytkownik API nie moze tworzyc obiektow w wybranym folderze."
- Filter error: "Zapytanie `object-list` po EAN nie powiodlo sie; sprawdz nazwe pola i filtr REST."

The API key must never be logged or echoed in UI errors. Query-string API key usage is avoided; the panel uses the `X-API-Key` header.

## Runtime Flow

1. User enters EAN in the web product form.
2. Existing local entry lookup continues as today.
3. If Pimcore integration is enabled and EAN is valid, the backend checks Pimcore via REST `object-list` using `class_name` and `existence_fields`.
4. If a matching Pimcore object exists, no extra prompt is shown.
5. If no matching object exists, the UI shows a prompt: the product does not exist in Pimcore and can be created.
6. If the user confirms, a modal opens with the configured mapped fields. EAN is prefilled and locked unless the administrator makes it editable.
7. On save, the backend validates required fields, parsers, object key template, and duplicate existence again.
8. The backend sends `POST /webservice/rest/object` with `className`, `parentId`, `key`, `published`, and `elements`.
9. On success, the backend records the created Pimcore object ID and continues the existing photo workflow.
10. Existing FTP upload, SQL image URL update, and local entry save continue unchanged.

The duplicate check is repeated immediately before create to avoid a race where another user creates the same EAN after the first prompt.

## REST Payload Shape

The create request follows the Pimcore 6.6 REST object create format:

```json
{
  "className": "Product",
  "parentId": 123,
  "key": "PUANTV03KAKAZZ5020",
  "published": true,
  "elements": [
    {
      "type": "input",
      "name": "SKU",
      "value": "PUANTV03KAKAZZ5020",
      "language": null
    },
    {
      "type": "input",
      "name": "EAN",
      "value": "5904804578169",
      "language": null
    }
  ]
}
```

The service must keep payload construction isolated in a dedicated module so tests can validate payloads without calling Pimcore.

## Backend Architecture

Add `picorgftp_sql/services/pimcore_service.py` with pure functions and a small client class:

- normalize Pimcore config;
- build REST URLs safely from `base_url`;
- send authenticated requests with `X-API-Key`;
- list classes and read class definitions;
- validate mappings against class fields;
- build object-list filters for EAN existence checks;
- build object create payloads;
- create, fetch, verify, and optionally delete manual-test objects;
- create real product objects;
- return structured result dictionaries for UI and logs.

Add an isolated Pimcore operation runner that owns active run state and numbered events. It exposes a small interface to start a run, append a sanitized event, read events after a sequence number, and finalize/persist a report. The REST client remains unaware of browser polling.

Add web data helpers in `picorgftp_sql/web_data.py`:

- settings snapshot fields for Pimcore without exposing API key;
- settings update and encrypted persistence;
- `test_pimcore_settings()`;
- `start_pimcore_test_create(values, cleanup_policy, username)`;
- `pimcore_operation_status(operation_id, after_sequence)`;
- `pimcore_operation_history(filters)`;
- `find_pimcore_product_by_ean(ean)`;
- `create_pimcore_product(payload, username)`.

Add web routes in `picorgftp_sql/web/app.py`:

- `POST /api/settings/pimcore/test`;
- `POST /api/settings/pimcore/test-create-runs`;
- `GET /api/settings/pimcore/test-create-runs/{operation_id}`;
- `GET /api/settings/pimcore/operations`;
- `GET /api/pimcore/product-status?ean=...`;
- `POST /api/pimcore/products`.

Use the same authentication guard as the rest of the web panel. Editing Pimcore settings and running or reading manual tests require admin role. Product status lookup can be available to normal logged-in users. Product create can be allowed to logged-in users if the business workflow requires it, but every create is logged with username and returned object ID.

## Logging And History

Persist structured audit records for:

- `PIMCORE_SETTINGS_TEST`;
- `PIMCORE_PRODUCT_LOOKUP`;
- `PIMCORE_PRODUCT_CREATE`;
- `PIMCORE_PRODUCT_CREATE_REJECTED`;
- `PIMCORE_TEST_CREATE`.

Every create record includes `operation_id`, operation type (`manual` from the main panel or `test` from settings), username, EAN/SKU when supplied, class name, parent ID, object ID/key/path, cleanup policy and result, started/finished timestamps, total elapsed time, numbered stage events, HTTP statuses, and check failures. The submitted mapped product values are retained in a sanitized payload snapshot for diagnosis. Logs always exclude API keys, authorization headers, cookies, and encrypted secret values.

The settings integration exposes a Pimcore-specific operation history. It lists manual and test creates with filters for operation type, result, user, date, EAN/SKU, and object key. Opening a record shows the same stage log and timing report that was displayed live. The general web history can contain a compact summary linked by `operation_id`, while detailed Pimcore diagnostics remain in the Pimcore history. Existing storage retention and backup rules apply.

## UI Behavior

The EAN prompt should not block normal typing. The client debounces lookup after a valid EAN-13 is entered and cancels stale requests. If Pimcore is unavailable, the form shows a non-blocking warning and the user can continue the existing photo flow. The actual create action only runs after explicit confirmation.

The create modal uses the configured mapping order. Required fields are marked. Parser errors are shown next to individual fields and also returned by the backend. `Save` is disabled while a create request is running and the modal remains open on validation/API errors.

The settings test-create modal is separate from the runtime create modal. It starts with all mapped data fields empty, keeps entered values after every run, and places the live log beside the form. Neither `Wyslij` nor successful completion closes it. An explicit `Wyczysc formularz` action clears fields and the current visible log; an explicit close control is the only way to dismiss the modal.

## Failure Modes

- REST disabled or unreachable: show warning, log, continue existing workflow without auto-create.
- Invalid API key: settings test error; runtime create disabled until fixed.
- Class or field mismatch: settings test error; runtime create disabled until fixed.
- Duplicate EAN found before create: close missing-product prompt and continue existing workflow.
- Duplicate EAN found during create: cancel create and show the object ID/path if returned by lookup.
- Live-log polling fails temporarily: keep the modal open, retry from the last sequence number, and show a connection warning without canceling the server-side run.
- Test create succeeds but verification fetch fails: retain the known object ID/key, report partial failure, and still attempt deletion only when the selected cleanup policy requires it.
- Test deletion fails: report partial failure and show the object ID/key/path and manual cleanup instruction.
- Create succeeds but local entry save fails: keep created Pimcore object, show local save error, log object ID for manual follow-up.
- Create succeeds but SQL image update later fails: existing SQL error handling continues; Pimcore object remains created.

## Testing

Automated coverage:

- config normalization and encrypted API key persistence;
- settings snapshot hides API key and exposes `api_key_set`;
- REST client URL/header construction uses `X-API-Key`;
- server-info/class/object-list success parsing with mocked HTTP;
- detailed error messages for HTTP 401/403, 404, timeout, invalid JSON, missing class, missing field, bad parent, verification failure, and deletion failure;
- manual-test form schema starts with empty values and never imports the current product form;
- required cleanup choice, required-field validation, and object-key validation occur before REST create;
- test object create/fetch/value verification and both cleanup policies;
- partial failure when verification or deletion fails after successful creation;
- active operation event sequencing, incremental polling, reconnect from the last sequence, and final persistence;
- redaction of API keys, authorization headers, cookies, and encrypted secrets from live and persisted logs;
- live-log UI remains open after submit, success, failure, and clear actions;
- form values remain after a run and clear only through `Wyczysc formularz`;
- CSV header import and mapping normalization;
- parser behavior for text, integer, decimal comma, boolean, and empty-to-null;
- object create payload generation;
- duplicate EAN detection across `EAN` and `Towar_powiazany_z_SKU`;
- web routes require authentication and admin role where appropriate;
- runtime flow blocks create when settings test has hard errors;
- UI integrity tests for the Pimcore settings section and create modal hooks.

Manual verification:

1. Save Pimcore settings with URL `http://10.10.0.5`, API key, class `Product`, and parent ID for `Produkty`.
2. Run the read-only settings test and verify every required check reports `ok` or explicitly reports create permission as not yet verified.
3. Open `Testowo dodaj obiekt` and verify every mapped product input is empty and independent of the main product form.
4. Fill test values, choose `Usun po tescie`, submit, watch every live stage, and verify the object is created, fetched, and deleted without closing or clearing the modal.
5. Clear the form explicitly, fill another test, choose `Pozostaw w Pimcore`, and verify the returned object ID/key/path and persisted operation history.
6. Enter an existing EAN in the main panel and verify no create prompt appears.
7. Enter a missing EAN, create a product with sample CSV-style data, and verify the object appears in Pimcore under `Produkty`.
8. Continue photo upload and verify existing FTP/SQL update behavior still works.

## Open Implementation Inputs

Before implementation, the administrator must provide or confirm:

- parent ID of the Pimcore `Produkty` folder;
- exact Pimcore class name, expected to be `Product`;
- exact Pimcore field names and element types for the CSV columns;
- whether new objects should be published immediately;
- whether normal web users may create Pimcore products or only admins.
