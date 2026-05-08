"""Unit tests for FTP preview download behaviour."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from picorgftp_sql.services import ftp_service


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


if __name__ == "__main__":
    unittest.main()
