from __future__ import annotations

import hashlib
import io
import mimetypes
import re
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from sqlalchemy import delete, func, or_, select
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
from app.services.audit import public_state, record_audit
from app.services.document_storage import StoredFile, StoredFileTooLarge, store_intake_bytes
from app.services.ocr_intake import analyze_document_intake
from app.services.worker_identity import normalize_worker_identifier, worker_identifier_hash

ARM_TAX_ID = "B95868543"
ARM_COMPANY_NAME = "Empresa Demo Industrial, S.L."

SUPPORTED_ARCHIVE_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".txt",
    ".csv",
    ".md",
}

NESTED_ARCHIVE_EXTENSIONS = {".zip"}


@dataclass(frozen=True)
class ArchiveFile:
    logical_path: str
    filename: str
    extension: str
    content: bytes
    depth: int


@dataclass
class ArchiveImportResult:
    archive_path: str
    tenant_id: int
    company_id: int
    files_seen: int = 0
    files_imported: int = 0
    intakes_created: int = 0
    intakes_reused: int = 0
    documents_staged: int = 0
    versions_created: int = 0
    duplicate_versions: int = 0
    workers_created: int = 0
    workers_updated: int = 0
    workers_removed: int = 0
    nested_archives_seen: int = 0
    skipped: list[dict[str, str]] = field(default_factory=list)
    by_scope: dict[str, int] = field(default_factory=dict)
    by_document_type: dict[str, int] = field(default_factory=dict)
    by_worker: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerRosterIdentity:
    first_name: str
    last_name: str
    identifier_value: str
    email: str | None = None
    phone: str | None = None
    social_security_number: str | None = None


DOCUMENT_TYPE_SPECS: tuple[tuple[str, str, str, bool], ...] = (
    ("CAE.COMPANY.RC_POLICY", "Poliza responsabilidad civil", "company", True),
    ("CAE.COMPANY.RC_RECEIPT", "Recibo responsabilidad civil", "company", True),
    ("CAE.COMPANY.AEAT_CLEARANCE", "Certificado AEAT", "company", True),
    ("CAE.COMPANY.SS_CLEARANCE", "Certificado Seguridad Social", "company", True),
    ("CAE.COMPANY.RLC_TC1", "RLC / TC1", "company", False),
    ("CAE.COMPANY.RNT_TC2", "RNT / TC2", "company", False),
    ("CAE.COMPANY.ITA", "Informe trabajadores en alta", "company", False),
    ("CAE.WORKER.ID_DOCUMENT", "Documento identificativo", "worker", True),
    ("CAE.WORKER.MEDICAL_FITNESS", "Aptitud medica laboral", "worker", True),
    ("CAE.WORKER.PPE_DELIVERY", "Entrega de EPIs", "worker", False),
    ("CAE.WORKER.BASIC_PRL_COURSE", "Curso basico PRL", "worker", False),
    ("CAE.WORKER.RISK_INFORMATION", "Informacion de riesgos", "worker", False),
    ("ARM.COMPANY.SOCIAL_SECURITY_PAYMENT", "Pago de seguros sociales", "company", False),
    ("ARM.COMPANY.SALARY_PAYMENT_DECLARATION", "Declaracion de pago de salarios", "company", False),
    ("ARM.COMPANY.CENSUS_CERTIFICATE", "Certificado censal", "company", False),
    ("ARM.COMPANY.MUTUA_CERTIFICATE", "Certificado de mutua", "company", False),
    ("ARM.COMPANY.PREVENTION_PLAN", "Plan de prevencion", "company", False),
    ("ARM.COMPANY.RISK_ASSESSMENT", "Evaluacion de riesgos laborales", "company", False),
    ("ARM.COMPANY.PREVENTIVE_ACTIVITY_PLANNING", "Planificacion preventiva", "company", False),
    ("ARM.COMPANY.SPA_CONTRACT", "Concierto servicio prevencion ajeno", "company", False),
    ("ARM.COMPANY.CURRENT_PAYMENT_CERTIFICATE", "Certificado corriente de pago", "company", True),
    ("ARM.COMPANY.ACCIDENT_POLICY", "Poliza accidentes", "company", True),
    ("ARM.COMPANY.ACCIDENT_RECEIPT", "Recibo poliza accidentes", "company", True),
    ("ARM.COMPANY.PROPERTY_POLICY", "Poliza multiriesgo", "company", True),
    ("ARM.COMPANY.WORKFORCE_RELATION", "Relacion de personal", "company", False),
    ("ARM.COMPANY.GENERAL_EVIDENCE", "Evidencia documental de empresa", "company", False),
    ("ARM.WORKER.TRAINING_EVIDENCE", "Evidencia formativa de trabajador", "worker", False),
    ("ARM.WORKER.SOCIAL_SECURITY_REGISTRATION", "Alta Seguridad Social trabajador", "worker", False),
    ("ARM.WORKER.CONTRACT", "Contrato de trabajador", "worker", False),
    ("ARM.WORKER.CONTRACT_EXTENSION", "Prorroga contractual", "worker", False),
    ("ARM.WORKER.SUBROGATION", "Subrogacion trabajador", "worker", False),
    ("ARM.WORKER.TAX_FAMILY_DECLARATION", "Declaracion situacion familiar", "worker", False),
    ("ARM.WORKER.MEDICAL_FITNESS_WAIVER", "Renuncia vigilancia salud", "worker", False),
    ("ARM.WORKER.TOOL_USE_AUTHORIZATION", "Autorizacion uso herramientas", "worker", False),
    ("ARM.WORKER.CLIENT_CONFIDENTIALITY", "Confidencialidad cliente", "worker", False),
    ("ARM.WORKER.CLIENT_INDUCTION", "Formacion o acceso cliente", "worker", False),
    ("ARM.WORKER.PHOTO", "Fotografia trabajador", "worker", False),
    ("ARM.WORKER.PERSONAL_RECORD", "Documento personal trabajador", "worker", False),
    ("ARM.WORKER.PRL_60H_COURSE", "Curso PRL 60 horas", "worker", False),
    ("ARM.WORKER.GENERAL_EVIDENCE", "Evidencia documental de trabajador", "worker", False),
    ("CAE.WORKER.PRL_50H_COURSE", "Curso PRL 50 horas", "worker", False),
    ("CAE.WORKER.PRL_ART19", "Formacion PRL Art. 19", "worker", False),
    ("CAE.WORKER.METAL_TRAINING", "Formacion metal", "worker", False),
    ("CAE.WORKER.METAL_RECYCLING", "Reciclaje metal", "worker", False),
    ("CAE.WORKER.FORKLIFT_TRAINING", "Formacion carretilla elevadora", "worker", False),
    ("CAE.WORKER.MEWP_TRAINING", "Formacion plataforma elevadora", "worker", False),
    ("CAE.WORKER.OVERHEAD_CRANE_TRAINING", "Formacion puente grua", "worker", False),
    ("CAE.WORKER.HEIGHT_WORKS_TRAINING", "Formacion trabajos en altura", "worker", False),
)

