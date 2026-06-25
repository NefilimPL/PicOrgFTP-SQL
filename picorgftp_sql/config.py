"""Configuration file loading and persistence."""

import tempfile

from .common import (
    A,
    A6,
    A9,
    AO,
    AF,
    Aq,
    Ar,
    B,
    BT,
    CONFIG_DIR_PROMPT_TITLE,
    DEFAULT_CONFIG,
    E,
    H,
    I,
    K,
    M,
    N,
    O,
    P,
    SQL_UPDATE_TEMPLATE,
    SQL_COLUMN_MAP_KEY,
    SQL_AVAILABLE_COLUMNS_KEY,
    LOCAL_FILE_INDEX_KEY,
    AUTO_CONTENT_FIT_KEY,
    PROCESSING_SETTINGS_KEY,
    SECURITY_SETTINGS_KEY,
    COLOR_FIELD_LABELS_KEY,
    AK,
    SLOT_DEFS_KEY,
    TRANSLATION_API_KEY,
    TRANSLATION_API_URL,
    TRANSLATION_PROVIDER_DEFAULT,
    TRANSLATION_PROVIDER_KEY,
    TRANSLATION_SETTINGS_KEY,
    b,
    c,
    ft,
    k,
    m,
    p,
    r,
    u,
    v,
    w,
    require_runtime_modules,
)
from .encryption import decrypt, encrypt
from .slot_utils import normalize_slot_definitions, normalize_sql_column_map
from . import settings

CONFIG_PATH = A.path.join(settings.AC, "config.json")
CONFIG_SAVE_FAILED_MSG = "Nie udało się zapisać pliku konfiguracyjnego:\n{error}"
CONFIG = Ar.loads(Ar.dumps(DEFAULT_CONFIG))


def _active_sqlite_store():
    """Return the active SQLite store adapter, or None in legacy mode."""

    try:
        from . import data_store

        store = data_store.get_active_store()
        if getattr(store, "mode", "") == "sqlite":
            return store
    except Exception:
        return None
    return None


def _get_config_path():
    return A.path.join(settings.AC, "config.json")


def _write_json_atomic(path, payload):
    """Persist JSON using a temp file to avoid partial writes."""

    directory = A.path.dirname(path) or "."
    A.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="config_", suffix=".json.tmp", dir=directory)
    try:
        with A.fdopen(fd, "w", encoding=k) as handle:
            Ar.dump(payload, handle, indent=4)
        A.replace(temp_path, path)
    finally:
        if A.path.exists(temp_path):
            try:
                A.remove(temp_path)
            except OSError:
                pass


def _write_error_log_direct(message):
    """Write a fallback error log entry without importing logging_utils."""

    try:
        settings.ensure_log_dir()
        with open(settings.AM, "a", encoding=k) as log_file:
            log_file.write(
                f"[{A9.now().strftime(A6)}] [USER: {AO}] [PC: {AF}] "
                f"ERROR: {message}\n"
            )
    except Exception:
        pass


def _normalize_sql_columns(raw_columns):
    if not isinstance(raw_columns, list):
        return []
    cleaned = []
    seen = set()
    for entry in raw_columns:
        text = str(entry).strip()
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
    return cleaned


def _normalize_color_field_labels(raw_labels):
    if not isinstance(raw_labels, dict):
        return {}
    cleaned = {}
    for field_key in ("color1", "color2", "color3"):
        value = raw_labels.get(field_key, B)
        if not Aq(value, str):
            continue
        text = str(value).strip().rstrip(":").rstrip("*").strip()
        if text:
            cleaned[field_key] = text
    return cleaned


