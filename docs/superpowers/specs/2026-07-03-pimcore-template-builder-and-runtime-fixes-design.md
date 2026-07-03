# Pimcore Template Builder And Runtime Fixes Design

**Date:** 2026-07-03
**Status:** Approved design, awaiting written-spec review
**Target:** PicOrgFTP-SQL web panel on branch `dev`, Pimcore legacy REST API 6.6.x

## Context

The guided Pimcore setup and runtime create/edit implementation is present, but live use exposed four remaining problems:

1. The test-create form opens with empty fields instead of editable, field-specific sample values.
2. The `Edytuj dane Pimcore` button can overflow the narrow `Produkt` panel into the later-painted `Sloty` panel. A click can therefore appear to do nothing. The edit flow also waits for the remote object request before opening its modal, so an API error is only shown in the main form status.
3. Pimcore fields cannot be derived from product values through reusable templates, conditional text, transformations, or optional translation.
4. `http://10.10.0.5` is a real-looking default value in both configuration and UI fallbacks, so it is inserted even for new installations.

EAN lookup must search the entire configured Pimcore class regardless of object folder. The configured parent folder must affect only creation of a new object.

## Goals

1. Pre-fill every test-create field with a fresh, recognizable, type-compatible sample while keeping every field editable.
2. Keep all product action controls inside the `Produkt` panel at every supported viewport width and make edit loading and failures visibly responsive.
3. Add persistent per-field value templates with literal text, placeholders, conditional groups, controlled transformations, dependency ordering, and cycle detection.
4. Add optional per-template translation with an explicit target language and non-blocking fallback.
5. Make template sources extensible so a future SQL value provider can be added without redesigning the template language.
6. Remove the old Pimcore URL default without erasing an intentionally saved live address.
7. Preserve existing create, edit, audit, secret-redaction, FTP, SQL, image, and desktop behavior outside the stated scope.

## Non-Goals

- Adding multiple SQL connections in this change.
- Executing SQL queries from templates in this change.
- Allowing arbitrary Python, JavaScript, regular-expression execution, or unbounded expressions in templates.
- Automatically rewriting existing Pimcore values when an edit modal opens.
- Changing the Pimcore class, object-folder, permission, or API-key model.
- Moving or otherwise refactoring unrelated desktop translation UI.

Multiple SQL connections, selection of connections for existing jobs, and `{SQL:...}` sources form a separate future project. This design provides only the source-provider boundary required to add that project later.

## Selected Architecture

Use a backend-owned template engine and a browser-based builder. Store a readable template string rather than a client-only program or an opaque block tree. The backend is authoritative for parsing, validation, dependency analysis, sample generation, and rendering. The browser inserts supported syntax, requests previews, and displays structured errors and warnings.

This keeps templates portable across web flows, prevents the client and server from developing different semantics, and leaves an explicit extension point for future data providers.

### Components

The implementation will keep responsibilities separated:

- a focused template module parses and renders one template;
- a mapping resolver validates dependencies and renders configured fields in topological order;
- a source catalogue exposes built-in product values and mapped Pimcore values through stable identifiers and aliases;
- a sample generator creates type-compatible values for test-create and builder previews;
- a translation service uses the already configured provider and returns either translated text or a structured warning;
- Pimcore services continue owning lookup, create, fetch, update, conflict handling, and payload conversion;
- web routes enforce administrator/runtime permissions and expose sanitized builder and rendering models;
- the browser owns modal state, user edits, button layout, and visible loading/error feedback.

## Configuration Contract

Each normalized Pimcore field mapping gains three backward-compatible properties:

```json
{
  "value_template": "",
  "translate": false,
  "target_language": null
}
```

- `value_template` is empty when a field is entered manually or uses its existing default.
- `translate` controls translation of the rendered final string, not individual placeholders.
- `target_language` is stored per template. The builder initially suggests the mapping's Pimcore language, but the administrator may select a different target.

Old mappings normalize to these values without changing their behavior. Template configuration is available only for compatible text fields (`input`, `textarea`, and text-like `select` mappings). Numeric and checkbox mappings remain valid sources but do not expose a text-template builder as their output editor.

Invalid syntax, unknown sources, unsupported functions, invalid arguments, ambiguous aliases, and dependency cycles block settings save with a field-specific message.

## Source Catalogue

The initial catalogue contains:

