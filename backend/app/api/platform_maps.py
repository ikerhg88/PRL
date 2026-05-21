from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import (
    Company,
    ExternalPlatform,
    PlatformAccount,
    PlatformDiscoveredLabel,
    PlatformStructureSnapshot,
)
from app.schemas import (
    PlatformDiscoveredLabelRead,
    PlatformDiscoveredLabelUpdate,
    PlatformDataCoverageRead,
    PlatformEditMethodsRead,
    PlatformLabelComparisonItem,
    PlatformLabelComparisonRead,
    PlatformStandardLabelRead,
    PlatformStructureSnapshotCreate,
    PlatformStructureSnapshotRead,
)
from app.services.access_control import require_tenant_wide_access
from app.services.audit import public_state, record_audit
from app.services.platform_mapping import (
    STANDARD_LABELS_BY_KEY,
    extract_labels_from_capture,
    standard_label_payloads,
)
from app.services.platform_data_coverage import build_platform_data_coverage
from app.services.platform_edit_methods import build_platform_edit_methods
from app.services.platform_validation_surfaces import build_validation_surface_map

router = APIRouter(prefix="/platform-maps", tags=["platform-maps"])
PROJECT_ROOT = Path(__file__).resolve().parents[3]


@router.get("/standard-labels", response_model=list[PlatformStandardLabelRead])
def list_standard_labels() -> list[dict[str, str]]:
    return standard_label_payloads()


@router.get("/snapshots", response_model=list[PlatformStructureSnapshotRead])
def list_structure_snapshots(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    external_platform_id: int | None = Query(default=None),
    platform_account_id: int | None = Query(default=None),
) -> list[PlatformStructureSnapshot]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    statement = select(PlatformStructureSnapshot).where(PlatformStructureSnapshot.tenant_id == tenant_id)
    if external_platform_id is not None:
        statement = statement.where(PlatformStructureSnapshot.external_platform_id == external_platform_id)
    if platform_account_id is not None:
        statement = statement.where(PlatformStructureSnapshot.platform_account_id == platform_account_id)
    return list(session.scalars(statement.order_by(PlatformStructureSnapshot.id.desc())))


@router.post("/snapshots", response_model=PlatformStructureSnapshotRead, status_code=201)
def create_structure_snapshot(
    payload: PlatformStructureSnapshotCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> PlatformStructureSnapshot:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    _validate_snapshot_refs(session, tenant_id=tenant_id, payload=payload)
    structure = payload.structure_json or {}
    summary = payload.summary_json or _summary_from_capture(structure)
    snapshot = PlatformStructureSnapshot(
        tenant_id=tenant_id,
        external_platform_id=payload.external_platform_id,
        platform_account_id=payload.platform_account_id,
        company_id=payload.company_id,
        platform_label=payload.platform_label,
        host=payload.host or _host_from_capture(structure),
        login_status=payload.login_status or _login_status_from_capture(structure),
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        status="mapped",
        structure_json=structure,
        summary_json=summary,
        created_by=actor_user_id,
    )
    session.add(snapshot)
    session.flush()
    labels = extract_labels_from_capture(structure)
    for item in labels:
        session.add(
            PlatformDiscoveredLabel(
                tenant_id=tenant_id,
                snapshot_id=snapshot.id,
                external_platform_id=payload.external_platform_id,
                platform_account_id=payload.platform_account_id,
                company_id=payload.company_id,
                label_kind=item.label_kind,
                raw_label=item.raw_label,
                normalized_label=item.normalized_label,
                page_label=item.page_label,
                entity_scope=item.entity_scope,
                standard_key=item.standard_key,
                confidence=item.confidence,
                review_status="proposed" if item.standard_key else "needs_review",
                metadata_json=item.metadata,
            )
        )
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_structure.snapshot_create",
        entity_type="platform_structure_snapshot",
        entity_id=snapshot.id,
        after=public_state(
            {
                "id": snapshot.id,
                "platform_label": snapshot.platform_label,
                "host": snapshot.host,
                "login_status": snapshot.login_status,
                "label_count": len(labels),
                "source_type": snapshot.source_type,
            }
        ),
    )
    session.commit()
    session.refresh(snapshot)
    return snapshot


