# Web Path Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every request-derived web file path is canonically contained within an explicit trusted root before I/O.

**Architecture:** A dependency-free `path_security` module owns trusted-root resolution and safe child construction. `web.app` and `web.upload_staging` apply it at each request-facing filesystem boundary; signed tokens remain compatible but are no longer the sole check.

**Tech Stack:** Python, pathlib, FastAPI/Starlette, pytest.

## Global Constraints

- Canonicalize candidates and roots, including link resolution, before containment checks.
- Preserve Windows case-insensitive and mapped-drive/network-share behaviour.
- Add no third-party dependency and preserve signed-token format.
- Invalid upload paths fail with HTTP 400; invalid file tokens fail with HTTP 403; cleanup skips invalid paths.

---

## File structure

- Create `picorgftp_sql/path_security.py`: generic canonical containment primitives.
- Create `tests/test_path_security.py`: direct security regression tests.
- Modify `picorgftp_sql/web/upload_staging.py`: protected staged-file paths and cleanup.
- Modify `picorgftp_sql/web/app.py`: protected cache, preview, and deletion paths.
- Modify `tests/test_upload_staging.py` and `tests/test_web_app_files.py`: integration regressions.

### Task 1: Trusted path primitives

**Files:** Create `picorgftp_sql/path_security.py`; create `tests/test_path_security.py`.

**Interfaces:** `PathSecurityError(ValueError)`; `resolve_path_within_roots(path, roots, *, require_exists=False, require_file=False) -> Path`; `build_child_path(root, *segments) -> Path`.

- [ ] **Step 1: Write failing tests**

```python
def test_resolve_path_within_roots_rejects_traversal(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    with pytest.raises(PathSecurityError):
        resolve_path_within_roots(root / ".." / "outside", [root])

def test_build_child_path_rejects_absolute_or_nested_segment(tmp_path):
    with pytest.raises(PathSecurityError):
        build_child_path(tmp_path, "..", "secret.txt")

def test_resolve_path_within_roots_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"; outside = tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathSecurityError):
        resolve_path_within_roots(root / "escape" / "secret.txt", [root])
```

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_path_security.py -v`; it must fail because the module does not exist.

- [ ] **Step 3: Implement the smallest API**

```python
class PathSecurityError(ValueError):
    pass

def resolve_path_within_roots(path, roots, *, require_exists=False, require_file=False) -> Path:
    target = Path(path).resolve(strict=False)
    for root in roots:
        trusted_root = Path(root).resolve(strict=False)
        try:
            target.relative_to(trusted_root)
        except ValueError:
            continue
        if require_exists and not target.exists(): raise PathSecurityError("path does not exist")
        if require_file and not target.is_file(): raise PathSecurityError("path is not a file")
        return target
    raise PathSecurityError("path is outside trusted roots")
```

`build_child_path` rejects absolute, empty, dot, parent, and separator-containing segments; it returns `resolve_path_within_roots(root / segment, [root])`.

- [ ] **Step 4: Verify GREEN**

Run `pytest tests/test_path_security.py -v`; it must pass (skip only symlink creation when Windows privileges disallow it).

- [ ] **Step 5: Commit**

Run `git add picorgftp_sql/path_security.py tests/test_path_security.py` then `git commit -m "feat: add trusted path security helpers"`.

### Task 2: Protect staged uploads

**Files:** Modify `picorgftp_sql/web/upload_staging.py`; modify `tests/test_upload_staging.py`.

**Interfaces:** Consume Task 1 helpers. Extend `UploadStagingService.stage(upload, job_dir, prefix, *, managed_root=None) -> StagedUpload`; preserve `cleanup_job_directory(...) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.anyio
async def test_stage_rejects_job_directory_outside_managed_root(tmp_path):
    managed_root = tmp_path / "managed"; managed_root.mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    with pytest.raises(PathSecurityError):
        await UploadStagingService().stage(
            upload_file("photo.jpg", jpeg_bytes()), str(outside), "01",
            managed_root=str(managed_root),
        )
```

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_upload_staging.py::test_stage_rejects_job_directory_outside_managed_root -v`; it must fail because `stage` does not yet accept or enforce `managed_root`.

- [ ] **Step 3: Implement the smallest change**

