import json
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from picorgftp_sql import web_data
from picorgftp_sql.services.pimcore_service import PimcoreApiError, PimcoreConflictError
from picorgftp_sql.web import app as web_app


def test_settings_snapshot_hides_pimcore_api_key():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"]["enabled"] = True
    cfg["pimcore"]["api_key"] = "secret"
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "load_users", return_value=[]),
    ):
        snapshot = web_data.settings_snapshot()

    assert snapshot["pimcore"]["api_key_set"] is True
    assert "api_key" not in snapshot["pimcore"]


def test_update_settings_preserves_blank_pimcore_api_key_and_saves_mapping():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"]["api_key"] = "saved-secret"
    saved = []
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(
            web_data,
            "save_config",
            side_effect=lambda payload, **kwargs: saved.append(
                json.loads(json.dumps(payload))
            ),
        ),
        patch.object(web_data.config, "initialize_config", return_value=cfg),
        patch.object(web_data, "settings_snapshot", return_value={}),
    ):
        web_data.update_settings(
            {
                "pimcore": {
                    "enabled": True,
                    "api_key": "",
                    "base_url": "http://10.10.0.5",
                    "field_mappings": [
                        {
                            "source": "EAN",
                            "pimcore_field": "EAN",
                            "type": "input",
                            "required": True,
                            "parser": "text",
                        }
                    ],
                }
            }
        )

    assert saved[0]["pimcore"]["api_key"] == "saved-secret"
    assert saved[0]["pimcore"]["field_mappings"][0]["source"] == "EAN"


def test_parse_csv_headers_supports_semicolon_and_quoted_labels():
    raw = (
        b'SKU;EAN;"TOTAL WEIGHT";"TOTAL VOLUME [m2]"\r\n'
        b"ABC;5904804578169;62,5;1,2\r\n"
    )

    assert web_data.parse_pimcore_csv_headers(raw) == [
        "SKU",
        "EAN",
        "TOTAL WEIGHT",
        "TOTAL VOLUME [m2]",
    ]


def test_pimcore_settings_test_route_returns_structured_report():
    client = TestClient(web_app.app)
    report = {
        "ok": False,
        "checks": [{"key": "mapping_fields", "status": "error"}],
        "total_ms": 4,
    }
    with (
        patch.object(
            web_app,
            "_require_admin",
            return_value={"username": "admin", "role": "admin"},
        ),
        patch.object(web_app, "test_pimcore_settings", return_value=report),
    ):
        response = client.post("/api/settings/pimcore/test")

    assert response.status_code == 200
    assert response.json() == report


def test_admin_can_test_sql_profile_route():
    client = TestClient(web_app.app)
    expected = {"ok": True, "message": "Polaczenie SQL dziala."}
    with (
        patch.object(
            web_app,
            "_require_admin",
            return_value={"username": "admin", "role": "admin"},
        ),
        patch.object(
            web_app,
            "test_sql_profile_connection",
            return_value=expected,
        ) as test_profile,
    ):
        response = client.post("/api/settings/sql-profiles/stock/test")

    assert response.status_code == 200
    assert response.json() == expected
    test_profile.assert_called_once_with("stock")


def test_settings_diagnostic_persists_full_detail_but_returns_public_report():
    report = {
        "ok": False,
        "checks": [
            {
                "key": "server_info",
                "status": "error",
                "response_excerpt": "short trace",
                "response_detail": "complete sanitized trace",
            }
        ],
    }
    with (
        patch.object(web_data, "run_settings_test", return_value=report),
        patch.object(web_data, "record_history") as record,
    ):
        result = web_data.test_pimcore_settings({}, "admin")

    assert "response_detail" not in result["checks"][0]
    persisted = record.call_args.kwargs["details"]["pimcore_settings_test"]
    assert persisted["checks"][0]["response_detail"] == "complete sanitized trace"


def test_discovery_uses_unsaved_key_without_persisting_or_returning_it():
    captured = {}
    fake_client = Mock()
    with (
        patch.object(web_data.config, "CONFIG", {"pimcore": {"api_key": "saved"}}),
        patch.object(web_data, "PimcoreClient", return_value=fake_client) as client_type,
        patch.object(
            web_data,
            "discover_classes",
            return_value=[{"id": "7", "name": "product"}],
        ) as discover,
    ):
        client_type.side_effect = lambda settings: (
            captured.setdefault("settings", settings),
            fake_client,
        )[1]
        result = web_data.discover_pimcore_classes(
            {"base_url": "http://10.10.0.5", "api_key": "temporary"}
        )

    assert captured["settings"]["api_key"] == "temporary"
    assert result == {"items": [{"id": "7", "name": "product"}]}
    assert "temporary" not in json.dumps(result)
    discover.assert_called_once_with(fake_client)