@router.get("/labels", response_model=list[PlatformDiscoveredLabelRead])
def list_discovered_labels(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    external_platform_id: int | None = Query(default=None),
    snapshot_id: int | None = Query(default=None),
    standard_key: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
) -> list[PlatformDiscoveredLabel]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    statement = select(PlatformDiscoveredLabel).where(PlatformDiscoveredLabel.tenant_id == tenant_id)
    if external_platform_id is not None:
        statement = statement.where(PlatformDiscoveredLabel.external_platform_id == external_platform_id)
    if snapshot_id is not None:
        statement = statement.where(PlatformDiscoveredLabel.snapshot_id == snapshot_id)
    if standard_key is not None:
        statement = statement.where(PlatformDiscoveredLabel.standard_key == standard_key)
    if review_status is not None:
        statement = statement.where(PlatformDiscoveredLabel.review_status == review_status)
    return list(
        session.scalars(
            statement.order_by(
                PlatformDiscoveredLabel.standard_key.is_(None),
                PlatformDiscoveredLabel.standard_key,
                PlatformDiscoveredLabel.raw_label,
            )
        )
    )


@router.patch("/labels/{label_id}", response_model=PlatformDiscoveredLabelRead)
def update_discovered_label(
    label_id: int,
    payload: PlatformDiscoveredLabelUpdate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> PlatformDiscoveredLabel:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    label = session.scalar(
        select(PlatformDiscoveredLabel).where(
            PlatformDiscoveredLabel.tenant_id == tenant_id,
            PlatformDiscoveredLabel.id == label_id,
        )
    )
    if label is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discovered label not found.")
    if payload.standard_key is not None and payload.standard_key not in STANDARD_LABELS_BY_KEY:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown standard_key.")
    before = _label_public_state(label)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(label, key, value)
    if payload.standard_key is not None and payload.entity_scope is None:
        label.entity_scope = STANDARD_LABELS_BY_KEY[payload.standard_key].entity_scope
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_structure.label_update",
        entity_type="platform_discovered_label",
        entity_id=label.id,
        before=before,
        after=_label_public_state(label),
    )
    session.commit()
    session.refresh(label)
    return label


@router.get("/compare", response_model=list[PlatformLabelComparisonRead])
def compare_standard_labels(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    standard_key: str | None = Query(default=None),
) -> list[PlatformLabelComparisonRead]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    statement = select(PlatformDiscoveredLabel).where(
        PlatformDiscoveredLabel.tenant_id == tenant_id,
        PlatformDiscoveredLabel.standard_key.is_not(None),
    )
    if standard_key is not None:
        if standard_key not in STANDARD_LABELS_BY_KEY:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown standard_key.")
        statement = statement.where(PlatformDiscoveredLabel.standard_key == standard_key)
    labels = list(session.scalars(statement.order_by(PlatformDiscoveredLabel.standard_key, PlatformDiscoveredLabel.raw_label)))
    if not labels:
        return []
    snapshots = {
        item.id: item
        for item in session.scalars(
            select(PlatformStructureSnapshot).where(
                PlatformStructureSnapshot.tenant_id == tenant_id,
                PlatformStructureSnapshot.id.in_({label.snapshot_id for label in labels}),
            )
        )
    }
    grouped: dict[str, dict[tuple[int | None, int | None, str], list[PlatformDiscoveredLabel]]] = defaultdict(lambda: defaultdict(list))
    for label in labels:
        snapshot = snapshots.get(label.snapshot_id)
        platform_label = snapshot.platform_label if snapshot else "Unknown"
        grouped[str(label.standard_key)][
            (label.external_platform_id, label.platform_account_id, platform_label)
        ].append(label)

    result: list[PlatformLabelComparisonRead] = []
    for key, platform_groups in grouped.items():
        items: list[PlatformLabelComparisonItem] = []
        for (external_platform_id, platform_account_id, platform_label), group_labels in platform_groups.items():
            snapshot = snapshots.get(group_labels[0].snapshot_id)
            items.append(
                PlatformLabelComparisonItem(
                    external_platform_id=external_platform_id,
                    platform_account_id=platform_account_id,
                    platform_label=platform_label,
                    host=snapshot.host if snapshot else None,
                    raw_labels=sorted({item.raw_label for item in group_labels}),
                    label_kinds=sorted({item.label_kind for item in group_labels}),
                    entity_scopes=sorted({item.entity_scope for item in group_labels if item.entity_scope}),
                    review_statuses=sorted({item.review_status for item in group_labels}),
                    count=len(group_labels),
                )
            )
        standard = STANDARD_LABELS_BY_KEY.get(key)
        result.append(
            PlatformLabelComparisonRead(
                standard_key=key,
                standard_label=PlatformStandardLabelRead(**standard.__dict__) if standard else None,
                platform_count=len(items),
                label_count=sum(item.count for item in items),
                items=sorted(items, key=lambda item: item.platform_label.lower()),
            )
        )
    return sorted(result, key=lambda item: item.standard_key)


