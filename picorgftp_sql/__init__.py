"""PicOrgFTP-SQL package."""

__all__ = ["App", "config", "localization"]


def __getattr__(name):
    if name == "App":
        from .app import App

        return App
    if name == "config":
        from . import config

        return config
    if name == "localization":
        from . import localization

        return localization
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(__all__) | set(globals()))
