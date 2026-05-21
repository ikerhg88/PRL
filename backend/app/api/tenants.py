from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.dependencies import ActorUserId, DbSession, TenantId
from app.db.models import Tenant
from app.schemas import TenantCreate, TenantRead
from app.services.access_control import require_system_admin_access
from app.services.audit import public_state, record_audit

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantRead])
def list_tenants(tenant_id: TenantId, session: DbSession, actor_user_id: ActorUserId) -> list[Tenant]:
    require_system_admin_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list(session.scalars(select(Tenant).order_by(Tenant.id)))


@router.post("", response_model=TenantRead, status_code=201)
def create_tenant(
    payload: TenantCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Tenant:
    require_system_admin_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    tenant = Tenant(name=payload.name, tax_id=payload.tax_id, status="active")
    session.add(tenant)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        action="tenant.create",
        entity_type="tenant",
        entity_id=tenant.id,
        after=public_state({"id": tenant.id, "name": tenant.name, "tax_id": tenant.tax_id}),
    )
    session.commit()
    session.refresh(tenant)
    return tenant
