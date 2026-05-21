from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import Document, DocumentIntake, DocumentType, DocumentVersion, Worker
from app.schemas import (
    DocumentIntakeApprove,
    DocumentIntakeBulkSkipped,
    DocumentIntakeBulkUploadRead,
    DocumentIntakeRead,
    DocumentVersionCreate,
    DocumentVersionRead,
)
from app.services.access_control import (
    accessible_company_ids_for_permission,
    require_company_permission,
    require_tenant_wide_access,
)
from app.services.audit import public_state, record_audit
from app.services.document_storage import StoredFile, StoredFileTooLarge, store_intake_bytes, store_intake_file
from app.services.ocr_intake import analyze_document_intake

router = APIRouter(prefix="/document-intake", tags=["document-intake"])

SUPPORTED_BULK_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".txt",
    ".csv",
    ".md",
}
MAX_BULK_FILES = 120
MAX_ZIP_DEPTH = 2


@dataclass(frozen=True)
class BulkMember:
    filename: str
    content: bytes
    mime_type: str


@dataclass(frozen=True)
class SkippedMember:
    filename: str
    reason: str


@router.get("", response_model=list[DocumentIntakeRead])
def list_document_intakes(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[DocumentIntake]:
    require_tenant(session, tenant_id)
    statement = select(DocumentIntake).where(DocumentIntake.tenant_id == tenant_id)
    if status_filter is not None:
        statement = statement.where(DocumentIntake.status == status_filter)
    allowed_company_ids = accessible_company_ids_for_permission(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        permission="document.read",
    )
    if allowed_company_ids is not None:
        statement = statement.where(
            or_(
                DocumentIntake.predicted_company_id.in_(allowed_company_ids),
                DocumentIntake.requested_company_id.in_(allowed_company_ids),
            )
        )
    return list(session.scalars(statement.order_by(DocumentIntake.id.desc())))


@router.post("/upload", response_model=DocumentIntakeRead, status_code=201)
async def upload_document_intake(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    file: UploadFile = File(...),
    intake_scope: str = Form(default="auto"),
    target_company_id: int | None = Form(default=None),
    target_worker_id: int | None = Form(default=None),
    target_notes: str | None = Form(default=None),
) -> DocumentIntake:
    require_tenant(session, tenant_id)
    scope = _normalize_intake_scope(intake_scope)
    try:
        stored = await store_intake_file(file, tenant_id=tenant_id)
    except StoredFileTooLarge as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    intake = _create_pending_intake(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        stored=stored,
        scope=scope,
        target_company_id=target_company_id,
        target_worker_id=target_worker_id,
        target_notes=target_notes,
    )
    session.add(intake)
    session.flush()
    _audit_intake_upload(session, tenant_id=tenant_id, actor_user_id=actor_user_id, intake=intake)
    session.commit()
    session.refresh(intake)
    return intake


@router.post("/bulk-upload", response_model=DocumentIntakeBulkUploadRead, status_code=201)
async def bulk_upload_document_intake(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    file: UploadFile = File(...),
    intake_scope: str = Form(default="auto"),
    target_company_id: int | None = Form(default=None),
    target_notes: str | None = Form(default=None),
) -> DocumentIntakeBulkUploadRead:
    require_tenant(session, tenant_id)
    scope = _normalize_intake_scope(intake_scope)
    if scope == "single_worker":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bulk-upload does not support single_worker scope; use upload for one worker.",
        )
    if scope in {"company", "multiple_workers"} and target_company_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="target_company_id is required for company or multiple_workers bulk upload.",
        )
    if target_company_id is not None:
        _require_target_company(session, tenant_id, target_company_id, actor_user_id)

    archive_bytes = await file.read()
    await file.close()
    try:
        members, skipped = _extract_bulk_members(
            archive_bytes,
            archive_name=file.filename or "documents.zip",
        )
    except BadZipFile as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded file is not a valid ZIP.") from exc
    if not members:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ZIP contains no supported documents.")

    intakes: list[DocumentIntake] = []
    for member in members:
        try:
            stored = store_intake_bytes(
                member.content,
                tenant_id=tenant_id,
                filename=member.filename,
                mime_type=member.mime_type,
            )
        except StoredFileTooLarge:
            skipped.append(SkippedMember(filename=member.filename, reason="file_exceeds_max_upload_bytes"))
            continue
        intake = _create_pending_intake(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            stored=stored,
            scope=scope,
            target_company_id=target_company_id,
            target_worker_id=None,
            target_notes=target_notes,
        )
        session.add(intake)
        session.flush()
        _audit_intake_upload(session, tenant_id=tenant_id, actor_user_id=actor_user_id, intake=intake, bulk=True)
        intakes.append(intake)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="document_intake.bulk_upload",
        entity_type="document_intake_batch",
        entity_id=None,
        after=public_state(
            {
                "archive_filename": file.filename,
                "created_count": len(intakes),
                "skipped_count": len(skipped),
                "intake_scope": scope,
                "target_company_id": target_company_id,
            }
        ),
    )
    session.commit()
    intake_ids = [item.id for item in intakes]
    refreshed = list(
        session.scalars(
            select(DocumentIntake)
            .where(DocumentIntake.tenant_id == tenant_id, DocumentIntake.id.in_(intake_ids))
            .order_by(DocumentIntake.id)
        )
    )
    return DocumentIntakeBulkUploadRead(
        total_entries=len(members) + len(skipped),
        created_count=len(refreshed),
        skipped_count=len(skipped),
        intakes=[DocumentIntakeRead.model_validate(item) for item in refreshed],
        skipped=[DocumentIntakeBulkSkipped(filename=item.filename, reason=item.reason) for item in skipped],
    )


