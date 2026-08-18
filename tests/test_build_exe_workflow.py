"""Static checks for the Windows EXE build workflow."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build-exe.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
WEB_REQUIREMENTS = ROOT / "requirements-web.txt"
BUILD_REQUIREMENTS = ROOT / "requirements-build.txt"
EMAIL_DELIVERY = ROOT / "picorgftp_sql" / "email_delivery.py"
BUILD_COMMON = ROOT / "Generator exe" / "build_common.ps1"
WEB_BUILD = ROOT / "Generator exe" / "build_web_exe.ps1"
WEB_BUILD_BATCH = ROOT / "Generator exe" / "BUILD_WEB_EXE.bat"
LOCAL_BUILD = ROOT / "Generator exe" / "build_local_exe.ps1"
LOCAL_BUILD_BATCH = ROOT / "Generator exe" / "BUILD_LOCAL_EXE.bat"
LOCAL_OCR_BUILD_BATCH = ROOT / "Generator exe" / "BUILD_LOCAL_EXE_OCR.bat"


def workflow_source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def ci_workflow_source() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def test_build_workflow_selects_self_hosted_runner_before_build() -> None:
    source = workflow_source()

    assert "select-runner:" in source
    assert "uses: actions/github-script@v9" in source
    assert "actions: read" in source
    assert "secrets.ACTIONS_RUNNER_READ_TOKEN || github.token" in source
    assert "github.rest.actions.listSelfHostedRunnersForRepo" in source
    assert "runner.status === \"online\"" in source
    assert "runner.busy === false" not in source
    assert "No online self-hosted Windows X64 runner was found" in source
    assert "['self-hosted', 'Windows', 'X64']" in source
    assert "JSON.stringify(selfHostedLabels)" in source
    assert "core.setOutput('runs_on'" in source
    assert "core.setOutput('available_count'" in source


def test_pull_request_ci_keeps_github_hosted_windows_runners() -> None:
    source = ci_workflow_source()

    assert "pull_request:" in source
    assert source.count("runs-on: windows-latest") >= 2
    assert "self-hosted" not in source


def test_build_job_uses_selected_runner_or_github_hosted_fallback() -> None:
    source = workflow_source()
    build_job_start = source.index("  build-windows:")
    build_job = source[build_job_start:]

    assert "needs: select-runner" in build_job
    assert "runs-on: ${{ fromJSON(needs.select-runner.outputs.runs_on) }}" in build_job
    assert "strategy:" in build_job
    assert "fail-fast: false" in build_job
    assert "target: local" in build_job
    assert "target: web" in build_job
    assert "JSON.stringify('windows-latest')" in source


def test_self_hosted_build_uses_existing_python_instead_of_setup_python() -> None:
    source = workflow_source()

    assert "uses: actions/setup-python@v6" in source
    assert "if: needs.select-runner.outputs.using_self_hosted != 'true'" in source
    assert 'python-version: "3.14"' in source
    assert "PICORGFTP_SQL_PYTHON" in source
    assert '$versionsToTry = @("3.14", "3.13", "3.12", "3.11")' in source
    assert "HKLM:\\SOFTWARE\\Python\\PythonCore" in source
    assert "HKCU:\\SOFTWARE\\Python\\PythonCore" in source
    assert '"3.14" = "Python314"' in source
    assert '$dirName\\python.exe' in source
    assert "Resolve Python diagnostics" in source
    assert 'if ($versionsToTry.Contains($version))' in source
    assert '$LASTEXITCODE -eq 0 -and $versionsToTry.Contains($version)' not in source
    assert "Python.Python.3.14" in source
    assert "-m PyInstaller" in source


def test_build_dependencies_install_into_isolated_virtualenv() -> None:
    source = workflow_source()

    assert "PICORGFTP_SQL_BASE_PYTHON" in source
    assert "Create isolated build virtualenv" in source
    assert "RUNNER_TEMP" in source
    assert "picorgftp-sql-build-${{ matrix.target }}" in source
    assert "-m venv" in source
    assert "PICORGFTP_SQL_PYTHON=$venvPython" in source
    assert 'pip install "pyinstaller>=6.6,<7"' not in source


def test_web_build_installs_msal_before_static_pyinstaller_analysis() -> None:
    source = workflow_source()
    web_requirements = WEB_REQUIREMENTS.read_text(encoding="utf-8")
    build_requirements = BUILD_REQUIREMENTS.read_text(encoding="utf-8")
    delivery_source = EMAIL_DELIVERY.read_text(encoding="utf-8")

    assert "msal>=1.37,<2" in web_requirements.splitlines()
    assert "msal>=1.37,<2" in build_requirements.splitlines()
    assert "-m pip install -r requirements-build.txt" in source
    assert "-m pip install -r requirements-web.txt" in source
    assert source.index("-m pip install -r requirements-web.txt") < source.index(
        "Build web manager EXE with PyInstaller"
    )
    assert "--collect-submodules picorgftp_sql" in source
    assert "import msal" in delivery_source


def test_web_build_explicitly_packages_all_composition_static_assets() -> None:
    source = BUILD_COMMON.read_text(encoding="utf-8")

    for asset in (
        "latest-request.js",
        "autocomplete.js",
        "runtime-status.js",
        "process-jobs.js",
        "app.js",
    ):
        assert asset in source


def test_web_build_supports_opt_in_vision_engine_and_embedded_models() -> None:
    common_source = BUILD_COMMON.read_text(encoding="utf-8")
    build_source = WEB_BUILD.read_text(encoding="utf-8")
    batch_source = WEB_BUILD_BATCH.read_text(encoding="utf-8")

    assert "IncludeVisionDependencies" in common_source
    assert '"requirements-vision.txt"' in common_source
    assert "[switch]$IncludeVision" in build_source
    assert "[switch]$IncludeVisionModels" in build_source
    assert "-IncludeVisionDependencies:$IncludeVision" in build_source
    assert "IncludeVisionModels wymaga parametru -IncludeVision" in build_source
    assert "--collect-all" in build_source
    assert "paddleocr" in build_source
    assert "PADDLE_PDX_CACHE_HOME" in build_source
    assert "ocr_models" in build_source
    assert "%*" in batch_source


def test_local_build_supports_opt_in_vision_engine_and_embedded_models() -> None:
    build_source = LOCAL_BUILD.read_text(encoding="utf-8")
    batch_source = LOCAL_BUILD_BATCH.read_text(encoding="utf-8")

    assert "[switch]$IncludeVision" in build_source
    assert "[switch]$IncludeVisionModels" in build_source
    assert "-IncludeVisionDependencies:$IncludeVision" in build_source
    assert "IncludeVisionModels wymaga parametru -IncludeVision" in build_source
    assert "--collect-all" in build_source
    assert "paddleocr" in build_source
    assert "PADDLE_PDX_CACHE_HOME" in build_source
    assert "ocr_models" in build_source
    assert "%*" in batch_source


def test_local_ocr_build_batch_offers_downloaded_and_embedded_model_variants() -> None:
    source = LOCAL_OCR_BUILD_BATCH.read_text(encoding="utf-8")

    assert "choice /c DM" in source
    assert "-IncludeVision" in source
    assert "-IncludeVision -IncludeVisionModels" in source
    assert "build_local_exe.ps1" in source


def test_artifact_uploads_are_guarded_by_probe_and_non_fatal_per_target() -> None:
    source = workflow_source()

    assert "id: artifact-probe" in source
    assert "name: PicOrgFTP-SQL-artifact-probe-${{ matrix.target }}-${{ github.run_id }}" in source
    assert "retention-days: 1" in source
    assert "steps.artifact-probe.outcome == 'success'" in source
    assert source.count("continue-on-error: true") >= 4
    assert source.count("retention-days: 7") >= 3
    assert "Artifact upload was skipped" in source


def test_node_actions_use_node_24_compatible_major_versions() -> None:
    source = workflow_source()

    assert "uses: actions/checkout@v7" in source
    assert "uses: actions/setup-python@v6" in source
    assert "uses: actions/upload-artifact@v7" in source
    assert "uses: actions/github-script@v9" in source


def test_release_assets_upload_without_github_cli() -> None:
    source = workflow_source()

    assert "gh release upload" not in source
    assert "github.rest.repos.uploadReleaseAsset" in source
    assert "github.rest.repos.deleteReleaseAsset" in source
    assert "github.rest.repos.listReleaseAssets" in source
