from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import Company, Document, DocumentVersion, ExternalPlatform, TransferJob, Worker
from app.schemas import CompanyDashboardSummary, DashboardSummary
from app.services.access_control import accessible_company_ids, require_company_access

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
) -> DashboardSummary:
    require_tenant(session, tenant_id)
    today = date.today()
    soon = today + timedelta(days=30)
    if company_id is not None:
        require_company_access(session, tenant_id=tenant_id, user_id=actor_user_id, company_id=company_id)
        scoped_company_ids: list[int] | None = [company_id]
    else:
        scoped_company_ids = accessible_company_ids(session, tenant_id=tenant_id, user_id=actor_user_id)
    company_filter = _company_filter(Company.id, scoped_company_ids)
    worker_company_filter = _company_filter(Worker.company_id, scoped_company_ids)
    document_company_filter = _company_document_filter(tenant_id, scoped_company_ids)
    return DashboardSummary(
        tenant_id=tenant_id,
        company_id=company_id,
        companies=_count(
            session,
            select(func.count()).select_from(Company).where(
                Company.tenant_id == tenant_id,
                *company_filter,
            ),
        ),
        workers=_count(
            session,
            select(func.count()).select_from(Worker).where(
                Worker.tenant_id == tenant_id,
                Worker.status != "deleted",
                *worker_company_filter,
            ),
        ),
        documents=_count(
            session,
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                *document_company_filter,
            ),
        ),
        valid_documents=_count(
            session,
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.status_internal == "valid_internal",
                *document_company_filter,
            ),
        ),
        expired_documents=_count(
            session,
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.status_internal == "expired",
                *document_company_filter,
            ),
        ),
        expiring_soon_documents=_count(
            session,
            select(func.count()).select_from(DocumentVersion).join(
                Document,
                Document.current_version_id == DocumentVersion.id,
            ).where(
                Document.tenant_id == tenant_id,
                *document_company_filter,
                DocumentVersion.expires_at.is_not(None),
                DocumentVersion.expires_at >= today,
                DocumentVersion.expires_at <= soon,
            ),
        ),
        pending_transfer_jobs=_count(
            session,
            select(func.count()).select_from(TransferJob).where(
                TransferJob.tenant_id == tenant_id,
                TransferJob.status.in_(["created", "queued", "running", "approval_pending"]),
            ),
        ),
        failed_transfer_jobs=_count(
            session,
            select(func.count()).select_from(TransferJob).where(
                TransferJob.tenant_id == tenant_id,
                TransferJob.status == "failed",
            ),
        ),
        platforms_cataloged=_count(
            session,
            select(func.count()).select_from(ExternalPlatform).where(ExternalPlatform.status != "removed"),
        ),
    )


@router.get("/companies", response_model=list[CompanyDashboardSummary])
def get_company_summaries(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[CompanyDashboardSummary]:
    require_tenant(session, tenant_id)
    today = date.today()
    soon = today + timedelta(days=30)
    allowed_company_ids = accessible_company_ids(session, tenant_id=tenant_id, user_id=actor_user_id)
    company_filter = _company_filter(Company.id, allowed_company_ids)
    companies = list(
        session.scalars(
            select(Company).where(Company.tenant_id == tenant_id, *company_filter).order_by(Company.name)
        )
    )
    summaries: list[CompanyDashboardSummary] = []
    for company in companies:
        filters = _company_document_filter(tenant_id, [company.id])
        summaries.append(
            CompanyDashboardSummary(
                tenant_id=tenant_id,
                company_id=company.id,
                company_name=company.name,
                company_type=company.company_type,
                workers=_count(
                    session,
                    select(func.count()).select_from(Worker).where(
                        Worker.tenant_id == tenant_id,
                        Worker.company_id == company.id,
                        Worker.status != "deleted",
                    ),
                ),
                documents=_count(
                    session,
                    select(func.count()).select_from(Document).where(
                        Document.tenant_id == tenant_id,
                        *filters,
                    ),
                ),
                valid_documents=_count(
                    session,
                    select(func.count()).select_from(Document).where(
                        Document.tenant_id == tenant_id,
                        Document.status_internal == "valid_internal",
                        *filters,
                    ),
                ),
                expired_documents=_count(
                    session,
                    select(func.count()).select_from(Document).where(
                        Document.tenant_id == tenant_id,
                        Document.status_internal == "expired",
                        *filters,
                    ),
                ),
                expiring_soon_documents=_count(
                    session,
                    select(func.count()).select_from(DocumentVersion).join(
                        Document,
                        Document.current_version_id == DocumentVersion.id,
                    ).where(
                        Document.tenant_id == tenant_id,
                        *filters,
                        DocumentVersion.expires_at.is_not(None),
                        DocumentVersion.expires_at >= today,
                        DocumentVersion.expires_at <= soon,
                    ),
                ),
            )
        )
    return summaries


def _count(session: DbSession, statement: Any) -> int:
    value = session.scalar(statement)
    return int(value or 0)


def _company_filter(column: Any, company_ids: Sequence[int] | None) -> tuple[ColumnElement[bool], ...]:
    if company_ids is None:
        return ()
    if not company_ids:
        return (false(),)
    return (column.in_(company_ids),)


def _company_document_filter(
    tenant_id: int,
    company_ids: Sequence[int] | None,
) -> tuple[ColumnElement[bool], ...]:
    if company_ids is None:
        return ()
    company_ids = list(company_ids)
    if not company_ids:
        return (false(),)
    worker_ids = select(Worker.id).where(
        Worker.tenant_id == tenant_id,
        Worker.company_id.in_(company_ids),
    )
    return (
        or_(
            and_(Document.entity_type == "company", Document.entity_id.in_(company_ids)),
            and_(Document.entity_type == "worker", Document.entity_id.in_(worker_ids)),
        ),
    )
