"""Pure representations for persisted local file-index generations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FileIndexSegment:
    segment_key: str
    section: str
    lookup_key: str
    payload: object


@dataclass(frozen=True)
class FileIndexGeneration:
    cache_key: str
    generation_id: str
    root: str
    version: int
    generated_at: str
    complete: bool
    dirs_scanned: int = 0
    products_scanned: int = 0
    snapshot: dict[str, object] | None = None

    def empty_snapshot(self) -> dict[str, object]:
        return {
            "version": self.version,
            "root": self.root,
            "generated_at": self.generated_at,
            "dirs_scanned": self.dirs_scanned,
            "products_scanned": self.products_scanned,
            "names": [],
            "types": {},
            "models": {},
            "colors": {},
            "extras": {},
            "files": {},
        }


def normalize_segment_key(value: object) -> str:
    text = str(value or "").strip().upper()
    for character in text:
        if character.isalnum():
            return character if character.isascii() else "_"
    return "_"


def snapshot_to_segments(snapshot: dict[str, object]) -> list[FileIndexSegment]:
    rows: list[FileIndexSegment] = []
    names = snapshot.get("names", [])
    for name in names if isinstance(names, list) else []:
        rows.append(
            FileIndexSegment(
                segment_key=normalize_segment_key(name),
                section="names",
                lookup_key=str(name).upper(),
                payload=name,
            )
        )
    for section in ("types", "models", "colors", "extras", "files"):
        values = snapshot.get(section, {})
        if not isinstance(values, dict):
            continue
        for lookup_key, payload in sorted(values.items()):
            name_key = str(lookup_key).split("\x1f", 1)[0]
            rows.append(
                FileIndexSegment(
                    segment_key=normalize_segment_key(name_key),
                    section=section,
                    lookup_key=str(lookup_key),
                    payload=payload,
                )
            )
    return rows


def segments_to_snapshot(
    generation: FileIndexGeneration,
    segments: Iterable[FileIndexSegment],
) -> dict[str, object]:
    snapshot = generation.empty_snapshot()
    for segment in segments:
        if segment.section == "names":
            snapshot["names"].append(segment.payload)
        elif segment.section in {"types", "models", "colors", "extras", "files"}:
            snapshot[segment.section][segment.lookup_key] = segment.payload
    snapshot["names"].sort()
    return snapshot
