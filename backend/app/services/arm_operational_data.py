from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Company,
    Document,
    DocumentIntake,
    DocumentType,
    DocumentVersion,
    Worker,
    WorkerPlatformRegistration,
    WorkerTraining,
    WorkerWorkAssignment,
)


ARM_TAX_ID = "B95868543"


@dataclass(frozen=True)
class ArmWorkerSpec:
    first_name: str
    last_name: str
    aliases: tuple[str, ...]
    identifier_last4: str | None = None


@dataclass(frozen=True)
class ArmOperationalDataResult:
    tenant_id: int
    company_id: int
    workers_ready: int
    test_workers_removed: int
    intakes_linked_to_company: int
    intakes_linked_to_workers: int
    pending_documents_staged: int


ARM_WORKERS: tuple[ArmWorkerSpec, ...] = (
    ArmWorkerSpec("Alicia", "Gomez Moreno", ("alicia gomez", "gomez moreno alicia", "alicia")),
    ArmWorkerSpec("Bruno", "Lopez Martin", ("bruno lopez", "bruno", "manu")),
    ArmWorkerSpec("Carlos", "Perez Ruiz", ("carlos perez ruiz", "carlos", "carlos")),
    ArmWorkerSpec("Daniel", "Torres Vidal", ("daniel torres vidal", "daniel")),
    ArmWorkerSpec("Eduardo", "Ramos Nunez", ("eduardo ramos nunez", "eduardo"), "000T"),
    ArmWorkerSpec("Fernando", "Ortega Cano", ("fernando ortega cano", "fernando")),
    ArmWorkerSpec("Hugo", "Molina Vera", ("hugo molina vera", "hugo", "hugo"), "111X"),
    ArmWorkerSpec("Mario", "Santos Vega", ("mario santos", "santos mario", "mario", "mario")),
    ArmWorkerSpec(
        "Laura",
        "Navarro Gil",
        ("laura navarro gil", "navarro gil laura", "laura"),
    ),
    ArmWorkerSpec("Nicolas", "Romero Soler", ("nicolas romero soler", "romero soler nicolas", "nicolas")),
)

WORKER_DOCUMENT_FALLBACKS = {
    "formacio n metal y reciclaje 28 03 2023 pdf": "bruno lopez",
}


def normalize_arm_operational_data(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
) -> ArmOperationalDataResult:
    company = session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.tax_id == ARM_TAX_ID)
    )
    if company is None:
        raise RuntimeError("ARM company not found. Run the local demo seed first.")

    company.name = "Empresa Demo Industrial, S.L."
    company.company_type = "own"
    company.status = "active"

    worker_by_alias = _ensure_workers(session, tenant_id=tenant_id, company_id=company.id)
    removed = _delete_test_workers(session, tenant_id=tenant_id, company_id=company.id, keep_worker_ids={w.id for w in worker_by_alias.values()})
    type_by_code = _document_types(session, tenant_id=tenant_id)

    intakes_linked_to_company = 0
    intakes_linked_to_workers = 0
    pending_documents_staged = 0
    intakes = list(
        session.scalars(
            select(DocumentIntake)
            .where(DocumentIntake.tenant_id == tenant_id)
            .order_by(DocumentIntake.id)
        )
    )
    for intake in intakes:
        filename_key = _norm(intake.original_filename)
        if _is_company_document(filename_key):
            doc_type = _company_document_type(filename_key, type_by_code)
            _link_intake(
                intake,
                company_id=company.id,
                worker_id=None,
                entity_type="company",
                entity_id=company.id,
                document_type_id=doc_type.id,
                confidence=max(intake.confidence or 0, 80),
            )
            intakes_linked_to_company += 1
            if _stage_pending_document(
                session,
                intake=intake,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                document_type_id=doc_type.id,
                entity_type="company",
                entity_id=company.id,
            ):
                pending_documents_staged += 1
            continue

        worker = _worker_for_filename(filename_key, worker_by_alias)
        if worker is None:
            continue
        doc_type = _worker_document_type(filename_key, type_by_code)
        _link_intake(
            intake,
            company_id=company.id,
            worker_id=worker.id,
            entity_type="worker",
            entity_id=worker.id,
            document_type_id=doc_type.id,
            confidence=max(intake.confidence or 0, 75),
        )
        intakes_linked_to_workers += 1
        if _stage_pending_document(
            session,
            intake=intake,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            document_type_id=doc_type.id,
            entity_type="worker",
            entity_id=worker.id,
        ):
            pending_documents_staged += 1

    session.flush()
    return ArmOperationalDataResult(
        tenant_id=tenant_id,
        company_id=company.id,
        workers_ready=len({worker.id for worker in worker_by_alias.values()}),
        test_workers_removed=removed,
        intakes_linked_to_company=intakes_linked_to_company,
        intakes_linked_to_workers=intakes_linked_to_workers,
        pending_documents_staged=pending_documents_staged,
    )


