from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("IPRL_CAE_CONFIG_FILE", str(ROOT / "config" / "iprl-cae.local.example.toml"))
os.environ.setdefault("IPRL_CAE_ENVIRONMENT", "local")
os.environ.setdefault("IPRL_CAE_DATABASE_URL", f"sqlite:///{(ROOT / 'storage' / 'demo.db').as_posix()}")
os.environ.setdefault("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(ROOT / "storage" / "documents"))
os.environ.setdefault("IPRL_CAE_SECRET_KEY", "local-demo-secret-key-for-development-only-32")

from sqlalchemy import select

from app.db.demo_seed import create_demo_database
from app.db.models import PlatformReviewSchedule, User
from app.db.session import get_session_factory
from app.services.audit import public_state, record_audit
from app.services.platform_review_runs import run_schedule_now, run_to_read
from app.services.platform_review_schedules import (
    ensure_review_schedules,
    list_due_review_schedules,
    schedules_to_read,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run due platform review schedules through the guarded readonly connector pipeline."
    )
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--priority-group", default="arm_first_priority")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--list-only", action="store_true", help="Only print due schedules without executing runs.")
    parser.add_argument(
        "--ensure",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create missing review schedules before checking due runs.",
    )
    args = parser.parse_args()

    create_demo_database()
    session_factory = get_session_factory()
    with session_factory() as session:
        actor = session.scalar(
            select(User).where(User.tenant_id == args.tenant_id, User.email == "demo@demo.invalid")
        )
        actor_user_id = actor.id if actor is not None else None
        if args.ensure:
            ensure_review_schedules(
                session,
                tenant_id=args.tenant_id,
                actor_user_id=actor_user_id,
                priority_group=args.priority_group,
            )
            session.commit()

        due = list_due_review_schedules(session, tenant_id=args.tenant_id, limit=args.limit)
        if args.list_only:
            print(
                json.dumps(
                    {
                        "tenant_id": args.tenant_id,
                        "due_count": len(due),
                        "due_schedules": schedules_to_read(session, due),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            return

        executed: list[dict[str, Any]] = []
        for schedule in due:
            run = run_schedule_now(
                session,
                tenant_id=schedule.tenant_id,
                schedule_id=schedule.id,
                actor_user_id=actor_user_id,
                trigger_source="due_schedule_runner",
            )
            if run is None:
                executed.append(_missing_run_summary(schedule))
                continue
            record_audit(
                session,
                tenant_id=schedule.tenant_id,
                actor_user_id=actor_user_id,
                action="platform_review_runs.due_runner",
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
            executed.append(_run_summary(run_to_read(run)))

        print(
            json.dumps(
                {
                    "tenant_id": args.tenant_id,
                    "due_count": len(due),
                    "executed_count": len(executed),
                    "executed": executed,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run["id"],
        "schedule_id": run["schedule_id"],
        "platform_slug": run["platform_slug"],
        "platform_name": run["platform_name"],
        "trigger_source": run["trigger_source"],
        "status": run["status"],
        "result_status": run["result_status"],
        "result_summary": run["result_summary"],
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "dry_run": run["dry_run"],
        "manual_approval_required": run["manual_approval_required"],
    }


def _missing_run_summary(schedule: PlatformReviewSchedule) -> dict[str, Any]:
    return {
        "schedule_id": schedule.id,
        "status": "failed",
        "result_status": "schedule_not_found",
        "result_summary": "No se pudo ejecutar el schedule seleccionado.",
    }


if __name__ == "__main__":
    main()
