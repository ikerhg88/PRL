from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.connectors.rpa.readonly_registry import implemented_readonly_platform_slugs
from app.db.models import (
    Company,
    Document,
    DocumentType,
    DocumentVersion,
    ExternalDocumentStatus,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformRpaMappingProposal,
    Worker,
    WorkerPlatformRegistration,
)


STATUS_RANK = {"green": 0, "orange": 1, "red": 2}
READ_OK_RESULT_STATUSES = {"login_likely_success", "completed", "readonly_status_counts_available"}
READ_BLOCKED_RESULT_STATUSES = {
    "account_missing",
    "connector_not_implemented",
    "credentials_missing",
    "rpa_disabled",
}
WRITE_OPERATION_KEYS = {
    "sync_company_profile",
    "upsert_worker",
    "deactivate_worker",
    "upload_worker_document",
    "upload_company_document",
    "upload_machine_vehicle_document",
}


def build_authorization_dashboard(
    session: Session,
    *,
    tenant_id: int,
    company_id: int | None = None,
    priority_group: str = "arm_first_priority",
) -> dict[str, Any]:
    company = _resolve_company(session, tenant_id=tenant_id, company_id=company_id)
    workers = list(
        session.scalars(
            select(Worker)
            .where(Worker.tenant_id == tenant_id, Worker.company_id == company.id)
            .order_by(Worker.last_name, Worker.first_name)
        )
    )
    worker_ids = [worker.id for worker in workers]
    documents = _documents_for_company_and_workers(session, tenant_id=tenant_id, company_id=company.id, worker_ids=worker_ids)
    versions_by_document = _versions_by_document(session, documents)
    type_by_id = _document_type_by_id(session, documents)
    registrations_by_worker = _registrations_by_worker(session, tenant_id=tenant_id, worker_ids=worker_ids)
    external_statuses_by_version = _external_statuses_by_version(session, tenant_id=tenant_id, documents=documents)

    incidents: list[dict[str, Any]] = []
    company_status = _company_status(company, documents, versions_by_document, type_by_id, incidents)
    worker_statuses = [
        _worker_status(
            worker,
            documents,
            versions_by_document,
            type_by_id,
            registrations_by_worker.get(worker.id, []),
            external_statuses_by_version,
            incidents,
        )
        for worker in workers
    ]
    platform_statuses = _platform_statuses(
        session,
        tenant_id=tenant_id,
        priority_group=priority_group,
        company_name=company.name,
        company_status=company_status["status"],
        worker_statuses=worker_statuses,
        incidents=incidents,
    )
    overall_status = _max_status(
        [company_status["status"], *[item["status"] for item in worker_statuses], *[item["status"] for item in platform_statuses]]
    )
    ordered_incidents = sorted(
        incidents,
        key=lambda item: (STATUS_RANK.get(item["severity"], 9) * -1, item["platform_name"] or "", item["title"]),
    )
    return {
        "generated_at": datetime.now(timezone.utc),
        "company": {
            "id": company.id,
            "name": company.name,
            "tax_id": company.tax_id,
            "status": company_status["status"],
            "summary": company_status["summary"],
        },
        "overall_status": overall_status,
        "totals": {
            "platforms": len(platform_statuses),
            "workers": len(worker_statuses),
            "green": sum(1 for item in [company_status, *worker_statuses, *platform_statuses] if item["status"] == "green"),
            "orange": sum(1 for item in [company_status, *worker_statuses, *platform_statuses] if item["status"] == "orange"),
            "red": sum(1 for item in [company_status, *worker_statuses, *platform_statuses] if item["status"] == "red"),
            "incidents": len(ordered_incidents),
            "red_incidents": sum(1 for item in ordered_incidents if item["severity"] == "red"),
            "orange_incidents": sum(1 for item in ordered_incidents if item["severity"] == "orange"),
        },
        "platforms": platform_statuses,
        "workers": worker_statuses,
        "incidents": ordered_incidents,
    }


def _resolve_company(session: Session, *, tenant_id: int, company_id: int | None) -> Company:
    statement = select(Company).where(Company.tenant_id == tenant_id)
    if company_id is not None:
        company = session.scalar(statement.where(Company.id == company_id))
        if company is None:
            raise ValueError("Company not found.")
        return company
    arm = session.scalar(
        statement.where(Company.name.ilike("%ARM%")).order_by(Company.id)
    )
    if arm is not None:
        return arm
    company = session.scalar(statement.order_by(Company.id))
    if company is None:
        raise ValueError("No companies available.")
    return company


