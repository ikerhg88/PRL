from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.companies import router as companies_router
from app.api.dashboard import router as dashboard_router
from app.api.document_intake import router as document_intake_router
from app.api.documents import router as documents_router
from app.api.documents import types_router as document_types_router
from app.api.exchange import router as exchange_router
from app.api.health import router as health_router
from app.api.platforms import router as platforms_router
from app.api.platforms import tenant_router as tenant_platforms_router
from app.api.platform_authorizations import router as platform_authorizations_router
from app.api.platform_maps import router as platform_maps_router
from app.api.platform_contracts import router as platform_contracts_router
from app.api.platform_review_schedules import router as platform_review_schedules_router
from app.api.requirements import router as requirements_router
from app.api.rpa_gateway import router as rpa_gateway_router
from app.api.saas import router as saas_router
from app.api.sso import router as sso_router
from app.api.system import router as system_router
from app.api.tenants import router as tenants_router
from app.api.transfers import router as transfers_router
from app.api.users import router as users_router
from app.api.work_centers import router as work_centers_router
from app.api.workers import router as workers_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(tenants_router, prefix=settings.api_prefix)
    app.include_router(saas_router, prefix=settings.api_prefix)
    app.include_router(sso_router, prefix=settings.api_prefix)
    app.include_router(users_router, prefix=settings.api_prefix)
    app.include_router(companies_router, prefix=settings.api_prefix)
    app.include_router(work_centers_router, prefix=settings.api_prefix)
    app.include_router(workers_router, prefix=settings.api_prefix)
    app.include_router(document_intake_router, prefix=settings.api_prefix)
    app.include_router(document_types_router, prefix=settings.api_prefix)
    app.include_router(documents_router, prefix=settings.api_prefix)
    app.include_router(requirements_router, prefix=settings.api_prefix)
    app.include_router(platforms_router, prefix=settings.api_prefix)
    app.include_router(tenant_platforms_router, prefix=settings.api_prefix)
    app.include_router(platform_maps_router, prefix=settings.api_prefix)
    app.include_router(platform_contracts_router, prefix=settings.api_prefix)
    app.include_router(platform_authorizations_router, prefix=settings.api_prefix)
    app.include_router(platform_review_schedules_router, prefix=settings.api_prefix)
    app.include_router(rpa_gateway_router, prefix=settings.api_prefix)
    app.include_router(exchange_router, prefix=settings.api_prefix)
    app.include_router(system_router, prefix=settings.api_prefix)
    app.include_router(transfers_router, prefix=settings.api_prefix)
    app.include_router(audit_router, prefix=settings.api_prefix)
    app.include_router(dashboard_router, prefix=settings.api_prefix)

    return app


app = create_app()
