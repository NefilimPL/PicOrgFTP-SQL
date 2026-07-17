"""Lightweight load and performance smoke tests for CI."""

from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("PICORGFTP_SQL_HEADLESS", "1")
os.environ.setdefault("PICORG_WEB_AUTH", "0")

try:
    from fastapi.testclient import TestClient
except Exception as exc:  # pragma: no cover - depends on CI test dependencies
    TestClient = None
    TEST_CLIENT_IMPORT_ERROR = exc
else:
    TEST_CLIENT_IMPORT_ERROR = None

from picorgftp_sql.web import app as web_app
from picorgftp_sql.web_workflow import (
    WebProductForm,
    normalized_product_payload,
    validate_product_form,
)
from picorgftp_sql.workflow_utils import (
    build_product_directory,
    build_slot_filename,
    parse_slot_filename,
)


def _budget(seconds: float) -> float:
    multiplier = float(os.environ.get("PICORG_PERF_BUDGET_MULTIPLIER", "1.0"))
    return seconds * multiplier


class CiPerformanceSmokeTests(unittest.TestCase):
    def test_product_helpers_handle_repeated_work_within_budget(self) -> None:
        product = WebProductForm(
            name="MAGGIORE",
            type_name="KOMODA",
            model="MA03",
            color1="BIALY",
            color2="DAB",
            color3="",
            extra="NO-LED",
            ean="5901234567890",
        )

        started = time.perf_counter()
        for index in range(2500):
            self.assertEqual(validate_product_form(product), [])
            payload = normalized_product_payload(product)
            output_dir = build_product_directory(
                "C:/tmp/out",
                payload["name"],
                payload["type_name"],
                payload["model"],
                payload["colors"],
                payload["extra"],
            )
            filename = build_slot_filename(
                payload["ean"],
                f"{(index % 12) + 1:02d}",
                "DETAIL",
                payload["name"],
                payload["type_name"],
                payload["model"],
                payload["colors"],
                payload["extra"],
                ".jpg",
            )
            parsed = parse_slot_filename(filename)
            self.assertIsNotNone(parsed)
            self.assertIn("MAGGIORE", output_dir)
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, _budget(6.0))

    @unittest.skipIf(
        TestClient is None,
        f"FastAPI TestClient unavailable: {TEST_CLIENT_IMPORT_ERROR}",
    )
    def test_health_endpoint_handles_small_ci_load_within_budget(self) -> None:
        client = TestClient(web_app.app)

        started = time.perf_counter()
        with patch.object(
            web_app,
            "notification_worker_health",
            return_value={
                "status": "online",
                "observed_at": "2026-07-17T08:00:00.000Z",
            },
        ):
            for _ in range(120):
                response = client.get("/api/health")
                self.assertEqual(response.status_code, 200)
                self.assertIs(response.json()["ok"], True)
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, _budget(10.0))


if __name__ == "__main__":
    unittest.main()
