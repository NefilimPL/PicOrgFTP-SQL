# Task 3 report — Web product query delegation

## Status

DONE_WITH_TEST_LIMITATION

## Summary

The web product search, identity lookup, suggestion, and save pre-lookup paths
now use the active data-store contract. Search builds `ProductSearchCriteria`,
translates the store's established uppercase product records back to the
browser's lowercase payload shape, and retains browser-side free-text query
filtering. Identity lookup prefers a product ID, then EAN, and `save_web_entry`
performs that lookup exactly once before saving.

Suggestions delegate their field, typed prefix, and explicit non-target product
context to the store. SQLite suggestions no longer materialize full lists;
legacy mode retains its workbook-list fallback. The initial web bootstrap list
loader was not changed. The product search and suggestions HTTP endpoints now
accept a limit and clamp it server-side to 1–100 before delegation.

## Files

- `picorgftp_sql/web_data.py`
- `picorgftp_sql/web/app.py`
- `tests/test_product_queries.py`
- `tests/test_web_app_files.py`

## Commit

- `perf: delegate product search to data store`

## Tests and limitation

Tests were written before production changes, but were not run. The user
explicitly authorized this limitation because the configured Python interpreter
cannot import the standard-library `encodings` package. No test-pass claim is
made.

The added coverage checks active-store delegation for search and suggestions,
the one-lookup save preflight, SQLite avoidance of full-list loading, and
endpoint limit clamping above 100.

## Self-review

- `git diff --check` completed without whitespace errors.
- Search, lookup, and suggestions use the selected active store; no SQLite path
  in these web helpers calls `load_lists()` or `prepare_excel_lists()`.
- Store records preserve the public browser response shape through the existing
  `WebEntry` conversion and payload helper.
- The public product endpoint names and response envelopes are unchanged.
- The startup `load_web_data()` product-list behavior and form UI were not
  changed.

## Fix round 1

### Status

DONE_WITH_TEST_LIMITATION

### Root cause and correction

The first implementation passed free-text `query` to the web helper only after
the active store had already enforced its limit. It also asked SQLite for
colour and extra suggestion fields outside the store's whitelisted column/key
set. This round extends `ProductSearchCriteria` with `query` and evaluates it
inside both fallback filtering and SQLite before `LIMIT`. SQLite now persists
normalized keys for all colour/extra fields and a normalized combined product
search key, so the query remains a selective SQL operation and never loads the
full list into Python.

The store suggestion whitelist now includes `color1`, `color2`, `color3`, and
`extra`; their results use the same prefix, explicit context, normalized-key,
and stable ordering model as the existing fields. Schema version 13 migrates
existing databases by backfilling the added keys once.

### Regression coverage

- A web search finds a matching SQLite record located after an earlier
  criterion match while requesting one result.
- SQLite searches apply a free-text match before the output limit.
- SQLite colour and extra suggestions return saved-record values with context.
- Direct EAN identity lookup retains the public lowercase payload.
- Zero and negative web search limits delegate as one.

### Commit

- `fix: preserve delegated product query semantics`

### Test limitation

The regression tests were added before the correction but not executed because
the user-authorized Python environment limitation remains: Python cannot
import `encodings`. No test-pass claim is made.

### Self-review

- The SQL query predicate uses persisted normalized text and is applied before
  `LIMIT`; it does not call `load_lists()` or materialize rows in Python.
- Existing uppercase store records and lowercase browser payload conversion are
  unchanged.
- New migration columns, insert/update values, and SQL placeholders were
  checked against the product-entry field order; `git diff --check` is clean.

## Fix round 2

### Status

DONE_WITH_TEST_LIMITATION

### Correction

The v13 product-key migration previously called `fetchall()` for its complete
product-row selection. It now consumes the cursor in fixed 500-row batches and
updates each row before requesting the next batch, so an upgrade never holds
the full product table in Python memory.

### Regression coverage

A migration regression test wraps the SQLite connection’s product cursor so
that `fetchall()` raises, then verifies the streamed migration backfills the
new colour, extra, and combined search keys.

### Commit

- `perf: stream product key migration`

### Test limitation

Tests were not run because the user-authorized Python environment limitation
remains: Python cannot import `encodings`. No test-pass claim is made.

### Self-review

- The migration only retains at most 500 selected rows at once.
- The migration still updates every normalized key and the combined search key
  through the same trusted column mapping.
- `git diff --check` is clean.
