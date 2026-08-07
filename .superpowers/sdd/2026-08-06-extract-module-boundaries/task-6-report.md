# Task 6 report: process-jobs frontend module

## Delivered boundary

- Created `picorgftp_sql/web/static/process-jobs.js`, which registers only
  `window.PicOrg.ProcessJobsController`.
- `refresh()` stores the latest runtime queue version, maintains the current
  active job, renders fetched queue data, and returns the same promise to
  concurrent callers while a request is in flight.
- `app.js` composes that controller with the process-queue API and renderer.
  Runtime process-queue version changes and explicit refreshes drive updates;
  the previous process-job timeout polling loop is removed.
- The existing template order remains `latest-request.js`, `autocomplete.js`,
  `runtime-status.js`, `process-jobs.js`, and `app.js`; the existing module
  boundary test protects it.

## Red/green evidence

### Red

Before the production asset existed, the controller test was run:

```powershell
& 'C:\Program Files\nodejs\node.exe' --test tests/js/process-jobs.test.js
```

It failed as expected with `MODULE_NOT_FOUND` for
`picorgftp_sql/web/static/process-jobs.js`.

### Green

After the implementation, these checks passed:

```powershell
& 'C:\Program Files\nodejs\node.exe' --test tests/js/*.test.js
& 'C:\Program Files\nodejs\node.exe' --check picorgftp_sql/web/static/process-jobs.js
& 'C:\Program Files\nodejs\node.exe' --check picorgftp_sql/web/static/app.js
& '.\tmp_pyenv\Scripts\python.exe' -m pytest tests/test_module_boundaries.py -q
git diff --check
```

Result: 14 Node tests passed, both syntax checks passed, module-boundary tests
passed (4 tests; four existing FastAPI deprecation warnings), and the diff
check passed.

## Commit

`refactor: extract process jobs frontend module`
