# Parcel Template Functions Implementation Plan

**Goal:** Add template functions for presence-aware parcel calculations.

**Architecture:** Extend the existing placeholder-function evaluator instead
of adding a new expression grammar. Functions that need extra fields receive
quoted source names and resolve them through the caller's existing source
resolver. The JavaScript builder exposes the same tokens and the documentation
shows ready-to-paste parcel formulas.

**Tech stack:** Python, pytest, vanilla JavaScript.

## Task 1: Add and test template presence functions

**Files:**

* Modify: `picorgftp_sql/pimcore_templates.py`
* Modify: `tests/test_pimcore_templates.py`

1. Write parametrized tests for `filled`, `any_filled`, `count_filled`, and
   `if_filled`, including whitespace-only values and invalid argument counts.
2. Run the new tests and confirm they fail because the functions are unknown.
3. Extend `_apply` to resolve quoted source arguments, preserve the existing
   error model, and return `0`/`1` or the required text.
4. Exclude the new conditional functions from automatic case conversion.
5. Add an eleven-width formula test that returns `2` when widths 1 and 2 are
   present and all other widths are blank.
6. Run `pytest tests/test_pimcore_templates.py -q`.

## Task 2: Expose and document the functions

**Files:**

* Modify: `picorgftp_sql/web/static/app.js`
* Modify: `tests/test_web_ui_integrity.py`
* Modify: `docs/pimcore.md`

1. Add the four builder tokens with Polish labels and syntax titles.
2. Extend the UI integrity assertion for the function list.
3. Document the functions, their argument rules, and copyable examples for
   counting packages by width and by any parcel dimension.
4. Run the focused UI integrity tests.

## Task 3: Verify the change

**Files:** No production files.

1. Run both focused test modules.
2. Inspect `git diff` to confirm only the template engine, builder, tests, and
   Pimcore documentation changed.
