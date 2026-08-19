"""Local image-dimension extraction primitives.

The optional PaddleOCR/OpenCV runtime is deliberately isolated here so the
standard web application can operate without ML dependencies installed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from importlib import metadata, util
import math
import os
from pathlib import Path
import re
import sys
from typing import Iterable, Mapping, Protocol


_DIMENSIONS = frozenset({"width", "depth", "height"})
_NUMBER_PATTERN = re.compile(r"(?<![\d.,])\d+(?:[.,]\d+)?")
_DIMENSION_HINTS = {
    "width": frozenset({"w", "width", "szer", "szerokosc", "szerokość"}),
    "depth": frozenset({"d", "depth", "gleb", "glebokosc", "głęb", "głębokość"}),
    "height": frozenset({"h", "height", "wys", "wysokosc", "wysokość"}),
}
_OCR_ENGINE_NAME = "PaddleOCR"
_OCR_GITHUB_URL = "https://github.com/PaddlePaddle/PaddleOCR"
_OCR_MODEL_NAME = "English default OCR pipeline (lang=en)"


class ImageDimensionUnavailable(RuntimeError):
    """Raised when the optional local OCR runtime has not been installed."""


@dataclass(frozen=True)
class ImageDimensionRequest:
    slot: str
    dimension: str
    minimum_text_confidence: float = 0.8

    def __post_init__(self) -> None:
        if not str(self.slot).strip():
            raise ValueError("Numer slotu jest wymagany.")
        if self.dimension not in _DIMENSIONS:
            raise ValueError("Nieobslugiwany rodzaj wymiaru.")
        if not 0 <= float(self.minimum_text_confidence) <= 1:
            raise ValueError("Minimalna pewnosc musi byc od 0 do 1.")


@dataclass(frozen=True)
class OcrTextBox:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    hint: str | None = None


@dataclass(frozen=True)
class DimensionLine:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class ImageDimensionResult:
    value: str
    text_confidence: float | None
    warning: dict[str, str] | None = None


@dataclass(frozen=True)
class OcrDiagnosticCandidate:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    dimension: str | None
    value: str
    accepted: bool


@dataclass(frozen=True)
class ImageOcrDiagnostics:
    available: bool
    dimensions: dict[str, str]
    candidates: list[OcrDiagnosticCandidate]
    message: str = ""


class ImageDimensionRecognizer(Protocol):
    def detect(self, path: str) -> list[OcrTextBox]:
        """Return OCR candidates for one local image file."""


def image_dimension_source_key(slot: str, dimension: str) -> str:
    return f"IMAGE_DIMENSION:{str(slot).strip()}:{str(dimension).upper()}"


def _display_confidence(value: float) -> int:
    return round(max(0.0, min(1.0, value)) * 100)


def _warning(code: str, slot: str, message: str) -> dict[str, str]:
    return {"code": code, "slot": slot, "message": message}


def _normalized_hint(value: str | None) -> str | None:
    text = str(value or "").strip().casefold()
    if not text:
        return None
    for dimension, hints in _DIMENSION_HINTS.items():
        if text in hints:
            return dimension
    return None


def _parse_numeric_value(value: str) -> str | None:
    match = _NUMBER_PATTERN.search(str(value or ""))
    if not match:
        return None
    try:
        parsed = Decimal(match.group(0).replace(",", "."))
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    normalized = format(parsed.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _candidate_for_dimension(
    boxes: Iterable[OcrTextBox], dimension: str
) -> OcrTextBox | None:
    candidates = [
        box
        for box in boxes
        if _normalized_hint(box.hint) == dimension
        and _parse_numeric_value(box.text) is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: float(item.confidence))


def _line_dimension(line: DimensionLine) -> str | None:
    angle = abs(math.degrees(math.atan2(line.y2 - line.y1, line.x2 - line.x1)))
    if angle > 90:
        angle = 180 - angle
    if angle <= 15:
        return "width"
    if 75 <= angle <= 105:
        return "height"
    if 20 <= angle <= 70:
        return "depth"
    return None


def _distance_to_segment(x: float, y: float, line: DimensionLine) -> float:
    delta_x = line.x2 - line.x1
    delta_y = line.y2 - line.y1
    squared_length = delta_x * delta_x + delta_y * delta_y
    if squared_length == 0:
        return math.hypot(x - line.x1, y - line.y1)
    factor = max(
        0.0,
        min(
            1.0,
            ((x - line.x1) * delta_x + (y - line.y1) * delta_y) / squared_length,
        ),
    )
    return math.hypot(x - (line.x1 + factor * delta_x), y - (line.y1 + factor * delta_y))


def associate_dimension_hints(
    boxes: Iterable[OcrTextBox], lines: Iterable[DimensionLine]
) -> list[OcrTextBox]:
    """Classify unlabelled numeric OCR boxes by their nearest dimension line."""

    usable_lines = [line for line in lines if _line_dimension(line)]
    associated: list[OcrTextBox] = []
    for box in boxes:
        if _normalized_hint(box.hint) or _parse_numeric_value(box.text) is None:
            associated.append(box)
            continue
        left, top, right, bottom = box.bbox
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        if not usable_lines:
            associated.append(box)
            continue
        closest = min(
            usable_lines,
            key=lambda line: _distance_to_segment(center_x, center_y, line),
        )
        associated.append(replace(box, hint=_line_dimension(closest)))
    return associated


def _default_recognizer() -> ImageDimensionRecognizer:
    return PaddleImageDimensionRecognizer()


def _optional_package_version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def image_ocr_runtime_info() -> dict[str, object]:
    """Return display metadata without importing optional OCR packages."""

    paddleocr_version = _optional_package_version("paddleocr")
    paddle_version = _optional_package_version("paddlepaddle")
    opencv_version = _optional_package_version("opencv-python-headless") or _optional_package_version("opencv-python")
    available = bool(
        paddleocr_version
        and paddle_version
        and opencv_version
        and util.find_spec("paddleocr")
        and util.find_spec("cv2")
    )
    model_cache_ready = _model_cache_has_content(ocr_model_cache_path())
    return {
        "available": available,
        "engine": {
            "name": _OCR_ENGINE_NAME,
            "version": paddleocr_version or "niezainstalowany",
        },
        "runtime": {
            "name": "PaddlePaddle + OpenCV",
            "version": " / ".join(
                value for value in (paddle_version, opencv_version) if value
            )
            or "niezainstalowany",
        },
        "models": [
            {
                "name": _OCR_MODEL_NAME,
                "version": "lang=en",
                "status": (
                    "ready"
                    if available and model_cache_ready
                    else "download_on_first_use"
                    if available
                    else "unavailable"
                ),
            }
        ],
        "github_url": _OCR_GITHUB_URL,
    }


def bundled_ocr_model_cache_path() -> str | None:
    """Return models unpacked by a PyInstaller one-file executable, if any."""

    bundle_root = getattr(sys, "_MEIPASS", "")
    if not bundle_root:
        return None
    candidate = Path(str(bundle_root)) / "ocr_models"
    return str(candidate) if candidate.is_dir() else None


def ocr_model_cache_path() -> str:
    """Choose a stable local cache, preferring models embedded in an EXE."""

    bundled = bundled_ocr_model_cache_path()
    if bundled:
        return bundled
    configured = str(os.environ.get("PADDLE_PDX_CACHE_HOME") or "").strip()
    if configured:
        return str(Path(configured))
    app_data = os.environ.get("LOCALAPPDATA")
    root = Path(app_data) if app_data else Path.home() / ".cache"
    return str(root / "PicOrgFTP-SQL" / "ocr-models")


def _model_cache_has_content(path: str) -> bool:
    try:
        return Path(path).is_dir() and any(Path(path).iterdir())
    except OSError:
        return False


def analyze_image_dimensions(
    path: str,
    minimum_text_confidence: float = 0.8,
    *,
    recognizer: ImageDimensionRecognizer | None = None,
) -> ImageOcrDiagnostics:
    """Inspect every OCR box for the settings diagnostic screen."""

    threshold = float(minimum_text_confidence)
    if not 0 <= threshold <= 1:
        raise ValueError("Minimalna pewnosc musi byc od 0 do 1.")
    try:
        boxes = (recognizer or _default_recognizer()).detect(path)
    except ImageDimensionUnavailable as exc:
        return ImageOcrDiagnostics(
            available=False,
            dimensions={dimension: "" for dimension in sorted(_DIMENSIONS)},
            candidates=[],
            message=str(exc).strip() or "Lokalny OCR nie jest zainstalowany.",
        )
    except Exception as exc:
        return ImageOcrDiagnostics(
            available=False,
            dimensions={dimension: "" for dimension in sorted(_DIMENSIONS)},
            candidates=[],
            message=f"Nie udalo sie uruchomic lokalnego OCR: {exc}",
        )

    candidates: list[OcrDiagnosticCandidate] = []
    best: dict[str, OcrDiagnosticCandidate] = {}
    for box in boxes:
        dimension = _normalized_hint(box.hint)
        value = _parse_numeric_value(box.text) or ""
        accepted = bool(dimension and value and float(box.confidence) >= threshold)
        candidate = OcrDiagnosticCandidate(
            text=str(box.text),
            confidence=float(box.confidence),
            bbox=box.bbox,
            dimension=dimension,
            value=value,
            accepted=accepted,
        )
        candidates.append(candidate)
        if accepted and dimension:
            previous = best.get(dimension)
            if previous is None or candidate.confidence > previous.confidence:
                best[dimension] = candidate
    return ImageOcrDiagnostics(
        available=True,
        dimensions={dimension: best.get(dimension, OcrDiagnosticCandidate("", 0, (0, 0, 0, 0), None, "", False)).value for dimension in sorted(_DIMENSIONS)},
        candidates=candidates,
    )


def _result_for_request(
    request: ImageDimensionRequest, boxes: Iterable[OcrTextBox]
) -> ImageDimensionResult:
    candidate = _candidate_for_dimension(boxes, request.dimension)
    if candidate is None:
        return ImageDimensionResult(
            "",
            None,
            _warning(
                "image_dimension_not_found",
                request.slot,
                f"Nie znaleziono wymiaru {request.dimension} na obrazie slotu {request.slot}.",
            ),
        )
    confidence = float(candidate.confidence)
    if confidence < float(request.minimum_text_confidence):
        actual = _display_confidence(confidence)
        required = _display_confidence(float(request.minimum_text_confidence))
        return ImageDimensionResult(
            "",
            confidence,
            _warning(
                "image_dimension_low_confidence",
                request.slot,
                f"Odczyt {actual}% jest ponizej wymaganego progu {required}%.",
            ),
        )
    return ImageDimensionResult(_parse_numeric_value(candidate.text) or "", confidence)


def resolve_image_dimensions(
    requests: Iterable[ImageDimensionRequest],
    slot_paths: Mapping[str, str],
    *,
    recognizer: ImageDimensionRecognizer | None = None,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Resolve template sources, running OCR no more than once per slot."""

    grouped: dict[str, list[ImageDimensionRequest]] = {}
    for request in requests:
        grouped.setdefault(str(request.slot), []).append(request)

    values: dict[str, str] = {}
    warnings: list[dict[str, str]] = []
    active_recognizer = recognizer
    for slot, slot_requests in grouped.items():
        path = str(slot_paths.get(slot) or "")
        if not path:
            for request in slot_requests:
                values[image_dimension_source_key(slot, request.dimension)] = ""
            warnings.append(
                _warning(
                    "image_dimension_missing_slot",
                    slot,
                    f"Brak obrazu w slocie {slot}.",
                )
            )
            continue
        try:
            if active_recognizer is None:
                active_recognizer = _default_recognizer()
            boxes = active_recognizer.detect(path)
        except Exception:
            for request in slot_requests:
                values[image_dimension_source_key(slot, request.dimension)] = ""
            warnings.append(
                _warning(
                    "ocr_unavailable",
                    slot,
                    "Lokalny OCR jest niedostepny.",
                )
            )
            continue
        for request in slot_requests:
            result = _result_for_request(request, boxes)
            values[image_dimension_source_key(slot, request.dimension)] = result.value
            if result.warning:
                warnings.append(result.warning)
    return values, warnings


