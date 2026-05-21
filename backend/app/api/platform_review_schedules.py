from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.dependencies import ActorUserId, DbSession, TenantId, require_tenant
from app.db.models import PlatformReviewSchedule
from app.schemas import (
    PlatformReviewHealthRead,
    PlatformReviewRunRead,
    PlatformReviewRunRequest,
    PlatformReviewScheduleRead,
    PlatformReviewScheduleUpdate,
    RpaVariantPlanRead,
)
from app.services.access_control import require_tenant_wide_access
from app.services.audit import public_state, record_audit
from app.services.platform_review_schedules import (
    activate_twelve_hour_review_schedules,
    build_review_health,
    ensure_review_schedules,
    list_review_schedules,
    schedules_to_read,
    update_review_schedule,
)
from app.services.platform_review_runs import list_review_runs, run_schedule_now, run_to_read
from app.services.rpa_variant_planner import build_rpa_variant_plan

router = APIRouter(prefix="/platform-review-schedules", tags=["platform-review-schedules"])


@router.get("", response_model=list[PlatformReviewScheduleRead])
def list_platform_review_schedules(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    priority_group: str | None = Query(default="arm_first_priority"),
) -> list[dict[str, Any]]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    priority_group = _normalized_priority_group(priority_group)
    schedules = list_review_schedules(session, tenant_id=tenant_id, priority_group=priority_group)
    return schedules_to_read(session, schedules)


@router.post("/ensure", response_model=list[PlatformReviewScheduleRead])
def ensure_platform_review_schedules(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    priority_group: str | None = Query(default="arm_first_priority"),
) -> list[dict[str, Any]]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    priority_group = _normalized_priority_group(priority_group)
    before_count = _schedule_count(session, tenant_id)
    schedules = ensure_review_schedules(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        priority_group=priority_group,
    )
    after_count = _schedule_count(session, tenant_id)
    if after_count != before_count:
        record_audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="platform_review_schedules.ensure",
            entity_type="platform_review_schedule",
            entity_id=None,
            after=public_state(
                {
                    "priority_group": priority_group,
                    "created": after_count - before_count,
                    "total": after_count,
                }
            ),
        )
    session.commit()
    return schedules_to_read(session, schedules)


@router.post("/activate-12h", response_model=list[PlatformReviewScheduleRead])
def activate_platform_review_schedules_12h(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    priority_group: str | None = Query(default="arm_first_priority"),
) -> list[dict[str, Any]]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    priority_group = _normalized_priority_group(priority_group)
    before = schedules_to_read(
        session,
        list_review_schedules(session, tenant_id=tenant_id, priority_group=priority_group),
    )
    schedules = activate_twelve_hour_review_schedules(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        priority_group=priority_group,
    )
    after = schedules_to_read(session, schedules)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_review_schedules.activate_12h",
        entity_type="platform_review_schedule",
        entity_id=None,
        before=public_state({"priority_group": priority_group, "schedules": before}),
        after=public_state({"priority_group": priority_group, "schedules": after}),
    )
    session.commit()
    return after


@router.get("/health", response_model=PlatformReviewHealthRead)
def get_platform_review_health(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    priority_group: str | None = Query(default="arm_first_priority"),
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    priority_group = _normalized_priority_group(priority_group)
    return build_review_health(session, tenant_id=tenant_id, priority_group=priority_group)


@router.get("/rpa-variant-plan", response_model=RpaVariantPlanRead)
def get_rpa_variant_plan(
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
    priority_group: str | None = Query(default="all"),
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return build_rpa_variant_plan(
        session,
        tenant_id=tenant_id,
        priority_group=_normalized_priority_group(priority_group),
    )


@router.patch("/{schedule_id}", response_model=PlatformReviewScheduleRead)
def update_platform_review_schedule(
    schedule_id: int,
    payload: PlatformReviewScheduleUpdate,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    existing = list(
        schedule
        for schedule in list_review_schedules(session, tenant_id=tenant_id, priority_group=None)
        if schedule.id == schedule_id
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform review schedule not found.")
    before = schedules_to_read(session, existing)[0]
    schedule = update_review_schedule(
        session,
        tenant_id=tenant_id,
        schedule_id=schedule_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform review schedule not found.")
    after = schedules_to_read(session, [schedule])[0]
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_review_schedules.update",
        entity_type="platform_review_schedule",
        entity_id=schedule.id,
        before=public_state(before),
        after=public_state(after),
    )
    session.commit()
    return after


@router.get("/{schedule_id}/runs", response_model=list[PlatformReviewRunRead])
def list_platform_review_runs(
    schedule_id: int,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> list[dict[str, Any]]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    return [run_to_read(run) for run in list_review_runs(session, tenant_id=tenant_id, schedule_id=schedule_id)]


@router.post("/{schedule_id}/run-now", response_model=PlatformReviewRunRead, status_code=201)
def run_platform_review_now(
    schedule_id: int,
    payload: PlatformReviewRunRequest,
    tenant_id: TenantId,
    session: DbSession,
    actor_user_id: ActorUserId,
) -> dict[str, Any]:
    require_tenant(session, tenant_id)
    require_tenant_wide_access(session, tenant_id=tenant_id, user_id=actor_user_id)
    run = run_schedule_now(
        session,
        tenant_id=tenant_id,
        schedule_id=schedule_id,
        actor_user_id=actor_user_id,
        account_proposal_id=payload.account_proposal_id,
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform review schedule not found.")
    read = run_to_read(run)
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform_review_runs.run_now",
        entity_type="platform_review_run",
        entity_id=run.id,
        after=public_state(
            {
                "id": run.id,
                "schedule_id": run.schedule_id,
                "platform_slug": run.platform_slug,
                "status": run.status,
                "result_status": run.result_status,
                "dry_run": run.dry_run,
                "manual_approval_required": run.manual_approval_required,
            }
        ),
    )
    session.commit()
    return read


def _schedule_count(session: DbSession, tenant_id: int) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(PlatformReviewSchedule).where(PlatformReviewSchedule.tenant_id == tenant_id)
        )
        or 0
    )


def _normalized_priority_group(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"", "all", "*", "none", "null"}:
        return None
    return value
