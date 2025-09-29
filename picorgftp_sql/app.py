"""Main Tkinter application class."""

from .common import *  # noqa: F401,F403
from .excel_utils import (
    SLOT_LABELS,
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
from . import config, localization
from .settings import EXCEL_SHEETS, AN, l

D = config.CONFIG
LANG_PREF = localization.LANG_PREF

from .localization import *  # noqa: F401,F403
class App(BU.Tk):
    def __init__(B):
        """Initialise the Tk window, form state and runtime caches."""

        super().__init__()
        B.title(APP_TITLE)
        B.geometry("1200x800")
        B.style = C.Style()
        B.style.theme_use("clam")
        B.style.configure(Z, fieldbackground=LIGHT_GREEN)
        D_ = prepare_excel_lists()
        B.entries = D_.get(W, {})
        if W in D_:
            D_.pop(W)
        B.lists = D_
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
        B.dragging_idx = I
        B.original_files = {}
        B.is_processing = h
        B.logged_counts = h
        B.suppress_next_lookup = h
        B._build_form()
        B._build_slots()
        H_ = Q(E_)
        B.combo_name.existing_count = H_
        set_app(B)

    def _build_form(A):
        """Create comboboxes and entry widgets for the product data form."""

        F_ = "<FocusOut>"
        D_ = "<KeyRelease>"
        E_ = "<Return>"
        B_ = C.Frame(A)
        B_.pack(side="top", fill="x", padx=10, pady=10)
        G_ = C.Label(B_, text=NAME_LABEL)
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
        H_ = C.Label(B_, text=TYPE_LABEL)
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
        I_ = C.Label(B_, text=MODEL_LABEL)
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
        J_ = C.Label(B_, text=COLOR1_LABEL)
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
        K_ = C.Label(B_, text=COLOR2_LABEL)
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
        L_ = C.Label(B_, text=COLOR3_LABEL)
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
        M_ = C.Label(B_, text=EXTRA_LABEL)
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
        N_ = C.Label(B_, text=EAN_OPTIONAL_LABEL)
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
        O_ = C.Button(B_, text=LOAD_LABEL, command=A._load_by_ean)
        O_.grid(row=7, column=2, padx=5, pady=2)
        P_ = C.Button(B_, text=EDIT_LISTS_LABEL, command=A._open_list_editor)
        P_.grid(row=0, column=2, padx=20)
        Q_ = C.Button(B_, text=SETTINGS_LABEL, command=A._open_settings)
        Q_.grid(row=0, column=3, padx=5)
        A.btn_submit = C.Button(B_, text=UPDATE_LABEL, command=A._on_submit)
        A.btn_submit.grid(row=8, column=0, columnspan=2, pady=10)
        A.btn_open = C.Button(B_, text=OPEN_FOLDER_LABEL, command=A._open_current_folder)
        A.btn_open.grid(row=8, column=2, padx=5, pady=10)
        A.ui_log = BS.ScrolledText(B_, width=48, height=8, state=Ak, wrap="word")
        A.ui_log.grid(row=0, column=4, rowspan=9, padx=10, sticky="nsew")
        S_ = C.Button(B_, text=CLEAR_LOG_LABEL, command=lambda: A._ui_log(clear=Al))
        S_.grid(row=8, column=3, padx=5, pady=10, sticky="e")
        B_.grid_columnconfigure(4, weight=1)

    def _build_slots(B):
        """Prepare the scrollable grid of drop targets used for images."""

        Q_ = "<Button-1>"
        R_ = "#ddd"
        S_ = "<Configure>"
        L_ = "units"
        M_ = C.Frame(B)
        M_.pack(fill=z, expand=J, padx=10, pady=10)
        A_ = F.Canvas(M_)
        T = C.Scrollbar(M_, orient=An, command=A_.yview)
        N_ = C.Frame(A_)
        N_.bind(S_, lambda e: A_.configure(scrollregion=A_.bbox("all")))
        Y = A_.create_window((0, 0), window=N_, anchor="nw")
        A_.bind(S_, lambda e, cw=Y: A_.itemconfig(cw, width=e.width))
        A_.configure(yscrollcommand=T.set)
        A_.pack(side=Am, fill=z, expand=J)
        T.pack(side=AV, fill="y")
        A_.bind_all(
            "<MouseWheel>", lambda e: A_.yview_scroll(int(-1 * (e.delta / 120)), L_)
        )
        A_.bind_all("<Button-4>", lambda e: A_.yview_scroll(-1, L_))
        A_.bind_all("<Button-5>", lambda e: A_.yview_scroll(1, L_))
        B.slots_frame = N_
        B.slots = []
        U = 5
        for G_, (V_, W_) in A0(SLOT_LABELS):
            Z_, O_ = divmod(G_, U)
            H_ = F.Frame(
                B.slots_frame,
                highlightthickness=0,
                highlightbackground=A8,
                highlightcolor=A8,
                bd=0,
            )
            H_.grid(row=Z_, column=O_, padx=5, pady=5, sticky="nsew")
            C.Label(H_, text=f"{V_} {W_}").pack()
            E_ = F.Frame(H_, height=100, bg=R_)
            E_.pack_propagate(h)
            E_.pack(fill=z, expand=J, padx=5, pady=5)
            D_ = F.Label(E_, text=NO_FILE_LABEL, bg=R_)
            D_.pack(fill=z, expand=J)
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
            local_icon.create_text(15, 10, text="LOCAL", font=("Arial", 7), fill="white")
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
            ftp_icon.create_text(15, 10, text="FTP", font=("Arial", 7), fill="white")
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
            sql_icon.create_text(15, 10, text="SQL", font=("Arial", 7), fill="white")
            sql_icon.offset_x = 0
            sql_icon.place(relx=1.0, rely=1.0, anchor="se", x=sql_icon.offset_x)
            sql_icon.place_forget()
            D_.drag_source_register(1, BJ)
            D_.dnd_bind("<<DragInitCmd>>", lambda e, i=G_: B._on_drag_init(e, i))
            D_.dnd_bind("<<DragEndCmd>>", lambda e: B._on_drag_end(e))
            B.slots.append(
                {
                    Aa: V_,
                    "label": W_,
                    y: D_,
                    A7: K_,
                    "local_icon": local_icon,
                    "ftp_icon": ftp_icon,
                    "sql_icon": sql_icon,
                    f: I,
                    AS: H_,
                    B0: I,
                }
            )
        for O_ in Ax(U):
            B.slots_frame.columnconfigure(O_, weight=1)

    def _set_icon_status(C, icon, present):
        """Toggle the coloured indicator showing local/remote file presence."""

        if not icon:
            return
        if present is I:
            icon.place_forget()
            return
        icon.place(relx=1.0, rely=1.0, anchor="se", x=getattr(icon, "offset_x", 0))
        icon.config(bg="green" if present else "red")

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

    def _refresh_combobox_list(B, combobox, all_values, existing_count=0):
        """Refresh the dropdown values while remembering which entries exist."""

        A_ = combobox
        A_[S] = all_values
        A_.existing_count = existing_count

    def _on_name_commit(C):
        """Handle the user confirming or typing a furniture name."""

        D_ = C.var_name.get().strip()
        if not D_:
            return
        if D_.upper() not in C.lists[n]:
            if O.askyesno(
                AJ, f"Nazwa '{D_}' nie istnieje na liście. Czy dodać ją do listy?"
            ):
                H = C._open_list_editor(n)
                C.wait_window(H)
                C.lists = prepare_excel_lists()
                C.entries = C.lists.get(W, {})
                if W in C.lists:
                    C.lists.pop(W)
                C.combo_name[S] = C.lists[n]
                if D_.upper() not in [A.upper() for A in C.lists[n]]:
                    C.var_name.set(B)
                    return
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
        if D_.upper() not in C.lists[t]:
            if O.askyesno(
                AJ, f"Typ '{D_}' nie istnieje na liście. Czy dodać go do listy?"
            ):
                H = C._open_list_editor(t)
                C.wait_window(H)
                C.lists = prepare_excel_lists()
                C.entries = C.lists.get(W, {})
                if W in C.lists:
                    C.lists.pop(W)
                C.combo_type[S] = C.lists[t]
                if D_.upper() not in [A.upper() for A in C.lists[t]]:
                    C.var_type.set(B)
                    return
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
                    log_error(
                        f"Rename folder NO-LED to NO-LED failed in load_existing_files: {T}"
                    )
        C._clear_all_slots()
        C.original_files = {}
        if not A.path.isdir(F):
            return
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
                                log_error(f"FTP download error for {fname}: {T}")
                        else:
                            ftp_presence[label] = fname
                    O_.quit()
                except E as T:
                    log_error(f"FTP check error for EAN {K_}: {T}")
                if not C.logged_counts:
                    log_info_loc(
                        "found_images_counts",
                        local=Q(original_files),
                        ftp=Q(remote_files),
                    )
                    C.logged_counts = J
                if C._should_check_sql_presence():
                    columns = [(slot[Aa], slot["label"]) for slot in C.slots]
                    if columns:
                        try:
                            template = D.get(w, SQL_UPDATE_TEMPLATE)
                            import re

                            table = I
                            where_clause = I
                            match = re.search(r"(?i)update\s+([0-9A-Za-z_\.]+)\s+set", template)
                            if match:
                                table = match.group(1)
                            where_index = template.lower().find(" where")
                            if where_index != -1:
                                where_template = template[where_index:]
                            else:
                                where_template = (
                                    " WHERE EAN = '{ean}' OR Towar_powiazany_z_SKU = '{ean}'"
                                )
                            if table:
                                where_clause = where_template.replace("{ean}", K_)
                                db_type = D.get(p, K).lower()
                                column_names = ", ".join(label for _, label in columns)
                                if db_type == K:
                                    query = (
                                        f"SELECT {column_names} FROM {table}{where_clause} LIMIT 1"
                                    )
                                else:
                                    query = (
                                        f"SELECT TOP 1 {column_names} FROM {table}{where_clause}"
                                    )
                                conn = I
                                cur = I
                                try:
                                    conn = connect_db()
                                    cur = conn.cursor()
                                    cur.execute(query)
                                    row = cur.fetchone()
                                    sql_presence = {
                                        prefix: h for prefix, _ in columns
                                    }
                                    if row:
                                        try:
                                            values = list(row)
                                        except E:
                                            values = row
                                        for idx, (prefix, _) in A0(columns):
                                            value = values[idx] if idx < Q(values) else I
                                            if isinstance(value, memoryview):
                                                value = bytes(value)
                                            if isinstance(value, (bytes, bytearray)):
                                                try:
                                                    value = value.decode("utf-8")
                                                except E:
                                                    value = value.decode(
                                                        "latin-1", errors="ignore"
                                                    )
                                            present = h
                                            if value is not I:
                                                present = bool(G(value).strip())
                                            sql_presence[prefix] = present
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
                            log_error(f"SQL check error for EAN {K_}: {T}")
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
            for X_, G_ in A0(C.slots):
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
                    C._set_icon_status(G_["sql_icon"], sql_presence.get(R_, h))
                else:
                    C._set_icon_status(G_["sql_icon"], I)

        threading.Thread(target=worker, daemon=J).start()

    def _on_model_commit(D):
        H = "new"
        o = D.var_name.get().strip()
        p = D.var_type.get().strip()
        e_ = D.var_model.get().strip()
        if not o or not p or not e_:
            return
        if e_.upper() not in D.lists[s]:
            if O.askyesno(
                AJ,
                f"Model '{e_}' nie istnieje na liście. Czy chcesz dodać go do listy?",
            ):
                A6_ = D._open_list_editor(s)
                D.wait_window(A6_)
                D.lists = prepare_excel_lists()
                D.entries = D.lists.get(W, {})
                if W in D.lists:
                    D.lists.pop(W)
                D.combo_model[S] = D.lists[s]
                if e_.upper() not in [A.upper() for A in D.lists[s]]:
                    D.var_model.set(B)
                    return
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
                            log_error(f"Rename folder NO-LED to NO-LED failed: {AL_}")
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
        J_ = [A for A in (H_, F_, G_) if A and A.upper() not in C.lists[Y]]
        if J_:
            P_ = AI.join(J_)
            R_ = (
                f"Kolor '{J_[0]}' nie istnieje na liście. Czy dodać nowy wpis?"
                if Q(J_) == 1
                else f"Kolory '{P_}' nie istnieją na liście. Czy dodać nowe wpisy?"
            )
            if O.askyesno(AJ, R_):
                T = C._open_list_editor(Y)
                C.wait_window(T)
                C.lists = prepare_excel_lists()
                C.entries = C.lists.get(W, {})
                if W in C.lists:
                    C.lists.pop(W)
                C.combo_color1[S] = C.lists[Y]
                C.combo_color2[S] = C.lists[Y]
                C.combo_color3[S] = C.lists[Y]
                if H_.upper() not in [A.upper() for A in C.lists[Y]]:
                    C.var_color1.set(B)
                    return
                if F_ and F_.upper() not in [A.upper() for A in C.lists[Y]]:
                    C.var_color2.set(B)
                if G_ and G_.upper() not in [A.upper() for A in C.lists[Y]]:
                    C.var_color3.set(B)
            else:
                if H_.upper() not in [A.upper() for A in C.lists[Y]]:
                    C.var_color1.set(B)
                    return
                if F_ and F_.upper() not in [A.upper() for A in C.lists[Y]]:
                    C.var_color2.set(B)
                if G_ and G_.upper() not in [A.upper() for A in C.lists[Y]]:
                    C.var_color3.set(B)
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
                    log_error(f"Rename folder NO-LED to NO-LED failed: {a_}")
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
            if D_.upper() not in [A.upper() for A in C.lists[d]]:
                if O.askyesno(
                    AJ,
                    VALUE_NOT_EXISTS_QUESTION.format(value=D_),
                ):
                    M_ = C._open_list_editor(d)
                    C.wait_window(M_)
                    C.lists = prepare_excel_lists()
                    C.entries = C.lists.get(W, {})
                    if W in C.lists:
                        C.lists.pop(W)
                    C.combo_extra[S] = C.lists[d]
                    if D_.upper() not in [A.upper() for A in C.lists[d]]:
                        C.var_extra.set(B)
                        D_ = B
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
            ("Obrazy/PDF/DOC", "*.jpg *.jpeg *.png *.pdf *.doc *.docx"),
            ("Wszystkie pliki", "*.*"),
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
        C_ = D_[y]
        K_ = D_[A7]
        if not F_:
            return
        try:
            G_ = AA.open(F_)
            G_.thumbnail((100, 100), AA.LANCZOS)
            H_ = ImageTk.PhotoImage(G_)
            C_.configure(image=H_, text=B)
            C_.image = H_
        except E:
            C_.configure(text=A.path.basename(F_), image=B)
            C_.image = I
        K_.place(x=0, y=0)

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
            C._set_icon_status(E_["local_icon"], h)
            if "sql_icon" in E_:
                C._set_icon_status(E_["sql_icon"], I)
            if G_:
                C._mark_slot(D_, I)
            else:
                C._mark_slot(D_, AR)
            C.focus_force()

    def _clear_all_slots(C):
        C.pending_additions.clear()
        C.pending_deletions.clear()
        C.pending_ftp_deletions.clear()
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
            if AS in A_:
                A_[AS].configure(
                    highlightthickness=0, highlightbackground=A8, highlightcolor=A8
                )

    def _open_list_editor(E, focus_sheet=I):
        H_ = F.Toplevel(E)
        H_.title(EDIT_LISTS_LABEL)
        H_.grab_set()
        I_ = C.Notebook(H_)
        I_.pack(expand=J, fill=z, padx=5, pady=5)
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
        return H_

    def _add_list_item(C, key, listbox):
        B_ = key
        E_ = LIST_EDITOR_TAB_LABELS.get(B_, B_)
        D_ = BI.askstring(
            LIST_ADD_DIALOG_TITLE,
            LIST_ADD_PROMPT_MSG.format(list=E_),
        )
        if D_:
            add_to_list(EXCEL_SHEETS[B_], D_)
            if D_.strip().upper() not in [A.upper() for A in C.lists[B_]]:
                C.lists[B_] = C.lists[B_] + [
                    D_.strip().upper() if B_ != d else D_.strip().replace(a, g).upper()
                ]
            listbox.insert(
                F.END,
                D_.strip().upper() if B_ != d else D_.strip().replace(a, g).upper(),
            )
            if B_ == n:
                C.combo_name[S] = C.lists[B_]
            elif B_ == t:
                C.combo_type[S] = C.lists[B_]
            elif B_ == s:
                C.combo_model[S] = C.lists[B_]
            elif B_ == Y:
                C.combo_color1[S] = C.lists[B_]
                C.combo_color2[S] = C.lists[B_]
                C.combo_color3[S] = C.lists[B_]
            elif B_ == d:
                C.combo_extra[S] = C.lists[B_]

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
                log_error(f"Failed to reload entries after saving: {R}")
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
                                Az_ = SLOT_LABELS[idx][0]
                                Be_ = label_category(SLOT_LABELS[idx][1])
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
                    if not A.path.isfile(src_path):
                        C.pending_additions.pop(F_, I)
                        continue
                    Az_ = SLOT_LABELS[F_][0]
                    Be_ = label_category(SLOT_LABELS[F_][1])
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
                        if ext_lower in [F, O, V, ".bmp", ".gif"]:
                            A1 = AA.open(src_path)
                            if C.opt_resize.get():
                                max_dim = C.resize_max_dim.get() or 2000
                                A1.thumbnail((max_dim, max_dim), AA.LANCZOS)
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
                            if C.opt_convert_tif.get():
                                target_fmt = C.tif_target_format.get().upper()
                                if target_fmt in ["JPG", "JPEG"]:
                                    t_ext = F
                                elif target_fmt == "PNG":
                                    t_ext = V
                                elif target_fmt == "BMP":
                                    t_ext = ".bmp"
                                elif target_fmt == "GIF":
                                    t_ext = ".gif"
                                else:
                                    t_ext = "." + target_fmt.lower()
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
                                A1 = AA.open(src_path)
                                if C.opt_resize.get():
                                    max_dim = C.resize_max_dim.get() or 2000
                                    A1.thumbnail((max_dim, max_dim), AA.LANCZOS)
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
                                A1.save(S_, **save_params)
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
                                                A1.save(S_, quality=quality, optimize=J)
                                        except E as R:
                                            log_error_loc(
                                                "file_resize_error",
                                                file=c_,
                                                error=R,
                                            )
                                log_info_loc("image_added_modified", file=c_)
                            else:
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
                                Y_ = f"Błąd FTP: {AT}"
                        except (
                            BK.gaierror,
                            CONNECTION_REFUSED_ERROR,
                            TIMEOUT_ERROR,
                            Au,
                        ) as R:
                            Y_ = NETWORK_ERROR_MSG
                        except E as R:
                            Y_ = f"Inny błąd: {R}"
                        else:
                            try:
                                files_local = [
                                    B
                                    for B in files_to_upload
                                    if A.path.isfile(A.path.join(i_, B))
                                ]
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
                                    try:
                                        with x(Bn, "rb") as Bo:
                                            ftp.storbinary(f"STOR {BT}", Bo)
                                            BQ += 1
                                            log_info_loc(
                                                "ftp_file_uploaded", file=X_, target=BT
                                            )
                                    except E as AU:
                                        Y_ = f"Błąd wysyłania pliku {X_}: {AU}"
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
                                        if not Y_:
                                            Y_ = f"Nie udało się usunąć niektórych plików na FTP: {AI.join(Ap)}"
                                        else:
                                            Y_ += f". Nie udało się usunąć plików: {AI.join(Ap)}"
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
                            B3_ = d_["label"]
                            if d_[f]:
                                if Az_ in C.ftp_presence:
                                    remote_fname = C.ftp_presence.get(Az_)
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
                                    raise E(f"Błąd formatowania zapytania SQL: {R}")
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
                        log_error(f"SQL update error for EAN {K_}: {R}")
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
                O.showerror(
                    SQL_ERROR_LABEL,
                    SQL_UPDATE_FAILED_MSG.format(reason=result_data[P]),
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
            if D.get(u, J):
                if result_data[P]:
                    log_info_loc(
                        "sql_error", error=result_data[P], time=result_data[S]
                    )
                else:
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
            A._load_existing_files()
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
        a_.title(SETTINGS_LABEL)
        a_.grab_set()
        Z = C.Notebook(a_)
        Z.pack(expand=J, fill=z, padx=5, pady=5)
        L = C.Frame(Z)
        Q = C.Frame(Z)
        S = C.Frame(Z)
        U = C.Frame(Z)
        Z.add(L, text=IMAGES_TAB_LABEL)
        Z.add(Q, text=FTP_TAB_LABEL)
        Z.add(S, text=SQL_TAB_LABEL)
        Z.add(U, text=LANGUAGE_TAB_LABEL)
        C.Label(L, text=IMAGE_SETTINGS_LABEL).grid(
            row=0, column=0, columnspan=4, padx=5, pady=5, sticky=T
        )
        Ah = C.Checkbutton(L, text=B, variable=A.opt_resize)
        Ah.grid(row=1, column=0, padx=5, sticky=T)
        C.Label(L, text=RESIZE_LABEL).grid(row=1, column=1, sticky=T)
        l_ = C.Entry(L, textvariable=A.resize_max_dim, width=5)
        l_.grid(row=1, column=2)
        C.Label(L, text=PX_MAX_LABEL).grid(row=1, column=3, sticky=T)
        Ai = C.Checkbutton(L, text=B, variable=A.opt_compress)
        Ai.grid(row=2, column=0, padx=5, sticky=T)
        C.Label(L, text=COMPRESS_LABEL).grid(row=2, column=1, sticky=T)
        n = C.Spinbox(L, from_=10, to=100, textvariable=A.compress_quality, width=5)
        n.grid(row=2, column=2, sticky=T)
        C.Label(L, text="%").grid(row=2, column=3, sticky=T)
        Aj = C.Checkbutton(L, text=B, variable=A.opt_maxsize)
        Aj.grid(row=3, column=0, padx=5, sticky=T)
        C.Label(L, text=LIMIT_SIZE_LABEL).grid(row=3, column=1, sticky=T)
        o = C.Spinbox(
            L, from_=100, to=10000, increment=100, textvariable=A.max_file_kb, width=6
        )
        o.grid(row=3, column=2, sticky=T)
        C.Label(L, text="KB").grid(row=3, column=3, sticky=T)
        Ak = C.Checkbutton(L, text=B, variable=A.opt_convert_tif)
        Ak.grid(row=4, column=0, padx=5, sticky=T)
        C.Label(L, text=CONVERT_TIF_LABEL).grid(row=4, column=1, sticky=T)
        q = C.Combobox(
            L,
            textvariable=A.tif_target_format,
            values=[At, "JPG", "BMP", "GIF"],
            state=d_,
            width=5,
        )
        q.grid(row=4, column=2, sticky=T)
        C.Label(U, text=LANGUAGE_LABEL).grid(row=0, column=0, sticky=R, padx=5, pady=2)
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

        def Am(*B):
            l_.configure(state=X if A.opt_resize.get() else V)

        def An(*B):
            n.configure(state=X if A.opt_compress.get() else V)

        def Ao(*B):
            o.configure(state=X if A.opt_maxsize.get() else V)

        Ap = A.opt_resize.trace_add(Y_, lambda *A_: Am())
        Aq = A.opt_compress.trace_add(Y_, lambda *A_: An())
        Ar = A.opt_maxsize.trace_add(Y_, lambda *B: Ao())
        get_file_lock_user = A.opt_convert_tif.trace_add(
            Y_, lambda *B: q.configure(state=d_ if A.opt_convert_tif.get() else V)
        )
        l_.configure(state=X if A.opt_resize.get() else V)
        n.configure(state=X if A.opt_compress.get() else V)
        o.configure(state=X if A.opt_maxsize.get() else V)
        q.configure(state=d_ if A.opt_convert_tif.get() else V)
        C.Label(Q, text=FTP_SERVER_LABEL).grid(row=0, column=0, sticky=R, padx=5, pady=2)
        s = F.StringVar(value=D[H][v])
        AD_ = C.Entry(Q, textvariable=s, width=30)
        AD_.grid(row=0, column=1, padx=5, pady=2)
        C.Label(Q, text=PORT_LABEL).grid(row=1, column=0, sticky=R, padx=5, pady=2)
        t = F.IntVar(value=D[H][r])
        AE_ = C.Entry(Q, textvariable=t, width=6)
        AE_.grid(row=1, column=1, sticky=T, padx=5, pady=2)
        C.Label(Q, text=k_).grid(row=2, column=0, sticky=R, padx=5, pady=2)
        x_ = F.StringVar(value=D[H][N])
        AF_ = C.Entry(Q, textvariable=x_, width=30)
        AF_.grid(row=2, column=1, padx=5, pady=2)
        C.Label(Q, text=j_).grid(row=3, column=0, sticky=R, padx=5, pady=2)
        y_ = F.StringVar(value=D[H][M])
        AG_ = C.Entry(Q, textvariable=y_, show=Y, width=30)
        AG_.grid(row=3, column=1, padx=5, pady=2)
        C.Label(Q, text=FTP_PATH_LABEL).grid(
            row=4, column=0, sticky=R, padx=5, pady=2
        )
        g_ = F.StringVar(value=D[H][m])
        AH_ = C.Entry(Q, textvariable=g_, width=30)
        AH_.grid(row=4, column=1, padx=5, pady=2)
        AI_ = C.Button(Q, text=a)
        AI_.grid(row=5, column=0, sticky=R, padx=5, pady=5)
        C.Label(Q, text=FTP_TEST_LABEL).grid(
            row=6, column=0, sticky=R, padx=5, pady=5
        )
        AJ_ = F.StringVar(value=B)
        sql_query_entry = C.Entry(Q, textvariable=AJ_, width=50, state=d_)
        sql_query_entry.grid(row=6, column=1, padx=5, pady=5, sticky=T)

        def Ax():
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

        Ay = C.Button(Q, text=AA_, command=Ax)
        Ay.grid(row=6, column=1, padx=5, pady=5, sticky=R)
        C.Label(Q, text=FTP_UPDATE_LABEL).grid(
            row=7, column=0, sticky=R, padx=5, pady=2
        )
        ftp_update_var = F.BooleanVar(value=D.get(ft, J))
        ftp_update_cb = C.Checkbutton(Q, variable=ftp_update_var)
        ftp_update_cb.grid(row=7, column=1, sticky=T, padx=5, pady=2)
        C.Label(S, text=DB_TYPE_LABEL).grid(
            row=0, column=0, sticky=R, padx=5, pady=2
        )
        A0 = F.StringVar(value=f_ if D.get(p, K).lower() == K else A9_)
        A1 = C.Combobox(S, textvariable=A0, values=[A9_, f_], state=d_, width=20)
        A1.grid(row=0, column=1, padx=5, pady=2, sticky=T)
        U = C.Frame(S)
        W = C.Frame(S)
        C.Label(U, text=A8_).grid(row=0, column=0, sticky=R, padx=5, pady=2)
        AK = F.StringVar(value=D[P][c])
        ensure_package = C.Entry(U, textvariable=AK, width=30)
        ensure_package.grid(row=0, column=1, padx=5, pady=2)
        C.Label(U, text=A7_).grid(row=1, column=0, sticky=R, padx=5, pady=2)
        AM = F.StringVar(value=D[P][b])
        AN = C.Entry(U, textvariable=AM, width=30)
        AN.grid(row=1, column=1, padx=5, pady=2)
        C.Label(U, text=k_).grid(row=2, column=0, sticky=R, padx=5, pady=2)
        AO = F.StringVar(value=D[P][N])
        AQ = C.Entry(U, textvariable=AO, width=30)
        AQ.grid(row=2, column=1, padx=5, pady=2)
        C.Label(U, text=j_).grid(row=3, column=0, sticky=R, padx=5, pady=2)
        AR = F.StringVar(value=D[P][M])
        AS = C.Entry(U, textvariable=AR, show=Y, width=30)
        AS.grid(row=3, column=1, padx=5, pady=2)
        U.grid(row=1, column=0, columnspan=2, sticky=T, padx=5, pady=2)
        C.Label(W, text=A8_).grid(row=0, column=0, sticky=R, padx=5, pady=2)
        AT = F.StringVar(value=D[K][c])
        AU = C.Entry(W, textvariable=AT, width=30)
        AU.grid(row=0, column=1, padx=5, pady=2)
        C.Label(W, text=A7_).grid(row=1, column=0, sticky=R, padx=5, pady=2)
        AV = F.StringVar(value=D[K][b])
        AW = C.Entry(W, textvariable=AV, width=30)
        AW.grid(row=1, column=1, padx=5, pady=2)
        C.Label(W, text=k_).grid(row=2, column=0, sticky=R, padx=5, pady=2)
        AX = F.StringVar(value=D[K][N])
        AY = C.Entry(W, textvariable=AX, width=30)
        AY.grid(row=2, column=1, padx=5, pady=2)
        C.Label(W, text=j_).grid(row=3, column=0, sticky=R, padx=5, pady=2)
        AZ = F.StringVar(value=D[K][M])
        Aa = C.Entry(W, textvariable=AZ, show=Y, width=30)
        Aa.grid(row=3, column=1, padx=5, pady=2)
        W.grid(row=1, column=0, columnspan=2, sticky=T, padx=5, pady=2)
        if D.get(p, K).lower() == K:
            U.grid_remove()
        else:
            W.grid_remove()

        def Az(event=I):
            if A0.get() == f_:
                U.grid_remove()
                W.grid()
            else:
                W.grid_remove()
                U.grid()

        A1.bind(A2, Az)
        C.Label(S, text=SQL_UPDATE_LABEL).grid(
            row=2, column=0, sticky=R, padx=5, pady=2
        )
        Ab = F.BooleanVar(value=D.get(u, J))
        Ac = C.Checkbutton(S, variable=Ab)
        Ac.grid(row=2, column=1, sticky=T, padx=5, pady=2)
        C.Label(S, text=SQL_QUERY_LABEL).grid(
            row=3, column=0, sticky="ne", padx=5, pady=2
        )
        h_ = F.Text(S, width=80, height=3)
        h_.insert(A_, D.get(w, SQL_UPDATE_TEMPLATE))
        h_.grid(row=3, column=1, padx=5, pady=2, sticky=T)
        C.Label(S, text=SQL_TEST_LABEL).grid(
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
                A3_.set(f"Błąd: {C_}")

        EDIT_LISTS_LABEL = C.Button(S, text=AA_, command=INCOMPLETE_DATA_MSG)
        EDIT_LISTS_LABEL.grid(row=4, column=1, padx=5, pady=5, sticky=R)

        def Ad(state):
            A_ = state
            AD_.configure(state=A_)
            AE_.configure(state=A_)
            AF_.configure(state=A_)
            AG_.configure(state=A_)
            AH_.configure(state=A_)

        def Ae(state_text, editor=Al):
            B_ = state_text
            A__ = B_
            C_ = X if B_ == X else V
            if D.get(p, K).lower() == K:
                AU.configure(state=A__)
                AW.configure(state=A__)
                AY.configure(state=A__)
                Aa.configure(state=A__)
            else:
                ensure_package.configure(state=A__)
                AN.configure(state=A__)
                AQ.configure(state=A__)
                AS.configure(state=A__)
            A1.configure(state=i_ if editor else A__)
            h_.configure(state=C_)
            Ac.configure(state=X)

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
        A4 = C.Frame(a_)
        A4.pack(pady=5)

        def BD_():
            global LANG_PREF
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
            D[p] = K if A0.get() == f_ else "mssql"
            D[w] = h_.get(A_, "end").strip()
            D[u] = bool(Ab.get())
            new_lang_pref = lang_var.get().strip()
            save_language_pref(new_lang_pref)
            LANG_PREF = new_lang_pref
            localization.LANG_PREF = LANG_PREF
            save_config(D)
            log_info_loc("settings_saved")
            Af()

        C.Button(A4, text=SAVE_LABEL, command=BD_).grid(row=0, column=0, padx=5)

        def Af():
            A.opt_resize.trace_remove(Y_, Ap)
            A.opt_compress.trace_remove(Y_, Aq)
            A.opt_maxsize.trace_remove(Y_, Ar)
            A.opt_convert_tif.trace_remove(Y_, get_file_lock_user)
            a_.destroy()

        C.Button(A4, text=CANCEL_LABEL, command=Af).grid(row=0, column=1, padx=5)
        a_.protocol("WM_DELETE_WINDOW", Af)
        Z.select(0)

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


