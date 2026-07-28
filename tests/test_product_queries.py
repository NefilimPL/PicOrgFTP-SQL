"""Tests for the common product query contract."""

from picorgftp_sql.product_queries import (
    ProductSearchCriteria,
    filter_product_records,
)
from picorgftp_sql import data_store, excel_utils


RECORDS = [
    {"PRODUCT_ID": "P-1", "EAN": "5901", "NAZWA": "ALFA", "TYP": "STÓŁ", "MODEL": "A1"},
    {"PRODUCT_ID": "P-2", "EAN": "5902", "NAZWA": "BETA", "TYP": "SZAFA", "MODEL": "B1"},
]


def test_filter_product_records_prefers_exact_identity_and_limits():
    criteria = ProductSearchCriteria(product_id="p-1")

    assert filter_product_records(RECORDS, criteria, limit=1) == [RECORDS[0]]


def test_legacy_store_uses_prepared_records_for_exact_identity_lookups(monkeypatch):
    monkeypatch.setattr(
        excel_utils,
        "prepare_excel_lists",
        lambda: {excel_utils.ENTRY_RECORDS_KEY: RECORDS},
    )
    store = data_store.LegacyDataStore()

    assert store.get_product_by_id(" p-1 ") == RECORDS[0]
    assert store.get_product_by_ean("5902") == RECORDS[1]


def test_legacy_store_suggests_values_from_prepared_records(monkeypatch):
    monkeypatch.setattr(
        excel_utils,
        "prepare_excel_lists",
        lambda: {excel_utils.ENTRY_RECORDS_KEY: RECORDS},
    )

    assert data_store.LegacyDataStore().suggest_product_field(
        "model", "a", {"name": "ALFA"}, limit=1
    ) == ["A1"]


def test_sqlite_product_queries_do_not_load_all_lists(tmp_path, monkeypatch):
    """Catch a regression to the full SQLite product-table materialization path."""

    adapter = data_store.SqliteDataStoreAdapter(str(tmp_path / "products.sqlite"))
    adapter.save_product_entry(
        {
            "product_id": "P-1",
            "ean": "5901234567890",
            "name": "ALFA",
            "type_name": "STÓŁ",
            "model": "A1",
        }
    )
    monkeypatch.setattr(
        adapter.store,
        "load_lists",
        lambda: (_ for _ in ()).throw(AssertionError("full load")),
    )

    assert adapter.get_product_by_ean("5901234567890")["product_id"] == "P-1"
    assert adapter.get_product_by_id("p-1")["ean"] == "5901234567890"
    assert adapter.search_product_entries(
        ProductSearchCriteria(name="alfa"), limit=1
    )[0]["name"] == "ALFA"
    assert adapter.suggest_product_field("model", "a", {"name": "ALFA"}) == ["A1"]
