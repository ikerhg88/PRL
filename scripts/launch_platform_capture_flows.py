from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import os
import sys
from datetime import datetime, timezone
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

from app.db.models import PlatformReviewRun, PlatformRpaAccountProposal, PlatformRpaManifest
from app.db.session import get_session_factory
from app.services.audit import public_state, record_audit
from app.services.platform_current_accounts_sync import ACTIVE_ACCOUNT_STATUS
from app.services.rpa_assisted_browser import (
    launch_visible_browser_for_gateway_run,
    read_visible_browser_status_for_gateway_run,
    sync_visible_browser_capture_for_gateway_run,
)
from app.services.rpa_gateway import CAPTURE_WRITE_SCREEN_ACTION, apply_gateway_decision, create_gateway_request


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Crea/autoriza/lanza flujos visibles de captura editable para cuentas "
            "activas sin ejecutar escrituras externas."
        )
    )
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--actor-user-id", type=int, default=1)
    parser.add_argument("--platform-slug", action="append", default=[])
    parser.add_argument("--create-missing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--authorize", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--launch", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--sync", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--skip-launched", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-launches", type=int, default=0, help="0 significa sin limite.")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "artifacts" / "platform-access-launches")
    args = parser.parse_args()

    args.report_dir.mkdir(parents=True, exist_ok=True)
    platform_slugs = {slug.strip() for slug in args.platform_slug if slug.strip()}
    launched_count = 0
    rows: list[dict[str, Any]] = []

    session_factory = get_session_factory()
    with session_factory() as session:
        manifests = {
            manifest.id: manifest
            for manifest in session.scalars(
                select(PlatformRpaManifest)
                .where(PlatformRpaManifest.tenant_id == args.tenant_id)
                .order_by(PlatformRpaManifest.platform_name)
            )
        }
        accounts = list(
            session.scalars(
                select(PlatformRpaAccountProposal)
                .where(
                    PlatformRpaAccountProposal.tenant_id == args.tenant_id,
                    PlatformRpaAccountProposal.status == ACTIVE_ACCOUNT_STATUS,
                )
                .order_by(PlatformRpaAccountProposal.id)
            )
        )
        for account in accounts:
            manifest = manifests.get(account.manifest_id)
            if manifest is None:
                continue
            if platform_slugs and manifest.platform_slug not in platform_slugs:
                continue
            run = _latest_capture_run(session, tenant_id=args.tenant_id, account_id=account.id)
            row: dict[str, Any] = {
                "account_proposal_id": account.id,
                "platform_slug": manifest.platform_slug,
                "platform_name": manifest.platform_name,
                "external_company_name": account.external_company_name,
                "run_id": run.id if run else None,
                "created": False,
                "authorized": False,
                "launched": False,
                "launch_status": None,
                "browser_state": None,
                "synced": False,
                "sync_status": None,
                "pages_captured": 0,
                "mapping_proposals_created": 0,
                "mapping_proposals_seen": 0,
                "row_level_blocker": None,
                "external_write_executed": False,
            }
            if run is None and args.create_missing:
                run = create_gateway_request(
                    session,
                    tenant_id=args.tenant_id,
                    manifest_id=manifest.id,
                    account_proposal_id=account.id,
                    action_key=CAPTURE_WRITE_SCREEN_ACTION,
                    actor_user_id=args.actor_user_id,
                    request_comment="Captura editable masiva para preparar altas de trabajador.",
                )
                row["created"] = run is not None
                row["run_id"] = run.id if run else None
            if run is None:
                row["launch_status"] = "capture_run_missing"
                rows.append(row)
                continue

            gateway = dict((run.evidence_json or {}).get("gateway") or {})
            if args.authorize and not gateway.get("external_browser_authorized"):
                run = apply_gateway_decision(
                    session,
                    tenant_id=args.tenant_id,
                    run_id=run.id,
                    decision="authorize_enter_page",
                    actor_user_id=args.actor_user_id,
                    notes="Autorizado por orden operativa para mapear altas de trabajador.",
                )
                row["authorized"] = run is not None

            gateway = dict((run.evidence_json or {}).get("gateway") or {}) if run is not None else {}
            already_launched = bool((gateway.get("browser_launch") or {}).get("launched"))
            can_launch_more = args.max_launches <= 0 or launched_count < args.max_launches
            if args.launch and (not already_launched or not args.skip_launched) and can_launch_more:
                launch = launch_visible_browser_for_gateway_run(session, tenant_id=args.tenant_id, run_id=run.id)
                if launch is not None:
                    row["launched"] = bool(launch.get("launched"))
                    row["launch_status"] = launch.get("status")
                    if launch.get("launched"):
                        launched_count += 1
                else:
                    row["launch_status"] = "gateway_request_not_found"
            elif already_launched:
                row["launched"] = True
                row["launch_status"] = "already_launched"
            elif not can_launch_more:
                row["launch_status"] = "launch_limit_reached"

            if args.sync:
                status_payload = read_visible_browser_status_for_gateway_run(
                    session,
                    tenant_id=args.tenant_id,
                    run_id=run.id,
                )
                row["browser_state"] = (status_payload or {}).get("state")
                sync_payload = sync_visible_browser_capture_for_gateway_run(
                    session,
                    tenant_id=args.tenant_id,
                    run_id=run.id,
                )
                row["synced"] = bool((sync_payload or {}).get("synced"))
                row["sync_status"] = (sync_payload or {}).get("status")
                row["pages_captured"] = int((sync_payload or {}).get("pages_captured") or 0)
                row["mapping_proposals_created"] = int(
                    (sync_payload or {}).get("mapping_proposals_created") or 0
                )
                row["mapping_proposals_seen"] = int((sync_payload or {}).get("mapping_proposals_seen") or 0)
                row["row_level_blocker"] = (sync_payload or {}).get("row_level_blocker")
            rows.append(row)

        summary = _summary(rows)
        record_audit(
            session,
            tenant_id=args.tenant_id,
            actor_user_id=args.actor_user_id,
            action="platform_capture_flows.bulk_launch",
            entity_type="tenant",
            entity_id=args.tenant_id,
            after=public_state(
                {
                    "platform_slugs": sorted(platform_slugs),
                    "summary": summary,
                    "external_write_executed": False,
                    "captcha_bypass": False,
                    "mfa_bypass": False,
                }
            ),
        )
        session.commit()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "external_write_executed": False,
            "captcha_bypass": False,
            "mfa_bypass": False,
            "commercial_routes_or_selectors_invented": False,
            "purpose": "editable_capture_mapping_for_worker_registration",
        },
        "summary": _summary(rows),
        "rows": rows,
    }
    stem = f"platform_access_launch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    json_path = args.report_dir / f"{stem}.json"
    markdown_path = args.report_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload["summary"] | {"json": str(json_path), "markdown": str(markdown_path)}, ensure_ascii=False, indent=2))


