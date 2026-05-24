from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    Document,
    DocumentType,
    DocumentVersion,
    PlatformObservedDocumentRequest,
    PlatformObservedEntity,
    PlatformReviewRun,
    PlatformRpaAccountProposal,
    Worker,
)
from app.services.platform_external_statuses import external_status_color, normalize_external_status

OBSERVED_DOCUMENT_REQUEST_KEYS = (
    "observed_document_requests",
    "document_requests",
    "document_rows",
    "required_documents",
)


def sync_readonly_capture_observations(
    session: Session,
    *,
    tenant_id: int,
    run: PlatformReviewRun,
    capture_summary: dict[str, Any],
) -> dict[str, Any]:
    account = _account_for_run(session, tenant_id=tenant_id, run=run)
    default_company = _default_company(session, tenant_id=tenant_id)
    observed_at = datetime.now(timezone.utc)
    entity_result = _sync_observed_entities(
        session,
        tenant_id=tenant_id,
        run=run,
        account=account,
        capture_summary=capture_summary,
        default_company=default_company,
        observed_at=observed_at,
    )
    request_result = _sync_observed_document_requests(
        session,
        tenant_id=tenant_id,
        run=run,
        account=account,
        capture_summary=capture_summary,
        default_company=default_company,
        observed_at=observed_at,
    )
    if entity_result["upserted"] or request_result["upserted"]:
        session.flush()
    return {
        "entities": entity_result,
        "document_requests": request_result,
    }


