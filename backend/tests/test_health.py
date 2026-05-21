from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def test_healthcheck_returns_configured_services_without_leaking_password(monkeypatch) -> None:
    monkeypatch.setenv("IPRL_CAE_ENVIRONMENT", "local")
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    dependency_names = {dependency["name"] for dependency in body["dependencies"]}
    assert dependency_names == {"postgresql", "redis"}
    serialized = str(body)
    assert "change-me" not in serialized
    assert "***" in serialized
    get_settings.cache_clear()
