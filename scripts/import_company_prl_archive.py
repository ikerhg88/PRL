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
from app.services.company_prl_archive_import import (
    ARM_COMPANY_NAME,
    ARM_TAX_ID,
    import_company_prl_archive,
    write_import_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa un paquete ZIP PRL/CAE de empresa al Hub.")
    parser.add_argument("archive", type=Path, help="Ruta del ZIP PRL/CAE.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--company-tax-id", default=ARM_TAX_ID)
    parser.add_argument("--company-name", default=ARM_COMPANY_NAME)
    parser.add_argument("--actor-email", default="demo@demo.invalid")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "artifacts" / "arm-prl-import")
    args = parser.parse_args()

    create_demo_database()
    session_factory = get_session_factory()
    with session_factory() as session:
        actor = session.scalar(
            select(User).where(User.tenant_id == args.tenant_id, User.email == args.actor_email)
        )
        result = import_company_prl_archive(
            session,
            archive_path=args.archive.resolve(),
            tenant_id=args.tenant_id,
            actor_user_id=actor.id if actor is not None else None,
            company_tax_id=args.company_tax_id,
            company_name=args.company_name,
        )
        json_path, markdown_path = write_import_report(result, report_dir=args.report_dir)
        session.commit()
    payload = asdict(result) | {
        "report_json": str(json_path),
        "report_markdown": str(markdown_path),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