KNOWN_WORKER_FOLDERS: dict[str, tuple[str, str, str | None]] = {
    "lopez martin bruno": ("Bruno", "Lopez Martin", None),
    "gomez moreno alicia": ("Alicia", "Gomez Moreno", None),
    "ramos nunez eduardo": ("Eduardo", "Ramos Nunez", "000T"),
    "perez ruiz carlos": ("Carlos", "Perez Ruiz", None),
    "santos mario": ("Mario", "Santos Vega", None),
    "navarro gil laura": ("Laura", "Navarro Gil", None),
    "ortega fernando": ("Fernando", "Ortega Cano", None),
    "romero soler nicolas": ("Nicolas", "Romero Soler", None),
    "molina vera hugo": ("Hugo", "Molina Vera", "111X"),
    "torres daniel": ("Daniel", "Torres Vidal", None),
}


def import_company_prl_archive(
    session: Session,
    *,
    archive_path: Path,
    tenant_id: int,
    actor_user_id: int | None,
    company_tax_id: str = ARM_TAX_ID,
    company_name: str = ARM_COMPANY_NAME,
    max_zip_depth: int = 3,
) -> ArchiveImportResult:
    company = _ensure_company(
        session,
        tenant_id=tenant_id,
        company_tax_id=company_tax_id,
        company_name=company_name,
    )
    type_by_code = _ensure_document_types(session, tenant_id=tenant_id)
    worker_by_name = _load_worker_index(session, tenant_id=tenant_id, company_id=company.id)
    worker_by_identifier_hash = _load_worker_identifier_index(
        session,
        tenant_id=tenant_id,
        company_id=company.id,
    )
    result = ArchiveImportResult(
        archive_path=str(archive_path),
        tenant_id=tenant_id,
        company_id=company.id,
    )
    members = _iter_zip_files(archive_path, max_depth=max_zip_depth, result=result)
    roster_by_name = _extract_roster_by_name(members)
    scope_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    worker_counter: Counter[str] = Counter()
    archive_worker_ids: set[int] = set()
    saw_worker_folder = False

    for member in members:
        result.files_seen += 1
        if _worker_folder_from_path(member.logical_path) is not None:
            saw_worker_folder = True
        if member.extension not in SUPPORTED_ARCHIVE_EXTENSIONS:
            result.skipped.append({"path": member.logical_path, "reason": f"unsupported:{member.extension or 'none'}"})
            continue

        classification = classify_archive_member(member.logical_path, type_by_code)
        worker: Worker | None = None
        if classification["scope"] == "worker":
            folder = _worker_folder_from_path(member.logical_path)
            if folder is None:
                result.skipped.append({"path": member.logical_path, "reason": "worker_folder_missing"})
                continue
            worker, created, updated = _ensure_worker_from_folder(
                session,
                tenant_id=tenant_id,
                company_id=company.id,
                folder=folder,
                worker_by_name=worker_by_name,
                worker_by_identifier_hash=worker_by_identifier_hash,
                roster_by_name=roster_by_name,
            )
            if created:
                result.workers_created += 1
            if updated:
                result.workers_updated += 1
            archive_worker_ids.add(worker.id)

        document_type = type_by_code[classification["document_type_code"]]
        _, intake, intake_created = _ensure_intake(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            member=member,
            company=company,
            worker=worker,
            document_type=document_type,
            classification=classification,
            result=result,
        )
        if intake is None:
            continue

        if intake_created:
            result.intakes_created += 1
        else:
            result.intakes_reused += 1

        version_created = _stage_document_version(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            intake=intake,
            document_type=document_type,
            entity_type=classification["scope"],
            entity_id=worker.id if worker is not None else company.id,
        )
        result.documents_staged += 1
        if version_created:
            result.versions_created += 1
        else:
            result.duplicate_versions += 1
        result.files_imported += 1
        scope_counter[classification["scope"]] += 1
        type_counter[document_type.code] += 1
        if worker is not None:
            worker_counter[f"{worker.first_name} {worker.last_name}"] += 1

    result.by_scope = dict(sorted(scope_counter.items()))
    result.by_document_type = dict(sorted(type_counter.items()))
    result.by_worker = dict(sorted(worker_counter.items()))
    if saw_worker_folder:
        result.workers_removed = _delete_test_workers(
            session,
            tenant_id=tenant_id,
            company_id=company.id,
            keep_worker_ids=archive_worker_ids,
        )
    record_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="company_prl_archive.import",
        entity_type="company",
        entity_id=company.id,
        after=public_state(
            {
                "archive_path": archive_path.name,
                "files_seen": result.files_seen,
                "files_imported": result.files_imported,
                "workers_created": result.workers_created,
                "workers_removed": result.workers_removed,
                "documents_staged": result.documents_staged,
                "skipped": len(result.skipped),
            }
        ),
    )
    session.flush()
    return result


