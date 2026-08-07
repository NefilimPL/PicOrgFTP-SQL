from __future__ import annotations

from io import BytesIO

from PIL import Image
from starlette.datastructures import UploadFile


def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (100, 100), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def upload_file(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))