def _normalize_processing_settings(raw_settings):
    defaults = DEFAULT_CONFIG.get(PROCESSING_SETTINGS_KEY, {})
    raw = raw_settings if Aq(raw_settings, dict) else {}

    def _int_value(key, minimum, maximum):
        try:
            value = int(raw.get(key, defaults.get(key)))
        except (TypeError, ValueError):
            value = int(defaults.get(key))
        return max(minimum, min(maximum, value))

    target_format = str(raw.get("target_format", defaults.get("target_format", "PNG")) or "PNG").strip().upper()
    if target_format == "JPEG":
        target_format = "JPG"
    if target_format not in {"JPG", "PNG", "WEBP", "BMP", "GIF", "TIFF"}:
        target_format = "PNG"
    upload_processing_mode = str(
        raw.get("upload_processing_mode", defaults.get("upload_processing_mode", "save"))
        or "save"
    ).strip().lower()
    if upload_processing_mode not in {"save", "host", "client"}:
        upload_processing_mode = "save"
    return {
        "resize_enabled": bool(raw.get("resize_enabled", defaults.get("resize_enabled", True))),
        "max_dim": _int_value("max_dim", 64, 20000),
        "compress_enabled": bool(raw.get("compress_enabled", defaults.get("compress_enabled", False))),
        "compress_quality": _int_value("compress_quality", 1, 100),
        "max_size_enabled": bool(raw.get("max_size_enabled", defaults.get("max_size_enabled", False))),
        "max_file_kb": _int_value("max_file_kb", 1, 102400),
        "convert_enabled": bool(raw.get("convert_enabled", defaults.get("convert_enabled", False))),
        "target_format": target_format,
        "upload_processing_mode": upload_processing_mode,
        "show_timing_details": bool(
            raw.get("show_timing_details", defaults.get("show_timing_details", False))
        ),
    }


def _normalize_security_settings(raw_settings):
    defaults = DEFAULT_CONFIG.get(SECURITY_SETTINGS_KEY, {})
    raw = raw_settings if Aq(raw_settings, dict) else {}

    def _int_value(key, minimum, maximum):
        try:
            value = int(raw.get(key, defaults.get(key)))
        except (TypeError, ValueError):
            value = int(defaults.get(key))
        return max(minimum, min(maximum, value))

    def _extension_list(key):
        value = raw.get(key, defaults.get(key, []))
        if Aq(value, str):
            parts = value.replace(";", ",").replace("\n", ",").split(",")
        elif Aq(value, list):
            parts = value
        else:
            parts = defaults.get(key, [])
        cleaned = []
        seen = set()
        for item in parts:
            text = str(item or "").strip().lower().lstrip(".")
            if not text or not text.isalnum() or len(text) > 12 or text in seen:
                continue
            cleaned.append(text)
            seen.add(text)
        return cleaned

    return {
        "max_upload_mb": _int_value("max_upload_mb", 1, 2048),
        "max_upload_pixels": _int_value("max_upload_pixels", 1, 400_000_000),
        "allowed_upload_extensions": _extension_list("allowed_upload_extensions"),
        "blocked_upload_extensions": _extension_list("blocked_upload_extensions"),
        "block_executable_uploads": bool(
            raw.get("block_executable_uploads", defaults.get("block_executable_uploads", True))
        ),
        "antivirus_scan_uploads": bool(
            raw.get("antivirus_scan_uploads", defaults.get("antivirus_scan_uploads", False))
        ),
    }


