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
)
from app.services.platform_mapping import STANDARD_LABELS_BY_KEY
from app.services.platform_current_accounts_sync import account_is_inactive


DATA_CATEGORIES: tuple[dict[str, Any], ...] = (
    {
        "key": "company",
        "label": "Empresa",
        "description": "Datos minimos de empresa ARM y empresa externa asociada.",
        "required_standard_keys": (
            "company.name",
            "company.tax_id",
            "company.address",
            "company.contact_email",
            "company.phone",
            "company.activity_cnae",
        ),
    },
    {
        "key": "workers",
        "label": "Trabajadores",
        "description": "Identidad, alta, puesto y aptitud laboral minimizada del trabajador.",
        "required_standard_keys": (
            "worker.full_name",
            "worker.identifier_value",
            "worker.social_security_number",
            "worker.work_position",
            "worker.starts_at",
            "worker.ends_at",
            "worker.medical_fitness_status",
            "worker.medical_fitness_expires_at",
        ),
    },
    {
        "key": "documents",
        "label": "Documentos",
        "description": "Catalogo documental, fichero, fechas y estado externo.",
        "required_standard_keys": (
            "document.type",
            "document.file",
            "document.issued_at",
            "document.expires_at",
            "document.status",
            "document.rejection_reason",
            "document.external_id",
        ),
    },
    {
        "key": "assignments",
        "label": "Centros/proyectos",
        "description": "Centro, proyecto, coordinacion y periodo aplicable.",
        "required_standard_keys": (
            "work_center.name",
            "project.name",
            "coordination.name",
            "period.start_date",
            "period.end_date",
        ),
    },
    {
        "key": "assets",
        "label": "Maquinaria/vehiculos",
        "description": "Activos CAE, maquinaria, vehiculos y productos con documentacion asociada.",
        "required_standard_keys": (
            "asset.type",
            "asset.identifier",
            "machine.code",
            "machine.manufacturer",
            "machine.model",
            "machine.serial",
            "vehicle.plate",
            "chemical_product.record",
        ),
    },
    {
        "key": "access_status",
        "label": "Acceso y estados",
        "description": "Acceso, estados documentales, incidencias y lectura de rechazos.",
        "required_standard_keys": (
            "platform.login.username",
            "platform.login.password",
            "document.status",
            "document.incident_flag",
            "document.rejection_reason",
        ),
    },
)

CANONICAL_KEY_ALIASES = {
    "company.legal_name": "company.name",
    "company.name": "company.name",
    "company.tax_id": "company.tax_id",
    "company.address": "company.address",
    "company.contact_email": "company.contact_email",
    "company.phone": "company.phone",
    "company.activity_cnae": "company.activity_cnae",
    "worker.first_name": "worker.first_name",
    "worker.last_name": "worker.last_name",
    "worker.identifier": "worker.identifier_value",
    "worker.identifier_value": "worker.identifier_value",
    "worker.company_id": "company.name",
    "worker.workplace_or_project": "project.name",
    "worker.job_role": "worker.work_position",
    "worker.ssn_naf_if_required": "worker.social_security_number",
    "worker.medical_fitness_status_minimized": "worker.medical_fitness_status",
    "document.local_document_type": "document.type",
    "document.external_document_type": "document.type",
    "document.safe_filename": "document.file",
    "document.file": "document.file",
    "document.sha256": "document.external_id",
    "document.issue_date": "document.issued_at",
    "document.expiry_date": "document.expires_at",
    "document.expiry_date_if_applicable": "document.expires_at",
    "document.entity_worker_id": "worker.identifier_value",
    "asset.type": "asset.type",
    "asset.identifier": "asset.identifier",
    "asset.plate": "vehicle.plate",
    "asset.serial_number": "machine.serial",
}


