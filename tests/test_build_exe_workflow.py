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
    assert "uses: actions/github-script@v7" in source
    assert "actions: read" in source
    assert "secrets.ACTIONS_RUNNER_READ_TOKEN || github.token" in source
    assert "github.rest.actions.listSelfHostedRunnersForRepo" in source
    assert "runner.status === \"online\"" in source
    assert "runner.busy === false" in source
    assert "['self-hosted', 'Windows', 'X64']" in source
    assert "JSON.stringify(selfHostedLabels)" in source
    assert "core.setOutput('runs_on'" in source


def test_build_job_uses_selected_runner_or_github_hosted_fallback() -> None:
    source = workflow_source()
    build_job_start = source.index("  build-windows:")
    build_job = source[build_job_start:]

    assert "needs: select-runner" in build_job
    assert "runs-on: ${{ fromJSON(needs.select-runner.outputs.runs_on) }}" in build_job
    assert "JSON.stringify('windows-latest')" in source


def test_artifact_uploads_are_guarded_by_probe_and_non_fatal() -> None:
    source = workflow_source()

    assert "id: artifact-probe" in source
    assert "name: PicOrgFTP-SQL-artifact-probe-${{ github.run_id }}" in source
    assert "retention-days: 1" in source
    assert "steps.artifact-probe.outcome == 'success'" in source
    assert source.count("continue-on-error: true") >= 4
    assert source.count("retention-days: 7") >= 3
    assert "Artifact upload was skipped" in source
