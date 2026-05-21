from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.schemas import ExternalDocumentStatusRead, PlatformAuthorizationDashboardRead
from app.services.access_control import require_tenant_wide_access
from app.services.platform_external_statuses import list_external_document_statuses
from app.services.platform_authorizations import build_authorization_dashboard

router = APIRouter(prefix="/platform-authorizations", tags=["platform-authorizations"])


@router.get("/dashboard", response_model=PlatformAuthorizationDashboardRead)
def get_platform_authorization_dashboard(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
    priority_group: str = Query(default="arm_first_priority"),
) -> dict[str, object]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    try:
        return build_authorization_dashboard(
            session,
            tenant_id=tenant_id,
            company_id=company_id,
            priority_group=priority_group,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/external-statuses", response_model=list[ExternalDocumentStatusRead])
def get_platform_authorization_external_statuses(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
    platform_slug: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list_external_document_statuses(
        session,
        tenant_id=tenant_id,
        company_id=company_id,
        platform_slug=platform_slug,
        limit=limit,
    )