def test_complete_setup_saves_only_after_successful_report():
    payload = {
        "base_url": "http://10.10.0.5",
        "api_key": "secret",
        "class_id": "7",
        "class_name": "product",
        "parent_id": "6626",
        "parent_path": "/Produkty",
        "field_mappings": [
            {
                "source": "EAN",
                "pimcore_field": "EAN",
                "type": "input",
                "required": True,
                "parser": "text",
            }
        ],
    }
    with (
        patch.object(web_data, "test_pimcore_settings", return_value={"ok": True, "checks": []}),
        patch.object(
            web_data,
            "update_settings",
            return_value={"pimcore": {"setup_complete": True}},
        ) as save,
    ):
        result = web_data.complete_pimcore_setup(payload, "admin")

    assert result["saved"] is True
    saved = save.call_args.args[0]["pimcore"]
    assert saved["setup_complete"] is True
    assert saved["enabled"] is True
    assert saved["object_key_template"] == "{EAN}"


def test_complete_setup_does_not_save_after_failed_report():
    with (
        patch.object(web_data, "test_pimcore_settings", return_value={"ok": False, "checks": []}),
        patch.object(web_data, "update_settings") as save,
    ):
        result = web_data.complete_pimcore_setup({"api_key": "secret"}, "admin")

    assert result == {"saved": False, "report": {"ok": False, "checks": []}}
    save.assert_not_called()


def test_pimcore_discovery_and_setup_routes_are_admin_only():
    client = TestClient(web_app.app)
    admin = {"username": "admin", "role": "admin"}
    with (
        patch.object(web_app, "_require_admin", return_value=admin) as require_admin,
        patch.object(
            web_app,
            "discover_pimcore_classes",
            return_value={"items": [{"id": "7", "name": "product"}]},
        ),
        patch.object(web_app, "discover_pimcore_fields", return_value={"items": []}),
        patch.object(web_app, "discover_pimcore_folders", return_value={"items": []}),
        patch.object(
            web_app,
            "complete_pimcore_setup",
            return_value={"saved": True, "report": {"ok": True}},
        ),
    ):
        classes = client.post("/api/settings/pimcore/discover/classes", json={"settings": {}})
        fields = client.post(
            "/api/settings/pimcore/discover/fields",
            json={"settings": {}, "class_id": "7"},
        )
        folders = client.post("/api/settings/pimcore/discover/folders", json={"settings": {}})
        saved = client.post("/api/settings/pimcore/setup", json={"settings": {}})

    assert classes.status_code == fields.status_code == folders.status_code == saved.status_code == 200
    assert require_admin.call_count == 4


def test_folder_discovery_route_degrades_to_empty_list_on_pimcore_error():
    client = TestClient(web_app.app)
    error = PimcoreApiError(
        "Pimcore zwrocil HTTP 502.",
        "/webservice/rest/object-list",
        status_code=502,
    )
    with (
        patch.object(web_app, "_require_admin", return_value={"username": "admin", "role": "admin"}),
        patch.object(web_app, "discover_pimcore_folders", side_effect=error),
    ):
        response = client.post("/api/settings/pimcore/discover/folders", json={"settings": {}})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["warning"]["status_code"] == 502


def test_pimcore_csv_headers_route_parses_uploaded_file():
    client = TestClient(web_app.app)
    with patch.object(
        web_app,
        "_require_admin",
        return_value={"username": "admin", "role": "admin"},
    ):
        response = client.post(
            "/api/settings/pimcore/import-csv-headers",
            files={
                "file": (
                    "products.csv",
                    b"SKU;EAN\r\nABC;5904804578169\r\n",
                    "text/csv",
                )
            },
        )

    assert response.status_code == 200
    assert response.json() == {"headers": ["SKU", "EAN"]}


def test_pimcore_operation_history_reads_persisted_audit_records():
    operation = {
        "operation_id": "op-1",
        "operation_type": "test",
        "username": "admin",
        "status": "partial",
        "started_at": 15.0,
        "events": [{"sequence": 1, "stage": "delete", "message": "HTTP 403"}],
    }
    records = [
        {"action": "entry_save", "details": {}},
        {"action": "pimcore_test_create", "details": {"pimcore_operation": operation}},
    ]
    with patch.object(web_data, "_load_history_records", return_value=records):
        result = web_data.pimcore_operation_history(
            operation_type="test",
            result="partial",
            user="admin",
            query="HTTP 403",
            date_from=10,
            date_to=20,
        )

    assert result == {"items": [operation], "count": 1}


