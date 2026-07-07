# Pimcore Runtime Field Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move field grouping and ordering out of product-field application settings and into Pimcore mapping settings used by runtime Pimcore forms.

**Architecture:** Product field settings return to label/enabled/required only. Pimcore field mappings own runtime layout metadata: group, order, and width. Backend normalization persists that metadata, runtime schema exposes it in display order, and browser rendering uses it for create, edit, and test Pimcore forms.

**Tech Stack:** Python configuration helpers, FastAPI web data helpers, vanilla JavaScript settings UI, CSS grid, pytest.

## Global Constraints

- Do not remove existing product field label, enabled, or required behavior.
- Do not change Pimcore mapping semantics for source, target, parser, templates, SQL values, translation, or required fields.
- Runtime layout must apply to `Edytuj dane Pimcore`, create product, and test create forms.
- Configuration must be changed only from settings.

---

### Task 1: Revert Product Field Groups

**Files:**
- Modify: `picorgftp_sql/product_fields.py`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Test: `tests/test_product_fields.py`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: `normalize_product_fields(raw_settings)`
- Produces: product field objects with `label`, `enabled`, and `required` only.

- [ ] Write failing tests that reject `group` and `order` in product field settings.
- [ ] Run `python -m pytest tests/test_product_fields.py::test_defaults_preserve_current_form_contract tests/test_product_fields.py::test_normalization_ignores_obsolete_group_and_order -q` and confirm failure.
- [ ] Remove product-field group/order normalization and UI controls.
- [ ] Run the same tests and confirm pass.

### Task 2: Persist Pimcore Mapping Layout Metadata

**Files:**
- Modify: `picorgftp_sql/pimcore_config.py`
- Modify: `picorgftp_sql/web_data.py`
- Test: `tests/test_pimcore_config.py`
- Test: `tests/test_pimcore_web.py`

**Interfaces:**
- Consumes: raw Pimcore mapping dictionaries.
- Produces: normalized mappings and runtime schema entries with `layout_group` and `layout_order`; fields sharing one row/order are rendered as equal-width columns.

- [ ] Write failing tests for normalized mapping layout metadata and runtime schema ordering.
- [ ] Run targeted pytest commands and confirm failure.
- [ ] Add normalization defaults and schema sorting.
- [ ] Run targeted pytest commands and confirm pass.

### Task 3: Render Pimcore Runtime Layout

**Files:**
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Test: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Consumes: runtime schema entries from Task 2.
- Produces: grouped field sections inside `.pimcore-runtime-fields`.

- [ ] Write failing UI integrity tests for mapping layout controls and runtime section rendering.
- [ ] Run `python -m pytest tests/test_web_ui_integrity.py -q` and confirm failure.
- [ ] Add settings controls and grouped runtime renderer.
- [ ] Run `python -m pytest tests/test_web_ui_integrity.py -q` and confirm pass.

### Task 4: Final Verification

**Files:**
- All modified files.

**Interfaces:**
- Consumes: completed tasks.
- Produces: verified change set.

- [ ] Run `python -m pytest tests/test_product_fields.py tests/test_pimcore_config.py tests/test_pimcore_web.py tests/test_web_ui_integrity.py tests/test_source_integrity.py -q`.
- [ ] Inspect `git diff --check`.
- [ ] Summarize changed files and verification.
