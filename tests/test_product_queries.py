"""Tests for the common product query contract."""

from unittest.mock import Mock

from picorgftp_sql.product_queries import (
    ProductSearchCriteria,
    filter_product_records,
)
from picorgftp_sql import data_store, excel_utils, web_data


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
            "PRODUCT_ID": "P-1",
            "EAN": "5901234567890",
            "NAZWA": "ALFA",
            "TYP": "STÓŁ",
            "MODEL": "A1",
        }
    )
    monkeypatch.setattr(
        adapter.store,
        "load_lists",
        lambda: (_ for _ in ()).throw(AssertionError("full load")),
    )

    expected = {
        "PRODUCT_ID": "P-1",
        "EAN": "5901234567890",
        "NAZWA": "ALFA",
        "TYP": "STÓŁ",
        "MODEL": "A1",
        "KOLOR1": "",
        "KOLOR2": "",
        "KOLOR3": "",
        "DODATKI": "NO-LED",
    }
    legacy = data_store.LegacyDataStore()
    monkeypatch.setattr(legacy, "_product_records", lambda: [expected])
    assert adapter.get_product_by_ean("5901234567890") == legacy.get_product_by_ean(
        "5901234567890"
    )
    assert adapter.get_product_by_id("p-1") == legacy.get_product_by_id("p-1")
    criteria = ProductSearchCriteria(name="alfa")
    assert adapter.search_product_entries(criteria, limit=1) == legacy.search_product_entries(
        criteria, limit=1
    )
    assert adapter.suggest_product_field(
        "model", "a", {"name": "ALFA"}
    ) == legacy.suggest_product_field("model", "a", {"name": "ALFA"})


def test_search_entries_delegates_to_active_store(monkeypatch):
    """Catch a regression to web-side product-list materialization."""

    store = Mock()
    store.search_product_entries.return_value = [
        {"PRODUCT_ID": "P-1", "EAN": "5901", "NAZWA": "ALFA"}
    ]
    monkeypatch.setattr(web_data, "get_active_store", lambda: store)
    monkeypatch.setattr(
        web_data,
        "prepare_excel_lists",
        lambda: (_ for _ in ()).throw(AssertionError("full load")),
    )

    result = web_data.search_entries(ean="5901", limit=10)

    assert result[0]["product_id"] == "P-1"
    store.search_product_entries.assert_called_once_with(
        ProductSearchCriteria(ean="5901"), limit=10
    )


def test_web_search_query_is_filtered_by_sqlite_store_before_limit(tmp_path, monkeypatch):
    """A matching row after an earlier criterion match must remain reachable."""

    store = data_store.SqliteDataStoreAdapter(str(tmp_path / "products.sqlite"))
    store.save_product_entry(
        {
            "PRODUCT_ID": "P-1",
            "EAN": "5901",
            "NAZWA": "ALFA",
            "TYP": "STOL",
            "MODEL": "A1",
            "DODATKI": "MISS",
        }
    )
    store.save_product_entry(
        {
            "PRODUCT_ID": "P-2",
            "EAN": "5902",
            "NAZWA": "ALFA",
            "TYP": "STOL",
            "MODEL": "A2",
            "DODATKI": "TARGET",
        }
    )
    monkeypatch.setattr(web_data, "get_active_store", lambda: store)
    monkeypatch.setattr(
        web_data,
        "prepare_excel_lists",
        lambda: (_ for _ in ()).throw(AssertionError("full load")),
    )

    result = web_data.search_entries(name="ALFA", query="target", limit=1)

    assert [entry["product_id"] for entry in result] == ["P-2"]


def test_search_entries_clamps_zero_and_negative_limits(monkeypatch):
    """Store delegation must keep non-positive product limits bounded."""

    store = Mock()
    store.search_product_entries.return_value = []
    monkeypatch.setattr(web_data, "get_active_store", lambda: store)

    web_data.search_entries(limit=0)
    web_data.search_entries(limit=-1)

    assert [call.kwargs["limit"] for call in store.search_product_entries.call_args_list] == [
        1,
        1,
    ]


def test_find_entry_by_ean_uses_store_and_returns_browser_payload(monkeypatch):
    """Identity lookup must retain the lowercase browser response contract."""

    store = Mock()
    store.get_product_by_ean.return_value = {
        "PRODUCT_ID": "P-1",
        "EAN": "5901",
        "NAZWA": "ALFA",
        "TYP": "STOL",
        "MODEL": "A1",
        "KOLOR1": "BIALY",
        "KOLOR2": "",
        "KOLOR3": "",
        "DODATKI": "NO-LED",
    }
    monkeypatch.setattr(web_data, "get_active_store", lambda: store)

    result = web_data.find_entry_by_identity(ean="5901")

    assert result is not None
    assert result["product_id"] == "P-1"
    assert result["ean"] == "5901"
    assert result["extra"] == "NO-LED"
    store.get_product_by_ean.assert_called_once_with("5901")


def test_field_suggestions_delegates_to_active_store(monkeypatch):
    """Catch a regression to loading all product rows for suggestions."""

    store = Mock()
    store.mode = "sqlite"
    store.suggest_product_field.return_value = ["ALFA"]
    monkeypatch.setattr(web_data, "get_active_store", lambda: store)
    monkeypatch.setattr(web_data, "_get_file_index", lambda **_kwargs: None)
    monkeypatch.setattr(
        web_data,
        "prepare_excel_lists",
        lambda: (_ for _ in ()).throw(AssertionError("full load")),
    )

    result = web_data.field_suggestions("name", {"name": "al"}, limit=10)

    assert result == ["ALFA"]
    store.suggest_product_field.assert_called_once_with(
        "name",
        "al",
        {
            "product_id": "",
            "ean": "",
            "name": "",
            "type_name": "",
            "model": "",
        },
        limit=10,
    )


def test_save_web_entry_uses_one_active_store_identity_lookup(monkeypatch):
    """Catch duplicate product-ID and EAN pre-lookups before a save."""

    store = Mock()
    store.get_product_by_id.return_value = {
        "PRODUCT_ID": "P-1",
        "EAN": "5901",
    }
    monkeypatch.setattr(web_data, "get_active_store", lambda: store)
    save_entry = Mock(return_value={"updated": True, "product_id": "P-1", "entry": {}})
    monkeypatch.setattr(web_data, "save_ean_entry", save_entry)

    web_data.save_web_entry(
        {
            "product_id": "P-1",
            "ean": "5901",
            "name": "ALFA",
            "type_name": "STOL",
            "model": "A1",
            "color1": "BIALY",
        }
    )

    store.get_product_by_id.assert_called_once_with("P-1")
    store.get_product_by_ean.assert_not_called()