def test_pimcore_test_run_routes_forward_admin_and_sequence():
    client = TestClient(web_app.app)
    user = {"username": "admin", "role": "admin"}
    with (
        patch.object(web_app, "_require_admin", return_value=user),
        patch.object(
            web_app,
            "start_pimcore_test_create",
            return_value={"operation_id": "op-1", "status": "queued"},
        ),
        patch.object(
            web_app,
            "pimcore_operation_status",
            return_value={"operation_id": "op-1", "events": [], "status": "running"},
        ) as status,
    ):
        started = client.post(
            "/api/settings/pimcore/test-create-runs",
            json={"values": {"EAN": "5904804578169"}, "cleanup_policy": "delete"},
        )
        polled = client.get(
            "/api/settings/pimcore/test-create-runs/op-1?after_sequence=4"
        )

    assert started.status_code == 200
    assert started.json()["operation"]["operation_id"] == "op-1"
    assert polled.status_code == 200
    status.assert_called_once_with("op-1", 4)


def test_missing_pimcore_operation_returns_404():
    client = TestClient(web_app.app)
    with (
        patch.object(
            web_app,
            "_require_admin",
            return_value={"username": "admin", "role": "admin"},
        ),
        patch.object(web_app, "pimcore_operation_status", return_value=None),
    ):
        response = client.get("/api/settings/pimcore/test-create-runs/missing")

    assert response.status_code == 404


def test_pimcore_history_route_forwards_all_filters():
    client = TestClient(web_app.app)
    with (
        patch.object(
            web_app,
            "_require_admin",
            return_value={"username": "admin", "role": "admin"},
        ),
        patch.object(
            web_app,
            "pimcore_operation_history",
            return_value={"items": [], "count": 0},
        ) as history,
    ):
        response = client.get(
            "/api/settings/pimcore/operations?"
            "operation_type=test&result=partial&user=admin&query=5904&"
            "date_from=10&date_to=20&limit=25"
        )

    assert response.status_code == 200
    history.assert_called_once_with(
        operation_type="test",
        result="partial",
        user="admin",
        query="5904",
        date_from=10.0,
        date_to=20.0,
        limit=25,
    )


def test_admin_can_export_pimcore_submissions_as_json():
    client = TestClient(web_app.app)
    expected = {"items": [{"operation_id": "op-1"}], "format": "json"}
    with (
        patch.object(
            web_app,
            "_require_admin",
            return_value={"username": "admin", "role": "admin"},
        ),
        patch.object(
            web_app,
            "export_pimcore_submissions",
            return_value=expected,
        ) as export,
    ):
        response = client.get(
            "/api/settings/pimcore/submissions/export?format=json&user=operator"
        )

    assert response.status_code == 200
    assert response.json() == expected
    export.assert_called_once()


def test_export_pimcore_submissions_as_csv_contains_common_columns():
    store = Mock()
    store.query_pimcore_submissions.return_value = [
        {
            "operation_id": "op-1",
            "operation_type": "manual_create",
            "username": "operator",
            "ean": "5901234567890",
            "status": "completed",
            "values": {"STOCK": "12"},
            "payload": {"className": "Product"},
            "result": {"object_id": 91},
            "warnings": [],
            "created_at": "2026-07-06T12:00:00.000Z",
        }
    ]

    with patch.object(web_data, "_active_sqlite_store", return_value=store):
        exported = web_data.export_pimcore_submissions(export_format="csv")

    assert exported["format"] == "csv"
    assert (
        "operation_id,operation_type,username,ean,status,created_at"
        in exported["content"]
    )
    assert (
        "op-1,manual_create,operator,5901234567890,completed,2026-07-06T12:00:00.000Z"
        in exported["content"]
    )


def test_product_status_returns_disabled_without_network_call():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"]["enabled"] = False

    with patch.object(web_data.config, "CONFIG", cfg):
        assert web_data.find_pimcore_product_by_ean("5904804578169") == {
            "enabled": False,
            "setup_complete": False,
            "exists": False,
            "object": None,
            "form_schema": [],
        }


