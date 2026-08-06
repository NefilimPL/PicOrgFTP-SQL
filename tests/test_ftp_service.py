"""Unit tests for FTP preview download behaviour."""

from __future__ import annotations

from ftplib import error_perm
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from picorgftp_sql.services import ftp_service
from picorgftp_sql.services.ftp_listing_cache import RemoteListingCache


class _FakeFTP:
    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = dict(files)

    def nlst(self):
        return list(self._files)

    def retrbinary(self, command: str, writer) -> None:
        _, filename = command.split(" ", 1)
        writer(self._files[filename])

    def quit(self) -> None:
        return None


class _SyncFTP:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def connect(self, host: str, port: int, timeout: int = 10) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        return None

    def set_pasv(self, passive: bool) -> None:
        return None

    def cwd(self, path: str) -> None:
        return None

    def delete(self, filename: str) -> None:
        self.deleted.append(filename)

    def quit(self) -> None:
        return None


class _TargetedListingFTP:
    def __init__(self) -> None:
        self.nlst_results: dict[str | None, list[str]] = {}
        self.nlst_calls: list[str | None] = []
        self.mlsd_calls = 0
        self.mlsd_results: list[tuple[str, dict[str, str]]] = []
        self.nlst_error: BaseException | None = None

    def nlst(self, pattern: str | None = None) -> list[str]:
        self.nlst_calls.append(pattern)
        if self.nlst_error is not None:
            raise self.nlst_error
        return list(self.nlst_results.get(pattern, []))

    def mlsd(self):
        self.mlsd_calls += 1
        return iter(self.mlsd_results)

    def quit(self) -> None:
        return None


class DownloadRemoteSlotsTests(unittest.TestCase):
    def test_download_remote_slots_keeps_preview_for_local_slots(self) -> None:
        files = {
            "5901234567890_01_MAIN.jpg": b"local-preview",
            "5901234567890_02_DETAIL.png": b"remote-only",
        }
        fake_ftp = _FakeFTP(files)
        with TemporaryDirectory() as temp_dir:
            existing_slot_paths = {"01": str(Path(temp_dir) / "existing.jpg")}
            slot_index_by_prefix = {"01": 0, "02": 1}
            with patch.object(ftp_service, "connect_ftp", return_value=fake_ftp):
                (
                    remote_files,
                    ftp_presence,
                    preview_info,
                    remote_only_info,
                ) = ftp_service.download_remote_slots(
                    {"host": "x", "port": 21, "user": "u", "pass": "p"},
                    "5901234567890",
                    existing_slot_paths,
                    slot_index_by_prefix,
                    temp_root=temp_dir,
                )
            self.assertEqual(
                remote_files,
                {
                    "01": "5901234567890_01_MAIN.jpg",
                    "02": "5901234567890_02_DETAIL.png",
                },
            )
            self.assertEqual(ftp_presence, remote_files)
            self.assertEqual(set(preview_info), {"01", "02"})
            self.assertEqual(set(remote_only_info), {"02"})
            self.assertTrue(Path(preview_info["01"]["temp_path"]).is_file())
            self.assertTrue(Path(preview_info["02"]["temp_path"]).is_file())
            self.assertEqual(
                remote_only_info["02"]["filename"],
                "5901234567890_02_DETAIL.png",
            )

    def test_sync_remote_files_deletes_candidates_without_uploads(self) -> None:
        fake_ftp = _SyncFTP()
        with TemporaryDirectory() as temp_dir:
            with patch.object(ftp_service.AB, "FTP", return_value=fake_ftp):
                result = ftp_service.sync_remote_files(
                    {"host": "x", "port": 21, "user": "u", "pass": "p", "path": ""},
                    temp_dir,
                    [],
                    ["5901234567890_02.jpg"],
                    set(),
                )

        self.assertEqual(result["deleted"], 1)
        self.assertEqual(fake_ftp.deleted, ["5901234567890_02.jpg"])


