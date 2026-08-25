# OCR Queue Visibility and Activity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a compact, safe OCR-refinement queue under the existing left-side process queue without letting ordinary browsing prevent background OCR.

**Architecture:** Queue rows stay durable only while pending or processing; completed rows are explicitly purged after ten seconds together with their trusted crop files. The backend owns authorization, TTL cleanup, activity classification and cancellation by image-content hash, while the browser only sends signed file tokens and renders the safe queue projection.

**Tech Stack:** Python 3, FastAPI, SQLite, Pillow, browser-native JavaScript/CSS, pytest, Node.js contract tests.

**Spec:** `docs/superpowers/specs/2026-08-25-ocr-queue-activity-design.md`

## Global Constraints

- Work on the existing branch; do not create a worktree.
- The queue list contains at most 5 rows, ordered `processing`, `pending`, then newest `completed`; the response contains the count hidden by that limit.
- A queue row exposes only a signed crop URL, state and textual OCR result; never expose IDs, hashes, paths, source boxes, product data, ownership or timing details.
- Administrators always see the queue. Ordinary authenticated users see it only when `background_queue_visible_to_users` is true, which defaults to false.
- Completed jobs and their crop files expire after exactly 10 seconds. Pending and processing jobs never expire through this cleanup.
- Queue crops include a symmetric 8 px source-image margin per side, clipped at the source-image edges, and render with `object-fit: contain`.
- Only upload/replacement, slot move/swap, slot removal, Synchronize/Update, and loading a product or photos reset OCR idle time. Settings, Pimcore, normal browsing, logging, status polling and OCR-progress polling do not.
- Removing a slot cancels pending refinement rows having the same image hash and deletes only their trusted crop files; it does not delete completed OCR scan values.
- Run Python tests with `.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825'`; remove only that verified temporary directory after test runs.

---

### Task 1: Persist queue visibility, crop context, cancellation and expiry

**Files:**
- Modify: `picorgftp_sql/ocr_settings.py:10-83`
- Modify: `picorgftp_sql/services/ocr_cache.py:103-148`
- Modify: `picorgftp_sql/sqlite_store.py:3833-3918`
- Modify: `tests/test_ocr_settings.py:1-66`
- Modify: `tests/test_ocr_cache.py:63-95`
- Modify: `tests/test_ocr_store.py:40-78`

**Interfaces:**
- Produces `background_queue_visible_to_users: bool` in `default_ocr_settings()` and `normalize_ocr_settings()`.
- Produces `SqliteStore.cancel_pending_ocr_crop_jobs(image_hash: str) -> list[str]` and `SqliteStore.purge_completed_ocr_crop_jobs(before: str) -> list[str]`; both return only database-held crop paths.
- Changes `enqueue_ocr_crop_jobs()` so each persisted `bbox` is the 8 px expanded source crop `[left, top, right, bottom]`, which remains the coordinate origin consumed by `restore_crop_bbox()`.

- [ ] **Step 1: Write the failing settings and crop-context tests.**

  Add the visibility key to the existing expected dictionary in
  `test_normalize_ocr_settings_bounds_idle_and_cpu_limits` and add a dedicated
  boolean normalization test:

  ```python
  "background_queue_visible_to_users": False,

  def test_normalize_ocr_settings_keeps_background_queue_visibility_flag():
      assert normalize_ocr_settings({"background_queue_visible_to_users": True})[
          "background_queue_visible_to_users"
      ] is True
  ```

  Change the queue-crop fixture to a `80 x 60` image with the accepted box
  `(10, 12, 40, 30)`, then expect `[2, 4, 48, 38]` and a real persisted crop
  of `184 x 136` pixels. Add a second candidate at `(0, 0, 4, 5)` and assert
  its saved box is clipped to `[0, 0, 12, 13]`. These tests fail if the crop is
  exact, asymmetrical or uses the unexpanded origin.

