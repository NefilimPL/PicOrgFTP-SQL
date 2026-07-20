# CodeQL Regex Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove both CodeQL polynomial-regex findings while preserving mailbox validation and secret-redaction boundaries.

**Architecture:** Replace the two fixed regular expressions with private, forward-only ASCII parser helpers. Existing callers retain their contracts; tests assert public behavior and the boundary parser directly.

**Tech Stack:** Python 3.13, pytest.

## Global Constraints

- Preserve the existing accepted e-mail local-part characters and structured-field grammar.
- Do not add dependencies or reduce the existing 8 KiB redaction-output limit.
- Every behavior change follows a red-green TDD cycle.

---

### Task 1: Deterministic parsers and regression tests

**Files:**

- Modify: `picorgftp_sql/email_settings.py:14-58`
- Modify: `picorgftp_sql/redaction.py:55-98`
- Test: `tests/test_email_settings.py`
- Test: `tests/test_redaction.py`

**Interfaces:**

- Produces: `_is_valid_email_local_part(value: str) -> bool`
- Produces: `_next_structured_field(text: str, delimiter_at: int) -> bool`

- [ ] **Step 1: Write failing regression and source-integrity tests**

Add public tests that accept the current allowed ASCII atom characters, reject a one-million-character mailbox, and check structured fields such as `next.field-2 =` and `_field:`. Add source-integrity tests asserting that `_EMAIL_LOCAL_RE` and `_STRUCTURED_FIELD_RE` are absent.

- [ ] **Step 2: Run the focused tests to verify the source-integrity assertions fail**

Run: `python -m pytest tests/test_email_settings.py tests/test_redaction.py -q`

Expected: failures only because both named regex constants still exist.

- [ ] **Step 3: Implement the two forward-only parsers**

Use an allowed-character set with `all()` for the email local part. In `_next_structured_field`, scan identifier characters, optional horizontal whitespace, then the required delimiter. Remove the two regex constants and their calls.

- [ ] **Step 4: Verify focused and full tests**

Run: `python -m pytest tests/test_email_settings.py tests/test_redaction.py -q; python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the code and tests**

Run: `git add picorgftp_sql/email_settings.py picorgftp_sql/redaction.py tests/test_email_settings.py tests/test_redaction.py && git commit -m "fix: remove CodeQL regex findings"`