class TargetedListingTests(unittest.TestCase):
    def test_targeted_nlst_returns_ean_files_without_full_listing(self) -> None:
        ftp = _TargetedListingFTP()
        ftp.nlst_results["5901_*"] = [
            "5901_01.jpg",
            "5901_02.png",
            "OTHER_01.jpg",
        ]

        result = ftp_service.list_remote_records_for_ean(
            ftp,
            "5901",
            capability="unknown",
        )

        self.assertEqual(
            [item.name for item in result.records],
            ["5901_01.jpg", "5901_02.png"],
        )
        self.assertEqual(result.capability, "supported")
        self.assertFalse(result.requires_full_listing)
        self.assertEqual(ftp.mlsd_calls, 0)
        self.assertEqual(ftp.nlst_calls, ["5901_*"])

    def test_unknown_empty_wildcard_requires_full_listing(self) -> None:
        ftp = _TargetedListingFTP()

        result = ftp_service.list_remote_records_for_ean(
            ftp,
            "5901",
            capability="unknown",
        )

        self.assertEqual(result.records, [])
        self.assertEqual(result.capability, "unknown")
        self.assertTrue(result.requires_full_listing)

    def test_supported_empty_wildcard_is_a_trusted_empty_result(self) -> None:
        ftp = _TargetedListingFTP()

        result = ftp_service.list_remote_records_for_ean(
            ftp,
            "5901",
            capability="supported",
        )

        self.assertEqual(result.records, [])
        self.assertEqual(result.capability, "supported")
        self.assertFalse(result.requires_full_listing)

    def test_wildcard_syntax_error_requires_full_listing(self) -> None:
        ftp = _TargetedListingFTP()
        ftp.nlst_error = error_perm("500 wildcard unsupported")

        result = ftp_service.list_remote_records_for_ean(
            ftp,
            "5901",
            capability="unknown",
        )

        self.assertEqual(result.records, [])
        self.assertEqual(result.capability, "unsupported")
        self.assertTrue(result.requires_full_listing)

    def test_unsupported_capability_skips_targeted_nlst(self) -> None:
        ftp = _TargetedListingFTP()

        result = ftp_service.list_remote_records_for_ean(
            ftp,
            "5901",
            capability="unsupported",
        )

        self.assertEqual(result.records, [])
        self.assertEqual(result.capability, "unsupported")
        self.assertTrue(result.requires_full_listing)
        self.assertEqual(ftp.nlst_calls, [])

    def test_product_lookup_uses_targeted_listing_without_full_listing(self) -> None:
        ftp = _TargetedListingFTP()
        ftp.nlst_results["5901_*"] = ["5901_01.jpg", "5901_02.png"]
        cache = RemoteListingCache()
        config = {"host": "ftp.example.test", "port": 21, "user": "operator", "pass": "p"}

        with (
            patch.object(ftp_service, "_REMOTE_LISTING_CACHE", cache),
            patch.object(ftp_service, "connect_ftp", return_value=ftp),
        ):
            files = ftp_service.list_remote_files_for_ean(config, "5901")

        self.assertEqual(files, {"01": "5901_01.jpg", "02": "5901_02.png"})
        self.assertEqual(ftp.mlsd_calls, 0)
        self.assertEqual(ftp.nlst_calls, ["5901_*"])

    def test_product_lookup_falls_back_once_then_reuses_full_snapshot(self) -> None:
        ftp = _TargetedListingFTP()
        ftp.mlsd_results = [("5901_01.jpg", {"type": "file"})]
        cache = RemoteListingCache()
        config = {"host": "ftp.example.test", "port": 21, "user": "operator", "pass": "p"}

        with (
            patch.object(ftp_service, "_REMOTE_LISTING_CACHE", cache),
            patch.object(ftp_service, "connect_ftp", return_value=ftp) as connect,
        ):
            first = ftp_service.list_remote_files_for_ean(config, "5901")
            second = ftp_service.list_remote_files_for_ean(config, "5901")

        self.assertEqual(first, {"01": "5901_01.jpg"})
        self.assertEqual(second, first)
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(ftp.mlsd_calls, 1)
        self.assertEqual(ftp.nlst_calls, ["5901_*"])


if __name__ == "__main__":
    unittest.main()