- enabled product-form values: name, type, model, colors 1-3, extra, and EAN;
- every configured Pimcore mapping value available in the current create/edit form;
- values already rendered from other template mappings, provided the dependency graph is acyclic.

Friendly built-in aliases include `NAZWA`, `TYP`, `MODEL`, `KOLOR 1`, `KOLOR 2`, `KOLOR 3`, `DODATEK`, and `EAN`. Matching is case-insensitive. Technical product keys and Pimcore mapping sources are also accepted.

When two providers expose the same unqualified alias, the alias is rejected as ambiguous and the builder inserts a qualified source name. The namespace contract is stable:

- `PRODUCT:<key>` for product-form values;
- `PIMCORE:<source>` for mapped Pimcore form values;
- a future provider may add qualified names such as `SQL:<result-name>`.

The UI normally inserts the shortest unambiguous friendly alias. Renaming a visible label does not change the underlying technical source key.

## Template Language

### Literal Text And Placeholders

Everything outside template syntax is emitted literally. For example:

```text
{NAZWA} - {TYP} {KOLOR 1}(/{KOLOR 2})
```

with `VIVO`, `sideboard`, `white`, and `black` renders:

```text
VIVO - SIDEBOARD WHITE/BLACK
```

The casing of a placeholder is a convenience transformation when no explicit casing function is supplied:

- `{NAZWA}` converts the value to uppercase;
- `{Nazwa}` converts the value to title case;
- `{nazwa}` converts the value to lowercase;
- mixed casing preserves the source value;
- `keep` explicitly disables the shorthand, for example `{NAZWA|keep}`.

The casing rule applies to the source-name part after an optional namespace. Function names and arguments do not influence it.

### Conditional Groups

Parentheses define a conditional group:

```text
{KOLOR 1}(/{KOLOR 2})
```

The complete group, including all literal text and punctuation, is omitted when any placeholder required inside that group resolves to an empty value. Thus an empty color 2 produces `WHITE`, not `WHITE/`.

Conditional groups may be nested to a bounded depth. A group without a placeholder is invalid because it would have no condition. Literal parentheses, braces, backslashes, commas, colons, and quotation marks that would otherwise be parsed can be escaped with a backslash.

### Controlled Functions

Functions form a left-to-right pipeline after the source:

```text
{MODEL|trim|replace:"_"," "|upper}
```

The first release supports:

- `keep` - preserve casing and disable the placeholder-name casing shortcut;
- `trim` - remove leading and trailing whitespace;
- `normalize_spaces` - collapse whitespace runs to one space;
- `upper`, `lower`, `title`, `capitalize` - controlled case conversion;
- `replace:"old","new"` - literal replacement;
- `default:"text"` - use text when the current value is empty;
- `substring:start,length` - select a bounded fragment; length may be omitted;
- `truncate:length,"suffix"` - bound the result and append a suffix when shortened;
- `strip_diacritics` - convert accented characters where a Unicode decomposition exists;
- `slug` - lowercase, strip diacritics, replace non-alphanumeric runs with `-`, and trim separators;
- `number:decimals,"decimal-separator","group-separator"` - parse a numeric input and format it with bounded precision.

Arguments are quoted when they contain separators. Unknown functions, wrong argument counts, invalid numeric arguments, templates above the configured length limit, and nesting above the configured depth limit are validation errors. The language never evaluates arbitrary code.

### Dependency Resolution

A template may reference another mapped Pimcore source. The resolver builds a dependency graph and evaluates it in topological order. Direct and indirect cycles are rejected before saving settings. A missing optional runtime value resolves to an empty string; a missing required mapping is reported by the existing required-field validation after rendering.

## Builder UX

Every compatible mapping row in the guided setup and compact Pimcore settings gets a `Buduj tekst` command. It opens an administrator-only nested modal containing:

- the target field name and language;
- a searchable source list grouped by provider;
- buttons for supported transformations;
- an `Dodaj grupę warunkową` command;
- an editable template textarea;
- syntax help with examples;
- example/current source values;
- a live rendered preview;
- a `Tłumacz wynik` checkbox and target-language selector;
- structured validation errors and translation warnings;
- save and cancel commands.

The builder inserts syntax at the current text cursor but never prevents direct text editing. Saving the modal updates the mapping row; the normal Pimcore settings save remains the persistence boundary. Cancel discards modal changes.

An administrator preview route may validate and render an unsaved template using submitted sample values. It never persists the template or returns secrets.

## Runtime Rendering

### Test Create

