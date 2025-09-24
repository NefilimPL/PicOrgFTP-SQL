"""Base directory handling and shared paths."""

from .common import *  # noqa: F401,F403 - legacy global names


def _resolve_settings_root():
    """Return the folder that should host ``local_settings.json``."""

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", B) or A.getenv("_MEIPASS2", B)
        meipass_abs = I
        if meipass:
            try:
                meipass_abs = A.path.abspath(meipass)
            except (ValueError, OSError):
                meipass_abs = I
        candidates = []
        exe_dir = A.path.dirname(getattr(sys, "executable", B) or B)
        if exe_dir:
            candidates.append(exe_dir)
        if sys.argv:
            try:
                argv_path = A.path.dirname(A.path.abspath(sys.argv[0]))
            except (ValueError, OSError, TypeError):
                argv_path = B
            if argv_path and argv_path not in candidates:
                candidates.append(argv_path)
        try:
            cwd = A.getcwd()
        except E:
            cwd = B
        if cwd and cwd not in candidates:
            candidates.append(cwd)

        existing = []
        fallback = []
        for candidate in candidates:
            if not candidate:
                continue
            try:
                candidate_abs = A.path.abspath(candidate)
            except (ValueError, OSError):
                continue
            if meipass_abs:
                try:
                    if A.path.commonpath([candidate_abs, meipass_abs]) == meipass_abs:
                        continue
                except (ValueError, OSError):
                    pass
            settings_file = A.path.join(candidate_abs, BASE_DIR_SETTINGS_FILE)
            if A.path.isfile(settings_file):
                existing.append(candidate_abs)
            else:
                fallback.append(candidate_abs)
        if existing:
            return existing[0]
        if fallback:
            return fallback[0]
        try:
            return exe_dir or cwd or A.getcwd()
        except E:
            return exe_dir or cwd or B

    module_dir = A.path.dirname(A.path.abspath(__file__))
    project_root = A.path.abspath(A.path.join(module_dir, A.pardir))
    root_settings = A.path.join(project_root, BASE_DIR_SETTINGS_FILE)
    root_marker = A.path.join(project_root, "PicOrgFTP-SQL.pyw")
    if A.path.exists(root_settings) or A.path.exists(root_marker):
        base_path = project_root
    else:
        base_path = module_dir
    return base_path or A.getcwd()


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
                A.makedirs(A.path.dirname(settings_path) or ".", exist_ok=J)
            except E:
                pass
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
        A.makedirs(A.path.dirname(settings_path) or ".", exist_ok=J)
    except E:
        pass
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

AC = BASE_DIR_OVERRIDE
l = A.path.join(AC, "_ZDJECIA PRZEROBIONE_")
LISTS_WORKBOOK_PATH = A.path.join(AC, "lists.xlsx")
AD = A.path.join(AC, "config.json")
AM = A.path.join(AC, "error_log.txt")
BM = A.path.join(AC, "changes_log.txt")
AN = A.path.join(AC, "temp_backup")
MODULE_DIR = A.path.dirname(A.path.abspath(__file__))
LC_DEFAULT = A.path.join(MODULE_DIR, "Localization")
LC = LC_DEFAULT
EXCEL_SHEETS = {n: n, t: t, s: s, Y: Y, d: d, W: W}
BW = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
]
