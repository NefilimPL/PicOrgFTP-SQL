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
