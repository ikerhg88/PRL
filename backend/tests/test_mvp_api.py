from __future__ import annotations

import hashlib
from datetime import date, timedelta
from io import BytesIO
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

from fastapi.testclient import TestClient


_tenant_counter = 0


def _tenant_admin(client: TestClient, name: str, tax_id: str | None = None) -> tuple[dict[str, object], dict[str, str]]:
    global _tenant_counter
    _tenant_counter += 1
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"admin-{_tenant_counter}@example.invalid",
            "name": f"Admin {_tenant_counter}",
            "password": "DemoPassword123!",
            "tenant_name": name,
            "tenant_tax_id": tax_id,
        },
    )
    assert response.status_code == 201
    signup = response.json()
    verify = client.post("/api/v1/auth/verify-email", json={"token": signup["dev_verification_token"]})
    assert verify.status_code == 200
    session = verify.json()
    headers = {
        "Authorization": f"Bearer {session['access_token']}",
        "X-Tenant-ID": str(session["tenant_id"]),
    }
    return {"id": session["tenant_id"], "name": name, "tax_id": tax_id}, headers


def test_company_worker_document_requirement_flow(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "IKER Demo", "A00000000")

    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "Contrata Demo", "tax_id": "B00000000", "company_type": "contractor"},
    ).json()
    worker = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Ana",
            "last_name": "Lopez",
            "identifier_type": "dni",
            "identifier_value": "00000387L",
            "identifier_hash": "hash-redacted",
            "identifier_last4": "1234",
            "identifier_expires_at": (date.today() + timedelta(days=365)).isoformat(),
            "social_security_number": "280000000000",
            "social_security_last4": "7788",
            "contract_type": "indefinido",
            "starts_at": date.today().isoformat(),
            "work_position": "Tecnico PRL",
            "work_center_name": "Obra Demo",
            "risk_profile": "medium",
            "medical_fitness_status": "apto",
            "medical_fitness_issued_at": date.today().isoformat(),
            "medical_fitness_expires_at": (date.today() + timedelta(days=300)).isoformat(),
            "medical_fitness_provider": "Servicio PRL",
        },
    ).json()
    assert worker["identifier_value"] == "00000387L"
    assert worker["identifier_last4"] == "1234"
    assert worker["social_security_number"] == "280000000000"
    assert worker["social_security_last4"] == "7788"
    training = client.post(
        f"/api/v1/workers/{worker['id']}/trainings",
        headers=headers,
        json={
            "course_code": "CAE.WORKER.BASIC_PRL_COURSE",
            "course_name": "Curso basico PRL 60h",
            "provider": "IPRL Formacion",
            "hours": 60,
            "issued_at": date.today().isoformat(),
            "expires_at": (date.today() + timedelta(days=365)).isoformat(),
        },
    ).json()
    assert training["worker_id"] == worker["id"]
    assert training["course_name"] == "Curso basico PRL 60h"
    document_type = client.post(
        "/api/v1/document-types",
        headers=headers,
        json={
            "code": "CAE.WORKER.BASIC_PRL_COURSE",
            "name": "Curso basico PRL",
            "entity_scope": "worker",
            "requires_expiration": False,
        },
    ).json()
    document = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_type": "worker",
            "entity_id": worker["id"],
        },
    ).json()
    version = client.post(
        f"/api/v1/documents/{document['id']}/versions",
        headers=headers,
        json={
            "file_storage_key": "local://documents/course.pdf",
            "sha256": "a" * 64,
            "filename": "course.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 1024,
            "issued_at": date.today().isoformat(),
            "source": "manual",
        },
    ).json()
    assert version["version_number"] == 1

    profile = client.post(
        "/api/v1/requirements/profiles",
        headers=headers,
        json={"name": "Perfil obra demo", "risk_level": "medium"},
    ).json()
    created_requirement = client.post(
        f"/api/v1/requirements/profiles/{profile['id']}/requirements",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_scope": "worker",
            "expiration_warning_days": 30,
        },
    ).json()
    listed_requirements = client.get(
        f"/api/v1/requirements/profiles/{profile['id']}/requirements",
        headers=headers,
    ).json()
    assert [item["id"] for item in listed_requirements] == [created_requirement["id"]]
    compliance = client.get(
        f"/api/v1/requirements/profiles/{profile['id']}/compliance/worker/{worker['id']}",
        headers=headers,
    ).json()

    assert compliance["overall_status"] == "compliant"
    assert compliance["valid_count"] == 1
    assert compliance["items"][0]["document_version_id"] == version["id"]

    audit = client.get("/api/v1/audit", headers=headers).json()
    assert {entry["action"] for entry in audit} >= {
        "company.create",
        "worker.create",
        "document_version.create",
    }
    assert "hash-redacted" not in str(audit)


def test_worker_dni_is_unique_within_company(client: TestClient) -> None:
    _, headers = _tenant_admin(client, "DNI Unico", "A11111111")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "ARM", "tax_id": "B95868543", "company_type": "own"},
    ).json()
    first = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Ana",
            "last_name": "Lopez",
            "identifier_type": "dni",
            "identifier_value": " 00000000-t ",
        },
    )
    assert first.status_code == 201
    assert first.json()["identifier_value"] == "00000000T"
    assert first.json()["identifier_last4"] == "000T"

    duplicate = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Ana Segunda",
            "last_name": "Lopez",
            "identifier_type": "dni",
            "identifier_value": "00000000T",
        },
    )
    assert duplicate.status_code == 409

    second = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Luis",
            "last_name": "Perez",
            "identifier_type": "dni",
            "identifier_value": "44444444A",
        },
    )
    assert second.status_code == 201
    conflict = client.put(
        f"/api/v1/workers/{second.json()['id']}",
        headers=headers,
        json={"identifier_value": "00000000T"},
    )
    assert conflict.status_code == 409


def test_expiring_document_is_warning(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant Warning")
    company = client.post("/api/v1/companies", headers=headers, json={"name": "Empresa"}).json()
    worker = client.post(
        "/api/v1/workers",
        headers=headers,
        json={"company_id": company["id"], "first_name": "Luis", "last_name": "Garcia"},
    ).json()
    document_type = client.post(
        "/api/v1/document-types",
        headers=headers,
        json={
            "code": "CAE.WORKER.MEDICAL_FITNESS",
            "name": "Aptitud laboral",
            "entity_scope": "worker",
            "requires_expiration": True,
        },
    ).json()
    document = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_type": "worker",
            "entity_id": worker["id"],
        },
    ).json()
    client.post(
        f"/api/v1/documents/{document['id']}/versions",
        headers=headers,
        json={
            "file_storage_key": "local://documents/aptitud.pdf",
            "sha256": "b" * 64,
            "filename": "aptitud.pdf",
            "expires_at": (date.today() + timedelta(days=10)).isoformat(),
        },
    )
    profile = client.post("/api/v1/requirements/profiles", headers=headers, json={"name": "Perfil"}).json()
    client.post(
        f"/api/v1/requirements/profiles/{profile['id']}/requirements",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_scope": "worker",
            "expiration_warning_days": 30,
        },
    )

    compliance = client.get(
        f"/api/v1/requirements/profiles/{profile['id']}/compliance/worker/{worker['id']}",
        headers=headers,
    ).json()

    assert compliance["overall_status"] == "warning"
    assert compliance["expiring_soon_count"] == 1


def test_worker_manual_delete_bulk_import_erp_and_profile_links(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant Trabajadores")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "Empresa Trabajadores", "tax_id": "B55555555", "company_type": "contractor"},
    ).json()
    worker = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Manual",
            "last_name": "Completo",
            "identifier_type": "dni",
            "identifier_value": "44444444A",
            "social_security_number": "281111222233",
            "work_position": "Oficial",
        },
    ).json()
    assert worker["identifier_value"] == "44444444A"
    assert worker["social_security_number"] == "281111222233"
    updated_worker = client.put(
        f"/api/v1/workers/{worker['id']}",
        headers=headers,
        json={
            "email": "manual@example.invalid",
            "phone": "+34999000111",
            "medical_fitness_status": "apto",
            "medical_fitness_expires_at": (date.today() + timedelta(days=180)).isoformat(),
        },
    ).json()
    assert updated_worker["email"] == "manual@example.invalid"
    assert updated_worker["medical_fitness_status"] == "apto"

    assignment = client.post(
        f"/api/v1/workers/{worker['id']}/work-assignments",
        headers=headers,
        json={
            "work_name": "Obra Manual",
            "client_company_name": "Hondaemo",
            "role": "Oficial",
            "status": "active",
        },
    ).json()
    platform_overview = client.get("/api/v1/tenant-platforms/access", headers=headers).json()
    platform = next(item for item in platform_overview if item["platform_key"] == "mock_cae")
    registration = client.post(
        f"/api/v1/workers/{worker['id']}/platform-registrations",
        headers=headers,
        json={
            "external_platform_id": platform["id"],
            "platform_name": platform["name"],
            "external_worker_id": "EXT-44444444A",
            "registration_status": "accepted",
            "assignment_scope": "Obra Manual",
        },
    ).json()

    assert assignment["work_name"] == "Obra Manual"
    assert registration["registration_status"] == "accepted"
    assignment = client.put(
        f"/api/v1/workers/{worker['id']}/work-assignments/{assignment['id']}",
        headers=headers,
        json={
            "work_name": "Obra Manual Revisada",
            "client_company_name": "Hondaemo",
            "role": "Recurso preventivo",
            "status": "active",
        },
    ).json()
    registration = client.put(
        f"/api/v1/workers/{worker['id']}/platform-registrations/{registration['id']}",
        headers=headers,
        json={
            "external_platform_id": platform["id"],
            "platform_name": platform["name"],
            "external_worker_id": "EXT-44444444A",
            "registration_status": "review_required",
            "assignment_scope": "Obra Manual Revisada",
        },
    ).json()
    assert assignment["role"] == "Recurso preventivo"
    assert registration["registration_status"] == "review_required"
    assert (
        client.get(f"/api/v1/workers/{worker['id']}/work-assignments", headers=headers).json()[0]["work_name"]
        == "Obra Manual Revisada"
    )
    assert (
        client.get(f"/api/v1/workers/{worker['id']}/platform-registrations", headers=headers).json()[0]["platform_name"]
        == "Plataforma Mock CAE"
    )

    csv_content = (
        "company_id,first_name,last_name,dni,naf,puesto,obra\n"
        f"{company['id']},CSV,Uno,22222222J,281122334455,Operario,Obra CSV\n"
        f"{company['id']},CSV,Dos,33333333P,282233445566,Encargado,Obra CSV\n"
    ).encode()
    bulk = client.post(
        "/api/v1/workers/bulk-upload",
        headers=headers,
        data={"upsert": "true"},
        files={"file": ("workers.csv", csv_content, "text/csv")},
    ).json()
    assert bulk["created"] == 2
    assert bulk["errors"] == []

    erp_connectors = client.get("/api/v1/tenant-platforms/erp-connectors", headers=headers).json()
    assert {item["connector_key"] for item in erp_connectors} == {"erp_demo_csv", "erp_authorized_api"}

    erp_preview = client.post(
        "/api/v1/workers/import-from-erp",
        headers=headers,
        json={"connector_key": "erp_demo_csv", "company_id": company["id"], "dry_run": True},
    ).json()
    assert erp_preview["dry_run"] is True
    assert len(erp_preview["preview"]) == 2
    erp_import = client.post(
        "/api/v1/workers/import-from-erp",
        headers=headers,
        json={"connector_key": "erp_demo_csv", "company_id": company["id"], "dry_run": False},
    ).json()
    assert erp_import["created"] == 2

    delete_response = client.delete(f"/api/v1/workers/{worker['id']}", headers=headers)
    assert delete_response.status_code == 204
    visible_workers = client.get("/api/v1/workers", headers=headers).json()
    assert worker["id"] not in {item["id"] for item in visible_workers}
    deleted_workers = client.get("/api/v1/workers?include_deleted=true", headers=headers).json()
    assert worker["id"] in {item["id"] for item in deleted_workers}
    restored = client.post(f"/api/v1/workers/{worker['id']}/restore", headers=headers).json()
    assert restored["status"] == "active"


