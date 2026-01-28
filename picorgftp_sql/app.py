"""Main Tkinter application class."""

import copy
import queue
import re
import traceback
import tokenize

from .common import *  # noqa: F401,F403
from .excel_utils import (
    add_to_list,
    label_category,
    prepare_excel_lists,
    remove_from_list,
    save_ean_entry,
)
from .logging_utils import log_error, log_error_loc, log_info, log_info_loc, set_app
from .system_utils import get_file_lock_user, is_admin
from .database import connect_db
from .config import save_config
from . import config, localization, settings, common, encryption
from .settings import BW, EXCEL_SHEETS, AN, l
from .slot_utils import normalize_slot_definitions, normalize_sql_column_map, next_slot_prefix

D = config.CONFIG
LANG_PREF = localization.LANG_PREF

from .localization import *  # noqa: F401,F403

EXCLUDED_CONVERT_FORMATS = {"PDF", "EPS", "PS", "XPS"}


def _build_image_extension_map():
    extensions = {}
    try:
        for ext, fmt in AA.registered_extensions().items():
            if not ext:
                continue
            fmt_upper = fmt.upper()
            if fmt_upper in EXCLUDED_CONVERT_FORMATS:
                continue
            extensions[ext.lower()] = fmt_upper
    except Exception:
        pass
    return extensions


IMAGE_EXTENSION_FORMATS = _build_image_extension_map()


def _build_format_extension_map():
    format_map = {}
    try:
        for ext, fmt in AA.registered_extensions().items():
            if not ext:
                continue
            fmt_upper = fmt.upper()
            if fmt_upper in EXCLUDED_CONVERT_FORMATS or fmt_upper not in AA.SAVE:
                continue
            ext_lower = ext.lower()
            if fmt_upper == "JPEG":
                if ext_lower == ".jpg":
                    format_map[fmt_upper] = ext_lower
                    continue
                if fmt_upper in format_map:
                    continue
            format_map.setdefault(fmt_upper, ext_lower)
    except Exception:
        pass
    return format_map


FORMAT_TO_EXTENSION = _build_format_extension_map()


def _build_convert_format_choices():
    formats = sorted(set(FORMAT_TO_EXTENSION))
    if "JPEG" in formats and "JPG" not in formats:
        formats.insert(0, "JPG")
    if not formats:
        formats = [At, "JPG", "BMP", "GIF"]
    return formats


CONVERT_TARGET_FORMATS = _build_convert_format_choices()


def _pick_lanczos_filter():
    if hasattr(AA, "Resampling"):
        return AA.Resampling.LANCZOS
    return getattr(AA, "LANCZOS", getattr(AA, "BICUBIC", 3))


LANCZOS_FILTER = _pick_lanczos_filter()

FORMAT_INFO_TEXTS = {
    "JPEG": LANG.get(
        "format_info_jpeg",
        "JPEG/JPG: stratny format, zwykle najmniejszy rozmiar; brak przezroczystości.",
    ),
    "PNG": LANG.get(
        "format_info_png",
        "PNG: bezstratny, wspiera przezroczystość; zwykle większy rozmiar.",
    ),
    "WEBP": LANG.get(
        "format_info_webp",
        "WEBP: może być stratny lub bezstratny; zwykle mniejszy niż PNG/JPEG.",
    ),
    "BMP": LANG.get(
        "format_info_bmp",
        "BMP: bez kompresji; bardzo duży rozmiar.",
    ),
    "GIF": LANG.get(
        "format_info_gif",
        "GIF: ograniczona paleta kolorów, dobra do prostych grafik; mniejszy niż PNG.",
    ),
    "TIFF": LANG.get(
        "format_info_tiff",
        "TIFF: często bezstratny, duży rozmiar; używany w skanach.",
    ),
}


def _format_info_text(fmt):
    if not fmt:
        return LANG.get(
            "format_info_placeholder",
            "Wybierz format, aby zobaczyć opis. Rozmiar zależy od treści obrazu.",
        )
    fmt_upper = fmt.upper()
    if fmt_upper == "JPG":
        fmt_upper = "JPEG"
    info = FORMAT_INFO_TEXTS.get(fmt_upper)
    if info:
        return info
    generic = LANG.get(
        "format_info_generic",
        "Brak opisu dla tego formatu. Rozmiar zależy od treści obrazu.",
    )
    return f"{fmt_upper}: {generic}"
