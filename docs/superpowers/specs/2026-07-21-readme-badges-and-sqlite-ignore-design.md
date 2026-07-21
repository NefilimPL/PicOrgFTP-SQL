# README badges and SQLite ignore rules

## Goal

Make the repository landing page show the project's delivery status and
technology baseline, while preventing local SQLite data from being added to
Git accidentally.

## `.gitignore`

Add explicit patterns for SQLite database files (`.sqlite`, `.sqlite3`, and
`.db`) and their SQLite-generated sidecar files. The sidecar patterns use the
standard suffix separator so that WAL, SHM, rollback-journal, and future
SQLite sidecars are covered without ignoring unrelated source files.

## README badge set

Keep the existing CI and Windows EXE workflow badges. Add badges that are
either dynamic GitHub metadata or verifiable repository facts:

- latest release and its publication date;
- Apache-2.0 licence, latest commit, repository size, open issues, and top
  language;
- CI Python 3.11 and EXE-build Python 3.11–3.14, matching the workflows;
- links to the build dependency list and build technologies: PyInstaller is
  declared in `requirements-build.txt`; PySide6 in `requirements-qt.txt`;
  FastAPI in `requirements-web.txt`; and pytest in the CI workflow.

Every badge links to the matching GitHub view, workflow, documentation, or
requirements file. Static badges state only facts controlled in this
repository; they are not used to imply a third-party service status.

## Verification

Use `git check-ignore --no-index` on representative SQLite database and
sidecar paths. Review the README badge links and `git diff --check` to ensure
the Markdown is valid and whitespace-free.
