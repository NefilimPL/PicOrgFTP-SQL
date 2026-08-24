"""Stage-aware local OCR orchestration for fast and accurate profiles."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from typing import Protocol

from PIL import Image

from .image_dimensions import ImageDimensionRecognizer, OcrTextBox, PaddleImageDimensionRecognizer
from .ocr_profiles import normalize_ocr_profile_ids


ProgressCallback = Callable[..., None]
StagePolicy = Callable[[str], object]


def _emit(callback: ProgressCallback | None, kind: str, **payload: object) -> None:
    if callback is not None:
        callback(kind, **payload)


def _wait_for_stage(
    callback: StagePolicy | None,
    stage: str,
    emit: ProgressCallback | None,
    sleeper: Callable[[float], None],
) -> None:
    if callback is None:
        return
    while True:
        decision = callback(stage)
        action = str(getattr(decision, "action", "run"))
        if action == "run":
            return
        reason = str(getattr(decision, "reason", "resource_limit"))
        retry = max(0.05, float(getattr(decision, "retry_after_seconds", 1.0)))
        if action == "throttle":
            _emit(emit, "throttled", stage=stage, resource=reason, retry_after_seconds=retry)
            sleeper(retry)
            continue
        _emit(emit, "paused", stage=stage, reason=reason, retry_after_seconds=retry)
        raise RuntimeError(f"OCR stage deferred: {reason}")


def _merge_boxes(boxes: Iterable[OcrTextBox]) -> list[OcrTextBox]:
    merged: list[OcrTextBox] = []
    indexes: dict[tuple[str, tuple[int, int, int, int]], int] = {}
    for box in boxes:
        key = (str(box.text).strip().casefold(), box.bbox)
        index = indexes.get(key)
        if index is None:
            indexes[key] = len(merged)
            merged.append(box)
        elif box.confidence > merged[index].confidence:
            merged[index] = box
    return merged


def _bounded_bbox(box: OcrTextBox, image: Image.Image) -> tuple[int, int, int, int] | None:
    left, top, right, bottom = (int(value) for value in box.bbox)
    left = max(0, min(image.width, left))
    top = max(0, min(image.height, top))
    right = max(left, min(image.width, right))
    bottom = max(top, min(image.height, bottom))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _translated(box: OcrTextBox, origin: tuple[int, int, int, int]) -> OcrTextBox:
    left, top, _right, _bottom = origin
    box_left, box_top, box_right, box_bottom = box.bbox
    return OcrTextBox(
        box.text,
        box.confidence,
        (left + box_left, top + box_top, left + box_right, top + box_bottom),
        box.hint,
        box.angle,
    )


def run_ocr_pipeline(
    path: str,
    *,
    profile_ids: Iterable[object],
    recognizer_factory: Callable[[object], ImageDimensionRecognizer] | None = None,
    on_event: ProgressCallback | None = None,
    before_stage: StagePolicy | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> list[OcrTextBox]:
    """Run selected profiles, restricting accurate OCR to fast-detected regions."""

    profiles = normalize_ocr_profile_ids(list(profile_ids))
    if not profiles:
        raise ValueError("At least one OCR profile must be selected.")
    factory = recognizer_factory or PaddleImageDimensionRecognizer
    source_path = str(path)
    all_boxes: list[OcrTextBox] = []

    if profiles == ["accurate"]:
        _wait_for_stage(before_stage, "accurate_full_image", on_event, sleeper)
        _emit(on_event, "stage_started", stage="accurate_full_image", model="accurate")
        boxes = factory("accurate").detect(source_path)
        _emit(on_event, "stage_finished", stage="accurate_full_image", model="accurate")
        return _merge_boxes(boxes)

    _wait_for_stage(before_stage, "fast_full_image", on_event, sleeper)
    _emit(on_event, "stage_started", stage="fast_full_image", model="fast")
    fast_boxes = factory("fast").detect(source_path)
    all_boxes.extend(fast_boxes)
    _emit(
        on_event,
        "candidate_regions",
        model="fast",
        regions=[
            {"bbox": list(box.bbox), "text": box.text, "confidence": box.confidence}
            for box in fast_boxes
        ],
    )
    _emit(on_event, "stage_finished", stage="fast_full_image", model="fast")

    if "accurate" not in profiles:
        return _merge_boxes(all_boxes)

    with Image.open(source_path) as source, TemporaryDirectory(prefix="picorg-ocr-") as temp_dir:
        source = source.convert("RGB")
        regions = [bbox for box in fast_boxes if (bbox := _bounded_bbox(box, source))]
        total = len(regions)
        for index, region in enumerate(regions, start=1):
            _wait_for_stage(before_stage, "accurate_crop", on_event, sleeper)
            _emit(
                on_event,
                "crop_started",
                stage="accurate_crop",
                model="accurate",
                crop_index=index,
                crop_total=total,
                bbox=list(region),
            )
            crop_path = Path(temp_dir) / f"crop-{index}.png"
            source.crop(region).save(crop_path, format="PNG", optimize=True)
            accurate_boxes = factory("accurate").detect(str(crop_path))
            all_boxes.extend(_translated(box, region) for box in accurate_boxes)
            _emit(
                on_event,
                "crop_finished",
                stage="accurate_crop",
                model="accurate",
                crop_index=index,
                crop_total=total,
                bbox=list(region),
            )
    return _merge_boxes(all_boxes)
