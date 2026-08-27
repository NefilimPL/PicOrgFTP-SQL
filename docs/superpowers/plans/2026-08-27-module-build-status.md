# Module Build Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only Settings tab that identifies the code embedded in the running build and compares every registered module with a local Git checkout.

**Architecture:** A dependency-free service owns the module registry, manifest schema, read-only Git inspection, and comparison rules. A build-time CLI creates a manifest packaged by both EXE generators; the web application exposes it only through an admin endpoint and lazily renders a Settings tab.

**Tech Stack:** Python, FastAPI, PyInstaller, PowerShell, browser JavaScript, pytest, Node test runner.

**Spec:** `docs/superpowers/specs/2026-08-27-module-build-status-design.md`

## Global Constraints

- Compare only against a local Git checkout; no GitHub or network request.
- Git inspection is read-only, uses a 2-second timeout, and never raises from an unavailable Git executable.
- The admin endpoint returns no repository or executable filesystem path.
- Generate and package the same manifest for local, web, and web-OCR EXE builds.
- Older EXEs with no manifest produce `build_metadata_missing`.
- Do not stage or modify unrelated OCR changes already present in the working tree.

---

### Task 1: Module registry, manifest, and comparison service

**Files:**
- Create: `picorgftp_sql/services/module_build_status.py`
- Create: `tests/test_module_build_status.py`

**Interfaces:**
- `ModuleDefinition(id: str, label: str, paths: tuple[str, ...])`
- `MODULES: tuple[ModuleDefinition, ...]`
- `build_manifest(repo_root: Path, *, build_variant: str, now: datetime) -> dict[str, object]`
- `load_packaged_module_manifest() -> dict[str, object] | None`
- `module_status_snapshot(manifest: Mapping[str, object] | None, runtime_root: Path, env: Mapping[str, str]) -> dict[str, object]`

- [ ] **Step 1: Write the failing manifest test**

~~~python
def test_build_manifest_includes_registered_ocr_and_generator_modules(monkeypatch, tmp_path):
    monkeypatch.setattr(module_build_status, "_git", lambda *_args: "abc123|2026-08-27T10:00:00+00:00")

    manifest = module_build_status.build_manifest(
        tmp_path, build_variant="web-ocr", now=datetime(2026, 8, 27, tzinfo=UTC)
    )

    assert manifest["schema_version"] == 1
    assert manifest["build_variant"] == "web-ocr"
    assert {"slots", "ocr", "ocr_tester", "pimcore", "settings", "generator_local", "generator_web"} <= {
        item["id"] for item in manifest["modules"]
    }
    assert all(set(item) == {"id", "label", "commit", "committed_at"} for item in manifest["modules"])
~~~

- [ ] **Step 2: Run it and confirm it fails**

Run: `& '.venv\\Scripts\\python.exe' -m pytest tests/test_module_build_status.py -q -k includes_registered --basetemp='pytest-temp\\module-status-red-1'`

Expected: FAIL because `module_build_status` does not exist.

- [ ] **Step 3: Implement the registry and manifest builder**

~~~python
@dataclass(frozen=True)
class ModuleDefinition:
    id: str
    label: str
    paths: tuple[str, ...]

def build_manifest(repo_root: Path, *, build_variant: str, now: datetime) -> dict[str, object]:
    return {
        "schema_version": 1,
        "build_variant": build_variant,
        "generated_at": now.astimezone(UTC).isoformat(),
        "repository_commit": _git_value(repo_root, "rev-parse", "HEAD"),
        "modules": [_manifest_module(repo_root, module) for module in MODULES],
    }
~~~

Define logical modules for application/data, slots, FTP, SQL, Pimcore, OCR, OCR tester, settings, web UI, local generator, and web generator. For each module run `git log -1 --format=%H|%cI -- <registered paths>`; parse a missing history as empty fields, not an exception.

- [ ] **Step 4: Write failing comparison tests**

