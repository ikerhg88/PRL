from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import Company
from app.schemas import CompanyCreate, CompanyRead, CompanyUpdate
from app.services.audit import public_state, record_audit
from app.services.access_control import (
    accessible_company_ids,
    require_company_access,
    require_company_permission,
    require_tenant_wide_access,
)

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[CompanyRead])
def list_companies(tenant_id: TenantId, session: DbSession, actor_user_id: ActorUserId) -> list[Company]:
    require_tenant(session, tenant_id)
    statement = select(Company).where(Company.tenant_id == tenant_id)
    allowed_company_ids = accessible_company_ids(session, tenant_id=tenant_id, user_id=actor_user_id)
    if allowed_company_ids is not None:
        statement = statement.where(Company.id.in_(allowed_company_ids))
    return list(session.scalars(statement.order_by(Company.id)))


@router.post("", response_model=CompanyRead, status_code=201)
def create_company(
    payload: CompanyCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Company:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    company = Company(tenant_id=tenant_id, **payload.model_dump())
    session.add(company)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="company.create",
        entity_type="company",
        entity_id=company.id,
        after=public_state(payload.model_dump() | {"id": company.id}),
    )
    session.commit()
    session.refresh(company)
    return company


@router.get("/{company_id}", response_model=CompanyRead)
def get_company(
    company_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Company:
    require_company_permission(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        company_id=company_id,
        permission="company.write",
    )
    company = session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.id == company_id)
    )
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
    return company


@router.put("/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Company:
    require_company_access(session, tenant_id=tenant_id, user_id=actor_user_id, company_id=company_id)
    company = session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.id == company_id)
    )
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
    before = public_state(
        {
            "name": company.name,
            "tax_id": company.tax_id,
            "company_type": company.company_type,
            "address": company.address,
            "status": company.status,
        }
    )
    for key, value in payload.model_dump().items():
        setattr(company, key, value)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="company.update",
        entity_type="company",
        entity_id=company.id,
        before=before,
        after=public_state(payload.model_dump() | {"id": company.id}),
    )
    session.commit()
    session.refresh(company)
    return company
