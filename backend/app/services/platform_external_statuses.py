from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import (
    Company,
    Document,
    DocumentType,
    DocumentVersion,
    ExternalDocumentStatus,
    ExternalPlatform,
    Worker,
)


@dataclass(frozen=True)
class ExternalStatusObservation:
    document_version_id: int
    status: str
    external_comment: str | None = None
    external_document_id: str | None = None
    external_requirement_id: str | None = None


def persist_external_status_observations(
    session: Session,
    *,
    tenant_id: int,
    external_platform_id: int,
    observations: list[ExternalStatusObservation],
) -> list[ExternalDocumentStatus]:
    persisted: list[ExternalDocumentStatus] = []
    checked_at = datetime.now(timezone.utc)
    for observation in observations:
        version = session.get(DocumentVersion, observation.document_version_id)
        if version is None:
            continue
        document = session.get(Document, version.document_id)
        if document is None or document.tenant_id != tenant_id:
            continue
        status = ExternalDocumentStatus(
            tenant_id=tenant_id,
            external_platform_id=external_platform_id,
            document_version_id=version.id,
            external_document_id=_clean_optional(observation.external_document_id, 160),
            external_requirement_id=_clean_optional(observation.external_requirement_id, 160),
            status=normalize_external_status(observation.status),
            external_comment=_clean_optional(observation.external_comment, 500),
            last_checked_at=checked_at,
        )
        session.add(status)
        persisted.append(status)
    if persisted:
        session.flush()
    return persisted


def observations_from_payload(payload: Any) -> list[ExternalStatusObservation]:
    if not isinstance(payload, list):
        return []
    observations: list[ExternalStatusObservation] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        version_id = item.get("document_version_id")
        status = item.get("status")
        if not isinstance(version_id, int) or not isinstance(status, str) or not status.strip():
            continue
        observations.append(
            ExternalStatusObservation(
                document_version_id=version_id,
                status=status,
                external_comment=item.get("external_comment") if isinstance(item.get("external_comment"), str) else None,
                external_document_id=item.get("external_document_id") if isinstance(item.get("external_document_id"), str) else None,
                external_requirement_id=item.get("external_requirement_id") if isinstance(item.get("external_requirement_id"), str) else None,
            )
        )
    return observations


def list_external_document_statuses(
    session: Session,
    *,
    tenant_id: int,
    company_id: int | None = None,
    platform_slug: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    statement = (
        select(
            ExternalDocumentStatus,
            ExternalPlatform,
            DocumentVersion,
            Document,
            DocumentType,
        )
        .join(ExternalPlatform, ExternalPlatform.id == ExternalDocumentStatus.external_platform_id)
        .join(DocumentVersion, DocumentVersion.id == ExternalDocumentStatus.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(DocumentType, DocumentType.id == Document.document_type_id)
        .where(ExternalDocumentStatus.tenant_id == tenant_id, Document.tenant_id == tenant_id)
    )
    if company_id is not None:
        statement = statement.where(_documents_for_company_ids(tenant_id, [company_id]))
    if platform_slug:
        statement = statement.where(ExternalPlatform.platform_key == platform_slug)
    rows = session.execute(
        statement.order_by(ExternalDocumentStatus.last_checked_at.desc(), ExternalDocumentStatus.id.desc()).limit(limit)
    ).all()
    entity_names = _entity_names(
        session,
        tenant_id=tenant_id,
        documents=[row[3] for row in rows],
    )
    result: list[dict[str, Any]] = []
    for external_status, platform, version, document, document_type in rows:
        result.append(
            {
                "id": external_status.id,
                "tenant_id": external_status.tenant_id,
                "external_platform_id": platform.id,
                "platform_key": platform.platform_key,
                "platform_name": platform.name,
                "document_id": document.id,
                "document_version_id": version.id,
                "document_type_code": document_type.code,
                "document_type_name": document_type.name,
                "entity_type": document.entity_type,
                "entity_id": document.entity_id,
                "entity_name": entity_names.get((document.entity_type, document.entity_id)),
                "status": external_status.status,
                "status_color": external_status_color(external_status.status),
                "external_comment": external_status.external_comment,
                "external_document_id": external_status.external_document_id,
                "external_requirement_id": external_status.external_requirement_id,
                "last_checked_at": external_status.last_checked_at,
            }
        )
    return result


def normalize_external_status(status: str) -> str:
    lowered = " ".join(status.strip().lower().split())
    if not lowered:
        return "unknown"
    if any(term in lowered for term in ("validado", "validada", "aceptado", "aceptada", "accepted", "valid", "ok")):
        return "accepted"
    if any(term in lowered for term in ("rechaz", "no conforme", "rejected")):
        return "rejected"
    if any(term in lowered for term in ("caduc", "expired")):
        return "expired_external"
    if any(term in lowered for term in ("revision", "revisión", "enviado", "subido", "submitted", "pending")):
        return "pending_external_validation"
    if any(term in lowered for term in ("no requerido", "no requerida", "no aplica", "not required")):
        return "not_applicable"
    if any(term in lowered for term in ("pendiente", "requerido", "incompleto", "missing", "required")):
        return "manual_required"
    if "bloqueado" in lowered or "blocked" in lowered:
        return "blocked_by_platform"
    return lowered.replace(" ", "_")[:80]


def external_status_color(status: str) -> str:
    normalized = normalize_external_status(status)
    if normalized in {"accepted", "accepted_with_warnings", "not_applicable"}:
        return "green"
    if normalized in {"rejected", "expired_external", "blocked_by_platform"}:
        return "red"
    return "orange"


def _entity_names(
    session: Session,
    *,
    tenant_id: int,
    documents: list[Document],
) -> dict[tuple[str, int], str]:
    result: dict[tuple[str, int], str] = {}
    company_ids = {document.entity_id for document in documents if document.entity_type == "company"}
    worker_ids = {document.entity_id for document in documents if document.entity_type == "worker"}
    if company_ids:
        for company in session.scalars(
            select(Company).where(Company.tenant_id == tenant_id, Company.id.in_(company_ids))
        ):
            result[("company", company.id)] = company.name
    if worker_ids:
        for worker in session.scalars(
            select(Worker).where(Worker.tenant_id == tenant_id, Worker.id.in_(worker_ids))
        ):
            result[("worker", worker.id)] = f"{worker.first_name} {worker.last_name}"
    return result


def _documents_for_company_ids(tenant_id: int, company_ids: list[int]) -> ColumnElement[bool]:
    if not company_ids:
        return false()
    worker_ids = select(Worker.id).where(
        Worker.tenant_id == tenant_id,
        Worker.company_id.in_(company_ids),
    )
    return or_(
        and_(Document.entity_type == "company", Document.entity_id.in_(company_ids)),
        and_(Document.entity_type == "worker", Document.entity_id.in_(worker_ids)),
    )


def _clean_optional(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned[:max_length] or None
