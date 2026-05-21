from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorContext
from app.connectors.rpa.write_registry import (
    get_write_connector,
    list_write_connectors,
    write_connector_key_for_platform_slug,
)
from app.db.models import (
    Company,
    Document,
    DocumentVersion,
    ExternalPlatform,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    Worker,
)
from app.services.platform_edit_methods import EDITABLE_OPERATION_REQUIRED_KEYS
from app.services.platform_write_previews import WritePreviewError, build_write_operation_preview
from app.services.platform_current_accounts_sync import INACTIVE_STATUSES

DEFAULT_WRITE_MATRIX_OPERATIONS = tuple(EDITABLE_OPERATION_REQUIRED_KEYS)
WORKER_OPERATIONS = {"upsert_worker", "deactivate_worker"}
DOCUMENT_OPERATIONS = {
    "upload_worker_document",
    "upload_company_document",
    "upload_machine_vehicle_document",
}
SPECIFIC_LIVE_ADAPTER_CONNECTORS = {"connector_rpa_seisconecta_write"}


async def build_platform_write_probe_matrix(
    session: Session,
    *,
    tenant_id: int,
    company_id: int | None = None,
    worker_id: int | None = None,
    operations: tuple[str, ...] = DEFAULT_WRITE_MATRIX_OPERATIONS,
    connector_dry_run: bool = False,
) -> dict[str, Any]:
    unknown_operations = sorted(set(operations) - set(DEFAULT_WRITE_MATRIX_OPERATIONS))
    if unknown_operations:
        raise ValueError(f"Unsupported operations: {', '.join(unknown_operations)}")

    company = _select_company(session, tenant_id=tenant_id, company_id=company_id)
    worker = _select_worker(
        session,
        tenant_id=tenant_id,
        company_id=company.id if company else None,
        worker_id=worker_id,
    )
    manifests = {
        manifest.id: manifest
        for manifest in session.scalars(
            select(PlatformRpaManifest)
            .where(PlatformRpaManifest.tenant_id == tenant_id)
            .order_by(PlatformRpaManifest.platform_name)
        )
    }
    platforms = {
        platform.id: platform
        for platform in session.scalars(select(ExternalPlatform).order_by(ExternalPlatform.name))
    }
    accounts = list(
        session.scalars(
            select(PlatformRpaAccountProposal)
            .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
            .where(PlatformRpaAccountProposal.status.notin_(INACTIVE_STATUSES))
            .order_by(PlatformRpaAccountProposal.manifest_id, PlatformRpaAccountProposal.external_company_name)
        )
    )

    rows: list[dict[str, Any]] = []
    for account in accounts:
        manifest = manifests.get(account.manifest_id)
        if manifest is None:
            continue
        platform = platforms.get(manifest.external_platform_id or -1)
        if platform is None or platform.platform_key == "mock_cae":
            continue
        for operation in operations:
            row = await _probe_operation(
                session,
                tenant_id=tenant_id,
                company=company,
                worker=worker,
                account=account,
                manifest=manifest,
                platform=platform,
                operation=operation,
                connector_dry_run=connector_dry_run,
            )
            rows.append(row)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "external_write_executed": False,
            "captcha_bypass": False,
            "mfa_bypass": False,
            "connector_dry_run": connector_dry_run,
            "live_submit_requires_preview_manual_approval_and_readback": True,
            "commercial_routes_or_selectors_invented": False,
        },
        "company": {
            "id": company.id if company else None,
            "name": company.name if company else None,
        },
        "worker_candidate": _worker_summary(worker),
        "summary": _summary(rows),
        "rows": rows,
    }