Resolve `job_dir` against `managed_root` when supplied, then build the generated staging filename with `build_child_path(job_dir, generated_name)`. Resolve that target against `job_dir` before validation, scanning, and failed-upload removal.  The application passes `_PROCESS_JOB_ROOT` as `managed_root`. In `cleanup_job_directory`, use the shared canonical resolver before `rmtree`, retaining its direct-child, active-path, and symlink checks.

- [ ] **Step 4: Verify GREEN**

Run `pytest tests/test_upload_staging.py -v`; it must pass.

- [ ] **Step 5: Commit**

Run `git add picorgftp_sql/web/upload_staging.py tests/test_upload_staging.py` then `git commit -m "fix: constrain upload staging paths"`.

### Task 3: Protect cache, tokens, and deletion

**Files:** Modify `picorgftp_sql/web/app.py`; modify `tests/test_web_app_files.py`.

**Interfaces:** Consume Task 1 helpers. Add `_file_token_roots() -> list[str]`; preserve `_path_from_file_token(token, require_exists=True) -> str` and current token encoding.

- [ ] **Step 1: Write failing tests**

```python
def test_file_token_rejects_signed_symlink_escaping_photos_root(tmp_path, monkeypatch):
    photos = tmp_path / "photos"; outside = tmp_path / "outside"
    photos.mkdir(); outside.mkdir(); (outside / "secret.jpg").write_bytes(b"secret")
    (photos / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(web_app.settings, "l", str(photos))
    with pytest.raises(HTTPException, match="poza katalogiem"):
        web_app._path_from_file_token(web_app._file_token(str(photos / "escape" / "secret.jpg")))

def test_delete_local_files_skips_path_outside_trusted_roots(tmp_path, monkeypatch):
    outside = tmp_path / "outside.jpg"; outside.write_bytes(b"keep")
    monkeypatch.setattr(web_app.settings, "l", str(tmp_path / "photos"))
    assert web_app._delete_local_files([{"local_path": str(outside)}], set())["deleted"] == 0
    assert outside.exists()
```

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_web_app_files.py -k "delete_local_files_skips_path" -v`; it must fail because direct callers of `_delete_local_files` are not yet contained. The signed-symlink test documents and preserves the existing token protection while it is refactored to the shared helper.

- [ ] **Step 3: Implement the smallest change**

`_file_token_roots` returns the photo root, FTP preview cache, and upload cache. `_path_from_file_token` verifies the signature, then calls `resolve_path_within_roots`; translate `PathSecurityError` to HTTP 403. Build upload-cache scope directories and random cache filenames with `build_child_path`; re-resolve before rename, validation, scanning, and removal. Revalidate `local_path` in `_delete_local_files` against `_file_token_roots` before `os.remove`, skipping invalid values.

- [ ] **Step 4: Verify GREEN**

Run `pytest tests/test_web_app_files.py tests/test_upload_staging.py -v`; it must pass, including mapped-drive and casing tests.

- [ ] **Step 5: Commit**

Run `git add picorgftp_sql/web/app.py tests/test_web_app_files.py` then `git commit -m "fix: validate web file paths against trusted roots"`.

### Task 4: Complete audit and verification

**Files:** Modify only a web file found by the audit to have a request-derived unguarded filesystem sink; add a matching focused test.

- [ ] **Step 1: Audit all sinks**

Run `rg -n "\b(open|FileResponse|os\.remove|os\.replace|os\.path\.(getsize|isfile|exists)|Image\.open|shutil\.rmtree)" picorgftp_sql/web -g '*.py'`. Trace each sink to a request field, upload filename, token, or client payload and classify it as protected, server-constant, or requiring a focused change.

- [ ] **Step 2: Run focused regression tests**

Run `pytest tests/test_path_security.py tests/test_upload_staging.py tests/test_web_app_files.py -v`; it must pass.

- [ ] **Step 3: Run full verification**

Run `pytest -q`, then `git diff --check; git status --short`. Report unrelated baseline failures exactly; do not attribute them to this change without evidence.

- [ ] **Step 4: Commit the final state**

Run `git add picorgftp_sql/path_security.py picorgftp_sql/web/app.py picorgftp_sql/web/upload_staging.py tests/test_path_security.py tests/test_upload_staging.py tests/test_web_app_files.py` then `git commit -m "fix: prevent web path traversal"`.
