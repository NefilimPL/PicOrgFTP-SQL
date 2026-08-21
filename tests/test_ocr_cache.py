from picorgftp_sql.services.image_dimensions import (
    ImageOcrDiagnostics,
    OcrDiagnosticCandidate,
)
from picorgftp_sql.services.ocr_cache import collect_image_values
from picorgftp_sql.sqlite_store import SqliteStore


def test_collect_image_values_persists_only_numeric_candidates(tmp_path):
    image = tmp_path / "slot.png"
    image.write_bytes(b"image-content")
    store = SqliteStore(str(tmp_path / "ocr.sqlite"))
    diagnostics = ImageOcrDiagnostics(
        available=True,
        dimensions={},
        candidates=[
            OcrDiagnosticCandidate("120/140", 0.91, (1, 2, 30, 20), None, "120?140", True),
            OcrDiagnosticCandidate("tekst", 0.98, (2, 4, 20, 18), None, "", False),
        ],
    )

    result = collect_image_values(str(image), store=store, analyze=lambda _path: diagnostics)

    cached = store.get_ocr_scan(result.image_hash)
    assert result.state == "completed"
    assert cached is not None
    assert cached["state"] == "completed"
    assert cached["values"] == [
        {
            "text": "120/140",
            "comparison": "120?140",
            "confidence": 0.91,
            "bbox": [1, 2, 30, 20],
        }
    ]


def test_collect_image_values_reuses_completed_hash_without_new_ocr(tmp_path):
    image = tmp_path / "slot.png"
    image.write_bytes(b"image-content")
    store = SqliteStore(str(tmp_path / "ocr.sqlite"))
    first = collect_image_values(
        str(image),
        store=store,
        analyze=lambda _path: ImageOcrDiagnostics(True, {}, []),
    )

    second = collect_image_values(
        str(image),
        store=store,
        analyze=lambda _path: (_ for _ in ()).throw(AssertionError("OCR should not run")),
    )

    assert second.image_hash == first.image_hash
    assert second.reused is True
