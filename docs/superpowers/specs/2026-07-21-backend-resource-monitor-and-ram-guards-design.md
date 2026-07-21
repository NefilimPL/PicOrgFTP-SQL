# Backend resource monitor and RAM guards — design

## Goal

Detect and diagnose excessive resource use by the PicOrgFTP-SQL backend on the host computer, including when no browser user is active. Show compact live system and backend metrics in the web header, retain a bounded diagnostic record only when the backend itself crosses a resource threshold, and guard known unbounded in-memory paths.

## Scope

The feature applies to the web backend running on Windows and to the existing desktop thumbnail queue safeguards.

It includes:

- host CPU, RAM and disk-activity telemetry;
- backend CPU, RAM and disk-I/O telemetry;
- an always-running, low-overhead sampler and threshold detector;
- a compact resource badge below the existing backend health badge, with a detailed hover/focus popover;
- globally configurable visibility and alert thresholds;
- a safe diagnostic simulation and a bounded real-resource test for administrators;
- memory-bound protections for thumbnail work, FTP preview data and completed jobs.

It does not treat high system usage alone as a backend incident and it does not try to attribute all host disk activity to PicOrgFTP-SQL.

## Metrics

The sampler runs every five seconds in a daemon thread started with the web application and stopped during shutdown. It caches its latest normalized sample; the health endpoint reads this cache and never performs an expensive resource probe per browser request.

### Host metrics

- `cpu_percent`: system CPU utilization over the sampling interval.
- `memory_percent`, `memory_used_bytes`, `memory_total_bytes`: physical-memory state.
- `disk_busy_percent`: aggregate physical-disk active time. If the Windows counter is unavailable, this field is unavailable instead of guessed.
- `observed_at`: canonical UTC timestamp.

### Backend metrics

- `cpu_percent`: CPU use of the backend and any registered real-test worker, normalized to host logical CPUs.
- `memory_working_set_bytes`, `memory_private_bytes`, `memory_percent`: current backend memory footprint.
- `disk_read_bytes_per_second`, `disk_write_bytes_per_second`, `disk_io_bytes_per_second`: backend I/O deltas over the interval.
- `active_jobs`, `queued_jobs`, `active_clients`: lightweight runtime context.
- `observed_at`: canonical UTC timestamp.

Host disk activity is a host-wide percentage. Backend disk usage is expressed as read/write throughput because a reliable share of physical-disk busy time cannot be attributed to one process.

Windows-native counters and APIs are preferred so the packaged application does not acquire a new runtime dependency. Unsupported counters return an explicit unavailable value and cannot on their own raise a warning.

## Detection and observability

The monitor evaluates only backend CPU, RAM and I/O against configured thresholds. Two consecutive five-second samples above a threshold are required before an incident is opened. A latch suppresses repeats until two normal samples have occurred; the existing observability incident grouping supplies its normal durable deduplication as an additional layer.

The warning event is a `backend.resource_high` observability event. Its redacted details contain the trigger metric and threshold, current host and backend measurements, job/client context, registered test-worker state and the bounded preceding one-minute sample history. It contains no credentials, request bodies or file contents.

High CPU, RAM or disk activity elsewhere on the host does not create this warning. It remains visible in the status popover as context only.

## Interface and settings

A resource indicator sits directly below the existing backend health control. Its compact, always-visible form is:

```
System:  CPU 60% · RAM 80% · DYSK 20%
Backend: CPU  4% · RAM  3% · I/O 1.2 MB/s
```

Color reflects backend threshold state, not host-only load. Hover, keyboard focus or click opens details with raw memory values, backend read/write rates, sample time, active thresholds, unavailability explanations and current detector state.

Global administrator settings provide:

- a `show_resource_status` visibility switch; it controls the display only, not monitoring or alerts;
- CPU, RAM and backend-I/O alert thresholds;
- a test section with safe and real test actions, their limits and their result.

The health response carries a safe `resources` projection so the existing five-second frontend health poll can update the badge without another browser poller.

## Diagnostic tests

Both actions are administrator-only and CSRF-protected.

### Safe simulation

The safe action records a clearly labelled test diagnostic snapshot without creating real resource load. It verifies visibility, redaction and observability persistence but does not claim that a threshold was organically crossed.

### Real resource test

The real action starts a registered helper process that is included in backend telemetry aggregation. The action itself does not create an alert. The ordinary sampler must observe two consecutive threshold breaches and create the same `backend.resource_high` event used for a production incident. If the chosen threshold is not crossed, the UI reports that no incident was generated.

The helper always has a hard 20-second deadline, a stop signal and `finally` cleanup. Its maximum envelope is:

- no more than 25% of aggregate host CPU capacity;
- no more than 256 MiB additional memory;
- no more than 128 MiB temporary disk data and throttled I/O;
- automatic deletion of temporary files and process registration on success, failure, timeout and backend shutdown.

The UI can choose CPU, RAM or disk I/O. A request whose configured threshold cannot be reached within the hard cap is rejected before launch with an explanation. This prevents a misleading false-positive test and avoids a persistent high-load process.

## Memory-growth safeguards

The audit identified potential growth vectors but did not reproduce the reported 1.5 GB event. The implementation therefore treats them as bounded-risk protections rather than claiming a confirmed root cause.

- The desktop thumbnail request/result pipeline becomes bounded and deduplicated. A request is marked pending only after successful enqueue; stale or overflow work is skipped and can be requested again after the next visible-window refresh.
- The browser FTP preview cache uses a fixed-size LRU policy and evicts stale entries.
- Completed in-memory process jobs have both retention and count/size bounds. Durable job history remains in SQLite.
- Upload-scan and rate-limit helper maps prune expired entries rather than retaining inactive keys indefinitely.

Each bound favors recomputing small display data over retaining indefinitely growing memory. It does not drop active process jobs or uploaded files.

## Error handling

Sampler failures are isolated: the last good sample remains available, the unavailable metric is labelled, and the monitor continues with the next interval. The monitor must never fail a business operation, health endpoint or application shutdown.

The real test reports launch, early exit, timeout and cleanup failures to the administrator and records a redacted diagnostic event. Shutdown signals and joins the helper within a short bounded wait; a stale registration is removed even if the process has already exited.

## Verification

Automated tests cover:

- normalized host/backend samples, unavailable disk counters and sampling deltas;
- threshold evaluation, two-sample confirmation, recovery latch and event deduplication;
- warning details, redaction and absence of host-only alerts;
- health API resource projection and global display setting normalization;
- safe simulation persistence;
- real-test limits, threshold-driven detection, timeout and cleanup using controlled fake workers;
- the frontend compact indicator, accessible detail popover and setting-controlled visibility;
- thumbnail queue overflow/retry behavior, cache LRU eviction and helper-map pruning.

The final manual check runs the real CPU, RAM and I/O test modes one at a time on Windows and verifies that no worker or temporary file remains after each test.