def test_runtime_form_schema_includes_sql_mapping_metadata():
    settings_payload = web_data.normalize_pimcore_settings(
        {
            "field_mappings": [
                {
                    "source": "STOCK",
                    "label": "Stan",
                    "pimcore_field": "stock",
                    "type": "input",
                    "parser": "text",
                    "value_template": "SQL",
                    "sql_query": "SELECT qty FROM stock WHERE ean = {ean}",
                    "sql_profile_id": "stock-db",
                }
            ]
        }
    )

    schema = web_data._pimcore_runtime_form_schema(settings_payload)

    assert schema[0]["value_template"] == "SQL"
    assert schema[0]["sql_query"] == "SELECT qty FROM stock WHERE ean = {ean}"
    assert schema[0]["sql_profile_id"] == "stock-db"


def test_runtime_status_is_disabled_when_setup_is_incomplete():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update({"enabled": True, "setup_complete": False})
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "find_product_by_ean") as lookup,
    ):
        result = web_data.find_pimcore_product_by_ean("5904804578169")

    assert result == {
        "enabled": False,
        "setup_complete": False,
        "exists": False,
        "object": None,
        "form_schema": [],
    }
    lookup.assert_not_called()


def test_bootstrap_exposes_only_runtime_pimcore_flags():
    client = TestClient(web_app.app)
    with (
        patch.object(web_app, "_require_user", return_value="operator"),
        patch.object(
            web_app,
            "_current_user_payload",
            return_value={"username": "operator", "role": "user"},
        ),
        patch.object(web_app, "load_web_data", return_value={}),
        patch.object(
            web_app,
            "pimcore_runtime_capabilities",
            return_value={"enabled": True, "setup_complete": True},
        ),
    ):
        response = client.get("/api/bootstrap")

    assert response.json()["pimcore"] == {"enabled": True, "setup_complete": True}


def test_runtime_create_route_allows_logged_in_user_and_returns_created_object():
    client = TestClient(web_app.app)
    expected = {
        "created": True,
        "duplicate": False,
        "object": {"id": 91, "key": "ABC", "path": "/Produkty/ABC"},
    }

    with (
        patch.object(web_app, "_require_user", return_value="operator"),
        patch.object(web_app, "create_pimcore_product", return_value=expected) as create,
    ):
        response = client.post(
            "/api/pimcore/products",
            json={"values": {"SKU": "ABC", "EAN": "5904804578169"}},
        )

    assert response.status_code == 200
    assert response.json() == expected
    create.assert_called_once_with({"SKU": "ABC", "EAN": "5904804578169"}, "operator")


def test_edit_adapter_requires_enabled_complete_setup():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update({"enabled": False, "setup_complete": True})
    with patch.object(web_data.config, "CONFIG", cfg):
        with pytest.raises(ValueError, match="wylaczona"):
            web_data.get_pimcore_product_for_edit(91)


def test_update_adapter_persists_manual_update_audit():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update({"enabled": True, "setup_complete": True})
    expected = {
        "object": {"id": 91, "path": "/Produkty/5904"},
        "values": {"EAN": "5904804578169"},
    }
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "update_product", return_value=expected),
        patch.object(web_data, "_persist_pimcore_operation") as persist,
    ):
        result = web_data.update_pimcore_product(
            91,
            "100",
            {"EAN": "5904804578169"},
            "operator",
        )

    assert result == expected
    report = persist.call_args.args[0]
    assert report["operation_type"] == "manual_update"
    assert report["username"] == "operator"


def test_create_adapter_uses_manual_create_operation_kind():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update({"enabled": True, "setup_complete": True})
    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(
            web_data,
            "create_product",
            return_value={"created": True, "duplicate": False, "object": {"id": 91}},
        ),
        patch.object(web_data, "_persist_pimcore_operation") as persist,
    ):
        web_data.create_pimcore_product({"EAN": "5904804578169"}, "operator")

    assert persist.call_args.args[0]["operation_type"] == "manual_create"


def test_create_adapter_persists_detailed_sqlite_submission_when_store_active():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update({"enabled": True, "setup_complete": True})
    store = Mock()

    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "_active_sqlite_store", return_value=store),
        patch.object(
            web_data,
            "create_product",
            return_value={
                "created": True,
                "duplicate": False,
                "object": {"id": 91},
                "payload": {"className": "Product"},
            },
        ),
        patch.object(web_data, "_persist_pimcore_operation"),
    ):
        web_data.create_pimcore_product({"EAN": "5904804578169"}, "operator")

    submitted = store.append_pimcore_submission.call_args.args[0]
    assert submitted["operation_type"] == "manual_create"
    assert submitted["username"] == "operator"
    assert submitted["values"]["EAN"] == "5904804578169"
    assert submitted["payload"]["className"] == "Product"


