from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Literal, cast

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import Document, DocumentType, DocumentVersion, Worker
from app.schemas import (
    DocumentCreate,
    DocumentRead,
    DocumentTypeCreate,
    DocumentTypeRead,
    DocumentVersionCreate,
    DocumentVersionRead,
)
from app.services.audit import public_state, record_audit
from app.services.access_control import (
    accessible_company_ids_for_permission,
    require_company_permission,
    require_tenant_wide_access,
)
from app.services.document_storage import (
    StoredFileNotFound,
    StoredFileTooLarge,
    resolve_storage_key,
    store_upload_file,
)

router = APIRouter(prefix="/documents", tags=["documents"])
types_router = APIRouter(prefix="/document-types", tags=["document-types"])
UploadSource = Literal["manual", "import", "ocr", "demo"]
ExpiryReviewStatus = Literal["ok", "review_required", "reviewed"]


@types_router.get("", response_model=list[DocumentTypeRead])
def list_document_types(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[DocumentType]:
    require_tenant(session, tenant_id)
    return list(
        session.scalars(
            select(DocumentType)
            .where(or_(DocumentType.tenant_id.is_(None), DocumentType.tenant_id == tenant_id))
            .order_by(DocumentType.entity_scope, DocumentType.code)
        )
    )


@types_router.post("", response_model=DocumentTypeRead, status_code=201)
def create_document_type(
    payload: DocumentTypeCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> DocumentType:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    document_type = DocumentType(tenant_id=tenant_id, **payload.model_dump())
    session.add(document_type)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="document_type.create",
        entity_type="document_type",
        entity_id=document_type.id,
        after=public_state(payload.model_dump() | {"id": document_type.id}),
    )
    session.commit()
    session.refresh(document_type)
    return document_type


@router.get("", response_model=list[DocumentRead])
def list_documents(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None),
) -> list[Document]:
    require_tenant(session, tenant_id)
    statement = select(Document).where(Document.tenant_id == tenant_id)
    if entity_type is not None:
        statement = statement.where(Document.entity_type == entity_type)
    if entity_id is not None:
        statement = statement.where(Document.entity_id == entity_id)
    if company_id is not None:
        require_company_permission(
            session,
            tenant_id=tenant_id,
            user_id=actor_user_id,
            company_id=company_id,
            permission="document.read",
        )
        statement = statement.where(_documents_for_company_ids(tenant_id, [company_id]))
    else:
        allowed_company_ids = accessible_company_ids_for_permission(
            session,
            tenant_id=tenant_id,
            user_id=actor_user_id,
            permission="document.read",
        )
        if allowed_company_ids is not None:
            statement = statement.where(_documents_for_company_ids(tenant_id, allowed_company_ids))
    return list(session.scalars(statement.order_by(Document.id)))


@router.post("", response_model=DocumentRead, status_code=201)
def create_document(
    payload: DocumentCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> Document:
    require_tenant(session, tenant_id)
    _require_document_type(session, tenant_id, payload.document_type_id)
    _require_document_entity_access(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        permission="document.write",
    )
    document = Document(tenant_id=tenant_id, **payload.model_dump())
    session.add(document)
    session.flush()
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="document.create",
        entity_type="document",
        entity_id=document.id,
        after=public_state(payload.model_dump() | {"id": document.id}),
    )
    session.commit()
    session.refresh(document)
    return document