~~~python
def test_snapshot_marks_changed_module_for_rebuild(monkeypatch, tmp_path):
    manifest = {"schema_version": 1, "modules": [
        {"id": "ocr", "label": "OCR", "commit": "old", "committed_at": "2026-08-01T00:00:00+00:00"}
    ]}
    monkeypatch.setattr(module_build_status, "_find_repo_root", lambda *_args: tmp_path)
    monkeypatch.setattr(module_build_status, "_module_git_state", lambda *_args: ("new", "2026-08-27T00:00:00+00:00", False))

    row = module_build_status.module_status_snapshot(manifest, tmp_path, {})["modules"][0]

    assert row["status"] == "rebuild_required"

def test_snapshot_keeps_embedded_data_when_repository_is_unavailable(tmp_path):
    manifest = {"schema_version": 1, "modules": []}

    snapshot = module_build_status.module_status_snapshot(manifest, tmp_path, {})

    assert snapshot["repository_status"] == "unavailable"
~~~

- [ ] **Step 5: Run comparison tests and confirm they fail**

Run: `& '.venv\\Scripts\\python.exe' -m pytest tests/test_module_build_status.py -q -k 'rebuild or unavailable' --basetemp='pytest-temp\\module-status-red-2'`

Expected: FAIL because comparison is not implemented.

- [ ] **Step 6: Implement safe manifest loading and local comparison**

~~~python
def module_status_snapshot(manifest, runtime_root, env):
    if not _valid_manifest(manifest):
        return _missing_manifest_snapshot()
    repo_root = _find_repo_root(runtime_root, env.get("PICORGFTP_SQL_REPOSITORY_ROOT", ""))
    if repo_root is None:
        return _snapshot_without_repository(manifest)
    return _compare_manifest_with_repository(manifest, repo_root)
~~~

Use `subprocess.run` with a list of fixed arguments, `capture_output=True`, `text=True`, `check=False`, and `timeout=2`. A dirty module has `uncommitted_changes` priority over commit comparison. Return only the public fields `id`, `label`, `build_commit`, `build_committed_at`, `local_commit`, `local_committed_at`, and `status`.

- [ ] **Step 7: Run all service tests and commit**

Run: `& '.venv\\Scripts\\python.exe' -m pytest tests/test_module_build_status.py -q --basetemp='pytest-temp\\module-status-green-1'`

Expected: PASS.

~~~bash
git add picorgftp_sql/services/module_build_status.py tests/test_module_build_status.py
git commit -m "feat: add module build status service"
~~~

### Task 2: Build manifest packaging and protected API

**Files:**
- Create: `tools/generate_module_build_manifest.py`
- Modify: `Generator exe/build_common.ps1`
- Modify: `Generator exe/build_local_exe.ps1`
- Modify: `Generator exe/build_web_exe.ps1`
- Modify: `picorgftp_sql/web/app.py`
- Modify: `tests/test_build_exe_workflow.py`
- Create: `tests/test_module_build_status_api.py`

**Interfaces:**
- CLI: `python tools/generate_module_build_manifest.py --repo-root . --build-variant web --output build/module_build_manifest.json`
- PowerShell: `New-ModuleBuildManifestArguments -Python $Python -RepoRoot $RepoRoot -WorkPath $WorkPath -BuildVariant web`
- API: `GET /api/settings/module-status`

- [ ] **Step 1: Write failing packaging and API tests**

~~~python
def test_manifest_cli_writes_requested_build_variant(tmp_path):
    output = tmp_path / "module_build_manifest.json"
    subprocess.run([
        sys.executable, "tools/generate_module_build_manifest.py",
        "--repo-root", str(ROOT), "--build-variant", "web", "--output", str(output),
    ], check=True)
    assert json.loads(output.read_text(encoding="utf-8"))["build_variant"] == "web"