def list_observed_entities(
    session: Session,
    *,
    tenant_id: int,
    account_proposal_id: int | None = None,
    entity_type: str | None = None,
    external_status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    statement = select(PlatformObservedEntity).where(PlatformObservedEntity.tenant_id == tenant_id)
    if account_proposal_id is not None:
        statement = statement.where(PlatformObservedEntity.account_proposal_id == account_proposal_id)
    if entity_type:
        statement = statement.where(PlatformObservedEntity.entity_type == entity_type)
    if external_status:
        statement = statement.where(PlatformObservedEntity.external_status == normalize_external_status(external_status))
    rows = session.scalars(statement.order_by(PlatformObservedEntity.last_seen_at.desc()).limit(limit)).all()
    return [_entity_to_read(row) for row in rows]


def list_observed_document_requests(
    session: Session,
    *,
    tenant_id: int,
    account_proposal_id: int | None = None,
    entity_scope: str | None = None,
    external_status: str | None = None,
    severity: str | None = None,
    only_actionable: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    statement = select(PlatformObservedDocumentRequest).where(PlatformObservedDocumentRequest.tenant_id == tenant_id)
    if account_proposal_id is not None:
        statement = statement.where(PlatformObservedDocumentRequest.account_proposal_id == account_proposal_id)
    if entity_scope:
        statement = statement.where(PlatformObservedDocumentRequest.entity_scope == entity_scope)
    if external_status:
        statement = statement.where(PlatformObservedDocumentRequest.external_status == normalize_external_status(external_status))
    if severity:
        statement = statement.where(PlatformObservedDocumentRequest.severity == severity)
    if only_actionable:
        statement = statement.where(
            PlatformObservedDocumentRequest.external_status.notin_({"accepted", "not_applicable"})
        )
    rows = session.scalars(statement.order_by(PlatformObservedDocumentRequest.last_seen_at.desc()).limit(limit)).all()
    return [_document_request_to_read(row) for row in rows]


def build_observed_state_summary(
    session: Session,
    *,
    tenant_id: int,
    account_proposal_id: int | None = None,
) -> dict[str, Any]:
    entity_rows = list_observed_entities(
        session,
        tenant_id=tenant_id,
        account_proposal_id=account_proposal_id,
        limit=500,
    )
    request_rows = list_observed_document_requests(
        session,
        tenant_id=tenant_id,
        account_proposal_id=account_proposal_id,
        limit=500,
    )
    actionable = [row for row in request_rows if row["external_status"] not in {"accepted", "not_applicable"}]
    return {
        "entities": len(entity_rows),
        "document_requests": len(request_rows),
        "actionable_document_requests": len(actionable),
        "by_status": _count_by(request_rows, "external_status"),
        "by_severity": _count_by(request_rows, "severity"),
        "last_seen_at": max(
            [row["last_seen_at"] for row in [*entity_rows, *request_rows] if row["last_seen_at"] is not None],
            default=None,
        ),
    }


def _sync_observed_entities(
    session: Session,
    *,
    tenant_id: int,
    run: PlatformReviewRun,
    account: PlatformRpaAccountProposal | None,
    capture_summary: dict[str, Any],
    default_company: Company | None,
    observed_at: datetime,
) -> dict[str, int]:
    rows = capture_summary.get("observed_workers")
    if not isinstance(rows, list):
        return {"seen": 0, "matched": 0, "upserted": 0, "skipped": 0}
    seen = matched = upserted = skipped = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        seen += 1
        display_name = _clean_optional(item.get("display_name"), 240)
        identifier_last4 = _clean_optional(item.get("identifier_last4"), 20)
        external_worker_id = _clean_optional(item.get("external_worker_id"), 160)
        if not display_name and not identifier_last4 and not external_worker_id:
            skipped += 1
            continue
        worker = _match_worker_from_observed_row(session, tenant_id=tenant_id, row=item)
        if worker is not None:
            matched += 1
        status = "accepted" if item.get("active") is True else "observed"
        key = external_worker_id or _stable_hash("worker", identifier_last4, display_name)
        existing = session.scalar(
            select(PlatformObservedEntity).where(
                PlatformObservedEntity.tenant_id == tenant_id,
                PlatformObservedEntity.account_proposal_id == run.account_proposal_id,
                PlatformObservedEntity.entity_type == "worker",
                PlatformObservedEntity.external_entity_key == key,
            )
        )
        values = {
            "manifest_id": run.manifest_id,
            "external_platform_id": (account.external_platform_id if account else None) or run.external_platform_id,
            "platform_account_id": account.platform_account_id if account else None,
            "source_run_id": run.id,
            "local_company_id": worker.company_id if worker is not None else (default_company.id if default_company else None),
            "local_worker_id": worker.id if worker is not None else None,
            "external_display_name": display_name,
            "external_status": normalize_external_status(status),
            "status_color": external_status_color(status),
            "confidence": 90 if worker is not None else 45,
            "source": "readonly_capture",
            "source_page_label": _clean_optional(item.get("source_page_label"), 180),
            "last_seen_at": observed_at,
            "metadata_json": {
                "identifier_last4": identifier_last4,
                "active": item.get("active") if isinstance(item.get("active"), bool) else None,
                "work_position_observed": _clean_optional(item.get("work_position"), 160),
                "capture_run_id": run.id,
            },
        }
        if existing is None:
            session.add(
                PlatformObservedEntity(
                    tenant_id=tenant_id,
                    account_proposal_id=run.account_proposal_id,
                    entity_type="worker",
                    external_entity_key=key,
                    observed_at=observed_at,
                    **values,
                )
            )
        else:
            for attr, value in values.items():
                setattr(existing, attr, value)
        upserted += 1
    return {"seen": seen, "matched": matched, "upserted": upserted, "skipped": skipped}


def _sync_observed_document_requests(
    session: Session,
    *,
    tenant_id: int,
    run: PlatformReviewRun,
    account: PlatformRpaAccountProposal | None,
    capture_summary: dict[str, Any],
    default_company: Company | None,
    observed_at: datetime,
) -> dict[str, int]:
    rows = _document_request_rows(capture_summary)
    seen = matched_entities = matched_types = upserted = skipped = 0
    for item in rows:
        seen += 1
        label = _first_text(
            item,
            "external_requirement_label",
            "document_label",
            "document_type",
            "requirement",
            "name",
        )
        if not label:
            skipped += 1
            continue
        entity_scope = _entity_scope(item)
        worker = _match_worker_from_observed_row(session, tenant_id=tenant_id, row=item) if entity_scope == "worker" else None
        local_company_id = (
            _int_or_none(item.get("local_company_id"))
            or (worker.company_id if worker is not None else None)
            or (default_company.id if default_company else None)
        )
        if worker is not None or entity_scope == "company":
            matched_entities += 1
        document_type = _match_document_type(session, tenant_id=tenant_id, entity_scope=entity_scope, label=label)
        if document_type is not None:
            matched_types += 1
        document, version = _latest_matching_document(
            session,
            tenant_id=tenant_id,
            entity_scope=entity_scope,
            company_id=local_company_id,
            worker_id=worker.id if worker is not None else None,
            document_type_id=document_type.id if document_type is not None else None,
        )
        external_status = normalize_external_status(_first_text(item, "external_status", "status") or "manual_required")
        color = external_status_color(external_status)
        external_entity_label = _first_text(item, "external_entity_label", "entity_name", "worker_display_name", "display_name")
        requirement_key = _first_text(item, "external_requirement_id", "external_id", "id")
        if not requirement_key:
            requirement_key = _stable_hash(
                str(run.account_proposal_id),
                entity_scope,
                external_entity_label,
                worker.identifier_last4 if worker is not None else None,
                label,
            )
        existing = session.scalar(
            select(PlatformObservedDocumentRequest).where(
                PlatformObservedDocumentRequest.tenant_id == tenant_id,
                PlatformObservedDocumentRequest.account_proposal_id == run.account_proposal_id,
                PlatformObservedDocumentRequest.external_requirement_key == requirement_key,
            )
        )
        values = {
            "manifest_id": run.manifest_id,
            "external_platform_id": (account.external_platform_id if account else None) or run.external_platform_id,
            "platform_account_id": account.platform_account_id if account else None,
            "source_run_id": run.id,
            "entity_scope": entity_scope,
            "local_company_id": local_company_id,
            "local_worker_id": worker.id if worker is not None else _int_or_none(item.get("local_worker_id")),
            "document_type_id": document_type.id if document_type is not None else None,
            "matched_document_id": document.id if document is not None else None,
            "matched_document_version_id": version.id if version is not None else None,
            "external_requirement_label": label,
            "external_entity_label": external_entity_label,
            "external_status": external_status,
            "status_color": color,
            "severity": _severity_for_status(external_status, color),
            "external_comment": _clean_optional(item.get("external_comment"), 1000),
            "rejection_reason": _clean_optional(item.get("rejection_reason"), 1000),
            "requested_at": _parse_datetime(item.get("requested_at")),
            "external_expires_at": _parse_date(item.get("external_expires_at") or item.get("expires_at")),
            "confidence": _request_confidence(worker=worker, document_type=document_type, version=version),
            "source": "readonly_capture",
            "source_page_label": _clean_optional(item.get("source_page_label"), 180),
            "last_seen_at": observed_at,
            "metadata_json": {
                "capture_run_id": run.id,
                "raw_status": _clean_optional(_first_text(item, "external_status", "status"), 120),
                "hub_document_available": version is not None,
            },
        }
        if existing is None:
            session.add(
                PlatformObservedDocumentRequest(
                    tenant_id=tenant_id,
                    account_proposal_id=run.account_proposal_id,
                    external_requirement_key=requirement_key,
                    observed_at=observed_at,
                    **values,
                )
            )
        else:
            for attr, value in values.items():
                setattr(existing, attr, value)
        upserted += 1
    return {
        "seen": seen,
        "matched_entities": matched_entities,
        "matched_document_types": matched_types,
        "upserted": upserted,
        "skipped": skipped,
    }


def _document_request_rows(capture_summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in OBSERVED_DOCUMENT_REQUEST_KEYS:
        value = capture_summary.get(key)
        if isinstance(value, list):
            rows.extend([item for item in value if isinstance(item, dict)])
    return rows


def _account_for_run(
    session: Session,
    *,
    tenant_id: int,
    run: PlatformReviewRun,
) -> PlatformRpaAccountProposal | None:
    if run.account_proposal_id is None:
        return None
    return session.scalar(
        select(PlatformRpaAccountProposal).where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.id == run.account_proposal_id,
        )
    )


def _default_company(session: Session, *, tenant_id: int) -> Company | None:
    companies = list(
        session.scalars(
            select(Company).where(
                Company.tenant_id == tenant_id,
                Company.company_type == "own",
            )
        )
    )
    if len(companies) == 1:
        return companies[0]
    return None


def _match_worker_from_observed_row(
    session: Session,
    *,
    tenant_id: int,
    row: dict[str, Any],
) -> Worker | None:
    identifier_last4 = _first_text(row, "identifier_last4", "worker_identifier_last4")
    display_name = _first_text(row, "display_name", "worker_display_name", "entity_name", "external_entity_label")
    candidates: list[Worker] = []
    if identifier_last4:
        candidates = list(
            session.scalars(
                select(Worker).where(
                    Worker.tenant_id == tenant_id,
                    Worker.identifier_last4 == identifier_last4.strip().upper()[-4:],
                )
            )
        )
    if not candidates and display_name:
        all_workers = list(session.scalars(select(Worker).where(Worker.tenant_id == tenant_id)))
        candidates = [worker for worker in all_workers if _worker_name_matches_display(worker, display_name)]
    if len(candidates) == 1:
        return candidates[0]
    if display_name:
        named = [worker for worker in candidates if _worker_name_matches_display(worker, display_name)]
        if len(named) == 1:
            return named[0]
    return None


def _match_document_type(
    session: Session,
    *,
    tenant_id: int,
    entity_scope: str,
    label: str,
) -> DocumentType | None:
    label_norm = _norm(label)
    if not label_norm:
        return None
    candidates = list(
        session.scalars(
            select(DocumentType).where(
                or_(DocumentType.tenant_id == tenant_id, DocumentType.tenant_id.is_(None)),
                DocumentType.entity_scope.in_([entity_scope, "both", "any"]),
            )
        )
    )
    exact = [
        item
        for item in candidates
        if _norm(item.code) == label_norm or _norm(item.name) == label_norm
    ]
    if len(exact) == 1:
        return exact[0]
    label_tokens = set(_tokens(label_norm))
    if not label_tokens:
        return None
    scored: list[tuple[int, DocumentType]] = []
    for candidate in candidates:
        candidate_tokens = set(_tokens(f"{candidate.code} {candidate.name}"))
        if not candidate_tokens:
            continue
        overlap = len(label_tokens & candidate_tokens)
        if overlap:
            scored.append((overlap, candidate))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], len(item[1].name)), reverse=True)
    return scored[0][1] if scored[0][0] >= min(2, len(label_tokens)) else None


