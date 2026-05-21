from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import or_, select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.connectors.base import ConnectorContext
from app.connectors.rpa.write_registry import implemented_write_connector_keys
from app.connectors.registry import get_connector
from app.db.models import (
    Document,
    DocumentType,
    DocumentVersion,
    ExternalDocumentStatus,
    ExternalPlatform,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    TransferAttempt,
    TransferJob,
    Worker,
    WorkerPlatformRegistration,
)
from app.schemas import TransferRead, TransferRequest
from app.services.audit import public_state, record_audit
from app.services.access_control import require_company_permission, require_tenant_wide_access
from app.services.manual_export import build_manual_export_zip
from app.services.platform_write_previews import WritePreviewError, build_write_operation_preview

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.get("", response_model=list[TransferRead])
def list_transfers(tenant_id: TenantId, session: DbSession, actor_user_id: ActorUserId) -> list[TransferRead]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    jobs = list(
        session.scalars(
            select(TransferJob).where(TransferJob.tenant_id == tenant_id).order_by(TransferJob.id.desc())
        )
    )
    return [_transfer_read(session, job) for job in jobs]


@router.post("", response_model=TransferRead, status_code=201)
async def create_transfer(
    payload: TransferRequest,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> TransferRead:
    require_tenant(session, tenant_id)
    platform = _get_platform(session, payload.platform_key)
    if payload.operation == "upsert_worker":
        return await _create_worker_transfer(payload, tenant_id, session, actor_user_id, platform)
    if payload.document_version_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_version_id is required for document transfers.",
        )
    version = _get_document_version(session, tenant_id, payload.document_version_id)
    document = session.get(Document, version.document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    _require_document_access(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        document=document,
        permission="document.write",
    )
    document_type = session.get(DocumentType, document.document_type_id)
    idempotency_key = (
        f"{tenant_id}:{platform.id}:{payload.operation}:{document.entity_type}:"
        f"{document.entity_id}:{version.sha256}"
    )
    job = TransferJob(
        tenant_id=tenant_id,
        external_platform_id=platform.id,
        connector_key=payload.connector_key,
        operation=payload.operation,
        status="created",
        dry_run=payload.dry_run,
        requires_approval=payload.manual_approval_required,
        idempotency_key=idempotency_key,
        started_at=datetime.now(timezone.utc),
    )
    session.add(job)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="transfer.before_external_action",
        entity_type="transfer_job",
        entity_id=job.id,
        after=public_state(
            {
                "platform_key": platform.platform_key,
                "connector_key": payload.connector_key,
                "dry_run": payload.dry_run,
                "manual_approval_required": payload.manual_approval_required,
                "idempotency_key": idempotency_key,
            }
        ),
    )

    connector = get_connector(payload.connector_key)
    context = ConnectorContext(
        tenant_id=str(tenant_id),
        platform_key=platform.platform_key,
        dry_run=payload.dry_run,
        manual_approval_required=payload.manual_approval_required,
        idempotency_key=idempotency_key,
    )
    result = await connector.upload_document(
        context,
        {
            "operation": payload.operation,
            "document_code": document_type.code if document_type is not None else None,
            "filename": version.filename,
            "sha256": version.sha256,
        },
    )
    job.status = result.status
    job.finished_at = datetime.now(timezone.utc)
    attempt = TransferAttempt(
        transfer_job_id=job.id,
        attempt_number=1,
        status=result.status,
        request_metadata={
            "document_version_id": version.id,
            "document_id": document.id,
            "operation": payload.operation,
        },
        response_metadata=result.model_dump(),
    )
    session.add(attempt)
    if _should_persist_external_status(result.external_status, result.evidence):
        session.add(
            ExternalDocumentStatus(
                tenant_id=tenant_id,
                external_platform_id=platform.id,
                document_version_id=version.id,
                status=result.external_status,
                external_comment=result.message,
            )
        )
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="transfer.after_external_action",
        entity_type="transfer_job",
        entity_id=job.id,
        after=public_state(result.model_dump()),
    )
    session.commit()
    session.refresh(job)
    return _transfer_read(session, job)


@router.post("/manual-export.zip")
async def create_manual_export_zip(
    payload: TransferRequest,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Response:
    if payload.connector_key != "connector_manual_export":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="manual-export.zip only supports connector_manual_export.",
        )
    job = await create_transfer(payload, tenant_id, session, actor_user_id)
    rows = [_manual_export_row(session, tenant_id=tenant_id, payload=payload)]
    package = build_manual_export_zip(rows)
    headers = {
        "Content-Disposition": f'attachment; filename="manual-export-job-{job.id}.zip"',
        "X-Transfer-Job-ID": str(job.id),
    }
    return Response(content=package, media_type="application/zip", headers=headers)


