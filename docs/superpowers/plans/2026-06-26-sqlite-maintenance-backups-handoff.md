# SQLite Maintenance and Backups Handoff

## Current State

Working tree should be clean before starting implementation.

Recent preparation commits:

- `b7afbd3 docs: design sqlite maintenance and backups`
- `b3a681b docs: plan sqlite maintenance and backups`

Read these files first:

- `docs/superpowers/specs/2026-06-26-sqlite-maintenance-backups-design.md`
- `docs/superpowers/plans/2026-06-26-sqlite-maintenance-backups.md`

No application code has been changed yet. The repo is prepared for a test-first
implementation run from the plan.

## Recommended Start Prompt For The Other Account

Paste this into the other account from the same repository root
`C:\_GitHub_\PicOrgFTP-SQL`:

```text
Kontynuuj pracę w repo C:\_GitHub_\PicOrgFTP-SQL.

Cel: zaimplementować zatwierdzony plan z:
docs/superpowers/plans/2026-06-26-sqlite-maintenance-backups.md

Najpierw przeczytaj:
docs/superpowers/specs/2026-06-26-sqlite-maintenance-backups-design.md
docs/superpowers/plans/2026-06-26-sqlite-maintenance-backups.md

Użyj wymaganych superpowers z planu: subagent-driven-development albo executing-plans.
Preferuję Inline Execution, jeśli subagenci nie są dostępni.

Wykonuj zadania po kolei, test-first:
1. pisz failing test,
2. uruchom go i potwierdź fail,
3. implementuj minimalnie,
4. uruchom testy,
5. commit po każdym zadaniu.

Nie usuwaj istniejących danych użytkownika ani ustawień SQLite/legacy.
Repair/backup/restore/diff dotyczą aktywnego SQLite, legacy zostaje import-only.
Zacznij od Task 1 w planie.
```

## Important Constraints

- Do not skip TDD. The plan is written around failing tests first.
- Do not remove existing SQLite or legacy data.
- Keep commits small and aligned to plan tasks.
- Any `git add` or `git commit` will likely need elevated permission.
- If a test snippet in the plan needs minor adjustment to fit current test class
  names, keep the intended behavior unchanged.

## Suggested Verification At The End

Run:

```powershell
python -m pytest tests/test_config.py tests/test_sql_service.py tests/test_sqlite_store.py tests/test_file_index.py tests/test_sqlite_backup.py tests/test_sqlite_maintenance.py tests/test_web_data_users.py tests/test_web_smoke_ci.py tests/test_web_ui_integrity.py tests/test_source_integrity.py -q
python -m pytest -q
python -m compileall -q PicOrgFTP-SQL.pyw PicOrgFTP-SQL-WEB.pyw PicOrgFTP-SQL-QtSlots.pyw picorgftp_sql tests tools
node --check picorgftp_sql/web/static/app.js
```