def classify_archive_member(logical_path: str, type_by_code: dict[str, DocumentType]) -> dict[str, str]:
    key = _norm(logical_path)
    worker_folder = _worker_folder_from_path(logical_path)
    scope = "worker" if worker_folder is not None else "company"
    if scope == "worker":
        code = _worker_document_type_code(key)
    else:
        code = _company_document_type_code(key)
    if code not in type_by_code:
        code = "ARM.WORKER.GENERAL_EVIDENCE" if scope == "worker" else "ARM.COMPANY.GENERAL_EVIDENCE"
    return {
        "scope": scope,
        "document_type_code": code,
        "worker_folder": worker_folder or "",
    }


def write_import_report(result: ArchiveImportResult, *, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = f"arm_prl_import_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    json_path = report_dir / f"{stem}.json"
    markdown_path = report_dir / f"{stem}.md"
    json_path.write_text(_result_json(result), encoding="utf-8")
    markdown_path.write_text(_result_markdown(result), encoding="utf-8")
    return json_path, markdown_path


def _iter_zip_files(
    archive_path: Path,
    *,
    max_depth: int,
    result: ArchiveImportResult,
) -> list[ArchiveFile]:
    members: list[ArchiveFile] = []

    def visit_zip(payload: Path | io.BytesIO, prefix: str, depth: int) -> None:
        try:
            with zipfile.ZipFile(payload) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename.replace("\\", "/").strip("/")
                    logical_path = f"{prefix}{name}" if prefix else name
                    extension = PurePosixPath(name).suffix.lower()
                    if extension in NESTED_ARCHIVE_EXTENSIONS and depth < max_depth:
                        result.nested_archives_seen += 1
                        visit_zip(io.BytesIO(archive.read(info)), f"{logical_path}/", depth + 1)
                        continue
                    members.append(
                        ArchiveFile(
                            logical_path=logical_path,
                            filename=PurePosixPath(name).name,
                            extension=extension,
                            content=archive.read(info),
                            depth=depth,
                        )
                    )
        except zipfile.BadZipFile:
            result.skipped.append({"path": prefix or str(archive_path), "reason": "bad_zip"})

    visit_zip(archive_path, "", 0)
    return members


def _extract_roster_by_name(members: list[ArchiveFile]) -> dict[str, WorkerRosterIdentity]:
    roster: dict[str, WorkerRosterIdentity] = {}
    for member in members:
        key = _norm(member.logical_path)
        if member.extension != ".docx" or "relacion personal dni ss" not in key:
            continue
        text = _extract_docx_text(member.content)
        for identity in _parse_roster_text(text):
            roster[_norm(f"{identity.first_name} {identity.last_name}")] = identity
    return roster


def _extract_docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except Exception:
        return ""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return ""
    values: list[str] = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            values.append(node.text)
    return " ".join(values)


def _parse_roster_text(text: str) -> list[WorkerRosterIdentity]:
    if not text:
        return []
    normalized_text = re.sub(r"\s+", " ", text).strip()
    row_pattern = re.compile(
        r"(?:^|\s)(\d{1,3})\s+(.+?)\s+(\d{2}/\d{2}/\d{4})\s+"
        r"((?:\d{8}[A-Za-z])|(?:[XYZ]\d{7}[A-Za-z]))\s+"
        r"(.+?)(?=\s+\d{1,3}\s+[A-ZÁÉÍÓÚÜÑ]|\Z)",
        flags=re.IGNORECASE,
    )
    rows: list[WorkerRosterIdentity] = []
    for match in row_pattern.finditer(normalized_text):
        raw_name = match.group(2).strip()
        identifier = normalize_worker_identifier(match.group(4))
        if not identifier:
            continue
        tail = match.group(5).strip()
        email = _extract_email(tail)
        phone = _extract_phone(tail)
        social_security = _extract_social_security(tail, phone=phone)
        first_name, last_name = _roster_name_to_first_last(raw_name)
        rows.append(
            WorkerRosterIdentity(
                first_name=first_name,
                last_name=last_name,
                identifier_value=identifier,
                email=email,
                phone=phone,
                social_security_number=social_security,
            )
        )
    return rows


def _match_roster_identity(
    worker_key: str,
    roster_by_name: dict[str, WorkerRosterIdentity],
) -> WorkerRosterIdentity | None:
    if worker_key in roster_by_name:
        return roster_by_name[worker_key]
    for key, identity in roster_by_name.items():
        if _same_worker_key(worker_key, key):
            return identity
    return None


def _roster_name_to_first_last(raw_name: str) -> tuple[str, str]:
    key = _norm(raw_name)
    if key in KNOWN_WORKER_FOLDERS:
        first_name, last_name, _ = KNOWN_WORKER_FOLDERS[key]
        return first_name, last_name
    for known_key, (first_name, last_name, _) in KNOWN_WORKER_FOLDERS.items():
        if _same_worker_key(key, known_key):
            return first_name, last_name
    tokens = _title_name(raw_name).split()
    if len(tokens) <= 1:
        return _title_name(raw_name), ""
    # Roster names are uppercase full names. The first one or two tokens are the
    # given name in this ARM source; the folder mapping above handles known exceptions.
    first_name = tokens[0]
    last_name = " ".join(tokens[1:])
    return first_name, last_name


def _extract_email(value: str) -> str | None:
    repaired = (
        value.replace(" @", "@")
        .replace("@ ", "@")
        .replace("- ", "-")
        .replace(" ,", ",")
        .replace(",com", ".com")
    )
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", repaired)
    return match.group(0).lower() if match else None


def _extract_phone(value: str) -> str | None:
    without_email = re.sub(r"[\w.+-]+\s*@\s*[\w.-]+\s*[,\.]\s*[A-Za-z]{2,}", " ", value)
    match = re.search(r"\b[6789]\d{8}\b", without_email)
    return match.group(0) if match else None


def _extract_social_security(value: str, *, phone: str | None) -> str | None:
    text = value
    if phone:
        text = text.replace(phone, " ")
    digits = re.findall(r"\d+", text)
    if not digits:
        return None
    compact = "".join(digits)
    if len(compact) >= 10:
        return compact[-12:] if len(compact) > 12 else compact
    return None


def _ensure_company(
    session: Session,
    *,
    tenant_id: int,
    company_tax_id: str,
    company_name: str,
) -> Company:
    company = session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.tax_id == company_tax_id)
    )
    if company is None:
        company = Company(
            tenant_id=tenant_id,
            name=company_name,
            tax_id=company_tax_id,
            company_type="own",
            status="active",
        )
        session.add(company)
        session.flush()
    company.name = company_name
    company.company_type = "own"
    company.status = "active"
    session.flush()
    return company


