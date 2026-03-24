"""Background local filesystem index used by GUI lookups."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time

from .workflow_utils import (
    build_color_segment,
    normalize_extra_segment,
    sanitize_path_segment,
)

INDEX_VERSION = 1
KEY_SEPARATOR = "\x1f"
NO_EXTRA_VALUE = "NO-LED"


def _directory_names(path: str) -> list[str]:
    """Return child directory names sorted alphabetically."""

    try:
        with os.scandir(path) as entries:
            return sorted(entry.name for entry in entries if entry.is_dir())
    except OSError:
        return []


def _file_names(path: str) -> list[str]:
    """Return direct child file names sorted alphabetically."""

    try:
        with os.scandir(path) as entries:
            return sorted(entry.name for entry in entries if entry.is_file())
    except OSError:
        return []


def _join_key(*parts: object) -> str:
    """Build a stable lookup key for the index payload."""

    normalized = []
    for value in parts:
        text = str(value or "").strip()
        if not text:
            continue
        normalized.append(text.upper())
    return KEY_SEPARATOR.join(normalized)


def _normalize_name_key(value: object) -> str:
    return sanitize_path_segment(value)


def _normalize_type_key(value: object) -> str:
    return sanitize_path_segment(value)


def _normalize_model_key(value: object) -> str:
    return sanitize_path_segment(value)


def _normalize_color_key(colors) -> str:
    return build_color_segment(colors)


def _normalize_extra_key(value: object) -> str:
    return normalize_extra_segment(value, fallback=NO_EXTRA_VALUE)


class LocalFileIndex:
    """Cache the local product directory tree for faster GUI lookups."""

    def __init__(self, root_dir: str, cache_path: str, status_callback=None):
        self.root_dir = os.path.abspath(root_dir)
        self.cache_path = os.path.abspath(cache_path)
        self._status_callback = status_callback
        self._lock = threading.Lock()
        self._snapshot = None
        self._refresh_thread = None
        self._status = {
            "state": "idle",
            "cache_loaded": False,
            "has_snapshot": False,
            "dirs_scanned": 0,
            "products_scanned": 0,
            "name_count": 0,
            "generated_at": None,
            "error": "",
        }

    def _emit_status(self, **updates) -> None:
        callback = None
        with self._lock:
            self._status = dict(self._status)
            self._status.update(updates)
            callback = self._status_callback
            payload = dict(self._status)
        if callback is not None:
            try:
                callback(payload)
            except Exception:
                pass

    def _replace_snapshot(self, snapshot: dict, *, state: str, cache_loaded: bool) -> None:
        with self._lock:
            self._snapshot = snapshot
        self._emit_status(
            state=state,
            cache_loaded=cache_loaded,
            has_snapshot=True,
            dirs_scanned=int(snapshot.get("dirs_scanned", 0)),
            products_scanned=int(snapshot.get("products_scanned", 0)),
            name_count=len(snapshot.get("names", [])),
            generated_at=snapshot.get("generated_at"),
            error="",
        )

    def _write_cache(self, snapshot: dict) -> None:
        directory = os.path.dirname(self.cache_path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix="file_index_",
            suffix=".json.tmp",
            dir=directory,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, indent=2)
            os.replace(temp_path, self.cache_path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _build_snapshot(self) -> dict:
        names = []
        types = {}
        models = {}
        colors = {}
        extras = {}
        files = {}
        dirs_scanned = 0
        products_scanned = 0
        last_progress_push = 0.0

        def _report_progress(force: bool = False) -> None:
            nonlocal last_progress_push
            if not force and (time.time() - last_progress_push) < 0.25:
                return
            last_progress_push = time.time()
            self._emit_status(
                state="refreshing",
                dirs_scanned=dirs_scanned,
                products_scanned=products_scanned,
                error="",
            )

        if not os.path.isdir(self.root_dir):
            return {
                "version": INDEX_VERSION,
                "root": self.root_dir,
                "generated_at": time.time(),
                "dirs_scanned": 0,
                "products_scanned": 0,
                "names": [],
                "types": {},
                "models": {},
                "colors": {},
                "extras": {},
                "files": {},
            }

        for name_dir in _directory_names(self.root_dir):
            dirs_scanned += 1
            name_path = os.path.join(self.root_dir, name_dir)
            name_key = _normalize_name_key(name_dir)
            if not name_key:
                continue
            names.append(name_dir.upper())
            type_values = []
            for type_dir in _directory_names(name_path):
                dirs_scanned += 1
                type_path = os.path.join(name_path, type_dir)
                type_key = _normalize_type_key(type_dir)
                if not type_key:
                    continue
                type_values.append(type_dir)
                model_values = []
                for model_dir in _directory_names(type_path):
                    dirs_scanned += 1
                    model_path = os.path.join(type_path, model_dir)
                    model_key = _normalize_model_key(model_dir)
                    if not model_key:
                        continue
                    model_values.append(model_dir)
                    color_values = []
                    for color_dir in _directory_names(model_path):
                        dirs_scanned += 1
                        color_path = os.path.join(model_path, color_dir)
                        color_key = _normalize_color_key(color_dir.split("-"))
                        if not color_key:
                            continue
                        color_values.append(color_dir)
                        extra_values = []
                        for extra_dir in _directory_names(color_path):
                            dirs_scanned += 1
                            extra_path = os.path.join(color_path, extra_dir)
                            extra_key = _normalize_extra_key(extra_dir)
                            if not extra_key:
                                continue
                            normalized_extra = (
                                NO_EXTRA_VALUE
                                if extra_key == NO_EXTRA_VALUE
                                else extra_dir
                            )
                            extra_values.append(normalized_extra)
                            files[
                                _join_key(
                                    name_key,
                                    type_key,
                                    model_key,
                                    color_key,
                                    extra_key,
                                )
                            ] = _file_names(extra_path)
                            products_scanned += 1
                            _report_progress()
                        extras[
                            _join_key(name_key, type_key, model_key, color_key)
                        ] = extra_values
                    colors[_join_key(name_key, type_key, model_key)] = color_values
                models[_join_key(name_key, type_key)] = model_values
            types[name_key] = type_values
        _report_progress(force=True)
        return {
            "version": INDEX_VERSION,
            "root": self.root_dir,
            "generated_at": time.time(),
            "dirs_scanned": dirs_scanned,
            "products_scanned": products_scanned,
            "names": names,
            "types": types,
            "models": models,
            "colors": colors,
            "extras": extras,
            "files": files,
        }

    def load_cache(self) -> bool:
        """Load a previously saved snapshot if it matches the active root."""

        try:
            with open(self.cache_path, "r", encoding="utf-8") as handle:
                snapshot = json.load(handle)
        except (OSError, ValueError, TypeError):
            return False
        if not isinstance(snapshot, dict):
            return False
        if snapshot.get("version") != INDEX_VERSION:
            return False
        if os.path.abspath(snapshot.get("root", "")) != self.root_dir:
            return False
        for key in ("names", "types", "models", "colors", "extras", "files"):
            if key not in snapshot:
                return False
        self._replace_snapshot(snapshot, state="cached", cache_loaded=True)
        return True

    def refresh_sync(self) -> bool:
        """Rebuild the snapshot immediately and persist it to disk."""

        cache_loaded = self.get_status().get("cache_loaded", False)
        self._emit_status(state="refreshing", error="")
        try:
            snapshot = self._build_snapshot()
            self._write_cache(snapshot)
        except Exception as exc:
            self._emit_status(state="error", error=str(exc))
            return False
        self._replace_snapshot(snapshot, state="ready", cache_loaded=cache_loaded)
        return True

    def refresh_async(self) -> bool:
        """Rebuild the index in a background thread."""

        with self._lock:
            thread = self._refresh_thread
            if thread is not None and thread.is_alive():
                return False
            thread = threading.Thread(
                target=self._refresh_worker,
                name="LocalFileIndex",
                daemon=True,
            )
            self._refresh_thread = thread
        thread.start()
        return True

    def _refresh_worker(self) -> None:
        try:
            self.refresh_sync()
        finally:
            with self._lock:
                self._refresh_thread = None

    def is_refreshing(self) -> bool:
        """Return True while the background refresh thread is active."""

        with self._lock:
            thread = self._refresh_thread
            return bool(thread is not None and thread.is_alive())

    def has_snapshot(self) -> bool:
        """Return True when a cache snapshot is currently available."""

        with self._lock:
            return self._snapshot is not None

    def get_status(self) -> dict:
        """Return a copy of the current index status."""

        with self._lock:
            return dict(self._status)

    def get_names(self) -> list[str]:
        """Return indexed top-level product names."""

        with self._lock:
            if self._snapshot is None:
                return []
            return list(self._snapshot.get("names", []))

    def get_types(self, name: object):
        """Return indexed type directories for a given product name."""

        key = _normalize_name_key(name)
        with self._lock:
            if self._snapshot is None:
                return None
            values = self._snapshot.get("types", {}).get(key)
            return list(values) if values is not None else None

    def get_models(self, name: object, type_value: object):
        """Return indexed model directories for a name/type pair."""

        key = _join_key(_normalize_name_key(name), _normalize_type_key(type_value))
        with self._lock:
            if self._snapshot is None:
                return None
            values = self._snapshot.get("models", {}).get(key)
            return list(values) if values is not None else None

    def get_colors(self, name: object, type_value: object, model: object):
        """Return indexed colour directories for a name/type/model tuple."""

        key = _join_key(
            _normalize_name_key(name),
            _normalize_type_key(type_value),
            _normalize_model_key(model),
        )
        with self._lock:
            if self._snapshot is None:
                return None
            values = self._snapshot.get("colors", {}).get(key)
            return list(values) if values is not None else None

    def get_extras(self, name: object, type_value: object, model: object, colors):
        """Return indexed extra directories for a specific colour combination."""

        key = _join_key(
            _normalize_name_key(name),
            _normalize_type_key(type_value),
            _normalize_model_key(model),
            _normalize_color_key(colors),
        )
        with self._lock:
            if self._snapshot is None:
                return None
            values = self._snapshot.get("extras", {}).get(key)
            return list(values) if values is not None else None

    def get_product_files(
        self,
        name: object,
        type_value: object,
        model: object,
        colors,
        extra_value: object,
    ):
        """Return indexed file names for a specific product directory."""

        key = _join_key(
            _normalize_name_key(name),
            _normalize_type_key(type_value),
            _normalize_model_key(model),
            _normalize_color_key(colors),
            _normalize_extra_key(extra_value),
        )
        with self._lock:
            if self._snapshot is None:
                return None
            values = self._snapshot.get("files", {}).get(key)
            return list(values) if values is not None else None
