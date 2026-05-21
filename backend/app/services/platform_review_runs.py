from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.rpa.readonly_registry import get_readonly_connector
from app.core.config import get_settings
from app.db.models import (
    PlatformReviewRun,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
)
from app.services.platform_credentials import resolve_platform_credentials
from app.services.platform_external_statuses import (
    observations_from_payload,
    persist_external_status_observations,
)


def list_review_runs(
    session: Session,
    *,
    tenant_id: int,
    schedule_id: int | None = None,
) -> list[PlatformReviewRun]:
    statement = select(PlatformReviewRun).where(PlatformReviewRun.tenant_id == tenant_id)
    if schedule_id is not None:
        statement = statement.where(PlatformReviewRun.schedule_id == schedule_id)
    return list(session.scalars(statement.order_by(PlatformReviewRun.id.desc())))


def run_schedule_now(
    session: Session,
    *,
    tenant_id: int,
    schedule_id: int,
    actor_user_id: int | None,
    account_proposal_id: int | None = None,
    trigger_source: str = "manual_run_now",
) -> PlatformReviewRun | None:
    schedule = session.scalar(
        select(PlatformReviewSchedule).where(
            PlatformReviewSchedule.tenant_id == tenant_id,
            PlatformReviewSchedule.id == schedule_id,
        )
    )
    if schedule is None:
        return None
    manifest = session.get(PlatformRpaManifest, schedule.manifest_id)
    if manifest is None or manifest.tenant_id != tenant_id:
        return None
    account = _resolve_account(
        session,
        tenant_id=tenant_id,
        manifest_id=manifest.id,
        account_proposal_id=account_proposal_id,
    )
    run = PlatformReviewRun(
        tenant_id=tenant_id,
        schedule_id=schedule.id,
        manifest_id=manifest.id,
        account_proposal_id=account.id if account is not None else None,
        external_platform_id=manifest.external_platform_id,
        platform_slug=manifest.platform_slug,
        platform_name=manifest.platform_name,
        operation="read_external_status",
        trigger_source=trigger_source,
        status="created",
        dry_run=True,
        manual_approval_required=True,
        started_at=datetime.now(timezone.utc),
        created_by=actor_user_id,
        evidence_json={
            "scope": "readonly_login_probe",
            "account_selected": account.source_platform_account_id if account is not None else None,
        },
    )
    session.add(run)
    session.flush()

    if account is None:
        _finish_run(run, "failed", "account_missing", "No hay cuenta ARM seleccionable para la plataforma.", {})
        _update_schedule_after_run(schedule, run)
        session.flush()
        return run

    settings = get_settings()
    if not settings.features.platform_rpa_connectors or not settings.connectors.rpa_enabled:
        _finish_run(
            run,
            "blocked_feature_disabled",
            "rpa_disabled",
            "La ejecucion RPA real esta deshabilitada por configuracion.",
            {
                "required_flags": [
                    "features.platform_rpa_connectors=true",
                    "connectors.rpa_enabled=true",
                ]
            },
        )
        _update_schedule_after_run(schedule, run)
        session.flush()
        return run

    resolution = resolve_platform_credentials(
        secret_ref=account.credential_secret_ref,
        platform_account_id=account.source_platform_account_id,
    )
    if resolution.credentials is None:
        _finish_run(
            run,
            "blocked_missing_credentials",
            "credentials_missing",
            "No se encontraron credenciales en variables de entorno para la referencia segura.",
            {"expected_env_vars": resolution.expected_env_vars},
        )
        _update_schedule_after_run(schedule, run)
        session.flush()
        return run

    connector = get_readonly_connector(manifest.platform_slug)
    if connector is None:
        _finish_run(
            run,
            "failed",
            "connector_not_implemented",
            f"No hay conector RPA de lectura implementado para {manifest.platform_slug}.",
            {},
        )
        _update_schedule_after_run(schedule, run)
        session.flush()
        return run

    result = connector.run_login_probe(
        entry_url=account.entry_url or (manifest.entry_urls[0] if manifest.entry_urls else ""),
        credentials=resolution.credentials,
        expected_context=account.external_company_name or manifest.platform_name,
    )
    _finish_run(
        run,
        result.status,
        result.result_status,
        result.result_summary,
        result.evidence,
    )
    observations = observations_from_payload(result.evidence.get("external_document_statuses"))
    if observations and manifest.external_platform_id is not None:
        persisted = persist_external_status_observations(
            session,
            tenant_id=tenant_id,
            external_platform_id=manifest.external_platform_id,
            observations=observations,
        )
        run.evidence_json = {
            **(run.evidence_json or {}),
            "persisted_external_status_count": len(persisted),
        }
    _update_schedule_after_run(schedule, run)
    session.flush()
    return run


def run_to_read(run: PlatformReviewRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "schedule_id": run.schedule_id,
        "manifest_id": run.manifest_id,
        "account_proposal_id": run.account_proposal_id,
        "external_platform_id": run.external_platform_id,
        "platform_slug": run.platform_slug,
        "platform_name": run.platform_name,
        "operation": run.operation,
        "trigger_source": run.trigger_source,
        "status": run.status,
        "dry_run": run.dry_run,
        "manual_approval_required": run.manual_approval_required,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "result_status": run.result_status,
        "result_summary": run.result_summary,
        "error_summary": run.error_summary,
        "evidence_json": run.evidence_json,
        "created_at": run.created_at,
    }


def _resolve_account(
    session: Session,
    *,
    tenant_id: int,
    manifest_id: int,
    account_proposal_id: int | None,
) -> PlatformRpaAccountProposal | None:
    statement = select(PlatformRpaAccountProposal).where(
        PlatformRpaAccountProposal.tenant_id == tenant_id,
        PlatformRpaAccountProposal.manifest_id == manifest_id,
    )
    if account_proposal_id is not None:
        statement = statement.where(PlatformRpaAccountProposal.id == account_proposal_id)
    return session.scalar(statement.order_by(PlatformRpaAccountProposal.id))


def _finish_run(
    run: PlatformReviewRun,
    status: str,
    result_status: str,
    summary: str,
    evidence: dict[str, Any],
) -> PlatformReviewRun:
    run.status = status
    run.result_status = result_status
    run.result_summary = summary
    run.error_summary = summary if status in {"failed", "blocked_feature_disabled", "blocked_missing_credentials"} else None
    run.evidence_json = {
        **(run.evidence_json or {}),
        **evidence,
    }
    run.finished_at = datetime.now(timezone.utc)
    return run


def _update_schedule_after_run(schedule: PlatformReviewSchedule, run: PlatformReviewRun) -> None:
    schedule.last_run_at = run.finished_at
    schedule.last_result_status = run.result_status
    schedule.last_result_summary = run.result_summary
    if schedule.enabled:
        schedule.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=schedule.interval_minutes)
    else:
        schedule.next_run_at = None
