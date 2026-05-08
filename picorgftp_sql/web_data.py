"""Data helpers for the LAN web interface."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import ctypes
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile

from . import common, config, settings
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
    SQL_AVAILABLE_COLUMNS_KEY,
    SQL_COLUMN_MAP_KEY,
    SLOT_DEFS_KEY,
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
    prepare_excel_lists,
    remove_from_list,
    save_ean_entry,
    NO_EAN_PLACEHOLDER,
)
from .services.ftp_service import list_remote_files_for_ean
from .services.sql_service import (
    extract_presence_context,
    query_presence_details,
    should_check_presence,
)
from .slot_utils import normalize_slot_definitions, normalize_sql_column_map
from .workflow_utils import build_product_directory, parse_slot_filename


LIST_SHEETS = {
    "names": "NAZWY",
    "types": "TYPY",
    "models": "MODELE",
    "colors": "KOLORY",
    "extras": "DODATKI",
}

WEB_USERS_PATH = "web_users.json"
IMAGE_PREVIEW_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 200_000


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


def _norm(value: object) -> str:
    return _text(value).upper()


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
    }


def _public_user(user: dict[str, object]) -> dict[str, object]:
    return {
        "username": _text(user.get("username")),
        "role": "admin" if _text(user.get("role")) == "admin" else "user",
        "enabled": bool(user.get("enabled", True)),
        "has_password": bool(_text(user.get("password_hash"))),
    }


def _default_admin() -> dict[str, object]:
    return {
        "username": "admin",
        "role": "admin",
        "enabled": True,
        "password_hash": _hash_password("admin"),
    }


def load_user_records() -> list[dict[str, object]]:
    """Load full local web user records, including password hashes."""

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
        username = _text(item.get("username"))
        if not username or username.lower() in seen:
            continue
        role = _text(item.get("role")) or "user"
        users.append(
            {
                "username": username,
                "role": "admin" if role == "admin" else "user",
                "enabled": bool(item.get("enabled", True)),
                "password_hash": _text(item.get("password_hash"))
                or (_hash_password("admin") if username.lower() == "admin" else ""),
            }
        )
        seen.add(username.lower())
    if not any(user["username"].lower() == "admin" for user in users):
        users.insert(0, _default_admin())
    return users


def load_users() -> list[dict[str, object]]:
    """Load public web user records for settings UI."""

    return [_public_user(user) for user in load_user_records()]


def save_users(users: list[dict[str, object]]) -> list[dict[str, object]]:
    """Persist local web user records."""

    path = Path(settings.AC) / WEB_USERS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(users, indent=4, ensure_ascii=False), encoding="utf-8")
    return load_users()


def authenticate_user(username: str, password: str) -> dict[str, object] | None:
    """Return a public user record when credentials are valid."""

    normalized = _text(username).lower()
    for user in load_user_records():
        if _text(user.get("username")).lower() != normalized:
            continue
        if not bool(user.get("enabled", True)):
            return None
        if verify_password(password, _text(user.get("password_hash"))):
            return _public_user(user)
    return None


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
        }
    )
    return save_users(users)


def update_user(
    username: str,
    *,
    enabled: bool | None = None,
    role: str | None = None,
    password: str | None = None,
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
        return save_users(users)
    raise ValueError("Nie znaleziono uzytkownika.")


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

    matches = search_entries(product_id=product_id, ean=ean, limit=1)
    return matches[0] if matches else None


def save_web_entry(payload: dict[str, object]) -> dict[str, object]:
    """Create or update an Excel entry using the existing desktop helper."""

    result = save_ean_entry(
        _text(payload.get("ean")) or NO_EAN_PLACEHOLDER,
        _text(payload.get("name")),
        _text(payload.get("type_name")),
        _text(payload.get("model")),
        _text(payload.get("color1")),
        _text(payload.get("color2")),
        _text(payload.get("color3")),
        _text(payload.get("extra")),
        product_id=_text(payload.get("product_id")),
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
    if not add_to_list(sheet, value):
        raise ValueError("Nie udalo sie dodac wartosci do listy.")
    return load_web_data()


def remove_list_value(list_key: str, value: str) -> dict[str, object]:
    """Remove a value from one of the editable Excel list sheets."""

    sheet = LIST_SHEETS.get(list_key)
    if not sheet:
        raise ValueError("Nieznana lista.")
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
    path.write_text(json.dumps(existing, indent=4, ensure_ascii=False), encoding="utf-8")


def update_settings(payload: dict[str, object]) -> dict[str, object]:
    """Update editable settings from the web UI."""

    cfg = config.CONFIG
    runtime_needs_reload = False
    app_payload = payload.get("app") if isinstance(payload.get("app"), dict) else {}
    ftp_payload = payload.get("ftp") if isinstance(payload.get("ftp"), dict) else {}
    db_payload = payload.get("database") if isinstance(payload.get("database"), dict) else {}
    slots_payload = payload.get("slots") if isinstance(payload.get("slots"), list) else None

    if "base_dir" in app_payload:
        base_dir = _text(app_payload.get("base_dir"))
        if base_dir:
            _save_local_settings({"base_dir_override": base_dir})
            runtime_needs_reload = True
    if APP_SECRET_KEY in app_payload:
        secret = _text(app_payload.get(APP_SECRET_KEY))
        if secret:
            _save_local_settings({APP_SECRET_KEY: common._encode_local_secret(secret)})
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

    if runtime_needs_reload:
        settings.initialize_runtime(interactive=False)
    save_config(cfg)
    config.initialize_config(interactive=False)
    return settings_snapshot()


def settings_snapshot() -> dict[str, object]:
    """Return non-secret settings for the web settings view."""

    cfg = config.CONFIG
    ftp = cfg.get(H, {})
    sql = cfg.get(P, {})
    mysql_cfg = cfg.get(K, {})
    slot_defs = cfg.get(SLOT_DEFS_KEY, []) or []
    sql_map = cfg.get(SQL_COLUMN_MAP_KEY, {}) or {}
    return {
        "windows_admin": is_windows_admin_process(),
        "base_dir": settings.AC,
        "processed_dir": settings.l,
        "config_path": config.CONFIG_PATH,
        "auth_enabled": True,
        "users": load_users(),
        "local_file_index": bool(cfg.get(LOCAL_FILE_INDEX_KEY, True)),
        "auto_content_fit": bool(cfg.get(AUTO_CONTENT_FIT_KEY, False)),
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
                "sql_column": sql_map.get(slot.get("prefix", ""), ""),
            }
            for slot in slot_defs
        ],
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


def find_product_photos(entry_payload: dict[str, object]) -> list[dict[str, object]]:
    """Find local processed photos for a saved web entry."""

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
    if os.path.isdir(product_dir):
        for filename in os.listdir(product_dir):
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
                "prefix": parsed.normalized_label,
                "filename": filename,
                "path": path,
                "is_image": ext in IMAGE_PREVIEW_EXTENSIONS,
                "local": True,
                "ftp": False,
                "sql": False,
                "ftp_filename": "",
                "sql_value": "",
            }
    ean = entry.ean
    if ean and bool(config.CONFIG.get(ft, True)):
        try:
            remote = list_remote_files_for_ean(config.CONFIG.get(H, {}), ean)
            for prefix, filename in remote.items():
                item = results_by_prefix.setdefault(
                    prefix,
                    {
                        "prefix": prefix,
                        "filename": "",
                        "path": "",
                        "is_image": False,
                        "local": False,
                        "sql": False,
                        "sql_value": "",
                    },
                )
                item["ftp"] = True
                item["ftp_filename"] = filename
        except Exception:
            pass
    if ean and should_check_presence(config.CONFIG):
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
                    item = results_by_prefix.setdefault(
                        prefix,
                        {
                            "prefix": prefix,
                            "filename": "",
                            "path": "",
                            "is_image": False,
                            "local": False,
                            "ftp": False,
                            "ftp_filename": "",
                        },
                    )
                    item["sql"] = bool(present)
                    item["sql_value"] = values.get(prefix, "")
        except Exception:
            pass
    return sorted(results_by_prefix.values(), key=lambda item: str(item.get("prefix", "")))
