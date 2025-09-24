"""Localization handling and translated UI strings."""

from .common import *  # noqa: F401,F403 - reuse legacy globals
from . import config, settings

LANG_CFG = "language.json"
LOCAL_SETTINGS_PATH = settings.BASE_DIR_SETTINGS_PATH
LANGUAGE_KEY = LANGUAGE_PREF_KEY
LANGUAGE_DEFAULT = LANGUAGE_PREF_DEFAULT
LC = settings.LC


def _iter_localization_roots():
    """Yield directories that may host localization resources."""

    roots = []
    seen = set()

    def register(path):
        if not path:
            return
        try:
            candidate = A.path.abspath(path)
        except (TypeError, ValueError, OSError):
            return
        if not candidate or candidate in seen:
            return
        seen.add(candidate)
        roots.append(candidate)

    def register_base(base_path):
        if not base_path:
            return
        register(A.path.join(base_path, "Localization"))
        register(base_path)

    try:
        settings_dir = A.path.dirname(A.path.abspath(LOCAL_SETTINGS_PATH))
    except (TypeError, ValueError, OSError):
        settings_dir = B
    register_base(settings_dir)

    exe_dir = A.path.dirname(getattr(sys, "executable", B) or B)
    register_base(exe_dir)

    if sys.argv:
        try:
            argv_dir = A.path.dirname(A.path.abspath(sys.argv[0]))
        except (TypeError, ValueError, OSError):
            argv_dir = B
        register_base(argv_dir)

    try:
        cwd = A.getcwd()
    except E:
        cwd = B
    register_base(cwd)

    register(LC)

    module_dir = A.path.dirname(A.path.abspath(__file__))
    register_base(module_dir)
    package_root = A.path.dirname(module_dir)
    register_base(package_root)

    return roots


def load_language_pref():
    """Read the saved language preference from ``local_settings.json``."""

    try:
        with x(LOCAL_SETTINGS_PATH, "r", encoding=k) as handle:
            data = Ar.load(handle)
        if Aq(data, dict):
            value = data.get(LANGUAGE_KEY, LANGUAGE_DEFAULT)
            if Aq(value, str):
                value = value.strip() or LANGUAGE_DEFAULT
                if value:
                    return value
    except E:
        pass
    for root in _iter_localization_roots():
        legacy_path = A.path.join(root, LANG_CFG)
        try:
            with x(legacy_path, "r", encoding=k) as handle:
                legacy_data = Ar.load(handle)
            if Aq(legacy_data, dict):
                value = legacy_data.get(LANGUAGE_KEY, LANGUAGE_DEFAULT)
                if Aq(value, str):
                    value = value.strip() or LANGUAGE_DEFAULT
                    if value:
                        try:
                            save_language_pref(value)
                        except E:
                            pass
                        try:
                            A.remove(legacy_path)
                        except E:
                            pass
                        global LC
                        LC = root if A.path.isdir(root) else A.path.dirname(root)
                        settings.LC = LC or settings.LC
                        return value
        except E:
            pass
    return LANGUAGE_DEFAULT


def save_language_pref(lang):
    """Persist the user's language preference to ``local_settings.json``."""

    value = lang.strip() if Aq(lang, str) else LANGUAGE_DEFAULT
    if not value:
        value = LANGUAGE_DEFAULT
    data = dict(BASE_DIR_SETTINGS_TEMPLATE)
    try:
        with x(LOCAL_SETTINGS_PATH, "r", encoding=k) as handle:
            existing = Ar.load(handle)
        if Aq(existing, dict):
            data.update(existing)
    except E:
        pass
    data[LANGUAGE_KEY] = value
    try:
        A.makedirs(A.path.dirname(LOCAL_SETTINGS_PATH) or ".", exist_ok=J)
    except E:
        pass
    try:
        with x(LOCAL_SETTINGS_PATH, T, encoding=k) as handle:
            Ar.dump(data, handle, indent=4)
    except E:
        pass


def load_localization(language=I):
    """Load translation strings for the requested language code."""

    lang_code = language
    if not lang_code or lang_code == "auto":
        try:
            BO.setlocale(BO.LC_ALL, "")
            lang_code = (BO.getlocale()[0] or "en").split("_")[0]
        except E:
            lang_code = "en"
    mapping = {"pl": "pl.json", "ua": "ua.json", "en": "eng.json"}
    filename = mapping.get(lang_code.lower(), "eng.json")
    for root in _iter_localization_roots():
        candidate = A.path.join(root, filename)
        if not A.path.exists(candidate):
            continue
        try:
            with x(candidate, "r", encoding=k) as handle:
                data = Ar.load(handle)
        except E:
            continue
        if Aq(data, dict):
            global LC
            resolved_root = root if A.path.isdir(root) else A.path.dirname(root)
            LC = resolved_root or LC
            settings.LC = LC or settings.LC
            return data
    return {}