def test_runtime_edit_routes_allow_logged_in_user():
    client = TestClient(web_app.app)
    loaded = {
        "object": {"id": 91},
        "marker": "100",
        "values": {"EAN": "5904804578169"},
        "form_schema": [],
    }
    updated = {"object": {"id": 91}, "values": {"EAN": "5904804578169"}}
    with (
        patch.object(web_app, "_require_user", return_value="operator"),
        patch.object(web_app, "get_pimcore_product_for_edit", return_value=loaded),
        patch.object(web_app, "update_pimcore_product", return_value=updated),
    ):
        get_response = client.get("/api/pimcore/products/91")
        put_response = client.put(
            "/api/pimcore/products/91",
            json={"marker": "100", "values": {"EAN": "5904804578169"}},
        )

    assert get_response.json() == loaded
    assert put_response.json() == updated


def test_runtime_edit_conflict_returns_409():
    client = TestClient(web_app.app)
    error = PimcoreConflictError("Obiekt zostal zmieniony.", 91, "100", "101")
    with (
        patch.object(web_app, "_require_user", return_value="operator"),
        patch.object(web_app, "update_pimcore_product", side_effect=error),
    ):
        response = client.put(
            "/api/pimcore/products/91",
            json={"marker": "100", "values": {"EAN": "5904804578169"}},
        )
    assert response.status_code == 409
    assert response.json()["detail"]["current_marker"] == "101"


def test_admin_can_preview_unsaved_pimcore_template():
    client = TestClient(web_app.app)
    payload = {
        "mappings": [],
        "target_source": "TITLE",
        "product_values": {},
        "values": {},
    }
    expected = {"values": {"TITLE": "VIVO"}, "warnings": []}
    with (
        patch.object(web_app, "_require_admin", return_value="admin"),
        patch.object(
            web_app,
            "preview_pimcore_template",
            return_value=expected,
            create=True,
        ),
    ):
        response = client.post(
            "/api/settings/pimcore/template-preview",
            json=payload,
        )

    assert response.status_code == 200
    assert response.json() == expected


def test_template_preview_fills_missing_product_placeholders_from_saved_entry():
    payload = {
        "mappings": [
            {
                "source": "TITLE",
                "label": "Nazwa",
                "pimcore_field": "title",
                "type": "input",
                "parser": "text",
                "value_template": "{PRODUCT:name|keep} - {PRODUCT:type|keep}",
            }
        ],
        "target_source": "TITLE",
        "product_values": {},
        "values": {},
    }
    records = {
        web_data.ENTRY_RECORDS_KEY: [
            {
                web_data.NAME_HEADER: "Vivo",
                web_data.TYPE_HEADER: "Komoda",
                web_data.MODEL_HEADER: "M1",
                web_data.COLOR1_HEADER: "bialy",
                web_data.EAN_HEADER: "5904804578169",
            }
        ]
    }

    with patch.object(web_data, "prepare_excel_lists", return_value=records):
        result = web_data.preview_pimcore_template(payload)

    assert result["values"]["TITLE"] == "Vivo - Komoda"


def test_admin_test_sample_route_returns_fresh_editable_values():
    client = TestClient(web_app.app)
    expected = {
        "form_schema": [{"source": "EAN"}],
        "values": {"EAN": "5904804578169"},
        "warnings": [],
    }
    with (
        patch.object(web_app, "_require_admin", return_value="admin"),
        patch.object(
            web_app,
            "pimcore_test_sample",
            return_value=expected,
            create=True,
        ),
    ):
        response = client.post("/api/settings/pimcore/test-sample")

    assert response.status_code == 200
    assert response.json() == expected


def test_test_sample_renders_product_placeholders_from_saved_entry_when_available():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update(
        {
            "enabled": True,
            "setup_complete": True,
            "field_mappings": [
                {
                    "source": "TITLE",
                    "label": "Title",
                    "pimcore_field": "title",
                    "type": "input",
                    "parser": "text",
                    "value_template": "{PRODUCT:name|keep} - {PRODUCT:type|keep}",
                }
            ],
        }
    )
    records = {
        web_data.ENTRY_RECORDS_KEY: [
            {
                web_data.NAME_HEADER: "Vivo",
                web_data.TYPE_HEADER: "Komoda",
                web_data.MODEL_HEADER: "M1",
                web_data.COLOR1_HEADER: "bialy",
                web_data.EAN_HEADER: "5904804578169",
            }
        ]
    }

    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(web_data, "prepare_excel_lists", return_value=records),
    ):
        sample = web_data.pimcore_test_sample()

    assert sample["values"]["TITLE"] == "Vivo - Komoda"


