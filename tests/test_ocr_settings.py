from picorgftp_sql.ocr_settings import normalize_ocr_settings


def test_normalize_ocr_settings_bounds_idle_and_cpu_limits():
    assert normalize_ocr_settings(
        {"idle_seconds": -1, "max_cpu_percent": 101}
    ) == {
        "enabled_slots": [],
        "background_enabled": False,
        "idle_seconds": 0,
        "max_cpu_percent": 100,
        "pause_cpu_percent": 100,
    }


def test_normalize_ocr_settings_removes_duplicate_and_empty_slots():
    assert normalize_ocr_settings({"enabled_slots": ["15", "", "15", 16]})[
        "enabled_slots"
    ] == ["15", "16"]