def _ensure_document_types(session: Session, *, tenant_id: int) -> dict[str, DocumentType]:
    by_code = {
        item.code: item
        for item in session.scalars(
            select(DocumentType).where(
                or_(DocumentType.tenant_id.is_(None), DocumentType.tenant_id == tenant_id)
            )
        )
    }
    for code, name, scope, requires_expiration in DOCUMENT_TYPE_SPECS:
        if code in by_code:
            continue
        document_type = DocumentType(
            tenant_id=tenant_id,
            code=code,
            name=name,
            entity_scope=scope,
            is_common_cae_type=False,
            requires_expiration=requires_expiration,
            retention_days=3650,
        )
        session.add(document_type)
        session.flush()
        by_code[code] = document_type
    return by_code


def _load_worker_index(session: Session, *, tenant_id: int, company_id: int) -> dict[str, Worker]:
    workers = list(
        session.scalars(
            select(Worker).where(Worker.tenant_id == tenant_id, Worker.company_id == company_id)
        )
    )
    return {_norm(f"{worker.first_name} {worker.last_name}"): worker for worker in workers}


def _load_worker_identifier_index(session: Session, *, tenant_id: int, company_id: int) -> dict[str, Worker]:
    workers = list(
        session.scalars(
            select(Worker).where(
                Worker.tenant_id == tenant_id,
                Worker.company_id == company_id,
                Worker.identifier_hash.is_not(None),
            )
        )
    )
    return {worker.identifier_hash: worker for worker in workers if worker.identifier_hash}


def _ensure_worker_from_folder(
    session: Session,
    *,
    tenant_id: int,
    company_id: int,
    folder: str,
    worker_by_name: dict[str, Worker],
    worker_by_identifier_hash: dict[str, Worker],
    roster_by_name: dict[str, WorkerRosterIdentity],
) -> tuple[Worker, bool, bool]:
    first_name, last_name, identifier_last4 = _worker_name_from_folder(folder)
    target_key = _norm(f"{first_name} {last_name}")
    roster = _match_roster_identity(target_key, roster_by_name)
    identifier_value = roster.identifier_value if roster is not None else None
    identifier_hash = worker_identifier_hash(identifier_value)
    worker = worker_by_identifier_hash.get(identifier_hash or "") if identifier_hash else None
    if worker is None:
        worker = worker_by_name.get(target_key)
    if worker is None:
        for key, candidate in worker_by_name.items():
            if _same_worker_key(key, target_key):
                worker = candidate
                break
    created = False
    updated = False
    if worker is None:
        worker = Worker(
            tenant_id=tenant_id,
            company_id=company_id,
            first_name=first_name,
            last_name=last_name,
            identifier_type="dni" if identifier_value or identifier_last4 else None,
            identifier_value=identifier_value,
            identifier_hash=identifier_hash,
            identifier_last4=identifier_last4 or (identifier_value[-4:] if identifier_value else None),
            employment_status="active",
            status="active",
        )
        session.add(worker)
        session.flush()
        created = True
    before = (
        worker.first_name,
        worker.last_name,
        worker.identifier_type,
        worker.identifier_value,
        worker.identifier_hash,
        worker.identifier_last4,
        worker.email,
        worker.phone,
        worker.social_security_number,
        worker.social_security_last4,
        worker.employment_status,
        worker.status,
    )
    worker.first_name = roster.first_name if roster is not None else first_name
    worker.last_name = roster.last_name if roster is not None else last_name
    if identifier_value:
        normalized_identifier = normalize_worker_identifier(identifier_value)
        worker.identifier_type = "dni"
        worker.identifier_value = normalized_identifier
        worker.identifier_hash = worker_identifier_hash(normalized_identifier)
        worker.identifier_last4 = normalized_identifier[-4:] if normalized_identifier else identifier_last4
    elif identifier_last4:
        worker.identifier_type = "dni"
        worker.identifier_last4 = identifier_last4
    if roster is not None:
        worker.email = roster.email or worker.email
        worker.phone = roster.phone or worker.phone
        worker.social_security_number = roster.social_security_number or worker.social_security_number
        if roster.social_security_number:
            worker.social_security_last4 = roster.social_security_number[-4:]
    worker.employment_status = "active"
    worker.status = "active"
    worker.cae_notes = (
        "Ficha ARM importada desde paquete PRL local. DNI/NIE usado como identidad unica "
        "cuando consta en relacion de personal; completar DNI si falta antes de escribir en plataformas."
    )
    after = (
        worker.first_name,
        worker.last_name,
        worker.identifier_type,
        worker.identifier_value,
        worker.identifier_hash,
        worker.identifier_last4,
        worker.email,
        worker.phone,
        worker.social_security_number,
        worker.social_security_last4,
        worker.employment_status,
        worker.status,
    )
    updated = before != after and not created
    worker_by_name[_norm(f"{worker.first_name} {worker.last_name}")] = worker
    if worker.identifier_hash:
        worker_by_identifier_hash[worker.identifier_hash] = worker
    session.flush()
    return worker, created, updated


