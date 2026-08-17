# User-ID Session Tokens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace usernames in web-session cookies with persistent, server-generated user UUIDs and reject pre-v2 session cookies.

**Architecture:** User records receive an immutable UUID4 `id` that is migrated and persisted during the first load of legacy records. Authentication supplies that stored public user record directly to the session-token generator; the reader resolves `id` with `find_user_by_id`, validates account state and session version, then returns the canonical username.

**Tech Stack:** Python 3.13 standard library (`uuid`, `base64`, `hmac`), FastAPI, pytest/unittest.

## Global Constraints

- Use UUID4 generated exclusively by the server; do not derive an identifier from the login request.
- Persist generated IDs during the first read of legacy records, for both JSON and SQLite-backed user storage.
- New session payloads must be `session-v2|<user-id>|<session-version>|<issued-at>|<nonce>` and retain the current Base64 URL-safe encoding and HMAC-SHA256 signature.
- Reject every pre-v2 session payload; deployment deliberately requires users to log in again.
- Leave browser-extension token behavior unchanged.

---

## File structure

- Modify `picorgftp_sql/web_data.py`: normalize, persist, expose, and find persistent user UUIDs.
- Modify `picorgftp_sql/web/app.py`: create and read the `session-v2` token format using stored user IDs.
- Modify `tests/test_web_data_users.py`: cover UUID generation, immediate legacy migration, and ID lookup.
- Modify `tests/test_web_smoke_ci.py`: cover session payload privacy, v2 validation, and rejection of signed legacy cookies.

### Task 1: Persist stable user UUIDs

**Files:**
- Modify: `picorgftp_sql/web_data.py:1-18,1089-1267,1373-1418`
- Test: `tests/test_web_data_users.py:1-120`

**Interfaces:**
- Produces: `find_user_by_id(user_id: str) -> dict[str, object] | None`.
- Produces: all public user records from `find_user`, `authenticate_user`, `authenticate_login`, `load_users`, and `add_user` include `id: str` containing a UUID4.
- Consumes: `SqliteStore.save_users(users)` and the existing JSON `web_users.json` persistence format; both already store complete user dictionaries.

- [ ] **Step 1: Write failing tests for UUID generation, migration, and lookup**

  Add `import uuid` to `tests/test_web_data_users.py`, then add these tests to `WebDataUserTests`:

  ```python
  def test_legacy_user_ids_are_migrated_and_persisted(self) -> None:
      temp_dir = _workspace_temp("web_data_users_uuid_migration")
      try:
          users_path = temp_dir / web_data.WEB_USERS_PATH
          users_path.write_text(
              json.dumps([{"username": "operator", "password_hash": "hash"}]),
              encoding="utf-8",
          )
          with patch.object(web_data.settings, "AC", str(temp_dir)):
              first = web_data.find_user("operator")
              stored = json.loads(users_path.read_text(encoding="utf-8"))
              second = web_data.find_user("operator")
      finally:
          shutil.rmtree(temp_dir)

      self.assertIsNotNone(first)
      self.assertEqual(uuid.UUID(first["id"]).version, 4)
      stored_operator = next(user for user in stored if user["username"] == "operator")
      self.assertEqual(stored_operator["id"], first["id"])
      self.assertEqual(second["id"], first["id"])

  def test_find_user_by_id_returns_public_user(self) -> None:
      record = web_data._default_admin()
      with patch.object(web_data, "load_user_records", return_value=[record]):
          user = web_data.find_user_by_id(record["id"])

      self.assertEqual(user["username"], "admin")
      self.assertEqual(user["id"], record["id"])
  ```

  Extend `test_add_user_persists_normalized_email` with:

  ```python
  self.assertEqual(uuid.UUID(saved_operator["id"]).version, 4)
  self.assertEqual(operator["id"], saved_operator["id"])
  ```

