"""Utilities for maintaining the Excel lists used by the application."""

from __future__ import annotations

import os
from typing import Dict

from openpyxl import Workbook, load_workbook
from tkinter import messagebox

from .common import ELEMENT_PIC, NON_PIC, OPEN_FURNITURE
from .logging_utils import log_error_loc, log_info_loc
from .system_utils import get_file_lock_user
from . import localization
from .settings import EXCEL_SHEETS, LISTS_WORKBOOK_PATH

ENTRY_SHEET = "ENTRIES"
NAME_HEADER = "NAZWA"
TYPE_HEADER = "TYP"
MODEL_HEADER = "MODEL"
COLOR1_HEADER = "KOLOR1"
COLOR2_HEADER = "KOLOR2"
COLOR3_HEADER = "KOLOR3"
EXTRA_HEADER = "DODATKI"
EXTRAS_SHEET = "DODATKI"
ENTRY_HEADERS = [
    "EAN",
    NAME_HEADER,
    TYPE_HEADER,
    MODEL_HEADER,
    COLOR1_HEADER,
    COLOR2_HEADER,
    COLOR3_HEADER,
    EXTRA_HEADER,
]

NO_EAN_PLACEHOLDER = "BRAK-EAN"
NO_LED_VALUE = "NO-LED"
EMPTY = ""
UNDERSCORE = "_"
HYPHEN = "-"
LOCKED_TITLE = "Plik zablokowany"
LOCKED_REASON_OTHER_PROCESS = "przez inny proces"
ERROR_TITLE = "Błąd"
WRITE_ERROR_TITLE = "Błąd zapisu"