@router.get("/{intake_id}", response_model=DocumentIntakeRead)
def get_document_intake(
    intake_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> DocumentIntake:
    intake = _require_intake(session, tenant_id, intake_id)
    company_id = intake.predicted_company_id or intake.requested_company_id
    if company_id is not None:
        require_company_permission(
            session,
            tenant_id=tenant_id,
            user_id=actor_user_id,
            company_id=company_id,
            permission="document.read",
        )
    else:
        require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return intake


@router.post("/{intake_id}/approve", response_model=DocumentVersionRead, status_code=201)
def approve_document_intake(
    intake_id: int,
    payload: DocumentIntakeApprove,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> DocumentVersion:
    intake = _require_intake(session, tenant_id, intake_id)
    if intake.status != "pending_review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document intake is already reviewed.")
    document_type_id = payload.document_type_id or intake.predicted_document_type_id
    entity_type = payload.entity_type or intake.predicted_entity_type
    entity_id = payload.entity_id or intake.predicted_entity_id
    if document_type_id is None or entity_type is None or entity_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Document type and entity are required.")
    document_type = _require_document_type(session, tenant_id, document_type_id)
    _require_document_entity_access(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        permission="document.write",
    )
    document = _ensure_document(
        session,
        tenant_id=tenant_id,
        document_type_id=document_type.id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    version = _create_version_from_intake(
        session,
        document=document,
        payload=DocumentVersionCreate(
            file_storage_key=intake.file_storage_key,
            sha256=intake.sha256,
            filename=intake.original_filename,
            mime_type=intake.mime_type,
            size_bytes=intake.size_bytes,
            issued_at=payload.issued_at or intake.issued_at,
            expires_at=payload.expires_at or intake.expires_at,
            source="ocr",
            created_by=actor_user_id,
        ),
    )
    intake.status = "accepted"
    intake.created_document_id = document.id
    intake.created_version_id = version.id
    intake.review_comment = payload.review_comment
    intake.reviewed_at = datetime.now(timezone.utc)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="document_intake.approve",
        entity_type="document_intake",
        entity_id=intake.id,
        after=public_state(
            {
                "intake_id": intake.id,
                "document_id": document.id,
                "version_id": version.id,
                "document_type_id": document_type.id,
                "entity_type": entity_type,
                "entity_id": entity_id,
            }
        ),
    )
    session.commit()
    session.refresh(version)
    return version


def _require_intake(session: DbSession, tenant_id: int, intake_id: int) -> DocumentIntake:
    intake = session.scalar(select(DocumentIntake).where(DocumentIntake.tenant_id == tenant_id, DocumentIntake.id == intake_id))
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document intake not found.")
    return intake


def _require_document_type(session: DbSession, tenant_id: int, document_type_id: int) -> DocumentType:
    document_type = session.scalar(
        select(DocumentType).where(
            DocumentType.id == document_type_id,
            or_(DocumentType.tenant_id.is_(None), DocumentType.tenant_id == tenant_id),
        )
    )
    if document_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document type not found.")
    return document_type


def _normalize_intake_scope(value: str) -> str:
    normalized = value.strip().lower()
    allowed = {"auto", "company", "single_worker", "multiple_workers"}
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"intake_scope must be one of: {', '.join(sorted(allowed))}.",
        )
    return normalized