async def _create_worker_transfer(
    payload: TransferRequest,
    tenant_id: int,
    session: DbSession,
    actor_user_id: int | None,
    platform: ExternalPlatform,
) -> TransferRead:
    if payload.worker_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="worker_id is required for upsert_worker.",
        )
    live_write_requested = not payload.dry_run
    if live_write_requested and not _live_worker_write_supported(payload):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Live worker writes require a registered RPA write connector, manual approval "
                "and live_external_write_authorized=true."
            ),
        )
    if not live_write_requested and not payload.manual_approval_required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Worker platform writes require dry_run=true and manual_approval_required=true.",
        )
    worker = _get_worker_for_transfer(session, tenant_id=tenant_id, worker_id=payload.worker_id)
    require_company_permission(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        company_id=worker.company_id,
        permission="worker.write",
    )
    account_for_preflight = _get_account_for_worker_transfer(
        session,
        tenant_id=tenant_id,
        platform=platform,
        account_proposal_id=payload.account_proposal_id,
    )
    existing_registration = None
    if payload.connector_key != "connector_manual_export":
        existing_registration = _existing_worker_registration(
            session,
            tenant_id=tenant_id,
            worker=worker,
            platform=platform,
            account=account_for_preflight,
        )
    if existing_registration is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No se puede dar de alta el trabajador porque ya existe en esta plataforma/cuenta. "
                f"Estado actual: {existing_registration.registration_status}."
            ),
        )
    worker_payload = _worker_transfer_metadata(worker)
    account: PlatformRpaAccountProposal | None = account_for_preflight
    preview: dict[str, object] | None = None
    if live_write_requested:
        account = _get_account_for_live_worker_transfer(
            session,
            tenant_id=tenant_id,
            platform=platform,
            account_proposal_id=payload.account_proposal_id,
        )
        try:
            preview = build_write_operation_preview(
                session,
                tenant_id=tenant_id,
                account_proposal_id=account.id,
                operation="upsert_worker",
                company_id=worker.company_id,
                worker_id=worker.id,
            )
        except WritePreviewError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if preview.get("status") != "preview_ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Live worker write blocked because preview is not ready.",
            )
        planned_external_changes = preview.get("planned_external_changes")
        prepared_fields: list[str] = []
        if isinstance(planned_external_changes, list):
            prepared_fields = [
                str(item.get("standard_key")) for item in planned_external_changes if isinstance(item, dict)
            ]
        worker_payload.update(
            {
                "live_write_authorized": True,
                "account": _account_metadata(account),
                "prepared_fields": prepared_fields,
            }
        )
    idempotency_key = (
        f"{tenant_id}:{platform.id}:{payload.operation}:worker:"
        f"{worker.id}:{(worker.updated_at or worker.created_at).isoformat() if worker.updated_at or worker.created_at else 'new'}"
    )
    job = TransferJob(
        tenant_id=tenant_id,
        platform_account_id=account_for_preflight.platform_account_id if account_for_preflight else None,
        external_platform_id=platform.id,
        connector_key=payload.connector_key,
        operation=payload.operation,
        status="created",
        dry_run=not live_write_requested,
        requires_approval=True,
        idempotency_key=idempotency_key,
        started_at=datetime.now(timezone.utc),
    )
    session.add(job)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="transfer.before_external_action",
        entity_type="transfer_job",
        entity_id=job.id,
        after=public_state(
            {
                "platform_key": platform.platform_key,
                "connector_key": payload.connector_key,
                "operation": payload.operation,
                "entity_type": "worker",
                "entity_id": worker.id,
                "prepared_fields": worker_payload["prepared_fields"],
                "dry_run": not live_write_requested,
                "manual_approval_required": True,
                "account_proposal_id": account_for_preflight.id if account_for_preflight else None,
                "platform_account_id": account_for_preflight.platform_account_id if account_for_preflight else None,
                "preview_status": preview.get("status") if preview else None,
                "live_external_write_authorized": payload.live_external_write_authorized,
                "idempotency_key": idempotency_key,
            }
        ),
    )

    connector = get_connector(payload.connector_key)
    context = ConnectorContext(
        tenant_id=str(tenant_id),
        platform_key=platform.platform_key,
        dry_run=not live_write_requested,
        manual_approval_required=True,
        idempotency_key=idempotency_key,
    )
    result = await connector.upsert_worker(context, worker_payload)
    job.status = result.status
    job.finished_at = datetime.now(timezone.utc)
    attempt = TransferAttempt(
        transfer_job_id=job.id,
        attempt_number=1,
        status=result.status,
        request_metadata={
            "worker_id": worker.id,
            "operation": payload.operation,
            "entity_type": "worker",
            "prepared_fields": worker_payload["prepared_fields"],
            "account_proposal_id": account_for_preflight.id if account_for_preflight else None,
            "platform_account_id": account_for_preflight.platform_account_id if account_for_preflight else None,
        },
        response_metadata=result.model_dump(),
    )
    session.add(attempt)
    if payload.connector_key == "connector_demo" and result.external_status == "accepted":
        _upsert_demo_worker_registration(session, tenant_id=tenant_id, worker=worker, platform=platform)
    if payload.connector_key == "connector_rpa_seisconecta_write" and (
        result.evidence.get("external_write_executed") or result.evidence.get("post_write_read_confirmed")
    ):
        _upsert_live_worker_registration(session, tenant_id=tenant_id, worker=worker, platform=platform, result=result)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="transfer.after_external_action",
        entity_type="transfer_job",
        entity_id=job.id,
        after=public_state(result.model_dump()),
    )
    session.commit()
    session.refresh(job)
    return _transfer_read(session, job)