def _ensure_intake(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    member: ArchiveFile,
    company: Company,
    worker: Worker | None,
    document_type: DocumentType,
    classification: dict[str, str],
    result: ArchiveImportResult,
) -> tuple[StoredFile | None, DocumentIntake | None, bool]:
    sha256 = hashlib.sha256(member.content).hexdigest()
    existing = session.scalar(
        select(DocumentIntake)
        .where(DocumentIntake.tenant_id == tenant_id, DocumentIntake.sha256 == sha256)
        .order_by(DocumentIntake.id)
    )
    issued_at, expires_at = _dates_from_path(member.logical_path, document_type=document_type)
    if existing is not None:
        _update_intake_target(
            existing,
            company=company,
            worker=worker,
            document_type=document_type,
            classification=classification,
            logical_path=member.logical_path,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        return None, existing, False

    try:
        stored = store_intake_bytes(
            member.content,
            tenant_id=tenant_id,
            filename=member.filename,
            mime_type=_mime_type(member.filename),
        )
    except StoredFileTooLarge:
        result.skipped.append({"path": member.logical_path, "reason": "file_too_large"})
        return None, None, False

    analysis = analyze_document_intake(session, tenant_id=tenant_id, stored_file=stored)
    intake = DocumentIntake(
        tenant_id=tenant_id,
        uploaded_by=actor_user_id,
        original_filename=member.filename,
        file_storage_key=stored.storage_key,
        sha256=stored.sha256,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        status="pending_review",
        intake_scope="single_worker" if worker is not None else "company",
        extraction_engine=analysis.extraction_engine,
        extracted_text_excerpt=analysis.extracted_text_excerpt,
        text_confidence=analysis.text_confidence,
        issued_at=issued_at or analysis.issued_at,
        expires_at=expires_at or analysis.expires_at,
        confidence=max(analysis.confidence, 75),
        classification_json=analysis.classification_json,
        signals_json=analysis.signals_json,
        target_notes="Importado desde paquete PRL ARM; validar antes de usar en plataformas externas.",
    )
    _update_intake_target(
        intake,
        company=company,
        worker=worker,
        document_type=document_type,
        classification=classification,
        logical_path=member.logical_path,
        issued_at=intake.issued_at,
        expires_at=intake.expires_at,
    )
    session.add(intake)
    session.flush()
    return stored, intake, True


def _update_intake_target(
    intake: DocumentIntake,
    *,
    company: Company,
    worker: Worker | None,
    document_type: DocumentType,
    classification: dict[str, str],
    logical_path: str,
    issued_at: date | None,
    expires_at: date | None,
) -> None:
    intake.requested_company_id = company.id
    intake.predicted_company_id = company.id
    intake.requested_worker_id = worker.id if worker is not None else None
    intake.predicted_worker_id = worker.id if worker is not None else None
    intake.predicted_entity_type = classification["scope"]
    intake.predicted_entity_id = worker.id if worker is not None else company.id
    intake.predicted_document_type_id = document_type.id
    intake.issued_at = issued_at
    intake.expires_at = expires_at
    intake.confidence = max(intake.confidence or 0, 78)
    intake.classification_json = {
        **(intake.classification_json or {}),
        "company_prl_archive": {
            "source": "archive_path_and_filename",
            "logical_path": logical_path,
            "document_type_code": document_type.code,
            "scope": classification["scope"],
            "worker_folder": classification.get("worker_folder") or None,
        },
    }
    intake.signals_json = {
        **(intake.signals_json or {}),
        "review_state": "pending_internal_review",
        "rgpd_minimization": "full_text_not_persisted_beyond_redacted_excerpt",
    }
    intake.review_comment = "Documento ARM importado; pendiente de validacion documental interna."
    intake.reviewed_at = None
    intake.updated_at = datetime.now(timezone.utc)


def _stage_document_version(
    session: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    intake: DocumentIntake,
    document_type: DocumentType,
    entity_type: str,
    entity_id: int,
) -> bool:
    document = session.scalar(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.document_type_id == document_type.id,
            Document.entity_type == entity_type,
            Document.entity_id == entity_id,
        )
    )
    if document is None:
        document = Document(
            tenant_id=tenant_id,
            document_type_id=document_type.id,
            entity_type=entity_type,
            entity_id=entity_id,
            status_internal="pending_internal_review",
        )
        session.add(document)
        session.flush()
    else:
        document.status_internal = "pending_internal_review"

    existing_version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.sha256 == intake.sha256,
        )
    )
    if existing_version is not None:
        document.current_version_id = existing_version.id
        intake.created_document_id = document.id
        intake.created_version_id = existing_version.id
        return False

    version_number = (
        session.scalar(
            select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document.id)
        )
        or 0
    ) + 1
    version = DocumentVersion(
        document_id=document.id,
        version_number=version_number,
        file_storage_key=intake.file_storage_key,
        sha256=intake.sha256,
        filename=intake.original_filename,
        mime_type=intake.mime_type,
        size_bytes=intake.size_bytes,
        issued_at=intake.issued_at,
        expires_at=intake.expires_at,
        expiry_review_status="review_required" if intake.expires_at else "ok",
        source="import",
        created_by=actor_user_id,
    )
    session.add(version)
    session.flush()
    document.current_version_id = version.id
    document.status_internal = "pending_internal_review"
    intake.created_document_id = document.id
    intake.created_version_id = version.id
    return True


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
    keep_workers = [worker for worker in candidates if worker.id in keep_worker_ids]
    duplicate_targets: dict[int, Worker] = {}
    for worker in candidates:
        if worker.id in keep_worker_ids:
            continue
        duplicate_target = _duplicate_target_for_worker(worker, keep_workers)
        if duplicate_target is not None:
            duplicate_targets[worker.id] = duplicate_target
    for source_worker_id, target_worker in duplicate_targets.items():
        _move_worker_references(session, source_worker_id=source_worker_id, target_worker=target_worker)
    delete_ids = [
        worker.id
        for worker in candidates
        if worker.id not in keep_worker_ids
        and (worker.id in duplicate_targets or _looks_like_non_archive_worker(worker))
    ]
    if not delete_ids:
        return 0
    duplicate_delete_ids = set(duplicate_targets)
    test_delete_ids = [worker_id for worker_id in delete_ids if worker_id not in duplicate_delete_ids]
    if duplicate_delete_ids:
        session.flush()
    if not test_delete_ids:
        session.execute(delete(Worker).where(Worker.id.in_(delete_ids)))
        session.flush()
        return len(delete_ids)
    document_ids = set(
        session.scalars(
            select(Document.id).where(
                Document.tenant_id == tenant_id,
                Document.entity_type == "worker",
                Document.entity_id.in_(test_delete_ids),
            )
        )
    )
    if document_ids:
        session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(document_ids)))
        session.execute(delete(Document).where(Document.id.in_(document_ids)))
    session.execute(delete(WorkerTraining).where(WorkerTraining.worker_id.in_(test_delete_ids)))
    session.execute(delete(WorkerWorkAssignment).where(WorkerWorkAssignment.worker_id.in_(test_delete_ids)))
    session.execute(delete(WorkerPlatformRegistration).where(WorkerPlatformRegistration.worker_id.in_(test_delete_ids)))
    for intake in session.scalars(
        select(DocumentIntake).where(
            DocumentIntake.tenant_id == tenant_id,
            or_(
                DocumentIntake.requested_worker_id.in_(test_delete_ids),
                DocumentIntake.predicted_worker_id.in_(test_delete_ids),
            ),
        )
    ):
        intake.requested_worker_id = None
        intake.predicted_worker_id = None
        if intake.predicted_entity_type == "worker" and intake.predicted_entity_id in test_delete_ids:
            intake.predicted_entity_type = None
            intake.predicted_entity_id = None
    session.execute(delete(Worker).where(Worker.id.in_(delete_ids)))
    session.flush()
    return len(delete_ids)