def _latest_capture_run(session, *, tenant_id: int, account_id: int) -> PlatformReviewRun | None:
    return session.scalars(
        select(PlatformReviewRun)
        .where(
            PlatformReviewRun.tenant_id == tenant_id,
            PlatformReviewRun.account_proposal_id == account_id,
            PlatformReviewRun.operation == CAPTURE_WRITE_SCREEN_ACTION,
        )
        .order_by(PlatformReviewRun.id.desc())
    ).first()


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "targets": len(rows),
        "created": sum(1 for row in rows if row["created"]),
        "authorized": sum(1 for row in rows if row["authorized"]),
        "launched_now": sum(1 for row in rows if row["launch_status"] == "visible_browser_launched"),
        "already_launched": sum(1 for row in rows if row["launch_status"] == "already_launched"),
        "launch_blocked_or_missing": sum(
            1
            for row in rows
            if row["launch_status"]
            not in {
                "visible_browser_launched",
                "already_launched",
            }
        ),
        "synced": sum(1 for row in rows if row["synced"]),
        "captures_not_available": sum(1 for row in rows if row["sync_status"] == "capture_not_available"),
        "mapping_proposals_created": sum(int(row["mapping_proposals_created"] or 0) for row in rows),
        "mapping_proposals_seen": sum(int(row["mapping_proposals_seen"] or 0) for row in rows),
        "external_write_executed": 0,
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Lanzamiento de accesos guiados a plataformas",
        "",
        "Este reporte no ejecuta escrituras externas. Solo abre/sincroniza pasarelas de captura editable para mapear altas de trabajador.",
        "",
        f"- Resumen: `{payload['summary']}`",
        "",
        "| Plataforma | Cuenta/empresa externa | Run | Navegador | Captura | Bloqueo de mapeo |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            "| "
            f"{row['platform_name']} | "
            f"{row['external_company_name']} | "
            f"{row['run_id']} | "
            f"{row['launch_status'] or row['browser_state'] or 'pendiente'} | "
            f"{row['sync_status'] or 'pendiente'} ({row['pages_captured']} pag.) | "
            f"{row['row_level_blocker'] or ''}"
            f" Mapeos: {row['mapping_proposals_created']}/{row['mapping_proposals_seen']} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
