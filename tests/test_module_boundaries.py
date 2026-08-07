from __future__ import annotations

import hashlib
from pathlib import Path

from picorgftp_sql.web.app import app


SERVICE_MODULES = tuple((Path(__file__).parents[1] / "picorgftp_sql" / "services").glob("*.py"))
ROUTE_SNAPSHOT_SHA256 = "934e219e33b84de2f3b4cfcd1fa836d332404a60ec652977f2c39de8e4f05adf"


def _route_snapshot() -> str:
    return "\n".join(
        f"{','.join(sorted(set(getattr(route, 'methods', set())) - {'HEAD', 'OPTIONS'}))} {route.path}"
        for route in app.routes
        if getattr(route, "path", "")
    )


def test_services_do_not_import_composition_roots() -> None:
    for path in SERVICE_MODULES:
        source = path.read_text(encoding="utf-8")
        assert "picorgftp_sql.web.app" not in source
        assert "picorgftp_sql.app" not in source


def test_route_contract_snapshot_is_stable() -> None:
    assert hashlib.sha256(_route_snapshot().encode("utf-8")).hexdigest() == ROUTE_SNAPSHOT_SHA256
