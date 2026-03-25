"""Persistent local file index used to speed up directory lookups."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from typing import Any

INDEX_VERSION = 1


def _normalize_relpath(path: str) -> str:
    text = str(path or "").replace("\\", "/").strip("/")
    if text == ".":
        return ""
    return text


def _clone_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {"dir_mtime_ns": None, "subdirs": [], "files": []}
    return {
        "dir_mtime_ns": entry.get("dir_mtime_ns"),
        "subdirs": list(entry.get("subdirs", [])),
        "files": [dict(item) for item in entry.get("files", []) if isinstance(item, dict)],
    }


class LocalFileIndex:
    """Cache directory listings on disk and refresh them in the background."""

    def __init__(self, root_dir: str, index_path: str, *, enabled: bool = True) -> None:
        self.root_dir = os.path.abspath(root_dir)
        self.index_path = os.path.abspath(index_path)
        self.enabled = bool(enabled)
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._loaded_from_disk = False
        self._refresh_thread: threading.Thread | None = None
        self._refresh_requested = False
        self._status: dict[str, Any] = {
            "state": "disabled" if not self.enabled else "idle",
            "dirs_scanned": 0,
            "files_scanned": 0,
            "started_at": None,
            "finished_at": None,
            "loaded_from_disk": False,
            "last_error": "",
            "cache_entries": 0,
            "dirty": False,
        }
        self._load_snapshot()

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.enabled = bool(enabled)
            if not self.enabled:
                self._status["state"] = "disabled"
            elif self._status.get("state") == "disabled":
                self._status["state"] = "idle"

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def list_subdirs(self, dir_path: str) -> list[str]:
        entry = self._get_entry(dir_path)
        return list(entry.get("subdirs", []))

    def list_files(self, dir_path: str) -> list[dict[str, Any]]:
        entry = self._get_entry(dir_path)
        return [dict(item) for item in entry.get("files", [])]

    def refresh_async(self, *, force: bool = False) -> bool:
        with self._lock:
            if not self.enabled:
                self._status["state"] = "disabled"
                return False
            if self._refresh_thread and self._refresh_thread.is_alive():
                if force:
                    self._refresh_requested = True
                return False
            thread = threading.Thread(
                target=self._refresh_worker_loop,
                name="LocalFileIndex",
                daemon=True,
            )
            self._refresh_requested = False
            self._refresh_thread = thread
        thread.start()
        return True

    def persist_if_dirty(self) -> bool:
        with self._lock:
            if not self.enabled or not self._dirty:
                return False
            snapshot = self._build_snapshot_locked()
        self._write_snapshot(snapshot)
        with self._lock:
            self._dirty = False
            self._status["dirty"] = False
        return True

    def _refresh_worker_loop(self) -> None:
        while True:
            started_at = time.time()
            self._update_status(
                state="running",
                dirs_scanned=0,
                files_scanned=0,
                started_at=started_at,
                finished_at=None,
                last_error="",
            )
            try:
                entries, dirs_scanned, files_scanned = self._scan_tree(started_at)
                finished_at = time.time()
                with self._lock:
                    self._entries = entries
                    self._loaded_from_disk = True
                    self._dirty = False
                    snapshot = self._build_snapshot_locked(finished_at=finished_at)
                    self._status.update(
                        {
                            "state": "idle",
                            "dirs_scanned": dirs_scanned,
                            "files_scanned": files_scanned,
                            "finished_at": finished_at,
                            "loaded_from_disk": True,
                            "cache_entries": len(entries),
                            "dirty": False,
                        }
                    )
                self._write_snapshot(snapshot)
            except Exception as exc:  # pragma: no cover - defensive runtime path
                self._update_status(
                    state="error",
                    finished_at=time.time(),
                    last_error=str(exc),
                )
            with self._lock:
                rerun = self._refresh_requested
                self._refresh_requested = False
                if not rerun:
                    self._refresh_thread = None
                    return

    def _scan_tree(self, started_at: float) -> tuple[dict[str, dict[str, Any]], int, int]:
        entries: dict[str, dict[str, Any]] = {}
        dirs_scanned = 0
        files_scanned = 0
        if not os.path.isdir(self.root_dir):
            return {"": {"dir_mtime_ns": None, "subdirs": [], "files": []}}, 0, 0
        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            dirnames.sort()
            filenames.sort()
            rel_path = _normalize_relpath(os.path.relpath(dirpath, self.root_dir))
            files = []
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                try:
                    stat = os.stat(full_path)
                except OSError:
                    continue
                files.append(
                    {
                        "name": filename,
                        "size": int(stat.st_size),
                        "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
                    }
                )
            try:
                dir_stat = os.stat(dirpath)
                dir_mtime_ns = int(
                    getattr(dir_stat, "st_mtime_ns", int(dir_stat.st_mtime * 1_000_000_000))
                )
            except OSError:
                dir_mtime_ns = None
            entries[rel_path] = {
                "dir_mtime_ns": dir_mtime_ns,
                "subdirs": list(dirnames),
                "files": files,
            }
            dirs_scanned += 1
            files_scanned += len(files)
            if dirs_scanned == 1 or dirs_scanned % 25 == 0:
                self._update_status(
                    state="running",
                    dirs_scanned=dirs_scanned,
                    files_scanned=files_scanned,
                    started_at=started_at,
                )
        if "" not in entries:
            entries[""] = {"dir_mtime_ns": None, "subdirs": [], "files": []}
        return entries, dirs_scanned, files_scanned

    def _get_entry(self, dir_path: str) -> dict[str, Any]:
        live_dir = os.path.abspath(dir_path)
        rel_path = self._to_rel_path(live_dir)
        if rel_path is None or not self.enabled:
            return self._read_live_entry(live_dir)
        with self._lock:
            cached = _clone_entry(self._entries.get(rel_path))
        if cached and self._entry_is_fresh(live_dir, cached):
            return cached
        live_entry = self._read_live_entry(live_dir)
        with self._lock:
            self._entries[rel_path] = _clone_entry(live_entry)
            self._dirty = True
            self._status["dirty"] = True
            self._status["cache_entries"] = len(self._entries)
        return live_entry

    def _read_live_entry(self, dir_path: str) -> dict[str, Any]:
        if not os.path.isdir(dir_path):
            return {"dir_mtime_ns": None, "subdirs": [], "files": []}
        subdirs = []
        files = []
        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            subdirs.append(entry.name)
                        elif entry.is_file(follow_symlinks=False):
                            stat = entry.stat(follow_symlinks=False)
                            files.append(
                                {
                                    "name": entry.name,
                                    "size": int(stat.st_size),
                                    "mtime_ns": int(
                                        getattr(
                                            stat,
                                            "st_mtime_ns",
                                            int(stat.st_mtime * 1_000_000_000),
                                        )
                                    ),
                                }
                            )
                    except OSError:
                        continue
        except OSError:
            return {"dir_mtime_ns": None, "subdirs": [], "files": []}
        subdirs.sort()
        files.sort(key=lambda item: item["name"])
        try:
            stat = os.stat(dir_path)
            dir_mtime_ns = int(
                getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
            )
        except OSError:
            dir_mtime_ns = None
        return {
            "dir_mtime_ns": dir_mtime_ns,
            "subdirs": subdirs,
            "files": files,
        }

    def _entry_is_fresh(self, dir_path: str, entry: dict[str, Any]) -> bool:
        if not os.path.isdir(dir_path):
            return entry.get("dir_mtime_ns") is None
        try:
            stat = os.stat(dir_path)
        except OSError:
            return False
        current_mtime_ns = int(
            getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        )
        return entry.get("dir_mtime_ns") == current_mtime_ns

    def _to_rel_path(self, dir_path: str) -> str | None:
        try:
            rel_path = os.path.relpath(dir_path, self.root_dir)
        except ValueError:
            return None
        if rel_path == os.pardir or rel_path.startswith(os.pardir + os.sep):
            return None
        return _normalize_relpath(rel_path)

    def _load_snapshot(self) -> None:
        if not os.path.exists(self.index_path):
            return
        try:
            with open(self.index_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        if payload.get("version") != INDEX_VERSION:
            return
        if os.path.abspath(str(payload.get("root_dir") or "")) != self.root_dir:
            return
        raw_entries = payload.get("entries", {})
        if not isinstance(raw_entries, dict):
            return
        entries = {}
        for rel_path, entry in raw_entries.items():
            normalized = _normalize_relpath(rel_path)
            entries[normalized] = _clone_entry(entry)
        finished_at = payload.get("finished_at")
        with self._lock:
            self._entries = entries
            self._loaded_from_disk = True
            self._status.update(
                {
                    "loaded_from_disk": True,
                    "finished_at": finished_at,
                    "cache_entries": len(entries),
                }
            )

    def _build_snapshot_locked(self, *, finished_at: float | None = None) -> dict[str, Any]:
        return {
            "version": INDEX_VERSION,
            "root_dir": self.root_dir,
            "finished_at": finished_at or self._status.get("finished_at"),
            "entries": {
                rel_path: _clone_entry(entry) for rel_path, entry in self._entries.items()
            },
        }

    def _write_snapshot(self, snapshot: dict[str, Any]) -> None:
        directory = os.path.dirname(self.index_path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix="local_file_index_",
            suffix=".json.tmp",
            dir=directory,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, indent=2)
            os.replace(temp_path, self.index_path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _update_status(self, **updates: Any) -> None:
        with self._lock:
            self._status.update(updates)
            self._status["loaded_from_disk"] = self._loaded_from_disk
            self._status["cache_entries"] = len(self._entries)
            self._status["dirty"] = self._dirty