def _documents_for_company_and_workers(
    session: Session,
    *,
    tenant_id: int,
    company_id: int,
    worker_ids: list[int],
) -> list[Document]:
    clauses = [((Document.entity_type == "company") & (Document.entity_id == company_id))]
    if worker_ids:
        clauses.append((Document.entity_type == "worker") & (Document.entity_id.in_(worker_ids)))
    return list(
        session.scalars(
            select(Document)
            .where(Document.tenant_id == tenant_id)
            .where(or_(*clauses))
            .order_by(Document.entity_type, Document.entity_id, Document.id)
        )
    )


def _versions_by_document(session: Session, documents: list[Document]) -> dict[int, list[DocumentVersion]]:
    if not documents:
        return {}
    versions = list(
        session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id.in_({document.id for document in documents}))
            .order_by(DocumentVersion.document_id, DocumentVersion.version_number)
        )
    )
    result: dict[int, list[DocumentVersion]] = {}
    for version in versions:
        result.setdefault(version.document_id, []).append(version)
    return result


def _document_type_by_id(session: Session, documents: list[Document]) -> dict[int, DocumentType]:
    if not documents:
        return {}
    return {
        item.id: item
        for item in session.scalars(
            select(DocumentType).where(DocumentType.id.in_({document.document_type_id for document in documents}))
        )
    }


def _registrations_by_worker(
    session: Session,
    *,
    tenant_id: int,
    worker_ids: list[int],
) -> dict[int, list[WorkerPlatformRegistration]]:
    if not worker_ids:
        return {}
    registrations = list(
        session.scalars(
            select(WorkerPlatformRegistration)
            .where(
                WorkerPlatformRegistration.tenant_id == tenant_id,
                WorkerPlatformRegistration.worker_id.in_(worker_ids),
            )
            .order_by(WorkerPlatformRegistration.platform_name)
        )
    )
    result: dict[int, list[WorkerPlatformRegistration]] = {}
    for registration in registrations:
        result.setdefault(registration.worker_id, []).append(registration)
    return result


def _external_statuses_by_version(
    session: Session,
    *,
    tenant_id: int,
    documents: list[Document],
) -> dict[int, list[ExternalDocumentStatus]]:
    version_ids = [document.current_version_id for document in documents if document.current_version_id is not None]
    if not version_ids:
        return {}
    statuses = list(
        session.scalars(
            select(ExternalDocumentStatus)
            .where(
                ExternalDocumentStatus.tenant_id == tenant_id,
                ExternalDocumentStatus.document_version_id.in_(version_ids),
            )
            .order_by(ExternalDocumentStatus.last_checked_at.desc())
        )
    )
    result: dict[int, list[ExternalDocumentStatus]] = {}
    for status in statuses:
        result.setdefault(status.document_version_id, []).append(status)
    return result


def _company_status(
    company: Company,
    documents: list[Document],
    versions_by_document: dict[int, list[DocumentVersion]],
    type_by_id: dict[int, DocumentType],
    incidents: list[dict[str, Any]],
) -> dict[str, Any]:
    company_docs = [document for document in documents if document.entity_type == "company" and document.entity_id == company.id]
    status = "green"
    if not company.tax_id:
        _add_incident(
            incidents,
            severity="red",
            entity_type="company",
            entity_id=company.id,
            title="Falta CIF/NIF de empresa",
            detail="La empresa no tiene identificador fiscal completo para contrastar plataformas.",
            suggested_action="Actualizar datos de empresa en el Hub.",
            local_update_path="/documents",
        )
        status = "red"
    if not company_docs:
        _add_incident(
            incidents,
            severity="orange",
            entity_type="company",
            entity_id=company.id,
            title="Sin documentos de empresa aprobados",
            detail="No hay documentacion de empresa lista para comparar o transferir.",
            suggested_action="Subir o aprobar documentos de empresa.",
            local_update_path="/documents",
        )
        status = _max_status([status, "orange"])
    for document in company_docs:
        doc_status = _document_readiness(document, versions_by_document, type_by_id)
        if doc_status["status"] != "green":
            _add_incident(
                incidents,
                severity=doc_status["status"],
                entity_type="company_document",
                entity_id=document.id,
                title=f"Documento empresa: {doc_status['title']}",
                detail=doc_status["detail"],
                suggested_action="Revisar documento de empresa y su version vigente.",
                local_update_path="/documents",
            )
            status = _max_status([status, doc_status["status"]])
    return {
        "status": status,
        "summary": f"{len(company_docs)} documentos de empresa revisados.",
    }