Opening `Testowo dodaj obiekt` requests a fresh sample context. Every mapping gets a recognizable field-specific value where its type permits:

- EAN is a new valid 13-digit GTIN with a correct check digit;
- numeric mappings receive distinct valid numbers;
- checkbox mappings receive a valid boolean representation;
- text mappings receive a value containing a sanitized field identity and a per-opening token;
- select mappings use a discovered option when available, then a configured default, and otherwise a recognizable editable sample.

Templates are rendered from that context in dependency order. Optional translations are attempted after rendering. All resulting fields remain editable. `Wygeneruj ponownie` replaces the current values only after explicit confirmation when the user has modified them.

The operation submits exactly the values currently visible in the form. Existing cleanup choices, unpublished test creation, duplicate checks, live events, and audit behavior remain unchanged.

### Create Missing Product

When lookup conclusively reports a missing EAN, the create modal receives a source context made from the current product form plus mapped Pimcore inputs. Saved templates are rendered automatically before the modal is presented. The user can edit every generated output except the existing read-only EAN rule.

The create request submits the displayed values. The backend still applies type parsers, required-field checks, duplicate detection, configured class, configured creation parent, publication, verification, redaction, and audit logging.

### Edit Existing Product

The edit modal opens immediately in a visible loading state, then fetches the object. It displays current Pimcore values without automatically applying templates. Each templated text field has a `Przelicz pole` command that renders only that field and its dependencies from the current edit-form/product context. The user decides whether to keep the generated value and may edit it before save.

Fetch failures are shown inside the already-open modal with a retry command. The main form may also receive a concise status, but it is not the only feedback channel. Existing EAN immutability, full-payload merge, optimistic conflict check, publication, verification, and audit behavior remain unchanged.

## Translation

Translation uses the provider already stored under the application's translation settings. The backend translation service supports the same provider choices as the local field-translation feature and keeps provider credentials server-side.

For a saved template with translation enabled:

1. render and normalize the complete source text;
2. send that text to the configured provider using the template's target language;
3. put the translated result into the editable form field on success;
4. retain the source text and return a structured warning on timeout, authentication failure, provider error, or empty response.

Translation failure never blocks creation or editing. Users can retry, correct, or accept the source text. Logs and API responses redact provider and Pimcore secrets.

Ordinary authenticated users may render only templates already saved in the active Pimcore configuration. Only administrators may preview arbitrary unsaved templates or modify template definitions.

## Pimcore Runtime Fixes

### Lookup Scope And Object Identity

EAN lookup and duplicate checks call object-list with only the structured EAN `q` filter, configured `objectClass`, and limit. They do not send the configured parent folder or add a path condition. Regression tests assert this invariant.

Creation continues to set `parentId` from the configured target folder. Fetch and update continue to address the selected object directly by ID.

Object-list identity normalization accepts the documented/current response shape and known legacy key variants. The edit button is enabled only when lookup returns exactly one object with a valid positive ID. A malformed match becomes an explicit availability error rather than an enabled button whose handler silently returns.

### Product Action Layout

The current three equal grid columns conflict with the edit button's fixed minimum width inside a panel capped at 360 px. Replace this constraint with a wrapping, content-safe layout. No action may exceed the product form's content box. At narrow widths every action may occupy a full row. Remove the edit button's conflicting fixed minimum width.

The later `Sloty` grid area must never paint over or intercept any product action. Desktop and mobile CSS integrity checks cover the relevant grid/flex rules and overflow behavior.

### Edit Feedback

Clicking edit immediately:

1. validates the stored positive object ID;
2. opens the edit modal;
3. displays a loading state and disables submit;
4. fetches current data;
5. renders fields and enables submit, or renders an in-modal error with retry.

The button cannot initiate duplicate concurrent fetches. Closing the modal invalidates any late response so stale data cannot reopen or overwrite a later selection.

## Pimcore URL Defaults And Migration

The normalized default `base_url` becomes an empty string. The wizard and compact settings use only the HTML placeholder:

```text
http://twoj-adres-pimcore.example
```

The placeholder is never submitted or persisted as a value.

Migration clears an existing `http://10.10.0.5` only when the integration is incomplete and there is no saved API key, class, or parent indicating an intentional configuration. A complete or otherwise populated existing configuration preserves its stored URL because `10.10.0.5` may be a real server at some installations.

No source file, fallback expression, default factory, generated settings template, or documentation instruction may reintroduce `10.10.0.5` as a default example.

