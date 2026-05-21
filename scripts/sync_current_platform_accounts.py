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
from app.services.platform_current_accounts_sync import (
    load_current_platform_rows,
    sync_current_platform_accounts,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincroniza plataformas actuales desde Excel.")
    parser.add_argument("excel", type=Path, help="Excel de usuarios y contrasenas de plataformas.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--actor-email", default="demo@demo.invalid")
    args = parser.parse_args()

    create_demo_database()
    rows = load_current_platform_rows(args.excel)
    session_factory = get_session_factory()
    with session_factory() as session:
        actor = session.scalar(
            select(User).where(User.tenant_id == args.tenant_id, User.email == args.actor_email)
        )
        result = sync_current_platform_accounts(
            session,
            tenant_id=args.tenant_id,
            actor_user_id=actor.id if actor is not None else None,
            rows=rows,
            source_path=args.excel,
        )
        session.commit()
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