- [ ] **Step 2: Run the new tests and verify they fail**

  Run:

  ```powershell
  & 'tmp_pytest\endpoint-verify\Scripts\python.exe' -m pytest tests\test_web_data_users.py -k "legacy_user_ids or find_user_by_id or add_user_persists_normalized_email" -q
  ```

  Expected: FAIL because `id` and `find_user_by_id` do not exist.

- [ ] **Step 3: Implement user-ID normalization and one-time persistence**

  In `picorgftp_sql/web_data.py`:

  1. Add `import uuid`.
  2. Add `_new_user_id() -> str`, returning `str(uuid.uuid4())`.
  3. Add `_normalized_user_id(value: object) -> str`; accept only a parseable UUID whose `.version == 4`, otherwise return `_new_user_id()`.
  4. Add `"id": _normalized_user_id(item.get("id"))` to `_normalized_user_record`, and `"id": _new_user_id()` to `_default_admin` and the new-user dictionary in `add_user`.
  5. Add `"id": _text(user.get("id"))` to `_public_user`.
  6. Extract the existing SQLite/JSON write bodies into `_persist_user_records(users: list[dict[str, object]]) -> None`. Make `save_users` call this helper and then `load_users`.
  7. In `load_user_records`, compare every normalized record with its source record’s `id`, regenerate a duplicate UUID if it has already appeared in the same load, and mark the collection as changed when an ID was added or replaced. Treat a missing data source or missing default admin as changed. If changed, call `_persist_user_records(users)` before returning. Do not call `save_users` from `load_user_records`, because `save_users` calls `load_users` and would re-enter the loader.
  8. Add `find_user_by_id`; normalize its input with `_text`, iterate `load_user_records`, compare the stored `id` with `hmac.compare_digest`, and return `_public_user(user)` on a match. Return `None` for blank or unknown IDs.

  The ID is intentionally public in the application’s internal user snapshot: it is a random server-generated lookup key, not a credential. The signed token remains the authorization credential.

- [ ] **Step 4: Run data-model tests and verify they pass**

  Run:

  ```powershell
  & 'tmp_pytest\endpoint-verify\Scripts\python.exe' -m pytest tests\test_web_data_users.py -q
  ```

  Expected: PASS.

- [ ] **Step 5: Commit the user-ID data model**

  ```powershell
  git add picorgftp_sql/web_data.py tests/test_web_data_users.py
  git commit -m "feat: persist web user identifiers"
  ```

### Task 2: Issue and validate v2 session tokens

**Files:**
- Modify: `picorgftp_sql/web/app.py:129-146,596-643,5160-5206`
- Test: `tests/test_web_smoke_ci.py:1-25,948-985`

**Interfaces:**
- Consumes: `find_user_by_id(user_id: str) -> dict[str, object] | None` from Task 1.
- Produces: `_make_session_token(user: Dict[str, Any]) -> str` for trusted authenticated user snapshots.
- Produces: `_read_session_token(token: Optional[str]) -> Optional[str]`, which accepts only `session-v2` and returns the resolved canonical username.

- [ ] **Step 1: Write failing v2-token and legacy-cookie tests**

  Add `import base64` and `import time` to `tests/test_web_smoke_ci.py`. Add the following tests to `WebSmokeCiTests`:

  ```python
  def test_session_v2_payload_uses_user_id_not_username(self) -> None:
      user = {
          "id": "7c8e1b5e-4c50-4da4-9b37-51b9db4600fa",
          "username": "operator",
          "enabled": True,
          "locked": False,
          "session_version": 3,
      }
      with patch.object(web_app, "find_user_by_id", return_value=user):
          token = web_app._make_session_token(user)
          payload = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8").rsplit("|", 1)[0]
          resolved = web_app._read_session_token(token)

      self.assertTrue(payload.startswith("session-v2|7c8e1b5e-4c50-4da4-9b37-51b9db4600fa|3|"))
      self.assertNotIn("operator", payload)
      self.assertEqual(resolved, "operator")

  def test_signed_pre_v2_session_cookie_is_rejected(self) -> None:
      payload = f"session|admin|0|{int(time.time())}|legacy-nonce"
      token = base64.urlsafe_b64encode(
          f"{payload}|{web_app._sign(payload)}".encode("utf-8")
      ).decode("ascii")

      with patch.object(web_app, "find_user", return_value={"username": "admin"}):
          self.assertIsNone(web_app._read_session_token(token))
  ```

