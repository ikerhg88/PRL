from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.rpa.readonly_registry import implemented_readonly_platform_slugs
from app.db.models import PlatformReviewSchedule, PlatformRpaManifest

DEFAULT_REVIEW_SCOPE = ["company", "workers", "documents", "incidents", "mappings"]
TWELVE_HOUR_INTERVAL_MINUTES = 720
DEFAULT_INTERVAL_MINUTES = TWELVE_HOUR_INTERVAL_MINUTES

WORKING_RESULT_STATUSES = {"login_likely_success", "completed", "readonly_status_counts_available"}
NOT_WORKING_RESULT_STATUSES = {
    "account_missing",
    "connector_not_implemented",
    "credentials_missing",
    "rpa_disabled",
}


def ensure_review_schedules(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    priority_group: str | None = "arm_first_priority",
) -> list[PlatformReviewSchedule]:
    manifests = _manifests(session, tenant_id=tenant_id, priority_group=priority_group)
    existing_by_manifest = {
        schedule.manifest_id: schedule
        for schedule in session.scalars(
            select(PlatformReviewSchedule).where(
                PlatformReviewSchedule.tenant_id == tenant_id,
                PlatformReviewSchedule.manifest_id.in_([manifest.id for manifest in manifests] or [-1]),
            )
        )
    }
    for manifest in manifests:
        if manifest.id in existing_by_manifest:
            continue
        schedule = PlatformReviewSchedule(
            tenant_id=tenant_id,
            manifest_id=manifest.id,
            external_platform_id=manifest.external_platform_id,
            enabled=False,
            interval_minutes=DEFAULT_INTERVAL_MINUTES,
            review_scope=list(DEFAULT_REVIEW_SCOPE),
            status="disabled",
            dry_run=True,
            manual_approval_required=True,
            notes="Controlador local creado; revision externa pendiente de activacion explicita.",
            created_by=actor_user_id,
        )
        session.add(schedule)
    session.flush()
    return list_review_schedules(session, tenant_id=tenant_id, priority_group=priority_group)


def activate_twelve_hour_review_schedules(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    priority_group: str | None = "arm_first_priority",
) -> list[PlatformReviewSchedule]:
    schedules = ensure_review_schedules(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        priority_group=priority_group,
    )
    for schedule in schedules:
        schedule.enabled = True
        schedule.interval_minutes = TWELVE_HOUR_INTERVAL_MINUTES
        schedule.status = "scheduled"
        schedule.next_run_at = _next_run_at(TWELVE_HOUR_INTERVAL_MINUTES)
        schedule.dry_run = True
        schedule.manual_approval_required = True
        if not schedule.notes:
            schedule.notes = (
                "Revision cada 12 horas en modo seguro: dry_run, aprobacion manual y solo "
                "lectura externa cuando exista conector autorizado."
            )
    session.flush()
    return list_review_schedules(session, tenant_id=tenant_id, priority_group=priority_group)


def build_review_health(
    session: Session,
    *,
    tenant_id: int,
    priority_group: str | None = "arm_first_priority",
) -> dict[str, Any]:
    schedules = list_review_schedules(session, tenant_id=tenant_id, priority_group=priority_group)
    rows = _health_rows(session, schedules)
    totals = {
        "platforms": len(rows),
        "working": sum(1 for row in rows if row["review_status"] == "working"),
        "not_working": sum(1 for row in rows if row["review_status"] == "not_working"),
        "not_configured": sum(1 for row in rows if row["review_status"] == "not_configured"),
        "not_checked": sum(1 for row in rows if row["review_status"] == "not_checked"),
    }
    safe_mode = all(row["dry_run"] and row["manual_approval_required"] for row in rows)
    return {
        "generated_at": datetime.now(timezone.utc),
        "priority_group": priority_group,
        "interval_minutes_required": TWELVE_HOUR_INTERVAL_MINUTES,
        "safe_mode": safe_mode,
        "totals": totals,
        "summary": (
            f"{totals['working']} funcionando, {totals['not_working']} no funcionando, "
            f"{totals['not_checked']} sin prueba y {totals['not_configured']} sin configurar."
        ),
        "platforms": rows,
    }


