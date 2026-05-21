from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.connectors.rpa.readonly_registry import implemented_readonly_platform_slugs
from app.db.models import (
    Company,
    Document,
    DocumentIntake,
    ExternalDocumentStatus,
    PlatformReviewRun,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformRpaMappingProposal,
    Worker,
    WorkerPlatformRegistration,
)
from app.services.platform_credentials import resolve_platform_credentials

SAFE_STOP_CONDITIONS = [
    "captcha",
    "mfa",
    "legal_notice",
    "session_conflict",
    "rate_limit_or_lock_warning",
    "unexpected_company_or_account",
    "screen_not_matching_approved_variant",
]

SAFE_ATTEMPT_POLICY = {
    "parallel_attempts": False,
    "max_credential_submissions_per_account": 1,
    "max_accounts_per_user_request": 1,
    "selector_guessing_allowed": False,
    "stop_on": SAFE_STOP_CONDITIONS,
}

IMPLEMENTED_READONLY_CONNECTORS = implemented_readonly_platform_slugs()


def build_rpa_variant_plan(
    session: Session,
    *,
    tenant_id: int,
    priority_group: str | None = None,
) -> dict[str, Any]:
    manifests = _manifests(session, tenant_id=tenant_id, priority_group=priority_group)
    schedules = _schedules_by_manifest(session, tenant_id=tenant_id, manifests=manifests)
    accounts = _accounts_by_manifest(session, tenant_id=tenant_id, manifests=manifests)
    mappings = _mappings_by_manifest(session, tenant_id=tenant_id, manifests=manifests)
    latest_runs = _latest_runs_by_manifest(session, tenant_id=tenant_id, manifests=manifests)
    platforms = [
        _platform_plan(
            manifest,
            schedule=schedules.get(manifest.id),
            accounts=accounts.get(manifest.id, []),
            mappings=mappings.get(manifest.id, []),
            latest_run=latest_runs.get(manifest.id),
        )
        for manifest in manifests
    ]
    ready_for_gateway = sum(1 for platform in platforms if platform["gateway_ready"])
    implemented_read_connectors = sum(
        1 for platform in platforms if platform["implemented_connector_available"]
    )
    return {
        "generated_at": datetime.now(timezone.utc),
        "priority_group": priority_group,
        "safe_mode": True,
        "policy": SAFE_ATTEMPT_POLICY,
        "arm_snapshot": _arm_snapshot(session, tenant_id=tenant_id),
        "totals": {
            "platforms": len(platforms),
            "accounts": sum(platform["account_count"] for platform in platforms),
            "credential_ready_accounts": sum(
                platform["credential_ready_accounts"] for platform in platforms
            ),
            "entry_ready_accounts": sum(platform["entry_ready_accounts"] for platform in platforms),
            "gateway_ready_platforms": ready_for_gateway,
            "implemented_read_connectors": implemented_read_connectors,
        },
        "platforms": platforms,
    }