def _merge_raw_config(raw_config, config_copy):
    """Merge a raw persisted config payload into a normalized config copy."""

    if not Aq(raw_config, dict):
        return config_copy
    config_copy[H][v] = raw_config.get(H, {}).get(v, config_copy[H][v])
    config_copy[H][r] = raw_config.get(H, {}).get(r, config_copy[H][r])
    config_copy[H][N] = decrypt(raw_config.get(H, {}).get(N, encrypt(config_copy[H][N])))
    config_copy[H][M] = decrypt(raw_config.get(H, {}).get(M, encrypt(config_copy[H][M])))
    config_copy[H][m] = raw_config.get(H, {}).get(m, config_copy[H][m])
    config_copy[P][c] = raw_config.get(P, {}).get(c, config_copy[P][c])
    config_copy[P][b] = raw_config.get(P, {}).get(b, config_copy[P][b])
    config_copy[P][N] = decrypt(raw_config.get(P, {}).get(N, encrypt(config_copy[P][N])))
    config_copy[P][M] = decrypt(raw_config.get(P, {}).get(M, encrypt(config_copy[P][M])))
    config_copy[K][c] = raw_config.get(K, {}).get(c, config_copy[K][c])
    config_copy[K][b] = raw_config.get(K, {}).get(b, config_copy[K][b])
    config_copy[K][N] = decrypt(raw_config.get(K, {}).get(N, encrypt(config_copy[K][N])))
    config_copy[K][M] = decrypt(raw_config.get(K, {}).get(M, encrypt(config_copy[K][M])))
    config_copy[p] = raw_config.get(p, config_copy[p])
    config_copy[w] = raw_config.get(w, config_copy[w])
    config_copy[ft] = raw_config.get(ft, config_copy[ft])
    config_copy[u] = raw_config.get(u, config_copy[u])
    config_copy[LOCAL_FILE_INDEX_KEY] = raw_config.get(
        LOCAL_FILE_INDEX_KEY, config_copy.get(LOCAL_FILE_INDEX_KEY, True)
    )
    config_copy[AUTO_CONTENT_FIT_KEY] = bool(
        raw_config.get(
            AUTO_CONTENT_FIT_KEY,
            config_copy.get(AUTO_CONTENT_FIT_KEY, False),
        )
    )
    config_copy[PROCESSING_SETTINGS_KEY] = _normalize_processing_settings(
        raw_config.get(
            PROCESSING_SETTINGS_KEY,
            config_copy.get(PROCESSING_SETTINGS_KEY, {}),
        )
    )
    raw_security = raw_config.get(
        SECURITY_SETTINGS_KEY,
        config_copy.get(SECURITY_SETTINGS_KEY, {}),
    )
    if not Aq(raw_security, dict):
        raw_security = {}
    legacy_processing = raw_config.get(PROCESSING_SETTINGS_KEY, {})
    if Aq(legacy_processing, dict):
        raw_security = dict(raw_security)
        for key in ("max_upload_mb", "max_upload_pixels"):
            if key not in raw_security and key in legacy_processing:
                raw_security[key] = legacy_processing[key]
    config_copy[SECURITY_SETTINGS_KEY] = _normalize_security_settings(raw_security)
    config_copy[COLOR_FIELD_LABELS_KEY] = _normalize_color_field_labels(
        raw_config.get(
            COLOR_FIELD_LABELS_KEY,
            config_copy.get(COLOR_FIELD_LABELS_KEY, {}),
        )
    )
    raw_slot_defs = raw_config.get(SLOT_DEFS_KEY, config_copy.get(SLOT_DEFS_KEY))
    slot_defs, _ = normalize_slot_definitions(raw_slot_defs)
    config_copy[SLOT_DEFS_KEY] = slot_defs
    raw_sql_map = raw_config.get(SQL_COLUMN_MAP_KEY, config_copy.get(SQL_COLUMN_MAP_KEY))
    sql_map, _ = normalize_sql_column_map(raw_sql_map, slot_defs)
    config_copy[SQL_COLUMN_MAP_KEY] = sql_map
    raw_columns = raw_config.get(
        SQL_AVAILABLE_COLUMNS_KEY, config_copy.get(SQL_AVAILABLE_COLUMNS_KEY)
    )
    config_copy[SQL_AVAILABLE_COLUMNS_KEY] = _normalize_sql_columns(raw_columns)
    raw_translation = raw_config.get(
        TRANSLATION_SETTINGS_KEY, config_copy.get(TRANSLATION_SETTINGS_KEY, {})
    )
    if not Aq(raw_translation, dict):
        raw_translation = {}
    translation_defaults = config_copy.get(TRANSLATION_SETTINGS_KEY, {})
    config_copy[TRANSLATION_SETTINGS_KEY] = {
        TRANSLATION_PROVIDER_KEY: raw_translation.get(
            TRANSLATION_PROVIDER_KEY,
            translation_defaults.get(
                TRANSLATION_PROVIDER_KEY, TRANSLATION_PROVIDER_DEFAULT
            ),
        ),
        TRANSLATION_API_KEY: decrypt(
            raw_translation.get(
                TRANSLATION_API_KEY,
                encrypt(translation_defaults.get(TRANSLATION_API_KEY, B)),
            )
        ),
        TRANSLATION_API_URL: raw_translation.get(
            TRANSLATION_API_URL,
            translation_defaults.get(TRANSLATION_API_URL, B),
        ),
    }
    return config_copy


