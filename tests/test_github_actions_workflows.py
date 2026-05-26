"""Checks for GitHub Actions workflow intent."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow_text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class GithubActionsWorkflowTests(unittest.TestCase):
    def test_code_quality_runs_on_push_pr_and_manual_dispatch(self) -> None:
        workflow = _workflow_text("code-quality.yml")

        self.assertIn("push:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertIn("workflow_dispatch:", workflow)

    def test_code_quality_push_and_pr_are_limited_to_main_master_dev(self) -> None:
        workflow = _workflow_text("code-quality.yml")

        for event_name in ("push", "pull_request"):
            match = re.search(
                rf"^  {event_name}:\s*\n(?P<body>(?:^    .*(?:\n|$))*)",
                workflow,
                flags=re.MULTILINE,
            )
            self.assertIsNotNone(match, event_name)
            body = match.group("body")
            self.assertIn("branches:", body)
            self.assertRegex(body, r"(?m)^\s+- main$")
            self.assertRegex(body, r"(?m)^\s+- master$")
            self.assertRegex(body, r"(?m)^\s+- dev$")

    def test_coverage_is_limited_to_project_sources(self) -> None:
        coveragerc = (ROOT / ".coveragerc").read_text(encoding="utf-8")

        self.assertIn("source =", coveragerc)
        self.assertIn("picorgftp_sql", coveragerc)
        self.assertNotIn("tests", coveragerc)

    def test_manual_dispatch_jobs_are_limited_to_main_master_dev(self) -> None:
        workflow = _workflow_text("code-quality.yml")
        branch_guard = (
            "if: github.event_name != 'workflow_dispatch' || "
            "contains(fromJSON('[\"main\", \"master\", \"dev\"]'), github.ref_name)"
        )

        self.assertEqual(workflow.count(branch_guard), 4)

    def test_code_quality_does_not_publish_or_upload_exe_artifacts(self) -> None:
        workflow = _workflow_text("code-quality.yml")

        forbidden_patterns = [
            r"actions/upload-artifact",
            r"\bgh\s+release\s+upload\b",
            r"Publish assets to release",
        ]
        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, workflow, flags=re.IGNORECASE))

    def test_build_exe_is_release_or_manual_only(self) -> None:
        workflow = _workflow_text("build-exe.yml")
        on_block_match = re.search(
            r"^on:\s*\n(?P<body>.*?)(?=^\S|\Z)",
            workflow,
            flags=re.MULTILINE | re.DOTALL,
        )

        self.assertIsNotNone(on_block_match)
        on_block = on_block_match.group("body")
        self.assertIn("workflow_dispatch:", on_block)
        self.assertIn("release:", on_block)
        self.assertNotIn("push:", on_block)


if __name__ == "__main__":
    unittest.main()
