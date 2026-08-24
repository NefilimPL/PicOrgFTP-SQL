from pathlib import Path

import pytest
from PIL import Image

from picorgftp_sql.services.image_dimensions import OcrTextBox
from picorgftp_sql.services.ocr_pipeline import run_ocr_pipeline
from picorgftp_sql.services.ocr_resource_policy import ResourceDecision


def test_both_profiles_send_only_fast_regions_to_accurate_model_and_translate_boxes(tmp_path):
    image_path = tmp_path / "source.png"
    Image.new("RGB", (80, 60), "white").save(image_path)
    calls: list[tuple[str, str]] = []
    events: list[dict[str, object]] = []

    class _Recognizer:
        def __init__(self, profile_id: str) -> None:
            self.profile_id = profile_id

        def detect(self, path: str) -> list[OcrTextBox]:
            calls.append((self.profile_id, Path(path).name))
            if self.profile_id == "fast":
                return [OcrTextBox("20 kg", 0.8, (10, 12, 30, 22))]
            return [OcrTextBox("20kg", 0.95, (1, 2, 11, 7))]

    boxes = run_ocr_pipeline(
        str(image_path),
        profile_ids=["fast", "accurate"],
        recognizer_factory=_Recognizer,
        on_event=lambda kind, **payload: events.append({"kind": kind, **payload}),
    )

    assert calls[0] == ("fast", "source.png")
    assert calls[1][0] == "accurate"
    assert calls[1][1] != "source.png"
    assert boxes[-1] == OcrTextBox("20kg", 0.95, (11, 14, 21, 19))
    assert {event["kind"] for event in events} >= {"candidate_regions", "crop_started"}
    assert next(event for event in events if event["kind"] == "crop_started")["bbox"] == [
        10,
        12,
        30,
        22,
    ]


@pytest.mark.parametrize(
    ("profiles", "expected_calls"),
    [(["fast"], ["fast"]), (["accurate"], ["accurate"])],
)
def test_single_profile_runs_one_full_image_stage(tmp_path, profiles, expected_calls):
    image_path = tmp_path / "source.png"
    Image.new("RGB", (80, 60), "white").save(image_path)
    calls: list[str] = []

    class _Recognizer:
        def __init__(self, profile_id: str) -> None:
            self.profile_id = profile_id

        def detect(self, _path: str) -> list[OcrTextBox]:
            calls.append(self.profile_id)
            return []

    assert run_ocr_pipeline(
        str(image_path), profile_ids=profiles, recognizer_factory=_Recognizer
    ) == []
    assert calls == expected_calls


def test_explicit_empty_profile_selection_is_rejected():
    with pytest.raises(ValueError, match="profile"):
        run_ocr_pipeline("source.png", profile_ids=[])


def test_pipeline_throttles_between_fast_stage_and_accurate_crop(tmp_path):
    image_path = tmp_path / "source.png"
    Image.new("RGB", (80, 60), "white").save(image_path)
    checks = iter(
        [
            ResourceDecision("run"),
            ResourceDecision("throttle", "memory_usage", 0.25),
            ResourceDecision("run"),
        ]
    )
    events: list[str] = []
    waits: list[float] = []

    class _Recognizer:
        def __init__(self, profile_id: str) -> None:
            self.profile_id = profile_id

        def detect(self, _path: str) -> list[OcrTextBox]:
            return [OcrTextBox("12", 0.9, (10, 10, 20, 20))] if self.profile_id == "fast" else []

    run_ocr_pipeline(
        str(image_path),
        profile_ids=["fast", "accurate"],
        recognizer_factory=_Recognizer,
        before_stage=lambda _stage: next(checks),
        on_event=lambda kind, **_payload: events.append(kind),
        sleeper=waits.append,
    )

    assert waits == [0.25]
    assert "throttled" in events
