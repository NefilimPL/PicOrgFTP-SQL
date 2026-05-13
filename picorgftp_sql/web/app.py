"""FastAPI LAN backend for the browser upload panel."""

from __future__ import annotations

import base64
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
import tempfile
import time
import traceback
import unicodedata
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from .. import common, config, settings
from ..bootstrap import initialize_application_runtime
from ..common import (
    AUTO_CONTENT_FIT_KEY,
    H,
    K,
    SQL_COLUMN_MAP_KEY,
    SQL_UPDATE_TEMPLATE,
    ft,
    p,
    u,
    w,
)
from ..database import connect_db
from ..image_utils import fit_image_to_content
from ..logging_utils import log_error
from ..services.ftp_service import sync_remote_files
from ..services.sql_service import extract_presence_context
from ..workflow_utils import build_product_directory, parse_slot_filename
from ..web_workflow import (
    WebProductForm,
    WebUploadedSlot,
    process_web_uploads,
    normalized_product_payload,
    processing_options_from_config,
    slot_definitions_from_config,
    validate_product_form,
)
from ..web_data import (
    add_list_value,
    add_user,
    authenticate_user,
    cache_ftp_preview,
    cleanup_web_ftp_cache,
    field_suggestions,
    find_entry_by_identity,
    find_user,
    find_product_photos,
    file_index_status,
    load_web_data,
    load_users,
    history_snapshot,
    ListValueInUseError,
    refresh_file_index,
    remove_list_value,
    record_history,
    save_web_entry,
    search_entries,
    settings_snapshot,
    test_ftp_connection,
    test_local_paths,
    test_sql_connection,
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
SESSION_COOKIE = "picorg_web_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"


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


def _make_session_token(username: str) -> str:
    payload = f"{username}|{int(time.time())}|{secrets.token_hex(12)}"
    token = f"{payload}|{_sign(payload)}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _read_session_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, issued_raw, nonce, signature = decoded.rsplit("|", 3)
    except Exception:
        return None
    payload = f"{username}|{issued_raw}|{nonce}"
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        issued = int(issued_raw)
    except ValueError:
        return None
    if int(time.time()) - issued > SESSION_MAX_AGE_SECONDS:
        return None
    user = find_user(username)
    if not user or not user.get("enabled"):
        return None
    return username


def _current_user(request: Request) -> Optional[str]:
    if not _auth_enabled():
        return _admin_username()
    return _read_session_token(request.cookies.get(SESSION_COOKIE))


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


def _file_token(path: str) -> str:
    payload = os.path.abspath(path)
    token = f"{payload}|{_sign(payload)}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


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
        raise HTTPException(status_code=403, detail="Plik poza katalogiem zdjec.")
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


async def _save_upload(upload: UploadFile, temp_dir: str, prefix: str) -> str:
    safe_name = _safe_upload_name(upload.filename, f"{prefix}.upload")
    suffix = Path(safe_name).suffix
    target_path = os.path.join(temp_dir, f"{prefix}_{secrets.token_hex(8)}{suffix}")
    with open(target_path, "wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    await upload.close()
    return target_path


def _result_payload(result: Any) -> Dict[str, Any]:
    return {
        "output_dir": result.output_dir,
        "ean": result.ean,
        "saved_files": [
            {
                "prefix": item.prefix,
                "label": item.label,
                "source_name": item.source_name,
                "filename": item.filename,
                "path": item.path,
                "size_bytes": item.size_bytes,
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


def _sync_result_to_sql(
    result: Any,
    *,
    clear_prefixes: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    if not bool(config.CONFIG.get(u, True)):
        return {"enabled": False, "updated": 0, "cleared": 0, "rows": 0, "elapsed_ms": 0, "error": ""}
    started = time.perf_counter()
    ean = str(getattr(result, "ean", "") or "").strip()
    payload = {"enabled": True, "updated": 0, "cleared": 0, "rows": 0, "elapsed_ms": 0, "error": ""}
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
        template = config.CONFIG.get(w, SQL_UPDATE_TEMPLATE) or SQL_UPDATE_TEMPLATE
        for prefix, filename in saved_by_prefix.items():
            column = _safe_sql_identifier(sql_map.get(prefix, ""))
            if not column:
                continue
            parsed = parse_slot_filename(filename)
            if not parsed:
                continue
            short_name = f"{ean}_{prefix}{parsed.extension}"
            query = template.format(col=column, filename=short_name, ean=ean)
            cur.execute(query)
            payload["updated"] += 1
            if getattr(cur, "rowcount", -1) >= 0:
                payload["rows"] += int(cur.rowcount)
        for prefix in clear_prefixes:
            column = _safe_sql_identifier(sql_map.get(prefix, ""))
            if not column:
                continue
            cur.execute(f"UPDATE {table} SET {column} = ''{where_clause}")
            payload["cleared"] += 1
            if getattr(cur, "rowcount", -1) >= 0:
                payload["rows"] += int(cur.rowcount)
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
    payload = normalized_product_payload(form)
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


def _existing_photo_conflicts(
    photos: List[Dict[str, Any]],
    uploaded_slots: List[WebUploadedSlot],
    delete_requests: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    uploaded_by_prefix = {str(slot.prefix): slot for slot in uploaded_slots}
    delete_prefixes = {str(item.get("prefix") or "") for item in delete_requests}
    conflicts: List[Dict[str, Any]] = []
    for photo in photos:
        prefix = str(photo.get("prefix") or "").strip()
        if not prefix or prefix not in uploaded_by_prefix or prefix in delete_prefixes:
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
    photos = find_product_photos(
        source_entry,
        include_local=True,
        include_ftp=bool(config.CONFIG.get(ft, True)),
        include_sql=False,
    )
    for photo in photos:
        prefix = str(photo.get("prefix") or "").strip()
        path = str(photo.get("path") or "").strip()
        ftp_filename = os.path.basename(str(photo.get("ftp_filename") or ""))
        if not prefix or prefix in delete_prefixes:
            continue
        slot = slot_by_prefix.get(prefix, {"prefix": prefix, "label": prefix})
        label = str(slot.get("label") or prefix)
        source_path = path if path and os.path.isfile(path) else ""
        had_local_source = bool(source_path)
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
        elif source_path and not ftp_filename and bool(config.CONFIG.get(ft, True)):
            should_process = True
        elif ftp_filename and not source_path:
            source_path = _download_ftp_photo_source(
                photo,
                str(source_entry.get("ean") or product.ean or ""),
                cache_scope=cache_scope,
            )
            should_process = bool(source_path and os.path.isfile(source_path))
        if not should_process:
            continue
        if prefix not in occupied_prefixes and prefix not in delete_prefixes:
            uploaded_slots.append(
                WebUploadedSlot(
                    prefix=prefix,
                    label=label,
                    source_path=source_path,
                    original_filename=ftp_filename or os.path.basename(source_path),
                )
            )
            occupied_prefixes.add(prefix)
            appended.append(prefix)
        if prefix not in delete_prefixes:
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
    cache_scope: str = "",
) -> List[str]:
    """Backward-compatible wrapper for tests and older call sites."""

    return _append_existing_photo_sources(
        existing_entry=existing_entry,
        product=product,
        uploaded_slots=uploaded_slots,
        delete_requests=delete_requests,
        slot_by_prefix=slot_by_prefix,
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
            item["url"] = f"/api/file?token={token}"
            item["thumb_url"] = f"/api/thumbnail?token={token}"
        else:
            item["token"] = ""
            item["url"] = ""
            item["thumb_url"] = ""
        if ftp_path:
            ftp_token = _file_token(ftp_path)
            item["ftp_token"] = ftp_token
            item["ftp_url"] = f"/api/file?token={ftp_token}"
            item["ftp_thumb_url"] = f"/api/thumbnail?token={ftp_token}"
        else:
            item["ftp_token"] = ""
            item["ftp_url"] = ""
            item["ftp_thumb_url"] = ""
        enriched.append(item)
    return enriched


def create_app() -> FastAPI:
    """Create the LAN web backend."""

    app = FastAPI(title="PicOrgFTP-SQL Web", version=get_app_version())
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def _log_unhandled_web_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            log_error(
                f"WEB {request.method} {request.url.path}: {exc}\n{traceback.format_exc()}"
            )
            raise

    @app.on_event("startup")
    def _startup() -> None:
        os.environ.setdefault("PICORGFTP_SQL_HEADLESS", "1")
        runtime_info = initialize_application_runtime(interactive=False)
        app.state.runtime_info = runtime_info
        cleanup_web_ftp_cache(force=True)

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
        user = authenticate_user(username, password)
        if not user:
            raise HTTPException(status_code=401, detail="Niepoprawny login lub haslo.")
        response = JSONResponse({"ok": True, "user": user})
        response.set_cookie(
            SESSION_COOKIE,
            _make_session_token(username),
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
        )
        return response

    @app.post("/api/logout")
    def logout(request: Request) -> JSONResponse:
        _require_user(request)
        response = JSONResponse({"ok": True})
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get("/api/bootstrap")
    def bootstrap(request: Request) -> Dict[str, Any]:
        _require_user(request)
        runtime_info = getattr(app.state, "runtime_info", None) or initialize_application_runtime(
            interactive=False
        )
        slots = slot_definitions_from_config(config.CONFIG)
        return {
            "base_dir": runtime_info["base_dir"],
            "processed_dir": settings.l,
            "config_path": runtime_info["config_path"],
            "version": get_display_version(),
            "auto_content_fit": bool(config.CONFIG.get(AUTO_CONTENT_FIT_KEY, False)),
            "runtime_warning": runtime_info.get("warning"),
            "slots": slots,
            "admin_user": _admin_username(),
            "auth_enabled": _auth_enabled(),
            "current_user": _current_user_payload(request),
            **load_web_data(),
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
    def history_api(request: Request, user: str = "", limit: int = 200) -> Dict[str, Any]:
        _require_user(request)
        return history_snapshot(user=user, limit=limit)

    @app.get("/api/logs")
    def logs_api(request: Request, limit: int = 300) -> Dict[str, Any]:
        _require_admin(request)
        return _logs_response(limit)

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
        return {
            "token": token,
            "url": f"/api/file?token={token}",
            "thumb_url": f"/api/thumbnail?token={token}",
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
    async def entries_photos(request: Request, source: str = "all") -> JSONResponse:
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
        try:
            snapshot = update_settings(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        snapshot["current_user"] = _current_user_payload(request)
        return JSONResponse(snapshot)

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
                current_username=str(current_user.get("username") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"users": users, "current_user": _current_user_payload(request)})

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

    @app.post("/api/process")
    async def process_uploads(request: Request) -> JSONResponse:
        username = _require_user(request)
        cache_scope = _user_cache_scope(request, username)
        form = await request.form()
        slots = slot_definitions_from_config(config.CONFIG)
        slot_by_prefix = {slot["prefix"]: slot for slot in slots}
        temp_dir = tempfile.mkdtemp(prefix="picorg_web_upload_")
        uploaded_slots: List[WebUploadedSlot] = []
        delete_requests: List[Dict[str, Any]] = []
        pending_ftp_slots: List[Dict[str, Any]] = []
        product: Optional[WebProductForm] = None
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
                value = form.get(f"slot_{prefix}")
                if not isinstance(value, UploadFile) or not value.filename:
                    token = str(form.get(f"existing_slot_{prefix}") or "").strip()
                    if token:
                        source_path = _path_from_file_token(token)
                        uploaded_slots.append(
                            WebUploadedSlot(
                                prefix=prefix,
                                label=slot["label"],
                                source_path=source_path,
                                original_filename=os.path.basename(source_path),
                                content_fit=_optional_form_bool(form, f"slot_fit_{prefix}"),
                            )
                        )
                        continue
                    ftp_filename = os.path.basename(str(form.get(f"existing_ftp_slot_{prefix}") or ""))
                    if ftp_filename:
                        pending_ftp_slots.append(
                            {
                                "prefix": prefix,
                                "label": slot["label"],
                                "filename": ftp_filename,
                                "ean": str(form.get(f"existing_ftp_ean_{prefix}") or ""),
                                "content_fit": _optional_form_bool(form, f"slot_fit_{prefix}"),
                            }
                        )
                        continue
                    continue
                source_path = await _save_upload(value, temp_dir, prefix)
                uploaded_slots.append(
                    WebUploadedSlot(
                        prefix=prefix,
                        label=slot["label"],
                        source_path=source_path,
                        original_filename=value.filename or "",
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
            errors = validate_product_form(product)
            if errors:
                raise ValueError(" ".join(errors))
            existing_entry = None
            if product.product_id.strip():
                existing_entry = find_entry_by_identity(product_id=product.product_id)
            if (
                existing_entry is None
                and product.ean.strip()
                and product.ean.strip().upper() != "BRAK-EAN"
            ):
                existing_entry = find_entry_by_identity(ean=product.ean)
            if existing_entry:
                preserved_product_id = product.product_id or str(
                    existing_entry.get("product_id") or ""
                )
                preserved_ean = product.ean or str(existing_entry.get("ean") or "")
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
            _append_pending_ftp_slots(
                product=product,
                pending_ftp_slots=pending_ftp_slots,
                uploaded_slots=uploaded_slots,
                delete_requests=delete_requests,
                cache_scope=cache_scope,
            )
            photo_lookup_entry = existing_entry or _entry_payload_from_product(product)
            existing_photos = find_product_photos(
                photo_lookup_entry,
                include_local=True,
                include_ftp=bool(config.CONFIG.get(ft, True)),
                include_sql=True,
            )
            if existing_entry is None:
                conflicts = _existing_photo_conflicts(
                    existing_photos,
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
                cache_scope=cache_scope,
            )
            if existing_entry is None and existing_photos and not uploaded_slots and not delete_requests:
                raise ValueError(
                    _format_existing_photo_conflicts(
                        [
                            {
                                "prefix": photo.get("prefix"),
                                "sources": _photo_source_labels(photo),
                            }
                            for photo in existing_photos
                        ]
                    )
                )
            entry_result = save_web_entry(
                {
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
            )
            result = process_web_uploads(
                base_output_dir=settings.l,
                form=product,
                uploaded_slots=uploaded_slots,
                options=processing_options_from_config(config.CONFIG),
                allow_empty=True,
            )
            saved_paths = {os.path.abspath(item.path) for item in result.saved_files}
            local_delete_result = _delete_local_files(delete_requests, saved_paths)
            ftp_backfill_prefixes = {
                str(item.get("prefix") or "")
                for item in delete_requests
                if item.get("ftp_backfill")
            }
            ftp_result = _sync_result_to_ftp(
                result,
                [
                    item.get("ftp_filename", "")
                    for item in delete_requests
                    if not item.get("ftp_backfill")
                ],
                skip_upload_prefixes=ftp_backfill_prefixes,
            )
            sql_result = _sync_result_to_sql(
                result,
                clear_prefixes={
                    str(item.get("prefix") or "")
                    for item in delete_requests
                    if item.get("sql") or item.get("ftp_filename") or item.get("local_path")
                },
            )
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
            shutil.rmtree(temp_dir, ignore_errors=True)
        payload = _result_payload(result)
        payload["entry"] = entry_result
        payload["migrated_slots"] = migrated_prefixes
        payload["ftp"] = ftp_result
        payload["sql"] = sql_result
        payload["local_delete"] = local_delete_result
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
                "sql": sql_result,
                "local_delete": local_delete_result,
                "output_dir": payload["output_dir"],
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
                sql=sql_result,
                local_delete=local_delete_result,
            ),
        )
        return JSONResponse(payload)

    return app


app = create_app()