@router.get("/data-coverage", response_model=PlatformDataCoverageRead)
def platform_data_coverage(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
    priority_group: str = Query(default="all"),
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return build_platform_data_coverage(
        session,
        tenant_id=tenant_id,
        company_id=company_id,
        priority_group=priority_group,
    )


@router.get("/edit-methods", response_model=PlatformEditMethodsRead)
def platform_edit_methods(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
    priority_group: str = Query(default="all"),
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return build_platform_edit_methods(
        session,
        tenant_id=tenant_id,
        company_id=company_id,
        priority_group=priority_group,
    )


@router.get("/validation-surfaces", response_model=dict[str, Any])
def platform_validation_surfaces(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    current_only: bool = Query(default=True),
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return build_validation_surface_map(
        capture_root=PROJECT_ROOT / "artifacts" / "platform-captures",
        current_only=current_only,
    )


def _validate_snapshot_refs(session: DbSession, *, tenant_id: int, payload: PlatformStructureSnapshotCreate) -> None:
    if payload.external_platform_id is not None and session.get(ExternalPlatform, payload.external_platform_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External platform not found.")
    if payload.platform_account_id is not None:
        account = session.scalar(
            select(PlatformAccount).where(
                PlatformAccount.tenant_id == tenant_id,
                PlatformAccount.id == payload.platform_account_id,
            )
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform account not found.")
        if payload.external_platform_id is not None and account.external_platform_id != payload.external_platform_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="platform_account_id does not belong to external_platform_id.",
            )
    if payload.company_id is not None:
        company = session.scalar(select(Company).where(Company.tenant_id == tenant_id, Company.id == payload.company_id))
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")


def _summary_from_capture(structure: dict[str, Any]) -> dict[str, Any]:
    raw_pages = structure.get("pages")
    pages = raw_pages if isinstance(raw_pages, list) else []
    return {
        "page_count": len(pages),
        "host": _host_from_capture(structure),
        "login_status": _login_status_from_capture(structure),
        "captcha_detected": bool((structure.get("outcome") or {}).get("captcha_detected")) if isinstance(structure.get("outcome"), dict) else False,
        "mfa_detected": bool((structure.get("outcome") or {}).get("mfa_detected")) if isinstance(structure.get("outcome"), dict) else False,
    }


def _host_from_capture(structure: dict[str, Any]) -> str | None:
    source = structure.get("source")
    if isinstance(source, dict):
        host = source.get("initial_host")
        if isinstance(host, str) and host:
            return host
    return None


def _login_status_from_capture(structure: dict[str, Any]) -> str | None:
    outcome = structure.get("outcome")
    if isinstance(outcome, dict):
        status_value = outcome.get("login_status")
        if isinstance(status_value, str) and status_value:
            return status_value
    return None


def _label_public_state(label: PlatformDiscoveredLabel) -> dict[str, Any]:
    return public_state(
        {
            "id": label.id,
            "snapshot_id": label.snapshot_id,
            "label_kind": label.label_kind,
            "raw_label": label.raw_label,
            "entity_scope": label.entity_scope,
            "standard_key": label.standard_key,
            "confidence": label.confidence,
            "review_status": label.review_status,
            "notes": label.notes,
        }
    )
