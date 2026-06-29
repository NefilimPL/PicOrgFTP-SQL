"""Data helpers for the LAN web interface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import ctypes
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unicodedata

from . import common, config, data_store, settings, storage_settings
from . import encryption
from .common import (
    APP_SECRET_KEY,
    AUTO_CONTENT_FIT_KEY,
    COLOR_FIELD_LABELS_KEY,
    H,
    K,
    LOCAL_FILE_INDEX_KEY,
    M,
    N,
    P,
    PROCESSING_SETTINGS_KEY,
    SECURITY_SETTINGS_KEY,
    SQL_AVAILABLE_COLUMNS_KEY,
    SQL_COLUMN_MAP_KEY,
    SLOT_DEFS_KEY,
    TRANSLATION_API_KEY,
    TRANSLATION_SETTINGS_KEY,
    b,
    c,
    ft,
    m,
    p,
    r,
    u,
    v,
    w,
)
from .config import save_config
from .database import connect_db
from .excel_utils import (
    COLOR1_HEADER,
    COLOR2_HEADER,
    COLOR3_HEADER,
    EAN_HEADER,
    ENTRY_RECORDS_KEY,
    EXTRA_HEADER,
    MODEL_HEADER,
    NAME_HEADER,
    PRODUCT_ID_HEADER,
    TYPE_HEADER,
    add_to_list,
    find_list_value_usage,
    prepare_excel_lists,
    remove_from_list,
    save_ean_entry,
    NO_EAN_PLACEHOLDER,
)
from .services.ftp_service import connect_ftp, list_remote_files_for_ean, list_remote_filenames
from .services.sql_service import (
    extract_presence_context,
    query_presence_details,
    should_check_presence,
)
from .file_index import LocalFileIndex
from .slot_utils import normalize_slot_definitions, normalize_sql_column_map
from .workflow_utils import (
    build_product_directory,
    parse_slot_filename,
    sanitize_path_segment,
    select_remote_files_for_ean,
)
from .web_workflow import available_convert_formats
from .version import get_display_version


WEB_FTP_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
WEB_FTP_CACHE_CLEAN_INTERVAL_SECONDS = 60 * 60
_FTP_CACHE_LAST_CLEANUP = 0.0

LIST_SHEETS = {
    "names": "NAZWY",
    "types": "TYPY",
    "models": "MODELE",
    "colors": "KOLORY",
    "extras": "DODATKI",
}

WEB_USERS_PATH = "web_users.json"
WEB_HISTORY_PATH = "web_history.json"
LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_SECONDS = 60 * 60
IMAGE_PREVIEW_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".psd",
    ".eps",
    ".ai",
    ".tif",
    ".tiff",
    ".webp",
}
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 200_000
_FILE_INDEX: LocalFileIndex | None = None
_FILE_INDEX_KEY: tuple[str, str, str, str] | None = None
_FILE_INDEX_REFRESH_STARTED = False
_FTP_CACHE_LOCKS: dict[str, threading.Lock] = {}
_FTP_CACHE_LOCKS_GUARD = threading.Lock()
_USERS_LOCK = threading.RLock()
_CONFIG_SECRET_FIELDS = {
    H: {N, M},
    P: {N, M},
    K: {N, M},
    TRANSLATION_SETTINGS_KEY: {TRANSLATION_API_KEY},
}


class ListValueInUseError(ValueError):
    """Raised when an Excel list value is still referenced by product entries."""

    def __init__(self, list_key: str, value: str, used_by: list[dict[str, str]]):
        self.list_key = list_key
        self.value = value
        self.used_by = used_by
        super().__init__("Nie usunieto wartosci, bo jest uzywana przez produkty.")


@dataclass(frozen=True)
class WebEntry:
    """Entry record returned to the web UI."""

    product_id: str
    ean: str
    name: str
    type_name: str
    model: str
    color1: str
    color2: str
    color3: str
    extra: str

    @property
    def label(self) -> str:
        parts = [self.name, self.type_name, self.model]
        colors = " / ".join(item for item in (self.color1, self.color2, self.color3) if item)
        if colors:
            parts.append(colors)
        if self.extra:
            parts.append(self.extra)
        suffix = f"EAN {self.ean}" if self.ean else self.product_id
        return " | ".join(item for item in parts if item) + (f" - {suffix}" if suffix else "")


def _text(value: object) -> str:
    return str(value or "").strip()


def _active_sqlite_store():
    """Return the active SQLite store adapter, or None in legacy mode."""

    try:
        store = data_store.get_active_store()
        if getattr(store, "mode", "") == "sqlite":
            return store
    except Exception:
        return None
    return None


def _norm(value: object) -> str:
    return _text(value).upper()


def _list_value_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", _text(value)).casefold()
    return "".join(ch for ch in text if not unicodedata.combining(ch)).strip()


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return ":".join(
        [
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a stored user password hash."""

    try:
        algorithm, iterations_raw, salt_raw, digest_raw = str(stored_hash or "").split(":", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_raw.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_raw.encode("ascii"))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def _entry_from_record(record: dict[str, object]) -> WebEntry:
    return WebEntry(
        product_id=_text(record.get(PRODUCT_ID_HEADER)),
        ean=_text(record.get(EAN_HEADER)),
        name=_text(record.get(NAME_HEADER)),
        type_name=_text(record.get(TYPE_HEADER)),
        model=_text(record.get(MODEL_HEADER)),
        color1=_text(record.get(COLOR1_HEADER)),
        color2=_text(record.get(COLOR2_HEADER)),
        color3=_text(record.get(COLOR3_HEADER)),
        extra=_text(record.get(EXTRA_HEADER)),
    )


def entry_to_payload(entry: WebEntry) -> dict[str, str]:
    """Return a browser-friendly dict for a workbook entry."""

    return {
        "product_id": entry.product_id,
        "ean": entry.ean,
        "name": entry.name,
        "type_name": entry.type_name,
        "model": entry.model,
        "color1": entry.color1,
        "color2": entry.color2,
        "color3": entry.color3,
        "extra": entry.extra,
        "label": entry.label,
    }


def load_web_data() -> dict[str, object]:
    """Load list values and entry records for the web UI."""

    lists = prepare_excel_lists()
    entries = [_entry_from_record(item) for item in lists.get(ENTRY_RECORDS_KEY, [])]
    return {
        "lists": {
            key: list(lists.get(sheet, []))
            for key, sheet in LIST_SHEETS.items()
        },
        "entries": [entry_to_payload(entry) for entry in entries],
        "file_index": file_index_status(start=True),
        "color_field_labels": dict(config.CONFIG.get(COLOR_FIELD_LABELS_KEY, {}) or {}),
        "ftp_enabled": bool(config.CONFIG.get(ft, True)),
    }


def _file_index_enabled() -> bool:
    return bool(config.CONFIG.get(LOCAL_FILE_INDEX_KEY, True))


def _get_file_index(*, start: bool = False) -> LocalFileIndex | None:
    global _FILE_INDEX
    global _FILE_INDEX_KEY
    global _FILE_INDEX_REFRESH_STARTED
    if not _file_index_enabled():
        return None
    root_dir = os.path.abspath(settings.l)
    index_path = os.path.abspath(os.path.join(settings.AC, "file_index.json"))
    active_store = data_store.get_active_store()
    cache_store = (
        active_store
        if getattr(active_store, "mode", "") == storage_settings.DATA_MODE_SQLITE
        else None
    )
    store_key = str(getattr(cache_store, "database_path", "")) if cache_store else ""
    key = (root_dir, index_path, getattr(active_store, "mode", ""), store_key)
    if _FILE_INDEX is None or _FILE_INDEX_KEY != key:
        index = LocalFileIndex(root_dir, index_path, cache_store=cache_store)
        index.load_cache()
        _FILE_INDEX = index
        _FILE_INDEX_KEY = key
        _FILE_INDEX_REFRESH_STARTED = False
    if start and _FILE_INDEX is not None and not _FILE_INDEX_REFRESH_STARTED:
        _FILE_INDEX.refresh_async()
        _FILE_INDEX_REFRESH_STARTED = True
    return _FILE_INDEX


