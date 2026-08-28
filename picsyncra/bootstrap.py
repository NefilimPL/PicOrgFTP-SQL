"""Runtime bootstrap helpers."""

from pathlib import Path

from . import config, settings
from .legacy_migration import migrate_legacy_data


def initialize_application_runtime(*, interactive=None):
    """Initialize runtime paths and configuration explicitly."""

    settings.initialize_runtime(interactive=interactive)
    migration = migrate_legacy_data(
        Path(settings.BASE_DIR_SETTINGS_PATH).parent,
        Path(settings.AC),
    )
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
        "migration": migration,
    }
