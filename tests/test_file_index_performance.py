from pathlib import Path

from picorgftp_sql import file_index
from picorgftp_sql.file_index import LocalFileIndex
from picorgftp_sql.file_index_segments import DirectoryFingerprint, scan_changed_segments


def test_scan_changed_segments_reuses_unchanged_product_directory(tmp_path: Path) -> None:
    root = tmp_path / "files"
    alfa = root / "ALFA"
    beta = root / "BETA"
    alfa.mkdir(parents=True)
    beta.mkdir()
    (alfa / "first.jpg").write_text("alfa", encoding="utf-8")
    (beta / "first.jpg").write_text("beta", encoding="utf-8")

    initial = scan_changed_segments(root, previous_fingerprints={})

    assert initial.full_scan_required is True
    assert initial.changed_segment_keys == ("ALFA", "BETA")

    (beta / "second.jpg").write_text("beta", encoding="utf-8")

    refresh = scan_changed_segments(root, initial.fingerprints)

    assert refresh.full_scan_required is False
    assert refresh.changed_segment_keys == ("BETA",)
    assert refresh.reused_segment_keys == ("ALFA",)


def test_scan_changed_segments_requires_full_scan_for_unreliable_fingerprint(
    tmp_path: Path,
) -> None:
    root = tmp_path / "files"
    product = root / "ALFA"
    product.mkdir(parents=True)
    (product / "first.jpg").write_text("alfa", encoding="utf-8")

    previous = scan_changed_segments(root, previous_fingerprints={})

    def unreliable_fingerprint(path: str, parser_version: int) -> DirectoryFingerprint:
        return DirectoryFingerprint(
            canonical_path=path,
            mtime_ns=0,
            entry_count=0,
            parser_version=parser_version,
            reliable=False,
        )

    refresh = scan_changed_segments(
        root,
        previous.fingerprints,
        fingerprint_provider=unreliable_fingerprint,
    )

    assert refresh.full_scan_required is True
    assert refresh.changed_segment_keys == ("ALFA",)
    assert refresh.reused_segment_keys == ()


def test_refresh_sync_reads_files_only_for_changed_product_segment(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "files"
    alfa_files = root / "ALFA" / "KOMODA" / "A1" / "BIALY" / "NO-LED"
    beta_files = root / "BETA" / "KOMODA" / "B1" / "CZARNY" / "NO-LED"
    alfa_files.mkdir(parents=True)
    beta_files.mkdir(parents=True)
    (alfa_files / "alfa.jpg").write_text("alfa", encoding="utf-8")
    (beta_files / "beta.jpg").write_text("beta", encoding="utf-8")
    index = LocalFileIndex(str(root), str(tmp_path / "file-index.json"))

    assert index.refresh_sync() is True
    (beta_files / "beta-new.jpg").write_text("beta", encoding="utf-8")

    read_paths: list[Path] = []
    original_file_names = file_index._file_names

    def spy_file_names(path: str) -> list[str]:
        read_paths.append(Path(path).resolve())
        return original_file_names(path)

    monkeypatch.setattr(file_index, "_file_names", spy_file_names)

    assert index.refresh_sync() is True

    assert read_paths == [beta_files.resolve()]
    assert index.get_product_files("BETA", "KOMODA", "B1", ["CZARNY"], "") == [
        "beta-new.jpg",
        "beta.jpg",
    ]


def test_refresh_sync_passes_reused_segments_to_cache_store(tmp_path: Path) -> None:
    class RecordingCacheStore:
        def __init__(self) -> None:
            self.reused_segment_keys: list[tuple[str, ...]] = []

        def save_file_index_cache(
            self,
            payload: dict,
            *,
            reused_segment_keys: tuple[str, ...] = (),
        ) -> None:
            self.reused_segment_keys.append(reused_segment_keys)

    root = tmp_path / "files"
    alfa_files = root / "ALFA" / "KOMODA" / "A1" / "BIALY" / "NO-LED"
    beta_files = root / "BETA" / "KOMODA" / "B1" / "CZARNY" / "NO-LED"
    alfa_files.mkdir(parents=True)
    beta_files.mkdir(parents=True)
    (alfa_files / "alfa.jpg").write_text("alfa", encoding="utf-8")
    (beta_files / "beta.jpg").write_text("beta", encoding="utf-8")
    cache_store = RecordingCacheStore()
    index = LocalFileIndex(
        str(root), str(tmp_path / "file-index.json"), cache_store=cache_store
    )

    assert index.refresh_sync() is True
    (beta_files / "beta-new.jpg").write_text("beta", encoding="utf-8")
    assert index.refresh_sync() is True

    assert cache_store.reused_segment_keys == [(), ("ALFA",)]
