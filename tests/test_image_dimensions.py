from __future__ import annotations

import picorgftp_sql.services.image_dimensions as image_dimensions

from picorgftp_sql.services.image_dimensions import (
    DimensionLine,
    ImageDimensionUnavailable,
    ImageDimensionRequest,
    OcrTextBox,
    analyze_image_dimensions,
    associate_dimension_hints,
    bundled_ocr_model_cache_path,
    image_ocr_runtime_info,
    ocr_model_cache_path,
    resolve_image_dimensions,
)


class FakeRecognizer:
    def __init__(self, boxes: list[OcrTextBox]):
        self.boxes = boxes
        self.calls = 0

    def detect(self, _path: str) -> list[OcrTextBox]:
        self.calls += 1
        return self.boxes


def test_resolves_decimal_comma_value_when_ocr_confidence_meets_threshold():
    recognizer = FakeRecognizer(
        [OcrTextBox("130,5 cm", 0.92, (0, 0, 80, 20), "width")]
    )

    values, warnings = resolve_image_dimensions(
        [ImageDimensionRequest("15", "width", 0.8)],
        {"15": "fixture.png"},
        recognizer=recognizer,
    )

    assert values == {"IMAGE_DIMENSION:15:WIDTH": "130.5"}
    assert warnings == []


def test_rejects_text_below_configured_confidence_threshold():
    recognizer = FakeRecognizer(
        [OcrTextBox("130,5", 0.74, (0, 0, 80, 20), "width")]
    )

    values, warnings = resolve_image_dimensions(
        [ImageDimensionRequest("15", "width", 0.8)],
        {"15": "fixture.png"},
        recognizer=recognizer,
    )

    assert values == {"IMAGE_DIMENSION:15:WIDTH": ""}
    assert warnings == [
        {
            "code": "image_dimension_low_confidence",
            "slot": "15",
            "message": "Odczyt 74% jest ponizej wymaganego progu 80%.",
        }
    ]


def test_reports_missing_slot_without_calling_ocr():
    recognizer = FakeRecognizer([])

    values, warnings = resolve_image_dimensions(
        [ImageDimensionRequest("15", "width", 0.8)],
        {},
        recognizer=recognizer,
    )

    assert values == {"IMAGE_DIMENSION:15:WIDTH": ""}
    assert warnings[0]["code"] == "image_dimension_missing_slot"
    assert recognizer.calls == 0


def test_uses_dimension_hint_to_select_height_value():
    recognizer = FakeRecognizer(
        [
            OcrTextBox("130,5", 0.92, (0, 0, 80, 20), "width"),
            OcrTextBox("85,8", 0.91, (90, 0, 160, 20), "height"),
        ]
    )

    values, warnings = resolve_image_dimensions(
        [ImageDimensionRequest("15", "height", 0.8)],
        {"15": "fixture.png"},
        recognizer=recognizer,
    )

    assert values == {"IMAGE_DIMENSION:15:HEIGHT": "85.8"}
    assert warnings == []


def test_uses_one_ocr_call_for_multiple_dimensions_from_one_slot():
    recognizer = FakeRecognizer(
        [
            OcrTextBox("130,5", 0.92, (0, 0, 80, 20), "width"),
            OcrTextBox("85,8", 0.91, (90, 0, 160, 20), "height"),
        ]
    )

    values, warnings = resolve_image_dimensions(
        [
            ImageDimensionRequest("15", "width", 0.8),
            ImageDimensionRequest("15", "height", 0.8),
        ],
        {"15": "fixture.png"},
        recognizer=recognizer,
    )

    assert values == {
        "IMAGE_DIMENSION:15:WIDTH": "130.5",
        "IMAGE_DIMENSION:15:HEIGHT": "85.8",
    }
    assert warnings == []
    assert recognizer.calls == 1


def test_associates_numeric_text_with_nearest_dimension_line_orientation():
    boxes = [
        OcrTextBox("130,5", 0.92, (40, 18, 100, 38)),
        OcrTextBox("85,8", 0.91, (180, 70, 220, 92)),
    ]
    lines = [
        DimensionLine(0, 45, 150, 45),
        DimensionLine(230, 0, 230, 160),
    ]

    associated = associate_dimension_hints(boxes, lines)

    assert associated[0].hint == "width"
    assert associated[1].hint == "height"


def test_diagnostics_classifies_boxes_and_applies_threshold():
    recognizer = FakeRecognizer(
        [
            OcrTextBox("130,5 cm", 0.91, (4, 8, 80, 28), "width"),
            OcrTextBox("40", 0.72, (90, 8, 120, 28), "depth"),
            OcrTextBox("tekst", 0.96, (130, 8, 180, 28)),
        ]
    )

    result = analyze_image_dimensions(
        "fixture.png", minimum_text_confidence=0.8, recognizer=recognizer
    )

    assert result.available is True
    assert result.dimensions == {"width": "130.5", "depth": "", "height": ""}
    assert result.candidates[0].accepted is True
    assert result.candidates[0].bbox == (4, 8, 80, 28)
    assert result.candidates[1].accepted is False
    assert result.candidates[1].dimension == "depth"
    assert result.candidates[2].value == ""


