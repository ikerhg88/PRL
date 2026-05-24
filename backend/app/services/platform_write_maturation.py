from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PlatformReviewRun, PlatformRpaAccountProposal, PlatformRpaManifest, PlatformWritePath
from app.services.platform_current_accounts_sync import account_is_inactive
from app.services.platform_reconciliation import build_platform_reconciliation_map
from app.services.platform_write_paths import PlatformWritePathError, set_write_path_review_status
from app.services.rpa_assisted_browser import (
    launch_visible_browser_for_gateway_run,
    read_visible_browser_status_for_gateway_run,
    sync_visible_browser_capture_for_gateway_run,
)
from app.services.rpa_gateway import CAPTURE_WRITE_SCREEN_ACTION, apply_gateway_decision, create_gateway_request


def mature_platform_write_readiness(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    platform_slugs: list[str] | None = None,
    account_proposal_ids: list[int] | None = None,
    create_missing_capture_requests: bool = True,
    authorize_capture_requests: bool = True,
    launch_browsers: bool = False,
    sync_available_captures: bool = True,
    approve_valid_captured_paths: bool = True,
    max_browser_launches: int = 0,
) -> dict[str, Any]:
    selected_slugs = {slug.strip() for slug in platform_slugs or [] if slug.strip()}
    selected_accounts = {account_id for account_id in account_proposal_ids or [] if account_id}
    targets = _targets(
        session,
        tenant_id=tenant_id,
        platform_slugs=selected_slugs,
        account_proposal_ids=selected_accounts,
    )
    rows: list[dict[str, Any]] = []
    launched = 0
    for account, manifest in targets:
        run = _latest_capture_run(session, tenant_id=tenant_id, account_proposal_id=account.id)
        row: dict[str, Any] = {
            "account_proposal_id": account.id,
            "manifest_id": manifest.id,
            "platform_slug": manifest.platform_slug,
            "platform_name": manifest.platform_name,
            "external_company_name": account.external_company_name,
            "capture_request_id": run.id if run else None,
            "capture_created": False,
            "capture_authorized": False,
            "browser_launched": False,
            "browser_state": None,
            "capture_synced": False,
            "write_paths_approved": 0,
            "write_paths_rejected_or_blocked": 0,
            "write_path_errors": [],
            "next_action": None,
        }
        if run is None and create_missing_capture_requests:
            run = create_gateway_request(
                session,
                tenant_id=tenant_id,
                manifest_id=manifest.id,
                account_proposal_id=account.id,
                action_key=CAPTURE_WRITE_SCREEN_ACTION,
                actor_user_id=actor_user_id,
                request_comment="Maduracion automatizada de mapeo editable para escritura desde Hub.",
            )
            row["capture_created"] = run is not None
            row["capture_request_id"] = run.id if run else None
        if run is None:
            row["next_action"] = "Crear pasarela de captura editable para esta cuenta."
            rows.append(row)
            continue

        gateway = dict((run.evidence_json or {}).get("gateway") or {})
        if authorize_capture_requests and not gateway.get("external_browser_authorized"):
            run = apply_gateway_decision(
                session,
                tenant_id=tenant_id,
                run_id=run.id,
                decision="authorize_enter_page",
                actor_user_id=actor_user_id,
                notes="Autorizado para capturar mapeo editable sin ejecutar escrituras externas.",
            )
            row["capture_authorized"] = run is not None
        if run is None:
            row["next_action"] = "No se pudo autorizar la pasarela."
            rows.append(row)
            continue

        if launch_browsers and (max_browser_launches <= 0 or launched < max_browser_launches):
            launch = launch_visible_browser_for_gateway_run(session, tenant_id=tenant_id, run_id=run.id)
            row["browser_launched"] = bool(launch and launch.get("launched"))
            if row["browser_launched"]:
                launched += 1
        if sync_available_captures:
            status = read_visible_browser_status_for_gateway_run(session, tenant_id=tenant_id, run_id=run.id)
            row["browser_state"] = (status or {}).get("state")
            sync = sync_visible_browser_capture_for_gateway_run(session, tenant_id=tenant_id, run_id=run.id)
            row["capture_synced"] = bool(sync and sync.get("synced"))
            row["sync_status"] = (sync or {}).get("status")
            row["write_paths_upserted"] = int((sync or {}).get("write_paths_upserted") or 0)
            row["write_path_operations_seen"] = list((sync or {}).get("write_path_operations_seen") or [])
        if approve_valid_captured_paths:
            approval = _approve_valid_pending_paths(
                session,
                tenant_id=tenant_id,
                account_proposal_id=account.id,
                actor_user_id=actor_user_id,
            )
            row["write_paths_approved"] = approval["approved"]
            row["write_paths_rejected_or_blocked"] = approval["blocked"]
            row["write_path_errors"] = approval["errors"]
        row["next_action"] = _next_action(row)
        rows.append(row)

    reconciliation = build_platform_reconciliation_map(session, tenant_id=tenant_id, priority_group="all")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "external_write_executed": False,
            "captcha_bypass": False,
            "mfa_bypass": False,
            "commercial_routes_or_selectors_invented": False,
            "approves_only_paths_with_field_paths_readback_and_evidence": True,
            "live_write_still_requires_submit_preview_approval_and_readback": True,
        },
        "summary": _summary(rows, reconciliation),
        "rows": rows,
        "reconciliation_summary": reconciliation["summary"],
    }


