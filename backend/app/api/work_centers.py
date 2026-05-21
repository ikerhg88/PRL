from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import WorkCenter
from app.schemas import WorkCenterCreate, WorkCenterRead
from app.services.audit import public_state, record_audit
from app.services.access_control import accessible_company_ids_for_permission, require_company_permission

router = APIRouter(prefix="/work-centers", tags=["work-centers"])


@router.get("", response_model=list[WorkCenterRead])
def list_work_centers(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
) -> list[WorkCenter]:
    require_tenant(session, tenant_id)
    statement = select(WorkCenter).where(WorkCenter.tenant_id == tenant_id)
    if company_id is not None:
        require_company_permission(
            session,
            tenant_id=tenant_id,
            user_id=actor_user_id,
            company_id=company_id,
            permission="company.read",
        )
        statement = statement.where(WorkCenter.company_id == company_id)
    else:
        allowed_company_ids = accessible_company_ids_for_permission(
            session,
            tenant_id=tenant_id,
            user_id=actor_user_id,
            permission="company.read",
        )
        if allowed_company_ids is not None:
            statement = statement.where(WorkCenter.company_id.in_(allowed_company_ids))
    return list(session.scalars(statement.order_by(WorkCenter.id)))


@router.post("", response_model=WorkCenterRead, status_code=201)
def create_work_center(
    payload: WorkCenterCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> WorkCenter:
    require_tenant(session, tenant_id)
    require_company_permission(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        company_id=payload.company_id,
        permission="company.write",
    )
    work_center = WorkCenter(tenant_id=tenant_id, **payload.model_dump())
    session.add(work_center)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="work_center.create",
        entity_type="work_center",
        entity_id=work_center.id,
        after=public_state(payload.model_dump() | {"id": work_center.id}),
    )
    session.commit()
    session.refresh(work_center)
    return work_center
