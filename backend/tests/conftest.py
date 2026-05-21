from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone

os.environ.setdefault("IPRL_CAE_ENVIRONMENT", "local")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import ExternalPlatform, PlatformConnectionMethod, Role, Tenant, User
from app.db.session import get_session
from app.main import create_app
from app.platforms.catalog import default_platform_catalog
from app.services.auth import hash_password
from app.services.sso import create_local_access_token


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("IPRL_CAE_ENVIRONMENT", "local")
    monkeypatch.setenv("IPRL_CAE_AUTH_DEV_TOKENS_ENABLED", "true")
    monkeypatch.setenv("IPRL_CAE_FEATURES__WORKER_ERP_IMPORT", "true")
    monkeypatch.setenv("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(tmp_path / "documents"))
    monkeypatch.setenv("IPRL_CAE_MAX_UPLOAD_BYTES", str(1024 * 1024))
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with TestingSessionLocal() as session:
        system_tenant = Tenant(name="System Test Tenant", tax_id="SYSTEM-TEST", status="active")
        session.add(system_tenant)
        session.flush()
        system_role = Role(
            tenant_id=system_tenant.id,
            name="system_admin",
            permissions=["system.admin", "tenant.admin"],
        )
        session.add(system_role)
        session.flush()
        system_user = User(
            tenant_id=system_tenant.id,
            email="system-admin@example.invalid",
            name="System Admin",
            password_hash=hash_password("DemoPassword123!"),
            role_id=system_role.id,
            status="active",
            email_verified_at=datetime.now(timezone.utc),
        )
        session.add(system_user)
        session.flush()
        system_tenant_id = system_tenant.id
        system_user_id = system_user.id
        for item in default_platform_catalog():
            platform = ExternalPlatform(
                platform_key=item.platform_key,
                name=item.name,
                status=item.status,
                is_commercial=item.is_commercial,
                notes=item.notes,
            )
            session.add(platform)
            session.flush()
            for method in item.methods:
                session.add(
                    PlatformConnectionMethod(
                        external_platform_id=platform.id,
                        method_key=method.method_key,
                        connector_type=method.connector_type,
                        connector_key=method.connector_key,
                        status=method.status,
                        implemented=method.implemented,
                        dry_run_supported=method.dry_run_supported,
                        manual_approval_required=method.manual_approval_required,
                        notes=method.notes,
                    )
                )
        session.commit()

    def override_get_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        def auth_headers_for_user(tenant_id: int, user_id: int) -> dict[str, str]:
            with TestingSessionLocal() as session:
                user = session.get(User, user_id)
                if user is None or user.tenant_id != tenant_id:
                    raise AssertionError(f"Cannot issue test token for tenant={tenant_id} user={user_id}")
                token = create_local_access_token(user=user, tenant_id=tenant_id, settings=get_settings())
                return {
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-ID": str(tenant_id),
                }

        def system_auth_headers() -> dict[str, str]:
            return auth_headers_for_user(system_tenant_id, system_user_id)

        setattr(test_client, "auth_headers_for_user", auth_headers_for_user)
        setattr(test_client, "system_auth_headers", system_auth_headers)
        yield test_client
    get_settings.cache_clear()
