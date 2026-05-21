from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    PlatformDiscoveredLabel,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformRpaMappingProposal,
    PlatformStructureSnapshot,
)
from app.services.platform_data_coverage import CANONICAL_KEY_ALIASES
from app.services.platform_mapping import STANDARD_LABELS, STANDARD_LABELS_BY_KEY, StandardLabel


EDITABLE_OPERATION_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "sync_company_profile": (
        "company.name",
        "company.tax_id",
        "company.address",
        "company.contact_email",
        "company.phone",
        "company.activity_cnae",
    ),
    "upsert_worker": (
        "worker.first_name",
        "worker.last_name",
        "worker.identifier_value",
        "worker.social_security_number",
        "worker.email",
        "worker.phone",
        "worker.work_position",
        "worker.starts_at",
        "worker.ends_at",
        "worker.medical_fitness_status",
        "worker.medical_fitness_expires_at",
    ),
    "deactivate_worker": (
        "worker.identifier_value",
        "worker.ends_at",
    ),
    "upload_worker_document": (
        "worker.identifier_value",
        "document.type",
        "document.file",
        "document.issued_at",
        "document.expires_at",
    ),
    "upload_company_document": (
        "company.tax_id",
        "document.type",
        "document.file",
        "document.issued_at",
        "document.expires_at",
    ),
    "upload_machine_vehicle_document": (
        "asset.type",
        "asset.identifier",
        "machine.code",
        "machine.serial",
        "vehicle.plate",
        "document.type",
        "document.file",
        "document.issued_at",
        "document.expires_at",
    ),
    "sync_assignment": (
        "work_center.name",
        "project.name",
        "coordination.name",
        "period.start_date",
        "period.end_date",
    ),
}

PLATFORM_OPERATION_REQUIRED_KEYS: dict[tuple[str, str], tuple[str, ...]] = {
    (
        "seisconecta",
        "upsert_worker",
    ): (
        "worker.identifier_value",
        "worker.first_name",
        "worker.last_name",
        "worker.nationality",
        "worker.contract_type",
        "worker.work_position",
    ),
}

READBACK_ONLY_KEYS = {
    "document.status",
    "document.rejection_reason",
    "document.incident_flag",
    "document.requested_at",
    "document.received_at",
    "document.validated_at",
    "document.external_id",
    "attendance.checks",
}

SENSITIVE_KEYS = {
    "platform.login.username",
    "platform.login.password",
    "worker.identifier_value",
    "worker.social_security_number",
    "worker.medical_fitness_status",
    "worker.medical_fitness_expires_at",
    "document.file",
}

EDITABLE_LABEL_KINDS = {"form_field"}


