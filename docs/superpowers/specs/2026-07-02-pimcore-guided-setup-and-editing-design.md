# Pimcore Guided Setup And Existing Product Editing Design

**Date:** 2026-07-02
**Status:** Awaiting written-spec review
**Target:** PicOrgFTP-SQL web panel on branch `dev`, Pimcore legacy REST API 6.6.x

## Context

The first Pimcore product-creation implementation exposes low-level REST details directly in settings. It assumes a class named `Product`, requires manual entry of a parent object ID, uses CSV headers as the primary source of form fields, and asks the administrator to configure element types and parsers. The live server test proved that the connection and API key work, but also exposed these problems:

- the server does not contain a class named `Product`;
- no EAN mapping is configured;
- the current object-list request uses the removed `condition` parameter and `className` instead of the supported `q` filter and `objectClass`;
- dependent checks can appear successful when no class or mappings are available;
- long Pimcore stack traces dominate the settings view;
- the settings do not explain what a class, parent folder, object key, or field mapping means.

The integration must become an administrator-guided setup followed by a compact maintenance screen. Runtime users must be able to create a missing product and edit an existing product only when the integration is enabled.

## Goals

1. Guide an administrator through the first valid Pimcore configuration without requiring knowledge of technical class names, field types, parsers, or raw object IDs.
2. Discover available classes, object folders, and class fields through read-only legacy REST calls, while preserving manual entry as a fallback.
3. Remove CSV from the normal setup path and keep CSV header import only under advanced settings.
4. Use the Pimcore 6.6 `q` filter and `objectClass` parameter for EAN lookup.
5. Keep runtime creation available to ordinary logged-in users when integration is enabled.
6. Add safe editing of selected fields on existing Pimcore products.
7. Make diagnostics concise, dependency-aware, actionable, timed, and fully auditable without exposing the API key.
8. Require no PHP changes or Pimcore server deployment.

## Non-Goals

- Editing every Pimcore field type.
- Changing an existing product's EAN through PicOrgFTP-SQL.
- Managing Pimcore classes, permissions, folders, or users.
- Replacing Pimcore's CSV import for bulk product creation.
- Editing image assets or the existing image/FTP/SQL workflow through the Pimcore data editor.
- Automatically selecting a class or folder without administrator confirmation.

## Selected UX Approach

The interface combines two modes:

1. **First configuration:** a four-step administrator-only wizard.
2. **Later maintenance:** one compact settings screen with optional discovery controls.

The wizard is not shown to ordinary users. When setup is incomplete, ordinary users continue using the existing image workflow without Pimcore controls and see no missing-product prompt.

### Wizard Entry Rules

Add `setup_complete` to the normalized Pimcore configuration. It is separate from `enabled`.

- `setup_complete = false`: an administrator opening `Settings > Pimcore` sees the wizard.
- `setup_complete = true`: the compact settings screen is shown even when the administrator intentionally disables the integration.
- The wizard can set `setup_complete = true` only after a successful read-only configuration test and an explicit save.
- Existing configurations without the new key are treated as complete only when they contain an API key, class, parent ID, valid required EAN mapping, and object-key source. Otherwise they enter the wizard.

### Wizard Steps

#### 1. Connection

Visible controls:

- Pimcore base URL;
- API key;
- `Check connection and fetch data` command.

The command tests server info and class-list access with unsaved form values. It never stores or logs the submitted API key.

#### 2. Product Location

Visible controls:

- class dropdown populated from `/webservice/rest/classes`;
- target object-folder dropdown populated through object-list folder discovery;
- refresh commands;
- explicit manual-entry fallback for class name/ID and parent ID.

The parent folder is the folder in Pimcore's **Objects** tree under which the new product data object is created. It is not an image, asset, or filesystem folder. Store both the selected technical values and display metadata:

- `class_id` and `class_name`;
- `parent_id` and `parent_path`.

#### 3. Product Fields

Load the selected class definition and extract supported field definitions. The normal table contains only:

- use-field checkbox;
- label shown in PicOrgFTP-SQL;
- Pimcore field dropdown;
- required checkbox.

The backend continues storing the existing normalized mapping shape for compatibility, but the UI infers `type`, `parser`, and supported language from the class definition. Unsupported complex field types are visible as unavailable with a reason and cannot be selected.

EAN has special handling:

- attempt an exact case-insensitive match to a class field named `EAN`;
- otherwise require the administrator to select the EAN target field;
- save it as source `EAN`, mark it required, and lock that requirement;
- derive `existence_fields` from its Pimcore target;
- use the fixed object-key template `{EAN}`.

CSV import is absent from the normal table. `Advanced > Import CSV headers` remains available for migration from the old workflow and may suggest mappings, but it cannot save them without administrator review.

#### 4. Verify And Save

Run the complete read-only checklist using the unsaved wizard values. Enable `Save and enable integration` only when all required checks pass. Saving persists the API key through the existing encrypted-secret path, sets `setup_complete`, and stores the selected class, folder, and mappings.