def _platform_plan(
    manifest: PlatformRpaManifest,
    *,
    schedule: PlatformReviewSchedule | None,
    accounts: list[PlatformRpaAccountProposal],
    mappings: list[PlatformRpaMappingProposal],
    latest_run: PlatformReviewRun | None,
) -> dict[str, Any]:
    account_readiness = [_account_readiness(account) for account in accounts]
    credential_ready = sum(1 for item in account_readiness if item["credential_ready"])
    entry_ready = sum(1 for item in account_readiness if item["entry_ready"])
    implemented_connector = manifest.platform_slug in IMPLEMENTED_READONLY_CONNECTORS
    mapping_summary = _mapping_summary(mappings)
    blockers = _blockers(
        manifest=manifest,
        schedule=schedule,
        accounts=accounts,
        credential_ready=credential_ready,
        entry_ready=entry_ready,
        mapping_summary=mapping_summary,
        latest_run=latest_run,
    )
    gateway_ready = bool(accounts and credential_ready and entry_ready and manifest.rpa_assisted_on_control)
    return {
        "manifest_id": manifest.id,
        "external_platform_id": manifest.external_platform_id,
        "platform_slug": manifest.platform_slug,
        "platform_name": manifest.platform_name,
        "priority_group": manifest.priority_group,
        "hosts": manifest.hosts,
        "account_count": len(accounts),
        "credential_ready_accounts": credential_ready,
        "entry_ready_accounts": entry_ready,
        "schedule_id": schedule.id if schedule is not None else None,
        "schedule_status": schedule.status if schedule is not None else "missing",
        "last_result_status": latest_run.result_status if latest_run is not None else None,
        "last_result_summary": latest_run.result_summary if latest_run is not None else None,
        "implemented_connector_available": implemented_connector,
        "gateway_ready": gateway_ready,
        "login_variants": _login_variants(
            manifest=manifest,
            credential_ready=credential_ready,
            entry_ready=entry_ready,
            latest_run=latest_run,
        ),
        "context_variants": _context_variants(manifest=manifest, accounts=accounts),
        "read_variants": _read_variants(
            manifest=manifest,
            mapping_summary=mapping_summary,
            implemented_connector=implemented_connector,
            latest_run=latest_run,
        ),
        "mapping_summary": mapping_summary,
        "safe_attempt_policy": SAFE_ATTEMPT_POLICY,
        "blockers": blockers,
        "next_action": _next_action(
            manifest=manifest,
            gateway_ready=gateway_ready,
            implemented_connector=implemented_connector,
            blockers=blockers,
            latest_run=latest_run,
        ),
    }


def _login_variants(
    *,
    manifest: PlatformRpaManifest,
    credential_ready: int,
    entry_ready: int,
    latest_run: PlatformReviewRun | None,
) -> list[dict[str, Any]]:
    base_status = "candidate" if credential_ready and entry_ready else "blocked"
    base_next = (
        "Disponible para deteccion segura en navegador visible."
        if base_status == "candidate"
        else "Faltan URL/host o credenciales configuradas."
    )
    observed = latest_run is not None and latest_run.result_status in {
        "readonly_capture_synced",
        "login_likely_success",
        "human_gate_authorized",
    }
    variants = [
        _variant(
            "single_page_password",
            "Login usuario/password en una pantalla",
            base_status,
            "Detectar formulario con usuario y password visibles antes de enviar credenciales.",
            base_next,
            ["entry_url", "configured_credentials"],
        ),
        _variant(
            "two_step_password",
            "Login en dos pasos",
            "observed" if observed and manifest.platform_slug == "ctaima" else base_status,
            "Enviar usuario solo si no hay password visible y esperar pantalla de password.",
            (
                "Usada en CTAIMA durante el flujo asistido; mantener parada ante sesion duplicada."
                if observed and manifest.platform_slug == "ctaima"
                else base_next
            ),
            ["entry_url", "configured_credentials", "visible_username_step"],
        ),
        _variant(
            "existing_session_or_resume",
            "Sesion ya abierta o reanudada",
            "candidate" if entry_ready else "blocked",
            "Aprovechar una sesion visible autorizada sin extraer cookies ni tokens.",
            "Confirmar empresa antes de leer datos.",
            ["visible_browser", "operator_context"],
        ),
    ]
    if manifest.rpa_assisted_on_control:
        variants.append(
            _variant(
                "human_control_handoff",
                "Control humano asistido",
                "candidate" if entry_ready else "blocked",
                "Pausar ante captcha, MFA, aviso legal o selector ambiguo.",
                "El operador resuelve el control en pantalla; el sistema no hace bypass.",
                ["visible_browser", "manual_approval_required"],
            )
        )
    return variants