def _duplicate_target_for_worker(worker: Worker, keep_workers: list[Worker]) -> Worker | None:
    name = _norm(f"{worker.first_name} {worker.last_name}")
    for target in keep_workers:
        target_name = _norm(f"{target.first_name} {target.last_name}")
        if _same_worker_key(name, target_name):
            return target
    return None


def _move_worker_references(session: Session, *, source_worker_id: int, target_worker: Worker) -> None:
    for document in session.scalars(
        select(Document).where(Document.entity_type == "worker", Document.entity_id == source_worker_id)
    ):
        document.entity_id = target_worker.id
    for training in session.scalars(select(WorkerTraining).where(WorkerTraining.worker_id == source_worker_id)):
        training.worker_id = target_worker.id
    for assignment in session.scalars(select(WorkerWorkAssignment).where(WorkerWorkAssignment.worker_id == source_worker_id)):
        assignment.worker_id = target_worker.id
    for registration in session.scalars(
        select(WorkerPlatformRegistration).where(WorkerPlatformRegistration.worker_id == source_worker_id)
    ):
        registration.worker_id = target_worker.id
    for intake in session.scalars(
        select(DocumentIntake).where(
            or_(
                DocumentIntake.requested_worker_id == source_worker_id,
                DocumentIntake.predicted_worker_id == source_worker_id,
                DocumentIntake.predicted_entity_id == source_worker_id,
            )
        )
    ):
        if intake.requested_worker_id == source_worker_id:
            intake.requested_worker_id = target_worker.id
        if intake.predicted_worker_id == source_worker_id:
            intake.predicted_worker_id = target_worker.id
        if intake.predicted_entity_type == "worker" and intake.predicted_entity_id == source_worker_id:
            intake.predicted_entity_id = target_worker.id