- [ ] **Step 2: Run the settings and crop tests to verify they fail.**

  Run:

  ```powershell
  .\.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825' tests/test_ocr_settings.py tests/test_ocr_cache.py -q
  ```

  Expected: failures for the missing visibility key and for exact, unpadded crop coordinates.

- [ ] **Step 3: Write the failing durable-queue lifecycle tests.**

  In `tests/test_ocr_store.py`, enqueue three jobs with distinct thumbnail
  paths; complete one and set its `updated_at` by direct SQLite update to a
  known old UTC string. Assert that:

  ```python
  assert store.purge_completed_ocr_crop_jobs("2026-08-25T10:00:00.000Z") == ["old.png"]
  assert [job["status"] for job in store.list_ocr_crop_jobs()] == ["pending", "processing"]

  assert store.cancel_pending_ocr_crop_jobs("hash-a") == ["pending.png"]
  assert store.list_ocr_crop_jobs()[0]["status"] == "processing"
  ```

  This catches the two harmful mutations: deleting a processing job and retaining
  a completed job whose TTL has passed.

- [ ] **Step 4: Run the storage tests to verify they fail.**

  Run:

  ```powershell
  .\.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825' tests/test_ocr_store.py -q
  ```

  Expected: `AttributeError` for both missing repository methods.

- [ ] **Step 5: Implement the smallest persistent behavior.**

  In `ocr_settings.py`, add the false default and normalized return value:

  ```python
  "background_queue_visible_to_users": bool(
      raw.get("background_queue_visible_to_users", False)
  ),
  ```

  In `enqueue_ocr_crop_jobs()`, calculate each side before cropping:

  ```python
  crop_left = max(0, left - 8)
  crop_top = max(0, top - 8)
  crop_right = min(source.width, right + 8)
  crop_bottom = min(source.height, bottom + 8)
  crop = source.crop((crop_left, crop_top, crop_right, crop_bottom)).convert("RGB")
  ```

  Persist the four `crop_*` values as `bbox`. In `SqliteStore`, select
  `thumbnail_path` before each scoped delete, use `status = 'pending' AND
  image_hash = ?` for cancellation, and use `status = 'completed' AND
  updated_at < ?` for expiry. Return nonempty thumbnail paths after the delete
  transaction commits.

- [ ] **Step 6: Run the focused tests to verify they pass.**

  Run:

  ```powershell
  .\.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825' tests/test_ocr_settings.py tests/test_ocr_cache.py tests/test_ocr_store.py -q
  ```

  Expected: all selected tests pass.

- [ ] **Step 7: Commit the persistence change.**

  ```powershell
  git add picorgftp_sql/ocr_settings.py picorgftp_sql/services/ocr_cache.py picorgftp_sql/sqlite_store.py tests/test_ocr_settings.py tests/test_ocr_cache.py tests/test_ocr_store.py
  git commit -m "feat: manage OCR queue crop lifetime"
  ```

### Task 2: Serve the bounded, authorized queue and purge expired crops

**Files:**
- Modify: `picorgftp_sql/web/app.py:1266-1286, 5147-5351, 6558-6587`
- Modify: `tests/test_pimcore_web.py:1920-1945, 2180-2210`

**Interfaces:**
- Produces `GET /api/ocr/jobs` response `{"jobs": list[QueueRow], "remaining_count": int}`.
- `QueueRow` has exactly `thumbnail_url: str`, `status: str`, and `result: list[str]`.
- Produces `_purge_expired_ocr_crop_jobs() -> int`, which calls the store with a UTC cutoff of now minus 10 seconds and only deletes files underneath `_ocr_crop_root()`.