class App(BU.Tk):
    def __init__(B):
        """Initialise the Tk window, form state and runtime caches."""

        super().__init__()
        B.title(APP_TITLE)
        B.geometry("1200x800")
        B.style = C.Style()
        B.style.theme_use("clam")
        B.style.configure(Z, fieldbackground=LIGHT_GREEN)
        B._configure_styles()
        B._slot_status = {
            "empty": NO_FILE_LABEL,
            "ready": LANG.get("slot_status_ready", "Gotowe"),
            "loading": LANG.get("slot_status_loading", "Wczytywanie"),
            "downloading": LANG.get("slot_status_downloading", "Pobieranie"),
            "uploading": LANG.get("slot_status_uploading", "Wysylanie"),
            "processing": LANG.get("slot_status_processing", "Przetwarzanie"),
        }
        D_ = prepare_excel_lists()
        if not isinstance(D_, dict):
            D_ = {}
        B.entries = D_.get(W, {})
        if not isinstance(B.entries, dict):
            B.entries = {}
        if W in D_:
            D_.pop(W)
        B.lists = D_
        for key in (n, t, s, Y, d):
            if not isinstance(B.lists.get(key), list):
                B.lists[key] = []
        if not A.path.isdir(l):
            A.makedirs(l, exist_ok=J)
        E_ = [B_.upper() for B_ in A.listdir(l) if A.path.isdir(A.path.join(l, B_))]
        G_ = [A_ for A_ in B.lists[n] if A_ not in E_]
        B.lists[n] = E_ + G_
        B.var_name = F.StringVar()
        B.var_type = F.StringVar()
        B.var_model = F.StringVar()
        B.var_color1 = F.StringVar()
        B.var_color2 = F.StringVar()
        B.var_color3 = F.StringVar()
        B.var_extra = F.StringVar()
        B.var_ean = F.StringVar()
        B.pending_additions = {}
        B.pending_deletions = {}
        B.pending_ftp_deletions = {}
        B.ftp_remote_only = {}
        B.ftp_presence = {}
        B.ftp_downloaded_final = set()
        B.sql_presence = I
        B._thumb_queue = queue.Queue()
        B._thumb_tokens = {}
        B._scrolling = h
        B._scroll_idle_job = I
        B.opt_resize = F.BooleanVar(value=J)
        B.opt_compress = F.BooleanVar(value=h)
        B.opt_maxsize = F.BooleanVar(value=h)
        B.resize_max_dim = F.IntVar(value=2000)
        B.compress_quality = F.IntVar(value=85)
        B.max_file_kb = F.IntVar(value=500)
        B.opt_convert_tif = F.BooleanVar(value=J)
        B.tif_target_format = F.StringVar(value=At)
        B.loading_by_ean = h
        B.suppress_scan = h
        B.model_select_win_open = h
        B._list_editor_window = I
        B._list_editor_notebook = I
        B._list_editor_tabs = {}
        B._settings_window = I
        B._active_list_prompts = set()
        B._last_focus_widget = I
        B.dragging_idx = I
        B.original_files = {}
        B.is_processing = h
        B._code_check_running = h
        B._code_check_last_report = ""
        B._ui_check_running = h
        B._ui_check_last_report = ""
        B.logged_counts = h
        B.suppress_next_lookup = h
        B.slot_definitions = []
        B.sql_column_map = {}
        B._load_slot_config()
        B._build_form()
        B._build_slots()
        B._thumb_worker = threading.Thread(target=B._thumbnail_worker, daemon=J)
        B._thumb_worker.start()
        B._slot_index_by_prefix = {
            slot["prefix"]: idx for idx, slot in A0(B.slot_definitions)
        }
        H_ = Q(E_)
        B.combo_name.existing_count = H_
        set_app(B)
        B._install_exception_handlers()

    def report_callback_exception(A, exc, val, tb):
        A._handle_exception(exc, val, tb, context="Tk callback")

    def _install_exception_handlers(A):
        def _sys_excepthook(exc_type, exc, tb):
            A._handle_exception(exc_type, exc, tb, context="Unhandled exception")

        sys.excepthook = _sys_excepthook

        if hasattr(threading, "excepthook"):
            def _thread_excepthook(args):
                context = f"Thread: {getattr(args.thread, 'name', 'unknown')}"
                A._handle_exception(
                    args.exc_type,
                    args.exc_value,
                    args.exc_traceback,
                    context=context,
                )

            threading.excepthook = _thread_excepthook

    def _handle_exception(A, exc_type, exc, tb, context=B):
        trace = "".join(traceback.format_exception(exc_type, exc, tb))
        message = f"{context}\n{trace}" if context else trace
        log_error(message)
        title = LANG.get("critical_error_title", "Błąd aplikacji")
        body = LANG.get(
            "critical_error_message",
            "Wystąpił krytyczny błąd aplikacji.\n\n{error}\n\nSzczegóły zapisano w logach.",
        )
        payload = body.format(error=exc)

        def _show_error():
            try:
                O.showerror(title, payload)
            except E:
                pass

        if threading.current_thread() != threading.main_thread():
            try:
                A.after(0, _show_error)
            except E:
                pass
        else:
            _show_error()

    def _configure_styles(A):
        A._ui_colors = {
            "bg": "#f6f4f0",
            "card": "#ffffff",
            "slot_bg": "#f1efeb",
            "slot_border": "#d2cdc5",
            "muted": "#6f6b65",
            "accent": "#2f6f60",
            "progress_trough": "#e7e2da",
        }
        A.configure(bg=A._ui_colors["bg"])
        A.style.configure("App.TFrame", background=A._ui_colors["bg"])
        A.style.configure("Card.TFrame", background=A._ui_colors["card"])
        A.style.configure("Settings.TFrame", background=A._ui_colors["card"])
        A.style.configure(
            "Settings.TLabel",
            background=A._ui_colors["card"],
            font=("Segoe UI", 9),
        )
        A.style.configure(
            "SettingsHeader.TLabel",
            background=A._ui_colors["card"],
            font=("Segoe UI Semibold", 9),
        )
        A.style.configure(
            "SettingsHint.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["muted"],
            font=("Segoe UI", 8),
        )
        A.style.configure(
            "Settings.TNotebook",
            background=A._ui_colors["bg"],
            borderwidth=0,
        )
        A.style.configure(
            "Settings.TNotebook.Tab",
            padding=(12, 6),
            font=("Segoe UI Semibold", 9),
        )
        A.style.map(
            "Settings.TNotebook.Tab",
            background=[("selected", A._ui_colors["card"])],
            foreground=[("selected", "black")],
        )
        A.style.configure(
            "Form.TLabel",
            background=A._ui_colors["card"],
            font=("Segoe UI", 9),
        )
        A.style.configure(
            "SlotTitle.TLabel",
            background=A._ui_colors["card"],
            font=("Segoe UI Semibold", 9),
        )
        A.style.configure(
            "SlotStatus.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["muted"],
            font=("Segoe UI", 8),
        )
        A.style.configure(
            "SlotFooter.TFrame",
            background=A._ui_colors["card"],
        )
        A.style.configure("TButton", padding=(10, 4), font=("Segoe UI Semibold", 9))
        A.style.configure("TCombobox", padding=(6, 3), font=("Segoe UI", 9))
        A.style.configure("TEntry", font=("Segoe UI", 9))
        A.style.configure("Slot.TProgressbar", troughcolor=A._ui_colors["progress_trough"])
        A.style.configure("Slot.TProgressbar", background=A._ui_colors["accent"])
        base_layout = A.style.layout("Horizontal.TProgressbar")
        if base_layout:
            A.style.layout("Horizontal.Slot.TProgressbar", base_layout)

    def _trigger_test_error(A, key):
        if key == "zero_div":
            1 / 0
        elif key == "file_missing":
            with x("__missing_file__.tmp", "r", encoding=k):
                pass
        elif key == "value_error":
            raise ValueError(LANG.get("error_test_value_message", "Testowy błąd ValueError."))
        elif key == "thread_error":
            def _worker():
                raise RuntimeError(
                    LANG.get("error_test_thread_message", "Testowy błąd w wątku.")
                )

            threading.Thread(target=_worker, name="TestErrorThread").start()
        else:
            raise RuntimeError(LANG.get("error_test_generic_message", "Testowy błąd runtime."))

    def _collect_code_diagnostics(B):
        module_dir = A.path.dirname(A.path.abspath(__file__))
        project_root = A.path.abspath(A.path.join(module_dir, A.pardir))
        root = project_root
        if not A.path.isdir(A.path.join(project_root, "picorgftp_sql")):
            root = module_dir
        files = []
        skip_dirs = {".git", "__pycache__", "venv", ".venv", "dist", "build"}
        if A.path.isdir(root):
            for dirpath, dirnames, filenames in A.walk(root):
                dirnames[:] = [d for d in dirnames if d not in skip_dirs]
                for filename in filenames:
                    if filename.lower().endswith((".py", ".pyw")):
                        files.append(A.path.join(dirpath, filename))
        files.sort()
        errors = []
        for path in files:
            lines = []
            try:
                with tokenize.open(path) as handle:
                    source = handle.read()
                lines = source.splitlines()
                compile(source, path, "exec")
            except (SyntaxError, IndentationError) as exc:
                line_no = Aj(exc, "lineno", I) or 0
                col_no = Aj(exc, "offset", I) or 0
                message = Aj(exc, "msg", G(exc))
                kind = type(exc).__name__
                if message:
                    if not message.startswith(kind):
                        message = f"{kind}: {message}"
                else:
                    message = kind
                line_text = Aj(exc, "text", I)
                if line_text is I and line_no and line_no <= Q(lines):
                    line_text = lines[line_no - 1]
                if line_text is not I:
                    line_text = G(line_text).rstrip("\n")
                errors.append(
                    {
                        "path": path,
                        "line": line_no,
                        "col": col_no,
                        "message": message,
                        "text": line_text or B,
                    }
                )
            except E as exc:
                errors.append(
                    {
                        "path": path,
                        "line": 0,
                        "col": 0,
                        "message": f"{type(exc).__name__}: {exc}",
                        "text": B,
                    }
                )
        return {"root": root, "files": files, "errors": errors}

    def _format_code_check_report(A, result):
        timestamp = A9.now().strftime(A6)
        root = result.get("root") or B
        files = result.get("files") or []
        errors = result.get("errors") or []
        lines = [
            LANG.get("code_check_report_title", "Raport diagnostyki kodu"),
            LANG.get("code_check_report_time", "Czas: {time}").format(time=timestamp),
        ]
        if root:
            lines.append(
                LANG.get("code_check_report_root", "Katalog: {path}").format(
                    path=root
                )
            )
        lines.append(
            LANG.get("code_check_report_files", "Pliki: {count}").format(
                count=Q(files)
            )
        )
        lines.append(
            LANG.get("code_check_report_errors", "Błędy: {count}").format(
                count=Q(errors)
            )
        )
        lines.append(B)
        if errors:
            lines.append(
                LANG.get("code_check_report_errors_header", "Lista błędów:")
            )
            for idx, err in A0(errors, 1):
                line_no = err.get("line", 0) or 0
                col_no = err.get("col", 0) or 0
                lines.append(
                    LANG.get(
                        "code_check_report_error_item",
                        "{idx}. {file} ({line}:{col})",
                    ).format(
                        idx=idx,
                        file=err.get("path", B),
                        line=line_no,
                        col=col_no,
                    )
                )
                message = err.get("message", B)
                if message:
                    lines.append(f"  {message}")
                line_text = err.get("text", B)
                if line_text:
                    lines.append(f"  {line_text}")
                    if col_no:
                        caret = " " * max(col_no - 1, 0) + "^"
                        lines.append(f"  {caret}")
                lines.append(B)
        else:
            lines.append(
                LANG.get(
                    "code_check_report_no_errors", "Brak błędów składni."
                )
            )
        if files:
            lines.append(B)
            lines.append(
                LANG.get("code_check_report_files_header", "Sprawdzone pliki:")
            )
            for path in files:
                lines.append(f"- {path}")
        return "\n".join(lines)

    def _run_code_diagnostics(A, status_var=I, button=I, report_widget=I):
        if Aj(A, "_code_check_running", h):
            return
        A._code_check_running = J
        if status_var:
            status_var.set(
                LANG.get("code_check_running", "Sprawdzanie kodu...")
            )
        if button:
            try:
                button.configure(state=V)
            except E:
                pass
        if report_widget:
            try:
                report_widget.configure(state=Az)
                report_widget.delete(A_, F.END)
                report_widget.configure(state=Ak)
            except E:
                pass

        def finalize(result):
            A._code_check_running = h
            if button:
                try:
                    button.configure(state=X)
                except E:
                    pass
            files = result.get("files") or []
            errors = result.get("errors") or []
            report_text = A._format_code_check_report(result)
            A._code_check_last_report = report_text
            if report_widget:
                try:
                    report_widget.configure(state=Az)
                    report_widget.delete(A_, F.END)
                    if report_text:
                        report_widget.insert(F.END, report_text)
                    report_widget.configure(state=Ak)
                except E:
                    pass
            if not files:
                msg = LANG.get(
                    "code_check_no_sources",
                    "Nie znaleziono plików źródłowych do sprawdzenia.",
                )
                if status_var:
                    status_var.set(msg)
                log_info_loc("code_check_no_sources")
                return
            total = Q(files)
            if not errors:
                msg = LANG.get(
                    "code_check_ok",
                    "Sprawdzono {count} plików. Nie wykryto błędów składni.",
                ).format(count=total)
                if status_var:
                    status_var.set(msg)
                log_info_loc("code_check_ok", count=total)
                return
            error_count = Q(errors)
            msg = LANG.get(
                "code_check_error_summary",
                "Wykryto {errors} błędów składni w {count} plikach. Szczegóły w logu.",
            ).format(errors=error_count, count=total)
            status_lines = [msg]
            preview_lines = []
            preview_header = LANG.get("code_check_error_preview", B)
            log_error_loc(
                "code_check_error_summary", errors=error_count, count=total
            )
            file_template = localization.LANG_EN.get(
                "code_check_error_detail",
                "Syntax error in {file} ({line}:{col}): {error}",
            )
            ui_template = LANG.get(
                "code_check_error_detail",
                "Błąd składni w {file} ({line}:{col}): {error}",
            )
            item_template = LANG.get(
                "code_check_error_item",
                "- {file} ({line}:{col}): {error}",
            )
            shown = 3
            max_ui = 5
            for idx, err in A0(errors):
                file_msg = file_template.format(
                    file=err.get("path", B),
                    line=err.get("line", 0),
                    col=err.get("col", 0),
                    error=err.get("message", B),
                )
                ui_msg = ui_template.format(
                    file=err.get("path", B),
                    line=err.get("line", 0),
                    col=err.get("col", 0),
                    error=err.get("message", B),
                )
                if idx < shown:
                    preview_lines.append(
                        item_template.format(
                            file=err.get("path", B),
                            line=err.get("line", 0),
                            col=err.get("col", 0),
                            error=err.get("message", B),
                        )
                    )
                if idx < max_ui:
                    log_error(file_msg, ui_message=ui_msg)
                else:
                    log_error(file_msg, ui_message=B)
            if error_count > shown:
                preview_lines.append(
                    LANG.get(
                        "code_check_error_more",
                        "... i {count} więcej",
                    ).format(count=error_count - shown)
                )
            if preview_lines:
                if preview_header:
                    status_lines.append(preview_header)
                status_lines.extend(preview_lines)
            if status_var:
                status_var.set("\n".join(status_lines))

        def worker():
            result = A._collect_code_diagnostics()
            A.after(0, lambda: finalize(result))

        threading.Thread(target=worker, daemon=J).start()

    def _scan_button_commands(A, root_widget=I):
        target = root_widget or A
        missing = []

        def _walk(widget):
            try:
                children = widget.winfo_children()
            except E:
                return
            for child in children:
                try:
                    cls = child.winfo_class()
                except E:
                    cls = B
                if cls in ("TButton", "Button"):
                    try:
                        cmd = child.cget("command")
                    except E:
                        cmd = B
                    try:
                        state = child.cget("state")
                    except E:
                        state = B
                    disabled = h
                    if state:
                        disabled = "disabled" in G(state)
                    if not cmd and not disabled:
                        text = B
                        try:
                            text = child.cget("text")
                        except E:
                            pass
                        missing.append(
                            {"path": G(child), "text": text, "state": state or B}
                        )
                _walk(child)

        _walk(target)
        return missing

    def _collect_toplevels(A):
        tops = []
        try:
            children = A.winfo_children()
        except E:
            return tops
        for child in children:
            try:
                if child.winfo_class() == "Toplevel":
                    tops.append(child)
            except E:
                pass
        return tops

    def _close_toplevel(A, win):
        if not win:
            return
        close_cb = Aj(win, "_close_window", I)
        if callable(close_cb):
            try:
                close_cb()
                return
            except E:
                pass
        try:
            if Aj(win, "grab_current", I) == win:
                win.grab_release()
        except E:
            pass
        try:
            win.destroy()
        except E:
            pass

    def _ui_test_after(A):
        flag = F.StringVar(value="pending")

        def _mark(value):
            if flag.get() == "pending":
                flag.set(value)

        A.after(10, lambda: _mark("ok"))
        A.after(200, lambda: _mark("timeout"))
        A.wait_variable(flag)
        if flag.get() == "ok":
            return J, B
        return h, LANG.get(
            "ui_check_detail_timeout", "Timeout waiting for after()."
        )

    def _ui_test_button_invoke(A, parent):
        hit = {"ok": h}

        def _mark():
            hit["ok"] = J

        btn = C.Button(parent, text="__ui_test__", command=_mark)
        detail = B
        try:
            btn.invoke()
            ok = hit["ok"]
            if not ok:
                detail = LANG.get(
                    "ui_check_detail_invoke",
                    "invoke() did not trigger.",
                )
        except E as exc:
            ok = h
            detail = G(exc)
        try:
            btn.destroy()
        except E:
            pass
        return ok, detail

    def _ui_test_event_binding(A, parent):
        hit = {"ok": h}

        def _mark(event=I):
            hit["ok"] = J

        btn = C.Button(parent, text="__ui_test__")
        detail = B
        try:
            btn.bind("<Button-1>", _mark)
            btn.event_generate("<Button-1>")
            try:
                A.update()
            except E:
                pass
            ok = hit["ok"]
            if not ok:
                detail = LANG.get(
                    "ui_check_detail_event",
                    "Click event was not handled.",
                )
        except E as exc:
            ok = h
            detail = G(exc)
        try:
            btn.destroy()
        except E:
            pass
        return ok, detail

    def _ui_test_open_list_editor(A):
        win = I
        detail = B
        ok = h
        try:
            win = A._open_list_editor()
            if win and Aj(win, "winfo_exists", I):
                ok = bool(win.winfo_exists())
            if not ok:
                detail = LANG.get(
                    "ui_check_detail_list_editor",
                    "List editor window failed to open.",
                )
        except E as exc:
            ok = h
            detail = G(exc)
        A._close_toplevel(win)
        return ok, detail

    def _ui_test_open_settings(A):
        win = I
        detail = B
        ok = h
        existing = getattr(A, "_settings_window", I)
        had_existing = h
        if existing and Aj(existing, "winfo_exists", I):
            try:
                had_existing = bool(existing.winfo_exists())
            except E:
                had_existing = h
        try:
            win = A._open_settings()
            if win and Aj(win, "winfo_exists", I):
                ok = bool(win.winfo_exists())
            if not ok:
                detail = LANG.get(
                    "ui_check_detail_settings",
                    "Settings window failed to open.",
                )
        except E as exc:
            ok = h
            detail = G(exc)
        if not had_existing:
            A._close_toplevel(win)
        return ok, detail

    def _ui_test_safe_button_clicks(A):
        results = []
        buttons = [
            ("ui_check_button_settings", Aj(A, "btn_settings", I)),
            ("ui_check_button_edit_lists", Aj(A, "btn_edit_lists", I)),
            ("ui_check_button_clear_log", Aj(A, "btn_clear_log", I)),
        ]
        for label_key, btn in buttons:
            name = LANG.get(label_key, label_key)
            if not btn:
                results.append(
                    {
                        "name": name,
                        "ok": h,
                        "detail": LANG.get(
                            "ui_check_detail_button_missing",
                            "Button not found.",
                        ),
                    }
                )
                continue
            try:
                state = btn.cget("state")
            except E:
                state = B
            if state and "disabled" in G(state):
                results.append(
                    {
                        "name": name,
                        "ok": J,
                        "detail": LANG.get(
                            "ui_check_detail_button_disabled",
                            "Skipped (disabled).",
                        ),
                    }
                )
                continue
            before = {G(w) for w in A._collect_toplevels()}
            detail = B
            ok = J
            try:
                btn.invoke()
                try:
                    A.update_idletasks()
                except E:
                    pass
            except E as exc:
                ok = h
                detail = LANG.get(
                    "ui_check_detail_button_invoke_error",
                    "Invoke error: {error}",
                ).format(error=exc)
            after = A._collect_toplevels()
            for win in after:
                if G(win) not in before:
                    A._close_toplevel(win)
            results.append({"name": name, "ok": ok, "detail": detail})
        return results

    def _ui_test_toplevel(A):
        top = F.Toplevel(A)
        detail = B
        ok = h
        try:
            top.title(LANG.get("ui_check_temp_window", "Test window"))
            top.geometry("240x120+60+60")
            top.update_idletasks()
            ok = bool(top.winfo_exists())
            if not ok:
                detail = LANG.get(
                    "ui_check_detail_toplevel", "Window creation failed."
                )
        except E as exc:
            ok = h
            detail = G(exc)
        try:
            top.destroy()
        except E:
            pass
        return ok, detail

    def _ui_test_modal(A):
        top = F.Toplevel(A)
        detail = B
        ok = h
        try:
            top.grab_set()
            current = top.grab_current()
            ok = current == top
            if not ok:
                detail = LANG.get(
                    "ui_check_detail_modal", "Modal grab failed."
                )
        except E as exc:
            ok = h
            detail = G(exc)
        try:
            top.grab_release()
        except E:
            pass
        try:
            top.destroy()
        except E:
            pass
        return ok, detail

    def _ui_test_scrolledtext(A, parent):
        frame = C.Frame(parent)
        detail = B
        ok = h
        try:
            st = BS.ScrolledText(frame, width=20, height=2, wrap="word")
            st.insert(F.END, "test")
            text = st.get(A_, F.END).strip()
            st.configure(state=Ak)
            ok = text == "test"
            if not ok:
                detail = LANG.get(
                    "ui_check_detail_scrolledtext",
                    "ScrolledText read/write failed.",
                )
        except E as exc:
            ok = h
            detail = G(exc)
        try:
            frame.destroy()
        except E:
            pass
        return ok, detail

    def _ui_test_combobox(A, parent):
        frame = C.Frame(parent)
        detail = B
        ok = h
        try:
            combo = C.Combobox(frame, values=["A", "B"], state="readonly")
            combo.set("B")
            ok = combo.get() == "B"
            if not ok:
                detail = LANG.get(
                    "ui_check_detail_combobox", "Combobox set/get failed."
                )
        except E as exc:
            ok = h
            detail = G(exc)
        try:
            frame.destroy()
        except E:
            pass
        return ok, detail

    def _format_ui_check_report(A, results, missing_buttons):
        timestamp = A9.now().strftime(A6)
        failures = Q([r for r in results if not r.get("ok")])
        lines = [
            LANG.get("ui_check_report_title", "UI diagnostics report"),
            LANG.get("ui_check_report_time", "Time: {time}").format(time=timestamp),
            LANG.get("ui_check_report_tests", "Tests: {count}").format(
                count=Q(results)
            ),
            LANG.get("ui_check_report_failures", "Failures: {count}").format(
                count=failures
            ),
            B,
            LANG.get("ui_check_report_results_header", "Test results:"),
        ]
        status_ok = LANG.get("ui_check_status_ok", "OK")
        status_fail = LANG.get("ui_check_status_fail", "FAIL")
        for result in results:
            status = status_ok if result.get("ok") else status_fail
            detail = result.get("detail", B)
            if detail:
                detail = f" - {detail}"
            lines.append(
                LANG.get(
                    "ui_check_report_result_item",
                    "{status} {name}{detail}",
                ).format(
                    status=status,
                    name=result.get("name", B),
                    detail=detail,
                )
            )
        lines.append(B)
        if missing_buttons:
            lines.append(
                LANG.get(
                    "ui_check_report_buttons_header",
                    "Buttons without command:",
                )
            )
            for item in missing_buttons:
                lines.append(
                    LANG.get(
                        "ui_check_report_buttons_item",
                        "- {path} ({text}) state={state}",
                    ).format(
                        path=item.get("path", B),
                        text=item.get("text", B),
                        state=item.get("state", B),
                    )
                )
        else:
            lines.append(
                LANG.get(
                    "ui_check_report_buttons_ok",
                    "All buttons have assigned actions.",
                )
            )
        return "\n".join(lines)

    def _run_ui_diagnostics(
        A, status_var=I, button=I, report_widget=I, root_widget=I
    ):
        if Aj(A, "_ui_check_running", h):
            return
        A._ui_check_running = J
        if status_var:
            status_var.set(
                LANG.get("ui_check_running", "UI tests running...")
            )
        if button:
            try:
                button.configure(state=V)
            except E:
                pass
        if report_widget:
            try:
                report_widget.configure(state=Az)
                report_widget.delete(A_, F.END)
                report_widget.configure(state=Ak)
            except E:
                pass
        parent = root_widget or A
        test_parent = C.Frame(parent)
        results = []
        missing_buttons = []

        def _record(name, ok, detail=B):
            results.append({"name": name, "ok": ok, "detail": detail})

        try:
            ok, detail = A._ui_test_after()
            _record(
                LANG.get("ui_check_test_after", "after() callback"),
                ok,
                detail,
            )
            ok, detail = A._ui_test_button_invoke(test_parent)
            _record(
                LANG.get("ui_check_test_button_invoke", "Button invoke"),
                ok,
                detail,
            )
            ok, detail = A._ui_test_event_binding(test_parent)
            _record(
                LANG.get("ui_check_test_event", "Click event binding"),
                ok,
                detail,
            )
            ok, detail = A._ui_test_toplevel()
            _record(
                LANG.get("ui_check_test_toplevel", "Window open/close"),
                ok,
                detail,
            )
            ok, detail = A._ui_test_modal()
            _record(
                LANG.get("ui_check_test_modal", "Modal window"),
                ok,
                detail,
            )
            ok, detail = A._ui_test_scrolledtext(test_parent)
            _record(
                LANG.get(
                    "ui_check_test_scrolledtext", "ScrolledText widget"
                ),
                ok,
                detail,
            )
            ok, detail = A._ui_test_combobox(test_parent)
            _record(
                LANG.get("ui_check_test_combobox", "Combobox widget"),
                ok,
                detail,
            )
            ok, detail = A._ui_test_open_list_editor()
            _record(
                LANG.get(
                    "ui_check_test_open_list_editor", "Open list editor"
                ),
                ok,
                detail,
            )
            ok, detail = A._ui_test_open_settings()
            _record(
                LANG.get("ui_check_test_open_settings", "Open settings"),
                ok,
                detail,
            )
            for result in A._ui_test_safe_button_clicks():
                results.append(result)
        except E as exc:
            _record(
                LANG.get("ui_check_test_unhandled", "Unhandled error"),
                h,
                G(exc),
            )
        try:
            missing_buttons = A._scan_button_commands(A)
        except E:
            missing_buttons = []
        try:
            test_parent.destroy()
        except E:
            pass

        report_text = A._format_ui_check_report(results, missing_buttons)
        A._ui_check_last_report = report_text
        if report_widget:
            try:
                report_widget.configure(state=Az)
                report_widget.delete(A_, F.END)
                if report_text:
                    report_widget.insert(F.END, report_text)
                report_widget.configure(state=Ak)
            except E:
                pass

        failures = Q([r for r in results if not r.get("ok")])
        button_issues = Q(missing_buttons)
        issues = failures + button_issues
        if issues == 0:
            msg = LANG.get(
                "ui_check_ok",
                "UI tests completed. No issues found.",
            )
            if status_var:
                status_var.set(msg)
            log_info_loc("ui_check_ok")
        else:
            msg = LANG.get(
                "ui_check_issue_summary",
                "UI tests found {issues} issues (failures: {failures}, buttons: {buttons}).",
            ).format(
                issues=issues,
                failures=failures,
                buttons=button_issues,
            )
            if status_var:
                status_var.set(msg)
            log_error_loc(
                "ui_check_issue_summary",
                issues=issues,
                failures=failures,
                buttons=button_issues,
            )
        A._ui_check_running = h
        if button:
            try:
                button.configure(state=X)
            except E:
                pass

    def _build_form(A):
        """Create comboboxes and entry widgets for the product data form."""

        F_ = "<FocusOut>"
        D_ = "<KeyRelease>"
        E_ = "<Return>"
        B_ = C.Frame(A, style="Card.TFrame", padding=10)
        B_.pack(side="top", fill="x", padx=12, pady=(12, 6))
        G_ = C.Label(B_, text=NAME_LABEL, style="Form.TLabel")
        G_.grid(row=0, column=0, sticky=R)
        A._add_tooltip(
            G_,
            LANG.get(
                "name_tooltip",
                "Pełna nazwa mebla bez kolorów, typu i modelu, np: 'Maggiore', 'LUNA', 'SLANT'.",
            ),
        )
        A.combo_name = C.Combobox(
            B_, textvariable=A.var_name, values=A.lists[n], state=X
        )
        A.combo_name.grid(row=0, column=1, padx=5, pady=2)
        A.combo_name.bind(E_, lambda e: A._on_name_commit())
        A.combo_name.bind(A2, lambda e: A._on_name_commit())
        A.combo_name.bind(F_, lambda e: A._on_name_commit())
        A.combo_name.bind(D_, A._on_key_release)
        A.combo_name.bind("<FocusIn>", A._remember_focus)
        H_ = C.Label(B_, text=TYPE_LABEL, style="Form.TLabel")
        H_.grid(row=1, column=0, sticky=R)
        A._add_tooltip(
            H_,
            LANG.get(
                "type_tooltip",
                "Typ mebla, np: 'KOMODA', 'RTV', 'STÓŁ' (można dodać długość, np. 'RTV 100', 'SZAFA 80').",
            ),
        )
        A.combo_type = C.Combobox(
            B_, textvariable=A.var_type, values=A.lists[t], state=V
        )
        A.combo_type.grid(row=1, column=1, padx=5, pady=2)
        A.combo_type.bind(E_, lambda e: A._on_type_commit())
        A.combo_type.bind(A2, lambda e: A._on_type_commit())
        A.combo_type.bind(F_, lambda e: A._on_type_commit())
        A.combo_type.bind(D_, A._on_key_release)
        A.combo_type.bind("<FocusIn>", A._remember_focus)
        I_ = C.Label(B_, text=MODEL_LABEL, style="Form.TLabel")
        I_.grid(row=2, column=0, sticky=R)
        A._add_tooltip(
            I_,
            LANG.get(
                "model_tooltip",
                "Model lub wersja mebla, np: 'MA03', 'Li01', 'SOL-05'.",
            ),
        )
        A.combo_model = C.Combobox(
            B_, textvariable=A.var_model, values=A.lists[s], state=V
        )
        A.combo_model.grid(row=2, column=1, padx=5, pady=2)
        A.combo_model.bind(E_, lambda e: A._on_model_commit())
        A.combo_model.bind(A2, lambda e: A._on_model_commit())
        A.combo_model.bind(D_, A._on_key_release)
        A.combo_model.bind("<FocusIn>", A._remember_focus)
        J_ = C.Label(B_, text=COLOR1_LABEL, style="Form.TLabel")
        J_.grid(row=3, column=0, sticky=R)
        A._add_tooltip(
            J_, LANG.get("color1_tooltip", "Główny kolor mebla (wymagany).")
        )
        A.combo_color1 = C.Combobox(
            B_, textvariable=A.var_color1, values=A.lists[Y], state=V
        )
        A.combo_color1.grid(row=3, column=1, padx=5, pady=2)
        A.combo_color1.bind(E_, lambda e: A._on_color_commit())
        A.combo_color1.bind(A2, lambda e: A._on_color_commit())
        A.combo_color1.bind(F_, lambda e: A._on_color_commit())
        A.combo_color1.bind(D_, A._on_key_release)
        A.combo_color1.bind("<FocusIn>", A._remember_focus)
        K_ = C.Label(B_, text=COLOR2_LABEL, style="Form.TLabel")
        K_.grid(row=4, column=0, sticky=R)
        A._add_tooltip(
            K_, LANG.get("color2_tooltip", "Drugi kolor mebla (opcjonalnie).")
        )
        A.combo_color2 = C.Combobox(
            B_, textvariable=A.var_color2, values=A.lists[Y], state=V
        )
        A.combo_color2.grid(row=4, column=1, padx=5, pady=2)
        A.combo_color2.bind(E_, lambda e: A._on_color_commit())
        A.combo_color2.bind(A2, lambda e: A._on_color_commit())
        A.combo_color2.bind(F_, lambda e: A._on_color_commit())
        A.combo_color2.bind(D_, A._on_key_release)
        A.combo_color2.bind("<FocusIn>", A._remember_focus)
        L_ = C.Label(B_, text=COLOR3_LABEL, style="Form.TLabel")
        L_.grid(row=5, column=0, sticky=R)
        A._add_tooltip(
            L_, LANG.get("color3_tooltip", "Trzeci kolor mebla (opcjonalnie).")
        )
        A.combo_color3 = C.Combobox(
            B_, textvariable=A.var_color3, values=A.lists[Y], state=V
        )
        A.combo_color3.grid(row=5, column=1, padx=5, pady=2)
        A.combo_color3.bind(E_, lambda e: A._on_color_commit())
        A.combo_color3.bind(A2, lambda e: A._on_color_commit())
        A.combo_color3.bind(F_, lambda e: A._on_color_commit())
        A.combo_color3.bind(D_, A._on_key_release)
        A.combo_color3.bind("<FocusIn>", A._remember_focus)
        M_ = C.Label(B_, text=EXTRA_LABEL, style="Form.TLabel")
        M_.grid(row=6, column=0, sticky=R)
        A._add_tooltip(
            M_,
            LANG.get(
                "extra_tooltip",
                "Dodatkowe informacje, np. LED, RGB (pozostaw puste, jeśli brak dodatków).",
            ),
        )
        A.combo_extra = C.Combobox(
            B_, textvariable=A.var_extra, values=A.lists[d], state=V
        )
        A.combo_extra.grid(row=6, column=1, padx=5, pady=2)
        A.combo_extra.bind(E_, lambda e: A._on_extra_commit())
        A.combo_extra.bind(A2, lambda e: A._on_extra_commit())
        A.combo_extra.bind(F_, lambda e: A._on_extra_commit())
        A.combo_extra.bind(D_, A._on_key_release)
        A.combo_extra.bind("<FocusIn>", A._remember_focus)
        N_ = C.Label(B_, text=EAN_OPTIONAL_LABEL, style="Form.TLabel")
        N_.grid(row=7, column=0, sticky=R)
        A._add_tooltip(
            N_,
            LANG.get(
                "ean_tooltip",
                "13-cyfrowy kod EAN produktu. Jeśli nie podany, zostanie użyte 'BRAK-EAN'.",
            ),
        )
        A.entry_ean = C.Entry(B_, textvariable=A.var_ean, state=X)
        A.entry_ean.grid(row=7, column=1, padx=5, pady=2)
        A.entry_ean.bind("<FocusIn>", A._remember_focus)
        O_ = C.Button(B_, text=LOAD_LABEL, command=A._load_by_ean)
        O_.grid(row=7, column=2, padx=5, pady=2)
        A.btn_edit_lists = C.Button(B_, text=EDIT_LISTS_LABEL, command=A._open_list_editor)
        A.btn_edit_lists.grid(row=0, column=2, padx=20)
        A.btn_settings = C.Button(B_, text=SETTINGS_LABEL, command=A._open_settings)
        A.btn_settings.grid(row=0, column=3, padx=5)
        A.btn_submit = C.Button(B_, text=UPDATE_LABEL, command=A._on_submit)
        A.btn_submit.grid(row=8, column=0, columnspan=2, pady=10)
        A.btn_open = C.Button(B_, text=OPEN_FOLDER_LABEL, command=A._open_current_folder)
        A.btn_open.grid(row=8, column=2, padx=5, pady=10)
        A.ui_log = BS.ScrolledText(B_, width=48, height=8, state=Ak, wrap="word")
        A.ui_log.grid(row=0, column=4, rowspan=9, padx=10, sticky="nsew")
        A.btn_clear_log = C.Button(
            B_, text=CLEAR_LOG_LABEL, command=lambda: A._ui_log(clear=Al)
        )
        A.btn_clear_log.grid(row=8, column=3, padx=5, pady=10, sticky="e")
        B_.grid_columnconfigure(4, weight=1)

    def _build_slots(B):
        """Prepare the scrollable grid of drop targets used for images."""

        Q_ = "<Button-1>"
        R_ = B._ui_colors["slot_bg"]
        T_ = B._ui_colors["slot_border"]
        S_ = "<Configure>"
        L_ = "units"
        try:
            B.unbind_all("<MouseWheel>")
            B.unbind_all("<Button-4>")
            B.unbind_all("<Button-5>")
        except E:
            pass
        M_ = C.Frame(B, style="App.TFrame")
        M_.pack(fill=z, expand=J, padx=12, pady=(6, 12))
        B._slots_container = M_
        A_ = F.Canvas(M_, bg=B._ui_colors["bg"], highlightthickness=0, bd=0)
        def _on_scroll(*args):
            A_.yview(*args)
            B._note_slots_scroll()

        T = C.Scrollbar(M_, orient=An, command=_on_scroll)
        N_ = C.Frame(A_, style="App.TFrame")
        N_.bind(S_, lambda e: A_.configure(scrollregion=A_.bbox("all")))
        Y = A_.create_window((0, 0), window=N_, anchor="nw")
        A_.bind(S_, lambda e, cw=Y: A_.itemconfig(cw, width=e.width))
        A_.configure(yscrollcommand=T.set)
        A_.pack(side=Am, fill=z, expand=J)
        T.pack(side=AV, fill="y")
        def _on_mousewheel(e):
            A_.yview_scroll(int(-1 * (e.delta / 120)), L_)
            B._note_slots_scroll()

        def _on_button4(e):
            A_.yview_scroll(-1, L_)
            B._note_slots_scroll()

        def _on_button5(e):
            A_.yview_scroll(1, L_)
            B._note_slots_scroll()

        A_.bind_all("<MouseWheel>", _on_mousewheel)
        A_.bind_all("<Button-4>", _on_button4)
        A_.bind_all("<Button-5>", _on_button5)
        B.slots_frame = N_
        B.slots = []
        U = 5
        for G_, slot_def in A0(B.slot_definitions):
            V_ = slot_def["prefix"]
            W_ = slot_def["label"]
            Z_, O_ = divmod(G_, U)
            H_ = F.Frame(
                B.slots_frame,
                highlightthickness=0,
                highlightbackground=A8,
                highlightcolor=A8,
                bg=B._ui_colors["card"],
                bd=0,
            )
            H_.grid(row=Z_, column=O_, padx=6, pady=6, sticky="nsew")
            slot_title = SLOT_TITLE_FORMAT.format(
                index=V_, label=get_slot_label(W_)
            )
            title_label = C.Label(
                H_,
                text=slot_title,
                style="SlotTitle.TLabel",
                anchor="w",
            )
            title_label.pack(fill="x", padx=6, pady=(6, 0))
            E_ = F.Frame(
                H_,
                height=110,
                bg=R_,
                highlightthickness=1,
                highlightbackground=T_,
                bd=0,
            )
            E_.pack_propagate(h)
            E_.pack(fill=z, expand=J, padx=6, pady=6)
            D_ = F.Label(E_, text=NO_FILE_LABEL, bg=R_, fg=B._ui_colors["muted"])
            D_.pack(fill=z, expand=J)
            if hasattr(D_, "drop_target_register") and hasattr(D_, "dnd_bind"):
                D_.drop_target_register(DND_ALL)
                D_.dnd_bind("<<Drop>>", lambda e, i=G_: B._on_drop(e, i))
            K_ = F.Label(E_, text="✕", fg=AT, bg=Ab)
            K_.bind(Q_, lambda e, i=G_: B._remove_file(i))
            K_.place(relx=0, rely=0, anchor="nw")
            K_.place_forget()
            X_ = F.Label(E_, text="...", fg=AT, bg="black")
            X_.bind(Q_, lambda e, i=G_: B._select_file(i))
            X_.place(relx=1.0, rely=0, anchor="ne")
            local_icon = F.Canvas(
                E_,
                width=30,
                height=20,
                highlightthickness=0,
                bd=1,
                relief="solid",
            )
            local_icon.create_text(
                15,
                10,
                text=LOCAL_ICON_LABEL,
                font=("Segoe UI", 7),
                fill="white",
            )
            local_icon.offset_x = -60
            local_icon.place(relx=1.0, rely=1.0, anchor="se", x=local_icon.offset_x)
            local_icon.place_forget()
            ftp_icon = F.Canvas(
                E_,
                width=30,
                height=20,
                highlightthickness=0,
                bd=1,
                relief="solid",
            )
            ftp_icon.create_text(
                15,
                10,
                text=FTP_ICON_LABEL,
                font=("Segoe UI", 7),
                fill="white",
            )
            ftp_icon.offset_x = -30
            ftp_icon.place(relx=1.0, rely=1.0, anchor="se", x=ftp_icon.offset_x)
            ftp_icon.place_forget()
            sql_icon = F.Canvas(
                E_,
                width=30,
                height=20,
                highlightthickness=0,
                bd=1,
                relief="solid",
            )
            sql_icon.create_text(
                15,
                10,
                text=SQL_ICON_LABEL,
                font=("Segoe UI", 7),
                fill="white",
            )
            sql_icon.offset_x = 0
            sql_icon.place(relx=1.0, rely=1.0, anchor="se", x=sql_icon.offset_x)
            sql_icon.place_forget()
            sql_icon.show_when_unknown = J
            if hasattr(D_, "drag_source_register") and hasattr(D_, "dnd_bind"):
                D_.drag_source_register(1, BJ)
                D_.dnd_bind("<<DragInitCmd>>", lambda e, i=G_: B._on_drag_init(e, i))
                D_.dnd_bind("<<DragEndCmd>>", lambda e: B._on_drag_end(e))
            footer = C.Frame(H_, style="SlotFooter.TFrame")
            footer.pack(fill="x", padx=6, pady=(0, 6))
            status_label = C.Label(
                footer,
                text=B._slot_status["empty"],
                style="SlotStatus.TLabel",
                anchor="w",
            )
            status_label.pack(fill="x")
            progress = C.Progressbar(
                footer,
                mode="determinate",
                maximum=100,
                value=0,
                style="Slot.TProgressbar",
            )
            progress.pack(fill="x", pady=(2, 0))
            B.slots.append(
                {
                    Aa: V_,
                    "label": W_,
                    "title_label": title_label,
                    y: D_,
                    A7: K_,
                    "local_icon": local_icon,
                    "ftp_icon": ftp_icon,
                    "sql_icon": sql_icon,
                    "status_label": status_label,
                    "progress": progress,
                    f: I,
                    AS: H_,
                    B0: I,
                }
            )
        for O_ in Ax(U):
            B.slots_frame.columnconfigure(O_, weight=1)

    def _note_slots_scroll(B):
        B._scrolling = J
        if B._scroll_idle_job is not I:
            try:
                B.after_cancel(B._scroll_idle_job)
            except E:
                pass
        B._scroll_idle_job = B.after(150, B._clear_slots_scroll)

    def _clear_slots_scroll(B):
        B._scrolling = h
        B._scroll_idle_job = I

    def _load_slot_config(B, log_issues=J):
        slot_defs, slot_issues = normalize_slot_definitions(
            config.CONFIG.get(SLOT_DEFS_KEY)
        )
        sql_map, map_issues = normalize_sql_column_map(
            config.CONFIG.get(SQL_COLUMN_MAP_KEY), slot_defs
        )
        changed = h
        if slot_defs != config.CONFIG.get(SLOT_DEFS_KEY):
            config.CONFIG[SLOT_DEFS_KEY] = slot_defs
            changed = J
        if sql_map != config.CONFIG.get(SQL_COLUMN_MAP_KEY):
            config.CONFIG[SQL_COLUMN_MAP_KEY] = sql_map
            changed = J
        if log_issues:
            for issue in slot_issues + map_issues:
                B._log_slot_issue(issue)
        if changed:
            save_config(
                config.CONFIG,
                preserve_secrets={
                    H: {N, M},
                    P: {N, M},
                    K: {N, M},
                    TRANSLATION_SETTINGS_KEY: {TRANSLATION_API_KEY},
                },
            )
        B.slot_definitions = slot_defs
        B.sql_column_map = sql_map

    def _log_slot_issue(A, issue):
        issue_type = issue.get("type")
        if issue_type == "slot_def_duplicate":
            log_error_loc(
                "slot_def_duplicate_prefix", prefix=issue.get("prefix", B)
            )
        elif issue_type == "slot_def_invalid":
            log_error_loc(
                "slot_def_invalid_entry", entry=issue.get("entry", B)
            )
        elif issue_type == "slot_def_fallback":
            log_error_loc("slot_def_fallback")
        elif issue_type == "sql_map_extra":
            log_error_loc(
                "sql_map_extra_entry", prefix=issue.get("prefix", B)
            )

    def _resolve_sql_column(B, prefix, label, log_missing=Ay):
        mapping = B.sql_column_map if isinstance(B.sql_column_map, dict) else {}
        if prefix in mapping:
            column = G(mapping.get(prefix) or B).strip()
            if not column:
                if log_missing:
                    log_error_loc(
                        "sql_column_unassigned", prefix=prefix, label=label
                    )
                return I
            return column
        if label:
            return label
        if log_missing:
            log_error_loc("sql_column_unassigned", prefix=prefix, label=label)
        return I

    def _apply_slot_definitions(B, slot_defs):
        B.pending_additions = {}
        B.pending_deletions = {}
        B.pending_ftp_deletions = {}
        B.ftp_remote_only = {}
        B.ftp_presence = {}
        B.ftp_downloaded_final = set()
        B.sql_presence = I
        B.original_files = {}
        B.dragging_idx = I
        B.loading_by_ean = h
        B.suppress_scan = h
        try:
            if getattr(B, "_slots_container", I):
                B._slots_container.destroy()
        except E:
            pass
        B._slots_container = I
        B.slot_definitions = slot_defs
        B._build_slots()
        B._slot_index_by_prefix = {
            slot["prefix"]: idx for idx, slot in A0(B.slot_definitions)
        }

    def _update_slot_titles(B, slot_defs):
        label_map = {slot["prefix"]: slot["label"] for slot in slot_defs}
        for slot in B.slots:
            prefix = slot.get(Aa)
            new_label = label_map.get(prefix)
            if not new_label:
                continue
            slot["label"] = new_label
            title_label = slot.get("title_label")
            if title_label:
                title_label.configure(
                    text=SLOT_TITLE_FORMAT.format(
                        index=prefix, label=get_slot_label(new_label)
                    )
                )

    def _queue_thumbnail(B, idx, path):
        if not path:
            return
        token = uuid.uuid4().hex
        B._thumb_tokens[idx] = token
        B._thumb_queue.put((idx, path, token))

    def _thumbnail_worker(B):
        while J:
            idx, path, token = B._thumb_queue.get()
            if token != B._thumb_tokens.get(idx):
                continue
            thumb = I
            try:
                with AA.open(path) as img:
                    img.thumbnail((100, 100), LANCZOS_FILTER)
                    thumb = img.copy()
            except E:
                thumb = I
            B.after(
                0,
                lambda i=idx, p=path, t=token, th=thumb: B._apply_thumbnail(
                    i, p, t, th
                ),
            )

    def _apply_thumbnail(B, idx, path, token, thumb):
        if token != B._thumb_tokens.get(idx):
            return
        if idx < 0 or idx >= Q(B.slots):
            return
        slot = B.slots[idx]
        if slot.get(f) != path:
            return
        if B._scrolling:
            B.after(
                80,
                lambda i=idx, p=path, t=token, th=thumb: B._apply_thumbnail(
                    i, p, t, th
                ),
            )
            return
        label = slot[y]
        remove_label = slot[A7]
        if thumb is I:
            label.configure(text=A.path.basename(path), image="")
            label.image = I
        else:
            photo = ImageTk.PhotoImage(thumb)
            label.configure(image=photo, text="")
            label.image = photo
        remove_label.place(x=0, y=0)
        B._update_slot_activity(idx, active=h)

    def _set_icon_status(C, icon, present):
        """Toggle the coloured indicator showing local/remote file presence."""

        if not icon:
            return
        if present is I:
            if getattr(icon, "show_when_unknown", h):
                icon.place(
                    relx=1.0,
                    rely=1.0,
                    anchor="se",
                    x=getattr(icon, "offset_x", 0),
                )
                icon.config(bg="#555555")
            else:
                icon.place_forget()
            return
        icon.place(relx=1.0, rely=1.0, anchor="se", x=getattr(icon, "offset_x", 0))
        icon.config(bg="green" if present else "red")

    def _get_slot_idle_status(B, idx):
        slot = B.slots[idx]
        if slot.get(f):
            return B._slot_status["ready"]
        return B._slot_status["empty"]

    def _update_slot_activity(B, idx, active=h, status=I):
        def _apply(status_text=status, active_state=active):
            if idx is I or idx < 0 or idx >= Q(B.slots):
                return
            slot = B.slots[idx]
            if status_text is I:
                status_text = B._get_slot_idle_status(idx)
            label = slot.get("status_label")
            progress = slot.get("progress")
            if label:
                label.configure(text=status_text)
            if progress:
                if active_state:
                    progress.configure(mode="indeterminate")
                    progress.start(12)
                else:
                    progress.stop()
                    progress.configure(mode="determinate", value=0)

        try:
            B.after(0, _apply)
        except E:
            _apply()

    def _update_all_slot_activity(B, active=h, status=I):
        for idx in Ax(Q(B.slots)):
            B._update_slot_activity(idx, active=active, status=status)

    def _should_check_sql_presence(A):
        """Return True when database credentials are configured for lookups."""

        db_type = config.CONFIG.get(p, K).lower()
        if db_type == K:
            mysql_cfg = config.CONFIG.get(K, {})
            return all(mysql_cfg.get(key) for key in (c, b, N))
        sql_cfg = config.CONFIG.get(P, {})
        if not (sql_cfg.get(c) and sql_cfg.get(b)):
            return h
        user = sql_cfg.get(N)
        password = sql_cfg.get(M)
        if user or password:
            return bool(user and password)
        return J

    def _extract_sql_presence_context(A, ean):
        """Return the table name and WHERE clause used for SQL presence checks."""

        if not ean:
            return I
        template = config.CONFIG.get(w, SQL_UPDATE_TEMPLATE) or SQL_UPDATE_TEMPLATE
        update_match = re.search(r"(?is)update\s+([^\s]+)\s+set", template)
        if not update_match:
            log_error_loc("sql_presence_table_parse_failed")
            return I
        table = update_match.group(1).strip().rstrip(";")
        where_match = re.search(r"(?is)\bwhere\b(.+)", template)
        if where_match:
            where_template = " WHERE" + where_match.group(1)
        else:
            where_template = " WHERE EAN = '{ean}' OR Towar_powiazany_z_SKU = '{ean}'"
        where_clause = where_template.replace("{ean}", ean)
        where_clause = where_clause.replace("{EAN}", ean)
        where_clause = where_clause.rstrip(";\n\r\t ")
        if where_clause and not where_clause.startswith(" "):
            where_clause = " " + where_clause
        return table, where_clause

    def _build_sql_presence_query(A, table, where_clause, column, db_type):
        """Compose a per-column SELECT used to check for SQL data availability."""

        if not (table and column):
            return I
        if db_type == K:
            base_query = f"SELECT {column} FROM {table}{where_clause}"
            if " limit " not in base_query.lower():
                base_query = f"{base_query.rstrip('; ')} LIMIT 1"
            return base_query
        return f"SELECT TOP 1 {column} FROM {table}{where_clause}".rstrip(";\n\r\t ")

    def _refresh_combobox_list(B, combobox, all_values, existing_count=0):
        """Refresh the dropdown values while remembering which entries exist."""

        A_ = combobox
        A_[S] = all_values
        A_.existing_count = existing_count

    def _normalize_list_value(A, list_key, value):
        """Return a normalized list entry for comparisons and saves."""

        if value is I:
            return B
        cleaned = G(value).strip()
        if not cleaned:
            return B
        if list_key == d:
            cleaned = cleaned.replace(a, g)
        return cleaned.upper()

    def _list_has_value(A, list_key, value):
        normalized = A._normalize_list_value(list_key, value)
        if not normalized:
            return h
        values = A.lists.get(list_key, [])
        return normalized in [G(A_).strip().upper() for A_ in values if A_]

    def _sync_list_comboboxes(A, list_key):
        values = A.lists.get(list_key, [])
        if list_key == n and Aj(A, "combo_name", I):
            A.combo_name[S] = values
        elif list_key == t and Aj(A, "combo_type", I):
            A.combo_type[S] = values
        elif list_key == s and Aj(A, "combo_model", I):
            A.combo_model[S] = values
        elif list_key == Y:
            if Aj(A, "combo_color1", I):
                A.combo_color1[S] = values
            if Aj(A, "combo_color2", I):
                A.combo_color2[S] = values
            if Aj(A, "combo_color3", I):
                A.combo_color3[S] = values
        elif list_key == d and Aj(A, "combo_extra", I):
            A.combo_extra[S] = values

    def _remember_focus(A, event):
        A._last_focus_widget = Aj(event, "widget", I)

    def _focus_widget(A, widget):
        try:
            if widget and widget.winfo_exists():
                widget.focus_set()
                return
        except E:
            pass
        try:
            A.focus_force()
        except E:
            pass

    def _restore_focus(A):
        A._focus_widget(A._last_focus_widget)

    def _prompt_add_list_value(A, list_key, value, prompt_msg, widget=I):
        normalized = A._normalize_list_value(list_key, value)
        if not normalized:
            return h
        if A._list_has_value(list_key, normalized):
            return J
        if list_key in A._active_list_prompts:
            return I
        A._active_list_prompts.add(list_key)
        try:
            if O.askyesno(AJ, prompt_msg):
                return A._add_list_value(list_key, normalized)
            return h
        finally:
            A._active_list_prompts.discard(list_key)
            if widget is not I:
                A._focus_widget(widget)

    def _add_list_value(A, list_key, value, listbox=I, show_exists=h):
        normalized = A._normalize_list_value(list_key, value)
        if not normalized:
            O.showwarning(WARNING_LABEL, LIST_VALUE_EMPTY_MSG)
            return h
        if A._list_has_value(list_key, normalized):
            if show_exists:
                list_label = LIST_EDITOR_TAB_LABELS.get(list_key, list_key)
                O.showinfo(
                    WARNING_LABEL,
                    LIST_VALUE_EXISTS_MSG.format(value=normalized, list=list_label),
                )
            return J
        if not add_to_list(EXCEL_SHEETS[list_key], normalized):
            return h
        if not isinstance(A.lists.get(list_key), list):
            A.lists[list_key] = []
        A.lists[list_key].append(normalized)
        if listbox is not I:
            try:
                existing = listbox.get(0, F.END)
            except E:
                existing = ()
            if normalized not in existing:
                listbox.insert(F.END, normalized)
        A._sync_list_comboboxes(list_key)
        return J

    def _on_name_commit(C):
        """Handle the user confirming or typing a furniture name."""

        D_ = C.var_name.get().strip()
        if not D_:
            return
        if not C._list_has_value(n, D_):
            result = C._prompt_add_list_value(
                n, D_, NAME_NOT_IN_LIST_QUESTION.format(value=D_), C.combo_name
            )
            if result is None:
                return
            if result:
                D_ = C._normalize_list_value(n, D_)
                if D_:
                    C.var_name.set(D_)
            else:
                C.var_name.set(B)
                return
        F = A.path.join(l, D_.upper())
        E_ = []
        if A.path.isdir(F):
            E_ = [B for B in A.listdir(F) if A.path.isdir(A.path.join(F, B))]
            C.combo_name.configure(style=Z)
        else:
            C.combo_name.configure(style=j)
        I = [A for A in C.lists[t] if A not in E_]
        C._refresh_combobox_list(C.combo_type, E_ + I, existing_count=Q(E_))
        C.combo_type.configure(state=X)
        C.var_type.set(B)
        C.var_model.set(B)
        C.var_color1.set(B)
        C.var_color2.set(B)
        C.var_color3.set(B)
        C.var_extra.set(B)
        C.var_ean.set(B)
        for G_ in (
            C.combo_type,
            C.combo_model,
            C.combo_color1,
            C.combo_color2,
            C.combo_color3,
            C.combo_extra,
        ):
            G_.configure(style=j)
        for G_ in (
            C.combo_model,
            C.combo_color1,
            C.combo_color2,
            C.combo_color3,
            C.combo_extra,
        ):
            G_.configure(state=V)
        C.btn_submit.configure(state=V)
        C.btn_open.configure(state=V)
        C.entry_ean.configure(state=X)
        C._clear_all_slots()

    def _on_type_commit(C):
        """React to type changes by unlocking model/colour comboboxes."""

        G_ = C.var_name.get().strip()
        D_ = C.var_type.get().strip()
        if not G_ or not D_:
            return
        if not C._list_has_value(t, D_):
            result = C._prompt_add_list_value(
                t, D_, TYPE_NOT_IN_LIST_QUESTION.format(value=D_), C.combo_type
            )
            if result is None:
                return
            if result:
                D_ = C._normalize_list_value(t, D_)
                if D_:
                    C.var_type.set(D_)
            else:
                C.var_type.set(B)
                return
        F = A.path.join(l, G_.upper(), D_.upper())
        E_ = []
        if A.path.isdir(F):
            E_ = [B for B in A.listdir(F) if A.path.isdir(A.path.join(F, B))]
            C.combo_type.configure(style=Z)
        else:
            C.combo_type.configure(style=j)
        I = [A for A in C.lists[s] if A not in E_]
        C._refresh_combobox_list(C.combo_model, E_ + I, existing_count=Q(E_))
        C.combo_model.configure(state=X)
        C.var_model.set(B)
        C.var_color1.set(B)
        C.var_color2.set(B)
        C.var_color3.set(B)
        C.var_extra.set(B)
        C.var_ean.set(B)
        for J_ in (C.combo_color1, C.combo_color2, C.combo_color3, C.combo_extra):
            J_.configure(style=j, state=V)
        C.btn_submit.configure(state=V)
        C.btn_open.configure(state=V)
        C.entry_ean.configure(state=X)
        C._clear_all_slots()

    def _load_existing_files(C):
        """Load images from disk and check FTP copies without blocking GUI."""
        if C.suppress_next_lookup:
            C.suppress_next_lookup = h
            return
        C.logged_counts = h
        F = A.path.join(
            l,
            C.var_name.get().strip().upper(),
            C.var_type.get().strip().upper(),
            C.var_model.get().strip().upper(),
        )
        Y_ = C.var_color1.get().strip().upper()
        Z_ = C.var_color2.get().strip().upper()
        b_ = C.var_color3.get().strip().upper()
        if Y_:
            S_ = [Y_]
            if Z_:
                S_.append(Z_)
            if b_:
                S_.append(b_)
            h_ = g.join(S_)
            F = A.path.join(F, h_)
        I_raw = C.var_extra.get()
        if isinstance(I_raw, dict):
            I_raw = B
        I_ = G(I_raw).strip()
        I_ = I_.replace(a, g)
        if I_ == B:
            I_ = L
        else:
            I_ = I_.upper()
        F = A.path.join(F, I_)
        if I_.upper() == L and not A.path.isdir(F):
            c_ = A.path.join(A.path.dirname(F), L)
            if A.path.isdir(c_):
                try:
                    A.rename(c_, F)
                except E as T:
                    log_error_loc("rename_no_led_failed", error=T)
        C._clear_all_slots()
        C.original_files = {}
        if not A.path.isdir(F):
            return
        C._update_all_slot_activity(active=J, status=C._slot_status["loading"])
        def worker():
            try:
                V_ = [
                    B for B in A.listdir(F) if A.path.isfile(A.path.join(F, B))
                ]
            except E:
                V_ = []
            original_files = {}
            slot_paths = {}
            remote_info = {}
            ean_guess = I
            if V_:
                i_ = V_[0]
                P_ = i_.split(a)
                if P_ and C.var_ean.get().strip() == B:
                    ean_guess = P_[0]
            for W_ in V_:
                d_ = A.path.join(F, W_)
                if not A.path.isfile(d_):
                    continue
                P_ = W_.split(a)
                if Q(P_) < 2:
                    continue
                label_part = P_[1]
                label = label_part.split(".")[0]
                norm_label = label.zfill(2)
                ext = A.path.splitext(label_part)[1]
                if label != norm_label:
                    normalized_name = f"{P_[0]}_{norm_label}{ext}"
                    normalized_path = A.path.join(F, normalized_name)
                    try:
                        A.rename(d_, normalized_path)
                        log_info_loc(
                            "file_renamed", old=W_, new=normalized_name
                        )
                        W_ = normalized_name
                        d_ = normalized_path
                    except E as T:
                        log_error_loc(
                            "file_rename_error", old=W_, new=normalized_name, error=T
                        )
                original_files[norm_label] = W_
                slot_paths[norm_label] = d_
            ftp_presence = {}
            sql_presence = I
            K_ = C.var_ean.get().strip()
            if K_ and Q(K_) == 13 and K_.isdigit() and K_.upper() != q:
                remote_files = {}
                try:
                    O_ = AB.FTP()
                    O_.connect(D[H][v], D[H][r], timeout=10)
                    O_.login(D[H][N], D[H][M])
                    O_.set_pasv(J)
                    if D[H][m]:
                        O_.cwd(D[H][m])
                    try:
                        e_ = O_.nlst()
                    except AB.error_perm:
                        e_ = []
                    j_ = {A.path.basename(B) for B in e_}
                    for name in j_:
                        if name.startswith(f"{K_}_"):
                            rest = name[len(f"{K_}_") :]
                            label_raw = rest.split(".")[0]
                            norm_label = label_raw.zfill(2)
                            remote_files[norm_label] = name
                    for label, fname in remote_files.items():
                        if label not in slot_paths:
                            temp_dir = tempfile.gettempdir()
                            temp_path_raw = A.path.join(temp_dir, fname)
                            try:
                                idx = C._slot_index_by_prefix.get(label)
                                if idx is not I:
                                    C._update_slot_activity(
                                        idx,
                                        active=J,
                                        status=C._slot_status["downloading"],
                                    )
                                with x(temp_path_raw, "wb") as fh:
                                    O_.retrbinary(f"RETR {fname}", fh.write)
                                ext = A.path.splitext(fname)[1]
                                normalized_fname = f"{K_}_{label}{ext}"
                                temp_path = A.path.join(temp_dir, normalized_fname)
                                try:
                                    A.rename(temp_path_raw, temp_path)
                                except E:
                                    temp_path = temp_path_raw
                                slot_paths[label] = temp_path
                                ftp_presence[label] = fname
                                remote_info[label] = {"filename": fname, "temp_path": temp_path}
                            except E as T:
                                log_error_loc(
                                    "ftp_download_error", file=fname, error=T
                                )
                        else:
                            ftp_presence[label] = fname
                    O_.quit()
                except E as T:
                    log_error_loc("ftp_check_error", ean=K_, error=T)
                if not C.logged_counts:
                    log_info_loc(
                        "found_images_counts",
                        local=Q(original_files),
                        ftp=Q(remote_files),
                    )
                    C.logged_counts = J
                if C._should_check_sql_presence():
                    columns = []
                    for slot in C.slots:
                        prefix = slot[Aa]
                        label = slot["label"]
                        column_name = C._resolve_sql_column(
                            prefix, label, log_missing=J
                        )
                        columns.append((prefix, column_name, label))
                    context = C._extract_sql_presence_context(K_)
                    if context:
                        table, where_clause = context
                        db_type = config.CONFIG.get(p, K).lower()
                        try:
                            conn = I
                            cur = I
                            try:
                                conn = connect_db()
                                cur = conn.cursor()
                                presence_map = {
                                    prefix: I for prefix, _, _ in columns
                                }
                                for prefix, column_name, _ in columns:
                                    if not column_name:
                                        continue
                                    query = C._build_sql_presence_query(
                                        table, where_clause, column_name, db_type
                                    )
                                    if not query:
                                        continue
                                    try:
                                        cur.execute(query)
                                        row = cur.fetchone()
                                    except E as column_error:
                                        presence_map[prefix] = I
                                        log_error_loc(
                                            "sql_presence_query_error",
                                            column=column_name,
                                            error=column_error,
                                        )
                                        continue
                                    if not row:
                                        presence_map[prefix] = h
                                        continue
                                    value = I
                                    try:
                                        value = row[0]
                                    except E:
                                        try:
                                            values = list(row)
                                        except E:
                                            values = row
                                        if values:
                                            value = values[0]
                                    if isinstance(value, memoryview):
                                        value = bytes(value)
                                    if isinstance(value, (bytes, bytearray)):
                                        try:
                                            value = value.decode("utf-8")
                                        except E:
                                            value = value.decode(
                                                "latin-1", errors="ignore"
                                            )
                                    if isinstance(value, str):
                                        presence_map[prefix] = bool(value.strip())
                                    else:
                                        presence_map[prefix] = value is not I
                                sql_presence = presence_map
                            finally:
                                if cur is not I:
                                    try:
                                        cur.close()
                                    except E:
                                        pass
                                if conn is not I:
                                    try:
                                        conn.close()
                                    except E:
                                        pass
                        except E as T:
                            sql_presence = I
                            log_error_loc("sql_check_error", ean=K_, error=T)
            C.after(
                0,
                lambda: finalize(
                    original_files,
                    slot_paths,
                    ftp_presence,
                    remote_info,
                    ean_guess,
                    sql_presence,
                ),
            )

        def finalize(
            original_files, slot_paths, ftp_presence, remote_info, ean_guess, sql_presence
        ):
            if ean_guess and C.var_ean.get().strip() == B:
                C.suppress_next_lookup = J
                C.var_ean.set(ean_guess)
                C.suppress_next_lookup = h
            C.original_files = original_files
            C.ftp_remote_only = remote_info
            C.ftp_presence = ftp_presence
            C.ftp_downloaded_final = set()
            C.sql_presence = sql_presence
            slots = list(A0(C.slots))
            batch_size = 2

            def process_batch(start_index=0):
                end_index = min(start_index + batch_size, Q(slots))
                for X_, G_ in slots[start_index:end_index]:
                    R_ = G_[Aa]
                    if R_ in slot_paths:
                        G_[f] = slot_paths[R_]
                        C._update_slot_ui(X_)
                        C._mark_slot(X_, A4)
                    else:
                        G_[f] = I
                    C._set_icon_status(G_["local_icon"], R_ in original_files)
                    C._set_icon_status(G_["ftp_icon"], R_ in ftp_presence)
                    if isinstance(sql_presence, dict):
                        C._set_icon_status(
                            G_["sql_icon"], sql_presence.get(R_, h)
                        )
                    else:
                        C._set_icon_status(G_["sql_icon"], I)
                    if R_ not in slot_paths:
                        C._update_slot_activity(X_, active=h)
                if end_index < Q(slots):
                    C.after(1, lambda: process_batch(end_index))

            process_batch()

        threading.Thread(target=worker, daemon=J).start()

    def _on_model_commit(D):
        H = "new"
        o = D.var_name.get().strip()
        p = D.var_type.get().strip()
        e_ = D.var_model.get().strip()
        if not o or not p or not e_:
            return
        if not D._list_has_value(s, e_):
            result = D._prompt_add_list_value(
                s,
                e_,
                MODEL_NOT_IN_LIST_QUESTION.format(value=e_),
                D.combo_model,
            )
            if result is None:
                return
            if result:
                e_ = D._normalize_list_value(s, e_)
                if e_:
                    D.var_model.set(e_)
            else:
                D.var_model.set(B)
                return
        T = A.path.join(l, o.upper(), p.upper(), e_.upper())
        A0_ = []
        if A.path.isdir(T):
            for A1 in A.listdir(T):
                A7 = A.path.join(T, A1)
                if A.path.isdir(A7):
                    A0_.append(A1)
            D.combo_model.configure(style=Z)
        else:
            D.combo_model.configure(style=j)
        r = [A_ for A_ in A0_ if g not in A_]
        A8_ = [A_ for A_ in D.lists[Y] if A_ not in r]
        A9_ = r + A8_
        D._refresh_combobox_list(D.combo_color1, A9_, existing_count=Q(r))
        D.combo_color2[S] = D.lists[Y]
        D.combo_color3[S] = D.lists[Y]
        for AA_ in (D.combo_color1, D.combo_color2, D.combo_color3):
            AA_.configure(state=X)
        D.var_color1.set(B)
        D.var_color2.set(B)
        D.var_color3.set(B)
        D.var_extra.set(B)
        D.var_ean.set(B)
        D.combo_extra.configure(style=j, state=V)
        D.btn_submit.configure(state=V)
        D.btn_open.configure(state=V)
        D._clear_all_slots()
        if not (D.loading_by_ean or D.suppress_scan):
            k_ = []
            if A.path.isdir(T):
                for A2 in A.listdir(T):
                    t_ = A.path.join(T, A2)
                    if A.path.isdir(t_):
                        f_ = A2.split(g)
                        a_ = f_[0] if Q(f_) > 0 else B
                        K__ = f_[1] if Q(f_) > 1 else B
                        M__ = f_[2] if Q(f_) > 2 else B
                        for A3 in A.listdir(t_):
                            AB_ = A.path.join(t_, A3)
                            if A.path.isdir(AB_):
                                u = A3
                                if u.upper() == L or u.upper() == L:
                                    N_ = L
                                else:
                                    N_ = u
                                R_ = q
                                for AC_, b_ in D.entries.items():
                                    if (
                                        b_.get(Ae) == o.upper()
                                        and b_.get(Ad) == p.upper()
                                        and b_.get(AZ) == e_.upper()
                                        and G(b_.get(AY) or B) == a_
                                        and G(b_.get(AX) or B) == K__
                                        and G(b_.get(AW) or B) == M__
                                        and G(b_.get(d) or B) == N_
                                    ):
                                        R_ = AC_
                                        break
                                k_.append((a_, K__, M__, N_, R_))
            if k_:
                if D.model_select_win_open:
                    return
                D.model_select_win_open = J
                P_ = F.Toplevel(D)
                P_.title(SELECT_COMBINATION_TITLE)
                P_.grab_set()
                F.Label(P_, text=SELECT_COMBINATION_PROMPT).pack(pady=5)
                v = C.Frame(P_)
                v.pack(padx=10, fill=z, expand=J)
                m = []
                for AD_ in k_:
                    a_, K__, M__, N_, R_ = AD_
                    w = a_
                    if K__:
                        w += f" / {K__}"
                    if M__:
                        w += f" / {M__}"
                    x = f"{w} - {N_} (EAN: {R_})"
                    m.append(x)
                AE_ = max((Q(A_) for A_ in m), default=0)
                AF_ = max(AE_ + 3, 20)
                i_ = F.Listbox(v, height=5, width=AF_)
                A4_ = C.Scrollbar(v, orient=An, command=i_.yview)
                i_.configure(yscrollcommand=A4_.set)
                A4_.pack(side=AV, fill="y")
                i_.pack(side=Am, fill=z, expand=J)
                for x in m:
                    i_.insert(F.END, x)
                if m:
                    i_.selection_set(0)

                def AG_():
                    A_ = i_.curselection()
                    if not A_:
                        return
                    B_ = A_[0]
                    D.selected_combo = k_[B_]
                    P_.destroy()

                def AH_():
                    D.selected_combo = H
                    P_.destroy()

                n = C.Frame(P_)
                n.pack(pady=5)
                C.Button(n, text=CHOOSE_LABEL, command=AG_).grid(row=0, column=0, padx=5)
                C.Button(n, text=NEW_COMBINATION_LABEL, command=AH_).grid(
                    row=0, column=1, padx=5
                )
                C.Button(n, text=CANCEL_LABEL, command=lambda: P_.destroy()).grid(
                    row=0, column=2, padx=5
                )
                D.selected_combo = I
                D.wait_window(P_)
                D.model_select_win_open = h
                y_ = Aj(D, "selected_combo", I)
                D.selected_combo = I
                if y_ and y_ != H:
                    a_, K__, M__, N_, R_ = y_
                    D.var_color1.set(a_)
                    D.var_color2.set(K__)
                    D.var_color3.set(M__)
                    AI_ = g.join([A_ for A_ in (a_, K__, M__) if A_])
                    c_ = A.path.join(T, AI_)
                    H_ = []
                    if A.path.isdir(c_):
                        H_ = [
                            B for B in A.listdir(c_) if A.path.isdir(A.path.join(c_, B))
                        ]
                        D.combo_color1.configure(style=Z)
                        if K__:
                            D.combo_color2.configure(style=Z)
                        if M__:
                            D.combo_color3.configure(style=Z)
                    else:
                        D.combo_color1.configure(style=j)
                        if K__:
                            D.combo_color2.configure(style=j)
                        if M__:
                            D.combo_color3.configure(style=j)
                    AK_ = [A_ for A_ in D.lists[d] if A_ not in H_]
                    if L in H_ and L not in H_:
                        try:
                            A.rename(A.path.join(c_, L), A.path.join(c_, L))
                        except E as AL_:
                            log_error_loc("rename_no_led_failed", error=AL_)
                        H_ = [
                            B for B in A.listdir(c_) if A.path.isdir(A.path.join(c_, B))
                        ]
                        if L in H_:
                            H_[H_.index(L)] = L
                    D._refresh_combobox_list(
                        D.combo_extra, H_ + AK_, existing_count=Q(H_)
                    )
                    D.combo_extra.configure(state=X)
                    if N_ == L:
                        D.var_extra.set(B)
                    else:
                        D.var_extra.set(N_)
                    if R_ and G(R_).upper() != q:
                        D.var_ean.set(R_)
                    else:
                        D.var_ean.set(q)
                    D.combo_extra.configure(
                        style=Z if N_ in H_ or N_ == L and L in H_ else j
                    )
                    D.combo_model.configure(style=Z)
                    D.combo_color1.configure(style=Z)
                    if K__:
                        D.combo_color2.configure(style=Z)
                    if M__:
                        D.combo_color3.configure(style=Z)
                    D._load_existing_files()
                    D.btn_submit.configure(state=X)
                    D.btn_open.configure(state=X)

    def _on_key_release(C, event):
        J_ = event
        A_ = J_.widget
        if J_.keysym in ("Up", "Down", "Left", "Right"):
            return
        D_ = I
        if A_ == C.combo_name:
            D_ = n
        elif A_ == C.combo_type:
            D_ = t
        elif A_ == C.combo_model:
            D_ = s
        elif A_ in (C.combo_color1, C.combo_color2, C.combo_color3):
            D_ = Y
        elif A_ == C.combo_extra:
            D_ = d
        else:
            return
        E_ = A_.get()
        if E_ == B:
            A_[S] = C.lists[D_]
            return
        H_ = [A for A in C.lists[D_] if A and A.lower().startswith(E_.lower())]
        if H_:
            H_.sort(key=G.lower)
            A_[S] = H_
            if J_.keysym not in ("BackSpace", "Delete"):
                K_ = H_[0]
                if E_.lower() != K_.lower():
                    A_.set(K_)
                    A_.icursor(Q(E_))
                    A_.selection_range(Q(E_), F.END)
        else:
            A_[S] = []

    def _on_color_commit(C):
        M_ = C.var_name.get().strip()
        N_ = C.var_type.get().strip()
        H_ = C.var_color1.get().strip()
        F_ = C.var_color2.get().strip()
        G_ = C.var_color3.get().strip()
        if C.var_ean.get().strip():
            C.var_ean.set(B)
        if not M_ or not N_ or not H_:
            return
        J_ = [A for A in (H_, F_, G_) if A and not C._list_has_value(Y, A)]
        if J_:
            if Y in C._active_list_prompts:
                return
            C._active_list_prompts.add(Y)
            try:
                P_ = AI.join(J_)
                R_ = (
                    COLOR_NOT_IN_LIST_SINGLE_QUESTION.format(value=J_[0])
                    if Q(J_) == 1
                    else COLOR_NOT_IN_LIST_PLURAL_QUESTION.format(values=P_)
                )
                if O.askyesno(AJ, R_):
                    K_ = []
                    for T in J_:
                        if not C._add_list_value(Y, T):
                            K_.append(T)
                    if H_ in K_:
                        C.var_color1.set(B)
                        return
                    if F_ and F_ in K_:
                        C.var_color2.set(B)
                    if G_ and G_ in K_:
                        C.var_color3.set(B)
                else:
                    if H_ in J_:
                        C.var_color1.set(B)
                        return
                    if F_ and F_ in J_:
                        C.var_color2.set(B)
                    if G_ and G_ in J_:
                        C.var_color3.set(B)
            finally:
                C._active_list_prompts.discard(Y)
                C._focus_widget(C.combo_color1)
        H_ = C.var_color1.get().strip()
        if not H_:
            return
        K_ = [H_]
        if F_:
            K_.append(F_)
        if G_:
            K_.append(G_)
        V_ = g.join(K_)
        I_ = A.path.join(
            l, M_.upper(), N_.upper(), C.var_model.get().strip().upper(), V_
        )
        D_ = []
        if A.path.isdir(I_):
            D_ = [B for B in A.listdir(I_) if A.path.isdir(A.path.join(I_, B))]
            if L in D_ and L not in D_:
                try:
                    A.rename(A.path.join(I_, L), A.path.join(I_, L))
                except E as a_:
                    log_error_loc("rename_no_led_failed", error=a_)
                D_ = [B for B in A.listdir(I_) if A.path.isdir(A.path.join(I_, B))]
            if L in D_:
                D_[D_.index(L)] = L
            C.combo_color1.configure(style=Z)
            if F_:
                C.combo_color2.configure(style=Z)
            if G_:
                C.combo_color3.configure(style=Z)
        else:
            C.combo_color1.configure(style=j)
            if F_:
                C.combo_color2.configure(style=j)
            if G_:
                C.combo_color3.configure(style=j)
        b_ = [A for A in C.lists[d] if A not in D_]
        C._refresh_combobox_list(C.combo_extra, D_ + b_, existing_count=Q(D_))
        C.combo_extra.configure(state=X)
        C.entry_ean.configure(state=X)
        C.btn_submit.configure(state=X)
        C.btn_open.configure(state=X)
        extra_raw = C.var_extra.get()
        C.var_extra.set(G(extra_raw).strip())
        if not C.suppress_scan:
            C._load_existing_files()

    def _on_extra_commit(C):
        D_ = C.var_extra.get().strip()
        G_ = C.var_name.get().strip()
        H_ = C.var_type.get().strip()
        I_ = C.var_model.get().strip()
        F_ = C.var_color1.get().strip()
        J_ = C.var_color2.get().strip()
        K_ = C.var_color3.get().strip()
        if D_ == B:
            C.combo_extra.configure(style=j)
        else:
            if not C._list_has_value(d, D_):
                result = C._prompt_add_list_value(
                    d,
                    D_,
                    VALUE_NOT_EXISTS_QUESTION.format(value=D_),
                    C.combo_extra,
                )
                if result is None:
                    return
                if result:
                    D_ = C._normalize_list_value(d, D_)
                    if D_:
                        C.var_extra.set(D_)
                else:
                    C.var_extra.set(B)
                    D_ = B
                    C.combo_extra.configure(style=j)
                    return
            E_ = A.path.join(
                l, G_.upper(), H_.upper(), I_.upper(), F_.upper() if F_ else B
            )
            if J_:
                E_ = A.path.join(E_, J_.upper())
                if K_:
                    E_ = A.path.join(E_, K_.upper())
            N_ = D_.strip().replace(a, g).upper() if D_ else L
            E_ = A.path.join(E_, N_)
            if A.path.isdir(E_):
                C.combo_extra.configure(style=Z)
            else:
                C.combo_extra.configure(style=j)
        if G_ and H_ and I_ and F_ and not C.suppress_scan:
            C._load_existing_files()

    def _select_file(A, idx):
        if A.is_processing:
            O.showwarning(OPERATION_TITLE, PROCESSING_MSG)
            return
        if not (
            A.var_name.get().strip()
            and A.var_type.get().strip()
            and A.var_model.get().strip()
            and A.var_color1.get().strip()
        ):
            O.showwarning(INCOMPLETE_DATA_MSG, MISSING_FIELDS_MSG)
            return
        C_ = [
            (FILETYPE_IMAGES_LABEL, "*.jpg *.jpeg *.png *.pdf *.doc *.docx"),
            (FILETYPE_ALL_LABEL, "*.*"),
        ]
        B_ = BT.askopenfilename(title=SELECT_FILE_TITLE, filetypes=C_)
        if B_:
            A._add_file_to_slot(idx, B_)

    def _on_drop(C, event, idx):
        if C.is_processing:
            return
        if not (
            C.var_name.get().strip()
            and C.var_type.get().strip()
            and C.var_model.get().strip()
            and C.var_color1.get().strip()
        ):
            O.showwarning(INCOMPLETE_DATA_MSG, MISSING_FIELDS_MSG)
            return
        G_ = C.tk.splitlist(event.data)
        if G_:
            C._add_file_to_slot(idx, G_[0])
        if C.dragging_idx is not I:
            D_ = C.dragging_idx
            if D_ != idx:
                H_ = h
                E_ = C.slots[D_][f]
                if E_:
                    if D_ in C.pending_additions:
                        C.pending_additions.pop(D_, I)
                        H_ = J
                    elif E_.startswith(l) and A.path.isfile(E_):
                        C.pending_deletions[D_] = E_
                    C.slots[D_][f] = I
                    F_ = C.slots[D_]
                    F_[y].configure(image=B, text=NO_FILE_LABEL)
                    F_[y].image = I
                    F_[A7].place_forget()
                    if H_:
                        C._mark_slot(D_, I)
                    else:
                        C._mark_slot(D_, AR)
                    C.focus_force()
            C.dragging_idx = I

    def _add_file_to_slot(B, idx, src_path):
        E_ = src_path
        C_ = idx
        D_ = B.slots[C_][f]
        if D_:
            if C_ in B.pending_additions:
                B.pending_additions.pop(C_, I)
            elif D_.startswith(l) and A.path.isfile(D_):
                B.pending_deletions[C_] = D_
        F_ = B.var_ean.get().strip()
        if not F_:
            F_ = q
        B.pending_additions[C_] = E_
        B.slots[C_][f] = E_
        B._update_slot_ui(C_)
        B.slots[C_][A7].place(x=0, y=0)
        B._mark_slot(C_, AR)
        B._set_icon_status(B.slots[C_]["local_icon"], J)
        if "sql_icon" in B.slots[C_]:
            B._set_icon_status(B.slots[C_]["sql_icon"], I)

    def _update_slot_ui(J, idx):
        D_ = J.slots[idx]
        F_ = D_[f]
        if not F_:
            return
        J._update_slot_activity(idx, active=Al, status=J._slot_status["loading"])
        D_[A7].place(x=0, y=0)
        J._queue_thumbnail(idx, F_)

    def _remove_file(C, idx):
        if C.is_processing:
            O.showwarning(OPERATION_TITLE, PROCESSING_MSG)
            return
        D_ = idx
        E_ = C.slots[D_]
        F_ = E_[f]
        if F_:
            if not O.askyesno(
                "Usuń plik", f"Czy na pewno usunąć plik {A.path.basename(F_)}?"
            ):
                return
            G_ = h
            if D_ in C.pending_additions:
                C.pending_additions.pop(D_, I)
                G_ = J
            elif F_.startswith(l) and A.path.isfile(F_):
                C.pending_deletions[D_] = F_
            elif not F_.startswith(l):
                label = E_[Aa]
                remote_name = I
                info = C.ftp_remote_only.pop(label, I)
                if info:
                    remote_name = info.get("filename")
                elif label in C.ftp_presence:
                    remote_name = C.ftp_presence.get(label)
                if remote_name:
                    C.pending_ftp_deletions[D_] = remote_name
            E_[f] = I
            E_[y].configure(image=B, text=NO_FILE_LABEL)
            E_[y].image = I
            E_[A7].place_forget()
            C._thumb_tokens.pop(D_, I)
            C._set_icon_status(E_["local_icon"], h)
            if "sql_icon" in E_:
                C._set_icon_status(E_["sql_icon"], I)
            if G_:
                C._mark_slot(D_, I)
            else:
                C._mark_slot(D_, AR)
            C._update_slot_activity(D_, active=h)
            C.focus_force()

    def _clear_all_slots(C):
        C.pending_additions.clear()
        C.pending_deletions.clear()
        C.pending_ftp_deletions.clear()
        C._thumb_tokens.clear()
        C.sql_presence = I
        for A_ in C.slots:
            A_[f] = I
            A_[y].configure(image=B, text=NO_FILE_LABEL)
            A_[y].image = I
            A_[A7].place_forget()
            A_["local_icon"].place_forget()
            A_["local_icon"].delete("slash")
            A_["ftp_icon"].place_forget()
            A_["ftp_icon"].delete("slash")
            if "sql_icon" in A_:
                A_["sql_icon"].place_forget()
                A_["sql_icon"].delete("slash")
            if "status_label" in A_:
                A_["status_label"].configure(text=C._slot_status["empty"])
            if "progress" in A_:
                A_["progress"].stop()
                A_["progress"].configure(mode="determinate", value=0)
            if AS in A_:
                A_[AS].configure(
                    highlightthickness=0, highlightbackground=A8, highlightcolor=A8
                )

    def _reset_form_fields(A, keep_ean=h):
        A.var_name.set(B)
        A.var_type.set(B)
        A.var_model.set(B)
        A.var_color1.set(B)
        A.var_color2.set(B)
        A.var_color3.set(B)
        A.var_extra.set(B)
        if not keep_ean:
            A.var_ean.set(B)
        if Aj(A, "combo_name", I):
            A.combo_name.configure(state=X, style=j)
            A.combo_name[S] = A.lists.get(n, [])
        if Aj(A, "combo_type", I):
            A.combo_type.configure(state=V, style=j)
            A.combo_type[S] = A.lists.get(t, [])
        if Aj(A, "combo_model", I):
            A.combo_model.configure(state=V, style=j)
            A.combo_model[S] = A.lists.get(s, [])
        if Aj(A, "combo_color1", I):
            A.combo_color1.configure(state=V, style=j)
            A.combo_color1[S] = A.lists.get(Y, [])
        if Aj(A, "combo_color2", I):
            A.combo_color2.configure(state=V, style=j)
            A.combo_color2[S] = A.lists.get(Y, [])
        if Aj(A, "combo_color3", I):
            A.combo_color3.configure(state=V, style=j)
            A.combo_color3[S] = A.lists.get(Y, [])
        if Aj(A, "combo_extra", I):
            A.combo_extra.configure(state=V, style=j)
            A.combo_extra[S] = A.lists.get(d, [])
        if Aj(A, "entry_ean", I):
            A.entry_ean.configure(state=X)
        if Aj(A, "btn_submit", I):
            A.btn_submit.configure(state=V)
        if Aj(A, "btn_open", I):
            A.btn_open.configure(state=V)
        A._clear_all_slots()

    def _open_list_editor(E, focus_sheet=I):
        existing = Aj(E, "_list_editor_window", I)
        if existing and existing.winfo_exists():
            try:
                if focus_sheet and Aj(E, "_list_editor_notebook", I):
                    idx = Aj(E, "_list_editor_tabs", {}).get(focus_sheet)
                    if idx is not I:
                        E._list_editor_notebook.select(idx)
                existing.deiconify()
                existing.lift()
                existing.grab_set()
                existing.focus_force()
            except E:
                pass
            return existing
        E._last_focus_widget = E.focus_get()
        H_ = F.Toplevel(E)
        H_.title(EDIT_LISTS_LABEL)
        H_.grab_set()
        I_ = C.Notebook(H_)
        I_.pack(expand=J, fill=z, padx=5, pady=5)
        E._list_editor_window = H_
        E._list_editor_notebook = I_
        E._list_editor_tabs = {}
        M_ = {}
        Aq_ = (n, t, s, Y, d)
        P_ = [
            (A_, LIST_EDITOR_TAB_LABELS.get(A_, A_))
            for A_ in Aq_
        ]
        N_ = 0
        for R_, (A_, S_) in A0(P_):
            B_ = C.Frame(I_)
            I_.add(B_, text=S_)
            M_[A_] = B_
            E._list_editor_tabs[A_] = R_
            if focus_sheet == A_:
                N_ = R_
        I_.select(N_)
        K_ = 0
        for T in Aq_:
            for G_ in E.lists[T]:
                if G_ and Q(G_) > K_:
                    K_ = Q(G_)
        U = max(K_ + 3, 20)
        for A_, B_ in M_.items():
            V_ = E.lists[A_]
            D_ = F.Listbox(B_, height=5, width=U)
            O_ = C.Scrollbar(B_, orient=An, command=D_.yview)
            D_.configure(yscrollcommand=O_.set)
            L_ = C.Frame(B_)
            L_.pack(side=AV, fill="y", padx=5, pady=5)
            O_.pack(side=AV, fill="y", pady=5)
            D_.pack(side=Am, fill=z, expand=J, padx=5, pady=5)
            for G_ in V_:
                D_.insert(F.END, G_)
            C.Button(
                L_,
                text=LIST_ADD_BUTTON_LABEL,
                command=lambda k=A_, l=D_: E._add_list_item(k, l),
            ).pack(fill="x", pady=2)
            C.Button(
                L_,
                text=LIST_REMOVE_BUTTON_LABEL,
                command=lambda k=A_, l=D_: E._remove_list_item(k, l),
            ).pack(fill="x", pady=2)
        def _close():
            if Aj(E, "_list_editor_window", I) is H_:
                E._list_editor_window = I
                E._list_editor_notebook = I
                E._list_editor_tabs = {}
            try:
                H_.destroy()
            finally:
                E._restore_focus()

        H_._close_window = _close
        H_.protocol("WM_DELETE_WINDOW", _close)
        return H_

    def _add_list_item(C, key, listbox):
        B_ = key
        E_ = LIST_EDITOR_TAB_LABELS.get(B_, B_)
        D_ = BI.askstring(
            LIST_ADD_DIALOG_TITLE,
            LIST_ADD_PROMPT_MSG.format(list=E_),
        )
        if D_:
            C._add_list_value(B_, D_, listbox=listbox, show_exists=J)

    def _remove_list_item(A, key, listbox):
        D_ = listbox
        B_ = key
        E_ = D_.curselection()
        if not E_:
            return
        F_ = E_[0]
        C_ = D_.get(F_)
        G_ = LIST_EDITOR_TAB_LABELS.get(B_, B_)
        if O.askyesno(
            LIST_REMOVE_DIALOG_TITLE,
            LIST_REMOVE_PROMPT_MSG.format(value=C_, list=G_),
        ):
            remove_from_list(EXCEL_SHEETS[B_], C_)
            if C_ in A.lists[B_] or C_.upper() in [A.upper() for A in A.lists[B_]]:
                A.lists[B_] = [
                    A_ for A_ in A.lists[B_] if A_.upper() != C_.strip().upper()
                ]
            D_.delete(F_)
            if B_ == n:
                A.combo_name[S] = A.lists[B_]
            elif B_ == t:
                A.combo_type[S] = A.lists[B_]
            elif B_ == s:
                A.combo_model[S] = A.lists[B_]
            elif B_ == Y:
                A.combo_color1[S] = A.lists[B_]
                A.combo_color2[S] = A.lists[B_]
                A.combo_color3[S] = A.lists[B_]
            elif B_ == d:
                A.combo_extra[S] = A.lists[B_]

    def _on_submit(C):
        A2 = "was_existing"
        t = "inter_set"
        s = "del_set"
        p = "add_set"
        o = "pending_del_leftover"
        n = "pending_add_leftover"
        k = "ftp_skipped"
        j = "sql_rows"
        d = "sql_queries"
        c = "ftp_time"
        b = "ftp_deleted"
        Z = "ftp_sent"
        Y = "ftp_error_msg"
        S = "sql_time"
        P = "sql_error_msg"
        K = "error_set"
        if not (
            C.var_name.get().strip()
            and C.var_type.get().strip()
            and C.var_model.get().strip()
            and C.var_color1.get().strip()
        ):
            O.showwarning(
                NO_DATA_MSG,
                FILL_REQUIRED_BEFORE_SUBMIT_MSG,
            )
            return
        if C.var_extra.get().strip() == B:
            C.var_extra.set(L)
        if not C.var_ean.get().strip():
            Ai_ = BI.askstring(
                EAN_PROMPT_TITLE,
                EAN_MISSING_PROMPT,
            )
            if Ai_ is I or Ai_.strip() == B:
                Ai_ = q
            C.var_ean.set(Ai_.strip())
        AE_ = C.var_name.get().strip()
        AF_ = C.var_type.get().strip()
        AG_ = C.var_model.get().strip()
        AH_ = C.var_color1.get().strip()
        p_ = C.var_color2.get().strip()
        s_ = C.var_color3.get().strip()
        b_ = C.var_extra.get().strip()
        if b_ == B or b_.upper() in [L, L]:
            b_ = L
        else:
            b_ = b_.replace(a, g).upper()
        K_ = C.var_ean.get().strip()
        BY_ = K_.upper() != q and K_ in C.entries
        BZ_ = save_ean_entry(
            K_, AE_, AF_, AG_, AH_, p_ or B, s_ or B, b_ if b_ != B else L
        )
        if BZ_ is h:
            return
        else:
            try:
                BC_ = prepare_excel_lists()
                if W in BC_:
                    C.entries = BC_[W]
            except E as R:
                log_error_loc("reload_entries_failed", error=R)
        C.is_processing = J
        C.btn_submit.configure(state=V)
        C.btn_open.configure(state=V)
        for widget in [
            C.combo_name,
            C.combo_type,
            C.combo_model,
            C.combo_color1,
            C.combo_color2,
            C.combo_color3,
            C.combo_extra,
            C.entry_ean,
        ]:
            try:
                widget.configure(state=Ak)
            except:
                pass
        C.ui_log.configure(state=Az)
        C.ui_log.insert(F.END, PROCESSING_UI_MSG + "\n")
        C.ui_log.configure(state=Ak)
        result_data = {}

        def heavy_work():
            A3 = "rowcount"
            X = "optimize"
            W = "quality"
            V = ".png"
            O = ".jpeg"
            F = ".jpg"
            result_data[Z] = 0
            result_data[b] = 0
            result_data[c] = 0
            result_data[d] = 0
            result_data[j] = 0
            result_data[S] = 0
            result_data[K] = set()
            result_data[Y] = B
            result_data[k] = Ay
            result_data[P] = B
            try:
                i_ = A.path.join(l, AE_.upper(), AF_.upper(), AG_.upper())
                Av_ = [AH_.upper()]
                if p_:
                    Av_.append(p_.upper())
                if s_:
                    Av_.append(s_.upper())
                BX_ = g.join(Av_)
                i_ = A.path.join(i_, BX_, b_ if b_ != B else L)
                A.makedirs(i_, exist_ok=J)
                BM_ = []
                files_to_upload = []
                try:
                    if A.path.exists(AN):
                        Af.rmtree(AN)
                    A.makedirs(AN, exist_ok=J)
                except E as R:
                    log_error_loc("backup_folder_failed", error=R)
                backed_up = []
                for T in set(C.pending_deletions.values()):
                    if T and A.path.isfile(T):
                        try:
                            Af.copy2(T, A.path.join(AN, A.path.basename(T)))
                            backed_up.append(A.path.basename(T))
                        except E as R:
                            log_error_loc(
                                "backup_file_failed",
                                file=A.path.basename(T),
                                error=R,
                            )
                if backed_up:
                    log_info_loc(
                        "backup_files_done", files=AI.join(backed_up)
                    )
                if C.ftp_remote_only:
                    for label, info in C.ftp_remote_only.items():
                        for idx, slot in A0(C.slots):
                            if slot[Aa] == label:
                                Az_ = slot[Aa]
                                Be_ = label_category(slot["label"])
                                P_ = [
                                    K_ if K_ else q,
                                    Az_,
                                    Be_,
                                    AE_.upper(),
                                    AF_.upper(),
                                    AG_.upper(),
                                    AH_.upper(),
                                ]
                                if p_:
                                    P_.append(p_.upper())
                                if s_:
                                    P_.append(s_.upper())
                                P_.append(b_ if b_ != B else L)
                                ext = A.path.splitext(info["filename"])[1]
                                c_ = a.join(P_) + ext
                                dest = A.path.join(i_, c_)
                                try:
                                    Af.copy2(info["temp_path"], dest)
                                    log_info_loc(
                                        "ftp_file_downloaded",
                                        file=info["filename"],
                                        temp=c_,
                                    )
                                    files_to_upload.append(c_)
                                    C.slots[idx][f] = dest
                                    C.ftp_downloaded_final.add(c_)
                                except E as R:
                                    log_error_loc(
                                        "file_save_error",
                                        file=info["filename"],
                                        error=R,
                                    )
                                break
                    C.ftp_remote_only = {}
                AJ_ = set(C.pending_additions.keys())
                AL_ = set(C.pending_deletions.keys())
                AM_ = AJ_ & AL_
                for F_ in list(AM_):
                    A8_ = C.pending_additions.get(F_)
                    Ay_ = C.pending_deletions.get(F_)
                    if A8_ and Ay_:
                        try:
                            BD_ = A.path.samefile(A8_, Ay_)
                        except E:
                            BD_ = A.path.normcase(
                                A.path.normpath(A8_)
                            ) == A.path.normcase(A.path.normpath(Ay_))
                        if BD_:
                            C.pending_additions.pop(F_, I)
                            C.pending_deletions.pop(F_, I)
                AJ_ = set(C.pending_additions.keys())
                AL_ = set(C.pending_deletions.keys())
                AM_ = AJ_ & AL_
                BE_ = {}
                for F_, src_path in list(C.pending_additions.items()):
                    if F_ not in C.pending_deletions and C.slots[F_].get(B0) != AR:
                        C.pending_additions.pop(F_, I)
                        continue
                    if not src_path:
                        C.pending_additions.pop(F_, I)
                        continue
                    if not A.path.isfile(src_path):
                        C.pending_additions.pop(F_, I)
                        continue
                    C._update_slot_activity(
                        F_, active=J, status=C._slot_status["processing"]
                    )
                    slot = C.slots[F_]
                    Az_ = slot[Aa]
                    Be_ = label_category(slot["label"])
                    P_ = [
                        K_ if K_ else q,
                        Az_,
                        Be_,
                        AE_.upper(),
                        AF_.upper(),
                        AG_.upper(),
                        AH_.upper(),
                    ]
                    if p_:
                        P_.append(p_.upper())
                    if s_:
                        P_.append(s_.upper())
                    P_.append(b_ if b_ != B else L)
                    BH_ = A.path.splitext(src_path)[1]
                    c_ = a.join(P_) + BH_
                    if F_ in C.pending_ftp_deletions and C.pending_ftp_deletions[F_] == c_:
                        C.pending_ftp_deletions.pop(F_, I)
                    S_ = A.path.join(i_, c_)
                    try:
                        if F_ in C.pending_deletions:
                            old_path = C.pending_deletions.get(F_)
                            if not old_path:
                                C.pending_deletions.pop(F_, I)
                            else:
                                try:
                                    same_target = A.path.samefile(old_path, S_)
                                except E:
                                    same_target = A.path.normcase(
                                        A.path.normpath(old_path)
                                    ) == A.path.normcase(A.path.normpath(S_))
                                if same_target:
                                    C.pending_deletions.pop(F_, I)
                                    try:
                                        if A.path.exists(old_path):
                                            A.remove(old_path)
                                            log_info_loc(
                                                "deleted_file_before_add",
                                                file=A.path.basename(old_path),
                                            )
                                    except E as z:
                                        log_error_loc(
                                            "remove_old_file_failed",
                                            file=A.path.basename(old_path),
                                            error=z,
                                        )
                                elif A.path.exists(S_):
                                    try:
                                        A.remove(S_)
                                    except E as z:
                                        log_error_loc(
                                            "remove_file_before_overwrite_failed",
                                            file=A.path.basename(S_),
                                            error=z,
                                        )
                        elif A.path.exists(S_):
                            try:
                                A.remove(S_)
                            except E as z:
                                log_error_loc(
                                    "remove_file_before_overwrite_failed",
                                    file=A.path.basename(S_),
                                    error=z,
                                )
                        ext_lower = BH_.lower()
                        is_image = ext_lower in IMAGE_EXTENSION_FORMATS
                        if is_image and C.opt_convert_tif.get():
                            target_fmt_raw = C.tif_target_format.get().strip().upper()
                            if not target_fmt_raw:
                                target_fmt_raw = At
                            target_fmt = "JPEG" if target_fmt_raw == "JPG" else target_fmt_raw
                            t_ext = FORMAT_TO_EXTENSION.get(
                                target_fmt, "." + target_fmt_raw.lower()
                            )
                            c_ = a.join(P_) + t_ext
                            S_ = A.path.join(i_, c_)
                            if A.path.exists(S_):
                                try:
                                    A.remove(S_)
                                except E as z:
                                    log_error_loc(
                                        "remove_file_before_overwrite_failed",
                                        file=A.path.basename(S_),
                                        error=z,
                                    )
                            with AA.open(src_path) as A1:
                                if target_fmt == "JPEG" and A1.mode in ("RGBA", "LA", "P"):
                                    A1 = A1.convert("RGB")
                                if C.opt_resize.get():
                                    max_dim = C.resize_max_dim.get() or 2000
                                    A1.thumbnail((max_dim, max_dim), LANCZOS_FILTER)
                                save_params = {}
                                if t_ext in [F, O]:
                                    quality = 95
                                    if C.opt_compress.get():
                                        quality = max(
                                            1, min(100, C.compress_quality.get() or 85)
                                        )
                                    save_params[W] = quality
                                    save_params[X] = J
                                if t_ext == V:
                                    save_params[X] = J
                                A1.save(S_, format=target_fmt, **save_params)
                                if C.opt_maxsize.get():
                                    max_bytes = (C.max_file_kb.get() or 0) * 1024
                                    if max_bytes > 0 and t_ext in [F, O]:
                                        try:
                                            quality = save_params.get(W, 95)
                                            while (
                                                quality > 10
                                                and A.path.getsize(S_) > max_bytes
                                            ):
                                                quality -= 5
                                                A1.save(
                                                    S_,
                                                    format=target_fmt,
                                                    quality=quality,
                                                    optimize=J,
                                                )
                                        except E as R:
                                            log_error_loc(
                                                "file_resize_error",
                                                file=c_,
                                                error=R,
                                            )
                            log_info_loc("image_added_modified", file=c_)
                        elif ext_lower in [F, O, V, ".bmp", ".gif"]:
                            with AA.open(src_path) as A1:
                                if C.opt_resize.get():
                                    max_dim = C.resize_max_dim.get() or 2000
                                    A1.thumbnail((max_dim, max_dim), LANCZOS_FILTER)
                                save_params = {}
                                if ext_lower in [F, O]:
                                    quality = 95
                                    if C.opt_compress.get():
                                        quality = max(
                                            1, min(100, C.compress_quality.get() or 85)
                                        )
                                    save_params[W] = quality
                                    save_params[X] = J
                                if ext_lower == V:
                                    save_params[X] = J
                                A1.save(S_, **save_params)
                                if C.opt_maxsize.get():
                                    max_bytes = (C.max_file_kb.get() or 0) * 1024
                                    if max_bytes > 0:
                                        if A.path.getsize(S_) > max_bytes and ext_lower in [
                                            F,
                                            O,
                                        ]:
                                            try:
                                                quality = save_params.get(W, 95)
                                                while (
                                                    quality > 10
                                                    and A.path.getsize(S_) > max_bytes
                                                ):
                                                    quality -= 5
                                                    A1.save(S_, quality=quality, optimize=J)
                                            except E as R:
                                                log_error_loc(
                                                    "file_resize_error",
                                                    file=c_,
                                                    error=R,
                                                )
                            log_info_loc("image_added_modified", file=c_)
                        elif ext_lower in [".tif", ".tiff"]:
                            Af.copy2(src_path, S_)
                            log_info_loc("file_added_modified", file=c_)
                        elif is_image:
                            Af.copy2(src_path, S_)
                            log_info_loc("file_added_modified", file=c_)
                        else:
                            Af.copy2(src_path, S_)
                            log_info_loc("file_added_modified", file=c_)
                        files_to_upload.append(c_)
                        C.slots[F_][f] = S_
                    except E as y:
                        log_error_loc(
                            "file_copy_failed",
                            file=A.path.basename(src_path),
                            error=y,
                        )
                        result_data[K].add(F_)
                        BE_[F_] = src_path
                        continue
                if K_ and Q(K_) == 13 and K_.isdigit():
                    try:
                        file_list = A.listdir(i_)
                    except E:
                        file_list = []
                    remove_candidates = {
                        A.path.basename(B) for B in C.pending_deletions.values()
                    }
                    for X_ in file_list:
                        path = A.path.join(i_, X_)
                        if not A.path.isfile(path):
                            continue
                        if X_ in remove_candidates:
                            continue
                        P_ = X_.split(a)
                        ean_prefix = P_[0] if P_ else B
                        if ean_prefix.upper() != K_.upper():
                            new_name = K_ + a + a.join(P_[1:]) if Q(P_) > 1 else K_
                            new_path = A.path.join(i_, new_name)
                            try:
                                if A.path.exists(new_path):
                                    A.remove(new_path)
                                A.rename(path, new_path)
                                log_info_loc(
                                    "file_renamed", old=X_, new=new_name
                                )
                                for F_, d_ in A0(C.slots):
                                    if d_[f] and A.path.basename(d_[f]) == X_:
                                        C.slots[F_][f] = new_path
                                        break
                                if X_ in files_to_upload:
                                    Bh_ = files_to_upload.index(X_)
                                    files_to_upload[Bh_] = new_name
                            except E as y:
                                log_error_loc(
                                    "file_rename_error", ean=K_, error=y
                                )
                                for i, d_ in A0(C.slots):
                                    if d_[f] and A.path.basename(d_[f]) == X_:
                                        result_data[K].add(i)
                                        break
                for idx, slot in A0(C.slots):
                    path = slot[f]
                    if (
                        path
                        and A.path.isfile(path)
                        and idx not in C.pending_deletions
                        and slot[Aa] not in C.ftp_presence
                    ):
                        fname = A.path.basename(path)
                        if fname not in files_to_upload:
                            files_to_upload.append(fname)
                        C.pending_additions.setdefault(idx, path)
                Am_ = {}
                for F_, T in list(C.pending_deletions.items()):
                    if F_ in result_data[K]:
                        Am_[F_] = T
                        continue
                    conflict_error = h
                    for Bh in result_data[K]:
                        if C.pending_additions.get(Bh) == T:
                            conflict_error = J
                            break
                    if conflict_error:
                        Am_[F_] = T
                        continue
                    try:
                        if A.path.isfile(T):
                            A.remove(T)
                            log_info_loc(
                                "file_deleted", file=A.path.basename(T)
                            )
                            BO_ = A.path.basename(T)
                            P_ = BO_.split(a)
                            if Q(P_) >= 2:
                                An_ = P_[0]
                                Bi = P_[1]
                                Bj = A.path.splitext(BO_)[1]
                                if An_ and Q(An_) == 13 and An_.isdigit():
                                    BM_.append(f"{An_}_{Bi}{Bj}")
                    except E as y:
                        log_error_loc(
                            "file_delete_failed",
                            file=A.path.basename(T),
                            error=y,
                        )
                        result_data[K].add(F_)
                        Am_[F_] = T
                for Cz_ in C.pending_ftp_deletions.values():
                    if Cz_:
                        BM_.append(Cz_)
                result_data[n] = BE_
                result_data[o] = Am_
                add_set = set(C.pending_additions.keys())
                del_set = set(C.pending_deletions.keys())
                inter_set = add_set & del_set
                result_data[p] = add_set
                result_data[s] = del_set
                result_data[t] = inter_set
                A__ = Ay
                Y_ = B
                BQ = 0
                BR_ = 0
                Bk = Ag.perf_counter()
                if not result_data[K]:
                    if not (K_ and Q(K_) == 13 and K_.isdigit()):
                        A__ = J
                    elif not D.get(ft, J):
                        log_info_loc("ftp_upload_skipped_settings")
                    else:
                        ftp = AB.FTP()
                        try:
                            ftp.connect(D[H][v], D[H][r], timeout=10)
                            ftp.login(D[H][N], D[H][M])
                            ftp.set_pasv(J)
                            if D[H][m]:
                                ftp.cwd(D[H][m])
                        except AB.error_perm as R:
                            AT = G(R)
                            if "530" in AT or LOGIN_INCORRECT_MSG in AT:
                                Y_ = LOGIN_DATA_ERROR_MSG
                            elif As in AT or NO_SUCH_FILE_MSG in AT:
                                Y_ = PATH_NOT_FOUND_MSG
                            else:
                                Y_ = FTP_GENERIC_ERROR_MSG.format(error=AT)
                        except (
                            BK.gaierror,
                            CONNECTION_REFUSED_ERROR,
                            TIMEOUT_ERROR,
                            Au,
                        ) as R:
                            Y_ = NETWORK_ERROR_MSG
                        except E as R:
                            Y_ = OTHER_ERROR_MSG.format(error=R)
                        else:
                            try:
                                files_local = [
                                    B
                                    for B in files_to_upload
                                    if A.path.isfile(A.path.join(i_, B))
                                ]
                                slot_index_by_filename = {}
                                for idx, slot in A0(C.slots):
                                    if slot.get(f):
                                        slot_index_by_filename[
                                            A.path.basename(slot[f])
                                        ] = idx
                                ftp_error = h
                                for X_ in files_local:
                                    if X_ in C.ftp_downloaded_final:
                                        log_info_loc(
                                            "ftp_upload_skipped_downloaded", file=X_
                                        )
                                        continue
                                    P_ = X_.split(a)
                                    Ao_ = P_[0] if P_ else B
                                    if not (Ao_ and Q(Ao_) == 13 and Ao_.isdigit()):
                                        continue
                                    Bl = P_[1] if Q(P_) > 1 else B
                                    Bm = A.path.splitext(X_)[1]
                                    BT = f"{Ao_}_{Bl}{Bm}"
                                    Bn = A.path.join(i_, X_)
                                    idx = slot_index_by_filename.get(X_)
                                    if idx is not I:
                                        C._update_slot_activity(
                                            idx,
                                            active=J,
                                            status=C._slot_status["uploading"],
                                        )
                                    try:
                                        with x(Bn, "rb") as Bo:
                                            ftp.storbinary(f"STOR {BT}", Bo)
                                            BQ += 1
                                            log_info_loc(
                                                "ftp_file_uploaded", file=X_, target=BT
                                            )
                                        if idx is not I:
                                            C._update_slot_activity(idx, active=h)
                                    except E as AU:
                                        Y_ = FTP_UPLOAD_ERROR_MSG.format(
                                            file=X_, error=AU
                                        )
                                        log_error_loc(
                                            "ftp_upload_error_file",
                                            file=X_,
                                            error=AU,
                                        )
                                        ftp_error = J
                                        break
                                if not ftp_error:
                                    Ap = []
                                    for AV_ in BM_:
                                        try:
                                            ftp.delete(AV_)
                                            BR_ += 1
                                            log_info_loc(
                                                "ftp_file_deleted", file=AV_
                                            )
                                        except E as AU:
                                            Bp = G(AU)
                                            if As in Bp:
                                                log_info_loc(
                                                    "ftp_file_missing_no_delete",
                                                    file=AV_,
                                                )
                                            else:
                                                Ap.append(AV_)
                                                log_error_loc(
                                                    "ftp_delete_error",
                                                    file=AV_,
                                                    error=AU,
                                                )
                                    if Ap:
                                        files_joined = AI.join(Ap)
                                        if not Y_:
                                            Y_ = FTP_DELETE_FAILED_MSG.format(
                                                files=files_joined
                                            )
                                        else:
                                            Y_ += FTP_DELETE_FAILED_APPEND_MSG.format(
                                                files=files_joined
                                            )
                            finally:
                                try:
                                    ftp.quit()
                                except E:
                                    pass
                result_data[Y] = Y_
                result_data[k] = A__
                result_data[Z] = BQ
                result_data[b] = BR_
                Bq = int((Ag.perf_counter() - Bk) * 1000)
                result_data[c] = Bq
                AW_ = B
                Aq_ = 0
                CANCEL_LABEL = 0
                INCOMPLETE_DATA_MSG = 0
                if D.get(u, J) and K_ and len(K_) == 13 and K_.isdigit():
                    Br = Ag.perf_counter()
                    try:
                        conn = connect_db()
                        cur = conn.cursor()
                        for d_ in C.slots:
                            Az_ = d_[Aa]
                            B3_ = C._resolve_sql_column(Az_, d_["label"], log_missing=J)
                            if not B3_:
                                continue
                            if d_[f]:
                                if Az_ in C.ftp_presence:
                                    remote_fname = C.ftp_presence.get(Az_)
                                    if not isinstance(remote_fname, str) or not remote_fname:
                                        continue
                                    parts = remote_fname.split(a)
                                    if Q(parts) >= 2:
                                        remote_label = parts[1].split(".")[0]
                                        if remote_label != Az_:
                                            continue
                                Bs = A.path.basename(d_[f])
                                ext = A.path.splitext(Bs)[1].lower()
                                short_name = f"{K_}_{Az_}{ext}"
                                try:
                                    AX_ = D.get(w, SQL_UPDATE_TEMPLATE)
                                    AC_ = AX_.format(
                                        col=B3_, filename=short_name, ean=K_
                                    )
                                except E as R:
                                    raise E(
                                        SQL_FORMAT_ERROR_MSG.format(error=R)
                                    )
                                cur.execute(AC_)
                                Aq_ += 1
                                if Aj(cur, A3, -1) >= 0:
                                    CANCEL_LABEL += cur.rowcount
                            elif Az_ in C.original_files:
                                AX_ = D.get(w, SQL_UPDATE_TEMPLATE)
                                AY_ = I
                                AZ_ = I
                                try:
                                    import re

                                    BU = re.search(
                                        "(?i)update\\s+([0-9A-Za-z_\\.]+)\\s+set", AX_
                                    )
                                    if BU:
                                        AY_ = BU.group(1)
                                    BV = AX_.lower().find(" where")
                                    if BV != -1:
                                        AZ_ = AX_[BV:]
                                except E:
                                    AY_ = I
                                    AZ_ = I
                                if not AY_:
                                    AY_ = "object_query_1"
                                if not AZ_:
                                    AZ_ = " WHERE EAN = '{ean}' OR Towar_powiazany_z_SKU = '{ean}'"
                                Bv = AZ_.replace("{ean}", K_)
                                AC_ = f"UPDATE {AY_} SET {B3_} = ''" + Bv
                                cur.execute(AC_)
                                Aq_ += 1
                                if Aj(cur, A3, -1) >= 0:
                                    CANCEL_LABEL += cur.rowcount
                        if Aq_ > 0:
                            conn.commit()
                            if Aq_:
                                log_info_loc(
                                    "db_update_success_log",
                                    ean=K_,
                                    cols=AI.join([f"{B3_} = ..." for B3_ in []]),
                                )
                        cur.close()
                        conn.close()
                    except E as R:
                        AW_ = G(R)
                        if "cur" in locals():
                            try:
                                cur.close()
                            except:
                                pass
                        if "conn" in locals():
                            try:
                                conn.rollback()
                            except:
                                pass
                            try:
                                conn.close()
                            except:
                                pass
                        log_error_loc("sql_update_error_log", ean=K_, error=R)
                    INCOMPLETE_DATA_MSG = int((Ag.perf_counter() - Br) * 1000)
                result_data[P] = AW_
                result_data[d] = Aq_
                result_data[j] = CANCEL_LABEL
                result_data[S] = INCOMPLETE_DATA_MSG
            except E as exc:
                log_error_loc(
                    "processing_unexpected_error", error=exc
                )
                result_data[K] = set(range(len(C.slots)))
                result_data[Y] = "Operacja przerwana z powodu błędu."
                result_data[P] = G(exc)
            result_data["ean"] = K_
            result_data[A2] = BY_

        thread = threading.Thread(target=heavy_work)
        thread.daemon = True
        thread.start()

        def check_thread():
            if thread.is_alive():
                C.after(100, check_thread)
            else:
                finalize()

        C.after(100, check_thread)

        def finalize():
            A = WARNING_LABEL
            for widget in [
                C.combo_name,
                C.combo_type,
                C.combo_model,
                C.combo_color1,
                C.combo_color2,
                C.combo_color3,
                C.combo_extra,
                C.entry_ean,
            ]:
                try:
                    widget.configure(state=X)
                except:
                    pass
            C.btn_submit.configure(state=X)
            C.btn_open.configure(state=X)
            C.is_processing = h
            err_set = result_data.get(K, set()) or set()
            add_set = result_data.get(p, set())
            del_set = result_data.get(s, set())
            inter_set = result_data.get(t, set())
            for F_ in err_set:
                C._mark_slot(F_, Ab)
            for F_ in inter_set:
                if F_ not in err_set:
                    C._mark_slot(F_, A4)
            for F_ in add_set - inter_set:
                if F_ not in err_set:
                    C._mark_slot(F_, A4)
            for F_ in del_set - inter_set:
                if F_ not in err_set:
                    C._mark_slot(F_, "gray")
            for F_, d_ in A0(C.slots):
                if F_ in add_set or F_ in del_set or F_ in err_set:
                    continue
                if d_[f]:
                    C._mark_slot(F_, A4)
                else:
                    C._mark_slot(F_, I)
            C._update_all_slot_activity(active=h)
            C.pending_additions = result_data.get(n, {})
            C.pending_deletions = result_data.get(o, {})
            Y_ = result_data.get(Y, B)
            A__ = result_data.get(k, Ay)
            AW_msg = result_data.get(P, B)
            K_val = result_data.get("ean", K_)
            if not err_set and not A__ and not Y_ and not AW_msg:
                C._load_existing_files()
            if err_set:
                O.showwarning(
                    A,
                    OPERATION_ERRORS_MSG.format(backup=AN),
                )
            elif Y_:
                O.showerror(
                    FTP_ERROR_LABEL,
                    FTP_SEND_FAILED_MSG.format(reason=Y_),
                )
            elif A__:
                O.showwarning(
                    A,
                    FTP_SKIPPED_NO_EAN_MSG,
                )
            elif result_data[P]:
                log_error_loc(
                    "sql_error", error=result_data[P], time=result_data.get(S, 0)
                )
            else:
                O.showinfo(SAVED_LABEL, UPDATE_SUCCESS_MSG.format(ean=K_val))
            if not A__:
                status = "OK" if not Y_ else Y_
                log_info_loc(
                    "ftp_summary",
                    uploaded=result_data[Z],
                    deleted=result_data[b],
                    time=result_data[c],
                    status=status,
                )
            if D.get(u, J) and not result_data[P]:
                log_info_loc(
                    "sql_summary",
                    queries=result_data[d],
                    rows=result_data[j],
                    time=result_data[S],
                )
            if result_data.get(A2, Ay):
                log_info_loc(
                    "entry_updated_log",
                    ean=K_val,
                    name=AE_,
                    type=AF_,
                    model=AG_,
                    color1=AH_,
                    color2=p_,
                    color3=s_,
                    extras=b_,
                )
            else:
                log_info_loc(
                    "entry_added_log",
                    ean=K_val,
                    name=AE_,
                    type=AF_,
                    model=AG_,
                    color1=AH_,
                    color2=p_,
                    color3=s_,
                    extras=b_,
                )

    def _load_by_ean(A):
        E_ = NO_EAN_LABEL
        D_ = A.var_ean.get().strip()
        if not D_:
            O.showwarning(E_, ENTER_EAN_TO_LOAD_MSG)
            return
        if D_.upper() == q:
            O.showwarning(E_, CANNOT_SEARCH_NO_EAN_MSG)
            return
        A._reset_form_fields(keep_ean=J)
        A.var_ean.set(D_)
        if D_ in A.entries:
            C_ = A.entries[D_]
            G_ = C_.get(Ae, B) or B
            H_ = C_.get(Ad, B) or B
            I_ = C_.get(AZ, B) or B
            K_ = C_.get(AY, B) or B
            M_ = C_.get(AX, B) or B
            N_ = C_.get(AW, B) or B
            F_ = C_.get(d, B) or B
            A.suppress_scan = J
            try:
                A.var_name.set(G_)
                A._on_name_commit()
                A.var_type.set(H_)
                A._on_type_commit()
                A.var_model.set(I_)
                A.loading_by_ean = J
                A._on_model_commit()
                A.loading_by_ean = h
                A.var_color1.set(K_)
                A.var_color2.set(M_)
                A.var_color3.set(N_)
                A._on_color_commit()
                if F_.upper() == L:
                    A.var_extra.set(B)
                else:
                    A.var_extra.set(F_)
                A._on_extra_commit()
                A.var_ean.set(D_)
            finally:
                A.suppress_scan = h
            A._load_existing_files()
        else:
            O.showinfo(NOT_FOUND_LABEL, NO_SAVED_DATA_FOR_EAN_MSG.format(ean=D_))

    def _open_current_folder(B):
        F_ = B.var_name.get().strip()
        G_ = B.var_type.get().strip()
        H_ = B.var_model.get().strip()
        I_ = B.var_color1.get().strip()
        K_ = B.var_color2.get().strip()
        M_ = B.var_color3.get().strip()
        N_ = B.var_extra.get().strip()
        if not (F_ and G_ and H_ and I_):
            O.showwarning(
                NO_DATA_MSG,
                FILL_REQUIRED_BEFORE_OPEN_MSG,
            )
            return
        C_ = A.path.join(l, F_.upper(), G_.upper(), H_.upper())
        D_ = [I_.upper()]
        if K_:
            D_.append(K_.upper())
        if M_:
            D_.append(M_.upper())
        Q_ = g.join(D_)
        R_ = N_.strip().replace(a, g).upper() if N_ else L
        C_ = A.path.join(C_, Q_, R_)
        A.makedirs(C_, exist_ok=J)
        try:
            if A.name == "nt":
                A.startfile(C_)
            else:
                BH.run(["xdg-open", C_], check=h)
        except E as P_:
            O.showerror(AK, FOLDER_OPEN_FAILED_MSG.format(error=P_))
            log_error_loc("folder_open_error", path=C_, error=P_)

    def _open_settings(A):
        existing = getattr(A, "_settings_window", I)
        if existing:
            try:
                if existing.winfo_exists():
                    try:
                        existing.deiconify()
                        existing.lift()
                        current_grab = existing.grab_current()
                        if current_grab in (I, existing):
                            existing.grab_set()
                        existing.focus_force()
                    except E:
                        pass
                    return existing
            except E:
                pass
            A._settings_window = I
        A._last_focus_widget = A.focus_get()
        a = CHANGE_DATA_ADMIN_LABEL
        Y = "*"
        i_ = "readonly"
        A5_ = RUN_AS_ADMIN_MSG
        A6_ = NO_PERMISSIONS_LABEL
        Ag_ = a
        A7_ = DATABASE_LABEL
        A8_ = SERVER_LABEL
        A9_ = MSSQL_SERVER_LABEL
        AA_ = TEST_BUTTON_LABEL
        AC_ = CONNECTED_LABEL
        j_ = PASSWORD_LABEL
        k_ = USER_LABEL
        f_ = MYSQL_LABEL
        Y_ = "write"
        d_ = i_
        a_ = F.Toplevel(A)
        A._settings_window = a_
        a_.title(SETTINGS_LABEL)
        a_.configure(bg=A._ui_colors["bg"])
        try:
            a_.transient(A)
        except E:
            pass
        a_.grab_set()

        def _raise_settings():
            try:
                if not a_.winfo_exists():
                    return
            except E:
                return
            try:
                a_.deiconify()
                a_.lift()
            except E:
                pass
            try:
                a_.focus_force()
            except E:
                pass
            try:
                current = a_.grab_current()
            except E:
                current = I
            try:
                if current in (I, a_):
                    a_.grab_set()
            except E:
                pass

        _raise_settings()
        slot_defs, _ = normalize_slot_definitions(D.get(SLOT_DEFS_KEY))
        sql_column_map, _ = normalize_sql_column_map(
            D.get(SQL_COLUMN_MAP_KEY), slot_defs
        )
        slot_defs = [dict(item) for item in slot_defs]
        sql_column_map = dict(sql_column_map)
        original_slot_defs = copy.deepcopy(slot_defs)
        original_sql_map = dict(sql_column_map)
        current_slot_defs = copy.deepcopy(A.slot_definitions)
        original_sql_settings = {
            "db_type": D.get(p, K),
            "sql_query": D.get(w, B),
            "enable_sql_update": D.get(u, J),
            "mssql": {
                c: D.get(P, {}).get(c, B),
                b: D.get(P, {}).get(b, B),
                N: D.get(P, {}).get(N, B),
                M: D.get(P, {}).get(M, B),
            },
            "mysql": {
                c: D.get(K, {}).get(c, B),
                b: D.get(K, {}).get(b, B),
                N: D.get(K, {}).get(N, B),
                M: D.get(K, {}).get(M, B),
            },
        }
        original_ftp_settings = {
            N: D.get(H, {}).get(N, B),
            M: D.get(H, {}).get(M, B),
        }
        original_translation_settings = {
            TRANSLATION_API_KEY: D.get(TRANSLATION_SETTINGS_KEY, {}).get(
                TRANSLATION_API_KEY, B
            ),
        }
        a_.columnconfigure(0, weight=1)
        a_.rowconfigure(0, weight=1)
        Z = C.Notebook(a_, style="Settings.TNotebook")
        Z.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        tab_padding = (12, 10)
        L = C.Frame(Z, style="Settings.TFrame", padding=tab_padding)
        ftp_tab = C.Frame(Z, style="Settings.TFrame", padding=tab_padding)
        S = C.Frame(Z, style="Settings.TFrame", padding=tab_padding)
        fields_tab = C.Frame(Z, style="Settings.TFrame", padding=tab_padding)
        U = C.Frame(Z, style="Settings.TFrame", padding=tab_padding)
        system_tab = C.Frame(Z, style="Settings.TFrame", padding=tab_padding)
        V_ = C.Frame(Z, style="Settings.TFrame", padding=tab_padding)
        Z.add(L, text=IMAGES_TAB_LABEL)
        Z.add(ftp_tab, text=FTP_TAB_LABEL)
        Z.add(S, text=SQL_TAB_LABEL)
        Z.add(fields_tab, text=FIELDS_TAB_LABEL)
        Z.add(U, text=LANGUAGE_TAB_LABEL)
        Z.add(system_tab, text=APP_TAB_LABEL)
        Z.add(V_, text=LANG.get("diagnostics_tab", "Diagnostyka"))

        def _slabel(parent, *args, **kwargs):
            kwargs.setdefault("style", "Settings.TLabel")
            return C.Label(parent, *args, **kwargs)
        _slabel(L, text=IMAGE_SETTINGS_LABEL, style="SettingsHeader.TLabel").grid(
            row=0, column=0, columnspan=4, padx=5, pady=5, sticky=T
        )
        Ah = C.Checkbutton(L, text=B, variable=A.opt_resize)
        Ah.grid(row=1, column=0, padx=5, sticky=T)
        _slabel(L, text=RESIZE_LABEL).grid(row=1, column=1, sticky=T)
        resize_frame = C.Frame(L, style="Settings.TFrame")
        resize_frame.grid(row=1, column=2, sticky="w")
        l_ = C.Entry(resize_frame, textvariable=A.resize_max_dim, width=5)
        l_.grid(row=0, column=0, sticky="w")
        _slabel(resize_frame, text=PX_MAX_LABEL).grid(
            row=0, column=1, sticky="w", padx=4
        )
        Ai = C.Checkbutton(L, text=B, variable=A.opt_compress)
        Ai.grid(row=2, column=0, padx=5, sticky=T)
        _slabel(L, text=COMPRESS_LABEL).grid(row=2, column=1, sticky=T)
        compress_frame = C.Frame(L, style="Settings.TFrame")
        compress_frame.grid(row=2, column=2, sticky="w")
        n = C.Spinbox(
            compress_frame, from_=10, to=100, textvariable=A.compress_quality, width=5
        )
        n.grid(row=0, column=0, sticky="w")
        _slabel(compress_frame, text=UNIT_PERCENT_LABEL).grid(
            row=0, column=1, sticky="w", padx=4
        )
        Aj = C.Checkbutton(L, text=B, variable=A.opt_maxsize)
        Aj.grid(row=3, column=0, padx=5, sticky=T)
        _slabel(L, text=LIMIT_SIZE_LABEL).grid(row=3, column=1, sticky=T)
        maxsize_frame = C.Frame(L, style="Settings.TFrame")
        maxsize_frame.grid(row=3, column=2, sticky="w")
        o = C.Spinbox(
            maxsize_frame,
            from_=100,
            to=10000,
            increment=100,
            textvariable=A.max_file_kb,
            width=6,
        )
        o.grid(row=0, column=0, sticky="w")
        _slabel(maxsize_frame, text=UNIT_KB_LABEL).grid(
            row=0, column=1, sticky="w", padx=4
        )
        Ak = C.Checkbutton(L, text=B, variable=A.opt_convert_tif)
        Ak.grid(row=4, column=0, padx=5, sticky=T)
        _slabel(L, text=CONVERT_TIF_LABEL).grid(row=4, column=1, sticky=T)
        q = C.Combobox(
            L,
            textvariable=A.tif_target_format,
            values=CONVERT_TARGET_FORMATS,
            state=d_,
            width=10,
        )
        q.grid(row=4, column=2, sticky="w")
        _slabel(
            L,
            text=LANG.get("format_info_label", "Informacje o formacie:"),
        ).grid(row=5, column=1, sticky="nw", padx=5, pady=2)
        format_info_var = F.StringVar(
            value=_format_info_text(A.tif_target_format.get())
        )
        format_info_frame = C.Frame(
            L, width=460, height=60, style="Settings.TFrame"
        )
        format_info_frame.grid(
            row=5, column=2, columnspan=2, sticky="nw", padx=5, pady=2
        )
        format_info_frame.grid_propagate(h)
        format_info_label = _slabel(
            format_info_frame,
            textvariable=format_info_var,
            wraplength=440,
            justify="left",
            anchor="nw",
        )
        format_info_label.grid(row=0, column=0, sticky="nw", padx=4, pady=2)
        _slabel(U, text=LANGUAGE_LABEL).grid(
            row=0, column=0, sticky=R, padx=5, pady=2
        )
        lang_var = F.StringVar(value=LANG_PREF)
        lang_combo = C.Combobox(
            U,
            textvariable=lang_var,
            values=["auto", "pl", "ua", "en"],
            state="readonly",
            width=10,
        )
        lang_combo.grid(row=0, column=1, padx=5, pady=2, sticky=T)
        lang_combo.configure(postcommand=lambda c=lang_combo: A._style_combobox_list(c))
        translation_settings = D.get(TRANSLATION_SETTINGS_KEY, {})
        translation_provider_map = {
            TRANSLATION_PROVIDER_GOOGLE_LABEL: TRANSLATION_PROVIDER_GOOGLE,
            TRANSLATION_PROVIDER_MYMEMORY_LABEL: TRANSLATION_PROVIDER_MYMEMORY,
            TRANSLATION_PROVIDER_DEEPL_LABEL: TRANSLATION_PROVIDER_DEEPL,
        }
        translation_provider_reverse = {
            value: label for label, value in translation_provider_map.items()
        }
        translation_provider_value = translation_settings.get(
            TRANSLATION_PROVIDER_KEY, TRANSLATION_PROVIDER_DEFAULT
        )
        translation_provider_var = F.StringVar(
            value=translation_provider_reverse.get(
                translation_provider_value, TRANSLATION_PROVIDER_GOOGLE_LABEL
            )
        )
        translation_api_key_var = F.StringVar(
            value=translation_settings.get(TRANSLATION_API_KEY, B)
        )
        translation_api_url_var = F.StringVar(
            value=translation_settings.get(TRANSLATION_API_URL, B)
        )
        _slabel(U, text=TRANSLATION_SECTION_LABEL, style="SettingsHeader.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=5, pady=(10, 4)
        )
        _slabel(U, text=TRANSLATION_PROVIDER_LABEL).grid(
            row=2, column=0, sticky=R, padx=5, pady=2
        )
        translation_provider_combo = C.Combobox(
            U,
            textvariable=translation_provider_var,
            values=list(translation_provider_map),
            state="readonly",
            width=22,
        )
        translation_provider_combo.grid(
            row=2, column=1, padx=5, pady=2, sticky=T
        )
        translation_provider_combo.configure(
            postcommand=lambda c=translation_provider_combo: A._style_combobox_list(c)
        )
        _slabel(U, text=TRANSLATION_API_KEY_LABEL).grid(
            row=3, column=0, sticky=R, padx=5, pady=2
        )
        translation_api_key_entry = C.Entry(
            U, textvariable=translation_api_key_var, show=Y, width=30
        )
        translation_api_key_entry.grid(
            row=3, column=1, padx=5, pady=2, sticky="w"
        )
        _slabel(U, text=TRANSLATION_API_URL_LABEL).grid(
            row=4, column=0, sticky=R, padx=5, pady=2
        )
        translation_api_url_entry = C.Entry(
            U, textvariable=translation_api_url_var, width=40
        )
        translation_api_url_entry.grid(
            row=4, column=1, padx=5, pady=2, sticky="w"
        )

        def _sync_translation_state(*_args):
            provider_value = translation_provider_map.get(
                translation_provider_var.get(), TRANSLATION_PROVIDER_DEFAULT
            )
            entry_state = X if provider_value == TRANSLATION_PROVIDER_DEEPL else V
            translation_api_key_entry.configure(state=entry_state)
            translation_api_url_entry.configure(state=entry_state)

        translation_provider_combo.bind(A2, _sync_translation_state)
        _sync_translation_state()

        def _load_local_settings_data():
            data = dict(BASE_DIR_SETTINGS_TEMPLATE)
            try:
                with x(settings.BASE_DIR_SETTINGS_PATH, "r", encoding=k) as handle:
                    existing = Ar.load(handle)
                if Aq(existing, dict):
                    data.update(existing)
            except E:
                pass
            return data

        def _save_local_settings_data(data):
            payload = dict(BASE_DIR_SETTINGS_TEMPLATE)
            if Aq(data, dict):
                payload.update(data)
            raw_secret = payload.get(APP_SECRET_KEY, B)
            if raw_secret:
                payload[APP_SECRET_KEY] = common._encode_local_secret(raw_secret)
            try:
                A.makedirs(A.path.dirname(settings.BASE_DIR_SETTINGS_PATH) or ".", exist_ok=J)
            except E:
                pass
            with x(settings.BASE_DIR_SETTINGS_PATH, T, encoding=k) as handle:
                Ar.dump(payload, handle, indent=4)

        local_settings_data = _load_local_settings_data()
        base_dir_value = local_settings_data.get(
            "base_dir_override", settings.BASE_DIR_OVERRIDE
        )
        if not Aq(base_dir_value, str):
            base_dir_value = settings.BASE_DIR_OVERRIDE or B
        base_dir_value = base_dir_value.strip()
        app_secret_value = local_settings_data.get(
            APP_SECRET_KEY, common.APP_SECRET
        )
        app_secret_value = common._decode_local_secret(
            app_secret_value, common.APP_SECRET
        )
        if not Aq(app_secret_value, str):
            app_secret_value = common.APP_SECRET
        app_secret_value = app_secret_value.strip() or common.APP_SECRET
        app_secret_mask = "*" * max(8, Q(app_secret_value))
        app_secret_var = F.StringVar(value=app_secret_mask)
        base_dir_var = F.StringVar(value=base_dir_value)
        system_unlocked = Ay

        def _choose_base_dir():
            initial_dir = base_dir_var.get().strip() or A.path.expanduser("~")
            selected = BT.askdirectory(
                parent=a_, title=BASE_DIR_PROMPT_TITLE, initialdir=initial_dir
            )
            if selected:
                base_dir_var.set(selected.strip())

        def _set_system_state(state):
            nonlocal system_unlocked
            system_unlocked = state
            if state:
                app_secret_var.set(app_secret_value)
                app_secret_entry.configure(state=X, show=B)
                base_dir_entry.configure(state=X)
                base_dir_btn.configure(state=X)
            else:
                app_secret_var.set(app_secret_mask)
                app_secret_entry.configure(state=i_, show=Y)
                base_dir_entry.configure(state=i_)
                base_dir_btn.configure(state=V)

        def _unlock_system_settings():
            if is_admin():
                _set_system_state(J)
                log_info_loc("settings_app_unlocked")
            else:
                O.showwarning(A6_, A5_)

        _slabel(
            system_tab,
            text=APP_SETTINGS_LABEL,
            style="SettingsHeader.TLabel",
        ).grid(row=0, column=0, columnspan=3, padx=5, pady=(0, 6), sticky="w")
        _slabel(system_tab, text=APP_SECRET_LABEL).grid(
            row=1, column=0, padx=5, pady=4, sticky=R
        )
        app_secret_entry = C.Entry(
            system_tab, textvariable=app_secret_var, show=Y, width=30, state=i_
        )
        app_secret_entry.grid(row=1, column=1, padx=5, pady=4, sticky="ew")
        _slabel(system_tab, text=BASE_DIR_OVERRIDE_LABEL).grid(
            row=2, column=0, padx=5, pady=4, sticky=R
        )
        base_dir_entry = C.Entry(
            system_tab, textvariable=base_dir_var, width=50, state=i_
        )
        base_dir_entry.grid(row=2, column=1, padx=5, pady=4, sticky="ew")
        base_dir_btn = C.Button(
            system_tab, text=CHOOSE_LABEL, command=_choose_base_dir, state=V
        )
        base_dir_btn.grid(row=2, column=2, padx=5, pady=4, sticky="w")
        _slabel(
            system_tab,
            text=APP_SETTINGS_HINT,
            style="SettingsHint.TLabel",
            wraplength=520,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, padx=5, pady=(6, 4), sticky="w")
        system_admin_btn = C.Button(
            system_tab, text=Ag_, command=_unlock_system_settings
        )
        system_admin_btn.grid(
            row=4, column=0, columnspan=3, padx=5, pady=(4, 0), sticky="e"
        )
        system_tab.columnconfigure(1, weight=1)
        _set_system_state(Ay)
        _slabel(
            V_,
            text=LANG.get("error_test_label", "Testy błędów"),
            style="SettingsHeader.TLabel",
        ).grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky=T)
        error_options = [
            LANG.get("error_test_zero_div", "Podział przez zero"),
            LANG.get("error_test_file_missing", "Brakujący plik"),
            LANG.get("error_test_value_error", "Błąd ValueError"),
            LANG.get("error_test_thread_error", "Błąd w wątku"),
        ]
        error_map = {
            error_options[0]: "zero_div",
            error_options[1]: "file_missing",
            error_options[2]: "value_error",
            error_options[3]: "thread_error",
        }
        error_var = F.StringVar(value=error_options[0] if error_options else B)
        error_combo = C.Combobox(
            V_,
            textvariable=error_var,
            values=error_options,
            state="readonly",
            width=30,
        )
        error_combo.grid(row=1, column=0, padx=5, pady=5, sticky=T)
        error_combo.configure(postcommand=lambda c=error_combo: A._style_combobox_list(c))

        def _trigger_error():
            selection = error_var.get()
            test_key = error_map.get(selection, "value_error")
            A._trigger_test_error(test_key)

        C.Button(
            V_,
            text=LANG.get("error_test_button", "Wywołaj błąd"),
            command=_trigger_error,
        ).grid(row=1, column=1, padx=5, pady=5, sticky="w")
        _slabel(
            V_,
            text=LANG.get(
                "error_test_hint",
                "Wybrane testy celowo wywołują wyjątek w celu sprawdzenia obsługi błędów.",
            ),
            wraplength=400,
            justify="left",
            style="SettingsHint.TLabel",
        ).grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        _slabel(
            V_,
            text=LANG.get("code_check_label", "Szybka diagnostyka kodu"),
            style="SettingsHeader.TLabel",
        ).grid(row=3, column=0, columnspan=2, padx=5, pady=(10, 4), sticky=T)
        code_check_status_var = F.StringVar(value=B)

        def _run_code_check():
            A._run_code_diagnostics(
                code_check_status_var, code_check_btn, code_report
            )

        code_check_btn = C.Button(
            V_,
            text=LANG.get("code_check_button", "Sprawdź kod"),
            command=_run_code_check,
        )
        code_check_btn.grid(row=4, column=0, padx=5, pady=5, sticky=T)
        _slabel(
            V_,
            textvariable=code_check_status_var,
            wraplength=400,
            justify="left",
        ).grid(row=4, column=1, padx=5, pady=5, sticky="w")
        _slabel(
            V_,
            text=LANG.get(
                "code_check_hint",
                "Sprawdza składnię plików .py/.pyw; nie uruchamia całej logiki aplikacji.",
            ),
            wraplength=400,
            justify="left",
            style="SettingsHint.TLabel",
        ).grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        _slabel(
            V_,
            text=LANG.get("ui_check_label", "Testy interfejsu"),
            style="SettingsHeader.TLabel",
        ).grid(row=6, column=0, columnspan=2, padx=5, pady=(8, 4), sticky=T)
        ui_check_status_var = F.StringVar(value=B)

        def _run_ui_check():
            A._run_ui_diagnostics(
                ui_check_status_var, ui_check_btn, code_report, a_
            )

        ui_check_btn = C.Button(
            V_,
            text=LANG.get("ui_check_button", "Test UI"),
            command=_run_ui_check,
        )
        ui_check_btn.grid(row=7, column=0, padx=5, pady=5, sticky=T)
        _slabel(
            V_,
            textvariable=ui_check_status_var,
            wraplength=400,
            justify="left",
        ).grid(row=7, column=1, padx=5, pady=5, sticky="w")
        _slabel(
            V_,
            text=LANG.get(
                "ui_check_hint",
                "Sprawdza podstawowe elementy UI (przyciski, okna, zdarzenia).",
            ),
            wraplength=400,
            justify="left",
            style="SettingsHint.TLabel",
        ).grid(row=8, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        _slabel(
            V_,
            text=LANG.get("code_check_report_label", "Raport diagnostyczny"),
            style="SettingsHeader.TLabel",
        ).grid(row=9, column=0, columnspan=2, padx=5, pady=(8, 4), sticky=T)
        code_report = BS.ScrolledText(
            V_, width=90, height=18, state=V, wrap="word"
        )
        code_report.grid(
            row=10, column=0, columnspan=2, padx=5, pady=(0, 8), sticky="nsew"
        )
        V_.columnconfigure(0, weight=1)
        V_.columnconfigure(1, weight=1)
        V_.rowconfigure(10, weight=1)

        def _toggle_resize(*_args):
            l_.configure(state=X if A.opt_resize.get() else V)

        def _toggle_compress(*_args):
            n.configure(state=X if A.opt_compress.get() else V)

        def _toggle_maxsize(*_args):
            o.configure(state=X if A.opt_maxsize.get() else V)

        resize_trace = A.opt_resize.trace_add(Y_, lambda *_args: _toggle_resize())
        compress_trace = A.opt_compress.trace_add(
            Y_, lambda *_args: _toggle_compress()
        )
        maxsize_trace = A.opt_maxsize.trace_add(Y_, lambda *_args: _toggle_maxsize())
        convert_tif_trace = A.opt_convert_tif.trace_add(
            Y_, lambda *B: q.configure(state=d_ if A.opt_convert_tif.get() else V)
        )
        A.tif_target_format.trace_add(
            Y_, lambda *B: format_info_var.set(_format_info_text(A.tif_target_format.get()))
        )
        l_.configure(state=X if A.opt_resize.get() else V)
        n.configure(state=X if A.opt_compress.get() else V)
        o.configure(state=X if A.opt_maxsize.get() else V)
        q.configure(state=d_ if A.opt_convert_tif.get() else V)
        _slabel(ftp_tab, text=FTP_SERVER_LABEL).grid(
            row=0, column=0, sticky=R, padx=5, pady=2
        )
        s = F.StringVar(value=D[H][v])
        AD_ = C.Entry(ftp_tab, textvariable=s, width=30)
        AD_.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        _slabel(ftp_tab, text=PORT_LABEL).grid(
            row=1, column=0, sticky=R, padx=5, pady=2
        )
        t = F.IntVar(value=D[H][r])
        AE_ = C.Entry(ftp_tab, textvariable=t, width=6)
        AE_.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        _slabel(ftp_tab, text=k_).grid(row=2, column=0, sticky=R, padx=5, pady=2)
        x_ = F.StringVar(value=D[H][N])
        AF_ = C.Entry(ftp_tab, textvariable=x_, width=30)
        AF_.grid(row=2, column=1, padx=5, pady=2, sticky="w")
        _slabel(ftp_tab, text=j_).grid(row=3, column=0, sticky=R, padx=5, pady=2)
        y_ = F.StringVar(value=D[H][M])
        AG_ = C.Entry(ftp_tab, textvariable=y_, show=Y, width=30)
        AG_.grid(row=3, column=1, padx=5, pady=2, sticky="w")
        _slabel(ftp_tab, text=FTP_PATH_LABEL).grid(
            row=4, column=0, sticky=R, padx=5, pady=2
        )
        g_ = F.StringVar(value=D[H][m])
        AH_ = C.Entry(ftp_tab, textvariable=g_, width=30)
        AH_.grid(row=4, column=1, padx=5, pady=2, sticky="w")
        AI_ = C.Button(ftp_tab, text=a)
        AI_.grid(row=5, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        _slabel(ftp_tab, text=FTP_TEST_LABEL).grid(
            row=6, column=0, sticky=R, padx=5, pady=5
        )
        AJ_ = F.StringVar(value=B)
        sql_query_entry = C.Entry(ftp_tab, textvariable=AJ_, width=50, state=d_)
        sql_query_entry.grid(row=6, column=1, padx=5, pady=5, sticky="w")

        def _test_ftp_connection():
            A_ = B
            try:
                C_ = AB.FTP()
                C_.connect(s.get(), t.get(), timeout=10)
                C_.login(x_.get(), y_.get())
                C_.set_pasv(J)
                if g_.get():
                    C_.cwd(g_.get())
            except AB.error_perm as F_:
                D_ = G(F_)
                if "530" in D_ or LOGIN_INCORRECT_MSG in D_:
                    A_ = LOGIN_DATA_ERROR_MSG
                elif As in D_ or NO_SUCH_FILE_MSG in D_:
                    A_ = PATH_NOT_FOUND_MSG
                else:
                    A_ = FTP_GENERIC_ERROR_MSG.format(error=D_)
            except (BK.gaierror, CONNECTION_REFUSED_ERROR, TIMEOUT_ERROR, Au) as F_:
                A_ = NETWORK_ERROR_MSG
            except E as F_:
                A_ = OTHER_ERROR_MSG.format(error=F_)
            else:
                A_ = AC_
                try:
                    C_.quit()
                except E:
                    pass
            AJ_.set(A_)

        ftp_test_btn = C.Button(ftp_tab, text=AA_, command=_test_ftp_connection)
        ftp_test_btn.grid(row=6, column=1, padx=5, pady=5, sticky=R)
        _slabel(ftp_tab, text=FTP_UPDATE_LABEL).grid(
            row=7, column=0, sticky=R, padx=5, pady=2
        )
        ftp_update_var = F.BooleanVar(value=D.get(ft, J))
        ftp_update_cb = C.Checkbutton(ftp_tab, variable=ftp_update_var)
        ftp_update_cb.grid(row=7, column=1, sticky=T, padx=5, pady=2)
        _slabel(S, text=DB_TYPE_LABEL).grid(
            row=0, column=0, sticky=R, padx=5, pady=2
        )
        db_type_var = F.StringVar(value=f_ if D.get(p, K).lower() == K else A9_)
        A1 = C.Combobox(
            S,
            textvariable=db_type_var,
            values=[A9_, f_],
            state=d_,
            width=20,
        )
        A1.grid(row=0, column=1, padx=5, pady=2, sticky=T)
        U = C.Frame(S, style="Settings.TFrame")
        W = C.Frame(S, style="Settings.TFrame")
        _slabel(U, text=A8_).grid(row=0, column=0, sticky=R, padx=5, pady=2)
        AK = F.StringVar(value=D[P][c])
        ensure_package = C.Entry(U, textvariable=AK, width=30)
        ensure_package.grid(row=0, column=1, padx=5, pady=2)
        _slabel(U, text=A7_).grid(row=1, column=0, sticky=R, padx=5, pady=2)
        AM = F.StringVar(value=D[P][b])
        AN = C.Entry(U, textvariable=AM, width=30)
        AN.grid(row=1, column=1, padx=5, pady=2)
        _slabel(U, text=k_).grid(row=2, column=0, sticky=R, padx=5, pady=2)
        AO = F.StringVar(value=D[P][N])
        AQ = C.Entry(U, textvariable=AO, width=30)
        AQ.grid(row=2, column=1, padx=5, pady=2)
        _slabel(U, text=j_).grid(row=3, column=0, sticky=R, padx=5, pady=2)
        AR = F.StringVar(value=D[P][M])
        AS = C.Entry(U, textvariable=AR, show=Y, width=30)
        AS.grid(row=3, column=1, padx=5, pady=2)
        U.grid(row=1, column=0, columnspan=2, sticky=T, padx=5, pady=2)
        _slabel(W, text=A8_).grid(row=0, column=0, sticky=R, padx=5, pady=2)
        AT = F.StringVar(value=D[K][c])
        AU = C.Entry(W, textvariable=AT, width=30)
        AU.grid(row=0, column=1, padx=5, pady=2)
        _slabel(W, text=A7_).grid(row=1, column=0, sticky=R, padx=5, pady=2)
        AV = F.StringVar(value=D[K][b])
        AW = C.Entry(W, textvariable=AV, width=30)
        AW.grid(row=1, column=1, padx=5, pady=2)
        _slabel(W, text=k_).grid(row=2, column=0, sticky=R, padx=5, pady=2)
        AX = F.StringVar(value=D[K][N])
        AY = C.Entry(W, textvariable=AX, width=30)
        AY.grid(row=2, column=1, padx=5, pady=2)
        _slabel(W, text=j_).grid(row=3, column=0, sticky=R, padx=5, pady=2)
        AZ = F.StringVar(value=D[K][M])
        Aa = C.Entry(W, textvariable=AZ, show=Y, width=30)
        Aa.grid(row=3, column=1, padx=5, pady=2)
        W.grid(row=1, column=0, columnspan=2, sticky=T, padx=5, pady=2)
        if D.get(p, K).lower() == K:
            U.grid_remove()
        else:
            W.grid_remove()

        def Az(event=I):
            if db_type_var.get() == f_:
                U.grid_remove()
                W.grid()
            else:
                W.grid_remove()
                U.grid()

        A1.bind(A2, Az)
        _slabel(S, text=SQL_UPDATE_LABEL).grid(
            row=2, column=0, sticky=R, padx=5, pady=2
        )
        Ab = F.BooleanVar(value=D.get(u, J))
        Ac = C.Checkbutton(S, variable=Ab)
        Ac.grid(row=2, column=1, sticky=T, padx=5, pady=2)
        _slabel(S, text=SQL_QUERY_LABEL).grid(
            row=3, column=0, sticky="ne", padx=5, pady=2
        )
        h_ = F.Text(S, width=80, height=3)
        h_.insert(A_, D.get(w, SQL_UPDATE_TEMPLATE))
        h_.grid(row=3, column=1, padx=5, pady=2, sticky=T)
        _slabel(S, text=SQL_TEST_LABEL).grid(
            row=4, column=0, sticky=R, padx=5, pady=5
        )
        A3_ = F.StringVar(value=B)
        MISSING_FIELDS_MSG = C.Entry(S, textvariable=A3_, width=50, state=d_)
        MISSING_FIELDS_MSG.grid(row=4, column=1, padx=5, pady=5, sticky=T)

        def INCOMPLETE_DATA_MSG():
            try:
                A_ = connect_db()
                try:
                    B_ = A_.cursor()
                    try:
                        B_.execute("SELECT 1")
                    except E:
                        pass
                    finally:
                        try:
                            B_.close()
                        except E:
                            pass
                finally:
                    try:
                        A_.close()
                    except E:
                        pass
                A3_.set(AC_)
            except E as C_:
                A3_.set(SQL_TEST_ERROR_MSG.format(error=C_))

        EDIT_LISTS_LABEL = C.Button(S, text=AA_, command=INCOMPLETE_DATA_MSG)
        EDIT_LISTS_LABEL.grid(row=4, column=1, padx=5, pady=5, sticky=R)

        available_columns = list(D.get(SQL_AVAILABLE_COLUMNS_KEY, []))
        sql_mapping_controls = []
        sql_edit_state = V
        fields_controls = []
        fields_state = V
        detect_status_var = F.StringVar(value=B)
        columns_listbox = I
        detect_btn = I
        field_button_widgets = {}

        def _dnd_first_item(payload):
            if not payload:
                return B
            try:
                items = a_.tk.splitlist(payload)
            except E:
                items = [payload]
            if not items:
                return B
            return G(items[0]).strip()

        def _field_button_text(slot):
            title = SLOT_TITLE_FORMAT.format(
                index=slot["prefix"], label=get_slot_label(slot["label"])
            )
            column = G(sql_column_map.get(slot["prefix"], B) or B).strip()
            if column:
                column_text = f"SQL: {column}"
            else:
                column_text = SQL_MAPPING_EMPTY_LABEL
            return f"{title}\n{column_text}"

        def _find_slot(prefix):
            for slot in slot_defs:
                if slot.get("prefix") == prefix:
                    return slot
            return I

        def _apply_sql_mapping(prefix, value):
            column = G(value or B).strip()
            sql_column_map[prefix] = column
            slot = _find_slot(prefix)
            if slot:
                btn = field_button_widgets.get(prefix)
                if btn:
                    btn.configure(text=_field_button_text(slot))

        def _on_column_drop(event, prefix):
            column = _dnd_first_item(event.data)
            if column:
                _apply_sql_mapping(prefix, column)

        def _on_field_drop(event, prefix):
            column = _dnd_first_item(event.data)
            if column:
                _apply_sql_mapping(prefix, column)

        def _on_column_drag_init(event):
            if columns_listbox is I:
                return
            selection = columns_listbox.curselection()
            if not selection:
                return
            value = columns_listbox.get(selection[0])
            return "copy", DND_TEXT, value

        def _set_available_columns(columns, table_name=B):
            nonlocal available_columns
            available_columns = list(columns or [])
            if columns_listbox:
                columns_listbox.delete(0, F.END)
                for col in available_columns:
                    columns_listbox.insert(F.END, col)
            if table_name:
                detect_status_var.set(
                    SQL_COLUMNS_DETECTED_MSG.format(
                        count=len(available_columns), table=table_name
                    )
                )

        def _parse_table_name(template):
            if not template:
                return B
            pattern = (
                r"update\s+(?:top\s+\(?\d+\)?\s+)?"
                r"(?:(?:low_priority|high_priority|ignore)\s+)*"
                r"([^\s]+)\s+set"
            )
            match = re.search(pattern, template, flags=re.I | re.S)
            if not match:
                return B
            return match.group(1).strip().rstrip(";")

        def _split_table_ref(table_ref):
            if not table_ref:
                return B, B
            cleaned = (
                table_ref.replace("[", B)
                .replace("]", B)
                .replace("`", B)
                .replace('"', B)
            )
            parts = [p for p in cleaned.split(".") if p]
            if not parts:
                return B, B
            table_name = parts[-1]
            schema = parts[-2] if len(parts) > 1 else B
            return table_name, schema

        def _detect_sql_columns():
            template = h_.get(A_, "end").strip()
            table_ref = _parse_table_name(template)
            if not table_ref:
                detect_status_var.set(SQL_COLUMNS_PARSE_FAILED_MSG)
                log_error_loc("sql_columns_parse_failed")
                return
            table_name, schema = _split_table_ref(table_ref)
            if not table_name:
                detect_status_var.set(SQL_COLUMNS_PARSE_FAILED_MSG)
                log_error_loc("sql_columns_parse_failed")
                return
            db_is_mysql = db_type_var.get() == f_
            conn = I
            cur = I
            try:
                if db_is_mysql:
                    conn = mysql.connector.connect(
                        host=AT.get().strip(),
                        user=AX.get().strip(),
                        password=AZ.get(),
                        database=AV.get().strip(),
                        connection_timeout=5,
                        use_pure=True,
                    )
                    if schema:
                        query = (
                            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                            "ORDER BY ORDINAL_POSITION"
                        )
                        params = (schema, table_name)
                    else:
                        query = (
                            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
                            "ORDER BY ORDINAL_POSITION"
                        )
                        params = (table_name,)
                else:
                    last_exc = I
                    extra = "Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=5"
                    for driver in BW:
                        try:
                            conn_str = (
                                f"DRIVER={{{driver}}};SERVER={AK.get().strip()};"
                                f"DATABASE={AM.get().strip()};UID={AO.get().strip()};"
                                f"PWD={AR.get()};{extra}"
                            )
                            conn = pyodbc.connect(conn_str)
                            break
                        except E as exc:
                            last_exc = exc
                    if conn is I:
                        raise E(last_exc or "Connection failed")
                    if schema:
                        query = (
                            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
                            "ORDER BY ORDINAL_POSITION"
                        )
                        params = (schema, table_name)
                    else:
                        query = (
                            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                            "WHERE TABLE_NAME = ? ORDER BY ORDINAL_POSITION"
                        )
                        params = (table_name,)
                cur = conn.cursor()
                cur.execute(query, params)
                columns = [G(row[0]) for row in cur.fetchall() if row and row[0]]
            except E as exc:
                detect_status_var.set(
                    SQL_COLUMNS_DETECT_FAILED_MSG.format(error=exc)
                )
                log_error_loc("sql_columns_detect_failed", error=exc)
                return
            finally:
                if cur is not I:
                    try:
                        cur.close()
                    except E:
                        pass
                if conn is not I:
                    try:
                        conn.close()
                    except E:
                        pass
            _set_available_columns(columns, table_ref)
            D[SQL_AVAILABLE_COLUMNS_KEY] = list(available_columns)
            save_config(
                D,
                preserve_secrets={
                    H: {N, M},
                    P: {N, M},
                    K: {N, M},
                    TRANSLATION_SETTINGS_KEY: {TRANSLATION_API_KEY},
                },
            )
            log_info_loc(
                "sql_columns_detected",
                table=table_ref,
                count=len(columns),
            )

        detect_row = C.Frame(S, style="Settings.TFrame")
        detect_row.grid(row=6, column=0, columnspan=2, sticky="w", padx=5, pady=(10, 5))
        detect_btn = C.Button(
            detect_row, text=SQL_DETECT_COLUMNS_LABEL, command=_detect_sql_columns
        )
        detect_btn.grid(row=0, column=0, padx=(0, 6))
        _slabel(detect_row, textvariable=detect_status_var).grid(
            row=0, column=1, sticky="w"
        )
        sql_mapping_controls[:] = [detect_btn]

        fields_tab.columnconfigure(0, weight=1)
        fields_tab.columnconfigure(1, weight=2)
        fields_tab.rowconfigure(1, weight=1)
        _slabel(
            fields_tab, text=FIELDS_MANAGE_LABEL, style="SettingsHeader.TLabel"
        ).grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        columns_panel = C.Frame(fields_tab, style="Settings.TFrame")
        columns_panel.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        columns_panel.columnconfigure(0, weight=1)
        columns_panel.rowconfigure(1, weight=1)
        _slabel(columns_panel, text=SQL_COLUMNS_LABEL).grid(
            row=0, column=0, sticky="w", padx=2, pady=(0, 4)
        )
        columns_listbox = F.Listbox(columns_panel, height=12, exportselection=0)
        columns_listbox.grid(row=1, column=0, sticky="nsew")
        columns_scroll = C.Scrollbar(
            columns_panel, orient=An, command=columns_listbox.yview
        )
        columns_scroll.grid(row=1, column=1, sticky="ns")
        columns_listbox.configure(yscrollcommand=columns_scroll.set)
        if hasattr(columns_listbox, "drag_source_register") and hasattr(
            columns_listbox, "dnd_bind"
        ):
            columns_listbox.drag_source_register(1, DND_TEXT)
            columns_listbox.dnd_bind("<<DragInitCmd>>", _on_column_drag_init)
        fields_controls.append(columns_listbox)
        try:
            columns_listbox.configure(state=fields_state)
        except E:
            pass
        if available_columns:
            _set_available_columns(available_columns)
        fields_grid = C.Frame(fields_tab, style="Settings.TFrame")
        fields_grid.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)

        def _configure_tile_text(widget):
            try:
                if "wraplength" in widget.keys():
                    widget.configure(wraplength=160)
                if "justify" in widget.keys():
                    widget.configure(justify="center")
            except E:
                pass

        def _refresh_fields_grid():
            for child in fields_grid.winfo_children():
                child.destroy()
            fields_controls[:] = []
            field_button_widgets.clear()
            if columns_listbox is not I:
                fields_controls.append(columns_listbox)
            columns = 5
            total = len(slot_defs) + 1
            for idx in Ax(total):
                row_idx, col_idx = divmod(idx, columns)
                if idx < len(slot_defs):
                    slot = slot_defs[idx]
                    title = _field_button_text(slot)
                    btn = C.Button(
                        fields_grid,
                        text=title,
                        command=lambda s=slot: _edit_field(s),
                        width=20,
                        state=fields_state,
                    )
                    _configure_tile_text(btn)
                    field_button_widgets[slot["prefix"]] = btn
                    if hasattr(btn, "drop_target_register") and hasattr(
                        btn, "dnd_bind"
                    ):
                        btn.drop_target_register(DND_TEXT)
                        btn.dnd_bind(
                            "<<Drop>>",
                            lambda e, p=slot["prefix"]: _on_field_drop(e, p),
                        )
                else:
                    btn = C.Button(
                        fields_grid,
                        text=FIELD_ADD_LABEL,
                        command=_add_field,
                        width=20,
                        state=fields_state,
                    )
                    _configure_tile_text(btn)
                fields_controls.append(btn)
                btn.grid(
                    row=row_idx,
                    column=col_idx,
                    padx=6,
                    pady=6,
                    sticky="nsew",
                )
            for col in Ax(columns):
                fields_grid.columnconfigure(col, weight=1)

        def _add_field():
            label = BI.askstring(
                FIELD_ADD_TITLE, FIELD_NAME_PROMPT, parent=a_
            )
            _raise_settings()
            if label is I:
                return
            label = label.strip()
            if not label:
                O.showwarning(WARNING_LABEL, FIELD_NAME_REQUIRED_MSG, parent=a_)
                return
            if any(
                s["label"].strip().lower() == label.lower() for s in slot_defs
            ):
                O.showwarning(
                    WARNING_LABEL,
                    FIELD_NAME_DUPLICATE_MSG.format(label=label),
                    parent=a_,
                )
                return
            prefix = next_slot_prefix(slot_defs)
            slot_defs.append({"prefix": prefix, "label": label})
            sql_column_map.setdefault(prefix, B)
            _refresh_fields_grid()

        def _edit_field(slot):
            editor = F.Toplevel(a_)
            editor.title(FIELD_EDIT_TITLE)
            try:
                editor.transient(a_)
            except E:
                pass
            editor.grab_set()
            C.Label(editor, text=FIELD_NAME_LABEL).grid(
                row=0, column=0, padx=5, pady=5, sticky=R
            )
            name_var = F.StringVar(value=slot["label"])
            name_entry = C.Entry(editor, textvariable=name_var, width=30)
            name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
            name_entry.focus_set()
            C.Label(editor, text=SQL_MAPPING_COLUMN_LABEL).grid(
                row=1, column=0, padx=5, pady=5, sticky=R
            )
            column_var = F.StringVar(value=sql_column_map.get(slot["prefix"], B))
            column_entry = C.Combobox(
                editor,
                textvariable=column_var,
                values=available_columns,
                state=X,
                width=30,
            )
            column_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
            if hasattr(column_entry, "drop_target_register") and hasattr(
                column_entry, "dnd_bind"
            ):
                column_entry.drop_target_register(DND_TEXT)

                def _drop_to_column(event):
                    column = _dnd_first_item(event.data)
                    if column:
                        column_var.set(column)

                column_entry.dnd_bind("<<Drop>>", _drop_to_column)
            def _close_editor():
                try:
                    editor.destroy()
                finally:
                    _raise_settings()

            def _save_field():
                new_label = name_var.get().strip()
                if not new_label:
                    O.showwarning(
                        WARNING_LABEL, FIELD_NAME_REQUIRED_MSG, parent=editor
                    )
                    return
                if any(
                    s is not slot
                    and s["label"].strip().lower() == new_label.lower()
                    for s in slot_defs
                ):
                    O.showwarning(
                        WARNING_LABEL,
                        FIELD_NAME_DUPLICATE_MSG.format(label=new_label),
                        parent=editor,
                    )
                    return
                slot["label"] = new_label
                sql_column_map[slot["prefix"]] = G(column_var.get() or B).strip()
                _refresh_fields_grid()
                _close_editor()

            def _delete_field():
                if not O.askyesno(
                    WARNING_LABEL,
                    FIELD_DELETE_CONFIRM_MSG.format(label=slot["label"]),
                    parent=editor,
                ):
                    return
                slot_defs.remove(slot)
                sql_column_map.pop(slot["prefix"], I)
                _refresh_fields_grid()
                _close_editor()

            def _lang_code_from_filename(filename):
                name = localization.settings.A.path.splitext(G(filename))[0].lower()
                if name == "eng":
                    return "en"
                return name

            def _discover_localization_files():
                lang_files = {}
                for root in localization.settings.get_localization_search_paths():
                    if not root:
                        continue
                    if not localization.settings.A.path.isdir(root):
                        continue
                    try:
                        entries = localization.settings.A.listdir(root)
                    except E:
                        continue
                    for entry in entries:
                        entry_lower = G(entry).lower()
                        if not entry_lower.endswith(".json"):
                            continue
                        code = _lang_code_from_filename(entry_lower)
                        if not code:
                            continue
                        if code not in lang_files:
                            lang_files[code] = localization.settings.A.path.join(
                                root, entry
                            )
                return lang_files

            def _read_translation_value(path, key):
                try:
                    with x(path, "r", encoding=k) as handle:
                        data = localization.Ar.load(handle)
                    if isinstance(data, dict):
                        value = data.get(key, B)
                        if isinstance(value, str):
                            return value
                except E:
                    pass
                return B

            def _translate_label_google(text, lang_code):
                if not text or not lang_code:
                    return I, B
                code = G(lang_code).lower()
                target = {"ua": "uk", "en": "en", "pl": "pl"}.get(code, code)
                try:
                    query = BP.quote_plus(text)
                    url = (
                        "https://translate.googleapis.com/translate_a/single"
                        f"?client=gtx&sl=auto&tl={target}&dt=t&q={query}"
                    )
                    request = BN.Request(
                        url, headers={"User-Agent": "Mozilla/5.0"}
                    )
                    with BN.urlopen(
                        request, timeout=5, context=SSL_CONTEXT
                    ) as response:
                        payload = response.read().decode(k)
                    data = localization.Ar.loads(payload)
                    if isinstance(data, list) and data:
                        parts = []
                        for item in data[0] or []:
                            if isinstance(item, list) and item:
                                part = item[0]
                                if part:
                                    parts.append(part)
                        if parts:
                            return B.join(parts), B
                    return I, "empty response"
                except E as exc:
                    return I, G(exc)

            def _pick_source_lang(text):
                if not text:
                    return "en"
                lower = G(text).lower()
                if re.search(r"[а-яіїєґ]", lower):
                    return "uk"
                if re.search(r"[ąćęłńóśźż]", lower):
                    return "pl"
                return "en"

            def _translate_label_mymemory(text, lang_code, source_lang):
                if not text or not lang_code or not source_lang:
                    return I, B
                code = G(lang_code).lower()
                source = G(source_lang).lower()
                source = {"ua": "uk"}.get(source, source)
                if source == "auto":
                    return I, "invalid source language"
                target = {"ua": "uk", "en": "en", "pl": "pl"}.get(code, code)
                try:
                    query = BP.quote_plus(text)
                    url = (
                        "https://api.mymemory.translated.net/get"
                        f"?q={query}&langpair={source}|{target}"
                    )
                    request = BN.Request(
                        url, headers={"User-Agent": "Mozilla/5.0"}
                    )
                    with BN.urlopen(
                        request, timeout=5, context=SSL_CONTEXT
                    ) as response:
                        payload = response.read().decode(k)
                    data = localization.Ar.loads(payload)
                    if isinstance(data, dict):
                        status = data.get("responseStatus")
                        if status != 200:
                            details = data.get("responseDetails") or "HTTP error"
                            return I, G(details)
                        response_data = data.get("responseData", {})
                        if isinstance(response_data, dict):
                            translated = response_data.get("translatedText", B)
                            if isinstance(translated, str) and translated:
                                return translated, B
                    return I, "empty response"
                except E as exc:
                    return I, G(exc)

            def _translate_label_deepl(text, lang_code, api_key, api_url):
                if not text or not lang_code or not api_key:
                    return I, B
                code = G(lang_code).lower()
                target = {"ua": "UK", "en": "EN", "pl": "PL"}.get(
                    code, code.upper()
                )
                endpoint = G(api_url or B).strip()
                if not endpoint:
                    if api_key.strip().endswith(":fx"):
                        endpoint = "https://api-free.deepl.com/v2/translate"
                    else:
                        endpoint = "https://api.deepl.com/v2/translate"
                try:
                    payload = BP.urlencode(
                        {"auth_key": api_key, "text": text, "target_lang": target}
                    ).encode(k)
                    request = BN.Request(
                        endpoint,
                        data=payload,
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                    with BN.urlopen(
                        request, timeout=5, context=SSL_CONTEXT
                    ) as response:
                        body = response.read().decode(k)
                    data = localization.Ar.loads(body)
                    if isinstance(data, dict):
                        translations = data.get("translations")
                        if isinstance(translations, list) and translations:
                            value = translations[0].get("text", B)
                            if isinstance(value, str) and value:
                                return value, B
                        if "message" in data:
                            return I, G(data.get("message") or "API error")
                except E as exc:
                    return I, G(exc)
                return I, "empty response"

            def _open_translation_dialog():
                label = name_var.get().strip()
                if not label:
                    O.showwarning(
                        WARNING_LABEL, FIELD_NAME_REQUIRED_MSG, parent=editor
                    )
                    return
                lang_files = _discover_localization_files()
                current_lang = LANG_PREF
                if (
                    isinstance(current_lang, str)
                    and current_lang
                    and current_lang != "auto"
                ):
                    lang_files = {
                        code: path
                        for code, path in lang_files.items()
                        if code != current_lang
                    }
                if not lang_files:
                    O.showwarning(
                        WARNING_LABEL, FIELD_TRANSLATE_NO_FILES_MSG, parent=editor
                    )
                    return
                provider_label = translation_provider_var.get()
                provider_value = translation_provider_map.get(
                    provider_label, TRANSLATION_PROVIDER_DEFAULT
                )
                source_lang = _pick_source_lang(label)
                api_key = translation_api_key_var.get().strip()
                api_url = translation_api_url_var.get().strip()
                if provider_value == TRANSLATION_PROVIDER_DEEPL and not api_key:
                    O.showwarning(
                        WARNING_LABEL,
                        FIELD_TRANSLATE_MISSING_API_KEY_MSG,
                        parent=editor,
                    )
                key = f"slot_label_{label.lower()}"
                dialog = F.Toplevel(editor)
                dialog.title(FIELD_TRANSLATE_TITLE)
                try:
                    dialog.transient(editor)
                except E:
                    pass
                dialog.grab_set()
                row = 0
                vars_by_lang = {}
                error_placeholders = {}
                translate_attempted = Ay
                translate_failed = Ay
                translate_success = Ay
                last_error = B
                for code, path in sorted(lang_files.items()):
                    display = f"{code} ({localization.settings.A.path.basename(path)})"
                    existing = _read_translation_value(path, key)
                    suggestion = existing
                    if not suggestion:
                        translated = I
                        error_msg = B
                        if provider_value == TRANSLATION_PROVIDER_DEEPL:
                            if api_key:
                                translate_attempted = J
                                translated, error_msg = _translate_label_deepl(
                                    label, code, api_key, api_url
                                )
                            else:
                                error_msg = "missing api key"
                        elif provider_value == TRANSLATION_PROVIDER_MYMEMORY:
                            translate_attempted = J
                            translated, error_msg = _translate_label_mymemory(
                                label, code, source_lang
                            )
                        else:
                            translate_attempted = J
                            translated, error_msg = _translate_label_google(label, code)
                        if translated is I:
                            if translate_attempted:
                                translate_failed = J
                                if error_msg and not last_error:
                                    last_error = error_msg
                            if not error_msg:
                                error_msg = "unknown error"
                            suggestion = FIELD_TRANSLATE_ENTRY_ERROR_MSG.format(
                                provider=provider_label, error=error_msg
                            )
                            error_placeholders[code] = suggestion
                        else:
                            translate_success = J
                            suggestion = translated
                    var = F.StringVar(value=suggestion)
                    vars_by_lang[code] = var
                    C.Label(dialog, text=display).grid(
                        row=row, column=0, padx=5, pady=3, sticky=R
                    )
                    entry = C.Entry(dialog, textvariable=var, width=40)
                    entry.grid(row=row, column=1, padx=5, pady=3, sticky="w")
                    row += 1

                def _save_translations():
                    for code, path in lang_files.items():
                        value = vars_by_lang[code].get().strip()
                        if not value:
                            continue
                        placeholder = error_placeholders.get(code)
                        if placeholder and value == placeholder:
                            continue
                        try:
                            with x(path, "r", encoding=k) as handle:
                                data = localization.Ar.load(handle)
                            if not isinstance(data, dict):
                                data = {}
                            data[key] = value
                            with x(path, T, encoding=k) as handle:
                                localization.Ar.dump(
                                    data, handle, indent=2, ensure_ascii=False
                                )
                                handle.write("\n")
                        except E as exc:
                            O.showerror(
                                localization.AK,
                                FIELD_TRANSLATE_SAVE_FAILED_MSG.format(error=exc),
                                parent=dialog,
                            )
                            return
                    dialog.destroy()

                button_row = C.Frame(dialog)
                button_row.grid(row=row, column=0, columnspan=2, pady=5)
                C.Button(
                    button_row, text=SAVE_LABEL, command=_save_translations
                ).grid(row=0, column=0, padx=5)
                C.Button(
                    button_row, text=CANCEL_LABEL, command=dialog.destroy
                ).grid(row=0, column=1, padx=5)
                dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
                if translate_attempted and translate_failed and not translate_success:
                    if last_error:
                        O.showwarning(
                            WARNING_LABEL,
                            FIELD_TRANSLATE_FETCH_FAILED_DETAIL_MSG.format(
                                provider=provider_label, error=last_error
                            ),
                            parent=dialog,
                        )
                    else:
                        O.showwarning(
                            WARNING_LABEL,
                            FIELD_TRANSLATE_FETCH_FAILED_MSG,
                            parent=dialog,
                        )

            translate_row = C.Frame(editor)
            translate_row.grid(row=2, column=0, columnspan=2, pady=(0, 5))
            C.Button(
                translate_row,
                text=FIELD_TRANSLATE_LABEL,
                command=_open_translation_dialog,
            ).grid(row=0, column=0, padx=5)
            button_row = C.Frame(editor)
            button_row.grid(row=3, column=0, columnspan=2, pady=5)

            C.Button(button_row, text=SAVE_LABEL, command=_save_field).grid(
                row=0, column=0, padx=5
            )
            C.Button(button_row, text=FIELD_DELETE_LABEL, command=_delete_field).grid(
                row=0, column=1, padx=5
            )
            C.Button(button_row, text=CANCEL_LABEL, command=_close_editor).grid(
                row=0, column=2, padx=5
            )
            editor.protocol("WM_DELETE_WINDOW", _close_editor)

        _refresh_fields_grid()

        def Ad(state):
            entry_state = X if state == X else V
            AD_.configure(state=entry_state)
            AE_.configure(state=entry_state)
            AF_.configure(state=entry_state)
            AG_.configure(state=entry_state)
            AH_.configure(state=entry_state)
            ftp_update_cb.configure(state=entry_state)

        def Ae(state_text, editor=Al):
            nonlocal sql_edit_state, fields_state
            B_ = state_text
            C_ = X if B_ == X else V
            entry_state = C_
            if D.get(p, K).lower() == K:
                AU.configure(state=entry_state)
                AW.configure(state=entry_state)
                AY.configure(state=entry_state)
                Aa.configure(state=entry_state)
            else:
                ensure_package.configure(state=entry_state)
                AN.configure(state=entry_state)
                AQ.configure(state=entry_state)
                AS.configure(state=entry_state)
            if B_ == X:
                combo_state = i_ if editor else X
            else:
                combo_state = V
            A1.configure(state=combo_state)
            h_.configure(state=C_)
            Ac.configure(state=C_)
            mapping_state = X if B_ == X else V
            sql_edit_state = mapping_state
            for widget in sql_mapping_controls:
                try:
                    widget.configure(state=mapping_state)
                except E:
                    pass
            fields_state = mapping_state
            for widget in fields_controls:
                try:
                    widget.configure(state=mapping_state)
                except E:
                    pass

        Ad(i_)
        Ae(i_)

        def LIGHT_GREEN():
            if is_admin():
                Ad(X)
                log_info_loc("settings_ftp_unlocked")
            else:
                O.showwarning(A6_, A5_)

        def NO_DATA_MSG():
            if is_admin():
                Ae(X)
                log_info_loc("settings_sql_unlocked")
            else:
                O.showwarning(A6_, A5_)

        AI_.configure(command=LIGHT_GREEN)
        BC_ = C.Button(S, text=Ag_, command=NO_DATA_MSG)
        BC_.grid(row=5, column=1, sticky=T, padx=5, pady=5)
        fields_admin_btn = C.Button(fields_tab, text=Ag_, command=NO_DATA_MSG)
        fields_admin_btn.grid(row=0, column=1, sticky="e", padx=5, pady=5)
        A4 = C.Frame(a_, style="Settings.TFrame")
        A4.grid(row=1, column=0, pady=5)

        def BD_():
            global LANG_PREF
            old_lang_pref = LANG_PREF
            D[H][v] = s.get().strip()
            try:
                D[H][r] = int(t.get())
            except:
                D[H][r] = 21
            D[H][N] = x_.get().strip()
            D[H][M] = y_.get()
            D[H][m] = g_.get().strip()
            D[ft] = bool(ftp_update_var.get())
            D[P][c] = AK.get().strip()
            D[P][b] = AM.get().strip()
            D[P][N] = AO.get().strip()
            D[P][M] = AR.get()
            D[K][c] = AT.get().strip()
            D[K][b] = AV.get().strip()
            D[K][N] = AX.get().strip()
            D[K][M] = AZ.get()
            D[p] = K if db_type_var.get() == f_ else "mssql"
            D[w] = h_.get(A_, "end").strip()
            D[u] = bool(Ab.get())
            D[SQL_AVAILABLE_COLUMNS_KEY] = list(available_columns)
            updated_slot_defs, slot_issues = normalize_slot_definitions(slot_defs)
            updated_sql_map, map_issues = normalize_sql_column_map(
                sql_column_map, updated_slot_defs
            )
            slot_defs[:] = updated_slot_defs
            sql_column_map.clear()
            sql_column_map.update(updated_sql_map)
            D[SLOT_DEFS_KEY] = updated_slot_defs
            D[SQL_COLUMN_MAP_KEY] = updated_sql_map
            for issue in slot_issues + map_issues:
                A._log_slot_issue(issue)
            old_slots = {s["prefix"]: s["label"] for s in original_slot_defs}
            new_slots = {s["prefix"]: s["label"] for s in updated_slot_defs}
            for prefix, label in old_slots.items():
                if prefix not in new_slots:
                    log_info_loc(
                        "slot_field_removed", prefix=prefix, label=label
                    )
            for prefix, label in new_slots.items():
                if prefix not in old_slots:
                    log_info_loc(
                        "slot_field_added", prefix=prefix, label=label
                    )
                else:
                    old_label = old_slots[prefix]
                    if old_label != label:
                        log_info_loc(
                            "slot_field_renamed",
                            prefix=prefix,
                            old=old_label,
                            new=label,
                        )
            for prefix, new_val in updated_sql_map.items():
                old_val = original_sql_map.get(prefix, B)
                if G(old_val or B).strip() != G(new_val or B).strip():
                    log_info_loc(
                        "sql_column_map_changed",
                        prefix=prefix,
                        old=(old_val or "-"),
                        new=(new_val or "-"),
                    )
            if original_sql_settings["db_type"] != D[p]:
                log_info_loc("settings_sql_changed", field=DB_TYPE_LABEL)
            if original_sql_settings["sql_query"] != D[w]:
                log_info_loc("settings_sql_changed", field=SQL_QUERY_LABEL)
            if original_sql_settings["enable_sql_update"] != D[u]:
                log_info_loc("settings_sql_changed", field=SQL_UPDATE_LABEL)
            if original_sql_settings["mssql"].get(c) != D[P][c]:
                log_info_loc(
                    "settings_sql_changed",
                    field=f"{MSSQL_SERVER_LABEL} {SERVER_LABEL}",
                )
            if original_sql_settings["mssql"].get(b) != D[P][b]:
                log_info_loc(
                    "settings_sql_changed",
                    field=f"{MSSQL_SERVER_LABEL} {DATABASE_LABEL}",
                )
            if original_sql_settings["mssql"].get(N) != D[P][N]:
                log_info_loc(
                    "settings_sql_changed",
                    field=f"{MSSQL_SERVER_LABEL} {USER_LABEL}",
                )
            if original_sql_settings["mssql"].get(M) != D[P][M]:
                log_info_loc(
                    "settings_sql_changed",
                    field=f"{MSSQL_SERVER_LABEL} {PASSWORD_LABEL}",
                )
            if original_sql_settings["mysql"].get(c) != D[K][c]:
                log_info_loc(
                    "settings_sql_changed",
                    field=f"{MYSQL_LABEL} {SERVER_LABEL}",
                )
            if original_sql_settings["mysql"].get(b) != D[K][b]:
                log_info_loc(
                    "settings_sql_changed",
                    field=f"{MYSQL_LABEL} {DATABASE_LABEL}",
                )
            if original_sql_settings["mysql"].get(N) != D[K][N]:
                log_info_loc(
                    "settings_sql_changed",
                    field=f"{MYSQL_LABEL} {USER_LABEL}",
                )
            if original_sql_settings["mysql"].get(M) != D[K][M]:
                log_info_loc(
                    "settings_sql_changed",
                    field=f"{MYSQL_LABEL} {PASSWORD_LABEL}",
                )
            if D.get(u, J):
                available_lower = {col.lower() for col in available_columns}
                for slot in updated_slot_defs:
                    prefix = slot["prefix"]
                    column = G(updated_sql_map.get(prefix, B) or B).strip()
                    if not column:
                        log_error_loc(
                            "sql_column_unassigned",
                            prefix=prefix,
                            label=slot["label"],
                        )
                    elif available_columns and column.lower() not in available_lower:
                        log_error_loc(
                            "sql_column_not_found",
                            prefix=prefix,
                            column=column,
                        )
            new_lang_pref = lang_var.get().strip()
            if not new_lang_pref:
                new_lang_pref = LANGUAGE_PREF_DEFAULT
            save_language_pref(new_lang_pref)
            language_changed = (
                G(new_lang_pref).strip().lower()
                != G(old_lang_pref or LANGUAGE_PREF_DEFAULT).strip().lower()
            )
            LANG_PREF = new_lang_pref
            localization.LANG_PREF = LANG_PREF
            D[TRANSLATION_SETTINGS_KEY] = {
                TRANSLATION_PROVIDER_KEY: translation_provider_map.get(
                    translation_provider_var.get(), TRANSLATION_PROVIDER_DEFAULT
                ),
                TRANSLATION_API_KEY: translation_api_key_var.get().strip(),
                TRANSLATION_API_URL: translation_api_url_var.get().strip(),
            }
            app_secret_changed = Ay
            restart_needed = Ay
            if system_unlocked:
                new_app_secret = app_secret_var.get().strip()
                if not new_app_secret:
                    O.showwarning(WARNING_LABEL, APP_SECRET_REQUIRED_MSG)
                    return
                new_base_dir = base_dir_var.get().strip()
                if new_base_dir:
                    ok, error = settings._ensure_directory_access(new_base_dir)
                    if not ok:
                        details = f"\n\n{error}" if error else B
                        O.showerror(
                            SETTINGS_LABEL,
                            f"{BASE_DIR_INVALID_SELECTION_MSG}{details}",
                        )
                        return
                local_payload = _load_local_settings_data()
                local_payload["base_dir_override"] = new_base_dir
                local_payload[APP_SECRET_KEY] = new_app_secret
                try:
                    _save_local_settings_data(local_payload)
                except E as exc:
                    O.showerror(
                        AK,
                        LOCAL_SETTINGS_SAVE_FAILED_MSG.format(error=exc),
                    )
                    return
                if new_app_secret != app_secret_value:
                    app_secret_changed = J
                    common.APP_SECRET = new_app_secret
                    common.BASE_DIR_SETTINGS_TEMPLATE[APP_SECRET_KEY] = new_app_secret
                    encryption.APP_SECRET = new_app_secret
                if new_base_dir != base_dir_value:
                    restart_needed = J
            preserve_secrets = {}
            ftp_preserve = set()
            if original_ftp_settings.get(N) == D[H][N]:
                ftp_preserve.add(N)
            if original_ftp_settings.get(M) == D[H][M]:
                ftp_preserve.add(M)
            if ftp_preserve:
                preserve_secrets[H] = ftp_preserve
            mssql_preserve = set()
            if original_sql_settings["mssql"].get(N) == D[P][N]:
                mssql_preserve.add(N)
            if original_sql_settings["mssql"].get(M) == D[P][M]:
                mssql_preserve.add(M)
            if mssql_preserve:
                preserve_secrets[P] = mssql_preserve
            mysql_preserve = set()
            if original_sql_settings["mysql"].get(N) == D[K][N]:
                mysql_preserve.add(N)
            if original_sql_settings["mysql"].get(M) == D[K][M]:
                mysql_preserve.add(M)
            if mysql_preserve:
                preserve_secrets[K] = mysql_preserve
            translation_preserve = set()
            if (
                original_translation_settings.get(TRANSLATION_API_KEY)
                == D[TRANSLATION_SETTINGS_KEY].get(TRANSLATION_API_KEY, B)
            ):
                translation_preserve.add(TRANSLATION_API_KEY)
            if translation_preserve:
                preserve_secrets[TRANSLATION_SETTINGS_KEY] = translation_preserve
            save_config(D, preserve_secrets=preserve_secrets)
            if app_secret_changed and not restart_needed:
                updated_config = config.load_config()
                config.CONFIG.clear()
                config.CONFIG.update(updated_config)
            if restart_needed and not language_changed:
                O.showinfo(SETTINGS_LABEL, APP_SETTINGS_RESTART_MSG)
            A.sql_column_map = updated_sql_map
            before_prefixes = [slot["prefix"] for slot in current_slot_defs]
            after_prefixes = [slot["prefix"] for slot in updated_slot_defs]
            if before_prefixes == after_prefixes:
                A.slot_definitions = updated_slot_defs
                A._slot_index_by_prefix = {
                    slot["prefix"]: idx
                    for idx, slot in A0(updated_slot_defs)
                }
                A._update_slot_titles(updated_slot_defs)
            else:
                if not A.is_processing and O.askyesno(
                    WARNING_LABEL, SLOT_DEFS_REBUILD_PROMPT
                ):
                    A.sql_column_map = updated_sql_map
                    A._apply_slot_definitions(updated_slot_defs)
                else:
                    log_info_loc("slot_defs_apply_restart")
            log_info_loc("settings_saved")
            Af()
            if language_changed:
                if A.is_processing:
                    O.showinfo(SETTINGS_LABEL, RESTART_TO_APPLY_LABEL)
                else:
                    try:
                        A.after(150, A._restart_application)
                    except E:
                        A._restart_application()

        C.Button(A4, text=SAVE_LABEL, command=BD_).grid(row=0, column=0, padx=5)

        def Af():
            A.opt_resize.trace_remove(Y_, resize_trace)
            A.opt_compress.trace_remove(Y_, compress_trace)
            A.opt_maxsize.trace_remove(Y_, maxsize_trace)
            A.opt_convert_tif.trace_remove(Y_, convert_tif_trace)
            if getattr(A, "_settings_window", I) is a_:
                A._settings_window = I
            try:
                a_.destroy()
            finally:
                A._restore_focus()

        C.Button(A4, text=CANCEL_LABEL, command=Af).grid(row=0, column=1, padx=5)
        a_.protocol("WM_DELETE_WINDOW", Af)
        Z.select(0)
        a_._close_settings = Af
        a_._close_window = Af
        return a_

    def _restart_application(B):
        args = I
        env = I
        try:
            meipass = getattr(sys, "_MEIPASS", B)
        except E:
            meipass = B
        if getattr(sys, "frozen", h) and meipass:
            try:
                base_name = A.path.basename(meipass)
            except E:
                base_name = B
            if base_name.startswith("_MEI"):
                try:
                    O.showinfo(SETTINGS_LABEL, RESTART_TO_APPLY_LABEL)
                except E:
                    pass
                return
        try:
            if getattr(sys, "frozen", h):
                args = [sys.executable] + sys.argv[1:]
                try:
                    env = A.environ.copy()
                    for key in (
                        "_MEIPASS2",
                        "PYINSTALLER_PARENT_PID",
                        "PYINSTALLER_ARCHIVE_FILE",
                        "TCL_LIBRARY",
                        "TK_LIBRARY",
                        "PYTHONHOME",
                        "PYTHONPATH",
                    ):
                        env.pop(key, I)
                except E:
                    env = I
            else:
                args = [sys.executable] + sys.argv
        except E:
            args = I
        if not args:
            return
        try:
            BH.Popen(args, env=env)
        except E:
            return
        try:
            B.destroy()
        except E:
            pass

    def _change_language(A):
        B = BI.askstring(SETTINGS_LABEL, LANGUAGE_PROMPT)
        if B:
            try:
                save_language_pref(B.lower())
            except E:
                O.showerror(AK, Ac)
            else:
                O.showinfo(SETTINGS_LABEL, RESTART_TO_APPLY_LABEL)

    def _style_combobox_list(L, combobox):
        A_ = combobox
        try:
            G_ = A_.tk.call("ttk::combobox::PopdownWindow", A_._w)
            H_ = G_ + ".f.l"
            B_ = A_.nametowidget(H_)
        except E:
            return
        D_ = Aj(A_, "existing_count", I)
        if D_ is I:
            return
        F_ = A_.cget(S)
        J_ = Q(F_) if F_ else 0
        K_ = B_.cget("background")
        for C_ in Ax(J_):
            if C_ < D_:
                B_.itemconfig(C_, background=LIGHT_GREEN)
            else:
                B_.itemconfig(C_, background=K_)

    def _mark_slot(D, idx, color):
        B_ = color
        E_ = {AR: "#0000ff", A4: "#00ff00", "gray": "#808080", Ab: "#ff0000"}
        C_ = E_.get(B_, "#000000")
        slot = D.slots[idx]
        slot[B0] = B_
        A_ = slot.get(AS)
        if A_:
            if B_ is I:
                A_.configure(
                    highlightthickness=0, highlightbackground=A8, highlightcolor=A8
                )
            else:
                A_.configure(
                    highlightbackground=C_, highlightcolor=C_, highlightthickness=2
                )

    def _add_tooltip(C, widget, text):
        B_ = widget
        A_ = I

        def D_(event):
            B__ = event
            nonlocal A_
            A_ = F.Toplevel(C)
            A_.wm_overrideredirect(J)
            A_.wm_geometry(f"+{B__.x_root+10}+{B__.y_root+10}")
            D__ = F.Label(
                A_,
                text=text,
                background="yellow",
                relief="solid",
                borderwidth=1,
                padx=5,
                pady=3,
            )
            D__.pack()

        def E__(event):
            nonlocal A_
            if A_:
                A_.destroy()
                A_ = I

        B_.bind("<Enter>", D_)
        B_.bind("<Leave>", E__)

    def _on_drag_init(A, event, idx):
        if A.is_processing:
            return
        B_ = A.slots[idx][f]
        if not B_:
            return
        A.dragging_idx = idx
        return "copy", BJ, (B_,)

    def _on_drag_end(A, event):
        A.dragging_idx = I

    def _ui_log(A, msg=AQ, clear=Ay):
        try:
            if clear:
                A.ui_log.configure(state=Az)
                A.ui_log.delete(A_, F.END)
                A.ui_log.configure(state=Ak)
                return
            if not msg:
                return
            A.ui_log.configure(state=Az)
            A.ui_log.insert(F.END, f"{msg}\n")
            A.ui_log.see(F.END)
            A.ui_log.configure(state=Ak)
        except E:
            pass
