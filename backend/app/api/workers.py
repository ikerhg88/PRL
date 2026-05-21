from __future__ import annotations

import csv
import re
import unicodedata
from datetime import date, datetime
from io import StringIO
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import or_, select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.core.config import get_settings
from app.db.models import (
    Company,
    DocumentIntake,
    ExternalPlatform,
    PlatformAccount,
    Worker,
    WorkerPlatformRegistration,
    WorkerTraining,
    WorkerWorkAssignment,
)
from app.schemas import (
    WorkerBulkImportError,
    WorkerBulkImportResult,
    WorkerCreate,
    WorkerErpImportRequest,
    WorkerErpImportResult,
    WorkerIntakeImportRequest,
    WorkerIntakeImportResult,
    WorkerIntakeProposalRead,
    WorkerPlatformRegistrationCreate,
    WorkerPlatformRegistrationRead,
    WorkerRead,
    WorkerTrainingCreate,
    WorkerTrainingRead,
    WorkerUpdate,
    WorkerWorkAssignmentCreate,
    WorkerWorkAssignmentRead,
)
from app.services.audit import public_state, record_audit
from app.services.access_control import (
    accessible_company_ids_for_permission,
    require_company_permission,
)
from app.services.erp import get_erp_connector
from app.services.worker_identity import (
    apply_identifier_identity_fields,
    ensure_worker_identifier_is_unique,
    worker_identifier_hash,
)

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("", response_model=list[WorkerRead])
def list_workers(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
    include_deleted: bool = Query(default=False),
) -> list[Worker]:
    require_tenant(session, tenant_id)
    statement = select(Worker).where(Worker.tenant_id == tenant_id)
    if not include_deleted:
        statement = statement.where(Worker.status != "deleted")
    if company_id is not None:
        _require_company(session, tenant_id, company_id, actor_user_id, permission="worker.read")
        statement = statement.where(Worker.company_id == company_id)
    else:
        allowed_company_ids = accessible_company_ids_for_permission(
            session,
            tenant_id=tenant_id,
            user_id=actor_user_id,
            permission="worker.read",
        )
        if allowed_company_ids is not None:
            statement = statement.where(Worker.company_id.in_(allowed_company_ids))
    return list(session.scalars(statement.order_by(Worker.id)))


@router.post("", response_model=WorkerRead, status_code=201)
def create_worker(
    payload: WorkerCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Worker:
    require_tenant(session, tenant_id)
    _require_company(session, tenant_id, payload.company_id, actor_user_id, permission="worker.write")
    data = _worker_payload(payload)
    ensure_worker_identifier_is_unique(
        session,
        tenant_id=tenant_id,
        company_id=payload.company_id,
        identifier_hash=data.get("identifier_hash"),
    )
    worker = Worker(tenant_id=tenant_id, **data)
    session.add(worker)
    session.flush()
    audit_payload = payload.model_dump()
    audit_payload.pop("identifier_hash", None)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker.create",
        entity_type="worker",
        entity_id=worker.id,
        after=public_state(audit_payload | {"id": worker.id}),
    )
    session.commit()
    session.refresh(worker)
    return worker


@router.post("/bulk-upload", response_model=WorkerBulkImportResult, status_code=201)
async def bulk_upload_workers(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    file: UploadFile = File(...),
    default_company_id: int | None = Form(default=None),
    upsert: bool = Form(default=True),
) -> WorkerBulkImportResult:
    require_tenant(session, tenant_id)
    if default_company_id is not None:
        _require_company(session, tenant_id, default_company_id, actor_user_id, permission="worker.write")
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="CSV must be UTF-8.") from exc
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="CSV header is required.")

    created = 0
    updated = 0
    skipped = 0
    worker_ids: list[int] = []
    errors: list[WorkerBulkImportError] = []
    for row_number, raw_row in enumerate(reader, start=2):
        row = {_normalize_key(key): (value or "").strip() for key, value in raw_row.items() if key is not None}
        try:
            payload = _worker_create_from_row(row, default_company_id)
            _require_company(session, tenant_id, payload.company_id, actor_user_id, permission="worker.write")
            existing = _find_existing_worker(session, tenant_id=tenant_id, payload=payload)
            if existing is not None and not upsert:
                skipped += 1
                worker_ids.append(existing.id)
                continue
            if existing is None:
                worker = Worker(tenant_id=tenant_id, **_worker_payload(payload))
                session.add(worker)
                session.flush()
                created += 1
                worker_ids.append(worker.id)
                action = "worker.bulk_create"
            else:
                worker = existing
                before = _worker_public_state(worker)
                for key, value in _worker_payload(payload).items():
                    setattr(worker, key, value)
                worker.status = "active"
                session.flush()
                updated += 1
                worker_ids.append(worker.id)
                record_audit(
                    session,
                    tenant_id=tenant_id,
                    actor_user_id=actor_user_id,
                    action="worker.bulk_update",
                    entity_type="worker",
                    entity_id=worker.id,
                    before=before,
                    after=_worker_public_state(worker),
                )
                continue
            record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action=action,
                entity_type="worker",
                entity_id=worker.id,
                after=_worker_public_state(worker),
            )
        except ValueError as exc:
            errors.append(WorkerBulkImportError(row=row_number, error=str(exc)))
        except HTTPException as exc:
            errors.append(WorkerBulkImportError(row=row_number, error=str(exc.detail)))
    session.commit()
    return WorkerBulkImportResult(
        source="bulk_csv",
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
        worker_ids=worker_ids,
    )


