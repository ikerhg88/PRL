from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import (
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformRpaMappingProposal,
)
from app.schemas import (
    PlatformContractImportRead,
    PlatformContractSummaryRead,
    PlatformRpaAccountProposalRead,
    PlatformRpaManifestRead,
    PlatformRpaMappingProposalRead,
    PlatformRpaMappingProposalUpdate,
)
from app.services.access_control import require_tenant_wide_access
from app.services.audit import public_state, record_audit
from app.services.platform_contracts import (
    FIRST_PRIORITY_ARM_SLUGS,
    import_all_arm_contracts,
    import_first_priority_arm_contracts,
    import_pending_review_arm_contracts,
)

router = APIRouter(prefix="/platform-contracts", tags=["platform-contracts"])


@router.post("/import/arm-first-priority", response_model=PlatformContractImportRead)
def import_arm_first_priority_contracts(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    try:
        result = import_first_priority_arm_contracts(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contract bundle not found: {exc}",
        ) from exc
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_contracts.import_arm_first_priority",
        entity_type="platform_rpa_manifest",
        entity_id=None,
        after=public_state(asdict(result)),
    )
    session.commit()
    return asdict(result)


@router.post("/import/arm-pending-review", response_model=PlatformContractImportRead)
def import_arm_pending_review_contracts(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    try:
        result = import_pending_review_arm_contracts(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contract bundle not found: {exc}",
        ) from exc
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_contracts.import_arm_pending_review",
        entity_type="platform_rpa_manifest",
        entity_id=None,
        after=public_state(asdict(result)),
    )
    session.commit()
    return asdict(result)


@router.post("/import/arm-all", response_model=PlatformContractImportRead)
def import_all_arm_platform_contracts(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    try:
        result = import_all_arm_contracts(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contract bundle not found: {exc}",
        ) from exc
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_contracts.import_arm_all",
        entity_type="platform_rpa_manifest",
        entity_id=None,
        after=public_state(asdict(result)),
    )
    session.commit()
    return asdict(result)


@router.get("/summary", response_model=PlatformContractSummaryRead)
def platform_contract_summary(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> PlatformContractSummaryRead:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    manifests = session.scalar(
        select(func.count()).select_from(PlatformRpaManifest).where(PlatformRpaManifest.tenant_id == tenant_id)
    ) or 0
    accounts = session.scalar(
        select(func.count())
        .select_from(PlatformRpaAccountProposal)
        .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
    ) or 0
    mappings = session.scalar(
        select(func.count())
        .select_from(PlatformRpaMappingProposal)
        .where(PlatformRpaMappingProposal.tenant_id == tenant_id)
    ) or 0
    approved_mappings = session.scalar(
        select(func.count())
        .select_from(PlatformRpaMappingProposal)
        .where(
            PlatformRpaMappingProposal.tenant_id == tenant_id,
            PlatformRpaMappingProposal.review_status == "approved",
        )
    ) or 0
    blocked_accounts = session.scalar(
        select(func.count())
        .select_from(PlatformRpaAccountProposal)
        .where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.status == "blocked_pending_host",
        )
    ) or 0
    priority_platforms = list(
        session.scalars(
            select(PlatformRpaManifest.platform_slug)
            .where(PlatformRpaManifest.tenant_id == tenant_id)
            .order_by(PlatformRpaManifest.platform_slug)
        )
    )
    return PlatformContractSummaryRead(
        manifests=manifests,
        accounts=accounts,
        mappings=mappings,
        approved_mappings=approved_mappings,
        pending_mappings=mappings - approved_mappings,
        blocked_accounts=blocked_accounts,
        priority_platforms=priority_platforms,
    )


@router.get("/priority-slugs", response_model=list[str])
def list_priority_slugs() -> list[str]:
    return list(FIRST_PRIORITY_ARM_SLUGS)


@router.get("/manifests", response_model=list[PlatformRpaManifestRead])
def list_rpa_manifests(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    priority_group: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[PlatformRpaManifest]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    statement = select(PlatformRpaManifest).where(PlatformRpaManifest.tenant_id == tenant_id)
    if priority_group is not None:
        statement = statement.where(PlatformRpaManifest.priority_group == priority_group)
    if status_filter is not None:
        statement = statement.where(PlatformRpaManifest.status == status_filter)
    return list(session.scalars(statement.order_by(PlatformRpaManifest.platform_slug)))


@router.get("/accounts", response_model=list[PlatformRpaAccountProposalRead])
def list_rpa_account_proposals(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    manifest_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[PlatformRpaAccountProposal]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    statement = select(PlatformRpaAccountProposal).where(PlatformRpaAccountProposal.tenant_id == tenant_id)
    if manifest_id is not None:
        statement = statement.where(PlatformRpaAccountProposal.manifest_id == manifest_id)
    if status_filter is not None:
        statement = statement.where(PlatformRpaAccountProposal.status == status_filter)
    return list(
        session.scalars(
            statement.order_by(
                PlatformRpaAccountProposal.external_platform_id,
                PlatformRpaAccountProposal.external_company_name,
            )
        )
    )


@router.get("/mappings", response_model=list[PlatformRpaMappingProposalRead])
def list_rpa_mapping_proposals(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    manifest_id: int | None = Query(default=None),
    mapping_kind: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
) -> list[PlatformRpaMappingProposal]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    statement = select(PlatformRpaMappingProposal).where(PlatformRpaMappingProposal.tenant_id == tenant_id)
    if manifest_id is not None:
        statement = statement.where(PlatformRpaMappingProposal.manifest_id == manifest_id)
    if mapping_kind is not None:
        statement = statement.where(PlatformRpaMappingProposal.mapping_kind == mapping_kind)
    if review_status is not None:
        statement = statement.where(PlatformRpaMappingProposal.review_status == review_status)
    return list(
        session.scalars(
            statement.order_by(
                PlatformRpaMappingProposal.mapping_kind,
                PlatformRpaMappingProposal.entity_scope,
                PlatformRpaMappingProposal.iker_key,
            )
        )
    )


@router.patch("/mappings/{mapping_id}", response_model=PlatformRpaMappingProposalRead)
def update_rpa_mapping_proposal(
    mapping_id: int,
    payload: PlatformRpaMappingProposalUpdate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> PlatformRpaMappingProposal:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    mapping = session.scalar(
        select(PlatformRpaMappingProposal).where(
            PlatformRpaMappingProposal.tenant_id == tenant_id,
            PlatformRpaMappingProposal.id == mapping_id,
        )
    )
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RPA mapping proposal not found.")
    before = _mapping_public_state(mapping)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(mapping, key, value)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_contracts.mapping_update",
        entity_type="platform_rpa_mapping_proposal",
        entity_id=mapping.id,
        before=before,
        after=_mapping_public_state(mapping),
    )
    session.commit()
    session.refresh(mapping)
    return mapping


def _mapping_public_state(mapping: PlatformRpaMappingProposal) -> dict[str, Any]:
    return public_state(
        {
            "id": mapping.id,
            "manifest_id": mapping.manifest_id,
            "mapping_kind": mapping.mapping_kind,
            "entity_scope": mapping.entity_scope,
            "iker_key": mapping.iker_key,
            "external_label": mapping.external_label,
            "external_catalog_value": mapping.external_catalog_value,
            "review_status": mapping.review_status,
            "status": mapping.status,
            "notes": mapping.notes,
        }
    )
