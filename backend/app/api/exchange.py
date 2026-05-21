from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.api.transfers import create_transfer
from app.connectors.rpa.write_registry import write_connector_key_for_platform_slug
from app.db.models import ExternalPlatform, PlatformRpaAccountProposal, PlatformRpaManifest
from app.db.models import PlatformReviewRun
from app.schemas import (
    ExchangeBulkCaptureWriteScreensRequest,
    ExchangeBulkWorkerSubmitRequest,
    ExchangeCaptureWriteScreenRequest,
    ExchangeWritePreviewRead,
    ExchangeWritePreviewRequest,
    ExchangeWriteSubmitRequest,
    PlatformReviewRunRead,
    TransferRead,
    TransferRequest,
)
from app.services.access_control import require_tenant_wide_access
from app.services.audit import public_state, record_audit
from app.services.platform_write_previews import WritePreviewError, build_write_operation_preview
from app.services.platform_current_accounts_sync import INACTIVE_STATUSES, account_is_inactive
from app.services.platform_write_probe_matrix import (
    DEFAULT_WRITE_MATRIX_OPERATIONS,
    SPECIFIC_LIVE_ADAPTER_CONNECTORS,
    build_platform_write_probe_matrix,
    live_write_adapter_catalog,
)
from app.services.platform_review_runs import run_to_read
from app.services.rpa_gateway import CAPTURE_WRITE_SCREEN_ACTION, create_gateway_request

router = APIRouter(prefix="/exchange", tags=["exchange"])