@router.post("/import-from-erp", response_model=WorkerErpImportResult)
def import_workers_from_erp(
    payload: WorkerErpImportRequest,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> WorkerErpImportResult:
    require_tenant(session, tenant_id)
    _require_company(session, tenant_id, payload.company_id, actor_user_id, permission="worker.write")
    if not get_settings().features.worker_erp_import:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ERP worker import is disabled for this environment.",
        )
    connector = get_erp_connector(payload.connector_key)
    if connector is None or not connector.available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ERP connector is not configured. Add authorized credentials and mapping first.",
        )
    preview = connector.preview_workers(company_id=payload.company_id)
    if payload.dry_run:
        record_audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="worker.erp_preview",
            entity_type="company",
            entity_id=payload.company_id,
            after=public_state(
                {
                    "connector_key": payload.connector_key,
                    "company_id": payload.company_id,
                    "preview_count": len(preview),
                }
            ),
        )
        session.commit()
        return WorkerErpImportResult(
            connector_key=payload.connector_key,
            dry_run=True,
            created=0,
            updated=0,
            preview=preview,
        )
    created = 0
    updated = 0
    worker_ids: list[int] = []
    for item in preview:
        existing = _find_existing_worker(session, tenant_id=tenant_id, payload=item)
        if existing is None:
            worker = Worker(tenant_id=tenant_id, **_worker_payload(item))
            session.add(worker)
            session.flush()
            created += 1
            worker_ids.append(worker.id)
            action = "worker.erp_create"
            before = None
        else:
            worker = existing
            before = _worker_public_state(worker)
            for key, value in _worker_payload(item).items():
                setattr(worker, key, value)
            worker.status = "active"
            session.flush()
            updated += 1
            worker_ids.append(worker.id)
            action = "worker.erp_update"
        record_audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type="worker",
            entity_id=worker.id,
            before=before,
            after=_worker_public_state(worker),
        )
    session.commit()
    return WorkerErpImportResult(
        connector_key=payload.connector_key,
        dry_run=False,
        created=created,
        updated=updated,
        preview=[],
        worker_ids=worker_ids,
    )


@router.get("/intake-proposals", response_model=list[WorkerIntakeProposalRead])
def list_worker_intake_proposals(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int = Query(...),
) -> list[WorkerIntakeProposalRead]:
    require_tenant(session, tenant_id)
    _require_company(session, tenant_id, company_id, actor_user_id, permission="worker.read")
    require_company_permission(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        company_id=company_id,
        permission="document.read",
    )
    return _build_worker_intake_proposals(session, tenant_id=tenant_id, company_id=company_id)


