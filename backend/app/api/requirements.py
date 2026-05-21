from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import DocumentRequirement, RequirementProfile, Worker
from app.schemas import (
    ComplianceSummary,
    DocumentRequirementCreate,
    DocumentRequirementRead,
    RequirementProfileCreate,
    RequirementProfileRead,
)
from app.services.audit import public_state, record_audit
from app.services.access_control import require_company_permission, require_tenant_wide_access
from app.services.compliance import calculate_compliance

router = APIRouter(prefix="/requirements", tags=["requirements"])


@router.get("/profiles", response_model=list[RequirementProfileRead])
def list_profiles(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[RequirementProfile]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list(
        session.scalars(
            select(RequirementProfile)
            .where(RequirementProfile.tenant_id == tenant_id)
            .order_by(RequirementProfile.id)
        )
    )


@router.post("/profiles", response_model=RequirementProfileRead, status_code=201)
def create_profile(
    payload: RequirementProfileCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> RequirementProfile:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    profile = RequirementProfile(tenant_id=tenant_id, **payload.model_dump())
    session.add(profile)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="requirement_profile.create",
        entity_type="requirement_profile",
        entity_id=profile.id,
        after=public_state(payload.model_dump() | {"id": profile.id}),
    )
    session.commit()
    session.refresh(profile)
    return profile


@router.post(
    "/profiles/{profile_id}/requirements",
    response_model=DocumentRequirementRead,
    status_code=201,
)
def add_requirement(
    profile_id: int,
    payload: DocumentRequirementCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> DocumentRequirement:
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    profile = session.scalar(
        select(RequirementProfile).where(
            RequirementProfile.tenant_id == tenant_id,
            RequirementProfile.id == profile_id,
        )
    )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement profile not found.")
    requirement = DocumentRequirement(profile_id=profile_id, **payload.model_dump())
    session.add(requirement)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="document_requirement.create",
        entity_type="document_requirement",
        entity_id=requirement.id,
        after=public_state(payload.model_dump() | {"id": requirement.id, "profile_id": profile_id}),
    )
    session.commit()
    session.refresh(requirement)
    return requirement


@router.get(
    "/profiles/{profile_id}/requirements",
    response_model=list[DocumentRequirementRead],
)
def list_requirements(
    profile_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[DocumentRequirement]:
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    profile = session.scalar(
        select(RequirementProfile).where(
            RequirementProfile.tenant_id == tenant_id,
            RequirementProfile.id == profile_id,
        )
    )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement profile not found.")
    return list(
        session.scalars(
            select(DocumentRequirement)
            .where(DocumentRequirement.profile_id == profile_id)
            .order_by(DocumentRequirement.id)
        )
    )


@router.get(
    "/profiles/{profile_id}/compliance/{entity_type}/{entity_id}",
    response_model=ComplianceSummary,
)
def get_compliance(
    profile_id: int,
    entity_type: str,
    entity_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> ComplianceSummary:
    profile = session.scalar(
        select(RequirementProfile).where(
            RequirementProfile.tenant_id == tenant_id,
            RequirementProfile.id == profile_id,
        )
    )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement profile not found.")
    _require_entity_access(session, tenant_id, actor_user_id, entity_type, entity_id)
    return calculate_compliance(
        session,
        tenant_id=tenant_id,
        profile_id=profile_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )


def _require_entity_access(
    session: DbSession,
    tenant_id: int,
    actor_user_id: int | None,
    entity_type: str,
    entity_id: int,
) -> None:
    if entity_type == "company":
        require_company_permission(
            session,
            tenant_id=tenant_id,
            user_id=actor_user_id,
            company_id=entity_id,
            permission="requirement.read",
        )
        return
    if entity_type == "worker":
        worker = session.scalar(select(Worker).where(Worker.tenant_id == tenant_id, Worker.id == entity_id))
        if worker is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found.")
        require_company_permission(
            session,
            tenant_id=tenant_id,
            user_id=actor_user_id,
            company_id=worker.company_id,
            permission="requirement.read",
        )
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Entity access denied.")
