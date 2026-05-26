# CI Quality Gates Design

## Goal

Add GitHub Actions checks that run before release builds and catch critical
breakage in the web panel, desktop entrypoints, static assets, lightweight
performance paths, and workflow configuration.

## Scope

The new CI workflow runs only for `push` and `pull_request` targeting
`main`, `master`, or `dev`. It does not build executable files. The existing
Windows EXE workflow remains available for published releases and manual runs.

## Approach

Use the existing Python test stack and add focused tests that do not require
external FTP, SQL, or browser services:

- FastAPI smoke checks for public routes, static assets, and route presence.
- Static web UI integrity checks for required form fields, buttons, modals,
  slot template elements, and JavaScript selectors.
- Desktop smoke checks for launchers, package imports, localization files,
  image assets, and headless runtime assumptions.
- Lightweight performance/load checks for critical pure-Python workflows and
  repeated health endpoint calls with conservative timing budgets.
- Static CI checks for Python bytecode compilation and JavaScript syntax.

## Error Handling

Tests must fail hard when critical UI controls, routes, assets, or launchers are
missing. Performance tests use generous budgets so they catch major regressions
without being sensitive to normal GitHub-hosted runner variance.

## Non-Goals

This change does not add browser pixel tests, real FTP/SQL integration tests, or
automatic EXE generation on push. Those can be added later as separate jobs if
the project needs heavier release gates.

## Self Review

- No placeholder requirements remain.
- The workflow trigger scope is explicit and matches the requested branches.
- The release workflow is kept separate from CI.
- Tests avoid real external services and stay deterministic.
