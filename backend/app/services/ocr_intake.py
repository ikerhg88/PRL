from __future__ import annotations

import re
import os
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.etree import ElementTree
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Company, DocumentType, Worker
from app.services.document_storage import StoredFile
from app.services.worker_identity import normalize_worker_identifier

MAX_EXTRACTED_CHARS = 80_000
MAX_EXCERPT_CHARS = 1_200


@dataclass(frozen=True)
class ExtractedText:
    text: str
    engine: str
    confidence: int
    warnings: list[str]


@dataclass(frozen=True)
class IntakeAnalysis:
    extraction_engine: str
    extracted_text_excerpt: str
    text_confidence: int
    predicted_document_type_id: int | None
    predicted_entity_type: str | None
    predicted_entity_id: int | None
    predicted_company_id: int | None
    predicted_worker_id: int | None
    issued_at: date | None
    expires_at: date | None
    confidence: int
    classification_json: dict[str, Any]
    signals_json: dict[str, Any]


DOCUMENT_TYPE_RULES: dict[str, list[str]] = {
    "CAE.COMPANY.RC_POLICY": ["responsabilidad civil", "poliza", "póliza", "seguro rc"],
    "CAE.COMPANY.RC_RECEIPT": ["recibo responsabilidad civil", "recibo rc", "prima", "justificante"],
    "CAE.COMPANY.AEAT_CLEARANCE": ["aeat", "agencia tributaria", "corriente obligaciones tributarias"],
    "CAE.COMPANY.SS_CLEARANCE": ["seguridad social", "tesoreria general", "corriente obligaciones seguridad social"],
    "CAE.COMPANY.RLC_TC1": ["rlc", "tc1", "recibo liquidacion cotizaciones"],
    "CAE.COMPANY.RNT_TC2": ["rnt", "tc2", "relacion nominal trabajadores"],
    "CAE.COMPANY.ITA": ["informe de trabajadores en alta", "ita", "trabajadores en alta"],
    "CAE.WORKER.ID_DOCUMENT": ["dni", "nie", "pasaporte", "documento nacional de identidad"],
    "CAE.WORKER.MEDICAL_FITNESS": [
        "certificado de aptitud",
        "aptitud laboral",
        "apto",
        "vigilancia de la salud",
        "reconocimiento medico",
        "reconocimiento médico",
    ],
    "CAE.WORKER.PPE_DELIVERY": ["entrega de epis", "equipos de proteccion individual", "epi"],
    "CAE.WORKER.BASIC_PRL_COURSE": [
        "curso basico prl",
        "curso básico prl",
        "formacion prl",
        "formación prl",
        "prevencion de riesgos laborales",
        "prevención de riesgos laborales",
    ],
    "CAE.WORKER.RISK_INFORMATION": ["informacion de riesgos", "información de riesgos", "riesgos del puesto"],
}


