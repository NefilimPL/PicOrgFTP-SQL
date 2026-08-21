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