def test_transfer_demo_and_manual_export_zip(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant Transfer")
    company = client.post("/api/v1/companies", headers=headers, json={"name": "Empresa"}).json()
    worker = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Alta",
            "last_name": "Demo",
            "identifier_type": "dni",
            "identifier_value": "00000387L",
            "identifier_last4": "387L",
            "work_position": "Operario de prueba",
            "medical_fitness_status": "apto",
        },
    ).json()
    document_type = client.post(
        "/api/v1/document-types",
        headers=headers,
        json={
            "code": "CAE.COMPANY.RC_POLICY",
            "name": "Poliza RC",
            "entity_scope": "company",
            "requires_expiration": True,
        },
    ).json()
    document = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_type": "company",
            "entity_id": company["id"],
        },
    ).json()
    version = client.post(
        f"/api/v1/documents/{document['id']}/versions",
        headers=headers,
        json={
            "file_storage_key": "local://documents/rc.pdf",
            "sha256": "c" * 64,
            "filename": "rc.pdf",
            "expires_at": (date.today() + timedelta(days=90)).isoformat(),
        },
    ).json()

    demo_transfer = client.post(
        "/api/v1/transfers",
        headers=headers,
        json={
            "platform_key": "mock_cae",
            "connector_key": "connector_demo",
            "operation": "upload_document",
            "document_version_id": version["id"],
        },
    ).json()
    assert demo_transfer["status"] == "ok"
    assert demo_transfer["idempotency_key"]

    worker_transfer = client.post(
        "/api/v1/transfers",
        headers=headers,
        json={
            "platform_key": "mock_cae",
            "connector_key": "connector_demo",
            "operation": "upsert_worker",
            "worker_id": worker["id"],
        },
    ).json()
    assert worker_transfer["status"] == "ok"
    assert worker_transfer["dry_run"] is True
    worker_registrations = client.get(
        f"/api/v1/workers/{worker['id']}/platform-registrations",
        headers=headers,
    ).json()
    assert worker_registrations[0]["registration_status"] == "accepted"
    assert worker_registrations[0]["source"] == "connector_demo"

    duplicate_worker_transfer = client.post(
        "/api/v1/transfers",
        headers=headers,
        json={
            "platform_key": "mock_cae",
            "connector_key": "connector_demo",
            "operation": "upsert_worker",
            "worker_id": worker["id"],
        },
    )
    assert duplicate_worker_transfer.status_code == 409
    assert "ya existe en esta plataforma/cuenta" in duplicate_worker_transfer.json()["detail"]

    real_rpa_transfer = client.post(
        "/api/v1/transfers",
        headers=headers,
        json={
            "platform_key": "sixconecta",
            "connector_key": "connector_rpa_seisconecta_write",
            "operation": "upsert_worker",
            "worker_id": worker["id"],
        },
    ).json()
    assert real_rpa_transfer["status"] == "blocked_mapping_review_required"
    assert real_rpa_transfer["dry_run"] is True

    real_rpa_document_transfer = client.post(
        "/api/v1/transfers",
        headers=headers,
        json={
            "platform_key": "sixconecta",
            "connector_key": "connector_rpa_seisconecta_write",
            "operation": "upload_company_document",
            "document_version_id": version["id"],
        },
    ).json()
    assert real_rpa_document_transfer["status"] == "blocked_mapping_review_required"
    assert real_rpa_document_transfer["dry_run"] is True

    external_statuses = client.get(
        f"/api/v1/platform-authorizations/external-statuses?company_id={company['id']}",
        headers=headers,
    ).json()
    assert len(external_statuses) == 1
    assert external_statuses[0]["platform_key"] == "mock_cae"
    assert external_statuses[0]["document_version_id"] == version["id"]
    assert external_statuses[0]["document_type_code"] == "CAE.COMPANY.RC_POLICY"
    assert external_statuses[0]["status"] == "accepted"
    assert external_statuses[0]["status_color"] == "green"

    zip_response = client.post(
        "/api/v1/transfers/manual-export.zip",
        headers=headers,
        json={
            "platform_key": "mock_cae",
            "connector_key": "connector_manual_export",
            "operation": "generate_manual_export",
            "document_version_id": version["id"],
        },
    )
    assert zip_response.status_code == 200
    assert zip_response.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(zip_response.content)) as archive:
        assert set(archive.namelist()) == {"README.md", "metadata.csv", "checklist.md"}
        metadata = archive.read("metadata.csv").decode()
        assert "CAE.COMPANY.RC_POLICY" in metadata
        assert "connector" not in metadata.lower()

    worker_zip_response = client.post(
        "/api/v1/transfers/manual-export.zip",
        headers=headers,
        json={
            "platform_key": "mock_cae",
            "connector_key": "connector_manual_export",
            "operation": "upsert_worker",
            "worker_id": worker["id"],
        },
    )
    assert worker_zip_response.status_code == 200
    with ZipFile(BytesIO(worker_zip_response.content)) as archive:
        metadata = archive.read("metadata.csv").decode()
        assert "upsert_worker" in metadata
        assert "Alta Demo" in metadata


def test_upload_computes_hash_stores_file_and_audits_download(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant Upload")
    company = client.post("/api/v1/companies", headers=headers, json={"name": "Empresa"}).json()
    updated_company = client.put(
        f"/api/v1/companies/{company['id']}",
        headers=headers,
        json={
            "name": "Empresa Actualizada",
            "tax_id": "B99999999",
            "company_type": "own",
            "address": "Calle Empresa 1",
            "status": "active",
        },
    )
    assert updated_company.status_code == 200
    assert updated_company.json()["address"] == "Calle Empresa 1"
    document_type = client.post(
        "/api/v1/document-types",
        headers=headers,
        json={
            "code": "CAE.COMPANY.SS_CLEARANCE",
            "name": "Certificado Seguridad Social",
            "entity_scope": "company",
            "requires_expiration": True,
        },
    ).json()
    document = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_type": "company",
            "entity_id": company["id"],
        },
    ).json()
    content = b"documento de prueba"

    upload = client.post(
        f"/api/v1/documents/{document['id']}/upload",
        headers=headers,
        data={
            "source": "manual",
            "expires_at": (date.today() + timedelta(days=365)).isoformat(),
            "platform_expires_at": (date.today() + timedelta(days=180)).isoformat(),
            "platform_expiry_source": "test-platform",
        },
        files={"file": ("certificado.pdf", content, "application/pdf")},
    ).json()

    assert upload["filename"] == "certificado.pdf"
    assert upload["mime_type"] == "application/pdf"
    assert upload["size_bytes"] == len(content)
    assert upload["sha256"] == hashlib.sha256(content).hexdigest()
    assert upload["file_storage_key"].startswith("local://tenant-")
    assert upload["platform_expires_at"] == (date.today() + timedelta(days=180)).isoformat()
    assert upload["expiry_review_status"] == "review_required"

    download = client.get(
        f"/api/v1/documents/{document['id']}/versions/{upload['id']}/download",
        headers=headers,
    )
    assert download.status_code == 200
    assert download.content == content

    audit = client.get("/api/v1/audit", headers=headers).json()
    assert "document_version.download" in {entry["action"] for entry in audit}


def test_upload_rejects_oversized_file(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant Limit")
    company = client.post("/api/v1/companies", headers=headers, json={"name": "Empresa"}).json()
    document_type = client.post(
        "/api/v1/document-types",
        headers=headers,
        json={"code": "CAE.COMPANY.ITA", "name": "ITA", "entity_scope": "company"},
    ).json()
    document = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_type": "company",
            "entity_id": company["id"],
        },
    ).json()

    response = client.post(
        f"/api/v1/documents/{document['id']}/upload",
        headers=headers,
        files={"file": ("large.pdf", b"x" * (1024 * 1024 + 1), "application/pdf")},
    )

    assert response.status_code == 413


def test_document_intake_ocr_classifies_worker_document_and_approves(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant OCR")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "Contrata OCR", "tax_id": "B33333333", "company_type": "contractor"},
    ).json()
    worker = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Ana",
            "last_name": "Lopez",
            "identifier_type": "dni",
            "identifier_last4": "1234",
            "work_position": "Tecnico PRL",
        },
    ).json()
    document_type = client.post(
        "/api/v1/document-types",
        headers=headers,
        json={
            "code": "CAE.WORKER.BASIC_PRL_COURSE",
            "name": "Curso basico PRL",
            "entity_scope": "worker",
            "requires_expiration": False,
        },
    ).json()

    content = (
        "Certificado de curso basico PRL\n"
        "Prevencion de riesgos laborales\n"
        "Trabajador: Ana Lopez\n"
        "DNI terminado en 1234\n"
        "Fecha de emision 10/05/2026\n"
    ).encode()
    intake = client.post(
        "/api/v1/document-intake/upload",
        headers=headers,
        data={"intake_scope": "single_worker", "target_worker_id": str(worker["id"])},
        files={"file": ("curso-prl.txt", content, "text/plain")},
    ).json()

    assert intake["status"] == "pending_review"
    assert intake["intake_scope"] == "single_worker"
    assert intake["requested_company_id"] == company["id"]
    assert intake["requested_worker_id"] == worker["id"]
    assert intake["extraction_engine"] == "text-direct"
    assert intake["predicted_document_type_id"] == document_type["id"]
    assert intake["predicted_entity_type"] == "worker"
    assert intake["predicted_entity_id"] == worker["id"]
    assert intake["predicted_worker_id"] == worker["id"]
    assert intake["predicted_company_id"] == company["id"]
    assert intake["issued_at"] == "2026-05-10"
    assert intake["expires_at"] is None
    assert intake["confidence"] >= 75
    assert "1234" in intake["extracted_text_excerpt"]

    version = client.post(f"/api/v1/document-intake/{intake['id']}/approve", headers=headers, json={}).json()
    assert version["source"] == "ocr"
    assert version["filename"] == "curso-prl.txt"

    documents = client.get(
        f"/api/v1/documents?entity_type=worker&entity_id={worker['id']}",
        headers=headers,
    ).json()
    assert documents[0]["current_version_id"] == version["id"]
    audit = client.get("/api/v1/audit", headers=headers).json()
    assert "document_intake.upload" in {entry["action"] for entry in audit}
    assert "document_intake.approve" in {entry["action"] for entry in audit}


