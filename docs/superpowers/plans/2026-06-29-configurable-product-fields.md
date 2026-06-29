# Configurable Product Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all eight product fields configurable by label, visibility, and required state in both desktop and web clients while preserving current defaults and persistence behavior.

**Architecture:** A new dependency-light `product_fields` module owns the canonical schema, migration, value cleaning, and required-field checks. Existing configuration loading and saving persists the normalized object through SQLite in SQLite mode and `config.json` in legacy mode. Both clients consume that normalized object, apply it to their forms, and clean disabled values before any lookup, validation, filename/path construction, or record save.

**Tech Stack:** Python 3, Tkinter/ttk, FastAPI, vanilla JavaScript/CSS, unittest/pytest, SQLite configuration store.

---

## File structure

- Create `picorgftp_sql/product_fields.py`: canonical field definitions, normalization, legacy label migration, effective value cleaning, and missing-required-field helpers.
- Create `tests/test_product_fields.py`: focused unit tests for the shared model.
- Modify `picorgftp_sql/common.py`: register the `product_fields` configuration key and defaults.
- Modify `picorgftp_sql/config.py`: normalize, load, migrate, and persist the new setting.
- Modify `tests/test_config.py`: configuration integration and SQLite round-trip coverage.
- Modify `picorgftp_sql/web_workflow.py`: apply field settings before validation and processing.
- Modify `picorgftp_sql/web_data.py`: expose/update settings and clean direct entry saves.
- Modify `picorgftp_sql/web/app.py`: pass the active settings through all server-side product operations.
- Modify `tests/test_web_workflow.py`, `tests/test_web_data_users.py`, and `tests/test_web_smoke_ci.py`: backend behavior and API coverage.
- Modify `picorgftp_sql/web/static/index.html`, `app.js`, and `app.css`: dynamic product form and vertical settings list.
- Modify `tests/test_web_ui_integrity.py` and `tests/test_source_integrity.py`: static UI contract coverage.
- Modify `picorgftp_sql/app.py`: desktop product-form state, validation, and vertical settings rows.
- Modify `picorgftp_sql/Localization/pl.json`, `eng.json`, and `ua.json`: settings-list labels and hints.
- Modify `tests/test_app_lookup_state.py` and `tests/test_desktop_smoke_ci.py`: desktop helper and localization coverage.
- Modify `README.md`: document the new configurable field behavior.

### Task 1: Shared product-field model and persistence

**Files:**
- Create: `picorgftp_sql/product_fields.py`
- Create: `tests/test_product_fields.py`
- Modify: `picorgftp_sql/common.py:202-210,256-325`
- Modify: `picorgftp_sql/config.py:5-54,125-137,220-310,313-490,525-605`
- Modify: `tests/test_config.py:7-45`

- [ ] **Step 1: Write failing shared-model tests**

```python
# tests/test_product_fields.py
from picorgftp_sql.product_fields import (
    PRODUCT_FIELD_KEYS,
    effective_product_values,
    missing_required_fields,
    normalize_product_fields,
)


def test_defaults_preserve_current_form_contract():
    settings = normalize_product_fields(None)
    assert tuple(settings) == PRODUCT_FIELD_KEYS
    assert all(item["enabled"] for item in settings.values())
    assert [key for key, item in settings.items() if item["required"]] == [
        "name", "type", "model", "color1"
    ]


def test_normalization_migrates_legacy_labels_and_rejects_unknown_fields():
    settings = normalize_product_fields(
        {
            "name": {"label": " Produkt*: ", "enabled": "yes", "required": 1},
            "color1": {"enabled": False, "required": True},
            "unknown": {"enabled": True},
        },
        legacy_color_labels={"color2": " Front: "},
    )
    assert settings["name"] == {"label": "Produkt", "enabled": True, "required": True}
    assert settings["color1"]["required"] is False
    assert settings["color2"]["label"] == "Front"
    assert "unknown" not in settings


def test_disabled_values_are_cleared_and_required_labels_are_effective():
    settings = normalize_product_fields(
        {
            "name": {"label": "Kolekcja", "enabled": True, "required": True},
            "type": {"enabled": False, "required": True},
            "ean": {"enabled": False},
        }
    )
    values = effective_product_values(
        {"name": "", "type_name": "KOMODA", "ean": "5901234567890"}, settings
    )
    assert values["type_name"] == ""
    assert values["ean"] == ""
    assert missing_required_fields(values, settings) == [("name", "Kolekcja")]
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `python -m pytest tests/test_product_fields.py -q`

Expected: FAIL because `picorgftp_sql.product_fields` does not exist.

- [ ] **Step 3: Implement the canonical model**

```python
# picorgftp_sql/product_fields.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PRODUCT_FIELDS_KEY = "product_fields"
LEGACY_COLOR_FIELD_LABELS_KEY = "color_field_labels"
PRODUCT_FIELD_KEYS = ("name", "type", "model", "color1", "color2", "color3", "extra", "ean")
PRODUCT_FIELD_VALUE_KEYS = {
    "name": "name",
    "type": "type_name",
    "model": "model",
    "color1": "color1",
    "color2": "color2",
    "color3": "color3",
    "extra": "extra",
    "ean": "ean",
}
DEFAULT_PRODUCT_FIELD_LABELS = {
    "name": "Nazwa",
    "type": "Typ",
    "model": "Model",
    "color1": "Kolor 1",
    "color2": "Kolor 2",
    "color3": "Kolor 3",
    "extra": "Dodatek",
    "ean": "EAN",
}
DEFAULT_REQUIRED_FIELDS = frozenset({"name", "type", "model", "color1"})


