from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    PlatformObservedDocumentRequest,
    PlatformObservedEntity,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformWritePath,
)
from app.services.platform_current_accounts_sync import account_is_inactive
from app.services.platform_data_coverage import build_platform_data_coverage
from app.services.platform_edit_methods import build_platform_edit_methods
from app.services.platform_validation_surfaces import build_validation_surface_map
from app.services.platform_write_probe_matrix import live_write_adapter_catalog

CORE_WRITE_OPERATIONS = ("upsert_worker", "upload_worker_document", "upload_company_document")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ACTIONABLE_EXTERNAL_STATUSES = {
    "manual_required",
    "rejected",
    "expired_external",
    "blocked_by_platform",
    "pending_external_validation",
    "unknown",
}


def build_platform_reconciliation_map(
    session: Session,
    *,
    tenant_id: int,
    company_id: int | None = None,
    priority_group: str = "all",
) -> dict[str, Any]:
    coverage = build_platform_data_coverage(
        session,
        tenant_id=tenant_id,
        company_id=company_id,
        priority_group=priority_group,
    )
    edit_methods = build_platform_edit_methods(
        session,
        tenant_id=tenant_id,
        company_id=company_id,
        priority_group=priority_group,
    )
    surfaces = build_validation_surface_map(
        capture_root=PROJECT_ROOT / "artifacts" / "platform-captures",
        current_only=True,
    )
    live_adapters = live_write_adapter_catalog(session, tenant_id=tenant_id)

    manifests = _manifests(session, tenant_id=tenant_id, priority_group=priority_group)
    accounts_by_manifest = _accounts_by_manifest(session, tenant_id=tenant_id)
    schedules_by_manifest = _schedules_by_manifest(session, tenant_id=tenant_id)
    coverage_by_context = {
        _context_key(item.get("manifest_id"), item.get("account_proposal_id")): item
        for item in coverage.get("contexts", [])
        if isinstance(item, dict)
    }
    edit_by_context = {
        _context_key(item.get("manifest_id"), item.get("account_proposal_id")): item
        for item in edit_methods.get("contexts", [])
        if isinstance(item, dict)
    }
    surface_by_slug = {
        str(item.get("platform_slug")): item
        for item in surfaces.get("platforms", [])
        if isinstance(item, dict)
    }
    live_by_manifest = {
        int(item["manifest_id"]): item
        for item in live_adapters.get("rows", [])
        if isinstance(item, dict) and isinstance(item.get("manifest_id"), int)
    }
    observed_entities = _observed_entities_by_context(session, tenant_id=tenant_id)
    observed_requests = _observed_document_requests_by_context(session, tenant_id=tenant_id)
    write_paths = _write_paths_by_context(session, tenant_id=tenant_id)

    rows: list[dict[str, Any]] = []
    for manifest in manifests:
        accounts: list[PlatformRpaAccountProposal | None] = list(accounts_by_manifest.get(manifest.id, []))
        if not accounts:
            accounts = [None]
        for account in accounts:
            key = _context_key(manifest.id, account.id if account else None)
            schedule = schedules_by_manifest.get(manifest.id)
            coverage_context = coverage_by_context.get(key)
            edit_context = edit_by_context.get(key)
            surface_context = surface_by_slug.get(manifest.platform_slug)
            adapter = live_by_manifest.get(manifest.id)
            entity_stats = observed_entities.get(key, _empty_observed_entities())
            request_stats = observed_requests.get(key, _empty_observed_requests())
            path_stats = write_paths.get(key, _empty_write_paths())
            row = _build_row(
                manifest=manifest,
                account=account,
                schedule=schedule,
                coverage_context=coverage_context,
                edit_context=edit_context,
                surface_context=surface_context,
                adapter=adapter,
                entity_stats=entity_stats,
                request_stats=request_stats,
                path_stats=path_stats,
            )
            rows.append(row)

    summary = _summary(rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "target": "map_all_active_platforms_for_read_and_write",
            "platform_unit": "platform + external company/account + work center/context",
            "external_write_executed": False,
            "requires_read_before_write": True,
            "requires_post_write_readback": True,
            "commercial_routes_or_selectors_invented": False,
        },
        "summary": summary,
        "rows": sorted(rows, key=lambda item: (item["platform_name"], item["external_company_name"] or "")),
    }