# Order used by the GUI when building slot labels.
SLOT_LABELS = [
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


def label_category(label: str) -> str:
    """Return a human-readable category for a slot label."""

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
    return base.replace(UNDERSCORE, HYPHEN).upper()


def _normalize_cell(value: object) -> str:
    """Normalize a worksheet cell value into a stripped string."""

    if value is None:
        return EMPTY
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _ensure_workbook_exists() -> None:
    """Create the workbook on disk if it is missing."""

    base_dir = os.path.dirname(LISTS_WORKBOOK_PATH)
    if not os.path.isdir(base_dir):
        os.makedirs(base_dir, exist_ok=True)
    if os.path.exists(LISTS_WORKBOOK_PATH):
        return
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name in EXCEL_SHEETS.values():
        sheet = workbook.create_sheet(title=sheet_name)
        if sheet_name == ENTRY_SHEET:
            sheet.append(ENTRY_HEADERS)
    try:
        workbook.save(LISTS_WORKBOOK_PATH)
    except Exception as exc:  # pylint: disable=broad-except
        messagebox.showerror(ERROR_TITLE, localization.LIST_CREATE_FAILED_MSG.format(error=exc))
        log_error_loc("excel_create_failed", error=exc)


def _load_workbook():
    """Load the shared workbook, ensuring it exists first."""

    _ensure_workbook_exists()
    return load_workbook(LISTS_WORKBOOK_PATH)


def prepare_excel_lists() -> Dict[str, Dict[str, dict] | list]:
    """Load all Excel lists into memory."""

    workbook = _load_workbook()
    lists: Dict[str, Dict[str, dict] | list] = {}
    for sheet_name in EXCEL_SHEETS.values():
        sheet = workbook[sheet_name]
        if sheet_name == ENTRY_SHEET:
            entries: Dict[str, dict] = {}
            for row in sheet.iter_rows(min_row=2, values_only=True):
                ean = _normalize_cell(row[0])
                if not ean:
                    continue
                name = _normalize_cell(row[1]).upper()
                furniture_type = _normalize_cell(row[2]).upper()
                model = _normalize_cell(row[3]).upper()
                color1 = _normalize_cell(row[4]).upper()
                color2 = _normalize_cell(row[5]).upper()
                color3 = _normalize_cell(row[6]).upper()
                extra = _normalize_cell(row[7]).replace(UNDERSCORE, HYPHEN).upper()
                entries[ean.strip()] = {
                    NAME_HEADER: name,
                    TYPE_HEADER: furniture_type,
                    MODEL_HEADER: model,
                    COLOR1_HEADER: color1,
                    COLOR2_HEADER: color2,
                    COLOR3_HEADER: color3,
                    EXTRA_HEADER: extra,
                }
            lists[sheet_name] = entries
        else:
            values: list[str] = []
            for cell in sheet["A"]:
                if not cell.value:
                    continue
                raw = str(cell.value).strip()
                if sheet_name == EXTRAS_SHEET:
                    raw = raw.replace(UNDERSCORE, HYPHEN)
                normalized = raw.upper()
                if normalized not in values:
                    values.append(normalized)
            lists[sheet_name] = values
    return lists


def _show_locked_dialog(reason: str) -> None:
    """Inform the user that the workbook is locked by another process."""

    title = LOCKED_TITLE
    text = localization.LANG.get(
        "excel_file_open",
        "Nie można zapisać listy. Plik Excel jest otwarty {reason}. Zamknij plik i spróbuj ponownie.",
    ).format(reason=reason)
    messagebox.showerror(title, text)


def _save_workbook(workbook: Workbook, error_event: str, **context) -> bool:
    """Persist the workbook and log a translated error message on failure."""

    try:
        workbook.save(LISTS_WORKBOOK_PATH)
        return True
    except Exception as exc:  # pylint: disable=broad-except
        messagebox.showerror(WRITE_ERROR_TITLE, localization.LIST_SAVE_FAILED_MSG.format(error=exc))
        context.setdefault("error", exc)
        log_error_loc(error_event, **context)
        return False


def add_to_list(sheet_name: str, value: str) -> None:
    """Append a new normalised value to the given list sheet."""

    if not value:
        return
    normalized = value.strip().upper()
    if sheet_name == EXCEL_SHEETS[EXTRAS_SHEET]:
        normalized = normalized.replace(UNDERSCORE, HYPHEN)
    locked_by = get_file_lock_user(LISTS_WORKBOOK_PATH)
    if locked_by:
        reason = f"przez użytkownika '{locked_by}'" if isinstance(locked_by, str) else LOCKED_REASON_OTHER_PROCESS
        _show_locked_dialog(reason)
        log_error_loc("excel_add_locked", value=normalized, list=sheet_name, reason=reason)
        return
    workbook = _load_workbook()
    sheet = workbook[sheet_name]
    existing = {str(cell.value).strip().upper() for cell in sheet["A"] if cell.value}
    if normalized in existing:
        return
    sheet.append([normalized])
    if _save_workbook(
        workbook,
        "excel_add_save_failed",
        value=normalized,
        list=sheet_name,
    ):
        log_info_loc("list_value_added", value=normalized, list=sheet_name)


def remove_from_list(sheet_name: str, value: str) -> None:
    """Remove the first occurrence of ``value`` from the target sheet."""

    locked_by = get_file_lock_user(LISTS_WORKBOOK_PATH)
    if locked_by:
        reason = f"przez użytkownika '{locked_by}'" if isinstance(locked_by, str) else LOCKED_REASON_OTHER_PROCESS
        _show_locked_dialog(reason)
        log_error_loc("excel_remove_locked", value=value, list=sheet_name, reason=reason)
        return
    workbook = _load_workbook()
    sheet = workbook[sheet_name]
    removed = False
    for row in list(sheet.iter_rows(min_row=1)):
        cell = row[0]
        if cell.value and str(cell.value).strip().upper() == value.strip().upper():
            sheet.delete_rows(cell.row)
            removed = True
            break
    if removed and _save_workbook(
        workbook,
        "excel_remove_save_failed",
        value=value,
        list=sheet_name,
    ):
        log_info_loc("list_value_removed", value=value, list=sheet_name)


def _update_row(row, name, furniture_type, model, color1, color2, color3, extra_value):
    """Mutate a worksheet row with the supplied normalised values."""

    row[1].value = name
    row[2].value = furniture_type
    row[3].value = model
    row[4].value = color1
    row[5].value = color2 or EMPTY
    row[6].value = color3 or EMPTY
    row[7].value = extra_value


def save_ean_entry(
    ean: str,
    name: str,
    furniture_type: str,
    model: str,
    color1: str,
    color2: str,
    color3: str,
    extra: str,
) -> bool:
    """Insert or update a row in the entries sheet, handling locks gracefully."""

    locked_by = get_file_lock_user(LISTS_WORKBOOK_PATH)
    if locked_by:
        reason = f"przez użytkownika '{locked_by}'" if isinstance(locked_by, str) else LOCKED_REASON_OTHER_PROCESS
        messagebox = localization.O if hasattr(localization, "O") else None
        if messagebox:
            messagebox.showerror(
                LOCKED_TITLE,
                localization.LANG.get(
                    "excel_data_file_open",
                    "Nie można zapisać danych. Plik Excel jest otwarty {reason}. Zamknij plik i spróbuj ponownie.",
                ).format(reason=reason),
            )
        log_error_loc("excel_entry_save_locked", ean=ean, reason=reason)
        return False

    workbook = _load_workbook()
    sheet = workbook[EXCEL_SHEETS[ENTRY_SHEET]]

    name = str(name).strip().upper()
    furniture_type = str(furniture_type).strip().upper()
    model = str(model).strip().upper()
    color1 = str(color1).strip().upper()
    color2 = str(color2).strip().upper() if color2 else EMPTY
    color3 = str(color3).strip().upper() if color3 else EMPTY
    extra_raw = str(extra).strip()
    if not extra_raw or extra_raw.upper() in {NO_LED_VALUE, NO_LED_VALUE.upper()}:
        extra_value = NO_LED_VALUE
    else:
        extra_value = extra_raw.replace(UNDERSCORE, HYPHEN).upper()

    updated = False
    target_row = None
    for row in sheet.iter_rows(min_row=2):
        raw_ean = row[0].value
        if raw_ean is None:
            continue
        if str(raw_ean).strip().upper() == str(ean).strip().upper():
            target_row = row
            updated = True
            break

    if target_row is not None:
        _update_row(target_row, name, furniture_type, model, color1, color2, color3, extra_value)
    else:
        trimmed = str(ean).strip()
        if trimmed.upper() != NO_EAN_PLACEHOLDER:
            candidate = None
            for row in sheet.iter_rows(min_row=2):
                raw = str(row[0].value or EMPTY).strip().upper()
                if raw == NO_EAN_PLACEHOLDER:
                    existing = {
                        NAME_HEADER: str(row[1].value or EMPTY).strip().upper(),
                        TYPE_HEADER: str(row[2].value or EMPTY).strip().upper(),
                        MODEL_HEADER: str(row[3].value or EMPTY).strip().upper(),
                        COLOR1_HEADER: str(row[4].value or EMPTY).strip().upper(),
                        COLOR2_HEADER: str(row[5].value or EMPTY).strip().upper(),
                        COLOR3_HEADER: str(row[6].value or EMPTY).strip().upper(),
                        EXTRA_HEADER: str(row[7].value or EMPTY).strip().replace(UNDERSCORE, HYPHEN).upper(),
                    }
                    if (
                        existing[NAME_HEADER] == name
                        and existing[TYPE_HEADER] == furniture_type
                        and existing[MODEL_HEADER] == model
                        and existing[COLOR1_HEADER] == color1
                        and existing[COLOR2_HEADER] == color2.upper()
                        and existing[COLOR3_HEADER] == color3.upper()
                        and existing[EXTRA_HEADER] == extra_value
                    ):
                        candidate = row
                        updated = True
                        break
            if candidate is not None:
                candidate[0].value = str(ean)
                _update_row(candidate, name, furniture_type, model, color1, color2, color3, extra_value)
            else:
                sheet.append(
                    [
                        str(ean),
                        name,
                        furniture_type,
                        model,
                        color1,
                        color2 or EMPTY,
                        color3 or EMPTY,
                        extra_value,
                    ]
                )
        else:
            sheet.append(
                [
                    str(ean),
                    name,
                    furniture_type,
                    model,
                    color1,
                    color2 or EMPTY,
                    color3 or EMPTY,
                    extra_value,
                ]
            )

    if _save_workbook(workbook, "excel_entry_save_failed", ean=ean):
        action = "updated" if updated else "added"
        log_info_loc("excel_entry_saved", ean=ean, action=action)
        return True
    return False


# Backwards compatibility with the original constant name expected by app.py
Aw = SLOT_LABELS
