from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.connectors.rpa.write_registry import (
    live_adapter_status_for_connector_key,
    write_connector_key_for_platform_slug,
)
from app.db.models import (
    ExternalPlatform,
    PlatformObservedDocumentRequest,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    Worker,
    WorkerPlatformRegistration,
)
from app.services.platform_contracts import CONTRACT_SLUG_TO_PLATFORM_KEY
from app.services.platform_current_accounts_sync import account_is_inactive
from app.services.platform_write_previews import WritePreviewError, build_write_operation_preview

EXISTING_WORKER_REGISTRATION_STATUSES = {
    "accepted",
    "accepted_with_warnings",
    "confirmed",
    "submitted",
    "submitted_pending_readback",
    "pending_external_validation",
    "review_required",
    "missing_required_document",
}
def build_mass_update_plan(
    session: Session,
    *,
    tenant_id: int,
    company_id: int | None = None,
    platform_slugs: list[str] | None = None,
    account_proposal_ids: list[int] | None = None,
    worker_ids: list[int] | None = None,
    include_missing_workers: bool = True,
    include_document_requests: bool = True,
    only_active_contexts: bool = True,
    limit: int = 200,
) -> dict[str, Any]:
    selected_slugs = {slug for slug in platform_slugs or [] if slug}
    selected_accounts = {account_id for account_id in account_proposal_ids or [] if account_id}
    selected_workers = {worker_id for worker_id in worker_ids or [] if worker_id}
    contexts = _active_contexts(
        session,
        tenant_id=tenant_id,
        platform_slugs=selected_slugs,
        account_proposal_ids=selected_accounts,
        only_active_contexts=only_active_contexts,
    )
    actions: list[dict[str, Any]] = []
    if include_document_requests:
        actions.extend(
            _document_request_actions(
                session,
                tenant_id=tenant_id,
                company_id=company_id,
                contexts=contexts,
                selected_workers=selected_workers,
                limit=limit,
            )
        )
    if include_missing_workers and len(actions) < limit:
        actions.extend(
            _missing_worker_actions(
                session,
                tenant_id=tenant_id,
                company_id=company_id,
                contexts=contexts,
                selected_workers=selected_workers,
                remaining=limit - len(actions),
            )
        )
    actions = actions[:limit]
    for action in actions:
        _attach_preview(session, tenant_id=tenant_id, action=action)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "external_write_executed": False,
            "requires_preview": True,
            "requires_human_approval": True,
            "requires_post_write_readback": True,
            "commercial_routes_or_selectors_invented": False,
            "target": "mass_update_platforms_from_hub",
        },
        "filters": {
            "company_id": company_id,
            "platform_slugs": sorted(selected_slugs),
            "account_proposal_ids": sorted(selected_accounts),
            "worker_ids": sorted(selected_workers),
            "include_missing_workers": include_missing_workers,
            "include_document_requests": include_document_requests,
            "only_active_contexts": only_active_contexts,
            "limit": limit,
        },
        "summary": _summary(actions),
        "actions": actions,
    }


def _active_contexts(
    session: Session,
    *,
    tenant_id: int,
    platform_slugs: set[str],
    account_proposal_ids: set[int],
    only_active_contexts: bool,
) -> list[dict[str, Any]]:
    schedules = {
        schedule.manifest_id: schedule
        for schedule in session.scalars(
            select(PlatformReviewSchedule).where(PlatformReviewSchedule.tenant_id == tenant_id)
        )
    }
    rows = session.execute(
        select(PlatformRpaAccountProposal, PlatformRpaManifest, ExternalPlatform)
        .join(PlatformRpaManifest, PlatformRpaManifest.id == PlatformRpaAccountProposal.manifest_id)
        .join(ExternalPlatform, ExternalPlatform.id == PlatformRpaManifest.external_platform_id)
        .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
        .order_by(PlatformRpaManifest.platform_name, PlatformRpaAccountProposal.external_company_name)
    ).all()
    contexts: list[dict[str, Any]] = []
    for account, manifest, platform in rows:
        if platform_slugs and manifest.platform_slug not in platform_slugs:
            continue
        if account_proposal_ids and account.id not in account_proposal_ids:
            continue
        schedule = schedules.get(manifest.id)
        active = bool(schedule and schedule.enabled and not account_is_inactive(account.status))
        if only_active_contexts and not active:
            continue
        connector_key = write_connector_key_for_platform_slug(manifest.platform_slug)
        contexts.append(
            {
                "account": account,
                "manifest": manifest,
                "platform": platform,
                "schedule": schedule,
                "active": active,
                "connector_key": connector_key,
                "live_adapter_status": live_adapter_status_for_connector_key(connector_key),
                "platform_key": CONTRACT_SLUG_TO_PLATFORM_KEY.get(manifest.platform_slug, platform.platform_key),
            }
        )
    return contexts