- [ ] **Step 1: Write the failing public-projection and access tests.**

  Replace the existing broad admin queue assertion in `test_admin_can_read_ocr_slots_and_background_queue` with one processing job, five pending jobs, and one completed job containing
  `{"text": "20kg", "comparison": "20"}`, and an on-disk crop. Patch
  `_current_user_payload` to return an admin and assert:

  ```python
  payload = client.get("/api/ocr/jobs").json()
  assert len(payload["jobs"]) == 5
  assert payload["remaining_count"] == 2
  assert payload["jobs"][0]["status"] == "processing"
  assert payload["jobs"][-1]["result"] == ["20kg → 20"]
  assert set(payload["jobs"][0]) == {"thumbnail_url", "status", "result"}
  ```

  Add one non-admin request with `background_queue_visible_to_users: False`
  expecting HTTP 403, then set it true and expect HTTP 200. This fails if the
  route still requires admin unconditionally or leaks internal row fields.

- [ ] **Step 2: Write the failing expiry cleanup test.**

  Create a completed job pointing to a real file under a patched crop root,
  set its `updated_at` to more than ten seconds old, call the queue route, and
  assert both `jobs == []` and `not crop_path.exists()`. Also retain a pending
  job older than the cutoff and assert it remains. This catches cleanup that
  removes every old queue item instead of completed items only.

- [ ] **Step 3: Run the route tests to verify they fail.**

  Run:

  ```powershell
  .\.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825' tests/test_pimcore_web.py -k "ocr and (queue or startup_cleanup)" -q
  ```

  Expected: the old API returns unbounded, internal rows and does not remove the completed crop.

- [ ] **Step 4: Implement bounded projection and trusted expiry.**

  Add module constants:

  ```python
  OCR_QUEUE_VISIBLE_LIMIT = 5
  OCR_QUEUE_COMPLETED_TTL_SECONDS = 10
  ```

  `_purge_expired_ocr_crop_jobs()` computes an ISO UTC cutoff, invokes
  `purge_completed_ocr_crop_jobs`, checks every returned path with
  `_path_is_under_root(path, _ocr_crop_root())`, and removes only existing files
  that pass that check. Call it at the beginning of `_run_ocr_queue_once()` and
  before listing jobs so expiry works even when background OCR is disabled.

  In `ocr_jobs`, call `_current_user_payload(request)`. Permit role `admin`; for
  other roles require normalized setting `background_queue_visible_to_users`.
  Build rows in this priority order while preserving the store's chronological
  order inside `processing` and `pending`, and reversing only completed jobs:

  ```python
  processing = [job for job in jobs if job.get("status") == "processing"]
  pending = [job for job in jobs if job.get("status") == "pending"]
  completed = [job for job in jobs if job.get("status") == "completed"]
  ordered = processing + pending + list(reversed(completed))
  visible = ordered[:OCR_QUEUE_VISIBLE_LIMIT]
  ```

  Format each result as `text` when comparison is blank or equal, otherwise
  `f"{text} → {comparison}"`; return only the three documented fields and a
  signed `thumbnail_url` when its trusted file still exists.

- [ ] **Step 5: Run the route tests to verify they pass.**

  Run:

  ```powershell
  .\.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825' tests/test_pimcore_web.py -k "ocr and (queue or startup_cleanup)" -q
  ```

  Expected: safe projection, visibility rule, ordering, limit and completed-only cleanup all pass.

- [ ] **Step 6: Commit the API change.**

  ```powershell
  git add picorgftp_sql/web/app.py tests/test_pimcore_web.py
  git commit -m "feat: expose bounded OCR refinement queue"
  ```

### Task 3: Restrict OCR-idle activity and cancel a removed slot's pending work

**Files:**
- Modify: `picorgftp_sql/web/app.py:5336-5351, 6558-6589`
- Modify: `tests/test_pimcore_web.py:1945-1975, 2180-2240`
- Modify: `tests/test_ocr_queue.py:1-112`

**Interfaces:**
- Produces `_is_ocr_blocking_request(request: Request) -> bool`.
- Produces `POST /api/ocr/activity` accepting `{"kind": "slot-change" | "data-load", "removed_slot_token": str}` and returning `{"ok": true, "cancelled": int}`.
- Uses the existing CSRF/same-origin mutation middleware and `_path_from_file_token()`; clients never submit a content hash or filesystem path.