def test_document_intake_supports_multiple_worker_batch_scope(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant OCR Batch")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "Contrata Batch", "tax_id": "B44444444", "company_type": "contractor"},
    ).json()
    client.post(
        "/api/v1/workers",
        headers=headers,
        json={"company_id": company["id"], "first_name": "Ana", "last_name": "Lopez"},
    )
    client.post(
        "/api/v1/workers",
        headers=headers,
        json={"company_id": company["id"], "first_name": "Luis", "last_name": "Garcia"},
    )
    content = b"Parte de formacion PRL Ana Lopez y Luis Garcia"

    response = client.post(
        "/api/v1/document-intake/upload",
        headers=headers,
        data={
            "intake_scope": "multiple_workers",
            "target_company_id": str(company["id"]),
            "target_notes": "lote mensual de trabajadores",
        },
        files={"file": ("lote-trabajadores.txt", content, "text/plain")},
    )
    intake = response.json()

    assert response.status_code == 201
    assert intake["intake_scope"] == "multiple_workers"
    assert intake["requested_company_id"] == company["id"]
    assert intake["requested_worker_id"] is None
    assert intake["predicted_worker_id"] is None
    assert intake["predicted_entity_type"] is None
    assert intake["signals_json"]["requires_batch_review"] is True


def test_document_intake_bulk_zip_creates_pending_company_proposals(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant OCR ZIP")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "ARM Industrial Assemblies", "tax_id": "B12345678", "company_type": "own"},
    ).json()
    client.post(
        "/api/v1/document-types",
        headers=headers,
        json={
            "code": "CAE.COMPANY.AEAT_CLEARANCE",
            "name": "Certificado Hacienda",
            "entity_scope": "company",
            "requires_expiration": True,
        },
    )
    client.post(
        "/api/v1/document-types",
        headers=headers,
        json={
            "code": "CAE.COMPANY.SS_CLEARANCE",
            "name": "Certificado Seguridad Social",
            "entity_scope": "company",
            "requires_expiration": True,
        },
    )
    nested = BytesIO()
    with ZipFile(nested, "w") as archive:
        archive.writestr("Certificado Seguridad Social.txt", "Certificado Seguridad Social ARM B12345678 hasta 31/12/2026")
    payload = BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr("Certificado Hacienda.txt", "AEAT corriente obligaciones tributarias ARM B12345678 01/01/2026")
        archive.writestr("nested.zip", nested.getvalue())
        archive.writestr("program.exe", b"not allowed")
    response = client.post(
        "/api/v1/document-intake/bulk-upload",
        headers=headers,
        data={
            "intake_scope": "company",
            "target_company_id": str(company["id"]),
            "target_notes": "Lote documental ARM",
        },
        files={"file": ("arm-docs.zip", payload.getvalue(), "application/zip")},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["created_count"] == 2
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["reason"] == "unsupported_extension"
    assert {item["status"] for item in result["intakes"]} == {"pending_review"}
    assert {item["requested_company_id"] for item in result["intakes"]} == {company["id"]}
    assert {item["predicted_entity_type"] for item in result["intakes"]} == {"company"}
    assert all(item["created_document_id"] is None for item in result["intakes"])
    audit = client.get("/api/v1/audit", headers=headers).json()
    actions = {entry["action"] for entry in audit}
    assert "document_intake.bulk_upload" in actions
    assert "document_intake.bulk_item_upload" in actions


def test_worker_intake_proposals_preview_and_import(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant ARM Workers")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "ARM Industrial Assemblies", "tax_id": "B87654321", "company_type": "own"},
    ).json()
    payload = BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr("Diploma_ALTURA_Jose_Manuel_Alvarez.txt", "curso altura")
        archive.writestr("Manu_metal_4_horas_28-03-2023.txt", "curso metal")
        archive.writestr("6_-_ART.19_David_-_22-07-2025.txt", "articulo 19")
        archive.writestr(
            "6_-_Art.19_-_20-11-25_ALFONSO_-_Diploma_curso_PRL_00000387L_.txt",
            "articulo 19",
        )
    bulk_response = client.post(
        "/api/v1/document-intake/bulk-upload",
        headers=headers,
        data={
            "intake_scope": "multiple_workers",
            "target_company_id": str(company["id"]),
            "target_notes": "Lote trabajadores ARM",
        },
        files={"file": ("arm-workers.zip", payload.getvalue(), "application/zip")},
    )
    assert bulk_response.status_code == 201
    assert bulk_response.json()["created_count"] == 4

    proposals = client.get(
        f"/api/v1/workers/intake-proposals?company_id={company['id']}",
        headers=headers,
    ).json()
    proposal_by_name = {item["display_name"]: item for item in proposals}
    assert set(proposal_by_name) == {
        "Alfonso Pendiente revisar",
        "David Pendiente revisar",
        "Jose Manuel Alvarez",
    }
    assert proposal_by_name["Jose Manuel Alvarez"]["status"] == "new"
    assert len(proposal_by_name["Jose Manuel Alvarez"]["evidence_filenames"]) == 2
    assert proposal_by_name["David Pendiente revisar"]["status"] == "incomplete"

    dry_run = client.post(
        "/api/v1/workers/import-from-intake",
        headers=headers,
        json={"company_id": company["id"], "dry_run": True},
    ).json()
    assert dry_run["created"] == 0
    assert client.get(f"/api/v1/workers?company_id={company['id']}", headers=headers).json() == []

    imported = client.post(
        "/api/v1/workers/import-from-intake",
        headers=headers,
        json={"company_id": company["id"], "dry_run": False},
    ).json()
    assert imported["created"] == 3
    workers = client.get(f"/api/v1/workers?company_id={company['id']}", headers=headers).json()
    assert {f"{item['first_name']} {item['last_name']}" for item in workers} == set(proposal_by_name)
    assert all(item["identifier_value"] is None for item in workers)
    assert all(item["social_security_number"] is None for item in workers)

    repeat = client.post(
        "/api/v1/workers/import-from-intake",
        headers=headers,
        json={"company_id": company["id"], "dry_run": False},
    ).json()
    assert repeat["created"] == 0
    assert repeat["skipped"] == 3
    audit = client.get("/api/v1/audit", headers=headers).json()
    assert "worker.intake_preview" in {entry["action"] for entry in audit}
    assert "worker.intake_import" in {entry["action"] for entry in audit}


def test_platform_structure_mapping_labels_compare_and_update(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant Platform Maps")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "ARM Industrial Assemblies", "tax_id": "B99999991", "company_type": "own"},
    ).json()
    platform = next(item for item in client.get("/api/v1/tenant-platforms/access", headers=headers).json() if item["platform_key"] == "mock_cae")
    capture = {
        "source": {"initial_host": "mock.local", "platform_label": "Mock Plataforma"},
        "outcome": {"login_status": "login_likely_success", "captcha_detected": False, "mfa_detected": False},
        "pages": [
            {
                "label": "Trabajadores",
                "title": "Trabajadores",
                "headings": ["Trabajadores", "Access Denied"],
                "nav_labels": ["Empresa", "Trabajadores", "Documentacion", "Maquinas/Equipos"],
                "table_headers": [["Empresa", "Trabajador", "Fecha Desde", "Fecha Hasta", "Estado"]],
                "forms": [
                    {
                        "method": "post",
                        "action": "/workers",
                        "inputs": [
                            {"tag": "input", "type": "text", "name": "nombre", "required": True},
                            {"tag": "input", "type": "text", "name": "apellidos", "required": True},
                            {"tag": "input", "type": "text", "name": "dni", "required": False},
                            {"tag": "input", "type": "file", "name": "fichero", "required": False},
                            {"tag": "input", "type": "password", "name": "password", "required": False},
                        ],
                        "buttons": [{"tag": "button", "type": "submit", "text": "Guardar trabajador"}],
                    }
                ],
            }
        ],
    }
    response = client.post(
        "/api/v1/platform-maps/snapshots",
        headers=headers,
        json={
            "external_platform_id": platform["id"],
            "company_id": company["id"],
            "platform_label": "Mock CAE ARM",
            "structure_json": capture,
            "source_ref": "artifacts/mock.redacted.json",
        },
    )
    assert response.status_code == 201
    snapshot = response.json()
    assert snapshot["host"] == "mock.local"
    assert snapshot["login_status"] == "login_likely_success"

    labels = client.get(
        f"/api/v1/platform-maps/labels?snapshot_id={snapshot['id']}",
        headers=headers,
    ).json()
    by_raw = {item["raw_label"]: item for item in labels}
    assert by_raw["nombre"]["standard_key"] == "worker.first_name"
    assert by_raw["apellidos"]["standard_key"] == "worker.last_name"
    assert by_raw["dni"]["standard_key"] == "worker.identifier_value"
    assert "password" not in {item["raw_label"] for item in labels}
    assert "Access Denied" not in {item["raw_label"] for item in labels}

    comparison = client.get(
        "/api/v1/platform-maps/compare?standard_key=worker.identifier_value",
        headers=headers,
    ).json()
    assert comparison[0]["standard_key"] == "worker.identifier_value"
    assert comparison[0]["platform_count"] == 1

    patched = client.patch(
        f"/api/v1/platform-maps/labels/{by_raw['Estado']['id']}",
        headers=headers,
        json={"standard_key": "document.status", "review_status": "approved", "notes": "Estado documental externo."},
    ).json()
    assert patched["standard_key"] == "document.status"
    assert patched["entity_scope"] == "document"
    assert patched["review_status"] == "approved"


def test_arm_first_priority_contract_import_and_mapping_review(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant ARM Contracts")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={
            "name": "ARM Industrial Assemblies",
            "tax_id": "ARM-MAP-001",
            "company_type": "contractor",
            "address": "Poligono ARM",
        },
    ).json()

    response = client.post("/api/v1/platform-contracts/import/arm-first-priority", headers=headers)
    assert response.status_code == 200
    imported = response.json()
    assert imported["manifests_imported"] == 6
    assert imported["accounts_imported"] == 11
    assert imported["platform_accounts_upserted"] == 11
    assert imported["mappings_imported"] > 0
    assert imported["skipped"] == []

    summary = client.get("/api/v1/platform-contracts/summary", headers=headers).json()
    assert summary["manifests"] == 6
    assert summary["accounts"] == 11
    assert summary["blocked_accounts"] == 0
    assert set(summary["priority_platforms"]) == {
        "e_coordina",
        "seisconecta",
        "validate",
        "timenet",
        "nomio",
        "vitaly_cae",
    }

    pending_response = client.post("/api/v1/platform-contracts/import/arm-pending-review", headers=headers)
    assert pending_response.status_code == 200
    pending_imported = pending_response.json()
    assert pending_imported["platform_slugs"] == ["ctaima"]
    assert pending_imported["manifests_imported"] == 1
    assert pending_imported["accounts_imported"] == 3
    assert pending_imported["skipped"] == []

    summary_after_pending = client.get("/api/v1/platform-contracts/summary", headers=headers).json()
    assert "ctaima" in summary_after_pending["priority_platforms"]
    assert summary_after_pending["manifests"] == 7

    manifests = client.get("/api/v1/platform-contracts/manifests", headers=headers).json()
    assert {item["status"] for item in manifests} == {"proposal_disabled"}
    assert all(item["dry_run_default"] is True for item in manifests)
    assert all(item["manual_approval_required"] is True for item in manifests)
    assert all(item["requires_signed_authorization"] is True for item in manifests)
    assert all(item["manifest_json"] is None for item in manifests if "manifest_json" in item)

    accounts = client.get("/api/v1/platform-contracts/accounts", headers=headers).json()
    assert len(accounts) == 14
    assert all(item["status"] == "proposal_disabled" for item in accounts)
    assert all(item["dry_run"] is True for item in accounts)
    assert all(item["manual_approval_required"] is True for item in accounts)
    assert all("credential_secret_ref" not in item for item in accounts)

    sixconecta_manifest = next(item for item in manifests if item["platform_slug"] == "seisconecta")
    sixconecta_account = next(item for item in accounts if item["manifest_id"] == sixconecta_manifest["id"])
    worker_for_sixconecta = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Prueba",
            "last_name": "Seisconecta",
            "identifier_type": "dni",
            "identifier_value": "00000387L",
            "identifier_last4": "0000",
            "nationality": "ES",
            "contract_type": "indefinido",
            "work_position": "Tecnico montaje",
        },
    ).json()
    write_preview = client.post(
        f"/api/v1/exchange/{sixconecta_account['id']}/preview",
        headers=headers,
        json={"operation": "sync_company_profile", "company_id": company["id"]},
    )
    assert write_preview.status_code == 200
    preview_payload = write_preview.json()
    assert preview_payload["operation"] == "sync_company_profile"
    assert preview_payload["status"] == "blocked_mapping_review_required"
    assert preview_payload["readiness"]["external_write_enabled"] is False
    assert preview_payload["readiness"]["dry_run_required"] is True
    assert {field["standard_key"] for field in preview_payload["fields"]} >= {
        "company.name",
        "company.tax_id",
        "company.address",
    }
    assert preview_payload["blockers"]

    capture_request = client.post(
        "/api/v1/rpa-gateway/requests",
        headers=headers,
        json={
            "manifest_id": sixconecta_manifest["id"],
            "account_proposal_id": sixconecta_account["id"],
            "action_key": "capture_write_screen",
            "request_comment": "Capturar pantalla editable de prueba.",
        },
    )
    assert capture_request.status_code == 201
    capture_run = capture_request.json()
    assert capture_run["operation"] == "capture_write_screen"
    assert capture_run["evidence_json"]["gateway"]["requested_action"] == "capture_write_screen"
    assert capture_run["evidence_json"]["gateway"]["writes_external_system"] is False
    sixconecta_edit_capture = client.post(
        "/api/v1/platform-maps/snapshots",
        headers=headers,
        json={
            "external_platform_id": sixconecta_manifest["external_platform_id"],
            "platform_account_id": sixconecta_account["platform_account_id"],
            "company_id": company["id"],
            "platform_label": "6conecta alta trabajador",
            "host": "www.6conecta.com",
            "login_status": "editable_capture_authorized",
            "source_type": "editable_capture",
            "source_ref": "test://seisconecta-worker-form",
            "structure_json": {
                "pages": [
                    {
                        "label": "Alta trabajador",
                        "title": "Trabajadores",
                        "headings": ["Datos del trabajador"],
                        "forms": [
                            {
                                "method": "post",
                                "inputs": [
                                    {"tag": "input", "type": "text", "name": "jform[nif]", "required": True},
                                    {"tag": "input", "type": "text", "name": "jform[nombre]", "required": True},
                                    {"tag": "input", "type": "text", "name": "jform[apellidos]", "required": True},
                                    {
                                        "tag": "select",
                                        "type": "",
                                        "name": "jform[nacionalidad_trabajador]",
                                        "required": True,
                                    },
                                    {
                                        "tag": "select",
                                        "type": "",
                                        "name": "jform[id_contrato][]",
                                        "required": True,
                                    },
                                    {"tag": "select", "type": "", "name": "jform[id_puesto]", "required": True},
                                ],
                            }
                        ],
                    }
                ]
            },
        },
    )
    assert sixconecta_edit_capture.status_code == 201

    coverage = client.get("/api/v1/platform-maps/data-coverage?priority_group=all", headers=headers).json()
    assert coverage["safe_mode"]["read_only"] is True
    assert coverage["safe_mode"]["stores_external_row_values"] is False
    assert coverage["totals"]["platforms"] == 7
    assert coverage["totals"]["contexts"] == 14
    assert coverage["totals"]["pending_items"] > 0
    assert coverage["totals"]["pending_red"] > 0
    assert coverage["totals"]["pending_orange"] > 0
    assert all(isinstance(blocker, str) for context in coverage["contexts"] for blocker in context["blockers"])
    ctaima_context = next(item for item in coverage["contexts"] if item["platform_slug"] == "ctaima")
    assert "CTAIMA" in ctaima_context["trace_label"]
    assert ctaima_context["pending_summary"]["total"] == len(ctaima_context["pending_items"])
    assert {item["kind"] for item in ctaima_context["pending_items"]} >= {
        "account_not_active",
        "missing_required_key",
        "pending_mapping_review",
    }
    assert {category["category_key"] for category in ctaima_context["categories"]} >= {
        "company",
        "workers",
        "documents",
        "assets",
    }
    assert all("pending_items" in category for category in ctaima_context["categories"])

    edit_methods = client.get("/api/v1/platform-maps/edit-methods?priority_group=all", headers=headers).json()
    assert edit_methods["policy"]["captcha_bypass"] is False
    assert edit_methods["policy"]["stores_static_commercial_selectors"] is False
    assert edit_methods["totals"]["platforms"] == 7
    assert edit_methods["totals"]["contexts"] == 14
    ctaima_edit_context = next(item for item in edit_methods["contexts"] if item["platform_slug"] == "ctaima")
    password_method = next(
        item for item in ctaima_edit_context["field_methods"] if item["standard_key"] == "platform.login.password"
    )
    assert password_method["status"] == "credential_secret_only"
    assert password_method["method"] == "inject_from_configured_secret_store_at_login"
    assert password_method["requires_manual_approval"] is True
    upsert_worker = next(item for item in ctaima_edit_context["operations"] if item["operation"] == "upsert_worker")
    assert upsert_worker["requires_before_after_audit"] is True
    assert "worker.identifier_value" in upsert_worker["required_standard_keys"]
    sixconecta_edit_context = next(item for item in edit_methods["contexts"] if item["platform_slug"] == "seisconecta")
    sixconecta_upsert = next(
        item for item in sixconecta_edit_context["operations"] if item["operation"] == "upsert_worker"
    )
    assert sixconecta_upsert["required_standard_keys"] == [
        "worker.identifier_value",
        "worker.first_name",
        "worker.last_name",
        "worker.nationality",
        "worker.contract_type",
        "worker.work_position",
    ]
    assert sixconecta_upsert["status"] == "ready_for_preview"
    worker_preview = client.post(
        f"/api/v1/exchange/{sixconecta_account['id']}/preview",
        headers=headers,
        json={
            "operation": "upsert_worker",
            "company_id": company["id"],
            "worker_id": worker_for_sixconecta["id"],
        },
    )
    assert worker_preview.status_code == 200
    worker_preview_payload = worker_preview.json()
    assert worker_preview_payload["status"] == "preview_ready"
    assert worker_preview_payload["readiness"]["external_write_enabled"] is False
    assert worker_preview_payload["readiness"]["account_ready_for_live"] is False
    assert not worker_preview_payload["blockers"]
    assert {item["standard_key"] for item in worker_preview_payload["planned_external_changes"]} == {
        "worker.identifier_value",
        "worker.first_name",
        "worker.last_name",
        "worker.nationality",
        "worker.contract_type",
        "worker.work_position",
    }

    mappings = client.get(
        "/api/v1/platform-contracts/mappings?mapping_kind=field&review_status=pending_review",
        headers=headers,
    ).json()
    first_name = next(item for item in mappings if item["iker_key"] == "worker.first_name")
    patched = client.patch(
        f"/api/v1/platform-contracts/mappings/{first_name['id']}",
        headers=headers,
        json={"review_status": "needs_provider_confirmation", "notes": "Pendiente validar contra captura."},
    )
    assert patched.status_code == 200
    assert patched.json()["review_status"] == "needs_provider_confirmation"


