"""Main Tkinter application class."""

import ast
import copy
from collections import OrderedDict, deque
import queue
import re
import traceback
import tokenize

from .common import *  # noqa: F401,F403
from .excel_utils import (
    COLOR1_HEADER,
    COLOR2_HEADER,
    COLOR3_HEADER,
    EAN_HEADER,
    ENTRY_RECORDS_KEY,
    EXTRA_HEADER,
    MODEL_HEADER,
    NAME_HEADER,
    PRODUCT_ID_HEADER,
    TYPE_HEADER,
    add_to_list,
    label_category,
    prepare_excel_lists,
    remove_from_list,
    save_ean_entry,
)
from .logging_utils import log_error, log_error_loc, log_info, log_info_loc, set_app
from .system_utils import get_file_lock_user, is_admin
from .database import connect_db
from .file_index import LocalFileIndex
from .config import save_config
from . import config, localization, settings, common, encryption
from .settings import BW, EXCEL_SHEETS, AN, l
from .product_state import (
    ProductIdentity,
    ProductState,
    merge_lookup_state as merge_product_lookup_state,
)
from .slot_utils import normalize_slot_definitions, normalize_sql_column_map, next_slot_prefix
from .services.excel_service import merge_saved_entry_into_lists
from .services.file_service import (
    build_expected_remote_filename as svc_build_expected_remote_filename,
    build_slot_target_filename as svc_build_slot_target_filename,
    infer_existing_remote_filename as svc_infer_existing_remote_filename,
    seed_metadata_migration as svc_seed_metadata_migration,
)
from .services.ftp_service import (
    download_remote_slots as svc_download_remote_slots,
    list_remote_filenames as svc_list_remote_filenames,
)
from .services.sql_service import (
    extract_presence_context as svc_extract_presence_context,
    query_presence_details as svc_query_presence_details,
    query_presence_map as svc_query_presence_map,
    should_check_presence as svc_should_check_presence,
)
from .workflow_utils import (
    build_product_directory,
    build_remote_slot_filename,
    build_slot_filename,
    build_sql_presence_query,
    has_presence_value,
    normalize_color_slots,
    normalize_extra_segment,
    parse_slot_filename,
    select_remote_files_for_ean,
    unique_columns,
)

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
SLOT_GRID_COLUMNS = 5
SLOT_PREVIEW_SIZE = (240, 176)
THUMBNAIL_RESULT_BATCH = 6
THUMBNAIL_POLL_MS = 28
PERF_MONITOR_MS = 16
PERF_SAMPLE_WINDOW = 90
FORM_TRACKED_FIELDS = (
    "name",
    "type",
    "model",
    "color1",
    "color2",
    "color3",
    "extra",
    "ean",
)
FORM_TRACKED_VAR_ATTRS = {
    "name": "var_name",
    "type": "var_type",
    "model": "var_model",
    "color1": "var_color1",
    "color2": "var_color2",
    "color3": "var_color3",
    "extra": "var_extra",
    "ean": "var_ean",
}

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
        B.geometry("1360x900")
        B.minsize(1180, 780)
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
        B.entries = {}
        B.entry_records = []
        B.entries_by_id = {}
        B._reload_entry_cache(D_)
        B.lists = D_
        for key in (n, t, s, Y, d):
            if not isinstance(B.lists.get(key), list):
                B.lists[key] = []
        if not A.path.isdir(l):
            A.makedirs(l, exist_ok=J)
        B._local_file_index_enabled = bool(D.get(LOCAL_FILE_INDEX_KEY, J))
        B._file_index_status_var = F.StringVar()
        B._file_index = LocalFileIndex(
            l,
            A.path.join(settings.AC, "file_index.json"),
            status_callback=B._on_file_index_status_change,
        )
        if B._local_file_index_enabled and B._file_index.load_cache():
            B._refresh_name_values_from_index()
        elif B._local_file_index_enabled:
            B._file_index_status_var.set(
                LANG.get(
                    "file_index_status_cold_start",
                    "Indeks plików: brak cache, pierwszy skan ruszy w tle po starcie.",
                )
            )
        else:
            B._file_index_status_var.set(
                LANG.get(
                    "file_index_status_disabled",
                    "Indeks plików: wyłączony w ustawieniach aplikacji.",
                )
            )
        B.var_name = F.StringVar()
        B.var_type = F.StringVar()
        B.var_model = F.StringVar()
        B.var_color1 = F.StringVar()
        B.var_color2 = F.StringVar()
        B.var_color3 = F.StringVar()
        B.var_extra = F.StringVar()
        B.var_ean = F.StringVar()
        B.var_product_id = F.StringVar()
        B._product_state = ProductState()
        B._sync_state_refs()
        B._thumb_tokens = {}
        B._thumb_cache = OrderedDict()
        B._thumb_cache_limit = 192
        B._thumb_cache_lock = threading.Lock()
        B._thumb_request_queue = queue.Queue()
        B._thumb_result_queue = queue.Queue()
        B._thumb_request_seq = 0
        B._thumb_poll_job = I
        B._load_existing_after_id = I
        B._load_existing_request_id = 0
        B._last_lookup_signature = I
        B._dashboard_refresh_job = I
        B._slot_grid_columns = 0
        B._slots_refresh_job = I
        B._perf_monitor_job = I
        B._perf_samples = deque(maxlen=PERF_SAMPLE_WINDOW)
        B._perf_last_tick = Ag.perf_counter()
        B._perf_status_var = F.StringVar()
        B._perf_detail_var = F.StringVar()
        B._busy_status_var = F.StringVar(
            value=LANG.get("busy_state_idle", "Stan: gotowe")
        )
        B._busy_counter = 0
        B._current_busy_label = ""
        B._existing_lookup_lock = threading.Lock()
        B._existing_lookup_running = h
        B._existing_lookup_busy = h
        B._existing_lookup_active_request_id = I
        B._retry_existing_lookup = h
        B._last_lookup_duration_ms = 0
        B._commit_snapshot = {}
        B._record_loaded = h
        B._last_ean_conflict_notice = I
        B._field_change_refresh_job = I
        B._loaded_field_values = {}
        B._form_field_meta = {}
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
        B.is_processing = h
        B._code_check_running = h
        B._code_check_last_report = ""
        B._ui_check_running = h
        B._ui_check_last_report = ""
        B._perf_check_running = h
        B._perf_check_last_report = ""
        B.logged_counts = h
        B.suppress_next_lookup = h
        B.slot_definitions = []
        B.sql_column_map = {}
        B._hero_status_var = F.StringVar()
        B._hero_context_var = F.StringVar()
        B._hero_storage_var = F.StringVar()
        B._hero_slots_var = F.StringVar()
        B._hero_remote_var = F.StringVar()
        B._slot_placeholder_text = LANG.get(
            "slot_drop_hint",
            "Przeciągnij plik tutaj\nlub kliknij Wybierz",
        )
        B._slot_select_label = LANG.get("slot_select_action", "Wybierz")
        B._slot_remove_label = LANG.get("slot_remove_action", "Usun")
        B.bind_class("SlotScroll", "<MouseWheel>", B._on_slots_mousewheel)
        B.bind_class("SlotScroll", "<Button-4>", B._on_slots_scroll_up)
        B.bind_class("SlotScroll", "<Button-5>", B._on_slots_scroll_down)
        B._thumb_worker = threading.Thread(
            target=B._thumbnail_worker_loop,
            name="ThumbnailLoader",
            daemon=J,
        )
        B._thumb_worker.start()
        for var in (
            B.var_name,
            B.var_type,
            B.var_model,
            B.var_color1,
            B.var_color2,
            B.var_color3,
            B.var_extra,
            B.var_ean,
        ):
            var.trace_add("write", B._queue_dashboard_refresh)
        for field_key in FORM_TRACKED_FIELDS:
            tracked_var = getattr(B, FORM_TRACKED_VAR_ATTRS[field_key], I)
            if tracked_var is not I:
                tracked_var.trace_add("write", B._queue_form_change_refresh)
        B._load_slot_config()
        B._build_form()
        B._build_slots()
        B._slot_index_by_prefix = {
            slot["prefix"]: idx for idx, slot in A0(B.slot_definitions)
        }
        B._refresh_name_values_from_index()
        B._refresh_commit_snapshot()
        B._update_dashboard_summary()
        B._thumb_poll_job = B.after(THUMBNAIL_POLL_MS, B._poll_thumbnail_results)
        B._perf_monitor_job = B.after(PERF_MONITOR_MS, B._perf_monitor_tick)
        B.protocol("WM_DELETE_WINDOW", B.destroy)
        B.after(150, B._start_file_index_refresh)
        set_app(B)
        B._install_exception_handlers()

    def report_callback_exception(A, exc, val, tb):
        A._handle_exception(exc, val, tb, context="Tk callback")

    def destroy(A):
        for job_attr in (
            "_thumb_poll_job",
            "_perf_monitor_job",
            "_load_existing_after_id",
            "_dashboard_refresh_job",
            "_field_change_refresh_job",
            "_slots_refresh_job",
        ):
            job_id = getattr(A, job_attr, I)
            if job_id is I:
                continue
            try:
                A.after_cancel(job_id)
            except E:
                pass
            setattr(A, job_attr, I)
        try:
            A._thumb_request_queue.put_nowait(I)
        except E:
            pass
        return super().destroy()

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
            "bg": "#eef2ef",
            "card": "#fbfaf7",
            "card_alt": "#f3f1ea",
            "hero": "#163640",
            "hero_text": "#f5fbfa",
            "text": "#18242c",
            "slot_bg": "#edf2ef",
            "slot_border": "#c7d2cf",
            "muted": "#61717b",
            "accent": "#2c7a63",
            "accent_dark": "#1f5d4b",
            "accent_soft": "#d8ebe4",
            "progress_trough": "#dbe5e0",
            "border": "#d6ddda",
            "danger": "#bc5a5d",
            "warning": "#b58336",
            "log_bg": "#10242d",
            "log_fg": "#d6ece9",
        }
        A.configure(bg=A._ui_colors["bg"])
        A.option_add("*Font", "{Segoe UI} 10")
        A.option_add("*Listbox.font", "{Segoe UI} 10")
        A.option_add("*Text.Font", "Consolas 9")
        A.style.configure("App.TFrame", background=A._ui_colors["bg"])
        A.style.configure("Card.TFrame", background=A._ui_colors["card"], relief="flat")
        A.style.configure(
            "ChangedField.TFrame",
            background="#fff1d9",
            relief="flat",
        )
        A.style.configure("Hero.TFrame", background=A._ui_colors["hero"], relief="flat")
        A.style.configure(
            "SidebarCard.TFrame",
            background=A._ui_colors["card_alt"],
            relief="flat",
        )
        A.style.configure("Settings.TFrame", background=A._ui_colors["card"])
        A.style.configure(
            "HeroTitle.TLabel",
            background=A._ui_colors["hero"],
            foreground=A._ui_colors["hero_text"],
            font=("Segoe UI Semibold", 16),
        )
        A.style.configure(
            "HeroSubtitle.TLabel",
            background=A._ui_colors["hero"],
            foreground="#d1e4e0",
            font=("Segoe UI", 9),
        )
        A.style.configure(
            "HeroMeta.TLabel",
            background=A._ui_colors["hero"],
            foreground=A._ui_colors["hero_text"],
            font=("Segoe UI Semibold", 9),
        )
        A.style.configure(
            "HeroContext.TLabel",
            background=A._ui_colors["hero"],
            foreground="#dbeae7",
            font=("Segoe UI", 9),
        )
        A.style.configure(
            "HeroPath.TLabel",
            background=A._ui_colors["hero"],
            foreground="#b6cbc6",
            font=("Consolas", 8),
        )
        A.style.configure(
            "SectionTitle.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["text"],
            font=("Segoe UI Semibold", 12),
        )
        A.style.configure(
            "SectionHint.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["muted"],
            font=("Segoe UI", 9),
        )
        A.style.configure(
            "Settings.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["text"],
            font=("Segoe UI", 9),
        )
        A.style.configure(
            "SettingsHeader.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["text"],
            font=("Segoe UI Semibold", 10),
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
            tabmargins=(0, 0, 0, 0),
        )
        A.style.configure(
            "Settings.TNotebook.Tab",
            background=A._ui_colors["card_alt"],
            foreground=A._ui_colors["muted"],
            padding=(16, 8),
            font=("Segoe UI Semibold", 9),
        )
        A.style.map(
            "Settings.TNotebook.Tab",
            background=[
                ("selected", A._ui_colors["card"]),
                ("active", A._ui_colors["accent_soft"]),
            ],
            foreground=[
                ("selected", A._ui_colors["text"]),
                ("active", A._ui_colors["text"]),
            ],
        )
        A.style.configure(
            "Form.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["muted"],
            font=("Segoe UI Semibold", 10),
        )
        A.style.configure(
            "ChangedForm.TLabel",
            background="#fff1d9",
            foreground="#8f641f",
            font=("Segoe UI Semibold", 10),
        )
        A.style.configure(
            "FormSection.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["text"],
            font=("Segoe UI Semibold", 12),
        )
        A.style.configure(
            "FormHint.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["muted"],
            font=("Segoe UI", 9),
        )
        A.style.configure(
            "SlotTitle.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["text"],
            font=("Segoe UI Semibold", 11),
        )
        A.style.configure(
            "SlotStatus.TLabel",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["muted"],
            font=("Segoe UI", 9),
        )
        A.style.configure(
            "SlotFooter.TFrame",
            background=A._ui_colors["card"],
        )
        A.style.configure(
            "TButton",
            padding=(12, 7),
            background=A._ui_colors["card_alt"],
            foreground=A._ui_colors["text"],
            borderwidth=0,
            font=("Segoe UI Semibold", 9),
        )
        A.style.map(
            "TButton",
            background=[
                ("pressed", "#d9e3df"),
                ("active", "#e4ece9"),
                ("disabled", "#ebe9e5"),
            ],
            foreground=[("disabled", "#9da8a5")],
        )
        A.style.configure(
            "Accent.TButton",
            background=A._ui_colors["accent"],
            foreground=A._ui_colors["hero_text"],
            borderwidth=0,
        )
        A.style.map(
            "Accent.TButton",
            background=[
                ("pressed", A._ui_colors["accent_dark"]),
                ("active", A._ui_colors["accent_dark"]),
                ("disabled", "#93b6aa"),
            ],
            foreground=[("disabled", "#eef7f4")],
        )
        A.style.configure(
            "Ghost.TButton",
            background=A._ui_colors["hero"],
            foreground=A._ui_colors["hero_text"],
            borderwidth=0,
        )
        A.style.map(
            "Ghost.TButton",
            background=[
                ("pressed", "#214754"),
                ("active", "#214754"),
                ("disabled", "#526871"),
            ]
        )
        A.style.configure(
            "Outline.TButton",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["text"],
            borderwidth=1,
            relief="solid",
        )
        A.style.map(
            "Outline.TButton",
            background=[("pressed", "#eef3f0"), ("active", "#f5f8f6")],
        )
        A.style.configure(
            "MiniOutline.TButton",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["muted"],
            borderwidth=1,
            relief="solid",
            padding=(7, 2),
            font=("Segoe UI Semibold", 8),
        )
        A.style.map(
            "MiniOutline.TButton",
            background=[("pressed", "#eef3f0"), ("active", "#f5f8f6")],
            foreground=[("disabled", "#a9b1ad")],
        )
        A.style.configure(
            "MiniWarn.TButton",
            background="#fff1d9",
            foreground="#8f641f",
            borderwidth=1,
            relief="solid",
            padding=(7, 2),
            font=("Segoe UI Semibold", 8),
        )
        A.style.map(
            "MiniWarn.TButton",
            background=[("pressed", "#ffe9c3"), ("active", "#fff5e4")],
            foreground=[("disabled", "#a9b1ad")],
        )
        A.style.configure(
            "TCombobox",
            padding=(10, 5),
            fieldbackground="#ffffff",
            background="#ffffff",
            bordercolor=A._ui_colors["border"],
            arrowsize=14,
            font=("Segoe UI", 11),
        )
        A.style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#ffffff")],
            selectbackground=[("readonly", "#ffffff")],
            selectforeground=[("readonly", A._ui_colors["text"])],
        )
        A.style.configure(
            "TEntry",
            fieldbackground="#ffffff",
            bordercolor=A._ui_colors["border"],
            foreground=A._ui_colors["text"],
            padding=(10, 6),
            font=("Segoe UI", 11),
        )
        A.style.configure(
            "TSpinbox",
            fieldbackground="#ffffff",
            bordercolor=A._ui_colors["border"],
            foreground=A._ui_colors["text"],
            padding=(6, 4),
            font=("Segoe UI", 10),
        )
        A.style.configure(
            "TCheckbutton",
            background=A._ui_colors["card"],
            foreground=A._ui_colors["text"],
            font=("Segoe UI", 9),
        )
        A.style.configure("Slot.TProgressbar", troughcolor=A._ui_colors["progress_trough"])
        A.style.configure("Slot.TProgressbar", background=A._ui_colors["accent"])
        base_layout = A.style.layout("Horizontal.TProgressbar")
        if base_layout:
            A.style.layout("Horizontal.Slot.TProgressbar", base_layout)

    def _queue_dashboard_refresh(A, *_args):
        if A._dashboard_refresh_job is not I:
            try:
                A.after_cancel(A._dashboard_refresh_job)
            except E:
                pass
        A._dashboard_refresh_job = A.after(50, A._update_dashboard_summary)

    def _update_dashboard_summary(A):
        A._dashboard_refresh_job = I
        A._refresh_all_slot_sql_ui()
        name_value = A.var_name.get().strip()
        type_value = A.var_type.get().strip()
        model_value = A.var_model.get().strip()
        color_values = normalize_color_slots(
            (
                A.var_color1.get(),
                A.var_color2.get(),
                A.var_color3.get(),
            )
        )
        extra_value = normalize_extra_segment(A.var_extra.get(), default=L)
        ean_value = A.var_ean.get().strip() or q
        product_id_value = A.var_product_id.get().strip() or "BRAK-ID"
        ready_slots = Q([slot for slot in Aj(A, "slots", []) if slot.get(f)])
        total_slots = Q(Aj(A, "slots", [])) or Q(A.slot_definitions)
        ftp_count = Q(A.ftp_presence)
        sql_count = 0
        if Aq(A.sql_presence, dict):
            sql_count = Q([value for value in A.sql_presence.values() if value])
        title_parts = [part for part in (name_value, type_value, model_value) if part]
        status_text = LANG.get("dashboard_status_idle", "Gotowe do pracy")
        if A.is_processing:
            status_text = LANG.get("dashboard_status_processing", "Trwa przetwarzanie")
        A._hero_status_var.set(status_text)
        if title_parts:
            A._hero_context_var.set(" / ".join(title_parts))
        else:
            A._hero_context_var.set(
                LANG.get(
                    "dashboard_context_empty",
                    "Uzupelnij dane produktu, aby przygotowac nowy zestaw zdjec.",
                )
            )
        if name_value and type_value and model_value and A.var_color1.get().strip():
            storage_text = build_product_directory(
                l,
                name_value,
                type_value,
                model_value,
                color_values,
                extra_value,
            )
            if Q(storage_text) > 72:
                storage_text = "..." + storage_text[-69:]
            A._hero_storage_var.set(storage_text)
        else:
            A._hero_storage_var.set(
                LANG.get(
                    "dashboard_path_placeholder",
                    "Sciezka produktu pojawi sie po uzupelnieniu wymaganych pol.",
                )
            )
        A._hero_slots_var.set(
            LANG.get(
                "dashboard_slots_value",
                "Sloty {ready}/{total}  |  +{additions}  -{deletions}",
            ).format(
                ready=ready_slots,
                total=total_slots,
                additions=Q(A.pending_additions),
                deletions=Q(A.pending_deletions) + Q(A.pending_ftp_deletions),
            )
        )
        A._hero_remote_var.set(
            LANG.get(
                "dashboard_remote_value",
                "ID {product_id}  |  EAN {ean}  |  FTP {ftp}  |  SQL {sql}  |  Dodatek {extra}",
            ).format(
                product_id=product_id_value,
                ean=ean_value,
                ftp=ftp_count,
                sql=sql_count,
                extra=extra_value,
            )
        )

    def _format_file_index_status(A, status):
        """Build a short UI message describing the local index state."""

        if not getattr(A, "_local_file_index_enabled", J):
            return LANG.get(
                "file_index_status_disabled",
                "Indeks plików: wyłączony w ustawieniach aplikacji.",
            )
        state = G(status.get("state") or "idle").strip().lower()
        error = G(status.get("error") or B).strip()
        name_count = int(status.get("name_count") or 0)
        products_scanned = int(status.get("products_scanned") or 0)
        dirs_scanned = int(status.get("dirs_scanned") or 0)
        cache_loaded = bool(status.get("cache_loaded"))
        if state == "cached":
            return LANG.get(
                "file_index_status_cached",
                "Indeks plików: wczytano cache lokalne ({names} nazw).",
            ).format(names=name_count)
        if state == "refreshing":
            if cache_loaded:
                return LANG.get(
                    "file_index_status_refreshing_cached",
                    "Indeks plików: odświeżanie w tle ({products} katalogów produktów).",
                ).format(products=products_scanned)
            return LANG.get(
                "file_index_status_refreshing",
                "Indeks plików: pierwszy skan w tle ({dirs} katalogów).",
            ).format(dirs=dirs_scanned)
        if state == "ready":
            return LANG.get(
                "file_index_status_ready",
                "Indeks plików: gotowy ({names} nazw, {products} katalogów produktów).",
            ).format(names=name_count, products=products_scanned)
        if state == "error":
            details = f": {error}" if error else B
            return LANG.get(
                "file_index_status_error",
                "Indeks plików: błąd odświeżania{details}",
            ).format(details=details)
        return LANG.get(
            "file_index_status_idle",
            "Indeks plików: oczekiwanie na start.",
        )

    def _on_file_index_status_change(A, status):
        """Synchronize background index progress back into the Tk UI."""

        def _apply():
            if not A.winfo_exists():
                return
            if not getattr(A, "_local_file_index_enabled", J):
                A._file_index_status_var.set(
                    LANG.get(
                        "file_index_status_disabled",
                        "Indeks plików: wyłączony w ustawieniach aplikacji.",
                    )
                )
                return
            A._file_index_status_var.set(A._format_file_index_status(status))
            if G(status.get("state") or B).strip().lower() in {"cached", "ready"}:
                A._refresh_name_values_from_index()

        if threading.current_thread() == threading.main_thread():
            _apply()
            return
        try:
            A.after(0, _apply)
        except E:
            pass

    def _start_file_index_refresh(A):
        """Kick off the background filesystem index if it is not already running."""

        if not getattr(A, "_local_file_index_enabled", J):
            A._file_index_status_var.set(
                LANG.get(
                    "file_index_status_disabled",
                    "Indeks plików: wyłączony w ustawieniach aplikacji.",
                )
            )
            return h
        file_index = Aj(A, "_file_index", I)
        if file_index is I:
            return h
        started = file_index.refresh_async()
        if not started:
            A._on_file_index_status_change(file_index.get_status())
        return started

    def _merge_existing_lookup_values(A, existing_values, fallback_values):
        """Merge disk-backed values ahead of workbook values without duplicates."""

        merged = []
        seen = set()
        for group in (existing_values or [], fallback_values or []):
            for raw_value in group:
                value = G(raw_value or B).strip()
                if not value or value in seen:
                    continue
                merged.append(value)
                seen.add(value)
        existing_count = 0
        for raw_value in existing_values or []:
            value = G(raw_value or B).strip()
            if value:
                existing_count += 1
        return merged, existing_count

    def _merge_live_lookup_values(B, indexed_values, live_values):
        """Merge indexed entries with live disk results without duplicates."""

        merged, _existing_count = B._merge_existing_lookup_values(
            indexed_values,
            live_values,
        )
        return merged

    def _list_child_directories(B, path, uppercase=h):
        """Return direct child directories using ``scandir`` for lower overhead."""

        values = []
        try:
            with A.scandir(path) as entries:
                for entry in entries:
                    if not entry.is_dir():
                        continue
                    value = entry.name.upper() if uppercase else entry.name
                    values.append(value)
        except E:
            return []
        values.sort()
        return values

    def _refresh_name_values_from_index(B):
        """Apply indexed top-level names to the main combobox when available."""

        existing_names = []
        if getattr(B, "_local_file_index_enabled", J):
            file_index = Aj(B, "_file_index", I)
            if file_index is not I:
                existing_names = file_index.get_names()
        live_names = B._list_child_directories(l, uppercase=J)
        existing_names = B._merge_live_lookup_values(existing_names, live_names)
        if not existing_names:
            return
        merged, existing_count = B._merge_existing_lookup_values(
            existing_names,
            B.lists.get(n, []),
        )
        B.lists[n] = merged
        if Aj(B, "combo_name", I) is not I:
            B._refresh_combobox_list(B.combo_name, merged, existing_count=existing_count)

    def _resolve_types_for_name(B, name_value, path):
        """Return type directories from the index or direct disk fallback."""

        indexed = I
        file_index = Aj(B, "_file_index", I)
        if getattr(B, "_local_file_index_enabled", J) and file_index is not I and file_index.has_snapshot():
            indexed = file_index.get_types(name_value)
        path_exists = A.path.isdir(path)
        live_values = B._list_child_directories(path) if path_exists else []
        if indexed is not I:
            return B._merge_live_lookup_values(indexed, live_values), path_exists
        if path_exists:
            return live_values, J
        return [], h

    def _resolve_models_for_type(B, name_value, type_value, path):
        """Return model directories from the index or direct disk fallback."""

        indexed = I
        file_index = Aj(B, "_file_index", I)
        if getattr(B, "_local_file_index_enabled", J) and file_index is not I and file_index.has_snapshot():
            indexed = file_index.get_models(name_value, type_value)
        path_exists = A.path.isdir(path)
        live_values = B._list_child_directories(path) if path_exists else []
        if indexed is not I:
            return B._merge_live_lookup_values(indexed, live_values), path_exists
        if path_exists:
            return live_values, J
        return [], h

    def _resolve_colors_for_model(B, name_value, type_value, model_value, path):
        """Return colour directories from the index or direct disk fallback."""

        indexed = I
        file_index = Aj(B, "_file_index", I)
        if getattr(B, "_local_file_index_enabled", J) and file_index is not I and file_index.has_snapshot():
            indexed = file_index.get_colors(name_value, type_value, model_value)
        path_exists = A.path.isdir(path)
        live_values = B._list_child_directories(path) if path_exists else []
        if indexed is not I:
            return B._merge_live_lookup_values(indexed, live_values), path_exists
        if path_exists:
            return live_values, J
        return [], h

    def _resolve_extras_for_colors(
        B,
        name_value,
        type_value,
        model_value,
        color_values,
        path,
    ):
        """Return extra directories from the index or direct disk fallback."""

        indexed = I
        file_index = Aj(B, "_file_index", I)
        if getattr(B, "_local_file_index_enabled", J) and file_index is not I and file_index.has_snapshot():
            indexed = file_index.get_extras(
                name_value,
                type_value,
                model_value,
                color_values,
            )
        path_exists = A.path.isdir(path)
        live_values = B._list_child_directories(path) if path_exists else []
        if indexed is not I:
            return B._merge_live_lookup_values(indexed, live_values), path_exists
        if path_exists:
            return live_values, J
        return [], h

    def _resolve_product_file_rows(
        B,
        product_dir,
        name_value,
        type_value,
        model_value,
        color_values,
        extra_value,
    ):
        """Return product files using the index first and ``scandir`` as fallback."""

        resolved = []
        seen = set()
        file_index = Aj(B, "_file_index", I)
        if getattr(B, "_local_file_index_enabled", J) and file_index is not I and file_index.has_snapshot():
            indexed_files = file_index.get_product_files(
                name_value,
                type_value,
                model_value,
                color_values,
                extra_value,
            )
            if indexed_files is not I:
                for filename in indexed_files:
                    path = A.path.join(product_dir, filename)
                    if A.path.isfile(path):
                        resolved.append((filename, path))
                        seen.add(filename)
        try:
            live_rows = []
            with A.scandir(product_dir) as entries:
                for entry in entries:
                    if entry.is_file():
                        live_rows.append((entry.name, entry.path))
            for filename, path in sorted(live_rows, key=lambda item: G(item[0]).lower()):
                if filename in seen:
                    continue
                resolved.append((filename, path))
            return resolved
        except E:
            return resolved

    def _set_local_file_index_enabled(A, enabled):
        """Toggle whether GUI lookups should use the persisted local file index."""

        A._local_file_index_enabled = bool(enabled)
        if A._local_file_index_enabled:
            file_index = Aj(A, "_file_index", I)
            if file_index is not I:
                if not file_index.has_snapshot():
                    file_index.load_cache()
                A._on_file_index_status_change(file_index.get_status())
            A._refresh_name_values_from_index()
            A._start_file_index_refresh()
            return
        A._file_index_status_var.set(
            LANG.get(
                "file_index_status_disabled",
                "Indeks plików: wyłączony w ustawieniach aplikacji.",
            )
        )

    def _sync_state_refs(A):
        """Expose the mutable product state through legacy attributes."""

        A.pending_additions = A._product_state.pending_additions
        A.pending_deletions = A._product_state.pending_deletions
        A.pending_ftp_deletions = A._product_state.pending_ftp_deletions
        A.ftp_remote_only = A._product_state.ftp_remote_only
        A.ftp_presence = A._product_state.ftp_presence
        A.ftp_preview_files = A._product_state.ftp_preview_files
        A.ftp_downloaded_final = A._product_state.ftp_downloaded_final
        A.sql_presence = A._product_state.sql_presence
        A.original_files = A._product_state.original_files

    def _set_product_identity(A, identity):
        """Store the latest product identity in the shared product state."""

        A._product_state.identity = identity

    def _snapshot_product_state(A):
        """Return a deep snapshot suitable for background worker usage."""

        identity = ProductIdentity(
            name=G(A.var_name.get() or B).strip(),
            type_name=G(A.var_type.get() or B).strip(),
            model=G(A.var_model.get() or B).strip(),
            color1=G(A.var_color1.get() or B).strip(),
            color2=G(A.var_color2.get() or B).strip(),
            color3=G(A.var_color3.get() or B).strip(),
            extra=G(A.var_extra.get() or B).strip(),
            ean=G(A.var_ean.get() or B).strip(),
            product_id=G(A.var_product_id.get() or B).strip(),
        )
        snapshot = A._product_state.clone()
        snapshot.identity = identity
        return snapshot

    def _snapshot_slot_runtime(A):
        """Return lightweight slot data that can be safely used by workers."""

        slot_records = []
        for slot in A.slots:
            slot_records.append(
                {
                    Aa: slot[Aa],
                    "label": slot["label"],
                    f: slot.get(f),
                    B0: slot.get(B0),
                }
            )
        return slot_records

    def _commit_product_state(A, state):
        """Replace runtime product state with a new main-thread snapshot."""

        if not isinstance(state, ProductState):
            return
        A._product_state = state
        A._sync_state_refs()

    def _reset_product_state(A):
        """Drop all file/FTP/SQL runtime state for the current product."""

        state = ProductState(identity=A._snapshot_product_state().identity)
        A._commit_product_state(state)

    def _get_modified_slot_indices(A):
        """Return slot indices carrying unsaved user edits."""

        dirty = (
            set(A.pending_additions)
            | set(A.pending_deletions)
            | set(A.pending_ftp_deletions)
        )
        for idx, slot in A0(A.slots):
            if slot.get(B0) == AR:
                dirty.add(idx)
        return dirty

    def _has_modified_slots(A):
        """Return True when at least one slot contains unsaved edits."""

        return bool(A._get_modified_slot_indices())

    def _normalize_color_vars(A, *, apply_changes=J):
        """Return color slots compacted to the left and optionally update the form."""

        normalized = normalize_color_slots(
            (
                A.var_color1.get(),
                A.var_color2.get(),
                A.var_color3.get(),
            )
        )
        if apply_changes:
            current = (
                G(A.var_color1.get() or B).strip().upper(),
                G(A.var_color2.get() or B).strip().upper(),
                G(A.var_color3.get() or B).strip().upper(),
            )
            normalized_tuple = tuple(normalized)
            if current != normalized_tuple:
                A.suppress_scan = J
                try:
                    A.var_color1.set(normalized[0])
                    A.var_color2.set(normalized[1])
                    A.var_color3.set(normalized[2])
                finally:
                    A.suppress_scan = h
        return normalized

    def _reload_entry_cache(A, excel_data):
        """Refresh in-memory entry indices from workbook payload data."""

        entries = excel_data.get(W, {})
        if not isinstance(entries, dict):
            entries = {}
        records = excel_data.get(ENTRY_RECORDS_KEY, [])
        if not isinstance(records, list):
            records = []
        A.entries = entries
        A.entry_records = [record for record in records if isinstance(record, dict)]
        A.entries_by_id = {
            G(record.get(PRODUCT_ID_HEADER) or B).strip().upper(): record
            for record in A.entry_records
            if G(record.get(PRODUCT_ID_HEADER) or B).strip()
        }

    def _normalize_entry_part(A, value, *, extra=h):
        """Normalize product form values for exact record matching."""

        if extra:
            return normalize_extra_segment(value, default=L)
        return G(value or B).strip().upper()

    def _build_entry_signature(
        A,
        name,
        type_value,
        model,
        color1,
        color2,
        color3,
        extra_value,
    ):
        """Build the canonical signature used to match a product entry."""

        return (
            A._normalize_entry_part(name),
            A._normalize_entry_part(type_value),
            A._normalize_entry_part(model),
            A._normalize_entry_part(color1),
            A._normalize_entry_part(color2),
            A._normalize_entry_part(color3),
            A._normalize_entry_part(extra_value, extra=J),
        )

    def _current_entry_signature(A):
        """Return the signature of the values currently visible in the form."""

        return A._build_entry_signature(
            A.var_name.get(),
            A.var_type.get(),
            A.var_model.get(),
            A.var_color1.get(),
            A.var_color2.get(),
            A.var_color3.get(),
            A.var_extra.get(),
        )

    def _current_lookup_signature(A):
        """Return the lookup key that should invalidate slot refreshes."""

        return A._current_entry_signature() + (
            A._normalize_entry_part(A.var_ean.get()),
        )

    def _refresh_commit_snapshot(A):
        """Store the latest committed form state to avoid accidental reprocessing."""

        A._commit_snapshot = {
            "name": A._normalize_entry_part(A.var_name.get()),
            "type": A._normalize_entry_part(A.var_type.get()),
            "model": A._normalize_entry_part(A.var_model.get()),
            "colors": (
                A._normalize_entry_part(A.var_color1.get()),
                A._normalize_entry_part(A.var_color2.get()),
                A._normalize_entry_part(A.var_color3.get()),
            ),
            "extra": A._normalize_entry_part(A.var_extra.get(), extra=J),
        }

    def _get_form_field_raw_value(A, field_key):
        """Return the current user-visible value for a tracked form field."""

        var_attr = FORM_TRACKED_VAR_ATTRS.get(field_key)
        tracked_var = getattr(A, var_attr, I) if var_attr else I
        if tracked_var is I:
            return B
        value = G(tracked_var.get() or B).strip()
        if field_key == "ean":
            return value.upper()
        return value

    def _normalize_form_field_value(A, field_key, value=I):
        """Normalize a tracked form field for dirty-state comparisons."""

        raw_value = A._get_form_field_raw_value(field_key) if value is I else G(value or B).strip()
        if field_key == "ean":
            return raw_value.upper()
        return A._normalize_entry_part(raw_value, extra=field_key == "extra")

    def _capture_loaded_field_values(A):
        """Snapshot the current visible form values as the original loaded state."""

        A._loaded_field_values = {
            field_key: A._get_form_field_raw_value(field_key)
            for field_key in FORM_TRACKED_FIELDS
        }
        A._queue_form_change_refresh()

    def _queue_form_change_refresh(A, *_args):
        """Debounce form dirty/highlight refresh to the next Tk idle turn."""

        A._last_ean_conflict_notice = I
        if A._field_change_refresh_job is not I:
            return
        A._field_change_refresh_job = A.after_idle(A._refresh_form_change_markers)

    def _should_lookup_existing_files_for_form_edit(A):
        """Return True when metadata edits should trigger a file lookup."""

        if A.suppress_scan or A._preserve_loaded_binding():
            return h
        return (
            bool(A.var_name.get().strip())
            and bool(A.var_type.get().strip())
            and bool(A.var_model.get().strip())
            and bool(A.var_color1.get().strip())
        )

    def _register_form_field(A, field_key, field, label, widget, restore_button):
        """Remember widgets that belong to a tracked form field."""

        if not field_key:
            return
        A._form_field_meta[field_key] = {
            "frame": field,
            "label": label,
            "widget": widget,
            "restore": restore_button,
        }
        A._queue_form_change_refresh()

    def _refresh_form_change_markers(A):
        """Highlight edited fields and enable per-field restore buttons."""

        A._field_change_refresh_job = I
        has_loaded_values = bool(A._loaded_field_values)
        for field_key, meta in Aj(A, "_form_field_meta", {}).items():
            dirty = h
            if has_loaded_values and field_key in A._loaded_field_values:
                dirty = (
                    A._normalize_form_field_value(field_key)
                    != A._normalize_form_field_value(
                        field_key, A._loaded_field_values.get(field_key, B)
                    )
                )
            frame = meta.get("frame")
            label = meta.get("label")
            restore_button = meta.get("restore")
            if frame:
                try:
                    frame.configure(
                        style="ChangedField.TFrame" if dirty else "Card.TFrame"
                    )
                except E:
                    pass
            if label:
                try:
                    label.configure(
                        style="ChangedForm.TLabel" if dirty else "Form.TLabel"
                    )
                except E:
                    pass
            if restore_button:
                try:
                    restore_button.configure(
                        state=X if dirty else V,
                        style="MiniWarn.TButton" if dirty else "MiniOutline.TButton",
                    )
                except E:
                    pass

    def _restore_form_field_value(A, field_key):
        """Restore a single field to the value from the last loaded entry."""

        if field_key not in A._loaded_field_values:
            return
        restored_value = A._loaded_field_values.get(field_key, B)
        if field_key == "name":
            A.var_name.set(restored_value)
            A._on_name_commit()
            A._on_type_commit()
            A._on_model_commit()
            A._on_color_commit()
            A._on_extra_commit()
        elif field_key == "type":
            A.var_type.set(restored_value)
            A._on_type_commit()
            A._on_model_commit()
            A._on_color_commit()
            A._on_extra_commit()
        elif field_key == "model":
            A.var_model.set(restored_value)
            A._on_model_commit()
            A._on_color_commit()
            A._on_extra_commit()
        elif field_key in {"color1", "color2", "color3"}:
            getattr(A, FORM_TRACKED_VAR_ATTRS[field_key]).set(restored_value)
            A._on_color_commit()
            A._on_extra_commit()
        elif field_key == "extra":
            A.var_extra.set(restored_value)
            A._on_extra_commit()
        elif field_key == "ean":
            A.var_ean.set(restored_value)
            A._refresh_existing_files_lookup_for_form_edit()
        A._queue_form_change_refresh()

    def _commit_matches_snapshot(A, key, value):
        """Return True when the current commit carries no actual form change."""

        return A._commit_snapshot.get(key) == value

    def _has_loaded_entry_context(A):
        """Return True when the form still belongs to a loaded product record."""

        product_id = G(A.var_product_id.get() or B).strip()
        loaded_values = Aj(A, "_loaded_field_values", {})
        return bool(product_id or loaded_values or A._record_loaded)

    def _preserve_loaded_binding(A):
        """Return True when edits should stay attached to the loaded record."""

        return A._has_loaded_entry_context()

    def _clear_loaded_entry_context(A, keep_ean=h):
        """Forget the currently loaded product binding and reset lookup cache."""

        A._record_loaded = h
        A.var_product_id.set(B)
        A._loaded_field_values = {}
        A._last_lookup_signature = I
        if not keep_ean:
            A.var_ean.set(B)
        A._queue_form_change_refresh()

    def _set_loaded_entry_context(A, record):
        """Attach the form to a specific saved product entry."""

        if not isinstance(record, dict):
            A._clear_loaded_entry_context()
            return
        product_id = G(record.get(PRODUCT_ID_HEADER) or B).strip().upper()
        ean = G(record.get(EAN_HEADER) or B).strip().upper()
        A.var_product_id.set(product_id)
        if ean:
            A.var_ean.set(ean)
        A._record_loaded = bool(product_id)
        A._capture_loaded_field_values()
        A._last_lookup_signature = I

    def _find_entry_records_by_fields(A, signature):
        """Return saved entry records matching the exact product signature."""

        return [
            record
            for record in A.entry_records
            if A._build_entry_signature(
                record.get(NAME_HEADER, B),
                record.get(TYPE_HEADER, B),
                record.get(MODEL_HEADER, B),
                record.get(COLOR1_HEADER, B),
                record.get(COLOR2_HEADER, B),
                record.get(COLOR3_HEADER, B),
                record.get(EXTRA_HEADER, B),
            )
            == signature
        ]

    def _find_entry_records_by_ean(A, ean):
        """Return cached records using the provided EAN value."""

        normalized = G(ean or B).strip().upper()
        if not normalized:
            return []
        return [
            record
            for record in A.entry_records
            if G(record.get(EAN_HEADER) or B).strip().upper() == normalized
        ]

    def _entry_record_signature(A, record):
        """Return the canonical product signature for a saved record."""

        if not isinstance(record, dict):
            return ()
        return A._build_entry_signature(
            record.get(NAME_HEADER, B),
            record.get(TYPE_HEADER, B),
            record.get(MODEL_HEADER, B),
            record.get(COLOR1_HEADER, B),
            record.get(COLOR2_HEADER, B),
            record.get(COLOR3_HEADER, B),
            record.get(EXTRA_HEADER, B),
        )

    def _resolve_ean_conflict(A, ean=I, *, quick_check=h):
        """Return a conflicting saved entry for the current EAN, if one exists."""

        normalized = G(ean if ean is not I else A.var_ean.get() or B).strip().upper()
        if not normalized or normalized == q:
            return I
        current_signature = A._current_entry_signature()
        if quick_check and not all(current_signature[:4]):
            return I
        current_product_id = G(A.var_product_id.get() or B).strip().upper()
        for record in A._find_entry_records_by_ean(normalized):
            record_product_id = G(record.get(PRODUCT_ID_HEADER) or B).strip().upper()
            if current_product_id and record_product_id and current_product_id == record_product_id:
                continue
            if A._entry_record_signature(record) == current_signature:
                continue
            return record
        return I

    def _warn_about_ean_conflict(A, *, force_message=h, quick_check=J):
        """Warn when the current EAN already belongs to another saved product."""

        ean = G(A.var_ean.get() or B).strip().upper()
        conflict = A._resolve_ean_conflict(ean, quick_check=quick_check)
        if conflict is I:
            A._last_ean_conflict_notice = I
            return J
        notice_key = (
            ean,
            G(conflict.get(PRODUCT_ID_HEADER) or B).strip().upper(),
            A._entry_record_signature(conflict),
        )
        if not force_message and A._last_ean_conflict_notice == notice_key:
            return h
        A._last_ean_conflict_notice = notice_key
        O.showwarning(
            LANG.get("ean_duplicate_title", "Duplikat EAN"),
            LANG.get(
                "ean_duplicate_warning",
                "Kod EAN {ean} jest już przypisany do innego wpisu:\n\n{record}\n\nWczytaj istniejący wpis albo użyj innego EAN.",
            ).format(
                ean=ean,
                record=A._describe_entry_record(conflict),
            ),
        )
        return h

    def _on_ean_focus_out(A, _event=I):
        """Run a quick duplicate-EAN check after leaving the field."""

        A._warn_about_ean_conflict(force_message=h, quick_check=J)

    def _describe_entry_record(A, record):
        """Build a concise label used in record selection prompts."""

        parts = [
            G(record.get(NAME_HEADER) or B).strip(),
            G(record.get(TYPE_HEADER) or B).strip(),
            G(record.get(MODEL_HEADER) or B).strip(),
        ]
        colors = [
            G(record.get(COLOR1_HEADER) or B).strip(),
            G(record.get(COLOR2_HEADER) or B).strip(),
            G(record.get(COLOR3_HEADER) or B).strip(),
        ]
        colors = [value for value in colors if value]
        if colors:
            parts.append(" / ".join(colors))
        extra_value = G(record.get(EXTRA_HEADER) or B).strip()
        if extra_value and extra_value.upper() != L:
            parts.append(extra_value)
        title = " | ".join([part for part in parts if part]) or LANG.get(
            "entry_record_fallback",
            "Zapisany produkt",
        )
        ean = G(record.get(EAN_HEADER) or B).strip() or q
        product_id = G(record.get(PRODUCT_ID_HEADER) or B).strip() or "BRAK-ID"
        return f"{title}  |  EAN: {ean}  |  ID: {product_id}"

    def _prompt_select_entry_record(A, records, title, prompt):
        """Ask the user which matching saved record should be loaded."""

        if not records:
            return I
        if Q(records) == 1:
            return records[0]
        A._last_focus_widget = A.focus_get()
        win = F.Toplevel(A)
        win.title(title)
        win.transient(A)
        win.grab_set()
        C.Label(win, text=prompt).pack(padx=10, pady=(10, 6), anchor="w")
        body = C.Frame(win)
        body.pack(fill=z, expand=J, padx=10, pady=(0, 8))
        listbox = F.Listbox(body, height=min(8, Q(records)), exportselection=0)
        scroll = C.Scrollbar(body, orient=An, command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side=AV, fill="y")
        listbox.pack(side=Am, fill=z, expand=J)
        labels = [A._describe_entry_record(record) for record in records]
        width = max(48, min(max((Q(label) for label in labels), default=48), 120))
        try:
            listbox.configure(width=width)
        except E:
            pass
        for label in labels:
            listbox.insert(F.END, label)
        listbox.selection_set(0)
        selected = {"record": I}

        def _choose():
            selection = listbox.curselection()
            if not selection:
                return
            selected["record"] = records[selection[0]]
            win.destroy()

        def _cancel():
            win.destroy()

        buttons = C.Frame(win)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        C.Button(
            buttons,
            text=CHOOSE_LABEL,
            command=_choose,
        ).pack(side=Am)
        C.Button(
            buttons,
            text=CANCEL_LABEL,
            command=_cancel,
        ).pack(side=AV)
        listbox.bind("<Double-Button-1>", lambda _event: _choose())
        win.protocol("WM_DELETE_WINDOW", _cancel)
        A.wait_window(win)
        A._restore_focus()
        return selected["record"]

    def _load_entry_record(A, record):
        """Populate the form from a saved entry record and refresh slot state."""

        if not isinstance(record, dict):
            return
        ean = G(record.get(EAN_HEADER) or B).strip().upper()
        extra_value = G(record.get(EXTRA_HEADER) or B).strip().upper()
        A._clear_loaded_entry_context(keep_ean=bool(ean))
        A._reset_form_fields(keep_ean=bool(ean))
        A.var_product_id.set(G(record.get(PRODUCT_ID_HEADER) or B).strip().upper())
        if ean:
            A.var_ean.set(ean)
        A.suppress_scan = J
        A.loading_by_ean = J
        try:
            A.var_name.set(G(record.get(NAME_HEADER) or B).strip().upper())
            A._on_name_commit()
            A.var_type.set(G(record.get(TYPE_HEADER) or B).strip().upper())
            A._on_type_commit()
            A.var_model.set(G(record.get(MODEL_HEADER) or B).strip().upper())
            A._on_model_commit()
            A.var_color1.set(G(record.get(COLOR1_HEADER) or B).strip().upper())
            A.var_color2.set(G(record.get(COLOR2_HEADER) or B).strip().upper())
            A.var_color3.set(G(record.get(COLOR3_HEADER) or B).strip().upper())
            A._on_color_commit()
            if extra_value == L:
                A.var_extra.set(B)
            else:
                A.var_extra.set(extra_value)
            A._on_extra_commit()
            if ean:
                A.var_ean.set(ean)
        finally:
            A.loading_by_ean = h
            A.suppress_scan = h
        A._set_loaded_entry_context(record)
        A._refresh_commit_snapshot()
        A._load_existing_files(force=J)

    def _search_current_entry(A):
        """Load a saved record by Product ID, EAN or the current form values."""

        ean = G(A.var_ean.get() or B).strip().upper()
        if ean:
            record = A.entries.get(ean)
            if record:
                resolved = dict(record)
                resolved[EAN_HEADER] = ean
                A._load_entry_record(resolved)
                return
            O.showinfo(NOT_FOUND_LABEL, NO_SAVED_DATA_FOR_EAN_MSG.format(ean=ean))
            A._activate_new_entry_mode(keep_values=J)
            return
        product_id = G(A.var_product_id.get() or B).strip().upper()
        if product_id and product_id in A.entries_by_id:
            A._load_entry_record(A.entries_by_id[product_id])
            return
        signature = A._current_entry_signature()
        if not any(signature) and not ean and not product_id:
            O.showwarning(
                NO_DATA_MSG,
                LANG.get(
                    "search_requires_any_value",
                    "Podaj EAN albo dane produktu, aby wyszukac wpis.",
                ),
            )
            return
        if not all(signature[:4]):
            A._activate_new_entry_mode(keep_values=J)
            return
        matches = A._find_entry_records_by_fields(signature)
        if not matches:
            A._activate_new_entry_mode(keep_values=J)
            return
        record = A._prompt_select_entry_record(
            matches,
            LANG.get("search_select_title", "Wybierz zapisany produkt"),
            LANG.get(
                "search_select_prompt",
                "Znaleziono kilka pasujących wpisów. Wybierz rekord do wczytania:",
            ),
        )
        if record:
            A._load_entry_record(record)

    def _activate_new_entry_mode(A, keep_values=J):
        """Drop the current loaded binding and continue as a new entry."""

        A._cancel_existing_lookup()
        preserve_ean = keep_values and bool(A.var_ean.get().strip())
        A.suppress_scan = J
        try:
            A._clear_loaded_entry_context(keep_ean=preserve_ean)
            if keep_values:
                A._reset_product_state()
                A._clear_all_slots()
            else:
                A._reset_form_fields(keep_ean=h)
        finally:
            A.suppress_scan = h
        A._busy_status_var.set(LANG.get("busy_state_idle", "Stan: gotowe"))
        A._refresh_commit_snapshot()
        A._queue_form_change_refresh()
        A._queue_dashboard_refresh()
        if (
            keep_values
            and A.var_name.get().strip()
            and A.var_type.get().strip()
            and A.var_model.get().strip()
            and A.var_color1.get().strip()
            and not A.suppress_scan
        ):
            A._schedule_existing_files_lookup()

    def _start_new_search(A):
        """Clear the form and switch back to an empty search state."""

        if A.is_processing:
            O.showwarning(OPERATION_TITLE, PROCESSING_MSG)
            return
        A._activate_new_entry_mode(keep_values=h)
        A._focus_widget(A.combo_name)

    def _set_busy_state(A, text, active=J):
        """Show or hide the compact global busy indicator near the log."""

        if active:
            A._busy_counter += 1
            A._current_busy_label = G(text or B).strip()
        else:
            A._busy_counter = max(0, A._busy_counter - 1)
            if A._busy_counter == 0:
                A._current_busy_label = B
        if A._busy_counter > 0 and A._current_busy_label:
            A._busy_status_var.set(
                LANG.get("busy_state_active", "Stan: {state}").format(
                    state=A._current_busy_label
                )
            )
            progress = Aj(A, "_busy_progress", I)
            if progress:
                try:
                    progress.start(10)
                except E:
                    pass
        else:
            A._busy_status_var.set(LANG.get("busy_state_idle", "Stan: gotowe"))
            progress = Aj(A, "_busy_progress", I)
            if progress:
                try:
                    progress.stop()
                except E:
                    pass

    def _current_perf_snapshot(B):
        """Return the latest lightweight UI telemetry values."""

        if B._perf_samples:
            avg_ms = sum(B._perf_samples) / Q(B._perf_samples)
        else:
            avg_ms = PERF_MONITOR_MS
        lag_ms = max(avg_ms - PERF_MONITOR_MS, 0.0)
        fps_est = min(60.0, 1000.0 / max(avg_ms, 1.0))
        try:
            thumb_q = B._thumb_request_queue.qsize()
        except E:
            thumb_q = 0
        return {
            "avg_ms": avg_ms,
            "lag_ms": lag_ms,
            "fps": fps_est,
            "thumb_queue": thumb_q,
            "lookup_ms": int(B._last_lookup_duration_ms or 0),
        }

    def _perf_monitor_tick(A):
        """Continuously update lightweight UI latency and throughput telemetry."""

        now = Ag.perf_counter()
        delta_ms = max((now - A._perf_last_tick) * 1000.0, 0.0)
        A._perf_last_tick = now
        A._perf_samples.append(delta_ms)
        snapshot = A._current_perf_snapshot()
        A._perf_status_var.set(
            LANG.get(
                "perf_status_line",
                "UI ~{fps:.0f} FPS  |  opóźnienie {lag:.0f} ms",
            ).format(fps=snapshot["fps"], lag=snapshot["lag_ms"])
        )
        A._perf_detail_var.set(
            LANG.get(
                "perf_detail_line",
                "miniatury w kolejce: {thumbs}  |  ostatni lookup: {lookup} ms",
            ).format(
                thumbs=snapshot["thumb_queue"],
                lookup=snapshot["lookup_ms"],
            )
        )
        next_interval = PERF_MONITOR_MS
        if not A.is_processing and snapshot["thumb_queue"] == 0 and A._busy_counter == 0:
            next_interval = 220
        try:
            if A.winfo_exists():
                A._perf_monitor_job = A.after(next_interval, A._perf_monitor_tick)
        except E:
            A._perf_monitor_job = I

    def _apply_slot_grid(B):
        if not Aj(B, "slots_frame", I):
            return
        columns = SLOT_GRID_COLUMNS
        if columns == B._slot_grid_columns:
            return
        max_columns = max(B._slot_grid_columns, columns)
        for idx in Ax(max_columns):
            try:
                B.slots_frame.columnconfigure(idx, weight=0, uniform="", minsize=0)
            except E:
                pass
        for idx in Ax(columns):
            B.slots_frame.columnconfigure(
                idx,
                weight=1,
                uniform="slot-grid",
                minsize=186,
            )
        for idx, slot in A0(B.slots):
            frame = slot.get(AS)
            if not frame:
                continue
            frame.grid(
                row=idx // columns,
                column=idx % columns,
                padx=6,
                pady=6,
                sticky="nsew",
            )
        B._slot_grid_columns = columns
        B._schedule_slots_canvas_refresh()

    def _schedule_slots_canvas_refresh(B, *_args):
        if B._slots_refresh_job is not I:
            return
        try:
            B._slots_refresh_job = B.after_idle(B._refresh_slots_canvas)
        except E:
            B._slots_refresh_job = I

    def _refresh_slots_canvas(B):
        B._slots_refresh_job = I
        canvas = Aj(B, "_slots_canvas", I)
        if not canvas:
            return
        try:
            bbox = canvas.bbox("all")
            if bbox:
                canvas.configure(scrollregion=bbox)
        except E:
            pass

    def _bind_slot_scroll_target(B, widget):
        if not widget:
            return
        try:
            tags = tuple(widget.bindtags())
            if "SlotScroll" not in tags:
                widget.bindtags(("SlotScroll",) + tags)
        except E:
            return
        for child in widget.winfo_children():
            B._bind_slot_scroll_target(child)

    def _scroll_slots(B, steps):
        canvas = Aj(B, "_slots_canvas", I)
        if not canvas:
            return
        try:
            canvas.yview_scroll(steps, "units")
        except E:
            return
        return "break"

    def _on_slots_mousewheel(B, event):
        delta = getattr(event, "delta", 0)
        if not delta:
            return
        steps = max(1, int(abs(delta) / 120)) or 1
        if delta > 0:
            steps *= -1
        return B._scroll_slots(steps)

    def _on_slots_scroll_up(B, _event):
        return B._scroll_slots(-1)

    def _on_slots_scroll_down(B, _event):
        return B._scroll_slots(1)

    def _get_thumbnail_cache_key(B, path):
        try:
            stat = A.stat(path)
            return (A.path.abspath(path), stat.st_mtime_ns, stat.st_size)
        except E:
            return (A.path.abspath(path), I, I)

    def _get_cached_thumbnail(B, path):
        cache_key = B._get_thumbnail_cache_key(path)
        with B._thumb_cache_lock:
            thumb = B._thumb_cache.get(cache_key)
            if thumb is I:
                return cache_key, I
            B._thumb_cache.move_to_end(cache_key)
            return cache_key, thumb

    def _store_cached_thumbnail(B, cache_key, thumb):
        if cache_key is I or thumb is I:
            return
        with B._thumb_cache_lock:
            B._thumb_cache[cache_key] = thumb
            B._thumb_cache.move_to_end(cache_key)
            while Q(B._thumb_cache) > B._thumb_cache_limit:
                B._thumb_cache.popitem(last=h)

    def _next_thumbnail_token(B):
        B._thumb_request_seq += 1
        return B._thumb_request_seq

    def _thumbnail_worker_loop(B):
        while J:
            job = B._thumb_request_queue.get()
            if job is I:
                return
            idx, path, token = job
            thumb = I
            if path and A.path.isfile(path):
                thumb = B._load_slot_thumbnail(path)
            B._thumb_result_queue.put((idx, path, token, thumb))

    def _poll_thumbnail_results(B):
        B._thumb_poll_job = I
        processed = 0
        while processed < THUMBNAIL_RESULT_BATCH:
            try:
                idx, path, token, thumb = B._thumb_result_queue.get_nowait()
            except queue.Empty:
                break
            processed += 1
            if B._thumb_tokens.get(idx) != token:
                continue
            if idx < 0 or idx >= Q(B.slots):
                continue
            if B._get_slot_preview_path(B.slots[idx]) != path:
                continue
            B._set_slot_preview(idx, path, thumb)
        try:
            if B.winfo_exists():
                B._thumb_poll_job = B.after(
                    THUMBNAIL_POLL_MS,
                    B._poll_thumbnail_results,
                )
        except E:
            B._thumb_poll_job = I

    def _schedule_existing_files_lookup(B, delay_ms=180):
        if B.suppress_scan:
            return
        if B._load_existing_after_id is not I:
            try:
                B.after_cancel(B._load_existing_after_id)
            except E:
                pass
        B._load_existing_after_id = B.after(delay_ms, B._run_scheduled_existing_files_lookup)

    def _run_scheduled_existing_files_lookup(B):
        B._load_existing_after_id = I
        B._load_existing_files()

    def _cancel_existing_lookup(B):
        if B._load_existing_after_id is not I:
            try:
                B.after_cancel(B._load_existing_after_id)
            except E:
                pass
            B._load_existing_after_id = I
        B._load_existing_request_id += 1
        clear_busy = h
        with B._existing_lookup_lock:
            B._retry_existing_lookup = h
            B._existing_lookup_running = h
            B._existing_lookup_active_request_id = I
            if B._existing_lookup_busy:
                B._existing_lookup_busy = h
                clear_busy = J
        B._update_all_slot_activity(active=h)
        if clear_busy:
            B._set_busy_state("", active=h)

    def _refresh_existing_files_lookup_for_form_edit(B):
        B._cancel_existing_lookup()
        if B._should_lookup_existing_files_for_form_edit():
            B._schedule_existing_files_lookup()

    def _finish_existing_lookup(B, request_id=I):
        should_retry = h
        clear_busy = h
        with B._existing_lookup_lock:
            if request_id is not I and B._existing_lookup_active_request_id != request_id:
                return
            should_retry = B._retry_existing_lookup
            B._retry_existing_lookup = h
            B._existing_lookup_running = h
            B._existing_lookup_active_request_id = I
            if B._existing_lookup_busy:
                B._existing_lookup_busy = h
                clear_busy = J
        if clear_busy:
            B._set_busy_state("", active=h)
        if should_retry:
            try:
                B.after(0, lambda: B._load_existing_files(force=J))
            except E:
                pass

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
            source = B
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
                continue
            errors.extend(B._collect_static_symbol_issues(path, source))
        return {"root": root, "files": files, "errors": errors}

    def _collect_static_symbol_issues(A, path, source):
        """Return targeted static issues that plain compilation would miss."""

        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            return []
        source_lines = source.splitlines()
        defined = set(dir(__builtins__))
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    defined.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    defined.add(alias.asname or alias.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for name in ast.walk(target):
                        if isinstance(name, ast.Name):
                            defined.add(name.id)
        issues = []
        seen = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
                continue
            name = node.id
            if not name.endswith("_HEADER") or name in defined:
                continue
            issue_key = (name, getattr(node, "lineno", 0))
            if issue_key in seen:
                continue
            seen.add(issue_key)
            issues.append(
                {
                    "path": path,
                    "line": getattr(node, "lineno", 0),
                    "col": getattr(node, "col_offset", 0) + 1,
                    "message": f"Undefined header constant: {name}",
                    "text": source_lines[getattr(node, "lineno", 1) - 1]
                    if getattr(node, "lineno", 0)
                    and getattr(node, "lineno", 0) <= Q(source_lines)
                    else B,
                }
            )
        return issues

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

    def _sample_thumbnail_paths(A, limit=8):
        """Collect a small sample of current images for the benchmark."""

        sample_paths = []
        seen = set()
        for slot in Aj(A, "slots", []):
            path = slot.get(f)
            if not path or path in seen or not common.A.path.isfile(path):
                continue
            sample_paths.append(path)
            seen.add(path)
            if Q(sample_paths) >= limit:
                return sample_paths
        current_dir = build_product_directory(
            l,
            A.var_name.get().strip(),
            A.var_type.get().strip(),
            A.var_model.get().strip(),
            [
                A.var_color1.get().strip(),
                A.var_color2.get().strip(),
                A.var_color3.get().strip(),
            ],
            A.var_extra.get().strip(),
        )
        if common.A.path.isdir(current_dir):
            try:
                for entry in common.A.scandir(current_dir):
                    if not entry.is_file():
                        continue
                    ext = common.A.path.splitext(entry.name)[1].lower()
                    if ext not in IMAGE_EXTENSION_FORMATS:
                        continue
                    if entry.path in seen:
                        continue
                    sample_paths.append(entry.path)
                    seen.add(entry.path)
                    if Q(sample_paths) >= limit:
                        break
            except E:
                pass
        return sample_paths

    def _benchmark_thumbnail_decode(A, sample_paths):
        """Measure thumbnail preparation time on a small image sample set."""

        durations = []
        for path in sample_paths:
            started = Ag.perf_counter()
            try:
                with AA.open(path) as img:
                    img.thumbnail(SLOT_PREVIEW_SIZE, LANCZOS_FILTER)
                    img.copy()
            except E:
                continue
            durations.append((Ag.perf_counter() - started) * 1000.0)
        if not durations:
            return {"count": 0, "avg_ms": 0.0, "max_ms": 0.0, "total_ms": 0.0}
        return {
            "count": Q(durations),
            "avg_ms": sum(durations) / Q(durations),
            "max_ms": max(durations),
            "total_ms": sum(durations),
        }

    def _format_performance_report(A, result):
        """Return a readable diagnostics report for the performance benchmark."""

        timestamp = A9.now().strftime(A6)
        ui = result.get("ui", {})
        thumbs = result.get("thumbs", {})
        queue_depth = result.get("thumb_queue", 0)
        busy = result.get("busy", B) or LANG.get("busy_state_idle", "Stan: gotowe")
        lines = [
            LANG.get("perf_report_title", "Raport wydajności interfejsu"),
            LANG.get("perf_report_time", "Czas: {time}").format(time=timestamp),
            LANG.get("perf_report_fps", "Szacowane FPS UI: {fps:.0f}").format(
                fps=ui.get("fps", 0.0)
            ),
            LANG.get("perf_report_ui_avg", "Średni krok UI: {value:.1f} ms").format(
                value=ui.get("avg_ms", 0.0)
            ),
            LANG.get("perf_report_ui_p95", "P95 kroku UI: {value:.1f} ms").format(
                value=ui.get("p95_ms", 0.0)
            ),
            LANG.get("perf_report_ui_max", "Maksymalny krok UI: {value:.1f} ms").format(
                value=ui.get("max_ms", 0.0)
            ),
            LANG.get(
                "perf_report_thumb_queue",
                "Miniatury oczekujące w kolejce: {count}",
            ).format(count=queue_depth),
            LANG.get("perf_report_busy", "Aktualny stan: {state}").format(state=busy),
            B,
        ]
        if thumbs.get("count", 0):
            lines.extend(
                [
                    LANG.get(
                        "perf_report_thumb_header", "Dekodowanie miniaturek:"
                    ),
                    LANG.get(
                        "perf_report_thumb_count",
                        "Próbki: {count}",
                    ).format(count=thumbs.get("count", 0)),
                    LANG.get(
                        "perf_report_thumb_avg",
                        "Średnio: {value:.1f} ms",
                    ).format(value=thumbs.get("avg_ms", 0.0)),
                    LANG.get(
                        "perf_report_thumb_max",
                        "Maksimum: {value:.1f} ms",
                    ).format(value=thumbs.get("max_ms", 0.0)),
                    LANG.get(
                        "perf_report_thumb_total",
                        "Łącznie: {value:.1f} ms",
                    ).format(value=thumbs.get("total_ms", 0.0)),
                ]
            )
        else:
            lines.append(
                LANG.get(
                    "perf_report_thumb_none",
                    "Brak lokalnych obrazów do testu dekodowania miniaturek.",
                )
            )
        return "\n".join(lines)

    def _run_performance_benchmark(A, status_var=I, button=I, report_widget=I):
        """Run a lightweight UI and thumbnail performance benchmark."""

        if Aj(A, "_perf_check_running", h):
            return
        A._perf_check_running = J
        if status_var:
            status_var.set(
                LANG.get("perf_check_running", "Test wydajności trwa...")
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
        A._set_busy_state(
            LANG.get("busy_perf_test", "Test wydajności interfejsu"),
            active=J,
        )
        sample_paths = A._sample_thumbnail_paths()
        ui_samples = []
        target_ms = 16
        iterations = 32
        last_tick = {"value": Ag.perf_counter()}

        def finalize(result):
            A._perf_check_running = h
            A._set_busy_state(B, active=h)
            if button:
                try:
                    button.configure(state=X)
                except E:
                    pass
            report_text = A._format_performance_report(result)
            A._perf_check_last_report = report_text
            if report_widget:
                try:
                    report_widget.configure(state=Az)
                    report_widget.delete(A_, F.END)
                    report_widget.insert(F.END, report_text)
                    report_widget.configure(state=Ak)
                except E:
                    pass
            ui_avg = result.get("ui", {}).get("avg_ms", 0.0)
            thumb_avg = result.get("thumbs", {}).get("avg_ms", 0.0)
            status = LANG.get(
                "perf_check_done",
                "UI ~{fps:.0f} FPS, średni krok {avg:.1f} ms, miniatury {thumb:.1f} ms.",
            ).format(
                fps=result.get("ui", {}).get("fps", 0.0),
                avg=ui_avg,
                thumb=thumb_avg,
            )
            if status_var:
                status_var.set(status)

        def worker(ui_result):
            thumb_result = A._benchmark_thumbnail_decode(sample_paths)
            result = {
                "ui": ui_result,
                "thumbs": thumb_result,
                "thumb_queue": getattr(A._thumb_request_queue, "qsize", lambda: 0)(),
                "busy": LANG.get("busy_state_idle", "Stan: gotowe"),
            }
            A.after(0, lambda: finalize(result))

        def measure(step=0):
            now = Ag.perf_counter()
            if step:
                ui_samples.append((now - last_tick["value"]) * 1000.0)
            last_tick["value"] = now
            if step < iterations:
                A.after(target_ms, lambda s=step + 1: measure(s))
                return
            sorted_samples = sorted(ui_samples) if ui_samples else [0.0]
            avg_ms = sum(sorted_samples) / max(Q(sorted_samples), 1)
            p95_index = max(0, int((Q(sorted_samples) - 1) * 0.95))
            ui_result = {
                "avg_ms": avg_ms,
                "p95_ms": sorted_samples[p95_index],
                "max_ms": max(sorted_samples),
                "fps": min(60.0, 1000.0 / max(avg_ms, 1.0)),
            }
            threading.Thread(target=worker, args=(ui_result,), daemon=J).start()

        A.after(target_ms, lambda: measure(1))

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

        D_ = "<KeyRelease>"
        E_ = "<Return>"
        A._app_shell = C.Frame(A, style="App.TFrame", padding=(14, 14, 14, 12))
        A._app_shell.pack(fill=z, expand=J)
        A._app_shell.columnconfigure(0, weight=1)
        A._app_shell.rowconfigure(1, weight=1)

        toolbar = C.Frame(A._app_shell, style="App.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=8)
        toolbar.columnconfigure(1, weight=3)
        toolbar.rowconfigure(0, weight=1)

        form_card = C.Frame(toolbar, style="Card.TFrame", padding=(12, 10))
        form_card.grid(row=0, column=0, sticky="ew")
        for column_idx in Ax(4):
            form_card.columnconfigure(column_idx, weight=1, uniform="toolbar-form")
        form_card.columnconfigure(0, weight=2)
        form_card.columnconfigure(1, weight=2)

        summary = C.Frame(form_card, style="Card.TFrame")
        summary.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 6))
        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)

        C.Label(summary, text=APP_TITLE, style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        C.Label(
            summary,
            textvariable=A._hero_slots_var,
            style="Form.TLabel",
            anchor="e",
            justify="right",
        ).grid(row=0, column=1, sticky="e")
        C.Label(
            summary,
            textvariable=A._hero_context_var,
            style="SectionHint.TLabel",
            wraplength=560,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        C.Label(
            summary,
            textvariable=A._hero_remote_var,
            style="Form.TLabel",
            anchor="e",
            justify="right",
            wraplength=360,
        ).grid(row=1, column=1, sticky="e", pady=(2, 0))
        C.Label(
            summary,
            textvariable=A._hero_storage_var,
            style="SectionHint.TLabel",
            wraplength=980,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))
        C.Label(
            summary,
            textvariable=A._hero_status_var,
            style="Form.TLabel",
            anchor="e",
            justify="right",
        ).grid(row=2, column=1, sticky="e", pady=(2, 0))
        C.Label(
            summary,
            textvariable=A._file_index_status_var,
            style="SectionHint.TLabel",
            wraplength=980,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        G_ = A._build_form_combobox(
            form_card,
            row=1,
            column=0,
            label_text=NAME_LABEL,
            field_key="name",
            textvariable=A.var_name,
            values=A.lists[n],
            state=X,
            tooltip_text=LANG.get(
                "name_tooltip",
                "Pelna nazwa mebla bez kolorow, typu i modelu, np: 'Maggiore', 'LUNA', 'SLANT'.",
            ),
            columnspan=2,
            width=28,
        )
        A.combo_name = G_
        G_.bind(E_, lambda e: A._on_name_commit())
        G_.bind(A2, lambda e: A._on_name_commit())
        G_.bind("<FocusOut>", lambda _event: A.after_idle(A._on_name_commit))
        G_.bind(D_, A._on_key_release)
        G_.bind("<FocusIn>", A._remember_focus)

        H_ = A._build_form_combobox(
            form_card,
            row=1,
            column=2,
            label_text=TYPE_LABEL,
            field_key="type",
            textvariable=A.var_type,
            values=A.lists[t],
            state=X,
            tooltip_text=LANG.get(
                "type_tooltip",
                "Typ mebla, np: 'KOMODA', 'RTV', 'STOL' (mozna dodac dlugosc, np. 'RTV 100', 'SZAFA 80').",
            ),
            width=18,
        )
        A.combo_type = H_
        H_.bind(E_, lambda e: A._on_type_commit())
        H_.bind(A2, lambda e: A._on_type_commit())
        H_.bind("<FocusOut>", lambda _event: A.after_idle(A._on_type_commit))
        H_.bind(D_, A._on_key_release)
        H_.bind("<FocusIn>", A._remember_focus)

        I_ = A._build_form_combobox(
            form_card,
            row=1,
            column=3,
            label_text=MODEL_LABEL,
            field_key="model",
            textvariable=A.var_model,
            values=A.lists[s],
            state=X,
            tooltip_text=LANG.get(
                "model_tooltip",
                "Model lub wersja mebla, np: 'MA03', 'Li01', 'SOL-05'.",
            ),
            width=18,
        )
        A.combo_model = I_
        I_.bind(E_, lambda e: A._on_model_commit())
        I_.bind(A2, lambda e: A._on_model_commit())
        I_.bind("<FocusOut>", lambda _event: A.after_idle(A._on_model_commit))
        I_.bind(D_, A._on_key_release)
        I_.bind("<FocusIn>", A._remember_focus)

        J_ = A._build_form_combobox(
            form_card,
            row=2,
            column=0,
            label_text=COLOR1_LABEL,
            field_key="color1",
            textvariable=A.var_color1,
            values=A.lists[Y],
            state=X,
            tooltip_text=LANG.get("color1_tooltip", "Glowny kolor mebla (wymagany)."),
            width=16,
        )
        A.combo_color1 = J_
        J_.bind(E_, lambda e: A._on_color_commit())
        J_.bind(A2, lambda e: A._on_color_commit())
        J_.bind(D_, A._on_key_release)
        J_.bind("<FocusIn>", A._remember_focus)

        K_ = A._build_form_combobox(
            form_card,
            row=2,
            column=1,
            label_text=COLOR2_LABEL,
            field_key="color2",
            textvariable=A.var_color2,
            values=A.lists[Y],
            state=X,
            tooltip_text=LANG.get("color2_tooltip", "Drugi kolor mebla (opcjonalnie)."),
            width=16,
        )
        A.combo_color2 = K_
        K_.bind(E_, lambda e: A._on_color_commit())
        K_.bind(A2, lambda e: A._on_color_commit())
        K_.bind(D_, A._on_key_release)
        K_.bind("<FocusIn>", A._remember_focus)

        L_ = A._build_form_combobox(
            form_card,
            row=2,
            column=2,
            label_text=COLOR3_LABEL,
            field_key="color3",
            textvariable=A.var_color3,
            values=A.lists[Y],
            state=X,
            tooltip_text=LANG.get("color3_tooltip", "Trzeci kolor mebla (opcjonalnie)."),
            width=16,
        )
        A.combo_color3 = L_
        L_.bind(E_, lambda e: A._on_color_commit())
        L_.bind(A2, lambda e: A._on_color_commit())
        L_.bind(D_, A._on_key_release)
        L_.bind("<FocusIn>", A._remember_focus)

        M_ = A._build_form_combobox(
            form_card,
            row=2,
            column=3,
            label_text=EXTRA_LABEL,
            field_key="extra",
            textvariable=A.var_extra,
            values=A.lists[d],
            state=X,
            tooltip_text=LANG.get(
                "extra_tooltip",
                "Dodatkowe informacje, np. LED, RGB (pozostaw puste, jesli brak dodatkow).",
            ),
            width=16,
        )
        A.combo_extra = M_
        M_.bind(E_, lambda e: A._on_extra_commit())
        M_.bind(A2, lambda e: A._on_extra_commit())
        M_.bind(D_, A._on_key_release)
        M_.bind("<FocusIn>", A._remember_focus)

        ean_field = C.Frame(form_card, style="Card.TFrame")
        ean_field.grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=3, pady=(0, 2)
        )
        ean_field.columnconfigure(0, weight=1)
        ean_field.columnconfigure(1, weight=1)
        product_id_field = C.Frame(ean_field, style="Card.TFrame")
        product_id_field.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        product_id_field.columnconfigure(0, weight=1)
        product_id_label = C.Label(
            product_id_field,
            text=LANG.get("product_id_label", "ID produktu"),
            style="Form.TLabel",
        )
        product_id_label.grid(row=0, column=0, sticky="w", pady=(0, 2))
        A._add_tooltip(
            product_id_label,
            LANG.get(
                "product_id_tooltip",
                "Stały identyfikator wpisu. Jest generowany automatycznie i nie można go edytować.",
            ),
        )
        A.entry_product_id = C.Entry(
            product_id_field,
            textvariable=A.var_product_id,
            state="readonly",
            width=20,
        )
        A.entry_product_id.grid(row=1, column=0, sticky="ew")
        ean_value_field = C.Frame(ean_field, style="Card.TFrame")
        ean_value_field.grid(row=0, column=1, sticky="ew")
        ean_value_field.columnconfigure(0, weight=1)
        ean_value_field.columnconfigure(1, weight=0)
        N_ = C.Label(ean_value_field, text=EAN_OPTIONAL_LABEL, style="Form.TLabel")
        N_.grid(row=0, column=0, sticky="w", pady=(0, 2))
        A._add_tooltip(
            N_,
            LANG.get(
                "ean_tooltip",
                "13-cyfrowy kod EAN produktu. Jesli nie podany, zostanie uzyte 'BRAK-EAN'.",
            ),
        )
        ean_restore = C.Button(
            ean_value_field,
            text=LANG.get("field_restore_button", "Reset"),
            style="MiniOutline.TButton",
            width=6,
            command=lambda: A._restore_form_field_value("ean"),
            state=V,
        )
        ean_restore.grid(row=0, column=1, sticky="e", padx=(6, 0), pady=(0, 2))
        A._add_tooltip(
            ean_restore,
            LANG.get(
                "field_restore_tooltip",
                "Przywraca wartosc z ostatnio wczytanego wpisu.",
            ),
        )
        A.entry_ean = C.Entry(
            ean_value_field, textvariable=A.var_ean, state=X, width=22
        )
        A.entry_ean.grid(row=1, column=0, columnspan=2, sticky="ew")
        A.entry_ean.bind("<FocusIn>", A._remember_focus)
        A.entry_ean.bind("<FocusOut>", A._on_ean_focus_out)
        A.entry_ean.bind("<Return>", lambda _event: A._search_current_entry())
        A._register_form_field("ean", ean_value_field, N_, A.entry_ean, ean_restore)

        actions = C.Frame(form_card, style="Card.TFrame")
        actions.grid(row=3, column=2, columnspan=2, sticky="ew", padx=3, pady=(0, 2))
        for column_idx in Ax(4):
            actions.columnconfigure(column_idx, weight=1)

        A.btn_submit = C.Button(
            actions,
            text=UPDATE_LABEL,
            style="Accent.TButton",
            command=A._on_submit,
        )
        A.btn_submit.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 4))
        A.btn_search_entry = C.Button(
            actions,
            text=LANG.get("search_entry_button", "Wyszukaj"),
            style="Outline.TButton",
            command=A._search_current_entry,
        )
        A.btn_search_entry.grid(row=1, column=0, sticky="ew")
        A.btn_new_search = C.Button(
            actions,
            text=LANG.get("new_entry_button", "Wyczysc pola"),
            style="Outline.TButton",
            command=A._start_new_search,
        )
        A.btn_new_search.grid(row=1, column=1, sticky="ew", padx=6)
        A.btn_open = C.Button(
            actions,
            text=OPEN_FOLDER_LABEL,
            style="Outline.TButton",
            command=A._open_current_folder,
        )
        A.btn_open.grid(row=1, column=2, sticky="ew")
        A.btn_edit_lists = C.Button(
            actions,
            text=EDIT_LISTS_LABEL,
            style="Outline.TButton",
            command=A._open_list_editor,
        )
        A.btn_edit_lists.grid(row=1, column=3, sticky="ew")
        A.btn_settings = C.Button(
            actions,
            text=SETTINGS_LABEL,
            style="Outline.TButton",
            command=A._open_settings,
        )
        A.btn_settings.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 0))

        log_card = C.Frame(toolbar, style="Card.TFrame", padding=(10, 10))
        log_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        log_card.columnconfigure(0, weight=1)
        C.Label(
            log_card,
            text=LANG.get("activity_log_section", "Aktywnosc i log"),
            style="SectionTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        C.Label(
            log_card,
            text=LANG.get(
                "activity_log_hint_compact",
                "Postep, komunikaty FTP/SQL i bledy w jednym miejscu.",
            ),
            style="SectionHint.TLabel",
            wraplength=280,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(2, 6))
        A.btn_clear_log = C.Button(
            log_card,
            text=CLEAR_LOG_LABEL,
            style="Outline.TButton",
            command=lambda: A._ui_log(clear=Al),
        )
        A.btn_clear_log.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(10, 0))
        C.Label(
            log_card,
            textvariable=A._perf_status_var,
            style="Form.TLabel",
        ).grid(row=2, column=0, sticky="w")
        C.Label(
            log_card,
            textvariable=A._perf_detail_var,
            style="SectionHint.TLabel",
            wraplength=280,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(1, 2))
        C.Label(
            log_card,
            textvariable=A._busy_status_var,
            style="SectionHint.TLabel",
            wraplength=280,
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(0, 2))
        A._busy_progress = C.Progressbar(
            log_card,
            mode="indeterminate",
            style="Slot.TProgressbar",
        )
        A._busy_progress.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        A.ui_log = BS.ScrolledText(log_card, width=34, height=3, state=Ak, wrap="word")
        A.ui_log.grid(row=6, column=0, columnspan=2, sticky="nsew")
        A._configure_log_widget()
        log_card.rowconfigure(6, weight=1)

        A._slots_mount = C.Frame(A._app_shell, style="Card.TFrame", padding=(10, 10))
        A._slots_mount.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        A._slots_mount.columnconfigure(0, weight=1)
        A._slots_mount.rowconfigure(0, weight=1)

    def _build_form_field(
        A,
        parent,
        *,
        row,
        column,
        label_text,
        widget=I,
        widget_factory=I,
        tooltip_text=I,
        columnspan=1,
        field_key=I,
    ):
        field = C.Frame(parent, style="Card.TFrame")
        field.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="ew",
            padx=3,
            pady=(0, 4),
        )
        field.columnconfigure(0, weight=1)
        field.columnconfigure(1, weight=0)
        label = C.Label(field, text=label_text, style="Form.TLabel")
        label.grid(row=0, column=0, sticky="w", pady=(0, 2))
        if tooltip_text:
            A._add_tooltip(label, tooltip_text)
        restore_button = I
        if field_key:
            restore_button = C.Button(
                field,
                text=LANG.get("field_restore_button", "Reset"),
                style="MiniOutline.TButton",
                width=6,
                command=lambda key=field_key: A._restore_form_field_value(key),
                state=V,
            )
            restore_button.grid(row=0, column=1, sticky="e", padx=(6, 0), pady=(0, 2))
            A._add_tooltip(
                restore_button,
                LANG.get(
                    "field_restore_tooltip",
                    "Przywraca wartosc z ostatnio wczytanego wpisu.",
                ),
            )
        if widget_factory is not I:
            widget = widget_factory(field)
        if widget is not I:
            widget.grid(row=1, column=0, columnspan=2, sticky="ew")
        A._register_form_field(field_key, field, label, widget, restore_button)
        return field, widget

    def _build_form_combobox(
        A,
        parent,
        *,
        row,
        column,
        label_text,
        textvariable,
        values,
        state=X,
        tooltip_text=I,
        columnspan=1,
        width=18,
        field_key=I,
    ):
        _field, combo = A._build_form_field(
            parent,
            row=row,
            column=column,
            label_text=label_text,
            tooltip_text=tooltip_text,
            columnspan=columnspan,
            field_key=field_key,
            widget_factory=lambda field: C.Combobox(
                field,
                textvariable=textvariable,
                values=values,
                state=state,
                width=width,
            ),
        )
        return combo

    def _configure_log_widget(A):
        A.ui_log.configure(
            background=A._ui_colors["log_bg"],
            foreground=A._ui_colors["log_fg"],
            insertbackground=A._ui_colors["hero_text"],
            padx=12,
            pady=10,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#17323b",
            selectbackground="#2b5260",
            selectforeground=A._ui_colors["hero_text"],
        )

    def _build_slots(B):
        """Prepare the scrollable grid of drop targets used for images."""

        Q_ = "<Button-1>"
        R_ = B._ui_colors["slot_bg"]
        T_ = B._ui_colors["slot_border"]
        S_ = "<Configure>"
        mount = Aj(B, "_slots_mount", I)
        if not mount:
            return
        M_ = C.Frame(mount, style="Card.TFrame")
        M_.grid(row=0, column=0, sticky="nsew")
        M_.columnconfigure(0, weight=1)
        M_.rowconfigure(1, weight=1)
        B._slots_container = M_
        header = C.Frame(M_, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        C.Label(
            header,
            text=LANG.get("slots_section", "Sloty zdjec"),
            style="SectionTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        body = C.Frame(M_, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        A_ = F.Canvas(body, bg=B._ui_colors["card"], highlightthickness=0, bd=0)
        B._slots_canvas = A_
        def _on_scroll(*args):
            A_.yview(*args)

        T = C.Scrollbar(body, orient=An, command=_on_scroll)
        N_ = C.Frame(A_, style="Card.TFrame")
        N_.bind(S_, B._schedule_slots_canvas_refresh)
        Y = A_.create_window((0, 0), window=N_, anchor="nw")
        def _on_canvas_resize(e, cw=Y):
            A_.itemconfig(cw, width=e.width)
            B._schedule_slots_canvas_refresh()

        A_.bind(S_, _on_canvas_resize)
        A_.configure(yscrollcommand=T.set)
        A_.pack(side=Am, fill=z, expand=J)
        T.pack(side=AV, fill="y")
        B.slots_frame = N_
        B._slot_grid_columns = 0
        B.slots = []
        for G_, slot_def in A0(B.slot_definitions):
            V_ = slot_def["prefix"]
            W_ = slot_def["label"]
            H_ = F.Frame(
                B.slots_frame,
                highlightthickness=1,
                highlightbackground=T_,
                highlightcolor=T_,
                bg=B._ui_colors["card"],
                bd=0,
            )
            slot_title = SLOT_TITLE_FORMAT.format(
                index=V_, label=get_slot_label(W_)
            )
            title_label = C.Label(
                H_,
                text=slot_title,
                style="SlotTitle.TLabel",
                anchor="w",
            )
            title_label.pack(fill="x", padx=8, pady=(8, 0))
            E_ = F.Frame(
                H_,
                height=SLOT_PREVIEW_SIZE[1],
                bg=R_,
                highlightthickness=1,
                highlightbackground=T_,
                bd=0,
            )
            E_.pack_propagate(h)
            E_.pack(fill=z, expand=J, padx=8, pady=8)
            D_ = F.Label(
                E_,
                text=B._slot_placeholder_text,
                bg=R_,
                fg=B._ui_colors["muted"],
                justify="center",
                font=("Segoe UI", 9),
                wraplength=220,
            )
            D_.pack(fill=z, expand=J)
            if hasattr(D_, "drop_target_register") and hasattr(D_, "dnd_bind"):
                D_.drop_target_register(DND_ALL)
                D_.dnd_bind("<<Drop>>", lambda e, i=G_: B._on_drop(e, i))
            K_ = F.Label(
                E_,
                text=B._slot_remove_label,
                fg=AT,
                bg=B._ui_colors["danger"],
                padx=7,
                font=("Segoe UI Semibold", 8),
            )
            K_.bind(Q_, lambda e, i=G_: B._remove_file(i))
            K_.place(relx=0, rely=0, anchor="nw")
            K_.place_forget()
            X_ = F.Label(
                E_,
                text=B._slot_select_label,
                fg=AT,
                bg=B._ui_colors["hero"],
                padx=7,
                font=("Segoe UI Semibold", 8),
            )
            X_.bind(Q_, lambda e, i=G_: B._select_file(i))
            X_.place(relx=1.0, rely=0, anchor="ne")
            local_icon = F.Label(
                E_,
                text=LOCAL_ICON_LABEL,
                fg=AT,
                bg=B._ui_colors["slot_bg"],
                padx=6,
                pady=1,
                font=("Segoe UI Semibold", 7),
                bd=1,
                relief="flat",
                cursor="arrow",
            )
            local_icon.bind(Q_, lambda e, i=G_: B._set_slot_preview_source(i, "local"))
            local_icon.offset_x = -74
            local_icon.place(relx=1.0, rely=1.0, anchor="se", x=local_icon.offset_x)
            local_icon.place_forget()
            ftp_icon = F.Label(
                E_,
                text=FTP_ICON_LABEL,
                fg=AT,
                bg=B._ui_colors["slot_bg"],
                padx=6,
                pady=1,
                font=("Segoe UI Semibold", 7),
                bd=1,
                relief="flat",
                cursor="arrow",
            )
            ftp_icon.bind(Q_, lambda e, i=G_: B._set_slot_preview_source(i, "ftp"))
            ftp_icon.offset_x = -38
            ftp_icon.place(relx=1.0, rely=1.0, anchor="se", x=ftp_icon.offset_x)
            ftp_icon.place_forget()
            sql_icon = F.Label(
                E_,
                text=SQL_ICON_LABEL,
                fg=AT,
                bg=B._ui_colors["slot_bg"],
                padx=6,
                pady=1,
                font=("Segoe UI Semibold", 7),
            )
            sql_icon.bind(Q_, lambda e, i=G_: B._copy_slot_sql_url(i))
            B._add_tooltip(
                sql_icon,
                LANG.get(
                    "slot_sql_copy_tooltip",
                    "Kliknij, aby skopiować URL obrazu SQL do schowka.",
                ),
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
            footer.pack(fill="x", padx=8, pady=(0, 8))
            status_label = C.Label(
                footer,
                text=B._slot_status["empty"],
                style="SlotStatus.TLabel",
                anchor="w",
            )
            status_label.pack(fill="x")
            sql_link = F.Label(
                footer,
                text=B,
                fg=B._ui_colors["hero"],
                bg=B._ui_colors["card"],
                cursor="hand2",
                anchor="w",
                justify="left",
                wraplength=SLOT_PREVIEW_SIZE[0] - 16,
                font=("Segoe UI", 8, "underline"),
            )
            sql_link.bind(Q_, lambda e, i=G_: B._copy_slot_sql_url(i))
            B._add_tooltip(
                sql_link,
                LANG.get(
                    "slot_sql_copy_tooltip",
                    "Kliknij, aby skopiować URL obrazu SQL do schowka.",
                ),
            )
            sql_link.pack(fill="x", pady=(2, 0))
            sql_link.pack_forget()
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
                    "sql_link": sql_link,
                    "sql_url": B,
                    "sql_presence_unknown": h,
                    "status_label": status_label,
                    "progress": I,
                    f: I,
                    "local_path": I,
                    "ftp_path": I,
                    "preview_path": I,
                    "preview_source": B,
                    AS: H_,
                    B0: I,
                }
            )
        B._apply_slot_grid()
        B._bind_slot_scroll_target(A_)
        B._bind_slot_scroll_target(N_)
        B.after_idle(B._schedule_slots_canvas_refresh)
        B._update_dashboard_summary()

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
        B._reset_product_state()
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
        token = B._next_thumbnail_token()
        B._thumb_tokens[idx] = token
        _cache_key, thumb = B._get_cached_thumbnail(path)
        if thumb is not I:
            B._set_slot_preview(idx, path, thumb)
            return
        B._thumb_request_queue.put((idx, path, token))

    def _build_slot_target_filename(
        B,
        idx,
        ean,
        name,
        type_value,
        model,
        color_values,
        extra_value,
        src_path,
        *,
        convert_tif_enabled=h,
        target_ext=B,
    ):
        """Return the final output filename for a slot and source file."""

        return svc_build_slot_target_filename(
            B.slots,
            idx,
            ean,
            name,
            type_value,
            model,
            color_values,
            extra_value,
            src_path,
            convert_tif_enabled=convert_tif_enabled,
            target_ext=target_ext,
        )

    def _build_expected_remote_filename(
        B,
        idx,
        ean,
        src_path,
        *,
        convert_tif_enabled=h,
        target_ext=B,
    ):
        """Return the canonical remote FTP name for a slot output."""

        return svc_build_expected_remote_filename(
            B.slots,
            idx,
            ean,
            src_path,
            convert_tif_enabled=convert_tif_enabled,
            target_ext=target_ext,
        )

    def _get_slot_sql_url(A, idx, state=I):
        """Return the raw SQL value stored for the slot, when available."""

        if idx < 0 or idx >= Q(A.slots):
            return B
        if state is I:
            state = A._product_state
        if not isinstance(state, ProductState):
            return B
        slot_prefix = A.slots[idx][Aa]
        return G(state.sql_values.get(slot_prefix) or B).strip()

    def _refresh_slot_sql_ui(A, idx, *, present=I, state=I):
        """Refresh the SQL badge and URL link for a slot."""

        if idx < 0 or idx >= Q(A.slots):
            return
        if state is I:
            state = A._product_state
        slot = A.slots[idx]
        slot_prefix = slot[Aa]
        if (
            present is I
            and not slot.get("sql_presence_unknown")
            and isinstance(state, ProductState)
            and isinstance(state.sql_presence, dict)
        ):
            present = state.sql_presence.get(slot_prefix, h)
        url = B
        if present is J:
            url = A._get_slot_sql_url(idx, state=state)
        slot["sql_url"] = url
        sql_link = slot.get("sql_link")
        if sql_link:
            if url:
                sql_link.configure(text=url)
                if not sql_link.winfo_manager():
                    sql_link.pack(fill="x", pady=(2, 0))
            else:
                sql_link.configure(text=B)
                if sql_link.winfo_manager():
                    sql_link.pack_forget()
        sql_icon = slot.get("sql_icon")
        if sql_icon:
            A._set_icon_status(sql_icon, present, clickable=bool(url))
            try:
                sql_icon.configure(cursor="hand2" if url else "arrow")
            except E:
                pass

    def _refresh_all_slot_sql_ui(A):
        """Refresh SQL link controls for every visible slot."""

        for idx in Ax(Q(Aj(A, "slots", []))):
            A._refresh_slot_sql_ui(idx)

    def _copy_slot_sql_url(A, idx):
        """Copy the current SQL image URL for the slot to the clipboard."""

        if idx < 0 or idx >= Q(A.slots):
            return
        slot = A.slots[idx]
        url = G(slot.get("sql_url") or B).strip()
        if not url:
            url = A._get_slot_sql_url(idx)
            slot["sql_url"] = url
        if not url:
            return
        try:
            A.clipboard_clear()
            A.clipboard_append(url)
            A.update_idletasks()
        except E as exc:
            log_error_loc("sql_url_copy_failed", error=exc)
            return
        log_info_loc("sql_url_copied", url=url)

    def _list_remote_filenames(B, ftp_conn):
        """Return remote file names using the most compatible FTP listing method."""

        return svc_list_remote_filenames(ftp_conn)

    def _seed_metadata_migration(
        B,
        output_dir,
        ean,
        name,
        type_value,
        model,
        color_values,
        extra_value,
        *,
        convert_tif_enabled=h,
        target_ext=B,
    ):
        """Prepare loaded files for a metadata correction without manual renaming."""

        if not B._preserve_loaded_binding():
            return 0
        return svc_seed_metadata_migration(
            B._product_state,
            B.slots,
            l,
            output_dir,
            ean,
            name,
            type_value,
            model,
            color_values,
            extra_value,
            convert_tif_enabled=convert_tif_enabled,
            target_ext=target_ext,
        )

    def _get_slot_existing_remote_filename(A, slot_prefix):
        """Return the current short remote name for a slot when it can be inferred."""

        return svc_infer_existing_remote_filename(A._product_state, slot_prefix)

    def _load_slot_thumbnail(B, path):
        cache_key, thumb = B._get_cached_thumbnail(path)
        if thumb is not I:
            return thumb
        try:
            with AA.open(path) as img:
                img.thumbnail(SLOT_PREVIEW_SIZE, LANCZOS_FILTER)
                thumb = img.copy()
            B._store_cached_thumbnail(cache_key, thumb)
            return thumb
        except E:
            return I

    def _same_path(C, left, right):
        if not (left and right):
            return h
        try:
            return A.path.samefile(left, right)
        except E:
            return A.path.normcase(A.path.normpath(left)) == A.path.normcase(
                A.path.normpath(right)
            )

    def _get_slot_preview_path(B, slot):
        return slot.get("preview_path") or slot.get(f)

    def _resolve_slot_preview_source(C, slot, preferred_source=""):
        if preferred_source == "ftp" and slot.get("ftp_path"):
            return "ftp", slot.get("ftp_path")
        if preferred_source == "local" and slot.get("local_path"):
            return "local", slot.get("local_path")
        ftp_path = slot.get("ftp_path")
        if ftp_path:
            return "ftp", ftp_path
        local_path = slot.get("local_path") or slot.get(f)
        if local_path:
            return "local", local_path
        return B, I

    def _set_slot_paths(
        C,
        idx,
        *,
        working_path=I,
        local_path=I,
        ftp_path=I,
        preferred_preview="",
    ):
        if idx < 0 or idx >= Q(C.slots):
            return
        slot = C.slots[idx]
        slot[f] = working_path
        slot["local_path"] = local_path
        slot["ftp_path"] = ftp_path
        preview_source, preview_path = C._resolve_slot_preview_source(
            slot,
            preferred_source=preferred_preview,
        )
        slot["preview_source"] = preview_source
        slot["preview_path"] = preview_path
        C._refresh_slot_source_icons(idx)

    def _get_state_slot_ftp_path(B, state, slot_prefix):
        if not isinstance(state, ProductState):
            return I
        info = state.ftp_preview_files.get(slot_prefix) or state.ftp_remote_only.get(
            slot_prefix
        )
        if isinstance(info, dict):
            return info.get("temp_path")
        return I

    def _resolve_state_slot_local_path(B, slot_prefix, working_path, state):
        if not (working_path and A.path.isfile(working_path)):
            return I
        ftp_path = B._get_state_slot_ftp_path(state, slot_prefix)
        if isinstance(state, ProductState) and slot_prefix in state.original_files:
            return working_path
        if ftp_path and B._same_path(working_path, ftp_path):
            return I
        return working_path

    def _refresh_slot_source_icons(C, idx):
        if idx < 0 or idx >= Q(C.slots):
            return
        slot = C.slots[idx]
        local_path = slot.get("local_path")
        ftp_path = slot.get("ftp_path")
        has_any_source = bool(slot.get(f) or local_path or ftp_path)
        preview_source = slot.get("preview_source")
        C._set_icon_status(
            slot.get("local_icon"),
            J if local_path else (I if not has_any_source else h),
            selected=bool(local_path and preview_source == "local"),
            clickable=bool(local_path),
        )
        C._set_icon_status(
            slot.get("ftp_icon"),
            J if ftp_path else (I if not has_any_source else h),
            selected=bool(ftp_path and preview_source == "ftp"),
            clickable=bool(ftp_path),
        )

    def _apply_lookup_slot_result(
        A,
        idx,
        state,
        local_slot_paths,
        slot_paths,
        *,
        preferred_preview="",
    ):
        """Apply lookup paths to a clean slot after async loading finishes."""

        if idx < 0 or idx >= Q(A.slots):
            return
        slot = A.slots[idx]
        slot_prefix = slot[Aa]
        working_path = slot_paths.get(slot_prefix)
        local_path = local_slot_paths.get(slot_prefix)
        ftp_path = A._get_state_slot_ftp_path(state, slot_prefix)
        if working_path or local_path or ftp_path:
            A._set_slot_paths(
                idx,
                working_path=working_path,
                local_path=local_path,
                ftp_path=ftp_path,
                preferred_preview=preferred_preview,
            )
            A._display_slot_preview(idx)
            A._mark_slot(idx, A4)
        else:
            A._clear_slot_preview(idx)
            A._mark_slot(idx, I)
        if isinstance(state.sql_presence, dict):
            slot["sql_presence_unknown"] = h
            A._refresh_slot_sql_ui(
                idx,
                present=state.sql_presence.get(slot_prefix, h),
                state=state,
            )
        else:
            slot["sql_presence_unknown"] = h
            A._refresh_slot_sql_ui(idx, present=I, state=state)

    def _preserve_modified_slot_after_lookup(A, idx, state):
        """Keep the current slot preview when the user changed it during lookup."""

        if idx < 0 or idx >= Q(A.slots):
            return
        slot = A.slots[idx]
        slot_prefix = slot[Aa]
        if idx in A.pending_additions:
            working_path = slot.get(f)
            if working_path and not slot.get("local_path"):
                slot["local_path"] = working_path
            ftp_path = A._get_state_slot_ftp_path(state, slot_prefix)
            if ftp_path:
                slot["ftp_path"] = ftp_path
            if not slot.get("preview_path") and working_path:
                slot["preview_source"] = "local"
                slot["preview_path"] = working_path
                A._display_slot_preview(idx)
            else:
                A._refresh_slot_source_icons(idx)
                A._update_slot_activity(idx, active=h)
        else:
            A._update_slot_activity(idx, active=h)
        slot["sql_presence_unknown"] = J
        A._refresh_slot_sql_ui(idx, present=I, state=state)
        A._mark_slot(idx, AR)

    def _prime_slot_preview(C, idx, path):
        if idx < 0 or idx >= Q(C.slots):
            return
        slot = C.slots[idx]
        if C._get_slot_preview_path(slot) != path:
            return
        slot[y].configure(text=A.path.basename(path), image="")
        slot[y].image = I
        slot[A7].place(x=0, y=0)

    def _display_slot_preview(C, idx):
        if idx < 0 or idx >= Q(C.slots):
            return
        slot = C.slots[idx]
        preview_path = C._get_slot_preview_path(slot)
        if not preview_path:
            C._clear_slot_preview(idx)
            return
        C._refresh_slot_source_icons(idx)
        C._update_slot_activity(idx, active=J, status=C._slot_status["loading"])
        C._prime_slot_preview(idx, preview_path)
        C._queue_thumbnail(idx, preview_path)

    def _clear_slot_preview(C, idx):
        if idx < 0 or idx >= Q(C.slots):
            return
        slot = C.slots[idx]
        slot[f] = I
        slot["local_path"] = I
        slot["ftp_path"] = I
        slot["preview_path"] = I
        slot["preview_source"] = B
        slot["sql_url"] = B
        slot[y].configure(image=B, text=C._slot_placeholder_text)
        slot[y].image = I
        slot[A7].place_forget()
        sql_link = slot.get("sql_link")
        if sql_link and sql_link.winfo_manager():
            sql_link.pack_forget()
        C._thumb_tokens.pop(idx, I)
        C._refresh_slot_source_icons(idx)
        C._update_slot_activity(idx, active=h)

    def _set_slot_preview_source(C, idx, source):
        if idx < 0 or idx >= Q(C.slots):
            return
        slot = C.slots[idx]
        preview_source, preview_path = C._resolve_slot_preview_source(
            slot,
            preferred_source=source,
        )
        if not preview_path:
            C._refresh_slot_source_icons(idx)
            return
        slot["preview_source"] = preview_source
        slot["preview_path"] = preview_path
        C._display_slot_preview(idx)

    def _set_slot_preview(B, idx, path, thumb):
        if idx < 0 or idx >= Q(B.slots):
            return
        slot = B.slots[idx]
        if B._get_slot_preview_path(slot) != path:
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

    def _set_icon_status(C, icon, present, *, selected=h, clickable=h):
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
                icon.config(bg=C._ui_colors["warning"] if hasattr(C, "_ui_colors") else "#555555")
            else:
                icon.place_forget()
            try:
                icon.config(cursor="arrow", relief="flat")
            except E:
                pass
            return
        icon.place(relx=1.0, rely=1.0, anchor="se", x=getattr(icon, "offset_x", 0))
        if hasattr(C, "_ui_colors"):
            if present:
                bg = C._ui_colors["accent"] if selected else C._ui_colors["hero"]
            else:
                bg = C._ui_colors["danger"]
        else:
            bg = "green" if present else "red"
        try:
            icon.config(
                bg=bg,
                relief="sunken" if (present and selected) else "flat",
                cursor="hand2" if (present and clickable) else "arrow",
            )
        except E:
            icon.config(bg=bg)

    def _get_slot_idle_status(B, idx):
        slot = B.slots[idx]
        if slot.get(f) or slot.get("local_path") or slot.get("ftp_path"):
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
                progress.stop()
                progress.configure(mode="determinate", value=100 if active_state else 0)

        if threading.current_thread() == threading.main_thread():
            _apply()
            return
        try:
            B.after(0, _apply)
        except E:
            _apply()

    def _update_all_slot_activity(B, active=h, status=I):
        for idx in Ax(Q(B.slots)):
            B._update_slot_activity(idx, active=active, status=status)

    def _should_check_sql_presence(A):
        """Return True when database credentials are configured for lookups."""

        return svc_should_check_presence(config.CONFIG)

    def _extract_sql_presence_context(A, ean):
        """Return the table name and WHERE clause used for SQL presence checks."""

        context = svc_extract_presence_context(config.CONFIG, ean)
        if not context:
            log_error_loc("sql_presence_table_parse_failed")
        return context

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

    def _query_sql_presence_map(A, columns, table, where_clause, db_type):
        """Fetch SQL presence for all mapped columns, batching when possible."""

        return svc_query_presence_map(columns, table, where_clause, db_type)

    def _query_sql_presence_details(A, columns, table, where_clause, db_type):
        """Fetch SQL presence flags together with raw SQL values."""

        return svc_query_presence_details(columns, table, where_clause, db_type)

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
            C._cancel_existing_lookup()
            return
        if C._commit_matches_snapshot("name", C._normalize_entry_part(D_)):
            return
        preserve_loaded = C._preserve_loaded_binding()
        preserved_type = C.var_type.get()
        preserved_model = C.var_model.get()
        preserved_color1 = C.var_color1.get()
        preserved_color2 = C.var_color2.get()
        preserved_color3 = C.var_color3.get()
        preserved_extra = C.var_extra.get()
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
        E_, path_exists = C._resolve_types_for_name(D_, F)
        C.combo_name.configure(style=Z if path_exists else j)
        remaining_types = [A for A in C.lists[t] if A not in E_]
        C._refresh_combobox_list(C.combo_type, E_ + remaining_types, existing_count=Q(E_))
        C.combo_type.configure(state=X)
        if preserve_loaded:
            C.var_type.set(preserved_type)
            C.var_model.set(preserved_model)
            C.var_color1.set(preserved_color1)
            C.var_color2.set(preserved_color2)
            C.var_color3.set(preserved_color3)
            C.var_extra.set(preserved_extra)
        else:
            C.var_type.set(B)
            C.var_model.set(B)
            C.var_color1.set(B)
            C.var_color2.set(B)
            C.var_color3.set(B)
            C.var_extra.set(B)
        if not preserve_loaded:
            C._clear_loaded_entry_context()
        else:
            C._last_lookup_signature = None
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
            G_.configure(state=X)
        C.btn_submit.configure(state=X)
        C.btn_open.configure(state=V)
        C.entry_ean.configure(state=X)
        C._refresh_commit_snapshot()
        if not preserve_loaded:
            C._clear_all_slots()
        C._refresh_existing_files_lookup_for_form_edit()

    def _on_type_commit(C):
        """React to type changes by unlocking model/colour comboboxes."""

        G_ = C.var_name.get().strip()
        D_ = C.var_type.get().strip()
        if not G_ or not D_:
            C._cancel_existing_lookup()
            return
        if C._commit_matches_snapshot("type", C._normalize_entry_part(D_)):
            return
        preserve_loaded = C._preserve_loaded_binding()
        preserved_model = C.var_model.get()
        preserved_color1 = C.var_color1.get()
        preserved_color2 = C.var_color2.get()
        preserved_color3 = C.var_color3.get()
        preserved_extra = C.var_extra.get()
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
        E_, path_exists = C._resolve_models_for_type(G_, D_, F)
        C.combo_type.configure(style=Z if path_exists else j)
        remaining_models = [A for A in C.lists[s] if A not in E_]
        C._refresh_combobox_list(C.combo_model, E_ + remaining_models, existing_count=Q(E_))
        C.combo_model.configure(state=X)
        if preserve_loaded:
            C.var_model.set(preserved_model)
            C.var_color1.set(preserved_color1)
            C.var_color2.set(preserved_color2)
            C.var_color3.set(preserved_color3)
            C.var_extra.set(preserved_extra)
        else:
            C.var_model.set(B)
            C.var_color1.set(B)
            C.var_color2.set(B)
            C.var_color3.set(B)
            C.var_extra.set(B)
        if not preserve_loaded:
            C._clear_loaded_entry_context()
        else:
            C._last_lookup_signature = None
        for J_ in (C.combo_color1, C.combo_color2, C.combo_color3, C.combo_extra):
            J_.configure(style=j, state=X)
        C.btn_submit.configure(state=X)
        C.btn_open.configure(state=V)
        C.entry_ean.configure(state=X)
        C._refresh_commit_snapshot()
        if not preserve_loaded:
            C._clear_all_slots()
        C._refresh_existing_files_lookup_for_form_edit()

    def _load_existing_files(C, force=h):
        """Load images from disk and check FTP copies without blocking GUI."""

        if C.suppress_next_lookup:
            C.suppress_next_lookup = h
            return
        if C._load_existing_after_id is not I:
            try:
                C.after_cancel(C._load_existing_after_id)
            except E:
                pass
            C._load_existing_after_id = I
        lookup_signature = C._current_lookup_signature()
        if not force and lookup_signature == C._last_lookup_signature:
            return
        C._load_existing_request_id += 1
        request_id = C._load_existing_request_id
        started_at = Ag.perf_counter()
        state_snapshot = C._snapshot_product_state()
        C.logged_counts = h
        name_value = C.var_name.get().strip()
        type_value = C.var_type.get().strip()
        model_value = C.var_model.get().strip()
        color_values = normalize_color_slots(
            (
                C.var_color1.get(),
                C.var_color2.get(),
                C.var_color3.get(),
            )
        )
        extra_raw = C.var_extra.get()
        if isinstance(extra_raw, dict):
            extra_raw = B
        extra_value = normalize_extra_segment(extra_raw, default=L)
        current_ean = C.var_ean.get().strip()
        product_dir = build_product_directory(
            l,
            name_value,
            type_value,
            model_value,
            color_values,
            extra_value,
        )
        if extra_value.upper() == L and not A.path.isdir(product_dir):
            c_ = A.path.join(A.path.dirname(product_dir), L)
            if A.path.isdir(c_):
                try:
                    A.rename(c_, product_dir)
                except E as T:
                    log_error_loc("rename_no_led_failed", error=T)
        def finalize_empty(rid):
            if rid != C._load_existing_request_id:
                return
            if not (C._preserve_loaded_binding() and any(slot.get(f) for slot in C.slots)):
                if not C._has_modified_slots():
                    C._reset_product_state()
                    C._clear_all_slots()
            C._last_lookup_signature = lookup_signature
            C._last_lookup_duration_ms = int(
                (Ag.perf_counter() - started_at) * 1000
            )
            C._queue_dashboard_refresh()

        if not A.path.isdir(product_dir):
            C.after(0, lambda rid=request_id: finalize_empty(rid))
            return
        with C._existing_lookup_lock:
            if C._existing_lookup_running:
                C._retry_existing_lookup = J
                return
            C._existing_lookup_running = J
            C._existing_lookup_active_request_id = request_id
            if not C._existing_lookup_busy:
                C._existing_lookup_busy = J
                C._set_busy_state(
                    LANG.get("busy_loading_product", "Wczytywanie danych produktu"),
                    active=J,
                )
        C._update_all_slot_activity(active=J, status=C._slot_status["loading"])

        def apply_local_results(
            worker_state,
            slot_paths,
            ean_guess,
            rid,
        ):
            if rid != C._load_existing_request_id:
                return
            if ean_guess and C.var_ean.get().strip() == B:
                C.suppress_next_lookup = J
                C.var_ean.set(ean_guess)
                C.suppress_next_lookup = h
            partial_state = worker_state.clone()
            partial_state.ftp_presence.clear()
            partial_state.ftp_preview_files.clear()
            partial_state.ftp_remote_only.clear()
            partial_state.sql_presence = I
            partial_state.sql_values.clear()
            partial_state.ftp_downloaded_final = set()
            dirty_slots = C._get_modified_slot_indices()
            slot_prefix_by_index = {
                idx: slot[Aa] for idx, slot in A0(C.slots)
            }
            partial_state = merge_product_lookup_state(
                C._product_state,
                partial_state,
                slot_prefix_by_index,
            )
            C._commit_product_state(partial_state)
            for X_, G_ in A0(C.slots):
                if X_ in dirty_slots:
                    C._preserve_modified_slot_after_lookup(X_, partial_state)
                    continue
                C._apply_lookup_slot_result(
                    X_,
                    partial_state,
                    slot_paths,
                    slot_paths,
                    preferred_preview="local",
                )
            C._queue_dashboard_refresh()

        def worker():
            worker_state = state_snapshot.clone()
            try:
                V_ = C._resolve_product_file_rows(
                    product_dir,
                    name_value,
                    type_value,
                    model_value,
                    color_values,
                    extra_value,
                )
                worker_state.original_files.clear()
                slot_paths = {}
                ean_guess = I
                if V_:
                    parsed = parse_slot_filename(V_[0][0])
                    if parsed and current_ean == B:
                        ean_guess = parsed.ean
                for W_, d_ in V_:
                    parsed = parse_slot_filename(W_)
                    if not parsed:
                        continue
                    norm_label = parsed.normalized_label
                    if parsed.normalized_name:
                        normalized_name = parsed.normalized_name
                        normalized_path = A.path.join(product_dir, normalized_name)
                        try:
                            A.rename(d_, normalized_path)
                            log_info_loc("file_renamed", old=W_, new=normalized_name)
                            W_ = normalized_name
                            d_ = normalized_path
                        except E as T:
                            log_error_loc(
                                "file_rename_error", old=W_, new=normalized_name, error=T
                            )
                    worker_state.original_files[norm_label] = W_
                    slot_paths[norm_label] = d_
                local_slot_paths = dict(slot_paths)
                try:
                    C.after(
                        0,
                        lambda rid=request_id: apply_local_results(
                            worker_state.clone(),
                            local_slot_paths,
                            ean_guess,
                            rid,
                        ),
                    )
                except E:
                    pass
                worker_state.ftp_presence.clear()
                worker_state.ftp_preview_files.clear()
                worker_state.ftp_remote_only.clear()
                worker_state.sql_presence = I
                worker_state.sql_values.clear()
                K_ = current_ean or G(ean_guess or B).strip()
                if K_ and Q(K_) == 13 and K_.isdigit() and K_.upper() != q:
                    remote_files = {}
                    try:
                        (
                            remote_files,
                            ftp_presence,
                            ftp_preview_files,
                            ftp_remote_only,
                        ) = svc_download_remote_slots(
                            D[H],
                            K_,
                            slot_paths,
                            C._slot_index_by_prefix,
                            temp_root=A.path.join(
                                tempfile.gettempdir(),
                                f"picorgftp_sql_{request_id}",
                            ),
                            status_callback=lambda idx, status: C._update_slot_activity(
                                idx,
                                active=J,
                                status=C._slot_status.get(status, status),
                            )
                            if idx is not I and request_id == C._load_existing_request_id
                            else I,
                        )
                        worker_state.ftp_presence.update(ftp_presence)
                        worker_state.ftp_preview_files.update(ftp_preview_files)
                        worker_state.ftp_remote_only.update(ftp_remote_only)
                        for label, info in ftp_remote_only.items():
                            slot_paths[label] = info["temp_path"]
                    except E as T:
                        log_error_loc("ftp_check_error", ean=K_, error=T)
                    if not C.logged_counts:
                        log_info_loc(
                            "found_images_counts",
                            local=Q(worker_state.original_files),
                            ftp=Q(remote_files),
                        )
                        C.logged_counts = J
                    if svc_should_check_presence(config.CONFIG):
                        columns = []
                        for slot in C.slots:
                            prefix = slot[Aa]
                            label = slot["label"]
                            column_name = C._resolve_sql_column(
                                prefix, label, log_missing=J
                            )
                            columns.append((prefix, column_name, label))
                        context = svc_extract_presence_context(config.CONFIG, K_)
                        if context:
                            table, where_clause = context
                            db_type = config.CONFIG.get(p, K).lower()
                            try:
                                (
                                    worker_state.sql_presence,
                                    worker_state.sql_values,
                                ) = C._query_sql_presence_details(
                                    columns, table, where_clause, db_type
                                )
                            except E as T:
                                worker_state.sql_presence = I
                                worker_state.sql_values.clear()
                                log_error_loc("sql_check_error", ean=K_, error=T)
                try:
                    C.after(
                        0,
                        lambda rid=request_id: finalize(
                            worker_state,
                            local_slot_paths,
                            slot_paths,
                            ean_guess,
                            rid,
                        ),
                    )
                except E:
                    C._finish_existing_lookup(request_id=request_id)
            except E:
                log_error(traceback.format_exc())
                try:
                    C.after(0, lambda rid=request_id: finalize_lookup_error(rid))
                except E:
                    C._finish_existing_lookup(request_id=request_id)

        def finalize(
            worker_state,
            local_slot_paths,
            slot_paths,
            ean_guess,
            rid,
        ):
            try:
                if rid != C._load_existing_request_id:
                    return
                if ean_guess and C.var_ean.get().strip() == B:
                    C.suppress_next_lookup = J
                    C.var_ean.set(ean_guess)
                    C.suppress_next_lookup = h
                dirty_slots = C._get_modified_slot_indices()
                slot_prefix_by_index = {
                    idx: slot[Aa] for idx, slot in A0(C.slots)
                }
                merged_state = merge_product_lookup_state(
                    C._product_state,
                    worker_state,
                    slot_prefix_by_index,
                )
                merged_state.ftp_downloaded_final = set()
                C._commit_product_state(merged_state)
                for X_, G_ in A0(C.slots):
                    if X_ in dirty_slots:
                        C._preserve_modified_slot_after_lookup(X_, merged_state)
                        continue
                    C._apply_lookup_slot_result(
                        X_,
                        merged_state,
                        local_slot_paths,
                        slot_paths,
                        preferred_preview="ftp",
                    )
                C._last_lookup_signature = lookup_signature
                C._last_lookup_duration_ms = int(
                    (Ag.perf_counter() - started_at) * 1000
                )
                C._queue_dashboard_refresh()
            finally:
                C._finish_existing_lookup(request_id=rid)

        def finalize_lookup_error(rid):
            try:
                if rid != C._load_existing_request_id:
                    return
                C._update_all_slot_activity(active=h)
                C._queue_dashboard_refresh()
            finally:
                C._finish_existing_lookup(request_id=rid)

        threading.Thread(target=worker, daemon=J).start()

    def _on_model_commit(D):
        H = "new"
        o = D.var_name.get().strip()
        p = D.var_type.get().strip()
        e_ = D.var_model.get().strip()
        if not o or not p or not e_:
            D._cancel_existing_lookup()
            return
        if D._commit_matches_snapshot("model", D._normalize_entry_part(e_)):
            return
        preserve_loaded = D._preserve_loaded_binding()
        preserved_color1 = D.var_color1.get()
        preserved_color2 = D.var_color2.get()
        preserved_color3 = D.var_color3.get()
        preserved_extra = D.var_extra.get()
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
        A0_, model_path_exists = D._resolve_colors_for_model(o, p, e_, T)
        D.combo_model.configure(style=Z if model_path_exists else j)
        r = [A_ for A_ in A0_ if g not in A_]
        A8_ = [A_ for A_ in D.lists[Y] if A_ not in r]
        A9_ = r + A8_
        D._refresh_combobox_list(D.combo_color1, A9_, existing_count=Q(r))
        D.combo_color2[S] = D.lists[Y]
        D.combo_color3[S] = D.lists[Y]
        for AA_ in (D.combo_color1, D.combo_color2, D.combo_color3):
            AA_.configure(state=X)
        if preserve_loaded:
            D.var_color1.set(preserved_color1)
            D.var_color2.set(preserved_color2)
            D.var_color3.set(preserved_color3)
            D.var_extra.set(preserved_extra)
        else:
            D.var_color1.set(B)
            D.var_color2.set(B)
            D.var_color3.set(B)
            D.var_extra.set(B)
        if not preserve_loaded:
            D._clear_loaded_entry_context()
        else:
            D._last_lookup_signature = I
        D.combo_extra.configure(style=j, state=X)
        D.btn_submit.configure(state=X)
        D.btn_open.configure(state=V)
        D._refresh_commit_snapshot()
        if not preserve_loaded:
            D._clear_all_slots()
        D._refresh_existing_files_lookup_for_form_edit()
        if not (D.loading_by_ean or D.suppress_scan or preserve_loaded):
            k_ = []
            A0_, model_path_exists = D._resolve_colors_for_model(o, p, e_, T)
            if model_path_exists:
                for A2 in A0_:
                    t_ = A.path.join(T, A2)
                    f_ = A2.split(g)
                    a_ = f_[0] if Q(f_) > 0 else B
                    K__ = f_[1] if Q(f_) > 1 else B
                    M__ = f_[2] if Q(f_) > 2 else B
                    extras_for_color, _extras_path_exists = D._resolve_extras_for_colors(
                        o,
                        p,
                        e_,
                        (a_, K__, M__),
                        t_,
                    )
                    for A3 in extras_for_color:
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
                    H_, extras_path_exists = D._resolve_extras_for_colors(
                        o,
                        p,
                        e_,
                        (a_, K__, M__),
                        c_,
                    )
                    D.combo_color1.configure(style=Z if extras_path_exists else j)
                    if K__:
                        D.combo_color2.configure(style=Z if extras_path_exists else j)
                    if M__:
                        D.combo_color3.configure(style=Z if extras_path_exists else j)
                    AK_ = [A_ for A_ in D.lists[d] if A_ not in H_]
                    if L in H_ and L not in H_:
                        try:
                            A.rename(A.path.join(c_, L), A.path.join(c_, L))
                        except E as AL_:
                            log_error_loc("rename_no_led_failed", error=AL_)
                        H_, _extras_path_exists = D._resolve_extras_for_colors(
                            o,
                            p,
                            e_,
                            (a_, K__, M__),
                            c_,
                        )
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
                    if R_ in D.entries:
                        loaded_record = dict(D.entries.get(R_, {}))
                        loaded_record[EAN_HEADER] = R_
                        D._set_loaded_entry_context(loaded_record)
                    else:
                        D._clear_loaded_entry_context(keep_ean=J)
                    D.combo_extra.configure(
                        style=Z if N_ in H_ or N_ == L and L in H_ else j
                    )
                    D.combo_model.configure(style=Z)
                    D.combo_color1.configure(style=Z)
                    if K__:
                        D.combo_color2.configure(style=Z)
                    if M__:
                        D.combo_color3.configure(style=Z)
                    D._refresh_commit_snapshot()
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
        H_, F_, G_ = C._normalize_color_vars()
        if not M_ or not N_ or not H_:
            C._cancel_existing_lookup()
            return
        color_signature = (
            C._normalize_entry_part(H_),
            C._normalize_entry_part(F_),
            C._normalize_entry_part(G_),
        )
        if C._commit_matches_snapshot("colors", color_signature):
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
        I_ = build_product_directory(
            l,
            M_,
            N_,
            C.var_model.get().strip(),
            K_,
            C.var_extra.get().strip(),
        )
        D_, extras_path_exists = C._resolve_extras_for_colors(
            M_,
            N_,
            C.var_model.get().strip(),
            K_,
            I_,
        )
        if L in D_ and L not in D_:
            try:
                A.rename(A.path.join(I_, L), A.path.join(I_, L))
            except E as a_:
                log_error_loc("rename_no_led_failed", error=a_)
            D_, extras_path_exists = C._resolve_extras_for_colors(
                M_,
                N_,
                C.var_model.get().strip(),
                K_,
                I_,
            )
        if L in D_:
            D_[D_.index(L)] = L
        C.combo_color1.configure(style=Z if extras_path_exists else j)
        if F_:
            C.combo_color2.configure(style=Z if extras_path_exists else j)
        if G_:
            C.combo_color3.configure(style=Z if extras_path_exists else j)
        b_ = [A for A in C.lists[d] if A not in D_]
        C._refresh_combobox_list(C.combo_extra, D_ + b_, existing_count=Q(D_))
        C.combo_extra.configure(state=X)
        C.entry_ean.configure(state=X)
        C.btn_submit.configure(state=X)
        C.btn_open.configure(state=X)
        extra_raw = C.var_extra.get()
        C.var_extra.set(G(extra_raw).strip())
        C._refresh_commit_snapshot()
        C._refresh_existing_files_lookup_for_form_edit()

    def _on_extra_commit(C):
        D_ = C.var_extra.get().strip()
        G_ = C.var_name.get().strip()
        H_ = C.var_type.get().strip()
        I_ = C.var_model.get().strip()
        F_ = C.var_color1.get().strip()
        J_ = C.var_color2.get().strip()
        K_ = C.var_color3.get().strip()
        if C._commit_matches_snapshot(
            "extra",
            C._normalize_entry_part(D_, extra=J),
        ):
            return
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
            E_ = build_product_directory(
                l,
                G_,
                H_,
                I_,
                [F_, J_, K_],
                D_,
            )
            if A.path.isdir(E_):
                C.combo_extra.configure(style=Z)
            else:
                C.combo_extra.configure(style=j)
        C._refresh_commit_snapshot()
        C._refresh_existing_files_lookup_for_form_edit()

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
                    C._clear_slot_preview(D_)
                    C.slots[D_]["sql_presence_unknown"] = J
                    C._refresh_slot_sql_ui(D_, present=I)
                    if H_:
                        C._mark_slot(D_, I)
                    else:
                        C._mark_slot(D_, AR)
                    C.focus_force()
            C.dragging_idx = I
        C._queue_dashboard_refresh()

    def _add_file_to_slot(B, idx, src_path):
        E_ = src_path
        C_ = idx
        D_ = B.slots[C_][f]
        if D_:
            if C_ in B.pending_additions:
                B.pending_additions.pop(C_, I)
            elif D_.startswith(l) and A.path.isfile(D_):
                B.pending_deletions[C_] = D_
        B.pending_ftp_deletions.pop(C_, I)
        label = B.slots[C_][Aa]
        ftp_info = B.ftp_remote_only.pop(label, I)
        if ftp_info and label not in B.ftp_preview_files:
            B.ftp_preview_files[label] = ftp_info
        B.pending_additions[C_] = E_
        B._set_slot_paths(
            C_,
            working_path=E_,
            local_path=E_,
            ftp_path=B._get_state_slot_ftp_path(B._product_state, label),
            preferred_preview="local",
        )
        B._update_slot_ui(C_)
        B._mark_slot(C_, AR)
        B.slots[C_]["sql_presence_unknown"] = J
        B._refresh_slot_sql_ui(C_, present=I)
        B._queue_dashboard_refresh()

    def _update_slot_ui(J, idx):
        D_ = J.slots[idx]
        if not (D_.get(f) or D_.get("local_path") or D_.get("ftp_path")):
            return
        J._display_slot_preview(idx)

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
            label = E_[Aa]
            G_ = h
            if D_ in C.pending_additions:
                C.pending_additions.pop(D_, I)
                G_ = J
            elif F_.startswith(l) and A.path.isfile(F_):
                C.pending_deletions[D_] = F_
            elif not F_.startswith(l):
                remote_name = I
                info = C.ftp_remote_only.pop(label, I)
                if info:
                    remote_name = info.get("filename")
                elif label in C.ftp_presence:
                    remote_name = C.ftp_presence.get(label)
                if remote_name:
                    C.pending_ftp_deletions[D_] = remote_name
            C.ftp_preview_files.pop(label, I)
            C._clear_slot_preview(D_)
            E_["sql_presence_unknown"] = J
            C._refresh_slot_sql_ui(D_, present=I)
            if G_:
                C._mark_slot(D_, I)
            else:
                C._mark_slot(D_, AR)
            C._queue_dashboard_refresh()
            C.focus_force()

    def _clear_all_slots(C):
        C.pending_additions.clear()
        C.pending_deletions.clear()
        C.pending_ftp_deletions.clear()
        C._thumb_tokens.clear()
        C._product_state.original_files.clear()
        C._product_state.ftp_remote_only.clear()
        C._product_state.ftp_presence.clear()
        C._product_state.ftp_preview_files.clear()
        C._product_state.ftp_downloaded_final.clear()
        C._product_state.sql_presence = I
        C._product_state.sql_values.clear()
        C._sync_state_refs()
        for idx, A_ in A0(C.slots):
            C._clear_slot_preview(idx)
            A_["sql_presence_unknown"] = h
            if "sql_icon" in A_:
                A_["sql_icon"].place_forget()
            if "status_label" in A_:
                A_["status_label"].configure(text=C._slot_status["empty"])
            if "progress" in A_:
                progress = A_["progress"]
                if progress:
                    progress.stop()
                    progress.configure(mode="determinate", value=0)
            C._mark_slot(idx, I)
        C._queue_dashboard_refresh()

    def _reset_form_fields(A, keep_ean=h):
        A.var_name.set(B)
        A.var_type.set(B)
        A.var_model.set(B)
        A.var_color1.set(B)
        A.var_color2.set(B)
        A.var_color3.set(B)
        A.var_extra.set(B)
        A.var_product_id.set(B)
        if not keep_ean:
            A.var_ean.set(B)
        if Aj(A, "combo_name", I):
            A.combo_name.configure(state=X, style=j)
            A.combo_name[S] = A.lists.get(n, [])
        if Aj(A, "combo_type", I):
            A.combo_type.configure(state=X, style=j)
            A.combo_type[S] = A.lists.get(t, [])
        if Aj(A, "combo_model", I):
            A.combo_model.configure(state=X, style=j)
            A.combo_model[S] = A.lists.get(s, [])
        if Aj(A, "combo_color1", I):
            A.combo_color1.configure(state=X, style=j)
            A.combo_color1[S] = A.lists.get(Y, [])
        if Aj(A, "combo_color2", I):
            A.combo_color2.configure(state=X, style=j)
            A.combo_color2[S] = A.lists.get(Y, [])
        if Aj(A, "combo_color3", I):
            A.combo_color3.configure(state=X, style=j)
            A.combo_color3[S] = A.lists.get(Y, [])
        if Aj(A, "combo_extra", I):
            A.combo_extra.configure(state=X, style=j)
            A.combo_extra[S] = A.lists.get(d, [])
        if Aj(A, "entry_ean", I):
            A.entry_ean.configure(state=X)
        if Aj(A, "btn_submit", I):
            A.btn_submit.configure(state=X)
        if Aj(A, "btn_search_entry", I):
            A.btn_search_entry.configure(state=X)
        if Aj(A, "btn_new_search", I):
            A.btn_new_search.configure(state=X)
        if Aj(A, "btn_open", I):
            A.btn_open.configure(state=V)
        A._refresh_commit_snapshot()
        A._clear_all_slots()
        A._queue_form_change_refresh()

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
        AH_, p_, s_ = C._normalize_color_vars()
        b_ = C.var_extra.get().strip()
        if b_ == B or b_.upper() in [L, L]:
            b_ = L
        else:
            b_ = b_.replace(a, g).upper()
        K_ = C.var_ean.get().strip()
        color_values = [AH_, p_, s_]
        if not C._warn_about_ean_conflict(force_message=J, quick_check=h):
            return
        output_dir = build_product_directory(
            l,
            AE_,
            AF_,
            AG_,
            color_values,
            b_,
        )
        resize_enabled = bool(C.opt_resize.get())
        compress_enabled = bool(C.opt_compress.get())
        limit_size_enabled = bool(C.opt_maxsize.get())
        convert_tif_enabled = bool(C.opt_convert_tif.get())
        max_dim = C.resize_max_dim.get() or 2000
        compress_quality = max(1, min(100, C.compress_quality.get() or 85))
        max_bytes = (C.max_file_kb.get() or 0) * 1024
        target_fmt_raw = C.tif_target_format.get().strip().upper() or At
        target_fmt = "JPEG" if target_fmt_raw == "JPG" else target_fmt_raw
        target_ext = FORMAT_TO_EXTENSION.get(target_fmt, "." + target_fmt_raw.lower())
        current_product_id = G(C.var_product_id.get() or B).strip().upper()
        BZ_ = save_ean_entry(
            K_,
            AE_,
            AF_,
            AG_,
            AH_,
            p_ or B,
            s_ or B,
            b_ if b_ != B else L,
            product_id=current_product_id,
        )
        if BZ_ is h:
            return
        else:
            try:
                BC_seed = copy.deepcopy(C.lists)
                BC_seed[W] = copy.deepcopy(C.entries)
                BC_seed[ENTRY_RECORDS_KEY] = copy.deepcopy(C.entry_records)
                BC_ = merge_saved_entry_into_lists(BC_seed, BZ_)
                C._reload_entry_cache(BC_)
                C.lists = BC_
            except E as R:
                log_error_loc("reload_entries_failed", error=R)
        saved_product_id = G(BZ_.get("product_id") or current_product_id).strip().upper()
        saved_entry = BZ_.get("entry") if isinstance(BZ_, dict) else {}
        if isinstance(saved_entry, dict):
            saved_entry = dict(saved_entry)
            saved_entry[EAN_HEADER] = K_
        C.var_product_id.set(saved_product_id)
        C._record_loaded = bool(saved_product_id)
        C._last_lookup_signature = I
        C.is_processing = J
        C._set_busy_state(
            LANG.get("busy_processing", "Przetwarzanie i synchronizacja"),
            active=J,
        )
        C.btn_submit.configure(state=V)
        C.btn_search_entry.configure(state=V)
        C.btn_new_search.configure(state=V)
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
        result_data = {A2: bool(BZ_.get("updated")) if isinstance(BZ_, dict) else h}
        state_snapshot = C._snapshot_product_state()
        C._set_product_identity(state_snapshot.identity)
        slot_state = C._snapshot_slot_runtime()
        preserve_loaded = C._preserve_loaded_binding()

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
            worker_state = state_snapshot.clone()
            worker_slots = copy.deepcopy(slot_state)
            try:
                i_ = output_dir
                A.makedirs(i_, exist_ok=J)
                BM_ = []
                files_to_upload = []
                ftp_delete_candidates = {
                    G(remote_name).strip()
                    for remote_name in worker_state.pending_ftp_deletions.values()
                    if G(remote_name).strip()
                }
                sql_update_prefixes = set()
                sql_clear_prefixes = {
                    worker_slots[idx][Aa]
                    for idx in worker_state.pending_ftp_deletions
                    if 0 <= idx < Q(worker_slots)
                }
                try:
                    if A.path.exists(AN):
                        Af.rmtree(AN)
                    A.makedirs(AN, exist_ok=J)
                except E as R:
                    log_error_loc("backup_folder_failed", error=R)
                if worker_state.ftp_remote_only:
                    for label, info in worker_state.ftp_remote_only.items():
                        for idx, slot in A0(worker_slots):
                            if slot[Aa] == label:
                                Az_ = slot[Aa]
                                Be_ = label_category(slot["label"])
                                ext = A.path.splitext(info["filename"])[1]
                                c_ = build_slot_filename(
                                    K_,
                                    Az_,
                                    Be_,
                                    AE_,
                                    AF_,
                                    AG_,
                                    color_values,
                                    b_,
                                    ext,
                                )
                                dest = A.path.join(i_, c_)
                                try:
                                    Af.copy2(info["temp_path"], dest)
                                    log_info_loc(
                                        "ftp_file_downloaded",
                                        file=info["filename"],
                                        temp=c_,
                                    )
                                    files_to_upload.append(c_)
                                    worker_slots[idx][f] = dest
                                    worker_state.ftp_downloaded_final.add(c_)
                                except E as R:
                                    log_error_loc(
                                        "file_save_error",
                                        file=info["filename"],
                                        error=R,
                                    )
                                break
                    worker_state.ftp_remote_only.clear()
                if preserve_loaded:
                    svc_seed_metadata_migration(
                        worker_state,
                        worker_slots,
                        l,
                        i_,
                        K_,
                        AE_,
                        AF_,
                        AG_,
                        color_values,
                        b_,
                        convert_tif_enabled=convert_tif_enabled,
                        target_ext=target_ext,
                    )
                AJ_ = set(worker_state.pending_additions.keys())
                AL_ = set(worker_state.pending_deletions.keys())
                AM_ = AJ_ & AL_
                for F_ in list(AM_):
                    A8_ = worker_state.pending_additions.get(F_)
                    Ay_ = worker_state.pending_deletions.get(F_)
                    if A8_ and Ay_:
                        try:
                            BD_ = A.path.samefile(A8_, Ay_)
                        except E:
                            BD_ = A.path.normcase(
                                A.path.normpath(A8_)
                            ) == A.path.normcase(A.path.normpath(Ay_))
                        if BD_:
                            BF_ = svc_build_slot_target_filename(
                                worker_slots,
                                F_,
                                K_,
                                AE_,
                                AF_,
                                AG_,
                                color_values,
                                b_,
                                A8_,
                                convert_tif_enabled=convert_tif_enabled,
                                target_ext=target_ext,
                            )
                            BG_ = A.path.join(i_, BF_) if BF_ else B
                            BH_ = h
                            if BG_:
                                try:
                                    BH_ = A.path.samefile(Ay_, BG_)
                                except E:
                                    BH_ = A.path.normcase(
                                        A.path.normpath(Ay_)
                                    ) == A.path.normcase(A.path.normpath(BG_))
                            if BH_:
                                worker_state.pending_additions.pop(F_, I)
                                worker_state.pending_deletions.pop(F_, I)
                AJ_ = set(worker_state.pending_additions.keys())
                AL_ = set(worker_state.pending_deletions.keys())
                AM_ = AJ_ & AL_
                backup_candidates = {
                    path for path in worker_state.pending_deletions.values() if path
                }
                for F_, src_path in list(worker_state.pending_additions.items()):
                    if not src_path or not A.path.isfile(src_path):
                        continue
                    c_ = svc_build_slot_target_filename(
                        worker_slots,
                        F_,
                        K_,
                        AE_,
                        AF_,
                        AG_,
                        color_values,
                        b_,
                        src_path,
                        convert_tif_enabled=convert_tif_enabled,
                        target_ext=target_ext,
                    )
                    if not c_:
                        continue
                    S_ = A.path.join(i_, c_)
                    try:
                        same_source_target = A.path.samefile(src_path, S_)
                    except E:
                        same_source_target = A.path.normcase(
                            A.path.normpath(src_path)
                        ) == A.path.normcase(A.path.normpath(S_))
                    if same_source_target:
                        backup_candidates.add(src_path)
                backed_up = []
                for T in sorted(backup_candidates):
                    if T and A.path.isfile(T):
                        try:
                            backup_name = A.path.basename(T)
                            backup_target = A.path.join(AN, backup_name)
                            if A.path.exists(backup_target):
                                root_name, ext_name = A.path.splitext(backup_name)
                                backup_target = A.path.join(
                                    AN,
                                    f"{root_name}__backup{ext_name}",
                                )
                            Af.copy2(T, backup_target)
                            backed_up.append(A.path.basename(backup_target))
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
                BE_ = {}
                for F_, src_path in list(worker_state.pending_additions.items()):
                    if not src_path:
                        worker_state.pending_additions.pop(F_, I)
                        continue
                    if not A.path.isfile(src_path):
                        worker_state.pending_additions.pop(F_, I)
                        continue
                    c_ = svc_build_slot_target_filename(
                        worker_slots,
                        F_,
                        K_,
                        AE_,
                        AF_,
                        AG_,
                        color_values,
                        b_,
                        src_path,
                        convert_tif_enabled=convert_tif_enabled,
                        target_ext=target_ext,
                    )
                    if not c_:
                        worker_state.pending_additions.pop(F_, I)
                        continue
                    S_ = A.path.join(i_, c_)
                    slot = worker_slots[F_]
                    Az_ = slot[Aa]
                    actual_remote_name = G(worker_state.ftp_presence.get(Az_) or B).strip()
                    current_remote_name = svc_infer_existing_remote_filename(
                        worker_state, Az_
                    )
                    expected_remote_name = svc_build_expected_remote_filename(
                        worker_slots,
                        F_,
                        K_,
                        src_path,
                        convert_tif_enabled=convert_tif_enabled,
                        target_ext=target_ext,
                    )
                    try:
                        same_source_target = A.path.samefile(src_path, S_)
                    except E:
                        same_source_target = A.path.normcase(
                            A.path.normpath(src_path)
                        ) == A.path.normcase(A.path.normpath(S_))
                    remote_missing = Az_ not in worker_state.ftp_presence
                    remote_name_changed = bool(
                        expected_remote_name
                        and current_remote_name
                        and current_remote_name != expected_remote_name
                    )
                    remote_sync_needed = bool(
                        slot.get(B0) == AR or remote_missing or remote_name_changed
                    )
                    sql_known_missing = Aq(worker_state.sql_presence, dict) and not worker_state.sql_presence.get(
                        Az_, h
                    )
                    sql_update_needed = bool(
                        expected_remote_name
                        and (
                            remote_name_changed
                            or sql_known_missing
                            or (slot.get(B0) == AR and not current_remote_name)
                        )
                    )
                    metadata_migration = (not same_source_target) or remote_name_changed
                    if (
                        F_ not in worker_state.pending_deletions
                        and slot.get(B0) != AR
                        and not metadata_migration
                    ):
                        worker_state.pending_additions.pop(F_, I)
                        continue
                    C._update_slot_activity(
                        F_, active=J, status=C._slot_status["processing"]
                    )
                    BH_ = A.path.splitext(src_path)[1]
                    temp_output_path = B
                    try:
                        if F_ in worker_state.pending_deletions:
                            old_path = worker_state.pending_deletions.get(F_)
                            if not old_path:
                                worker_state.pending_deletions.pop(F_, I)
                            else:
                                try:
                                    same_old_source = A.path.samefile(old_path, src_path)
                                except E:
                                    same_old_source = A.path.normcase(
                                        A.path.normpath(old_path)
                                    ) == A.path.normcase(A.path.normpath(src_path))
                                try:
                                    same_target = A.path.samefile(old_path, S_)
                                except E:
                                    same_target = A.path.normcase(
                                        A.path.normpath(old_path)
                                    ) == A.path.normcase(A.path.normpath(S_))
                                if same_target:
                                    worker_state.pending_deletions.pop(F_, I)
                                    if not same_old_source:
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
                        elif A.path.exists(S_) and not same_source_target:
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
                        if is_image and convert_tif_enabled:
                            t_ext = target_ext
                            save_target = S_
                            if same_source_target:
                                save_target = f"{S_}.__gui_tmp__"
                                temp_output_path = save_target
                                if A.path.exists(save_target):
                                    A.remove(save_target)
                            elif A.path.exists(S_):
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
                                if resize_enabled:
                                    A1.thumbnail((max_dim, max_dim), LANCZOS_FILTER)
                                save_params = {}
                                if t_ext in [F, O]:
                                    quality = 95
                                    if compress_enabled:
                                        quality = compress_quality
                                    save_params[W] = quality
                                    save_params[X] = J
                                if t_ext == V:
                                    save_params[X] = J
                                A1.save(save_target, format=target_fmt, **save_params)
                                if limit_size_enabled:
                                    if max_bytes > 0 and t_ext in [F, O]:
                                        try:
                                            quality = save_params.get(W, 95)
                                            while (
                                                quality > 10
                                                and A.path.getsize(save_target) > max_bytes
                                            ):
                                                quality -= 5
                                                A1.save(
                                                    save_target,
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
                            if temp_output_path:
                                A.replace(temp_output_path, S_)
                                temp_output_path = B
                            log_info_loc("image_added_modified", file=c_)
                        elif ext_lower in [F, O, V, ".bmp", ".gif"]:
                            save_target = S_
                            if same_source_target:
                                save_target = f"{S_}.__gui_tmp__"
                                temp_output_path = save_target
                                if A.path.exists(save_target):
                                    A.remove(save_target)
                            with AA.open(src_path) as A1:
                                if resize_enabled:
                                    A1.thumbnail((max_dim, max_dim), LANCZOS_FILTER)
                                save_params = {}
                                if ext_lower in [F, O]:
                                    quality = 95
                                    if compress_enabled:
                                        quality = compress_quality
                                    save_params[W] = quality
                                    save_params[X] = J
                                if ext_lower == V:
                                    save_params[X] = J
                                A1.save(save_target, **save_params)
                                if limit_size_enabled:
                                    if max_bytes > 0:
                                        if A.path.getsize(save_target) > max_bytes and ext_lower in [
                                            F,
                                            O,
                                        ]:
                                            try:
                                                quality = save_params.get(W, 95)
                                                while (
                                                    quality > 10
                                                    and A.path.getsize(save_target) > max_bytes
                                                ):
                                                    quality -= 5
                                                    A1.save(
                                                        save_target,
                                                        quality=quality,
                                                        optimize=J,
                                                    )
                                            except E as R:
                                                log_error_loc(
                                                    "file_resize_error",
                                                    file=c_,
                                                    error=R,
                                                )
                            if temp_output_path:
                                A.replace(temp_output_path, S_)
                                temp_output_path = B
                            log_info_loc("image_added_modified", file=c_)
                        elif ext_lower in [".tif", ".tiff"]:
                            if not same_source_target:
                                Af.copy2(src_path, S_)
                            log_info_loc("file_added_modified", file=c_)
                        elif is_image:
                            if not same_source_target:
                                Af.copy2(src_path, S_)
                            log_info_loc("file_added_modified", file=c_)
                        else:
                            if not same_source_target:
                                Af.copy2(src_path, S_)
                            log_info_loc("file_added_modified", file=c_)
                        if remote_name_changed and actual_remote_name:
                            ftp_delete_candidates.add(actual_remote_name)
                        if sql_update_needed:
                            sql_update_prefixes.add(Az_)
                        if (
                            F_ in worker_state.pending_ftp_deletions
                            and expected_remote_name
                            and worker_state.pending_ftp_deletions[F_] == expected_remote_name
                        ):
                            worker_state.pending_ftp_deletions.pop(F_, I)
                            ftp_delete_candidates.discard(expected_remote_name)
                        if remote_sync_needed and c_ not in files_to_upload:
                            files_to_upload.append(c_)
                        worker_slots[F_][f] = S_
                    except E as y:
                        log_error_loc(
                            "file_copy_failed",
                            file=A.path.basename(src_path),
                            error=y,
                        )
                        if temp_output_path and A.path.exists(temp_output_path):
                            try:
                                A.remove(temp_output_path)
                            except E:
                                pass
                        result_data[K].add(F_)
                        BE_[F_] = src_path
                        continue
                if K_ and Q(K_) == 13 and K_.isdigit():
                    try:
                        file_list = A.listdir(i_)
                    except E:
                        file_list = []
                    remove_candidates = {
                        A.path.basename(B) for B in worker_state.pending_deletions.values()
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
                                for F_, d_ in A0(worker_slots):
                                    if d_[f] and A.path.basename(d_[f]) == X_:
                                        worker_slots[F_][f] = new_path
                                        break
                                if X_ in files_to_upload:
                                    Bh_ = files_to_upload.index(X_)
                                    files_to_upload[Bh_] = new_name
                            except E as y:
                                log_error_loc(
                                    "file_rename_error", ean=K_, error=y
                                )
                                for i, d_ in A0(worker_slots):
                                    if d_[f] and A.path.basename(d_[f]) == X_:
                                        result_data[K].add(i)
                                        break
                for idx, slot in A0(worker_slots):
                    path = slot[f]
                    if (
                        path
                        and A.path.isfile(path)
                        and idx not in worker_state.pending_deletions
                        and slot[Aa] not in worker_state.ftp_presence
                    ):
                        fname = A.path.basename(path)
                        if fname not in files_to_upload:
                            files_to_upload.append(fname)
                        sql_update_prefixes.add(slot[Aa])
                        worker_state.pending_additions.setdefault(idx, path)
                Am_ = {}
                for F_, T in list(worker_state.pending_deletions.items()):
                    if F_ in result_data[K]:
                        Am_[F_] = T
                        continue
                    conflict_error = h
                    for Bh in result_data[K]:
                        if worker_state.pending_additions.get(Bh) == T:
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
                            if F_ not in worker_state.pending_additions:
                                current_remote_name = G(
                                    worker_state.ftp_presence.get(worker_slots[F_][Aa]) or B
                                ).strip()
                                if current_remote_name:
                                    ftp_delete_candidates.add(current_remote_name)
                                sql_clear_prefixes.add(worker_slots[F_][Aa])
                    except E as y:
                        log_error_loc(
                            "file_delete_failed",
                            file=A.path.basename(T),
                            error=y,
                        )
                        result_data[K].add(F_)
                        Am_[F_] = T
                add_set = set(worker_state.pending_additions.keys())
                del_set = set(worker_state.pending_deletions.keys())
                inter_set = add_set & del_set
                worker_state.pending_additions = BE_
                worker_state.pending_deletions = Am_
                BM_ = sorted(ftp_delete_candidates)
                result_data[n] = dict(BE_)
                result_data[o] = dict(Am_)
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
                                for idx, slot in A0(worker_slots):
                                    if slot.get(f):
                                        slot_index_by_filename[
                                            A.path.basename(slot[f])
                                        ] = idx
                                ftp_error = h
                                for X_ in files_local:
                                    if X_ in worker_state.ftp_downloaded_final:
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
                        for d_ in worker_slots:
                            Az_ = d_[Aa]
                            B3_ = C._resolve_sql_column(Az_, d_["label"], log_missing=J)
                            if not B3_:
                                continue
                            if Az_ in sql_update_prefixes and d_[f]:
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
                            elif Az_ in sql_clear_prefixes:
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
                result_data[K] = set(range(len(worker_slots)))
                result_data[Y] = "Operacja przerwana z powodu błędu."
                result_data[P] = G(exc)
            worker_state.original_files = {
                slot[Aa]: A.path.basename(slot[f])
                for slot in worker_slots
                if slot.get(f) and A.path.isfile(slot[f])
            }
            result_data["product_state"] = worker_state
            result_data["slot_paths"] = {
                idx: slot.get(f)
                for idx, slot in A0(worker_slots)
            }
            result_data["ean"] = K_
            result_data["saved_entry"] = saved_entry

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
            try:
                C.entry_product_id.configure(state="readonly")
            except E:
                pass
            C.btn_submit.configure(state=X)
            C.btn_search_entry.configure(state=X)
            C.btn_new_search.configure(state=X)
            C.btn_open.configure(state=X)
            C.is_processing = h
            C._set_busy_state(B, active=h)
            err_set = result_data.get(K, set()) or set()
            add_set = result_data.get(p, set())
            del_set = result_data.get(s, set())
            inter_set = result_data.get(t, set())
            committed_state = result_data.get("product_state")
            slot_paths = result_data.get("slot_paths", {}) or {}
            if isinstance(committed_state, ProductState):
                C._commit_product_state(committed_state)
            else:
                C.pending_additions = result_data.get(n, {})
                C.pending_deletions = result_data.get(o, {})
            Y_ = result_data.get(Y, B)
            A__ = result_data.get(k, Ay)
            AW_msg = result_data.get(P, B)
            if err_set or A__ or Y_ or AW_msg:
                for idx, slot in A0(C.slots):
                    path = slot_paths.get(idx)
                    if path and not A.path.isfile(path):
                        path = I
                    prefix = slot[Aa]
                    ftp_path = I
                    local_path = path
                    if isinstance(committed_state, ProductState):
                        ftp_path = C._get_state_slot_ftp_path(committed_state, prefix)
                        local_path = C._resolve_state_slot_local_path(
                            prefix,
                            path,
                            committed_state,
                        )
                    working_path = path or ftp_path
                    if working_path or local_path or ftp_path:
                        C._set_slot_paths(
                            idx,
                            working_path=working_path,
                            local_path=local_path,
                            ftp_path=ftp_path,
                            preferred_preview="ftp" if ftp_path else "local",
                        )
                        C._display_slot_preview(idx)
                    else:
                        C._clear_slot_preview(idx)
                    if isinstance(committed_state, ProductState):
                        if isinstance(committed_state.sql_presence, dict):
                            slot["sql_presence_unknown"] = h
                            C._refresh_slot_sql_ui(
                                idx,
                                present=committed_state.sql_presence.get(prefix, h),
                                state=committed_state,
                            )
                        else:
                            slot["sql_presence_unknown"] = h
                            C._refresh_slot_sql_ui(
                                idx,
                                present=I,
                                state=committed_state,
                            )
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
            C._queue_dashboard_refresh()
            K_val = result_data.get("ean", K_)
            saved_entry_record = result_data.get("saved_entry")
            if not err_set and not A__ and not Y_ and not AW_msg:
                if saved_entry_record:
                    C._load_entry_record(saved_entry_record)
                else:
                    C._load_existing_files()
            elif saved_entry_record:
                C._set_loaded_entry_context(saved_entry_record)
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
            C._start_file_index_refresh()

    def _load_by_ean(A):
        E_ = NO_EAN_LABEL
        D_ = A.var_ean.get().strip()
        if not D_:
            O.showwarning(E_, ENTER_EAN_TO_LOAD_MSG)
            return
        if D_.upper() == q:
            O.showwarning(E_, CANNOT_SEARCH_NO_EAN_MSG)
            return
        if D_ in A.entries:
            record = dict(A.entries[D_])
            record[EAN_HEADER] = D_
            A._load_entry_record(record)
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
        C_ = build_product_directory(
            l,
            F_,
            G_,
            H_,
            [I_, K_, M_],
            N_,
        )
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
        a_.geometry("1080x780")
        a_.minsize(960, 720)
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
        local_file_index_var = F.BooleanVar(
            value=bool(D.get(LOCAL_FILE_INDEX_KEY, J))
        )
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
        file_index_toggle = C.Checkbutton(
            system_tab,
            text=LANG.get(
                "file_index_enable_label",
                "Używaj lokalnego indeksu katalogów do przyspieszenia podpowiedzi i odczytu plików.",
            ),
            variable=local_file_index_var,
        )
        file_index_toggle.grid(row=4, column=0, columnspan=3, padx=5, pady=(4, 0), sticky="w")
        file_index_btn = C.Button(
            system_tab,
            text=LANG.get("file_index_rebuild_action", "Odbuduj indeks plików"),
            command=A._start_file_index_refresh,
        )
        file_index_btn.grid(row=5, column=0, padx=5, pady=(6, 0), sticky="w")
        _slabel(
            system_tab,
            textvariable=A._file_index_status_var,
            style="SettingsHint.TLabel",
            wraplength=420,
            justify="left",
        ).grid(row=5, column=1, columnspan=2, padx=5, pady=(6, 0), sticky="w")
        system_admin_btn = C.Button(
            system_tab, text=Ag_, command=_unlock_system_settings
        )
        system_admin_btn.grid(
            row=6, column=0, columnspan=3, padx=5, pady=(6, 0), sticky="e"
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
            text=LANG.get("perf_check_label", "Test wydajności GUI"),
            style="SettingsHeader.TLabel",
        ).grid(row=9, column=0, columnspan=2, padx=5, pady=(8, 4), sticky=T)
        perf_check_status_var = F.StringVar(value=B)

        def _run_perf_check():
            A._run_performance_benchmark(
                perf_check_status_var,
                perf_check_btn,
                code_report,
            )

        perf_check_btn = C.Button(
            V_,
            text=LANG.get("perf_check_button", "Test wydajności"),
            command=_run_perf_check,
        )
        perf_check_btn.grid(row=10, column=0, padx=5, pady=5, sticky=T)
        _slabel(
            V_,
            textvariable=perf_check_status_var,
            wraplength=400,
            justify="left",
        ).grid(row=10, column=1, padx=5, pady=5, sticky="w")
        _slabel(
            V_,
            text=LANG.get(
                "perf_check_hint",
                "Mierzy krok pętli UI i czas przygotowania miniaturek na aktualnych danych.",
            ),
            wraplength=400,
            justify="left",
            style="SettingsHint.TLabel",
        ).grid(row=11, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        _slabel(
            V_,
            text=LANG.get("code_check_report_label", "Raport diagnostyczny"),
            style="SettingsHeader.TLabel",
        ).grid(row=12, column=0, columnspan=2, padx=5, pady=(8, 4), sticky=T)
        code_report = BS.ScrolledText(
            V_, width=90, height=18, state=V, wrap="word"
        )
        code_report.grid(
            row=13, column=0, columnspan=2, padx=5, pady=(0, 8), sticky="nsew"
        )
        code_report.configure(
            background=A._ui_colors["log_bg"],
            foreground=A._ui_colors["log_fg"],
            insertbackground=A._ui_colors["hero_text"],
            padx=10,
            pady=8,
            relief="flat",
            bd=0,
        )
        V_.columnconfigure(0, weight=1)
        V_.columnconfigure(1, weight=1)
        V_.rowconfigure(13, weight=1)

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
            D[LOCAL_FILE_INDEX_KEY] = bool(local_file_index_var.get())
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
            A._set_local_file_index_enabled(D.get(LOCAL_FILE_INDEX_KEY, J))
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
                background="#10242d",
                foreground="#e4f1ef",
                relief="solid",
                borderwidth=1,
                padx=8,
                pady=5,
                justify="left",
                wraplength=300,
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