- [ ] **Step 1: Write the failing request-classification tests.**

  Extend the existing progress-poll test with hand-built Request-like objects
  and assert the precise boundary:

  ```python
  assert _is_ocr_blocking_request(post("/api/upload-cache")) is True
  assert _is_ocr_blocking_request(post("/api/process/background")) is True
  assert _is_ocr_blocking_request(post("/api/ocr/activity")) is True
  assert _is_ocr_blocking_request(get("/api/settings")) is False
  assert _is_ocr_blocking_request(get("/api/settings/ocr/runs/run-1")) is False
  assert _is_ocr_blocking_request(get("/api/pimcore/objects")) is False
  ```

  In the scheduler test, make `last_activity` mutable, simulate a settings GET,
  and assert the value is unchanged; then simulate a marked activity and assert
  the scheduler returns `idle_wait` until its configured timeout passes.

- [ ] **Step 2: Write the failing slot-removal endpoint test.**

  Issue a token for a real file below a patched upload-cache root, enqueue one
  pending row with the matching SHA-256 and one with another hash, call
  `/api/ocr/activity` with `removed_slot_token`, and assert:

  ```python
  assert response.json() == {"ok": True, "cancelled": 1}
  assert not matching_crop.exists()
  assert other_crop.exists()
  ```

  Use the real `SqliteStore`, `_file_token`, `_image_sha256` and route; patch
  only authentication. This fails if the browser-provided token is ignored or
  if cancellation deletes a different image's crop.

- [ ] **Step 3: Run the activity tests to verify they fail.**

  Run:

  ```powershell
  .\.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825' tests/test_ocr_queue.py tests/test_pimcore_web.py -k "ocr and (activity or idle or queue)" -q
  ```

  Expected: missing classifier and activity endpoint failures.

- [ ] **Step 4: Implement exact activity classification and cancellation.**

  Define the only automatic blockers as POST routes
  `/api/upload-cache`, `/api/web-images/cache`, `/api/process/background` and
  `/api/ocr/activity`. In `_prioritize_interactive_work`, increment
  `ocr_active_requests` and update `ocr_last_activity` only when this helper
  returns true; leave every other request completely outside that state.

  The activity route requires `_require_user(request)` and the OCR feature,
  parses a dict body, accepts only `slot-change` and `data-load`, then sets
  `ocr_last_activity` under `ocr_activity_lock`. If `removed_slot_token` is a
  nonempty string, resolve it with `_path_from_file_token`, calculate its SHA-256
  server-side, call `cancel_pending_ocr_crop_jobs`, and delete only returned
  files inside `_ocr_crop_root()`. Return the number of cancelled queue rows.

- [ ] **Step 5: Run the activity tests to verify they pass.**

  Run:

  ```powershell
  .\.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825' tests/test_ocr_queue.py tests/test_pimcore_web.py -k "ocr and (activity or idle or queue)" -q
  ```

  Expected: unrelated navigation does not extend idle time, approved operations do, and removal cancels only matching pending work.

- [ ] **Step 6: Commit the activity change.**

  ```powershell
  git add picorgftp_sql/web/app.py tests/test_ocr_queue.py tests/test_pimcore_web.py
  git commit -m "feat: limit OCR queue activity signals"
  ```

### Task 4: Move the queue into the workspace and wire its browser activity signals

**Files:**
- Modify: `picorgftp_sql/web/static/index.html:135-145`
- Modify: `picorgftp_sql/web/static/app.js:120-160, 316-322, 3568-3682, 7747-7910, 13940-14310, 14928-14945`
- Modify: `picorgftp_sql/web/static/app.css:720-838, 1483-1518`
- Modify: `tests/test_web_ui_integrity.py:80-120, 1030-1220`

**Interfaces:**
- Adds `#ocrBackgroundQueuePanel`, `#ocrBackgroundQueueSummary` and `#ocrBackgroundQueueList` immediately after `#processQueuePanel`'s section and before `#slotsTitle`.
- Adds `renderOcrBackgroundQueue(payload)`, `refreshOcrBackgroundQueue()` and `recordOcrActivity({ removedSlotToken?: string, kind?: "slot-change" | "data-load" })`.
- Adds `background_queue_visible_to_users` to the existing OCR settings save payload and renders it only as the administrator's visibility checkbox.

