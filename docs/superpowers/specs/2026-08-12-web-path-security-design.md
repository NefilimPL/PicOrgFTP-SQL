# Web path security design

## Goal

Remove path-traversal risks from the web panel and make every file-system
operation that can receive request-derived data verify an explicit trusted
root.  The change must preserve signed file tokens, Windows mapped/network
photo roots, and the existing upload and preview workflows.

## Root cause

The web application has several local safeguards: signed preview tokens,
filename cleaning, and ad-hoc `abspath`/`commonpath` comparisons.  They are
implemented independently by upload, cache, staging, preview, and deletion
code.  Consequently, request-derived values can still reach file APIs through
path expressions, and the checks do not consistently canonicalize symbolic
links or prove containment at every destructive operation.

## Design

Add a focused path-security helper with two responsibilities:

1. Resolve a candidate path and every permitted root to canonical paths,
   including symbolic-link resolution, then require that the candidate is a
   descendant of one permitted root.  It will optionally require an existing
   regular file.
2. Build a child path only from non-absolute segments and verify the resulting
   canonical path remains within its root.  Request-derived names and scopes
   remain sanitized, but the containment check is the security boundary.

The web application will use these helpers at every file-system boundary:

- staging and upload-cache creation, reading, renaming, validation, scanning,
  and failed-upload cleanup;
- cached web-image writes and cache cleanup;
- signed-token resolution before previews, thumbnails, processing, and local
  deletion;
- job-directory cleanup and any recursive deletion of managed staging data.

The token signature remains an authorization property; containment within the
configured photo/cache roots remains an independent authorization property.
No raw client path will become trusted merely because it is signed or has a
safe-looking filename.

## Compatibility and error handling

Existing valid files below the configured photo directory, FTP cache, and web
upload cache keep working.  Root comparison is case-insensitive on Windows
and continues to support a configured drive letter that resolves to a network
share.  Invalid, absolute, traversing, or link-escaping paths fail before I/O
with the existing appropriate HTTP error family (400 for invalid uploads,
403 for unauthorized file access, and safe skip/no-op for background cleanup).

## Testing

Regression tests will prove that the shared helper rejects traversal,
absolute-path segments, and symbolic links escaping a managed root while
accepting valid descendants.  Web tests will cover token preview/deletion and
upload staging/cache behavior.  The affected test modules and the full Python
test suite will be run after implementation.