def live_write_adapter_catalog(session: Session, *, tenant_id: int) -> dict[str, Any]:
    connectors = {connector.connector_key: connector for connector in list_write_connectors()}
    manifests = list(
        session.scalars(
            select(PlatformRpaManifest)
            .where(PlatformRpaManifest.tenant_id == tenant_id)
            .order_by(PlatformRpaManifest.platform_name)
        )
    )
    accounts_by_manifest: dict[int, int] = {}
    for account in session.scalars(
        select(PlatformRpaAccountProposal).where(PlatformRpaAccountProposal.tenant_id == tenant_id)
    ):
        accounts_by_manifest[account.manifest_id] = accounts_by_manifest.get(account.manifest_id, 0) + 1

    rows: list[dict[str, Any]] = []
    for manifest in manifests:
        connector_key = write_connector_key_for_platform_slug(manifest.platform_slug)
        connector = connectors.get(connector_key or "")
        connector_profile = getattr(connector, "profile", None)
        live_adapter_status = _live_adapter_status(manifest.platform_slug)
        rows.append(
            {
                "manifest_id": manifest.id,
                "platform_slug": manifest.platform_slug,
                "platform_name": manifest.platform_name,
                "status": manifest.status,
                "account_count": accounts_by_manifest.get(manifest.id, 0),
                "write_connector_key": connector_key,
                "write_connector_registered": connector is not None,
                "supported_operations": list(getattr(connector_profile, "supported_operations", ())),
                "live_adapter_status": live_adapter_status,
                "dry_run_default": manifest.dry_run_default,
                "manual_approval_required": manifest.manual_approval_required,
                "required_before_live_write": _required_before_live_write(live_adapter_status),
            }
        )

    by_status = Counter(str(row["live_adapter_status"]) for row in rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "dry_run_required_by_default": True,
            "manual_approval_required": True,
            "before_after_audit_required": True,
            "post_write_readback_required": True,
            "captcha_bypass": False,
            "mfa_bypass": False,
            "commercial_routes_or_selectors_invented": False,
        },
        "summary": {
            "platforms": len(rows),
            "registered_write_connectors": sum(1 for row in rows if row["write_connector_registered"]),
            "live_adapter_statuses": dict(sorted(by_status.items())),
        },
        "rows": rows,
    }


async def _probe_operation(
    session: Session,
    *,
    tenant_id: int,
    company: Company | None,
    worker: Worker | None,
    account: PlatformRpaAccountProposal,
    manifest: PlatformRpaManifest,
    platform: ExternalPlatform,
    operation: str,
    connector_dry_run: bool,
) -> dict[str, Any]:
    document_version = _document_version_for_operation(session, company=company, worker=worker, operation=operation)
    base = {
        "platform_slug": manifest.platform_slug,
        "platform_key": platform.platform_key,
        "platform_name": manifest.platform_name,
        "account_proposal_id": account.id,
        "external_company_name": account.external_company_name,
        "account_status": account.status,
        "account_source_status": account.account_status,
        "host": account.host,
        "operation": operation,
        "write_connector_key": write_connector_key_for_platform_slug(manifest.platform_slug),
        "live_adapter_status": _live_adapter_status(manifest.platform_slug),
        "external_write_executed": False,
    }

    if operation in WORKER_OPERATIONS and worker is None:
        return base | _skipped("skipped_no_worker", "No worker candidate is available in the Hub.")
    if operation in DOCUMENT_OPERATIONS and document_version is None:
        return base | _skipped("skipped_no_document_version", "No compatible local document version is available.")

    try:
        preview = build_write_operation_preview(
            session,
            tenant_id=tenant_id,
            account_proposal_id=account.id,
            operation=operation,
            company_id=company.id if company else None,
            worker_id=worker.id if worker and operation in {"upsert_worker", "deactivate_worker", "upload_worker_document"} else None,
            document_version_id=document_version.id if document_version else None,
        )
    except WritePreviewError as exc:
        return base | {
            "status": "preview_error",
            "preview_ready": False,
            "mapping_ready": False,
            "local_data_ready": False,
            "account_ready_for_live": False,
            "blocker_count": 1,
            "blocker_kinds": "preview_error:1",
            "blocked_keys": "",
            "planned_change_count": 0,
            "next_action": str(exc),
            "connector_dry_run_status": "",
            "connector_dry_run_message": "",
        }

    row = base | _row_from_preview(preview)
    if connector_dry_run and operation == "upsert_worker" and worker is not None and row["write_connector_key"]:
        connector = get_write_connector(str(row["write_connector_key"]))
        if connector is not None:
            context = ConnectorContext(
                tenant_id=str(tenant_id),
                platform_key=platform.platform_key,
                dry_run=True,
                manual_approval_required=True,
                idempotency_key=f"probe:{tenant_id}:{account.id}:{worker.id}",
            )
            result = await connector.upsert_worker(
                context,
                {
                    "worker_ref": str(worker.id),
                    "prepared_fields": [item["standard_key"] for item in _planned_changes(preview)],
                },
            )
            row["connector_dry_run_status"] = result.status
            row["connector_dry_run_message"] = result.message
            row["external_write_executed"] = bool(result.evidence.get("external_write_executed"))
    return row


