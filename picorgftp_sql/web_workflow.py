"""Web upload workflow shared by the local LAN backend."""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
from typing import Sequence

from .common import (
    AUTO_CONTENT_FIT_KEY,
    ELEMENT_PIC,
    NON_PIC,
    OPEN_FURNITURE,
    SLOT_DEFS_KEY,
)
from .image_utils import fit_image_to_content
from .slot_utils import normalize_slot_definitions
from .workflow_utils import (
    NO_EAN_PLACEHOLDER,
    NO_EXTRA_PLACEHOLDER,
    build_product_directory,
    build_slot_filename,
    normalize_color_slots,
    normalize_extra_segment,
)

try:  # pragma: no cover - optional runtime dependency
    from PIL import Image
except Exception:  # pragma: no cover - handled when image processing is requested
    Image = None


IMAGE_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


@dataclass(frozen=True)
class WebProductForm:
    """Product data submitted from the browser."""

    name: str
    type_name: str
    model: str
    color1: str
    color2: str = ""
    color3: str = ""
    extra: str = ""
    ean: str = ""
    product_id: str = ""


@dataclass(frozen=True)
class WebUploadedSlot:
    """Uploaded file assigned to a configured photo slot."""

    prefix: str
    label: str
    source_path: str
    original_filename: str = ""
    content_fit: bool = False


@dataclass(frozen=True)
class WebProcessingOptions:
    """Image processing options for the web workflow."""

    resize_enabled: bool = True
    max_dim: int = 2000
    compress_enabled: bool = False
    compress_quality: int = 85
    auto_content_fit: bool = False


@dataclass(frozen=True)
class WebProcessedFile:
    """Single file saved by the web workflow."""

    prefix: str
    label: str
    source_name: str
    filename: str
    path: str
    size_bytes: int


@dataclass(frozen=True)
class WebProcessingResult:
    """Summary returned to the web API after processing uploads."""

    output_dir: str
    ean: str
    saved_files: list[WebProcessedFile]
    skipped_slots: list[str]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _slot_category(label: str) -> str:
    """Return the filename category used by the desktop workflow."""

    base = _clean(label).rstrip("0123456789")
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
    return base.replace("_", "-").upper()


def slot_definitions_from_config(config_dict: dict) -> list[dict[str, str]]:
    """Return normalized slot definitions from a runtime config dict."""

    slots, _issues = normalize_slot_definitions(config_dict.get(SLOT_DEFS_KEY))
    return slots


def validate_product_form(form: WebProductForm) -> list[str]:
    """Return validation errors for the browser product form."""

    errors = []
    if not _clean(form.name):
        errors.append("Nazwa produktu jest wymagana.")
    if not _clean(form.type_name):
        errors.append("Typ produktu jest wymagany.")
    if not _clean(form.model):
        errors.append("Model produktu jest wymagany.")
    if not _clean(form.color1):
        errors.append("Kolor 1 jest wymagany.")
    ean = _clean(form.ean)
    if ean and ean != NO_EAN_PLACEHOLDER and (not ean.isdigit() or len(ean) != 13):
        errors.append("EAN musi miec 13 cyfr albo zostac pusty.")
    return errors


def normalized_product_payload(form: WebProductForm) -> dict[str, object]:
    """Normalize product fields in the same direction as the desktop workflow."""

    colors = normalize_color_slots([form.color1, form.color2, form.color3])
    extra = normalize_extra_segment(form.extra, fallback=NO_EXTRA_PLACEHOLDER)
    ean = _clean(form.ean) or NO_EAN_PLACEHOLDER
    return {
        "name": _clean(form.name),
        "type_name": _clean(form.type_name),
        "model": _clean(form.model),
        "colors": colors,
        "extra": extra,
        "ean": ean,
    }


def _resample_filter():
    if Image is not None and hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", 3))


def _save_processed_file(
    source_path: str,
    target_path: str,
    options: WebProcessingOptions,
    *,
    content_fit: bool = False,
) -> None:
    """Copy or lightly process a browser-uploaded file to its target path."""

    ext = os.path.splitext(source_path)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        shutil.copy2(source_path, target_path)
        return
    if Image is None:
        shutil.copy2(source_path, target_path)
        return

    with Image.open(source_path) as image:
        work = image.copy()
        if options.auto_content_fit or content_fit:
            work = fit_image_to_content(work)
        if options.resize_enabled:
            max_dim = max(1, int(options.max_dim or 2000))
            work.thumbnail((max_dim, max_dim), _resample_filter())

        save_params = {}
        if ext in {".jpg", ".jpeg"}:
            if work.mode in ("RGBA", "LA", "P"):
                work = work.convert("RGB")
            quality = max(1, min(100, int(options.compress_quality or 85)))
            save_params["quality"] = quality if options.compress_enabled else 95
            save_params["optimize"] = True
        elif ext == ".png":
            save_params["optimize"] = True

        work.save(target_path, **save_params)


def process_web_uploads(
    *,
    base_output_dir: str,
    form: WebProductForm,
    uploaded_slots: Sequence[WebUploadedSlot],
    options: WebProcessingOptions | None = None,
) -> WebProcessingResult:
    """Save uploaded slot files into the product folder tree."""

    errors = validate_product_form(form)
    if errors:
        raise ValueError(" ".join(errors))
    if not uploaded_slots:
        raise ValueError("Dodaj przynajmniej jeden plik do slotu.")

    payload = normalized_product_payload(form)
    options = options or WebProcessingOptions()
    output_dir = build_product_directory(
        base_output_dir,
        payload["name"],
        payload["type_name"],
        payload["model"],
        payload["colors"],
        payload["extra"],
    )
    os.makedirs(output_dir, exist_ok=True)

    saved_files: list[WebProcessedFile] = []
    skipped_slots: list[str] = []
    for upload in uploaded_slots:
        source_path = _clean(upload.source_path)
        if not source_path or not os.path.isfile(source_path):
            skipped_slots.append(upload.prefix)
            continue
        ext = os.path.splitext(upload.original_filename or source_path)[1]
        if not ext:
            ext = os.path.splitext(source_path)[1]
        if not ext:
            skipped_slots.append(upload.prefix)
            continue
        filename = build_slot_filename(
            payload["ean"],
            upload.prefix,
            _slot_category(upload.label),
            payload["name"],
            payload["type_name"],
            payload["model"],
            payload["colors"],
            payload["extra"],
            ext.lower(),
        )
        target_path = os.path.join(output_dir, filename)
        _save_processed_file(source_path, target_path, options, content_fit=upload.content_fit)
        saved_files.append(
            WebProcessedFile(
                prefix=upload.prefix,
                label=upload.label,
                source_name=os.path.basename(upload.original_filename or source_path),
                filename=filename,
                path=target_path,
                size_bytes=os.path.getsize(target_path),
            )
        )

    if not saved_files:
        raise ValueError("Nie zapisano zadnego pliku.")
    return WebProcessingResult(
        output_dir=output_dir,
        ean=str(payload["ean"]),
        saved_files=saved_files,
        skipped_slots=skipped_slots,
    )


def processing_options_from_config(config_dict: dict) -> WebProcessingOptions:
    """Build conservative web defaults from the existing runtime config."""

    return WebProcessingOptions(
        resize_enabled=True,
        max_dim=2000,
        compress_enabled=False,
        compress_quality=85,
        auto_content_fit=bool(config_dict.get(AUTO_CONTENT_FIT_KEY, False)),
    )
