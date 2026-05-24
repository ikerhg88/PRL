from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Company, Document, DocumentIntake, DocumentVersion, Tenant, Worker
from app.services.company_prl_archive_import import import_company_prl_archive
from app.services.document_import_approval import approve_company_imported_documents
from app.services.ocr_intake import extract_text


def test_company_prl_archive_import_maps_workers_company_docs_and_docx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(tmp_path / "documents"))
    monkeypatch.setenv("IPRL_CAE_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024))
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    archive_path = tmp_path / "arm.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("ARM/PREVENCION/EVALUACION DE RIESGOS LABORALES 22-07-2025.pdf", b"%PDF-1.4\nrisk")
        archive.writestr(
            "ARM/Relacion personal DNI-SS ARM.docx",
            _docx_bytes(
                "RELACION DE PERSONAL TRABAJADOR F. NACIMIENTO DNI CORREO ELECTRONICO TELEFONO S. SOCIAL "
                "1 PEDRO JAVIER GARCIA 01/01/1980 12345678Z pedro@arm-assemblies.com 600111222 281234567812"
            ),
        )
        archive.writestr(
            "ARM/TRABAJADORES/GARCIA, PEDRO JAVIER/DOCUMENTACION PLATAFORMAS/Pedro Javier_EPIS 10-11-2025.pdf",
            b"%PDF-1.4\nepi",
        )
        archive.writestr(
            "ARM/TRABAJADORES/GLZ. DE S.ROMAN FDZ, ELENA/DOCUMENTACION PERSONAL/DNI ELENA 21-07-2031.pdf",
            b"%PDF-1.4\ndni",
        )
        archive.writestr("ARM/cache/thumbs.db", b"ignored")

    with SessionLocal() as session:
        tenant = Tenant(name="Tenant", tax_id="T1", status="active")
        session.add(tenant)
        session.flush()
        result = import_company_prl_archive(
            session,
            archive_path=archive_path,
            tenant_id=tenant.id,
            actor_user_id=None,
        )
        session.commit()

        assert result.files_seen == 5
        assert result.files_imported == 4
        assert result.workers_created == 2
        assert any(item["reason"].startswith("unsupported:.db") for item in result.skipped)
        assert result.by_document_type["ARM.COMPANY.RISK_ASSESSMENT"] == 1
        assert result.by_document_type["CAE.WORKER.PPE_DELIVERY"] == 1
        assert result.by_document_type["CAE.WORKER.ID_DOCUMENT"] == 1
        assert result.by_document_type["ARM.COMPANY.WORKFORCE_RELATION"] == 1

        company = session.scalar(select(Company).where(Company.tax_id == "B95868543"))
        assert company is not None
        workers = list(session.scalars(select(Worker).order_by(Worker.first_name)))
        assert [(worker.first_name, worker.last_name) for worker in workers] == [
            ("Elena", "Gonzalez de San Roman Fernandez"),
            ("Pedro Javier", "Garcia"),
        ]
        pedro = next(worker for worker in workers if worker.first_name == "Pedro Javier")
        assert pedro.identifier_value == "12345678Z"
        assert pedro.identifier_hash is not None
        assert pedro.identifier_last4 == "678Z"
        assert pedro.email == "pedro@arm-assemblies.com"
        assert pedro.phone == "600111222"
        assert pedro.social_security_number == "281234567812"
        documents = list(session.scalars(select(Document)))
        versions = list(session.scalars(select(DocumentVersion)))
        intakes = list(session.scalars(select(DocumentIntake)))
        assert len(documents) == 4
        assert len(versions) == 4
        assert len(intakes) == 4
        assert {item.status for item in intakes} == {"pending_review"}
        assert {item.status_internal for item in documents} == {"pending_internal_review"}

        approval = approve_company_imported_documents(
            session,
            tenant_id=tenant.id,
            company_tax_id="B95868543",
            actor_user_id=None,
            review_comment="Aprobado por instruccion de prueba.",
        )
        session.commit()
        assert approval.documents_approved == 4
        assert approval.intakes_accepted == 4
        assert {item.status for item in intakes} == {"accepted"}
        assert {item.status_internal for item in documents} == {"valid_internal"}


def test_extract_text_supports_docx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(tmp_path / "documents"))
    get_settings.cache_clear()
    docx_path = tmp_path / "relation.docx"
    docx_path.write_bytes(_docx_bytes("Trabajador ARM"))
    extracted = extract_text(
        docx_path,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert extracted.engine == "docx-xml-text"
    assert "Trabajador ARM" in extracted.text


def test_company_only_archive_does_not_remove_existing_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(tmp_path / "documents"))
    monkeypatch.setenv("IPRL_CAE_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024))
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    archive_path = tmp_path / "arm-company-only.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("ARM/DOCUMENTACION MENSUAL/2026/Enero/Assemblies RLC.pdf", b"%PDF-1.4\nrlc")

    with SessionLocal() as session:
        tenant = Tenant(name="Tenant", tax_id="T1", status="active")
        session.add(tenant)
        session.flush()
        company = Company(
            tenant_id=tenant.id,
            name="ARM Industrial Assemblies, S.L.",
            tax_id="B95868543",
            company_type="own",
            status="active",
        )
        session.add(company)
        session.flush()
        worker = Worker(
            tenant_id=tenant.id,
            company_id=company.id,
            first_name="Eleder",
            last_name="Gomez",
            status="active",
            employment_status="active",
        )
        session.add(worker)
        session.flush()

        result = import_company_prl_archive(
            session,
            archive_path=archive_path,
            tenant_id=tenant.id,
            actor_user_id=None,
        )
        session.commit()

        assert result.workers_removed == 0
        workers = list(session.scalars(select(Worker).order_by(Worker.id)))
        assert [(item.first_name, item.last_name) for item in workers] == [("Eleder", "Gomez")]


def _docx_bytes(text: str) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(
            "word/document.xml",
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
            ),
        )
    return payload.getvalue()
