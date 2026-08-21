"""Persistent OCR-value collection for immutable image content."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Protocol

from .image_dimensions import ImageOcrDiagnostics


class OcrScanStore(Protocol):
    def get_ocr_scan(self, image_hash: str) -> dict[str, object] | None: ...

    def upsert_ocr_scan(
        self, image_hash: str, values: list[dict[str, object]], state: str
    ) -> None: ...


@dataclass(frozen=True)
class OcrCacheResult:
    image_hash: str
    state: str
    reused: bool
    values: list[dict[str, object]]


def image_content_hash(path: str) -> str:
    """Hash image bytes in bounded chunks, independent from its slot or filename."""

    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def collect_image_values(
    path: str,
    *,
    store: OcrScanStore,
    analyze: Callable[[str], ImageOcrDiagnostics],
) -> OcrCacheResult:
    """Run OCR once for new image content and persist every numeric candidate."""

    image_hash = image_content_hash(path)
    existing = store.get_ocr_scan(image_hash)
    if isinstance(existing, dict) and str(existing.get("state") or "") == "completed":
        values = list(existing.get("values") or [])
        return OcrCacheResult(image_hash, "completed", True, values)

    store.upsert_ocr_scan(image_hash, [], "scanning")
    diagnostics = analyze(path)
    values = [
        {
            "text": str(candidate.text),
            "comparison": str(candidate.value),
            "confidence": float(candidate.confidence),
            "bbox": list(candidate.bbox),
        }
        for candidate in diagnostics.candidates
        if candidate.accepted and str(candidate.value).strip()
    ]
    state = "completed" if diagnostics.available else "error"
    store.upsert_ocr_scan(image_hash, values, state)
    return OcrCacheResult(image_hash, state, False, values)