def _latest_matching_document(
    session: Session,
    *,
    tenant_id: int,
    entity_scope: str,
    company_id: int | None,
    worker_id: int | None,
    document_type_id: int | None,
) -> tuple[Document | None, DocumentVersion | None]:
    if document_type_id is None:
        return None, None
    entity_id = worker_id if entity_scope == "worker" else company_id
    if entity_id is None:
        return None, None
    document = session.scalar(
        select(Document)
        .where(
            Document.tenant_id == tenant_id,
            Document.entity_type == entity_scope,
            Document.entity_id == entity_id,
            Document.document_type_id == document_type_id,
        )
        .order_by(Document.id.desc())
        .limit(1)
    )
    if document is None:
        return None, None
    version = None
    if document.current_version_id is not None:
        version = session.get(DocumentVersion, document.current_version_id)
    if version is None:
        version = session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
    return document, version


def _entity_scope(item: dict[str, Any]) -> str:
    raw = _first_text(item, "entity_scope", "entity_type", "scope") or ""
    lowered = raw.lower()
    if "worker" in lowered or "trabajador" in lowered or "empleado" in lowered:
        return "worker"
    if "company" in lowered or "empresa" in lowered:
        return "company"
    if _first_text(item, "worker_display_name", "display_name", "identifier_last4"):
        return "worker"
    return "company"


