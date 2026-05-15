"""Generate a PyInstaller Windows VERSIONINFO file."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


VERSION_ENV_VAR = "PICORGFTP_SQL_VERSION"
DEFAULT_VERSION = "dev"
DEFAULT_PRODUCT_NAME = "PicOrgFTP-SQL"
DEFAULT_COMPANY_NAME = "NefilimPL"
DEFAULT_COPYRIGHT = "Copyright (C) NefilimPL"


def _clean_version(value: object) -> str:
    text = str(value or "").strip()
    return text or DEFAULT_VERSION


def read_build_version(repo_root: Path, explicit_version: str | None = None) -> str:
    if explicit_version:
        return _clean_version(explicit_version)

    env_version = os.environ.get(VERSION_ENV_VAR)
    if env_version:
        return _clean_version(env_version)

    version_path = repo_root / "picorgftp_sql" / "VERSION"
    try:
        return _clean_version(version_path.read_text(encoding="utf-8"))
    except OSError:
        return DEFAULT_VERSION


def version_to_windows_tuple(version: str) -> tuple[int, int, int, int]:
    cleaned = _clean_version(version)
    numbers = [int(match) for match in re.findall(r"\d+", cleaned)]
    if not numbers:
        return (0, 0, 0, 0)

    if cleaned.lower().startswith("dev-") and len(numbers) == 1:
        numbers = [0, 0, 0, numbers[0]]

    padded = (numbers + [0, 0, 0, 0])[:4]
    return tuple(min(part, 65535) for part in padded)


def build_version_info_text(
    *,
    version: str,
    file_description: str,
    internal_name: str,
    original_filename: str,
    product_name: str,
    company_name: str,
    legal_copyright: str,
) -> str:
    numeric_version = version_to_windows_tuple(version)
    strings = {
        "CompanyName": company_name,
        "FileDescription": file_description,
        "FileVersion": version,
        "InternalName": internal_name,
        "LegalCopyright": legal_copyright,
        "OriginalFilename": original_filename,
        "ProductName": product_name,
        "ProductVersion": version,
    }
    string_structs = "\n".join(
        f"          StringStruct({key!r}, {value!r}),"
        for key, value in strings.items()
    )

    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric_version!r},
    prodvers={numeric_version!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904b0',
        [
{string_structs}
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a PyInstaller --version-file for Windows EXE builds."
    )
    parser.add_argument("--output", required=True, help="Path to write the version file.")
    parser.add_argument("--version", help="Version string to embed. Defaults to env/file.")
    parser.add_argument(
        "--file-description",
        required=True,
        help="Windows FileDescription value.",
    )
    parser.add_argument(
        "--internal-name",
        required=True,
        help="Windows InternalName value.",
    )
    parser.add_argument(
        "--original-filename",
        required=True,
        help="Windows OriginalFilename value.",
    )
    parser.add_argument(
        "--product-name",
        default=DEFAULT_PRODUCT_NAME,
        help="Windows ProductName value.",
    )
    parser.add_argument(
        "--company-name",
        default=DEFAULT_COMPANY_NAME,
        help="Windows CompanyName value.",
    )
    parser.add_argument(
        "--legal-copyright",
        default=DEFAULT_COPYRIGHT,
        help="Windows LegalCopyright value.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    version = read_build_version(repo_root, args.version)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_version_info_text(
            version=version,
            file_description=args.file_description,
            internal_name=args.internal_name,
            original_filename=args.original_filename,
            product_name=args.product_name,
            company_name=args.company_name,
            legal_copyright=args.legal_copyright,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