def analyze_document_intake(
    session: Session,
    *,
    tenant_id: int,
    stored_file: StoredFile,
) -> IntakeAnalysis:
    extraction = extract_text(stored_file.path, mime_type=stored_file.mime_type)
    normalized_text = _normalize(extraction.text)
    document_match = _match_document_type(session, tenant_id=tenant_id, normalized_text=normalized_text)
    worker_match = _match_worker(session, tenant_id=tenant_id, normalized_text=normalized_text)
    company_match = _match_company(session, tenant_id=tenant_id, normalized_text=normalized_text)
    issued_at, expires_at, date_signals = _extract_dates(normalized_text)
    predicted_document_type = document_match["document_type"]
    if predicted_document_type is not None and not predicted_document_type.requires_expiration:
        expires_at = None

    predicted_document_type_id = predicted_document_type.id if predicted_document_type is not None else None
    predicted_entity_type = None
    predicted_entity_id = None
    predicted_worker_id = worker_match["worker_id"]
    predicted_company_id = company_match["company_id"]

    if predicted_document_type is not None:
        if predicted_document_type.entity_scope == "worker" and predicted_worker_id is not None:
            predicted_entity_type = "worker"
            predicted_entity_id = predicted_worker_id
            predicted_company_id = worker_match["company_id"]
        elif predicted_document_type.entity_scope == "company" and predicted_company_id is not None:
            predicted_entity_type = "company"
            predicted_entity_id = predicted_company_id

    confidence = _overall_confidence(
        text_confidence=extraction.confidence,
        document_score=int(document_match["score"]),
        entity_score=max(int(worker_match["score"]), int(company_match["score"])),
        has_entity=predicted_entity_id is not None,
    )
    classification_json = {
        "document": {
            "code": predicted_document_type.code if predicted_document_type is not None else None,
            "name": predicted_document_type.name if predicted_document_type is not None else None,
            "score": document_match["score"],
            "reasons": document_match["reasons"],
        },
        "worker": worker_match,
        "company": company_match,
        "dates": date_signals,
        "warnings": extraction.warnings + _risk_warnings(predicted_document_type, confidence),
    }
    signals_json = {
        "sha256": stored_file.sha256,
        "filename": stored_file.filename,
        "mime_type": stored_file.mime_type,
        "text_length": len(extraction.text),
        "contains_medical_fitness_terms": bool(
            re.search(r"\b(apto|no apto|vigilancia de la salud|reconocimiento medico)\b", normalized_text)
        ),
    }
    return IntakeAnalysis(
        extraction_engine=extraction.engine,
        extracted_text_excerpt=_redacted_excerpt(extraction.text),
        text_confidence=extraction.confidence,
        predicted_document_type_id=predicted_document_type_id,
        predicted_entity_type=predicted_entity_type,
        predicted_entity_id=predicted_entity_id,
        predicted_company_id=predicted_company_id,
        predicted_worker_id=predicted_worker_id,
        issued_at=issued_at,
        expires_at=expires_at,
        confidence=confidence,
        classification_json=classification_json,
        signals_json=signals_json,
    )


def extract_text(path: Path, *, mime_type: str) -> ExtractedText:
    suffix = path.suffix.lower()
    warnings: list[str] = []
    if mime_type.startswith("text/") or suffix in {".txt", ".csv", ".md"}:
        return ExtractedText(
            text=_read_text_file(path),
            engine="text-direct",
            confidence=95,
            warnings=[],
        )
    if mime_type == "application/pdf" or suffix == ".pdf":
        text = _extract_pdf_text(path, warnings)
        confidence = 88 if text.strip() else 0
        if not text.strip():
            warnings.append("No text layer found. Install OCRmyPDF/Tesseract pipeline for scanned PDFs.")
        return ExtractedText(text=text, engine="pypdf-text-layer", confidence=confidence, warnings=warnings)
    if (
        mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or suffix == ".docx"
    ):
        text = _extract_docx_text(path, warnings)
        confidence = 88 if text.strip() else 0
        return ExtractedText(text=text, engine="docx-xml-text", confidence=confidence, warnings=warnings)
    if mime_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        text = _extract_image_ocr(path, warnings)
        confidence = 72 if text.strip() else 0
        return ExtractedText(text=text, engine="tesseract-image-ocr", confidence=confidence, warnings=warnings)
    warnings.append(f"Unsupported OCR mime type: {mime_type}")
    return ExtractedText(text="", engine="unsupported", confidence=0, warnings=warnings)


def _extract_pdf_text(path: Path, warnings: list[str]) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - dependency should exist in normal installs
        warnings.append(f"pypdf unavailable: {exc.__class__.__name__}")
        return ""
    try:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
            if sum(len(item) for item in pages) > MAX_EXTRACTED_CHARS:
                break
        return "\n".join(pages)[:MAX_EXTRACTED_CHARS]
    except Exception as exc:
        warnings.append(f"PDF text extraction failed: {exc.__class__.__name__}")
        return ""


def _extract_image_ocr(path: Path, warnings: list[str]) -> str:
    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:  # pragma: no cover - optional runtime path
        warnings.append(f"Tesseract OCR unavailable: {exc.__class__.__name__}")
        return ""
    try:
        tesseract_cmd = _resolve_tesseract_cmd()
        if tesseract_cmd is not None:
            pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)
        with Image.open(path) as image:
            return str(pytesseract.image_to_string(image, lang="spa+eng"))[:MAX_EXTRACTED_CHARS]
    except Exception as exc:
        warnings.append(f"Tesseract OCR failed: {exc.__class__.__name__}")
        return ""


