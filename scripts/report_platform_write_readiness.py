from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
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

from app.db.models import Company, Worker
from app.db.session import get_session_factory
from app.services.platform_write_probe_matrix import build_platform_write_probe_matrix


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera matriz de capacidad de alta por plataforma actual.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--company-tax-id", default="B95868543")
    parser.add_argument("--worker-id", type=int, default=None)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "artifacts" / "platform-write-readiness")
    args = parser.parse_args()

    session_factory = get_session_factory()
    with session_factory() as session:
        company = session.scalar(
            select(Company).where(Company.tenant_id == args.tenant_id, Company.tax_id == args.company_tax_id)
        )
        if company is None:
            raise SystemExit("ARM company not found.")
        worker = _worker(session, tenant_id=args.tenant_id, company_id=company.id, worker_id=args.worker_id)
        matrix = asyncio.run(
            build_platform_write_probe_matrix(
                session,
                tenant_id=args.tenant_id,
                company_id=company.id,
                worker_id=worker.id if worker else None,
                operations=("upsert_worker",),
                connector_dry_run=False,
            )
        )
        rows = [_readiness_row(row) for row in matrix["rows"]]
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "company": matrix["company"],
            "worker_candidate": matrix["worker_candidate"],
            "summary": _summary(rows),
            "rows": rows,
        }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    stem = f"current_platform_write_readiness_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    json_path = args.report_dir / f"{stem}.json"
    markdown_path = args.report_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload["summary"] | {"json": str(json_path), "markdown": str(markdown_path)}, ensure_ascii=False, indent=2))


def _worker(session, *, tenant_id: int, company_id: int, worker_id: int | None) -> Worker | None:
    statement = select(Worker).where(Worker.tenant_id == tenant_id, Worker.company_id == company_id)
    if worker_id is not None:
        statement = statement.where(Worker.id == worker_id)
    workers = list(session.scalars(statement.order_by(Worker.id)))
    if not workers:
        return None
    return max(workers, key=_worker_score)


def _worker_score(worker: Worker) -> int:
    values = (
        worker.identifier_value,
        worker.identifier_last4,
        worker.nationality,
        worker.contract_type,
        worker.work_position,
        worker.social_security_number,
        worker.email,
        worker.phone,
        worker.medical_fitness_status,
        worker.medical_fitness_expires_at,
    )
    return sum(1 for value in values if value is not None and str(value).strip())


def _readiness_row(row: dict[str, object]) -> dict[str, object]:
    live_adapter_status = str(row.get("live_adapter_status") or "")
    preview_ready = bool(row.get("preview_ready"))
    mapping_ready = bool(row.get("mapping_ready"))
    local_data_ready = bool(row.get("local_data_ready"))
    account_ready = bool(row.get("account_ready_for_live"))
    can_submit_now = (
        preview_ready
        and mapping_ready
        and local_data_ready
        and account_ready
        and live_adapter_status == "specific_live_adapter_available"
    )
    blockers = []
    if not account_ready:
        blockers.append("cuenta en modo protegido/dry-run")
    if not local_data_ready:
        blockers.append("faltan datos ARM obligatorios")
    if not mapping_ready:
        blockers.append("falta mapeo/captura editable aprobada")
    if live_adapter_status == "blocked_live_adapter_missing":
        blockers.append("falta helper live de escritura")
    elif live_adapter_status == "no_write_connector":
        blockers.append("no hay conector de escritura registrado")
    return {
        "platform_slug": row.get("platform_slug"),
        "platform_name": row.get("platform_name"),
        "external_company_name": row.get("external_company_name"),
        "account_proposal_id": row.get("account_proposal_id"),
        "can_register_worker_now": can_submit_now,
        "capability": "si_alta_real_lista" if can_submit_now else "no_bloqueado",
        "blockers": blockers,
        "preview_status": row.get("status"),
        "mapping_ready": mapping_ready,
        "local_data_ready": local_data_ready,
        "account_ready_for_live": account_ready,
        "live_adapter_status": live_adapter_status,
        "next_action": row.get("next_action"),
    }


def _summary(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "active_contexts_checked": len(rows),
        "can_register_worker_now": sum(1 for row in rows if row["can_register_worker_now"]),
        "blocked": sum(1 for row in rows if not row["can_register_worker_now"]),
        "specific_live_adapter_available": sum(
            1 for row in rows if row["live_adapter_status"] == "specific_live_adapter_available"
        ),
        "blocked_live_adapter_missing": sum(
            1 for row in rows if row["live_adapter_status"] == "blocked_live_adapter_missing"
        ),
        "no_write_connector": sum(
            1 for row in rows if row["live_adapter_status"] == "no_write_connector"
        ),
    }


def _markdown(payload: dict[str, object]) -> str:
    rows = payload["rows"]
    assert isinstance(rows, list)
    lines = [
        "# Matriz de alta de trabajador por plataforma actual",
        "",
        f"- Empresa: {payload['company']}",
        f"- Trabajador candidato: {payload['worker_candidate']}",
        f"- Resumen: {payload['summary']}",
        "",
        "| Plataforma | Cuenta/empresa externa | Alta trabajador ya | Bloqueo principal |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        assert isinstance(row, dict)
        blockers = row.get("blockers") or []
        blocker_text = ", ".join(str(item) for item in blockers) if blockers else "sin bloqueo"
        lines.append(
            "| "
            f"{row.get('platform_name')} | "
            f"{row.get('external_company_name')} | "
            f"{'SI' if row.get('can_register_worker_now') else 'NO'} | "
            f"{blocker_text} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