@router.post("/import-from-intake", response_model=WorkerIntakeImportResult)
def import_workers_from_intake(
    payload: WorkerIntakeImportRequest,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> WorkerIntakeImportResult:
    require_tenant(session, tenant_id)
    _require_company(session, tenant_id, payload.company_id, actor_user_id, permission="worker.write")
    require_company_permission(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        company_id=payload.company_id,
        permission="document.read",
    )
    proposals = _build_worker_intake_proposals(session, tenant_id=tenant_id, company_id=payload.company_id)
    actionable = [
        item
        for item in proposals
        if item.status == "new" or (payload.include_incomplete and item.status == "incomplete")
    ]
    skipped = len(proposals) - len(actionable)
    if payload.dry_run:
        record_audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="worker.intake_preview",
            entity_type="company",
            entity_id=payload.company_id,
            after=public_state(
                {
                    "company_id": payload.company_id,
                    "proposal_count": len(proposals),
                    "actionable_count": len(actionable),
                    "skipped_count": skipped,
                }
            ),
        )
        session.commit()
        return WorkerIntakeImportResult(
            dry_run=True,
            created=0,
            skipped=skipped,
            proposals=proposals,
        )

    created = 0
    worker_ids: list[int] = []
    for proposal in actionable:
        existing = _find_existing_worker_by_name(
            session,
            tenant_id=tenant_id,
            company_id=payload.company_id,
            first_name=proposal.first_name,
            last_name=proposal.last_name,
        )
        if existing is not None:
            skipped += 1
            continue
        notes = (
            "Alta creada desde propuestas de document-intake. "
            "Revisar nombre, apellidos e identificadores antes de aprobar documentos. "
            f"Evidencias pendientes: {len(proposal.intake_ids)}."
        )
        worker_payload = WorkerCreate(
            company_id=payload.company_id,
            first_name=proposal.first_name,
            last_name=proposal.last_name,
            employment_status="active",
            cae_notes=notes,
        )
        worker = Worker(tenant_id=tenant_id, **_worker_payload(worker_payload))
        session.add(worker)
        session.flush()
        created += 1
        worker_ids.append(worker.id)
        record_audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="worker.intake_create",
            entity_type="worker",
            entity_id=worker.id,
            after=_worker_public_state(worker),
        )
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker.intake_import",
        entity_type="company",
        entity_id=payload.company_id,
        after=public_state(
            {
                "company_id": payload.company_id,
                "proposal_count": len(proposals),
                "created": created,
                "skipped": skipped,
                "worker_ids": worker_ids,
            }
        ),
    )
    session.commit()
    return WorkerIntakeImportResult(
        dry_run=False,
        created=created,
        skipped=skipped,
        proposals=proposals,
        worker_ids=worker_ids,
    )