def list_review_schedules(
    session: Session,
    *,
    tenant_id: int,
    priority_group: str | None = "arm_first_priority",
) -> list[PlatformReviewSchedule]:
    statement = select(PlatformReviewSchedule).join(
        PlatformRpaManifest,
        PlatformRpaManifest.id == PlatformReviewSchedule.manifest_id,
    ).where(PlatformReviewSchedule.tenant_id == tenant_id)
    if priority_group is not None:
        statement = statement.where(PlatformRpaManifest.priority_group == priority_group)
    return list(
        session.scalars(
            statement.order_by(PlatformRpaManifest.platform_name, PlatformReviewSchedule.id)
        )
    )


def list_due_review_schedules(
    session: Session,
    *,
    tenant_id: int | None = None,
    now: datetime | None = None,
    limit: int | None = 20,
) -> list[PlatformReviewSchedule]:
    effective_now = now or datetime.now(timezone.utc)
    statement = select(PlatformReviewSchedule).where(
        PlatformReviewSchedule.enabled.is_(True),
        PlatformReviewSchedule.next_run_at.is_not(None),
        PlatformReviewSchedule.next_run_at <= effective_now,
    )
    if tenant_id is not None:
        statement = statement.where(PlatformReviewSchedule.tenant_id == tenant_id)
    statement = statement.order_by(PlatformReviewSchedule.next_run_at, PlatformReviewSchedule.id)
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement))


def update_review_schedule(
    session: Session,
    *,
    tenant_id: int,
    schedule_id: int,
    changes: dict[str, Any],
) -> PlatformReviewSchedule | None:
    schedule = session.scalar(
        select(PlatformReviewSchedule).where(
            PlatformReviewSchedule.tenant_id == tenant_id,
            PlatformReviewSchedule.id == schedule_id,
        )
    )
    if schedule is None:
        return None

    recalculate_next = False
    if "interval_minutes" in changes:
        schedule.interval_minutes = changes["interval_minutes"]
        recalculate_next = True
    if "review_scope" in changes:
        schedule.review_scope = changes["review_scope"]
    if "notes" in changes:
        schedule.notes = changes["notes"]
    if "enabled" in changes:
        schedule.enabled = changes["enabled"]
        recalculate_next = True
    if "status" in changes:
        status = changes["status"]
        if status == "scheduled":
            schedule.enabled = True
            recalculate_next = True
        elif status in {"disabled", "paused"}:
            schedule.enabled = False
            schedule.next_run_at = None
        schedule.status = status

    if schedule.enabled:
        schedule.status = "scheduled"
        if recalculate_next or schedule.next_run_at is None:
            schedule.next_run_at = _next_run_at(schedule.interval_minutes)
    else:
        schedule.status = schedule.status if schedule.status == "paused" else "disabled"
        schedule.next_run_at = None

    schedule.dry_run = True
    schedule.manual_approval_required = True
    session.flush()
    return schedule


def schedule_to_read(schedule: PlatformReviewSchedule, manifest: PlatformRpaManifest) -> dict[str, Any]:
    return {
        "id": schedule.id,
        "tenant_id": schedule.tenant_id,
        "manifest_id": schedule.manifest_id,
        "external_platform_id": schedule.external_platform_id,
        "platform_slug": manifest.platform_slug,
        "platform_name": manifest.platform_name,
        "priority_group": manifest.priority_group,
        "enabled": schedule.enabled,
        "interval_minutes": schedule.interval_minutes,
        "review_scope": schedule.review_scope,
        "status": schedule.status,
        "dry_run": schedule.dry_run,
        "manual_approval_required": schedule.manual_approval_required,
        "last_run_at": schedule.last_run_at,
        "next_run_at": schedule.next_run_at,
        "last_result_status": schedule.last_result_status,
        "last_result_summary": schedule.last_result_summary,
        "notes": schedule.notes,
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
    }


