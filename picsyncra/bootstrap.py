"""Runtime bootstrap helpers."""

from pathlib import Path

from . import config, settings
from .brand import SQLITE_FILENAME
from .legacy_migration import (
    _LEGACY_SQLITE_FILENAME,
    process_pending_legacy_target_cleanups,
)
from .sqlite_coordination import clear_retired_database_marker
from .storage_settings import resolve_backup_dir


def _clear_completed_legacy_handover_markers() -> None:
    """Do not leave a completed handover marker in the user data directory."""

    try:
        process_pending_legacy_target_cleanups(Path(resolve_backup_dir()))
    except OSError:
        pass
    roots = (Path(settings.AC), Path(settings.BASE_DIR_SETTINGS_PATH).parent)
    for root in roots:
        legacy_database = root / _LEGACY_SQLITE_FILENAME
        current_database = root / SQLITE_FILENAME
        if current_database.is_file():
            clear_retired_database_marker(legacy_database)


def initialize_application_runtime(*, interactive=None):
    """Initialize runtime paths and configuration explicitly."""

    settings.initialize_runtime(interactive=interactive)
    _clear_completed_legacy_handover_markers()
    config.initialize_config(interactive=interactive)
    if settings.BASE_DIR_OVERRIDE_WARNING:
        try:
            from .logging_utils import log_error

            log_error(f"Runtime base directory fallback: {settings.BASE_DIR_OVERRIDE_WARNING}")
        except Exception:
            pass
    return {
        "base_dir": settings.AC,
        "config_path": config.CONFIG_PATH,
        "warning": settings.BASE_DIR_OVERRIDE_WARNING,
    }
