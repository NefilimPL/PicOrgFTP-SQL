"""FastAPI LAN backend for the browser upload panel."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import unicodedata
import warnings
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlsplit
import zipfile

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from .. import common, config, data_store, settings, sqlite_backup, storage_settings
from ..bootstrap import initialize_application_runtime
from ..common import (
    AUTO_CONTENT_FIT_KEY,
    COLOR_FIELD_LABELS_KEY,
    H,
    K,
    M,
    N,
    P,
    PROCESSING_SETTINGS_KEY,
    SECURITY_SETTINGS_KEY,
    SQL_AVAILABLE_COLUMNS_KEY,
    SQL_COLUMN_MAP_KEY,
    TRANSLATION_API_KEY,
    TRANSLATION_SETTINGS_KEY,
    ft,
    p,
    u,
    w,
)
from ..database import connect_db
from ..image_utils import fit_image_to_content
from ..legacy_import import import_legacy_to_sqlite
from ..logging_utils import log_error
from ..product_fields import PRODUCT_FIELDS_KEY, normalize_product_fields
from ..pimcore_templates import TemplateError
from ..services.ftp_service import sync_remote_files
from ..services.pimcore_service import PimcoreApiError, PimcoreConflictError
from ..services.sql_service import detect_available_columns, extract_presence_context
from ..sqlite_maintenance import repair_sqlite_database
from ..workflow_utils import build_product_directory, parse_slot_filename, sanitize_path_segment
from ..web_image_import import (
    ImageImportError,
    discover_image_candidates,
    download_image_bytes,
    fetch_page_html,
    filename_from_url,
)
from ..web_workflow import (
    WebProductForm,
    WebUploadedSlot,
    effective_product_form,
    preprocess_cached_upload,
    process_web_uploads,
    normalized_product_payload,
    processing_options_from_config,
    slot_definitions_from_config,
    validate_product_form,
)
from ..web_data import (
    add_list_value,
    add_user,
    authenticate_login,
    authenticate_user,
    cache_ftp_preview,
    cleanup_web_ftp_cache,
    complete_pimcore_setup,
    discover_pimcore_classes,
    discover_pimcore_fields,
    discover_pimcore_folders,
    field_suggestions,
    find_entry_by_identity,
    find_pimcore_product_by_ean,
    find_user,
    find_product_photos,
    file_index_status,
    get_pimcore_product_for_edit,
    invalidate_ftp_preview_cache,
    load_web_data,
    load_users,
    mark_browser_extension_token_issued,
    mark_browser_extension_token_used,
    history_snapshot,
    ListValueInUseError,
    parse_pimcore_csv_headers,
    pimcore_test_sample,
    pimcore_operation_history,
    pimcore_operation_status,
    pimcore_runtime_capabilities,
    refresh_file_index,
    render_saved_pimcore_templates,
    remove_list_value,
    record_history,
    save_web_entry,
    search_entries,
    create_pimcore_product,
    preview_pimcore_template,
    settings_snapshot,
    settings_secret_values,
    start_pimcore_test_create,
    test_pimcore_settings,
    test_ftp_connection,
    test_local_paths,
    test_sql_connection,
    test_sql_profile_connection,
    update_pimcore_product,
    update_settings,
    update_user,
)
from ..version import get_app_version, get_display_version

try:  # pragma: no cover - optional runtime dependency
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover
    Image = None
    ImageOps = None


STATIC_DIR = Path(__file__).resolve().parent / "static"
BROWSER_EXTENSION_DIR = Path(__file__).resolve().parents[1] / "browser_extension"
SESSION_COOKIE = "picorg_web_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
BROWSER_EXTENSION_TOKEN_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"
ACTIVE_CLIENT_MAX_AGE_SECONDS = 180
PRESENCE_CLIENT_MAX_AGE_SECONDS = 45
ACTIVE_CLIENT_FLUSH_INTERVAL_SECONDS = 15
PRESENCE_CLIENT_ID_HEADER = "x-picorg-client-id"
WEB_UPLOAD_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
WEB_UPLOAD_CACHE_CLEAN_INTERVAL_SECONDS = 30 * 60
CSRF_HEADER = "x-picorg-csrf"
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_UPLOAD_CACHE_LAST_CLEANUP = 0.0
_BROWSER_EXTENSION_IMPORTS: Dict[str, List[Dict[str, Any]]] = {}
_BROWSER_EXTENSION_IMPORTS_LOCK = threading.Lock()
_PROCESS_JOB_RETENTION_SECONDS = 6 * 60 * 60
_PROCESS_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="picorg-process")
_PROCESS_JOBS: Dict[str, Dict[str, Any]] = {}
_PROCESS_JOBS_LOCK = threading.Lock()
_ACTIVE_CLIENTS: Dict[str, Dict[str, Any]] = {}
_ACTIVE_CLIENTS_LOCK = threading.Lock()
_ACTIVE_CLIENTS_LOADED = False
_ACTIVE_CLIENTS_DIRTY = False
_ACTIVE_CLIENTS_LAST_FLUSH = 0.0
_RATE_LIMITS: Dict[str, List[float]] = {}
_RATE_LIMITS_LOCK = threading.Lock()
_UPLOAD_SCAN_RESULTS: Dict[str, Dict[str, Any]] = {}
_UPLOAD_SCAN_RESULTS_LOCK = threading.Lock()
_BACKUP_SCHEDULER_STOP = threading.Event()
_BACKUP_SCHEDULER_THREAD: threading.Thread | None = None
RATE_LIMIT_LOGIN_ATTEMPTS = 20
RATE_LIMIT_LOGIN_WINDOW_SECONDS = 10 * 60
RATE_LIMIT_UPLOAD_ATTEMPTS = 80
RATE_LIMIT_UPLOAD_WINDOW_SECONDS = 60
ANTIVIRUS_SCAN_TIMEOUT_SECONDS = 120
EXECUTABLE_UPLOAD_EXTENSIONS = {
    "exe",
    "bat",
    "cmd",
    "com",
    "msi",
    "ps1",
    "vbs",
    "js",
    "jar",
    "dll",
    "scr",
    "pif",
    "sh",
}
GENERIC_UPLOAD_MIME_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
}
UPLOAD_MIME_TYPES = {
    "jpg": {"image/jpeg", "image/jpg", "image/pjpeg"},
    "jpeg": {"image/jpeg", "image/jpg", "image/pjpeg"},
    "png": {"image/png"},
    "webp": {"image/webp"},
    "gif": {"image/gif"},
    "bmp": {"image/bmp", "image/x-ms-bmp", "image/x-windows-bmp"},
    "tif": {"image/tiff", "image/tif"},
    "tiff": {"image/tiff", "image/tif"},
    "avif": {"image/avif", "image/heif", "image/heic"},
    "psd": {"image/vnd.adobe.photoshop", "image/x-photoshop", "image/psd"},
    "pdf": {"application/pdf", "application/x-pdf"},
    "eps": {"application/postscript", "application/eps", "image/eps"},
    "ai": {
        "application/pdf",
        "application/postscript",
        "application/illustrator",
        "application/vnd.adobe.illustrator",
    },
}
IMAGE_UPLOAD_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "gif",
    "bmp",
    "tif",
    "tiff",
    "avif",
    "psd",
}
METADATA_STRIP_UPLOAD_EXTENSIONS = {"jpg", "jpeg", "png"}
UPLOAD_EXTENSION_MIME_TYPE = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "avif": "image/avif",
}
IMAGE_SIGNATURE_EXTENSIONS = (
    "jpg",
    "png",
    "webp",
    "gif",
    "bmp",
    "tif",
    "avif",
)


@dataclass(frozen=True)
class _QueuedUploadFile:
    path: str
    filename: str


@dataclass(frozen=True)
class _SavedUploadCache:
    path: str
    size: int
    name: str


@dataclass
class _ProcessFormSnapshot:
    fields: Dict[str, str] = field(default_factory=dict)
    uploads: Dict[str, _QueuedUploadFile] = field(default_factory=dict)
    temp_dir: str = ""

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.uploads:
            return self.uploads[key]
        return self.fields.get(key, default)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _timing_item(key: str, label: str, started: float, **details: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "key": key,
        "label": label,
        "elapsed_ms": _elapsed_ms(started),
    }
    if details:
        payload["details"] = details
    return payload


def _timing_payload(stages: List[Dict[str, Any]], started: float) -> Dict[str, Any]:
    return {"total_ms": _elapsed_ms(started), "stages": stages}


def _processing_settings() -> Dict[str, Any]:
    return config._normalize_processing_settings(
        config.CONFIG.get(PROCESSING_SETTINGS_KEY, {})
    )


def _active_product_field_settings() -> Dict[str, Dict[str, object]]:
    return normalize_product_fields(
        config.CONFIG.get(PRODUCT_FIELDS_KEY),
        legacy_color_labels=config.CONFIG.get(COLOR_FIELD_LABELS_KEY),
    )


def _security_settings() -> Dict[str, Any]:
    raw_security = config.CONFIG.get(SECURITY_SETTINGS_KEY, {})
    if not isinstance(raw_security, dict):
        raw_security = {}
    merged = dict(raw_security)
    legacy_processing = config.CONFIG.get(PROCESSING_SETTINGS_KEY, {})
    if isinstance(legacy_processing, dict):
        for key in ("max_upload_mb", "max_upload_pixels"):
            if key not in merged and key in legacy_processing:
                merged[key] = legacy_processing[key]
    return config._normalize_security_settings(merged)


def _upload_processing_mode() -> str:
    return str(_processing_settings().get("upload_processing_mode") or "save")


def _show_timing_details() -> bool:
    return bool(_processing_settings().get("show_timing_details", False))


def _upload_limits() -> tuple[int, int]:
    security = _security_settings()
    max_bytes = max(1, int(security.get("max_upload_mb") or 50)) * 1024 * 1024
    max_pixels = max(1, int(security.get("max_upload_pixels") or 25_000_000))
    return max_bytes, max_pixels


def _upload_limit_message(size: int, max_bytes: int) -> str:
    limit_mb = max_bytes / (1024 * 1024)
    return f"Plik ma zbyt duzy rozmiar. Limit uploadu to {limit_mb:g} MB."


def _raise_upload_too_large(message: str) -> None:
    raise HTTPException(status_code=413, detail=message)


def _auth_enabled() -> bool:
    return os.environ.get("PICORG_WEB_AUTH", "1").strip().lower() in {"1", "true", "yes", "on"}


def _admin_username() -> str:
    return (
        os.environ.get("PICORG_WEB_ADMIN_USER", DEFAULT_ADMIN_USERNAME).strip()
        or DEFAULT_ADMIN_USERNAME
    )


def _admin_password() -> str:
    return os.environ.get("PICORG_WEB_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)


def _session_secret() -> bytes:
    value = os.environ.get("PICORG_WEB_SESSION_SECRET") or common.APP_SECRET
    return value.encode("utf-8")


def _sign(payload: str) -> str:
    return hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _csrf_token_for_session(session_token: Optional[str]) -> str:
    token = str(session_token or "")
    if not token:
        return ""
    return _sign(f"csrf|{token}")


def _csrf_token(request: Request) -> str:
    if not _auth_enabled():
        return ""
    return _csrf_token_for_session(request.cookies.get(SESSION_COOKIE))


def _request_host(request: Request) -> str:
    return str(request.headers.get("host") or request.url.netloc or "").lower()


def _origin_matches_request(request: Request, value: str) -> bool:
    parsed = urlsplit(str(value or ""))
    if not parsed.scheme or not parsed.netloc:
        return False
    return (
        parsed.scheme.lower() == str(request.url.scheme or "").lower()
        and parsed.netloc.lower() == _request_host(request)
    )


def _require_same_origin_mutation(request: Request) -> None:
    origin = str(request.headers.get("origin") or "")
    referer = str(request.headers.get("referer") or "")
    fetch_site = str(request.headers.get("sec-fetch-site") or "").lower()
    if origin and not _origin_matches_request(request, origin):
        raise HTTPException(status_code=403, detail="Odrzucono request z obcego Origin.")
    if not origin and referer and not _origin_matches_request(request, referer):
        raise HTTPException(status_code=403, detail="Odrzucono request z obcego Referer.")
    if not origin and not referer and fetch_site in {"cross-site", "same-site"}:
        raise HTTPException(status_code=403, detail="Odrzucono request spoza panelu.")


def _validate_mutating_request(request: Request) -> None:
    method = str(request.method or "").upper()
    if method not in MUTATING_METHODS:
        return
    path = str(request.url.path or "")
    if path.startswith("/api/browser-extension/"):
        return
    _require_same_origin_mutation(request)
    if path == "/api/login":
        if str(request.headers.get("x-requested-with") or "").lower() != "xmlhttprequest":
            raise HTTPException(status_code=403, detail="Brak naglowka requestu panelu.")
        return
    if not _auth_enabled():
        return
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        return
    expected = _csrf_token_for_session(session_token)
    supplied = str(request.headers.get(CSRF_HEADER) or "")
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="Niepoprawny token CSRF.")


def _make_session_token(username: str) -> str:
    user = find_user(username) or {}
    session_version = int(user.get("session_version") or 0)
    payload = f"session|{username}|{session_version}|{int(time.time())}|{secrets.token_hex(12)}"
    token = f"{payload}|{_sign(payload)}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _make_browser_extension_token(username: str) -> str:
    user = mark_browser_extension_token_issued(username) or find_user(username) or {}
    token_version = int(user.get("extension_token_version") or 0)
    payload = f"browser-extension|{username}|{token_version}|{int(time.time())}|{secrets.token_hex(16)}"
    token = f"{payload}|{_sign(payload)}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _read_session_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        payload, signature = decoded.rsplit("|", 1)
    except Exception:
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    parts = payload.split("|")
    if len(parts) == 5 and parts[0] == "session":
        _marker, username, version_raw, issued_raw, _nonce = parts
    elif len(parts) == 3:
        username, issued_raw, _nonce = parts
        version_raw = "0"
    else:
        return None
    try:
        issued = int(issued_raw)
        session_version = int(version_raw)
    except ValueError:
        return None
    if int(time.time()) - issued > SESSION_MAX_AGE_SECONDS:
        return None
    user = find_user(username)
    if not user or not user.get("enabled") or user.get("locked"):
        return None
    if int(user.get("session_version") or 0) != session_version:
        return None
    return username


def _read_browser_extension_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        payload, signature = decoded.rsplit("|", 1)
    except Exception:
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    parts = payload.split("|")
    if len(parts) == 5 and parts[0] == "browser-extension":
        _marker, username, version_raw, issued_raw, _nonce = parts
    elif len(parts) == 4 and parts[0] == "browser-extension":
        _marker, username, issued_raw, _nonce = parts
        version_raw = "0"
    else:
        return None
    try:
        issued = int(issued_raw)
        token_version = int(version_raw)
    except ValueError:
        return None
    if int(time.time()) - issued > BROWSER_EXTENSION_TOKEN_MAX_AGE_SECONDS:
        return None
    user = find_user(username)
    if not user or not user.get("enabled") or user.get("locked"):
        return None
    if int(user.get("extension_token_version") or 0) != token_version:
        return None
    mark_browser_extension_token_used(username, token_version)
    return username


def _current_user(request: Request) -> Optional[str]:
    if not _auth_enabled():
        return _admin_username()
    return _read_session_token(request.cookies.get(SESSION_COOKIE))


def _request_remote_address(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "") or "")


def _rate_limit_scope(request: Request) -> tuple[str, int, int]:
    method = str(request.method or "").upper()
    path = str(request.url.path or "")
    if method == "POST" and path == "/api/login":
        return "login", RATE_LIMIT_LOGIN_ATTEMPTS, RATE_LIMIT_LOGIN_WINDOW_SECONDS
    upload_paths = {
        "/api/upload-cache",
        "/api/browser-extension/upload-cache",
        "/api/web-images/cache",
        "/api/web-images/scan",
        "/api/process",
        "/api/process/background",
    }
    if method == "POST" and path in upload_paths:
        return "upload", RATE_LIMIT_UPLOAD_ATTEMPTS, RATE_LIMIT_UPLOAD_WINDOW_SECONDS
    return "", 0, 0


def _check_rate_limit(request: Request) -> None:
    scope, limit, window = _rate_limit_scope(request)
    if not scope or limit <= 0 or window <= 0:
        return
    now = time.time()
    remote = _request_remote_address(request) or "unknown"
    key = f"{scope}|{remote}"
    cutoff = now - window
    with _RATE_LIMITS_LOCK:
        attempts = [item for item in _RATE_LIMITS.get(key, []) if item >= cutoff]
        if len(attempts) >= limit:
            retry_after = max(1, int(window - (now - attempts[0])))
            raise HTTPException(
                status_code=429,
                detail=f"Za duzo requestow z tego adresu IP. Sprobuj ponownie za {retry_after} s.",
                headers={"Retry-After": str(retry_after)},
            )
        attempts.append(now)
        _RATE_LIMITS[key] = attempts


def _extension_bearer_token(request: Request) -> str:
    authorization = str(request.headers.get("authorization") or "").strip()
    if not authorization.lower().startswith("bearer "):
        return ""
    return authorization.split(None, 1)[1].strip()


def _require_browser_extension_user(request: Request) -> str:
    if not _auth_enabled():
        return _admin_username()
    username = _read_browser_extension_token(_extension_bearer_token(request))
    if not username:
        raise HTTPException(status_code=401, detail="Niepoprawny albo wygasly token rozszerzenia.")
    return username


def _require_user(request: Request) -> str:
    if not _auth_enabled():
        return _admin_username()
    username = _current_user(request)
    if not username:
        raise HTTPException(status_code=401, detail="Brak aktywnej sesji.")
    return username


def _current_user_payload(request: Request) -> Dict[str, Any]:
    username = _require_user(request)
    user = find_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="Brak aktywnej sesji.")
    return user


def _user_cache_scope(request: Request, username: str) -> str:
    session_token = str(request.cookies.get(SESSION_COOKIE) or "")
    if session_token:
        scope_material = session_token
    else:
        client = getattr(request, "client", None)
        client_host = str(getattr(client, "host", "") or "")
        headers = getattr(request, "headers", {}) or {}
        user_agent = str(headers.get("user-agent", "") if hasattr(headers, "get") else "")
        scope_material = f"{client_host}|{user_agent}|no-session"
    token_digest = hashlib.sha1(scope_material.encode("utf-8")).hexdigest()[:12]
    raw_scope = f"{username}-{token_digest}"
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", raw_scope).strip("._-") or "user-session"


def _require_admin(request: Request) -> Dict[str, Any]:
    user = _current_user_payload(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Wymagane konto administratora.")
    return user


def _static_file(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / name)


def _safe_upload_name(filename: Optional[str], fallback: str) -> str:
    name = Path(filename or "").name.strip()
    if not name:
        name = fallback
    return name


def _safe_file_suffix(filename: str) -> str:
    suffix = Path(filename or "").suffix.strip().lower()
    if suffix and len(suffix) <= 12 and re.fullmatch(r"\.[a-z0-9]+", suffix):
        return suffix
    return ""


def _upload_extension(filename: object) -> str:
    suffix = _safe_file_suffix(str(filename or ""))
    return suffix[1:] if suffix.startswith(".") else ""


def _validate_upload_extension(filename: object) -> None:
    extension = _upload_extension(filename)
    security = _security_settings()
    allowed = set(security.get("allowed_upload_extensions") or [])
    blocked = set(security.get("blocked_upload_extensions") or [])
    if not extension:
        raise HTTPException(status_code=400, detail="Plik musi miec rozszerzenie.")
    if extension in blocked:
        raise HTTPException(status_code=400, detail=f"Typ pliku .{extension} jest zablokowany.")
    if security.get("block_executable_uploads", True) and extension in EXECUTABLE_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Plik wykonywalny .{extension} jest zablokowany.",
        )
    if allowed and extension not in allowed:
        raise HTTPException(status_code=400, detail=f"Typ pliku .{extension} nie jest dozwolony.")


def _normalized_content_type(content_type: object) -> str:
    return str(content_type or "").split(";", 1)[0].strip().lower()


def _validate_upload_mime_type(filename: object, content_type: object) -> None:
    extension = _upload_extension(filename)
    normalized = _normalized_content_type(content_type)
    if normalized in GENERIC_UPLOAD_MIME_TYPES:
        return
    allowed = UPLOAD_MIME_TYPES.get(extension)
    if allowed is None:
        raise HTTPException(
            status_code=400,
            detail=f"Typ pliku .{extension} nie ma skonfigurowanej walidacji MIME.",
        )
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"MIME type {normalized} nie pasuje do pliku .{extension}.",
        )


def _is_iso_base_media_brand(header: bytes, allowed_brands: Set[bytes]) -> bool:
    if len(header) < 16 or header[4:8] != b"ftyp":
        return False
    brands = {header[8:12]}
    compatible = header[16:64]
    brands.update(compatible[index : index + 4] for index in range(0, len(compatible) - 3, 4))
    return any(brand in allowed_brands for brand in brands)


def _upload_signature_matches(extension: str, header: bytes) -> bool:
    if extension in {"jpg", "jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == "png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == "gif":
        return header.startswith((b"GIF87a", b"GIF89a"))
    if extension == "bmp":
        return header.startswith(b"BM")
    if extension in {"tif", "tiff"}:
        return header.startswith((b"II*\x00", b"MM\x00*"))
    if extension == "webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    if extension == "avif":
        return _is_iso_base_media_brand(header, {b"avif", b"avis"})
    if extension == "pdf":
        return header.startswith(b"%PDF-")
    if extension == "eps":
        return header.startswith(b"%!PS-Adobe-")
    if extension == "ai":
        return header.startswith((b"%PDF-", b"%!PS-Adobe-"))
    if extension == "psd":
        return header.startswith(b"8BPS")
    return False


def _upload_extension_from_signature(header: bytes) -> str:
    for extension in IMAGE_SIGNATURE_EXTENSIONS:
        if _upload_signature_matches(extension, header):
            return extension
    return ""


def _upload_extensions_equivalent(current: str, detected: str) -> bool:
    if current == detected:
        return True
    return {current, detected} <= {"jpg", "jpeg"} or {current, detected} <= {"tif", "tiff"}


def _upload_name_with_extension(filename: str, extension: str) -> str:
    stem = Path(filename or "").stem.strip(" .-_") or "upload"
    return f"{stem}.{extension}"


def _normalize_upload_cache_extension(
    path: str,
    filename: str,
    content_type: object,
) -> tuple[str, str, str]:
    try:
        with open(path, "rb") as handle:
            header = handle.read(128)
    except OSError:
        return path, filename, _normalized_content_type(content_type)
    detected_extension = _upload_extension_from_signature(header)
    current_extension = _upload_extension(filename)
    if not detected_extension or _upload_extensions_equivalent(current_extension, detected_extension):
        return path, filename, _normalized_content_type(content_type)
    corrected_name = _upload_name_with_extension(filename, detected_extension)
    base, _old_extension = os.path.splitext(path)
    corrected_path = f"{base}.{detected_extension}"
    if os.path.normcase(os.path.abspath(corrected_path)) != os.path.normcase(os.path.abspath(path)):
        os.replace(path, corrected_path)
    return corrected_path, corrected_name, UPLOAD_EXTENSION_MIME_TYPE.get(detected_extension, "")


def _validate_upload_signature(path: str, filename: object) -> None:
    extension = _upload_extension(filename)
    try:
        with open(path, "rb") as handle:
            header = handle.read(128)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Nie mozna odczytac wyslanego pliku.") from exc
    if not header:
        raise HTTPException(status_code=400, detail="Plik jest pusty.")
    stripped = header.lstrip().lower()
    if stripped.startswith((b"<html", b"<!doctype", b"<svg", b"<?xml")):
        raise HTTPException(
            status_code=400,
            detail="Zawartosc pliku wyglada jak HTML/XML/SVG, a nie dozwolony upload.",
        )
    if not _upload_signature_matches(extension, header):
        raise HTTPException(
            status_code=400,
            detail=f"Sygnatura pliku nie pasuje do rozszerzenia .{extension}.",
        )


def _validate_upload_image_file(path: str, filename: object, max_pixels: int) -> tuple[int, int]:
    extension = _upload_extension(filename)
    if extension not in IMAGE_UPLOAD_EXTENSIONS:
        return 0, 0
    if Image is None:
        raise HTTPException(status_code=415, detail="Pillow nie jest dostepny do walidacji obrazu.")
    try:
        with warnings.catch_warnings():
            if hasattr(Image, "DecompressionBombWarning"):
                warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                width, height = int(image.size[0]), int(image.size[1])
                pixels = width * height
                if pixels > max_pixels:
                    _raise_upload_too_large(
                        f"Obraz ma {pixels} pikseli ({width}x{height}), limit uploadu to {max_pixels} pikseli."
                    )
                image.verify()
                return width, height
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Nie mozna otworzyc pliku jako obrazu.") from exc


def _validate_upload_content(
    path: str,
    filename: object,
    content_type: object,
    max_pixels: int,
) -> tuple[int, int]:
    _validate_upload_mime_type(filename, content_type)
    _validate_upload_signature(path, filename)
    return _validate_upload_image_file(path, filename, max_pixels)


def _jpeg_safe_image(image: Any) -> Any:
    if image.mode in {"RGB", "L"}:
        return image
    if image.mode in {"RGBA", "LA"}:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, (0, 0), rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _strip_upload_metadata(path: str, filename: object) -> None:
    extension = _upload_extension(filename)
    if extension not in METADATA_STRIP_UPLOAD_EXTENSIONS or Image is None:
        return
    temp_path = f"{path}.clean-{secrets.token_hex(6)}"
    try:
        with Image.open(path) as image:
            work = image.copy()
        if ImageOps is not None:
            try:
                work = ImageOps.exif_transpose(work)
            except Exception:
                pass
        if extension in {"jpg", "jpeg"}:
            work = _jpeg_safe_image(work)
            work.save(temp_path, format="JPEG", quality=95, optimize=True)
        else:
            work.save(temp_path, format="PNG", optimize=True)
        os.replace(temp_path, path)
    except Exception as exc:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="Nie mozna wyczyscic metadanych obrazu.") from exc


def _enforce_upload_size(path: str, max_bytes: int) -> int:
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Nie mozna sprawdzic rozmiaru wyslanego pliku.") from exc
    if size > max_bytes:
        _raise_upload_too_large(_upload_limit_message(size, max_bytes))
    return size


def _defender_scan_executable() -> str:
    if os.name != "nt":
        return ""
    candidates: List[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / "Windows Defender" / "MpCmdRun.exe")
    platform_root = Path(os.environ.get("ProgramData") or r"C:\ProgramData") / "Microsoft" / "Windows Defender" / "Platform"
    try:
        candidates.extend(sorted(platform_root.glob("*/MpCmdRun.exe"), reverse=True))
    except OSError:
        pass
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


def _remember_upload_scan_result(path: str, result: Dict[str, Any]) -> None:
    if not path:
        return
    with _UPLOAD_SCAN_RESULTS_LOCK:
        _UPLOAD_SCAN_RESULTS[os.path.abspath(path)] = dict(result)


def _copy_upload_scan_result(source_path: str, target_path: str) -> None:
    if not source_path or not target_path:
        return
    with _UPLOAD_SCAN_RESULTS_LOCK:
        result = _UPLOAD_SCAN_RESULTS.get(os.path.abspath(source_path))
        if result:
            _UPLOAD_SCAN_RESULTS[os.path.abspath(target_path)] = dict(result)


def _upload_scan_result(path: str) -> Dict[str, Any]:
    with _UPLOAD_SCAN_RESULTS_LOCK:
        return dict(_UPLOAD_SCAN_RESULTS.get(os.path.abspath(path)) or {})


def _uploaded_scan_summary(uploaded_slots: List[WebUploadedSlot]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for slot in uploaded_slots:
        result = _upload_scan_result(str(slot.source_path or ""))
        if result:
            item = dict(result)
            item["prefix"] = str(slot.prefix or "")
            item["filename"] = str(slot.original_filename or "")
            results.append(item)
    scanned = [item for item in results if item.get("scanned")]
    enabled = any(item.get("enabled") for item in results)
    return {
        "enabled": enabled,
        "scanned": len(scanned),
        "skipped": sum(1 for item in results if item.get("enabled") and not item.get("scanned")),
        "items": results,
    }


def _scan_uploaded_file(path: str) -> Dict[str, Any]:
    if not _security_settings().get("antivirus_scan_uploads", False):
        result = {"enabled": False, "scanned": False, "scanner": "", "elapsed_ms": 0}
        _remember_upload_scan_result(path, result)
        return result
    started = time.perf_counter()
    scanner = _defender_scan_executable()
    if not scanner:
        raise HTTPException(
            status_code=503,
            detail="Skan antywirusowy uploadu jest wlaczony, ale nie znaleziono Microsoft Defender MpCmdRun.exe.",
        )
    try:
        completed = subprocess.run(
            [
                scanner,
                "-Scan",
                "-ScanType",
                "3",
                "-File",
                os.path.abspath(path),
                "-DisableRemediation",
            ],
            capture_output=True,
            text=True,
            timeout=ANTIVIRUS_SCAN_TIMEOUT_SECONDS,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=503, detail="Skan antywirusowy uploadu przekroczyl limit czasu.") from exc
    output = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if str(part or "").strip()
    )
    result = {
        "enabled": True,
        "scanned": completed.returncode == 0,
        "scanner": "Microsoft Defender",
        "return_code": int(completed.returncode),
        "elapsed_ms": _elapsed_ms(started),
    }
    _remember_upload_scan_result(path, result)
    if completed.returncode != 0:
        details = output[-500:] if output else f"kod {completed.returncode}"
        raise HTTPException(
            status_code=400,
            detail=f"Skan antywirusowy odrzucil upload ({details}).",
        )
    return result


def _upload_cache_root() -> str:
    return os.path.join(settings.AC, "web_upload_cache")


def _upload_cache_dir(cache_scope: object = "") -> str:
    safe_scope = sanitize_path_segment(cache_scope) or "user-session"
    return os.path.join(_upload_cache_root(), safe_scope)


def _path_is_under_root(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:
        return False


def _is_upload_cache_path(path: str) -> bool:
    return bool(path and _path_is_under_root(path, _upload_cache_root()))


def _delete_upload_cache_files(paths: List[str]) -> Dict[str, Any]:
    root = os.path.abspath(_upload_cache_root())
    deleted = 0
    skipped = 0
    errors: List[str] = []
    touched_dirs: Set[str] = set()
    for raw_path in sorted({os.path.abspath(path) for path in paths if path}):
        if not _path_is_under_root(raw_path, root):
            skipped += 1
            continue
        touched_dirs.add(os.path.dirname(raw_path))
        try:
            if os.path.isfile(raw_path):
                os.remove(raw_path)
                deleted += 1
            else:
                skipped += 1
        except OSError as exc:
            errors.append(f"{raw_path}: {exc}")
    for directory in sorted(touched_dirs, key=len, reverse=True):
        current = os.path.abspath(directory)
        while _path_is_under_root(current, root) and current != root:
            try:
                os.rmdir(current)
            except OSError:
                break
            current = os.path.dirname(current)
    try:
        os.rmdir(root)
    except OSError:
        pass
    return {"deleted": deleted, "skipped": skipped, "errors": errors}


def cleanup_web_upload_cache(
    *,
    max_age_seconds: int = WEB_UPLOAD_CACHE_MAX_AGE_SECONDS,
    min_interval_seconds: int = WEB_UPLOAD_CACHE_CLEAN_INTERVAL_SECONDS,
    force: bool = False,
) -> Dict[str, Any]:
    """Remove stale browser upload cache files."""

    global _UPLOAD_CACHE_LAST_CLEANUP
    now = time.time()
    if not force and now - _UPLOAD_CACHE_LAST_CLEANUP < max(1, int(min_interval_seconds or 1)):
        return {"deleted_files": 0, "deleted_dirs": 0, "skipped": True, "errors": []}
    _UPLOAD_CACHE_LAST_CLEANUP = now
    root = os.path.abspath(_upload_cache_root())
    if not os.path.isdir(root):
        return {"deleted_files": 0, "deleted_dirs": 0, "skipped": False, "errors": []}

    cutoff = now - max(60, int(max_age_seconds or WEB_UPLOAD_CACHE_MAX_AGE_SECONDS))
    deleted_files = 0
    deleted_dirs = 0
    errors: List[str] = []
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


def _file_token(path: str) -> str:
    payload = os.path.abspath(path)
    token = f"{payload}|{_sign(payload)}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _file_version(path: str) -> str:
    try:
        stat = os.stat(path)
    except OSError:
        return ""
    return f"{int(stat.st_mtime_ns)}-{int(stat.st_size)}"


def _versioned_file_url(path: str, endpoint: str, token: str) -> str:
    url = f"{endpoint}?token={token}"
    version = _file_version(path)
    if version:
        url = f"{url}&v={version}"
    return url


def _path_from_file_token(token: str, *, require_exists: bool = True) -> str:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        path, signature = decoded.rsplit("|", 1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Niepoprawny token pliku.") from exc
    if not hmac.compare_digest(_sign(path), signature):
        raise HTTPException(status_code=403, detail="Niepoprawny podpis pliku.")
    abs_path = os.path.abspath(path)
    roots = [
        os.path.abspath(settings.l),
        os.path.abspath(os.path.join(settings.AC, "web_ftp_cache")),
        os.path.abspath(_upload_cache_root()),
    ]
    allowed = False
    for root in roots:
        try:
            common = os.path.commonpath([abs_path, root])
        except ValueError:
            continue
        if common == root:
            allowed = True
            break
    if not allowed:
        raise HTTPException(status_code=403, detail="Plik poza katalogiem zdjec lub cache.")
    if require_exists and not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Nie znaleziono pliku.")
    return abs_path


def _resample_filter() -> Any:
    if Image is not None and hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", 3))


def _thumbnail_bytes(path: str, *, width: int = 360, height: int = 260, content_fit: bool = False) -> bytes:
    if Image is None:
        raise HTTPException(status_code=415, detail="Pillow nie jest dostepny dla miniaturek.")
    try:
        with Image.open(path) as image:
            try:
                image.seek(0)
            except Exception:
                pass
            work = image.copy()
    except Exception as exc:
        raise HTTPException(status_code=415, detail="Podglad tego formatu nie jest dostepny.") from exc
    if ImageOps is not None:
        try:
            work = ImageOps.exif_transpose(work)
        except Exception:
            pass
    if content_fit:
        try:
            work = fit_image_to_content(work)
        except Exception:
            pass
    work.thumbnail((max(64, width), max(64, height)), _resample_filter())
    if work.mode not in {"RGB", "L"}:
        background = Image.new("RGB", work.size, (255, 255, 255))
        if work.mode in {"RGBA", "LA"}:
            rgba = work.convert("RGBA")
            background.paste(rgba, (0, 0), rgba.getchannel("A"))
        else:
            background.paste(work.convert("RGB"), (0, 0))
        work = background
    elif work.mode == "L":
        work = work.convert("RGB")
    buffer = io.BytesIO()
    work.save(buffer, format="JPEG", quality=82, optimize=True)
    return buffer.getvalue()


def _image_dimensions(path: str) -> tuple[int, int]:
    if Image is None:
        return 0, 0
    try:
        with Image.open(path) as image:
            if ImageOps is not None:
                try:
                    image = ImageOps.exif_transpose(image)
                except Exception:
                    pass
            return int(image.size[0]), int(image.size[1])
    except Exception:
        return 0, 0


def _validate_upload_image_pixels(path: str, max_pixels: int) -> tuple[int, int]:
    width, height = _image_dimensions(path)
    if width <= 0 or height <= 0:
        return width, height
    pixels = int(width) * int(height)
    if pixels > max_pixels:
        _raise_upload_too_large(
            f"Obraz ma {pixels} pikseli ({width}x{height}), limit uploadu to {max_pixels} pikseli."
        )
    return width, height


async def _save_upload(upload: UploadFile, temp_dir: str, prefix: str) -> str:
    safe_name = _safe_upload_name(upload.filename, f"{prefix}.upload")
    suffix = _safe_file_suffix(safe_name)
    target_path = os.path.join(temp_dir, f"{prefix}_{secrets.token_hex(8)}{suffix}")
    max_bytes, max_pixels = _upload_limits()
    size = 0
    try:
        _validate_upload_extension(safe_name)
        with open(target_path, "wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    _raise_upload_too_large(_upload_limit_message(size, max_bytes))
                handle.write(chunk)
        _validate_upload_content(target_path, safe_name, getattr(upload, "content_type", ""), max_pixels)
        _strip_upload_metadata(target_path, safe_name)
        _enforce_upload_size(target_path, max_bytes)
        _scan_uploaded_file(target_path)
        return target_path
    except Exception:
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        raise
    finally:
        await upload.close()


def _upload_prefix_from_form_key(key: str) -> str:
    text = str(key or "").strip()
    if text.startswith("slot_"):
        text = text[5:]
    return sanitize_path_segment(text) or "slot"


async def _materialize_process_form(form: Any, temp_dir: str) -> _ProcessFormSnapshot:
    os.makedirs(temp_dir, exist_ok=True)
    fields: Dict[str, str] = {}
    uploads: Dict[str, _QueuedUploadFile] = {}
    items = form.multi_items() if hasattr(form, "multi_items") else form.items()
    for key, value in items:
        key_text = str(key)
        if isinstance(value, UploadFile):
            if not value.filename:
                continue
            path = await _save_upload(value, temp_dir, _upload_prefix_from_form_key(key_text))
            uploads[key_text] = _QueuedUploadFile(
                path=path,
                filename=_safe_upload_name(value.filename, os.path.basename(path)),
            )
            continue
        fields[key_text] = str(value)
    return _ProcessFormSnapshot(fields=fields, uploads=uploads, temp_dir=temp_dir)


async def _save_upload_cache_entry(
    upload: UploadFile,
    cache_scope: str,
    prefix: str,
    *,
    normalize_extension: bool = False,
) -> _SavedUploadCache:
    safe_name = _safe_upload_name(upload.filename, f"{prefix}.upload")
    stem = Path(safe_name).stem
    suffix = _safe_file_suffix(safe_name)
    safe_prefix = sanitize_path_segment(prefix) or "slot"
    safe_stem = sanitize_path_segment(stem) or "upload"
    safe_stem = safe_stem[:80].strip(" .-_") or "upload"
    cache_dir = _upload_cache_dir(cache_scope)
    os.makedirs(cache_dir, exist_ok=True)
    target_path = os.path.join(
        cache_dir,
        f"{safe_prefix}_{secrets.token_hex(12)}_{safe_stem}{suffix}",
    )
    max_bytes, max_pixels = _upload_limits()
    size = 0
    try:
        _validate_upload_extension(safe_name)
        content_type = getattr(upload, "content_type", "")
        with open(target_path, "wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    _raise_upload_too_large(_upload_limit_message(size, max_bytes))
                handle.write(chunk)
        if normalize_extension:
            target_path, safe_name, content_type = _normalize_upload_cache_extension(
                target_path,
                safe_name,
                content_type,
            )
            _validate_upload_extension(safe_name)
        _validate_upload_content(target_path, safe_name, content_type, max_pixels)
        _strip_upload_metadata(target_path, safe_name)
        size = _enforce_upload_size(target_path, max_bytes)
        _scan_uploaded_file(target_path)
        return _SavedUploadCache(target_path, size, safe_name)
    except Exception:
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        raise
    finally:
        await upload.close()


async def _save_upload_cache(upload: UploadFile, cache_scope: str, prefix: str) -> tuple[str, int]:
    saved = await _save_upload_cache_entry(upload, cache_scope, prefix)
    return saved.path, saved.size


def _save_web_image_cache(
    image_url: str,
    page_url: str,
    cache_scope: str,
    prefix: str,
) -> tuple[str, int, str, int, int]:
    max_bytes, max_pixels = _upload_limits()
    data, filename, _mime_type, width, height = download_image_bytes(
        image_url,
        page_url,
        max_bytes=max_bytes,
        max_pixels=max_pixels,
    )
    safe_name = _safe_upload_name(filename or filename_from_url(image_url), f"{prefix}.jpg")
    _validate_upload_extension(safe_name)
    stem = Path(safe_name).stem
    suffix = _safe_file_suffix(safe_name) or ".jpg"
    safe_prefix = sanitize_path_segment(prefix) or "slot"
    safe_stem = sanitize_path_segment(stem) or "web_image"
    safe_stem = safe_stem[:80].strip(" .-_") or "web_image"
    cache_dir = _upload_cache_dir(cache_scope)
    os.makedirs(cache_dir, exist_ok=True)
    target_path = os.path.join(
        cache_dir,
        f"{safe_prefix}_{secrets.token_hex(12)}_{safe_stem}{suffix}",
    )
    with open(target_path, "wb") as handle:
        handle.write(data)
    return target_path, len(data), safe_name, width, height


def _scan_web_image_page(
    page_url: str,
    *,
    mode: str = "metadata",
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    html = fetch_page_html(page_url)
    scan_mode = str(mode or "metadata").strip().lower()
    probe_images = scan_mode not in {"links", "link", "fast"}
    images = discover_image_candidates(
        page_url,
        html,
        probe_images=probe_images,
        filters=filters or {},
    )
    return {
        "source_url": page_url,
        "images": images,
        "count": len(images),
        "mode": "metadata" if probe_images else "links",
    }


def _record_browser_extension_import(username: str, item: Dict[str, Any]) -> None:
    key = str(username or "").strip().lower() or _admin_username().lower()
    with _BROWSER_EXTENSION_IMPORTS_LOCK:
        queue = _BROWSER_EXTENSION_IMPORTS.setdefault(key, [])
        queue.append(item)
        del queue[:-120]


def _pop_browser_extension_imports(username: str) -> List[Dict[str, Any]]:
    key = str(username or "").strip().lower() or _admin_username().lower()
    with _BROWSER_EXTENSION_IMPORTS_LOCK:
        items = list(_BROWSER_EXTENSION_IMPORTS.get(key, []))
        _BROWSER_EXTENSION_IMPORTS[key] = []
    return items


def _browser_extension_cors_headers(request: Request) -> Dict[str, str]:
    origin = str(request.headers.get("origin") or "")
    if origin.startswith(("chrome-extension://", "edge-extension://")):
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Headers": "authorization, content-type",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Vary": "Origin",
        }
    return {}


def _browser_extension_json(request: Request, payload: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(payload, headers=_browser_extension_cors_headers(request))


def _browser_extension_defaults(request: Request, username: str) -> str:
    base_url = str(request.base_url).rstrip("/")
    user = find_user(username) or {}
    payload = {
        "panelUrl": base_url,
        "apiToken": _make_browser_extension_token(username),
        "tokenVersion": int(user.get("extension_token_version") or 0),
        "panelVersion": get_display_version(),
    }
    return "window.PICORG_EXTENSION_DEFAULTS = " + json.dumps(payload, ensure_ascii=False) + ";\n"


def _browser_extension_zip_bytes(request: Request, username: str) -> bytes:
    if not BROWSER_EXTENSION_DIR.is_dir():
        raise HTTPException(status_code=404, detail="Brak plikow rozszerzenia.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        root_name = "picorgftp-sql-browser-extension"
        for path in sorted(BROWSER_EXTENSION_DIR.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(BROWSER_EXTENSION_DIR).as_posix()
            if relative == "defaults.js":
                continue
            archive.write(path, f"{root_name}/{relative}")
        archive.writestr(
            f"{root_name}/defaults.js",
            _browser_extension_defaults(request, username),
        )
    return buffer.getvalue()


def _result_payload(result: Any) -> Dict[str, Any]:
    return {
        "output_dir": result.output_dir,
        "ean": result.ean,
        "saved_files": [
            {
                "prefix": item.prefix,
                "label": item.label,
                "filename_label": item.filename_label,
                "source_name": item.source_name,
                "filename": item.filename,
                "path": item.path,
                "size_bytes": item.size_bytes,
                "source_size_bytes": getattr(item, "source_size_bytes", 0),
                "elapsed_ms": getattr(item, "elapsed_ms", 0),
                "operation": getattr(item, "operation", ""),
                "preprocessed": bool(getattr(item, "preprocessed", False)),
                "content_fit": bool(getattr(item, "content_fit", False)),
            }
            for item in result.saved_files
        ],
        "skipped_slots": result.skipped_slots,
    }


def _remote_name_for_output(filename: str) -> str:
    parsed = parse_slot_filename(filename)
    if not parsed or not parsed.ean:
        return ""
    return f"{parsed.ean}_{parsed.normalized_label}{parsed.extension}"


def _sync_result_to_ftp(
    result: Any,
    delete_candidates: Optional[List[str]] = None,
    *,
    skip_upload_prefixes: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    if not bool(config.CONFIG.get(ft, True)):
        return {"enabled": False, "uploaded": 0, "deleted": 0, "elapsed_ms": 0, "error": ""}
    skip_upload_prefixes = {str(prefix) for prefix in (skip_upload_prefixes or set())}
    filenames = [
        item.filename
        for item in result.saved_files
        if getattr(item, "filename", "") and str(getattr(item, "prefix", "")) not in skip_upload_prefixes
    ]
    uploaded_remote_names = {_remote_name_for_output(filename) for filename in filenames}
    delete_set = {
        os.path.basename(str(item or ""))
        for item in (delete_candidates or [])
        if os.path.basename(str(item or ""))
    }
    delete_set.difference_update({item for item in uploaded_remote_names if item})
    if not filenames and not delete_set:
        return {"enabled": True, "uploaded": 0, "deleted": 0, "elapsed_ms": 0, "error": ""}
    try:
        payload = sync_remote_files(
            config.CONFIG.get(H, {}),
            result.output_dir,
            filenames,
            sorted(delete_set),
            set(),
        )
    except Exception as exc:
        payload = {"uploaded": 0, "deleted": 0, "elapsed_ms": 0, "error": str(exc)}
    payload["enabled"] = True
    return payload


def _safe_sql_identifier(value: object) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"[0-9A-Za-z_\.]+", text) else ""


def _sql_row_exists_query(table: str, where_clause: str, db_type: str) -> str:
    if not table:
        return ""
    if str(db_type or "").lower() == str(K).lower():
        query = f"SELECT 1 FROM {table}{where_clause}".rstrip(";\n\r\t ")
        if " limit " not in query.lower():
            query = f"{query} LIMIT 1"
        return query
    return f"SELECT TOP 1 1 FROM {table}{where_clause}".rstrip(";\n\r\t ")


def _cursor_rowcount(cur: Any) -> int:
    try:
        return int(getattr(cur, "rowcount", -1))
    except (TypeError, ValueError):
        return -1


def _sync_result_to_sql(
    result: Any,
    *,
    clear_prefixes: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    if not bool(config.CONFIG.get(u, True)):
        return {
            "enabled": False,
            "updated": 0,
            "cleared": 0,
            "rows": 0,
            "elapsed_ms": 0,
            "error": "",
            "skipped": False,
            "reason": "",
        }
    started = time.perf_counter()
    ean = str(getattr(result, "ean", "") or "").strip()
    payload = {
        "enabled": True,
        "updated": 0,
        "cleared": 0,
        "rows": 0,
        "elapsed_ms": 0,
        "error": "",
        "skipped": False,
        "reason": "",
    }
    if not (ean and len(ean) == 13 and ean.isdigit()):
        payload["error"] = "SQL pominiety: brak poprawnego EAN-13."
        return payload
    sql_map = config.CONFIG.get(SQL_COLUMN_MAP_KEY, {}) or {}
    context = extract_presence_context(config.CONFIG, ean)
    if not context:
        payload["error"] = "SQL pominiety: nie mozna ustalic tabeli/warunku z zapytania."
        return payload
    table, where_clause = context
    saved_by_prefix = {item.prefix: item.filename for item in result.saved_files if getattr(item, "filename", "")}
    clear_prefixes = set(clear_prefixes or set()) - set(saved_by_prefix)
    if not saved_by_prefix and not clear_prefixes:
        return payload
    conn = None
    cur = None
    try:
        conn = connect_db()
        cur = conn.cursor()
        row_exists_query = _sql_row_exists_query(table, where_clause, config.CONFIG.get(p, K))
        if row_exists_query:
            cur.execute(row_exists_query)
            if not cur.fetchone():
                payload["skipped"] = True
                payload["reason"] = "nie znaleziono wiersza produktu dla tego EAN"
                return payload
        template = str(config.CONFIG.get(w, "") or "").strip()
        if not template:
            payload["skipped"] = True
            payload["reason"] = "nie skonfigurowano zapytania SQL"
            return payload
        for prefix, filename in saved_by_prefix.items():
            column = _safe_sql_identifier(sql_map.get(prefix, ""))
            if not column:
                continue
            parsed = parse_slot_filename(filename)
            if not parsed:
                continue
            short_name = f"{ean}_{prefix}{parsed.extension}"
            query = template.format(col=column, column=column, filename=short_name, ean=ean)
            cur.execute(query)
            rowcount = _cursor_rowcount(cur)
            if rowcount != 0:
                payload["updated"] += 1
            if rowcount > 0:
                payload["rows"] += rowcount
        for prefix in clear_prefixes:
            column = _safe_sql_identifier(sql_map.get(prefix, ""))
            if not column:
                continue
            cur.execute(f"UPDATE {table} SET {column} = ''{where_clause}")
            rowcount = _cursor_rowcount(cur)
            if rowcount != 0:
                payload["cleared"] += 1
            if rowcount > 0:
                payload["rows"] += rowcount
        if payload["updated"] or payload["cleared"]:
            conn.commit()
    except Exception as exc:
        payload["error"] = str(exc)
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        payload["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return payload


def _ftp_skip_upload_prefixes(
    result: Any,
    existing_photos: List[Dict[str, Any]],
    *,
    explicit_prefixes: Set[str],
    migrated_prefixes: Set[str],
    ftp_backfill_prefixes: Set[str],
) -> Set[str]:
    """Return saved prefixes that do not need a remote upload."""

    skip = {str(prefix) for prefix in ftp_backfill_prefixes if str(prefix)}
    explicit = {str(prefix) for prefix in explicit_prefixes if str(prefix)}
    migrated = {str(prefix) for prefix in migrated_prefixes if str(prefix)}
    photos_by_prefix = {
        str(photo.get("prefix") or ""): photo
        for photo in existing_photos
        if str(photo.get("prefix") or "")
    }
    for item in getattr(result, "saved_files", []) or []:
        prefix = str(getattr(item, "prefix", "") or "")
        if not prefix or prefix in skip or prefix in explicit or prefix in migrated:
            continue
        if photos_by_prefix.get(prefix, {}).get("ftp"):
            skip.add(prefix)
    return skip


def _ftp_replacement_delete_candidates(
    result: Any,
    existing_photos: List[Dict[str, Any]],
    *,
    explicit_prefixes: Set[str],
) -> List[str]:
    """Return old remote files replaced by explicit slot changes."""

    explicit = {str(prefix) for prefix in explicit_prefixes if str(prefix)}
    photos_by_prefix = {
        str(photo.get("prefix") or ""): photo
        for photo in existing_photos
        if str(photo.get("prefix") or "")
    }
    delete_candidates: List[str] = []
    for item in getattr(result, "saved_files", []) or []:
        prefix = str(getattr(item, "prefix", "") or "")
        if not prefix or prefix not in explicit:
            continue
        current_remote = os.path.basename(
            str(photos_by_prefix.get(prefix, {}).get("ftp_filename") or "")
        )
        if not current_remote:
            continue
        expected_remote = _remote_name_for_output(str(getattr(item, "filename", "") or ""))
        if expected_remote and current_remote != expected_remote:
            delete_candidates.append(current_remote)
    return delete_candidates


def _delete_local_files(delete_requests: List[Dict[str, Any]], saved_paths: Set[str]) -> Dict[str, Any]:
    payload = {"deleted": 0, "skipped": 0, "errors": []}
    normalized_saved_paths = {os.path.normcase(os.path.abspath(path)) for path in saved_paths}
    for item in delete_requests:
        path = str(item.get("local_path") or "")
        if not path:
            continue
        abs_path = os.path.abspath(path)
        if os.path.normcase(abs_path) in normalized_saved_paths:
            payload["skipped"] += 1
            continue
        try:
            if os.path.isfile(abs_path):
                os.remove(abs_path)
                payload["deleted"] += 1
            else:
                payload["skipped"] += 1
        except Exception as exc:
            payload["errors"].append(f"{os.path.basename(abs_path)}: {exc}")
    return payload


def _entry_payload_from_product(product: WebProductForm) -> Dict[str, Any]:
    return {
        "product_id": product.product_id,
        "ean": product.ean,
        "name": product.name,
        "type_name": product.type_name,
        "model": product.model,
        "color1": product.color1,
        "color2": product.color2,
        "color3": product.color3,
        "extra": product.extra,
    }


def _form_from_entry_payload(entry: Dict[str, Any]) -> WebProductForm:
    return WebProductForm(
        name=str(entry.get("name") or ""),
        type_name=str(entry.get("type_name") or ""),
        model=str(entry.get("model") or ""),
        color1=str(entry.get("color1") or ""),
        color2=str(entry.get("color2") or ""),
        color3=str(entry.get("color3") or ""),
        extra=str(entry.get("extra") or ""),
        ean=str(entry.get("ean") or ""),
        product_id=str(entry.get("product_id") or ""),
    )


def _output_identity(form: WebProductForm) -> tuple[str, str]:
    payload = normalized_product_payload(form, _active_product_field_settings())
    output_dir = build_product_directory(
        settings.l,
        payload["name"],
        payload["type_name"],
        payload["model"],
        payload["colors"],
        payload["extra"],
    )
    return os.path.normcase(os.path.abspath(output_dir)), str(payload["ean"] or "").upper()


def _should_migrate_existing_photos(
    existing_entry: Optional[Dict[str, Any]],
    product: WebProductForm,
) -> bool:
    if not existing_entry:
        return False
    return _output_identity(_form_from_entry_payload(existing_entry)) != _output_identity(product)


def _download_ftp_photo_source(
    photo: Dict[str, Any],
    fallback_ean: str,
    *,
    cache_scope: str = "",
) -> str:
    ftp_filename = os.path.basename(str(photo.get("ftp_filename") or ""))
    ftp_ean = str(photo.get("ean") or fallback_ean or "").strip()
    if not ftp_filename or not ftp_ean:
        return ""
    try:
        return cache_ftp_preview(ftp_ean, ftp_filename, cache_scope=cache_scope)
    except ValueError as exc:
        raise ValueError(f"Nie udalo sie pobrac pliku FTP {ftp_filename}: {exc}") from exc


def _same_existing_source(source_path: str, upload: WebUploadedSlot, photo: Dict[str, Any]) -> bool:
    upload_path = str(upload.source_path or "")
    if source_path and upload_path:
        try:
            return os.path.samefile(source_path, upload_path)
        except OSError:
            return os.path.normcase(os.path.abspath(source_path)) == os.path.normcase(
                os.path.abspath(upload_path)
            )
    ftp_filename = os.path.basename(str(photo.get("ftp_filename") or ""))
    return bool(ftp_filename and ftp_filename == os.path.basename(str(upload.original_filename or "")))


def _photo_source_labels(photo: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    if photo.get("local"):
        labels.append("LOCAL")
    if photo.get("ftp"):
        labels.append("FTP")
    if photo.get("sql"):
        labels.append("SQL")
    return labels or ["nieznane"]


def _photo_has_file_source(photo: Dict[str, Any]) -> bool:
    return bool(
        photo.get("path")
        or photo.get("filename")
        or photo.get("ftp_path")
        or photo.get("ftp_filename")
    )


def _existing_photo_conflicts(
    photos: List[Dict[str, Any]],
    uploaded_slots: List[WebUploadedSlot],
    delete_requests: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    uploaded_by_prefix = {str(slot.prefix): slot for slot in uploaded_slots}
    delete_prefixes = {str(item.get("prefix") or "") for item in delete_requests}
    conflicts: List[Dict[str, Any]] = []
    for photo in photos:
        if not _photo_has_file_source(photo):
            continue
        prefix = str(photo.get("prefix") or "").strip()
        if not prefix or prefix not in uploaded_by_prefix or prefix in delete_prefixes:
            continue
        if photo.get("ftp") and not photo.get("local"):
            continue
        source_path = str(photo.get("path") or "").strip()
        source_path = source_path if source_path and os.path.isfile(source_path) else ""
        upload = uploaded_by_prefix[prefix]
        if _same_existing_source(source_path, upload, photo):
            continue
        conflicts.append(
            {
                "prefix": prefix,
                "sources": _photo_source_labels(photo),
                "filename": photo.get("filename") or photo.get("ftp_filename") or photo.get("sql_value") or "",
            }
        )
    return conflicts


def _format_existing_photo_conflicts(conflicts: List[Dict[str, Any]]) -> str:
    parts = []
    for item in conflicts:
        sources = "/".join(str(source) for source in item.get("sources", []))
        parts.append(f"{item.get('prefix')} ({sources})")
    return (
        "Znaleziono juz istniejace zdjecia dla wpisanych danych w slotach: "
        f"{', '.join(parts)}. Wczytaj istniejace zdjecia albo usun wybrane sloty przed "
        "ponownym przetworzeniem."
    )


def _process_event_details(
    product: WebProductForm,
    uploaded_slots: List[WebUploadedSlot],
    delete_requests: List[Dict[str, Any]],
    **extra: Any,
) -> Dict[str, Any]:
    details: Dict[str, Any] = {
        "product_id": product.product_id,
        "ean": product.ean,
        "name": product.name,
        "type": product.type_name,
        "model": product.model,
        "colors": [product.color1, product.color2, product.color3],
        "extra": product.extra,
        "uploaded_slots": [slot.prefix for slot in uploaded_slots],
        "delete_slots": [str(item.get("prefix") or "") for item in delete_requests],
    }
    details.update(extra)
    return details


def _append_existing_photo_sources(
    *,
    existing_entry: Optional[Dict[str, Any]],
    product: WebProductForm,
    uploaded_slots: List[WebUploadedSlot],
    delete_requests: List[Dict[str, Any]],
    slot_by_prefix: Dict[str, Dict[str, str]],
    existing_photos: Optional[List[Dict[str, Any]]] = None,
    cache_scope: str = "",
) -> List[str]:
    """Add existing local/FTP photos that need to be processed by the web form."""

    source_entry = existing_entry or _entry_payload_from_product(product)
    if not source_entry:
        return []
    identity_changed = bool(existing_entry) and _should_migrate_existing_photos(existing_entry, product)
    occupied_prefixes = {slot.prefix for slot in uploaded_slots}
    delete_prefixes = {str(item.get("prefix") or "") for item in delete_requests}
    appended: List[str] = []
    photos = existing_photos
    if photos is None:
        photos = find_product_photos(
            source_entry,
            include_local=True,
            include_ftp=bool(config.CONFIG.get(ft, True)),
            include_sql=True,
        )
    for photo in photos:
        prefix = str(photo.get("prefix") or "").strip()
        path = str(photo.get("path") or "").strip()
        ftp_filename = os.path.basename(str(photo.get("ftp_filename") or ""))
        if not prefix or prefix in delete_prefixes:
            continue
        slot = slot_by_prefix.get(prefix, {"prefix": prefix, "label": prefix})
        label = str(slot.get("label") or prefix)
        filename_label = str(slot.get("filename_label") or "")
        source_path = path if path and os.path.isfile(path) else ""
        had_local_source = bool(source_path)
        needs_sql_update = bool(photo.get("sql_checked")) and not bool(photo.get("sql"))
        append_delete_request = False
        if prefix in occupied_prefixes:
            if identity_changed:
                delete_requests.append(
                    {
                        "prefix": prefix,
                        "label": label,
                        "local_path": source_path,
                        "ftp_filename": ftp_filename,
                        "sql": False,
                        "migration": True,
                    }
                )
                delete_prefixes.add(prefix)
            continue
        should_process = False
        if identity_changed and source_path:
            should_process = True
        elif source_path and bool(config.CONFIG.get(ft, True)) and not bool(photo.get("ftp")):
            should_process = True
            append_delete_request = True
        elif ftp_filename and not source_path:
            source_path = _download_ftp_photo_source(
                photo,
                str(source_entry.get("ean") or product.ean or ""),
                cache_scope=cache_scope,
            )
            should_process = bool(source_path and os.path.isfile(source_path))
            append_delete_request = should_process
        elif source_path and needs_sql_update:
            should_process = True
        if not should_process:
            continue
        if prefix not in occupied_prefixes and prefix not in delete_prefixes:
            uploaded_slots.append(
                WebUploadedSlot(
                    prefix=prefix,
                    label=label,
                    filename_label=filename_label,
                    source_path=source_path,
                    original_filename=ftp_filename or os.path.basename(source_path),
                )
            )
            occupied_prefixes.add(prefix)
            appended.append(prefix)
        if prefix not in delete_prefixes and (identity_changed or append_delete_request):
            delete_requests.append(
                {
                    "prefix": prefix,
                    "label": label,
                    "local_path": path if path and os.path.isfile(path) else "",
                    "ftp_filename": ftp_filename,
                    "sql": False,
                    "migration": identity_changed,
                    "ftp_backfill": bool(ftp_filename and not had_local_source),
                }
            )
            delete_prefixes.add(prefix)
    return appended


def _append_existing_photo_migrations(
    *,
    existing_entry: Optional[Dict[str, Any]],
    product: WebProductForm,
    uploaded_slots: List[WebUploadedSlot],
    delete_requests: List[Dict[str, Any]],
    slot_by_prefix: Dict[str, Dict[str, str]],
    existing_photos: Optional[List[Dict[str, Any]]] = None,
    cache_scope: str = "",
) -> List[str]:
    """Backward-compatible wrapper for tests and older call sites."""

    return _append_existing_photo_sources(
        existing_entry=existing_entry,
        product=product,
        uploaded_slots=uploaded_slots,
        delete_requests=delete_requests,
        slot_by_prefix=slot_by_prefix,
        existing_photos=existing_photos,
        cache_scope=cache_scope,
    )


def _append_pending_ftp_slots(
    *,
    product: WebProductForm,
    pending_ftp_slots: List[Dict[str, Any]],
    uploaded_slots: List[WebUploadedSlot],
    delete_requests: List[Dict[str, Any]],
    cache_scope: str = "",
) -> List[str]:
    """Download FTP-only selected slots so they can be saved like uploaded files."""

    occupied_prefixes = {slot.prefix for slot in uploaded_slots}
    appended: List[str] = []
    for item in pending_ftp_slots:
        prefix = str(item.get("prefix") or "")
        if not prefix or prefix in occupied_prefixes:
            continue
        ftp_filename = os.path.basename(str(item.get("filename") or ""))
        ftp_ean = str(item.get("ean") or product.ean or "").strip()
        try:
            source_path = cache_ftp_preview(ftp_ean, ftp_filename, cache_scope=cache_scope)
        except ValueError as exc:
            raise ValueError(
                f"Nie udalo sie pobrac pliku FTP {ftp_filename}: {exc}"
            ) from exc
        uploaded_slots.append(
            WebUploadedSlot(
                prefix=prefix,
                label=str(item.get("label") or prefix),
                filename_label=str(item.get("filename_label") or ""),
                source_path=source_path,
                original_filename=ftp_filename,
                content_fit=item.get("content_fit"),
            )
        )
        occupied_prefixes.add(prefix)
        appended.append(prefix)
        if ftp_filename:
            delete_requests.append(
                {
                    "prefix": prefix,
                    "label": str(item.get("label") or prefix),
                    "local_path": "",
                    "ftp_filename": ftp_filename,
                    "sql": False,
                    "ftp_backfill": False,
                }
            )
    return appended


def _read_log_tail(path: str, limit: int = 300) -> Dict[str, Any]:
    line_limit = max(1, min(2000, int(limit or 300)))
    log_path = Path(path)
    payload: Dict[str, Any] = {"path": str(log_path), "exists": log_path.exists(), "lines": []}
    if not log_path.exists():
        return payload
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            payload["lines"] = [_clean_log_line(line.rstrip("\r\n")) for line in handle.readlines()[-line_limit:]]
    except OSError as exc:
        payload["error"] = str(exc)
    return payload


ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
CONTROL_LOG_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HTTP_ACCESS_RE = re.compile(r'"[A-Z]+ [^"]+ HTTP/[0-9.]+"\s+(\d{3})\s+\w+')
PLAIN_LOG_START_RE = re.compile(r"^(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL):\s+", re.IGNORECASE)
TIMESTAMP_LOG_START_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2}")


def _clean_log_line(line: str) -> str:
    text = ANSI_ESCAPE_RE.sub("", str(line))
    return CONTROL_LOG_RE.sub("", text)


def _http_statuses(lines: List[str]) -> List[int]:
    statuses: List[int] = []
    for line in lines:
        for match in HTTP_ACCESS_RE.finditer(line):
            try:
                statuses.append(int(match.group(1)))
            except ValueError:
                pass
    return statuses


def _web_events_log_path() -> Path:
    return Path(settings.LOG_DIR) / "picorg_web_events.log"


def _safe_event_detail(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)


def _write_web_event(
    *,
    level: str,
    event: str,
    username: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    log_path = _web_events_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level_text = str(level or "INFO").strip().upper()
        event_text = _safe_event_detail(event).upper() or "WEB_EVENT"
        user_text = _safe_event_detail(username) or "unknown"
        message_text = _safe_event_detail(message)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] [USER: {user_text}] {level_text}: {event_text} - {message_text}\n")
            if details:
                handle.write(
                    "details: "
                    + json.dumps(details, ensure_ascii=False, sort_keys=True, default=str)
                    + "\n"
                )
    except OSError:
        pass


def _log_event_summary(line: str) -> str:
    text = _clean_log_line(line)
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    text = re.sub(r"^(DEBUG|ERROR|WARNING|WARN|INFO|CRITICAL):\s*", "", text, flags=re.IGNORECASE)
    return text.strip() or line.strip()


def _log_event_severity(source_key: str, lines: List[str]) -> str:
    text = "\n".join(lines)
    lowered = text.lower()
    first_line = lines[0] if lines else ""
    statuses = _http_statuses(lines)
    if statuses:
        max_status = max(statuses)
        if max_status >= 500:
            return "critical"
        if max_status >= 400:
            return "warning"
    if source_key == "web_events":
        level_match = re.search(
            r"\]\s*(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL):\s*",
            first_line,
            re.IGNORECASE,
        )
        level = level_match.group(1).upper() if level_match else ""
        if level in {"CRITICAL", "ERROR"}:
            return "critical"
        if level in {"WARNING", "WARN"}:
            return "warning"
        return "info"
    if source_key == "web_err" and re.search(
        r"\b(CRITICAL|ERROR|Traceback|Exception|failed)\b", text, re.IGNORECASE
    ):
        return "critical"
    if source_key == "errors":
        if "traceback" in lowered or "exception" in lowered or "web " in lowered:
            return "critical"
        return "warning"
    if any(marker in lowered for marker in (" error", "blad", "failed", "exception")):
        return "warning"
    return "info"


def _parse_log_events(log_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    key = str(log_payload.get("key") or "")
    label = str(log_payload.get("label") or key)
    path = str(log_payload.get("path") or "")
    events: List[Dict[str, Any]] = []
    current: Optional[List[str]] = None

    def _append_current() -> None:
        nonlocal current
        if not current:
            return
        first_line = current[0]
        timestamp_match = re.match(r"^\[([^\]]+)\]", first_line)
        timestamp = timestamp_match.group(1) if timestamp_match else ""
        digest = hashlib.sha1(f"{key}|{first_line}|{len(current)}".encode("utf-8")).hexdigest()
        severity = _log_event_severity(key, current)
        events.append(
            {
                "id": digest,
                "source": key,
                "source_label": label,
                "path": path,
                "time": timestamp,
                "order": len(events),
                "severity": severity,
                "summary": _log_event_summary(first_line),
                "lines": list(current),
            }
        )
        current = None

    for raw_line in log_payload.get("lines", []) or []:
        line = _clean_log_line(str(raw_line))
        if not line.strip():
            continue
        if TIMESTAMP_LOG_START_RE.match(line) or PLAIN_LOG_START_RE.match(line):
            _append_current()
            current = [line]
        elif current is not None:
            current.append(line)
        else:
            current = [line]
    _append_current()
    return events


def _logs_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest_critical = next((event for event in events if event.get("severity") == "critical"), None)
    latest_warning = next((event for event in events if event.get("severity") == "warning"), None)
    return {
        "critical_count": sum(1 for event in events if event.get("severity") == "critical"),
        "warning_count": sum(1 for event in events if event.get("severity") == "warning"),
        "latest_critical_id": latest_critical.get("id") if latest_critical else "",
        "latest_warning_id": latest_warning.get("id") if latest_warning else "",
    }


def _log_targets() -> List[Dict[str, Any]]:
    return [
        {"key": "web_events", "label": "Zdarzenia web", "path": _web_events_log_path()},
        {"key": "errors", "label": "Bledy i exception", "path": settings.AM},
        {"key": "changes", "label": "Zmiany systemowe", "path": settings.BM},
        {"key": "web_out", "label": "Web stdout", "path": Path(settings.LOG_DIR) / "picorg_web_out.log"},
        {"key": "web_err", "label": "Web stderr", "path": Path(settings.LOG_DIR) / "picorg_web_err.log"},
    ]


def _is_system_change_event(event: Dict[str, Any]) -> bool:
    if event.get("source") != "changes":
        return True
    raw_text = "\n".join(str(line) for line in event.get("lines", [])).lower()
    plain_text = unicodedata.normalize("NFKD", raw_text).encode("ascii", "ignore").decode("ascii")
    text = f"{raw_text}\n{plain_text}"
    product_markers = (
        "excel entry",
        "wpis ean",
        " ean ",
        "added value",
        "removed value",
        "dodano wartosc",
        "usunieto wartosc",
        "added/modified image",
        "added/modified file",
        "dodano/zmodyfikowano obraz",
        "dodano/zmodyfikowano plik",
        "renamed file",
        "wysylanie pliku",
        "wysylanie plikow",
        "uploading file",
        "sending files",
    )
    if any(marker in text for marker in product_markers):
        return False
    system_markers = (
        "settings",
        "ustawien",
        "ustawienie",
        "config",
        "konfigur",
        "sql",
        "index",
        "admin",
        "administrator",
        "slot_def",
        "field definition",
        "photo field",
        "pola zdjec",
        "pol zdjec",
        "code_check",
        "ui_check",
        "connection",
        "polaczenie",
        "runtime",
        "local_settings",
    )
    return any(marker in text for marker in system_markers)


def _is_relevant_web_runtime_event(event: Dict[str, Any]) -> bool:
    if event.get("source") not in {"web_out", "web_err"}:
        return True
    text = "\n".join(str(line) for line in event.get("lines", [])).lower()
    routine_markers = (
        "started server process",
        "waiting for application startup",
        "application startup complete",
        "uvicorn running on",
        "press ctrl+c to quit",
    )
    if any(marker in text for marker in routine_markers):
        return False
    statuses = _http_statuses([str(line) for line in event.get("lines", [])])
    if statuses and max(statuses) < 500:
        return False
    return True


def _is_visible_log_event(event: Dict[str, Any]) -> bool:
    return _is_system_change_event(event) and _is_relevant_web_runtime_event(event)


def _log_payloads(limit: int) -> List[Dict[str, Any]]:
    logs: List[Dict[str, Any]] = []
    for target in _log_targets():
        payload = {
            "key": target["key"],
            "label": target["label"],
            **_read_log_tail(target["path"], limit),
        }
        events = [event for event in _parse_log_events(payload) if _is_visible_log_event(event)]
        events.reverse()
        payload["events"] = events
        payload["event_count"] = len(events)
        payload["critical_count"] = sum(1 for event in events if event.get("severity") == "critical")
        payload["warning_count"] = sum(1 for event in events if event.get("severity") == "warning")
        logs.append(payload)
    return logs


def _clear_log_files() -> Dict[str, Any]:
    cleared: List[str] = []
    errors: List[str] = []
    for target in _log_targets():
        path = Path(target["path"])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            cleared.append(str(path))
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    return {"cleared": cleared, "errors": errors}


def _logs_response(limit: int) -> Dict[str, Any]:
    logs = _log_payloads(limit)
    events = [event for log in logs for event in log.get("events", [])]
    events.sort(
        key=lambda item: (str(item.get("time") or ""), int(item.get("order") or 0)),
        reverse=True,
    )
    return {"logs": logs, "events": events, "summary": _logs_summary(events)}


def _snapshot_entry_payload(form: _ProcessFormSnapshot) -> Dict[str, str]:
    return {
        "product_id": str(form.get("product_id") or ""),
        "name": str(form.get("name") or ""),
        "type_name": str(form.get("type_name") or ""),
        "model": str(form.get("model") or ""),
        "color1": str(form.get("color1") or ""),
        "color2": str(form.get("color2") or ""),
        "color3": str(form.get("color3") or ""),
        "extra": str(form.get("extra") or ""),
        "ean": str(form.get("ean") or ""),
    }


def _process_entry_label(entry: Dict[str, Any]) -> str:
    colors = " / ".join(
        str(entry.get(key) or "").strip()
        for key in ("color1", "color2", "color3")
        if str(entry.get(key) or "").strip()
    )
    parts = [
        str(entry.get("name") or "").strip(),
        str(entry.get("type_name") or "").strip(),
        str(entry.get("model") or "").strip(),
        colors,
        str(entry.get("extra") or "").strip(),
    ]
    suffix = str(entry.get("ean") or entry.get("product_id") or "").strip()
    label = " | ".join(part for part in parts if part)
    return f"{label} - {suffix}" if label and suffix else label or suffix or "bez identyfikatora"


def _process_warning_messages(payload: Dict[str, Any]) -> List[str]:
    messages: List[str] = []
    ftp_payload = payload.get("ftp") if isinstance(payload.get("ftp"), dict) else {}
    sql_payload = payload.get("sql") if isinstance(payload.get("sql"), dict) else {}
    local_delete = payload.get("local_delete") if isinstance(payload.get("local_delete"), dict) else {}
    if ftp_payload.get("error"):
        messages.append(f"FTP: {ftp_payload.get('error')}")
    if sql_payload.get("error"):
        messages.append(f"SQL: {sql_payload.get('error')}")
    local_errors = local_delete.get("errors") if isinstance(local_delete, dict) else []
    if local_errors:
        messages.append("Usuwanie lokalne: " + "; ".join(str(item) for item in local_errors))
    skipped = payload.get("skipped_slots") or []
    if skipped:
        messages.append("Pominiete sloty: " + ", ".join(str(item) for item in skipped))
    return messages


def _process_upload_snapshot(
    *,
    username: str,
    cache_scope: str,
    form: _ProcessFormSnapshot,
    progress: Optional[
        Callable[[int, str, List[Dict[str, Any]], Optional[Dict[str, Any]]], None]
    ] = None,
) -> Dict[str, Any]:
    def mark(
        percent: int,
        label: str,
        *,
        current_key: str = "",
        current_label: str = "",
    ) -> None:
        if progress:
            current_stage = None
            if current_key:
                current_stage = {
                    "key": current_key,
                    "label": current_label or label,
                    "started_at": time.time(),
                    "elapsed_ms": 0,
                    "running": True,
                }
            progress(percent, label, list(timings), current_stage)

    process_started = time.perf_counter()
    timings: List[Dict[str, Any]] = []
    stage_started = time.perf_counter()
    mark(4, "Przygotowanie danych", current_key="prepare", current_label="Przygotowanie danych i slotow")
    slots = slot_definitions_from_config(config.CONFIG)
    slot_by_prefix = {slot["prefix"]: slot for slot in slots}
    uploaded_slots: List[WebUploadedSlot] = []
    delete_requests: List[Dict[str, Any]] = []
    pending_ftp_slots: List[Dict[str, Any]] = []
    explicit_slot_prefixes: Set[str] = set()
    product: Optional[WebProductForm] = None
    field_settings = _active_product_field_settings()
    antivirus_scan_result: Dict[str, Any] = {"enabled": False, "scanned": 0, "skipped": 0, "items": []}
    try:
        for prefix, slot in slot_by_prefix.items():
            if str(form.get(f"delete_slot_{prefix}") or "") == "1":
                delete_item: Dict[str, Any] = {
                    "prefix": prefix,
                    "label": slot["label"],
                    "local_path": "",
                    "ftp_filename": os.path.basename(str(form.get(f"delete_ftp_slot_{prefix}") or "")),
                    "sql": str(form.get(f"delete_sql_slot_{prefix}") or "") == "1",
                }
                local_token = str(form.get(f"delete_local_slot_{prefix}") or "").strip()
                if local_token:
                    delete_item["local_path"] = _path_from_file_token(
                        local_token,
                        require_exists=False,
                    )
                delete_requests.append(delete_item)
            token = str(form.get(f"existing_slot_{prefix}") or "").strip()
            if token:
                source_path = _path_from_file_token(token)
                original_filename = _safe_upload_name(
                    str(form.get(f"existing_slot_name_{prefix}") or ""),
                    os.path.basename(source_path),
                )
                preprocessed = str(form.get(f"existing_slot_preprocessed_{prefix}") or "") == "1"
                explicit_slot_prefixes.add(prefix)
                uploaded_slots.append(
                    WebUploadedSlot(
                        prefix=prefix,
                        label=slot["label"],
                        filename_label=slot.get("filename_label", ""),
                        source_path=source_path,
                        original_filename=original_filename,
                        content_fit=_optional_form_bool(form, f"slot_fit_{prefix}"),
                        preprocessed=preprocessed,
                    )
                )
                continue
            ftp_filename = os.path.basename(str(form.get(f"existing_ftp_slot_{prefix}") or ""))
            if ftp_filename:
                explicit_slot_prefixes.add(prefix)
                pending_ftp_slots.append(
                    {
                        "prefix": prefix,
                        "label": slot["label"],
                        "filename_label": slot.get("filename_label", ""),
                        "filename": ftp_filename,
                        "ean": str(form.get(f"existing_ftp_ean_{prefix}") or ""),
                        "content_fit": _optional_form_bool(form, f"slot_fit_{prefix}"),
                    }
                )
                continue
            value = form.get(f"slot_{prefix}")
            if not isinstance(value, _QueuedUploadFile):
                continue
            explicit_slot_prefixes.add(prefix)
            uploaded_slots.append(
                WebUploadedSlot(
                    prefix=prefix,
                    label=slot["label"],
                    filename_label=slot.get("filename_label", ""),
                    source_path=value.path,
                    original_filename=value.filename,
                    content_fit=_optional_form_bool(form, f"slot_fit_{prefix}"),
                )
            )
        product = WebProductForm(
            name=str(form.get("name") or ""),
            type_name=str(form.get("type_name") or ""),
            model=str(form.get("model") or ""),
            color1=str(form.get("color1") or ""),
            color2=str(form.get("color2") or ""),
            color3=str(form.get("color3") or ""),
            extra=str(form.get("extra") or ""),
            ean=str(form.get("ean") or ""),
            product_id=str(form.get("product_id") or ""),
        )
        product = effective_product_form(product, field_settings)
        errors = validate_product_form(product, field_settings)
        if errors:
            raise ValueError(" ".join(errors))
        timings.append(
            _timing_item(
                "prepare",
                "Przygotowanie danych i slotow",
                stage_started,
                uploaded=len(uploaded_slots),
                deleted=len(delete_requests),
                ftp_pending=len(pending_ftp_slots),
            )
        )
        stage_started = time.perf_counter()
        mark(10, "Wyszukiwanie wpisu", current_key="entry_lookup", current_label="Wyszukanie istniejacego wpisu")
        existing_entry = None
        if product.product_id.strip():
            existing_entry = find_entry_by_identity(product_id=product.product_id)
        if existing_entry is None and product.ean.strip() and product.ean.strip().upper() != "BRAK-EAN":
            existing_entry = find_entry_by_identity(ean=product.ean)
        if existing_entry:
            preserved_product_id = product.product_id or str(existing_entry.get("product_id") or "")
            preserved_ean = product.ean
            if field_settings["ean"]["enabled"]:
                preserved_ean = preserved_ean or str(existing_entry.get("ean") or "")
            if preserved_product_id != product.product_id or preserved_ean != product.ean:
                product = WebProductForm(
                    name=product.name,
                    type_name=product.type_name,
                    model=product.model,
                    color1=product.color1,
                    color2=product.color2,
                    color3=product.color3,
                    extra=product.extra,
                    ean=preserved_ean,
                    product_id=preserved_product_id,
                )
        timings.append(
            _timing_item(
                "entry_lookup",
                "Wyszukanie istniejacego wpisu",
                stage_started,
                found=bool(existing_entry),
            )
        )
        stage_started = time.perf_counter()
        mark(20, "Sprawdzanie zdjec", current_key="photo_scan", current_label="Sprawdzenie istniejacych zdjec")
        _append_pending_ftp_slots(
            product=product,
            pending_ftp_slots=pending_ftp_slots,
            uploaded_slots=uploaded_slots,
            delete_requests=delete_requests,
            cache_scope=cache_scope,
        )
        photo_lookup_entry = existing_entry or _entry_payload_from_product(product)
        include_sql_in_existing_photo_scan = existing_entry is not None
        existing_photos = find_product_photos(
            photo_lookup_entry,
            include_local=True,
            include_ftp=bool(config.CONFIG.get(ft, True)),
            include_sql=include_sql_in_existing_photo_scan,
        )
        existing_file_photos = [photo for photo in existing_photos if _photo_has_file_source(photo)]
        if existing_entry is None:
            conflicts = _existing_photo_conflicts(
                existing_file_photos,
                uploaded_slots,
                delete_requests,
            )
            if conflicts:
                raise ValueError(_format_existing_photo_conflicts(conflicts))
        migrated_prefixes = _append_existing_photo_migrations(
            existing_entry=existing_entry,
            product=product,
            uploaded_slots=uploaded_slots,
            delete_requests=delete_requests,
            slot_by_prefix=slot_by_prefix,
            existing_photos=existing_photos,
            cache_scope=cache_scope,
        )
        if existing_entry is None and existing_file_photos and not uploaded_slots and not delete_requests:
            raise ValueError(
                _format_existing_photo_conflicts(
                    [
                        {
                            "prefix": photo.get("prefix"),
                            "sources": _photo_source_labels(photo),
                        }
                        for photo in existing_file_photos
                    ]
                )
            )
        timings.append(
            _timing_item(
                "photo_scan",
                "Sprawdzenie istniejacych zdjec",
                stage_started,
                found=len(existing_photos),
                migrated=len(migrated_prefixes),
            )
        )
        antivirus_scan_result = _uploaded_scan_summary(uploaded_slots)
        if antivirus_scan_result.get("enabled") or antivirus_scan_result.get("items"):
            timings.append(
                {
                    "key": "antivirus_scan",
                    "label": "Skan antywirusowy uploadu",
                    "elapsed_ms": sum(
                        int(item.get("elapsed_ms") or 0)
                        for item in antivirus_scan_result.get("items", [])
                    ),
                    "details": {
                        "enabled": bool(antivirus_scan_result.get("enabled")),
                        "scanned": int(antivirus_scan_result.get("scanned") or 0),
                        "skipped": int(antivirus_scan_result.get("skipped") or 0),
                    },
                }
            )
        stage_started = time.perf_counter()
        mark(34, "Przetwarzanie plikow", current_key="local_files", current_label="Zapis/przetwarzanie plikow lokalnych")
        result = process_web_uploads(
            base_output_dir=settings.l,
            form=product,
            uploaded_slots=uploaded_slots,
            options=processing_options_from_config(config.CONFIG),
            allow_empty=True,
            field_settings=field_settings,
        )
        timings.append(
            _timing_item(
                "local_files",
                "Zapis/przetwarzanie plikow lokalnych",
                stage_started,
                saved=len(result.saved_files),
            )
        )
        stage_started = time.perf_counter()
        mark(60, "Usuwanie lokalne", current_key="local_delete", current_label="Usuwanie lokalne")
        saved_paths = {os.path.abspath(item.path) for item in result.saved_files}
        local_delete_result = _delete_local_files(delete_requests, saved_paths)
        timings.append(
            _timing_item(
                "local_delete",
                "Usuwanie lokalne",
                stage_started,
                deleted=local_delete_result.get("deleted", 0),
                skipped=local_delete_result.get("skipped", 0),
            )
        )
        stage_started = time.perf_counter()
        mark(70, "Synchronizacja FTP", current_key="ftp", current_label="Synchronizacja FTP")
        ftp_backfill_prefixes = {
            str(item.get("prefix") or "")
            for item in delete_requests
            if item.get("ftp_backfill")
        }
        skip_upload_prefixes = _ftp_skip_upload_prefixes(
            result,
            existing_file_photos,
            explicit_prefixes=explicit_slot_prefixes,
            migrated_prefixes=(
                set(migrated_prefixes)
                if _should_migrate_existing_photos(existing_entry, product)
                else set()
            ),
            ftp_backfill_prefixes=ftp_backfill_prefixes,
        )
        ftp_delete_candidates = [
            item.get("ftp_filename", "")
            for item in delete_requests
            if not item.get("ftp_backfill")
        ]
        ftp_delete_candidates.extend(
            _ftp_replacement_delete_candidates(
                result,
                existing_file_photos,
                explicit_prefixes=explicit_slot_prefixes,
            )
        )
        ftp_result = _sync_result_to_ftp(
            result,
            ftp_delete_candidates,
            skip_upload_prefixes=skip_upload_prefixes,
        )
        timings.append(
            _timing_item(
                "ftp",
                "Synchronizacja FTP",
                stage_started,
                uploaded=ftp_result.get("uploaded", 0),
                deleted=ftp_result.get("deleted", 0),
                skipped=len(skip_upload_prefixes),
            )
        )
        stage_started = time.perf_counter()
        mark(80, "Czyszczenie cache FTP", current_key="ftp_cache", current_label="Czyszczenie cache FTP")
        changed_ftp_names = {
            _remote_name_for_output(str(item.filename or ""))
            for item in result.saved_files
            if getattr(item, "filename", "")
        }
        changed_ftp_names.update(
            os.path.basename(str(name or ""))
            for name in ftp_delete_candidates
            if os.path.basename(str(name or ""))
        )
        changed_ftp_names.discard("")
        ftp_cache_result = invalidate_ftp_preview_cache(
            result.ean,
            changed_ftp_names,
            cache_scope=cache_scope,
        )
        timings.append(
            _timing_item(
                "ftp_cache",
                "Czyszczenie cache FTP",
                stage_started,
                deleted=ftp_cache_result.get("deleted", 0),
            )
        )
        stage_started = time.perf_counter()
        mark(88, "Aktualizacja SQL", current_key="sql", current_label="Aktualizacja SQL")
        sql_result = _sync_result_to_sql(
            result,
            clear_prefixes={
                str(item.get("prefix") or "")
                for item in delete_requests
                if item.get("sql") or item.get("ftp_filename") or item.get("local_path")
            },
        )
        timings.append(
            _timing_item(
                "sql",
                "Aktualizacja SQL",
                stage_started,
                updated=sql_result.get("updated", 0),
                cleared=sql_result.get("cleared", 0),
                skipped=bool(sql_result.get("skipped")),
            )
        )
        stage_started = time.perf_counter()
        mark(94, "Sprzatanie cache", current_key="upload_cache", current_label="Sprzatanie cache uploadu")
        upload_cache_result = _delete_upload_cache_files(
            [
                str(slot.source_path or "")
                for slot in uploaded_slots
                if _is_upload_cache_path(str(slot.source_path or ""))
            ]
        )
        timings.append(
            _timing_item(
                "upload_cache",
                "Sprzatanie cache uploadu",
                stage_started,
                deleted=upload_cache_result.get("deleted", 0),
                skipped=upload_cache_result.get("skipped", 0),
            )
        )
        stage_started = time.perf_counter()
        mark(96, "Zapis wpisu", current_key="entry_save", current_label="Zapis wpisu produktu")
        entry_result = save_web_entry(_entry_payload_from_product(product))
        timings.append(_timing_item("entry_save", "Zapis wpisu produktu", stage_started))
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        details: Dict[str, Any] = {"status_code": exc.status_code}
        if product is not None:
            details.update(_process_event_details(product, uploaded_slots, delete_requests))
        _write_web_event(
            level="warning" if exc.status_code < 500 else "error",
            event="PROCESS_REJECTED",
            username=username,
            message=detail,
            details=details,
        )
        raise
    except ValueError as exc:
        details = {}
        if product is not None:
            details = _process_event_details(product, uploaded_slots, delete_requests)
        _write_web_event(
            level="warning",
            event="PROCESS_REJECTED",
            username=username,
            message=str(exc),
            details=details,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if form.temp_dir:
            shutil.rmtree(form.temp_dir, ignore_errors=True)

    payload = _result_payload(result)
    payload["entry"] = entry_result
    payload["migrated_slots"] = migrated_prefixes
    payload["deleted_slots"] = delete_requests
    payload["ftp"] = ftp_result
    payload["ftp_cache"] = ftp_cache_result
    payload["upload_cache"] = upload_cache_result
    payload["sql"] = sql_result
    payload["local_delete"] = local_delete_result
    payload["antivirus_scan"] = antivirus_scan_result
    stage_started = time.perf_counter()
    mark(98, "Odswiezanie indeksu", current_key="file_index", current_label="Odswiezenie indeksu lokalnego")
    payload["file_index"] = refresh_file_index()
    timings.append(_timing_item("file_index", "Odswiezenie indeksu lokalnego", stage_started))
    payload["timing"] = _timing_payload(timings, process_started)
    payload["show_timing_details"] = _show_timing_details()
    record_history(
        username=username,
        action="process",
        ean=product.ean,
        product_id=entry_result.get("product_id", "") if isinstance(entry_result, dict) else "",
        summary=(
            "Zapisano usuniecia produktu."
            if delete_requests and not result.saved_files
            else "Zsynchronizowano produkt bez zmian w plikach."
            if not delete_requests and not result.saved_files
            else "Przetworzono pliki produktu."
        ),
        details={
            "saved_files": payload["saved_files"],
            "deleted_slots": delete_requests,
            "migrated_slots": migrated_prefixes,
            "ftp": ftp_result,
            "ftp_cache": ftp_cache_result,
            "upload_cache": upload_cache_result,
            "antivirus_scan": antivirus_scan_result,
            "sql": sql_result,
            "local_delete": local_delete_result,
            "output_dir": payload["output_dir"],
            "timing": payload["timing"],
            "entry": entry_result.get("entry", {}) if isinstance(entry_result, dict) else {},
        },
    )
    event_level = "info"
    event_name = "PROCESS_COMPLETED"
    if (
        ftp_result.get("error")
        or sql_result.get("error")
        or (local_delete_result.get("errors") if isinstance(local_delete_result, dict) else [])
        or result.skipped_slots
    ):
        event_level = "warning"
        event_name = "PROCESS_COMPLETED_WITH_WARNINGS"
    _write_web_event(
        level=event_level,
        event=event_name,
        username=username,
        message=(
            f"Zapisano {len(result.saved_files)} plikow, "
            f"usunieto lokalnie {local_delete_result.get('deleted', 0)}."
        ),
        details=_process_event_details(
            product,
            uploaded_slots,
            delete_requests,
            saved_files=[item.filename for item in result.saved_files],
            skipped_slots=result.skipped_slots,
            migrated_slots=migrated_prefixes,
            ftp=ftp_result,
            ftp_cache=ftp_cache_result,
            upload_cache=upload_cache_result,
            antivirus_scan=antivirus_scan_result,
            sql=sql_result,
            local_delete=local_delete_result,
        ),
    )
    return payload


def _exception_message(exc: BaseException) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        return detail if isinstance(detail, str) else str(detail)
    return str(exc) or exc.__class__.__name__


def _cleanup_process_jobs(now: Optional[float] = None) -> None:
    cutoff = (time.time() if now is None else now) - _PROCESS_JOB_RETENTION_SECONDS
    with _PROCESS_JOBS_LOCK:
        for job_id, job in list(_PROCESS_JOBS.items()):
            if job.get("status") not in {"completed", "failed"}:
                continue
            if float(job.get("finished_at") or 0) < cutoff:
                _PROCESS_JOBS.pop(job_id, None)


def _process_job_payload(job: Dict[str, Any], *, include_result: bool = True) -> Dict[str, Any]:
    payload = {
        "job_id": job.get("id", ""),
        "status": job.get("status", "queued"),
        "username": job.get("username", ""),
        "created_at": job.get("created_at", 0),
        "created_time": job.get("created_time", ""),
        "started_at": job.get("started_at", 0),
        "finished_at": job.get("finished_at", 0),
        "entry": dict(job.get("entry") or {}),
        "entry_label": job.get("entry_label", ""),
        "progress": int(job.get("progress") or 0),
        "progress_label": job.get("progress_label", ""),
        "queue_position": int(job.get("queue_position") or 0),
        "timing": _process_job_timing(job),
        "error": job.get("error", ""),
        "warning_messages": list(job.get("warning_messages") or []),
    }
    if include_result and job.get("result") is not None:
        payload["result"] = job.get("result")
    return payload


def _process_job_timing(job: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    now_value = time.time() if now is None else float(now)
    started_at = float(job.get("started_at") or 0)
    finished_at = float(job.get("finished_at") or 0)
    end_at = finished_at if finished_at else now_value
    total_ms = int(max(0, end_at - started_at) * 1000) if started_at else 0
    stages = [dict(stage) for stage in (job.get("timing_stages") or []) if isinstance(stage, dict)]
    current = job.get("current_stage") if isinstance(job.get("current_stage"), dict) else None
    if current and not finished_at:
        current_stage = dict(current)
        current_started = float(current_stage.get("started_at") or 0)
        if current_started:
            current_stage["elapsed_ms"] = int(max(0, now_value - current_started) * 1000)
        current_stage["running"] = True
        stages.append(current_stage)
    return {"total_ms": total_ms, "stages": stages}


def _set_process_job_progress(
    job_id: str,
    percent: int,
    label: str,
    stages: Optional[List[Dict[str, Any]]] = None,
    current_stage: Optional[Dict[str, Any]] = None,
) -> None:
    value = max(0, min(100, int(percent or 0)))
    with _PROCESS_JOBS_LOCK:
        job = _PROCESS_JOBS.get(job_id)
        if not job:
            return
        job["progress"] = value
        job["progress_label"] = str(label or "")
        if stages is not None:
            job["timing_stages"] = [dict(stage) for stage in stages if isinstance(stage, dict)]
        if current_stage is not None:
            job["current_stage"] = dict(current_stage)


def _queue_process_job(
    *,
    username: str,
    cache_scope: str,
    form: _ProcessFormSnapshot,
) -> Dict[str, Any]:
    _cleanup_process_jobs()
    job_id = secrets.token_hex(8)
    entry = _snapshot_entry_payload(form)
    created_at = time.time()
    job = {
        "id": job_id,
        "status": "queued",
        "username": username,
        "cache_scope": cache_scope,
        "form": form,
        "entry": entry,
        "entry_label": _process_entry_label(entry),
        "created_at": created_at,
        "created_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at)),
        "started_at": 0.0,
        "finished_at": 0.0,
        "result": None,
        "progress": 0,
        "progress_label": "Oczekuje w kolejce",
        "timing_stages": [],
        "current_stage": None,
        "error": "",
        "warning_messages": [],
    }
    with _PROCESS_JOBS_LOCK:
        _PROCESS_JOBS[job_id] = job
    _PROCESS_EXECUTOR.submit(_run_process_job, job_id)
    return _process_job_payload(job, include_result=False)


def _run_process_job(job_id: str) -> None:
    with _PROCESS_JOBS_LOCK:
        job = _PROCESS_JOBS.get(job_id)
        if not job:
            return
        job["status"] = "running"
        job["started_at"] = time.time()
        job["progress"] = max(1, int(job.get("progress") or 0))
        job["progress_label"] = "Start zadania"
        username = str(job.get("username") or "")
        cache_scope = str(job.get("cache_scope") or "")
        form = job.get("form")
        entry = dict(job.get("entry") or {})
        entry_label = str(job.get("entry_label") or "")
    try:
        payload = _process_upload_snapshot(
            username=username,
            cache_scope=cache_scope,
            form=form,
            progress=lambda percent, label, stages, current_stage: _set_process_job_progress(
                job_id,
                percent,
                label,
                stages,
                current_stage,
            ),
        )
        warning_messages = _process_warning_messages(payload)
        with _PROCESS_JOBS_LOCK:
            job = _PROCESS_JOBS.get(job_id)
            if not job:
                return
            job["status"] = "completed"
            job["finished_at"] = time.time()
            job["result"] = payload
            job["progress"] = 100
            job["progress_label"] = "Zakonczono"
            job["timing_stages"] = payload.get("timing", {}).get("stages", [])
            job["current_stage"] = None
            job["warning_messages"] = warning_messages
            job.pop("form", None)
    except Exception as exc:
        message = _exception_message(exc)
        status_code = getattr(exc, "status_code", 500)
        _write_web_event(
            level="warning" if int(status_code or 500) < 500 else "error",
            event="PROCESS_JOB_FAILED",
            username=username,
            message=f"{entry_label}: {message}",
            details={"job_id": job_id, "entry": entry},
        )
        with _PROCESS_JOBS_LOCK:
            job = _PROCESS_JOBS.get(job_id)
            if not job:
                return
            job["status"] = "failed"
            job["finished_at"] = time.time()
            job["error"] = message
            job["progress_label"] = "Blad zadania"
            job["warning_messages"] = [message]
            job["current_stage"] = None
            job.pop("form", None)


def _process_job_for_user(job_id: str, username: str) -> Optional[Dict[str, Any]]:
    _cleanup_process_jobs()
    with _PROCESS_JOBS_LOCK:
        job = _PROCESS_JOBS.get(job_id)
        if not job or str(job.get("username") or "") != username:
            return None
        return dict(job)


def _process_jobs_for_user(username: str, limit: int = 20) -> List[Dict[str, Any]]:
    _cleanup_process_jobs()
    with _PROCESS_JOBS_LOCK:
        jobs = [
            dict(job)
            for job in _PROCESS_JOBS.values()
            if str(job.get("username") or "") == username
        ]
    jobs.sort(key=lambda item: float(item.get("created_at") or 0), reverse=True)
    return [_process_job_payload(job, include_result=False) for job in jobs[: max(1, min(100, limit))]]


def _active_process_jobs_snapshot() -> Dict[str, Any]:
    _cleanup_process_jobs()
    now = time.time()
    with _PROCESS_JOBS_LOCK:
        active_jobs = [
            dict(job)
            for job in _PROCESS_JOBS.values()
            if job.get("status") in {"queued", "running"}
        ]
    running = sorted(
        [job for job in active_jobs if job.get("status") == "running"],
        key=lambda item: float(item.get("started_at") or item.get("created_at") or 0),
    )
    queued = sorted(
        [job for job in active_jobs if job.get("status") == "queued"],
        key=lambda item: float(item.get("created_at") or 0),
    )
    ordered = running + queued
    payload_jobs: List[Dict[str, Any]] = []
    queued_position = 0
    for job in ordered:
        item = dict(job)
        if item.get("status") == "running":
            item["queue_position"] = 0
        else:
            queued_position += 1
            item["queue_position"] = queued_position
        payload_jobs.append(_process_job_payload(item, include_result=False))
    return {
        "jobs": payload_jobs,
        "current": payload_jobs[0] if payload_jobs and payload_jobs[0].get("status") == "running" else None,
        "active_count": len(payload_jobs),
        "queued_count": len(queued),
        "server_time": now,
    }


def _active_clients_log_path() -> Path:
    return Path(settings.LOG_DIR) / "web_active_clients.json"


def _clean_presence_client_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    cleaned = re.sub(r"[^0-9A-Za-z_.-]+", "", text)[:80]
    return cleaned


def _request_presence_client_id(request: Request) -> str:
    headers = getattr(request, "headers", {}) or {}
    value = headers.get(PRESENCE_CLIENT_ID_HEADER) if hasattr(headers, "get") else ""
    return _clean_presence_client_id(value)


def _active_client_key(item: Dict[str, Any]) -> str:
    client_id = _clean_presence_client_id(item.get("client_id"))
    if client_id:
        return "|".join(
            [
                str(item.get("username") or ""),
                "client",
                client_id,
            ]
        )
    return "|".join(
        [
            str(item.get("username") or ""),
            str(item.get("remote_address") or ""),
            str(item.get("user_agent") or ""),
        ]
    )


def _load_active_clients_from_disk_locked(now_value: float) -> None:
    global _ACTIVE_CLIENTS_LOADED
    if _ACTIVE_CLIENTS_LOADED:
        return
    _ACTIVE_CLIENTS_LOADED = True
    path = _active_clients_log_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, list):
        return
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            last_seen = float(item.get("last_seen_epoch") or 0)
        except (TypeError, ValueError):
            continue
        if last_seen and now_value - last_seen <= ACTIVE_CLIENT_MAX_AGE_SECONDS:
            _ACTIVE_CLIENTS[_active_client_key(item)] = item


def _prune_active_clients_locked(now_value: float) -> None:
    global _ACTIVE_CLIENTS_DIRTY
    expired = [
        key
        for key, item in _ACTIVE_CLIENTS.items()
        if now_value - float(item.get("last_seen_epoch") or 0) > ACTIVE_CLIENT_MAX_AGE_SECONDS
    ]
    for key in expired:
        _ACTIVE_CLIENTS.pop(key, None)
    if expired:
        _ACTIVE_CLIENTS_DIRTY = True


def _active_client_payload_locked(now_value: float) -> List[Dict[str, Any]]:
    _load_active_clients_from_disk_locked(now_value)
    _prune_active_clients_locked(now_value)
    clients = sorted(
        _ACTIVE_CLIENTS.values(),
        key=lambda item: float(item.get("last_seen_epoch") or 0),
        reverse=True,
    )[:100]
    return [dict(item) for item in clients]


def _flush_active_clients_locked(now_value: float, *, force: bool = False) -> None:
    global _ACTIVE_CLIENTS_DIRTY, _ACTIVE_CLIENTS_LAST_FLUSH
    if not _ACTIVE_CLIENTS_DIRTY and not force:
        return
    if not force and now_value - _ACTIVE_CLIENTS_LAST_FLUSH < ACTIVE_CLIENT_FLUSH_INTERVAL_SECONDS:
        return
    payload = _active_client_payload_locked(now_value)
    try:
        path = _active_clients_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
        _ACTIVE_CLIENTS_DIRTY = False
        _ACTIVE_CLIENTS_LAST_FLUSH = now_value
    except OSError:
        pass


def _active_clients_snapshot(now: Optional[float] = None) -> List[Dict[str, Any]]:
    now_value = time.time() if now is None else float(now)
    with _ACTIVE_CLIENTS_LOCK:
        clients = _active_client_payload_locked(now_value)
        _flush_active_clients_locked(now_value)
        return clients


def _remove_active_client(username: str, client_id: str, now: Optional[float] = None) -> int:
    global _ACTIVE_CLIENTS_DIRTY
    clean_username = str(username or "").strip()
    clean_client_id = _clean_presence_client_id(client_id)
    if not clean_username or not clean_client_id:
        return 0
    now_value = time.time() if now is None else float(now)
    removed = 0
    with _ACTIVE_CLIENTS_LOCK:
        _load_active_clients_from_disk_locked(now_value)
        _prune_active_clients_locked(now_value)
        for key, item in list(_ACTIVE_CLIENTS.items()):
            if (
                str(item.get("username") or "").strip() == clean_username
                and _clean_presence_client_id(item.get("client_id")) == clean_client_id
            ):
                _ACTIVE_CLIENTS.pop(key, None)
                removed += 1
        if removed:
            _ACTIVE_CLIENTS_DIRTY = True
            _flush_active_clients_locked(now_value, force=True)
    return removed


def _active_presence_enabled() -> bool:
    return bool(_security_settings().get("show_active_web_users", False))


def _active_presence_payload(
    clients: List[Dict[str, Any]],
    now: Optional[float] = None,
) -> Dict[str, Any]:
    if not _active_presence_enabled():
        return {"enabled": False, "users": []}
    now_value = time.time() if now is None else float(now)
    by_username: Dict[str, Dict[str, Any]] = {}
    for client in clients:
        username = str(client.get("username") or "").strip()
        if not username or username == "niezalogowany":
            continue
        if not _clean_presence_client_id(client.get("client_id")):
            continue
        try:
            last_seen_epoch = float(client.get("last_seen_epoch") or 0)
        except (TypeError, ValueError):
            last_seen_epoch = 0.0
        if now_value - last_seen_epoch > PRESENCE_CLIENT_MAX_AGE_SECONDS:
            continue
        existing = by_username.get(username)
        if existing and float(existing.get("last_seen_epoch") or 0) >= last_seen_epoch:
            continue
        by_username[username] = {
            "username": username,
            "last_seen": str(client.get("last_seen") or ""),
            "last_seen_epoch": last_seen_epoch,
        }
    users = sorted(
        by_username.values(),
        key=lambda item: float(item.get("last_seen_epoch") or 0),
        reverse=True,
    )[:100]
    return {"enabled": True, "users": users}


def _record_active_client(request: Request, status_code: int) -> None:
    global _ACTIVE_CLIENTS_DIRTY
    path_text = str(request.url.path or "")
    if path_text.startswith("/static/") or path_text in {
        "/api/health",
        "/api/logout",
        "/api/server/presence/leave",
    }:
        return
    try:
        username = _current_user(request) or ""
    except Exception:
        username = ""
    client = getattr(request, "client", None)
    headers = getattr(request, "headers", {}) or {}
    now_value = time.time()
    item = {
        "username": username or "niezalogowany",
        "remote_address": str(getattr(client, "host", "") or ""),
        "remote_port": int(getattr(client, "port", 0) or 0),
        "user_agent": str(headers.get("user-agent", "") if hasattr(headers, "get") else ""),
        "client_id": _request_presence_client_id(request),
        "method": str(request.method or ""),
        "path": path_text,
        "status_code": int(status_code or 0),
        "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_seen_epoch": now_value,
    }
    with _ACTIVE_CLIENTS_LOCK:
        _load_active_clients_from_disk_locked(now_value)
        _prune_active_clients_locked(now_value)
        _ACTIVE_CLIENTS[_active_client_key(item)] = item
        _ACTIVE_CLIENTS_DIRTY = True
        _flush_active_clients_locked(now_value)


def _optional_form_bool(form: Any, key: str) -> Optional[bool]:
    value = form.get(key)
    if value is None:
        return None
    return str(value).strip() == "1"


def _enrich_photo_payload(photos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for photo in photos:
        item = dict(photo)
        path = str(photo.get("path") or "")
        ftp_path = str(photo.get("ftp_path") or "")
        if path:
            token = _file_token(path)
            item["token"] = token
            item["file_version"] = _file_version(path)
            item["url"] = _versioned_file_url(path, "/api/file", token)
            item["thumb_url"] = _versioned_file_url(path, "/api/thumbnail", token)
        else:
            item["token"] = ""
            item["file_version"] = ""
            item["url"] = ""
            item["thumb_url"] = ""
        if ftp_path:
            ftp_token = _file_token(ftp_path)
            item["ftp_token"] = ftp_token
            item["ftp_file_version"] = _file_version(ftp_path)
            item["ftp_url"] = _versioned_file_url(ftp_path, "/api/file", ftp_token)
            item["ftp_thumb_url"] = _versioned_file_url(ftp_path, "/api/thumbnail", ftp_token)
        else:
            item["ftp_token"] = ""
            item["ftp_file_version"] = ""
            item["ftp_url"] = ""
            item["ftp_thumb_url"] = ""
        enriched.append(item)
    return enriched


def _run_due_sqlite_backups_once() -> Dict[str, Any]:
    settings_payload = storage_settings.load_backup_settings()
    slots = sqlite_backup.due_schedule_slots(settings_payload)
    if not slots:
        return {"created": 0, "slots": []}
    backup_dir = storage_settings.resolve_backup_dir()
    result = sqlite_backup.create_backup(
        storage_settings.resolve_sqlite_path(),
        backup_dir,
        reason="scheduled",
    )
    sqlite_backup.enforce_retention(backup_dir, settings_payload.get("max_copies", 10))
    updated = sqlite_backup.mark_schedule_slots_run(settings_payload, slots)
    storage_settings.save_backup_settings(updated)
    return {"created": 1, "slots": slots, "backup": result}


def _backup_scheduler_loop() -> None:
    while not _BACKUP_SCHEDULER_STOP.wait(60):
        try:
            _run_due_sqlite_backups_once()
        except Exception as exc:
            log_error(f"WEB scheduled SQLite backup failed: {exc}\n{traceback.format_exc()}")


def _start_backup_scheduler() -> None:
    global _BACKUP_SCHEDULER_THREAD
    if _BACKUP_SCHEDULER_THREAD is not None and _BACKUP_SCHEDULER_THREAD.is_alive():
        return
    _BACKUP_SCHEDULER_STOP.clear()
    _BACKUP_SCHEDULER_THREAD = threading.Thread(
        target=_backup_scheduler_loop,
        name="picorg-sqlite-backup-scheduler",
        daemon=True,
    )
    _BACKUP_SCHEDULER_THREAD.start()


def _stop_backup_scheduler() -> None:
    global _BACKUP_SCHEDULER_THREAD
    _BACKUP_SCHEDULER_STOP.set()
    thread = _BACKUP_SCHEDULER_THREAD
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)
    _BACKUP_SCHEDULER_THREAD = None


def create_app() -> FastAPI:
    """Create the LAN web backend."""

    app = FastAPI(title="PicOrgFTP-SQL Web", version=get_app_version())
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def _runtime_info() -> Dict[str, Any]:
        return {
            "base_dir": settings.AC,
            "processed_dir": settings.l,
            "config_path": config.CONFIG_PATH,
            "warning": settings.BASE_DIR_OVERRIDE_WARNING,
        }

    @app.middleware("http")
    async def _log_unhandled_web_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            log_error(
                f"WEB {request.method} {request.url.path}: {exc}\n{traceback.format_exc()}"
            )
            raise

    @app.middleware("http")
    async def _guard_mutating_requests(request: Request, call_next):
        try:
            _validate_mutating_request(request)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)

    @app.middleware("http")
    async def _guard_rate_limits(request: Request, call_next):
        try:
            _check_rate_limit(request)
        except HTTPException as exc:
            return JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
                headers=getattr(exc, "headers", None),
            )
        return await call_next(request)

    @app.middleware("http")
    async def _add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'",
        )
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    @app.middleware("http")
    async def _track_active_clients(request: Request, call_next):
        response = await call_next(request)
        _record_active_client(request, getattr(response, "status_code", 0))
        return response

    @app.on_event("startup")
    def _startup() -> None:
        os.environ.setdefault("PICORGFTP_SQL_HEADLESS", "1")
        runtime_info = initialize_application_runtime(interactive=False)
        app.state.runtime_info = runtime_info
        cleanup_web_ftp_cache(force=True)
        cleanup_web_upload_cache(force=True)
        _start_backup_scheduler()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        _stop_backup_scheduler()
        with _ACTIVE_CLIENTS_LOCK:
            _flush_active_clients_locked(time.time(), force=True)

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {
            "ok": True,
            "version": get_display_version(),
            "time": datetime.now().isoformat(timespec="seconds"),
        }

    @app.get("/")
    def index(request: Request) -> Response:
        if _auth_enabled() and not _current_user(request):
            return RedirectResponse("/login", status_code=303)
        return _static_file("index.html")

    @app.get("/login")
    def login_page(request: Request) -> Response:
        if not _auth_enabled():
            return RedirectResponse("/", status_code=303)
        if _current_user(request):
            return RedirectResponse("/", status_code=303)
        return _static_file("login.html")

    @app.post("/api/login")
    async def login(request: Request) -> JSONResponse:
        form = await request.form()
        username = str(form.get("username") or "").strip()
        password = str(form.get("password") or "")
        auth_result = authenticate_login(
            username,
            password,
            remote_address=_request_remote_address(request),
            user_agent=str(request.headers.get("user-agent") or ""),
        )
        user = auth_result.get("user") if isinstance(auth_result.get("user"), dict) else None
        if not auth_result.get("ok"):
            failed_count = int(auth_result.get("failed_login_count") or (user or {}).get("failed_login_count") or 0)
            locked = bool((user or {}).get("locked"))
            reason = str(auth_result.get("reason") or "bad_password")
            level = "WARNING"
            if locked and (user or {}).get("lock_manual"):
                message = "Konto administratora zablokowane po blednych probach logowania."
            elif locked:
                message = "Konto zablokowane czasowo po blednych probach logowania."
            elif failed_count > 1:
                message = "Kolejna bledna proba logowania."
            else:
                message = "Bledna proba logowania."
            _write_web_event(
                level=level,
                event="login_failed",
                username=username or "unknown",
                message=message,
                details={
                    "reason": reason,
                    "failed_login_count": failed_count,
                    "limit": auth_result.get("limit"),
                    "locked": locked,
                    "lock_manual": bool((user or {}).get("lock_manual")),
                    "lock_expires_at": (user or {}).get("lock_expires_at", ""),
                    "remote_address": _request_remote_address(request),
                    "user_agent": str(request.headers.get("user-agent") or "")[:200],
                },
            )
            if locked and (user or {}).get("lock_manual"):
                raise HTTPException(
                    status_code=423,
                    detail="Konto jest zablokowane. Odblokuj je w panelu startowym WEB.",
                )
            if locked:
                until = str((user or {}).get("lock_expires_at") or "")
                suffix = f" do {until}" if until else ""
                raise HTTPException(status_code=423, detail=f"Konto jest zablokowane{suffix}.")
            raise HTTPException(status_code=401, detail="Niepoprawny login lub haslo.")
        if not user:
            raise HTTPException(status_code=401, detail="Niepoprawny login lub haslo.")
        session_token = _make_session_token(username)
        response = JSONResponse(
            {"ok": True, "user": user, "csrf_token": _csrf_token_for_session(session_token)}
        )
        response.set_cookie(
            SESSION_COOKIE,
            session_token,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.post("/api/logout")
    def logout(request: Request) -> JSONResponse:
        username = _require_user(request)
        _remove_active_client(username, _request_presence_client_id(request))
        response = JSONResponse({"ok": True})
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get("/api/bootstrap")
    def bootstrap(request: Request) -> Dict[str, Any]:
        _require_user(request)
        runtime_info = _runtime_info()
        slots = slot_definitions_from_config(config.CONFIG)
        return {
            "base_dir": runtime_info["base_dir"],
            "processed_dir": settings.l,
            "config_path": runtime_info["config_path"],
            "version": get_display_version(),
            "auto_content_fit": bool(config.CONFIG.get(AUTO_CONTENT_FIT_KEY, False)),
            "processing": _processing_settings(),
            "security": _security_settings(),
            "runtime_warning": runtime_info.get("warning"),
            "slots": slots,
            "admin_user": _admin_username(),
            "auth_enabled": _auth_enabled(),
            "current_user": _current_user_payload(request),
            "csrf_token": _csrf_token(request),
            **load_web_data(),
            "pimcore": pimcore_runtime_capabilities(),
        }

    @app.get("/api/data")
    def data(request: Request) -> Dict[str, Any]:
        _require_user(request)
        return load_web_data()

    @app.get("/api/file-index/status")
    def file_index_status_api(request: Request) -> Dict[str, Any]:
        _require_user(request)
        return file_index_status(start=True)

    @app.get("/api/history")
    def history_api(
        request: Request,
        user: str = "",
        limit: int = 1000,
        query: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        _require_user(request)
        return history_snapshot(
            user=user,
            limit=limit,
            query=query,
            page=page,
            page_size=page_size,
        )

    @app.get("/api/logs")
    def logs_api(request: Request, limit: int = 300) -> Dict[str, Any]:
        _require_admin(request)
        return _logs_response(limit)

    @app.get("/api/server/active-users")
    def active_users_api(request: Request) -> Dict[str, Any]:
        _require_admin(request)
        return {"clients": _active_clients_snapshot()}

    @app.get("/api/server/presence")
    def active_presence_api(request: Request) -> Dict[str, Any]:
        _require_user(request)
        return _active_presence_payload(_active_clients_snapshot())

    @app.post("/api/server/presence/leave")
    def active_presence_leave_api(request: Request) -> Dict[str, Any]:
        username = _require_user(request)
        removed = _remove_active_client(username, _request_presence_client_id(request))
        return {"ok": True, "removed": removed}

    @app.post("/api/logs/clear")
    async def logs_clear_api(request: Request) -> JSONResponse:
        current_user = _require_admin(request)
        payload = await request.json()
        password = str(payload.get("password") if isinstance(payload, dict) else "")
        username = str(current_user.get("username") or "")
        verified = authenticate_user(username, password)
        if not verified or verified.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Niepoprawne haslo administratora.")
        clear_result = _clear_log_files()
        response = _logs_response(400)
        response["cleared"] = clear_result["cleared"]
        response["clear_errors"] = clear_result["errors"]
        return JSONResponse(response)

    @app.post("/api/file-index/refresh")
    def file_index_refresh_api(request: Request) -> Dict[str, Any]:
        _require_admin(request)
        return refresh_file_index()

    @app.get("/api/suggestions")
    def suggestions_api(
        request: Request,
        field: str,
        name: str = "",
        type_name: str = "",
        model: str = "",
        color1: str = "",
        color2: str = "",
        color3: str = "",
        extra: str = "",
    ) -> Dict[str, Any]:
        _require_user(request)
        values = field_suggestions(
            field,
            {
                "name": name,
                "type_name": type_name,
                "model": model,
                "color1": color1,
                "color2": color2,
                "color3": color3,
                "extra": extra,
            },
        )
        return {"values": values, "file_index": file_index_status(start=True)}

    @app.post("/api/ftp-preview")
    async def ftp_preview_api(request: Request) -> Dict[str, Any]:
        username = _require_user(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
        try:
            path = await run_in_threadpool(
                cache_ftp_preview,
                payload.get("ean"),
                payload.get("filename"),
                _user_cache_scope(request, username),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        token = _file_token(path)
        version = _file_version(path)
        return {
            "token": token,
            "file_version": version,
            "url": _versioned_file_url(path, "/api/file", token),
            "thumb_url": _versioned_file_url(path, "/api/thumbnail", token),
        }

    @app.post("/api/upload-cache")
    async def upload_cache_api(request: Request) -> Dict[str, Any]:
        started = time.perf_counter()
        username = _require_user(request)
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or not upload.filename:
            raise HTTPException(status_code=400, detail="Brak pliku do wyslania.")
        original_name = upload.filename
        prefix = str(form.get("prefix") or "slot").strip() or "slot"
        cleanup_web_upload_cache()
        save_started = time.perf_counter()
        path, size = await _save_upload_cache(upload, _user_cache_scope(request, username), prefix)
        save_ms = _elapsed_ms(save_started)
        preprocess_ms = 0
        preprocessed = False
        display_name = _safe_upload_name(original_name, os.path.basename(path))
        if _upload_processing_mode() == "host":
            preprocess_started = time.perf_counter()
            original_scan_path = path
            path, display_name, preprocessed = await run_in_threadpool(
                preprocess_cached_upload,
                path,
                original_name,
                processing_options_from_config(config.CONFIG),
            )
            _copy_upload_scan_result(original_scan_path, path)
            preprocess_ms = _elapsed_ms(preprocess_started)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
        token = _file_token(path)
        return {
            "token": token,
            "name": _safe_upload_name(display_name, os.path.basename(path)),
            "size_bytes": size,
            "preprocessed": preprocessed,
            "file_version": _file_version(path),
            "url": _versioned_file_url(path, "/api/file", token),
            "thumb_url": _versioned_file_url(path, "/api/thumbnail", token),
            "timing": {
                "total_ms": _elapsed_ms(started),
                "save_ms": save_ms,
                "preprocess_ms": preprocess_ms,
                "antivirus_scan_ms": int(_upload_scan_result(path).get("elapsed_ms") or 0),
                "mode": _upload_processing_mode(),
            },
            "antivirus_scan": _upload_scan_result(path),
        }

    @app.options("/api/browser-extension/{path:path}")
    def browser_extension_options(request: Request, path: str = "") -> Response:
        return Response(status_code=204, headers=_browser_extension_cors_headers(request))

    @app.get("/api/browser-extension/download")
    def browser_extension_download_api(request: Request) -> Response:
        username = _require_user(request)
        data = _browser_extension_zip_bytes(request, username)
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="picorgftp-sql-browser-extension.zip"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/api/browser-extension/ping")
    def browser_extension_ping_api(request: Request) -> JSONResponse:
        username = _require_browser_extension_user(request)
        return _browser_extension_json(
            request,
            {
                "ok": True,
                "username": username,
                "version": get_display_version(),
                "token_version": int((find_user(username) or {}).get("extension_token_version") or 0),
            },
        )

    @app.get("/api/browser-extension/imports")
    def browser_extension_imports_api(request: Request) -> Dict[str, Any]:
        username = _require_user(request)
        return {"items": _pop_browser_extension_imports(username)}

    @app.post("/api/browser-extension/upload-cache")
    async def browser_extension_upload_cache_api(request: Request) -> JSONResponse:
        started = time.perf_counter()
        username = _require_browser_extension_user(request)
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or not upload.filename:
            raise HTTPException(status_code=400, detail="Brak pliku do wyslania.")
        original_name = upload.filename
        prefix = str(form.get("prefix") or "web").strip() or "web"
        source_url = str(form.get("source_url") or "").strip()
        page_url = str(form.get("page_url") or "").strip()
        cleanup_web_upload_cache()
        save_started = time.perf_counter()
        saved_cache = await _save_upload_cache_entry(
            upload,
            _user_cache_scope(request, username),
            prefix,
            normalize_extension=True,
        )
        path = saved_cache.path
        size = saved_cache.size
        save_ms = _elapsed_ms(save_started)
        preprocess_ms = 0
        preprocessed = False
        display_name = _safe_upload_name(saved_cache.name or original_name, os.path.basename(path))
        if _upload_processing_mode() == "host":
            preprocess_started = time.perf_counter()
            original_scan_path = path
            path, display_name, preprocessed = await run_in_threadpool(
                preprocess_cached_upload,
                path,
                display_name,
                processing_options_from_config(config.CONFIG),
            )
            _copy_upload_scan_result(original_scan_path, path)
            preprocess_ms = _elapsed_ms(preprocess_started)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
        width, height = _image_dimensions(path)
        token = _file_token(path)
        cache_mime_type = UPLOAD_EXTENSION_MIME_TYPE.get(
            _upload_extension(display_name),
            str(upload.content_type or ""),
        )
        cache_payload = {
            "token": token,
            "name": _safe_upload_name(display_name, os.path.basename(path)),
            "size_bytes": size,
            "width": width,
            "height": height,
            "preprocessed": preprocessed,
            "file_version": _file_version(path),
            "url": _versioned_file_url(path, "/api/file", token),
            "thumb_url": _versioned_file_url(path, "/api/thumbnail", token),
            "timing": {
                "total_ms": _elapsed_ms(started),
                "save_ms": save_ms,
                "preprocess_ms": preprocess_ms,
                "antivirus_scan_ms": int(_upload_scan_result(path).get("elapsed_ms") or 0),
                "mode": _upload_processing_mode(),
            },
            "antivirus_scan": _upload_scan_result(path),
        }
        item = {
            "source_url": source_url,
            "page_url": page_url,
            "filename": cache_payload["name"],
            "width": width,
            "height": height,
            "size_bytes": size,
            "mime_type": cache_mime_type,
            "source": "browser-extension",
            "kind": "image",
            "cache": cache_payload,
        }
        _record_browser_extension_import(username, item)
        return _browser_extension_json(request, {"ok": True, "item": item})

    @app.post("/api/web-images/scan")
    async def web_images_scan_api(request: Request) -> JSONResponse:
        _require_user(request)
        payload = await request.json()
        page_url = str(payload.get("url") if isinstance(payload, dict) else "").strip()
        if not page_url:
            raise HTTPException(status_code=400, detail="Podaj link do strony.")
        mode = str(payload.get("mode") or payload.get("scan_mode") or "metadata").strip()
        filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
        try:
            result = await run_in_threadpool(
                _scan_web_image_page,
                page_url,
                mode=mode,
                filters=filters,
            )
        except ImageImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/api/web-images/cache")
    async def web_images_cache_api(request: Request) -> Dict[str, Any]:
        started = time.perf_counter()
        username = _require_user(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Niepoprawne dane obrazu.")
        image_url = str(payload.get("url") or "").strip()
        page_url = str(payload.get("page_url") or payload.get("referer") or "").strip()
        prefix = str(payload.get("prefix") or "slot").strip() or "slot"
        if not image_url:
            raise HTTPException(status_code=400, detail="Brak adresu obrazu.")
        cleanup_web_upload_cache()
        save_started = time.perf_counter()
        try:
            path, size, display_name, width, height = await run_in_threadpool(
                _save_web_image_cache,
                image_url,
                page_url,
                _user_cache_scope(request, username),
                prefix,
            )
        except ImageImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_ms = _elapsed_ms(save_started)
        preprocess_ms = 0
        preprocessed = False
        if _upload_processing_mode() == "host":
            preprocess_started = time.perf_counter()
            path, display_name, preprocessed = await run_in_threadpool(
                preprocess_cached_upload,
                path,
                display_name,
                processing_options_from_config(config.CONFIG),
            )
            preprocess_ms = _elapsed_ms(preprocess_started)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
        token = _file_token(path)
        return {
            "token": token,
            "name": _safe_upload_name(display_name, os.path.basename(path)),
            "size_bytes": size,
            "width": width,
            "height": height,
            "preprocessed": preprocessed,
            "file_version": _file_version(path),
            "url": _versioned_file_url(path, "/api/file", token),
            "thumb_url": _versioned_file_url(path, "/api/thumbnail", token),
            "timing": {
                "total_ms": _elapsed_ms(started),
                "save_ms": save_ms,
                "preprocess_ms": preprocess_ms,
                "mode": _upload_processing_mode(),
            },
        }

    @app.get("/api/entries/search")
    def entries_search(
        request: Request,
        ean: str = "",
        product_id: str = "",
        name: str = "",
        type_name: str = "",
        model: str = "",
        query: str = "",
    ) -> Dict[str, Any]:
        _require_user(request)
        return {
            "entries": search_entries(
                ean=ean,
                product_id=product_id,
                name=name,
                type_name=type_name,
                model=model,
                query=query,
            )
        }

    @app.post("/api/entries/save")
    async def entries_save(request: Request) -> JSONResponse:
        username = _require_user(request)
        payload = await request.json()
        try:
            result = save_web_entry(payload if isinstance(payload, dict) else {})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result:
            entry = result.get("entry", {}) if isinstance(result, dict) else {}
            record_history(
                username=username,
                action="entry_save",
                ean=(entry.get("EAN") or payload.get("ean")) if isinstance(payload, dict) else "",
                product_id=result.get("product_id", "") if isinstance(result, dict) else "",
                summary="Zapisano wpis produktu.",
                details={
                    "updated": bool(result.get("updated")) if isinstance(result, dict) else False,
                    "entry": entry,
                },
            )
        return JSONResponse({"ok": True, "entry": result})

    @app.post("/api/entries/photos")
    async def entries_photos(
        request: Request,
        source: str = "all",
        prefixes: str = "",
    ) -> JSONResponse:
        _require_user(request)
        payload = await request.json()
        source_key = str(source or "all").strip().lower()
        if source_key not in {"all", "local", "ftp", "sql"}:
            raise HTTPException(status_code=400, detail="Nieznane zrodlo zdjec.")
        photos = await run_in_threadpool(
            find_product_photos,
            payload if isinstance(payload, dict) else {},
            include_local=source_key in {"all", "local"},
            include_ftp=source_key in {"all", "ftp"},
            include_sql=source_key in {"all", "sql"},
        )
        requested_prefixes = {
            item.strip()
            for item in str(prefixes or "").split(",")
            if item.strip()
        }
        if requested_prefixes:
            photos = [
                photo
                for photo in photos
                if str(photo.get("prefix") or "") in requested_prefixes
            ]
        return JSONResponse({"photos": _enrich_photo_payload(photos), "source": source_key})

    @app.get("/api/file")
    def file_preview(request: Request, token: str) -> FileResponse:
        _require_user(request)
        path = _path_from_file_token(token)
        return FileResponse(path, headers={"Cache-Control": "private, max-age=300"})

    @app.get("/api/thumbnail")
    def file_thumbnail(
        request: Request,
        token: str,
        fit: int = 0,
        width: int = 360,
        height: int = 260,
    ) -> Response:
        _require_user(request)
        path = _path_from_file_token(token)
        content = _thumbnail_bytes(
            path,
            width=max(64, min(900, int(width or 360))),
            height=max(64, min(900, int(height or 260))),
            content_fit=bool(fit),
        )
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=900"},
        )

    @app.post("/api/lists/{list_key}")
    async def list_add(request: Request, list_key: str) -> JSONResponse:
        _require_user(request)
        payload = await request.json()
        value = str(payload.get("value") if isinstance(payload, dict) else "")
        try:
            data_payload = add_list_value(list_key, value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(data_payload)

    @app.delete("/api/lists/{list_key}")
    async def list_remove(request: Request, list_key: str) -> JSONResponse:
        _require_user(request)
        payload = await request.json()
        value = str(payload.get("value") if isinstance(payload, dict) else "")
        try:
            data_payload = remove_list_value(list_key, value)
        except ListValueInUseError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(exc),
                    "list_key": exc.list_key,
                    "value": exc.value,
                    "used_by": exc.used_by,
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(data_payload)

    @app.get("/api/settings")
    def settings_api(request: Request) -> Dict[str, Any]:
        user = _require_admin(request)
        payload = settings_snapshot()
        payload["current_user"] = user
        return payload

    @app.post("/api/settings")
    async def settings_save(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Niepoprawne ustawienia.")
        previous_session_secret = _session_secret()
        try:
            snapshot = await run_in_threadpool(update_settings, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log_error(f"WEB settings save failed: {exc}\n{traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail=f"Nie udalo sie zapisac ustawien: {exc}",
            ) from exc
        app.state.runtime_info = _runtime_info()
        if _auth_enabled() and not hmac.compare_digest(previous_session_secret, _session_secret()):
            snapshot["session_invalidated"] = True
            snapshot["session_message"] = "Zapisano APP_SECRET. Zaloguj sie ponownie."
            response = JSONResponse(snapshot)
            response.delete_cookie(SESSION_COOKIE)
            return response
        snapshot["current_user"] = _current_user_payload(request)
        return JSONResponse(snapshot)

    @app.post("/api/settings/sql-profiles/{profile_id}/test")
    async def settings_sql_profile_test(
        request: Request,
        profile_id: str,
    ) -> JSONResponse:
        _require_admin(request)
        result = await run_in_threadpool(test_sql_profile_connection, profile_id)
        return JSONResponse(result)

    @app.post("/api/settings/pimcore/test")
    async def pimcore_settings_test_api(request: Request) -> JSONResponse:
        user = _require_admin(request)
        raw = await request.body()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        overrides = payload.get("settings") if isinstance(payload, dict) else None
        report = await run_in_threadpool(
            test_pimcore_settings,
            overrides,
            str(user.get("username") or "admin"),
        )
        return JSONResponse(report)

    @app.post("/api/settings/pimcore/template-preview")
    async def pimcore_template_preview_api(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        try:
            result = await run_in_threadpool(preview_pimcore_template, payload)
        except (TemplateError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": getattr(exc, "code", "invalid_template"),
                    "message": str(exc),
                    "position": getattr(exc, "position", 0),
                },
            ) from exc
        return JSONResponse(result)

    @app.post("/api/settings/pimcore/test-sample")
    async def pimcore_test_sample_api(request: Request) -> JSONResponse:
        _require_admin(request)
        try:
            result = await run_in_threadpool(pimcore_test_sample)
        except (TemplateError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/api/settings/pimcore/discover/classes")
    async def pimcore_discover_classes_api(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        settings_payload = payload.get("settings") if isinstance(payload, dict) else None
        try:
            result = await run_in_threadpool(discover_pimcore_classes, settings_payload)
        except PimcoreApiError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        return JSONResponse(result)

    @app.post("/api/settings/pimcore/discover/fields")
    async def pimcore_discover_fields_api(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        if not isinstance(payload, dict) or not str(payload.get("class_id") or "").strip():
            raise HTTPException(status_code=400, detail="Wybierz klase Pimcore.")
        try:
            result = await run_in_threadpool(
                discover_pimcore_fields,
                payload.get("settings"),
                payload.get("class_id"),
            )
        except PimcoreApiError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        return JSONResponse(result)

    @app.post("/api/settings/pimcore/discover/folders")
    async def pimcore_discover_folders_api(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        try:
            result = await run_in_threadpool(
                discover_pimcore_folders,
                payload.get("settings") if isinstance(payload, dict) else None,
            )
        except PimcoreApiError as exc:
            return JSONResponse({"items": [], "warning": exc.as_dict()})
        return JSONResponse(result)

    @app.post("/api/settings/pimcore/setup")
    async def pimcore_setup_api(request: Request) -> JSONResponse:
        user = _require_admin(request)
        payload = await request.json()
        settings_payload = payload.get("settings") if isinstance(payload, dict) else None
        result = await run_in_threadpool(
            complete_pimcore_setup,
            settings_payload,
            str(user.get("username") or "admin"),
        )
        return JSONResponse(result, status_code=200 if result.get("saved") else 422)

    @app.post("/api/settings/pimcore/import-csv-headers")
    async def pimcore_csv_headers_api(request: Request) -> JSONResponse:
        _require_admin(request)
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or not upload.filename:
            raise HTTPException(status_code=400, detail="Brak pliku CSV.")
        content = await upload.read()
        if len(content) > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Plik CSV jest za duzy.")
        try:
            headers = parse_pimcore_csv_headers(content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"headers": headers})

    @app.post("/api/settings/pimcore/test-create-runs")
    async def pimcore_test_create_start_api(request: Request) -> JSONResponse:
        user = _require_admin(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Niepoprawne dane testu Pimcore.")
        try:
            operation = start_pimcore_test_create(
                payload.get("values"),
                payload.get("cleanup_policy"),
                str(user.get("username") or "admin"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"operation": operation})

    @app.get("/api/settings/pimcore/test-create-runs/{operation_id}")
    def pimcore_test_create_status_api(
        request: Request,
        operation_id: str,
        after_sequence: int = 0,
    ) -> Dict[str, Any]:
        _require_admin(request)
        operation = pimcore_operation_status(operation_id, after_sequence)
        if not operation:
            raise HTTPException(status_code=404, detail="Nie znaleziono operacji Pimcore.")
        return operation

    @app.get("/api/settings/pimcore/operations")
    def pimcore_operations_api(
        request: Request,
        operation_type: str = "",
        result: str = "",
        user: str = "",
        query: str = "",
        date_from: float = 0,
        date_to: float = 0,
        limit: int = 200,
    ) -> Dict[str, Any]:
        _require_admin(request)
        return pimcore_operation_history(
            operation_type=operation_type,
            result=result,
            user=user,
            query=query,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

    @app.get("/api/pimcore/product-status")
    async def pimcore_product_status_api(request: Request, ean: str) -> JSONResponse:
        username = _require_user(request)
        try:
            result = await run_in_threadpool(find_pimcore_product_by_ean, ean)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PimcoreApiError as exc:
            _write_web_event(
                level="warning",
                event="PIMCORE_PRODUCT_LOOKUP",
                username=username,
                message=str(exc),
                details={"ean": ean, "error": exc.as_dict()},
            )
            return JSONResponse(
                {
                    "enabled": True,
                    "available": False,
                    "exists": False,
                    "object": None,
                    "error": exc.as_dict(),
                }
            )
        result["available"] = True
        _write_web_event(
            level="info",
            event="PIMCORE_PRODUCT_LOOKUP",
            username=username,
            message=f"EAN {ean}: {'istnieje' if result.get('exists') else 'brak'}.",
            details={
                "ean": ean,
                "exists": bool(result.get("exists")),
                "object": result.get("object"),
            },
        )
        return JSONResponse(result)

    @app.post("/api/pimcore/render-templates")
    async def pimcore_render_templates_api(request: Request) -> JSONResponse:
        _require_user(request)
        payload = await request.json()
        source = payload if isinstance(payload, dict) else {}
        try:
            result = await run_in_threadpool(
                render_saved_pimcore_templates,
                source.get("product_values"),
                source.get("values"),
                source.get("targets"),
            )
        except (TemplateError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.get("/api/pimcore/products/{object_id}")
    async def pimcore_product_edit_data_api(request: Request, object_id: int) -> JSONResponse:
        _require_user(request)
        try:
            result = await run_in_threadpool(get_pimcore_product_for_edit, object_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PimcoreApiError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        return JSONResponse(result)

    @app.put("/api/pimcore/products/{object_id}")
    async def pimcore_product_update_api(request: Request, object_id: int) -> JSONResponse:
        username = _require_user(request)
        payload = await request.json()
        values = payload.get("values") if isinstance(payload, dict) else None
        marker = payload.get("marker") if isinstance(payload, dict) else None
        if not isinstance(values, dict) or not str(marker or ""):
            raise HTTPException(status_code=400, detail="Brak danych albo wersji produktu Pimcore.")
        try:
            result = await run_in_threadpool(
                update_pimcore_product,
                object_id,
                marker,
                values,
                username,
            )
        except PimcoreConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(exc),
                    "object_id": exc.object_id,
                    "expected_marker": exc.expected_marker,
                    "current_marker": exc.current_marker,
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PimcoreApiError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        return JSONResponse(result)

    @app.post("/api/pimcore/products")
    async def pimcore_product_create_api(request: Request) -> JSONResponse:
        username = _require_user(request)
        payload = await request.json()
        values = payload.get("values") if isinstance(payload, dict) else None
        if not isinstance(values, dict):
            raise HTTPException(status_code=400, detail="Brak danych produktu Pimcore.")
        try:
            result = await run_in_threadpool(create_pimcore_product, values, username)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PimcoreApiError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        return JSONResponse(result)

    @app.post("/api/settings/import-legacy")
    async def settings_import_legacy(request: Request) -> JSONResponse:
        _require_admin(request)
        database_path = storage_settings.resolve_sqlite_path()
        if not database_path:
            raise HTTPException(status_code=400, detail="Nie ustawiono sciezki bazy SQLite.")
        try:
            result = await run_in_threadpool(
                import_legacy_to_sqlite,
                legacy_dir=settings.AC,
                database_path=database_path,
            )
            storage_settings.save_bootstrap_settings(
                {storage_settings.DATA_MODE_KEY: storage_settings.DATA_MODE_SQLITE}
            )
            data_store.reset_active_store_cache()
            config.initialize_config(interactive=False)
        except Exception as exc:
            log_error(f"WEB legacy import failed: {exc}\n{traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail=f"Nie udalo sie zaimportowac danych legacy: {exc}",
            ) from exc
        app.state.runtime_info = _runtime_info()
        result["settings"] = settings_snapshot()
        result["message"] = "Zaimportowano stare dane do SQLite i wlaczono tryb SQLite."
        return JSONResponse(result)

    @app.post("/api/settings/sqlite/repair")
    async def settings_sqlite_repair(request: Request) -> JSONResponse:
        _require_admin(request)
        database_path = storage_settings.resolve_sqlite_path()
        backup_dir = storage_settings.resolve_backup_dir()
        result = await run_in_threadpool(
            repair_sqlite_database,
            database_path,
            backup_dir,
        )
        data_store.reset_active_store_cache()
        config.initialize_config(interactive=False)
        result["settings"] = settings_snapshot()
        return JSONResponse(result)

    @app.post("/api/settings/sqlite/backup")
    async def settings_sqlite_backup(request: Request) -> JSONResponse:
        _require_admin(request)
        result = await run_in_threadpool(
            sqlite_backup.create_backup,
            storage_settings.resolve_sqlite_path(),
            storage_settings.resolve_backup_dir(),
            reason="manual",
        )
        sqlite_backup.enforce_retention(
            storage_settings.resolve_backup_dir(),
            storage_settings.load_backup_settings().get("max_copies", 10),
        )
        return JSONResponse(result)

    @app.get("/api/settings/sqlite/backups")
    def settings_sqlite_backups(request: Request) -> Dict[str, Any]:
        _require_admin(request)
        return {"items": sqlite_backup.list_backups(storage_settings.resolve_backup_dir())}

    @app.post("/api/settings/sqlite/backup-diff")
    async def settings_sqlite_backup_diff(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        backup_path = str(payload.get("backup_path") if isinstance(payload, dict) else "")
        result = await run_in_threadpool(
            sqlite_backup.diff_databases,
            storage_settings.resolve_sqlite_path(),
            backup_path,
        )
        return JSONResponse(result)

    @app.post("/api/settings/sqlite/restore")
    async def settings_sqlite_restore(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        backup_path = str(payload.get("backup_path") if isinstance(payload, dict) else "")
        result = await run_in_threadpool(
            sqlite_backup.restore_backup,
            storage_settings.resolve_sqlite_path(),
            backup_path,
            storage_settings.resolve_backup_dir(),
        )
        data_store.reset_active_store_cache()
        config.initialize_config(interactive=False)
        result["settings"] = settings_snapshot()
        return JSONResponse(result)

    @app.post("/api/settings/sql-columns/detect")
    def settings_sql_columns_detect(request: Request) -> JSONResponse:
        _require_admin(request)
        result = detect_available_columns(config.CONFIG)
        if result.get("ok"):
            config.CONFIG[SQL_AVAILABLE_COLUMNS_KEY] = list(result.get("columns") or [])
            config.save_config(
                config.CONFIG,
                preserve_secrets={
                    H: {N, M},
                    P: {N, M},
                    K: {N, M},
                    TRANSLATION_SETTINGS_KEY: {TRANSLATION_API_KEY},
                },
            )
            result["settings"] = settings_snapshot()
        return JSONResponse(result)

    @app.post("/api/settings/secrets")
    async def settings_secrets(request: Request) -> JSONResponse:
        current_user = _require_admin(request)
        payload = await request.json()
        password = str(payload.get("password") if isinstance(payload, dict) else "")
        username = str(current_user.get("username") or "")
        verified = authenticate_user(username, password)
        if not verified or verified.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Niepoprawne haslo administratora.")
        return JSONResponse(
            settings_secret_values(),
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/users")
    def users_get(request: Request) -> Dict[str, Any]:
        user = _require_admin(request)
        return {"users": load_users(), "current_user": user}

    @app.post("/api/users")
    async def users_add(request: Request) -> JSONResponse:
        _require_admin(request)
        payload = await request.json()
        try:
            users = add_user(
                str(payload.get("username") if isinstance(payload, dict) else ""),
                str(payload.get("password") if isinstance(payload, dict) else ""),
                str(payload.get("role") if isinstance(payload, dict) else "user"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"users": users, "current_user": _current_user_payload(request)})

    @app.patch("/api/users/{username}")
    async def users_update(request: Request, username: str) -> JSONResponse:
        current_user = _require_admin(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
        try:
            users = update_user(
                username,
                enabled=payload.get("enabled") if "enabled" in payload else None,
                role=payload.get("role") if "role" in payload else None,
                password=payload.get("password") if "password" in payload else None,
                unlock=bool(payload.get("unlock")) if "unlock" in payload else None,
                revoke_sessions=bool(payload.get("revoke_sessions")) if "revoke_sessions" in payload else None,
                revoke_extension_token=bool(payload.get("revoke_extension_token"))
                if "revoke_extension_token" in payload
                else None,
                current_username=str(current_user.get("username") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if payload.get("unlock"):
            _write_web_event(
                level="INFO",
                event="login_unlocked",
                username=username,
                message=f"Odblokowano konto {username}.",
                details={"by": str(current_user.get("username") or "")},
            )
        current_username = str(current_user.get("username") or "")
        current_session_invalidated = (
            username.lower() == current_username.lower()
            and (
                bool(payload.get("revoke_sessions"))
                or bool(payload.get("password"))
            )
        )
        response_payload: Dict[str, Any] = {
            "users": users,
            "current_user": current_user if current_session_invalidated else _current_user_payload(request),
        }
        if current_session_invalidated:
            response_payload["session_invalidated"] = True
            response_payload["session_message"] = "Sesje konta zostaly uniewaznione. Zaloguj sie ponownie."
            response = JSONResponse(response_payload)
            response.delete_cookie(SESSION_COOKIE)
            return response
        return JSONResponse(response_payload)

    @app.post("/api/diagnostics/{target}")
    def diagnostics(request: Request, target: str) -> JSONResponse:
        _require_admin(request)
        if target == "local":
            return JSONResponse(test_local_paths())
        if target == "ftp":
            return JSONResponse(test_ftp_connection())
        if target == "sql":
            return JSONResponse(test_sql_connection())
        raise HTTPException(status_code=404, detail="Nieznany test diagnostyczny.")

    @app.get("/api/process-jobs")
    def process_jobs_api(request: Request, limit: int = 20) -> Dict[str, Any]:
        username = _require_user(request)
        return {"jobs": _process_jobs_for_user(username, limit=limit)}

    @app.get("/api/process-jobs/active")
    def process_jobs_active_api(request: Request) -> Dict[str, Any]:
        _require_user(request)
        return _active_process_jobs_snapshot()

    @app.get("/api/process-jobs/{job_id}")
    def process_job_api(request: Request, job_id: str) -> Dict[str, Any]:
        username = _require_user(request)
        job = _process_job_for_user(job_id, username)
        if not job:
            raise HTTPException(status_code=404, detail="Nie znaleziono zadania.")
        return _process_job_payload(job)

    @app.post("/api/process/background")
    async def process_uploads_background(request: Request) -> JSONResponse:
        username = _require_user(request)
        cache_scope = _user_cache_scope(request, username)
        temp_dir = tempfile.mkdtemp(prefix="picorg_web_process_")
        try:
            form = await request.form()
            snapshot = await _materialize_process_form(form, temp_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        job = _queue_process_job(
            username=username,
            cache_scope=cache_scope,
            form=snapshot,
        )
        return JSONResponse({"queued": True, "job": job})

    @app.post("/api/process")
    async def process_uploads(request: Request) -> JSONResponse:
        username = _require_user(request)
        cache_scope = _user_cache_scope(request, username)
        temp_dir = tempfile.mkdtemp(prefix="picorg_web_process_")
        try:
            form = await request.form()
            snapshot = await _materialize_process_form(form, temp_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        payload = await run_in_threadpool(
            lambda: _process_upload_snapshot(
                username=username,
                cache_scope=cache_scope,
                form=snapshot,
            )
        )
        return JSONResponse(payload)
    return app


app = create_app()
