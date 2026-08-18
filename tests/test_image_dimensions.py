from __future__ import annotations

from picorgftp_sql.services.image_dimensions import (
    DimensionLine,
    ImageDimensionRequest,
    OcrTextBox,
    associate_dimension_hints,
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
