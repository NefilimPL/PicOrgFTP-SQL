from picorgftp_sql.sqlite_store import SqliteStore


def initialized_store(tmp_path):
    store = SqliteStore(str(tmp_path / "store.sqlite"))
    store.initialize()
    return store


def test_ocr_scan_survives_store_reopen(tmp_path):
    path = tmp_path / "store.sqlite"
    store = SqliteStore(str(path))
    store.initialize()
    store.upsert_ocr_scan(
        "a" * 64,
        [
            {
                "text": "120/140",
                "comparison": "120?140",
                "confidence": 0.91,
                "bbox": [1, 2, 3, 4],
            }
        ],
        "partial",
    )

    reopened = SqliteStore(str(path))
    reopened.initialize()

    assert reopened.get_ocr_scan("a" * 64)["values"][0]["comparison"] == "120?140"


def test_ocr_approval_requires_same_image_hash_set(tmp_path):
    store = initialized_store(tmp_path)
    store.record_ocr_approval("WIDTH", "120", ["hash-a"])

    assert store.has_ocr_approval("WIDTH", "120", ["hash-a"])
    assert not store.has_ocr_approval("WIDTH", "120", ["hash-b"])


def test_ocr_crop_job_is_claimed_once_and_completed(tmp_path):
    store = initialized_store(tmp_path)
    store.enqueue_ocr_crop_job(
        {"image_hash": "hash-a", "bbox": [1, 2, 30, 20], "thumbnail_path": "crop.png"}
    )

    job = store.claim_ocr_crop_job()

    assert job["image_hash"] == "hash-a"
    assert store.claim_ocr_crop_job() is None
    store.complete_ocr_crop_job(job["id"], [{"text": "120", "comparison": "120"}])
    assert store.list_ocr_crop_jobs()[0]["status"] == "completed"


def test_ocr_crop_job_can_return_to_pending_when_user_activity_resumes(tmp_path):
    store = initialized_store(tmp_path)
    job_id = store.enqueue_ocr_crop_job({"image_hash": "a" * 64, "bbox": [1, 2, 3, 4]})

    claimed = store.claim_ocr_crop_job()
    store.requeue_ocr_crop_job(job_id)
    resumed = store.claim_ocr_crop_job()

    assert claimed is not None
    assert resumed is not None
    assert resumed["id"] == job_id
