"""Tests for web API file token and local deletion helpers."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from picorgftp_sql.web import app as web_app

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional test dependency
    Image = None


def _workspace_temp(name: str) -> Path:
    root = Path(__file__).resolve().parents[1] / "tmp_test" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


class _MemoryUpload:
    def __init__(self, filename: str, chunks: list[bytes], content_type: str = "image/jpeg") -> None:
        self.filename = filename
        self.content_type = content_type
        self._chunks = list(chunks)
        self.closed = False

    async def read(self, _size: int = -1) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    async def close(self) -> None:
        self.closed = True


class WebAppFileTests(unittest.TestCase):
    def _image_bytes(self, image_format: str, mode: str = "RGB") -> bytes:
        if Image is None:
            self.skipTest("Pillow unavailable")
        buffer = io.BytesIO()
        color = 1 if mode == "1" else 255 if mode == "L" else "white"
        Image.new(mode, (16, 16), color).save(buffer, format=image_format)
        return buffer.getvalue()

    def _optional_image_bytes(self, image_format: str, mode: str = "RGB") -> bytes | None:
        try:
            return self._image_bytes(image_format, mode)
        except Exception:
            return None

    def _ftyp_payload(self, brand: bytes) -> bytes:
        return b"\x00\x00\x00\x18ftyp" + brand + b"\x00\x00\x00\x00" + brand + b"mif1"

    def test_output_identity_ignores_disabled_product_fields(self) -> None:
        first = web_app.WebProductForm(
            name="MAGGIORE",
            type_name="KOMODA",
            model="MA03",
            color1="BIALY",
            ean="5901234567890",
        )
        second = web_app.WebProductForm(
            name="MAGGIORE",
            type_name="STOL",
            model="MA03",
            color1="BIALY",
            ean="5901234567890",
        )

        with (
            patch.object(
                web_app.config,
                "CONFIG",
                {"product_fields": {"type": {"enabled": False}}},
            ),
            patch.object(web_app.settings, "l", "C:\\processed"),
        ):
            self.assertEqual(
                web_app._output_identity(first),
                web_app._output_identity(second),
            )

    def test_delete_token_can_be_resolved_after_file_disappears(self) -> None:
        temp_dir = _workspace_temp("web_app_delete_token")
        try:
            processed = temp_dir / "processed"
            processed.mkdir()
            target = processed / "old.jpg"
            target.write_bytes(b"old")
            token = web_app._file_token(str(target))
            target.unlink()

            with (
                patch.object(web_app.settings, "l", str(processed)),
                patch.object(web_app.settings, "AC", str(temp_dir)),
            ):
                self.assertEqual(
                    Path(web_app._path_from_file_token(token, require_exists=False)),
                    target,
                )
                with self.assertRaises(HTTPException):
                    web_app._path_from_file_token(token)
        finally:
            shutil.rmtree(temp_dir)

    def test_upload_cache_token_can_be_resolved(self) -> None:
        temp_dir = _workspace_temp("web_app_upload_cache_token")
        try:
            processed = temp_dir / "processed"
            upload_cache = temp_dir / "web_upload_cache" / "session"
            processed.mkdir()
            upload_cache.mkdir(parents=True)
            target = upload_cache / "01_cached.jpg"
            target.write_bytes(b"cached")
            token = web_app._file_token(str(target))

            with (
                patch.object(web_app.settings, "l", str(processed)),
                patch.object(web_app.settings, "AC", str(temp_dir)),
            ):
                self.assertEqual(Path(web_app._path_from_file_token(token)), target)
        finally:
            shutil.rmtree(temp_dir)

    def test_delete_upload_cache_files_only_removes_upload_cache_paths(self) -> None:
        temp_dir = _workspace_temp("web_app_upload_cache_cleanup")
        try:
            upload_cache = temp_dir / "web_upload_cache" / "session"
            processed = temp_dir / "processed"
            upload_cache.mkdir(parents=True)
            processed.mkdir()
            cached = upload_cache / "01_cached.jpg"
            processed_file = processed / "keep.jpg"
            cached.write_bytes(b"cached")
            processed_file.write_bytes(b"keep")

            with patch.object(web_app.settings, "AC", str(temp_dir)):
                with patch.object(web_app.os, "walk", side_effect=AssertionError("os.walk")):
                    result = web_app._delete_upload_cache_files([str(cached), str(processed_file)])

            self.assertEqual(result["deleted"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["errors"], [])
            self.assertFalse(cached.exists())
            self.assertTrue(processed_file.exists())
        finally:
            shutil.rmtree(temp_dir)

    def test_save_process_upload_rejects_oversized_file_and_removes_partial(self) -> None:
        temp_dir = _workspace_temp("web_app_process_upload_limit")
        try:
            upload = _MemoryUpload("large.jpg", [b"x" * (1024 * 1024), b"y"])
            with (
                patch.object(web_app.settings, "AC", str(temp_dir)),
                patch.object(
                    web_app.config,
                    "CONFIG",
                    {
                        web_app.PROCESSING_SETTINGS_KEY: {
                            "max_upload_mb": 1,
                            "max_upload_pixels": 25_000_000,
                        }
                    },
                ),
            ):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(web_app._save_upload(upload, str(temp_dir), "01"))

            self.assertEqual(caught.exception.status_code, 413)
            self.assertEqual(list(temp_dir.iterdir()), [])
            self.assertTrue(upload.closed)
        finally:
            shutil.rmtree(temp_dir)

    def test_save_process_upload_rejects_executable_extension(self) -> None:
        temp_dir = _workspace_temp("web_app_process_upload_executable")
        try:
            upload = _MemoryUpload("payload.exe", [b"MZ"])
            with (
                patch.object(web_app.settings, "AC", str(temp_dir)),
                patch.object(
                    web_app.config,
                    "CONFIG",
                    {
                        web_app.SECURITY_SETTINGS_KEY: {
                            "allowed_upload_extensions": ["jpg", "exe"],
                            "blocked_upload_extensions": [],
                            "block_executable_uploads": True,
                        }
                    },
                ),
            ):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(web_app._save_upload(upload, str(temp_dir), "01"))

            self.assertEqual(caught.exception.status_code, 400)
            self.assertEqual(list(temp_dir.iterdir()), [])
            self.assertTrue(upload.closed)
        finally:
            shutil.rmtree(temp_dir)

    def test_save_upload_cache_rejects_extension_outside_allow_list(self) -> None:
        temp_dir = _workspace_temp("web_app_upload_extension_limit")
        try:
            upload = _MemoryUpload("document.pdf", [b"%PDF"])
            with (
                patch.object(web_app.settings, "AC", str(temp_dir)),
                patch.object(
                    web_app.config,
                    "CONFIG",
                    {
                        web_app.SECURITY_SETTINGS_KEY: {
                            "allowed_upload_extensions": ["jpg", "png"],
                            "blocked_upload_extensions": [],
                            "block_executable_uploads": True,
                        }
                    },
                ),
            ):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(web_app._save_upload_cache(upload, "session", "01"))

            self.assertEqual(caught.exception.status_code, 400)
            self.assertEqual(caught.exception.detail, "Typ pliku .pdf nie jest dozwolony.")
            cache_root = temp_dir / "web_upload_cache"
            cached_files = list(cache_root.rglob("*")) if cache_root.exists() else []
            self.assertEqual([path for path in cached_files if path.is_file()], [])
            self.assertTrue(upload.closed)
        finally:
            shutil.rmtree(temp_dir)

    def test_save_upload_cache_rejects_image_above_pixel_limit_and_removes_file(self) -> None:
        if Image is None:
            self.skipTest("Pillow unavailable")
        temp_dir = _workspace_temp("web_app_upload_pixel_limit")
        try:
            buffer = io.BytesIO()
            Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
            upload = _MemoryUpload("large.png", [buffer.getvalue()], "image/png")
            with (
                patch.object(web_app.settings, "AC", str(temp_dir)),
                patch.object(
                    web_app.config,
                    "CONFIG",
                    {
                        web_app.PROCESSING_SETTINGS_KEY: {
                            "max_upload_mb": 50,
                            "max_upload_pixels": 50,
                        }
                    },
                ),
            ):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(web_app._save_upload_cache(upload, "session", "01"))

            self.assertEqual(caught.exception.status_code, 413)
            cache_root = temp_dir / "web_upload_cache"
            cached_files = list(cache_root.rglob("*")) if cache_root.exists() else []
            self.assertEqual([path for path in cached_files if path.is_file()], [])
            self.assertTrue(upload.closed)
        finally:
            shutil.rmtree(temp_dir)

    def test_save_upload_cache_rejects_html_content_named_as_jpg(self) -> None:
        temp_dir = _workspace_temp("web_app_upload_magic_mismatch")
        try:
            upload = _MemoryUpload("photo.jpg", [b"<!doctype html><script>alert(1)</script>"], "image/jpeg")
            with (
                patch.object(web_app.settings, "AC", str(temp_dir)),
                patch.object(
                    web_app.config,
                    "CONFIG",
                    {
                        web_app.SECURITY_SETTINGS_KEY: {
                            "allowed_upload_extensions": ["jpg", "png"],
                            "blocked_upload_extensions": [],
                            "block_executable_uploads": True,
                        }
                    },
                ),
            ):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(web_app._save_upload_cache(upload, "session", "01"))

            self.assertEqual(caught.exception.status_code, 400)
            self.assertIn("HTML/XML/SVG", caught.exception.detail)
            cache_root = temp_dir / "web_upload_cache"
            cached_files = list(cache_root.rglob("*")) if cache_root.exists() else []
            self.assertEqual([path for path in cached_files if path.is_file()], [])
            self.assertTrue(upload.closed)
        finally:
            shutil.rmtree(temp_dir)

    def test_save_upload_cache_strips_jpeg_exif_metadata(self) -> None:
        if Image is None:
            self.skipTest("Pillow unavailable")
        temp_dir = _workspace_temp("web_app_upload_metadata_strip")
        try:
            buffer = io.BytesIO()
            image = Image.new("RGB", (16, 16), "white")
            exif = image.getexif()
            exif[0x010E] = "private description"
            image.save(buffer, format="JPEG", exif=exif.tobytes())
            upload = _MemoryUpload("photo.jpg", [buffer.getvalue()], "image/jpeg")
            with patch.object(web_app.settings, "AC", str(temp_dir)):
                path, _size = asyncio.run(web_app._save_upload_cache(upload, "session", "01"))

            with Image.open(path) as saved:
                self.assertEqual(dict(saved.getexif()), {})
            self.assertTrue(upload.closed)
        finally:
            shutil.rmtree(temp_dir)

    def test_save_upload_cache_accepts_jfif_jpeg_when_allowed(self) -> None:
        if Image is None:
            self.skipTest("Pillow unavailable")
        temp_dir = _workspace_temp("web_app_upload_jfif")
        try:
            buffer = io.BytesIO()
            Image.new("RGB", (16, 16), "white").save(buffer, format="JPEG")
            upload = _MemoryUpload("photo.jfif", [buffer.getvalue()], "image/jpeg")
            with (
                patch.object(web_app.settings, "AC", str(temp_dir)),
                patch.object(
                    web_app.config,
                    "CONFIG",
                    {
                        web_app.SECURITY_SETTINGS_KEY: {
                            "allowed_upload_extensions": ["jfif"],
                            "blocked_upload_extensions": [],
                            "block_executable_uploads": True,
                        }
                    },
                ),
            ):
                path, _size = asyncio.run(web_app._save_upload_cache(upload, "session", "01"))

            self.assertTrue(path.endswith(".jfif"))
            with Image.open(path) as image:
                self.assertEqual(image.format, "JPEG")
            self.assertTrue(upload.closed)
        finally:
            shutil.rmtree(temp_dir)

    def test_save_upload_cache_accepts_additional_image_formats_when_allowed(self) -> None:
        if Image is None:
            self.skipTest("Pillow unavailable")
        temp_dir = _workspace_temp("web_app_upload_additional_image_formats")
        cases = [
            ("photo.jpe", "image/jpeg", self._image_bytes("JPEG")),
            ("photo.peg", "image/jpeg", self._image_bytes("JPEG")),
            ("photo.apng", "image/apng", self._image_bytes("PNG")),
            ("photo.dib", "image/bmp", self._image_bytes("DIB")),
            ("photo.ico", "image/x-icon", self._image_bytes("ICO", "RGBA")),
            ("photo.tga", "image/x-tga", self._image_bytes("TGA")),
            ("photo.ppm", "image/x-portable-pixmap", self._image_bytes("PPM")),
            ("photo.pgm", "image/x-portable-graymap", self._image_bytes("PPM", "L")),
            ("photo.pbm", "image/x-portable-bitmap", self._image_bytes("PPM", "1")),
            ("photo.pnm", "image/x-portable-anymap", self._image_bytes("PPM")),
            ("photo.pcx", "image/x-pcx", self._image_bytes("PCX")),
        ]
        avif_payload = self._optional_image_bytes("AVIF")
        if avif_payload is not None:
            cases.append(("photo.avifs", "image/avif-sequence", avif_payload))
        jpeg2000_payload = self._optional_image_bytes("JPEG2000")
        if jpeg2000_payload is not None:
            cases.extend(
                [
                    ("photo.jp2", "image/jp2", jpeg2000_payload),
                    ("photo.j2k", "image/jp2", jpeg2000_payload),
                    ("photo.jpc", "image/jp2", jpeg2000_payload),
                    ("photo.jpx", "image/jpx", jpeg2000_payload),
                ]
            )

        try:
            for filename, content_type, payload in cases:
                with self.subTest(filename=filename):
                    extension = filename.rsplit(".", 1)[1]
                    upload = _MemoryUpload(filename, [payload], content_type)
                    with (
                        patch.object(web_app.settings, "AC", str(temp_dir)),
                        patch.object(
                            web_app.config,
                            "CONFIG",
                            {
                                web_app.SECURITY_SETTINGS_KEY: {
                                    "allowed_upload_extensions": [extension],
                                    "blocked_upload_extensions": [],
                                    "block_executable_uploads": True,
                                }
                            },
                        ),
                    ):
                        path, _size = asyncio.run(web_app._save_upload_cache(upload, "session", "01"))

                    self.assertTrue(path.endswith(f".{extension}"))
                    self.assertTrue(upload.closed)
        finally:
            shutil.rmtree(temp_dir)

    def test_save_upload_cache_accepts_heif_family_and_cursor_passthrough_when_allowed(self) -> None:
        temp_dir = _workspace_temp("web_app_upload_heif_passthrough")
        cases = [
            ("photo.heic", "image/heic", self._ftyp_payload(b"heic")),
            ("photo.heif", "image/heif", self._ftyp_payload(b"mif1")),
            ("photo.hif", "image/heif", self._ftyp_payload(b"heic")),
            ("photo.cur", "image/x-icon", b"\x00\x00\x02\x00\x01\x00" + b"\x00" * 64),
        ]
        try:
            for filename, content_type, payload in cases:
                with self.subTest(filename=filename):
                    extension = filename.rsplit(".", 1)[1]
                    upload = _MemoryUpload(filename, [payload], content_type)
                    with (
                        patch.object(web_app.settings, "AC", str(temp_dir)),
                        patch.object(
                            web_app.config,
                            "CONFIG",
                            {
                                web_app.SECURITY_SETTINGS_KEY: {
                                    "allowed_upload_extensions": [extension],
                                    "blocked_upload_extensions": [],
                                    "block_executable_uploads": True,
                                }
                            },
                        ),
                    ):
                        path, _size = asyncio.run(web_app._save_upload_cache(upload, "session", "01"))

                    self.assertTrue(path.endswith(f".{extension}"))
                    self.assertTrue(upload.closed)
        finally:
            shutil.rmtree(temp_dir)

    def test_save_upload_cache_entry_normalizes_browser_extension_webp_named_jpg(self) -> None:
        if Image is None:
            self.skipTest("Pillow unavailable")
        temp_dir = _workspace_temp("web_app_upload_normalize_webp_extension")
        try:
            buffer = io.BytesIO()
            try:
                Image.new("RGB", (16, 16), "white").save(buffer, format="WEBP")
            except Exception:
                self.skipTest("Pillow WebP support unavailable")
            upload = _MemoryUpload("product.jpg", [buffer.getvalue()], "image/jpeg")
            with (
                patch.object(web_app.settings, "AC", str(temp_dir)),
                patch.object(
                    web_app.config,
                    "CONFIG",
                    {
                        web_app.SECURITY_SETTINGS_KEY: {
                            "allowed_upload_extensions": ["jpg", "webp"],
                            "blocked_upload_extensions": [],
                            "block_executable_uploads": True,
                        }
                    },
                ),
            ):
                saved = asyncio.run(
                    web_app._save_upload_cache_entry(
                        upload,
                        "session",
                        "web",
                        normalize_extension=True,
                    )
                )

            self.assertTrue(saved.path.endswith(".webp"))
            self.assertEqual(saved.name, "product.webp")
            with Image.open(saved.path) as image:
                self.assertEqual(image.format, "WEBP")
            self.assertTrue(upload.closed)
        finally:
            shutil.rmtree(temp_dir)

    def test_save_upload_cache_runs_optional_antivirus_scan(self) -> None:
        if Image is None:
            self.skipTest("Pillow unavailable")
        temp_dir = _workspace_temp("web_app_upload_antivirus")
        try:
            buffer = io.BytesIO()
            Image.new("RGB", (10, 10), "white").save(buffer, format="JPEG")
            upload = _MemoryUpload("photo.jpg", [buffer.getvalue()], "image/jpeg")
            with (
                patch.object(web_app.settings, "AC", str(temp_dir)),
                patch.object(
                    web_app.config,
                    "CONFIG",
                    {
                        web_app.SECURITY_SETTINGS_KEY: {
                            "antivirus_scan_uploads": True,
                        }
                    },
                ),
                patch.object(web_app, "_defender_scan_executable", return_value="MpCmdRun.exe"),
                patch.object(
                    web_app.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0, stdout="clean", stderr=""),
                ) as scan,
            ):
                path, _size = asyncio.run(web_app._save_upload_cache(upload, "session", "01"))

            scan.assert_called_once()
            scan_result = web_app._upload_scan_result(path)
            self.assertTrue(scan_result["enabled"])
            self.assertTrue(scan_result["scanned"])
            self.assertEqual(scan_result["scanner"], "Microsoft Defender")
        finally:
            shutil.rmtree(temp_dir)

    def test_delete_local_files_is_idempotent_and_preserves_saved_paths(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            delete_file = root / "delete.jpg"
            saved_file = root / "saved.jpg"
            missing_file = root / "missing.jpg"
            delete_file.write_bytes(b"delete")
            saved_file.write_bytes(b"saved")

            result = web_app._delete_local_files(
                [
                    {"local_path": str(delete_file)},
                    {"local_path": str(saved_file)},
                    {"local_path": str(missing_file)},
                ],
                {str(saved_file)},
            )

            self.assertEqual(result["deleted"], 1)
            self.assertEqual(result["skipped"], 2)
            self.assertEqual(result["errors"], [])
            self.assertFalse(delete_file.exists())
            self.assertTrue(saved_file.exists())

    def test_ftp_sync_skips_upload_for_backfilled_prefixes(self) -> None:
        result = SimpleNamespace(
            output_dir="processed",
            saved_files=[
                SimpleNamespace(
                    prefix="03",
                    filename="5901234567890_03_DETAIL_MAGGIORE.jpg",
                )
            ],
        )

        with (
            patch.dict(web_app.config.CONFIG, {web_app.ft: True, web_app.H: {}}, clear=False),
            patch.object(
                web_app,
                "sync_remote_files",
                return_value={"uploaded": 0, "deleted": 0, "elapsed_ms": 1, "error": ""},
            ) as sync_remote,
        ):
            payload = web_app._sync_result_to_ftp(
                result,
                [],
                skip_upload_prefixes={"03"},
            )

        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["uploaded"], 0)
        sync_remote.assert_not_called()

    def test_existing_local_photos_are_migrated_when_product_path_changes(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            processed = root / "processed"
            old_file = processed / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY" / "NO-LED"
            old_file.mkdir(parents=True)
            photo_path = old_file / "5901234567890_03_DETAIL_MAGGIORE_KOMODA_MA03_BIALY_NO-LED.jpg"
            photo_path.write_bytes(b"old")
            uploaded_slots = []
            delete_requests = []
            existing_entry = {
                "product_id": "PRD-1",
                "ean": "5901234567890",
                "name": "MAGGIORE",
                "type_name": "KOMODA",
                "model": "MA03",
                "color1": "BIALY",
                "color2": "",
                "color3": "",
                "extra": "NO-LED",
            }
            product = web_app.WebProductForm(
                product_id="PRD-1",
                ean="5901234567890",
                name="MAGGIORE",
                type_name="KOMODA",
                model="MA03",
                color1="BIALY",
                color2="DAB",
                extra="NO-LED",
            )

            with (
                patch.object(web_app.settings, "l", str(processed)),
                patch.object(
                    web_app,
                    "find_product_photos",
                    return_value=[
                        {
                            "prefix": "03",
                            "path": str(photo_path),
                            "filename": photo_path.name,
                        }
                    ],
                ),
            ):
                migrated = web_app._append_existing_photo_migrations(
                    existing_entry=existing_entry,
                    product=product,
                    uploaded_slots=uploaded_slots,
                    delete_requests=delete_requests,
                    slot_by_prefix={"03": {"prefix": "03", "label": "DETAIL_pic"}},
                )

            self.assertEqual(migrated, ["03"])
            self.assertEqual(uploaded_slots[0].prefix, "03")
            self.assertEqual(uploaded_slots[0].source_path, str(photo_path))
            self.assertEqual(delete_requests[0]["local_path"], str(photo_path))

    def test_ftp_only_photos_are_downloaded_when_local_file_is_missing(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            processed = root / "processed"
            cache_file = root / "cache" / "5901234567890_03.jpg"
            cache_file.parent.mkdir(parents=True)
            cache_file.write_bytes(b"ftp")
            uploaded_slots = []
            delete_requests = []
            existing_entry = {
                "product_id": "PRD-1",
                "ean": "5901234567890",
                "name": "MAGGIORE",
                "type_name": "KOMODA",
                "model": "MA03",
                "color1": "BIALY",
                "extra": "NO-LED",
            }
            product = web_app.WebProductForm(
                product_id="PRD-1",
                ean="5901234567890",
                name="MAGGIORE",
                type_name="KOMODA",
                model="MA03",
                color1="BIALY",
                extra="NO-LED",
            )

            with (
                patch.object(web_app.settings, "l", str(processed)),
                patch.object(
                    web_app,
                    "find_product_photos",
                    return_value=[
                        {
                            "ean": "5901234567890",
                            "prefix": "03",
                            "path": "",
                            "ftp_filename": "5901234567890_03.jpg",
                        }
                    ],
                ),
                patch.object(web_app, "cache_ftp_preview", return_value=str(cache_file)) as cache_ftp,
            ):
                appended = web_app._append_existing_photo_migrations(
                    existing_entry=existing_entry,
                    product=product,
                    uploaded_slots=uploaded_slots,
                    delete_requests=delete_requests,
                    slot_by_prefix={"03": {"prefix": "03", "label": "DETAIL_pic"}},
                )

            self.assertEqual(appended, ["03"])
            cache_ftp.assert_called_once_with(
                "5901234567890",
                "5901234567890_03.jpg",
                cache_scope="",
            )
            self.assertEqual(uploaded_slots[0].source_path, str(cache_file))
            self.assertEqual(delete_requests[0]["local_path"], "")
            self.assertEqual(delete_requests[0]["ftp_filename"], "5901234567890_03.jpg")
            self.assertTrue(delete_requests[0]["ftp_backfill"])

    def test_local_only_photos_are_appended_for_missing_ftp_upload(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            processed = root / "processed"
            local_dir = processed / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY" / "NO-LED"
            local_dir.mkdir(parents=True)
            photo_path = local_dir / "5901234567890_03_DETAIL_MAGGIORE_KOMODA_MA03_BIALY_NO-LED.jpg"
            photo_path.write_bytes(b"local")
            uploaded_slots = []
            delete_requests = []
            product = web_app.WebProductForm(
                product_id="PRD-1",
                ean="5901234567890",
                name="MAGGIORE",
                type_name="KOMODA",
                model="MA03",
                color1="BIALY",
                extra="NO-LED",
            )

            with (
                patch.object(web_app.settings, "l", str(processed)),
                patch.dict(web_app.config.CONFIG, {web_app.ft: True}, clear=False),
                patch.object(
                    web_app,
                    "find_product_photos",
                    return_value=[
                        {
                            "ean": "5901234567890",
                            "prefix": "03",
                            "path": str(photo_path),
                            "filename": photo_path.name,
                            "ftp_filename": "",
                        }
                    ],
                ),
            ):
                appended = web_app._append_existing_photo_migrations(
                    existing_entry={"ean": "5901234567890"},
                    product=product,
                    uploaded_slots=uploaded_slots,
                    delete_requests=delete_requests,
                    slot_by_prefix={"03": {"prefix": "03", "label": "DETAIL_pic"}},
                )

            self.assertEqual(appended, ["03"])
            self.assertEqual(uploaded_slots[0].source_path, str(photo_path))
            self.assertEqual(delete_requests[0]["ftp_filename"], "")
            self.assertFalse(delete_requests[0]["ftp_backfill"])

    def test_local_photo_is_appended_for_missing_sql_without_delete_request(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            processed = root / "processed"
            local_dir = processed / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY" / "NO-LED"
            local_dir.mkdir(parents=True)
            photo_path = local_dir / "5901234567890_03_DETAIL_MAGGIORE_KOMODA_MA03_BIALY_NO-LED.jpg"
            photo_path.write_bytes(b"local")
            uploaded_slots = []
            delete_requests = []
            product = web_app.WebProductForm(
                product_id="PRD-1",
                ean="5901234567890",
                name="MAGGIORE",
                type_name="KOMODA",
                model="MA03",
                color1="BIALY",
                extra="NO-LED",
            )

            with (
                patch.object(web_app.settings, "l", str(processed)),
                patch.object(
                    web_app,
                    "find_product_photos",
                    return_value=[
                        {
                            "ean": "5901234567890",
                            "prefix": "03",
                            "path": str(photo_path),
                            "filename": photo_path.name,
                            "ftp": True,
                            "ftp_filename": "5901234567890_03.jpg",
                            "sql": False,
                            "sql_checked": True,
                        }
                    ],
                ) as find_photos,
            ):
                appended = web_app._append_existing_photo_migrations(
                    existing_entry={
                        "product_id": "PRD-1",
                        "ean": "5901234567890",
                        "name": "MAGGIORE",
                        "type_name": "KOMODA",
                        "model": "MA03",
                        "color1": "BIALY",
                        "color2": "",
                        "color3": "",
                        "extra": "NO-LED",
                    },
                    product=product,
                    uploaded_slots=uploaded_slots,
                    delete_requests=delete_requests,
                    slot_by_prefix={"03": {"prefix": "03", "label": "DETAIL_pic"}},
                )

            self.assertEqual(appended, ["03"])
            self.assertEqual(uploaded_slots[0].source_path, str(photo_path))
            self.assertEqual(delete_requests, [])
            self.assertTrue(find_photos.call_args.kwargs["include_sql"])

    def test_existing_photo_migration_uses_preloaded_photos(self) -> None:
        uploaded_slots = []
        delete_requests = []
        product = web_app.WebProductForm(
            product_id="PRD-1",
            ean="5901234567890",
            name="MAGGIORE",
            type_name="KOMODA",
            model="MA03",
            color1="BIALY",
            extra="NO-LED",
        )
        existing_photos = [
            {
                "ean": "5901234567890",
                "prefix": "03",
                "path": str(Path(__file__)),
                "filename": Path(__file__).name,
                "local": True,
                "ftp": True,
                "ftp_filename": "5901234567890_03.jpg",
                "sql": True,
                "sql_checked": True,
            }
        ]

        with patch.object(web_app, "find_product_photos") as find_photos:
            appended = web_app._append_existing_photo_migrations(
                existing_entry={
                    "product_id": "PRD-1",
                    "ean": "5901234567890",
                    "name": "MAGGIORE",
                    "type_name": "KOMODA",
                    "model": "MA03",
                    "color1": "BIALY",
                    "color2": "",
                    "color3": "",
                    "extra": "NO-LED",
                },
                product=product,
                uploaded_slots=uploaded_slots,
                delete_requests=delete_requests,
                slot_by_prefix={"03": {"prefix": "03", "label": "DETAIL_pic"}},
                existing_photos=existing_photos,
            )

        self.assertEqual(appended, [])
        find_photos.assert_not_called()

    def test_ftp_upload_is_skipped_for_sql_only_repair_with_existing_remote(self) -> None:
        result = SimpleNamespace(
            saved_files=[
                SimpleNamespace(
                    prefix="03",
                    filename="5901234567890_03_DETAIL_MAGGIORE.jpg",
                )
            ],
        )

        skipped = web_app._ftp_skip_upload_prefixes(
            result,
            [{"prefix": "03", "ftp": True}],
            explicit_prefixes=set(),
            migrated_prefixes=set(),
            ftp_backfill_prefixes=set(),
        )

        self.assertEqual(skipped, {"03"})

    def test_ftp_upload_is_skipped_for_existing_remote_even_when_local_file_exists(self) -> None:
        result = SimpleNamespace(
            saved_files=[
                SimpleNamespace(
                    prefix="03",
                    filename="5901234567890_03_DETAIL_MAGGIORE.jpg",
                )
            ],
        )

        skipped = web_app._ftp_skip_upload_prefixes(
            result,
            [{"prefix": "03", "local": True, "ftp": True}],
            explicit_prefixes=set(),
            migrated_prefixes=set(),
            ftp_backfill_prefixes=set(),
        )

        self.assertEqual(skipped, {"03"})

    def test_sql_sync_skips_updates_when_product_row_is_missing(self) -> None:
        result = SimpleNamespace(
            ean="5901234567890",
            saved_files=[
                SimpleNamespace(
                    prefix="03",
                    filename="5901234567890_03_DETAIL_MAGGIORE.jpg",
                )
            ],
        )

        class Cursor:
            rowcount = -1

            def __init__(self) -> None:
                self.queries = []

            def execute(self, query):
                self.queries.append(query)

            def fetchone(self):
                return None

            def close(self):
                return None

        class Connection:
            def __init__(self) -> None:
                self.cursor_obj = Cursor()
                self.committed = False

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.committed = True

            def rollback(self):
                return None

            def close(self):
                return None

        conn = Connection()
        with (
            patch.dict(
                web_app.config.CONFIG,
                {
                    web_app.u: True,
                    web_app.p: web_app.K,
                    web_app.w: "UPDATE object_query_1 SET {col} = '{filename}' WHERE EAN = '{ean}'",
                    web_app.SQL_COLUMN_MAP_KEY: {"03": "img_03"},
                },
                clear=False,
            ),
            patch.object(web_app, "connect_db", return_value=conn),
        ):
            payload = web_app._sync_result_to_sql(result)

        self.assertTrue(payload["skipped"])
        self.assertEqual(payload["updated"], 0)
        self.assertEqual(payload["rows"], 0)
        self.assertEqual(len(conn.cursor_obj.queries), 1)
        self.assertIn("SELECT 1", conn.cursor_obj.queries[0])
        self.assertFalse(conn.committed)

    def test_sql_sync_does_not_count_zero_row_updates(self) -> None:
        result = SimpleNamespace(
            ean="5901234567890",
            saved_files=[
                SimpleNamespace(
                    prefix="03",
                    filename="5901234567890_03_DETAIL_MAGGIORE.jpg",
                )
            ],
        )

        class Cursor:
            rowcount = -1

            def __init__(self) -> None:
                self.queries = []

            def execute(self, query):
                self.queries.append(query)
                self.rowcount = 0 if str(query).lstrip().upper().startswith("UPDATE") else -1

            def fetchone(self):
                return (1,)

            def close(self):
                return None

        class Connection:
            def __init__(self) -> None:
                self.cursor_obj = Cursor()
                self.committed = False

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.committed = True

            def rollback(self):
                return None

            def close(self):
                return None

        conn = Connection()
        with (
            patch.dict(
                web_app.config.CONFIG,
                {
                    web_app.u: True,
                    web_app.p: web_app.K,
                    web_app.w: "UPDATE object_query_1 SET {col} = '{filename}' WHERE EAN = '{ean}'",
                    web_app.SQL_COLUMN_MAP_KEY: {"03": "img_03"},
                },
                clear=False,
            ),
            patch.object(web_app, "connect_db", return_value=conn),
        ):
            payload = web_app._sync_result_to_sql(result)

        self.assertFalse(payload["skipped"])
        self.assertEqual(payload["updated"], 0)
        self.assertEqual(payload["rows"], 0)
        self.assertEqual(len(conn.cursor_obj.queries), 2)
        self.assertFalse(conn.committed)

    def test_complete_existing_photo_is_not_appended_without_missing_sources(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            processed = root / "processed"
            local_dir = processed / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY" / "NO-LED"
            local_dir.mkdir(parents=True)
            photo_path = local_dir / "5901234567890_03_DETAIL_MAGGIORE_KOMODA_MA03_BIALY_NO-LED.jpg"
            photo_path.write_bytes(b"local")
            uploaded_slots = []
            delete_requests = []
            product = web_app.WebProductForm(
                product_id="PRD-1",
                ean="5901234567890",
                name="MAGGIORE",
                type_name="KOMODA",
                model="MA03",
                color1="BIALY",
                extra="NO-LED",
            )

            with (
                patch.object(web_app.settings, "l", str(processed)),
                patch.dict(web_app.config.CONFIG, {web_app.ft: True}, clear=False),
                patch.object(
                    web_app,
                    "find_product_photos",
                    return_value=[
                        {
                            "ean": "5901234567890",
                            "prefix": "03",
                            "path": str(photo_path),
                            "filename": photo_path.name,
                            "local": True,
                            "ftp": True,
                            "ftp_filename": "5901234567890_03.jpg",
                            "sql": True,
                            "sql_checked": True,
                        }
                    ],
                ),
            ):
                appended = web_app._append_existing_photo_migrations(
                    existing_entry={
                        "product_id": "PRD-1",
                        "ean": "5901234567890",
                        "name": "MAGGIORE",
                        "type_name": "KOMODA",
                        "model": "MA03",
                        "color1": "BIALY",
                        "color2": "",
                        "color3": "",
                        "extra": "NO-LED",
                    },
                    product=product,
                    uploaded_slots=uploaded_slots,
                    delete_requests=delete_requests,
                    slot_by_prefix={"03": {"prefix": "03", "label": "DETAIL_pic"}},
                )

            self.assertEqual(appended, [])
            self.assertEqual(uploaded_slots, [])
            self.assertEqual(delete_requests, [])

    def test_enriched_local_photo_urls_include_file_version(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            photo_path = Path(temp_dir) / "5901234567890_03.jpg"
            photo_path.write_bytes(b"first")

            first = web_app._enrich_photo_payload([{"prefix": "03", "path": str(photo_path)}])[0]
            photo_path.write_bytes(b"changed-content")
            second = web_app._enrich_photo_payload([{"prefix": "03", "path": str(photo_path)}])[0]

        self.assertIn("&v=", first["url"])
        self.assertIn("&v=", first["thumb_url"])
        self.assertNotEqual(first["file_version"], second["file_version"])
        self.assertNotEqual(first["thumb_url"], second["thumb_url"])

    def test_ftp_upload_is_kept_for_explicitly_changed_slot(self) -> None:
        result = SimpleNamespace(
            saved_files=[
                SimpleNamespace(
                    prefix="03",
                    filename="5901234567890_03_DETAIL_MAGGIORE.jpg",
                )
            ],
        )

        skipped = web_app._ftp_skip_upload_prefixes(
            result,
            [{"prefix": "03", "ftp": True}],
            explicit_prefixes={"03"},
            migrated_prefixes=set(),
            ftp_backfill_prefixes=set(),
        )

        self.assertEqual(skipped, set())

    def test_explicit_slot_replacement_deletes_old_remote_when_extension_changes(self) -> None:
        result = SimpleNamespace(
            saved_files=[
                SimpleNamespace(
                    prefix="03",
                    filename="5901234567890_03_DETAIL_MAGGIORE.png",
                )
            ],
        )

        deletes = web_app._ftp_replacement_delete_candidates(
            result,
            [{"prefix": "03", "ftp_filename": "5901234567890_03.jpg"}],
            explicit_prefixes={"03"},
        )

        self.assertEqual(deletes, ["5901234567890_03.jpg"])

    def test_explicit_slot_replacement_keeps_same_remote_name_for_overwrite(self) -> None:
        result = SimpleNamespace(
            saved_files=[
                SimpleNamespace(
                    prefix="03",
                    filename="5901234567890_03_DETAIL_MAGGIORE.jpg",
                )
            ],
        )

        deletes = web_app._ftp_replacement_delete_candidates(
            result,
            [{"prefix": "03", "ftp_filename": "5901234567890_03.jpg"}],
            explicit_prefixes={"03"},
        )

        self.assertEqual(deletes, [])

    def test_deleted_ftp_only_slot_is_not_downloaded_again(self) -> None:
        product = web_app.WebProductForm(
            product_id="PRD-1",
            ean="5901234567890",
            name="MAGGIORE",
            type_name="KOMODA",
            model="MA03",
            color1="BIALY",
        )
        delete_requests = [{"prefix": "03", "ftp_filename": "5901234567890_03.jpg"}]

        with (
            patch.object(
                web_app,
                "find_product_photos",
                return_value=[
                    {
                        "ean": "5901234567890",
                        "prefix": "03",
                        "path": "",
                        "ftp_filename": "5901234567890_03.jpg",
                    }
                ],
            ),
            patch.object(web_app, "cache_ftp_preview") as cache_ftp,
        ):
            appended = web_app._append_existing_photo_migrations(
                existing_entry={"ean": "5901234567890"},
                product=product,
                uploaded_slots=[],
                delete_requests=delete_requests,
                slot_by_prefix={"03": {"prefix": "03", "label": "DETAIL_pic"}},
            )

        self.assertEqual(appended, [])
        cache_ftp.assert_not_called()

    def test_pending_ftp_slot_can_replace_deleted_target_prefix(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            cache_file = Path(temp_dir) / "5901234567890_02.jpg"
            cache_file.write_bytes(b"ftp")
            product = web_app.WebProductForm(
                product_id="PRD-1",
                ean="5901234567890",
                name="MAGGIORE",
                type_name="KOMODA",
                model="MA03",
                color1="BIALY",
            )
            uploaded_slots = []
            delete_requests = [
                {
                    "prefix": "03",
                    "label": "DETAIL_pic",
                    "local_path": "",
                    "ftp_filename": "5901234567890_03.jpg",
                    "sql": False,
                }
            ]
            pending_ftp_slots = [
                {
                    "prefix": "03",
                    "label": "DETAIL_pic",
                    "filename": "5901234567890_02.jpg",
                    "ean": "5901234567890",
                    "content_fit": True,
                }
            ]

            with patch.object(web_app, "cache_ftp_preview", return_value=str(cache_file)) as cache_ftp:
                appended = web_app._append_pending_ftp_slots(
                    product=product,
                    pending_ftp_slots=pending_ftp_slots,
                    uploaded_slots=uploaded_slots,
                    delete_requests=delete_requests,
                )

            self.assertEqual(appended, ["03"])
            cache_ftp.assert_called_once_with(
                "5901234567890",
                "5901234567890_02.jpg",
                cache_scope="",
            )
            self.assertEqual(uploaded_slots[0].prefix, "03")
            self.assertEqual(uploaded_slots[0].source_path, str(cache_file))
            self.assertTrue(uploaded_slots[0].content_fit)
            self.assertEqual(
                [item["ftp_filename"] for item in delete_requests],
                ["5901234567890_03.jpg", "5901234567890_02.jpg"],
            )

    def test_ftp_only_existing_photos_backfill_unoccupied_slots(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            uploaded_source = Path(temp_dir) / "new-14.jpg"
            cache_file = Path(temp_dir) / "5901234567890_15.jpg"
            uploaded_source.write_bytes(b"new")
            cache_file.write_bytes(b"ftp")
            product = web_app.WebProductForm(
                ean="5901234567890",
                name="MAGGIORE",
                type_name="KOMODA",
                model="MA03",
                color1="BIALY",
            )
            uploaded_slots = [
                web_app.WebUploadedSlot(
                    prefix="14",
                    label="DETAIL_pic",
                    source_path=str(uploaded_source),
                    original_filename="new-14.jpg",
                )
            ]
            delete_requests = []
            existing_photos = [
                {"ean": "5901234567890", "prefix": "14", "ftp": True, "ftp_filename": "5901234567890_14.jpg"},
                {"ean": "5901234567890", "prefix": "15", "ftp": True, "ftp_filename": "5901234567890_15.jpg"},
            ]

            with patch.object(web_app, "cache_ftp_preview", return_value=str(cache_file)) as cache_ftp:
                appended = web_app._append_existing_photo_migrations(
                    existing_entry=None,
                    product=product,
                    uploaded_slots=uploaded_slots,
                    delete_requests=delete_requests,
                    slot_by_prefix={
                        "14": {"prefix": "14", "label": "DETAIL_pic"},
                        "15": {"prefix": "15", "label": "DETAIL_pic"},
                    },
                    existing_photos=existing_photos,
                )

            self.assertEqual(appended, ["15"])
            self.assertEqual([slot.prefix for slot in uploaded_slots], ["14", "15"])
            self.assertEqual(uploaded_slots[0].source_path, str(uploaded_source))
            self.assertEqual(uploaded_slots[1].source_path, str(cache_file))
            self.assertEqual(delete_requests[0]["prefix"], "15")
            self.assertTrue(delete_requests[0]["ftp_backfill"])
            cache_ftp.assert_called_once_with(
                "5901234567890",
                "5901234567890_15.jpg",
                cache_scope="",
            )

    def test_log_parser_groups_traceback_into_one_critical_event(self) -> None:
        events = web_app._parse_log_events(
            {
                "key": "errors",
                "label": "Bledy",
                "path": "errors.log",
                "lines": [
                    "[2026-05-11 14:14:11] [USER: user] [PC: pc] ERROR: WEB POST /api/ftp-preview: boom",
                    "Traceback (most recent call last):",
                    "  File \"app.py\", line 1, in handler",
                    "RuntimeError: boom",
                    "[2026-05-11 14:15:00] [USER: user] [PC: pc] ERROR: Brak dostepu",
                ],
            }
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["severity"], "critical")
        self.assertEqual(len(events[0]["lines"]), 4)
        self.assertEqual(events[1]["severity"], "warning")

    def test_log_parser_splits_plain_lines_and_strips_control_sequences(self) -> None:
        events = web_app._parse_log_events(
            {
                "key": "web_out",
                "label": "Web stdout",
                "path": "out.log",
                "lines": [
                    '\x1b[32mINFO\x1b[0m:     127.0.0.1:1 - "GET /ok HTTP/1.1" 200 OK',
                    'INFO:     127.0.0.1:2 - "GET /missing HTTP/1.1" 404 Not Found',
                ],
            }
        )

        self.assertEqual(len(events), 2)
        self.assertNotIn("\x1b", events[0]["summary"])
        self.assertEqual(events[0]["severity"], "info")
        self.assertEqual(events[1]["severity"], "warning")

    def test_web_event_info_details_with_error_keys_stay_info(self) -> None:
        events = web_app._parse_log_events(
            {
                "key": "web_events",
                "label": "Zdarzenia web",
                "path": "events.log",
                "lines": [
                    "[2026-05-12 12:54:30] [USER: admin] INFO: PROCESS_COMPLETED - Zapisano 0 plikow, usunieto lokalnie 0.",
                    'details: {"ftp": {"error": ""}, "sql": {"error": ""}}',
                ],
            }
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["severity"], "info")

    def test_user_cache_scope_is_session_specific(self) -> None:
        first = web_app._user_cache_scope(
            SimpleNamespace(cookies={web_app.SESSION_COOKIE: "session-one"}),
            "admin",
        )
        second = web_app._user_cache_scope(
            SimpleNamespace(cookies={web_app.SESSION_COOKIE: "session-two"}),
            "admin",
        )
        other_user = web_app._user_cache_scope(
            SimpleNamespace(cookies={web_app.SESSION_COOKIE: "session-one"}),
            "operator",
        )

        self.assertNotEqual(first, second)
        self.assertNotEqual(first, other_user)
        self.assertTrue(first.startswith("admin-"))

    def test_user_cache_scope_without_session_uses_client_context(self) -> None:
        first = web_app._user_cache_scope(
            SimpleNamespace(
                cookies={},
                client=SimpleNamespace(host="192.0.2.10"),
                headers={"user-agent": "browser-a"},
            ),
            "admin",
        )
        second = web_app._user_cache_scope(
            SimpleNamespace(
                cookies={},
                client=SimpleNamespace(host="192.0.2.11"),
                headers={"user-agent": "browser-a"},
            ),
            "admin",
        )

        self.assertNotEqual(first, second)

    def test_log_payloads_are_newest_first_and_hide_successful_access_logs(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            log_path = Path(temp_dir) / "picorg_web_out.log"
            log_path.write_text(
                "\n".join(
                    [
                        "INFO:     Custom maintenance event.",
                        'INFO:     127.0.0.1:1 - "GET /api/logs?limit=120 HTTP/1.1" 200 OK',
                        'INFO:     127.0.0.1:2 - "GET /crash HTTP/1.1" 500 Internal Server Error',
                    ]
                ),
                encoding="utf-8",
            )
            targets = [{"key": "web_out", "label": "Web stdout", "path": log_path}]

            with patch.object(web_app, "_log_targets", return_value=targets):
                payload = web_app._log_payloads(20)[0]

            summaries = [event["summary"] for event in payload["events"]]
            self.assertEqual(len(summaries), 2)
            self.assertIn("/crash", summaries[0])
            self.assertEqual(summaries[1], "Custom maintenance event.")

    def test_runtime_logs_hide_uvicorn_startup_and_400_access_noise(self) -> None:
        startup_event = {
            "source": "web_err",
            "lines": ["INFO:     Uvicorn running on http://0.0.0.0:8010 (Press CTRL+C to quit)"],
        }
        bad_request_event = {
            "source": "web_out",
            "lines": ['INFO:     127.0.0.1:1 - "POST /api/process HTTP/1.1" 400 Bad Request'],
        }
        server_error_event = {
            "source": "web_out",
            "lines": ['INFO:     127.0.0.1:1 - "POST /api/process HTTP/1.1" 500 Internal Server Error'],
        }

        self.assertFalse(web_app._is_visible_log_event(startup_event))
        self.assertFalse(web_app._is_visible_log_event(bad_request_event))
        self.assertTrue(web_app._is_visible_log_event(server_error_event))

    def test_background_process_routes_are_registered(self) -> None:
        route_paths = {getattr(route, "path", "") for route in web_app.app.routes}

        self.assertIn("/api/process/background", route_paths)
        self.assertIn("/api/process-jobs", route_paths)
        self.assertIn("/api/process-jobs/active", route_paths)
        self.assertIn("/api/process-jobs/{job_id}", route_paths)

    def test_process_warning_messages_are_user_visible(self) -> None:
        payload = {
            "ftp": {"error": "brak polaczenia"},
            "sql": {"error": "brak wiersza"},
            "local_delete": {"errors": ["03: odmowa dostepu"]},
            "skipped_slots": ["04"],
        }

        messages = web_app._process_warning_messages(payload)

        self.assertIn("FTP: brak polaczenia", messages)
        self.assertIn("SQL: brak wiersza", messages)
        self.assertTrue(any("03: odmowa dostepu" in item for item in messages))
        self.assertTrue(any("04" in item for item in messages))

    def test_process_job_payload_hides_internal_form_snapshot(self) -> None:
        job = {
            "id": "abc",
            "status": "queued",
            "form": object(),
            "entry": {"ean": "5901234567890", "name": "MAGGIORE"},
            "entry_label": "MAGGIORE - 5901234567890",
        }

        payload = web_app._process_job_payload(job)

        self.assertNotIn("form", payload)
        self.assertEqual(payload["job_id"], "abc")
        self.assertEqual(payload["entry"]["ean"], "5901234567890")

    def test_active_process_jobs_snapshot_is_global_and_ordered(self) -> None:
        with web_app._PROCESS_JOBS_LOCK:
            original = dict(web_app._PROCESS_JOBS)
            web_app._PROCESS_JOBS.clear()
            web_app._PROCESS_JOBS.update(
                {
                    "running": {
                        "id": "running",
                        "status": "running",
                        "username": "user1",
                        "created_at": 1.0,
                        "started_at": 3.0,
                        "entry": {"name": "RUN"},
                        "entry_label": "RUN",
                        "progress": 34,
                        "progress_label": "Zapis wpisu",
                    },
                    "queued": {
                        "id": "queued",
                        "status": "queued",
                        "username": "user2",
                        "created_at": 2.0,
                        "entry": {"name": "WAIT"},
                        "entry_label": "WAIT",
                        "progress": 0,
                        "progress_label": "Oczekuje w kolejce",
                    },
                }
            )
        try:
            snapshot = web_app._active_process_jobs_snapshot()
        finally:
            with web_app._PROCESS_JOBS_LOCK:
                web_app._PROCESS_JOBS.clear()
                web_app._PROCESS_JOBS.update(original)

        self.assertEqual(snapshot["active_count"], 2)
        self.assertEqual(snapshot["queued_count"], 1)
        self.assertEqual(snapshot["jobs"][0]["job_id"], "running")
        self.assertEqual(snapshot["jobs"][0]["progress"], 34)
        self.assertEqual(snapshot["jobs"][1]["username"], "user2")
        self.assertEqual(snapshot["jobs"][1]["queue_position"], 1)

    def test_active_presence_payload_is_disabled_by_default(self) -> None:
        with patch.object(web_app.config, "CONFIG", {}):
            payload = web_app._active_presence_payload(
                [
                    {
                        "username": "admin",
                        "last_seen": "2026-06-30 10:00:00",
                        "last_seen_epoch": 20,
                    },
                ]
            )

        self.assertEqual(payload, {"enabled": False, "users": []})

    def test_active_presence_payload_sanitizes_and_deduplicates_users(self) -> None:
        clients = [
            {
                "username": "admin",
                "client_id": "client-a",
                "remote_address": "10.0.0.1",
                "path": "/api/bootstrap",
                "last_seen": "old",
                "last_seen_epoch": 10,
            },
            {
                "username": "operator",
                "client_id": "client-b",
                "user_agent": "browser",
                "last_seen": "now",
                "last_seen_epoch": 30,
            },
            {
                "username": "admin",
                "client_id": "client-a",
                "remote_port": 1234,
                "last_seen": "new",
                "last_seen_epoch": 40,
            },
            {
                "username": "niezalogowany",
                "last_seen": "anon",
                "last_seen_epoch": 50,
            },
            {
                "username": "",
                "last_seen": "blank",
                "last_seen_epoch": 60,
            },
        ]
        with patch.object(
            web_app.config,
            "CONFIG",
            {web_app.SECURITY_SETTINGS_KEY: {"show_active_web_users": True}},
        ):
            payload = web_app._active_presence_payload(clients, now=40)

        self.assertTrue(payload["enabled"])
        self.assertEqual(
            payload["users"],
            [
                {"username": "admin", "last_seen": "new", "last_seen_epoch": 40.0},
                {"username": "operator", "last_seen": "now", "last_seen_epoch": 30.0},
            ],
        )

    def test_active_presence_payload_requires_browser_client_id(self) -> None:
        clients = [
            {
                "username": "admin",
                "last_seen": "html request",
                "last_seen_epoch": 100,
            },
            {
                "username": "operator",
                "client_id": "client-a",
                "last_seen": "browser poll",
                "last_seen_epoch": 100,
            },
        ]
        with patch.object(
            web_app.config,
            "CONFIG",
            {web_app.SECURITY_SETTINGS_KEY: {"show_active_web_users": True}},
        ):
            payload = web_app._active_presence_payload(clients, now=100)

        self.assertEqual(
            payload["users"],
            [
                {
                    "username": "operator",
                    "last_seen": "browser poll",
                    "last_seen_epoch": 100.0,
                }
            ],
        )

    def test_active_client_key_prefers_browser_client_id(self) -> None:
        first = {
            "username": "admin",
            "client_id": "client-a",
            "remote_address": "10.0.0.1",
            "user_agent": "browser-a",
        }
        same_client_new_connection = {
            "username": "admin",
            "client_id": "client-a",
            "remote_address": "10.0.0.2",
            "user_agent": "browser-b",
        }
        other_client = {
            "username": "admin",
            "client_id": "client-b",
            "remote_address": "10.0.0.1",
            "user_agent": "browser-a",
        }

        self.assertEqual(
            web_app._active_client_key(first),
            web_app._active_client_key(same_client_new_connection),
        )
        self.assertNotEqual(
            web_app._active_client_key(first),
            web_app._active_client_key(other_client),
        )

    def test_remove_active_client_removes_only_matching_browser_client(self) -> None:
        with web_app._ACTIVE_CLIENTS_LOCK:
            original = dict(web_app._ACTIVE_CLIENTS)
            original_loaded = web_app._ACTIVE_CLIENTS_LOADED
            web_app._ACTIVE_CLIENTS.clear()
            web_app._ACTIVE_CLIENTS_LOADED = True
            first = {
                "username": "admin",
                "client_id": "client-a",
                "last_seen_epoch": 100.0,
            }
            second = {
                "username": "admin",
                "client_id": "client-b",
                "last_seen_epoch": 100.0,
            }
            other_user = {
                "username": "operator",
                "client_id": "client-a",
                "last_seen_epoch": 100.0,
            }
            web_app._ACTIVE_CLIENTS[web_app._active_client_key(first)] = first
            web_app._ACTIVE_CLIENTS[web_app._active_client_key(second)] = second
            web_app._ACTIVE_CLIENTS[web_app._active_client_key(other_user)] = other_user
        try:
            removed = web_app._remove_active_client("admin", "client-a", now=100.0)
            snapshot = web_app._active_clients_snapshot(now=100.0)
        finally:
            with web_app._ACTIVE_CLIENTS_LOCK:
                web_app._ACTIVE_CLIENTS.clear()
                web_app._ACTIVE_CLIENTS.update(original)
                web_app._ACTIVE_CLIENTS_LOADED = original_loaded

        self.assertEqual(removed, 1)
        self.assertEqual(
            {(item.get("username"), item.get("client_id")) for item in snapshot},
            {("admin", "client-b"), ("operator", "client-a")},
        )

    def test_active_presence_payload_hides_stale_browser_clients_quickly(self) -> None:
        now = 200.0
        clients = [
            {
                "username": "admin",
                "client_id": "client-a",
                "last_seen": "stale",
                "last_seen_epoch": now - web_app.PRESENCE_CLIENT_MAX_AGE_SECONDS - 1,
            },
            {
                "username": "operator",
                "client_id": "client-b",
                "last_seen": "fresh",
                "last_seen_epoch": now,
            },
        ]
        with patch.object(
            web_app.config,
            "CONFIG",
            {web_app.SECURITY_SETTINGS_KEY: {"show_active_web_users": True}},
        ):
            payload = web_app._active_presence_payload(clients, now=now)

        self.assertEqual(
            payload["users"],
            [{"username": "operator", "last_seen": "fresh", "last_seen_epoch": now}],
        )

    def test_existing_photo_conflicts_detect_unloaded_replacement(self) -> None:
        upload = web_app.WebUploadedSlot(
            prefix="03",
            label="DETAIL_pic",
            source_path="new.jpg",
            original_filename="new.jpg",
        )
        conflicts = web_app._existing_photo_conflicts(
            [{"prefix": "03", "local": True, "path": "old.jpg", "filename": "old.jpg"}],
            [upload],
            [],
        )

        self.assertEqual(conflicts[0]["prefix"], "03")
        self.assertEqual(conflicts[0]["sources"], ["LOCAL"])

    def test_existing_photo_conflicts_ignores_explicit_ftp_source(self) -> None:
        upload = web_app.WebUploadedSlot(
            prefix="03",
            label="DETAIL_pic",
            source_path="cache.jpg",
            original_filename="5901234567890_03.jpg",
        )
        conflicts = web_app._existing_photo_conflicts(
            [{"prefix": "03", "ftp": True, "ftp_filename": "5901234567890_03.jpg"}],
            [upload],
            [],
        )

        self.assertEqual(conflicts, [])

    def test_existing_photo_conflicts_allows_upload_to_replace_ftp_only_slot(self) -> None:
        upload = web_app.WebUploadedSlot(
            prefix="03",
            label="DETAIL_pic",
            source_path="new.jpg",
            original_filename="new.jpg",
        )
        conflicts = web_app._existing_photo_conflicts(
            [{"prefix": "03", "ftp": True, "ftp_filename": "5901234567890_03.jpg"}],
            [upload],
            [],
        )

        self.assertEqual(conflicts, [])

    def test_existing_photo_conflicts_ignore_sql_only_presence(self) -> None:
        upload = web_app.WebUploadedSlot(
            prefix="03",
            label="DETAIL_pic",
            source_path="new.jpg",
            original_filename="new.jpg",
        )
        conflicts = web_app._existing_photo_conflicts(
            [{"prefix": "03", "sql": True, "sql_checked": True, "sql_value": ""}],
            [upload],
            [],
        )

        self.assertEqual(conflicts, [])

    def test_system_change_filter_hides_product_and_photo_entries(self) -> None:
        settings_event = {
            "source": "changes",
            "lines": ["[2026-05-12 10:00:00] [USER: user] Settings saved (images/FTP/SQL)."],
        }
        image_event = {
            "source": "changes",
            "lines": ["[2026-05-12 10:01:00] [USER: user] Added/modified image 123.jpg"],
        }
        entry_event = {
            "source": "changes",
            "lines": ["[2026-05-12 10:02:00] [USER: user] Updated Excel entry for EAN 5901234567890."],
        }

        self.assertTrue(web_app._is_system_change_event(settings_event))
        self.assertFalse(web_app._is_system_change_event(image_event))
        self.assertFalse(web_app._is_system_change_event(entry_event))

    def test_clear_log_files_truncates_configured_targets(self) -> None:
        workspace_tmp = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=workspace_tmp) as temp_dir:
            root = Path(temp_dir)
            error_log = root / "error_log.txt"
            changes_log = root / "changes_log.txt"
            error_log.write_text("error\n", encoding="utf-8")
            changes_log.write_text("change\n", encoding="utf-8")
            targets = [
                {"key": "errors", "label": "Bledy", "path": error_log},
                {"key": "changes", "label": "Zmiany", "path": changes_log},
            ]

            with patch.object(web_app, "_log_targets", return_value=targets):
                result = web_app._clear_log_files()

            self.assertEqual(result["errors"], [])
            self.assertEqual(error_log.read_text(encoding="utf-8"), "")
            self.assertEqual(changes_log.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