def _parse_generated_at(value: object) -> tuple[str, float | None]:
    text = _text(value)
    if text.endswith("Z") and "T" in text:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return text, dt.timestamp()
        except ValueError:
            return text, None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return text, None
    iso = (
        datetime.fromtimestamp(number, timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    return iso, number


def file_index_status(*, start: bool = False) -> dict[str, object]:
    """Return web-friendly local file index status."""

    if not _file_index_enabled():
        return {"enabled": False, "state": "disabled", "label": "Indeks lokalny wylaczony."}
    index = _get_file_index(start=start)
    if index is None:
        return {"enabled": False, "state": "disabled", "label": "Indeks lokalny wylaczony."}
    status = index.get_status()
    generated_at, generated_ts = _parse_generated_at(status.get("generated_at"))
    age_seconds = int(time.time() - generated_ts) if generated_ts is not None else None
    state = str(status.get("state") or "idle")
    if state == "refreshing":
        label = "Indeksowanie lokalnych plikow..."
    elif generated_at:
        if generated_ts is not None:
            readable = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(generated_ts))
        else:
            readable = generated_at
        label = f"Indeks lokalny: {readable}"
    elif status.get("cache_loaded"):
        label = "Indeks lokalny: cache wczytany."
    else:
        label = "Indeks lokalny: brak snapshotu."
    return {
        "enabled": True,
        "state": state,
        "cache_loaded": bool(status.get("cache_loaded")),
        "has_snapshot": bool(status.get("has_snapshot")),
        "dirs_scanned": int(status.get("dirs_scanned") or 0),
        "products_scanned": int(status.get("products_scanned") or 0),
        "name_count": int(status.get("name_count") or 0),
        "generated_at": generated_at,
        "age_seconds": age_seconds,
        "error": str(status.get("error") or ""),
        "label": label,
    }


def refresh_file_index() -> dict[str, object]:
    """Start a background local file index refresh."""

    index = _get_file_index(start=False)
    if index is not None:
        index.refresh_async()
    return file_index_status()


def _history_path() -> Path:
    return Path(settings.AC) / WEB_HISTORY_PATH


def _load_history_records() -> list[dict[str, object]]:
    sqlite_store = _active_sqlite_store()
    if sqlite_store is not None:
        return sqlite_store.load_history()
    path = _history_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _save_history_records(records: list[dict[str, object]]) -> None:
    sqlite_store = _active_sqlite_store()
    if sqlite_store is not None:
        sqlite_store.save_history(records)
        return
    path = _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records[-2000:], indent=2, ensure_ascii=False), encoding="utf-8")