def _clean_label(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().rstrip(":*").strip()


def _bool_value(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def default_product_fields() -> dict[str, dict[str, object]]:
    return {
        key: {"label": "", "enabled": True, "required": key in DEFAULT_REQUIRED_FIELDS}
        for key in PRODUCT_FIELD_KEYS
    }


def normalize_product_fields(
    raw_settings: object,
    *,
    legacy_color_labels: object = None,
) -> dict[str, dict[str, object]]:
    raw = raw_settings if isinstance(raw_settings, Mapping) else {}
    legacy = legacy_color_labels if isinstance(legacy_color_labels, Mapping) else {}
    normalized = default_product_fields()
    for key in PRODUCT_FIELD_KEYS:
        item = raw.get(key)
        item = item if isinstance(item, Mapping) else {}
        if "label" in item:
            label = _clean_label(item.get("label"))
        elif key in {"color1", "color2", "color3"}:
            label = _clean_label(legacy.get(key))
        else:
            label = ""
        enabled = _bool_value(item.get("enabled"), True)
        required = enabled and _bool_value(item.get("required"), key in DEFAULT_REQUIRED_FIELDS)
        normalized[key] = {"label": label, "enabled": enabled, "required": required}
    return normalized


def effective_product_values(
    raw_values: Mapping[str, Any],
    raw_settings: object,
) -> dict[str, Any]:
    values = dict(raw_values)
    settings = normalize_product_fields(raw_settings)
    for key, value_key in PRODUCT_FIELD_VALUE_KEYS.items():
        if not settings[key]["enabled"]:
            values[value_key] = ""
    return values


def effective_field_label(key: str, raw_settings: object) -> str:
    settings = normalize_product_fields(raw_settings)
    return str(settings[key]["label"] or DEFAULT_PRODUCT_FIELD_LABELS[key])


def missing_required_fields(
    raw_values: Mapping[str, Any],
    raw_settings: object,
) -> list[tuple[str, str]]:
    settings = normalize_product_fields(raw_settings)
    values = effective_product_values(raw_values, settings)
    missing = []
    for key, value_key in PRODUCT_FIELD_VALUE_KEYS.items():
        if settings[key]["required"] and not str(values.get(value_key) or "").strip():
            missing.append((key, effective_field_label(key, settings)))
    return missing
```

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run: `python -m pytest tests/test_product_fields.py -q`

Expected: `3 passed`.

- [ ] **Step 5: Write failing configuration integration tests**

```python
# append to tests/test_config.py
from copy import deepcopy
from unittest.mock import patch

from picorgftp_sql.product_fields import PRODUCT_FIELDS_KEY
from picorgftp_sql.sqlite_store import SqliteStore


def test_merge_raw_config_migrates_color_labels_to_product_fields():
    target = deepcopy(common.DEFAULT_CONFIG)
    merged = config._merge_raw_config(
        {"color_field_labels": {"color1": "Korpus"}}, target
    )
    assert merged[PRODUCT_FIELDS_KEY]["color1"]["label"] == "Korpus"
    assert merged[PRODUCT_FIELDS_KEY]["name"]["required"] is True


def test_save_config_persists_normalized_product_fields_to_sqlite():
    payload = deepcopy(common.DEFAULT_CONFIG)
    payload[PRODUCT_FIELDS_KEY] = {"model": {"enabled": False, "required": True}}
    store = unittest.mock.Mock(database_path="test.sqlite")
    with patch.object(config, "_active_sqlite_store", return_value=store):
        config.save_config(payload)
    saved = store.save_config.call_args.args[0][PRODUCT_FIELDS_KEY]
    assert saved["model"] == {"label": "", "enabled": False, "required": False}


def test_save_config_roundtrips_product_fields_through_sqlite(tmp_path):
    payload = deepcopy(common.DEFAULT_CONFIG)
    payload[PRODUCT_FIELDS_KEY] = {
        "name": {"label": "Kolekcja", "enabled": True, "required": True}
    }
    store = SqliteStore(tmp_path / "product-fields.sqlite")
    with patch.object(config, "_active_sqlite_store", return_value=store):
        config.save_config(payload)
    assert store.load_config()[PRODUCT_FIELDS_KEY]["name"]["label"] == "Kolekcja"
```

- [ ] **Step 6: Run the integration tests and confirm RED**

Run: `python -m pytest tests/test_config.py -q`

Expected: FAIL because `DEFAULT_CONFIG`, config merge, and config save do not yet own `product_fields`.

- [ ] **Step 7: Wire normalization into defaults, load, migration, and save**

In `common.py`, import `PRODUCT_FIELDS_KEY` and `default_product_fields` from `product_fields`, then add:

```python
DEFAULT_CONFIG.setdefault(PRODUCT_FIELDS_KEY, default_product_fields())
```

In `config.py`, import `normalize_product_fields` and replace each `COLOR_FIELD_LABELS_KEY` load/save branch with:

```python
config_copy[PRODUCT_FIELDS_KEY] = normalize_product_fields(
    raw_config.get(PRODUCT_FIELDS_KEY),
    legacy_color_labels=raw_config.get(COLOR_FIELD_LABELS_KEY),
)
```

Add this key to initial configuration creation and `save_config` payloads:

```python
PRODUCT_FIELDS_KEY: normalize_product_fields(
    config.get(PRODUCT_FIELDS_KEY),
    legacy_color_labels=config.get(COLOR_FIELD_LABELS_KEY),
),
```

Keep `_normalize_color_field_labels` as a compatibility helper for old callers during this task, but stop exposing it as the active UI configuration.

- [ ] **Step 8: Run focused configuration tests and confirm GREEN**

Run: `python -m pytest tests/test_product_fields.py tests/test_config.py -q`

Expected: all selected tests pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add picorgftp_sql/product_fields.py picorgftp_sql/common.py picorgftp_sql/config.py tests/test_product_fields.py tests/test_config.py
git commit -m "feat: add configurable product field model"
```

### Task 2: Server-side cleaning, validation, and settings API

**Files:**
- Modify: `picorgftp_sql/web_workflow.py:80-100,203-234,363-389`
- Modify: `picorgftp_sql/web_data.py:20-40,263-277,1277-1302,1467-1520,1592-1660`
- Modify: `picorgftp_sql/web/app.py:35-115,1701-1748,2495-2630,3494-3519,3893-3914`
- Modify: `tests/test_web_workflow.py:10-23,186-218`
- Modify: `tests/test_web_data_users.py:586-705`
- Modify: `tests/test_web_smoke_ci.py:408-431`

- [ ] **Step 1: Write failing workflow tests for configurable validation and cleaning**

```python
# append to tests/test_web_workflow.py
def test_validation_uses_custom_required_labels_and_ignores_disabled_fields(self) -> None:
    settings = {
        "name": {"label": "Kolekcja", "enabled": True, "required": True},
        "type": {"enabled": False, "required": True},
        "model": {"enabled": True, "required": False},
        "color1": {"enabled": False, "required": True},
    }
    form = WebProductForm(name="", type_name="KOMODA", model="", color1="BIALY")
    assert validate_product_form(form, settings) == ["Pole „Kolekcja” jest wymagane."]
    payload = normalized_product_payload(form, settings)
    assert payload["type_name"] == ""
    assert payload["colors"] == ["", "", ""]


def test_disabled_ean_skips_format_validation(self) -> None:
    settings = {"ean": {"enabled": False, "required": True}}
    form = WebProductForm(name="N", type_name="T", model="M", color1="C", ean="123")
    assert validate_product_form(form, settings) == []
    assert normalized_product_payload(form, settings)["ean"] == "BRAK-EAN"
```

- [ ] **Step 2: Run workflow tests and confirm RED**

Run: `python -m pytest tests/test_web_workflow.py -q`

Expected: FAIL because workflow functions do not accept field settings.

- [ ] **Step 3: Implement settings-aware workflow helpers**

Add to `web_workflow.py`:

```python
from dataclasses import asdict, replace
from .product_fields import (
    effective_product_values,
    missing_required_fields,
    normalize_product_fields,
)


def effective_product_form(form: WebProductForm, field_settings=None) -> WebProductForm:
    values = effective_product_values(asdict(form), normalize_product_fields(field_settings))
    return replace(form, **{key: values[key] for key in asdict(form) if key in values})


def validate_product_form(form: WebProductForm, field_settings=None) -> list[str]:
    settings = normalize_product_fields(field_settings)
    effective = effective_product_form(form, settings)
    errors = [
        f"Pole „{label}” jest wymagane."
        for _key, label in missing_required_fields(asdict(effective), settings)
    ]
    ean = _clean(effective.ean)
    if ean and ean != NO_EAN_PLACEHOLDER and (not ean.isdigit() or len(ean) != 13):
        errors.append("EAN musi miec 13 cyfr albo zostac pusty.")
    return errors
```

Update `normalized_product_payload` to accept `field_settings=None`. Add the same optional keyword to `process_web_uploads` after `allow_empty`, and use `effective_product_form` before normalization, validation, directory building, and filename building.

- [ ] **Step 4: Run workflow tests and confirm GREEN**

Run: `python -m pytest tests/test_web_workflow.py -q`

Expected: all workflow tests pass.

- [ ] **Step 5: Write failing settings update and direct-save tests**

```python
# append to tests/test_web_data_users.py
def test_update_settings_normalizes_and_saves_product_fields(self) -> None:
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    saved = []
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "save_config", side_effect=lambda payload, **_kwargs: saved.append(payload)),
        patch.object(web_data, "settings_snapshot", return_value={}),
    ):
        web_data.update_settings(
            {"app": {"product_fields": {"model": {"label": "Wersja", "enabled": False, "required": True}}}}
        )
    assert saved[0]["product_fields"]["model"] == {
        "label": "Wersja", "enabled": False, "required": False
    }


def test_save_web_entry_clears_disabled_values_before_persistence(self) -> None:
    cfg = {"product_fields": {"type": {"enabled": False}}}
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "save_ean_entry", return_value={"ok": True}) as save_entry,
    ):
        web_data.save_web_entry(
            {"name": "N", "type_name": "KOMODA", "model": "M", "color1": "C"}
        )
    assert save_entry.call_args.args[2] == ""
```

- [ ] **Step 6: Run backend settings tests and confirm RED**

Run: `python -m pytest tests/test_web_data_users.py -q`

Expected: FAIL because settings snapshots and saves still use `color_field_labels`.

- [ ] **Step 7: Expose, update, and enforce `product_fields` on the backend**

In `web_data.py`:

```python
from .product_fields import (
    PRODUCT_FIELDS_KEY,
    effective_product_values,
    missing_required_fields,
    normalize_product_fields,
)
```

Return `product_fields` from `load_web_data()` and `settings_snapshot()`. In `update_settings()` normalize the submitted object before calling `save_config`:

```python
if PRODUCT_FIELDS_KEY in app_payload:
    cfg[PRODUCT_FIELDS_KEY] = normalize_product_fields(app_payload.get(PRODUCT_FIELDS_KEY))
```

At the start of `save_web_entry`, clean the payload and enforce required fields:

```python
field_settings = normalize_product_fields(config.CONFIG.get(PRODUCT_FIELDS_KEY))
payload = effective_product_values(payload, field_settings)
missing = missing_required_fields(payload, field_settings)
if missing:
    raise ValueError(" ".join(f"Pole „{label}” jest wymagane." for _key, label in missing))
```

In `web/app.py`, compute active field settings once per process job, replace the submitted `WebProductForm` with `effective_product_form`, and pass the settings into `validate_product_form`, `normalized_product_payload`, and `process_web_uploads`. Apply the same cleaning in `/api/entries/save` through `save_web_entry`.

- [ ] **Step 8: Run backend tests and confirm GREEN**

Run: `python -m pytest tests/test_web_workflow.py tests/test_web_data_users.py tests/test_web_smoke_ci.py -q`

Expected: all selected tests pass.

- [ ] **Step 9: Commit Task 2**

```bash
git add picorgftp_sql/web_workflow.py picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_web_workflow.py tests/test_web_data_users.py tests/test_web_smoke_ci.py
git commit -m "feat: enforce product field settings on web backend"
```

### Task 3: Web form and vertical settings list

**Files:**
- Modify: `picorgftp_sql/web/static/index.html:30-66`
- Modify: `picorgftp_sql/web/static/app.js:1-50,1081-1178,1539-1589,4106-4118,4675-4718,4860-4920,5466-5627`
- Modify: `picorgftp_sql/web/static/app.css:759-805,1790-1822`
- Modify: `tests/test_web_ui_integrity.py:17-108`
- Modify: `tests/test_source_integrity.py:48-90`

- [ ] **Step 1: Write failing static UI contract tests**

```python
# append to tests/test_web_ui_integrity.py
def test_all_product_fields_have_dynamic_containers_and_labels(self) -> None:
    html = _parse(INDEX_HTML)
    canonical = {"name", "type", "model", "color1", "color2", "color3", "extra", "ean"}
    containers = {
        attrs.get("data-product-field")
        for _tag, attrs in html.tags
        if attrs.get("data-product-field")
    }
    labels = {
        attrs.get("data-product-field-label")
        for _tag, attrs in html.tags
        if attrs.get("data-product-field-label")
    }
    assert canonical <= containers
    assert canonical <= labels


def test_web_settings_builds_vertical_product_field_rows(self) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    css = (ROOT / "picorgftp_sql" / "web" / "static" / "app.css").read_text(encoding="utf-8")
    assert "function productFieldSettingsList" in source
    assert 'className = "product-field-settings-list"' in source
    assert 'className = "product-field-settings-row"' in source
    assert ".product-field-settings-list" in css
    assert ".product-field-settings-row" in css
```

- [ ] **Step 2: Run UI integrity tests and confirm RED**

Run: `python -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py -q`

Expected: FAIL because only color labels are dynamic and no settings list exists.

- [ ] **Step 3: Make every product field dynamically addressable**

Change each product field label in `index.html` to this pattern, using `type` as the canonical key while retaining `type_name` as the input name:

```html
<label data-product-field="name">
  <span data-product-field-label="name">Nazwa *</span>
  <input name="name" autocomplete="off" spellcheck="false" required>
</label>
```

Apply the same structure to type, model, colors, extra, and EAN.

- [ ] **Step 4: Replace color-only JavaScript state with normalized product-field state**

Use these client definitions in `app.js`:

```javascript
const productFieldDefinitions = {
  name: { input: "name", label: "Nazwa", required: true },
  type: { input: "type_name", label: "Typ", required: true },
  model: { input: "model", label: "Model", required: true },
  color1: { input: "color1", label: "Kolor 1", required: true },
  color2: { input: "color2", label: "Kolor 2", required: false },
  color3: { input: "color3", label: "Kolor 3", required: false },
  extra: { input: "extra", label: "Dodatek", required: false },
  ean: { input: "ean", label: "EAN", required: false },
};

function normalizedProductFields(raw = {}) {
  return Object.fromEntries(Object.entries(productFieldDefinitions).map(([key, defaults]) => {
    const item = raw?.[key] || {};
    const enabled = item.enabled !== false;
    return [key, {
      label: cleanDisplayLabel(item.label),
      enabled,
      required: enabled && ("required" in item ? Boolean(item.required) : defaults.required),
    }];
  }));
}

function applyProductFieldSettings() {
  state.productFields = normalizedProductFields(state.productFields);
  for (const [key, definition] of Object.entries(productFieldDefinitions)) {
    const item = state.productFields[key];
    const container = document.querySelector(`[data-product-field="${key}"]`);
    const label = document.querySelector(`[data-product-field-label="${key}"]`);
    const input = productForm.elements[definition.input];
    container.hidden = !item.enabled;
    input.disabled = !item.enabled;
    input.required = item.enabled && item.required;
    if (!item.enabled) input.value = "";
    label.textContent = `${item.label || definition.label}${item.required ? " *" : ""}`;
  }
  findByEanButton.hidden = !state.productFields.ean.enabled;
  updateFieldWarnings();
}
```

Load `payload.product_fields` in bootstrap, data refresh, and settings-save paths. Call `applyProductFieldSettings()` after bootstrap, refresh, filling an entry, resetting the form, and saving settings so hidden fields cannot retain loaded values.

- [ ] **Step 5: Build the vertical web settings list and payload**

```javascript
function productFieldSettingsList(settings = {}) {
  const list = document.createElement("div");
  list.className = "product-field-settings-list wide-field";
  const normalized = normalizedProductFields(settings);
  for (const [key, definition] of Object.entries(productFieldDefinitions)) {
    const item = normalized[key];
    const row = document.createElement("div");
    const title = document.createElement("strong");
    const labelField = inputField(`product_field_${key}_label`, "Wlasna nazwa", item.label, {
      placeholder: definition.label,
    });
    const enabled = checkField(`product_field_${key}_enabled`, "Aktywne", item.enabled);
    const required = checkField(`product_field_${key}_required`, "Wymagane", item.required);
    const enabledInput = enabled.querySelector("input");
    const requiredInput = required.querySelector("input");
    row.className = "product-field-settings-row";
    row.dataset.productFieldSetting = key;
    title.textContent = definition.label;
    const sync = () => {
      requiredInput.disabled = !enabledInput.checked;
      if (!enabledInput.checked) requiredInput.checked = false;
    };
    enabledInput.addEventListener("change", sync);
    sync();
    row.append(title, labelField, enabled, required);
    list.appendChild(row);
  }
  return list;
}

function collectProductFieldSettings(form) {
  const data = new FormData(form);
  return Object.fromEntries(Object.keys(productFieldDefinitions).map((key) => [key, {
    label: data.get(`product_field_${key}_label`) || "",
    enabled: data.has(`product_field_${key}_enabled`),
    required: data.has(`product_field_${key}_required`),
  }]));
}
```

Replace the `Nazwy pol kolorow` group with `Pola produktu` and submit the result under `app.product_fields`.

- [ ] **Step 6: Add responsive list styles**

```css
.product-field-settings-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.product-field-settings-row {
  display: grid;
  grid-template-columns: minmax(110px, 0.6fr) minmax(220px, 1fr) minmax(130px, 0.5fr) minmax(130px, 0.5fr);
  gap: 10px;
  align-items: end;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
}

@media (max-width: 760px) {
  .product-field-settings-row {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 7: Run static and web smoke tests and confirm GREEN**

Run: `python -m pytest tests/test_web_ui_integrity.py tests/test_source_integrity.py tests/test_web_smoke_ci.py -q`

Expected: all selected tests pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py tests/test_source_integrity.py
git commit -m "feat: add web product field settings list"
```

### Task 4: Desktop product form and settings list

**Files:**
- Modify: `picorgftp_sql/app.py:1-85,1420-1546,3701-3908,4040-4104,6595-6650,6799-6840,6990-7046,8178-8805,10190-10320`
- Modify: `tests/test_app_lookup_state.py:54-75,168-190`
- Modify: `tests/test_source_integrity.py`

- [ ] **Step 1: Write failing desktop helper tests with lightweight stubs**

```python
# append to tests/test_app_lookup_state.py
class _Var:
    def __init__(self, value=""):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


@unittest.skipIf(App is None, f"App import unavailable: {APP_IMPORT_ERROR}")
class ProductFieldSettingsTests(unittest.TestCase):
    def test_missing_required_fields_use_desktop_custom_label(self) -> None:
        harness = type("Harness", (), {})()
        harness.var_name = _Var("")
        harness.var_type = _Var("KOMODA")
        harness.var_model = _Var("")
        harness.var_color1 = _Var("")
        harness.var_color2 = _Var("")
        harness.var_color3 = _Var("")
        harness.var_extra = _Var("")
        harness.var_ean = _Var("")
        with patch("picorgftp_sql.app.D", {
            "product_fields": {
                "name": {"label": "Kolekcja", "enabled": True, "required": True},
                "type": {"enabled": False},
                "model": {"enabled": True, "required": False},
                "color1": {"enabled": False},
            }
        }):
            missing = App._missing_required_product_fields(harness)
        self.assertEqual(missing, ["Kolekcja"])

    def test_effective_desktop_values_clear_disabled_fields(self) -> None:
        harness = type("Harness", (), {})()
        for key, value in {
            "name": "N", "type": "KOMODA", "model": "M", "color1": "C",
            "color2": "", "color3": "", "extra": "LED", "ean": "5901234567890"
        }.items():
            setattr(harness, f"var_{key}", _Var(value))
        with patch("picorgftp_sql.app.D", {"product_fields": {"type": {"enabled": False}}}):
            App._clear_disabled_product_field_values(harness)
        self.assertEqual(harness.var_type.get(), "")
```

- [ ] **Step 2: Run desktop helper tests and confirm RED**

Run: `python -m pytest tests/test_app_lookup_state.py -q`

Expected: FAIL because the generic desktop product-field methods do not exist.

- [ ] **Step 3: Replace color-only desktop helpers with generic field helpers**

Import shared definitions from `product_fields.py` and add these methods to `App`:

```python
def _product_field_settings(A):
    return normalize_product_fields(
        D.get(PRODUCT_FIELDS_KEY),
        legacy_color_labels=D.get(COLOR_FIELD_LABELS_KEY),
    )


def _default_product_field_name(A, field_key):
    localized = {
        "name": NAME_LABEL,
        "type": TYPE_LABEL,
        "model": MODEL_LABEL,
        "color1": COLOR1_LABEL,
        "color2": COLOR2_LABEL,
        "color3": COLOR3_LABEL,
        "extra": EXTRA_LABEL,
        "ean": EAN_OPTIONAL_LABEL,
    }.get(field_key, "")
    return str(localized or DEFAULT_PRODUCT_FIELD_LABELS[field_key]).strip().rstrip(":*").strip()


def _product_field_label_text(A, field_key):
    item = A._product_field_settings()[field_key]
    label = item["label"] or A._default_product_field_name(field_key)
    return f"{label}{'*' if item['required'] else ''}:"


def _clear_disabled_product_field_values(A):
    for key, item in A._product_field_settings().items():
        if not item["enabled"]:
            getattr(A, FORM_TRACKED_VAR_ATTRS[key]).set(B)


def _missing_required_product_fields(A):
    settings = A._product_field_settings()
    values = {
        PRODUCT_FIELD_VALUE_KEYS[key]: A._get_form_field_raw_value(key)
        for key in PRODUCT_FIELD_KEYS
    }
    return [
        item["label"] or A._default_product_field_name(key)
        for key, _label in missing_required_fields(values, settings)
        for item in (settings[key],)
    ]


def _refresh_product_fields(A):
    A._clear_disabled_product_field_values()
    for key, item in A._product_field_settings().items():
        meta = getattr(A, "_form_field_meta", {}).get(key, {})
        frame = meta.get("frame")
        label = meta.get("label")
        if frame:
            frame.grid() if item["enabled"] else frame.grid_remove()
        if label:
            label.configure(text=A._product_field_label_text(key))
```

Use `_missing_required_product_fields()` instead of the four hard-coded name/type/model/color1 checks in file selection, drag-and-drop, lookup readiness, and submit. Show the joined effective labels in the warning message. Call `_clear_disabled_product_field_values()` before building the output directory and calling `save_ean_entry`.

Skip the EAN prompt and use `BRAK-EAN` when EAN is disabled. Use the no-extra placeholder directly when extra is disabled. Hide or disable EAN-only actions while EAN is disabled.

- [ ] **Step 4: Run desktop helper tests and confirm GREEN**

Run: `python -m pytest tests/test_app_lookup_state.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Replace the three desktop color settings with eight vertical rows**

Create one variable group per canonical field when opening settings:

```python
product_field_settings = A._product_field_settings()
product_field_vars = {
    key: {
        "label": F.StringVar(value=item["label"]),
        "enabled": F.BooleanVar(value=item["enabled"]),
        "required": F.BooleanVar(value=item["required"]),
    }
    for key, item in product_field_settings.items()
}
```

Build a `product_fields_frame` on the system tab. For each field, add a new row containing the localized default label, label entry, `Aktywne` checkbox, and `Wymagane` checkbox. The enabled checkbox command must clear and disable the required checkbox when switched off.

On save, replace the old `COLOR_FIELD_LABELS_KEY` assignment with:

```python
D[PRODUCT_FIELDS_KEY] = normalize_product_fields({
    key: {
        "label": vars_["label"].get(),
        "enabled": vars_["enabled"].get(),
        "required": vars_["required"].get(),
    }
    for key, vars_ in product_field_vars.items()
})
```

After `save_config`, call `A._refresh_product_fields()` so the open form updates immediately.

- [ ] **Step 6: Add a static desktop source contract test**

```python
# append to tests/test_source_integrity.py
def test_desktop_uses_generic_product_field_settings(self) -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "picorgftp_sql" / "app.py").read_text(encoding="utf-8")
    assert "def _refresh_product_fields" in source
    assert "def _missing_required_product_fields" in source
    assert "product_field_vars" in source
    assert "for key, item in product_field_settings.items()" in source
```

- [ ] **Step 7: Run desktop and source tests and confirm GREEN**

Run: `python -m pytest tests/test_app_lookup_state.py tests/test_source_integrity.py tests/test_desktop_smoke_ci.py -q`

Expected: all selected tests pass and `picorgftp_sql.app` imports headlessly.

- [ ] **Step 8: Commit Task 4**

```bash
git add picorgftp_sql/app.py tests/test_app_lookup_state.py tests/test_source_integrity.py
git commit -m "feat: apply product field settings to desktop"
```

### Task 5: Localization and user documentation

**Files:**
- Modify: `picorgftp_sql/Localization/pl.json`
- Modify: `picorgftp_sql/Localization/eng.json`
- Modify: `picorgftp_sql/Localization/ua.json`
- Modify: `tests/test_desktop_smoke_ci.py:51-62`
- Modify: `README.md:29-36,146-153`

- [ ] **Step 1: Write a failing localization contract test**

```python
# append inside test_localization_files_are_valid_json in tests/test_desktop_smoke_ci.py
required_product_field_keys = {
    "product_fields_section",
    "product_fields_hint",
    "product_field_custom_label",
    "product_field_enabled",
    "product_field_required",
}
for path in sorted(localization_dir.glob("*.json")):
    payload = json.loads(path.read_text(encoding="utf-8"))
    self.assertEqual(required_product_field_keys - set(payload), set(), path.name)
```

- [ ] **Step 2: Run localization tests and confirm RED**

Run: `python -m pytest tests/test_desktop_smoke_ci.py -q`

Expected: FAIL listing the five missing localization keys.

- [ ] **Step 3: Add localized settings strings**

Add the five keys to each localization JSON file. Use these Polish values and equivalent English/Ukrainian translations:

```json
"product_fields_section": "Pola produktu",
"product_fields_hint": "Pusta nazwa zachowuje etykietę domyślną. Wyłączone pola są pomijane przy zapisie i przetwarzaniu.",
"product_field_custom_label": "Własna nazwa",
"product_field_enabled": "Aktywne",
"product_field_required": "Wymagane"
```

- [ ] **Step 4: Update README behavior summaries**

In both English and Polish feature lists, replace the color-label-only wording with a statement that all eight product fields can be renamed, enabled/disabled, and marked required in web and desktop settings, with SQLite/config.json persistence according to data mode.

- [ ] **Step 5: Run localization and documentation-adjacent checks**

Run: `python -m pytest tests/test_desktop_smoke_ci.py tests/test_source_integrity.py -q`

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add picorgftp_sql/Localization/pl.json picorgftp_sql/Localization/eng.json picorgftp_sql/Localization/ua.json tests/test_desktop_smoke_ci.py README.md
git commit -m "docs: describe configurable product fields"
```

### Task 6: Full verification and cleanup

**Files:**
- Review all files changed in Tasks 1-5.

- [ ] **Step 1: Run syntax and whitespace checks**

Run: `python -m compileall -q picorgftp_sql tests`

Expected: exit code 0 and no output.

Run: `git diff --check`

Expected: exit code 0 and no output.

- [ ] **Step 2: Run the complete automated test suite**

Run: `python -m pytest -q`

Expected: all tests pass with no failures or errors.

- [ ] **Step 3: Inspect the final change scope**

Run: `git status --short`

Expected: only intentional product-field implementation files are modified; no `.superpowers`, temp, cache, database, or generated build files appear.

Run: `git diff --stat 4a3160f..HEAD`

Expected: changes are limited to the files listed in this plan.

- [ ] **Step 4: Perform targeted manual smoke checks when a display is available**

Desktop:

1. Open settings and verify eight vertically listed fields.
2. Rename `Nazwa` to `Kolekcja`, disable `Typ`, and make `EAN` required.
3. Save and verify the product form updates without restart.
4. Confirm `Typ` is hidden, `Kolekcja` is displayed, and EAN has a required marker.

Web:

1. Open Settings → Application and verify the responsive eight-row list.
2. Confirm disabling a row unchecks and disables its required switch.
3. Save the same settings and verify the main form updates immediately.
4. Submit a product and confirm disabled values are absent from the stored entry, path, and filename.

Expected: desktop and web behavior matches the accepted design.
