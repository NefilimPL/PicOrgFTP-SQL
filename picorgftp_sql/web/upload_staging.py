"""Safe staging of uploads before they enter the image processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
from collections.abc import Callable

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile


_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StagedUpload:
    path: str
    original_name: str
    detected_extension: str
    size_bytes: int
    width: int | None
    height: int | None


class UploadSizeLimitExceeded(ValueError):
    """Signals a streaming size limit breach to the HTTP adapter."""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__("upload exceeds the configured size limit")
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class UploadStagingService:
    """Streams an upload to an internal location and runs blocking checks off-loop."""

    def __init__(
        self,
        *,
        max_bytes: int = 50 * 1024 * 1024,
        max_pixels: int = 25_000_000,
        validate_image: Callable[[str, object, int], tuple[int, int]] | None = None,
        scan_file: Callable[[str], object] | None = None,
    ) -> None:
        self._max_bytes = max_bytes
        self._max_pixels = max_pixels
        self._validate_image = validate_image
        self._scan_file = scan_file

    async def stage(self, upload: UploadFile, job_dir: str, prefix: str) -> StagedUpload:
        original_name = os.path.basename(str(upload.filename or f"{prefix}.upload"))
        suffix = Path(original_name).suffix.lower()
        safe_prefix = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in str(prefix)
        ).strip("._") or "upload"
        target_path = os.path.join(job_dir, f"{safe_prefix}_{secrets.token_hex(8)}{suffix}")
        size_bytes = 0

        try:
            await run_in_threadpool(os.makedirs, job_dir, exist_ok=True)
            with open(target_path, "wb") as handle:
                while True:
                    chunk = await upload.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > self._max_bytes:
                        raise UploadSizeLimitExceeded(size_bytes, self._max_bytes)
                    await run_in_threadpool(handle.write, chunk)

            width: int | None = None
            height: int | None = None
            if self._validate_image is not None:
                width, height = await run_in_threadpool(
                    self._validate_image,
                    target_path,
                    original_name,
                    self._max_pixels,
                )
            if self._scan_file is not None:
                await run_in_threadpool(self._scan_file, target_path)

            return StagedUpload(
                path=target_path,
                original_name=original_name,
                detected_extension=suffix.lstrip("."),
                size_bytes=size_bytes,
                width=width,
                height=height,
            )
        except Exception:
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except OSError:
                    pass
            raise
        finally:
            await upload.close()