def test_all_exe_builds_package_the_module_manifest():
    for path in (LOCAL_BUILD, WEB_BUILD):
        source = path.read_text(encoding="utf-8")
        assert "New-ModuleBuildManifestArguments" in source
        assert "module_build_manifest.json" in source

def test_module_status_route_is_admin_only_and_returns_snapshot():
    client = TestClient(web_app.app)
    expected = {"repository_status": "available", "build": {}, "modules": []}
    with patch.object(web_app, "_require_admin", return_value={"role": "admin"}), patch.object(
        web_app, "module_status_snapshot", return_value=expected
    ):
        assert client.get("/api/settings/module-status").json() == expected
~~~

- [ ] **Step 2: Run the new tests and confirm they fail**

Run: `& '.venv\\Scripts\\python.exe' -m pytest tests/test_build_exe_workflow.py tests/test_module_build_status_api.py -q -k 'manifest or module_status_route' --basetemp='pytest-temp\\module-status-red-3'`

Expected: FAIL because the CLI, packaging helper, and route do not exist.

- [ ] **Step 3: Implement CLI, packaging helper, and route**

~~~powershell
function New-ModuleBuildManifestArguments {
    param([string]$Python, [string]$RepoRoot, [string]$WorkPath, [string]$BuildVariant)
    $manifestPath = Join-Path $WorkPath "module_build_manifest.json"
    Invoke-Native $Python "tools\\generate_module_build_manifest.py" "--repo-root" $RepoRoot "--build-variant" $BuildVariant "--output" $manifestPath
    return @("--add-data", "$manifestPath;picorgftp_sql")
}
~~~

The CLI writes UTF-8 JSON from Task 1. In each generator, create the manifest after `$WorkPath` exists and pass the returned arguments to PyInstaller. The local build passes `local`; web uses `web` or `web-ocr` based on `$IncludeVisionModels`. Add `module-build-status.js` to `Get-WebStaticDataArguments` so the tested browser module is also bundled.

~~~python
@app.get("/api/settings/module-status")
def module_status_api(request: Request) -> dict[str, object]:
    _require_admin(request)
    return module_status_snapshot(
        load_packaged_module_manifest(), Path(sys.executable).resolve().parent, os.environ
    )
~~~

Keep the endpoint out of editable `settings_snapshot()`; do not include raw paths in its response.

- [ ] **Step 4: Run focused tests and commit**

Run: `& '.venv\\Scripts\\python.exe' -m pytest tests/test_build_exe_workflow.py tests/test_module_build_status_api.py -q -k 'manifest or module_status_route' --basetemp='pytest-temp\\module-status-green-2'`

Expected: PASS.

~~~bash
git add tools/generate_module_build_manifest.py 'Generator exe/build_common.ps1' 'Generator exe/build_local_exe.ps1' 'Generator exe/build_web_exe.ps1' picorgftp_sql/web/app.py tests/test_build_exe_workflow.py tests/test_module_build_status_api.py
git commit -m "feat: package and expose module build status"
~~~

### Task 3: Settings tab, refresh behavior, and final verification

