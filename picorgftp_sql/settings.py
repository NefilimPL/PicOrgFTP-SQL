"""Base directory handling and shared paths."""

from .common import *  # noqa: F401,F403 - legacy global names


def _resolve_settings_root():
    """Return the folder that should host ``local_settings.json``."""

    if getattr(sys, "frozen", False):
        base_path = A.path.dirname(sys.executable)
        return base_path or A.getcwd()
    module_dir = A.path.dirname(A.path.abspath(__file__))
    project_root = A.path.abspath(A.path.join(module_dir, A.pardir))
    root_settings = A.path.join(project_root, BASE_DIR_SETTINGS_FILE)
    root_marker = A.path.join(project_root, "PicOrgFTP-SQL.pyw")
    if A.path.exists(root_settings) or A.path.exists(root_marker):
        base_path = project_root
    else:
        base_path = module_dir
    return base_path or A.getcwd()


def _iter_localization_roots():
    """Yield candidate directories that may contain localization files."""

    module_dir = A.path.dirname(A.path.abspath(__file__))
    project_root = A.path.abspath(A.path.join(module_dir, A.pardir))
    meipass = getattr(sys, "_MEIPASS", B)
    if getattr(sys, "frozen", False):
        exe_dir = A.path.dirname(sys.executable) or A.getcwd()
        yield A.path.join(exe_dir, "Localization")
        if meipass:
            yield A.path.join(meipass, "Localization")
            yield A.path.join(meipass, "picorgftp_sql", "Localization")
    yield A.path.join(module_dir, "Localization")
    yield A.path.join(project_root, "Localization")


def _resolve_localization_root():
    """Return the first existing localization directory from candidates."""

    for candidate in _iter_localization_roots():
        if candidate and A.path.isdir(candidate):
            return candidate
    module_dir = A.path.dirname(A.path.abspath(__file__))
    return A.path.join(module_dir, "Localization")


BASE_DIR_SETTINGS_PATH = A.path.join(_resolve_settings_root(), BASE_DIR_SETTINGS_FILE)
BASE_DIR_OVERRIDE_WARNING = I


def _load_base_dir_override(settings_path, template, fallback_value):
    """Read an override value from ``settings_path`` if one is available."""

    override_value = fallback_value
    try:
        if A.path.exists(settings_path):
            with x(settings_path, "r", encoding=k) as settings_file:
                data = Ar.load(settings_file)
            new_value = data.get("base_dir_override", fallback_value)
            if Aq(new_value, str):
                override_value = new_value.strip()
        else:
            try:
                with x(settings_path, T, encoding=k) as settings_file:
                    Ar.dump(template, settings_file, indent=4)
            except E:
                pass
    except E:
        pass
    return override_value if Aq(override_value, str) else fallback_value


def _save_base_dir_override(settings_path, template, value):
    """Persist ``value`` into ``settings_path`` while merging extra keys."""

    data = dict(template)
    try:
        if A.path.exists(settings_path):
            with x(settings_path, "r", encoding=k) as settings_file:
                existing = Ar.load(settings_file)
            if Aq(existing, dict):
                data.update(existing)
    except E:
        pass
    data["base_dir_override"] = value
    try:
        with x(settings_path, T, encoding=k) as settings_file:
            Ar.dump(data, settings_file, indent=4)
    except E:
        pass


def _ensure_directory_access(path):
    """Try to create ``path`` if required and return a success flag."""

    try:
        if not A.path.isdir(path):
            A.makedirs(path, exist_ok=J)
        return J, I
    except E as exc:
        return Ay, exc


def _prompt_for_base_dir(settings_path, template, current_value, message):
    """Interactively ask the user for a working directory location."""

    root = F.Tk()
    root.withdraw()
    try:
        if message:
            try:
                O.showwarning(SETTINGS_LABEL, message)
            except E:
                pass
        initial_dir = current_value or A.path.expanduser("~")
        while J:
            selected = BT.askdirectory(
                parent=root,
                title=BASE_DIR_PROMPT_TITLE,
                initialdir=initial_dir,
            )
            if not selected:
                try:
                    O.showerror(SETTINGS_LABEL, BASE_DIR_PROMPT_REQUIRED_MSG)
                except E:
                    pass
                raise SystemExit(0)
            selected = selected.strip()
            if not selected:
                try:
                    O.showwarning(SETTINGS_LABEL, BASE_DIR_INVALID_SELECTION_MSG)
                except E:
                    pass
                continue
            ok, error = _ensure_directory_access(selected)
            if ok:
                _save_base_dir_override(settings_path, template, selected)
                return selected, I
            initial_dir = selected
            try:
                details = f"\n\n{error}" if error else B
                O.showerror(SETTINGS_LABEL, f"{BASE_DIR_INVALID_SELECTION_MSG}{details}")
            except E:
                pass
    finally:
        try:
            root.destroy()
        except E:
            pass


def _ensure_base_dir_override(settings_path, template, fallback_value):
    """Resolve a usable base directory, prompting when necessary."""

    override_value = _load_base_dir_override(settings_path, template, fallback_value)
    candidate = override_value.strip() if Aq(override_value, str) else B
    if candidate:
        ok, error = _ensure_directory_access(candidate)
        if ok:
            return candidate, I
        message = (
            "Nie można uzyskać dostępu do katalogu wskazanego w pliku \"local_settings.json\":\n"
            f"{candidate}\n\n"
            f"{BASE_DIR_PROMPT_REASON_MSG}"
        )
        if error:
            message = f"{message}\n\n{error}"
    else:
        message = BASE_DIR_PROMPT_REASON_MSG
    return _prompt_for_base_dir(settings_path, template, candidate, message)


BASE_DIR_OVERRIDE, BASE_DIR_OVERRIDE_WARNING = _ensure_base_dir_override(
    BASE_DIR_SETTINGS_PATH,
    BASE_DIR_SETTINGS_TEMPLATE,
    BASE_DIR_OVERRIDE,
)


def get_localization_search_paths():
    """Return a list of unique directories that may host translation files."""

    seen = []
    for candidate in _iter_localization_roots():
        if candidate and candidate not in seen:
            seen.append(candidate)
    return seen


AC = BASE_DIR_OVERRIDE
l = A.path.join(AC, "_ZDJECIA PRZEROBIONE_")
LISTS_WORKBOOK_PATH = A.path.join(AC, "lists.xlsx")
AD = A.path.join(AC, "config.json")
AM = A.path.join(AC, "error_log.txt")
BM = A.path.join(AC, "changes_log.txt")
AN = A.path.join(AC, "temp_backup")
MODULE_DIR = A.path.dirname(A.path.abspath(__file__))
LC_DEFAULT = _resolve_localization_root()
LC = LC_DEFAULT
EXCEL_SHEETS = {n: n, t: t, s: s, Y: Y, d: d, W: W}
BW = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
]
