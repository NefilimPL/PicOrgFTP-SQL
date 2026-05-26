# Code Quality GitHub Actions Design

Date: 2026-05-26

## Goal

Add a longer, more reliable GitHub Actions quality gate for every push and pull request. The gate should catch code errors, common static issues, security problems, GUI/web regressions that can be checked automatically, performance helper regressions, and broken EXE packaging early.

Official release EXE generation stays in the release workflow. Pushes should only verify that EXE generation is still possible.

## Current Context

The project is a Python application with:

- a desktop GUI based on Tkinter and a PySide6 slot preview prototype;
- a FastAPI LAN web panel with static HTML/CSS/JS assets;
- existing unit tests under `tests/`;
- an existing `.github/workflows/build-exe.yml` workflow that builds and publishes Windows artifacts.

The current build workflow runs on `push`, `workflow_dispatch`, and release publication. The requested behavior is to avoid automatic EXE artifact creation on normal pushes and keep publication tied to GitHub releases.

## Selected Approach

Create a new `.github/workflows/code-quality.yml` workflow for every `push`, `pull_request`, and manual run. It will run on `windows-latest` with Python 3.11 to match the Windows-focused application and existing EXE workflow.

The workflow will install runtime dependencies from:

- `requirements-web.txt`;
- `requirements-qt.txt`;
- `requirements-build.txt` for PyInstaller smoke checks;
- QA tools installed directly in CI: `pytest`, `coverage`, `ruff`, and `bandit`.

## Checks

The workflow will include separate jobs or clearly separated steps for:

- `compileall` over `picorgftp_sql` and `tests`;
- `ruff check` for static Python issues;
- `bandit` over `picorgftp_sql` for basic security scanning;
- full `pytest` with coverage XML output;
- static web GUI smoke checks for required web assets;
- FastAPI application smoke import by calling `create_app()`;
- focused performance helper tests already present in the test suite;
- PyInstaller smoke build for local and web entry points, without uploading artifacts.

## EXE Handling

The existing `.github/workflows/build-exe.yml` will be adjusted so normal pushes no longer publish EXE artifacts. It should keep:

- `release: published` for official tagged release builds;
- `workflow_dispatch` for manual build runs.

The new QA workflow will still test that PyInstaller can build both entry points. It will write only temporary CI output under `dist/ci-smoke` and `build/ci-smoke-*`, and it will not upload artifacts or attach anything to releases.

## README Update

Add a badge for the new code quality workflow. Keep the existing release/build workflow badge if it remains useful, but its meaning should be release/manual build rather than every-push build.

## Error Handling

Each category should fail the workflow when it finds a real issue. For tools that may be newly introduced and noisy, configure them narrowly enough for the current codebase instead of allowing failures silently.

For Bandit, exclude tests and use a practical severity/confidence threshold if needed so the workflow catches meaningful issues without blocking on test-only patterns.

## Validation

Local validation may be limited if Python is not available on the current machine. The workflow files should still be syntactically valid YAML and should rely on `actions/setup-python` in GitHub Actions to provision Python.

After implementation, verify:

- changed workflow files are valid text/YAML;
- triggers match the desired behavior;
- no EXE artifacts are uploaded from push QA;
- release publishing remains in `build-exe.yml`.