**Files:**
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`
- Create: `picorgftp_sql/web/static/module-build-status.js`
- Create: `tests/js/module-build-status.test.js`
- Modify: `tests/test_web_ui_integrity.py`

**Interfaces:**
- Tab: `data-settings-tab="module-status"`
- Browser module: `window.PicOrg.ModuleBuildStatus.normalizeSnapshot(value)` and `window.PicOrg.ModuleBuildStatus.statusLabel(status)`
- Application functions: `loadModuleBuildStatus() -> Promise<object>` and `renderSettingsModuleStatus() -> void`
- Status labels: `matching`, `rebuild_required`, `uncommitted_changes`, `repository_unavailable`, and `build_metadata_missing`

- [ ] **Step 1: Write failing browser-module tests**

~~~javascript
test("normalizes a rebuild-required module and translates its status", () => {
  const status = loadModuleBuildStatus();
  const snapshot = status.normalizeSnapshot({
    build: { build_variant: "web-ocr", generated_at: "2026-08-27T10:00:00+00:00" },
    repository_status: "available",
    modules: [{ id: "ocr", label: "OCR", build_commit: "old", local_commit: "new", status: "rebuild_required" }],
  });

  assert.equal(snapshot.modules[0].status, "rebuild_required");
  assert.equal(status.statusLabel(snapshot.modules[0].status), "Wymaga ponownego builda");
});
~~~

Add a second test where `repository_status` is unavailable and assert that embedded build variant and commit remain visible. Keep the refresh button assertion in `tests/test_web_ui_integrity.py`, where the existing monolithic `app.js` is already covered statically.

- [ ] **Step 2: Run browser tests and confirm they fail**

Run: `node --test tests/js/module-build-status.test.js`

Expected: FAIL because `module-build-status.js` does not exist.

- [ ] **Step 3: Implement the lazy admin tab**

~~~javascript
function normalizeSnapshot(value) {
  const source = value && typeof value === "object" ? value : {};
  return { build: source.build || null, repository_status: String(source.repository_status || "unavailable"), modules: Array.isArray(source.modules) ? source.modules : [] };
}

function statusLabel(status) {
  return { matching: "Zgodny", rebuild_required: "Wymaga ponownego builda", uncommitted_changes: "Niezacommitowane zmiany", repository_unavailable: "Repozytorium niedostepne", build_metadata_missing: "Brak danych buildu" }[status] || "Nieznany status";
}

window.PicOrg.ModuleBuildStatus = { normalizeSnapshot, statusLabel };

async function loadModuleBuildStatus() {
  state.moduleBuildStatus = await requestJson("/api/settings/module-status");
  return state.moduleBuildStatus;
}

function renderSettingsModuleStatus() {
  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.textContent = "OdĹ›wieĹĽ porĂłwnanie";
  refresh.addEventListener("click", () => loadModuleBuildStatus().then(renderSettings));
  // Render module label, build commit/date, local commit/date, and translated text status.
}
~~~

Load the new module before `app.js` in `index.html`. Add the tab next to the existing Settings tabs. In `renderSettings()`, call the renderer only for `module-status`; load data lazily and show an in-tab loading/error message. Add accessible CSS status badges with both text and a visual indicator, so colors alone do not carry meaning.

- [ ] **Step 4: Add and run static UI integrity test**

~~~python
def test_settings_ui_contains_module_status_tab_and_endpoint():
    html = (ROOT / "picorgftp_sql/web/static/index.html").read_text(encoding="utf-8")
    source = (ROOT / "picorgftp_sql/web/static/app.js").read_text(encoding="utf-8")

    assert 'data-settings-tab="module-status"' in html
    assert '"/api/settings/module-status"' in source
    assert "module-build-status.js" in html
    assert "Odśwież porównanie" in source
~~~

Run: `& '.venv\\Scripts\\python.exe' -m pytest tests/test_web_ui_integrity.py -q -k module_status --basetemp='pytest-temp\\module-status-green-3'`

Expected: PASS.

- [ ] **Step 5: Run browser tests, focused Python tests, diff check, and commit**

Run: `node --test tests/js/module-build-status.test.js`

Run: `& '.venv\\Scripts\\python.exe' -m pytest tests/test_module_build_status.py tests/test_module_build_status_api.py tests/test_build_exe_workflow.py tests/test_web_ui_integrity.py -q --basetemp='pytest-temp\\module-status-final'`

Run: `git diff --check`

Expected: all tests PASS; diff check exits 0 without whitespace errors.

~~~bash
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js picorgftp_sql/web/static/app.css picorgftp_sql/web/static/module-build-status.js tests/js/module-build-status.test.js tests/test_web_ui_integrity.py
git commit -m "feat: show module build status in settings"
~~~
