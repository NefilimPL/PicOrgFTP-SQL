"""FTP workflow helpers."""

from __future__ import annotations

import os
import tempfile

from ..common import (
    AB,
    BK,
    CONNECTION_REFUSED_ERROR,
    E,
    G,
    H,
    J,
    LOGIN_DATA_ERROR_MSG,
    LOGIN_INCORRECT_MSG,
    NETWORK_ERROR_MSG,
    NO_SUCH_FILE_MSG,
    OTHER_ERROR_MSG,
    PATH_NOT_FOUND_MSG,
    TIMEOUT_ERROR,
    As,
    Au,
)
from ..workflow_utils import parse_slot_filename, select_remote_files_for_ean


def list_remote_filenames(ftp_conn):
    """Return remote file names using the most compatible FTP listing method."""

    names = []
    if hasattr(ftp_conn, "mlsd"):
        try:
            for entry_name, facts in ftp_conn.mlsd():
                if not entry_name or entry_name in (".", ".."):
                    continue
                entry_type = ""
                if isinstance(facts, dict):
                    entry_type = str(facts.get("type") or "").strip().lower()
                if entry_type and entry_type not in ("file",):
                    continue
                names.append(os.path.basename(entry_name))
        except (AB.error_perm, E):
            names = []
        if names:
            return names
    try:
        return [os.path.basename(name) for name in ftp_conn.nlst()]
    except AB.error_perm as exc:
        msg = str(exc).lower()
        if "no files found" in msg or "file not found" in msg:
            return []
        raise


def connect_ftp(ftp_config):
    """Create and return an FTP connection using the configured settings."""

    ftp = AB.FTP()
    ftp.connect(ftp_config["host"], ftp_config["port"], timeout=10)
    ftp.login(ftp_config["user"], ftp_config["pass"])
    ftp.set_pasv(J)
    if ftp_config.get("path"):
        ftp.cwd(ftp_config["path"])
    return ftp


def list_remote_files_for_ean(ftp_config, ean):
    """Return a map of slot prefix to remote file name for a single EAN."""

    ftp = connect_ftp(ftp_config)
    try:
        return select_remote_files_for_ean(ean, list_remote_filenames(ftp))
    finally:
        try:
            ftp.quit()
        except E:
            pass


def download_remote_slots(
    ftp_config,
    ean,
    existing_slot_paths,
    slot_index_by_prefix,
    *,
    temp_root=None,
    status_callback=None,
):
    """Download remote-only files for the product and return local temp info."""

    ftp = connect_ftp(ftp_config)
    try:
        remote_files = select_remote_files_for_ean(ean, list_remote_filenames(ftp))
        ftp_presence = {}
        remote_info = {}
        temp_root = temp_root or tempfile.mkdtemp(prefix="picorgftp_sql_")
        for label, filename in remote_files.items():
            if label in existing_slot_paths:
                ftp_presence[label] = filename
                continue
            raw_temp_path = os.path.join(temp_root, filename)
            if status_callback:
                status_callback(slot_index_by_prefix.get(label), "downloading")
            with open(raw_temp_path, "wb") as handle:
                ftp.retrbinary(f"RETR {filename}", handle.write)
            parsed = parse_slot_filename(filename)
            normalized_name = (
                parsed.normalized_name
                if parsed and parsed.normalized_name
                else os.path.basename(filename)
            )
            temp_path = os.path.join(temp_root, normalized_name)
            try:
                os.replace(raw_temp_path, temp_path)
            except OSError:
                temp_path = raw_temp_path
            ftp_presence[label] = filename
            remote_info[label] = {"filename": filename, "temp_path": temp_path}
        return remote_files, ftp_presence, remote_info
    finally:
        try:
            ftp.quit()
        except E:
            pass


def sync_remote_files(
    ftp_config,
    output_dir,
    files_to_upload,
    delete_candidates,
    ftp_downloaded_final,
    *,
    slot_index_by_filename=None,
    status_callback=None,
):
    """Upload local files and delete obsolete remote files."""

    result = {
        "uploaded": 0,
        "deleted": 0,
        "elapsed_ms": 0,
        "skipped_no_ean": False,
        "error": "",
    }
    started = __import__("time").perf_counter()
    ftp = AB.FTP()
    try:
        try:
            ftp.connect(ftp_config["host"], ftp_config["port"], timeout=10)
            ftp.login(ftp_config["user"], ftp_config["pass"])
            ftp.set_pasv(J)
            if ftp_config.get("path"):
                ftp.cwd(ftp_config["path"])
        except AB.error_perm as exc:
            text = G(exc)
            if "530" in text or LOGIN_INCORRECT_MSG in text:
                result["error"] = LOGIN_DATA_ERROR_MSG
            elif As in text or NO_SUCH_FILE_MSG in text:
                result["error"] = PATH_NOT_FOUND_MSG
            else:
                result["error"] = OTHER_ERROR_MSG.format(error=text)
            return result
        except (BK.gaierror, CONNECTION_REFUSED_ERROR, TIMEOUT_ERROR, Au):
            result["error"] = NETWORK_ERROR_MSG
            return result
        except E as exc:
            result["error"] = OTHER_ERROR_MSG.format(error=exc)
            return result

        files_local = [
            filename
            for filename in files_to_upload
            if os.path.isfile(os.path.join(output_dir, filename))
        ]
        slot_index_by_filename = slot_index_by_filename or {}
        for filename in files_local:
            if filename in ftp_downloaded_final:
                continue
            parts = filename.split("_")
            ean = parts[0] if parts else ""
            if not (ean and len(ean) == 13 and ean.isdigit()):
                result["skipped_no_ean"] = True
                continue
            prefix = parts[1] if len(parts) > 1 else ""
            extension = os.path.splitext(filename)[1]
            remote_name = f"{ean}_{prefix}{extension}"
            path = os.path.join(output_dir, filename)
            slot_idx = slot_index_by_filename.get(filename)
            if status_callback:
                status_callback(slot_idx, "uploading")
            with open(path, "rb") as handle:
                ftp.storbinary(f"STOR {remote_name}", handle)
            result["uploaded"] += 1
            if status_callback:
                status_callback(slot_idx, "")

        for remote_name in sorted(delete_candidates):
            try:
                ftp.delete(remote_name)
                result["deleted"] += 1
            except E as exc:
                text = G(exc)
                if As not in text:
                    result["error"] = OTHER_ERROR_MSG.format(error=exc)
                    break
    finally:
        result["elapsed_ms"] = int((__import__("time").perf_counter() - started) * 1000)
        try:
            ftp.quit()
        except E:
            pass
    return result