def _live_worker_write_supported(payload: TransferRequest) -> bool:
    return (
        payload.connector_key in implemented_write_connector_keys()
        and payload.operation == "upsert_worker"
        and payload.manual_approval_required
        and payload.live_external_write_authorized
    )


def _transfer_read(session: DbSession, job: TransferJob) -> TransferRead:
    payload = TransferRead.model_validate(job).model_dump()
    attempt = session.scalar(
        select(TransferAttempt)
        .where(TransferAttempt.transfer_job_id == job.id)
        .order_by(TransferAttempt.id.desc())
        .limit(1)
    )
    if attempt is not None:
        response = attempt.response_metadata or {}
        evidence = response.get("evidence") if isinstance(response, dict) else None
        evidence = evidence if isinstance(evidence, dict) else {}
        payload.update(
            {
                "last_attempt_status": attempt.status,
                "last_attempt_message": response.get("message") if isinstance(response, dict) else None,
                "post_write_read_confirmed": evidence.get("post_write_read_confirmed"),
                "valid_external_write": evidence.get("valid_external_write"),
                "status_artifact": evidence.get("post_write_readback_artifact") or evidence.get("status_artifact"),
            }
        )
    return TransferRead.model_validate(payload)


def _get_platform(session: DbSession, platform_key: str) -> ExternalPlatform:
    platform = session.scalar(
        select(ExternalPlatform).where(ExternalPlatform.platform_key == platform_key)
    )
    if platform is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found.")
    return platform


def _get_account_for_live_worker_transfer(
    session: DbSession,
    *,
    tenant_id: int,
    platform: ExternalPlatform,
    account_proposal_id: int | None,
) -> PlatformRpaAccountProposal:
    if account_proposal_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="account_proposal_id is required for live worker writes.",
        )
    account = session.scalar(
        select(PlatformRpaAccountProposal)
        .join(PlatformRpaManifest, PlatformRpaManifest.id == PlatformRpaAccountProposal.manifest_id)
        .where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.id == account_proposal_id,
            PlatformRpaManifest.external_platform_id == platform.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform account proposal not found.")
    if account.account_status != "active_in_source":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Live worker write blocked because the platform account is not active in source.",
        )
    return account


