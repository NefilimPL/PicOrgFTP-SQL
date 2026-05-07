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
        self.moveto_calls: list[float] = []
        self.content_height = 1000.0
        self.viewport_height = 200.0
        self.fraction = 0.0

    def bbox(self, _tag: str):
        return (0, 0, 100, int(self.content_height))

    def winfo_height(self) -> int:
        return int(self.viewport_height)

    def yview(self):
        return (
            self.fraction,
            min(1.0, self.fraction + (self.viewport_height / self.content_height)),
        )

    def yview_moveto(self, fraction: float) -> None:
        max_fraction = (self.content_height - self.viewport_height) / self.content_height
        self.fraction = max(0.0, min(max_fraction, float(fraction)))
        self.moveto_calls.append(self.fraction)

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
    _get_slots_scroll_metrics = (
        App._get_slots_scroll_metrics if App is not None else None
    )
    _get_slots_scroll_offset = App._get_slots_scroll_offset if App is not None else None
    _set_slots_scroll_offset = App._set_slots_scroll_offset if App is not None else None
    _mark_slots_scroll_active = (
        App._mark_slots_scroll_active if App is not None else None
    )
    _flush_slots_scroll = App._flush_slots_scroll if App is not None else None
    _scroll_slots_by_pixels = App._scroll_slots_by_pixels if App is not None else None
    _finish_slots_scroll = App._finish_slots_scroll if App is not None else None

    def __init__(self) -> None:
        self._slots_canvas = _CanvasStub()
        self._slots_scroll_job = None
        self._slots_scroll_end_job = None
        self._slots_scroll_target_px = 0.0
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

    def _prefetch_visible_slot_thumbnails(self) -> None:
        return None


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

    def test_slot_scroll_uses_smooth_pixel_target(self) -> None:
        harness = _ScrollHarness()

        App._scroll_slots(harness, 10)
        App._flush_slots_scroll(harness)

        self.assertTrue(harness._slots_scroll_active)
        self.assertEqual(harness._slots_canvas.scroll_calls, [])
        self.assertAlmostEqual(harness._slots_scroll_target_px, 300.0)
        self.assertAlmostEqual(harness._slots_canvas.moveto_calls[-1], 0.084)
        self.assertIsNotNone(harness._slots_scroll_job)


if __name__ == "__main__":
    unittest.main()
