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
from app.services.company_prl_archive_import import ARM_TAX_ID
from app.services.document_import_approval import approve_company_imported_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Aprueba documentos ARM importados sin revision humana.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--company-tax-id", default=ARM_TAX_ID)
    parser.add_argument("--actor-email", default="demo@demo.invalid")
    parser.add_argument(
        "--review-comment",
        default="Aprobado por instruccion del usuario durante la migracion ARM.",
    )
    args = parser.parse_args()

    create_demo_database()
    session_factory = get_session_factory()
    with session_factory() as session:
        actor = session.scalar(
            select(User).where(User.tenant_id == args.tenant_id, User.email == args.actor_email)
        )
        result = approve_company_imported_documents(
            session,
            tenant_id=args.tenant_id,
            company_tax_id=args.company_tax_id,
            actor_user_id=actor.id if actor is not None else None,
            review_comment=args.review_comment,
        )
        session.commit()
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