def _row_from_preview(preview: dict[str, Any]) -> dict[str, Any]:
    raw_blockers = preview.get("blockers")
    blockers: list[dict[str, Any]] = [
        item for item in raw_blockers if isinstance(item, dict)
    ] if isinstance(raw_blockers, list) else []
    blocker_counter = Counter(str(item.get("kind")) for item in blockers if isinstance(item, dict))
    blocked_keys = sorted(
        {
            str(item.get("standard_key"))
            for item in blockers
            if isinstance(item, dict) and item.get("standard_key")
        }
    )
    raw_readiness = preview.get("readiness")
    readiness: dict[str, Any] = raw_readiness if isinstance(raw_readiness, dict) else {}
    planned_changes = _planned_changes(preview)
    return {
        "status": preview.get("status"),
        "preview_ready": bool(readiness.get("preview_ready")),
        "mapping_ready": bool(readiness.get("mapping_ready")),
        "local_data_ready": bool(readiness.get("local_data_ready")),
        "account_ready_for_live": bool(readiness.get("account_ready_for_live")),
        "blocker_count": len(blockers),
        "blocker_kinds": _counter_text(blocker_counter),
        "blocked_keys": ", ".join(blocked_keys[:12]),
        "planned_change_count": len(planned_changes),
        "next_action": preview.get("next_action"),
        "connector_dry_run_status": "",
        "connector_dry_run_message": "",
    }


def _planned_changes(preview: dict[str, Any]) -> list[dict[str, Any]]:
    raw_changes = preview.get("planned_external_changes")
    if not isinstance(raw_changes, list):
        return []
    return [item for item in raw_changes if isinstance(item, dict)]


def _document_version_for_operation(
    session: Session,
    *,
    company: Company | None,
    worker: Worker | None,
    operation: str,
) -> DocumentVersion | None:
    if operation == "upload_worker_document":
        if worker is None:
            return None
        document = _latest_document(session, entity_type="worker", entity_id=worker.id)
    elif operation == "upload_company_document":
        if company is None:
            return None
        document = _latest_document(session, entity_type="company", entity_id=company.id)
    elif operation == "upload_machine_vehicle_document":
        document = session.scalars(
            select(Document)
            .where(Document.entity_type.in_(("asset", "machine", "vehicle")))
            .order_by(Document.id.desc())
        ).first()
    else:
        return None
    if document is None:
        return None
    if document.current_version_id:
        version = session.get(DocumentVersion, document.current_version_id)
        if version is not None:
            return version
    return session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc(), DocumentVersion.id.desc())
    ).first()


def _latest_document(session: Session, *, entity_type: str, entity_id: int) -> Document | None:
    return session.scalars(
        select(Document)
        .where(Document.entity_type == entity_type, Document.entity_id == entity_id)
        .order_by(Document.id.desc())
    ).first()


def _select_company(session: Session, *, tenant_id: int, company_id: int | None) -> Company | None:
    statement = select(Company).where(Company.tenant_id == tenant_id)
    if company_id is not None:
        statement = statement.where(Company.id == company_id)
    return session.scalars(statement.order_by(Company.id)).first()