def _build_row(
    *,
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
    schedule: PlatformReviewSchedule | None,
    coverage_context: dict[str, Any] | None,
    edit_context: dict[str, Any] | None,
    surface_context: dict[str, Any] | None,
    adapter: dict[str, Any] | None,
    entity_stats: dict[str, Any],
    request_stats: dict[str, Any],
    path_stats: dict[str, Any],
) -> dict[str, Any]:
    active = bool(schedule and schedule.enabled and account is not None and not account_is_inactive(account.status))
    entry_ready = bool(
        (coverage_context or {}).get("entry_url_configured")
        or (account.entry_url if account else None)
        or manifest.entry_urls
    )
    surface_count = _surface_count(surface_context)
    operations = _operation_statuses(edit_context)
    ready_operations = [operation for operation, status in operations.items() if status == "ready_for_preview"]
    missing_core_operations = [operation for operation in CORE_WRITE_OPERATIONS if operations.get(operation) != "ready_for_preview"]
    live_adapter_status = str((adapter or {}).get("live_adapter_status") or "no_write_connector")
    helper_status = str((adapter or {}).get("helper_status") or "missing")
    read_status = _read_status(
        entry_ready=entry_ready,
        schedule=schedule,
        surface_count=surface_count,
        entity_stats=entity_stats,
        request_stats=request_stats,
    )
    write_status = _write_status(
        live_adapter_status=live_adapter_status,
        missing_core_operations=missing_core_operations,
        path_stats=path_stats,
    )
    blockers = _blockers(
        active=active,
        entry_ready=entry_ready,
        read_status=read_status,
        write_status=write_status,
        live_adapter_status=live_adapter_status,
        missing_core_operations=missing_core_operations,
        path_stats=path_stats,
        request_stats=request_stats,
    )
    mapping_status = "complete" if active and read_status == "ready" and write_status == "ready" and not blockers else "partial"
    if not active or not entry_ready or live_adapter_status in {"no_write_connector", "blocked_live_adapter_missing"}:
        mapping_status = "blocked"
    return {
        "manifest_id": manifest.id,
        "platform_slug": manifest.platform_slug,
        "platform_name": manifest.platform_name,
        "account_proposal_id": account.id if account else None,
        "platform_account_id": account.platform_account_id if account else None,
        "external_company_name": (coverage_context or {}).get("external_company_name")
        or (account.external_company_name if account else None),
        "trace_label": (coverage_context or {}).get("trace_label") or _trace_label(manifest, account),
        "host": (coverage_context or {}).get("host") or (account.host if account else None) or (manifest.hosts[0] if manifest.hosts else None),
        "active": active,
        "entry_ready": entry_ready,
        "last_read_status": schedule.last_result_status if schedule else None,
        "last_read_summary": schedule.last_result_summary if schedule else None,
        "next_run_at": schedule.next_run_at if schedule else None,
        "read_status": read_status,
        "write_status": write_status,
        "mapping_status": mapping_status,
        "surface_count": surface_count,
        "observed_entities": entity_stats,
        "observed_document_requests": request_stats,
        "write_paths": path_stats,
        "operations": operations,
        "ready_operations": ready_operations,
        "missing_core_operations": missing_core_operations,
        "live_adapter_status": live_adapter_status,
        "helper_status": helper_status,
        "next_action": _next_action(
            active=active,
            read_status=read_status,
            write_status=write_status,
            blockers=blockers,
            request_stats=request_stats,
        ),
        "blockers": blockers,
        "fully_mapped_for_read_write": mapping_status == "complete",
    }


def _read_status(
    *,
    entry_ready: bool,
    schedule: PlatformReviewSchedule | None,
    surface_count: int,
    entity_stats: dict[str, Any],
    request_stats: dict[str, Any],
) -> str:
    if not entry_ready:
        return "blocked_missing_entry_url"
    if surface_count == 0:
        return "needs_read_surface_mapping"
    if entity_stats["total"] == 0 and request_stats["total"] == 0 and not (schedule and schedule.last_result_status):
        return "needs_first_read"
    return "ready"


def _write_status(
    *,
    live_adapter_status: str,
    missing_core_operations: list[str],
    path_stats: dict[str, Any],
) -> str:
    if live_adapter_status == "no_write_connector":
        return "blocked_no_write_connector"
    if live_adapter_status == "blocked_live_adapter_missing":
        return "blocked_live_adapter_missing"
    if missing_core_operations:
        return "needs_mapping"
    if path_stats["approved"] == 0:
        return "needs_approved_write_paths"
    return "ready"


