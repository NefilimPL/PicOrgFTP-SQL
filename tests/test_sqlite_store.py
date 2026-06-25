"""Tests for the SQLite-backed application data store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from picorgftp_sql.excel_utils import ENTRY_RECORDS_KEY
from picorgftp_sql.sqlite_store import SqliteStore


def test_schema_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "data.sqlite"
    store = SqliteStore(str(db_path))

    store.initialize()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {
        "schema_version",
        "app_settings",
        "slot_definitions",
        "sql_column_map",
        "sql_available_columns",
        "list_values",
        "product_entries",
        "web_users",
        "web_history",
        "file_index_cache",
    } <= tables


def test_config_roundtrip_preserves_payload(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    store.save_config({"db_type": "mysql", "enable_sql_update": True})

    assert store.load_config()["db_type"] == "mysql"
    assert store.load_config()["enable_sql_update"] is True


def test_slots_and_sql_columns_roundtrip(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    store.save_slots(
        [{"prefix": "01", "label": "MAIN", "filename_label": "MAIN_pic"}],
        {"01": "img_01"},
    )
    store.save_sql_columns(["img_01", "img_02"], table_name="object_query_1")

    slots, sql_map = store.load_slots()
    assert slots == [{"prefix": "01", "label": "MAIN", "filename_label": "MAIN_pic"}]
    assert sql_map == {"01": "img_01"}
    assert store.load_sql_columns() == ["img_01", "img_02"]


def test_lists_roundtrip_uses_excel_payload_shape(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    store.save_lists(
        {
            "NAZWY": ["MAGGIORE"],
            "TYPY": ["KOMODA"],
            "MODELE": ["MA03"],
            "KOLORY": ["BIALY"],
            "DODATKI": ["NO-LED"],
            ENTRY_RECORDS_KEY: [
                {
                    "EAN": "5901234567890",
                    "NAZWA": "MAGGIORE",
                    "TYP": "KOMODA",
                    "MODEL": "MA03",
                    "KOLOR1": "BIALY",
                    "KOLOR2": "",
                    "KOLOR3": "",
                    "DODATKI": "NO-LED",
                    "PRODUCT_ID": "PRD-1",
                }
            ],
        }
    )

    payload = store.load_lists()
    assert payload["NAZWY"] == ["MAGGIORE"]
    assert payload["TYPY"] == ["KOMODA"]
    assert payload[ENTRY_RECORDS_KEY][0]["PRODUCT_ID"] == "PRD-1"


def test_add_and_remove_list_value(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    assert store.add_list_value("NAZWY", "maggiore") is True
    assert store.add_list_value("NAZWY", "MAGGIORE") is False
    assert store.load_lists()["NAZWY"] == ["MAGGIORE"]

    store.remove_list_value("NAZWY", "maggiore")

    assert store.load_lists()["NAZWY"] == []


def test_save_product_entry_updates_by_product_id(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "data.sqlite"))
    store.initialize()

    first = store.save_product_entry(
        {
            "EAN": "5901234567890",
            "NAZWA": "MAGGIORE",
            "TYP": "KOMODA",
            "MODEL": "MA03",
            "KOLOR1": "BIALY",
            "KOLOR2": "",
            "KOLOR3": "",
            "DODATKI": "NO-LED",
            "PRODUCT_ID": "PRD-1",
        }
    )
    second = store.save_product_entry(
        {
            "EAN": "5901234567890",
            "NAZWA": "MAGGIORE",
            "TYP": "KOMODA",
            "MODEL": "MA04",
            "KOLOR1": "BIALY",
            "KOLOR2": "",
            "KOLOR3": "",
            "DODATKI": "NO-LED",
            "PRODUCT_ID": "PRD-1",
        }
    )

    records = store.load_lists()[ENTRY_RECORDS_KEY]
    assert first["updated"] is False
    assert second["updated"] is True
    assert len(records) == 1
    assert records[0]["MODEL"] == "MA04"