def _document_request_actions(
    session: Session,
    *,
    tenant_id: int,
    company_id: int | None,
    contexts: list[dict[str, Any]],
    selected_workers: set[int],
    limit: int,
) -> list[dict[str, Any]]:
    context_by_account = {context["account"].id: context for context in contexts}
    if not context_by_account:
        return []
    statement = select(PlatformObservedDocumentRequest).where(
        PlatformObservedDocumentRequest.tenant_id == tenant_id,
        PlatformObservedDocumentRequest.account_proposal_id.in_(list(context_by_account)),
        PlatformObservedDocumentRequest.matched_document_version_id.is_not(None),
        PlatformObservedDocumentRequest.external_status.notin_({"accepted", "not_applicable"}),
    )
    if selected_workers:
        statement = statement.where(PlatformObservedDocumentRequest.local_worker_id.in_(selected_workers))
    rows = session.scalars(statement.order_by(PlatformObservedDocumentRequest.severity.desc(), PlatformObservedDocumentRequest.last_seen_at.desc()).limit(limit)).all()
    actions: list[dict[str, Any]] = []
    for request in rows:
        if request.entity_scope == "worker" and request.local_worker_id is None:
            continue
        context = context_by_account.get(request.account_proposal_id)
        if context is None:
            continue
        if company_id is not None and request.local_company_id not in {None, company_id}:
            continue
        operation = "upload_worker_document" if request.entity_scope == "worker" else "upload_company_document"
        actions.append(
            _base_action(context)
            | {
                "action_id": f"document_request:{request.id}",
                "kind": "document_request",
                "operation": operation,
                "entity_scope": request.entity_scope,
                "worker_id": request.local_worker_id,
                "company_id": request.local_company_id or company_id,
                "document_version_id": request.matched_document_version_id,
                "observed_request_id": request.id,
                "title": request.external_requirement_label,
                "detail": request.rejection_reason or request.external_comment or request.external_status,
                "source_status": request.external_status,
                "severity": request.severity,
            }
        )
    return actions


def _missing_worker_actions(
    session: Session,
    *,
    tenant_id: int,
    company_id: int | None,
    contexts: list[dict[str, Any]],
    selected_workers: set[int],
    remaining: int,
) -> list[dict[str, Any]]:
    if remaining <= 0:
        return []
    statement = select(Worker).where(Worker.tenant_id == tenant_id, Worker.status == "active")
    if company_id is not None:
        statement = statement.where(Worker.company_id == company_id)
    if selected_workers:
        statement = statement.where(Worker.id.in_(selected_workers))
    workers = list(session.scalars(statement.order_by(Worker.last_name, Worker.first_name)))
    actions: list[dict[str, Any]] = []
    for context in contexts:
        for worker in workers:
            if _worker_exists_in_context(session, tenant_id=tenant_id, worker=worker, context=context):
                continue
            actions.append(
                _base_action(context)
                | {
                    "action_id": f"missing_worker:{context['account'].id}:{worker.id}",
                    "kind": "missing_worker",
                    "operation": "upsert_worker",
                    "entity_scope": "worker",
                    "worker_id": worker.id,
                    "company_id": worker.company_id,
                    "document_version_id": None,
                    "observed_request_id": None,
                    "title": f"Alta trabajador: {worker.first_name} {worker.last_name}",
                    "detail": "No consta registro confirmado para este trabajador en la plataforma/cuenta.",
                    "source_status": "missing_in_platform_context",
                    "severity": "orange",
                }
            )
            if len(actions) >= remaining:
                return actions
    return actions


