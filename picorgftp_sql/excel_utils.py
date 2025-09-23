"""Excel-related helpers for managing lists and entries."""

from .common import *  # noqa: F401,F403
from .settings import AE, o
from .logging_utils import log_error_loc, log_info_loc
from .system_utils import get_file_lock_user
from . import localization

Aw = [
    ("01", "Assembly_instruction"),
    ("02", "Assembly_instruction1"),
    ("03", "DETAIL_pic"),
    ("04", "DETAIL_pic1"),
    ("05", "element_pic1"),
    ("06", ELEMENT_PIC),
    ("07", "LED_Assembly_instruction"),
    ("08", "MOOD_pic"),
    ("09", "MOOD_pic1"),
    ("10", "MOOD_pic2"),
    ("11", "MOOD_pic3"),
    ("12", "MOOD_pic4"),
    ("13", "MOOD_pic5"),
    ("14", NON_PIC),
    ("15", OPEN_FURNITURE),
    ("16", "open_furniture1"),
    ("17", "open_furniture2"),
    ("18", "NO_EAN"),
    ("19", "Technical_drawing"),
    ("20", "Technical_drawing1"),
    ("21", "Technical_drawing2"),
    ("22", "WB_pic"),
    ("23", "WB_pic1"),
    ("24", "WB_pic2"),
    ("25", "WB_pic3"),
    ("26", "WB_pic4"),
]


def label_category(label):
    base = label.rstrip("0123456789")
    if base.startswith("LED_"):
        base = base[4:]
    lowered = base.lower()
    if "assembly_instruction" in lowered:
        return "ASSEMBLY"
    if "technical_drawing" in lowered:
        return "TECHNICAL"
    if "mood_pic" in lowered:
        return "MOOD"
    if "wb_pic" in lowered:
        return "WB"
    if "detail_pic" in lowered:
        return "DETAIL"
    if ELEMENT_PIC in lowered:
        return "ELEMENT"
    if OPEN_FURNITURE in lowered:
        return "OPEN-FURNITURE"
    if "no_ean" in lowered:
        return "NO-EAN"
    if NON_PIC in lowered:
        return "NON-PIC"
    return base.replace(a, g).upper()


def prepare_excel_lists():
    if not A.path.isdir(A.path.dirname(o)):
        A.makedirs(A.path.dirname(o), exist_ok=J)
    if not A.path.exists(o):
        workbook = BV()
        workbook.remove(workbook.active)
        for sheet_name in AE.values():
            sheet = workbook.create_sheet(title=sheet_name)
            if sheet_name == W:
                sheet.append(["EAN", Ae, Ad, AZ, AY, AX, AW, d])
        try:
            workbook.save(o)
        except E as exc:
            O.showerror(AK, localization.LIST_CREATE_FAILED_MSG.format(error=exc))
            log_error_loc("excel_create_failed", error=exc)
    workbook = Ah(o)
    lists = {}
    for sheet_name in AE.values():
        sheet = workbook[sheet_name]
        if sheet_name == W:
            entries = {}
            for row in sheet.iter_rows(min_row=2, values_only=J):
                if not row[0]:
                    continue
                ean = G(row[0]).strip()
                name = G(row[1]) if row[1] else B
                typ = G(row[2]) if row[2] else B
                model = G(row[3]) if row[3] else B
                col1 = G(row[4]) if row[4] else B
                col2 = G(row[5]) if row[5] else B
                col3 = G(row[6]) if row[6] else B
                extra = G(row[7]) if row[7] else B
                name = name.strip().upper()
                typ = typ.strip().upper()
                model = model.strip().upper()
                col1 = col1.strip().upper()
                col2 = col2.strip().upper()
                col3 = col3.strip().upper()
                extra = extra.strip().replace(a, g).upper()
                entries[ean] = {Ae: name, Ad: typ, AZ: model, AY: col1, AX: col2, AW: col3, d: extra}
            lists[sheet_name] = entries
        else:
            values = []
            for cell in sheet["A"]:
                if cell.value:
                    raw = G(cell.value).strip()
                    if sheet_name == d:
                        raw = raw.replace(a, g)
                    raw = raw.upper()
                    if raw not in values:
                        values.append(raw)
            lists[sheet_name] = values
    return lists


def add_to_list(sheet_name, value):
    if not value:
        return
    normalized = G(value).strip().upper()
    if sheet_name == AE[d]:
        normalized = normalized.replace(a, g)
    locked_by = get_file_lock_user(o)
    if locked_by:
        reason = f"przez użytkownika '{locked_by}'" if Aq(locked_by, G) else Ap
        O.showerror(
            Ao,
            localization.LANG.get(
                "excel_file_open",
                "Nie można zapisać listy. Plik Excel jest otwarty {reason}. Zamknij plik i spróbuj ponownie.",
            ).format(reason=reason),
        )
        log_error_loc("excel_add_locked", value=normalized, list=sheet_name, reason=reason)
        return
    workbook = Ah(o)
    sheet = workbook[sheet_name]
    existing = [G(cell.value).strip().upper() for cell in sheet["A"] if cell.value]
    if normalized not in existing:
        sheet.append([normalized])
        try:
            workbook.save(o)
        except E as exc:
            O.showerror(Ac, localization.LIST_SAVE_FAILED_MSG.format(error=exc))
            log_error_loc("excel_add_save_failed", value=normalized, list=sheet_name, error=exc)
            return
        log_info_loc("list_value_added", value=normalized, list=sheet_name)


