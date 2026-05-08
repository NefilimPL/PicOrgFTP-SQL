"""FastAPI LAN backend for the browser upload panel."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile

from .. import config, settings
from ..bootstrap import initialize_application_runtime
from ..common import APP_SECRET, H, K, SQL_COLUMN_MAP_KEY, SQL_UPDATE_TEMPLATE, ft, p, u, w
from ..database import connect_db
from ..image_utils import fit_image_to_content
from ..services.ftp_service import sync_remote_files
from ..services.sql_service import extract_presence_context
from ..workflow_utils import parse_slot_filename
from ..web_workflow import (
    WebProductForm,
    WebUploadedSlot,
    process_web_uploads,
    processing_options_from_config,
    slot_definitions_from_config,
    validate_product_form,
)
from ..web_data import (
    add_list_value,
    add_user,
    authenticate_user,
    cache_ftp_preview,
    field_suggestions,
    find_user,
    find_product_photos,
    file_index_status,
    load_web_data,
    load_users,
    history_snapshot,
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
    value = os.environ.get("PICORG_WEB_SESSION_SECRET") or APP_SECRET
    return value.encode("utf-8")


def _sign(payload: str) -> str:
    return hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _make_session_token(username: str) -> str:
    payload = f"{username}|{int(time.time())}|{secrets.token_hex(12)}"
    token = f"{payload}|{_sign(payload)}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _read_session_token(token: str | None) -> str | None:
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


def _current_user(request: Request) -> str | None:
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


def _current_user_payload(request: Request) -> dict[str, Any]:
    username = _require_user(request)
    user = find_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="Brak aktywnej sesji.")
    return user


def _require_admin(request: Request) -> dict[str, Any]:
    user = _current_user_payload(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Wymagane konto administratora.")
    return user


def _static_file(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / name)


def _safe_upload_name(filename: str | None, fallback: str) -> str:
    name = Path(filename or "").name.strip()
    if not name:
        name = fallback
    return name


def _file_token(path: str) -> str:
    payload = os.path.abspath(path)
    token = f"{payload}|{_sign(payload)}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _path_from_file_token(token: str) -> str:
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
    if not os.path.isfile(abs_path):
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


def _result_payload(result: Any) -> dict[str, Any]:
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


def _sync_result_to_ftp(result: Any, delete_candidates: list[str] | None = None) -> dict[str, Any]:
    if not bool(config.CONFIG.get(ft, True)):
        return {"enabled": False, "uploaded": 0, "deleted": 0, "elapsed_ms": 0, "error": ""}
    filenames = [item.filename for item in result.saved_files if getattr(item, "filename", "")]
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
    clear_prefixes: set[str] | None = None,
) -> dict[str, Any]:
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


def _delete_local_files(delete_requests: list[dict[str, Any]], saved_paths: set[str]) -> dict[str, Any]:
    payload = {"deleted": 0, "skipped": 0, "errors": []}
    for item in delete_requests:
        path = str(item.get("local_path") or "")
        if not path:
            continue
        abs_path = os.path.abspath(path)
        if abs_path in saved_paths:
            payload["skipped"] += 1
            continue
        try:
            if os.path.isfile(abs_path):
                os.remove(abs_path)
                payload["deleted"] += 1
        except Exception as exc:
            payload["errors"].append(f"{os.path.basename(abs_path)}: {exc}")
    return payload


def create_app() -> FastAPI:
    """Create the LAN web backend."""

    app = FastAPI(title="PicOrgFTP-SQL Web", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.on_event("startup")
    def _startup() -> None:
        os.environ.setdefault("PICORGFTP_SQL_HEADLESS", "1")
        runtime_info = initialize_application_runtime(interactive=False)
        app.state.runtime_info = runtime_info

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
    def bootstrap(request: Request) -> dict[str, Any]:
        _require_user(request)
        runtime_info = getattr(app.state, "runtime_info", None) or initialize_application_runtime(
            interactive=False
        )
        slots = slot_definitions_from_config(config.CONFIG)
        return {
            "base_dir": runtime_info["base_dir"],
            "processed_dir": settings.l,
            "config_path": runtime_info["config_path"],
            "slots": slots,
            "admin_user": _admin_username(),
            "auth_enabled": _auth_enabled(),
            "current_user": _current_user_payload(request),
            **load_web_data(),
        }

    @app.get("/api/data")
    def data(request: Request) -> dict[str, Any]:
        _require_user(request)
        return load_web_data()

    @app.get("/api/file-index/status")
    def file_index_status_api(request: Request) -> dict[str, Any]:
        _require_user(request)
        return file_index_status(start=True)

    @app.get("/api/history")
    def history_api(request: Request, user: str = "", limit: int = 200) -> dict[str, Any]:
        _require_user(request)
        return history_snapshot(user=user, limit=limit)

    @app.post("/api/file-index/refresh")
    def file_index_refresh_api(request: Request) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
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
    async def ftp_preview_api(request: Request) -> dict[str, Any]:
        _require_user(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
        try:
            path = cache_ftp_preview(payload.get("ean"), payload.get("filename"))
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
    ) -> dict[str, Any]:
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
                ean=payload.get("ean") if isinstance(payload, dict) else "",
                product_id=result.get("product_id", "") if isinstance(result, dict) else "",
                summary="Zapisano wpis produktu.",
                details={
                    "updated": bool(result.get("updated")) if isinstance(result, dict) else False,
                    "entry": entry,
                },
            )
        return JSONResponse({"ok": True, "entry": result})

    @app.post("/api/entries/photos")
    async def entries_photos(request: Request) -> JSONResponse:
        _require_user(request)
        payload = await request.json()
        photos = find_product_photos(payload if isinstance(payload, dict) else {})
        enriched = []
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
        return JSONResponse({"photos": enriched})

    @app.get("/api/file")
    def file_preview(request: Request, token: str) -> FileResponse:
        _require_user(request)
        path = _path_from_file_token(token)
        return FileResponse(path)

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
        return Response(content=content, media_type="image/jpeg")

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
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(data_payload)

    @app.get("/api/settings")
    def settings_api(request: Request) -> dict[str, Any]:
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
    def users_get(request: Request) -> dict[str, Any]:
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
        form = await request.form()
        slots = slot_definitions_from_config(config.CONFIG)
        slot_by_prefix = {slot["prefix"]: slot for slot in slots}
        temp_dir = tempfile.mkdtemp(prefix="picorg_web_upload_")
        uploaded_slots: list[WebUploadedSlot] = []
        delete_requests: list[dict[str, Any]] = []
        try:
            for prefix, slot in slot_by_prefix.items():
                if str(form.get(f"delete_slot_{prefix}") or "") == "1":
                    delete_item: dict[str, Any] = {
                        "prefix": prefix,
                        "label": slot["label"],
                        "local_path": "",
                        "ftp_filename": os.path.basename(str(form.get(f"delete_ftp_slot_{prefix}") or "")),
                        "sql": str(form.get(f"delete_sql_slot_{prefix}") or "") == "1",
                    }
                    local_token = str(form.get(f"delete_local_slot_{prefix}") or "").strip()
                    if local_token:
                        delete_item["local_path"] = _path_from_file_token(local_token)
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
                                content_fit=str(form.get(f"slot_fit_{prefix}") or "") == "1",
                            )
                        )
                    continue
                source_path = await _save_upload(value, temp_dir, prefix)
                uploaded_slots.append(
                    WebUploadedSlot(
                        prefix=prefix,
                        label=slot["label"],
                        source_path=source_path,
                        original_filename=value.filename or "",
                        content_fit=str(form.get(f"slot_fit_{prefix}") or "") == "1",
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
            )
            saved_paths = {os.path.abspath(item.path) for item in result.saved_files}
            local_delete_result = _delete_local_files(delete_requests, saved_paths)
            ftp_result = _sync_result_to_ftp(
                result,
                [item.get("ftp_filename", "") for item in delete_requests],
            )
            sql_result = _sync_result_to_sql(
                result,
                clear_prefixes={
                    str(item.get("prefix") or "")
                    for item in delete_requests
                    if item.get("sql") or item.get("ftp_filename") or item.get("local_path")
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        payload = _result_payload(result)
        payload["entry"] = entry_result
        payload["ftp"] = ftp_result
        payload["sql"] = sql_result
        payload["local_delete"] = local_delete_result
        record_history(
            username=username,
            action="process",
            ean=product.ean,
            product_id=entry_result.get("product_id", "") if isinstance(entry_result, dict) else "",
            summary="Przetworzono pliki produktu.",
            details={
                "saved_files": payload["saved_files"],
                "deleted_slots": delete_requests,
                "ftp": ftp_result,
                "sql": sql_result,
                "local_delete": local_delete_result,
                "output_dir": payload["output_dir"],
                "entry": entry_result.get("entry", {}) if isinstance(entry_result, dict) else {},
            },
        )
        return JSONResponse(payload)

    return app


app = create_app()