def _worker_status(
    worker: Worker,
    documents: list[Document],
    versions_by_document: dict[int, list[DocumentVersion]],
    type_by_id: dict[int, DocumentType],
    registrations: list[WorkerPlatformRegistration],
    external_statuses_by_version: dict[int, list[ExternalDocumentStatus]],
    incidents: list[dict[str, Any]],
) -> dict[str, Any]:
    worker_docs = [document for document in documents if document.entity_type == "worker" and document.entity_id == worker.id]
    worker_incidents_before = len(incidents)
    status = "green"
    if worker.status == "deleted" or worker.employment_status not in {"active", "pending"}:
        _add_worker_incident(worker, incidents, "red", "Trabajador no activo", "La ficha no esta activa para autorizacion.")
        status = "red"
    if not worker.identifier_value:
        _add_worker_incident(worker, incidents, "red", "Falta DNI/NIE", "El trabajador no tiene identificador completo.")
        status = "red"
    if not worker.work_position:
        _add_worker_incident(worker, incidents, "orange", "Falta puesto", "El puesto ayuda a mapear requisitos por plataforma.")
        status = _max_status([status, "orange"])
    if not worker.medical_fitness_status:
        _add_worker_incident(worker, incidents, "red", "Falta aptitud laboral", "No hay estado de aptitud laboral minimizado.")
        status = "red"
    elif "pendiente" in worker.medical_fitness_status.lower():
        _add_worker_incident(worker, incidents, "orange", "Aptitud pendiente", "La aptitud laboral necesita revision.")
        status = _max_status([status, "orange"])
    if worker.medical_fitness_expires_at is not None:
        days = (worker.medical_fitness_expires_at - date.today()).days
        if days < 0:
            _add_worker_incident(worker, incidents, "red", "Aptitud caducada", "La aptitud laboral esta caducada.")
            status = "red"
        elif days <= 30:
            _add_worker_incident(worker, incidents, "orange", "Aptitud proxima a caducar", f"Caduca en {days} dias.")
            status = _max_status([status, "orange"])
    if not worker_docs:
        _add_worker_incident(worker, incidents, "orange", "Sin documentos de trabajador", "No hay documentos vinculados a la ficha.")
        status = _max_status([status, "orange"])
    for document in worker_docs:
        doc_status = _document_readiness(document, versions_by_document, type_by_id)
        if doc_status["status"] != "green":
            _add_worker_incident(
                worker,
                incidents,
                doc_status["status"],
                f"Documento trabajador: {doc_status['title']}",
                doc_status["detail"],
            )
            status = _max_status([status, doc_status["status"]])
        current_version_id = document.current_version_id
        if current_version_id is not None:
            for external in external_statuses_by_version.get(current_version_id, []):
                normalized = _external_status_to_color(external.status)
                if normalized != "green":
                    _add_worker_incident(
                        worker,
                        incidents,
                        normalized,
                        f"Estado externo {external.status}",
                        external.external_comment or "Estado externo requiere seguimiento.",
                    )
                    status = _max_status([status, normalized])
    if not registrations:
        _add_worker_incident(worker, incidents, "orange", "Sin registro de plataforma", "La ficha no tiene plataformas asignadas en el Hub.")
        status = _max_status([status, "orange"])
    return {
        "worker_id": worker.id,
        "worker_name": f"{worker.first_name} {worker.last_name}",
        "company_id": worker.company_id,
        "status": status,
        "identifier_present": bool(worker.identifier_value),
        "medical_fitness_status": worker.medical_fitness_status,
        "documents": len(worker_docs),
        "platform_registrations": len(registrations),
        "platform_registration_details": [
            _platform_registration_detail(registration)
            for registration in registrations
        ],
        "incident_count": len(incidents) - worker_incidents_before,
        "local_update_path": f"/workers?worker_id={worker.id}",
    }