def build_platform_edit_methods(
    session: Session,
    *,
    tenant_id: int,
    company_id: int | None = None,
    priority_group: str = "all",
) -> dict[str, Any]:
    company = _company(session, tenant_id=tenant_id, company_id=company_id)
    manifests = _manifests(session, tenant_id=tenant_id, priority_group=priority_group)
    manifest_ids = [manifest.id for manifest in manifests]
    accounts_by_manifest = _accounts_by_manifest(session, tenant_id=tenant_id, manifest_ids=manifest_ids)
    snapshots = _snapshots_by_id(session, tenant_id=tenant_id)
    labels_by_platform = _labels_by_platform(session, tenant_id=tenant_id)
    labels_by_account = _labels_by_account(session, tenant_id=tenant_id)
    mappings_by_manifest = _mappings_by_manifest(
        session,
        tenant_id=tenant_id,
        manifest_ids=manifest_ids,
    )

    contexts: list[dict[str, Any]] = []
    totals = {
        "platforms": len(manifests),
        "contexts": 0,
        "field_methods": 0,
        "ready_for_preview": 0,
        "needs_editable_capture": 0,
        "needs_mapping_review": 0,
        "needs_mapping": 0,
        "not_external_edit_target": 0,
        "credential_secret_only": 0,
        "operations": 0,
        "operations_ready_for_preview": 0,
    }

    for manifest in manifests:
        accounts: list[PlatformRpaAccountProposal | None] = [*accounts_by_manifest.get(manifest.id, [])]
        if not accounts:
            accounts.append(None)
        for account in accounts:
            labels_by_key = _context_labels_by_key(
                manifest=manifest,
                account=account,
                labels_by_platform=labels_by_platform,
                labels_by_account=labels_by_account,
            )
            mappings_by_key = mappings_by_manifest.get(manifest.id, {})
            field_methods = [
                _field_method(
                    standard,
                    labels=labels_by_key.get(standard.key, []),
                    mappings=mappings_by_key.get(standard.key, []),
                    snapshots=snapshots,
                    manifest=manifest,
                    account=account,
                )
                for standard in STANDARD_LABELS
            ]
            operations = _operation_methods(manifest=manifest, field_methods=field_methods)
            context = {
                "manifest_id": manifest.id,
                "platform_slug": manifest.platform_slug,
                "platform_name": manifest.platform_name,
                "external_platform_id": manifest.external_platform_id,
                "account_proposal_id": account.id if account else None,
                "platform_account_id": account.platform_account_id if account else None,
                "external_company_name": account.external_company_name if account else None,
                "trace_label": _trace_label(manifest, account, company),
                "host": account.host if account and account.host else (manifest.hosts[0] if manifest.hosts else None),
                "entry_url_configured": bool(account.entry_url if account else manifest.entry_urls),
                "dry_run": bool(account.dry_run if account else manifest.dry_run_default),
                "manual_approval_required": bool(
                    account.manual_approval_required if account else manifest.manual_approval_required
                ),
                "rpa_assisted_on_control": bool(manifest.rpa_assisted_on_control),
                "field_methods": field_methods,
                "operations": operations,
                "source_summary": {
                    "observed_standard_keys": sorted(labels_by_key),
                    "mapped_standard_keys": sorted(mappings_by_key),
                    "manifest_allowed_operations": list(manifest.allowed_operations or []),
                },
            }
            contexts.append(context)
            totals["contexts"] += 1
            totals["field_methods"] += len(field_methods)
            for method in field_methods:
                status_key = method["status"]
                if status_key in totals:
                    totals[status_key] += 1
            totals["operations"] += len(operations)
            totals["operations_ready_for_preview"] += sum(
                1 for operation in operations if operation["status"] == "ready_for_preview"
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "external_writes_require_preview": True,
            "external_writes_require_before_after_audit": True,
            "captcha_bypass": False,
            "stores_credentials_or_tokens": False,
            "stores_static_commercial_selectors": False,
            "selector_strategy": "resolve_by_observed_label_or_stable_name_at_runtime",
        },
        "company": {
            "id": company.id if company else None,
            "name": company.name if company else "ARM",
        },
        "totals": totals,
        "contexts": contexts,
    }


def _company(session: Session, *, tenant_id: int, company_id: int | None) -> Company | None:
    statement = select(Company).where(Company.tenant_id == tenant_id)
    if company_id is not None:
        statement = statement.where(Company.id == company_id)
    return session.scalars(statement.order_by(Company.id)).first()


def _manifests(session: Session, *, tenant_id: int, priority_group: str) -> list[PlatformRpaManifest]:
    statement = select(PlatformRpaManifest).where(PlatformRpaManifest.tenant_id == tenant_id)
    if priority_group and priority_group != "all":
        statement = statement.where(PlatformRpaManifest.priority_group == priority_group)
    return list(session.scalars(statement.order_by(PlatformRpaManifest.platform_name)))


def _accounts_by_manifest(
    session: Session,
    *,
    tenant_id: int,
    manifest_ids: list[int],
) -> dict[int, list[PlatformRpaAccountProposal]]:
    if not manifest_ids:
        return {}
    rows = session.scalars(
        select(PlatformRpaAccountProposal)
        .where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.manifest_id.in_(manifest_ids),
        )
        .order_by(PlatformRpaAccountProposal.manifest_id, PlatformRpaAccountProposal.external_company_name)
    )
    result: dict[int, list[PlatformRpaAccountProposal]] = defaultdict(list)
    for row in rows:
        result[row.manifest_id].append(row)
    return result