- [ ] **Step 1: Write the failing browser-rendering contract test.**

  In `tests/test_web_ui_integrity.py`, extract the renderer and run it with the
  existing Node fake-DOM pattern. Feed this hand-written API payload:

  ```javascript
  { jobs: [
      { thumbnail_url: "/api/file?token=crop-1", status: "processing", result: [] },
      { thumbnail_url: "/api/file?token=crop-2", status: "completed", result: ["20kg → 20"] },
    ], remaining_count: 7 }
  ```

  Assert that both images use their supplied signed URL, the completed text is
  rendered, and the summary equals `+7 kolejnych`. Separately assert HTML index
  order:

  ```python
  assert html.index('id="ocrBackgroundQueuePanel"') > html.index('id="processQueuePanel"')
  assert html.index('id="ocrBackgroundQueuePanel"') < html.index('id="slotsTitle"')
  ```

  The implementation step below changes `.ocr-background-queue-item img` to
  `object-fit: contain`; confirm it visually in the final browser pass rather
  than adding a brittle source-text assertion.

- [ ] **Step 2: Write the failing browser activity contract test.**

  Extract the slot helpers with Node, arrange a loaded photo `{ token:
  "old-slot-token" }`, clear it, and capture requests. Assert the only emitted
  request is:

  ```javascript
  {
    path: "/api/ocr/activity",
    method: "POST",
    body: { kind: "slot-change", removed_slot_token: "old-slot-token" }
  }
  ```

  Add a second case moving a slot and assert it sends `slot-change` without a
  removal token. This catches a regression where a move cancels its still-active
  image or a clear leaves a queued crop behind.

- [ ] **Step 3: Run the UI contract tests to verify they fail.**

  Run:

  ```powershell
  .\.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825' tests/test_web_ui_integrity.py -k "ocr or slot" -q
  ```

  Expected: absent workspace queue panel, no queue activity request, and `cover` crop styling.

- [ ] **Step 4: Implement the compact workspace panel and safe polling.**

  Insert an `ocr-background-queue-section` directly after the current process
  queue section. Extend the workspace grid areas to four left-column rows:

  ```css
  grid-template-areas:
    "product slots"
    "queue slots"
    "ocrqueue slots"
    "result slots";
  ```

  Render the queue directly into fixed DOM nodes, never into settings. Use the
  safe API response, display one `article` per row with thumbnail, Polish state
  label and result, and display `+${remaining_count} kolejnych` only when the
  count is positive. An unavailable (403) queue hides the entire panel without
  showing an error. Add a `createPoller("ocr-queue", 2000,
  refreshOcrBackgroundQueue)` only after bootstrap and invoke an initial refresh
  after `loadBootstrap()`; this lets completed rows vanish within their 10-second
  lifecycle without user navigation.

  Style the panel with the same compact left-column visual language as the
  process queue. Constrain the image box, use `object-fit: contain`, and retain
  the processing-state highlight. Remove `queueOutput` and the `/api/ocr/jobs`
  request from `renderSettingsOcr()`; add a single checkbox labeled
  `Pokaz kolejke dopracowywania OCR uzytkownikom` to its collection group and
  include `background_queue_visible_to_users` in `settingsSaveButton` data.

- [ ] **Step 5: Implement browser activity calls at the allowed moments.**

  `recordOcrActivity` posts JSON through `requestJson`, allowing the existing
  CSRF helper to attach protection, and deliberately ignores its own failure so
  a local slot edit remains usable while the server reconnects. Call it before:

  - `setSlotFile` replaces or uploads a slot, passing the previous selected
    file or photo token as `removed_slot_token` when present;
  - `clearSlotAssignment` removes a selected file or photo, passing that token;
  - `moveSlotContent` completes a move or swap, without a removal token;
  - `submitProductForm` starts Synchronize/Update, without a removal token;
  - `fillForm(..., { loadPhotos: true })` starts product/photo loading, with
    `kind: "data-load"`.

  Do not call it from settings rendering, Pimcore dialogs, normal searches,
  health/log/resource polling, OCR diagnostics polling or queue polling.