def _create_pending_intake(
    session: DbSession,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    stored: StoredFile,
    scope: str,
    target_company_id: int | None,
    target_worker_id: int | None,
    target_notes: str | None,
) -> DocumentIntake:
    analysis = analyze_document_intake(session, tenant_id=tenant_id, stored_file=stored)
    predicted_document_type_id = analysis.predicted_document_type_id
    predicted_entity_type = analysis.predicted_entity_type
    predicted_entity_id = analysis.predicted_entity_id
    predicted_company_id = analysis.predicted_company_id
    predicted_worker_id = analysis.predicted_worker_id
    confidence = analysis.confidence
    classification_json = dict(analysis.classification_json)
    signals_json = dict(analysis.signals_json)
    signals_json["requested_scope"] = scope
    if target_notes:
        signals_json["target_notes"] = target_notes

    if scope == "single_worker":
        if target_worker_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="target_worker_id is required when intake_scope is single_worker.",
            )
        worker = _require_target_worker(session, tenant_id, target_worker_id, actor_user_id)
        if target_company_id is not None and worker.company_id != target_company_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="target_company_id does not match target_worker_id company.",
            )
        target_company_id = worker.company_id
        predicted_entity_type = "worker"
        predicted_entity_id = worker.id
        predicted_company_id = worker.company_id
        predicted_worker_id = worker.id
        confidence = max(confidence, 85)
        classification_json["target_override"] = "single_worker"
    elif scope == "company":
        if target_company_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="target_company_id is required when intake_scope is company.",
            )
        _require_target_company(session, tenant_id, target_company_id, actor_user_id)
        predicted_entity_type = "company"
        predicted_entity_id = target_company_id
        predicted_company_id = target_company_id
        predicted_worker_id = None
        confidence = max(confidence, 80)
        classification_json["target_override"] = "company"
    elif scope == "multiple_workers":
        if target_company_id is not None:
            _require_target_company(session, tenant_id, target_company_id, actor_user_id)
            predicted_company_id = target_company_id
        predicted_entity_type = None
        predicted_entity_id = None
        predicted_worker_id = None
        signals_json["requires_batch_review"] = True
        classification_json["target_override"] = "multiple_workers"

    if predicted_company_id is not None:
        require_company_permission(
            session,
            tenant_id=tenant_id,
            user_id=actor_user_id,
            company_id=predicted_company_id,
            permission="document.write",
        )
    return DocumentIntake(
        tenant_id=tenant_id,
        uploaded_by=actor_user_id,
        original_filename=stored.filename,
        file_storage_key=stored.storage_key,
        sha256=stored.sha256,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        status="pending_review",
        intake_scope=scope,
        requested_company_id=target_company_id,
        requested_worker_id=target_worker_id,
        target_notes=target_notes,
        extraction_engine=analysis.extraction_engine,
        extracted_text_excerpt=analysis.extracted_text_excerpt,
        text_confidence=analysis.text_confidence,
        predicted_document_type_id=predicted_document_type_id,
        predicted_entity_type=predicted_entity_type,
        predicted_entity_id=predicted_entity_id,
        predicted_company_id=predicted_company_id,
        predicted_worker_id=predicted_worker_id,
        issued_at=analysis.issued_at,
        expires_at=analysis.expires_at,
        confidence=confidence,
        classification_json=classification_json,
        signals_json=signals_json,
    )