def _select_worker(
    session: Session,
    *,
    tenant_id: int,
    company_id: int | None,
    worker_id: int | None,
) -> Worker | None:
    statement = select(Worker).where(Worker.tenant_id == tenant_id)
    if worker_id is not None:
        statement = statement.where(Worker.id == worker_id)
    elif company_id is not None:
        statement = statement.where(Worker.company_id == company_id)
    workers = list(session.scalars(statement.order_by(Worker.id)))
    if not workers:
        return None
    return max(workers, key=_worker_score)


def _worker_score(worker: Worker) -> int:
    fields = (
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
    return sum(1 for value in fields if value is not None and str(value).strip())


def _worker_summary(worker: Worker | None) -> dict[str, Any]:
    if worker is None:
        return {"id": None, "label": None, "identifier_last4": None}
    return {
        "id": worker.id,
        "label": f"{worker.first_name} {worker.last_name}",
        "identifier_last4": worker.identifier_last4,
        "completeness_score": _worker_score(worker),
    }


def _skipped(status: str, detail: str) -> dict[str, Any]:
    return {
        "status": status,
        "preview_ready": False,
        "mapping_ready": False,
        "local_data_ready": False,
        "account_ready_for_live": False,
        "blocker_count": 0,
        "blocker_kinds": "",
        "blocked_keys": "",
        "planned_change_count": 0,
        "next_action": detail,
        "connector_dry_run_status": "",
        "connector_dry_run_message": "",
    }


def _live_adapter_status(platform_slug: str) -> str:
    connector_key = write_connector_key_for_platform_slug(platform_slug)
    if connector_key is None:
        return "no_write_connector"
    if connector_key in SPECIFIC_LIVE_ADAPTER_CONNECTORS:
        return "specific_live_adapter_available"
    return "blocked_live_adapter_missing"


def _required_before_live_write(live_adapter_status: str) -> list[str]:
    requirements = [
        "platform_company_context_selected",
        "field_mapping_approved",
        "editable_screen_capture_approved",
        "preview_generated",
        "human_approval_recorded",
        "before_after_audit_enabled",
        "post_write_readback_confirmation",
    ]
    if live_adapter_status == "blocked_live_adapter_missing":
        return ["platform_specific_live_adapter", "pre_write_duplicate_readback", *requirements]
    if live_adapter_status == "specific_live_adapter_available":
        return ["pre_write_duplicate_readback", *requirements]
    return ["registered_write_connector", *requirements]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_status = Counter(str(row["status"]) for row in rows)
    by_operation = Counter(str(row["operation"]) for row in rows)
    dry_run = Counter(str(row.get("connector_dry_run_status") or "") for row in rows)
    dry_run.pop("", None)
    live_adapters = Counter(str(row.get("live_adapter_status") or "") for row in rows)
    live_adapters.pop("", None)
    return {
        "contexts": len({(row["platform_slug"], row["account_proposal_id"]) for row in rows}),
        "rows": len(rows),
        "platforms": len({row["platform_slug"] for row in rows}),
        "operations": dict(sorted(by_operation.items())),
        "statuses": dict(sorted(by_status.items())),
        "preview_ready_rows": sum(1 for row in rows if row["preview_ready"]),
        "mapping_ready_rows": sum(1 for row in rows if row["mapping_ready"]),
        "local_data_ready_rows": sum(1 for row in rows if row["local_data_ready"]),
        "account_ready_for_live_rows": sum(1 for row in rows if row["account_ready_for_live"]),
        "external_writes_executed": sum(1 for row in rows if row["external_write_executed"]),
        "live_adapter_statuses": dict(sorted(live_adapters.items())),
        "connector_dry_run_statuses": dict(sorted(dry_run.items())),
    }


def _counter_text(counter: Counter[str]) -> str:
    return ", ".join(f"{key}:{count}" for key, count in sorted(counter.items()) if key and key != "None")
