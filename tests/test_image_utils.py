"""Tests for image content fitting helpers."""

from __future__ import annotations

from PIL import Image

from picorgftp_sql.image_utils import fit_image_to_content, find_content_bbox


def test_find_content_bbox_detects_white_border() -> None:
    image = Image.new("RGB", (400, 300), "white")
    for x in range(150, 251):
        for y in range(100, 201):
            image.putpixel((x, y), (20, 20, 20))

    bbox = find_content_bbox(image)

    assert bbox is not None
    assert 140 <= bbox[0] <= 155
    assert 95 <= bbox[1] <= 105
    assert 245 <= bbox[2] <= 260
    assert 195 <= bbox[3] <= 210


def test_fit_image_to_content_crops_background_and_matches_target_aspect() -> None:
    image = Image.new("RGB", (400, 300), "white")
    for x in range(150, 251):
        for y in range(100, 201):
            image.putpixel((x, y), (20, 20, 20))

    fitted = fit_image_to_content(image, target_size=(200, 200), margin_ratio=0.08)

    assert fitted.size[0] < image.size[0]
    assert fitted.size[1] < image.size[1]
    assert abs((fitted.size[0] / fitted.size[1]) - 1.0) < 0.05
    assert fitted.getbbox() is not None


def test_fit_image_to_content_uses_alpha_border() -> None:
    image = Image.new("RGBA", (300, 200), (255, 255, 255, 0))
    for x in range(90, 211):
        for y in range(60, 141):
            image.putpixel((x, y), (0, 0, 0, 255))

    fitted = fit_image_to_content(image, target_size=(240, 176), margin_ratio=0.05)

    assert fitted.size[0] < image.size[0]
    assert fitted.size[1] < image.size[1]
    assert fitted.getbbox() is not None
