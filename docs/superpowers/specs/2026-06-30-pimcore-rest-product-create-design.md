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
  "allow_write_probe": false,
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
- optional `allow_write_probe` toggle;
- editable mapping table for CSV source field -> Pimcore field -> REST element type -> language -> required -> parser -> default.

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
12. The create payload can be built locally from sample values without missing required fields.

Optional write-probe checks, enabled only when `allow_write_probe` is on:

1. Create an unpublished temporary object below `parent_id` with key `picorg-test-<timestamp>`.
2. Fetch the object by returned ID.
3. Delete the temporary object.
4. If deletion fails, show the object ID, key, and REST response so the administrator can remove it manually.

This write-probe is the only reliable way to prove create/save/delete workspace permissions. Without it, the settings test must label create permission as "not verified" rather than "ok".

## Error Reporting

Every failed settings test item returns:

- check key;
- severity: `error`, `warning`, or `info`;
- human message in Polish;
- endpoint or local validation area;
- HTTP status code when present;
- Pimcore response message or a short response-body excerpt;
- suggested fix.

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
- create and delete temporary write-probe objects;
- create real product objects;
- return structured result dictionaries for UI and logs.

Add web data helpers in `picorgftp_sql/web_data.py`:

- settings snapshot fields for Pimcore without exposing API key;
- settings update and encrypted persistence;
- `test_pimcore_settings()`;
- `find_pimcore_product_by_ean(ean)`;
- `create_pimcore_product(payload, username)`.

Add web routes in `picorgftp_sql/web/app.py`:

- `POST /api/settings/pimcore/test`;
- `GET /api/pimcore/product-status?ean=...`;
- `POST /api/pimcore/products`.

Use the same authentication guard as the rest of the web panel. Editing Pimcore settings and running write-probe require admin role. Product status lookup can be available to normal logged-in users. Product create can be allowed to logged-in users if the business workflow requires it, but every create is logged with username and returned object ID.

## Logging And History

Log compact structured events:

- `PIMCORE_SETTINGS_TEST`;
- `PIMCORE_PRODUCT_LOOKUP`;
- `PIMCORE_PRODUCT_CREATE`;
- `PIMCORE_PRODUCT_CREATE_REJECTED`;
- `PIMCORE_WRITE_PROBE`.

Logs include username, EAN, class name, parent ID, object ID, and check failures. Logs exclude API keys and full request bodies containing sensitive defaults.

Web history should include successful product creation so administrators can audit who created a Pimcore product before photo upload.

## UI Behavior

The EAN prompt should not block normal typing. The client debounces lookup after a valid EAN-13 is entered and cancels stale requests. If Pimcore is unavailable, the form shows a non-blocking warning and the user can continue the existing photo flow. The actual create action only runs after explicit confirmation.

The create modal uses the configured mapping order. Required fields are marked. Parser errors are shown next to individual fields and also returned by the backend. `Save` is disabled while a create request is running and the modal remains open on validation/API errors.

## Failure Modes

- REST disabled or unreachable: show warning, log, continue existing workflow without auto-create.
- Invalid API key: settings test error; runtime create disabled until fixed.
- Class or field mismatch: settings test error; runtime create disabled until fixed.
- Duplicate EAN found before create: close missing-product prompt and continue existing workflow.
- Duplicate EAN found during create: cancel create and show the object ID/path if returned by lookup.
- Create succeeds but local entry save fails: keep created Pimcore object, show local save error, log object ID for manual follow-up.
- Create succeeds but SQL image update later fails: existing SQL error handling continues; Pimcore object remains created.

## Testing

Automated coverage:

- config normalization and encrypted API key persistence;
- settings snapshot hides API key and exposes `api_key_set`;
- REST client URL/header construction uses `X-API-Key`;
- server-info/class/object-list success parsing with mocked HTTP;
- detailed error messages for HTTP 401/403, 404, timeout, invalid JSON, missing class, missing field, bad parent, and write-probe failure;
- CSV header import and mapping normalization;
- parser behavior for text, integer, decimal comma, boolean, and empty-to-null;
- object create payload generation;
- duplicate EAN detection across `EAN` and `Towar_powiazany_z_SKU`;
- web routes require authentication and admin role where appropriate;
- runtime flow blocks create when settings test has hard errors;
- UI integrity tests for the Pimcore settings section and create modal hooks.

Manual verification:

1. Save Pimcore settings with URL `http://10.10.0.5`, API key, class `Product`, and parent ID for `Produkty`.
2. Run read-only settings test and verify every required check reports `ok`.
3. Enable write-probe, run test, and verify the temporary object is created, fetched, and deleted.
4. Enter an existing EAN and verify no create prompt appears.
5. Enter a missing EAN, create a product with sample CSV-style data, and verify the object appears in Pimcore under `Produkty`.
6. Continue photo upload and verify existing FTP/SQL update behavior still works.

## Open Implementation Inputs

Before implementation, the administrator must provide or confirm:

- parent ID of the Pimcore `Produkty` folder;
- exact Pimcore class name, expected to be `Product`;
- exact Pimcore field names and element types for the CSV columns;
- whether new objects should be published immediately;
- whether normal web users may create Pimcore products or only admins;
- whether write-probe can be enabled in production settings tests.
