from __future__ import annotations

# ruff: noqa: E402

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

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
from app.db.models import User
from app.db.session import get_session_factory
from app.services.arm_operational_data import normalize_arm_operational_data
from app.services.audit import public_state, record_audit
from app.services.platform_current_accounts_sync import load_current_platform_rows, sync_current_platform_accounts
from app.services.platform_contracts import import_all_arm_contracts
from app.services.platform_review_schedules import activate_twelve_hour_review_schedules, ensure_review_schedules


def main() -> None:
    create_demo_database()
    session_factory = get_session_factory()
    with session_factory() as session:
        actor = session.scalar(select(User).where(User.tenant_id == 1, User.email == "demo@demo.invalid"))
        actor_user_id = actor.id if actor else None
        operational = normalize_arm_operational_data(
            session,
            tenant_id=1,
            actor_user_id=actor_user_id,
        )
        contracts = import_all_arm_contracts(
            session,
            tenant_id=1,
            actor_user_id=actor_user_id,
        )
        current_platforms_path = ROOT / "requisitos" / "usuarios y contraseñas PLATAFORMAS.xlsx"
        current_accounts = None
        if current_platforms_path.exists():
            current_accounts = sync_current_platform_accounts(
                session,
                tenant_id=1,
                actor_user_id=actor_user_id,
                rows=load_current_platform_rows(current_platforms_path),
                source_path=current_platforms_path,
            )
            schedules = ensure_review_schedules(
                session,
                tenant_id=1,
                actor_user_id=actor_user_id,
                priority_group=None,
            )
        else:
            ensure_review_schedules(
                session,
                tenant_id=1,
                actor_user_id=actor_user_id,
                priority_group=None,
            )
            schedules = activate_twelve_hour_review_schedules(
                session,
                tenant_id=1,
                actor_user_id=actor_user_id,
                priority_group=None,
            )
        summary = {
            "operational": asdict(operational),
            "contracts": asdict(contracts),
            "current_platform_accounts": asdict(current_accounts) if current_accounts is not None else None,
            "schedules_activated": len(schedules),
        }
        record_audit(
            session,
            tenant_id=1,
            actor_user_id=actor_user_id,
            action="arm_operational_state.load",
            entity_type="tenant",
            entity_id=1,
            after=public_state(summary),
        )
        session.commit()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
