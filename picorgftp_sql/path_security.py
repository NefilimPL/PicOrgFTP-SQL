"""Canonical path containment helpers for trusted filesystem roots."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path


class PathSecurityError(ValueError):
    """Raised when a path is not safe to use below a trusted root."""


def _canonical_path(path: str | os.PathLike[str]) -> str:
    return os.path.realpath(os.path.abspath(os.fspath(path)))


def resolve_path_within_roots(
    path: str | os.PathLike[str],
    roots: Iterable[str | os.PathLike[str]],
    *,
    require_exists: bool = False,
    require_file: bool = False,
) -> Path:
    """Return a canonical path only when it is contained by a trusted root."""
    target = _canonical_path(path)
    for root in roots:
        trusted_root = _canonical_path(root)
        try:
            common = os.path.commonpath([target, trusted_root])
        except ValueError:
            continue
        if os.path.normcase(common) != os.path.normcase(trusted_root):
            continue
        if require_exists and not os.path.exists(target):
            raise PathSecurityError("path does not exist")
        if require_file and not os.path.isfile(target):
            raise PathSecurityError("path is not a regular file")
        return Path(target)
    raise PathSecurityError("path is outside trusted roots")


def build_child_path(root: str | os.PathLike[str], *segments: object) -> Path:
    """Build a canonical child path from individual non-path segments only."""
    safe_segments: list[str] = []
    for segment in segments:
        value = str(segment or "")
        part = Path(value)
        if (
            not value
            or part.is_absolute()
            or len(part.parts) != 1
            or part.name in {"", ".", ".."}
        ):
            raise PathSecurityError("unsafe path segment")
        safe_segments.append(part.name)
    if not safe_segments:
        raise PathSecurityError("missing path segment")
    return resolve_path_within_roots(os.path.join(os.fspath(root), *safe_segments), [root])
