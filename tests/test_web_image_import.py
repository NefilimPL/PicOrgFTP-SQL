"""Tests for importing product images from external web pages."""

from __future__ import annotations

import io
from urllib.error import HTTPError

from picorgftp_sql.web_image_import import discover_image_candidates
from picorgftp_sql.web_image_import import fetch_page_html


def test_discover_image_candidates_collects_gallery_sources_and_dimensions() -> None:
    html = """
    <html>
      <head>
        <meta property="og:image" content="/og-product.jpg">
      </head>
      <body>
        <a href="/zoom/front.jpg">
          <img
            src="/thumb/front.jpg"
            data-image-large-src="/large/front.jpg"
            srcset="/medium/front.jpg 500w, /max/front.jpg 1200w">
        </a>
        <div style="background-image: url('/gallery/detail.jpg')"></div>
      </body>
    </html>
    """
    sizes = {
        "https://shop.example/og-product.jpg": (900, 700, 100_000, "image/jpeg"),
        "https://shop.example/zoom/front.jpg": (1200, 900, 180_000, "image/jpeg"),
        "https://shop.example/thumb/front.jpg": (120, 90, 12_000, "image/jpeg"),
        "https://shop.example/large/front.jpg": (1000, 750, 140_000, "image/jpeg"),
        "https://shop.example/medium/front.jpg": (500, 375, 60_000, "image/jpeg"),
        "https://shop.example/max/front.jpg": (1600, 1200, 230_000, "image/jpeg"),
        "https://shop.example/gallery/detail.jpg": (800, 600, 90_000, "image/jpeg"),
    }

    candidates = discover_image_candidates(
        "https://shop.example/product.html",
        html,
        image_probe=lambda url, _referer: sizes[url],
    )

    by_url = {item["url"]: item for item in candidates}
    assert set(by_url) == set(sizes)
    assert by_url["https://shop.example/max/front.jpg"]["width"] == 1600
    assert by_url["https://shop.example/max/front.jpg"]["height"] == 1200
    assert by_url["https://shop.example/thumb/front.jpg"]["kind"] == "thumbnail"


def test_discover_image_candidates_ignores_non_image_links() -> None:
    html = """
    <html>
      <body>
        <a href="/regulamin.pdf">PDF</a>
        <img src="/photo.webp">
        <source srcset="/photo-small.webp 320w, /photo-big.webp 1280w">
      </body>
    </html>
    """

    candidates = discover_image_candidates(
        "https://shop.example/product.html",
        html,
        image_probe=lambda url, _referer: (100, 100, 10, "image/webp"),
    )

    assert [item["url"] for item in candidates] == [
        "https://shop.example/photo.webp",
        "https://shop.example/photo-small.webp",
        "https://shop.example/photo-big.webp",
    ]


def test_fetch_page_html_retries_forbidden_page_with_browser_headers() -> None:
    calls = []

    class FakeResponse:
        headers = {"content-type": "text/html; charset=utf-8"}

        def __init__(self) -> None:
            self._sent = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size=-1):
            if self._sent:
                return b""
            self._sent = True
            return b"<html>ok</html>"

    def fake_open(request, _timeout=12):
        calls.append(dict(request.header_items()))
        if len(calls) == 1:
            raise HTTPError(
                request.full_url,
                403,
                "Forbidden",
                hdrs=None,
                fp=io.BytesIO(b"blocked"),
            )
        return FakeResponse()

    html = fetch_page_html(
        "https://shop.example/product.html",
        opener=fake_open,
        validator=lambda url: str(url),
    )

    assert html == "<html>ok</html>"
    assert len(calls) == 2
    assert "Referer" not in calls[0]
    assert calls[1]["Referer"] == "https://shop.example/"
    assert "pl-PL" in calls[1]["Accept-language"]