@router.post("/{document_id}/versions", response_model=DocumentVersionRead, status_code=201)
def create_document_version(
    document_id: int,
    payload: DocumentVersionCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> DocumentVersion:
    require_tenant(session, tenant_id)
    document = session.scalar(
        select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    _require_document_access(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        document=document,
        permission="document.write",
    )

    version = _create_version_from_payload(session, tenant_id, document, payload, actor_user_id)
    session.commit()
    session.refresh(version)
    return version


@router.post("/{document_id}/upload", response_model=DocumentVersionRead, status_code=201)
async def upload_document_version(
    document_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    file: UploadFile = File(...),
    issued_at: date | None = Form(default=None),
    expires_at: date | None = Form(default=None),
    platform_expires_at: date | None = Form(default=None),
    platform_expiry_source: str | None = Form(default=None),
    source: str = Form(default="manual"),
    created_by: int | None = Form(default=None),
) -> DocumentVersion:
    require_tenant(session, tenant_id)
    if source not in {"manual", "import", "ocr", "demo"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File upload source must be manual, import, ocr or demo.",
        )
    document = session.scalar(
        select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    _require_document_access(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        document=document,
        permission="document.write",
    )

    try:
        stored = await store_upload_file(file, tenant_id=tenant_id, document_id=document_id)
    except StoredFileTooLarge as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc

    payload = DocumentVersionCreate(
        file_storage_key=stored.storage_key,
        sha256=stored.sha256,
        filename=stored.filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        issued_at=issued_at,
        expires_at=expires_at,
        platform_expires_at=platform_expires_at,
        expiry_review_status=_expiry_review_status(expires_at, platform_expires_at),
        platform_expiry_source=platform_expiry_source,
        source=cast(UploadSource, source),
        created_by=created_by,
    )
    version = _create_version_from_payload(session, tenant_id, document, payload, actor_user_id)
    session.commit()
    session.refresh(version)
    return version


@router.get("/{document_id}/versions/{version_id}/download")
def download_document_version(
    document_id: int,
    version_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> FileResponse:
    document = session.scalar(
        select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    _require_document_access(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        document=document,
        permission="document.read",
    )
    version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.id == version_id,
        )
    )
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    try:
        path = resolve_storage_key(version.file_storage_key)
    except StoredFileNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="document_version.download",
        entity_type="document_version",
        entity_id=version.id,
        after=public_state(
            {
                "document_id": document.id,
                "version_id": version.id,
                "filename": version.filename,
                "sha256": version.sha256,
            }
        ),
    )
    session.commit()
    return FileResponse(path=path, filename=version.filename, media_type=version.mime_type)


def _create_version_from_payload(
    session: DbSession,
    tenant_id: int,
    document: Document,
    payload: DocumentVersionCreate,
    actor_user_id: int | None,
) -> DocumentVersion:
    current_max = session.scalar(
        select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document.id)
    )
    version_payload = payload.model_dump()
    if version_payload["expiry_review_status"] == "ok":
        version_payload["expiry_review_status"] = _expiry_review_status(
            payload.expires_at,
            payload.platform_expires_at,
        )
    version = DocumentVersion(
        document_id=document.id,
        version_number=(current_max or 0) + 1,
        **version_payload,
    )
    session.add(version)
    session.flush()
    document.current_version_id = version.id
    document.status_internal = _document_status_from_version(version)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="document_version.create",
        entity_type="document",
        entity_id=document.id,
        after=public_state(
            version_payload
            | {
                "document_id": document.id,
                "version_id": version.id,
                "version_number": version.version_number,
                "status_internal": document.status_internal,
            }
        ),
    )
    return version


def _expiry_review_status(expires_at: date | None, platform_expires_at: date | None) -> ExpiryReviewStatus:
    if platform_expires_at is None:
        return "ok"
    if expires_at != platform_expires_at:
        return "review_required"
    return "ok"


def _document_status_from_version(version: DocumentVersion) -> str:
    if version.expires_at and version.expires_at < date.today():
        return "expired"
    if version.expiry_review_status == "review_required":
        return "pending_internal_review"
    return "valid_internal"


@router.get("/{document_id}/versions", response_model=list[DocumentVersionRead])
def list_document_versions(
    document_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[DocumentVersion]:
    document = session.scalar(
        select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    _require_document_access(
        session,
        tenant_id=tenant_id,
        user_id=actor_user_id,
        document=document,
        permission="document.read",
    )
    return list(
        session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number)
        )
    )


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


def _documents_for_company_ids(tenant_id: int, company_ids: Sequence[int]) -> ColumnElement[bool]:
    company_ids = list(company_ids)
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


def _require_document_access(
    session: DbSession,
    *,
    tenant_id: int,
    user_id: int | None,
    document: Document,
    permission: str,
) -> None:
    _require_document_entity_access(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        entity_type=document.entity_type,
        entity_id=document.entity_id,
        permission=permission,
    )