def _ensure_workers(session: Session, *, tenant_id: int, company_id: int) -> dict[str, Worker]:
    existing = list(
        session.scalars(
            select(Worker).where(Worker.tenant_id == tenant_id, Worker.company_id == company_id)
        )
    )
    workers_by_alias: dict[str, Worker] = {}
    for spec in ARM_WORKERS:
        worker = _find_worker(existing, spec)
        if worker is None:
            worker = Worker(
                tenant_id=tenant_id,
                company_id=company_id,
                first_name=spec.first_name,
                last_name=spec.last_name,
            )
            session.add(worker)
            session.flush()
            existing.append(worker)
        worker.first_name = spec.first_name
        worker.last_name = spec.last_name
        worker.identifier_type = "dni" if spec.identifier_last4 else worker.identifier_type
        worker.identifier_last4 = spec.identifier_last4 or worker.identifier_last4
        worker.employment_status = "active"
        worker.status = "active"
        worker.cae_notes = (
            "Ficha ARM normalizada desde evidencias documentales locales; "
            "documentos pendientes de revision humana antes de uso externo."
        )
        for alias in spec.aliases:
            workers_by_alias[_norm(alias)] = worker
        workers_by_alias[_norm(f"{spec.first_name} {spec.last_name}")] = worker
    session.flush()
    return workers_by_alias


def _find_worker(existing: list[Worker], spec: ArmWorkerSpec) -> Worker | None:
    aliases = {_norm(alias) for alias in spec.aliases}
    target = _norm(f"{spec.first_name} {spec.last_name}")
    for worker in existing:
        name = _norm(f"{worker.first_name} {worker.last_name}")
        if name == target or name in aliases:
            return worker
        if any(alias in name or name in alias for alias in aliases):
            return worker
    return None


def _delete_test_workers(
    session: Session,
    *,
    tenant_id: int,
    company_id: int,
    keep_worker_ids: set[int],
) -> int:
    candidates = list(
        session.scalars(
            select(Worker).where(
                Worker.tenant_id == tenant_id,
                Worker.company_id == company_id,
            )
        )
    )
    delete_ids = [
        worker.id
        for worker in candidates
        if worker.id not in keep_worker_ids and _looks_like_test_worker(worker)
    ]
    if not delete_ids:
        return 0
    document_ids = set(
        session.scalars(
            select(Document.id).where(
                Document.tenant_id == tenant_id,
                Document.entity_type == "worker",
                Document.entity_id.in_(delete_ids),
            )
        )
    )
    session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(document_ids or {-1})))
    session.execute(delete(Document).where(Document.id.in_(document_ids or {-1})))
    session.execute(delete(WorkerTraining).where(WorkerTraining.worker_id.in_(delete_ids)))
    session.execute(delete(WorkerWorkAssignment).where(WorkerWorkAssignment.worker_id.in_(delete_ids)))
    session.execute(delete(WorkerPlatformRegistration).where(WorkerPlatformRegistration.worker_id.in_(delete_ids)))
    session.execute(delete(Worker).where(Worker.id.in_(delete_ids)))
    session.flush()
    return len(delete_ids)


def _looks_like_test_worker(worker: Worker) -> bool:
    name = _norm(f"{worker.first_name} {worker.last_name}")
    return (
        name.startswith("prueba ")
        or name.startswith("empleado prueba")
        or name.startswith("e2etestapi")
        or "pendiente revisar" in name
        or name == "bruno lopez"
        or "live seisconecta" in name
        or "alta plataforma" in name
    )


