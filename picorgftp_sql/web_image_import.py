"""Discover and download product images from external web pages."""

from __future__ import annotations

from html.parser import HTMLParser
import io
import ipaddress
import mimetypes
import os
import re
import socket
from typing import Callable, Iterable
from urllib.parse import unquote, urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

from .common import SSL_CONTEXT

try:  # pragma: no cover - optional runtime dependency
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover
    Image = None
    ImageOps = None


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".avif",
}
MAX_PAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_CANDIDATES = 140
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)

IMAGE_ATTRS = {
    "src",
    "href",
    "content",
    "data-src",
    "data-original",
    "data-lazy",
    "data-lazy-src",
    "data-full",
    "data-full-src",
    "data-image",
    "data-image-src",
    "data-image-large-src",
    "data-large",
    "data-large-src",
    "data-zoom-image",
    "data-zoom-src",
    "data-src-large",
    "data-thumb",
    "poster",
}
SRCSET_ATTRS = {"srcset", "data-srcset", "data-lazy-srcset"}
THUMBNAIL_HINTS = (
    "thumb",
    "thumbnail",
    "small",
    "mini",
    "cart_default",
    "home_default",
    "small_default",
)
IMAGE_URL_RE = re.compile(
    r"""(?P<url>(?:https?:)?//[^\s"'<>\\)]+?\.(?:jpe?g|png|webp|gif|bmp|tiff?|avif)(?:\?[^\s"'<>\\)]*)?)""",
    re.IGNORECASE,
)
BACKGROUND_URL_RE = re.compile(
    r"""url\(\s*['"]?(?P<url>[^'")]+)['"]?\s*\)""",
    re.IGNORECASE,
)


class ImageImportError(ValueError):
    """Raised when a web image import request cannot be completed safely."""


def _text(value: object) -> str:
    return str(value or "").strip()


