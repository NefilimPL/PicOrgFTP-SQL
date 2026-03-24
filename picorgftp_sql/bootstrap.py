"""Runtime bootstrap helpers."""

from . import config, settings


def initialize_application_runtime(*, interactive=None):
    """Initialize runtime paths and configuration explicitly."""

    settings.initialize_runtime(interactive=interactive)
    config.initialize_config(interactive=interactive)
    return {
        "base_dir": settings.AC,
        "config_path": config.CONFIG_PATH,
        "warning": settings.BASE_DIR_OVERRIDE_WARNING,
    }