def _targets(
    session: Session,
    *,
    tenant_id: int,
    platform_slugs: set[str],
    account_proposal_ids: set[int],
) -> list[tuple[PlatformRpaAccountProposal, PlatformRpaManifest]]:
    statement = (
        select(PlatformRpaAccountProposal, PlatformRpaManifest)
        .join(PlatformRpaManifest, PlatformRpaManifest.id == PlatformRpaAccountProposal.manifest_id)
        .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
        .order_by(PlatformRpaManifest.platform_name, PlatformRpaAccountProposal.external_company_name)
    )
    rows = []
    for account, manifest in session.execute(statement).all():
        if account_is_inactive(account.status):
            continue
        if platform_slugs and manifest.platform_slug not in platform_slugs:
            continue
        if account_proposal_ids and account.id not in account_proposal_ids:
            continue
        rows.append((account, manifest))
    return rows


def _latest_capture_run(
    session: Session,
    *,
    tenant_id: int,
    account_proposal_id: int,
) -> PlatformReviewRun | None:
    return session.scalars(
        select(PlatformReviewRun)
        .where(
            PlatformReviewRun.tenant_id == tenant_id,
            PlatformReviewRun.account_proposal_id == account_proposal_id,
            PlatformReviewRun.operation == CAPTURE_WRITE_SCREEN_ACTION,
        )
        .order_by(PlatformReviewRun.id.desc())
    ).first()


def _approve_valid_pending_paths(
    session: Session,
    *,
    tenant_id: int,
    account_proposal_id: int,
    actor_user_id: int | None,
) -> dict[str, Any]:
    approved = 0
    blocked = 0
    errors: list[str] = []
    paths = list(
        session.scalars(
            select(PlatformWritePath).where(
                PlatformWritePath.tenant_id == tenant_id,
                PlatformWritePath.account_proposal_id == account_proposal_id,
                PlatformWritePath.review_status == "pending_review",
            )
        )
    )
    for path in paths:
        try:
            set_write_path_review_status(
                session,
                tenant_id=tenant_id,
                path_id=path.id,
                review_status="approved",
                notes="Aprobado por maduracion automatizada: path tiene evidencia, field_paths y readback_paths.",
                actor_user_id=actor_user_id,
            )
            approved += 1
        except PlatformWritePathError as exc:
            blocked += 1
            errors.append(f"path {path.id}: {exc}")
    return {"approved": approved, "blocked": blocked, "errors": errors[:10]}


def _next_action(row: dict[str, Any]) -> str:
    if row["write_paths_approved"]:
        return "Recalcular preview y ejecutar submit si la plataforma tiene helper live especifico."
    if row.get("write_paths_upserted"):
        return "Revisar/aprobar paths capturados; alguno no cumple criterios de aprobacion automatica."
    if row.get("capture_synced"):
        return "La captura no produjo paths editables aprobables; navegar hasta formulario de alta/documentos."
    if row.get("browser_launched"):
        return "Completar login/captcha/MFA si aparece y navegar al formulario editable; despues sincronizar captura."
    if row.get("capture_request_id"):
        return "Abrir pasarela y lanzar navegador guiado para capturar formulario editable."
    return "Crear pasarela de captura editable."


def _summary(rows: list[dict[str, Any]], reconciliation: dict[str, Any]) -> dict[str, Any]:
    return {
        "targets": len(rows),
        "capture_requests_created": sum(1 for row in rows if row["capture_created"]),
        "capture_requests_authorized": sum(1 for row in rows if row["capture_authorized"]),
        "browsers_launched": sum(1 for row in rows if row["browser_launched"]),
        "captures_synced": sum(1 for row in rows if row["capture_synced"]),
        "write_paths_approved": sum(int(row["write_paths_approved"] or 0) for row in rows),
        "write_paths_blocked": sum(int(row["write_paths_rejected_or_blocked"] or 0) for row in rows),
        "write_ready_contexts": reconciliation["summary"].get("write_ready", 0),
        "fully_mapped_for_read_write": reconciliation["summary"].get("fully_mapped_for_read_write", 0),
        "external_write_executed": 0,
    }
