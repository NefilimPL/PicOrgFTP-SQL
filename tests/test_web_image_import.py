"""Tests for importing product images from external web pages."""

from __future__ import annotations

import io
from urllib.error import HTTPError

import picorgftp_sql.web_image_import as web_image_import
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


def test_discover_image_candidates_keeps_html_urls_when_probe_fails() -> None:
    html = """
    <html>
      <body>
        <img src="/gallery/product-front.jpg">
      </body>
    </html>
    """

    candidates = discover_image_candidates(
        "https://shop.example/product.html",
        html,
        image_probe=lambda _url, _referer: (_ for _ in ()).throw(RuntimeError("blocked")),
    )

    assert len(candidates) == 1
    assert candidates[0]["url"] == "https://shop.example/gallery/product-front.jpg"
    assert candidates[0]["width"] == 0
    assert candidates[0]["height"] == 0
    assert candidates[0]["size_bytes"] == 0
    assert candidates[0]["mime_type"] == "image/jpeg"


def test_discover_image_candidates_reads_escaped_script_urls() -> None:
    html = r"""
    <html>
      <body>
        <script>
          window.productImages = [
            "https:\/\/cdn.example\/products\/front.webp",
            "\/products\/relative-detail.jpg"
          ];
        </script>
      </body>
    </html>
    """

    candidates = discover_image_candidates(
        "https://shop.example/product.html",
        html,
        image_probe=lambda url, _referer: (900, 700, 100_000, "image/webp")
        if url.endswith(".webp")
        else (800, 600, 90_000, "image/jpeg"),
    )

    assert [item["url"] for item in candidates] == [
        "https://cdn.example/products/front.webp",
        "https://shop.example/products/relative-detail.jpg",
    ]


def test_discover_image_candidates_can_return_links_without_probing() -> None:
    probed = []
    html = """
    <html>
      <body>
        <img srcset="/small.jpg 240w, /large.jpg 1200w">
        <img src="/thumb/photo.jpg" width="120" height="80">
      </body>
    </html>
    """

    candidates = discover_image_candidates(
        "https://shop.example/product.html",
        html,
        image_probe=lambda url, _referer: probed.append(url) or (1, 1, 1, "image/jpeg"),
        probe_images=False,
        filters={"minWidth": 800, "hideThumbnails": True},
    )

    assert probed == []
    assert [item["url"] for item in candidates] == [
        "https://shop.example/large.jpg",
    ]
    assert candidates[0]["width"] == 1200
    assert candidates[0]["size_bytes"] == 0


def test_discover_image_candidates_applies_size_filter_after_probe() -> None:
    html = """
    <html>
      <body>
        <img src="/small-file.jpg">
        <img src="/large-file.jpg">
      </body>
    </html>
    """
    sizes = {
        "https://shop.example/small-file.jpg": (1200, 900, 20 * 1024, "image/jpeg"),
        "https://shop.example/large-file.jpg": (1200, 900, 220 * 1024, "image/jpeg"),
    }

    candidates = discover_image_candidates(
        "https://shop.example/product.html",
        html,
        image_probe=lambda url, _referer: sizes[url],
        filters={"minKb": 100},
    )

    assert [item["url"] for item in candidates] == [
        "https://shop.example/large-file.jpg",
    ]


def test_discover_image_candidates_applies_include_and_exclude_url_filter() -> None:
    html = """
    <html>
      <body>
        <img src="/gallery/large-front.jpg">
        <img src="/gallery/thumb-front.jpg">
        <img src="/gallery/detail-side.jpg">
      </body>
    </html>
    """

    candidates = discover_image_candidates(
        "https://shop.example/product.html",
        html,
        probe_images=False,
        filters={"urlFilter": "front !thumb"},
    )

    assert [item["url"] for item in candidates] == [
        "https://shop.example/gallery/large-front.jpg",
    ]


def test_discover_image_candidates_applies_or_url_filter_groups() -> None:
    html = """
    <html>
      <body>
        <img src="/gallery/sofa-bialy-front.jpg">
        <img src="/gallery/sofa-czarny-front.jpg">
        <img src="/gallery/sofa-szary-front.jpg">
        <img src="/gallery/sofa-czarny-thumb.jpg">
      </body>
    </html>
    """

    candidates = discover_image_candidates(
        "https://shop.example/product.html",
        html,
        probe_images=False,
        filters={"urlFilter": "<bialy|czarny> !thumb"},
    )

    assert [item["url"] for item in candidates] == [
        "https://shop.example/gallery/sofa-bialy-front.jpg",
        "https://shop.example/gallery/sofa-czarny-front.jpg",
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


def test_fetch_page_html_uses_curl_fallback_after_repeated_forbidden(monkeypatch) -> None:
    calls = []

    def fake_open(request, _timeout=12):
        calls.append(dict(request.header_items()))
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(b"blocked"),
        )

    monkeypatch.setattr(
        web_image_import,
        "_fetch_page_html_with_curl",
        lambda url: f"<html>curl:{url}</html>",
    )

    html = fetch_page_html(
        "https://shop.example/product.html",
        opener=fake_open,
        validator=lambda url: str(url),
    )

    assert html == "<html>curl:https://shop.example/product.html</html>"
    assert len(calls) == 2