## Compact Settings Screen

After setup, the Pimcore tab presents these sections on one screen:

1. Connection status, base URL, masked API key, and connection refresh.
2. Product location with class and folder dropdowns plus optional manual fallback.
3. Selected product fields with inferred technical types.
4. Commands: save, read-only test, test-create, and history.
5. Collapsed advanced settings.

Advanced settings contain:

- optional CSV header import;
- timeout, defaulting to 30 seconds and bounded to 1-120 seconds;
- TLS verification, defaulting to enabled;
- technical mapping details needed for migration or troubleshooting;
- read-only display of the derived `{EAN}` object-key template and EAN lookup target.

Normal runtime product creation and editing always publish immediately. The test-create workflow always overrides publication to false.

## Discovery Architecture

Add administrator-only, CSRF-protected routes that accept an unsaved connection snapshot without persisting it:

- `POST /api/settings/pimcore/discover/classes`;
- `POST /api/settings/pimcore/discover/folders`;
- `POST /api/settings/pimcore/discover/fields`.

Every response is a sanitized display model. The API key is never returned, included in endpoint text, or written to application logs.

### Class Discovery

Call `/webservice/rest/classes`, normalize legacy response variants, and return class ID/name pairs sorted by name. Field discovery calls `/webservice/rest/class/id/{class_id}` and returns technical name, display title when available, legacy element type, language capability, supported parser, and whether PicOrgFTP-SQL can edit the type.

### Folder Discovery

Call `/webservice/rest/object-list` with the JSON filter `q={"type":"folder"}` and bounded pagination. Object-list returns folder identities; load folder details as needed to obtain key/path labels. Return ID/path pairs sorted by path. A folder-discovery timeout leaves the manual parent-ID fallback usable and does not modify saved settings.

## Legacy REST Compatibility Fix

Replace SQL-like condition strings with a structured EAN filter. For one EAN target, encode:

```json
{"EAN": "5901234567890"}
```

For multiple explicitly configured targets, encode:

```json
{"$or": [{"EAN": "5901234567890"}, {"OTHER_EAN": "5901234567890"}]}
```

The object-list request uses:

- `q` for the JSON filter;
- `objectClass` for the selected technical class name;
- `limit=2` to detect duplicate results.

Never send the legacy raw `condition` parameter. Validate every field name before constructing the JSON object, and let URL encoding handle the serialized JSON.

References:

- Pimcore 6.6.11 object-list controller: `https://github.com/pimcore/pimcore/blob/v6.6.11/bundles/AdminBundle/Controller/Rest/Element/DataObjectController.php#L381-L420`
- Pimcore 6.6.11 JSON filter builder: `https://github.com/pimcore/pimcore/blob/v6.6.11/bundles/AdminBundle/Controller/Rest/Helper.php#L24-L117`

## Runtime Visibility And Lookup

When `enabled = false` or setup is incomplete:

- do not make Pimcore lookup calls;
- do not show the `Edit Pimcore data` button;
- do not show the missing-product creation prompt;
- leave the existing image, FTP, and SQL workflow unchanged.

When integration is enabled and setup is complete:

- show `Edit Pimcore data` beside the existing product-match command;
- keep it disabled until a valid 13-digit EAN lookup conclusively returns one existing product;
- hide/disable it again when EAN changes, lookup is running, no product exists, or an error occurs;
- show the create prompt only after a successful lookup conclusively returns no product;
- never interpret timeout, authentication, server, or malformed-response errors as a missing product.

## Create Missing Product

The existing create prompt remains available to ordinary logged-in users when integration is enabled.

1. User enters a valid EAN.
2. A debounced lookup returns no object.
3. The user confirms creation.
4. The modal shows the configured fields in mapping order with EAN locked.
5. `Save and publish` rechecks duplicates, creates the product under the selected parent, publishes it, verifies it by ID, and leaves the image workflow available.
6. `Cancel` closes the modal without a mutation request.

The object key is always derived from EAN. Duplicate detection remains the authoritative guard immediately before POST.

## Edit Existing Product

The edit modal is available to ordinary logged-in users only when lookup returned exactly one object.

1. Clicking `Edit Pimcore data` fetches the current object by ID.
2. The modal shows only configured mappings and pre-fills their current values.
3. EAN is read-only.
4. Store the loaded object's ID and modification timestamp/version marker.
5. `Cancel` performs no mutation request.
6. `Save and publish` re-fetches the object and rejects the update with HTTP 409 when the modification marker changed.
7. Merge changed configured elements into the complete freshly fetched object payload. Preserve unconfigured elements and required object metadata, set `published = true`, and send `PUT /webservice/rest/object/id/{id}`.
8. Re-fetch the object, verify the saved selected values, and report the object ID/path and stage timings.

The complete-payload merge is required because the legacy reverse mapper applies generic object properties from the request. A partial object payload must not accidentally clear parent or metadata.

References:

- Pimcore 6.6.11 update endpoint: `https://github.com/pimcore/pimcore/blob/v6.6.11/bundles/AdminBundle/Controller/Rest/Element/DataObjectController.php#L243-L331`
- Pimcore 6.6.11 concrete reverse mapping: `https://github.com/pimcore/pimcore/blob/v6.6.11/models/Webservice/Data/DataObject/Concrete.php#L77-L120`

## Diagnostics And Error Presentation

Checks use four states:

- `ok`: the check ran and passed;
- `error`: required behavior ran and failed;
- `warning`: behavior is usable but needs attention;
- `skipped`: prerequisites failed, so the check did not run.

Dependency rules prevent false success. Examples:

- missing class means field compatibility is `skipped`, not `ok`;
- empty mappings make form-schema and EAN mapping checks `error`;
- failed authentication skips every remote check after authentication;
- object-list is not tested until class and EAN mapping are valid.

The checklist shows a concise message and suggested correction. Endpoint, method, HTTP status, elapsed time, response excerpt, and technical error are placed in expandable details. Limit the visible response excerpt; keep the complete sanitized diagnostic in the persistent operation log. Pimcore stack traces never render as an unbounded inline paragraph.

## Logging And Audit

Create and edit operations reuse the persistent Pimcore audit model and numbered live events. Record:

- operation ID and kind (`test`, `manual_create`, or `manual_update`);
- username and EAN;
- Pimcore object ID/key/path when known;
- stage, method, endpoint path, HTTP status, severity, elapsed time, and stage time;
- cleanup or publication result;
- conflict and verification outcomes;
- sanitized response excerpts and suggested corrections.

The API key and any submitted secret remain redacted from request data, event text, endpoint strings, results, and persisted records.

## Permissions

- Only web administrators may open the wizard, discover schema/folders, save integration settings, run the settings write test, or view all Pimcore audit history.
- Ordinary logged-in users may perform runtime lookup, create, fetch selected edit data, and update when integration is enabled and complete.
- Pimcore's API user still enforces server-side read/create/update/delete permissions.

## Migration And Backward Compatibility

- Preserve existing encrypted API-key storage and blank-secret update behavior.
- Preserve valid existing mappings and expose their technical details under Advanced.
- Infer `setup_complete` for old valid configurations; incomplete configurations enter the wizard.
- Keep existing settings and runtime endpoints compatible where practical, adding fields rather than exposing secrets.
- Do not change the desktop application, FTP flow, SQL URL update, image processing, or browser-extension behavior.

## Testing Strategy

### Unit And Service Tests

- normalize and migrate `setup_complete`, class ID/path display metadata, and inferred mappings;
- encode safe `q` JSON and use `objectClass`, never `condition`/`className`;
- normalize class, folder, field, object-list, and object-detail response variants;
- infer supported element types/parsers and reject unsupported fields;
- merge selected edits into a complete object without changing unconfigured elements or parent metadata;
- detect modification conflicts;
- verify create and update values after write.

### Web Route Tests

- admin-only discovery and wizard-save routes;
- no secret exposure in discovery/settings/log responses;
- disabled/incomplete integration short-circuits runtime network calls;
- ordinary users can create and update only through runtime routes;
- update conflict returns structured HTTP 409;
- concise diagnostics preserve endpoint/status/timing details.

### UI Integrity And Browser Tests

- wizard appears only for administrators with incomplete setup;
- compact screen appears after setup, including when integration is intentionally disabled;
- advanced controls and CSV import are collapsed by default;
- class/folder/field selection works without manual technical entry;
- Pimcore runtime controls are absent when disabled;
- edit button is visible but disabled until exactly one object is found;
- create/edit cancel performs no mutation;
- create/edit save keeps the modal open while running and reports result without disrupting the image form;
- desktop and narrow mobile layouts have no overlaps or horizontal overflow.

### Real Pimcore Verification

1. Discover the actual class and target folder.
2. Select the EAN mapping and at least one additional editable field.
3. Complete the read-only checklist.
4. Run test-create with delete cleanup.
5. Run test-create while retaining an unpublished object, inspect it, then remove it.
6. Create a missing EAN through the main panel and confirm immediate publication.
7. Edit one configured field, verify it in Pimcore, and confirm unconfigured fields remain unchanged.
8. Simulate a concurrent modification and confirm the panel refuses to overwrite it.
9. Disable integration and confirm all runtime Pimcore controls and calls disappear.

## Acceptance Criteria

- A non-technical administrator can complete setup using discovered lists and field choices without a CSV file.
- No class, parent ID, type, parser, language, EAN target, or object-key template requires normal free-text entry.
- Manual class/parent input and CSV import remain available only as fallback/advanced controls.
- The live server no longer receives the rejected `condition` parameter.
- Diagnostics never report dependent checks as successful when prerequisites are missing.
- Ordinary users can create missing products and safely edit selected fields only while integration is enabled.
- `Cancel` sends no mutation; save publishes immediately.
- Updates preserve unconfigured Pimcore fields and reject concurrent changes.
- The API key remains encrypted at rest and absent from all normal responses and logs.