def _looks_like_non_archive_worker(worker: Worker) -> bool:
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


def _worker_document_type_code(key: str) -> str:
    if any(token in key for token in ("dni", "nie", "pasaporte", "passport")):
        return "CAE.WORKER.ID_DOCUMENT"
    if "ta2" in key or "alta seguridad social" in key or re.search(r"\balta\b", key):
        return "ARM.WORKER.SOCIAL_SECURITY_REGISTRATION"
    if "prorroga" in key:
        return "ARM.WORKER.CONTRACT_EXTENSION"
    if "subrogacion" in key:
        return "ARM.WORKER.SUBROGATION"
    if "contrato" in key:
        return "ARM.WORKER.CONTRACT"
    if "situacion familiar" in key or "modelo 145" in key or "declaracion familiar" in key:
        return "ARM.WORKER.TAX_FAMILY_DECLARATION"
    if "renuncia" in key and ("vigilancia" in key or "reconocimiento" in key or "medico" in key):
        return "ARM.WORKER.MEDICAL_FITNESS_WAIVER"
    if any(token in key for token in ("apto", "reconocimiento medico", "reconocimiento med", "vigilancia salud")):
        return "CAE.WORKER.MEDICAL_FITNESS"
    if "epi" in key:
        return "CAE.WORKER.PPE_DELIVERY"
    if "art 19" in key or "art19" in key:
        return "CAE.WORKER.PRL_ART19"
    if "art 18" in key or "manual" in key or "riesgos" in key:
        return "CAE.WORKER.RISK_INFORMATION"
    if "50 h" in key or "50h" in key or "50 horas" in key:
        return "CAE.WORKER.PRL_50H_COURSE"
    if "60 horas" in key or "60horas" in key:
        return "ARM.WORKER.PRL_60H_COURSE"
    if "carretilla" in key:
        return "CAE.WORKER.FORKLIFT_TRAINING"
    if "plataforma" in key:
        return "CAE.WORKER.MEWP_TRAINING"
    if "puente grua" in key:
        return "CAE.WORKER.OVERHEAD_CRANE_TRAINING"
    if "altura" in key or "alturas" in key:
        return "CAE.WORKER.HEIGHT_WORKS_TRAINING"
    if "reciclaje" in key:
        return "CAE.WORKER.METAL_RECYCLING"
    if "metal" in key:
        return "CAE.WORKER.METAL_TRAINING"
    if "confidencialidad" in key or "confidecialidad" in key:
        return "ARM.WORKER.CLIENT_CONFIDENTIALITY"
    if any(token in key for token in ("cliente_f", "cliente_c", "sprilur", "sp ri", "cliente")):
        return "ARM.WORKER.CLIENT_INDUCTION"
    if "herramienta" in key or "maquina" in key:
        return "ARM.WORKER.TOOL_USE_AUTHORIZATION"
    if "foto" in key or "image" in key:
        return "ARM.WORKER.PHOTO"
    if "formacion" in key or "diploma" in key or "curso" in key:
        return "ARM.WORKER.TRAINING_EVIDENCE"
    if "documentacion personal" in key:
        return "ARM.WORKER.PERSONAL_RECORD"
    return "ARM.WORKER.GENERAL_EVIDENCE"


def _company_document_type_code(key: str) -> str:
    if "rlc" in key or "tc1" in key:
        return "CAE.COMPANY.RLC_TC1"
    if "rnt" in key or "tc2" in key:
        return "CAE.COMPANY.RNT_TC2"
    if "aeat" in key or "hacienda" in key or "tributaria" in key:
        return "CAE.COMPANY.AEAT_CLEARANCE"
    if "seguridad social" in key and "pago" not in key:
        return "CAE.COMPANY.SS_CLEARANCE"
    if re.search(r"\bita\b", key):
        return "CAE.COMPANY.ITA"
    if "pago salarios" in key:
        return "ARM.COMPANY.SALARY_PAYMENT_DECLARATION"
    if "pago seguros sociales" in key or ("seguros sociales" in key and "pago" in key):
        return "ARM.COMPANY.SOCIAL_SECURITY_PAYMENT"
    if "situacion censal" in key:
        return "ARM.COMPANY.CENSUS_CERTIFICATE"
    if "fremap" in key or "mutua" in key:
        return "ARM.COMPANY.MUTUA_CERTIFICATE"
    if "evaluacion de riesgos" in key:
        return "ARM.COMPANY.RISK_ASSESSMENT"
    if "plan de prevencion" in key:
        return "ARM.COMPANY.PREVENTION_PLAN"
    if "planificacion" in key:
        return "ARM.COMPANY.PREVENTIVE_ACTIVITY_PLANNING"
    if "quiron" in key or "contrato concierto" in key or "servicio prevencion" in key:
        return "ARM.COMPANY.SPA_CONTRACT"
    if "relacion personal" in key:
        return "ARM.COMPANY.WORKFORCE_RELATION"
    if "corriente de pago" in key:
        return "ARM.COMPANY.CURRENT_PAYMENT_CERTIFICATE"
    if "multiriesgo" in key:
        return "ARM.COMPANY.PROPERTY_POLICY"
    if "acc" in key or "accidente" in key:
        return "ARM.COMPANY.ACCIDENT_RECEIPT" if "recibo" in key else "ARM.COMPANY.ACCIDENT_POLICY"
    if "responsabilidad civil" in key or re.search(r"\brc\b", key):
        return "CAE.COMPANY.RC_RECEIPT" if "recibo" in key or "justificante" in key else "CAE.COMPANY.RC_POLICY"
    return "ARM.COMPANY.GENERAL_EVIDENCE"


