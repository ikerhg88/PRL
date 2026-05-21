from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import AuditLog
from app.schemas import AuditLogRead
from app.services.access_control import require_tenant_wide_access

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogRead])
def list_audit(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    limit: int = 100,
) -> list[AuditLog]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.id.desc())
            .limit(min(limit, 500))
        )
    )