def _audit_intake_upload(
    session: DbSession,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    intake: DocumentIntake,
    bulk: bool = False,
) -> None:
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="document_intake.bulk_item_upload" if bulk else "document_intake.upload",
        entity_type="document_intake",
        entity_id=intake.id,
        after=public_state(
            {
                "id": intake.id,
                "filename": intake.original_filename,
                "sha256": intake.sha256,
                "confidence": intake.confidence,
                "intake_scope": intake.intake_scope,
                "requested_company_id": intake.requested_company_id,
                "requested_worker_id": intake.requested_worker_id,
                "predicted_document_type_id": intake.predicted_document_type_id,
                "predicted_entity_type": intake.predicted_entity_type,
                "predicted_entity_id": intake.predicted_entity_id,
            }
        ),
    )


def _extract_bulk_members(
    archive_content: bytes,
    *,
    archive_name: str,
    depth: int = 0,
) -> tuple[list[BulkMember], list[SkippedMember]]:
    if depth > MAX_ZIP_DEPTH:
        return [], [SkippedMember(filename=archive_name, reason="max_nested_zip_depth_exceeded")]
    from io import BytesIO

    members: list[BulkMember] = []
    skipped: list[SkippedMember] = []
    with ZipFile(BytesIO(archive_content)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if _unsafe_zip_member(name):
                skipped.append(SkippedMember(filename=name, reason="unsafe_zip_path"))
                continue
            suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if suffix == ".zip":
                nested_content = archive.read(info)
                nested_members, nested_skipped = _extract_bulk_members(
                    nested_content,
                    archive_name=name,
                    depth=depth + 1,
                )
                members.extend(nested_members)
                skipped.extend(nested_skipped)
            elif suffix in SUPPORTED_BULK_EXTENSIONS:
                mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
                members.append(BulkMember(filename=name, content=archive.read(info), mime_type=mime_type))
            else:
                skipped.append(SkippedMember(filename=name, reason="unsupported_extension"))
            if len(members) >= MAX_BULK_FILES:
                skipped.append(SkippedMember(filename=archive_name, reason="max_bulk_files_reached"))
                break
    return members, skipped


def _unsafe_zip_member(name: str) -> bool:
    parts = [part for part in name.split("/") if part]
    return not parts or any(part == ".." for part in parts) or name.startswith("/")


def _require_target_company(
    session: DbSession,
    tenant_id: int,
    company_id: int,
    actor_user_id: int | None,
) -> None:
    require_company_permission(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        company_id=company_id,
        permission="document.write",
    )


def _require_target_worker(
    session: DbSession,
    tenant_id: int,
    worker_id: int,
    actor_user_id: int | None,
) -> Worker:
    worker = session.scalar(select(Worker).where(Worker.tenant_id == tenant_id, Worker.id == worker_id))
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found.")
    require_company_permission(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        company_id=worker.company_id,
        permission="document.write",
    )
    return worker


def _ensure_document(
    session: DbSession,
    *,
    tenant_id: int,
    document_type_id: int,
    entity_type: str,
    entity_id: int,
) -> Document:
    document = session.scalar(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.document_type_id == document_type_id,
            Document.entity_type == entity_type,
            Document.entity_id == entity_id,
        )
    )
    if document is not None:
        return document
    document = Document(
        tenant_id=tenant_id,
        document_type_id=document_type_id,
        entity_type=entity_type,
        entity_id=entity_id,
        status_internal="draft",
    )
    session.add(document)
    session.flush()
    return document


def _create_version_from_intake(
    session: DbSession,
    *,
    document: Document,
    payload: DocumentVersionCreate,
) -> DocumentVersion:
    current_max = session.scalar(select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document.id))
    version = DocumentVersion(
        document_id=document.id,
        version_number=(current_max or 0) + 1,
        **payload.model_dump(),
    )
    session.add(version)
    session.flush()
    document.current_version_id = version.id
    document.status_internal = "expired" if version.expires_at and version.expires_at < date.today() else "valid_internal"
    return version


def _require_document_entity_access(
    session: DbSession,
    *,
    tenant_id: int,
    user_id: int | None,
    entity_type: str,
    entity_id: int,
    permission: str,
) -> None:
    if entity_type == "company":
        require_company_permission(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            company_id=entity_id,
            permission=permission,
        )
        return
    if entity_type == "worker":
        worker = session.scalar(select(Worker).where(Worker.tenant_id == tenant_id, Worker.id == entity_id))
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