def record_history(
    *,
    username: str,
    action: str,
    ean: object = "",
    product_id: object = "",
    summary: str = "",
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    """Append a compact web history entry."""

    timestamp = time.time()
    record = {
        "id": f"{int(timestamp * 1000)}-{secrets.token_hex(4)}",
        "ts": timestamp,
        "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
        "user": _text(username) or "unknown",
        "action": _text(action),
        "ean": _text(ean) or "BRAK-EAN",
        "product_id": _text(product_id),
        "summary": _text(summary),
        "details": details or {},
    }
    records = _load_history_records()
    records.append(record)
    _save_history_records(records)
    return record


def _history_record_search_text(item: dict[str, object]) -> str:
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    entry = details.get("entry") if isinstance(details.get("entry"), dict) else {}
    pieces = [
        item.get("ean"),
        item.get("product_id"),
        item.get("summary"),
        item.get("action"),
        item.get("user"),
    ]
    pieces.extend(entry.values())
    return " ".join(_text(piece) for piece in pieces if _text(piece)).casefold()


def _history_timestamp_value(item: dict[str, object]) -> float:
    value = item.get("created_at") or item.get("ts")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        text = _text(value)
    if text.endswith("Z") and "T" in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def history_snapshot(
    *,
    user: str = "",
    limit: int = 200,
    query: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    """Return recent web history grouped by EAN."""

    user_filter = _text(user).lower()
    query_filter = _text(query).casefold()
    records = sorted(_load_history_records(), key=_history_timestamp_value, reverse=True)
    if user_filter:
        records = [item for item in records if _text(item.get("user")).lower() == user_filter]
    if query_filter:
        records = [item for item in records if query_filter in _history_record_search_text(item)]
    limit = max(1, min(1000, int(limit or 200)))
    records = records[:limit]
    grouped: dict[str, dict[str, object]] = {}
    for item in records:
        ean = _text(item.get("ean")) or "BRAK-EAN"
        group = grouped.setdefault(ean, {"ean": ean, "latest_ts": 0.0, "items": []})
        group["items"].append(item)
        group["latest_ts"] = max(
            float(group.get("latest_ts") or 0),
            _history_timestamp_value(item),
        )
    groups = sorted(grouped.values(), key=lambda item: float(item.get("latest_ts") or 0), reverse=True)
    page_size = max(1, min(50, int(page_size or 50)))
    page = max(1, int(page or 1))
    total_groups = len(groups)
    total_pages = max(1, (total_groups + page_size - 1) // page_size)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    groups_page = groups[start : start + page_size]
    users = sorted({_text(item.get("user")) for item in _load_history_records() if _text(item.get("user"))})
    return {
        "groups": groups_page,
        "users": users,
        "count": len(records),
        "total_groups": total_groups,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "query": _text(query),
    }


def _ftp_cache_dir(ean: object, cache_scope: object = "") -> str:
    safe_ean = sanitize_path_segment(ean) or "NO-EAN"
    safe_scope = sanitize_path_segment(cache_scope)
    if safe_scope:
        return os.path.join(settings.AC, "web_ftp_cache", safe_scope, safe_ean)
    return os.path.join(settings.AC, "web_ftp_cache", safe_ean)


def _ftp_cache_root() -> str:
    return os.path.join(settings.AC, "web_ftp_cache")


def cleanup_web_ftp_cache(
    *,
    max_age_seconds: int = WEB_FTP_CACHE_MAX_AGE_SECONDS,
    min_interval_seconds: int = WEB_FTP_CACHE_CLEAN_INTERVAL_SECONDS,
    force: bool = False,
) -> dict[str, object]:
    """Remove stale browser FTP preview cache files."""

    global _FTP_CACHE_LAST_CLEANUP
    now = time.time()
    if not force and now - _FTP_CACHE_LAST_CLEANUP < max(1, int(min_interval_seconds or 1)):
        return {"deleted_files": 0, "deleted_dirs": 0, "skipped": True, "errors": []}
    _FTP_CACHE_LAST_CLEANUP = now
    root = os.path.abspath(_ftp_cache_root())
    if not os.path.isdir(root):
        return {"deleted_files": 0, "deleted_dirs": 0, "skipped": False, "errors": []}

    cutoff = now - max(60, int(max_age_seconds or WEB_FTP_CACHE_MAX_AGE_SECONDS))
    deleted_files = 0
    deleted_dirs = 0
    errors: list[str] = []
    for current_root, dirs, files in os.walk(root, topdown=False):
        try:
            if os.path.commonpath([root, os.path.abspath(current_root)]) != root:
                continue
        except ValueError:
            continue
        for filename in files:
            path = os.path.join(current_root, filename)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    deleted_files += 1
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        for dirname in dirs:
            path = os.path.join(current_root, dirname)
            try:
                os.rmdir(path)
                deleted_dirs += 1
            except OSError:
                pass
    try:
        os.rmdir(root)
        deleted_dirs += 1
    except OSError:
        pass
    return {
        "deleted_files": deleted_files,
        "deleted_dirs": deleted_dirs,
        "skipped": False,
        "errors": errors,
    }


def _ftp_cache_filename(filename: object) -> str:
    basename = os.path.basename(_text(filename))
    parsed = parse_slot_filename(basename)
    if parsed and parsed.normalized_name:
        basename = parsed.normalized_name
    stem, ext = os.path.splitext(basename)
    safe_stem = sanitize_path_segment(stem) or "ftp_file"
    safe_ext = ext if ext and len(ext) <= 12 else ""
    return f"{safe_stem}{safe_ext}"


def _cached_ftp_previews(ean: object) -> tuple[dict[str, str], dict[str, str]]:
    """Return remote FTP filenames and cached local preview paths for an EAN."""

    if not ean or not bool(config.CONFIG.get(ft, True)):
        return {}, {}
    ftp = connect_ftp(config.CONFIG.get(H, {}))
    cache_dir = _ftp_cache_dir(ean)
    os.makedirs(cache_dir, exist_ok=True)
    try:
        remote_files = select_remote_files_for_ean(ean, list_remote_filenames(ftp))
        preview_paths: dict[str, str] = {}
        for prefix, filename in remote_files.items():
            target_path = os.path.join(cache_dir, _ftp_cache_filename(filename))
            _download_ftp_to_cache(ftp, filename, target_path)
            if os.path.isfile(target_path):
                preview_paths[prefix] = target_path
        return remote_files, preview_paths
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


def cache_ftp_preview(ean: object, filename: object, cache_scope: object = "") -> str:
    """Download one FTP file to the web preview cache and return the local path."""

    cleanup_web_ftp_cache()
    ean_text = _text(ean)
    filename_text = os.path.basename(_text(filename))
    if not ean_text or not filename_text:
        raise ValueError("Brakuje EAN albo nazwy pliku FTP.")
    parsed = parse_slot_filename(filename_text)
    if not parsed or _norm(parsed.ean) != _norm(ean_text):
        raise ValueError("Plik FTP nie pasuje do wybranego EAN.")
    cache_dir = _ftp_cache_dir(ean_text, cache_scope=cache_scope)
    os.makedirs(cache_dir, exist_ok=True)
    target_path = os.path.join(cache_dir, _ftp_cache_filename(filename_text))
    if os.path.isfile(target_path):
        return target_path
    ftp = connect_ftp(config.CONFIG.get(H, {}))
    try:
        _download_ftp_to_cache(ftp, filename_text, target_path)
        return target_path
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


def invalidate_ftp_preview_cache(
    ean: object,
    filenames: list[object] | set[object] | tuple[object, ...],
    cache_scope: object = "",
) -> dict[str, object]:
    """Remove cached FTP previews for remote files that were changed."""

    ean_text = _text(ean)
    if not ean_text:
        return {"deleted": 0, "errors": []}
    cache_dir = _ftp_cache_dir(ean_text, cache_scope=cache_scope)
    deleted = 0
    errors: list[str] = []
    for filename in filenames or []:
        filename_text = os.path.basename(_text(filename))
        if not filename_text:
            continue
        target_path = os.path.join(cache_dir, _ftp_cache_filename(filename_text))
        try:
            if os.path.isfile(target_path):
                os.remove(target_path)
                deleted += 1
        except OSError as exc:
            errors.append(f"{filename_text}: {exc}")
    return {"deleted": deleted, "errors": errors}


def _ftp_cache_lock(target_path: str) -> threading.Lock:
    key = os.path.abspath(target_path)
    with _FTP_CACHE_LOCKS_GUARD:
        lock = _FTP_CACHE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _FTP_CACHE_LOCKS[key] = lock
        return lock


def _download_ftp_to_cache(ftp, filename: str, target_path: str) -> str:
    """Download an FTP file into cache without racing concurrent web requests."""

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    lock = _ftp_cache_lock(target_path)
    with lock:
        if os.path.isfile(target_path):
            return target_path
        temp_path = f"{target_path}.{secrets.token_hex(8)}.download"
        try:
            with open(temp_path, "wb") as handle:
                ftp.retrbinary(f"RETR {filename}", handle.write)
            last_error: OSError | None = None
            for _attempt in range(5):
                try:
                    if os.path.isfile(target_path):
                        return target_path
                    os.replace(temp_path, target_path)
                    return target_path
                except OSError as exc:
                    last_error = exc
                    time.sleep(0.2)
            if os.path.isfile(target_path):
                return target_path
            if last_error is not None:
                raise last_error
            return target_path
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


def _dedupe(values: list[object], *, limit: int = 200) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = _text(value)
        if not text:
            continue
        key = text.upper()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def field_suggestions(field: str, payload: dict[str, object]) -> list[str]:
    """Return context-aware suggestions, with existing product data first."""

    lists = prepare_excel_lists()
    entries = [_entry_from_record(item) for item in lists.get(ENTRY_RECORDS_KEY, [])]
    name = _text(payload.get("name"))
    type_name = _text(payload.get("type_name"))
    model = _text(payload.get("model"))
    colors = [_text(payload.get("color1")), _text(payload.get("color2")), _text(payload.get("color3"))]
    extra = _text(payload.get("extra"))
    existing: list[object] = []

    def _entry_context(entry: WebEntry, *, through: str) -> bool:
        if through in {"type_name", "model", "color", "extra"} and name and not _matches_field(entry.name, name):
            return False
        if through in {"model", "color", "extra"} and type_name and not _matches_field(entry.type_name, type_name):
            return False
        if through in {"color", "extra"} and model and not _matches_field(entry.model, model):
            return False
        return True

    index = _get_file_index(start=True)
    if field == "name":
        if index is not None and index.has_snapshot():
            existing.extend(index.get_names())
        existing.extend(entry.name for entry in entries)
        workbook = lists.get(LIST_SHEETS["names"], [])
    elif field == "type_name":
        if index is not None and index.has_snapshot():
            indexed = index.get_types(name)
            if indexed:
                existing.extend(indexed)
        existing.extend(entry.type_name for entry in entries if _entry_context(entry, through="type_name"))
        workbook = lists.get(LIST_SHEETS["types"], [])
    elif field == "model":
        if index is not None and index.has_snapshot():
            indexed = index.get_models(name, type_name)
            if indexed:
                existing.extend(indexed)
        existing.extend(entry.model for entry in entries if _entry_context(entry, through="model"))
        workbook = lists.get(LIST_SHEETS["models"], [])
    elif field in {"color1", "color2", "color3"}:
        if index is not None and index.has_snapshot():
            indexed = index.get_colors(name, type_name, model)
            if indexed:
                for item in indexed:
                    existing.extend(str(item).replace("_", "-").split("-"))
        for entry in entries:
            if _entry_context(entry, through="color"):
                existing.extend([entry.color1, entry.color2, entry.color3])
        workbook = lists.get(LIST_SHEETS["colors"], [])
    elif field == "extra":
        if index is not None and index.has_snapshot():
            indexed = index.get_extras(name, type_name, model, colors)
            if indexed:
                existing.extend(indexed)
        existing.extend(entry.extra for entry in entries if _entry_context(entry, through="extra"))
        workbook = lists.get(LIST_SHEETS["extras"], [])
    else:
        workbook = []
    if field == "extra" and not extra:
        existing.insert(0, "NO-LED")
    return _dedupe([*existing, *list(workbook or [])])


def _public_user(user: dict[str, object]) -> dict[str, object]:
    now = time.time()
    lock_until = _float_user_value(user.get("login_locked_until"))
    manual_lock = bool(user.get("login_lock_manual", False))
    temporary_lock = lock_until > now
    locked = manual_lock or temporary_lock
    failed_at = _float_user_value(user.get("last_failed_login_at"))
    token_issued_at = _float_user_value(user.get("extension_token_issued_at"))
    token_last_used_at = _float_user_value(user.get("extension_token_last_used_at"))
    return {
        "username": _text(user.get("username")),
        "role": "admin" if _text(user.get("role")) == "admin" else "user",
        "enabled": bool(user.get("enabled", True)),
        "has_password": bool(_text(user.get("password_hash"))),
        "session_version": _int_user_value(user.get("session_version")),
        "extension_token_version": _int_user_value(user.get("extension_token_version")),
        "extension_token_issued_ts": token_issued_at,
        "extension_token_issued_at": _format_local_time(token_issued_at) if token_issued_at else "",
        "extension_token_last_used_ts": token_last_used_at,
        "extension_token_last_used_at": _format_local_time(token_last_used_at) if token_last_used_at else "",
        "locked": locked,
        "lock_manual": manual_lock,
        "lock_expires_ts": lock_until if temporary_lock else 0.0,
        "lock_expires_at": _format_local_time(lock_until) if temporary_lock else "",
        "lock_reason": _text(user.get("login_lock_reason")),
        "failed_login_count": _int_user_value(user.get("failed_login_count")),
        "last_failed_login_ts": failed_at,
        "last_failed_login_at": _format_local_time(failed_at) if failed_at else "",
        "last_failed_login_ip": _text(user.get("last_failed_login_ip")),
        "last_failed_login_user_agent": _text(user.get("last_failed_login_user_agent")),
    }


def _default_admin() -> dict[str, object]:
    return {
        "username": "admin",
        "role": "admin",
        "enabled": True,
        "password_hash": _hash_password("admin"),
        "session_version": 0,
        "extension_token_version": 0,
        "extension_token_issued_at": 0.0,
        "extension_token_last_used_at": 0.0,
        "failed_login_count": 0,
        "last_failed_login_at": 0.0,
        "last_failed_login_ip": "",
        "last_failed_login_user_agent": "",
        "login_locked_until": 0.0,
        "login_lock_manual": False,
        "login_lock_reason": "",
    }


def _int_user_value(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _float_user_value(value: object) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _format_local_time(timestamp: float) -> str:
    if not timestamp:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(timestamp)))


def _normalized_user_record(item: dict[str, object]) -> dict[str, object] | None:
    username = _text(item.get("username"))
    if not username:
        return None
    role = _text(item.get("role")) or "user"
    return {
        "username": username,
        "role": "admin" if role == "admin" else "user",
        "enabled": bool(item.get("enabled", True)),
        "password_hash": _text(item.get("password_hash"))
        or (_hash_password("admin") if username.lower() == "admin" else ""),
        "session_version": _int_user_value(item.get("session_version")),
        "extension_token_version": _int_user_value(item.get("extension_token_version")),
        "extension_token_issued_at": _float_user_value(item.get("extension_token_issued_at")),
        "extension_token_last_used_at": _float_user_value(item.get("extension_token_last_used_at")),
        "failed_login_count": _int_user_value(item.get("failed_login_count")),
        "last_failed_login_at": _float_user_value(item.get("last_failed_login_at")),
        "last_failed_login_ip": _text(item.get("last_failed_login_ip")),
        "last_failed_login_user_agent": _text(item.get("last_failed_login_user_agent"))[:200],
        "login_locked_until": _float_user_value(item.get("login_locked_until")),
        "login_lock_manual": bool(item.get("login_lock_manual", False)),
        "login_lock_reason": _text(item.get("login_lock_reason")),
    }


def _login_lock_active(user: dict[str, object], now: float | None = None) -> bool:
    now_value = time.time() if now is None else float(now)
    if bool(user.get("login_lock_manual", False)):
        return True
    return _float_user_value(user.get("login_locked_until")) > now_value


def _clear_login_state(user: dict[str, object]) -> None:
    user["failed_login_count"] = 0
    user["login_locked_until"] = 0.0
    user["login_lock_manual"] = False
    user["login_lock_reason"] = ""


def _bump_user_counter(user: dict[str, object], key: str) -> int:
    value = _int_user_value(user.get(key)) + 1
    user[key] = value
    return value


def load_user_records() -> list[dict[str, object]]:
    """Load full local web user records, including password hashes."""

    with _USERS_LOCK:
        sqlite_store = _active_sqlite_store()
        if sqlite_store is not None:
            data = sqlite_store.load_users()
            if not data:
                return [_default_admin()]
            users = []
            seen = set()
            for item in data:
                if not isinstance(item, dict):
                    continue
                user = _normalized_user_record(item)
                if not user or user["username"].lower() in seen:
                    continue
                users.append(user)
                seen.add(user["username"].lower())
            if not any(user["username"].lower() == "admin" for user in users):
                users.insert(0, _default_admin())
            return users
        path = Path(settings.AC) / WEB_USERS_PATH
        if not path.exists():
            return [_default_admin()]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return [_default_admin()]
        if not isinstance(data, list):
            return [_default_admin()]
        users = []
        seen = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            user = _normalized_user_record(item)
            if not user or user["username"].lower() in seen:
                continue
            users.append(user)
            seen.add(user["username"].lower())
        if not any(user["username"].lower() == "admin" for user in users):
            users.insert(0, _default_admin())
        return users


def load_users() -> list[dict[str, object]]:
    """Load public web user records for settings UI."""

    return [_public_user(user) for user in load_user_records()]


def save_users(users: list[dict[str, object]]) -> list[dict[str, object]]:
    """Persist local web user records."""

    with _USERS_LOCK:
        sqlite_store = _active_sqlite_store()
        if sqlite_store is not None:
            sqlite_store.save_users(users)
            return load_users()
        path = Path(settings.AC) / WEB_USERS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(users, indent=4, ensure_ascii=False), encoding="utf-8")
        return load_users()


def authenticate_user(username: str, password: str) -> dict[str, object] | None:
    """Return a public user record when credentials are valid."""

    normalized = _text(username).lower()
    with _USERS_LOCK:
        for user in load_user_records():
            if _text(user.get("username")).lower() != normalized:
                continue
            if not bool(user.get("enabled", True)) or _login_lock_active(user):
                return None
            if verify_password(password, _text(user.get("password_hash"))):
                return _public_user(user)
    return None


def authenticate_login(
    username: str,
    password: str,
    *,
    remote_address: str = "",
    user_agent: str = "",
) -> dict[str, object]:
    """Authenticate a login attempt and update lockout state."""

    normalized = _text(username).lower()
    now = time.time()
    with _USERS_LOCK:
        users = load_user_records()
        matched: dict[str, object] | None = None
        for user in users:
            if _text(user.get("username")).lower() == normalized:
                matched = user
                break
        if matched is None:
            return {
                "ok": False,
                "known": False,
                "reason": "unknown_user",
                "failed_login_count": 0,
            }
        if not bool(matched.get("enabled", True)):
            return {
                "ok": False,
                "known": True,
                "reason": "disabled",
                "user": _public_user(matched),
            }
        expired_lock_cleared = False
        if (
            not bool(matched.get("login_lock_manual", False))
            and _float_user_value(matched.get("login_locked_until"))
            and _float_user_value(matched.get("login_locked_until")) <= now
        ):
            _clear_login_state(matched)
            expired_lock_cleared = True
        if _login_lock_active(matched, now):
            return {
                "ok": False,
                "known": True,
                "reason": "locked",
                "user": _public_user(matched),
            }
        if verify_password(password, _text(matched.get("password_hash"))):
            had_failed_state = bool(_int_user_value(matched.get("failed_login_count"))) or bool(
                matched.get("login_lock_reason")
            )
            if had_failed_state or expired_lock_cleared:
                _clear_login_state(matched)
                save_users(users)
            return {
                "ok": True,
                "known": True,
                "reason": "ok",
                "user": _public_user(matched),
            }

        failed_count = _int_user_value(matched.get("failed_login_count")) + 1
        matched["failed_login_count"] = failed_count
        matched["last_failed_login_at"] = now
        matched["last_failed_login_ip"] = _text(remote_address)
        matched["last_failed_login_user_agent"] = _text(user_agent)[:200]
        just_locked = False
        if failed_count >= LOGIN_FAILURE_LIMIT:
            just_locked = True
            if _text(matched.get("role")) == "admin":
                matched["login_lock_manual"] = True
                matched["login_locked_until"] = 0.0
                matched["login_lock_reason"] = "admin_failed_logins_manual_unlock"
            else:
                matched["login_lock_manual"] = False
                matched["login_locked_until"] = now + LOGIN_LOCK_SECONDS
                matched["login_lock_reason"] = "failed_logins_temporary_lock"
        save_users(users)
        return {
            "ok": False,
            "known": True,
            "reason": "locked" if just_locked else "bad_password",
            "just_locked": just_locked,
            "failed_login_count": failed_count,
            "limit": LOGIN_FAILURE_LIMIT,
            "user": _public_user(matched),
        }


def find_user(username: str) -> dict[str, object] | None:
    """Return a public user by username."""

    normalized = _text(username).lower()
    for user in load_user_records():
        if _text(user.get("username")).lower() == normalized:
            return _public_user(user)
    return None


def add_user(username: str, password: str, role: str = "user") -> list[dict[str, object]]:
    """Add a web user account."""

    username = _text(username)
    if not username:
        raise ValueError("Nazwa uzytkownika nie moze byc pusta.")
    if not _text(password):
        raise ValueError("Haslo uzytkownika nie moze byc puste.")
    users = load_user_records()
    if any(user["username"].lower() == username.lower() for user in users):
        raise ValueError("Taki uzytkownik juz istnieje.")
    users.append(
        {
            "username": username,
            "role": "admin" if _text(role) == "admin" else "user",
            "enabled": True,
            "password_hash": _hash_password(password),
            "session_version": 0,
            "extension_token_version": 0,
            "extension_token_issued_at": 0.0,
            "extension_token_last_used_at": 0.0,
            "failed_login_count": 0,
            "last_failed_login_at": 0.0,
            "last_failed_login_ip": "",
            "last_failed_login_user_agent": "",
            "login_locked_until": 0.0,
            "login_lock_manual": False,
            "login_lock_reason": "",
        }
    )
    return save_users(users)


def update_user(
    username: str,
    *,
    enabled: bool | None = None,
    role: str | None = None,
    password: str | None = None,
    unlock: bool | None = None,
    revoke_sessions: bool | None = None,
    revoke_extension_token: bool | None = None,
    current_username: str = "",
) -> list[dict[str, object]]:
    """Update a web user account."""

    users = load_user_records()
    for user in users:
        if user["username"].lower() != _text(username).lower():
            continue
        if enabled is not None:
            if _text(current_username).lower() == _text(username).lower() and not bool(enabled):
                raise ValueError("Nie mozna wylaczyc konta, na ktorym jestes zalogowany.")
            user["enabled"] = bool(enabled)
        if role is not None:
            user["role"] = "admin" if _text(role) == "admin" else "user"
        if password is not None and _text(password):
            user["password_hash"] = _hash_password(password)
            _bump_user_counter(user, "session_version")
            _bump_user_counter(user, "extension_token_version")
        if unlock:
            _clear_login_state(user)
        if revoke_sessions:
            _bump_user_counter(user, "session_version")
        if revoke_extension_token:
            _bump_user_counter(user, "extension_token_version")
        return save_users(users)
    raise ValueError("Nie znaleziono uzytkownika.")


def unlock_user(username: str) -> list[dict[str, object]]:
    """Clear login lockout state for a web user account."""

    return update_user(username, unlock=True)


def mark_browser_extension_token_issued(username: str) -> dict[str, object] | None:
    """Store token issue time for the current browser extension token version."""

    normalized = _text(username).lower()
    with _USERS_LOCK:
        users = load_user_records()
        for user in users:
            if _text(user.get("username")).lower() != normalized:
                continue
            user["extension_token_issued_at"] = time.time()
            save_users(users)
            return _public_user(user)
    return None


def mark_browser_extension_token_used(username: str, version: int) -> dict[str, object] | None:
    """Store last-use time when an extension token matches the active version."""

    normalized = _text(username).lower()
    with _USERS_LOCK:
        users = load_user_records()
        for user in users:
            if _text(user.get("username")).lower() != normalized:
                continue
            if _int_user_value(user.get("extension_token_version")) != int(version):
                return None
            user["extension_token_last_used_at"] = time.time()
            save_users(users)
            return _public_user(user)
    return None


def _matches_field(entry_value: str, expected: str) -> bool:
    expected_norm = _norm(expected)
    if not expected_norm:
        return True
    return _norm(entry_value) == expected_norm


def search_entries(
    *,
    ean: str = "",
    product_id: str = "",
    name: str = "",
    type_name: str = "",
    model: str = "",
    query: str = "",
    limit: int = 30,
) -> list[dict[str, str]]:
    """Search saved product entries by EAN, product id or form fields."""

    entries = [_entry_from_record(item) for item in prepare_excel_lists().get(ENTRY_RECORDS_KEY, [])]
    ean_norm = _norm(ean)
    product_id_norm = _norm(product_id)
    query_norm = _norm(query)
    matches: list[WebEntry] = []
    for entry in entries:
        if product_id_norm and _norm(entry.product_id) != product_id_norm:
            continue
        if ean_norm and _norm(entry.ean) != ean_norm:
            continue
        if not _matches_field(entry.name, name):
            continue
        if not _matches_field(entry.type_name, type_name):
            continue
        if not _matches_field(entry.model, model):
            continue
        if query_norm:
            haystack = _norm(
                " ".join(
                    [
                        entry.product_id,
                        entry.ean,
                        entry.name,
                        entry.type_name,
                        entry.model,
                        entry.color1,
                        entry.color2,
                        entry.color3,
                        entry.extra,
                    ]
                )
            )
            if query_norm not in haystack:
                continue
        matches.append(entry)
        if len(matches) >= limit:
            break
    return [entry_to_payload(entry) for entry in matches]


def find_entry_by_identity(*, product_id: str = "", ean: str = "") -> dict[str, str] | None:
    """Return one saved entry by product id or EAN."""

    if _text(product_id):
        matches = search_entries(product_id=product_id, limit=1)
        if matches:
            return matches[0]
    if _text(ean) and _text(ean).upper() != NO_EAN_PLACEHOLDER:
        matches = search_entries(ean=ean, limit=1)
        if matches:
            return matches[0]
    return None


def save_web_entry(payload: dict[str, object]) -> dict[str, object]:
    """Create or update an Excel entry using the existing desktop helper."""

    product_id = _text(payload.get("product_id"))
    ean = _text(payload.get("ean"))
    existing = find_entry_by_identity(product_id=product_id) if product_id else None
    if existing is None and ean and ean.upper() != NO_EAN_PLACEHOLDER:
        existing = find_entry_by_identity(ean=ean)
    if existing:
        product_id = product_id or _text(existing.get("product_id"))
        if not ean and _text(existing.get("ean")):
            ean = _text(existing.get("ean"))
    result = save_ean_entry(
        ean or NO_EAN_PLACEHOLDER,
        _text(payload.get("name")),
        _text(payload.get("type_name")),
        _text(payload.get("model")),
        _text(payload.get("color1")),
        _text(payload.get("color2")),
        _text(payload.get("color3")),
        _text(payload.get("extra")),
        product_id=product_id,
    )
    if not result:
        raise ValueError("Nie udalo sie zapisac wpisu w Excelu.")
    return result


def add_list_value(list_key: str, value: str) -> dict[str, object]:
    """Add a value to one of the editable Excel list sheets."""

    sheet = LIST_SHEETS.get(list_key)
    if not sheet:
        raise ValueError("Nieznana lista.")
    if not _text(value):
        raise ValueError("Wartosc nie moze byc pusta.")
    lists = prepare_excel_lists()
    normalized = _list_value_key(value)
    if normalized and any(_list_value_key(item) == normalized for item in lists.get(sheet, [])):
        raise ValueError("Taka wartosc juz istnieje na liscie.")
    if not add_to_list(sheet, value):
        raise ValueError("Nie udalo sie dodac wartosci do listy.")
    return load_web_data()


def remove_list_value(list_key: str, value: str) -> dict[str, object]:
    """Remove a value from one of the editable Excel list sheets."""

    sheet = LIST_SHEETS.get(list_key)
    if not sheet:
        raise ValueError("Nieznana lista.")
    used_by = find_list_value_usage(sheet, value)
    if used_by:
        raise ListValueInUseError(list_key, value, used_by)
    remove_from_list(sheet, value)
    return load_web_data()


def is_windows_admin_process() -> bool:
    """Return True when the backend process is already elevated."""

    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _local_settings_path() -> Path:
    return Path(settings.BASE_DIR_SETTINGS_PATH)


def _normalize_base_dir(value: object) -> str:
    text = _text(value).strip("\"'")
    if not text:
        return ""
    expanded = os.path.expandvars(os.path.expanduser(text))
    return os.path.abspath(expanded)


def _same_path(left: object, right: object) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
            os.path.abspath(str(right))
        )
    except Exception:
        return str(left or "") == str(right or "")