def _severity_for_status(status: str, color: str) -> str:
    if status in {"rejected", "expired_external", "blocked_by_platform", "manual_required"}:
        return "red"
    if color == "green":
        return "green"
    return "orange"


def _request_confidence(
    *,
    worker: Worker | None,
    document_type: DocumentType | None,
    version: DocumentVersion | None,
) -> int:
    confidence = 40
    if worker is not None:
        confidence += 20
    if document_type is not None:
        confidence += 20
    if version is not None:
        confidence += 10
    return min(confidence, 95)


def _entity_to_read(row: PlatformObservedEntity) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "manifest_id": row.manifest_id,
        "account_proposal_id": row.account_proposal_id,
        "external_platform_id": row.external_platform_id,
        "platform_account_id": row.platform_account_id,
        "source_run_id": row.source_run_id,
        "entity_type": row.entity_type,
        "local_company_id": row.local_company_id,
        "local_worker_id": row.local_worker_id,
        "external_entity_key": row.external_entity_key,
        "external_display_name": row.external_display_name,
        "external_status": row.external_status,
        "status_color": row.status_color,
        "confidence": row.confidence,
        "source": row.source,
        "source_page_label": row.source_page_label,
        "observed_at": row.observed_at,
        "last_seen_at": row.last_seen_at,
        "metadata_json": row.metadata_json,
    }


