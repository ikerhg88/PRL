from __future__ import annotations

from fastapi.testclient import TestClient


def test_signup_email_verification_login_and_company_onboarding(client: TestClient) -> None:
    signup_response = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Admin SaaS",
            "email": "admin@example.com",
            "password": "StrongPass123!",
            "tenant_name": "Tenant SaaS",
            "company_name": "Empresa Inicial",
            "company_tax_id": "B12345678",
            "company_address": "Calle Demo 1",
        },
    )
    assert signup_response.status_code == 201
    signup_payload = signup_response.json()
    assert signup_payload["tenant_id"] > 0
    assert signup_payload["company_id"] > 0
    assert signup_payload["dev_verification_token"]

    blocked_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "StrongPass123!"},
    )
    assert blocked_login.status_code == 403
    assert blocked_login.json()["detail"] == "Email verification is required."

    verify_response = client.post(
        "/api/v1/auth/verify-email",
        json={"token": signup_payload["dev_verification_token"]},
    )
    assert verify_response.status_code == 200
    session_payload = verify_response.json()
    assert session_payload["access_token"]
    assert session_payload["user"]["email"] == "admin@example.com"
    assert session_payload["company_access"][0]["company_name"] == "Empresa Inicial"

    auth_header = {"Authorization": f"Bearer {session_payload['access_token']}"}
    me_response = client.get("/api/v1/auth/me", headers=auth_header)
    assert me_response.status_code == 200
    assert me_response.json()["tenant_id"] == signup_payload["tenant_id"]

    onboarding_response = client.post(
        "/api/v1/auth/companies/onboarding",
        headers=auth_header,
        json={
            "name": "Empresa Secundaria",
            "tax_id": "B87654321",
            "company_type": "own",
            "address": "Avenida Producto 2",
        },
    )
    assert onboarding_response.status_code == 201
    assert onboarding_response.json()["name"] == "Empresa Secundaria"

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "StrongPass123!"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["company_access"]


def test_google_signup_requires_configured_oauth_client(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/google/signup/start",
        json={
            "redirect_uri": "http://localhost:3000/auth/google/callback",
            "tenant_name": "Tenant Google",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Google OAuth client ID is not configured."


def test_tenant_scoped_routes_reject_header_impersonation_without_token(client: TestClient) -> None:
    signup_response = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Admin Secure",
            "email": "secure@example.com",
            "password": "StrongPass123!",
            "tenant_name": "Tenant Secure",
        },
    )
    tenant_id = signup_response.json()["tenant_id"]

    response = client.get(
        "/api/v1/companies",
        headers={"X-Tenant-ID": str(tenant_id), "X-User-ID": "1"},
    )

    assert response.status_code == 401


def test_system_admin_routes_reject_anonymous_requests(client: TestClient) -> None:
    assert client.get("/api/v1/tenants").status_code == 401
    assert client.get("/api/v1/saas/overview").status_code == 401