## API Boundaries

Exact route names may follow existing naming conventions, but the responsibilities are fixed:

- administrator-only validation/preview of an unsaved template and settings snapshot;
- administrator-only generation of a fresh test-create sample form;
- authenticated rendering of saved runtime templates for create or an explicitly selected edit field;
- existing authenticated create, fetch, and update routes;
- existing administrator-only settings persistence and test-create operation routes.

All mutation routes remain CSRF-protected under the application's current mechanism. Responses contain source catalogues, rendered values, validation issues, and warnings, but never Pimcore or translation API keys.

## Error Handling

- Syntax errors include a stable code, target mapping, character position where possible, concise message, and suggested correction.
- Dependency errors name the cycle or missing/ambiguous source chain.
- Translation errors are warnings with the source result retained.
- Pimcore lookup errors are never interpreted as a missing product.
- A lookup match without a usable ID is an explicit error and keeps edit disabled.
- Edit fetch failures remain in the edit modal and support retry without changing the product form.
- Template rendering cannot bypass existing parser, required-field, duplicate, conflict, or Pimcore payload validation.

## Testing Strategy

### Template Unit Tests

- literal text and punctuation;
- friendly, technical, qualified, and ambiguous source resolution;
- uppercase/title/lowercase/preserve shortcuts;
- every supported function and invalid argument shape;
- conditional groups with empty and populated values, escaping, nesting, and depth bounds;
- unknown sources/functions and malformed syntax with positions;
- dependency order, direct cycles, and indirect cycles;
- output and input size limits;
- future provider registration through the source-catalogue interface.

### Configuration And Sample Tests

- old mappings gain empty template defaults without behavior changes;
- valid template/translation fields round-trip through normalization and public settings;
- invalid mappings cannot be saved;
- sample values are fresh per generation, field-specific, parser-compatible, and editable in the UI model;
- generated EAN values contain 13 digits, pass check-digit validation, and differ across generations;
- old URL defaults normalize/migrate according to incomplete versus intentional configuration state.

### Pimcore Service And Route Tests

- lookup and duplicate checks use class scope without parent/path filters;
- create payload alone uses the configured parent;
- object-list identity variants produce a positive ID or an explicit error;
- administrator-only unsaved preview and test-sample routes;
- ordinary users render only saved runtime templates;
- no secret exposure in preview, render, warning, settings, or audit responses;
- translation success and source-text fallback;
- create/edit parsers and required checks still run after generation;
- existing update conflict and complete-payload preservation remain intact.

### UI And Layout Tests

- builder controls exist only for compatible fields and remain administrator-only;
- direct template editing, insertion commands, preview, cancel, and save behavior;
- test-create opens populated and supports regeneration and manual edits;
- create templates render automatically while edit templates require `Przelicz pole`;
- edit modal opens before fetch completion and renders retryable errors;
- stale edit responses are ignored after close or product change;
- product actions remain inside the product section at desktop, tablet, and mobile widths;
- the edit button cannot be enabled without a positive object ID;
- the URL example is a placeholder rather than a value.

### Regression Verification

Run the focused Pimcore/config/web/UI tests first, followed by the complete test suite. Real-server verification should confirm class-wide lookup across at least two folders, creation under the configured parent, editable generated values, edit recalculation by explicit action, and non-blocking translation failure.

## Acceptance Criteria

- Opening test-create produces a fresh editable value for every field without requiring initial manual entry.
- `{NAZWA} - {TYP} {KOLOR 1}(/{KOLOR 2})` produces the agreed output and removes the complete optional fragment when color 2 is empty.
- Literal text, conditional fragments, all documented functions, dependencies, escaping, and validation behave identically in preview and runtime rendering.
- Templates are saved per mapping; create and test apply them automatically; edit applies them only on explicit recalculation.
- Translation has a per-template language, uses the configured provider, and falls back to editable source text with a warning.
- The edit button never overlaps `Sloty`, gives immediate loading feedback, and shows fetch failures in its modal.
- Existing products are found anywhere in the configured class; only new objects use the configured parent folder.
- New installations do not receive `http://10.10.0.5` as a value, while intentional existing configurations are not erased.
- The design can accept a future qualified SQL source provider without changing stored template syntax or the Pimcore mapping contract.
- Existing security, redaction, audit, conflict, publication, FTP, SQL, image, and desktop behavior remains regression-tested.
