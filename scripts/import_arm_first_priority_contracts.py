from __future__ import annotations

# ruff: noqa: E402

import argparse
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
from app.services.audit import public_state, record_audit
from app.services.platform_contracts import (
    DEFAULT_CONTRACT_BUNDLE,
    import_first_priority_arm_contracts,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import ARM first-priority RPA contract manifests as disabled proposals."
    )
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--source-root", default=str(DEFAULT_CONTRACT_BUNDLE))
    args = parser.parse_args()

    create_demo_database()
    session_factory = get_session_factory()
    with session_factory() as session:
        actor = session.scalar(
            select(User).where(User.tenant_id == args.tenant_id, User.email == "demo@demo.invalid")
        )
        result = import_first_priority_arm_contracts(
            session,
            tenant_id=args.tenant_id,
            actor_user_id=actor.id if actor else None,
            source_root=Path(args.source_root),
        )
        record_audit(
            session,
            tenant_id=args.tenant_id,
            actor_user_id=actor.id if actor else None,
            action="platform_contracts.import_arm_first_priority",
            entity_type="platform_rpa_manifest",
            entity_id=None,
            after=public_state(asdict(result)),
        )
        session.commit()
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