class PaddleImageDimensionRecognizer:
    """Optional local PaddleOCR adapter.

    It intentionally raises a clear domain exception until optional OCR
    dependencies have been installed from requirements-vision.txt.
    """

    def __init__(self) -> None:
        bundled_models = bundled_ocr_model_cache_path()
        if bundled_models:
            os.environ["PADDLE_PDX_CACHE_HOME"] = bundled_models
        else:
            os.environ.setdefault("PADDLE_PDX_CACHE_HOME", ocr_model_cache_path())
        try:
            import cv2
            from paddleocr import PaddleOCR
        except ImportError as exc:  # pragma: no cover - runtime optionality
            raise ImageDimensionUnavailable from exc
        self._cv2 = cv2
        self._ocr = PaddleOCR(lang="en")

    def detect(self, path: str) -> list[OcrTextBox]:  # pragma: no cover - optional runtime
        raw = self._ocr.predict(path)
        boxes: list[OcrTextBox] = []
        for page in raw:
            payload = page.json if hasattr(page, "json") else page
            result = payload.get("res", payload) if isinstance(payload, dict) else {}
            texts = result.get("rec_texts", []) if isinstance(result, dict) else []
            scores = result.get("rec_scores", []) if isinstance(result, dict) else []
            polygons = result.get("rec_polys", []) if isinstance(result, dict) else []
            for text, score, polygon in zip(texts, scores, polygons):
                xs = [int(point[0]) for point in polygon]
                ys = [int(point[1]) for point in polygon]
                boxes.append(
                    OcrTextBox(
                        str(text),
                        float(score),
                        (min(xs), min(ys), max(xs), max(ys)),
                        None,
                    )
                )
        image = self._cv2.imread(path)
        if image is None:
            return boxes
        gray = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2GRAY)
        edges = self._cv2.Canny(gray, 50, 150)
        raw_lines = self._cv2.HoughLinesP(
            edges,
            1,
            math.pi / 180,
            45,
            minLineLength=30,
            maxLineGap=12,
        )
        lines = (
            [DimensionLine(*(int(value) for value in line[0])) for line in raw_lines]
            if raw_lines is not None
            else []
        )
        return associate_dimension_hints(boxes, lines)