def _worker_folder_from_path(logical_path: str) -> str | None:
    parts = [part for part in logical_path.replace("\\", "/").split("/") if part]
    for index, part in enumerate(parts[:-1]):
        if _norm(part) == "trabajadores":
            return parts[index + 1]
    return None


def _worker_name_from_folder(folder: str) -> tuple[str, str, str | None]:
    key = _norm(folder)
    if key in KNOWN_WORKER_FOLDERS:
        return KNOWN_WORKER_FOLDERS[key]
    if "," in folder:
        last, first = [part.strip() for part in folder.split(",", 1)]
        return _title_name(first), _title_name(last), None
    tokens = folder.split()
    if len(tokens) >= 2:
        return _title_name(tokens[-1]), _title_name(" ".join(tokens[:-1])), None
    return _title_name(folder), "", None


def _same_worker_key(existing: str, target: str) -> bool:
    existing_tokens = set(existing.split())
    target_tokens = set(target.split())
    common = existing_tokens & target_tokens
    return len(common) >= 2 or (len(common) == 1 and len(existing_tokens | target_tokens) <= 3)


def _dates_from_path(logical_path: str, *, document_type: DocumentType) -> tuple[date | None, date | None]:
    key = _norm(logical_path)
    parsed = [_parse_date(match.group(0)) for match in _date_matches(logical_path)]
    dates = [item for item in parsed if item is not None]
    if not dates:
        return None, None
    ordered = sorted(set(dates))
    if "hasta" in key or " al " in f" {key} " or "caduc" in key or document_type.requires_expiration:
        issued_at = ordered[0] if len(ordered) > 1 else None
        return issued_at, ordered[-1]
    if document_type.code == "CAE.WORKER.ID_DOCUMENT":
        return None, ordered[-1]
    return ordered[0], None


def _date_matches(value: str) -> list[re.Match[str]]:
    return list(re.finditer(r"\b\d{1,2}[-_.]\d{1,2}[-_.]\d{2,4}\b|\b\d{4}-\d{1,2}-\d{1,2}\b", value))


def _parse_date(value: str) -> date | None:
    cleaned = value.replace("_", "-").replace(".", "-")
    parts = cleaned.split("-")
    try:
        if len(parts[0]) == 4:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            if year < 100:
                year += 2000
        return date(year, month, day)
    except ValueError:
        return None


def _mime_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _title_name(value: str) -> str:
    particles = {"de", "del", "la", "las", "los", "y"}
    parts = []
    for token in _norm(value).split():
        parts.append(token if token in particles else token.capitalize())
    return " ".join(parts)


def _norm(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def _result_json(result: ArchiveImportResult) -> str:
    import json

    return json.dumps(
        {
            "archive_path": result.archive_path,
            "tenant_id": result.tenant_id,
            "company_id": result.company_id,
            "files_seen": result.files_seen,
            "files_imported": result.files_imported,
            "intakes_created": result.intakes_created,
            "intakes_reused": result.intakes_reused,
            "documents_staged": result.documents_staged,
            "versions_created": result.versions_created,
            "duplicate_versions": result.duplicate_versions,
            "workers_created": result.workers_created,
            "workers_updated": result.workers_updated,
            "workers_removed": result.workers_removed,
            "nested_archives_seen": result.nested_archives_seen,
            "by_scope": result.by_scope,
            "by_document_type": result.by_document_type,
            "by_worker": result.by_worker,
            "skipped": result.skipped,
        },
        ensure_ascii=False,
        indent=2,
    )


def _result_markdown(result: ArchiveImportResult) -> str:
    lines = [
        "# Importacion PRL ARM",
        "",
        f"- Archivo: `{result.archive_path}`",
        f"- Tenant: `{result.tenant_id}`",
        f"- Empresa: `{result.company_id}`",
        f"- Ficheros vistos: {result.files_seen}",
        f"- Ficheros importados: {result.files_imported}",
        f"- Intakes creados/reusados: {result.intakes_created}/{result.intakes_reused}",
        f"- Documentos preparados: {result.documents_staged}",
        f"- Versiones nuevas/duplicadas: {result.versions_created}/{result.duplicate_versions}",
        f"- Trabajadores creados/actualizados/eliminados de prueba: {result.workers_created}/{result.workers_updated}/{result.workers_removed}",
        f"- Omitidos: {len(result.skipped)}",
        "",
        "## Por trabajador",
    ]
    for worker, count in result.by_worker.items():
        lines.append(f"- {worker}: {count}")
    lines += ["", "## Por tipo documental"]
    for code, count in result.by_document_type.items():
        lines.append(f"- `{code}`: {count}")
    if result.skipped:
        lines += ["", "## Omitidos"]
        for item in result.skipped[:80]:
            lines.append(f"- `{item['path']}`: {item['reason']}")
    lines.append("")
    return "\n".join(lines)