def test_test_sample_is_available_when_complete_integration_is_temporarily_disabled():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update(
        {
            "enabled": False,
            "setup_complete": True,
            "field_mappings": [
                {
                    "source": "SKU",
                    "label": "SKU",
                    "pimcore_field": "sku",
                    "type": "input",
                    "parser": "text",
                }
            ],
        }
    )

    with patch.object(web_data.config, "CONFIG", cfg):
        sample = web_data.pimcore_test_sample()

    assert sample["values"]["SKU"].startswith("TEST_SKU_")


def test_logged_in_user_can_render_only_saved_templates():
    client = TestClient(web_app.app)
    expected = {"values": {"TITLE": "VIVO"}, "warnings": []}
    with (
        patch.object(web_app, "_require_user", return_value="operator"),
        patch.object(
            web_app,
            "render_saved_pimcore_templates",
            return_value=expected,
            create=True,
        ) as render,
    ):
        response = client.post(
            "/api/pimcore/render-templates",
            json={
                "product_values": {"name": "Vivo"},
                "values": {},
                "targets": ["TITLE"],
            },
        )

    assert response.status_code == 200
    assert response.json() == expected
    render.assert_called_once_with({"name": "Vivo"}, {}, ["TITLE"], "create")


def test_render_saved_pimcore_templates_auto_applies_sql_only_when_empty():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update(
        {
            "enabled": True,
            "setup_complete": True,
            "field_mappings": [
                {
                    "source": "STOCK",
                    "label": "Stan",
                    "pimcore_field": "stockText",
                    "type": "input",
                    "parser": "text",
                    "value_template": "SQL",
                    "sql_query": "SELECT stock FROM product WHERE ean = {ean}",
                    "sql_profile_id": "stock",
                }
            ],
        }
    )
    cfg["sql_profiles"] = [
        {
            "id": "stock",
            "label": "Stock",
            "type": "mysql",
            "host": "mysql.local",
            "database": "catalog",
            "user": "reader",
            "password": "secret",
            "enabled": True,
        }
    ]

    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(
            web_data,
            "execute_sql_value_query",
            return_value=web_data.SqlValueResult("12", []),
        ),
    ):
        empty = web_data.render_saved_pimcore_templates(
            {"ean": "5901234567890"},
            {"STOCK": ""},
            ["STOCK"],
        )
        manual = web_data.render_saved_pimcore_templates(
            {"ean": "5901234567890"},
            {"STOCK": "manual"},
            ["STOCK"],
        )

    assert empty["values"]["STOCK"] == "12"
    assert empty["calculated_values"]["STOCK"] == "12"
    assert empty["changed"]["STOCK"] is False
    assert manual["values"]["STOCK"] == "manual"
    assert manual["calculated_values"]["STOCK"] == "12"
    assert manual["changed"]["STOCK"] is True


def test_render_saved_pimcore_templates_for_edit_does_not_auto_apply_sql():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"].update(
        {
            "enabled": True,
            "setup_complete": True,
            "field_mappings": [
                {
                    "source": "STOCK",
                    "label": "Stan",
                    "pimcore_field": "stockText",
                    "type": "input",
                    "parser": "text",
                    "value_template": "SQL",
                    "sql_query": "SELECT stock FROM product WHERE ean = {ean}",
                    "sql_profile_id": "stock",
                }
            ],
        }
    )
    cfg["sql_profiles"] = [
        {
            "id": "stock",
            "label": "Stock",
            "type": "mysql",
            "host": "mysql.local",
            "database": "catalog",
            "user": "reader",
            "password": "secret",
            "enabled": True,
        }
    ]

    with (
        patch.object(web_data.config, "CONFIG", cfg),
        patch.object(
            web_data,
            "execute_sql_value_query",
            return_value=web_data.SqlValueResult("12", []),
        ),
    ):
        result = web_data.render_saved_pimcore_templates(
            {"ean": "5901234567890"},
            {"STOCK": "existing"},
            ["STOCK"],
            mode="edit",
        )

    assert result["values"]["STOCK"] == "existing"
    assert result["calculated_values"]["STOCK"] == "12"
    assert result["changed"]["STOCK"] is True
