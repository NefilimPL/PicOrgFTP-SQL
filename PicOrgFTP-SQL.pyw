"""Application entry point."""

from picorgftp_sql.app import App
from picorgftp_sql.common import O, SETTINGS_LABEL
from picorgftp_sql.settings import BASE_DIR_OVERRIDE_WARNING


def main():
    """Start the GUI application and warn about configuration issues."""

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


if __name__ == "__main__":
    main()