def test_arm_all_contract_import_configures_current_arm_platforms(client: TestClient) -> None:
    _tenant, headers = _tenant_admin(client, "Tenant ARM All Platforms")

    response = client.post("/api/v1/platform-contracts/import/arm-all", headers=headers)
    assert response.status_code == 200
    imported = response.json()
    assert imported["manifests_imported"] == 20
    assert imported["accounts_imported"] == 34
    assert imported["platform_accounts_upserted"] == 34
    assert imported["mappings_imported"] > 0
    assert imported["skipped"] == []

    summary = client.get("/api/v1/platform-contracts/summary", headers=headers).json()
    assert summary["manifests"] == 20
    assert summary["accounts"] == 34
    assert summary["blocked_accounts"] == 2
    assert {"e_coordina", "ctaima", "dokyfy", "sarenet"}.issubset(set(summary["priority_platforms"]))

    schedules = client.post("/api/v1/platform-review-schedules/ensure?priority_group=all", headers=headers).json()
    assert len(schedules) == 20
    assert all(item["dry_run"] is True for item in schedules)
    assert all(item["manual_approval_required"] is True for item in schedules)


def test_arm_available_write_platforms_preview_only_and_human_assisted(client: TestClient) -> None:
    _tenant, headers = _tenant_admin(client, "Tenant ARM Write Guard")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "ARM Industrial Assemblies", "tax_id": "B95868543", "company_type": "contractor"},
    ).json()
    worker = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Eleder",
            "last_name": "Gomez",
            "identifier_type": "dni",
            "identifier_value": "00000387L",
            "identifier_last4": "387L",
            "nationality": "ES",
            "contract_type": "indefinido",
            "work_position": "Montador",
            "medical_fitness_status": "apto",
            "medical_fitness_expires_at": (date.today() + timedelta(days=180)).isoformat(),
        },
    ).json()

    import_response = client.post("/api/v1/platform-contracts/import/arm-all", headers=headers)
    assert import_response.status_code == 200
    schedule_response = client.post("/api/v1/platform-review-schedules/ensure?priority_group=all", headers=headers)
    assert schedule_response.status_code == 200
    manifests = client.get("/api/v1/platform-contracts/manifests", headers=headers).json()
    accounts = client.get("/api/v1/platform-contracts/accounts", headers=headers).json()
    manifest_by_id = {manifest["id"]: manifest for manifest in manifests}
    write_connector_by_slug = {
        "ctaima": "connector_rpa_ctaima_write",
        "dokyfy": "connector_rpa_dokyfy_write",
        "e_coordina": "connector_rpa_e_coordina_write",
        "egestiona": "connector_rpa_egestiona_write",
        "folyo": "connector_rpa_folyo_write",
        "iedoce": "connector_rpa_iedoce_write",
        "integra_asem": "connector_rpa_integra_asem_write",
        "koordinatu": "connector_rpa_koordinatu_write",
        "metacontratas": "connector_rpa_metacontratas_write",
        "nomio": "connector_rpa_nomio_write",
        "quioo": "connector_rpa_quioo_write",
        "sgs_gestiona": "connector_rpa_sgs_gestiona_write",
        "seisconecta": "connector_rpa_seisconecta_write",
        "smartosh": "connector_rpa_smartosh_write",
        "timenet": "connector_rpa_timenet_write",
        "ucae": "connector_rpa_ucae_write",
        "validate": "connector_rpa_validate_write",
        "vitaly_cae": "connector_rpa_vitaly_cae_write",
    }
    platform_key_by_slug = {
        "ctaima": "ctaima_cae",
        "dokyfy": "dokify",
        "e_coordina": "ecoordina",
        "egestiona": "egestiona",
        "folyo": "folyo",
        "iedoce": "iedoce",
        "integra_asem": "asemwebservices_integra",
        "koordinatu": "koordinatu",
        "metacontratas": "metacontratas",
        "nomio": "nomio",
        "quioo": "quioo",
        "sgs_gestiona": "sgs_gestiona",
        "seisconecta": "sixconecta",
        "smartosh": "smartosh",
        "timenet": "timenet",
        "ucae": "ucae",
        "validate": "validate",
        "vitaly_cae": "vitaly_cae",
    }
    writable_accounts = [
        account
        for account in accounts
        if manifest_by_id[account["manifest_id"]]["platform_slug"] in write_connector_by_slug
    ]
    assert {manifest_by_id[account["manifest_id"]]["platform_slug"] for account in writable_accounts} == set(
        write_connector_by_slug
    )

    live_adapters = client.get("/api/v1/exchange/live-adapters", headers=headers)
    assert live_adapters.status_code == 200
    live_payload = live_adapters.json()
    assert live_payload["summary"]["platforms"] == 20
    assert live_payload["summary"]["registered_write_connectors"] == 18
    assert live_payload["summary"]["live_adapter_statuses"]["specific_live_adapter_available"] == 2
    assert live_payload["summary"]["live_adapter_statuses"]["blocked_live_adapter_missing"] == 16
    seisconecta_adapter = next(row for row in live_payload["rows"] if row["platform_slug"] == "seisconecta")
    assert seisconecta_adapter["live_adapter_status"] == "specific_live_adapter_available"
    assert seisconecta_adapter["helper_status"] == "live_implemented"
    assert seisconecta_adapter["helper"]["script_path"] == "scripts/seisconecta_live_upsert_worker.py"
    ctaima_adapter = next(row for row in live_payload["rows"] if row["platform_slug"] == "ctaima")
    assert ctaima_adapter["live_adapter_status"] == "specific_live_adapter_available"
    assert ctaima_adapter["helper_status"] == "live_implemented"
    assert ctaima_adapter["helper"]["script_path"] == "scripts/ctaima_live_upsert_worker.py"
    assert ctaima_adapter["helper"]["commercial_routes_or_selectors_invented"] is False
    assert "pre_write_duplicate_readback" in ctaima_adapter["required_before_live_write"]

    write_matrix = client.get(
        "/api/v1/exchange/write-matrix",
        headers=headers,
        params={
            "company_id": company["id"],
            "worker_id": worker["id"],
            "operations": "upsert_worker",
            "connector_dry_run": "true",
        },
    )
    assert write_matrix.status_code == 200
    matrix_payload = write_matrix.json()
    assert matrix_payload["policy"]["external_write_executed"] is False
    assert matrix_payload["policy"]["commercial_routes_or_selectors_invented"] is False
    assert matrix_payload["summary"]["rows"] == 34
    assert matrix_payload["summary"]["external_writes_executed"] == 0
    live_ready_account_rows = sum(
        1
        for account in writable_accounts
        if manifest_by_id[account["manifest_id"]]["platform_slug"] in {"seisconecta", "ctaima"}
    )
    assert matrix_payload["summary"]["live_adapter_statuses"]["specific_live_adapter_available"] == live_ready_account_rows
    assert (
        matrix_payload["summary"]["live_adapter_statuses"]["blocked_live_adapter_missing"]
        == len(writable_accounts) - live_ready_account_rows
    )
    assert any(
        row["helper"]["status"] == "scaffolded_pending_capture"
        for row in matrix_payload["rows"]
        if row["write_connector_key"] and row["platform_slug"] not in {"seisconecta", "ctaima"}
    )
    assert any(row["connector_dry_run_status"] for row in matrix_payload["rows"] if row["write_connector_key"])

    bulk_submit = client.post(
        "/api/v1/exchange/workers/bulk-submit",
        headers=headers,
        json={
            "company_id": company["id"],
            "worker_id": worker["id"],
            "dry_run": True,
            "manual_approval_required": True,
            "create_capture_requests": True,
        },
    )
    assert bulk_submit.status_code == 200
    bulk_payload = bulk_submit.json()
    assert bulk_payload["policy"]["external_routes_or_selectors_invented"] is False
    assert bulk_payload["summary"]["targets"] == len(writable_accounts)
    assert bulk_payload["summary"]["transfer_jobs_created"] == len(writable_accounts)
    assert bulk_payload["summary"]["capture_requests_created"] == len(writable_accounts)
    assert bulk_payload["summary"]["external_writes_confirmed"] == 0
    assert {row["connector_key"] for row in bulk_payload["rows"]} == set(write_connector_by_slug.values())

    mass_plan = client.post(
        "/api/v1/exchange/mass-update/plan",
        headers=headers,
        json={
            "company_id": company["id"],
            "include_missing_workers": True,
            "include_document_requests": False,
            "only_active_contexts": False,
            "limit": 20,
        },
    )
    assert mass_plan.status_code == 200
    mass_plan_payload = mass_plan.json()
    assert mass_plan_payload["policy"]["external_write_executed"] is False
    assert mass_plan_payload["policy"]["commercial_routes_or_selectors_invented"] is False
    assert mass_plan_payload["summary"]["actions"] > 0
    assert mass_plan_payload["summary"]["missing_workers"] == mass_plan_payload["summary"]["actions"]
    assert {row["kind"] for row in mass_plan_payload["actions"]} == {"missing_worker"}

    mass_submit = client.post(
        "/api/v1/exchange/mass-update/submit",
        headers=headers,
        json={
            "company_id": company["id"],
            "include_missing_workers": True,
            "include_document_requests": False,
            "only_active_contexts": False,
            "limit": 3,
            "dry_run": True,
            "manual_approval_required": True,
            "create_capture_requests": True,
        },
    )
    assert mass_submit.status_code == 200
    mass_submit_payload = mass_submit.json()
    assert mass_submit_payload["policy"]["external_routes_or_selectors_invented"] is False
    assert mass_submit_payload["policy"]["requires_post_write_readback"] is True
    assert mass_submit_payload["summary"]["selected_actions"] == 3
    assert mass_submit_payload["summary"]["confirmed_external"] == 0
    assert mass_submit_payload["summary"]["capture_requests_created"] >= 1

    bulk_capture = client.post(
        "/api/v1/exchange/capture-write-screens/bulk",
        headers=headers,
        json={
            "include_accounts_without_write_connector": True,
            "skip_existing_active": True,
            "request_comment": "Mapeo editable masivo de prueba.",
        },
    )
    assert bulk_capture.status_code == 200
    bulk_capture_payload = bulk_capture.json()
    assert bulk_capture_payload["policy"]["external_browser_launched"] is False
    assert bulk_capture_payload["policy"]["external_write_executed"] is False
    assert bulk_capture_payload["summary"]["targets"] == len(accounts)
    assert bulk_capture_payload["summary"]["skipped_existing_active"] == len(writable_accounts)
    assert bulk_capture_payload["summary"]["created"] == len(accounts) - len(writable_accounts)
    assert bulk_capture_payload["summary"]["accounts_without_write_connector"] == len(accounts) - len(writable_accounts)

    for account in writable_accounts:
        manifest = manifest_by_id[account["manifest_id"]]
        preview = client.post(
            f"/api/v1/exchange/{account['id']}/preview",
            headers=headers,
            json={
                "operation": "upsert_worker",
                "company_id": company["id"],
                "worker_id": worker["id"],
            },
        )
        assert preview.status_code == 200
        payload = preview.json()
        assert payload["platform"]["platform_slug"] == manifest["platform_slug"]
        assert payload["operation"] == "upsert_worker"
        assert payload["readiness"]["external_write_enabled"] is False
        assert payload["readiness"]["dry_run_required"] is True
        assert payload["readiness"]["manual_approval_required"] is True
        assert payload["readiness"]["before_after_audit_required"] is True
        assert payload["account"]["dry_run"] is True
        assert payload["account"]["manual_approval_required"] is True
        assert payload["policy"]["captcha_bypass"] is False
        assert payload["policy"]["mfa_bypass"] is False
        assert payload["policy"]["stores_static_commercial_selectors"] is False
        assert payload["policy"]["stores_credentials_or_tokens"] is False
        assert payload["policy"]["live_external_write_requires_submit_job"] is True
        assert payload["status"] in {
            "preview_ready",
            "blocked_mapping_review_required",
            "blocked_local_data_required",
        }

    for slug, connector_key in write_connector_by_slug.items():
        transfer = client.post(
            "/api/v1/transfers",
            headers=headers,
            json={
                "platform_key": platform_key_by_slug[slug],
                "connector_key": connector_key,
                "operation": "upsert_worker",
                "worker_id": worker["id"],
                "dry_run": True,
                "manual_approval_required": True,
            },
        )
        assert transfer.status_code == 201
        transfer_payload = transfer.json()
        assert transfer_payload["status"] == "blocked_mapping_review_required"
        assert transfer_payload["dry_run"] is True
        assert transfer_payload["requires_approval"] is True
        assert transfer_payload["last_attempt_status"] == "blocked_mapping_review_required"
        assert "dry-run" in transfer_payload["last_attempt_message"]
        assert transfer_payload["post_write_read_confirmed"] is None
        assert transfer_payload["valid_external_write"] is None

    ctaima_manifest = next(manifest for manifest in manifests if manifest["platform_slug"] == "ctaima")
    ctaima_account = next(account for account in writable_accounts if account["manifest_id"] == ctaima_manifest["id"])
    exchange_submit = client.post(
        f"/api/v1/exchange/{ctaima_account['id']}/submit",
        headers=headers,
        json={
            "operation": "upsert_worker",
            "company_id": company["id"],
            "worker_id": worker["id"],
            "dry_run": True,
            "manual_approval_required": True,
        },
    )
    assert exchange_submit.status_code == 201
    exchange_submit_payload = exchange_submit.json()
    assert exchange_submit_payload["connector_key"] == "connector_rpa_ctaima_write"
    assert exchange_submit_payload["status"] == "blocked_mapping_review_required"
    assert exchange_submit_payload["dry_run"] is True
    assert exchange_submit_payload["valid_external_write"] is None

    exchange_capture_request = client.post(
        f"/api/v1/exchange/{ctaima_account['id']}/capture-write-screen",
        headers=headers,
        json={"request_comment": "Capturar pantalla editable desde Exchange."},
    )
    assert exchange_capture_request.status_code == 201
    exchange_capture_run = exchange_capture_request.json()
    assert exchange_capture_run["operation"] == "capture_write_screen"
    assert exchange_capture_run["account_proposal_id"] == ctaima_account["id"]
    assert exchange_capture_run["evidence_json"]["gateway"]["requested_action"] == "capture_write_screen"
    assert exchange_capture_run["evidence_json"]["gateway"]["writes_external_system"] is False

    gateway_request = client.post(
        "/api/v1/rpa-gateway/requests",
        headers=headers,
        json={
            "manifest_id": ctaima_manifest["id"],
            "account_proposal_id": ctaima_account["id"],
            "action_key": "capture_write_screen",
            "request_comment": "Probar pasarela humana ante captcha/MFA/control.",
        },
    )
    assert gateway_request.status_code == 201
    run = gateway_request.json()
    assert run["status"] == "human_action_required"
    assert run["dry_run"] is True
    assert run["manual_approval_required"] is True
    assert run["operation"] == "capture_write_screen"
    assert run["evidence_json"]["gateway"]["requested_action"] == "capture_write_screen"
    assert run["evidence_json"]["gateway"]["writes_external_system"] is False
    assert run["evidence_json"]["gateway"]["safe_controls"]["captcha_bypass"] is False
    assert run["evidence_json"]["gateway"]["safe_controls"]["mfa_bypass"] is False

    required_upsert_keys = [
        "worker.first_name",
        "worker.last_name",
        "worker.identifier_value",
        "worker.social_security_number",
        "worker.email",
        "worker.phone",
        "worker.work_position",
        "worker.contract_type",
    ]
    write_path = client.post(
        f"/api/v1/exchange/{ctaima_account['id']}/write-paths",
        headers=headers,
        json={
            "operation": "upsert_worker",
            "entity_scope": "worker",
            "path_kind": "editable_form",
            "path_label": "Alta trabajador CTAIMA capturada",
            "entry_path": "/captured/worker-edit",
            "field_paths": {
                key: {
                    "strategy": "observed_label_or_stable_name",
                    "label": key,
                    "source": "redacted_capture",
                }
                for key in required_upsert_keys
            },
            "selector_map": {
                "submit": {
                    "strategy": "observed_button",
                    "label": "Guardar",
                }
            },
            "readback_paths": {
                "worker.identifier_value": {
                    "strategy": "search_readback",
                    "label": "DNI/NIE",
                }
            },
            "source_evidence_ref": "platform_review_run:test-redacted-capture",
            "metadata": {"source": "unit_test_redacted_capture"},
        },
    )
    assert write_path.status_code == 201
    write_path_payload = write_path.json()
    assert write_path_payload["review_status"] == "pending_review"
    assert write_path_payload["field_paths"]["worker.first_name"]["source"] == "redacted_capture"

    approved_path = client.post(
        f"/api/v1/exchange/write-paths/{write_path_payload['id']}/review",
        headers=headers,
        json={"review_status": "approved", "notes": "Captura editable revisada."},
    )
    assert approved_path.status_code == 200
    assert approved_path.json()["review_status"] == "approved"
    assert approved_path.json()["status"] == "approved_for_preview_and_readback"

    listed_paths = client.get(
        "/api/v1/exchange/write-paths",
        headers=headers,
        params={"account_proposal_id": ctaima_account["id"], "operation": "upsert_worker"},
    )
    assert listed_paths.status_code == 200
    assert listed_paths.json()[0]["id"] == write_path_payload["id"]

    mapped_preview = client.post(
        f"/api/v1/exchange/{ctaima_account['id']}/preview",
        headers=headers,
        json={
            "operation": "upsert_worker",
            "company_id": company["id"],
            "worker_id": worker["id"],
        },
    )
    assert mapped_preview.status_code == 200
    mapped_preview_payload = mapped_preview.json()
    assert mapped_preview_payload["status"] in {"preview_ready", "blocked_local_data_required"}
    assert mapped_preview_payload["readiness"]["mapping_ready"] is True
    assert mapped_preview_payload["policy"]["stores_only_reviewed_captured_write_paths"] is True
    assert all(
        field["approved_write_path_count"] == 1
        for field in mapped_preview_payload["fields"]
        if field["standard_key"] in required_upsert_keys
    )