def _get_account_for_worker_transfer(
    session: DbSession,
    *,
    tenant_id: int,
    platform: ExternalPlatform,
    account_proposal_id: int | None,
) -> PlatformRpaAccountProposal | None:
    if account_proposal_id is None:
        return None
    account = session.scalar(
        select(PlatformRpaAccountProposal)
        .join(PlatformRpaManifest, PlatformRpaManifest.id == PlatformRpaAccountProposal.manifest_id)
        .where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.id == account_proposal_id,
            PlatformRpaManifest.external_platform_id == platform.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform account proposal not found.")
    return account


def _existing_worker_registration(
    session: DbSession,
    *,
    tenant_id: int,
    worker: Worker,
    platform: ExternalPlatform,
    account: PlatformRpaAccountProposal | None,
) -> WorkerPlatformRegistration | None:
    existing_statuses = {
        "accepted",
        "accepted_with_warnings",
        "confirmed",
        "submitted",
        "submitted_pending_readback",
        "pending_external_validation",
        "review_required",
        "missing_required_document",
    }
    statement = select(WorkerPlatformRegistration).where(
        WorkerPlatformRegistration.tenant_id == tenant_id,
        WorkerPlatformRegistration.worker_id == worker.id,
        WorkerPlatformRegistration.external_platform_id == platform.id,
        WorkerPlatformRegistration.registration_status.in_(existing_statuses),
    )
    if account is not None and account.platform_account_id is not None:
        statement = statement.where(
            or_(
                WorkerPlatformRegistration.platform_account_id == account.platform_account_id,
                WorkerPlatformRegistration.platform_account_id.is_(None),
            )
        )
    registration = session.scalar(statement.order_by(WorkerPlatformRegistration.id.desc()).limit(1))
    if registration is not None:
        return registration
    return None


def _account_metadata(account: PlatformRpaAccountProposal) -> dict[str, object]:
    return {
        "account_proposal_id": account.id,
        "platform_account_id": account.platform_account_id,
        "source_platform_account_id": account.source_platform_account_id,
        "external_company_name": account.external_company_name,
        "entry_url": account.entry_url,
        "host": account.host,
        "credential_secret_ref": account.credential_secret_ref,
        "account_status": account.account_status,
        "status": account.status,
    }


def _should_persist_external_status(external_status: str, evidence: dict[str, object]) -> bool:
    if evidence.get("persist_external_status") is False:
        return False
    return external_status in {"accepted", "rejected", "expired", "valid", "invalid"}


def _get_document_version(
    session: DbSession,
    tenant_id: int,
    document_version_id: int,
) -> DocumentVersion:
    version = session.get(DocumentVersion, document_version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    document = session.get(Document, version.document_id)
    if document is None or document.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    return version


def _get_worker_for_transfer(session: DbSession, *, tenant_id: int, worker_id: int) -> Worker:
    worker = session.scalar(select(Worker).where(Worker.tenant_id == tenant_id, Worker.id == worker_id))
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found.")
    return worker


def _worker_transfer_metadata(worker: Worker) -> dict[str, object]:
    prepared_fields = [
        "worker_ref",
        "first_name",
        "last_name",
        "identifier_type",
        "identifier_last4",
        "employment_status",
        "work_position",
        "work_center_name",
        "medical_fitness_status",
        "medical_fitness_expires_at",
    ]
    return {
        "worker_ref": str(worker.id),
        "first_name": worker.first_name,
        "last_name": worker.last_name,
        "identifier_type": worker.identifier_type,
        "identifier_value": worker.identifier_value,
        "identifier_last4": worker.identifier_last4,
        "nationality": worker.nationality,
        "contract_type": worker.contract_type,
        "employment_status": worker.employment_status,
        "work_position": worker.work_position,
        "work_center_name": worker.work_center_name,
        "medical_fitness_status": worker.medical_fitness_status,
        "medical_fitness_expires_at": worker.medical_fitness_expires_at.isoformat()
        if worker.medical_fitness_expires_at is not None
        else None,
        "prepared_fields": prepared_fields,
    }


def _upsert_demo_worker_registration(
    session: DbSession,
    *,
    tenant_id: int,
    worker: Worker,
    platform: ExternalPlatform,
) -> WorkerPlatformRegistration:
    registration = session.scalar(
        select(WorkerPlatformRegistration).where(
            WorkerPlatformRegistration.tenant_id == tenant_id,
            WorkerPlatformRegistration.worker_id == worker.id,
            WorkerPlatformRegistration.external_platform_id == platform.id,
        )
    )
    if registration is None:
        registration = WorkerPlatformRegistration(
            tenant_id=tenant_id,
            worker_id=worker.id,
            external_platform_id=platform.id,
            platform_name=platform.name,
            external_worker_id=f"demo-worker-{worker.id}",
            registration_status="accepted",
            assignment_scope=worker.work_center_name,
            source="connector_demo",
            last_synced_at=datetime.now(timezone.utc),
            notes="Alta validada contra simulador local en dry_run; sin escritura externa.",
        )
        session.add(registration)
    else:
        registration.registration_status = "accepted"
        registration.external_worker_id = registration.external_worker_id or f"demo-worker-{worker.id}"
        registration.assignment_scope = worker.work_center_name
        registration.source = "connector_demo"
        registration.last_synced_at = datetime.now(timezone.utc)
        registration.notes = "Alta validada contra simulador local en dry_run; sin escritura externa."
    return registration


def _upsert_live_worker_registration(
    session: DbSession,
    *,
    tenant_id: int,
    worker: Worker,
    platform: ExternalPlatform,
    result: object,
) -> WorkerPlatformRegistration:
    registration = session.scalar(
        select(WorkerPlatformRegistration).where(
            WorkerPlatformRegistration.tenant_id == tenant_id,
            WorkerPlatformRegistration.worker_id == worker.id,
            WorkerPlatformRegistration.external_platform_id == platform.id,
        )
    )
    evidence = getattr(result, "evidence", {}) if result is not None else {}
    read_confirmed = bool(evidence.get("post_write_read_confirmed"))
    platform_account_id = evidence.get("platform_account_id")
    external_worker_id = evidence.get("external_worker_id")
    try:
        platform_account_id_int = int(platform_account_id) if platform_account_id is not None else None
    except (TypeError, ValueError):
        platform_account_id_int = None
    write_executed = bool(evidence.get("external_write_executed"))
    registration_status = "confirmed" if read_confirmed else "submitted_pending_readback"
    if read_confirmed and write_executed:
        notes = "Alta enviada y confirmada por lectura posterior en navegador visible autorizado."
    elif read_confirmed:
        notes = "Trabajador existente confirmado por lectura posterior; no se ha repetido el alta."
    else:
        notes = "Alta enviada en navegador visible autorizado; pendiente de lectura posterior confirmada."
    if registration is None:
        registration = WorkerPlatformRegistration(
            tenant_id=tenant_id,
            worker_id=worker.id,
            external_platform_id=platform.id,
            platform_account_id=platform_account_id_int,
            platform_name=platform.name,
            external_worker_id=str(external_worker_id) if external_worker_id else None,
            registration_status=registration_status,
            assignment_scope=worker.work_center_name or worker.work_position,
            source="connector_rpa_seisconecta_write",
            last_synced_at=datetime.now(timezone.utc),
            notes=f"{notes} Evidencia: {evidence.get('status_artifact')}",
        )
        session.add(registration)
    else:
        registration.registration_status = registration_status
        registration.platform_account_id = registration.platform_account_id or platform_account_id_int
        if external_worker_id:
            registration.external_worker_id = str(external_worker_id)
        registration.assignment_scope = worker.work_center_name or worker.work_position
        registration.source = "connector_rpa_seisconecta_write"
        registration.last_synced_at = datetime.now(timezone.utc)
        registration.notes = f"{notes} Evidencia: {evidence.get('status_artifact')}"
    return registration


def _manual_export_row(session: DbSession, *, tenant_id: int, payload: TransferRequest) -> dict[str, str]:
    if payload.operation == "upsert_worker":
        if payload.worker_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="worker_id is required for upsert_worker.",
            )
        worker = _get_worker_for_transfer(session, tenant_id=tenant_id, worker_id=payload.worker_id)
        return {
            "operation": payload.operation,
            "tenant_id": str(tenant_id),
            "platform_key": payload.platform_key,
            "entity_type": "worker",
            "entity_id": str(worker.id),
            "worker_display": f"{worker.first_name} {worker.last_name}",
            "identifier_last4": worker.identifier_last4 or "",
            "work_position": worker.work_position or "",
            "document_code": "",
            "filename": "",
            "sha256": "",
            "expires_at": "",
        }
    if payload.document_version_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_version_id is required for document transfers.",
        )
    version = _get_document_version(session, tenant_id, payload.document_version_id)
    document = session.get(Document, version.document_id)
    document_type = session.get(DocumentType, document.document_type_id) if document is not None else None
    return {
        "operation": payload.operation,
        "tenant_id": str(tenant_id),
        "platform_key": payload.platform_key,
        "entity_type": document.entity_type if document is not None else "",
        "entity_id": str(document.entity_id) if document is not None else "",
        "worker_display": "",
        "identifier_last4": "",
        "work_position": "",
        "document_code": document_type.code if document_type is not None else "",
        "filename": version.filename,
        "sha256": version.sha256,
        "expires_at": version.expires_at.isoformat() if version.expires_at is not None else "",
    }


def _require_document_access(
    session: DbSession,
    *,
    tenant_id: int,
    user_id: int | None,
    document: Document,
    permission: str,
) -> None:
    if document.entity_type == "company":
        require_company_permission(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            company_id=document.entity_id,
            permission=permission,
        )
        return
    if document.entity_type == "worker":
        worker = session.scalar(select(Worker).where(Worker.tenant_id == tenant_id, Worker.id == document.entity_id))
        if worker is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found.")
        require_company_permission(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            company_id=worker.company_id,
            permission=permission,
        )
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Entity access denied.")
