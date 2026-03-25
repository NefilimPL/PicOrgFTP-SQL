"""Persistent directory-index helpers used to speed up folder lookups."""

from __future__ import annotations

import json
import os
import tempfile
import threading

INDEX_VERSION = 1
DEFAULT_INDEX_FILENAME = "directory_index.json"


def build_index_path(base_dir: str, filename: str = DEFAULT_INDEX_FILENAME) -> str:
    """Return the default on-disk location for the directory cache."""

    root = os.path.abspath(base_dir or os.getcwd())
    return os.path.join(root, filename)


class DirectoryIndex:
    """Cache direct child directories for the product tree and persist them to disk."""

    def __init__(self, root_dir: str, *, index_path: str | None = None):
        self.root_dir = os.path.abspath(root_dir)
        self.index_path = os.path.abspath(index_path or build_index_path(os.path.dirname(self.root_dir)))
        self._entries: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def load(self) -> bool:
        """Load the cache from disk when it matches the active root."""

        try:
            with open(self.index_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return False
        if not isinstance(payload, dict):
            return False
        if payload.get("version") != INDEX_VERSION:
            return False
        if os.path.abspath(str(payload.get("root_dir") or "")) != self.root_dir:
            return False
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, dict):
            return False
        cleaned = {}
        for key, value in raw_entries.items():
            if not isinstance(key, str) or not isinstance(value, list):
                continue
            children = sorted(
                {
                    str(item).strip()
                    for item in value
                    if isinstance(item, str) and str(item).strip()
                }
            )
            cleaned[key] = children
        with self._lock:
            self._entries = cleaned
        return True

    def save(self) -> bool:
        """Persist the current cache to disk atomically."""

        payload = {
            "version": INDEX_VERSION,
            "root_dir": self.root_dir,
            "entries": self.snapshot_entries(),
        }
        directory = os.path.dirname(self.index_path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix="directory_index_",
            suffix=".json.tmp",
            dir=directory,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            os.replace(temp_path, self.index_path)
            return True
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def get_child_dirs(self, path: str, *, refresh: bool = False) -> list[str]:
        """Return direct child directories, optionally refreshing the cache."""

        abs_path = os.path.abspath(path)
        key = self._path_key(abs_path)
        if key is None:
            return self._scan_child_dirs(abs_path)
        if not refresh and os.path.isdir(abs_path):
            with self._lock:
                cached = self._entries.get(key)
            if cached is not None:
                return list(cached)
        children = self._scan_child_dirs(abs_path)
        self._store_entry(key, children)
        return children

    def refresh_path_chain(self, path: str) -> None:
        """Refresh the cache for ``path`` and each parent up to the root."""

        abs_path = os.path.abspath(path)
        targets = []
        current = abs_path
        while True:
            key = self._path_key(current)
            if key is None:
                break
            targets.append(current)
            if os.path.normcase(current) == os.path.normcase(self.root_dir):
                break
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        for target in reversed(targets):
            self.get_child_dirs(target, refresh=True)

    def rebuild(self, *, max_depth: int = 5, progress_callback=None) -> dict[str, int]:
        """Rebuild the full cache by scanning the directory tree in the background."""

        new_entries: dict[str, list[str]] = {}
        queue = [(self.root_dir, 0)]
        scanned = 0
        while queue:
            current, depth = queue.pop(0)
            key = self._path_key(current)
            if key is None:
                continue
            children = self._scan_child_dirs(current)
            new_entries[key] = children
            scanned += 1
            if progress_callback:
                progress_callback(scanned, current)
            if depth >= max_depth:
                continue
            for child in children:
                queue.append((os.path.join(current, child), depth + 1))
        with self._lock:
            self._entries = new_entries
        self.save()
        return {"directories": scanned}

    def entry_count(self) -> int:
        """Return the number of cached directories."""

        with self._lock:
            return len(self._entries)

    def snapshot_entries(self) -> dict[str, list[str]]:
        """Return a deep copy of the cached directory map."""

        with self._lock:
            return {key: list(value) for key, value in self._entries.items()}

    def _store_entry(self, key: str, children: list[str]) -> None:
        with self._lock:
            self._entries[key] = list(children)

    def _path_key(self, path: str) -> str | None:
        try:
            relative = os.path.relpath(path, self.root_dir)
        except ValueError:
            return None
        if relative == ".":
            return ""
        if relative.startswith(".."):
            return None
        return relative.replace("\\", "/")

    def _scan_child_dirs(self, path: str) -> list[str]:
        try:
            with os.scandir(path) as iterator:
                return sorted(entry.name for entry in iterator if entry.is_dir())
        except Exception:
            return []
