# Observability Live Checkpoint Design

## Goal

Guarantee a lossless handoff from the 24-hour live-log snapshot to the durable SSE stream while preserving pause semantics, request ordering, and exact incident/job navigation.

## Atomic snapshot contract

`SqliteStore.snapshot_operational_event_stream(since, limit=2000)` uses one SQLite read transaction and one connection. It reads the current maximum stream ledger row, exposes only that row's opaque `event_id` as `stream_after_id`, and selects the newest surviving `operational_events` whose ledger sequence is at or below the captured high-water and whose timestamp is within the requested window. It returns at most 2,000 items in chronological display order. A ledger row remains a valid marker after its event payload is pruned; an empty ledger returns an empty marker. The private integer sequence never leaves the store method.

`GET /api/observability/events?live_seed=1&since=...` is admin-only and delegates to this snapshot. Its response adds `stream_after_id`; it does not expose a cursor or sequence. The ordinary events endpoint keeps its current filters, cursor behavior, default limit 20, and maximum limit 100.

## Client handoff and pause behavior

The browser requests the atomic seed first. Only the latest seed generation may merge state or open the stream. It then opens exactly one EventSource using `after_id=stream_after_id` when the marker is nonempty. The server resolves that durable ledger marker, so all rows inserted after the snapshot drain in pages of 100, including more than 100 rows and reconnects before the first delivered frame.

When live output is paused, seed and SSE records are deduplicated against both visible items and the pause buffer, then placed only in the bounded pause buffer. Neither forced refresh nor stream callbacks mutate or render `live.items`; resume performs the single merge and render. EventSource `onopen` continues to show `Wstrzymano` while paused.

## Navigation and unread ordering

Global incident discovery pages are temporary and never populate severity caches. Once the exact incident and its real severity are known, a separate severity-filtered cursor walk resets and fills only that severity tab until the target is present or the feed ends, preserving its `nextCursor`. Jobs use their own feed and maintain the jobs cache/cursor. No severity is inferred from a job record.

Unread request generations are allocated synchronously when a request is dispatched, including read mutations. A response applies its unread snapshot only if its dispatch generation is still current; a stale read response therefore cannot overwrite a newer poll or list response.

## Verification

Store tests cover empty ledgers, surviving 24-hour selection, a deleted marker, insertion after the checkpoint, draining more than 100 later events, and absence of sequence fields. API tests cover authorization, the live-seed response, and unchanged normal pagination. Source/UI tests cover seed-before-stream, marker URL construction, paused refresh buffering, paused connection status, dispatch-time unread ordering, and isolated exact navigation caches.
