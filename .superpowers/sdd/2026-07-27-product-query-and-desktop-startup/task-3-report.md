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