- [ ] **Step 6: Run the UI contract tests to verify they pass.**

  Run:

  ```powershell
  .\.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825' tests/test_web_ui_integrity.py -k "ocr or slot" -q
  ```

  Expected: panel placement, five-row renderer contract, visible overflow count,
  no settings queue, safe activity calls and uncut crop preview all pass.

- [ ] **Step 7: Commit the browser change.**

  ```powershell
  git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css tests/test_web_ui_integrity.py
  git commit -m "feat: show OCR refinement queue beside slots"
  ```

### Task 5: Document the operational behavior and verify the integrated change

**Files:**
- Modify: `docs/pimcore.md:OCR section`
- Modify: `docs/web-panel.md:Diagnostyka OCR section`
- Modify: `tests/test_pimcore_web.py` only if integrated route coverage exposes a real contract gap

**Interfaces:**
- Documents the user-visible queue, role visibility switch, five-row limit,
  10-second completed result lifetime, 8 px crop margin, and precise definition
  of OCR-blocking activity.

- [ ] **Step 1: Write the documentation-facing acceptance checklist.**

  Add a concise Markdown list to both OCR documentation sections stating the
  literal user-observable contract: queue under the ordinary left queue; only
  crop/result; five visible and `+N`; result disappears after 10 seconds; normal
  browsing and Pimcore do not reset idle time; a deleted slot cancels its pending
  scan. Do not add a source-text test for prose.

- [ ] **Step 2: Run the complete regression suite.**

  Run:

  ```powershell
  .\.venv\Scripts\pytest.exe --basetemp '.pytest-ocr-codex-20260825' -q
  ```

  Expected: all tests pass, with the repository's existing intentional skip if present.

- [ ] **Step 3: Check JavaScript syntax and whitespace.**

  Run:

  ```powershell
  & 'C:\Program Files\nodejs\node.exe' --check picorgftp_sql\web\static\app.js
  git diff --check
  ```

  Expected: Node exits 0 and Git reports no whitespace errors.

- [ ] **Step 4: Remove the verified test scratch directory.**

  Resolve `.pytest-ocr-codex-20260825` beneath the repository, confirm it is the
  exact test directory, then remove that directory only. Re-run `git status --short`
  to confirm no test artifacts are tracked.

- [ ] **Step 5: Commit documentation and any integration-test correction.**

  ```powershell
  git add docs/pimcore.md docs/web-panel.md tests/test_pimcore_web.py
  git commit -m "docs: explain OCR refinement queue behavior"
  ```

## Plan Self-Review

1. **Spec coverage:** Task 1 implements settings, 8 px context, record cleanup and cancellation. Task 2 implements safe roles, five-row projection, overflow count and ten-second completed expiry. Task 3 limits idle activity and protects deletion by signed token. Task 4 implements the requested position, crop-only/result-only view, proportional preview and browser signals. Task 5 documents and fully verifies every supplied acceptance criterion.
2. **Placeholder scan:** The plan contains no deferred work markers or generic test instructions; every task names files, interfaces, commands and expected behavior.
3. **Type consistency:** The store returns `list[str]` trusted paths to backend cleanup. The activity route accepts `removed_slot_token`, and browser helper sends that exact JSON key. The queue route returns `jobs` plus `remaining_count`; the browser renderer consumes that exact payload.

## Execution Handoff

The plan is ready at `docs/superpowers/plans/2026-08-25-ocr-queue-visibility-and-activity.md`. The user asked to proceed on this current branch, so execute it inline with `superpowers:executing-plans`, maintaining the test-first cycle and reviewing after each task.
