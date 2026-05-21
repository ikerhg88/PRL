from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.schemas import (
    PlatformReviewRunRead,
    RpaGatewayBrowserLaunchRead,
    RpaGatewayBrowserStatusRead,
    RpaGatewayCaptureSyncRead,
    RpaGatewayDecisionCreate,
    RpaGatewayOptionsRead,
    RpaGatewayRequestCreate,
)
from app.services.access_control import require_tenant_wide_access
from app.services.audit import public_state, record_audit
from app.services.rpa_assisted_browser import (
    launch_visible_browser_for_gateway_run,
    read_visible_browser_status_for_gateway_run,
    sync_visible_browser_capture_for_gateway_run,
)
from app.services.rpa_gateway import (
    apply_gateway_decision,
    create_gateway_request,
    gateway_options,
    list_gateway_requests,
)
from app.services.platform_review_runs import run_to_read

router = APIRouter(prefix="/rpa-gateway", tags=["rpa-gateway"])


@router.get("/options", response_model=RpaGatewayOptionsRead)
def get_rpa_gateway_options(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    priority_group: str | None = Query(default=None),
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return gateway_options(session, tenant_id=tenant_id, priority_group=priority_group)


@router.get("/requests", response_model=list[PlatformReviewRunRead])
def get_rpa_gateway_requests(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return list_gateway_requests(session, tenant_id=tenant_id, limit=limit)


@router.post("/requests", response_model=PlatformReviewRunRead, status_code=201)
def create_rpa_gateway_request(
    payload: RpaGatewayRequestCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    try:
        run = create_gateway_request(
            session,
            tenant_id=tenant_id,
            schedule_id=payload.schedule_id,
            manifest_id=payload.manifest_id,
            account_proposal_id=payload.account_proposal_id,
            action_key=payload.action_key,
            actor_user_id=actor_user_id,
            request_comment=payload.request_comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    read = run_to_read(run)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="rpa_gateway.request_create",
        entity_type="platform_review_run",
        entity_id=run.id,
        after=public_state(
            {
                "id": run.id,
                "schedule_id": run.schedule_id,
                "platform_slug": run.platform_slug,
                "operation": run.operation,
                "status": run.status,
                "result_status": run.result_status,
                "dry_run": run.dry_run,
                "manual_approval_required": run.manual_approval_required,
            }
        ),
    )
    session.commit()
    return read


@router.post("/requests/{run_id}/launch-visible-browser", response_model=RpaGatewayBrowserLaunchRead)
def launch_rpa_gateway_visible_browser(
    run_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    launch = launch_visible_browser_for_gateway_run(session, tenant_id=tenant_id, run_id=run_id)
    if launch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway request not found.")
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="rpa_gateway.launch_visible_browser",
        entity_type="platform_review_run",
        entity_id=run_id,
        after=public_state(
            {
                "id": run_id,
                "status": launch["status"],
                "launched": launch["launched"],
                "credential_available": launch["credential_available"],
            }
        ),
    )
    session.commit()
    return launch


@router.get("/requests/{run_id}/browser-status", response_model=RpaGatewayBrowserStatusRead)
def get_rpa_gateway_visible_browser_status(
    run_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    status_payload = read_visible_browser_status_for_gateway_run(session, tenant_id=tenant_id, run_id=run_id)
    if status_payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway request not found.")
    return status_payload


@router.post("/requests/{run_id}/sync-readonly-capture", response_model=RpaGatewayCaptureSyncRead)
def sync_rpa_gateway_readonly_capture(
    run_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    sync_result = sync_visible_browser_capture_for_gateway_run(session, tenant_id=tenant_id, run_id=run_id)
    if sync_result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway request not found.")
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="rpa_gateway.sync_readonly_capture",
        entity_type="platform_review_run",
        entity_id=run_id,
        after=public_state(
            {
                "id": run_id,
                "synced": sync_result["synced"],
                "status": sync_result["status"],
                "pages_captured": sync_result["pages_captured"],
                "persisted_row_level": sync_result["persisted_row_level"],
            }
        ),
    )
    session.commit()
    return sync_result


@router.post("/requests/{run_id}/decision", response_model=PlatformReviewRunRead)
def decide_rpa_gateway_request(
    run_id: int,
    payload: RpaGatewayDecisionCreate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    try:
        run = apply_gateway_decision(
            session,
            tenant_id=tenant_id,
            run_id=run_id,
            decision=payload.decision,
            actor_user_id=actor_user_id,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway request not found.")
    read = run_to_read(run)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="rpa_gateway.human_decision",
        entity_type="platform_review_run",
        entity_id=run.id,
        after=public_state(
            {
                "id": run.id,
                "decision": payload.decision,
                "platform_slug": run.platform_slug,
                "status": run.status,
                "result_status": run.result_status,
            }
        ),
    )
    session.commit()
    return read