def load_config(interactive=I):
    """Return a configuration dictionary, creating defaults when necessary."""

    # Work on a copy so that callers modifying the result do not mutate
    # DEFAULT_CONFIG, which acts as a template for new installations.
    global CONFIG_PATH
    if interactive is I:
        interactive = not settings.HEADLESS_ENV
    config_copy = Ar.loads(Ar.dumps(DEFAULT_CONFIG))
    sqlite_store = _active_sqlite_store()
    if sqlite_store is not None:
        CONFIG_PATH = getattr(sqlite_store, "database_path", CONFIG_PATH)
        raw_config = sqlite_store.load_config()
        if raw_config:
            return _merge_raw_config(raw_config, config_copy)
        save_config(config_copy)
        return config_copy
    config_path = _get_config_path()
    if not A.path.exists(config_path):
        if interactive and not settings.has_saved_base_dir_override():
            require_runtime_modules("tkinter")
            chosen_dir = BT.askdirectory(title=CONFIG_DIR_PROMPT_TITLE)
            if chosen_dir:
                config_path = A.path.join(chosen_dir, "config.json")
        if not A.path.exists(config_path):
            # Persist an initial configuration with encrypted secrets so the
            # application can be used immediately after installation.
            translation_defaults = config_copy.get(TRANSLATION_SETTINGS_KEY, {})
            initial = {
                H: {
                    v: config_copy[H][v],
                    r: config_copy[H][r],
                    N: encrypt(config_copy[H][N]),
                    M: encrypt(config_copy[H][M]),
                    m: config_copy[H][m],
                },
                P: {
                    c: config_copy[P][c],
                    b: config_copy[P][b],
                    N: encrypt(config_copy[P][N]),
                    M: encrypt(config_copy[P][M]),
                },
                K: {
                    c: config_copy[K][c],
                    b: config_copy[K][b],
                    N: encrypt(config_copy[K][N]),
                    M: encrypt(config_copy[K][M]),
                },
                p: config_copy[p],
                w: config_copy[w],
                ft: config_copy[ft],
                u: config_copy[u],
                SLOT_DEFS_KEY: config_copy.get(SLOT_DEFS_KEY),
                SQL_COLUMN_MAP_KEY: config_copy.get(SQL_COLUMN_MAP_KEY),
                SQL_AVAILABLE_COLUMNS_KEY: config_copy.get(SQL_AVAILABLE_COLUMNS_KEY),
                LOCAL_FILE_INDEX_KEY: config_copy.get(LOCAL_FILE_INDEX_KEY, True),
                AUTO_CONTENT_FIT_KEY: bool(
                    config_copy.get(AUTO_CONTENT_FIT_KEY, False)
                ),
                PROCESSING_SETTINGS_KEY: _normalize_processing_settings(
                    config_copy.get(PROCESSING_SETTINGS_KEY)
                ),
                SECURITY_SETTINGS_KEY: _normalize_security_settings(
                    config_copy.get(SECURITY_SETTINGS_KEY)
                ),
                COLOR_FIELD_LABELS_KEY: config_copy.get(COLOR_FIELD_LABELS_KEY, {}),
                TRANSLATION_SETTINGS_KEY: {
                    TRANSLATION_PROVIDER_KEY: translation_defaults.get(
                        TRANSLATION_PROVIDER_KEY, TRANSLATION_PROVIDER_DEFAULT
                    ),
                    TRANSLATION_API_KEY: encrypt(
                        translation_defaults.get(TRANSLATION_API_KEY, B)
                    ),
                    TRANSLATION_API_URL: translation_defaults.get(
                        TRANSLATION_API_URL, B
                    ),
                },
            }
            try:
                # Ensure the configuration directory exists before writing.
                _write_json_atomic(config_path, initial)
            except E as exc:
                _write_error_log_direct(f"Failed to create config.json: {exc}")
    CONFIG_PATH = config_path
    try:
        with open(CONFIG_PATH, "r", encoding=k) as handle:
            raw_config = Ar.load(handle)
        config_copy[H][v] = raw_config.get(H, {}).get(v, config_copy[H][v])
        config_copy[H][r] = raw_config.get(H, {}).get(r, config_copy[H][r])
        config_copy[H][N] = decrypt(raw_config.get(H, {}).get(N, encrypt(config_copy[H][N])))
        config_copy[H][M] = decrypt(raw_config.get(H, {}).get(M, encrypt(config_copy[H][M])))
        config_copy[H][m] = raw_config.get(H, {}).get(m, config_copy[H][m])
        config_copy[P][c] = raw_config.get(P, {}).get(c, config_copy[P][c])
        config_copy[P][b] = raw_config.get(P, {}).get(b, config_copy[P][b])
        config_copy[P][N] = decrypt(raw_config.get(P, {}).get(N, encrypt(config_copy[P][N])))
        config_copy[P][M] = decrypt(raw_config.get(P, {}).get(M, encrypt(config_copy[P][M])))
        config_copy[K][c] = raw_config.get(K, {}).get(c, config_copy[K][c])
        config_copy[K][b] = raw_config.get(K, {}).get(b, config_copy[K][b])
        config_copy[K][N] = decrypt(raw_config.get(K, {}).get(N, encrypt(config_copy[K][N])))
        config_copy[K][M] = decrypt(raw_config.get(K, {}).get(M, encrypt(config_copy[K][M])))
        config_copy[p] = raw_config.get(p, config_copy[p])
        config_copy[w] = raw_config.get(w, config_copy[w])
        config_copy[ft] = raw_config.get(ft, config_copy[ft])
        config_copy[u] = raw_config.get(u, config_copy[u])
        config_copy[LOCAL_FILE_INDEX_KEY] = raw_config.get(
            LOCAL_FILE_INDEX_KEY, config_copy.get(LOCAL_FILE_INDEX_KEY, True)
        )
        config_copy[AUTO_CONTENT_FIT_KEY] = bool(
            raw_config.get(
                AUTO_CONTENT_FIT_KEY,
                config_copy.get(AUTO_CONTENT_FIT_KEY, False),
            )
        )
        config_copy[PROCESSING_SETTINGS_KEY] = _normalize_processing_settings(
            raw_config.get(
                PROCESSING_SETTINGS_KEY,
                config_copy.get(PROCESSING_SETTINGS_KEY, {}),
            )
        )
        raw_security = raw_config.get(
            SECURITY_SETTINGS_KEY,
            config_copy.get(SECURITY_SETTINGS_KEY, {}),
        )
        if not Aq(raw_security, dict):
            raw_security = {}
        legacy_processing = raw_config.get(PROCESSING_SETTINGS_KEY, {})
        if Aq(legacy_processing, dict):
            raw_security = dict(raw_security)
            for key in ("max_upload_mb", "max_upload_pixels"):
                if key not in raw_security and key in legacy_processing:
                    raw_security[key] = legacy_processing[key]
        config_copy[SECURITY_SETTINGS_KEY] = _normalize_security_settings(raw_security)
        config_copy[COLOR_FIELD_LABELS_KEY] = _normalize_color_field_labels(
            raw_config.get(
                COLOR_FIELD_LABELS_KEY,
                config_copy.get(COLOR_FIELD_LABELS_KEY, {}),
            )
        )
        raw_slot_defs = raw_config.get(SLOT_DEFS_KEY, config_copy.get(SLOT_DEFS_KEY))
        slot_defs, _ = normalize_slot_definitions(raw_slot_defs)
        config_copy[SLOT_DEFS_KEY] = slot_defs
        raw_sql_map = raw_config.get(SQL_COLUMN_MAP_KEY, config_copy.get(SQL_COLUMN_MAP_KEY))
        sql_map, _ = normalize_sql_column_map(raw_sql_map, slot_defs)
        config_copy[SQL_COLUMN_MAP_KEY] = sql_map
        raw_columns = raw_config.get(
            SQL_AVAILABLE_COLUMNS_KEY, config_copy.get(SQL_AVAILABLE_COLUMNS_KEY)
        )
        config_copy[SQL_AVAILABLE_COLUMNS_KEY] = _normalize_sql_columns(raw_columns)
        raw_translation = raw_config.get(
            TRANSLATION_SETTINGS_KEY, config_copy.get(TRANSLATION_SETTINGS_KEY, {})
        )
        translation_defaults = config_copy.get(TRANSLATION_SETTINGS_KEY, {})
        config_copy[TRANSLATION_SETTINGS_KEY] = {
            TRANSLATION_PROVIDER_KEY: raw_translation.get(
                TRANSLATION_PROVIDER_KEY,
                translation_defaults.get(
                    TRANSLATION_PROVIDER_KEY, TRANSLATION_PROVIDER_DEFAULT
                ),
            ),
            TRANSLATION_API_KEY: decrypt(
                raw_translation.get(
                    TRANSLATION_API_KEY,
                    encrypt(translation_defaults.get(TRANSLATION_API_KEY, B)),
                )
            ),
            TRANSLATION_API_URL: raw_translation.get(
                TRANSLATION_API_URL,
                translation_defaults.get(TRANSLATION_API_URL, B),
            ),
        }
        try:
            # Saving back the normalised structure keeps missing keys aligned
            # with future versions of the configuration schema.
            preserve_secrets = {
                H: {N, M},
                P: {N, M},
                K: {N, M},
                TRANSLATION_SETTINGS_KEY: {TRANSLATION_API_KEY},
            }
            save_config(
                config_copy,
                raw_config=raw_config,
                preserve_secrets=preserve_secrets,
            )
        except E:
            pass
    except E as exc:
        try:
            _write_error_log_direct(f"Failed to load config.json: {exc}")
        except Exception:
            pass
    return config_copy


