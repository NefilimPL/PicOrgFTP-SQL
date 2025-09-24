"""Convenience helpers for writing to the UI and rotating log files."""

from .common import *  # noqa: F401,F403 - reuse shared helpers
from .settings import AM, BM
from . import localization

AG = None


def set_app(app):
    """Register the Tk ``app`` instance so log messages can reach the GUI."""

    global AG
    AG = app


def rotate_log(path, max_bytes=1073741824, backups=3):
    """Rotate log files when they exceed ``max_bytes`` in size."""

    target = path
    try:
        if A.path.exists(target) and A.path.getsize(target) >= max_bytes:
            # Shift existing files up one index, pruning the oldest backup.
            for index in Ax(backups, 0, -1):
                src = f"{target}.{index}" if index > 1 else target
                dst = f"{target}.{index + 1}"
                if A.path.exists(src):
                    try:
                        if A.path.exists(dst):
                            A.remove(dst)
                    except Exception:
                        pass
                    try:
                        A.rename(src, dst)
                    except Exception:
                        pass
            with x(target, T, encoding=k) as handle:
                handle.write(f"[{A9.now().strftime(A6)}] Log rotated\n")
    except E:
        pass


def log_error(message, ui_message=None):
    """Write an error entry to the log files and optionally the UI."""

    try:
        rotate_log(AM)
        timestamp = A9.now().strftime(A6)
        with x(AM, "a", encoding=k) as handle:
            handle.write(f"[{timestamp}] [USER: {AO}] [PC: {AF}] ERROR: {message}\n")
    except E:
        pass
    try:
        if AG:
            if threading.current_thread() != threading.main_thread():
                AG.after(0, lambda msg=(ui_message or message): AG._ui_log(f"❗ {msg}"))
            else:
                AG._ui_log(f"❗ {ui_message or message}")
    except E:
        pass


def log_info(message, ui_message=None):
    """Write an informational log entry and mirror it to the UI."""

    try:
        rotate_log(BM)
        timestamp = A9.now().strftime(A6)
        with x(BM, "a", encoding=k) as handle:
            handle.write(f"[{timestamp}] [USER: {AO}] [PC: {AF}] {message}\n")
    except E:
        pass
    try:
        if AG:
            if threading.current_thread() != threading.main_thread():
                AG.after(0, lambda msg=(ui_message or message): AG._ui_log(f"• {msg}"))
            else:
                AG._ui_log(f"• {ui_message or message}")
    except E:
        pass


def log_error_loc(key, **kwargs):
    """Log a translated error message based on a localization key."""

    file_msg = localization.LANG_EN.get(key, key).format(**kwargs)
    ui_msg = localization.LANG.get(key, file_msg).format(**kwargs)
    log_error(file_msg, ui_msg)


def log_info_loc(key, **kwargs):
    """Log a translated info message based on a localization key."""

    file_msg = localization.LANG_EN.get(key, key).format(**kwargs)
    ui_msg = localization.LANG.get(key, file_msg).format(**kwargs)
    log_info(file_msg, ui_msg)