def test_worker_transfer_blocks_legacy_registration_without_platform_account_id(client: TestClient) -> None:
    _tenant, headers = _tenant_admin(client, "Tenant ARM Legacy Registration Guard")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "ARM Industrial Assemblies", "tax_id": "B95868543", "company_type": "contractor"},
    ).json()
    worker = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Prueba",
            "last_name": "Hub",
            "identifier_type": "dni",
            "identifier_value": "99999999R",
            "identifier_last4": "999R",
            "nationality": "ES",
            "contract_type": "indefinido",
            "work_position": "Montador",
        },
    ).json()
    assert client.post("/api/v1/platform-contracts/import/arm-all", headers=headers).status_code == 200
    manifests = client.get("/api/v1/platform-contracts/manifests", headers=headers).json()
    accounts = client.get("/api/v1/platform-contracts/accounts", headers=headers).json()
    seisconecta_manifest = next(manifest for manifest in manifests if manifest["platform_slug"] == "seisconecta")
    seisconecta_account = next(
        account for account in accounts if account["manifest_id"] == seisconecta_manifest["id"]
    )
    legacy_registration = client.post(
        f"/api/v1/workers/{worker['id']}/platform-registrations",
        headers=headers,
        json={
            "platform_account_id": None,
            "external_platform_id": seisconecta_manifest["external_platform_id"],
            "platform_name": "6conecta",
            "registration_status": "submitted_pending_readback",
            "source": "connector_rpa_seisconecta_write",
        },
    )
    assert legacy_registration.status_code == 201

    duplicate = client.post(
        "/api/v1/transfers",
        headers=headers,
        json={
            "platform_key": "sixconecta",
            "connector_key": "connector_rpa_seisconecta_write",
            "operation": "upsert_worker",
            "worker_id": worker["id"],
            "account_proposal_id": seisconecta_account["id"],
            "dry_run": True,
            "manual_approval_required": True,
        },
    )

    assert duplicate.status_code == 409
    assert "ya existe en esta plataforma/cuenta" in duplicate.json()["detail"]


