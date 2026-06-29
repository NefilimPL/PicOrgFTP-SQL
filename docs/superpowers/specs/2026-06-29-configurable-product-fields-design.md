# Configurable Product Fields Design

## Goal

Allow administrators to configure the display label, visibility, and required state of every product field in both the desktop and web applications. Preserve the current behavior when no custom configuration is entered.

The configurable fields are:

- `name` — default label `Nazwa`, enabled and required by default;
- `type` — default label `Typ`, enabled and required by default;
- `model` — default label `Model`, enabled and required by default;
- `color1` — default label `Kolor 1`, enabled and required by default;
- `color2` — default label `Kolor 2`, enabled and optional by default;
- `color3` — default label `Kolor 3`, enabled and optional by default;
- `extra` — default label `Dodatek`, enabled and optional by default;
- `ean` — default label `EAN`, enabled and optional by default.

## Configuration model

Add one `product_fields` configuration object keyed by the canonical field names above. Each field has this normalized shape:

```json
{
  "label": "",
  "enabled": true,
  "required": false
}
```

An empty `label` means that the client must use its existing localized default label. A non-empty label is shared by the web and desktop clients. Label normalization trims whitespace and trailing `:` and `*` characters.

Normalization always returns all eight known fields, rejects unknown field keys, coerces `enabled` and `required` to booleans, and forces `required` to `false` when `enabled` is `false`. Missing or malformed configuration uses the defaults listed above.

The field order is fixed and is not user-configurable.

## Persistence and migration

The setting uses the existing configuration persistence boundary:

- in SQLite data mode, `save_config` stores it in the active SQLite application's configuration store;
- in legacy data mode, `save_config` stores it in `config.json`.

No separate settings table or external SQL dependency is introduced.

Existing `color_field_labels` values are migrated on read when an equivalent `product_fields` label is absent. Explicit `product_fields` values take precedence. New saves use `product_fields`; the legacy color-label key is no longer required by updated clients.

## Settings interfaces

Replace the current three color-label controls in both settings interfaces with a vertical list of all eight product fields.

Each list item contains:

1. the default field name;
2. an optional custom-label input;
3. an `Aktywne` switch;
4. a `Wymagane` switch.

Disabling `Aktywne` immediately clears, disables, and unchecks `Wymagane`. The saved normalized value therefore has `required=false`. Re-enabling the field does not silently restore its old required state; the administrator must select it again if needed.

The web list is responsive. Each field remains a separate row or card, while its switches may wrap below the label input on narrow screens. The desktop list uses one vertically stacked row per field within the existing settings window.

Saving applies the new configuration to the open product form without an application restart.

## Product form behavior

Both clients derive the label, visibility, required marker, and validation rules from normalized `product_fields`.

- An enabled field is displayed with its custom label or localized default label.
- A required enabled field includes `*` in its visible label.
- A disabled field and its surrounding label/container are hidden.
- Disabled values are cleared and treated as empty before lookups, validation, persistence, path construction, and filename construction.
- Validation errors use the effective visible label rather than a hard-coded field name.

The web client updates the native HTML `required` property for immediate browser feedback. Server-side validation remains authoritative and uses the same normalized configuration so a modified HTTP request cannot bypass disabled-field cleaning or required-field validation.

The desktop client updates its existing completeness checks, save/process actions, and form validation from the same normalized configuration.

## Disabled-field normalization

Before saving or processing a product, both workflows construct an effective product payload in which disabled fields are empty. Existing path helpers already omit empty name, type, model, and color segments.

Two existing technical fallbacks remain:

- disabled or empty EAN becomes `BRAK-EAN` where a filename or stored entry requires an EAN value;
- disabled or empty extra uses the existing no-extra placeholder where the workflow requires that segment.

Existing records are still readable and can populate enabled fields. Values in fields that are currently disabled are ignored and are only cleared from a record when that record is saved again.

## Data flow

1. Configuration loading normalizes `product_fields` and applies legacy color-label migration.
2. The web settings snapshot and desktop settings window read the normalized object.
3. An administrator edits and saves the vertical field list.
4. The existing configuration persistence layer writes the complete normalized object to SQLite or `config.json`, depending on data mode.
5. Both product forms refresh their labels, visible rows, and required rules.
6. Submission code cleans disabled values, validates enabled required fields, then passes the effective payload to existing record, path, filename, and processing code.

## Error handling

- Invalid top-level values fall back to the complete default configuration.
- Invalid per-field values fall back only for that field.
- Unknown field keys are ignored.
- A disabled field can never remain required after normalization.
- Custom labels containing only whitespace or suffix punctuation become empty and therefore use the default label.
- Persistence errors continue through the existing settings error handling and must not partially replace the in-memory configuration.

## Testing

Automated coverage will include:

- default and malformed configuration normalization;
- migration from `color_field_labels` and precedence of explicit new values;
- round-trip persistence through legacy configuration and the active SQLite config store;
- settings API snapshot and update behavior;
- cleaning disabled fields before validation, record persistence, path building, and filename building;
- dynamic required validation using effective labels;
- web form label, visibility, and native `required` updates;
- vertical, responsive web settings markup and all eight rows;
- desktop settings rows and immediate product-form refresh;
- regression coverage proving the default configuration retains the current required fields and visible labels.

The focused tests run first during test-driven implementation, followed by the complete test suite.
