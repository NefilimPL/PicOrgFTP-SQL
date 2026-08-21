from picorgftp_sql.services.image_dimensions import (
    ImageOcrDiagnostics,
    OcrDiagnosticCandidate,
)
from picorgftp_sql.services.ocr_cache import (
    collect_image_values,
    image_content_hash,
    restore_crop_bbox,
)
from picorgftp_sql.services.ocr_cache import enqueue_ocr_crop_jobs
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


def test_enqueue_ocr_crop_jobs_persists_a_real_crop_for_each_numeric_value(tmp_path):
    from PIL import Image

    image = tmp_path / "slot.png"
    Image.new("RGB", (80, 60), "white").save(image)
    store = SqliteStore(str(tmp_path / "ocr.sqlite"))
    diagnostics = ImageOcrDiagnostics(
        available=True,
        dimensions={},
        candidates=[
            OcrDiagnosticCandidate("120/140", 0.91, (10, 12, 40, 30), None, "120?140", True),
            OcrDiagnosticCandidate("tekst", 0.98, (42, 12, 70, 30), None, "", False),
        ],
    )

    job_ids = enqueue_ocr_crop_jobs(
        str(image),
        image_hash="a" * 64,
        diagnostics=diagnostics,
        store=store,
        crop_dir=str(tmp_path / "ocr-crops"),
    )

    jobs = store.list_ocr_crop_jobs()
    assert len(job_ids) == 1
    assert jobs[0]["image_hash"] == "a" * 64
    assert jobs[0]["bbox"] == [10, 12, 40, 30]
    assert (tmp_path / "ocr-crops" / f"{job_ids[0]}.png").is_file()


def test_collect_image_values_passes_fresh_diagnostics_to_crop_queue_callback(tmp_path):
    image = tmp_path / "slot.png"
    image.write_bytes(b"image-content")
    store = SqliteStore(str(tmp_path / "ocr.sqlite"))
    diagnostics = ImageOcrDiagnostics(True, {}, [])
    queued = []

    collect_image_values(
        str(image),
        store=store,
        analyze=lambda _path: diagnostics,
        enqueue_crops=lambda image_hash, result: queued.append((image_hash, result)),
    )

    assert queued == [(image_content_hash(str(image)), diagnostics)]


def test_restore_crop_bbox_maps_upscaled_refinement_coordinates_to_source_image():
    assert restore_crop_bbox(
        [4, 8, 80, 40],
        [10, 12, 40, 30],
    ) == [11, 14, 30, 22]
