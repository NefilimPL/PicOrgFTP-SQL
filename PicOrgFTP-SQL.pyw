"""Application entry point."""

import json
import os
import traceback


def _resolve_boot_log_dir():
    settings_path = os.path.join(os.getcwd(), "local_settings.json")
    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            base_dir = data.get("base_dir_override")
            if isinstance(base_dir, str) and base_dir.strip():
                return base_dir.strip()
    except Exception:
        pass
    return os.getcwd()


def _write_boot_log(message):
    log_dir = _resolve_boot_log_dir()
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = os.getcwd()
    log_path = os.path.join(log_dir, "error_log_boot.txt")
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


def _show_boot_error(message):
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Błąd aplikacji", message)
        root.destroy()
    except Exception:
        pass


def main():
    """Start the GUI application and warn about configuration issues."""

    try:
        from picorgftp_sql.app import App
        from picorgftp_sql.common import O, SETTINGS_LABEL
        from picorgftp_sql.settings import BASE_DIR_OVERRIDE_WARNING
    except Exception:
        trace = traceback.format_exc()
        boot_message = (
            "Krytyczny błąd podczas uruchamiania aplikacji.\n\n"
            f"{trace}\n\nSzczegóły zapisano w error_log_boot.txt."
        )
        _write_boot_log(trace)
        _show_boot_error(boot_message)
        raise

    try:
        app = App()
        if BASE_DIR_OVERRIDE_WARNING:
            O.showwarning(SETTINGS_LABEL, BASE_DIR_OVERRIDE_WARNING)
        for combo in (
            app.combo_name,
            app.combo_type,
            app.combo_model,
            app.combo_color1,
            app.combo_color2,
            app.combo_color3,
            app.combo_extra,
        ):
            combo.configure(postcommand=lambda c=combo: app._style_combobox_list(c))
        app.mainloop()
    except Exception:
        trace = traceback.format_exc()
        boot_message = (
            "Krytyczny błąd podczas uruchamiania aplikacji.\n\n"
            f"{trace}\n\nSzczegóły zapisano w error_log_boot.txt."
        )
        _write_boot_log(trace)
        _show_boot_error(boot_message)
        raise


if __name__ == "__main__":
    main()