def _document_request_to_read(row: PlatformObservedDocumentRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "manifest_id": row.manifest_id,
        "account_proposal_id": row.account_proposal_id,
        "external_platform_id": row.external_platform_id,
        "platform_account_id": row.platform_account_id,
        "source_run_id": row.source_run_id,
        "entity_scope": row.entity_scope,
        "local_company_id": row.local_company_id,
        "local_worker_id": row.local_worker_id,
        "document_type_id": row.document_type_id,
        "matched_document_id": row.matched_document_id,
        "matched_document_version_id": row.matched_document_version_id,
        "external_requirement_key": row.external_requirement_key,
        "external_requirement_label": row.external_requirement_label,
        "external_entity_label": row.external_entity_label,
        "external_status": row.external_status,
        "status_color": row.status_color,
        "severity": row.severity,
        "external_comment": row.external_comment,
        "rejection_reason": row.rejection_reason,
        "requested_at": row.requested_at,
        "external_expires_at": row.external_expires_at,
        "confidence": row.confidence,
        "source": row.source,
        "source_page_label": row.source_page_label,
        "observed_at": row.observed_at,
        "last_seen_at": row.last_seen_at,
        "metadata_json": row.metadata_json,
    }


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        result[value] = result.get(value, 0) + 1
    return result


def _worker_name_matches_display(worker: Worker, display_name: str) -> bool:
    worker_tokens = set(_tokens(f"{worker.first_name} {worker.last_name}"))
    display_tokens = set(_tokens(display_name.replace(",", " ")))
    if not worker_tokens or not display_tokens:
        return False
    return len(worker_tokens & display_tokens) >= min(2, len(display_tokens))


def _tokens(value: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return [token for token in normalized.split() if len(token) >= 3]


def _norm(value: str) -> str:
    return " ".join(_tokens(value))


def _first_text(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        cleaned = _clean_optional(item.get(key), 320)
        if cleaned:
            return cleaned
    return None


def _clean_optional(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned[:max_length] or None


def _stable_hash(*values: Any) -> str:
    material = "|".join(str(value or "") for value in values)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value.strip():
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    parsed_date = _parse_date(value)
    if parsed_date is None:
        return None
    return datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone.utc)