def test_diagnostics_returns_a_message_instead_of_raising_when_ocr_is_broken():
    class BrokenRecognizer:
        def detect(self, _path: str) -> list[OcrTextBox]:
            raise RuntimeError("The pipeline (OCR) does not exist")

    result = analyze_image_dimensions("fixture.png", recognizer=BrokenRecognizer())

    assert result.available is False
    assert result.candidates == []
    assert "pipeline" in result.message


def test_diagnostics_keeps_the_ocr_unavailable_message():
    class UnavailableRecognizer:
        def detect(self, _path: str) -> list[OcrTextBox]:
            raise ImageDimensionUnavailable("Brak konfiguracji pipeline OCR.")

    result = analyze_image_dimensions("fixture.png", recognizer=UnavailableRecognizer())

    assert result.available is False
    assert result.message == "Brak konfiguracji pipeline OCR."


def test_template_resolution_returns_a_warning_when_ocr_initialization_crashes():
    class BrokenRecognizer:
        def detect(self, _path: str) -> list[OcrTextBox]:
            raise RuntimeError("The pipeline (OCR) does not exist")

    values, warnings = resolve_image_dimensions(
        [ImageDimensionRequest("15", "width", 0.8)],
        {"15": "fixture.png"},
        recognizer=BrokenRecognizer(),
    )

    assert values == {"IMAGE_DIMENSION:15:WIDTH": ""}
    assert warnings == [
        {
            "code": "ocr_unavailable",
            "slot": "15",
            "message": "Lokalny OCR jest niedostepny.",
        }
    ]


def test_ocr_runtime_info_has_stable_engine_and_github_metadata():
    info = image_ocr_runtime_info()

    assert info["engine"]["name"] == "PaddleOCR"
    assert info["github_url"].startswith("https://github.com/")
    assert isinstance(info["models"], list)
    assert info["models"][0]["version"] == "lang=en"


def test_ocr_runtime_info_does_not_treat_cache_control_directories_as_models(
    tmp_path, monkeypatch
):
    for name in ("func_ret", "locks", "temp"):
        (tmp_path / name).mkdir()
    package_root = tmp_path / "paddlex"
    pipeline_config = package_root / "configs" / "pipelines" / "OCR.yaml"
    pipeline_config.parent.mkdir(parents=True)
    pipeline_config.touch()
    package_origin = package_root / "__init__.py"
    package_origin.touch()
    monkeypatch.setattr(image_dimensions, "ocr_model_cache_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        image_dimensions, "_optional_package_version", lambda _package: "1.0"
    )
    monkeypatch.setattr(
        image_dimensions.util,
        "find_spec",
        lambda package: type("Spec", (), {"origin": str(package_origin)})()
        if package == "paddlex"
        else object(),
    )

    info = image_ocr_runtime_info()

    assert info["available"] is True
    assert info["models"][0]["status"] == "download_on_first_use"


def test_ocr_runtime_info_requires_the_paddlex_ocr_pipeline_configuration(
    tmp_path, monkeypatch
):
    package_root = tmp_path / "paddlex"
    package_root.mkdir()
    package_origin = package_root / "__init__.py"
    package_origin.touch()
    monkeypatch.setattr(
        image_dimensions, "_optional_package_version", lambda _package: "1.0"
    )
    monkeypatch.setattr(
        image_dimensions.util,
        "find_spec",
        lambda package: type("Spec", (), {"origin": str(package_origin)})()
        if package == "paddlex"
        else object(),
    )

    info = image_ocr_runtime_info()

    assert info["available"] is False


def test_ocr_runtime_info_requires_paddlex_ocr_core_dependencies(monkeypatch):
    monkeypatch.setattr(
        image_dimensions, "_optional_package_version", lambda _package: "1.0"
    )
    monkeypatch.setattr(image_dimensions.util, "find_spec", lambda _package: object())
    monkeypatch.setattr(
        image_dimensions, "_paddlex_ocr_pipeline_is_available", lambda: True
    )
    monkeypatch.setattr(
        image_dimensions,
        "_paddlex_ocr_core_is_available",
        lambda: False,
        raising=False,
    )

    info = image_ocr_runtime_info()

    assert info["available"] is False


def test_detects_embedded_ocr_model_cache_in_pyinstaller_bundle(tmp_path, monkeypatch):
    model_cache = tmp_path / "ocr_models"
    model_cache.mkdir()
    monkeypatch.setattr(image_dimensions.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert bundled_ocr_model_cache_path() == str(model_cache)


def test_uses_configured_local_model_cache_when_no_bundle_is_present(tmp_path, monkeypatch):
    monkeypatch.delattr(image_dimensions.sys, "_MEIPASS", raising=False)
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(tmp_path))

    assert ocr_model_cache_path() == str(tmp_path)