def test_arm_authorization_dashboard_reports_worker_and_platform_incidents(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant ARM Authorizations")
    company = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "ARM Industrial Assemblies", "tax_id": "ARM000001", "company_type": "contractor"},
    ).json()
    import_response = client.post("/api/v1/platform-contracts/import/arm-first-priority", headers=headers)
    assert import_response.status_code == 200

    ready_worker = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Marta",
            "last_name": "Soler",
            "identifier_type": "dni",
            "identifier_value": "11111111H",
            "identifier_last4": "1111",
            "work_position": "Montadora",
            "medical_fitness_status": "apto",
            "medical_fitness_issued_at": date.today().isoformat(),
            "medical_fitness_expires_at": (date.today() + timedelta(days=180)).isoformat(),
        },
    ).json()
    incomplete_worker = client.post(
        "/api/v1/workers",
        headers=headers,
        json={
            "company_id": company["id"],
            "first_name": "Pablo",
            "last_name": "Rivas",
            "work_position": "Operario",
        },
    ).json()
    document_type = client.post(
        "/api/v1/document-types",
        headers=headers,
        json={
            "code": "CAE.WORKER.ID",
            "name": "Identificacion trabajador",
            "entity_scope": "worker",
            "requires_expiration": True,
        },
    ).json()
    document = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_type": "worker",
            "entity_id": ready_worker["id"],
        },
    ).json()
    client.post(
        f"/api/v1/documents/{document['id']}/versions",
        headers=headers,
        json={
            "file_storage_key": "local://documents/arm-worker-id.pdf",
            "sha256": "e" * 64,
            "filename": "arm-worker-id.pdf",
            "issued_at": date.today().isoformat(),
            "expires_at": (date.today() + timedelta(days=365)).isoformat(),
        },
    )
    client.post(
        f"/api/v1/workers/{ready_worker['id']}/platform-registrations",
        headers=headers,
        json={
            "platform_name": "e-coordina",
            "registration_status": "missing_required_document",
            "assignment_scope": "ARM",
            "notes": "SOFIDEL: falta Entrega de EPIs para Eleder Bilbao.",
        },
    )

    response = client.get(
        f"/api/v1/platform-authorizations/dashboard?company_id={company['id']}",
        headers=headers,
    )
    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["company"]["name"] == "ARM Industrial Assemblies"
    assert dashboard["overall_status"] == "red"
    assert dashboard["totals"]["platforms"] == 6
    assert dashboard["totals"]["workers"] == 2
    assert dashboard["totals"]["red_incidents"] >= 1
    assert all(platform["dry_run_default"] is True for platform in dashboard["platforms"])
    assert all(platform["manual_approval_required"] is True for platform in dashboard["platforms"])
    assert all(platform["local_update_path"] == "/authorizations" for platform in dashboard["platforms"])
    assert all("read_external_status" in platform["allowed_operations"] for platform in dashboard["platforms"])
    e_coordina = next(platform for platform in dashboard["platforms"] if platform["platform_slug"] == "e_coordina")
    assert e_coordina["read_status"] == "orange"
    assert e_coordina["write_status"] == "red"
    assert e_coordina["authorization_status"] == "orange"
    assert e_coordina["next_action"]
    assert all(platform["read_summary"] != "Conector no implementado" for platform in dashboard["platforms"])
    workers_by_name = {worker["worker_name"]: worker for worker in dashboard["workers"]}
    ready_authorization = workers_by_name["Marta Soler"]
    incomplete_authorization = workers_by_name["Pablo Rivas"]
    assert ready_authorization["platform_registrations"] == 1
    assert ready_authorization["platform_registration_details"][0]["platform_name"] == "e-coordina"
    assert ready_authorization["platform_registration_details"][0]["registration_status"] == "missing_required_document"
    assert ready_authorization["platform_registration_details"][0]["registration_status_color"] == "red"
    assert "Entrega de EPIs" in ready_authorization["platform_registration_details"][0]["notes"]
    assert incomplete_authorization["platform_registration_details"] == []
    assert any(item["title"] == "Falta DNI/NIE" for item in dashboard["incidents"])
    assert any(
        item["local_update_path"] == f"/workers?worker_id={incomplete_worker['id']}"
        for item in dashboard["incidents"]
    )