def validate_public_http_url(url: object) -> str:
    """Return a cleaned public HTTP(S) URL or raise ImageImportError."""

    text = _text(url)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ImageImportError("Podaj pelny adres strony http:// albo https://.")
    host = parsed.hostname.strip().lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ImageImportError("Adres lokalny nie jest dozwolony.")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        raise ImageImportError(f"Nie udalo sie rozwiazac hosta: {host}") from exc
    for item in addresses:
        raw_ip = item[4][0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            raise ImageImportError("Adres wskazuje na siec lokalna lub prywatna.")
    return text


def _urlopen(request: Request, timeout: int = 12):
    kwargs = {"timeout": timeout}
    if SSL_CONTEXT is not None:
        kwargs["context"] = SSL_CONTEXT
    return urlopen(request, **kwargs)


def _read_limited(response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(1024 * 256, max_bytes - total + 1))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise ImageImportError("Pobrany plik jest zbyt duzy.")
    return b"".join(chunks)


def fetch_page_html(url: object) -> str:
    """Download a page as HTML."""

    cleaned_url = validate_public_http_url(url)
    request = Request(
        cleaned_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with _urlopen(request) as response:
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type and "xml" not in content_type and content_type:
                raise ImageImportError("Podany adres nie zwrocil strony HTML.")
            data = _read_limited(response, MAX_PAGE_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
    except ImageImportError:
        raise
    except Exception as exc:
        raise ImageImportError(f"Nie udalo sie pobrac strony: {exc}") from exc
    return data.decode(charset, errors="replace")


def _without_fragment(url: str) -> str:
    return urldefrag(url)[0]


def _normalize_url(base_url: str, url: object) -> str:
    text = _text(url).replace("&amp;", "&").strip(" '\"\n\r\t")
    if not text or text.startswith(("data:", "javascript:", "mailto:", "tel:")):
        return ""
    if text.startswith("//"):
        base_scheme = urlparse(base_url).scheme or "https"
        text = f"{base_scheme}:{text}"
    absolute = urljoin(base_url, text)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return _without_fragment(absolute)


def _image_ext_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    return os.path.splitext(path)[1].lower()


def looks_like_image_url(url: str) -> bool:
    if _image_ext_from_url(url) in IMAGE_EXTENSIONS:
        return True
    lowered = url.lower()
    return any(f".{ext.lstrip('.')}" in lowered for ext in IMAGE_EXTENSIONS)


def filename_from_url(url: str, fallback: str = "web-image") -> str:
    path = unquote(urlparse(url).path)
    name = os.path.basename(path).strip(" .")
    if not name:
        extension = mimetypes.guess_extension(mimetype_from_url(url) or "") or ".jpg"
        return f"{fallback}{extension}"
    if not os.path.splitext(name)[1]:
        name = f"{name}.jpg"
    return name


def mimetype_from_url(url: str) -> str:
    guessed, _encoding = mimetypes.guess_type(urlparse(url).path)
    return guessed or ""


def _parse_dimension(value: object) -> int:
    match = re.search(r"\d+", _text(value))
    return int(match.group(0)) if match else 0


def _parse_srcset(value: object) -> list[str]:
    result: list[str] = []
    for raw_part in _text(value).split(","):
        part = raw_part.strip()
        if not part:
            continue
        candidate = part.split()[0].strip()
        if candidate:
            result.append(candidate)
    return result


def _kind_from_source(url: str, source: str, width: int = 0, height: int = 0) -> str:
    lowered = f"{url} {source}".lower()
    if any(hint in lowered for hint in THUMBNAIL_HINTS):
        return "thumbnail"
    if width and height and max(width, height) <= 320:
        return "thumbnail"
    return "image"


def _expanded_url_variants(url: str) -> Iterable[str]:
    replacements = [
        ("-small_default/", "-large_default/"),
        ("-home_default/", "-large_default/"),
        ("-cart_default/", "-large_default/"),
        ("-medium_default/", "-large_default/"),
        ("-small_default/", "-thickbox_default/"),
        ("-home_default/", "-thickbox_default/"),
        ("-cart_default/", "-thickbox_default/"),
        ("-medium_default/", "-thickbox_default/"),
    ]
    for old, new in replacements:
        if old in url:
            yield url.replace(old, new)
    yield re.sub(r"([?&])(width|height|w|h)=\d+&?", r"\1", url)


class _ImageCandidateParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.candidates: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        width = _parse_dimension(attr_map.get("width"))
        height = _parse_dimension(attr_map.get("height"))
        for key in SRCSET_ATTRS:
            for item in _parse_srcset(attr_map.get(key)):
                self._add(item, f"{tag}.{key}", width, height)
        for key in IMAGE_ATTRS:
            value = attr_map.get(key)
            if not value:
                continue
            if key == "href" and tag not in {"a", "link"}:
                continue
            if key == "content" and tag != "meta":
                continue
            if tag == "link" and key == "href":
                rel = attr_map.get("rel", "").lower()
                as_value = attr_map.get("as", "").lower()
                if "image" not in rel and as_value != "image":
                    continue
            self._add(value, f"{tag}.{key}", width, height)

    def _add(self, raw_url: object, source: str, width: int = 0, height: int = 0) -> None:
        url = _normalize_url(self.base_url, raw_url)
        if not url or not looks_like_image_url(url):
            return
        self.candidates.append(
            {
                "url": url,
                "source": source,
                "width": width,
                "height": height,
                "kind": _kind_from_source(url, source, width, height),
            }
        )
        for variant in _expanded_url_variants(url):
            normalized = _normalize_url(self.base_url, variant)
            if normalized and normalized != url and looks_like_image_url(normalized):
                self.candidates.append(
                    {
                        "url": normalized,
                        "source": "expanded",
                        "width": 0,
                        "height": 0,
                        "kind": _kind_from_source(normalized, "expanded"),
                    }
                )


def _html_url_candidates(base_url: str, html: str) -> list[dict[str, object]]:
    parser = _ImageCandidateParser(base_url)
    parser.feed(html)
    for match in BACKGROUND_URL_RE.finditer(html):
        parser._add(match.group("url"), "style.background")
    for match in IMAGE_URL_RE.finditer(html):
        parser._add(match.group("url"), "html.url")
    return parser.candidates


def probe_image_url(url: str, referer: str = "") -> tuple[int, int, int, str]:
    """Download an image and return width, height, size and MIME type."""

    cleaned_url = validate_public_http_url(url)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    request = Request(cleaned_url, headers=headers)
    try:
        with _urlopen(request) as response:
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            data = _read_limited(response, MAX_IMAGE_BYTES)
    except ImageImportError:
        raise
    except Exception as exc:
        raise ImageImportError(f"Nie udalo sie pobrac obrazu: {exc}") from exc
    width = 0
    height = 0
    if Image is not None:
        try:
            with Image.open(io.BytesIO(data)) as image:
                if ImageOps is not None:
                    try:
                        image = ImageOps.exif_transpose(image)
                    except Exception:
                        pass
                width, height = image.size
                content_type = content_type or Image.MIME.get(image.format, "")
        except Exception as exc:
            raise ImageImportError("Pobrany plik nie jest obslugiwanym obrazem.") from exc
    if content_type and not content_type.startswith("image/"):
        raise ImageImportError("Pobrany plik nie jest obrazem.")
    return width, height, len(data), content_type or mimetype_from_url(url) or "image/jpeg"


def download_image_bytes(url: str, referer: str = "") -> tuple[bytes, str, str, int, int]:
    """Download an image and return bytes, filename, MIME type, width and height."""

    cleaned_url = validate_public_http_url(url)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    request = Request(cleaned_url, headers=headers)
    try:
        with _urlopen(request) as response:
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            data = _read_limited(response, MAX_IMAGE_BYTES)
    except ImageImportError:
        raise
    except Exception as exc:
        raise ImageImportError(f"Nie udalo sie pobrac obrazu: {exc}") from exc
    width = 0
    height = 0
    if Image is not None:
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                content_type = content_type or Image.MIME.get(image.format, "")
        except Exception as exc:
            raise ImageImportError("Pobrany plik nie jest obslugiwanym obrazem.") from exc
    if content_type and not content_type.startswith("image/"):
        raise ImageImportError("Pobrany plik nie jest obrazem.")
    return (
        data,
        filename_from_url(cleaned_url),
        content_type or mimetype_from_url(cleaned_url) or "image/jpeg",
        width,
        height,
    )


def discover_image_candidates(
    page_url: str,
    html: str,
    *,
    image_probe: Callable[[str, str], tuple[int, int, int, str]] | None = None,
    limit: int = MAX_CANDIDATES,
) -> list[dict[str, object]]:
    """Return de-duplicated image candidates from HTML with optional dimensions."""

    probe = image_probe or probe_image_url
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for raw in _html_url_candidates(page_url, html):
        url = str(raw.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        width = int(raw.get("width") or 0)
        height = int(raw.get("height") or 0)
        size_bytes = 0
        mime_type = mimetype_from_url(url)
        try:
            probed_width, probed_height, probed_size, probed_mime = probe(url, page_url)
            width = probed_width or width
            height = probed_height or height
            size_bytes = probed_size
            mime_type = probed_mime or mime_type
        except Exception:
            if not width and not height:
                continue
        item = {
            "url": url,
            "filename": filename_from_url(url),
            "width": width,
            "height": height,
            "size_bytes": size_bytes,
            "mime_type": mime_type,
            "source": raw.get("source") or "",
            "kind": _kind_from_source(url, str(raw.get("source") or ""), width, height),
        }
        result.append(item)
        if len(result) >= limit:
            break
    return result
