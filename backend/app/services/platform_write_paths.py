from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    PlatformReviewRun,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformWritePath,
)
from app.services.platform_edit_methods import EDITABLE_OPERATION_REQUIRED_KEYS
from app.services.rpa_gateway import CAPTURE_WRITE_SCREEN_ACTION

APPROVED_WRITE_PATH_STATUS = "approved"
PENDING_WRITE_PATH_STATUS = "pending_review"
REJECTED_WRITE_PATH_STATUS = "rejected"
WRITE_PATH_REVIEW_STATUSES = {
    APPROVED_WRITE_PATH_STATUS,
    PENDING_WRITE_PATH_STATUS,
    REJECTED_WRITE_PATH_STATUS,
    "needs_capture_refresh",
}


class PlatformWritePathError(ValueError):
    pass


def list_write_paths(
    session: Session,
    *,
    tenant_id: int,
    account_proposal_id: int | None = None,
    manifest_id: int | None = None,
    operation: str | None = None,
    review_status: str | None = None,
) -> list[PlatformWritePath]:
    statement = select(PlatformWritePath).where(PlatformWritePath.tenant_id == tenant_id)
    if account_proposal_id is not None:
        statement = statement.where(PlatformWritePath.account_proposal_id == account_proposal_id)
    if manifest_id is not None:
        statement = statement.where(PlatformWritePath.manifest_id == manifest_id)
    if operation is not None:
        statement = statement.where(PlatformWritePath.operation == operation)
    if review_status is not None:
        statement = statement.where(PlatformWritePath.review_status == review_status)
    return list(
        session.scalars(
            statement.order_by(
                PlatformWritePath.review_status,
                PlatformWritePath.operation,
                PlatformWritePath.path_label,
                PlatformWritePath.id,
            )
        )
    )


def upsert_write_path_for_account(
    session: Session,
    *,
    tenant_id: int,
    account_proposal_id: int,
    operation: str,
    entity_scope: str | None,
    path_kind: str,
    path_label: str,
    entry_path: str | None,
    field_paths: dict[str, Any],
    selector_map: dict[str, Any],
    readback_paths: dict[str, Any],
    capture_run_id: int | None,
    source_evidence_ref: str | None,
    metadata: dict[str, Any],
    actor_user_id: int | None,
) -> PlatformWritePath:
    if operation not in EDITABLE_OPERATION_REQUIRED_KEYS:
        raise PlatformWritePathError("Operacion de escritura no soportada.")
    if not field_paths:
        raise PlatformWritePathError("field_paths no puede estar vacio; guarda solo rutas observadas.")
    _assert_no_secret_payload(field_paths, label="field_paths")
    _assert_no_secret_payload(selector_map, label="selector_map")
    _assert_no_secret_payload(readback_paths, label="readback_paths")

    account, manifest = _resolve_account_and_manifest(
        session,
        tenant_id=tenant_id,
        account_proposal_id=account_proposal_id,
    )
    capture_run = _validate_capture_run(
        session,
        tenant_id=tenant_id,
        manifest_id=manifest.id,
        account_proposal_id=account.id,
        capture_run_id=capture_run_id,
    )
    evidence_ref = source_evidence_ref or _capture_source_ref(capture_run)

    existing = session.scalar(
        select(PlatformWritePath).where(
            PlatformWritePath.tenant_id == tenant_id,
            PlatformWritePath.account_proposal_id == account.id,
            PlatformWritePath.operation == operation,
            PlatformWritePath.path_kind == path_kind,
            PlatformWritePath.path_label == path_label,
        )
    )
    if existing is None:
        existing = PlatformWritePath(
            tenant_id=tenant_id,
            manifest_id=manifest.id,
            account_proposal_id=account.id,
            external_platform_id=manifest.external_platform_id,
            platform_account_id=account.platform_account_id,
            capture_run_id=capture_run.id if capture_run is not None else None,
            operation=operation,
            entity_scope=entity_scope,
            path_kind=path_kind,
            path_label=path_label,
            host=account.host or (manifest.hosts[0] if manifest.hosts else None),
            entry_path=entry_path,
            field_paths_json=field_paths,
            selector_map_json=selector_map,
            readback_paths_json=readback_paths,
            source_evidence_ref=evidence_ref,
            review_status=PENDING_WRITE_PATH_STATUS,
            status="captured_pending_review",
            metadata_json=metadata,
            created_by=actor_user_id,
        )
        session.add(existing)
    else:
        existing.entity_scope = entity_scope
        existing.external_platform_id = manifest.external_platform_id
        existing.platform_account_id = account.platform_account_id
        existing.capture_run_id = capture_run.id if capture_run is not None else capture_run_id
        existing.host = account.host or (manifest.hosts[0] if manifest.hosts else existing.host)
        existing.entry_path = entry_path
        existing.field_paths_json = field_paths
        existing.selector_map_json = selector_map
        existing.readback_paths_json = readback_paths
        existing.source_evidence_ref = evidence_ref
        existing.review_status = PENDING_WRITE_PATH_STATUS
        existing.status = "captured_pending_review"
        existing.approval_notes = None
        existing.approved_by = None
        existing.approved_at = None
        existing.metadata_json = metadata
    session.flush()
    return existing


