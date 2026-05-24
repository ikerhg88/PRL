from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.schemas import (
    PlatformObservedDocumentRequestRead,
    PlatformObservedEntityRead,
    PlatformObservedStateSummaryRead,
)
from app.services.access_control import require_tenant_wide_access
from app.services.platform_observations import (
    build_observed_state_summary,
    list_observed_document_requests,
    list_observed_entities,
)
from app.services.platform_reconciliation import build_platform_reconciliation_map

router = APIRouter(prefix="/platform-observations", tags=["platform-observations"])


@router.get("/summary", response_model=PlatformObservedStateSummaryRead)
def get_observed_state_summary(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    account_proposal_id: int | None = Query(default=None),
) -> dict[str, object]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return build_observed_state_summary(
        session,
        tenant_id=tenant_id,
        account_proposal_id=account_proposal_id,
    )


@router.get("/operational-map", response_model=dict[str, object])
def get_platform_operational_map(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
    priority_group: str = Query(default="all"),
) -> dict[str, object]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return build_platform_reconciliation_map(
        session,
        tenant_id=tenant_id,
        company_id=company_id,
        priority_group=priority_group,
    )


@router.get("/entities", response_model=list[PlatformObservedEntityRead])
def get_observed_entities(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    account_proposal_id: int | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    external_status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict[str, object]]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list_observed_entities(
        session,
        tenant_id=tenant_id,
        account_proposal_id=account_proposal_id,
        entity_type=entity_type,
        external_status=external_status,
        limit=limit,
    )


@router.get("/document-requests", response_model=list[PlatformObservedDocumentRequestRead])
def get_observed_document_requests(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    account_proposal_id: int | None = Query(default=None),
    entity_scope: str | None = Query(default=None),
    external_status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    only_actionable: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict[str, object]]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list_observed_document_requests(
        session,
        tenant_id=tenant_id,
        account_proposal_id=account_proposal_id,
        entity_scope=entity_scope,
        external_status=external_status,
        severity=severity,
        only_actionable=only_actionable,
        limit=limit,
    )