- [ ] **Step 2: Run the new tests and verify they fail**

  Run:

  ```powershell
  & 'tmp_pytest\endpoint-verify\Scripts\python.exe' -m pytest tests\test_web_smoke_ci.py -k "session_v2_payload or pre_v2_session_cookie" -q
  ```

  Expected: FAIL because `_make_session_token` accepts a username, emits `session`, and the reader accepts the old format.

- [ ] **Step 3: Implement `session-v2` creation and reading**

  In `picorgftp_sql/web/app.py`:

  1. Import `find_user_by_id` from `web_data` beside `find_user`.
  2. Change `_make_session_token` to accept the authenticated `user` dictionary rather than a username. Read only `user["id"]` and `user["session_version"]`; create `session-v2|<id>|<version>|<timestamp>|<nonce>`, sign it with `_sign`, then Base64 URL-safe encode it exactly as before.
  3. Replace the `len(parts) == 5 and parts[0] == "session"` and three-part legacy branches in `_read_session_token` with a single exact `session-v2` branch. Parse `user_id`, version, issued time, and nonce; reject any other marker or field count.
  4. Resolve the record with `find_user_by_id(user_id)`, retain the enabled, lock, age, and `session_version` checks, and return `str(user.get("username") or "") or None`.
  5. In `/api/login`, call `_make_session_token(user)` after successful authentication. The authenticated `user` is returned by storage-backed `authenticate_login`; do not pass the request’s `username` to session-token creation.

- [ ] **Step 4: Run focused authentication regressions and verify they pass**

  Run:

  ```powershell
  & 'tmp_pytest\endpoint-verify\Scripts\python.exe' -m pytest tests\test_web_smoke_ci.py -k "auth_enabled_protects_routes_and_accepts_login_session or session_v2_payload or pre_v2_session_cookie or password_change_invalidates_current_session or app_secret_change_returns_relogin_response_instead_of_401" -q
  ```

  Expected: PASS.

- [ ] **Step 5: Commit the v2 session protocol**

  ```powershell
  git add picorgftp_sql/web/app.py tests/test_web_smoke_ci.py
  git commit -m "fix: bind sessions to stored user ids"
  ```

### Task 3: Verify the complete affected surface

**Files:**
- Verify: `tests/test_web_data_users.py`
- Verify: `tests/test_web_smoke_ci.py`
- Verify: `tests/test_web_runtime_api.py`
- Verify: `tests/test_web_app_files.py`

**Interfaces:**
- Consumes: the persisted UUID data model from Task 1 and the v2 session protocol from Task 2.
- Produces: verification evidence that the web authentication and adjacent route tests remain green.

- [ ] **Step 1: Run the complete web-user and web-session suites**

  Run:

  ```powershell
  & 'tmp_pytest\endpoint-verify\Scripts\python.exe' -m pytest tests\test_web_data_users.py tests\test_web_smoke_ci.py tests\test_web_runtime_api.py tests\test_web_app_files.py -q
  ```

  Expected: PASS.

- [ ] **Step 2: Inspect the final diff for security invariants**

  Run:

  ```powershell
  git diff HEAD~3..HEAD -- picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_web_data_users.py tests/test_web_smoke_ci.py
  ```

  Confirm that `_make_session_token` receives a storage-backed user dictionary, emits `session-v2`, contains no username in the payload, and `_read_session_token` rejects legacy markers.

- [ ] **Step 3: Record the verification result in the handoff**

  Report the exact pytest command and result, state that existing cookies are intentionally rejected, and call out that the browser-extension token format was not changed.
