# Task 5 report: bounded audited memory-growth paths

## Scope

- Bounded both desktop thumbnail queues at two thumbnail-memory windows (100
  entries), changed request and result writes to non-blocking operations, and
  made pending state reflect only successfully queued work. A dropped result
  clears only its matching request token so a newer request remains pending.
- Added a 120-entry browser FTP-preview LRU helper. Network writes and both cache
  read sites go through the helper, so reads touch recency and the oldest entry
  is evicted above the cap.
- Retained every queued/running process job while bounding recent terminal jobs
  to the newest 200 entries within the existing six-hour retention period.
- Added lifetime cleanup for upload-scan metadata (missing backing file or older
  than 24 hours) and rate-limit keys (per-scope expiry window). The internal scan
  timestamp is removed from returned scan details.
- Preserved the existing resource-monitor implementation and Task 4 resource UI.

## TDD evidence

- The initial RED queue test hung because the old blocking `Queue.put` was called
  synchronously against a full one-slot test queue. After isolating the stack and
  queue state, the test used a bounded daemon-thread join and failed explicitly
  with `thumbnail enqueue must be non-blocking`.
- The required RED selection then completed with five intended failures: missing
  queue cap, blocking request/result writes, missing completed-job cap, and
  missing rate-limit pruning.
- Separate RED tests failed for missing upload-scan pruning and the FTP LRU helper.
- Self-review found that preprocessing deletes the source upload before copying
  antivirus metadata. A regression test failed until copy-before-prune preserved
  metadata on the processed path.
- A dropped-result pending-state test failed until the worker cleared its matching
  token; a companion test confirms a newer pending token is preserved.

## Verification

- Focused bounded-memory suite: 8 passed.
- Required related suite: 127 passed, 23 subtests passed.
- Upload/antivirus related selection: 21 passed, 20 subtests passed.
- Fresh full suite: 1,000 passed, 52 subtests passed, with 13 existing
  FastAPI/Starlette deprecation warnings.
- JavaScript syntax checking with Node was unavailable because Node is not
  installed; the full static UI integrity suite passed.

## Self-review

- Confirmed the request path writes pending state only after `put_nowait`
  succeeds, while token advancement still invalidates stale work.
- Confirmed full result queues cannot block the thumbnail worker and cannot erase
  a newer pending request for the same slot/path.
- Confirmed process-job count eviction is newest-first and never considers active
  statuses for removal.
- Confirmed scan timestamps remain internal and source-replacement metadata is
  copied before missing-file pruning.
- Confirmed there is exactly one raw `ftpPreviewCache.set` site, inside the LRU
  helper, and both read paths touch entries through that helper.
- `git diff --check` and scoped status checks are part of final pre-commit
  verification.

## Commit

This report is included in the commit `fix: bound resource monitoring caches`.

## Residual risks

- Browser cache behavior is guarded by static source-integrity tests rather than
  an executed JavaScript unit test because the repository has no JS test runner
  and Node is unavailable in this environment.

## Review follow-up: pending-state synchronization and lifecycle cleanup

### Scope

- Added one desktop pending-state lock plus per-slot pending tokens. Request
  enqueue now holds the lock across token publication, non-blocking queue
  publication, and path/token pending publication. A result-full worker must
  acquire that same lock before clearing only its own pending token/path.
- Normal result polling now compares the queued result token with the current
  pending token before removing pending state. A stale same-path result cannot
  erase a newer request; a matching result removes both path and token.
- Added locked path/token clearing to slot clear, fit toggle, and clear-all flows,
  including compatibility with existing lightweight desktop test harnesses.
- Extracted `_cleanup_process_jobs_locked()` and invoked it inside the existing
  process-job lock immediately after both success and failure transitions.

### TDD and regression evidence

- Four coordinated RED cases reproduced all review blockers: worker-before-
  pending publication, stale result removal, matching result token cleanup, and
  204 lifecycle transitions retaining more than 200 terminal jobs.
- A further RED helper test caught paired path/token cleanup, then the first full
  run caught the existing `_ClearSlotsHarness` compatibility regression after
  1,004 passes. The exact existing test plus all desktop helpers then passed.
- Blocker-focused GREEN: 9 passed.
- Required related suite: 131 passed, 23 subtests passed.
- Final fresh full suite: 1,005 passed, 52 subtests passed, with the same 13
  existing FastAPI/Starlette deprecation warnings.

### Deadlock and lifecycle review

- The producer uses only `put_nowait` while holding the pending lock. The worker
  releases queue internals before acquiring that lock on a result-full path, so
  there is no queue-lock/pending-lock cycle.
- Cleanup considers only terminal jobs, runs under `_PROCESS_JOBS_LOCK`, and
  preserves queued/running jobs throughout completion and failure transitions.
- A fresh independent read-only review of the corrected working tree reported no
  Critical, Important, or Minor findings and assessed it ready.

### Follow-up commit

This follow-up is included in `fix: synchronize bounded thumbnail state`.