def _ensure_base_dir_web_access(path: str) -> None:
    ok, error = settings._ensure_directory_access(path)
    if not ok:
        details = f" Szczegoly: {error}" if error else ""
        raise ValueError(f"Nie mozna uzyc katalogu bazowego: {path}.{details}")
    try:
        fd, probe_path = tempfile.mkstemp(
            prefix="picorg_base_dir_check_",
            suffix=".tmp",
            dir=path,
        )
        os.close(fd)
        os.remove(probe_path)
    except OSError as exc:
        raise ValueError(f"Brak zapisu w katalogu bazowym: {path}. Szczegoly: {exc}") from exc


def _load_local_settings() -> dict[str, object]:
    path = _local_settings_path()
    if not path.exists():
        return dict(common.BASE_DIR_SETTINGS_TEMPLATE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(common.BASE_DIR_SETTINGS_TEMPLATE)
    return data if isinstance(data, dict) else dict(common.BASE_DIR_SETTINGS_TEMPLATE)


def _save_local_settings(payload: dict[str, object]) -> None:
    path = _local_settings_path()
    existing = _load_local_settings()
    existing.update(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix="local_settings_",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(existing, handle, indent=4, ensure_ascii=False)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _apply_base_dir_from_web(value: object) -> bool:
    requested = _normalize_base_dir(value)
    if not requested:
        return False
    _ensure_base_dir_web_access(requested)
    previous = settings.AC
    _save_local_settings({"base_dir_override": requested})
    settings.initialize_runtime(interactive=False)
    if not _same_path(settings.AC, requested):
        warning = settings.BASE_DIR_OVERRIDE_WARNING or "runtime pozostal przy poprzednim katalogu"
        raise ValueError(
            "Zapisano local_settings.json, ale backend nie przelaczyl sie na nowy "
            f"katalog. Wybrany: {requested}. Aktywny: {settings.AC}. {warning}"
        )
    return not _same_path(previous, settings.AC)


def _apply_app_secret_from_web(value: object) -> bool:
    secret = _text(value)
    if not secret:
        return False
    _save_local_settings({APP_SECRET_KEY: common._encode_local_secret(secret)})
    if secret == common.APP_SECRET:
        return False
    common.APP_SECRET = secret
    common.BASE_DIR_SETTINGS_TEMPLATE[APP_SECRET_KEY] = common._encode_local_secret(secret)
    encryption.APP_SECRET = secret
    return True


def _preserve_unsubmitted_config_secrets(payload: dict[str, object]) -> dict[str, set[str]]:
    preserve = {section: set(keys) for section, keys in _CONFIG_SECRET_FIELDS.items()}
    ftp_payload = payload.get("ftp") if isinstance(payload.get("ftp"), dict) else {}
    if _text(ftp_payload.get("user")):
        preserve[H].discard(N)
    if _text(ftp_payload.get("password")):
        preserve[H].discard(M)

    db_payload = payload.get("database") if isinstance(payload.get("database"), dict) else {}
    for section_key, section_name in ((P, "mssql"), (K, "mysql")):
        section_payload = db_payload.get(section_name)
        if not isinstance(section_payload, dict):
            continue
        if _text(section_payload.get("user")):
            preserve[section_key].discard(N)
        if _text(section_payload.get("password")):
            preserve[section_key].discard(M)
    return {section: keys for section, keys in preserve.items() if keys}


def update_settings(payload: dict[str, object]) -> dict[str, object]:
    """Update editable settings from the web UI."""

    app_payload = payload.get("app") if isinstance(payload.get("app"), dict) else {}
    ftp_payload = payload.get("ftp") if isinstance(payload.get("ftp"), dict) else {}
    db_payload = payload.get("database") if isinstance(payload.get("database"), dict) else {}
    processing_payload = payload.get("processing") if isinstance(payload.get("processing"), dict) else {}
    security_payload = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    backup_payload = payload.get("sqlite_backup") if isinstance(payload.get("sqlite_backup"), dict) else None
    slots_payload = payload.get("slots") if isinstance(payload.get("slots"), list) else None
    runtime_reloaded = False

    if "image_dir" in app_payload:
        runtime_reloaded = _apply_base_dir_from_web(app_payload.get("image_dir")) or runtime_reloaded
    elif "base_dir" in app_payload:
        runtime_reloaded = _apply_base_dir_from_web(app_payload.get("base_dir")) or runtime_reloaded
    storage_updates: dict[str, object] = {}
    for payload_key, settings_key in {
        "data_mode": storage_settings.DATA_MODE_KEY,
        "database_location_mode": storage_settings.DATABASE_LOCATION_MODE_KEY,
        "database_path": storage_settings.DATABASE_PATH_KEY,
    }.items():
        if payload_key in app_payload:
            storage_updates[settings_key] = app_payload.get(payload_key)
    if storage_updates:
        storage_settings.save_bootstrap_settings(storage_updates)
        data_store.reset_active_store_cache()
        runtime_reloaded = True
    if backup_payload is not None:
        storage_settings.save_backup_settings(backup_payload)
    if APP_SECRET_KEY in security_payload:
        runtime_reloaded = _apply_app_secret_from_web(security_payload.get(APP_SECRET_KEY)) or runtime_reloaded
    elif APP_SECRET_KEY in app_payload:
        runtime_reloaded = _apply_app_secret_from_web(app_payload.get(APP_SECRET_KEY)) or runtime_reloaded
    if runtime_reloaded:
        config.initialize_config(interactive=False)
    cfg = config.CONFIG

    if LOCAL_FILE_INDEX_KEY in app_payload:
        cfg[LOCAL_FILE_INDEX_KEY] = bool(app_payload.get(LOCAL_FILE_INDEX_KEY))
    if AUTO_CONTENT_FIT_KEY in app_payload:
        cfg[AUTO_CONTENT_FIT_KEY] = bool(app_payload.get(AUTO_CONTENT_FIT_KEY))
    if COLOR_FIELD_LABELS_KEY in app_payload and isinstance(
        app_payload.get(COLOR_FIELD_LABELS_KEY), dict
    ):
        cfg[COLOR_FIELD_LABELS_KEY] = {
            key: _text(value)
            for key, value in app_payload[COLOR_FIELD_LABELS_KEY].items()
            if key in {"color1", "color2", "color3"} and _text(value)
        }

    if processing_payload:
        merged_processing = dict(cfg.get(PROCESSING_SETTINGS_KEY, {}) or {})
        merged_processing.update(processing_payload)
        cfg[PROCESSING_SETTINGS_KEY] = config._normalize_processing_settings(merged_processing)

    if security_payload:
        merged_security = dict(cfg.get(SECURITY_SETTINGS_KEY, {}) or {})
        merged_security.update(security_payload)
        cfg[SECURITY_SETTINGS_KEY] = config._normalize_security_settings(merged_security)

    if ftp_payload:
        ftp = cfg.setdefault(H, {})
        for key, cfg_key in {
            "host": v,
            "path": m,
            "user": N,
            "password": M,
        }.items():
            if key in ftp_payload:
                value = _text(ftp_payload.get(key))
                if key in {"user", "password"} and not value:
                    continue
                ftp[cfg_key] = value
        if "port" in ftp_payload:
            try:
                ftp[r] = int(ftp_payload.get("port") or 21)
            except ValueError:
                ftp[r] = 21
        if "enabled" in ftp_payload:
            cfg[ft] = bool(ftp_payload.get("enabled"))

    if db_payload:
        db_type = _text(db_payload.get("type")).lower()
        if db_type in {"mysql", "mssql"}:
            cfg[p] = K if db_type == "mysql" else "mssql"
        if "sql_update_enabled" in db_payload:
            cfg[u] = bool(db_payload.get("sql_update_enabled"))
        if "query" in db_payload:
            cfg[w] = _text(db_payload.get("query"))
        for section_key, section_name in ((P, "mssql"), (K, "mysql")):
            section_payload = db_payload.get(section_name)
            if not isinstance(section_payload, dict):
                continue
            section = cfg.setdefault(section_key, {})
            for key, cfg_key in {
                "server": c,
                "database": b,
                "user": N,
                "password": M,
            }.items():
                if key in section_payload:
                    value = _text(section_payload.get(key))
                    if key in {"user", "password"} and not value:
                        continue
                    section[cfg_key] = value

    if slots_payload is not None:
        slot_defs, _slot_issues = normalize_slot_definitions(slots_payload)
        submitted_map = {
            _text(slot.get("prefix")): _text(slot.get("sql_column"))
            for slot in slots_payload
            if isinstance(slot, dict) and _text(slot.get("prefix"))
        }
        merged_map = dict(cfg.get(SQL_COLUMN_MAP_KEY, {}) or {})
        merged_map.update({key: value for key, value in submitted_map.items() if value})
        sql_map, _map_issues = normalize_sql_column_map(merged_map, slot_defs)
        cfg[SLOT_DEFS_KEY] = slot_defs
        cfg[SQL_COLUMN_MAP_KEY] = sql_map

    save_config(cfg, preserve_secrets=_preserve_unsubmitted_config_secrets(payload))
    config.initialize_config(interactive=False)
    return settings_snapshot()


def settings_snapshot() -> dict[str, object]:
    """Return non-secret settings for the web settings view."""

    cfg = config.CONFIG
    storage = storage_settings.storage_summary()
    ftp = cfg.get(H, {})
    sql = cfg.get(P, {})
    mysql_cfg = cfg.get(K, {})
    slot_defs = cfg.get(SLOT_DEFS_KEY, []) or []
    sql_map = cfg.get(SQL_COLUMN_MAP_KEY, {}) or {}
    return {
        "version": get_display_version(),
        "windows_admin": is_windows_admin_process(),
        "base_dir": settings.AC,
        "image_dir": storage.get("image_dir", settings.AC),
        "data_mode": storage.get("data_mode", "legacy"),
        "database_location_mode": storage.get("database_location_mode", "image_dir"),
        "database_path": storage.get("database_path", ""),
        "sqlite_backup": storage_settings.load_backup_settings(),
        "sqlite_backup_dir": storage_settings.resolve_backup_dir(),
        "processed_dir": settings.l,
        "config_path": config.CONFIG_PATH,
        "local_settings_path": str(_local_settings_path()),
        "runtime_warning": settings.BASE_DIR_OVERRIDE_WARNING,
        "auth_enabled": True,
        "users": load_users(),
        "app_secret_set": bool(_text(common.APP_SECRET)),
        "local_file_index": bool(cfg.get(LOCAL_FILE_INDEX_KEY, True)),
        "auto_content_fit": bool(cfg.get(AUTO_CONTENT_FIT_KEY, False)),
        "processing": config._normalize_processing_settings(
            cfg.get(PROCESSING_SETTINGS_KEY, {})
        ),
        "security": config._normalize_security_settings(
            cfg.get(SECURITY_SETTINGS_KEY, {})
        ),
        "processing_formats": available_convert_formats(),
        "ftp": {
            "host": _text(ftp.get(v)),
            "port": ftp.get(r),
            "path": _text(ftp.get(m)),
            "user_set": bool(_text(ftp.get(N))),
            "password_set": bool(_text(ftp.get(M))),
            "enabled": bool(cfg.get(ft, True)),
        },
        "database": {
            "type": _text(cfg.get(p)),
            "sql_update_enabled": bool(cfg.get(u, True)),
            "query": _text(cfg.get(w)),
            "mssql": {
                "server": _text(sql.get(c)),
                "database": _text(sql.get(b)),
                "user_set": bool(_text(sql.get(N))),
                "password_set": bool(_text(sql.get(M))),
            },
            "mysql": {
                "server": _text(mysql_cfg.get(c)),
                "database": _text(mysql_cfg.get(b)),
                "user_set": bool(_text(mysql_cfg.get(N))),
                "password_set": bool(_text(mysql_cfg.get(M))),
            },
        },
        "slot_count": len(slot_defs),
        "sql_map_count": len(sql_map),
        "sql_available_columns_count": len(cfg.get(SQL_AVAILABLE_COLUMNS_KEY, []) or []),
        "sql_available_columns": cfg.get(SQL_AVAILABLE_COLUMNS_KEY, []) or [],
        "color_field_labels": cfg.get(COLOR_FIELD_LABELS_KEY, {}) or {},
        "slots": [
            {
                "prefix": slot.get("prefix", ""),
                "label": slot.get("label", ""),
                "filename_label": slot.get("filename_label", slot.get("label", "")),
                "filename_label_explicit": bool(slot.get("filename_label")),
                "sql_column": sql_map.get(slot.get("prefix", ""), ""),
            }
            for slot in slot_defs
        ],
    }


def settings_secret_values() -> dict[str, object]:
    """Return decrypted settings secrets for the explicit admin reveal action."""

    cfg = config.CONFIG
    ftp = cfg.get(H, {}) if isinstance(cfg.get(H), dict) else {}
    mssql_cfg = cfg.get(P, {}) if isinstance(cfg.get(P), dict) else {}
    mysql_cfg = cfg.get(K, {}) if isinstance(cfg.get(K), dict) else {}
    return {
        "app_secret": _text(common.APP_SECRET),
        "ftp": {
            "user": _text(ftp.get(N)),
            "password": _text(ftp.get(M)),
        },
        "database": {
            "mssql": {
                "user": _text(mssql_cfg.get(N)),
                "password": _text(mssql_cfg.get(M)),
            },
            "mysql": {
                "user": _text(mysql_cfg.get(N)),
                "password": _text(mysql_cfg.get(M)),
            },
        },
    }


def test_local_paths() -> dict[str, object]:
    """Check backend access to local working folders."""

    targets = {
        "base_dir": settings.AC,
        "processed_dir": settings.l,
        "config_dir": os.path.dirname(config.CONFIG_PATH),
    }
    checks = []
    for key, path in targets.items():
        check = {"key": key, "path": path, "exists": os.path.isdir(path), "read": False, "write": False, "error": ""}
        try:
            os.makedirs(path, exist_ok=True)
            os.listdir(path)
            check["exists"] = True
            check["read"] = True
            fd, temp_path = tempfile.mkstemp(prefix="picorg_web_check_", suffix=".tmp", dir=path)
            os.close(fd)
            os.remove(temp_path)
            check["write"] = True
        except Exception as exc:
            check["error"] = str(exc)
        checks.append(check)
    return {"ok": all(item["read"] and item["write"] for item in checks), "checks": checks}


def test_ftp_connection() -> dict[str, object]:
    """Check FTP connectivity using current config."""

    if not bool(config.CONFIG.get(ft, True)):
        return {"ok": False, "message": "Aktualizacja FTP jest wylaczona."}
    try:
        files = list_remote_files_for_ean(config.CONFIG.get(H, {}), "")
        return {"ok": True, "message": "Polaczenie FTP dziala.", "sample_count": len(files)}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def test_sql_connection() -> dict[str, object]:
    """Check database connectivity using current config."""

    try:
        conn = connect_db()
        try:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return {"ok": True, "message": "Polaczenie SQL dziala."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def find_product_photos(
    entry_payload: dict[str, object],
    *,
    include_local: bool = True,
    include_ftp: bool = True,
    include_sql: bool = True,
) -> list[dict[str, object]]:
    """Find processed photos and presence flags for a saved web entry."""

    entry = _entry_from_record(
        {
            PRODUCT_ID_HEADER: entry_payload.get("product_id"),
            EAN_HEADER: entry_payload.get("ean"),
            NAME_HEADER: entry_payload.get("name"),
            TYPE_HEADER: entry_payload.get("type_name"),
            MODEL_HEADER: entry_payload.get("model"),
            COLOR1_HEADER: entry_payload.get("color1"),
            COLOR2_HEADER: entry_payload.get("color2"),
            COLOR3_HEADER: entry_payload.get("color3"),
            EXTRA_HEADER: entry_payload.get("extra"),
        }
    )
    product_dir = build_product_directory(
        settings.l,
        entry.name,
        entry.type_name,
        entry.model,
        [entry.color1, entry.color2, entry.color3],
        entry.extra,
    )
    target_ean = _norm(entry.ean)
    results_by_prefix: dict[str, dict[str, object]] = {}
    file_names: list[str] = []
    if include_local:
        seen_files = set()
        index = _get_file_index(start=True)
        if index is not None and index.has_snapshot():
            indexed = index.get_product_files(
                entry.name,
                entry.type_name,
                entry.model,
                [entry.color1, entry.color2, entry.color3],
                entry.extra,
            )
            if indexed is not None:
                for filename in indexed:
                    if filename not in seen_files:
                        file_names.append(filename)
                        seen_files.add(filename)
        if os.path.isdir(product_dir):
            for filename in os.listdir(product_dir):
                if filename not in seen_files:
                    file_names.append(filename)
                    seen_files.add(filename)
    if include_local and file_names:
        for filename in file_names:
            path = os.path.join(product_dir, filename)
            if not os.path.isfile(path):
                continue
            parsed = parse_slot_filename(filename)
            if not parsed:
                continue
            if target_ean and _norm(parsed.ean) != target_ean:
                continue
            ext = os.path.splitext(filename)[1].lower()
            results_by_prefix[parsed.normalized_label] = {
                "ean": entry.ean,
                "prefix": parsed.normalized_label,
                "filename": filename,
                "path": path,
                "is_image": ext in IMAGE_PREVIEW_EXTENSIONS,
                "local": True,
                "ftp": False,
                "sql": False,
                "ftp_path": "",
                "ftp_filename": "",
                "sql_value": "",
                "sql_checked": False,
            }
    ean = entry.ean
    if include_ftp and ean and bool(config.CONFIG.get(ft, True)):
        try:
            remote = list_remote_files_for_ean(config.CONFIG.get(H, {}), ean)
            for prefix, filename in remote.items():
                item = results_by_prefix.setdefault(
                    prefix,
                    {
                        "ean": entry.ean,
                        "prefix": prefix,
                        "filename": "",
                        "path": "",
                        "is_image": False,
                        "local": False,
                        "sql": False,
                        "sql_value": "",
                        "sql_checked": False,
                    },
                )
                item["ftp"] = True
                item["ean"] = entry.ean
                item["ftp_filename"] = filename
                item["ftp_path"] = ""
                ext = os.path.splitext(filename)[1].lower()
                item["is_image"] = bool(item.get("is_image")) or ext in IMAGE_PREVIEW_EXTENSIONS
        except Exception:
            pass
    if include_sql and ean and should_check_presence(config.CONFIG):
        try:
            context = extract_presence_context(config.CONFIG, ean)
            if context:
                table, where_clause = context
                slots = config.CONFIG.get(SLOT_DEFS_KEY, []) or []
                sql_map = config.CONFIG.get(SQL_COLUMN_MAP_KEY, {}) or {}
                columns = [
                    (slot.get("prefix", ""), sql_map.get(slot.get("prefix", ""), ""), slot.get("label", ""))
                    for slot in slots
                    if sql_map.get(slot.get("prefix", ""), "")
                ]
                presence, values = query_presence_details(
                    columns,
                    table,
                    where_clause,
                    config.CONFIG.get(p, K),
                )
                for prefix, present in presence.items():
                    if present is None:
                        continue
                    item = results_by_prefix.setdefault(
                        prefix,
                        {
                            "ean": entry.ean,
                            "prefix": prefix,
                            "filename": "",
                            "path": "",
                            "is_image": False,
                            "local": False,
                            "ftp": False,
                            "ftp_path": "",
                            "ftp_filename": "",
                            "sql_checked": False,
                        },
                    )
                    if not present and not (item.get("local") or item.get("ftp")):
                        results_by_prefix.pop(prefix, None)
                        continue
                    item["sql"] = bool(present)
                    item["sql_checked"] = True
                    item["ean"] = entry.ean
                    item["sql_value"] = values.get(prefix, "")
        except Exception:
            pass
    return sorted(results_by_prefix.values(), key=lambda item: str(item.get("prefix", "")))