def _context_variants(
    *,
    manifest: PlatformRpaManifest,
    accounts: list[PlatformRpaAccountProposal],
) -> list[dict[str, Any]]:
    account_labels = [account.external_company_name for account in accounts if account.external_company_name]
    return [
        _variant(
            "confirm_authorized_company",
            "Confirmar empresa/cuenta autorizada",
            "candidate" if account_labels else "blocked",
            "Validar que la pantalla externa corresponde a la cuenta ARM seleccionada.",
            "Detener si aparecen varias empresas y no hay coincidencia aprobada.",
            ["platform_account", "external_company_name"],
        ),
        _variant(
            "client_or_project_scope",
            "Confirmar cliente/proyecto",
            "candidate" if manifest.platform_slug == "ctaima" else "pending_review",
            "Confirmar cliente final, centro o contrata antes de leer estados.",
            "Necesita evidencia redaccionada por plataforma y cuenta.",
            ["assignment_scope", "approved_entity_resolution"],
        ),
    ]


def _read_variants(
    *,
    manifest: PlatformRpaManifest,
    mapping_summary: dict[str, Any],
    implemented_connector: bool,
    latest_run: PlatformReviewRun | None,
) -> list[dict[str, Any]]:
    latest_ok = latest_run is not None and latest_run.result_status in {
        "login_likely_success",
        "readonly_status_counts_available",
        "readonly_capture_synced",
    }
    return [
        _variant(
            "readonly_status_capture",
            "Captura redaccionada de estados",
            "implemented" if implemented_connector else "candidate",
            "Leer estructura visible, contadores y estados sin guardar valores de fila.",
            (
                "Conector de solo lectura disponible."
                if implemented_connector
                else "Usar pasarela humana y sincronizar evidencia redaccionada."
            ),
            ["readonly_capture", "no_har", "no_cookies", "no_row_values"],
        ),
        _variant(
            "row_level_status_mapping",
            "Mapeo fila a fila trabajador/documento",
            "candidate" if latest_ok and mapping_summary["approved"] else "blocked",
            "Persistir estado externo por trabajador/documento solo con mapeo aprobado.",
            (
                "Aprobar mapeos y resolucion de entidades antes de persistir filas."
                if not mapping_summary["approved"]
                else "Ejecutar preview y validar entidades resueltas."
            ),
            ["capture_mapping_approved", "entity_resolution_approved"],
        ),
        _variant(
            "manual_export_fallback",
            "Fallback de exportacion manual",
            "candidate",
            "Generar paquete/manual cuando la lectura RPA no encaja.",
            "Mantener como camino disponible para todas las plataformas.",
            ["manual_export", "human_review"],
        ),
    ]


def _variant(
    key: str,
    label: str,
    status: str,
    purpose: str,
    next_action: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "purpose": purpose,
        "next_action": next_action,
        "evidence": evidence,
        "stop_conditions": SAFE_STOP_CONDITIONS,
    }


def _account_readiness(account: PlatformRpaAccountProposal) -> dict[str, Any]:
    credential_resolution = resolve_platform_credentials(
        secret_ref=account.credential_secret_ref,
        platform_account_id=account.source_platform_account_id,
    )
    return {
        "account_id": account.id,
        "entry_ready": bool(account.entry_url or account.host),
        "credential_ready": credential_resolution.credentials is not None,
        "status": account.status,
    }


def _mapping_summary(mappings: list[PlatformRpaMappingProposal]) -> dict[str, Any]:
    by_kind = Counter(mapping.mapping_kind for mapping in mappings)
    approved = sum(1 for mapping in mappings if mapping.review_status == "approved")
    return {
        "total": len(mappings),
        "approved": approved,
        "pending_review": sum(1 for mapping in mappings if mapping.review_status != "approved"),
        "by_kind": dict(sorted(by_kind.items())),
    }


