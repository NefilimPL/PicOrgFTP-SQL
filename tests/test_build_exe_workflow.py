"""Static checks for the Windows EXE build workflow."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build-exe.yml"


def workflow_source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_build_workflow_selects_self_hosted_runner_before_build() -> None:
    source = workflow_source()

    assert "select-runner:" in source
    assert "uses: actions/github-script@v9" in source
    assert "actions: read" in source
    assert "secrets.ACTIONS_RUNNER_READ_TOKEN || github.token" in source
    assert "github.rest.actions.listSelfHostedRunnersForRepo" in source
    assert "runner.status === \"online\"" in source
    assert "runner.busy === false" in source
    assert "['self-hosted', 'Windows', 'X64']" in source
    assert "JSON.stringify(selfHostedLabels)" in source
    assert "core.setOutput('runs_on'" in source
    assert "core.setOutput('available_count'" in source


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
