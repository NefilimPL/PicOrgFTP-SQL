"""FastAPI LAN backend for the browser upload panel."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from pathlib import Path
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
from ..common import APP_SECRET
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
    load_web_data,
    remove_list_value,
    save_web_entry,
    search_entries,
    settings_snapshot,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
SESSION_COOKIE = "picorg_web_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"


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
    if username != _admin_username():
        return None
    return username


def _current_user(request: Request) -> str | None:
    return _read_session_token(request.cookies.get(SESSION_COOKIE))


def _require_user(request: Request) -> str:
    username = _current_user(request)
    if not username:
        raise HTTPException(status_code=401, detail="Brak aktywnej sesji.")
    return username


def _static_file(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / name)


def _safe_upload_name(filename: str | None, fallback: str) -> str:
    name = Path(filename or "").name.strip()
    if not name:
        name = fallback
    return name


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
        if not _current_user(request):
            return RedirectResponse("/login", status_code=303)
        return _static_file("index.html")

    @app.get("/login")
    def login_page(request: Request) -> Response:
        if _current_user(request):
            return RedirectResponse("/", status_code=303)
        return _static_file("login.html")

    @app.post("/api/login")
    async def login(request: Request) -> JSONResponse:
        form = await request.form()
        username = str(form.get("username") or "").strip()
        password = str(form.get("password") or "")
        if username != _admin_username() or not hmac.compare_digest(
            password, _admin_password()
        ):
            raise HTTPException(status_code=401, detail="Niepoprawny login lub haslo.")
        response = JSONResponse({"ok": True, "username": username})
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
            **load_web_data(),
        }

    @app.get("/api/data")
    def data(request: Request) -> dict[str, Any]:
        _require_user(request)
        return load_web_data()

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
        _require_user(request)
        payload = await request.json()
        try:
            result = save_web_entry(payload if isinstance(payload, dict) else {})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"ok": True, "entry": result})

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
        _require_user(request)
        return settings_snapshot()

    @app.post("/api/process")
    async def process_uploads(request: Request) -> JSONResponse:
        _require_user(request)
        form = await request.form()
        slots = slot_definitions_from_config(config.CONFIG)
        slot_by_prefix = {slot["prefix"]: slot for slot in slots}
        temp_dir = tempfile.mkdtemp(prefix="picorg_web_upload_")
        uploaded_slots: list[WebUploadedSlot] = []
        try:
            for prefix, slot in slot_by_prefix.items():
                value = form.get(f"slot_{prefix}")
                if not isinstance(value, UploadFile) or not value.filename:
                    continue
                source_path = await _save_upload(value, temp_dir, prefix)
                uploaded_slots.append(
                    WebUploadedSlot(
                        prefix=prefix,
                        label=slot["label"],
                        source_path=source_path,
                        original_filename=value.filename or "",
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
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        payload = _result_payload(result)
        payload["entry"] = entry_result
        return JSONResponse(payload)

    return app


app = create_app()