def _blockers(
    *,
    manifest: PlatformRpaManifest,
    schedule: PlatformReviewSchedule | None,
    accounts: list[PlatformRpaAccountProposal],
    credential_ready: int,
    entry_ready: int,
    mapping_summary: dict[str, Any],
    latest_run: PlatformReviewRun | None,
) -> list[str]:
    blockers: list[str] = []
    if not accounts:
        blockers.append("No hay cuenta ARM asociada a la plataforma.")
    if accounts and not entry_ready:
        blockers.append("No hay URL/host de entrada listo.")
    if accounts and not credential_ready:
        blockers.append("No hay credenciales resolubles en servidor.")
    if schedule is None:
        blockers.append("No hay controlador de revision creado.")
    if manifest.platform_slug not in IMPLEMENTED_READONLY_CONNECTORS:
        blockers.append("No hay conector automatico de lectura; usar pasarela humana.")
    if mapping_summary["approved"] == 0:
        blockers.append("No hay mapeos aprobados para persistir filas en el Hub.")
    if latest_run is not None and latest_run.result_status == "readonly_capture_synced":
        evidence: dict[str, Any] = latest_run.evidence_json if isinstance(latest_run.evidence_json, dict) else {}
        gateway_value = evidence.get("gateway")
        gateway: dict[str, Any] = gateway_value if isinstance(gateway_value, dict) else {}
        capture_value = gateway.get("readonly_capture")
        capture: dict[str, Any] = capture_value if isinstance(capture_value, dict) else {}
        if capture.get("session_conflict"):
            blockers.append("La ultima lectura detecto sesion duplicada en la plataforma.")
    return blockers


def _next_action(
    *,
    manifest: PlatformRpaManifest,
    gateway_ready: bool,
    implemented_connector: bool,
    blockers: list[str],
    latest_run: PlatformReviewRun | None,
) -> str:
    if latest_run is not None and latest_run.result_status == "readonly_capture_synced":
        return "Revisar captura sincronizada y aprobar mapeo antes de persistir filas."
    if implemented_connector and gateway_ready:
        return "Ejecutar lectura controlada; persistir filas solo con mapeo aprobado."
    if gateway_ready:
        return "Lanzar pasarela humana para validar login y capturar estructura redaccionada."
    if blockers:
        return blockers[0]
    if manifest.priority_group != "arm_first_priority":
        return "Decidir si entra en el ciclo operativo de 12 horas."
    return "Mantener programacion segura y revisar ultimo resultado."


def _arm_snapshot(session: Session, *, tenant_id: int) -> dict[str, Any]:
    company = _resolve_arm_company(session, tenant_id=tenant_id)
    if company is None:
        return {
            "company_id": None,
            "company_name": None,
            "workers": 0,
            "company_documents": 0,
            "worker_documents": 0,
            "pending_intakes": 0,
            "platform_registrations": 0,
            "external_statuses": 0,
        }
    worker_ids = list(
        session.scalars(
            select(Worker.id).where(Worker.tenant_id == tenant_id, Worker.company_id == company.id)
        )
    )
    company_documents = session.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.tenant_id == tenant_id,
            Document.entity_type == "company",
            Document.entity_id == company.id,
        )
    ) or 0
    worker_documents = 0
    if worker_ids:
        worker_documents = session.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.entity_type == "worker",
                Document.entity_id.in_(worker_ids),
            )
        ) or 0
    pending_intakes = session.scalar(
        select(func.count())
        .select_from(DocumentIntake)
        .where(
            DocumentIntake.tenant_id == tenant_id,
            DocumentIntake.status == "pending_review",
            or_(
                DocumentIntake.requested_company_id == company.id,
                DocumentIntake.predicted_company_id == company.id,
            ),
        )
    ) or 0
    platform_registrations = 0
    if worker_ids:
        platform_registrations = session.scalar(
            select(func.count())
            .select_from(WorkerPlatformRegistration)
            .where(
                WorkerPlatformRegistration.tenant_id == tenant_id,
                WorkerPlatformRegistration.worker_id.in_(worker_ids),
            )
        ) or 0
    external_statuses = session.scalar(
        select(func.count())
        .select_from(ExternalDocumentStatus)
        .where(ExternalDocumentStatus.tenant_id == tenant_id)
    ) or 0
    return {
        "company_id": company.id,
        "company_name": company.name,
        "workers": len(worker_ids),
        "company_documents": company_documents,
        "worker_documents": worker_documents,
        "pending_intakes": pending_intakes,
        "platform_registrations": platform_registrations,
        "external_statuses": external_statuses,
    }