def _snapshots_by_id(session: Session, *, tenant_id: int) -> dict[int, PlatformStructureSnapshot]:
    rows = session.scalars(
        select(PlatformStructureSnapshot).where(PlatformStructureSnapshot.tenant_id == tenant_id)
    )
    return {row.id: row for row in rows}


def _labels_by_platform(
    session: Session,
    *,
    tenant_id: int,
) -> dict[int, list[PlatformDiscoveredLabel]]:
    rows = session.scalars(
        select(PlatformDiscoveredLabel).where(
            PlatformDiscoveredLabel.tenant_id == tenant_id,
            PlatformDiscoveredLabel.external_platform_id.is_not(None),
            PlatformDiscoveredLabel.standard_key.is_not(None),
        )
    )
    result: dict[int, list[PlatformDiscoveredLabel]] = defaultdict(list)
    for row in rows:
        if row.external_platform_id is not None:
            result[row.external_platform_id].append(row)
    return result


def _labels_by_account(
    session: Session,
    *,
    tenant_id: int,
) -> dict[int, list[PlatformDiscoveredLabel]]:
    rows = session.scalars(
        select(PlatformDiscoveredLabel).where(
            PlatformDiscoveredLabel.tenant_id == tenant_id,
            PlatformDiscoveredLabel.platform_account_id.is_not(None),
            PlatformDiscoveredLabel.standard_key.is_not(None),
        )
    )
    result: dict[int, list[PlatformDiscoveredLabel]] = defaultdict(list)
    for row in rows:
        if row.platform_account_id is not None:
            result[row.platform_account_id].append(row)
    return result


def _mappings_by_manifest(
    session: Session,
    *,
    tenant_id: int,
    manifest_ids: list[int],
) -> dict[int, dict[str, list[PlatformRpaMappingProposal]]]:
    result: dict[int, dict[str, list[PlatformRpaMappingProposal]]] = defaultdict(lambda: defaultdict(list))
    if not manifest_ids:
        return result
    rows = session.scalars(
        select(PlatformRpaMappingProposal).where(
            PlatformRpaMappingProposal.tenant_id == tenant_id,
            PlatformRpaMappingProposal.manifest_id.in_(manifest_ids),
        )
    )
    for row in rows:
        key = _canonical_key(row.iker_key, row.mapping_kind)
        if key:
            result[row.manifest_id][key].append(row)
    return result


def _context_labels_by_key(
    *,
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
    labels_by_platform: dict[int, list[PlatformDiscoveredLabel]],
    labels_by_account: dict[int, list[PlatformDiscoveredLabel]],
) -> dict[str, list[PlatformDiscoveredLabel]]:
    rows: list[PlatformDiscoveredLabel] = []
    if manifest.external_platform_id is not None:
        rows.extend(labels_by_platform.get(manifest.external_platform_id, []))
    if account and account.platform_account_id is not None:
        rows.extend(labels_by_account.get(account.platform_account_id, []))

    seen: set[int] = set()
    result: dict[str, list[PlatformDiscoveredLabel]] = defaultdict(list)
    for row in rows:
        if row.id in seen or row.standard_key is None:
            continue
        seen.add(row.id)
        result[row.standard_key].append(row)
    return result


def _field_method(
    standard: StandardLabel,
    *,
    labels: list[PlatformDiscoveredLabel],
    mappings: list[PlatformRpaMappingProposal],
    snapshots: dict[int, PlatformStructureSnapshot],
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
) -> dict[str, Any]:
    editable_labels = [label for label in labels if label.label_kind in EDITABLE_LABEL_KINDS]
    mapping_statuses = sorted({mapping.review_status for mapping in mappings})
    status = _field_status(standard=standard, editable_labels=editable_labels, labels=labels, mappings=mappings)
    method = _method_name(standard=standard, has_editable_evidence=bool(editable_labels), status=status)
    return {
        "standard_key": standard.key,
        "display_name": standard.display_name,
        "entity_scope": standard.entity_scope,
        "category": standard.category,
        "data_type": standard.data_type,
        "status": status,
        "method": method,
        "selector_policy": _selector_policy(status),
        "requires_preview": _requires_preview(status),
        "requires_manual_approval": _requires_manual_approval(
            standard=standard,
            manifest=manifest,
            account=account,
        ),
        "requires_before_after_audit": status in {"ready_for_preview", "credential_secret_only"},
        "sensitive": standard.key in SENSITIVE_KEYS,
        "observed_labels": [_label_evidence(label, snapshots) for label in labels[:8]],
        "mapping_candidates": [_mapping_evidence(mapping) for mapping in mappings[:8]],
        "evidence_summary": {
            "observed_label_count": len(labels),
            "editable_label_count": len(editable_labels),
            "mapping_count": len(mappings),
            "mapping_review_statuses": mapping_statuses,
        },
        "next_action": _field_next_action(status),
    }


