"""Unit tests for lightweight GUI performance helpers."""

from __future__ import annotations

import unittest

try:
    from picorgftp_sql.app import App
    from picorgftp_sql.common import d, n
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local test env
    App = None
    APP_IMPORT_ERROR = exc
else:
    APP_IMPORT_ERROR = None


class _ComboboxStub:
    def __init__(self) -> None:
        self.assignments: list[tuple[str, tuple[str, ...]]] = []

    def __setitem__(self, key: str, value) -> None:
        self.assignments.append((key, tuple(value)))


class _CanvasStub:
    def __init__(self) -> None:
        self.scroll_calls: list[tuple[int, str]] = []

    def yview_scroll(self, steps: int, unit: str) -> None:
        self.scroll_calls.append((steps, unit))

    def update_idletasks(self) -> None:
        return None


class _ListHarness:
    _normalize_list_value = App._normalize_list_value if App is not None else None
    _invalidate_list_filter_cache = (
        App._invalidate_list_filter_cache if App is not None else None
    )
    _refresh_list_value_set = App._refresh_list_value_set if App is not None else None

    def __init__(self) -> None:
        self.lists = {
            n: ["ALFA"],
            d: ["NO_LED"],
        }
        self._list_filter_cache = {}


class _ScrollHarness:
    _mark_slots_scroll_active = (
        App._mark_slots_scroll_active if App is not None else None
    )
    _flush_slots_scroll = App._flush_slots_scroll if App is not None else None
    _finish_slots_scroll = App._finish_slots_scroll if App is not None else None

    def __init__(self) -> None:
        self._slots_canvas = _CanvasStub()
        self._slots_scroll_job = None
        self._slots_scroll_end_job = None
        self._slots_scroll_pending_steps = 0
        self._slots_scroll_active = False
        self.after_calls: list[tuple[int, object]] = []
        self.cancelled: list[str] = []
        self.refreshes = 0

    def after(self, delay_ms: int, callback):
        self.after_calls.append((delay_ms, callback))
        return f"job-{len(self.after_calls)}"

    def after_cancel(self, job_id: str) -> None:
        self.cancelled.append(job_id)

    def _schedule_slots_canvas_refresh(self) -> None:
        self.refreshes += 1


@unittest.skipIf(App is None, f"App import unavailable: {APP_IMPORT_ERROR}")
class AppPerformanceHelperTests(unittest.TestCase):
    def test_set_combobox_values_skips_identical_payload(self) -> None:
        combo = _ComboboxStub()

        App._set_combobox_values(None, combo, ["A", "B"])
        App._set_combobox_values(None, combo, ["A", "B"])
        App._set_combobox_values(None, combo, ["A", "C"])

        self.assertEqual(
            combo.assignments,
            [
                ("values", ("A", "B")),
                ("values", ("A", "C")),
            ],
        )

    def test_list_membership_uses_refreshed_normalized_set(self) -> None:
        harness = _ListHarness()
        harness._list_value_sets = App._build_list_value_sets(harness)

        self.assertTrue(App._list_has_value(harness, n, "alfa"))
        self.assertTrue(App._list_has_value(harness, d, "NO-LED"))

        harness.lists[n].append("BETA")
        App._refresh_list_value_set(harness, n)

        self.assertTrue(App._list_has_value(harness, n, "beta"))

    def test_slot_scroll_is_coalesced_and_capped(self) -> None:
        harness = _ScrollHarness()

        App._scroll_slots(harness, 50)
        App._flush_slots_scroll(harness)

        self.assertTrue(harness._slots_scroll_active)
        self.assertEqual(harness._slots_canvas.scroll_calls, [(10, "units")])
        self.assertEqual(harness._slots_scroll_pending_steps, 40)
        self.assertIsNotNone(harness._slots_scroll_job)


if __name__ == "__main__":
    unittest.main()