def remove_from_list(sheet_name, value):
    locked_by = get_file_lock_user(o)
    if locked_by:
        reason = f"przez użytkownika '{locked_by}'" if Aq(locked_by, G) else Ap
        O.showerror(
            Ao,
            localization.LANG.get(
                "excel_file_open",
                "Nie można zapisać listy. Plik Excel jest otwarty {reason}. Zamknij plik i spróbuj ponownie.",
            ).format(reason=reason),
        )
        log_error_loc("excel_remove_locked", value=value, list=sheet_name, reason=reason)
        return
    workbook = Ah(o)
    sheet = workbook[sheet_name]
    removed = Ay
    for row in list(sheet.iter_rows(min_row=1)):
        cell = row[0]
        if cell.value and G(cell.value).strip().upper() == G(value).strip().upper():
            sheet.delete_rows(cell.row)
            removed = J
            break
    if removed:
        try:
            workbook.save(o)
        except E as exc:
            O.showerror(Ac, localization.LIST_SAVE_FAILED_MSG.format(error=exc))
            log_error_loc("excel_remove_save_failed", value=value, list=sheet_name, error=exc)
            return
        log_info_loc("list_value_removed", value=value, list=sheet_name)


def save_ean_entry(ean, name, typ, model, col1, col2, col3, extra):
    locked_by = get_file_lock_user(o)
    if locked_by:
        reason = f"przez użytkownika '{locked_by}'" if Aq(locked_by, G) else Ap
        O.showerror(
            Ao,
            localization.LANG.get(
                "excel_data_file_open",
                "Nie można zapisać danych. Plik Excel jest otwarty {reason}. Zamknij plik i spróbuj ponownie.",
            ).format(reason=reason),
        )
        log_error_loc("excel_entry_save_locked", ean=ean, reason=reason)
        return h
    workbook = Ah(o)
    sheet = workbook[AE[W]]
    name = G(name).strip().upper()
    typ = G(typ).strip().upper()
    model = G(model).strip().upper()
    col1 = G(col1).strip().upper()
    col2 = G(col2).strip().upper() if col2 else B
    col3 = G(col3).strip().upper() if col3 else B
    extra_value = G(extra).strip()
    if extra_value == B or extra_value.upper() in [L, L]:
        extra_value = L
    else:
        extra_value = extra_value.replace(a, g).upper()
    updated = h
    target_row = I
    for row in sheet.iter_rows(min_row=2):
        raw_ean = row[0].value
        if raw_ean is I:
            continue
        if G(raw_ean).upper() == G(ean).upper():
            target_row = row
            updated = J
            break
    if target_row:
        target_row[1].value = name
        target_row[2].value = typ
        target_row[3].value = model
        target_row[4].value = col1
        target_row[5].value = col2 or B
        target_row[6].value = col3 or B
        target_row[7].value = extra_value
    else:
        trimmed = G(ean).strip()
        if trimmed.upper() != q:
            candidate = I
            for row in sheet.iter_rows(min_row=2):
                raw = G(row[0].value).strip().upper() if row[0].value else B
                if raw == q:
                    existing_name = G(row[1].value).strip().upper() if row[1].value else B
                    existing_typ = G(row[2].value).strip().upper() if row[2].value else B
                    existing_model = G(row[3].value).strip().upper() if row[3].value else B
                    existing_col1 = G(row[4].value).strip().upper() if row[4].value else B
                    existing_col2 = G(row[5].value).strip().upper() if row[5].value else B
                    existing_col3 = G(row[6].value).strip().upper() if row[6].value else B
                    existing_extra = G(row[7].value).strip() if row[7].value else B
                    existing_extra = existing_extra.replace(a, g).upper()
                    if (
                        existing_name == name
                        and existing_typ == typ
                        and existing_model == model
                        and existing_col1 == col1
                        and existing_col2 == (col2 or B)
                        and existing_col3 == (col3 or B)
                        and existing_extra == extra_value
                    ):
                        candidate = row
                        updated = J
                        break
            if candidate:
                candidate[0].value = G(ean)
                candidate[1].value = name
                candidate[2].value = typ
                candidate[3].value = model
                candidate[4].value = col1
                candidate[5].value = col2 or B
                candidate[6].value = col3 or B
                candidate[7].value = extra_value
            else:
                sheet.append([G(ean), name, typ, model, col1, col2 or B, col3 or B, extra_value])
        else:
            candidate = I
            for row in sheet.iter_rows(min_row=2):
                raw = G(row[0].value).strip().upper() if row[0].value else B
                if raw == q:
                    existing_name = G(row[1].value).strip().upper() if row[1].value else B
                    existing_typ = G(row[2].value).strip().upper() if row[2].value else B
                    existing_model = G(row[3].value).strip().upper() if row[3].value else B
                    existing_col1 = G(row[4].value).strip().upper() if row[4].value else B
                    existing_col2 = G(row[5].value).strip().upper() if row[5].value else B
                    existing_col3 = G(row[6].value).strip().upper() if row[6].value else B
                    existing_extra = G(row[7].value).strip() if row[7].value else B
                    existing_extra = existing_extra.replace(a, g).upper()
                    if (
                        existing_name == name
                        and existing_typ == typ
                        and existing_model == model
                        and existing_col1 == col1
                        and existing_col2 == (col2 or B)
                        and existing_col3 == (col3 or B)
                        and existing_extra == extra_value
                    ):
                        candidate = row
                        updated = J
                        break
            if candidate:
                candidate[1].value = name
                candidate[2].value = typ
                candidate[3].value = model
                candidate[4].value = col1
                candidate[5].value = col2 or B
                candidate[6].value = col3 or B
                candidate[7].value = extra_value
            else:
                sheet.append([G(ean), name, typ, model, col1, col2 or B, col3 or B, extra_value])
    try:
        workbook.save(o)
    except E as exc:
        O.showerror(Ac, localization.LIST_DATA_SAVE_FAILED_MSG.format(error=exc))
        log_error_loc("excel_entry_save_failed", ean=ean, error=exc)
        return h
    return J
