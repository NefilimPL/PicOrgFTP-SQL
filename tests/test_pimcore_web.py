import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from picorgftp_sql import web_data
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


def test_product_status_returns_disabled_without_network_call():
    cfg = json.loads(json.dumps(web_data.config.DEFAULT_CONFIG))
    cfg["pimcore"]["enabled"] = False

    with patch.object(web_data.config, "CONFIG", cfg):
        assert web_data.find_pimcore_product_by_ean("5904804578169") == {
            "enabled": False,
            "exists": False,
            "object": None,
            "form_schema": [],
        }


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