def build_platform_data_coverage(
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
    observed = _observed_keys_by_platform(session, tenant_id=tenant_id)
    proposed, approved = _mapping_keys_by_manifest(session, tenant_id=tenant_id, manifest_ids=manifest_ids)

    contexts: list[dict[str, Any]] = []
    totals = {
        "platforms": len(manifests),
        "contexts": 0,
        "categories": len(DATA_CATEGORIES),
        "approved": 0,
        "mapped": 0,
        "partial": 0,
        "missing": 0,
        "pending_items": 0,
        "pending_red": 0,
        "pending_orange": 0,
        "missing_required_keys": 0,
        "pending_review_keys": 0,
    }
    for manifest in manifests:
        accounts: list[PlatformRpaAccountProposal | None] = [*accounts_by_manifest.get(manifest.id, [])]
        if not accounts:
            accounts.append(None)
        platform_observed = observed.get(manifest.external_platform_id or -1, {})
        platform_proposed = proposed.get(manifest.id, set()) | set(platform_observed)
        platform_approved = approved.get(manifest.id, set()) | {
            key for key, statuses in platform_observed.items() if "approved" in statuses
        }
        for account in accounts:
            if account is not None and account_is_inactive(account.status):
                context = {
                    "manifest_id": manifest.id,
                    "platform_slug": manifest.platform_slug,
                    "platform_name": manifest.platform_name,
                    "account_proposal_id": account.id,
                    "platform_account_id": account.platform_account_id,
                    "external_company_name": account.external_company_name,
                    "trace_label": _trace_label(manifest, account, company),
                    "host": account.host if account.host else (manifest.hosts[0] if manifest.hosts else None),
                    "entry_url_configured": bool(account.entry_url or manifest.entry_urls),
                    "manual_approval_required": bool(account.manual_approval_required),
                    "dry_run": bool(account.dry_run),
                    "categories": [],
                    "blockers": [
                        {
                            "kind": "account_inactive",
                            "severity": "neutral",
                            "detail": "Cuenta dada de baja: no genera avisos ni incidencias operativas.",
                        }
                    ],
                    "pending_items": [],
                    "pending_summary": {"total": 0, "red": 0, "orange": 0},
                    "next_action": "Cuenta baja/inactiva; no se revisa automaticamente.",
                    "source_summary": {
                        "observed_keys": [],
                        "contract_or_proposed_keys": [],
                        "approved_keys": [],
                    },
                }
                contexts.append(context)
                totals["contexts"] += 1
                continue
            categories = [
                _category_coverage(
                    category,
                    proposed_keys=platform_proposed,
                    approved_keys=platform_approved,
                    observed_statuses=platform_observed,
                )
                for category in DATA_CATEGORIES
            ]
            blockers = _context_blockers(manifest, account, categories)
            pending_items = _context_pending_items(
                manifest=manifest,
                account=account,
                categories=categories,
            )
            context = {
                "manifest_id": manifest.id,
                "platform_slug": manifest.platform_slug,
                "platform_name": manifest.platform_name,
                "account_proposal_id": account.id if account else None,
                "platform_account_id": account.platform_account_id if account else None,
                "external_company_name": account.external_company_name if account else None,
                "trace_label": _trace_label(manifest, account, company),
                "host": account.host if account and account.host else (manifest.hosts[0] if manifest.hosts else None),
                "entry_url_configured": bool(account.entry_url if account else manifest.entry_urls),
                "manual_approval_required": bool(
                    account.manual_approval_required if account else manifest.manual_approval_required
                ),
                "dry_run": bool(account.dry_run if account else manifest.dry_run_default),
                "categories": categories,
                "blockers": blockers,
                "pending_items": pending_items,
                "pending_summary": _pending_summary(pending_items),
                "next_action": _next_action(categories, blockers),
                "source_summary": {
                    "observed_keys": sorted(platform_observed),
                    "contract_or_proposed_keys": sorted(platform_proposed),
                    "approved_keys": sorted(platform_approved),
                },
            }
            contexts.append(context)
            totals["contexts"] += 1
            for category in categories:
                totals[category["status"]] += 1
                totals["missing_required_keys"] += len(category["missing_keys"])
                totals["pending_review_keys"] += len(category["pending_review_keys"])
                totals["pending_items"] += len(category["pending_items"])
                totals["pending_red"] += sum(1 for item in category["pending_items"] if item["severity"] == "red")
                totals["pending_orange"] += sum(1 for item in category["pending_items"] if item["severity"] == "orange")
            totals["pending_items"] += len([item for item in pending_items if item["scope"] == "account"])
            totals["pending_red"] += sum(
                1 for item in pending_items if item["scope"] == "account" and item["severity"] == "red"
            )
            totals["pending_orange"] += sum(
                1 for item in pending_items if item["scope"] == "account" and item["severity"] == "orange"
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safe_mode": {
            "read_only": True,
            "stores_external_row_values": False,
            "stores_credentials_or_tokens": False,
            "captcha_bypass": False,
            "medical_data_minimized": True,
        },
        "company": {
            "id": company.id if company else None,
            "name": company.name if company else "ARM",
        },
        "totals": totals,
        "category_contract": [
            {
                "key": category["key"],
                "label": category["label"],
                "description": category["description"],
                "required_standard_keys": list(category["required_standard_keys"]),
            }
            for category in DATA_CATEGORIES
        ],
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


def _observed_keys_by_platform(session: Session, *, tenant_id: int) -> dict[int, dict[str, set[str]]]:
    labels = session.scalars(
        select(PlatformDiscoveredLabel).where(
            PlatformDiscoveredLabel.tenant_id == tenant_id,
            PlatformDiscoveredLabel.standard_key.is_not(None),
        )
    )
    result: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for label in labels:
        if label.external_platform_id is None or label.standard_key is None:
            continue
        result[label.external_platform_id][label.standard_key].add(label.review_status)
    return result


def _mapping_keys_by_manifest(
    session: Session,
    *,
    tenant_id: int,
    manifest_ids: list[int],
) -> tuple[dict[int, set[str]], dict[int, set[str]]]:
    proposed: dict[int, set[str]] = defaultdict(set)
    approved: dict[int, set[str]] = defaultdict(set)
    if not manifest_ids:
        return proposed, approved
    rows = session.scalars(
        select(PlatformRpaMappingProposal).where(
            PlatformRpaMappingProposal.tenant_id == tenant_id,
            PlatformRpaMappingProposal.manifest_id.in_(manifest_ids),
        )
    )
    for row in rows:
        key = _canonical_key(row.iker_key, row.mapping_kind)
        if key is None:
            continue
        proposed[row.manifest_id].add(key)
        if row.review_status == "approved":
            approved[row.manifest_id].add(key)
    return proposed, approved


def _canonical_key(value: str | None, mapping_kind: str | None = None) -> str | None:
    if not value:
        return "document.type" if mapping_kind == "document_type" else None
    cleaned = value.strip()
    if mapping_kind == "document_type":
        return "document.type"
    if cleaned in STANDARD_LABELS_BY_KEY:
        return cleaned
    return CANONICAL_KEY_ALIASES.get(cleaned)


def _category_coverage(
    category: dict[str, Any],
    *,
    proposed_keys: set[str],
    approved_keys: set[str],
    observed_statuses: dict[str, set[str]],
) -> dict[str, Any]:
    required = set(category["required_standard_keys"])
    mapped = required & proposed_keys
    approved = required & approved_keys
    observed = required & set(observed_statuses)
    missing = required - mapped
    pending_review = mapped - approved
    if len(approved) == len(required):
        status = "approved"
    elif not missing:
        status = "mapped"
    elif mapped:
        status = "partial"
    else:
        status = "missing"
    return {
        "category_key": category["key"],
        "label": category["label"],
        "status": status,
        "mapped_count": len(mapped),
        "approved_count": len(approved),
        "observed_count": len(observed),
        "required_count": len(required),
        "mapped_keys": sorted(mapped),
        "approved_keys": sorted(approved),
        "observed_keys": sorted(observed),
        "pending_review_keys": sorted(pending_review),
        "missing_keys": sorted(missing),
        "pending_items": _category_pending_items(
            category_key=category["key"],
            category_label=category["label"],
            missing_keys=missing,
            pending_review_keys=pending_review,
        ),
    }


def _context_blockers(
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
    categories: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if account is None:
        blockers.append("sin_cuenta_externa")
    elif account.status == "blocked_pending_host":
        blockers.append("host_pendiente")
    elif account.status != "active":
        blockers.append("cuenta_no_activada")
    if not (account.entry_url if account else manifest.entry_urls):
        blockers.append("entry_url_pendiente")
    if any(category["status"] in {"partial", "missing"} for category in categories):
        blockers.append("faltan_claves_estandar")
    if any(category["pending_review_keys"] for category in categories):
        blockers.append("mapeos_pendientes_revision")
    return list(dict.fromkeys(blockers))


def _next_action(categories: list[dict[str, Any]], blockers: list[str]) -> str:
    if "entry_url_pendiente" in blockers or "host_pendiente" in blockers:
        return "Completar host/URL de la cuenta antes de lanzar lectura."
    if any(category["status"] == "missing" for category in categories):
        return "Lanzar captura guiada read-only y mapear etiquetas faltantes."
    if any(category["status"] == "partial" for category in categories):
        return "Completar mapeos de categoria y revisar equivalencias."
    if any(category["pending_review_keys"] for category in categories):
        return "Aprobar o corregir mapeos propuestos antes de persistir filas."
    return "Listo para validacion de lectura fila a fila en dry-run."


def _context_pending_items(
    *,
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
    categories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if account is None:
        items.append(
            _pending_item(
                item_id=f"{manifest.platform_slug}:account:missing",
                scope="account",
                kind="missing_external_account",
                severity="red",
                title="Sin cuenta externa",
                detail="No hay cuenta externa asociada al manifiesto para lanzar lecturas.",
                suggested_action="Crear o importar la cuenta externa autorizada.",
            )
        )
    else:
        if account.status == "blocked_pending_host":
            items.append(
                _pending_item(
                    item_id=f"{manifest.platform_slug}:{account.id}:host_pending",
                    scope="account",
                    kind="host_pending",
                    severity="red",
                    title="Host o URL pendiente",
                    detail="La cuenta no tiene host o URL suficiente para abrir una lectura guiada.",
                    suggested_action="Completar host/URL desde contrato o captura autorizada.",
                )
            )
        elif account.status != "active":
            items.append(
                _pending_item(
                    item_id=f"{manifest.platform_slug}:{account.id}:account_not_active",
                    scope="account",
                    kind="account_not_active",
                    severity="orange",
                    title="Cuenta sin activar",
                    detail="La cuenta esta importada como propuesta y requiere activacion explicita por tenant/plataforma.",
                    suggested_action="Revisar autorizacion, credenciales y flags dry_run/manual_approval antes de activar.",
                )
            )
        if not account.entry_url:
            items.append(
                _pending_item(
                    item_id=f"{manifest.platform_slug}:{account.id}:entry_url_missing",
                    scope="account",
                    kind="entry_url_missing",
                    severity="red",
                    title="Entrada no configurada",
                    detail="Falta la URL de entrada para el navegador guiado.",
                    suggested_action="Completar entry_url con una fuente autorizada, sin inventar rutas.",
                )
            )
    for category in categories:
        for item in category["pending_items"]:
            items.append(item)
    return items


def _category_pending_items(
    *,
    category_key: str,
    category_label: str,
    missing_keys: set[str],
    pending_review_keys: set[str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for standard_key in sorted(missing_keys):
        standard = STANDARD_LABELS_BY_KEY.get(standard_key)
        items.append(
            _pending_item(
                item_id=f"{category_key}:missing:{standard_key}",
                scope="category",
                category_key=category_key,
                category_label=category_label,
                kind="missing_required_key",
                severity="red",
                standard_key=standard_key,
                standard_label=standard.display_name if standard else standard_key,
                title="Clave obligatoria sin mapa",
                detail=f"Falta mapear {standard_key} para la categoria {category_label}.",
                suggested_action="Lanzar captura guiada read-only o completar el mapeo desde contrato/captura redaccionada.",
            )
        )
    for standard_key in sorted(pending_review_keys):
        standard = STANDARD_LABELS_BY_KEY.get(standard_key)
        items.append(
            _pending_item(
                item_id=f"{category_key}:review:{standard_key}",
                scope="category",
                category_key=category_key,
                category_label=category_label,
                kind="pending_mapping_review",
                severity="orange",
                standard_key=standard_key,
                standard_label=standard.display_name if standard else standard_key,
                title="Mapeo pendiente de revision",
                detail=f"{standard_key} tiene equivalencia propuesta pero no aprobada.",
                suggested_action="Aprobar, corregir o rechazar la equivalencia antes de persistir filas externas.",
            )
        )
    return items


def _pending_item(
    *,
    item_id: str,
    scope: str,
    kind: str,
    severity: str,
    title: str,
    detail: str,
    suggested_action: str,
    category_key: str | None = None,
    category_label: str | None = None,
    standard_key: str | None = None,
    standard_label: str | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "scope": scope,
        "category_key": category_key,
        "category_label": category_label,
        "kind": kind,
        "severity": severity,
        "standard_key": standard_key,
        "standard_label": standard_label,
        "title": title,
        "detail": detail,
        "suggested_action": suggested_action,
    }


def _pending_summary(pending_items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(pending_items),
        "red": sum(1 for item in pending_items if item["severity"] == "red"),
        "orange": sum(1 for item in pending_items if item["severity"] == "orange"),
        "missing_required_key": sum(1 for item in pending_items if item["kind"] == "missing_required_key"),
        "pending_mapping_review": sum(1 for item in pending_items if item["kind"] == "pending_mapping_review"),
        "account": sum(1 for item in pending_items if item["scope"] == "account"),
    }


def _trace_label(
    manifest: PlatformRpaManifest,
    account: PlatformRpaAccountProposal | None,
    company: Company | None,
) -> str:
    company_name = company.name if company else "ARM"
    if account and account.external_company_name:
        return f"{manifest.platform_name} / {company_name} en {account.external_company_name}"
    return f"{manifest.platform_name} / {company_name}"
