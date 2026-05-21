from __future__ import annotations

from fastapi.testclient import TestClient

from app.connectors.registry import list_connectors
from app.main import create_app
from app.platforms.catalog import default_platform_catalog


EXPECTED_COMMERCIAL_KEYS = {
    "asemwebservices_integra",
    "coordinaplus",
    "ctaima_cae",
    "dokify",
    "ecogestor",
    "ecoordina",
    "egestiona",
    "folyo",
    "iedoce",
    "konvergia",
    "koordinatu",
    "metacontratas",
    "nalanda",
    "nomio",
    "obralia",
    "quioo",
    "sarenet",
    "sgs_gestiona",
    "sgred",
    "sicondoc_construred",
    "sixconecta",
    "smartosh",
    "tdoc",
    "timenet",
    "ucae",
    "validate",
    "vitaly_cae",
}


def test_catalog_contains_researched_platforms_without_enabling_real_connectors() -> None:
    catalog = default_platform_catalog()
    by_key = {platform.platform_key: platform for platform in catalog}

    assert set(by_key) == {"mock_cae", *EXPECTED_COMMERCIAL_KEYS}
    assert by_key["mock_cae"].is_commercial is False
    assert by_key["dokify"].is_commercial is True
    assert by_key["ctaima_cae"].status == "researched_developer_portal"
    assert {method.method_key for method in by_key["mock_cae"].methods} == {
        "demo_simulation",
        "manual_export",
    }
    assert by_key["dokify"].technical_research.official_api_answer.startswith("yes")
    assert by_key["dokify"].technical_research.documentation_url == "https://www.dokify.net/api"
    assert by_key["metacontratas"].technical_research.official_api_answer == "no_public_api_found"
    assert by_key["ecoordina"].technical_research.public_technical_docs_status == (
        "public_integration_page_no_contract_spec"
    )
    commercial_api_methods = [
        method
        for platform in catalog
        if platform.is_commercial
        for method in platform.methods
        if method.method_key == "official_api"
    ]
    assert commercial_api_methods
    assert all(method.implemented is False for method in commercial_api_methods)


def test_catalog_only_marks_demo_and_manual_export_connectors_as_implemented() -> None:
    allowed_connectors = {connector.connector_key for connector in list_connectors()}

    for platform in default_platform_catalog():
        for method in platform.methods:
            if method.implemented:
                assert method.connector_key in allowed_connectors
            else:
                assert method.connector_key is None


def test_platform_catalog_api() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/platforms/catalog")

    assert response.status_code == 200
    body = response.json()
    keys = {item["platform_key"] for item in body}
    assert keys == {"mock_cae", *EXPECTED_COMMERCIAL_KEYS}
    assert body[0]["is_commercial"] is False
    dokify = next(item for item in body if item["platform_key"] == "dokify")
    assert dokify["status"] == "researched_api_declared"
    assert dokify["technical_research"]["official_api_answer"] == "yes_public_api_product_gated_details"
    assert dokify["technical_research"]["evidence_urls"] == ["https://www.dokify.net/api"]


def test_system_platform_modules_are_separated_from_tenant_configuration() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/system/platform-modules")

    assert response.status_code == 200
    modules = response.json()
    assert modules
    assert {module["module_scope"] for module in modules} == {"system"}
    demo = next(module for module in modules if module["connector_key"] == "connector_demo")
    manual_export = next(module for module in modules if module["connector_key"] == "connector_manual_export")
    assert {module["platform_key"] for module in modules} == {"mock_cae", *EXPECTED_COMMERCIAL_KEYS}
    assert demo["health_status"] == "ok"
    assert demo["tenant_config_required"] is True
    assert manual_export["implemented"] is True
    assert manual_export["tenant_config_required"] is True
    commercial_api_modules = [
        module
        for module in modules
        if module["platform_key"] in EXPECTED_COMMERCIAL_KEYS and module["method_key"] == "official_api"
    ]
    assert commercial_api_modules
    assert {module["implemented"] for module in commercial_api_modules} == {False}