def _base_action(context: dict[str, Any]) -> dict[str, Any]:
    account: PlatformRpaAccountProposal = context["account"]
    manifest: PlatformRpaManifest = context["manifest"]
    platform: ExternalPlatform = context["platform"]
    return {
        "account_proposal_id": account.id,
        "platform_account_id": account.platform_account_id,
        "manifest_id": manifest.id,
        "platform_slug": manifest.platform_slug,
        "platform_name": manifest.platform_name,
        "platform_key": context["platform_key"],
        "external_platform_id": platform.id,
        "external_company_name": account.external_company_name,
        "host": account.host,
        "connector_key": context["connector_key"],
        "live_adapter_status": context["live_adapter_status"],
        "active": context["active"],
    }


def _attach_preview(session: Session, *, tenant_id: int, action: dict[str, Any]) -> None:
    if action["connector_key"] is None:
        action.update(
            {
                "preview_status": "blocked_no_write_connector",
                "ready_for_submit": False,
                "capture_recommended": False,
                "blockers": [{"kind": "no_write_connector", "detail": "No hay conector de escritura registrado."}],
                "planned_external_changes": [],
                "next_action": "Registrar conector protegido antes de preparar escritura.",
            }
        )
        return
    try:
        preview = build_write_operation_preview(
            session,
            tenant_id=tenant_id,
            account_proposal_id=action["account_proposal_id"],
            operation=action["operation"],
            company_id=action.get("company_id"),
            worker_id=action.get("worker_id"),
            document_version_id=action.get("document_version_id"),
        )
    except WritePreviewError as exc:
        action.update(
            {
                "preview_status": "preview_error",
                "ready_for_submit": False,
                "capture_recommended": True,
                "blockers": [{"kind": "preview_error", "detail": str(exc)}],
                "planned_external_changes": [],
                "next_action": str(exc),
            }
        )
        return
    preview_status = str(preview.get("status") or "blocked")
    blockers = preview.get("blockers") if isinstance(preview.get("blockers"), list) else []
    planned_changes = preview.get("planned_external_changes")
    action.update(
        {
            "preview_status": preview_status,
            "ready_for_submit": preview_status == "preview_ready",
            "capture_recommended": preview_status != "preview_ready"
            or action["live_adapter_status"] != "specific_live_adapter_available",
            "blockers": blockers,
            "planned_external_changes": planned_changes if isinstance(planned_changes, list) else [],
            "next_action": preview.get("next_action") or "Revisar preview.",
        }
    )


def _worker_exists_in_context(
    session: Session,
    *,
    tenant_id: int,
    worker: Worker,
    context: dict[str, Any],
) -> bool:
    account: PlatformRpaAccountProposal = context["account"]
    platform: ExternalPlatform = context["platform"]
    statement = select(WorkerPlatformRegistration).where(
        WorkerPlatformRegistration.tenant_id == tenant_id,
        WorkerPlatformRegistration.worker_id == worker.id,
        WorkerPlatformRegistration.external_platform_id == platform.id,
        WorkerPlatformRegistration.registration_status.in_(EXISTING_WORKER_REGISTRATION_STATUSES),
    )
    if account.platform_account_id is not None:
        statement = statement.where(
            or_(
                WorkerPlatformRegistration.platform_account_id == account.platform_account_id,
                WorkerPlatformRegistration.platform_account_id.is_(None),
            )
        )
    return session.scalar(statement.limit(1)) is not None


def _summary(actions: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind = Counter(str(action["kind"]) for action in actions)
    by_preview = Counter(str(action.get("preview_status") or "unknown") for action in actions)
    by_platform = Counter(str(action["platform_slug"]) for action in actions)
    return {
        "actions": len(actions),
        "document_requests": by_kind.get("document_request", 0),
        "missing_workers": by_kind.get("missing_worker", 0),
        "ready_for_submit": sum(1 for action in actions if action.get("ready_for_submit") is True),
        "blocked": sum(1 for action in actions if action.get("ready_for_submit") is not True),
        "capture_recommended": sum(1 for action in actions if action.get("capture_recommended") is True),
        "with_live_helper": sum(
            1 for action in actions if action.get("live_adapter_status") == "specific_live_adapter_available"
        ),
        "by_preview_status": dict(sorted(by_preview.items())),
        "by_kind": dict(sorted(by_kind.items())),
        "by_platform": dict(sorted(by_platform.items())),
    }
