from picorgftp_sql.ocr_settings import normalize_ocr_settings
from picorgftp_sql.services.ocr_profiles import available_ocr_profiles


def test_normalize_ocr_settings_bounds_idle_and_cpu_limits():
    assert normalize_ocr_settings(
        {"idle_seconds": -1, "max_cpu_percent": 101}
    ) == {
        "enabled_slots": [],
        "background_enabled": False,
        "idle_seconds": 0,
        "max_cpu_percent": 100,
        "pause_cpu_percent": 100,
        "model_profiles": ["fast"],
    }


def test_normalize_ocr_settings_removes_duplicate_and_empty_slots():
    assert normalize_ocr_settings({"enabled_slots": ["15", "", "15", 16]})[
        "enabled_slots"
    ] == ["15", "16"]


def test_normalize_ocr_settings_keeps_known_profiles_in_requested_order():
    assert normalize_ocr_settings(
        {"model_profiles": ["accurate", "fast", "unknown", "accurate"]}
    )["model_profiles"] == ["accurate", "fast"]


def test_local_ocr_profiles_describe_mobile_and_server_engines():
    profiles = {profile.id: profile for profile in available_ocr_profiles()}

    assert profiles["fast"].recognizer_model == "PP-OCRv5_mobile_rec"
    assert profiles["accurate"].recognizer_model == "PP-OCRv5_server_rec"