def _resolve_arm_company(session: Session, *, tenant_id: int) -> Company | None:
    return session.scalar(
        select(Company)
        .where(Company.tenant_id == tenant_id, Company.name.ilike("%ARM%"))
        .order_by(Company.id)
    )


def _manifests(
    session: Session,
    *,
    tenant_id: int,
    priority_group: str | None,
) -> list[PlatformRpaManifest]:
    statement = select(PlatformRpaManifest).where(PlatformRpaManifest.tenant_id == tenant_id)
    if priority_group is not None:
        statement = statement.where(PlatformRpaManifest.priority_group == priority_group)
    return list(session.scalars(statement.order_by(PlatformRpaManifest.platform_name)))


def _schedules_by_manifest(
    session: Session,
    *,
    tenant_id: int,
    manifests: list[PlatformRpaManifest],
) -> dict[int, PlatformReviewSchedule]:
    if not manifests:
        return {}
    return {
        schedule.manifest_id: schedule
        for schedule in session.scalars(
            select(PlatformReviewSchedule).where(
                PlatformReviewSchedule.tenant_id == tenant_id,
                PlatformReviewSchedule.manifest_id.in_([manifest.id for manifest in manifests]),
            )
        )
    }


def _accounts_by_manifest(
    session: Session,
    *,
    tenant_id: int,
    manifests: list[PlatformRpaManifest],
) -> dict[int, list[PlatformRpaAccountProposal]]:
    result: dict[int, list[PlatformRpaAccountProposal]] = {}
    if not manifests:
        return result
    for account in session.scalars(
        select(PlatformRpaAccountProposal)
        .where(
            PlatformRpaAccountProposal.tenant_id == tenant_id,
            PlatformRpaAccountProposal.manifest_id.in_([manifest.id for manifest in manifests]),
        )
        .order_by(PlatformRpaAccountProposal.manifest_id, PlatformRpaAccountProposal.id)
    ):
        result.setdefault(account.manifest_id, []).append(account)
    return result


def _mappings_by_manifest(
    session: Session,
    *,
    tenant_id: int,
    manifests: list[PlatformRpaManifest],
) -> dict[int, list[PlatformRpaMappingProposal]]:
    result: dict[int, list[PlatformRpaMappingProposal]] = {}
    if not manifests:
        return result
    for mapping in session.scalars(
        select(PlatformRpaMappingProposal).where(
            PlatformRpaMappingProposal.tenant_id == tenant_id,
            PlatformRpaMappingProposal.manifest_id.in_([manifest.id for manifest in manifests]),
        )
    ):
        result.setdefault(mapping.manifest_id, []).append(mapping)
    return result


def _latest_runs_by_manifest(
    session: Session,
    *,
    tenant_id: int,
    manifests: list[PlatformRpaManifest],
) -> dict[int, PlatformReviewRun]:
    result: dict[int, PlatformReviewRun] = {}
    if not manifests:
        return result
    runs = list(
        session.scalars(
            select(PlatformReviewRun)
            .where(
                PlatformReviewRun.tenant_id == tenant_id,
                PlatformReviewRun.manifest_id.in_([manifest.id for manifest in manifests]),
            )
            .order_by(PlatformReviewRun.manifest_id, PlatformReviewRun.id.desc())
        )
    )
    for run in runs:
        result.setdefault(run.manifest_id, run)
    return result
