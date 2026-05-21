from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, Document, DocumentIntake, DocumentVersion, Worker
from app.services.audit import public_state, record_audit


@dataclass
class CompanyDocumentApprovalResult:
    tenant_id: int
    company_id: int
    documents_approved: int = 0
    versions_reviewed: int = 0
    intakes_accepted: int = 0


def approve_company_imported_documents(
    session: Session,
    *,
    tenant_id: int,
    company_tax_id: str,
    actor_user_id: int | None,
    review_comment: str,
) -> CompanyDocumentApprovalResult:
    company = session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.tax_id == company_tax_id)
    )
    if company is None:
        raise ValueError("Company not found.")

    worker_ids = set(
        session.scalars(
            select(Worker.id).where(Worker.tenant_id == tenant_id, Worker.company_id == company.id)
        )
    )
    result = CompanyDocumentApprovalResult(tenant_id=tenant_id, company_id=company.id)
    documents = list(
        session.scalars(
            select(Document).where(
                Document.tenant_id == tenant_id,
                (
                    (Document.entity_type == "company") & (Document.entity_id == company.id)
                    | ((Document.entity_type == "worker") & (Document.entity_id.in_(worker_ids)))
                ),
            )
        )
    )
    version_ids: set[int] = set()
    for document in documents:
        if document.current_version_id is not None:
            version_ids.add(document.current_version_id)
        if document.status_internal != "valid_internal":
            document.status_internal = "valid_internal"
            result.documents_approved += 1

    if version_ids:
        versions = list(
            session.scalars(select(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))
        )
        for version in versions:
            if version.expiry_review_status == "review_required":
                version.expiry_review_status = "reviewed"
                result.versions_reviewed += 1

    intakes = list(
        session.scalars(
            select(DocumentIntake).where(
                DocumentIntake.tenant_id == tenant_id,
                (
                    (DocumentIntake.requested_company_id == company.id)
                    | (DocumentIntake.predicted_company_id == company.id)
                    | (DocumentIntake.requested_worker_id.in_(worker_ids))
                    | (DocumentIntake.predicted_worker_id.in_(worker_ids))
                ),
            )
        )
    )
    reviewed_at = datetime.now(timezone.utc)
    for intake in intakes:
        if intake.status != "accepted":
            result.intakes_accepted += 1
        intake.status = "accepted"
        intake.review_comment = review_comment
        intake.reviewed_at = reviewed_at
        intake.signals_json = {
            **(intake.signals_json or {}),
            "review_state": "accepted_by_user_instruction",
        }

    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="company_prl_archive.approve_imported_documents",
        entity_type="company",
        entity_id=company.id,
        after=public_state(
            {
                "company_tax_id": company_tax_id,
                "documents_approved": result.documents_approved,
                "versions_reviewed": result.versions_reviewed,
                "intakes_accepted": result.intakes_accepted,
            }
        ),
    )
    session.flush()
    return result