def _field_status(
    *,
    standard: StandardLabel,
    editable_labels: list[PlatformDiscoveredLabel],
    labels: list[PlatformDiscoveredLabel],
    mappings: list[PlatformRpaMappingProposal],
) -> str:
    if standard.key == "platform.login.password":
        return "credential_secret_only"
    if standard.key in READBACK_ONLY_KEYS:
        return "not_external_edit_target"
    if editable_labels:
        return "ready_for_preview"
    if any(mapping.review_status == "approved" for mapping in mappings):
        return "needs_editable_capture"
    if labels or mappings:
        return "needs_mapping_review"
    return "needs_mapping"


def _method_name(*, standard: StandardLabel, has_editable_evidence: bool, status: str) -> str:
    if status == "credential_secret_only":
        return "inject_from_configured_secret_store_at_login"
    if status == "not_external_edit_target":
        return "readback_only_no_edit_method"
    if not has_editable_evidence:
        return "capture_edit_screen_before_method_binding"
    if standard.data_type == "file":
        return "upload_file_by_observed_file_input"
    if standard.data_type == "date":
        return "fill_date_by_observed_label_or_name"
    if standard.data_type == "boolean":
        return "toggle_or_select_boolean_by_observed_label"
    if standard.data_type == "record":
        return "open_or_select_record_by_observed_label"
    if standard.data_type == "password":
        return "inject_from_configured_secret_store_at_login"
    return "fill_by_observed_label_or_name"


def _selector_policy(status: str) -> str:
    if status in {"ready_for_preview", "credential_secret_only"}:
        return "resolve_by_observed_label_or_stable_name_at_runtime"
    if status == "not_external_edit_target":
        return "no_write_selector"
    return "no_selector_until_editable_capture_is_mapped"


def _requires_preview(status: str) -> bool:
    return status in {"ready_for_preview", "credential_secret_only", "needs_editable_capture"}


def _requires_manual_approval(
    *,
    standard: StandardLabel,
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
) -> bool:
    if standard.key in SENSITIVE_KEYS:
        return True
    if account and account.manual_approval_required:
        return True
    return bool(manifest.manual_approval_required)


def _label_evidence(
    label: PlatformDiscoveredLabel,
    snapshots: dict[int, PlatformStructureSnapshot],
) -> dict[str, Any]:
    snapshot = snapshots.get(label.snapshot_id)
    metadata = label.metadata_json or {}
    return {
        "label_id": label.id,
        "raw_label": label.raw_label,
        "label_kind": label.label_kind,
        "page_label": label.page_label,
        "confidence": label.confidence,
        "review_status": label.review_status,
        "source": metadata.get("source"),
        "input_type": metadata.get("type"),
        "tag": metadata.get("tag"),
        "required": metadata.get("required"),
        "host": snapshot.host if snapshot else None,
        "source_ref": snapshot.source_ref if snapshot else None,
        "login_status": snapshot.login_status if snapshot else None,
    }


def _mapping_evidence(mapping: PlatformRpaMappingProposal) -> dict[str, Any]:
    return {
        "mapping_id": mapping.id,
        "mapping_kind": mapping.mapping_kind,
        "entity_scope": mapping.entity_scope,
        "external_label": mapping.external_label,
        "external_catalog_value": mapping.external_catalog_value,
        "requirement": mapping.requirement,
        "applies_to": mapping.applies_to,
        "review_status": mapping.review_status,
        "status": mapping.status,
    }