def _extract_docx_text(path: Path, warnings: list[str]) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
    except Exception as exc:
        warnings.append(f"DOCX text extraction failed: {exc.__class__.__name__}")
        return ""
    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as exc:
        warnings.append(f"DOCX XML parse failed: {exc.__class__.__name__}")
        return ""
    text_parts: list[str] = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            text_parts.append(node.text)
        if sum(len(item) for item in text_parts) > MAX_EXTRACTED_CHARS:
            break
    return "\n".join(text_parts)[:MAX_EXTRACTED_CHARS]


def _resolve_tesseract_cmd() -> Path | None:
    configured = os.getenv("TESSERACT_CMD")
    if configured:
        configured_path = Path(configured)
        if configured_path.exists():
            _configure_tessdata(configured_path)
            return configured_path

    user_profile = os.getenv("USERPROFILE")
    portable_tesseract = (
        Path(user_profile) / "AppData/Local/AlbaranesParserPortable/external_bin/tesseract/tesseract.exe"
        if user_profile
        else None
    )
    candidates = [
        shutil.which("tesseract"),
        "C:/Program Files/Tesseract-OCR/tesseract.exe",
        "C:/Program Files (x86)/Tesseract-OCR/tesseract.exe",
        portable_tesseract,
        "C:/Program Files/PDF24/tesseract/tesseract.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists() and _configure_tessdata(path):
            return path
    return None


def _configure_tessdata(tesseract_cmd: Path) -> bool:
    configured_tessdata = os.getenv("TESSDATA_PREFIX")
    if configured_tessdata and Path(configured_tessdata).exists():
        return True

    tessdata = tesseract_cmd.parent / "tessdata"
    if (tessdata / "spa.traineddata").exists() or (tessdata / "eng.traineddata").exists():
        os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))
        return True
    return False


def _match_document_type(session: Session, *, tenant_id: int, normalized_text: str) -> dict[str, Any]:
    document_types = list(
        session.scalars(
            select(DocumentType)
            .where(or_(DocumentType.tenant_id.is_(None), DocumentType.tenant_id == tenant_id))
            .order_by(DocumentType.id)
        )
    )
    best: DocumentType | None = None
    best_score = 0
    best_reasons: list[str] = []
    for document_type in document_types:
        score = 0
        reasons: list[str] = []
        rule_terms = DOCUMENT_TYPE_RULES.get(document_type.code, [])
        for term in rule_terms:
            if _normalize(term) in normalized_text:
                score += 24
                reasons.append(term)
        for token in _significant_tokens(document_type.name):
            if token in normalized_text:
                score += 8
        if document_type.code.lower().replace(".", " ") in normalized_text:
            score += 30
            reasons.append(document_type.code)
        score = min(score, 100)
        if score > best_score:
            best = document_type
            best_score = score
            best_reasons = reasons[:6]
    if best_score < 25:
        return {"document_type": None, "score": best_score, "reasons": best_reasons}
    return {"document_type": best, "score": best_score, "reasons": best_reasons}


def _match_worker(session: Session, *, tenant_id: int, normalized_text: str) -> dict[str, Any]:
    best_worker: Worker | None = None
    best_score = 0
    reasons: list[str] = []
    compact_text = re.sub(r"[^a-z0-9]+", "", normalized_text)
    workers = list(session.scalars(select(Worker).where(Worker.tenant_id == tenant_id, Worker.status == "active")))
    for worker in workers:
        score = 0
        local_reasons: list[str] = []
        worker_identifier = normalize_worker_identifier(worker.identifier_value)
        if worker_identifier and worker_identifier.lower() in compact_text:
            score += 92
            local_reasons.append("identifier_value")
        full_name = _normalize(f"{worker.first_name} {worker.last_name}")
        name_tokens = _significant_tokens(full_name)
        matched = [token for token in name_tokens if token in normalized_text]
        if matched:
            score += min(60, len(matched) * 22)
            local_reasons.append("name_tokens")
        if len(name_tokens) >= 2 and full_name in normalized_text:
            score += 25
            local_reasons.append("full_name")
        if worker.identifier_last4 and re.search(rf"\b{re.escape(worker.identifier_last4)}\b", normalized_text):
            score += 18
            local_reasons.append("identifier_last4")
        score = min(score, 100)
        if score > best_score:
            best_worker = worker
            best_score = score
            reasons = local_reasons
    if best_worker is None or best_score < 40:
        return {"worker_id": None, "company_id": None, "score": best_score, "reasons": reasons}
    return {
        "worker_id": best_worker.id,
        "company_id": best_worker.company_id,
        "score": best_score,
        "reasons": reasons,
    }