def _document_types(session: Session, *, tenant_id: int) -> dict[str, DocumentType]:
    by_code = {
        item.code: item
        for item in session.scalars(
            select(DocumentType).where(
                (DocumentType.tenant_id.is_(None)) | (DocumentType.tenant_id == tenant_id)
            )
        )
    }
    for code, name, scope in (
        ("ARM.COMPANY.SOCIAL_SECURITY_PAYMENT", "Pago de seguros sociales", "company"),
        ("ARM.COMPANY.SALARY_PAYMENT_DECLARATION", "Declaracion de pago de salarios", "company"),
        ("ARM.WORKER.TRAINING_EVIDENCE", "Evidencia formativa de trabajador", "worker"),
        ("CAE.WORKER.PRL_50H_COURSE", "Curso PRL 50 horas", "worker"),
        ("CAE.WORKER.PRL_ART19", "Formacion PRL Art. 19", "worker"),
        ("CAE.WORKER.METAL_TRAINING", "Formacion metal", "worker"),
        ("CAE.WORKER.METAL_RECYCLING", "Reciclaje metal", "worker"),
        ("CAE.WORKER.FORKLIFT_TRAINING", "Formacion carretilla elevadora", "worker"),
        ("CAE.WORKER.MEWP_TRAINING", "Formacion plataforma elevadora", "worker"),
        ("CAE.WORKER.OVERHEAD_CRANE_TRAINING", "Formacion puente grua", "worker"),
        ("CAE.WORKER.HEIGHT_WORKS_TRAINING", "Formacion trabajos en altura", "worker"),
        ("ARM.WORKER.PRL_60H_COURSE", "Curso PRL 60 horas", "worker"),
        ("ARM.WORKER.CLIENT_CONFIDENTIALITY", "Confidencialidad cliente", "worker"),
        ("ARM.WORKER.CLIENT_INDUCTION", "Formacion o acceso cliente", "worker"),
        ("ARM.WORKER.TOOL_USE_AUTHORIZATION", "Autorizacion uso herramientas", "worker"),
        ("ARM.WORKER.SOCIAL_SECURITY_REGISTRATION", "Alta Seguridad Social trabajador", "worker"),
        ("ARM.WORKER.CONTRACT", "Contrato de trabajador", "worker"),
        ("ARM.WORKER.GENERAL_EVIDENCE", "Evidencia documental de trabajador", "worker"),
    ):
        if code in by_code:
            continue
        document_type = DocumentType(
            tenant_id=tenant_id,
            code=code,
            name=name,
            entity_scope=scope,
            is_common_cae_type=False,
            requires_expiration=False,
            retention_days=3650,
        )
        session.add(document_type)
        session.flush()
        by_code[code] = document_type
    return by_code


def _is_company_document(filename_key: str) -> bool:
    return any(
        token in filename_key
        for token in (
            "pago seguros sociales",
            "tc1",
            "tc2",
            "certificado hacienda",
            "certificado seguridad social",
            "ita",
            "pago salarios",
        )
    )


def _company_document_type(filename_key: str, type_by_code: dict[str, DocumentType]) -> DocumentType:
    if "certificado hacienda" in filename_key:
        return type_by_code["CAE.COMPANY.AEAT_CLEARANCE"]
    if "certificado seguridad social" in filename_key:
        return type_by_code["CAE.COMPANY.SS_CLEARANCE"]
    if "pago seguros sociales" in filename_key:
        return type_by_code["ARM.COMPANY.SOCIAL_SECURITY_PAYMENT"]
    if "tc1" in filename_key:
        return type_by_code["CAE.COMPANY.RLC_TC1"]
    if "tc2" in filename_key:
        return type_by_code["CAE.COMPANY.RNT_TC2"]
    if re.search(r"\bita\b", filename_key):
        return type_by_code["CAE.COMPANY.ITA"]
    if "pago salarios" in filename_key:
        return type_by_code["ARM.COMPANY.SALARY_PAYMENT_DECLARATION"]
    return type_by_code["ARM.COMPANY.SOCIAL_SECURITY_PAYMENT"]


def _worker_document_type(filename_key: str, type_by_code: dict[str, DocumentType]) -> DocumentType:
    if "epi" in filename_key:
        return type_by_code["CAE.WORKER.PPE_DELIVERY"]
    if "carretilla" in filename_key:
        return type_by_code["CAE.WORKER.FORKLIFT_TRAINING"]
    if "plataforma" in filename_key:
        return type_by_code["CAE.WORKER.MEWP_TRAINING"]
    if "puente grua" in filename_key or "puente grúa" in filename_key:
        return type_by_code["CAE.WORKER.OVERHEAD_CRANE_TRAINING"]
    if "altura" in filename_key or "alturas" in filename_key:
        return type_by_code["CAE.WORKER.HEIGHT_WORKS_TRAINING"]
    if "reciclaje" in filename_key:
        return type_by_code["CAE.WORKER.METAL_RECYCLING"]
    if "metal" in filename_key:
        return type_by_code["CAE.WORKER.METAL_TRAINING"]
    if "art 19" in filename_key or "art19" in filename_key:
        return type_by_code["CAE.WORKER.PRL_ART19"]
    if "50 h" in filename_key or "50 horas" in filename_key:
        return type_by_code["CAE.WORKER.PRL_50H_COURSE"]
    if "60 h" in filename_key or "60 horas" in filename_key or "60horas" in filename_key:
        return type_by_code["ARM.WORKER.PRL_60H_COURSE"]
    if "confidencialidad" in filename_key or "confidecialidad" in filename_key:
        return type_by_code["ARM.WORKER.CLIENT_CONFIDENTIALITY"]
    if "cliente_f" in filename_key or "cliente_c" in filename_key:
        return type_by_code["ARM.WORKER.CLIENT_INDUCTION"]
    if "herramienta" in filename_key or "maquina" in filename_key:
        return type_by_code["ARM.WORKER.TOOL_USE_AUTHORIZATION"]
    if "contrato" in filename_key:
        return type_by_code["ARM.WORKER.CONTRACT"]
    if "alta" in filename_key or "ta2" in filename_key:
        return type_by_code["ARM.WORKER.SOCIAL_SECURITY_REGISTRATION"]
    if "prl" in filename_key or "curso" in filename_key:
        return type_by_code["CAE.WORKER.BASIC_PRL_COURSE"]
    return type_by_code["ARM.WORKER.GENERAL_EVIDENCE"]


