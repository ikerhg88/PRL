from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentRequirement, DocumentType, DocumentVersion
from app.schemas import ComplianceItem, ComplianceSummary


def calculate_compliance(
    session: Session,
    *,
    tenant_id: int,
    profile_id: int,
    entity_type: str,
    entity_id: int,
) -> ComplianceSummary:
    requirements = list(
        session.scalars(
            select(DocumentRequirement)
            .where(DocumentRequirement.profile_id == profile_id)
            .where(DocumentRequirement.entity_scope == entity_type)
            .order_by(DocumentRequirement.id)
        )
    )

    items: list[ComplianceItem] = []
    for requirement in requirements:
        document_type = session.get(DocumentType, requirement.document_type_id)
        if document_type is None:
            continue
        document = session.scalar(
            select(Document)
            .where(Document.tenant_id == tenant_id)
            .where(Document.document_type_id == requirement.document_type_id)
            .where(Document.entity_type == entity_type)
            .where(Document.entity_id == entity_id)
        )
        version = None
        status_value = "missing"
        if document is not None and document.current_version_id is not None:
            version = session.get(DocumentVersion, document.current_version_id)
            status_value = _document_status(document, version, requirement.expiration_warning_days)
        elif document is not None:
            status_value = document.status_internal

        items.append(
            ComplianceItem(
                requirement_id=requirement.id,
                document_type_id=requirement.document_type_id,
                document_code=document_type.code,
                document_name=document_type.name,
                status=status_value,
                blocks_access=requirement.blocks_access,
                document_id=document.id if document is not None else None,
                document_version_id=version.id if version is not None else None,
                expires_at=version.expires_at if version is not None else None,
            )
        )

    counters = {
        "missing_count": sum(1 for item in items if item.status == "missing"),
        "expired_count": sum(1 for item in items if item.status == "expired"),
        "rejected_count": sum(1 for item in items if item.status == "rejected_internal"),
        "expiring_soon_count": sum(1 for item in items if item.status == "expiring_soon"),
        "valid_count": sum(1 for item in items if item.status == "valid_internal"),
    }
    overall_status = _overall_status(items)
    return ComplianceSummary(
        entity_type=entity_type,
        entity_id=entity_id,
        profile_id=profile_id,
        overall_status=overall_status,
        items=items,
        **counters,
    )


def _document_status(
    document: Document,
    version: DocumentVersion | None,
    expiration_warning_days: int,
) -> str:
    if document.status_internal == "rejected_internal":
        return "rejected_internal"
    if version is None:
        return document.status_internal
    today = date.today()
    if version.expires_at is not None and version.expires_at < today:
        return "expired"
    if (
        version.expires_at is not None
        and version.expires_at <= today + timedelta(days=expiration_warning_days)
    ):
        return "expiring_soon"
    if document.status_internal in {"draft", "pending_internal_review"}:
        return document.status_internal
    return "valid_internal"


def _overall_status(items: list[ComplianceItem]) -> str:
    blocking = [item for item in items if item.blocks_access]
    if any(item.status in {"missing", "expired", "rejected_internal"} for item in blocking):
        return "blocked"
    if any(item.status == "expiring_soon" for item in items):
        return "warning"
    if any(item.status in {"draft", "pending_internal_review"} for item in items):
        return "pending_review"
    return "compliant"
