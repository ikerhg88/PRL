from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.dependencies import ActorUserId, DbSession, TenantId
from app.db.models import Company, Reseller, SaaSPlan, Tenant, TenantCommercialProfile, User
from app.schemas import (
    ResellerCreate,
    ResellerRead,
    SaaSOverview,
    SaaSPlanCreate,
    SaaSPlanRead,
    TenantCommercialProfileCreate,
    TenantCommercialProfileRead,
)
from app.services.audit import public_state, record_audit
from app.services.access_control import require_system_admin_access

router = APIRouter(prefix="/saas", tags=["saas"])


@router.get("/overview", response_model=SaaSOverview)
def get_saas_overview(tenant_id: TenantId, session: DbSession, actor_user_id: ActorUserId) -> SaaSOverview:
    require_system_admin_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return SaaSOverview(
        tenants=_count(session, select(func.count()).select_from(Tenant)),
        active_tenants=_count(
            session,
            select(func.count()).select_from(Tenant).where(Tenant.status == "active"),
        ),
        resellers=_count(session, select(func.count()).select_from(Reseller)),
        plans=_count(session, select(func.count()).select_from(SaaSPlan)),
        users=_count(session, select(func.count()).select_from(User)),
        companies=_count(session, select(func.count()).select_from(Company)),
        reseller_managed_tenants=_count(
            session,
            select(func.count())
            .select_from(TenantCommercialProfile)
            .where(TenantCommercialProfile.billing_mode == "reseller_managed"),
        ),
    )


@router.get("/plans", response_model=list[SaaSPlanRead])
def list_plans(tenant_id: TenantId, session: DbSession, actor_user_id: ActorUserId) -> list[SaaSPlan]:
    require_system_admin_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list(session.scalars(select(SaaSPlan).order_by(SaaSPlan.plan_key)))


@router.post("/plans", response_model=SaaSPlanRead, status_code=201)
def create_plan(
    payload: SaaSPlanCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> SaaSPlan:
    require_system_admin_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    plan = SaaSPlan(**payload.model_dump())
    session.add(plan)
    session.flush()
    record_audit(
        session,
        tenant_id=None,
        actor_user_id=actor_user_id,
        action="saas_plan.create",
        entity_type="saas_plan",
        entity_id=plan.id,
        after=public_state(payload.model_dump() | {"id": plan.id}),
    )
    session.commit()
    session.refresh(plan)
    return plan


@router.get("/resellers", response_model=list[ResellerRead])
def list_resellers(tenant_id: TenantId, session: DbSession, actor_user_id: ActorUserId) -> list[Reseller]:
    require_system_admin_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list(session.scalars(select(Reseller).order_by(Reseller.name)))


@router.post("/resellers", response_model=ResellerRead, status_code=201)
def create_reseller(
    payload: ResellerCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Reseller:
    require_system_admin_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    reseller = Reseller(**payload.model_dump())
    session.add(reseller)
    session.flush()
    record_audit(
        session,
        tenant_id=None,
        actor_user_id=actor_user_id,
        action="reseller.create",
        entity_type="reseller",
        entity_id=reseller.id,
        after=public_state(payload.model_dump() | {"id": reseller.id}),
    )
    session.commit()
    session.refresh(reseller)
    return reseller


@router.get("/tenant-profiles", response_model=list[TenantCommercialProfileRead])
def list_tenant_profiles(tenant_id: TenantId, session: DbSession, actor_user_id: ActorUserId) -> list[TenantCommercialProfile]:
    require_system_admin_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list(session.scalars(select(TenantCommercialProfile).order_by(TenantCommercialProfile.id)))


@router.post("/tenant-profiles", response_model=TenantCommercialProfileRead, status_code=201)
def upsert_tenant_profile(
    payload: TenantCommercialProfileCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> TenantCommercialProfile:
    require_system_admin_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    tenant = session.get(Tenant, payload.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    if payload.plan_id is not None and session.get(SaaSPlan, payload.plan_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    if payload.reseller_id is not None and session.get(Reseller, payload.reseller_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reseller not found.")
    profile = session.scalar(
        select(TenantCommercialProfile).where(TenantCommercialProfile.tenant_id == payload.tenant_id)
    )
    if profile is None:
        profile = TenantCommercialProfile(**payload.model_dump())
        session.add(profile)
    else:
        profile.plan_id = payload.plan_id
        profile.reseller_id = payload.reseller_id
        profile.billing_mode = payload.billing_mode
        profile.seats_purchased = payload.seats_purchased
        profile.status = payload.status
    session.flush()
    record_audit(
        session,
        tenant_id=payload.tenant_id,
        actor_user_id=actor_user_id,
        action="tenant_commercial_profile.upsert",
        entity_type="tenant_commercial_profile",
        entity_id=profile.id,
        after=public_state(payload.model_dump() | {"id": profile.id}),
    )
    session.commit()
    session.refresh(profile)
    return profile


@router.get("/resellers/{reseller_id}/tenant-profiles", response_model=list[TenantCommercialProfileRead])
def list_reseller_tenant_profiles(
    reseller_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[TenantCommercialProfile]:
    require_system_admin_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    if session.get(Reseller, reseller_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reseller not found.")
    return list(
        session.scalars(
            select(TenantCommercialProfile)
            .where(TenantCommercialProfile.reseller_id == reseller_id)
            .order_by(TenantCommercialProfile.tenant_id)
        )
    )


def _count(session: DbSession, statement: Any) -> int:
    value = session.scalar(statement)
    return int(value or 0)