LC = LC or settings.LC_DEFAULT
LANG_PREF = load_language_pref()
LANG = load_localization(LANG_PREF)
LANG_EN = load_localization("en")

settings.LC = LC

NO_FILE_LABEL = LANG.get("no_file", NO_FILE_FALLBACK)
LANGUAGE_TAB_LABEL = LANG.get("language_tab", "Język")
LANGUAGE_LABEL = LANG.get("language_label", "Język:")
PROCESSING_MSG = LANG.get("processing", PROCESSING_MSG)
PROCESSING_UI_MSG = LANG.get(
    "processing_ui", ">>> Processing, please wait..."
)
OPERATION_TITLE = LANG.get("operation_title", OPERATION_TITLE)
NETWORK_ERROR_MSG = LANG.get("network_error", NETWORK_ERROR_MSG)
PATH_NOT_FOUND_MSG = LANG.get("path_not_found", PATH_NOT_FOUND_MSG)
LOGIN_DATA_ERROR_MSG = LANG.get("login_data_error", LOGIN_DATA_ERROR_MSG)
MISSING_FIELDS_MSG = LANG.get("missing_fields", MISSING_FIELDS_MSG)
INCOMPLETE_DATA_MSG = LANG.get("incomplete_data", INCOMPLETE_DATA_MSG)
NO_DATA_MSG = LANG.get("no_data", NO_DATA_MSG)
CANCEL_LABEL = LANG.get("cancel", CANCEL_LABEL)
SETTINGS_LABEL = LANG.get("settings", SETTINGS_LABEL)
EDIT_LISTS_LABEL = LANG.get("edit_lists", EDIT_LISTS_LABEL)
LIST_TAB_NAMES_LABEL = LANG.get("list_tab_names", LIST_TAB_NAMES_LABEL)
LIST_TAB_TYPES_LABEL = LANG.get("list_tab_types", LIST_TAB_TYPES_LABEL)
LIST_TAB_MODELS_LABEL = LANG.get("list_tab_models", LIST_TAB_MODELS_LABEL)
LIST_TAB_COLORS_LABEL = LANG.get("list_tab_colors", LIST_TAB_COLORS_LABEL)
LIST_TAB_EXTRAS_LABEL = LANG.get("list_tab_extras", LIST_TAB_EXTRAS_LABEL)
LIST_ADD_BUTTON_LABEL = LANG.get("list_add_button", LIST_ADD_BUTTON_LABEL)
LIST_REMOVE_BUTTON_LABEL = LANG.get("list_remove_button", LIST_REMOVE_BUTTON_LABEL)
LIST_ADD_DIALOG_TITLE = LANG.get("list_add_title", LIST_ADD_DIALOG_TITLE)
LIST_REMOVE_DIALOG_TITLE = LANG.get("list_remove_title", LIST_REMOVE_DIALOG_TITLE)
LIST_ADD_PROMPT_MSG = LANG.get("list_add_prompt", LIST_ADD_PROMPT_MSG)
LIST_REMOVE_PROMPT_MSG = LANG.get("list_remove_prompt", LIST_REMOVE_PROMPT_MSG)
LIST_EDITOR_TAB_LABELS = {
    n: LIST_TAB_NAMES_LABEL,
    t: LIST_TAB_TYPES_LABEL,
    s: LIST_TAB_MODELS_LABEL,
    Y: LIST_TAB_COLORS_LABEL,
    d: LIST_TAB_EXTRAS_LABEL,
}
Ac = LANG.get("save_error", Ac)
AJ = LANG.get("not_in_list", AJ)
AK = LANG.get("error", AK)
CHANGE_LANGUAGE_LABEL = LANG.get("change_language", "Zmień język")
LANGUAGE_PROMPT = LANG.get("language_prompt", "Kod języka (pl, ua, eng):")
RESTART_TO_APPLY_LABEL = LANG.get(
    "restart_to_apply", "Uruchom ponownie aplikację, aby zastosować zmiany"
)
CONFIG_SAVE_FAILED_MSG = LANG.get(
    "config_save_failed",
    config.CONFIG_SAVE_FAILED_MSG,
)
config.CONFIG_SAVE_FAILED_MSG = CONFIG_SAVE_FAILED_MSG
LIST_CREATE_FAILED_MSG = LANG.get(
    "list_create_failed",
    "Nie udało się utworzyć pliku list.xlsx:\n{error}",
)
LIST_SAVE_FAILED_MSG = LANG.get(
    "list_save_failed",
    "Nie udało się zapisać pliku list.xlsx:\n{error}",
)
LIST_DATA_SAVE_FAILED_MSG = LANG.get(
    "list_data_save_failed",
    "Nie udało się zapisać danych do pliku list.xlsx:\n{error}",
)
FOLDER_OPEN_FAILED_MSG = LANG.get(
    "folder_open_failed",
    "Nie udało się otworzyć folderu:\n{error}",
)
OPERATION_ERRORS_MSG = LANG.get(
    "operation_errors",
    "Operacja zakończyła się z błędami. Sprawdź logi oraz folder kopii zapasowej: {backup}",
)
FTP_SEND_FAILED_MSG = LANG.get(
    "ftp_send_failed",
    "Dane lokalne zostały zapisane, jednak wysyłanie plików na serwer FTP nie powiodło się.\nPowód: {reason}",
)
FTP_SKIPPED_NO_EAN_MSG = LANG.get(
    "ftp_skipped_no_ean",
    "Dane lokalne zostały zapisane, jednak nie wysłano zdjęć na FTP z powodu braku prawidłowego kodu EAN-13.",
)
SQL_UPDATE_FAILED_MSG = LANG.get(
    "sql_update_failed",
    "Dane lokalne oraz FTP zostały zaktualizowane, jednak wystąpił błąd podczas aktualizacji bazy danych.\nPowód: {reason}",
)
SAVED_LABEL = LANG.get("saved", "Zapisano")
UPDATE_SUCCESS_MSG = LANG.get(
    "update_success", "Zaktualizowano dane dla EAN {ean}."
)
NO_EAN_LABEL = LANG.get("no_ean", "Brak EAN")
ENTER_EAN_TO_LOAD_MSG = LANG.get(
    "enter_ean_to_load", "Wprowadź kod EAN, aby wczytać dane."
)
CANNOT_SEARCH_NO_EAN_MSG = LANG.get(
    "cannot_search_no_ean", "Nie można wyszukać danych dla 'BRAK-EAN'."
)
NOT_FOUND_LABEL = LANG.get("not_found", "Nie znaleziono")
NO_SAVED_DATA_FOR_EAN_MSG = LANG.get(
    "no_saved_data_for_ean", "Brak zapisanych danych dla EAN {ean}."
)
FILL_REQUIRED_BEFORE_OPEN_MSG = LANG.get(
    "fill_required_before_open",
    "Uzupełnij wszystkie wymagane pola (nazwa, typ, model, kolor 1) przed otwarciem folderu.",
)
CHANGE_DATA_ADMIN_LABEL = LANG.get(
    "change_data_admin", "Zmień dane (Administrator)"
)
DATABASE_LABEL = LANG.get("database_label", "Baza danych:")
SERVER_LABEL = LANG.get("server_label", "Serwer:")
MSSQL_SERVER_LABEL = LANG.get("mssql_server", "MS SQL Server")
TEST_BUTTON_LABEL = LANG.get("test_button", "Testuj")
CONNECTED_LABEL = LANG.get("connected", "Połączono")
PASSWORD_LABEL = LANG.get("password_label", "Hasło:")
USER_LABEL = LANG.get("user_label", "Użytkownik:")
MYSQL_LABEL = LANG.get("mysql_label", "MySQL")
SAVE_LABEL = LANG.get("save", "Zapisz")
NO_PERMISSIONS_LABEL = LANG.get("no_permissions", "Brak uprawnień")
RUN_AS_ADMIN_MSG = LANG.get(
    "run_as_admin",
    "Uruchom operację z uprawnieniami administratora, aby edytować te ustawienia.",
)
IMAGE_SETTINGS_LABEL = LANG.get(
    "image_settings", "Ustawienia przetwarzania obrazów:"
)
RESIZE_LABEL = LANG.get(
    "resize_label", "Zmniejszaj obrazy większe niż"
)
PX_MAX_LABEL = LANG.get("px_max_label", "px (max wymiar)")
COMPRESS_LABEL = LANG.get(
    "compress_label", "Kompresuj JPEG (jakość)"
)
LIMIT_SIZE_LABEL = LANG.get(
    "limit_size_label", "Ogranicz rozmiar pliku do"
)
CONVERT_TIF_LABEL = LANG.get(
    "convert_tif_label", "Konwertuj .tif na"
)
FTP_SERVER_LABEL = LANG.get("ftp_server_label", "Serwer FTP:")
PORT_LABEL = LANG.get("port_label", "Port:")
FTP_PATH_LABEL = LANG.get(
    "ftp_path_label", "Ścieżka (katalog) na serwerze:"
)
FTP_TEST_LABEL = LANG.get(
    "ftp_test_label", "Test połączenia FTP:"
)
FTP_UPDATE_LABEL = LANG.get(
    "ftp_update_label", "Aktualizuj pliki na FTP:"
)
DB_TYPE_LABEL = LANG.get("db_type_label", "Typ bazy danych:")
SQL_UPDATE_LABEL = LANG.get(
    "sql_update_label", "Aktualizuj bazę przy zapisie:"
)
SQL_QUERY_LABEL = LANG.get("sql_query_label", "Zapytanie SQL:")
SQL_TEST_LABEL = LANG.get("sql_test_label", "Test połączenia SQL:")
NAME_LABEL = LANG.get("name_label", "Nazwa mebla*:")
TYPE_LABEL = LANG.get("type_label", "Typ mebla*:")
MODEL_LABEL = LANG.get("model_label", "Model mebla*:")
COLOR1_LABEL = LANG.get("color1_label", "Kolor 1*:")
COLOR2_LABEL = LANG.get("color2_label", "Kolor 2:")
COLOR3_LABEL = LANG.get("color3_label", "Kolor 3:")
EXTRA_LABEL = LANG.get("extra_label", "Dodatkowe:")
EAN_OPTIONAL_LABEL = LANG.get(
    "ean_optional_label", "EAN (opcjonalnie):"
)
LOAD_LABEL = LANG.get("load_label", "Wczytaj")
OPEN_FOLDER_LABEL = LANG.get(
    "open_folder", LANG_EN.get("open_folder", "Open folder")
)
CLEAR_LOG_LABEL = LANG.get("clear_log", LANG_EN.get("clear_log", "Clear log"))
UPDATE_LABEL = LANG.get("update_label", "Aktualizuj")
CHOOSE_LABEL = LANG.get("choose_label", "Wybierz")
NEW_COMBINATION_LABEL = LANG.get("new_combination_label", "Nowa kombinacja")
FTP_ERROR_LABEL = LANG.get("ftp_error", "Błąd FTP")
SQL_ERROR_LABEL = LANG.get("sql_error", "Błąd SQL")
IMAGES_TAB_LABEL = LANG.get("images_tab", "Obrazy")
FTP_TAB_LABEL = LANG.get("ftp_tab", "FTP")
SQL_TAB_LABEL = LANG.get("sql_tab", "SQL")
WARNING_LABEL = LANG.get("warning", "Uwaga")
SELECT_COMBINATION_TITLE = LANG.get(
    "select_combination_title", "Wybierz istniejącą kombinację"
)
SELECT_COMBINATION_PROMPT = LANG.get(
    "select_combination_prompt",
    "Wybierz istniejącą kombinację kolorów:",
)
SELECT_FILE_TITLE = LANG.get("select_file_title", "Wybierz plik")
OTHER_ERROR_MSG = LANG.get("other_error", "Inny błąd: {error}")
FTP_GENERIC_ERROR_MSG = LANG.get("ftp_generic_error", "Błąd FTP: {error}")
FILL_REQUIRED_BEFORE_SUBMIT_MSG = LANG.get(
    "fill_required_before_submit",
    "Uzupełnij wszystkie wymagane pola oznaczone * przed zatwierdzeniem.",
)
EAN_PROMPT_TITLE = LANG.get("ean_prompt_title", "EAN")
EAN_MISSING_PROMPT = LANG.get(
    "ean_missing_prompt",
    "Nie podano EAN.\nWprowadź kod EAN (13 cyfr) lub pozostaw puste aby użyć 'BRAK-EAN':",
)
APP_TITLE = LANG.get("app_title", "Katalogowanie zdjęć mebli")
