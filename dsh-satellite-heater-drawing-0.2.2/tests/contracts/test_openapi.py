from __future__ import annotations

import json
from pathlib import Path

from heater_drawing.domain.models import ErrorCode

ROOT = Path(__file__).resolve().parents[2]


def resolved_routes(document: dict[str, object]) -> set[str]:
    routes: set[str] = set()
    servers = document["servers"]
    for path, item in document["paths"].items():
        for method in ("get", "post", "put", "patch", "delete"):
            operation = item.get(method)
            if operation:
                assert operation["x-implementation-status"] == "not_implemented"
                selected = operation.get("servers", item.get("servers", servers))
                for server in selected:
                    routes.add(server["url"].rstrip("/") + path)
    return routes


def test_openapi_resolves_health_and_business_routes_correctly() -> None:
    document = json.loads(
        (ROOT / "schemas/openapi.json").read_text(encoding="utf-8")
    )
    routes = resolved_routes(document)
    assert "/healthz" in routes
    assert "/readyz" in routes
    business = routes - {"/healthz", "/readyz"}
    assert business
    assert all(path.startswith("/api/heater/v1/") for path in business)
    assert not any(path.startswith("/api/heater/v1/health") for path in routes)
    assert not any(path.startswith("/api/heater/v1/ready") for path in routes)


def test_openapi_error_code_matches_python_enum() -> None:
    document = json.loads(
        (ROOT / "schemas/openapi.json").read_text(encoding="utf-8")
    )
    values = document["components"]["schemas"]["ErrorCode"]["enum"]
    assert set(values) == {item.value for item in ErrorCode}