def test_platform_review_schedule_controller_configures_intervals(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant ARM Schedule")
    import_response = client.post("/api/v1/platform-contracts/import/arm-first-priority", headers=headers)
    assert import_response.status_code == 200

    ensured = client.post("/api/v1/platform-review-schedules/ensure", headers=headers)
    assert ensured.status_code == 200
    schedules = ensured.json()
    assert len(schedules) == 6
    assert {item["status"] for item in schedules} == {"disabled"}
    assert all(item["dry_run"] is True for item in schedules)
    assert all(item["manual_approval_required"] is True for item in schedules)
    assert all(item["interval_minutes"] == 720 for item in schedules)

    health = client.get("/api/v1/platform-review-schedules/health", headers=headers)
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["interval_minutes_required"] == 720
    assert health_payload["safe_mode"] is True
    assert health_payload["totals"]["not_configured"] == 6

    activated = client.post("/api/v1/platform-review-schedules/activate-12h", headers=headers)
    assert activated.status_code == 200
    activated_schedules = activated.json()
    assert all(item["enabled"] is True for item in activated_schedules)
    assert all(item["status"] == "scheduled" for item in activated_schedules)
    assert all(item["interval_minutes"] == 720 for item in activated_schedules)

    health_after_activation = client.get("/api/v1/platform-review-schedules/health", headers=headers).json()
    assert health_after_activation["totals"]["not_checked"] == 6

    target = next(item for item in activated_schedules if item["platform_slug"] == "e_coordina")
    patched = client.patch(
        f"/api/v1/platform-review-schedules/{target['id']}",
        headers=headers,
        json={
            "enabled": True,
            "interval_minutes": 720,
            "review_scope": ["company", "workers", "documents", "incidents"],
            "notes": "Revisar dos veces al dia en dry_run.",
        },
    )
    assert patched.status_code == 200
    updated = patched.json()
    assert updated["enabled"] is True
    assert updated["status"] == "scheduled"
    assert updated["interval_minutes"] == 720
    assert updated["next_run_at"] is not None
    assert updated["review_scope"] == ["company", "workers", "documents", "incidents"]

    listed = client.get("/api/v1/platform-review-schedules", headers=headers).json()
    assert len(listed) == 6
    assert next(item for item in listed if item["id"] == target["id"])["status"] == "scheduled"

    run_response = client.post(
        f"/api/v1/platform-review-schedules/{target['id']}/run-now",
        headers=headers,
        json={},
    )
    assert run_response.status_code == 201
    run = run_response.json()
    assert run["platform_slug"] == "e_coordina"
    assert run["status"] == "blocked_feature_disabled"
    assert run["dry_run"] is True
    assert run["manual_approval_required"] is True
    assert "required_flags" in run["evidence_json"]

    listed_after_run = client.get("/api/v1/platform-review-schedules", headers=headers).json()
    ran_schedule = next(item for item in listed_after_run if item["id"] == target["id"])
    assert ran_schedule["last_run_at"] is not None
    assert ran_schedule["last_result_status"] == "rpa_disabled"
    assert ran_schedule["next_run_at"] is not None

    health_after_run = client.get("/api/v1/platform-review-schedules/health", headers=headers).json()
    e_coordina_health = next(
        item for item in health_after_run["platforms"] if item["platform_slug"] == "e_coordina"
    )
    assert e_coordina_health["review_status"] == "not_working"
    assert e_coordina_health["last_result_status"] == "rpa_disabled"
    assert health_after_run["totals"]["not_working"] == 1

    runs = client.get(f"/api/v1/platform-review-schedules/{target['id']}/runs", headers=headers).json()
    assert [item["id"] for item in runs] == [run["id"]]

    audit = client.get("/api/v1/audit", headers=headers).json()
    assert {entry["action"] for entry in audit} >= {
        "platform_review_schedules.activate_12h",
        "platform_review_schedules.ensure",
        "platform_review_schedules.update",
        "platform_review_runs.run_now",
    }


def test_rpa_gateway_creates_human_assisted_request(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant RPA Gateway")
    import_response = client.post("/api/v1/platform-contracts/import/arm-first-priority", headers=headers)
    assert import_response.status_code == 200
    client.post("/api/v1/platform-review-schedules/ensure", headers=headers)

    options_response = client.get("/api/v1/rpa-gateway/options", headers=headers)
    assert options_response.status_code == 200
    options = options_response.json()
    assert options["policy"]["captcha_bypass_supported"] is False
    assert options["policy"]["visible_browser_required_for_human_controls"] is True
    assert any(action["action_key"] == "read_external_status" and action["enabled"] for action in options["actions"])
    assert any(action["action_key"] == "upload_worker_document" and not action["enabled"] for action in options["actions"])

    schedule = next(item for item in options["schedules"] if item["platform_slug"] == "e_coordina")
    request_response = client.post(
        "/api/v1/rpa-gateway/requests",
        headers=headers,
        json={
            "schedule_id": schedule["schedule_id"],
            "action_key": "read_external_status",
            "request_comment": "Revisar estado sin modificar nada.",
        },
    )
    assert request_response.status_code == 201
    run = request_response.json()
    assert run["status"] == "human_action_required"
    assert run["result_status"] == "waiting_human_gateway"
    assert run["trigger_source"] == "human_gateway_request"
    assert run["evidence_json"]["gateway"]["ui_boundary"].startswith("Pantalla propia")
    assert run["evidence_json"]["gateway"]["changes_applied"] == []
    assert run["evidence_json"]["gateway"]["safe_controls"]["captcha_bypass"] is False
    assert run["evidence_json"]["gateway"]["allowed_external_url"]
    assert run["evidence_json"]["gateway"]["guided_flow"]["title"].startswith("Flujo guiado")
    assert "Solo lectura" in run["evidence_json"]["gateway"]["guided_flow"]["read_only_boundary"]

    launch_before_authorization = client.post(
        f"/api/v1/rpa-gateway/requests/{run['id']}/launch-visible-browser",
        headers=headers,
    )
    assert launch_before_authorization.status_code == 200
    assert launch_before_authorization.json()["launched"] is False
    assert launch_before_authorization.json()["status"] == "authorization_required"
    browser_status = client.get(
        f"/api/v1/rpa-gateway/requests/{run['id']}/browser-status",
        headers=headers,
    )
    assert browser_status.status_code == 200
    assert browser_status.json()["state"] == "browser_not_started"
    sync_without_capture = client.post(
        f"/api/v1/rpa-gateway/requests/{run['id']}/sync-readonly-capture",
        headers=headers,
    )
    assert sync_without_capture.status_code == 200
    assert sync_without_capture.json()["synced"] is False
    assert sync_without_capture.json()["status"] == "capture_not_available"

    decision_response = client.post(
        f"/api/v1/rpa-gateway/requests/{run['id']}/decision",
        headers=headers,
        json={"decision": "authorize_enter_page", "notes": "Operador delante de pantalla."},
    )
    assert decision_response.status_code == 200
    authorized = decision_response.json()
    assert authorized["result_status"] == "human_gate_authorized"
    assert authorized["evidence_json"]["gateway"]["external_browser_authorized"] is True

    resolved_response = client.post(
        f"/api/v1/rpa-gateway/requests/{run['id']}/decision",
        headers=headers,
        json={"decision": "human_control_resolved", "notes": "Captcha resuelto manualmente."},
    )
    assert resolved_response.status_code == 200
    resolved = resolved_response.json()
    assert resolved["status"] == "completed_with_warnings"
    assert resolved["result_status"] == "human_control_resolved"
    assert resolved["evidence_json"]["gateway"]["changes_applied"] == []

    requests = client.get("/api/v1/rpa-gateway/requests", headers=headers).json()
    assert [item["id"] for item in requests] == [run["id"]]

    pending_response = client.post("/api/v1/platform-contracts/import/arm-pending-review", headers=headers)
    assert pending_response.status_code == 200
    ctaima = next(
        item for item in client.get("/api/v1/platform-contracts/manifests", headers=headers).json()
        if item["platform_slug"] == "ctaima"
    )
    ctaima_account = next(
        item
        for item in client.get("/api/v1/platform-contracts/accounts", headers=headers).json()
        if item["manifest_id"] == ctaima["id"] and item["external_company_name"]
    )
    ctaima_request = client.post(
        "/api/v1/rpa-gateway/requests",
        headers=headers,
        json={
            "manifest_id": ctaima["id"],
            "account_proposal_id": ctaima_account["id"],
            "action_key": "read_external_status",
            "request_comment": "Recargar CTAIMA con pasarela humana.",
        },
    )
    assert ctaima_request.status_code == 201
    ctaima_run = ctaima_request.json()
    assert ctaima_run["platform_slug"] == "ctaima"
    assert ctaima_run["evidence_json"]["gateway"]["external_company_name"] == ctaima_account["external_company_name"]
    assert ctaima_run["evidence_json"]["gateway"]["visible_browser_required"] is True

    audit = client.get("/api/v1/audit", headers=headers).json()
    assert {entry["action"] for entry in audit} >= {
        "rpa_gateway.request_create",
        "rpa_gateway.human_decision",
        "rpa_gateway.launch_visible_browser",
    }


def test_company_scoped_dashboard_and_filters(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant Multi Empresa")
    company_a = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "Empresa A", "tax_id": "A11111111", "company_type": "contractor"},
    ).json()
    company_b = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "Empresa B", "tax_id": "B11111111", "company_type": "subcontractor"},
    ).json()
    worker_a = client.post(
        "/api/v1/workers",
        headers=headers,
        json={"company_id": company_a["id"], "first_name": "A", "last_name": "Uno"},
    ).json()
    worker_b = client.post(
        "/api/v1/workers",
        headers=headers,
        json={"company_id": company_b["id"], "first_name": "B", "last_name": "Dos"},
    ).json()
    document_type = client.post(
        "/api/v1/document-types",
        headers=headers,
        json={"code": "CAE.WORKER.TEST", "name": "Test", "entity_scope": "worker"},
    ).json()
    document_a = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_type": "worker",
            "entity_id": worker_a["id"],
        },
    ).json()
    client.post(
        f"/api/v1/documents/{document_a['id']}/versions",
        headers=headers,
        json={
            "file_storage_key": "local://a.pdf",
            "sha256": "d" * 64,
            "filename": "a.pdf",
        },
    )

    workers_a = client.get(f"/api/v1/workers?company_id={company_a['id']}", headers=headers).json()
    documents_a = client.get(f"/api/v1/documents?company_id={company_a['id']}", headers=headers).json()
    dashboard_a = client.get(
        f"/api/v1/dashboard/summary?company_id={company_a['id']}",
        headers=headers,
    ).json()
    company_summaries = client.get("/api/v1/dashboard/companies", headers=headers).json()

    assert [worker["id"] for worker in workers_a] == [worker_a["id"]]
    assert [document["id"] for document in documents_a] == [document_a["id"]]
    assert dashboard_a["company_id"] == company_a["id"]
    assert dashboard_a["companies"] == 1
    assert dashboard_a["workers"] == 1
    assert dashboard_a["documents"] == 1
    summary_by_company = {summary["company_id"]: summary for summary in company_summaries}
    assert summary_by_company[company_a["id"]]["documents"] == 1
    assert summary_by_company[company_b["id"]]["documents"] == 0
    assert worker_b["id"] not in [worker["id"] for worker in workers_a]


def test_user_can_access_multiple_companies_without_seeing_unassigned_companies(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant Gestoria")
    company_a = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "Sofidel", "tax_id": "A22222222", "company_type": "client"},
    ).json()
    company_b = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "Renault", "tax_id": "B22222222", "company_type": "client"},
    ).json()
    company_c = client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "Mercedes", "tax_id": "C22222222", "company_type": "client"},
    ).json()
    worker_a = client.post(
        "/api/v1/workers",
        headers=headers,
        json={"company_id": company_a["id"], "first_name": "A", "last_name": "Uno"},
    ).json()
    worker_b = client.post(
        "/api/v1/workers",
        headers=headers,
        json={"company_id": company_b["id"], "first_name": "B", "last_name": "Dos"},
    ).json()
    worker_c = client.post(
        "/api/v1/workers",
        headers=headers,
        json={"company_id": company_c["id"], "first_name": "C", "last_name": "Tres"},
    ).json()
    document_type = client.post(
        "/api/v1/document-types",
        headers=headers,
        json={"code": "CAE.COMPANY.ACCESS_TEST", "name": "Access", "entity_scope": "company"},
    ).json()
    document_a = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_type": "company",
            "entity_id": company_a["id"],
        },
    ).json()
    client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "document_type_id": document_type["id"],
            "entity_type": "company",
            "entity_id": company_c["id"],
        },
    ).json()
    user = client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": "operador@gestoria.invalid", "name": "Operador Gestoria"},
    ).json()
    for company in [company_a, company_b]:
        client.post(
            f"/api/v1/users/{user['id']}/company-access",
            headers=headers,
            json={
                "company_id": company["id"],
                "access_level": "manager",
                "role_name": "Gestoria",
                "permissions": ["company.read", "worker.read", "document.read"],
            },
        )

    user_headers = client.auth_headers_for_user(tenant["id"], user["id"])  # type: ignore[attr-defined]
    visible_companies = client.get("/api/v1/companies", headers=user_headers).json()
    visible_workers = client.get("/api/v1/workers", headers=user_headers).json()
    visible_documents = client.get("/api/v1/documents", headers=user_headers).json()
    access_detail = client.get(f"/api/v1/users/{user['id']}/company-access", headers=user_headers).json()
    dashboard = client.get("/api/v1/dashboard/summary", headers=user_headers).json()

    assert {company["id"] for company in visible_companies} == {company_a["id"], company_b["id"]}
    assert {worker["id"] for worker in visible_workers} == {worker_a["id"], worker_b["id"]}
    assert {document["id"] for document in visible_documents} == {document_a["id"]}
    assert {access["company_id"] for access in access_detail} == {company_a["id"], company_b["id"]}
    assert dashboard["companies"] == 2
    assert dashboard["workers"] == 2
    assert client.get(f"/api/v1/companies/{company_c['id']}", headers=user_headers).status_code == 403
    assert (
        client.post(
            "/api/v1/workers",
            headers=user_headers,
            json={"company_id": company_c["id"], "first_name": "No", "last_name": "Access"},
        ).status_code
        == 403
    )
    assert worker_c["id"] not in {worker["id"] for worker in visible_workers}


