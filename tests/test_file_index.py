"""Unit tests for the local filesystem index cache."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from picorgftp_sql.file_index import LocalFileIndex
from picorgftp_sql.sqlite_store import SqliteStore


class LocalFileIndexTests(unittest.TestCase):
    def test_refresh_sync_builds_hierarchy_and_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "_ZDJECIA PRZEROBIONE_"
            product_dir = root / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY-CZARNY" / "NO-LED"
            product_dir.mkdir(parents=True)
            (product_dir / "5901234567890_01_MAIN.jpg").write_text("a", encoding="utf-8")
            (product_dir / "5901234567890_02_DETAIL.png").write_text("b", encoding="utf-8")
            alt_dir = root / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY-CZARNY" / "LED-RGB"
            alt_dir.mkdir(parents=True)
            (alt_dir / "5901234567890_08_MOOD.png").write_text("c", encoding="utf-8")
            second_name = root / "LUNA" / "SZAFKA" / "LU01" / "DAB" / "NO-LED"
            second_name.mkdir(parents=True)
            cache_path = base / "file_index.json"

            index = LocalFileIndex(str(root), str(cache_path))
            self.assertFalse(index.load_cache())
            self.assertTrue(index.refresh_sync())

            self.assertEqual(index.get_names(), ["LUNA", "MAGGIORE"])
            self.assertEqual(index.get_types("maggiore"), ["KOMODA"])
            self.assertEqual(index.get_models("MAGGIORE", "komoda"), ["MA03"])
            self.assertEqual(
                index.get_colors("MAGGIORE", "KOMODA", "MA03"),
                ["BIALY-CZARNY"],
            )
            self.assertEqual(
                index.get_extras("MAGGIORE", "KOMODA", "MA03", ["bialy", "czarny"]),
                ["LED-RGB", "NO-LED"],
            )
            self.assertEqual(
                index.get_product_files(
                    "MAGGIORE",
                    "KOMODA",
                    "MA03",
                    ["BIALY", "CZARNY"],
                    "",
                ),
                ["5901234567890_01_MAIN.jpg", "5901234567890_02_DETAIL.png"],
            )
            self.assertEqual(index.get_types("NIE-MA"), None)
            self.assertEqual(index.get_status()["state"], "ready")

    def test_load_cache_reuses_saved_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "_ZDJECIA PRZEROBIONE_"
            product_dir = root / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY" / "NO-LED"
            product_dir.mkdir(parents=True)
            (product_dir / "5901234567890_01_MAIN.jpg").write_text("a", encoding="utf-8")
            cache_path = base / "file_index.json"

            writer = LocalFileIndex(str(root), str(cache_path))
            self.assertTrue(writer.refresh_sync())

            reader = LocalFileIndex(str(root), str(cache_path))
            self.assertTrue(reader.load_cache())
            self.assertEqual(reader.get_names(), ["MAGGIORE"])
            self.assertEqual(
                reader.get_product_files(
                    "MAGGIORE",
                    "KOMODA",
                    "MA03",
                    ["BIALY"],
                    "NO-LED",
                ),
                ["5901234567890_01_MAIN.jpg"],
            )
            self.assertEqual(reader.get_status()["state"], "cached")

    def test_sqlite_cache_store_reuses_saved_snapshot_without_json_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "_ZDJECIA PRZEROBIONE_"
            product_dir = root / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY" / "NO-LED"
            product_dir.mkdir(parents=True)
            (product_dir / "5901234567890_01_MAIN.jpg").write_text("a", encoding="utf-8")
            cache_path = base / "file_index.json"
            sqlite_store = SqliteStore(str(base / "data.sqlite"))

            writer = LocalFileIndex(
                str(root),
                str(cache_path),
                cache_store=sqlite_store,
            )
            self.assertTrue(writer.refresh_sync())

            self.assertFalse(cache_path.exists())
            self.assertEqual(
                sqlite_store.load_file_index_cache()["names"],
                ["MAGGIORE"],
            )

            reader = LocalFileIndex(
                str(root),
                str(cache_path),
                cache_store=sqlite_store,
            )
            self.assertTrue(reader.load_cache())
            self.assertEqual(reader.get_names(), ["MAGGIORE"])
            self.assertEqual(reader.get_status()["state"], "cached")

    def test_sqlite_cache_store_writes_iso_generated_at_and_segments(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "_ZDJECIA PRZEROBIONE_"
            product_dir = root / "MAGGIORE" / "KOMODA" / "MA03" / "BIALY" / "NO-LED"
            product_dir.mkdir(parents=True)
            (product_dir / "5901234567890_01_MAIN.jpg").write_text("a", encoding="utf-8")
            sqlite_store = SqliteStore(str(base / "data.sqlite"))

            index = LocalFileIndex(str(root), str(base / "file_index.json"), cache_store=sqlite_store)
            self.assertTrue(index.refresh_sync())
            snapshot = sqlite_store.load_file_index_cache()

            self.assertIsInstance(snapshot["generated_at"], str)
            self.assertIn("T", snapshot["generated_at"])
            self.assertTrue(snapshot["generated_at"].endswith("Z"))
            self.assertEqual(sqlite_store.load_file_index_segment("M", "names", "MAGGIORE"), "MAGGIORE")


if __name__ == "__main__":
    unittest.main()