@router.get("/write-matrix")
async def get_exchange_write_matrix(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    company_id: int | None = Query(default=None),
    worker_id: int | None = Query(default=None),
    operations: list[str] | None = Query(default=None),
    connector_dry_run: bool = Query(default=False),
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    selected_operations = tuple(operations or DEFAULT_WRITE_MATRIX_OPERATIONS)
    try:
        return await build_platform_write_probe_matrix(
            session,
            tenant_id=tenant_id,
            company_id=company_id,
            worker_id=worker_id,
            operations=selected_operations,
            connector_dry_run=connector_dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/live-adapters")
def get_exchange_live_adapters(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return live_write_adapter_catalog(session, tenant_id=tenant_id)


@router.post("/capture-write-screens/bulk")
def bulk_create_capture_write_screen_requests(
    payload: ExchangeBulkCaptureWriteScreensRequest,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    platform_slugs = {slug.strip() for slug in payload.platform_slugs if slug.strip()}
    targets = _list_capture_targets(
        session,
        tenant_id=tenant_id,
        platform_slugs=platform_slugs,
        include_accounts_without_write_connector=payload.include_accounts_without_write_connector,
    )
    rows: list[dict[str, Any]] = []
    for account, manifest, platform, connector_key in targets:
        existing_run = _active_capture_run(
            session,
            tenant_id=tenant_id,
            account_proposal_id=account.id,
        )
        row_base = {
            "account_proposal_id": account.id,
            "manifest_id": manifest.id,
            "platform_slug": manifest.platform_slug,
            "platform_name": manifest.platform_name,
            "external_company_name": account.external_company_name,
            "platform_key": platform.platform_key,
            "write_connector_key": connector_key,
        }
        if existing_run is not None and payload.skip_existing_active:
            rows.append(
                row_base
                | {
                    "status": "skipped_existing_active_capture",
                    "capture_request_id": existing_run.id,
                    "detail": "Ya existe una pasarela activa de captura editable para esta cuenta.",
                }
            )
            continue
        run = create_gateway_request(
            session,
            tenant_id=tenant_id,
            manifest_id=manifest.id,
            account_proposal_id=account.id,
            action_key=CAPTURE_WRITE_SCREEN_ACTION,
            actor_user_id=actor_user_id,
            request_comment=payload.request_comment
            or "Mapeo editable masivo para preparar escritura externa.",
        )
        if run is None:
            rows.append(
                row_base
                | {
                    "status": "failed_to_create_capture",
                    "capture_request_id": None,
                    "detail": "No se pudo crear schedule/pasarela para esta cuenta.",
                }
            )
            continue
        session.flush()
        rows.append(
            row_base
            | {
                "status": "created",
                "capture_request_id": run.id,
                "detail": "Pasarela de captura editable creada.",
            }
        )

    summary = {
        "targets": len(rows),
        "created": sum(1 for row in rows if row["status"] == "created"),
        "skipped_existing_active": sum(
            1 for row in rows if row["status"] == "skipped_existing_active_capture"
        ),
        "failed": sum(1 for row in rows if row["status"] == "failed_to_create_capture"),
        "accounts_without_write_connector": sum(1 for row in rows if row["write_connector_key"] is None),
    }
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="exchange.bulk_capture_write_screen",
        entity_type="platform_rpa_account_proposal",
        entity_id=None,
        after=public_state(
            {
                "platform_slugs": sorted(platform_slugs),
                "include_accounts_without_write_connector": payload.include_accounts_without_write_connector,
                "skip_existing_active": payload.skip_existing_active,
                "summary": summary,
            }
        ),
    )
    session.commit()
    return {
        "policy": {
            "external_routes_or_selectors_invented": False,
            "external_browser_launched": False,
            "external_write_executed": False,
            "captcha_bypass": False,
            "mfa_bypass": False,
            "purpose": "editable_capture_mapping",
        },
        "summary": summary,
        "rows": rows,
    }


@router.post("/workers/bulk-submit")
async def bulk_submit_worker_to_platforms(
    payload: ExchangeBulkWorkerSubmitRequest,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    platform_slugs = {slug.strip() for slug in payload.platform_slugs if slug.strip()}
    targets = _list_account_write_targets(session, tenant_id=tenant_id, platform_slugs=platform_slugs)
    rows: list[dict[str, Any]] = []
    for account, manifest, platform, connector_key in targets:
        row_base = {
            "account_proposal_id": account.id,
            "manifest_id": manifest.id,
            "platform_slug": manifest.platform_slug,
            "platform_name": manifest.platform_name,
            "external_company_name": account.external_company_name,
            "platform_key": platform.platform_key,
            "connector_key": connector_key,
            "live_adapter_status": "specific_live_adapter_available"
            if connector_key in SPECIFIC_LIVE_ADAPTER_CONNECTORS
            else "blocked_live_adapter_missing",
        }
        try:
            preview = build_write_operation_preview(
                session,
                tenant_id=tenant_id,
                account_proposal_id=account.id,
                operation="upsert_worker",
                company_id=payload.company_id,
                worker_id=payload.worker_id,
            )
        except WritePreviewError as exc:
            capture_run_id = _maybe_create_capture_request(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                account=account,
                enabled=payload.create_capture_requests,
                reason=str(exc),
            )
            rows.append(
                row_base
                | {
                    "status": "preview_error",
                    "preview_status": "preview_error",
                    "transfer_id": None,
                    "transfer_status": None,
                    "capture_request_id": capture_run_id,
                    "detail": str(exc),
                }
            )
            continue

        preview_status = str(preview.get("status"))

        try:
            transfer = await create_transfer(
                TransferRequest(
                    platform_key=platform.platform_key,
                    connector_key=cast(Any, connector_key),
                    operation="upsert_worker",
                    worker_id=payload.worker_id,
                    account_proposal_id=account.id,
                    dry_run=payload.dry_run,
                    manual_approval_required=payload.manual_approval_required,
                    live_external_write_authorized=payload.live_external_write_authorized,
                ),
                tenant_id,
                session,
                actor_user_id,
            )
            capture_run_id = None
            if transfer.status in {"blocked_mapping_review_required", "blocked_live_adapter_missing"}:
                capture_run_id = _maybe_create_capture_request(
                    session,
                    tenant_id=tenant_id,
                    actor_user_id=actor_user_id,
                    account=account,
                    enabled=payload.create_capture_requests,
                    reason=f"transfer_status={transfer.status}",
                )
            rows.append(
                row_base
                | {
                    "status": transfer.status,
                    "preview_status": preview_status,
                    "transfer_id": transfer.id,
                    "transfer_status": transfer.status,
                    "capture_request_id": capture_run_id,
                    "detail": transfer.last_attempt_message,
                }
            )
        except HTTPException as exc:
            already_exists = "ya existe" in str(exc.detail).lower()
            capture_run_id = _maybe_create_capture_request(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                account=account,
                enabled=payload.create_capture_requests and not already_exists,
                reason=str(exc.detail),
            )
            rows.append(
                row_base
                | {
                    "status": "already_exists_external" if already_exists else "blocked_submit",
                    "preview_status": preview_status,
                    "transfer_id": None,
                    "transfer_status": None,
                    "capture_request_id": capture_run_id,
                    "detail": exc.detail,
                }
            )

    summary = {
        "targets": len(rows),
        "transfer_jobs_created": sum(1 for row in rows if row["transfer_id"] is not None),
        "capture_requests_created": sum(1 for row in rows if row["capture_request_id"] is not None),
        "external_writes_confirmed": sum(1 for row in rows if row["status"] == "confirmed_external"),
        "blocked": sum(1 for row in rows if str(row["status"]).startswith("blocked") or row["status"] == "preview_error"),
    }
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="exchange.bulk_worker_submit",
        entity_type="worker",
        entity_id=payload.worker_id,
        after=public_state(
            {
                "worker_id": payload.worker_id,
                "dry_run": payload.dry_run,
                "manual_approval_required": payload.manual_approval_required,
                "live_external_write_authorized": payload.live_external_write_authorized,
                "summary": summary,
            }
        ),
    )
    session.commit()
    return {
        "policy": {
            "external_routes_or_selectors_invented": False,
            "captcha_bypass": False,
            "mfa_bypass": False,
            "requires_preview": True,
            "requires_human_approval": True,
            "requires_post_write_readback": True,
        },
        "summary": summary,
        "rows": rows,
    }


@router.post("/{account_proposal_id}/preview", response_model=ExchangeWritePreviewRead)
def create_exchange_write_preview(
    account_proposal_id: int,
    payload: ExchangeWritePreviewRequest,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, object]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    try:
        preview = build_write_operation_preview(
            session,
            tenant_id=tenant_id,
            account_proposal_id=account_proposal_id,
            operation=payload.operation,
            company_id=payload.company_id,
            worker_id=payload.worker_id,
            document_version_id=payload.document_version_id,
        )
    except WritePreviewError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="exchange.write_preview",
        entity_type="platform_rpa_account_proposal",
        entity_id=account_proposal_id,
        after=public_state(
            {
                "account_proposal_id": account_proposal_id,
                "operation": preview["operation"],
                "status": preview["status"],
                "platform": preview["platform"],
                "entity": preview["entity"],
                "readiness": preview["readiness"],
                "blocker_count": len(preview["blockers"]),
                "planned_change_count": len(preview["planned_external_changes"]),
            }
        ),
    )
    session.commit()
    return preview


@router.post("/{account_proposal_id}/submit", response_model=TransferRead, status_code=201)
async def submit_exchange_write(
    account_proposal_id: int,
    payload: ExchangeWriteSubmitRequest,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> TransferRead:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    account, manifest, platform, connector_key = _resolve_account_write_target(
        session,
        tenant_id=tenant_id,
        account_proposal_id=account_proposal_id,
    )
    try:
        preview = build_write_operation_preview(
            session,
            tenant_id=tenant_id,
            account_proposal_id=account.id,
            operation=payload.operation,
            company_id=payload.company_id,
            worker_id=payload.worker_id,
            document_version_id=payload.document_version_id,
        )
    except WritePreviewError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if not payload.dry_run and preview.get("status") != "preview_ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Live external write blocked because preview is not ready.",
        )
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="exchange.write_submit_requested",
        entity_type="platform_rpa_account_proposal",
        entity_id=account.id,
        after=public_state(
            {
                "account_proposal_id": account.id,
                "manifest_id": manifest.id,
                "platform_slug": manifest.platform_slug,
                "platform_key": platform.platform_key,
                "connector_key": connector_key,
                "operation": payload.operation,
                "preview_status": preview.get("status"),
                "dry_run": payload.dry_run,
                "manual_approval_required": payload.manual_approval_required,
                "live_external_write_authorized": payload.live_external_write_authorized,
            }
        ),
    )
    session.flush()
    transfer_payload = TransferRequest(
        platform_key=platform.platform_key,
        connector_key=cast(Any, connector_key),
        operation=payload.operation,
        document_version_id=payload.document_version_id,
        worker_id=payload.worker_id,
        account_proposal_id=account.id,
        dry_run=payload.dry_run,
        manual_approval_required=payload.manual_approval_required,
        live_external_write_authorized=payload.live_external_write_authorized,
    )
    return await create_transfer(
        transfer_payload,
        tenant_id,
        session,
        actor_user_id,
    )


@router.post(
    "/{account_proposal_id}/capture-write-screen",
    response_model=PlatformReviewRunRead,
    status_code=201,
)
def create_exchange_capture_write_screen_request(
    account_proposal_id: int,
    payload: ExchangeCaptureWriteScreenRequest,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    account = session.scalar(
        select(PlatformRpaAccountProposal).where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.id == account_proposal_id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform account not found.")
    if account_is_inactive(account.status):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Platform account is inactive/baja.")
    try:
        run = create_gateway_request(
            session,
            tenant_id=tenant_id,
            manifest_id=account.manifest_id,
            account_proposal_id=account.id,
            action_key=CAPTURE_WRITE_SCREEN_ACTION,
            actor_user_id=actor_user_id,
            request_comment=payload.request_comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform manifest not found.")
    read = run_to_read(run)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="exchange.capture_write_screen_request",
        entity_type="platform_review_run",
        entity_id=run.id,
        after=public_state(
            {
                "id": run.id,
                "account_proposal_id": account.id,
                "platform_slug": run.platform_slug,
                "operation": run.operation,
                "status": run.status,
                "dry_run": run.dry_run,
                "manual_approval_required": run.manual_approval_required,
            }
        ),
    )
    session.commit()
    return read


def _resolve_account_write_target(
    session: DbSession,
    *,
    tenant_id: int,
    account_proposal_id: int,
) -> tuple[PlatformRpaAccountProposal, PlatformRpaManifest, ExternalPlatform, str]:
    account = session.scalar(
        select(PlatformRpaAccountProposal).where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.id == account_proposal_id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform account not found.")
    if account_is_inactive(account.status):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Platform account is inactive/baja.")
    manifest = session.scalar(
        select(PlatformRpaManifest).where(
            PlatformRpaManifest.tenant_id == tenant_id,
            PlatformRpaManifest.id == account.manifest_id,
        )
    )
    if manifest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform manifest not found.")
    if manifest.external_platform_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Platform manifest is not linked.")
    platform = session.get(ExternalPlatform, manifest.external_platform_id)
    if platform is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External platform not found.")
    connector_key = write_connector_key_for_platform_slug(manifest.platform_slug)
    if connector_key is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No registered write connector exists for this platform.",
        )
    return account, manifest, platform, connector_key


def _list_account_write_targets(
    session: DbSession,
    *,
    tenant_id: int,
    platform_slugs: set[str],
) -> list[tuple[PlatformRpaAccountProposal, PlatformRpaManifest, ExternalPlatform, str]]:
    rows = session.execute(
        select(PlatformRpaAccountProposal, PlatformRpaManifest, ExternalPlatform)
        .join(PlatformRpaManifest, PlatformRpaManifest.id == PlatformRpaAccountProposal.manifest_id)
        .join(ExternalPlatform, ExternalPlatform.id == PlatformRpaManifest.external_platform_id)
        .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
        .where(PlatformRpaAccountProposal.status.notin_(INACTIVE_STATUSES))
        .order_by(PlatformRpaManifest.platform_name, PlatformRpaAccountProposal.external_company_name)
    ).all()
    targets: list[tuple[PlatformRpaAccountProposal, PlatformRpaManifest, ExternalPlatform, str]] = []
    for account, manifest, platform in rows:
        if platform_slugs and manifest.platform_slug not in platform_slugs:
            continue
        connector_key = write_connector_key_for_platform_slug(manifest.platform_slug)
        if connector_key is None:
            continue
        targets.append((account, manifest, platform, connector_key))
    return targets


def _list_capture_targets(
    session: DbSession,
    *,
    tenant_id: int,
    platform_slugs: set[str],
    include_accounts_without_write_connector: bool,
) -> list[tuple[PlatformRpaAccountProposal, PlatformRpaManifest, ExternalPlatform, str | None]]:
    rows = session.execute(
        select(PlatformRpaAccountProposal, PlatformRpaManifest, ExternalPlatform)
        .join(PlatformRpaManifest, PlatformRpaManifest.id == PlatformRpaAccountProposal.manifest_id)
        .join(ExternalPlatform, ExternalPlatform.id == PlatformRpaManifest.external_platform_id)
        .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
        .where(PlatformRpaAccountProposal.status.notin_(INACTIVE_STATUSES))
        .order_by(PlatformRpaManifest.platform_name, PlatformRpaAccountProposal.external_company_name)
    ).all()
    targets: list[tuple[PlatformRpaAccountProposal, PlatformRpaManifest, ExternalPlatform, str | None]] = []
    for account, manifest, platform in rows:
        if platform_slugs and manifest.platform_slug not in platform_slugs:
            continue
        connector_key = write_connector_key_for_platform_slug(manifest.platform_slug)
        if connector_key is None and not include_accounts_without_write_connector:
            continue
        targets.append((account, manifest, platform, connector_key))
    return targets


def _active_capture_run(
    session: DbSession,
    *,
    tenant_id: int,
    account_proposal_id: int,
) -> PlatformReviewRun | None:
    return session.scalar(
        select(PlatformReviewRun)
        .where(
            PlatformReviewRun.tenant_id == tenant_id,
            PlatformReviewRun.account_proposal_id == account_proposal_id,
            PlatformReviewRun.operation == CAPTURE_WRITE_SCREEN_ACTION,
            PlatformReviewRun.status.in_(("human_action_required", "running", "pending")),
        )
        .order_by(PlatformReviewRun.id.desc())
        .limit(1)
    )


def _maybe_create_capture_request(
    session: DbSession,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    account: PlatformRpaAccountProposal,
    enabled: bool,
    reason: str,
) -> int | None:
    if not enabled:
        return None
    run = create_gateway_request(
        session,
        tenant_id=tenant_id,
        manifest_id=account.manifest_id,
        account_proposal_id=account.id,
        action_key=CAPTURE_WRITE_SCREEN_ACTION,
        actor_user_id=actor_user_id,
        request_comment=f"Preparar escritura: {reason}"[:500],
    )
    if run is None:
        return None
    session.flush()
    return run.id