def set_write_path_review_status(
    session: Session,
    *,
    tenant_id: int,
    path_id: int,
    review_status: str,
    notes: str | None,
    actor_user_id: int | None,
) -> PlatformWritePath:
    if review_status not in WRITE_PATH_REVIEW_STATUSES:
        raise PlatformWritePathError("Estado de revision de path no soportado.")
    path = session.scalar(
        select(PlatformWritePath).where(
            PlatformWritePath.tenant_id == tenant_id,
            PlatformWritePath.id == path_id,
        )
    )
    if path is None:
        raise PlatformWritePathError("Path de escritura no encontrado.")
    if review_status == APPROVED_WRITE_PATH_STATUS:
        _validate_approvable_path(path)
        path.approved_by = actor_user_id
        path.approved_at = datetime.now(timezone.utc)
        path.status = "approved_for_preview_and_readback"
    elif review_status == REJECTED_WRITE_PATH_STATUS:
        path.approved_by = None
        path.approved_at = None
        path.status = "rejected"
    else:
        path.approved_by = None
        path.approved_at = None
        path.status = "captured_pending_review"
    path.review_status = review_status
    path.approval_notes = notes
    session.flush()
    return path


def write_path_to_read(path: PlatformWritePath) -> dict[str, Any]:
    return {
        "id": path.id,
        "tenant_id": path.tenant_id,
        "manifest_id": path.manifest_id,
        "account_proposal_id": path.account_proposal_id,
        "external_platform_id": path.external_platform_id,
        "platform_account_id": path.platform_account_id,
        "capture_run_id": path.capture_run_id,
        "operation": path.operation,
        "entity_scope": path.entity_scope,
        "path_kind": path.path_kind,
        "path_label": path.path_label,
        "host": path.host,
        "entry_path": path.entry_path,
        "field_paths": path.field_paths_json or {},
        "selector_map": path.selector_map_json or {},
        "readback_paths": path.readback_paths_json or {},
        "source_evidence_ref": path.source_evidence_ref,
        "review_status": path.review_status,
        "status": path.status,
        "approval_notes": path.approval_notes,
        "approved_by": path.approved_by,
        "approved_at": path.approved_at,
        "metadata": path.metadata_json or {},
        "created_by": path.created_by,
        "created_at": path.created_at,
        "updated_at": path.updated_at,
    }


def _resolve_account_and_manifest(
    session: Session,
    *,
    tenant_id: int,
    account_proposal_id: int,
) -> tuple[PlatformRpaAccountProposal, PlatformRpaManifest]:
    account = session.scalar(
        select(PlatformRpaAccountProposal).where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.id == account_proposal_id,
        )
    )
    if account is None:
        raise PlatformWritePathError("Cuenta de plataforma no encontrada.")
    manifest = session.scalar(
        select(PlatformRpaManifest).where(
            PlatformRpaManifest.tenant_id == tenant_id,
            PlatformRpaManifest.id == account.manifest_id,
        )
    )
    if manifest is None:
        raise PlatformWritePathError("Manifiesto de plataforma no encontrado.")
    return account, manifest


def _validate_capture_run(
    session: Session,
    *,
    tenant_id: int,
    manifest_id: int,
    account_proposal_id: int,
    capture_run_id: int | None,
) -> PlatformReviewRun | None:
    if capture_run_id is None:
        return None
    run = session.scalar(
        select(PlatformReviewRun).where(
            PlatformReviewRun.tenant_id == tenant_id,
            PlatformReviewRun.id == capture_run_id,
        )
    )
    if run is None:
        raise PlatformWritePathError("Captura de pasarela no encontrada.")
    if run.manifest_id != manifest_id or run.account_proposal_id != account_proposal_id:
        raise PlatformWritePathError("La captura no pertenece a esta plataforma/cuenta.")
    if run.operation != CAPTURE_WRITE_SCREEN_ACTION:
        raise PlatformWritePathError("La evidencia debe venir de una captura editable.")
    return run


def _capture_source_ref(run: PlatformReviewRun | None) -> str | None:
    if run is None:
        return None
    gateway = dict((run.evidence_json or {}).get("gateway") or {})
    browser_launch = dict(gateway.get("browser_launch") or {})
    status_artifact = browser_launch.get("status_artifact")
    if isinstance(status_artifact, str) and status_artifact.strip():
        return status_artifact.strip()
    return f"platform_review_run:{run.id}"


def _validate_approvable_path(path: PlatformWritePath) -> None:
    if not path.field_paths_json:
        raise PlatformWritePathError("No se puede aprobar un path sin field_paths.")
    if not path.readback_paths_json:
        raise PlatformWritePathError("No se puede aprobar un path sin readback_paths.")
    if not path.capture_run_id and not path.source_evidence_ref:
        raise PlatformWritePathError("No se puede aprobar un path sin evidencia o captura asociada.")


def _assert_no_secret_payload(payload: Mapping[str, Any], *, label: str) -> None:
    for key, value in _walk_mapping(payload):
        lowered_key = key.lower()
        if any(token in lowered_key for token in ("password", "secret", "token", "credential")):
            raise PlatformWritePathError(f"{label} contiene una clave que parece secreto: {key}.")
        if isinstance(value, str) and _looks_like_raw_secret(value):
            raise PlatformWritePathError(f"{label} contiene un valor que parece secreto.")


def _walk_mapping(payload: Mapping[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key, value in payload.items():
        next_key = f"{prefix}.{key}" if prefix else str(key)
        rows.append((next_key, value))
        if isinstance(value, Mapping):
            rows.extend(_walk_mapping(value, next_key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, Mapping):
                    rows.extend(_walk_mapping(item, f"{next_key}[{index}]"))
    return rows


def _looks_like_raw_secret(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    secret_markers = ("-----BEGIN", "sk-", "eyJ", "AKIA")
    return any(marker in text for marker in secret_markers)