def _field_next_action(status: str) -> str:
    if status == "ready_for_preview":
        return "Crear preview de escritura con valores ARM y guardar auditoria antes/despues."
    if status == "credential_secret_only":
        return "Usar credencial cifrada configurada; no pedir ni registrar el valor al operador."
    if status == "needs_editable_capture":
        return "Abrir pantalla de edicion autorizada y capturar etiquetas editables redaccionadas."
    if status == "needs_mapping_review":
        return "Revisar equivalencia contra captura editable antes de ejecutar escritura."
    if status == "not_external_edit_target":
        return "Leer el valor desde la plataforma; no editar este campo desde el Hub."
    return "Mapear el campo desde contrato o captura editable autorizada."


def _operation_methods(*, manifest: PlatformRpaManifest, field_methods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    field_by_key = {field["standard_key"]: field for field in field_methods}
    configured_operations = set(manifest.allowed_operations or [])
    operation_names = [
        operation
        for operation in EDITABLE_OPERATION_REQUIRED_KEYS
        if not configured_operations or operation in configured_operations
    ]
    operations: list[dict[str, Any]] = []
    for operation_name in operation_names:
        required = list(operation_required_keys(manifest.platform_slug, operation_name))
        required_fields = [field_by_key[key] for key in required if key in field_by_key]
        blocking_statuses = {
            field["status"]
            for field in required_fields
            if field["status"]
            not in {
                "ready_for_preview",
                "credential_secret_only",
                "not_external_edit_target",
            }
        }
        missing_keys = sorted(
            field["standard_key"]
            for field in required_fields
            if field["status"] in {"needs_mapping", "needs_mapping_review"}
        )
        needs_capture_keys = sorted(
            field["standard_key"]
            for field in required_fields
            if field["status"] == "needs_editable_capture"
        )
        status = _operation_status(blocking_statuses=blocking_statuses)
        operations.append(
            {
                "operation": operation_name,
                "status": status,
                "required_standard_keys": required,
                "ready_keys": sorted(
                    field["standard_key"]
                    for field in required_fields
                    if field["status"] in {"ready_for_preview", "credential_secret_only"}
                ),
                "missing_or_unreviewed_keys": missing_keys,
                "needs_editable_capture_keys": needs_capture_keys,
                "requires_preview": True,
                "requires_manual_approval": True,
                "requires_before_after_audit": True,
                "next_action": _operation_next_action(status),
            }
        )
    return operations


def operation_required_keys(platform_slug: str, operation: str) -> tuple[str, ...]:
    return PLATFORM_OPERATION_REQUIRED_KEYS.get(
        (platform_slug, operation),
        EDITABLE_OPERATION_REQUIRED_KEYS[operation],
    )


def _operation_status(*, blocking_statuses: set[str]) -> str:
    if not blocking_statuses:
        return "ready_for_preview"
    if "needs_editable_capture" in blocking_statuses:
        return "needs_editable_capture"
    if "needs_mapping_review" in blocking_statuses:
        return "needs_mapping_review"
    return "needs_mapping"


def _operation_next_action(status: str) -> str:
    if status == "ready_for_preview":
        return "Generar preview con datos ARM, solicitar autorizacion y ejecutar job auditado."
    if status == "needs_editable_capture":
        return "Capturar pantalla editable y asociar campos observados antes del preview."
    if status == "needs_mapping_review":
        return "Resolver mapeos pendientes o ambiguos por plataforma/empresa."
    return "Completar mapeo de campos requeridos para la operacion."


def _canonical_key(value: str | None, mapping_kind: str | None = None) -> str | None:
    if not value:
        return "document.type" if mapping_kind == "document_type" else None
    cleaned = value.strip()
    if mapping_kind == "document_type":
        return "document.type"
    if cleaned in STANDARD_LABELS_BY_KEY:
        return cleaned
    return CANONICAL_KEY_ALIASES.get(cleaned)


def _trace_label(
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
    company: Company | None,
) -> str:
    company_name = company.name if company else "ARM"
    if account and account.external_company_name:
        return f"{manifest.platform_name} / {company_name} en {account.external_company_name}"
    return f"{manifest.platform_name} / {company_name}"
