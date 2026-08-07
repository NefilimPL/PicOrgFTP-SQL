# Task 5 report: autocomplete frontend module

## Delivered boundary

- Created `picorgftp_sql/web/static/autocomplete.js`. It exposes only
  `window.PicOrg.AutocompleteController` and `window.PicOrg.setupAutocomplete`.
  Loading the asset registers those APIs only; it does not create DOM nodes,
  listeners, requests, or timers.
- Moved the autocomplete controller plus debounce, cancellation, local/remote
  merge, panel rendering, ARIA option state, mouse selection, and keyboard
  handling into that module.
- Reduced `latest-request.js` to `LatestRequest` and moved its autocomplete
  session coverage to the new module tests.
- Kept `app.js` as the composition root: it creates one dependency object,
  starts autocomplete once, and delegates the two modal-close call sites to
  the returned `closePanels` control.
- Updated the template order to `latest-request.js`, `autocomplete.js`,
  `runtime-status.js`, `process-jobs.js`, then `app.js`, and added a Python
  boundary regression test for that order.

## Red/green evidence

### Red

After creating `tests/js/helpers.js` and the controller contract test, before
creating the production module, this command was run:

```powershell
& 'C:\Program Files\nodejs\node.exe' --test tests/js/autocomplete.test.js
```

It failed as expected with `MODULE_NOT_FOUND` for
`picorgftp_sql/web/static/autocomplete.js`. The failure was caused by the
missing production module, not a test setup error.

### Green

After the extraction, the required JavaScript checks were run:

```powershell
& 'C:\Program Files\nodejs\node.exe' --test tests/js/latest-request.test.js tests/js/autocomplete.test.js
& 'C:\Program Files\nodejs\node.exe' --check picorgftp_sql/web/static/autocomplete.js
& 'C:\Program Files\nodejs\node.exe' --check picorgftp_sql/web/static/app.js
```

Result: all five Node tests passed and both syntax checks exited 0.

The module-boundary test was also run with the repository's working Python
environment:

```powershell
& '.\tmp_pyenv\Scripts\python.exe' -m pytest tests/test_module_boundaries.py -q
```

Result: `4 passed` (with four existing FastAPI deprecation warnings).

`git diff --check` also exited 0.

## Tests added or moved

- `controller merges the latest remote values with local values` is the new
  requested latest-request controller contract.
- `controller ignores remote results after the request context changes` moved
  the stale-response regression to the extracted controller.
- `controller skips remote work when local visible results fill the panel`
  moved the local-result limit regression to the extracted controller.
- `test_frontend_modules_load_before_the_app_composition_root` protects the
  required template asset order.

## Commit

`refactor: extract autocomplete module`

## Concerns

- The required `process-jobs.js` tag is now in its specified order, but that
  asset is not present on the Task-5 worktree. Its extraction belongs to the
  subsequent process-jobs task; until it lands the browser will log a harmless
  404 for that tag while continuing to load `app.js`.
- The default `python` environment cannot collect FastAPI tests because its
  installed `pydantic` and `pydantic-core` versions are incompatible. The
  repository `tmp_pyenv` environment ran the boundary test successfully.