def _match_company(session: Session, *, tenant_id: int, normalized_text: str) -> dict[str, Any]:
    best_company: Company | None = None
    best_score = 0
    reasons: list[str] = []
    companies = list(session.scalars(select(Company).where(Company.tenant_id == tenant_id)))
    for company in companies:
        score = 0
        local_reasons: list[str] = []
        if company.tax_id and _normalize(company.tax_id) in normalized_text:
            score += 75
            local_reasons.append("tax_id")
        name_tokens = _significant_tokens(company.name)
        matched = [token for token in name_tokens if token in normalized_text]
        if matched:
            score += min(55, len(matched) * 18)
            local_reasons.append("company_name")
        score = min(score, 100)
        if score > best_score:
            best_company = company
            best_score = score
            reasons = local_reasons
    if best_company is None or best_score < 35:
        return {"company_id": None, "score": best_score, "reasons": reasons}
    return {"company_id": best_company.id, "score": best_score, "reasons": reasons}


def _extract_dates(normalized_text: str) -> tuple[date | None, date | None, dict[str, Any]]:
    dates = [_parse_date(match.group(0)) for match in re.finditer(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", normalized_text)]
    dates += [_parse_date(match.group(0)) for match in re.finditer(r"\b\d{4}-\d{1,2}-\d{1,2}\b", normalized_text)]
    parsed = [item for item in dates if item is not None]
    issued = _date_after_keyword(normalized_text, ["emision", "emisión", "expedicion", "fecha"])
    expires = _date_after_keyword(normalized_text, ["caducidad", "validez", "vence", "hasta"])
    if expires is None and len(parsed) == 1:
        expires = parsed[0]
    if issued is None and expires is not None:
        before_expiry = [item for item in parsed if item != expires and item < expires]
        issued = min(before_expiry) if before_expiry else None
    return issued, expires, {"detected_dates": [item.isoformat() for item in sorted(set(parsed))]}


def _date_after_keyword(normalized_text: str, keywords: list[str]) -> date | None:
    for keyword in keywords:
        pattern = rf"{keyword}.{{0,40}}?(\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{4}}-\d{{1,2}}-\d{{1,2}})"
        match = re.search(pattern, normalized_text)
        if match:
            return _parse_date(match.group(1))
    return None


def _parse_date(value: str) -> date | None:
    parts = re.split(r"[/-]", value)
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


def _overall_confidence(*, text_confidence: int, document_score: int, entity_score: int, has_entity: bool) -> int:
    value = int((text_confidence * 0.25) + (document_score * 0.40) + (entity_score * 0.35))
    if not has_entity:
        value = min(value, 62)
    return max(0, min(100, value))


def _risk_warnings(document_type: DocumentType | None, confidence: int) -> list[str]:
    warnings: list[str] = []
    if confidence < 75:
        warnings.append("Human review required before creating a document version.")
    if document_type is not None and document_type.code == "CAE.WORKER.MEDICAL_FITNESS":
        warnings.append("Medical fitness detected: store only fitness status, dates and minimum evidence.")
    return warnings


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()[: MAX_EXTRACTED_CHARS * 2]
    for encoding in ["utf-8", "latin-1"]:
        try:
            return raw.decode(encoding, errors="ignore")[:MAX_EXTRACTED_CHARS]
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")[:MAX_EXTRACTED_CHARS]


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_marks.lower()).strip()


def _significant_tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]{3,}", _normalize(value)) if token not in {"para", "con", "del", "los", "las"}]


def _redacted_excerpt(text: str) -> str:
    excerpt = text[:MAX_EXCERPT_CHARS]
    excerpt = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email]", excerpt)
    excerpt = re.sub(r"\b\d{8}[A-Za-z]\b", "[id]", excerpt)
    excerpt = re.sub(r"\b[XYZ]\d{7}[A-Za-z]\b", "[id]", excerpt, flags=re.IGNORECASE)
    excerpt = re.sub(r"\b\d{9,}\b", "[number]", excerpt)
    return excerpt