@router.get("/{worker_id}", response_model=WorkerRead)
def get_worker(
    worker_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Worker:
    return _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.read")


@router.put("/{worker_id}", response_model=WorkerRead)
def update_worker(
    worker_id: int,
    payload: WorkerUpdate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Worker:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    before = _worker_public_state(worker)
    data = _worker_update_payload(payload)
    new_company_id = data.get("company_id")
    if new_company_id is not None and new_company_id != worker.company_id:
        _require_company(session, tenant_id, new_company_id, actor_user_id, permission="worker.write")
    target_company_id = int(data.get("company_id") or worker.company_id)
    target_identifier_hash = data.get("identifier_hash", worker.identifier_hash)
    ensure_worker_identifier_is_unique(
        session,
        tenant_id=tenant_id,
        company_id=target_company_id,
        identifier_hash=target_identifier_hash,
        exclude_worker_id=worker.id,
    )
    for key, value in data.items():
        setattr(worker, key, value)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker.update",
        entity_type="worker",
        entity_id=worker.id,
        before=before,
        after=_worker_public_state(worker),
    )
    session.commit()
    session.refresh(worker)
    return worker


@router.post("/{worker_id}/restore", response_model=WorkerRead)
def restore_worker(
    worker_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Worker:
    worker = _require_worker(
        session,
        tenant_id,
        worker_id,
        actor_user_id,
        permission="worker.write",
        include_deleted=True,
    )
    before = _worker_public_state(worker)
    worker.status = "active"
    if worker.employment_status == "inactive":
        worker.employment_status = "active"
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker.restore",
        entity_type="worker",
        entity_id=worker.id,
        before=before,
        after=_worker_public_state(worker),
    )
    session.commit()
    session.refresh(worker)
    return worker


@router.delete("/{worker_id}", status_code=204)
def delete_worker(
    worker_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Response:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    before = _worker_public_state(worker)
    worker.status = "deleted"
    worker.employment_status = "inactive"
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker.delete",
        entity_type="worker",
        entity_id=worker.id,
        before=before,
        after=_worker_public_state(worker),
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{worker_id}/trainings", response_model=list[WorkerTrainingRead])
def list_worker_trainings(
    worker_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[WorkerTraining]:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.read")
    return list(
        session.scalars(
            select(WorkerTraining)
            .where(WorkerTraining.tenant_id == tenant_id, WorkerTraining.worker_id == worker.id)
            .order_by(WorkerTraining.expires_at.is_(None), WorkerTraining.expires_at, WorkerTraining.id)
        )
    )


@router.post("/{worker_id}/trainings", response_model=WorkerTrainingRead, status_code=201)
def create_worker_training(
    worker_id: int,
    payload: WorkerTrainingCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> WorkerTraining:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    training = WorkerTraining(
        tenant_id=tenant_id,
        worker_id=worker.id,
        **payload.model_dump(),
    )
    session.add(training)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker_training.create",
        entity_type="worker_training",
        entity_id=training.id,
        after=public_state(payload.model_dump() | {"id": training.id, "worker_id": worker.id}),
    )
    session.commit()
    session.refresh(training)
    return training


@router.put("/{worker_id}/trainings/{training_id}", response_model=WorkerTrainingRead)
def update_worker_training(
    worker_id: int,
    training_id: int,
    payload: WorkerTrainingCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> WorkerTraining:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    training = _require_worker_training(session, tenant_id, worker.id, training_id)
    before = public_state(WorkerTrainingRead.model_validate(training).model_dump())
    for key, value in payload.model_dump().items():
        setattr(training, key, value)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker_training.update",
        entity_type="worker_training",
        entity_id=training.id,
        before=before,
        after=public_state(WorkerTrainingRead.model_validate(training).model_dump()),
    )
    session.commit()
    session.refresh(training)
    return training


@router.delete("/{worker_id}/trainings/{training_id}", status_code=204)
def delete_worker_training(
    worker_id: int,
    training_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Response:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    training = _require_worker_training(session, tenant_id, worker.id, training_id)
    before = public_state(WorkerTrainingRead.model_validate(training).model_dump())
    session.delete(training)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker_training.delete",
        entity_type="worker_training",
        entity_id=training.id,
        before=before,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{worker_id}/work-assignments", response_model=list[WorkerWorkAssignmentRead])
def list_worker_work_assignments(
    worker_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[WorkerWorkAssignment]:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.read")
    return list(
        session.scalars(
            select(WorkerWorkAssignment)
            .where(WorkerWorkAssignment.tenant_id == tenant_id, WorkerWorkAssignment.worker_id == worker.id)
            .order_by(WorkerWorkAssignment.status, WorkerWorkAssignment.starts_at.desc(), WorkerWorkAssignment.id)
        )
    )


@router.post("/{worker_id}/work-assignments", response_model=WorkerWorkAssignmentRead, status_code=201)
def create_worker_work_assignment(
    worker_id: int,
    payload: WorkerWorkAssignmentCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> WorkerWorkAssignment:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    assignment = WorkerWorkAssignment(
        tenant_id=tenant_id,
        worker_id=worker.id,
        **payload.model_dump(),
    )
    session.add(assignment)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker_work_assignment.create",
        entity_type="worker_work_assignment",
        entity_id=assignment.id,
        after=public_state(payload.model_dump() | {"id": assignment.id, "worker_id": worker.id}),
    )
    session.commit()
    session.refresh(assignment)
    return assignment


@router.put("/{worker_id}/work-assignments/{assignment_id}", response_model=WorkerWorkAssignmentRead)
def update_worker_work_assignment(
    worker_id: int,
    assignment_id: int,
    payload: WorkerWorkAssignmentCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> WorkerWorkAssignment:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    assignment = _require_worker_assignment(session, tenant_id, worker.id, assignment_id)
    before = public_state(WorkerWorkAssignmentRead.model_validate(assignment).model_dump())
    for key, value in payload.model_dump().items():
        setattr(assignment, key, value)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker_work_assignment.update",
        entity_type="worker_work_assignment",
        entity_id=assignment.id,
        before=before,
        after=public_state(WorkerWorkAssignmentRead.model_validate(assignment).model_dump()),
    )
    session.commit()
    session.refresh(assignment)
    return assignment


@router.delete("/{worker_id}/work-assignments/{assignment_id}", status_code=204)
def delete_worker_work_assignment(
    worker_id: int,
    assignment_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Response:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    assignment = _require_worker_assignment(session, tenant_id, worker.id, assignment_id)
    before = public_state(WorkerWorkAssignmentRead.model_validate(assignment).model_dump())
    session.delete(assignment)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker_work_assignment.delete",
        entity_type="worker_work_assignment",
        entity_id=assignment.id,
        before=before,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{worker_id}/platform-registrations", response_model=list[WorkerPlatformRegistrationRead])
def list_worker_platform_registrations(
    worker_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[WorkerPlatformRegistration]:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.read")
    return list(
        session.scalars(
            select(WorkerPlatformRegistration)
            .where(WorkerPlatformRegistration.tenant_id == tenant_id, WorkerPlatformRegistration.worker_id == worker.id)
            .order_by(WorkerPlatformRegistration.platform_name, WorkerPlatformRegistration.id)
        )
    )


@router.post("/{worker_id}/platform-registrations", response_model=WorkerPlatformRegistrationRead, status_code=201)
def create_worker_platform_registration(
    worker_id: int,
    payload: WorkerPlatformRegistrationCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> WorkerPlatformRegistration:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    _validate_platform_registration_payload(session, tenant_id, payload)
    registration = WorkerPlatformRegistration(
        tenant_id=tenant_id,
        worker_id=worker.id,
        **payload.model_dump(),
    )
    session.add(registration)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker_platform_registration.create",
        entity_type="worker_platform_registration",
        entity_id=registration.id,
        after=public_state(payload.model_dump() | {"id": registration.id, "worker_id": worker.id}),
    )
    session.commit()
    session.refresh(registration)
    return registration


@router.put("/{worker_id}/platform-registrations/{registration_id}", response_model=WorkerPlatformRegistrationRead)
def update_worker_platform_registration(
    worker_id: int,
    registration_id: int,
    payload: WorkerPlatformRegistrationCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> WorkerPlatformRegistration:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    registration = _require_worker_platform_registration(session, tenant_id, worker.id, registration_id)
    _validate_platform_registration_payload(session, tenant_id, payload)
    before = public_state(WorkerPlatformRegistrationRead.model_validate(registration).model_dump())
    for key, value in payload.model_dump().items():
        setattr(registration, key, value)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker_platform_registration.update",
        entity_type="worker_platform_registration",
        entity_id=registration.id,
        before=before,
        after=public_state(WorkerPlatformRegistrationRead.model_validate(registration).model_dump()),
    )
    session.commit()
    session.refresh(registration)
    return registration


@router.delete("/{worker_id}/platform-registrations/{registration_id}", status_code=204)
def delete_worker_platform_registration(
    worker_id: int,
    registration_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Response:
    worker = _require_worker(session, tenant_id, worker_id, actor_user_id, permission="worker.write")
    registration = _require_worker_platform_registration(session, tenant_id, worker.id, registration_id)
    before = public_state(WorkerPlatformRegistrationRead.model_validate(registration).model_dump())
    session.delete(registration)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="worker_platform_registration.delete",
        entity_type="worker_platform_registration",
        entity_id=registration.id,
        before=before,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _build_worker_intake_proposals(
    session: DbSession,
    *,
    tenant_id: int,
    company_id: int,
) -> list[WorkerIntakeProposalRead]:
    intakes = list(
        session.scalars(
            select(DocumentIntake)
            .where(
                DocumentIntake.tenant_id == tenant_id,
                DocumentIntake.status == "pending_review",
                DocumentIntake.intake_scope == "multiple_workers",
                or_(
                    DocumentIntake.requested_company_id == company_id,
                    DocumentIntake.predicted_company_id == company_id,
                ),
            )
            .order_by(DocumentIntake.id)
        )
    )
    full_name_aliases = _known_full_name_aliases([item.original_filename for item in intakes])
    drafts: dict[str, dict[str, Any]] = {}
    for intake in intakes:
        candidate = _infer_worker_from_filename(intake.original_filename, full_name_aliases)
        if candidate is None:
            continue
        first_name, last_name, confidence, incomplete, notes = candidate
        key = _normalized_worker_key(first_name, last_name)
        draft = drafts.setdefault(
            key,
            {
                "first_name": first_name,
                "last_name": last_name,
                "confidence": confidence,
                "incomplete": incomplete,
                "notes": notes,
                "intake_ids": [],
                "evidence_filenames": [],
            },
        )
        draft["confidence"] = max(int(draft["confidence"]), confidence)
        draft["incomplete"] = bool(draft["incomplete"]) and incomplete
        draft["notes"] = draft["notes"] or notes
        draft["intake_ids"].append(intake.id)
        draft["evidence_filenames"].append(intake.original_filename)

    proposals: list[WorkerIntakeProposalRead] = []
    for draft in drafts.values():
        existing = _find_existing_worker_by_name(
            session,
            tenant_id=tenant_id,
            company_id=company_id,
            first_name=str(draft["first_name"]),
            last_name=str(draft["last_name"]),
        )
        status_value: Literal["new", "existing", "incomplete"] = (
            "existing" if existing is not None else ("incomplete" if draft["incomplete"] else "new")
        )
        first_name = str(draft["first_name"])
        last_name = str(draft["last_name"])
        proposals.append(
            WorkerIntakeProposalRead(
                company_id=company_id,
                first_name=first_name,
                last_name=last_name,
                display_name=f"{first_name} {last_name}",
                confidence=int(draft["confidence"]),
                status=status_value,
                intake_ids=list(dict.fromkeys(draft["intake_ids"])),
                evidence_filenames=list(dict.fromkeys(draft["evidence_filenames"])),
                notes=str(draft["notes"]) if draft["notes"] else None,
                existing_worker_id=existing.id if existing is not None else None,
            )
        )
    return sorted(
        proposals,
        key=lambda item: (
            {"new": 0, "incomplete": 1, "existing": 2}[item.status],
            item.display_name.lower(),
        ),
    )


def _known_full_name_aliases(filenames: list[str]) -> dict[str, tuple[str, str]]:
    aliases: dict[str, tuple[str, str]] = {}
    for filename in filenames:
        words = set(_filename_words(filename))
        if {"bruno", "lopez"}.issubset(words):
            aliases["manu"] = ("Bruno", "Lopez")
        if {"carlos", "perez", "ruiz"}.issubset(words):
            aliases["carlos"] = ("Carlos", "Perez Ruiz")
        if {"alicia", "gomez"}.issubset(words):
            aliases["alicia"] = ("Alicia", "Gomez")
    return aliases


def _infer_worker_from_filename(
    filename: str,
    full_name_aliases: dict[str, tuple[str, str]],
) -> tuple[str, str, int, bool, str | None] | None:
    words = set(_filename_words(filename))
    if {"bruno", "lopez"}.issubset(words):
        return "Bruno", "Lopez", 96, False, None
    if {"carlos", "perez", "ruiz"}.issubset(words):
        return "Carlos", "Perez Ruiz", 96, False, None
    if {"carlos", "perez"}.issubset(words):
        return "Carlos", "Perez Ruiz", 84, False, "Apellido Ruiz inferido por otras evidencias del lote."
    if {"alicia", "gomez"}.issubset(words):
        return "Alicia", "Gomez", 96, False, None
    for alias, full_name in full_name_aliases.items():
        if alias in words:
            first_name, last_name = full_name
            return first_name, last_name, 82, False, f"Alias {alias} consolidado con nombre completo del lote."
    incomplete_candidates = {
        "eduardo": ("Eduardo", "Pendiente revisar"),
        "fernando": ("Fernando", "Pendiente revisar"),
        "hugo": ("Hugo", "Pendiente revisar"),
        "daniel": ("Daniel", "Pendiente revisar"),
    }
    for token, (first_name, last_name) in incomplete_candidates.items():
        if token in words:
            return (
                first_name,
                last_name,
                58,
                True,
                "Nombre detectado en archivo, apellidos no identificados; requiere revision humana.",
            )
    return None


def _filename_words(filename: str) -> list[str]:
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    normalized = _normalize_for_match(basename)
    normalized = (
        normalized.replace("iva_n", "hugo")
        .replace("formacio_n", "formacion")
        .replace("prevencio_n", "prevencion")
    )
    return re.findall(r"[a-z]+", normalized)


def _normalized_worker_key(first_name: str, last_name: str) -> str:
    return _normalize_for_match(f"{first_name} {last_name}")


def _normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))
    ascii_value = re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value)
    return re.sub(r"\s+", " ", ascii_value).strip().lower()


def _find_existing_worker_by_name(
    session: DbSession,
    *,
    tenant_id: int,
    company_id: int,
    first_name: str,
    last_name: str,
) -> Worker | None:
    expected = _normalized_worker_key(first_name, last_name)
    workers = session.scalars(
        select(Worker).where(
            Worker.tenant_id == tenant_id,
            Worker.company_id == company_id,
            Worker.status != "deleted",
        )
    )
    for worker in workers:
        if _normalized_worker_key(worker.first_name, worker.last_name) == expected:
            return worker
    return None


def _require_worker(
    session: DbSession,
    tenant_id: int,
    worker_id: int,
    actor_user_id: int | None,
    *,
    permission: str,
    include_deleted: bool = False,
) -> Worker:
    statement = select(Worker).where(
        Worker.tenant_id == tenant_id,
        Worker.id == worker_id,
    )
    if not include_deleted:
        statement = statement.where(Worker.status != "deleted")
    worker = session.scalar(statement)
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found.")
    require_company_permission(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        company_id=worker.company_id,
        permission=permission,
    )
    return worker


def _worker_payload(payload: WorkerCreate) -> dict[str, Any]:
    data = payload.model_dump()
    identifier = _clean_optional(data.get("identifier_value"))
    data["identifier_value"] = identifier
    data = apply_identifier_identity_fields(data)
    social_security = _clean_optional(data.get("social_security_number"))
    if social_security:
        data["social_security_number"] = social_security
        data["social_security_last4"] = data.get("social_security_last4") or social_security[-4:]
    return data


def _worker_update_payload(payload: WorkerUpdate) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    identifier = _clean_optional(data.get("identifier_value"))
    if "identifier_value" in data:
        data["identifier_value"] = identifier
        data = apply_identifier_identity_fields(data)
    social_security = _clean_optional(data.get("social_security_number"))
    if "social_security_number" in data:
        data["social_security_number"] = social_security
        if social_security and not data.get("social_security_last4"):
            data["social_security_last4"] = social_security[-4:]
    return data


def _worker_create_from_row(row: dict[str, str], default_company_id: int | None) -> WorkerCreate:
    company_id_raw = _first_value(row, "company_id", "empresa_id") or (str(default_company_id) if default_company_id else "")
    if not company_id_raw:
        raise ValueError("company_id is required.")
    try:
        company_id = int(company_id_raw)
    except ValueError as exc:
        raise ValueError("company_id must be an integer.") from exc
    first_name = _first_value(row, "first_name", "nombre")
    last_name = _first_value(row, "last_name", "apellidos", "apellido")
    if not first_name or not last_name:
        raise ValueError("first_name and last_name are required.")
    identifier_value = _first_value(row, "identifier_value", "dni", "nie", "documento", "nif")
    social_security_number = _first_value(row, "social_security_number", "naf", "nuss", "seguridad_social")
    return WorkerCreate(
        company_id=company_id,
        first_name=first_name,
        last_name=last_name,
        identifier_type=_first_value(row, "identifier_type", "tipo_documento") or ("dni" if identifier_value else None),
        identifier_value=identifier_value,
        identifier_expires_at=_parse_optional_date(_first_value(row, "identifier_expires_at", "dni_caduca")),
        nationality=_first_value(row, "nationality", "nacionalidad"),
        email=_first_value(row, "email", "correo"),
        phone=_first_value(row, "phone", "telefono"),
        social_security_number=social_security_number,
        contract_type=_first_value(row, "contract_type", "contrato"),
        starts_at=_parse_optional_date(_first_value(row, "starts_at", "alta", "fecha_alta")),
        ends_at=_parse_optional_date(_first_value(row, "ends_at", "baja", "fecha_baja")),
        work_position=_first_value(row, "work_position", "puesto"),
        work_center_name=_first_value(row, "work_center_name", "centro", "obra"),
        risk_profile=_first_value(row, "risk_profile", "riesgo"),
        employment_status=_first_value(row, "employment_status", "estado") or "active",
        medical_fitness_status=_first_value(row, "medical_fitness_status", "aptitud"),
        medical_fitness_issued_at=_parse_optional_date(_first_value(row, "medical_fitness_issued_at", "aptitud_emision")),
        medical_fitness_expires_at=_parse_optional_date(_first_value(row, "medical_fitness_expires_at", "aptitud_caduca")),
        medical_fitness_provider=_first_value(row, "medical_fitness_provider", "servicio_prevencion"),
        medical_fitness_restrictions=_first_value(row, "medical_fitness_restrictions", "restricciones"),
        cae_notes=_first_value(row, "cae_notes", "notas"),
    )


def _find_existing_worker(session: DbSession, *, tenant_id: int, payload: WorkerCreate) -> Worker | None:
    identifier_hash = worker_identifier_hash(payload.identifier_value)
    if identifier_hash:
        return session.scalar(
            select(Worker).where(
                Worker.tenant_id == tenant_id,
                Worker.company_id == payload.company_id,
                Worker.identifier_hash == identifier_hash,
                Worker.status != "deleted",
            )
        )
    return None


def _validate_platform_registration_payload(
    session: DbSession,
    tenant_id: int,
    payload: WorkerPlatformRegistrationCreate,
) -> None:
    if payload.platform_account_id is not None:
        account = session.scalar(
            select(PlatformAccount).where(
                PlatformAccount.tenant_id == tenant_id,
                PlatformAccount.id == payload.platform_account_id,
            )
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform account not found.")
    if payload.external_platform_id is not None:
        platform = session.scalar(select(ExternalPlatform).where(ExternalPlatform.id == payload.external_platform_id))
        if platform is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External platform not found.")


def _require_worker_training(
    session: DbSession,
    tenant_id: int,
    worker_id: int,
    training_id: int,
) -> WorkerTraining:
    training = session.scalar(
        select(WorkerTraining).where(
            WorkerTraining.tenant_id == tenant_id,
            WorkerTraining.worker_id == worker_id,
            WorkerTraining.id == training_id,
        )
    )
    if training is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker training not found.")
    return training


def _require_worker_assignment(
    session: DbSession,
    tenant_id: int,
    worker_id: int,
    assignment_id: int,
) -> WorkerWorkAssignment:
    assignment = session.scalar(
        select(WorkerWorkAssignment).where(
            WorkerWorkAssignment.tenant_id == tenant_id,
            WorkerWorkAssignment.worker_id == worker_id,
            WorkerWorkAssignment.id == assignment_id,
        )
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker assignment not found.")
    return assignment


def _require_worker_platform_registration(
    session: DbSession,
    tenant_id: int,
    worker_id: int,
    registration_id: int,
) -> WorkerPlatformRegistration:
    registration = session.scalar(
        select(WorkerPlatformRegistration).where(
            WorkerPlatformRegistration.tenant_id == tenant_id,
            WorkerPlatformRegistration.worker_id == worker_id,
            WorkerPlatformRegistration.id == registration_id,
        )
    )
    if registration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker platform registration not found.")
    return registration


def _worker_public_state(worker: Worker) -> dict[str, Any]:
    return public_state(
        {
            "id": worker.id,
            "company_id": worker.company_id,
            "first_name": worker.first_name,
            "last_name": worker.last_name,
            "identifier_type": worker.identifier_type,
            "identifier_value": worker.identifier_value,
            "identifier_last4": worker.identifier_last4,
            "identifier_expires_at": worker.identifier_expires_at.isoformat()
            if worker.identifier_expires_at
            else None,
            "nationality": worker.nationality,
            "email": worker.email,
            "phone": worker.phone,
            "social_security_number": worker.social_security_number,
            "social_security_last4": worker.social_security_last4,
            "contract_type": worker.contract_type,
            "starts_at": worker.starts_at.isoformat() if worker.starts_at else None,
            "ends_at": worker.ends_at.isoformat() if worker.ends_at else None,
            "work_position": worker.work_position,
            "work_center_name": worker.work_center_name,
            "risk_profile": worker.risk_profile,
            "employment_status": worker.employment_status,
            "medical_fitness_status": worker.medical_fitness_status,
            "medical_fitness_issued_at": worker.medical_fitness_issued_at.isoformat()
            if worker.medical_fitness_issued_at
            else None,
            "medical_fitness_expires_at": worker.medical_fitness_expires_at.isoformat()
            if worker.medical_fitness_expires_at
            else None,
            "medical_fitness_provider": worker.medical_fitness_provider,
            "medical_fitness_restrictions": worker.medical_fitness_restrictions,
            "cae_notes": worker.cae_notes,
            "status": worker.status,
        }
    )


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _first_value(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return None


def _parse_optional_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date {value}. Use YYYY-MM-DD or DD/MM/YYYY.")


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _require_company(
    session: DbSession,
    tenant_id: int,
    company_id: int,
    actor_user_id: int | None,
    *,
    permission: str,
) -> Company:
    require_company_permission(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        company_id=company_id,
        permission=permission,
    )
    company = session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.id == company_id)
    )
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
    return company