def _blockers(
    *,
    active: bool,
    entry_ready: bool,
    read_status: str,
    write_status: str,
    live_adapter_status: str,
    missing_core_operations: list[str],
    path_stats: dict[str, Any],
    request_stats: dict[str, Any],
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if not active:
        blockers.append({"kind": "inactive_context", "detail": "El contexto no se revisa ni genera avisos."})
    if not entry_ready:
        blockers.append({"kind": "missing_entry_url", "detail": "Falta URL/host de entrada autorizado."})
    if read_status != "ready":
        blockers.append({"kind": read_status, "detail": _read_blocker_detail(read_status)})
    if live_adapter_status != "specific_live_adapter_available":
        blockers.append({"kind": live_adapter_status, "detail": "Falta helper live especifico o conector de escritura."})
    if missing_core_operations:
        blockers.append(
            {
                "kind": "missing_core_operation_mapping",
                "detail": ", ".join(missing_core_operations),
            }
        )
    if path_stats["pending"] > 0:
        blockers.append({"kind": "pending_write_path_review", "detail": f"{path_stats['pending']} path(s) pendientes de revision."})
    if write_status not in {"ready", "blocked_no_write_connector", "blocked_live_adapter_missing", "needs_mapping"}:
        blockers.append({"kind": write_status, "detail": "Falta completar evidencia de escritura."})
    if request_stats["actionable"] > 0 and request_stats["with_hub_document"] == 0:
        blockers.append({"kind": "external_requests_without_hub_document", "detail": "Hay peticiones externas sin documento equivalente disponible en Hub."})
    return blockers


def _next_action(
    *,
    active: bool,
    read_status: str,
    write_status: str,
    blockers: list[dict[str, str]],
    request_stats: dict[str, Any],
) -> str:
    if not active:
        return "Activar el contexto si vuelve a tener trabajos."
    if read_status != "ready":
        return _read_blocker_detail(read_status)
    if request_stats["actionable"] > 0:
        return "Resolver peticiones externas normalizadas desde Notificaciones."
    if write_status == "ready":
        return "Contexto listo para preparar previews y ejecutar con lectura posterior."
    if write_status == "blocked_live_adapter_missing":
        return "Completar helper live especifico y lectura posterior para esta plataforma."
    if write_status == "blocked_no_write_connector":
        return "Registrar conector de escritura protegido para la plataforma."
    if write_status == "needs_mapping":
        return "Completar mapeos de lectura/escritura y paths aprobados para operaciones core."
    return blockers[0]["detail"] if blockers else "Revisar contexto."


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    active_rows = [row for row in rows if row["active"]]
    blocker_counter: Counter[str] = Counter()
    for row in rows:
        blocker_counter.update(blocker["kind"] for blocker in row["blockers"])
    return {
        "contexts": len(rows),
        "active_contexts": len(active_rows),
        "inactive_contexts": len(rows) - len(active_rows),
        "read_ready": sum(1 for row in active_rows if row["read_status"] == "ready"),
        "write_ready": sum(1 for row in active_rows if row["write_status"] == "ready"),
        "fully_mapped_for_read_write": sum(1 for row in active_rows if row["fully_mapped_for_read_write"]),
        "with_live_helper": sum(1 for row in active_rows if row["live_adapter_status"] == "specific_live_adapter_available"),
        "observed_entities": sum(row["observed_entities"]["total"] for row in rows),
        "observed_document_requests": sum(row["observed_document_requests"]["total"] for row in rows),
        "actionable_document_requests": sum(row["observed_document_requests"]["actionable"] for row in rows),
        "blockers": dict(sorted(blocker_counter.items())),
    }


def _observed_entities_by_context(session: Session, *, tenant_id: int) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = defaultdict(_empty_observed_entities)
    for row in session.scalars(select(PlatformObservedEntity).where(PlatformObservedEntity.tenant_id == tenant_id)):
        key = _context_key(row.manifest_id, row.account_proposal_id)
        current = result[key]
        current["total"] += 1
        current["workers"] += 1 if row.entity_type == "worker" else 0
        current["companies"] += 1 if row.entity_type == "company" else 0
        if row.local_worker_id or row.local_company_id:
            current["matched"] += 1
        current["last_seen_at"] = _max_iso(current["last_seen_at"], row.last_seen_at)
    return dict(result)


def _observed_document_requests_by_context(session: Session, *, tenant_id: int) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = defaultdict(_empty_observed_requests)
    for row in session.scalars(
        select(PlatformObservedDocumentRequest).where(PlatformObservedDocumentRequest.tenant_id == tenant_id)
    ):
        key = _context_key(row.manifest_id, row.account_proposal_id)
        current = result[key]
        current["total"] += 1
        if row.external_status in ACTIONABLE_EXTERNAL_STATUSES or row.severity in {"red", "orange"}:
            current["actionable"] += 1
        if row.matched_document_version_id:
            current["with_hub_document"] += 1
        if row.document_type_id:
            current["mapped_document_type"] += 1
        current["by_status"][row.external_status] = current["by_status"].get(row.external_status, 0) + 1
        current["last_seen_at"] = _max_iso(current["last_seen_at"], row.last_seen_at)
    return dict(result)


def _write_paths_by_context(session: Session, *, tenant_id: int) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = defaultdict(_empty_write_paths)
    for row in session.scalars(select(PlatformWritePath).where(PlatformWritePath.tenant_id == tenant_id)):
        key = _context_key(row.manifest_id, row.account_proposal_id)
        current = result[key]
        current["total"] += 1
        if row.review_status == "approved":
            current["approved"] += 1
        elif row.review_status == "pending_review":
            current["pending"] += 1
        elif row.review_status == "rejected":
            current["rejected"] += 1
        current["operations"][row.operation] = current["operations"].get(row.operation, 0) + 1
    return dict(result)


def _operation_statuses(edit_context: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for operation in (edit_context or {}).get("operations", []):
        if not isinstance(operation, dict):
            continue
        operation_key = operation.get("operation")
        status = operation.get("status")
        if isinstance(operation_key, str) and isinstance(status, str):
            result[operation_key] = status
    return result


def _surface_count(surface_context: dict[str, Any] | None) -> int:
    summary = (surface_context or {}).get("summary")
    if not isinstance(summary, dict):
        return 0
    return sum(int(value) for value in summary.values() if isinstance(value, int))


def _manifests(session: Session, *, tenant_id: int, priority_group: str) -> list[PlatformRpaManifest]:
    statement = select(PlatformRpaManifest).where(PlatformRpaManifest.tenant_id == tenant_id)
    if priority_group and priority_group != "all":
        statement = statement.where(PlatformRpaManifest.priority_group == priority_group)
    return list(session.scalars(statement.order_by(PlatformRpaManifest.platform_name)))


def _accounts_by_manifest(session: Session, *, tenant_id: int) -> dict[int, list[PlatformRpaAccountProposal]]:
    result: dict[int, list[PlatformRpaAccountProposal]] = defaultdict(list)
    for account in session.scalars(
        select(PlatformRpaAccountProposal)
        .where(PlatformRpaAccountProposal.tenant_id == tenant_id)
        .order_by(PlatformRpaAccountProposal.manifest_id, PlatformRpaAccountProposal.external_company_name)
    ):
        result[account.manifest_id].append(account)
    return dict(result)


def _schedules_by_manifest(session: Session, *, tenant_id: int) -> dict[int, PlatformReviewSchedule]:
    return {
        schedule.manifest_id: schedule
        for schedule in session.scalars(select(PlatformReviewSchedule).where(PlatformReviewSchedule.tenant_id == tenant_id))
    }


def _empty_observed_entities() -> dict[str, Any]:
    return {"total": 0, "workers": 0, "companies": 0, "matched": 0, "last_seen_at": None}


def _empty_observed_requests() -> dict[str, Any]:
    return {
        "total": 0,
        "actionable": 0,
        "with_hub_document": 0,
        "mapped_document_type": 0,
        "by_status": {},
        "last_seen_at": None,
    }


def _empty_write_paths() -> dict[str, Any]:
    return {"total": 0, "approved": 0, "pending": 0, "rejected": 0, "operations": {}}


def _context_key(manifest_id: Any, account_proposal_id: Any) -> str:
    return f"{manifest_id}:{account_proposal_id if account_proposal_id is not None else 'none'}"


def _trace_label(manifest: PlatformRpaManifest, account: PlatformRpaAccountProposal | None) -> str:
    if account is None:
        return manifest.platform_name
    return f"{manifest.platform_name} / {account.external_company_name or account.source_platform_account_id}"


def _read_blocker_detail(status: str) -> str:
    details = {
        "blocked_missing_entry_url": "Configurar URL/host autorizado antes de leer.",
        "needs_read_surface_mapping": "Lanzar captura de solo lectura y mapear superficies.",
        "needs_first_read": "Ejecutar primera lectura del contexto activo.",
    }
    return details.get(status, "Completar lectura externa.")


def _max_iso(current: str | None, value: datetime | None) -> str | None:
    if value is None:
        return current
    candidate = value.isoformat()
    if current is None:
        return candidate
    return max(current, candidate)