def _platform_statuses(
    session: Session,
    *,
    tenant_id: int,
    priority_group: str,
    company_name: str,
    company_status: str,
    worker_statuses: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    manifests = list(
        session.scalars(
            _manifest_statement(tenant_id=tenant_id, priority_group=priority_group)
            .order_by(PlatformRpaManifest.platform_name)
        )
    )
    schedules_by_manifest = {
        schedule.manifest_id: schedule
        for schedule in session.scalars(
            select(PlatformReviewSchedule).where(
                PlatformReviewSchedule.tenant_id == tenant_id,
                PlatformReviewSchedule.manifest_id.in_([manifest.id for manifest in manifests] or [-1]),
            )
        )
    }
    result: list[dict[str, Any]] = []
    for manifest in manifests:
        accounts = list(
            session.scalars(
                select(PlatformRpaAccountProposal)
                .where(
                    PlatformRpaAccountProposal.tenant_id == tenant_id,
                    PlatformRpaAccountProposal.manifest_id == manifest.id,
                )
                .order_by(PlatformRpaAccountProposal.external_company_name)
            )
        )
        mappings_count = session.scalar(
            select(func.count())
            .select_from(PlatformRpaMappingProposal)
            .where(
                PlatformRpaMappingProposal.tenant_id == tenant_id,
                PlatformRpaMappingProposal.manifest_id == manifest.id,
            )
        ) or 0
        approved_count = len(
            list(
                session.scalars(
                    select(PlatformRpaMappingProposal.id).where(
                        PlatformRpaMappingProposal.tenant_id == tenant_id,
                        PlatformRpaMappingProposal.manifest_id == manifest.id,
                        PlatformRpaMappingProposal.review_status == "approved",
                    )
                )
            )
        )
        status = _max_status([company_status, *[item["status"] for item in worker_statuses]])
        if any(account.status == "blocked_pending_host" for account in accounts) or manifest.status == "blocked_pending_host":
            _add_incident(
                incidents,
                severity="red",
                entity_type="platform",
                entity_id=manifest.id,
                platform_name=manifest.platform_name,
                title="Host o URL pendiente",
                detail="No se puede preparar preview hasta resolver el punto de entrada.",
                suggested_action="Completar host/URL en contratos y cuenta de plataforma.",
                local_update_path="/authorizations",
            )
            status = "red"
        if manifest.status == "proposal_disabled" or any(account.status == "proposal_disabled" for account in accounts):
            _add_incident(
                incidents,
                severity="orange",
                entity_type="platform",
                entity_id=manifest.id,
                platform_name=manifest.platform_name,
                title="Cuenta deshabilitada para escritura",
                detail="La plataforma esta preparada solo como propuesta revisable.",
                suggested_action="Revisar manifiesto, aprobar mapeos y ejecutar preview antes de activar.",
                local_update_path="/authorizations",
            )
            status = _max_status([status, "orange"])
        if mappings_count and approved_count < mappings_count:
            _add_incident(
                incidents,
                severity="orange",
                entity_type="platform_mapping",
                entity_id=manifest.id,
                platform_name=manifest.platform_name,
                title="Mapeos pendientes",
                detail=f"{mappings_count - approved_count} mapeos pendientes de aprobacion o confirmacion.",
                suggested_action="Revisar mapeos de plataforma en el Hub.",
                local_update_path="/authorizations",
            )
            status = _max_status([status, "orange"])
        capability = _platform_capability(
            manifest=manifest,
            accounts=accounts,
            mapping_count=mappings_count or 0,
            approved_mapping_count=approved_count,
            schedule=schedules_by_manifest.get(manifest.id),
        )
        result.append(
            {
                "manifest_id": manifest.id,
                "platform_name": manifest.platform_name,
                "platform_slug": manifest.platform_slug,
                "status": status,
                "account_count": len(accounts),
                "disabled_account_count": sum(1 for account in accounts if account.status == "proposal_disabled"),
                "blocked_account_count": sum(1 for account in accounts if account.status == "blocked_pending_host"),
                "mapping_count": mappings_count or 0,
                "approved_mapping_count": approved_count,
                "worker_green": sum(1 for item in worker_statuses if item["status"] == "green"),
                "worker_orange": sum(1 for item in worker_statuses if item["status"] == "orange"),
                "worker_red": sum(1 for item in worker_statuses if item["status"] == "red"),
                "requires_signed_authorization": manifest.requires_signed_authorization,
                "dry_run_default": manifest.dry_run_default,
                "manual_approval_required": manifest.manual_approval_required,
                "sensitive_data_minimization_required": manifest.sensitive_data_minimization_required,
                "allowed_operations": manifest.allowed_operations,
                "read_status": capability["read_status"],
                "read_summary": capability["read_summary"],
                "read_detail": capability["read_detail"],
                "write_status": capability["write_status"],
                "write_summary": capability["write_summary"],
                "write_detail": capability["write_detail"],
                "authorization_status": capability["authorization_status"],
                "authorization_summary": capability["authorization_summary"],
                "authorization_detail": capability["authorization_detail"],
                "next_action": capability["next_action"],
                "local_update_path": "/authorizations",
                "account_contexts": _account_contexts(
                    manifest=manifest,
                    accounts=accounts,
                    company_name=company_name,
                ),
            }
        )
    return result


def _manifest_statement(*, tenant_id: int, priority_group: str) -> Any:
    statement = select(PlatformRpaManifest).where(PlatformRpaManifest.tenant_id == tenant_id)
    if priority_group and priority_group != "all":
        statement = statement.where(PlatformRpaManifest.priority_group == priority_group)
    return statement


def _account_contexts(
    *,
    manifest: PlatformRpaManifest,
    accounts: list[PlatformRpaAccountProposal],
    company_name: str,
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for account in accounts:
        external_company = account.external_company_name
        trace_label = (
            f"{manifest.platform_name} / {company_name} en {external_company}"
            if external_company
            else f"{manifest.platform_name} / {company_name}"
        )
        contexts.append(
            {
                "account_proposal_id": account.id,
                "platform_account_id": account.platform_account_id,
                "external_company_name": external_company,
                "trace_label": trace_label,
                "status": account.status,
                "disabled": account.status == "proposal_disabled",
                "blocked": account.status == "blocked_pending_host",
                "has_entry_point": bool(account.entry_url or account.host),
            }
        )
    return contexts


def _platform_capability(
    *,
    manifest: PlatformRpaManifest,
    accounts: list[PlatformRpaAccountProposal],
    mapping_count: int,
    approved_mapping_count: int,
    schedule: PlatformReviewSchedule | None,
) -> dict[str, str]:
    account_blocked = any(account.status == "blocked_pending_host" for account in accounts)
    account_disabled = any(account.status == "proposal_disabled" for account in accounts)
    has_account = len(accounts) > 0
    has_entry_point = bool(manifest.entry_urls or manifest.hosts) or any(
        account.entry_url or account.host for account in accounts
    )
    read_capability = _read_capability(
        manifest=manifest,
        has_account=has_account,
        has_entry_point=has_entry_point,
        account_blocked=account_blocked,
        schedule=schedule,
    )
    write_capability = _write_capability(
        manifest=manifest,
        account_disabled=account_disabled,
        account_blocked=account_blocked,
        mapping_count=mapping_count,
        approved_mapping_count=approved_mapping_count,
    )
    authorization_capability = _authorization_capability(
        manifest=manifest,
        account_disabled=account_disabled,
        account_blocked=account_blocked,
    )
    return {
        **read_capability,
        **write_capability,
        **authorization_capability,
        "next_action": _capability_next_action(
            read_capability=read_capability,
            write_capability=write_capability,
            authorization_capability=authorization_capability,
        ),
    }


def _read_capability(
    *,
    manifest: PlatformRpaManifest,
    has_account: bool,
    has_entry_point: bool,
    account_blocked: bool,
    schedule: PlatformReviewSchedule | None,
) -> dict[str, str]:
    if "read_external_status" not in set(manifest.allowed_operations):
        return {
            "read_status": "red",
            "read_summary": "No declarada",
            "read_detail": "El manifiesto no declara lectura de estados externos.",
        }
    if not has_account:
        return {
            "read_status": "red",
            "read_summary": "Sin cuenta ARM",
            "read_detail": "No hay cuenta seleccionable para probar lectura.",
        }
    if account_blocked or not has_entry_point:
        return {
            "read_status": "red",
            "read_summary": "Falta host/URL",
            "read_detail": "Completar punto de entrada antes de abrir navegador.",
        }
    if manifest.platform_slug not in implemented_readonly_platform_slugs():
        return {
            "read_status": "red",
            "read_summary": "Conector no implementado",
            "read_detail": f"No hay lectura RPA implementada para {manifest.platform_name}.",
        }
    if schedule is None:
        return {
            "read_status": "orange",
            "read_summary": "Pendiente de programar",
            "read_detail": "Crear controlador de revision y lanzar una prueba.",
        }
    if schedule.last_result_status in READ_OK_RESULT_STATUSES:
        return {
            "read_status": "green",
            "read_summary": "Lee estados",
            "read_detail": schedule.last_result_summary or "Ultima lectura registrada como correcta.",
        }
    if schedule.last_result_status in READ_BLOCKED_RESULT_STATUSES:
        return {
            "read_status": "red",
            "read_summary": "Bloqueada",
            "read_detail": schedule.last_result_summary or f"Ultimo resultado: {schedule.last_result_status}.",
        }
    if schedule.enabled:
        return {
            "read_status": "orange",
            "read_summary": "Programada sin prueba",
            "read_detail": "Lanzar Probar lectura para confirmar si funciona.",
        }
    return {
        "read_status": "orange",
        "read_summary": "Pendiente de activar",
        "read_detail": "Activar revision y lanzar prueba en modo seguro.",
    }


def _write_capability(
    *,
    manifest: PlatformRpaManifest,
    account_disabled: bool,
    account_blocked: bool,
    mapping_count: int,
    approved_mapping_count: int,
) -> dict[str, str]:
    write_declared = bool(set(manifest.allowed_operations) & WRITE_OPERATION_KEYS)
    if not write_declared:
        return {
            "write_status": "red",
            "write_summary": "No declarada",
            "write_detail": "El manifiesto no declara operaciones de escritura.",
        }
    if manifest.dry_run_default or manifest.manual_approval_required or manifest.status == "proposal_disabled":
        return {
            "write_status": "red",
            "write_summary": "No escribe ahora",
            "write_detail": "Solo esta permitido preview/dry_run con aprobacion humana.",
        }
    if account_disabled or account_blocked:
        return {
            "write_status": "red",
            "write_summary": "Cuenta no activada",
            "write_detail": "La cuenta sigue deshabilitada o bloqueada por configuracion.",
        }
    if mapping_count and approved_mapping_count < mapping_count:
        return {
            "write_status": "orange",
            "write_summary": "Mapeos pendientes",
            "write_detail": f"Faltan {mapping_count - approved_mapping_count} mapeos por aprobar.",
        }
    return {
        "write_status": "green",
        "write_summary": "Preparada",
        "write_detail": "La escritura requiere job auditado e idempotente antes de ejecutarse.",
    }


def _authorization_capability(
    *,
    manifest: PlatformRpaManifest,
    account_disabled: bool,
    account_blocked: bool,
) -> dict[str, str]:
    if account_blocked:
        return {
            "authorization_status": "red",
            "authorization_summary": "Bloqueada",
            "authorization_detail": "Falta host/URL o cuenta valida antes de autorizar.",
        }
    if manifest.requires_signed_authorization:
        return {
            "authorization_status": "orange",
            "authorization_summary": "Requiere autorizacion",
            "authorization_detail": "Debe constar autorizacion firmada antes de ejecucion real.",
        }
    if account_disabled or manifest.status == "proposal_disabled":
        return {
            "authorization_status": "orange",
            "authorization_summary": "Propuesta deshabilitada",
            "authorization_detail": "Activar solo tras revisar contrato, cuenta y alcance.",
        }
    return {
        "authorization_status": "green",
        "authorization_summary": "Autorizada",
        "authorization_detail": "Controles y alcance base disponibles.",
    }


def _capability_next_action(
    *,
    read_capability: dict[str, str],
    write_capability: dict[str, str],
    authorization_capability: dict[str, str],
) -> str:
    if read_capability["read_status"] == "red":
        return read_capability["read_detail"]
    if authorization_capability["authorization_status"] != "green":
        return authorization_capability["authorization_detail"]
    if write_capability["write_status"] != "green":
        return write_capability["write_detail"]
    if read_capability["read_status"] == "orange":
        return read_capability["read_detail"]
    return "Mantener revision programada y auditar cualquier operacion externa."


def _document_readiness(
    document: Document,
    versions_by_document: dict[int, list[DocumentVersion]],
    type_by_id: dict[int, DocumentType],
) -> dict[str, str]:
    document_type = type_by_id.get(document.document_type_id)
    versions = versions_by_document.get(document.id, [])
    current = next((version for version in versions if version.id == document.current_version_id), versions[-1] if versions else None)
    if current is None:
        return {"status": "red", "title": "sin version", "detail": "El documento no tiene version inmutable."}
    if document.status_internal in {"pending_review", "draft"}:
        return {"status": "orange", "title": "pendiente de revision", "detail": f"{document_type.name if document_type else 'Documento'} no esta aprobado."}
    if document.status_internal in {"rejected", "expired"}:
        return {"status": "red", "title": document.status_internal, "detail": f"{document_type.name if document_type else 'Documento'} esta en estado {document.status_internal}."}
    if current.expires_at is not None:
        days = (current.expires_at - date.today()).days
        if days < 0:
            return {"status": "red", "title": "caducado", "detail": f"Caducado hace {abs(days)} dias."}
        if days <= 30:
            return {"status": "orange", "title": "proximo a caducar", "detail": f"Caduca en {days} dias."}
    if current.expiry_review_status == "review_required":
        return {"status": "orange", "title": "caducidad discrepante", "detail": "La fecha local y la comunicada por plataforma no coinciden."}
    return {"status": "green", "title": "listo", "detail": "Documento listo localmente."}


def _add_worker_incident(
    worker: Worker,
    incidents: list[dict[str, Any]],
    severity: str,
    title: str,
    detail: str,
) -> None:
    _add_incident(
        incidents,
        severity=severity,
        entity_type="worker",
        entity_id=worker.id,
        title=title,
        detail=detail,
        suggested_action="Actualizar ficha del trabajador en el Hub.",
        local_update_path=f"/workers?worker_id={worker.id}",
    )


def _add_incident(
    incidents: list[dict[str, Any]],
    *,
    severity: str,
    entity_type: str,
    entity_id: int,
    title: str,
    detail: str,
    suggested_action: str,
    local_update_path: str,
    platform_name: str | None = None,
) -> None:
    incidents.append(
        {
            "incident_key": f"{entity_type}:{entity_id}:{platform_name or '-'}:{title}".lower().replace(" ", "_"),
            "severity": severity,
            "platform_name": platform_name,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "title": title,
            "detail": detail,
            "suggested_action": suggested_action,
            "local_update_path": local_update_path,
            "source": "hub_local_readiness",
        }
    )


def _external_status_to_color(status: str) -> str:
    lowered = status.lower()
    if any(term in lowered for term in ("accepted", "valid", "ok", "confirmed")):
        return "green"
    if any(term in lowered for term in ("reject", "expired", "missing")):
        return "red"
    return "orange"


def _platform_registration_detail(registration: WorkerPlatformRegistration) -> dict[str, Any]:
    return {
        "id": registration.id,
        "platform_name": registration.platform_name,
        "external_worker_id": registration.external_worker_id,
        "registration_status": registration.registration_status,
        "registration_status_color": _platform_registration_status_to_color(registration.registration_status),
        "assignment_scope": registration.assignment_scope,
        "source": registration.source,
        "last_synced_at": registration.last_synced_at,
        "notes": registration.notes,
    }


def _platform_registration_status_to_color(status: str) -> str:
    lowered = status.lower()
    if any(term in lowered for term in ("caduc", "expired", "reject", "blocked", "missing", "deleted", "inactive")):
        return "red"
    if any(term in lowered for term in ("not_synced", "pending", "review", "manual", "unknown")):
        return "orange"
    if any(term in lowered for term in ("accepted", "active", "valid", "synced", "ok", "confirmed")):
        return "green"
    return "orange"


def _max_status(values: list[str]) -> str:
    if not values:
        return "green"
    return max(values, key=lambda item: STATUS_RANK.get(item, 0))