def _worker_for_filename(filename_key: str, worker_by_alias: dict[str, Worker]) -> Worker | None:
    fallback_alias = WORKER_DOCUMENT_FALLBACKS.get(filename_key)
    if fallback_alias:
        return worker_by_alias.get(_norm(fallback_alias))
    for alias, worker in sorted(worker_by_alias.items(), key=lambda item: len(item[0]), reverse=True):
        if alias and alias in filename_key:
            return worker
    return None


def _link_intake(
    intake: DocumentIntake,
    *,
    company_id: int,
    worker_id: int | None,
    entity_type: str,
    entity_id: int,
    document_type_id: int,
    confidence: int,
) -> None:
    intake.requested_company_id = company_id
    intake.predicted_company_id = company_id
    intake.requested_worker_id = worker_id
    intake.predicted_worker_id = worker_id
    intake.predicted_entity_type = entity_type
    intake.predicted_entity_id = entity_id
    intake.predicted_document_type_id = document_type_id
    intake.intake_scope = "single_worker" if worker_id is not None else "company"
    intake.confidence = confidence
    intake.classification_json = {
        **(intake.classification_json or {}),
        "arm_operational_normalization": "filename_and_local_ocr_evidence",
    }
    intake.signals_json = {
        **(intake.signals_json or {}),
        "arm_operational_state": "pending_human_review",
    }


def _stage_pending_document(
    session: Session,
    *,
    intake: DocumentIntake,
    tenant_id: int,
    actor_user_id: int | None,
    document_type_id: int,
    entity_type: str,
    entity_id: int,
) -> bool:
    if intake.created_version_id is not None:
        version = session.get(DocumentVersion, intake.created_version_id)
        document = session.get(Document, intake.created_document_id) if intake.created_document_id else None
        if version is not None and document is not None:
            document.document_type_id = document_type_id
            document.entity_type = entity_type
            document.entity_id = entity_id
            document.status_internal = "pending_internal_review"
            return False

    existing_version = session.scalar(
        select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            Document.tenant_id == tenant_id,
            DocumentVersion.sha256 == intake.sha256,
        )
        .order_by(DocumentVersion.id)
    )
    if existing_version is not None:
        document = session.get(Document, existing_version.document_id)
        if document is not None:
            document.document_type_id = document_type_id
            document.entity_type = entity_type
            document.entity_id = entity_id
            document.status_internal = "pending_internal_review"
            intake.created_document_id = document.id
            intake.created_version_id = existing_version.id
            return False

    document = Document(
        tenant_id=tenant_id,
        document_type_id=document_type_id,
        entity_type=entity_type,
        entity_id=entity_id,
        status_internal="pending_internal_review",
    )
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        file_storage_key=intake.file_storage_key,
        sha256=intake.sha256,
        filename=intake.original_filename,
        mime_type=intake.mime_type,
        size_bytes=intake.size_bytes,
        issued_at=intake.issued_at,
        expires_at=intake.expires_at,
        source="import",
        created_by=actor_user_id,
    )
    session.add(version)
    session.flush()
    document.current_version_id = version.id
    document.status_internal = "pending_internal_review"
    intake.created_document_id = document.id
    intake.created_version_id = version.id
    intake.review_comment = "Documento preparado para el Hub; pendiente de validacion humana."
    intake.reviewed_at = None
    intake.updated_at = datetime.now(timezone.utc)
    return True


def _norm(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()