def _load_raw_config():
    """Return the raw configuration dict without decryption."""

    sqlite_store = _active_sqlite_store()
    if sqlite_store is not None:
        return sqlite_store.load_config()
    try:
        config_path = _get_config_path()
        if A.path.exists(config_path):
            with open(config_path, "r", encoding=k) as handle:
                raw_config = Ar.load(handle)
            if Aq(raw_config, dict):
                return raw_config
    except E:
        pass
    return {}


def save_config(config, raw_config=None, preserve_secrets=None):
    """Serialise the provided configuration dictionary to disk."""

    # Persist secrets in encrypted form to avoid storing clear text credentials.
    global CONFIG_PATH
    if preserve_secrets is None:
        preserve_secrets = {}
    if raw_config is None and preserve_secrets:
        raw_config = _load_raw_config()
    if not Aq(raw_config, dict):
        raw_config = {}
    if not Aq(preserve_secrets, dict):
        preserve_secrets = {}
    else:
        preserve_secrets = {
            section: set(keys) for section, keys in preserve_secrets.items()
        }
    translation_settings = config.get(TRANSLATION_SETTINGS_KEY, {})

    def _pick_secret(section_key, item_key, value):
        preserve_keys = preserve_secrets.get(section_key, set())
        if preserve_keys and item_key in preserve_keys:
            raw_section = raw_config.get(section_key, {})
            if Aq(raw_section, dict) and item_key in raw_section:
                raw_value = raw_section.get(item_key)
                if raw_value is not None:
                    return raw_value
        return encrypt(value)

    payload = {
        H: {
            v: config[H][v],
            r: config[H][r],
            N: _pick_secret(H, N, config[H][N]),
            M: _pick_secret(H, M, config[H][M]),
            m: config[H][m],
        },
        P: {
            c: config[P][c],
            b: config[P][b],
            N: _pick_secret(P, N, config[P][N]),
            M: _pick_secret(P, M, config[P][M]),
        },
        K: {
            c: config[K][c],
            b: config[K][b],
            N: _pick_secret(K, N, config[K][N]),
            M: _pick_secret(K, M, config[K][M]),
        },
        p: config.get(p, K),
        w: config.get(w, SQL_UPDATE_TEMPLATE),
        ft: config.get(ft, True),
        u: config.get(u, True),
        SLOT_DEFS_KEY: config.get(SLOT_DEFS_KEY),
        SQL_COLUMN_MAP_KEY: config.get(SQL_COLUMN_MAP_KEY),
        SQL_AVAILABLE_COLUMNS_KEY: _normalize_sql_columns(
            config.get(SQL_AVAILABLE_COLUMNS_KEY, [])
        ),
        LOCAL_FILE_INDEX_KEY: bool(config.get(LOCAL_FILE_INDEX_KEY, True)),
        AUTO_CONTENT_FIT_KEY: bool(config.get(AUTO_CONTENT_FIT_KEY, False)),
        PROCESSING_SETTINGS_KEY: _normalize_processing_settings(
            config.get(PROCESSING_SETTINGS_KEY, {})
        ),
        SECURITY_SETTINGS_KEY: _normalize_security_settings(
            config.get(SECURITY_SETTINGS_KEY, {})
        ),
        COLOR_FIELD_LABELS_KEY: _normalize_color_field_labels(
            config.get(COLOR_FIELD_LABELS_KEY, {})
        ),
        TRANSLATION_SETTINGS_KEY: {
            TRANSLATION_PROVIDER_KEY: translation_settings.get(
                TRANSLATION_PROVIDER_KEY, TRANSLATION_PROVIDER_DEFAULT
            ),
            TRANSLATION_API_KEY: _pick_secret(
                TRANSLATION_SETTINGS_KEY,
                TRANSLATION_API_KEY,
                translation_settings.get(TRANSLATION_API_KEY, B),
            ),
            TRANSLATION_API_URL: translation_settings.get(TRANSLATION_API_URL, B),
        },
    }
    sqlite_store = _active_sqlite_store()
    if sqlite_store is not None:
        try:
            CONFIG_PATH = getattr(sqlite_store, "database_path", CONFIG_PATH)
            sqlite_store.save_config(payload)
        except E as exc:
            if O:
                O.showerror(AK, CONFIG_SAVE_FAILED_MSG.format(error=exc))
            try:
                _write_error_log_direct(f"Failed to save SQLite config: {exc}")
            except Exception:
                pass
        return
    try:
        config_path = _get_config_path()
        CONFIG_PATH = config_path
        _write_json_atomic(config_path, payload)
    except E as exc:
        if O:
            O.showerror(AK, CONFIG_SAVE_FAILED_MSG.format(error=exc))
        try:
            _write_error_log_direct(f"Failed to save config.json: {exc}")
        except Exception:
            pass


def initialize_config(interactive=I):
    """Load configuration into the shared mutable config dictionary."""

    if not settings.is_runtime_initialized():
        settings.initialize_runtime(interactive=interactive)
    loaded = load_config(interactive=interactive)
    CONFIG.clear()
    CONFIG.update(loaded)
    return CONFIG