def schedules_to_read(session: Session, schedules: list[PlatformReviewSchedule]) -> list[dict[str, Any]]:
    if not schedules:
        return []
    manifests = {
        manifest.id: manifest
        for manifest in session.scalars(
            select(PlatformRpaManifest).where(PlatformRpaManifest.id.in_({schedule.manifest_id for schedule in schedules}))
        )
    }
    return [schedule_to_read(schedule, manifests[schedule.manifest_id]) for schedule in schedules if schedule.manifest_id in manifests]


def _health_rows(session: Session, schedules: list[PlatformReviewSchedule]) -> list[dict[str, Any]]:
    if not schedules:
        return []
    manifests = {
        manifest.id: manifest
        for manifest in session.scalars(
            select(PlatformRpaManifest).where(
                PlatformRpaManifest.id.in_({schedule.manifest_id for schedule in schedules})
            )
        )
    }
    return [
        _health_row(schedule, manifests[schedule.manifest_id])
        for schedule in schedules
        if schedule.manifest_id in manifests
    ]


def _health_row(schedule: PlatformReviewSchedule, manifest: PlatformRpaManifest) -> dict[str, Any]:
    configured_12h = schedule.enabled and schedule.interval_minutes == TWELVE_HOUR_INTERVAL_MINUTES
    connector_available = manifest.platform_slug in implemented_readonly_platform_slugs()
    working: list[str] = []
    not_working: list[str] = []

    if configured_12h:
        working.append("Programado cada 12 horas.")
    else:
        not_working.append("No esta activo cada 12 horas.")

    if schedule.dry_run and schedule.manual_approval_required:
        working.append("Controles seguros activos: dry_run y aprobacion manual.")
    else:
        not_working.append("Faltan controles seguros obligatorios.")

    if connector_available:
        working.append("Conector de solo lectura disponible.")
    else:
        not_working.append("Conector de lectura real no implementado para esta plataforma.")

    if schedule.last_result_status in WORKING_RESULT_STATUSES:
        working.append("Ultima lectura registrada como correcta.")
    elif schedule.last_result_status in NOT_WORKING_RESULT_STATUSES:
        not_working.append(f"Ultima lectura bloqueada o fallida: {schedule.last_result_status}.")
    elif schedule.last_result_status is None:
        not_working.append("Todavia no hay ninguna lectura ejecutada.")
    else:
        not_working.append(f"Ultimo resultado pendiente de revisar: {schedule.last_result_status}.")

    review_status, status_color = _health_status(schedule, configured_12h)
    return {
        "schedule_id": schedule.id,
        "manifest_id": schedule.manifest_id,
        "platform_slug": manifest.platform_slug,
        "platform_name": manifest.platform_name,
        "enabled": schedule.enabled,
        "interval_minutes": schedule.interval_minutes,
        "configured_every_12h": configured_12h,
        "connector_available": connector_available,
        "dry_run": schedule.dry_run,
        "manual_approval_required": schedule.manual_approval_required,
        "last_run_at": schedule.last_run_at,
        "next_run_at": schedule.next_run_at,
        "last_result_status": schedule.last_result_status,
        "last_result_summary": schedule.last_result_summary,
        "review_status": review_status,
        "status_color": status_color,
        "working": working,
        "not_working": not_working,
    }


def _health_status(
    schedule: PlatformReviewSchedule,
    configured_12h: bool,
) -> tuple[str, str]:
    if not configured_12h:
        return "not_configured", "orange"
    if schedule.last_result_status is None:
        return "not_checked", "orange"
    if schedule.last_result_status in WORKING_RESULT_STATUSES:
        return "working", "green"
    return "not_working", "red"


def _manifests(
    session: Session,
    *,
    tenant_id: int,
    priority_group: str | None,
) -> list[PlatformRpaManifest]:
    statement = select(PlatformRpaManifest).where(PlatformRpaManifest.tenant_id == tenant_id)
    if priority_group is not None:
        statement = statement.where(PlatformRpaManifest.priority_group == priority_group)
    return list(session.scalars(statement.order_by(PlatformRpaManifest.platform_name)))


def _next_run_at(interval_minutes: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=interval_minutes)