def test_admin_can_assign_users_to_platform_accounts(client: TestClient) -> None:
    tenant, admin_headers = _tenant_admin(client, "Tenant Plataformas")
    operator = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={"email": "operador-plataformas@example.invalid", "name": "Operador Plataformas"},
    ).json()

    overview = client.get("/api/v1/tenant-platforms/access", headers=admin_headers).json()
    mock_platform = next(platform for platform in overview if platform["platform_key"] == "mock_cae")
    assert {platform["platform_key"] for platform in overview} >= {"mock_cae", "dokify", "ctaima_cae"}
    assert any(method["connector_key"] == "connector_manual_export" for method in mock_platform["methods"])
    assert {method["connector_type"] for method in mock_platform["methods"]} == {"demo", "manual_export"}

    account = client.post(
        "/api/v1/tenant-platforms/accounts",
        headers=admin_headers,
        json={
            "external_platform_id": mock_platform["id"],
            "display_name": "Mock CAE pruebas",
            "auth_type": "manual",
            "encrypted_secret_ref": "env:SHOULD_NOT_LEAK",
            "mode": "send_receive",
            "dry_run": True,
            "manual_approval_required": True,
        },
    ).json()
    assert "encrypted_secret_ref" not in account

    access = client.post(
        f"/api/v1/tenant-platforms/accounts/{account['id']}/user-access",
        headers=admin_headers,
        json={
            "user_id": operator["id"],
            "access_level": "operator",
            "permissions": ["connector.read", "connector.execute"],
            "allowed_operations": ["generate_manual_export"],
        },
    ).json()
    assert access["platform_account_id"] == account["id"]
    assert access["user_id"] == operator["id"]
    assert access["allowed_operations"] == ["generate_manual_export"]

    assigned = client.get(
        f"/api/v1/tenant-platforms/accounts/{account['id']}/user-access",
        headers=admin_headers,
    ).json()
    assert assigned[0]["user_email"] == operator["email"]
    overview_after = client.get("/api/v1/tenant-platforms/access", headers=admin_headers).json()
    mock_after = next(platform for platform in overview_after if platform["platform_key"] == "mock_cae")
    assert mock_after["accounts"][0]["assigned_users"][0]["access_level"] == "operator"

    revoke = client.delete(
        f"/api/v1/tenant-platforms/accounts/{account['id']}/user-access/{operator['id']}",
        headers=admin_headers,
    )
    assert revoke.status_code == 204
    audit = client.get("/api/v1/audit", headers=admin_headers).json()
    assert "platform_account_user_access.upsert" in {entry["action"] for entry in audit}
    assert "platform_account_user_access.revoke" in {entry["action"] for entry in audit}
    assert "SHOULD_NOT_LEAK" not in str(audit)


def test_granular_permission_grants_cross_multiple_companies(client: TestClient) -> None:
    tenant, admin_headers = _tenant_admin(client, "Tenant ACL Granular")
    operator = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={"email": "operador-acl@example.invalid", "name": "Operador ACL"},
    ).json()
    company_a = client.post(
        "/api/v1/companies",
        headers=admin_headers,
        json={"name": "Empresa ACL A", "tax_id": "ACL-A", "company_type": "client"},
    ).json()
    company_b = client.post(
        "/api/v1/companies",
        headers=admin_headers,
        json={"name": "Empresa ACL B", "tax_id": "ACL-B", "company_type": "client"},
    ).json()
    company_c = client.post(
        "/api/v1/companies",
        headers=admin_headers,
        json={"name": "Empresa ACL C", "tax_id": "ACL-C", "company_type": "client"},
    ).json()
    grant_payloads = [
        {
            "scope_type": "company",
            "scope_id": company_a["id"],
            "permission": "company.read",
            "effect": "allow",
            "reason": "Visibilidad operativa A",
        },
        {
            "scope_type": "company",
            "scope_id": company_a["id"],
            "permission": "document.validate",
            "effect": "allow",
        },
        {
            "scope_type": "company",
            "scope_id": company_b["id"],
            "permission": "company.read",
            "effect": "allow",
        },
        {
            "scope_type": "company",
            "scope_id": company_b["id"],
            "permission": "document.write",
            "effect": "allow",
        },
        {
            "scope_type": "company",
            "scope_id": company_b["id"],
            "permission": "document.write",
            "effect": "deny",
            "reason": "B requiere validacion previa",
        },
    ]
    for payload in grant_payloads:
        response = client.post(
            f"/api/v1/users/{operator['id']}/permission-grants",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 201

    operator_headers = client.auth_headers_for_user(tenant["id"], operator["id"])  # type: ignore[attr-defined]
    visible_companies = client.get("/api/v1/companies", headers=operator_headers).json()
    effective = client.get(
        f"/api/v1/users/{operator['id']}/effective-permissions",
        headers=operator_headers,
    ).json()
    company_b_effective = client.get(
        f"/api/v1/users/{operator['id']}/effective-permissions?company_id={company_b['id']}",
        headers=operator_headers,
    ).json()

    assert {company["id"] for company in visible_companies} == {company_a["id"], company_b["id"]}
    assert company_c["id"] not in {company["company_id"] for company in effective["company_permissions"]}
    matrix = {row["company_id"]: row for row in effective["company_permissions"]}
    assert "document.validate" in matrix[company_a["id"]]["permissions"]
    assert "document.write" not in matrix[company_b["id"]]["permissions"]
    assert "document.write" in matrix[company_b["id"]]["denied_permissions"]
    assert company_b_effective["company_permissions"][0]["company_id"] == company_b["id"]
    assert client.get(
        f"/api/v1/users/{operator['id']}/effective-permissions?company_id={company_c['id']}",
        headers=operator_headers,
    ).status_code == 403

    grants = client.get(
        f"/api/v1/users/{operator['id']}/permission-grants",
        headers=admin_headers,
    ).json()
    revoke = client.delete(
        f"/api/v1/users/{operator['id']}/permission-grants/{grants[0]['id']}",
        headers=admin_headers,
    )
    assert revoke.status_code == 204
    audit = client.get("/api/v1/audit", headers=admin_headers).json()
    assert "user_permission_grant.create" in {entry["action"] for entry in audit}
    assert "user_permission_grant.revoke" in {entry["action"] for entry in audit}


def test_saas_and_reseller_management_endpoints(client: TestClient) -> None:
    tenant, _tenant_headers = _tenant_admin(client, "Tenant Revendido")
    system_headers = client.system_auth_headers()  # type: ignore[attr-defined]
    assert client.get("/api/v1/saas/overview").status_code == 401
    plan = client.post(
        "/api/v1/saas/plans",
        headers=system_headers,
        json={
            "plan_key": "reseller_test",
            "name": "Reseller Test",
            "max_tenants": None,
            "max_companies": None,
            "max_users": None,
            "features": ["multi_tenant_resale", "client_company_portal"],
        },
    ).json()
    reseller = client.post(
        "/api/v1/saas/resellers",
        headers=system_headers,
        json={"name": "Gestoria Partner", "tax_id": "GESTORIA-TEST", "contact_email": "partner@example.invalid"},
    ).json()
    profile = client.post(
        "/api/v1/saas/tenant-profiles",
        headers=system_headers,
        json={
            "tenant_id": tenant["id"],
            "plan_id": plan["id"],
            "reseller_id": reseller["id"],
            "billing_mode": "reseller_managed",
            "seats_purchased": 50,
            "status": "active",
        },
    ).json()
    overview = client.get("/api/v1/saas/overview", headers=system_headers).json()
    reseller_profiles = client.get(
        f"/api/v1/saas/resellers/{reseller['id']}/tenant-profiles",
        headers=system_headers,
    ).json()

    assert profile["billing_mode"] == "reseller_managed"
    assert profile["reseller_id"] == reseller["id"]
    assert overview["resellers"] == 1
    assert overview["reseller_managed_tenants"] == 1
    assert reseller_profiles[0]["tenant_id"] == tenant["id"]


def test_google_sso_provider_configuration_and_authorization_start(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant Google SSO")
    provider = client.post(
        "/api/v1/auth/sso/providers/google",
        headers=headers,
        json={
            "client_id": "test-client.apps.googleusercontent.com",
            "encrypted_client_secret_ref": "env:IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET",
            "allowed_domains": ["Example.com"],
            "auto_provision": True,
            "status": "active",
        },
    ).json()

    assert provider["provider_key"] == "google"
    assert provider["issuer"] == "https://accounts.google.com"
    assert provider["discovery_url"] == "https://accounts.google.com/.well-known/openid-configuration"
    assert provider["allowed_domains"] == ["example.com"]
    assert "encrypted_client_secret_ref" not in provider

    start = client.post(
        "/api/v1/auth/sso/google/start",
        headers=headers,
        json={
            "redirect_uri": "http://localhost:3000/auth/google/callback",
            "next_url": "/admin",
        },
    ).json()
    parsed = urlparse(start["authorization_url"])
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/v2/auth"
    assert query["client_id"] == ["test-client.apps.googleusercontent.com"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid profile email"]
    assert query["state"] == [start["state"]]
    assert query["code_challenge_method"] == ["S256"]
    assert query["hd"] == ["example.com"]

    blocked_redirect = client.post(
        "/api/v1/auth/sso/google/start",
        headers=headers,
        json={"redirect_uri": "https://evil.example/callback", "next_url": "/admin"},
    )
    assert blocked_redirect.status_code == 422

    providers = client.get("/api/v1/auth/sso/providers", headers=headers).json()
    assert providers[0]["provider_key"] == "google"
    audit = client.get("/api/v1/audit", headers=headers).json()
    assert "IPRL_CAE_GOOGLE_OIDC_CLIENT_SECRET" not in str(audit)


def test_google_sso_start_requires_active_provider(client: TestClient) -> None:
    tenant, headers = _tenant_admin(client, "Tenant Google Disabled")
    client.post(
        "/api/v1/auth/sso/providers/google",
        headers=headers,
        json={
            "client_id": "test-client.apps.googleusercontent.com",
            "status": "disabled",
        },
    )
    response = client.post(
        "/api/v1/auth/sso/google/start",
        headers=headers,
        json={"redirect_uri": "http://localhost:3000/auth/google/callback"},
    )

    assert response.status_code == 409
