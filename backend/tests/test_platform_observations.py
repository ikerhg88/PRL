from __future__ import annotations

import asyncio

from pytest import MonkeyPatch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import (
    Company,
    Document,
    DocumentType,
    DocumentVersion,
    ExternalPlatform,
    PlatformAccount,
    PlatformObservedDocumentRequest,
    PlatformObservedEntity,
    PlatformReviewRun,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    PlatformWritePath,
    Tenant,
    Worker,
    WorkerPlatformRegistration,
)
from app.services import platform_reconciliation
from app.services.platform_observations import (
    build_observed_state_summary,
    sync_readonly_capture_observations,
)
from app.services.platform_write_maturation import mature_platform_write_readiness
from app.services.platform_write_probe_matrix import build_platform_write_probe_matrix


def test_sync_readonly_capture_observations_normalizes_workers_and_document_requests() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with TestingSessionLocal() as session:
        tenant = Tenant(name="ARM", tax_id="B00000000", status="active")
        session.add(tenant)
        session.flush()
        company = Company(tenant_id=tenant.id, name="ARM Industrial Assemblies, S.L.", company_type="own")
        session.add(company)
        platform = ExternalPlatform(platform_key="ctaima_cae", name="CTAIMA / CTAIMA CAE", status="active")
        session.add(platform)
        session.flush()
        worker = Worker(
            tenant_id=tenant.id,
            company_id=company.id,
            first_name="Eleder",
            last_name="Bilbao Egusquiza",
            identifier_type="dni",
            identifier_value="78870388F",
            identifier_last4="388F",
            work_position="TECNICO AUTOMATIZACION",
            status="active",
        )
        document_type = DocumentType(
            tenant_id=tenant.id,
            code="ARM.WORKER.EPI_DELIVERY",
            name="Entrega de EPIs",
            entity_scope="worker",
            requires_expiration=False,
        )
        account = PlatformAccount(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            display_name="CTAIMA / Sofidel",
            auth_type="encrypted_db_ref",
            mode="send_receive",
        )
        session.add_all([worker, document_type, account])
        session.flush()
        document = Document(
            tenant_id=tenant.id,
            document_type_id=document_type.id,
            entity_type="worker",
            entity_id=worker.id,
            status_internal="valid_internal",
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            file_storage_key="local://epi.pdf",
            sha256="a" * 64,
            filename="epi.pdf",
            mime_type="application/pdf",
            size_bytes=123,
            source="import",
        )
        session.add(version)
        session.flush()
        document.current_version_id = version.id
        manifest = PlatformRpaManifest(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            platform_slug="ctaima",
            platform_name="CTAIMA / CTAIMA CAE",
            hosts=["www.ctaimacae.net"],
            entry_urls=["https://www.ctaimacae.net/CTAIMA_CAE/connections/valida.asp"],
            allowed_operations=["read_external_status", "upload_worker_document"],
            allowed_entity_types=["worker", "document"],
            status="active",
        )
        session.add(manifest)
        session.flush()
        proposal = PlatformRpaAccountProposal(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            platform_account_id=account.id,
            source_platform_account_id="ctaima_arm_sofidel",
            external_company_name="SOFIDEL",
            entry_url="https://www.ctaimacae.net/CTAIMA_CAE/connections/valida.asp",
            host="www.ctaimacae.net",
            status="active",
            account_status="active_in_source",
            allowed_operations=["read_external_status", "upload_worker_document"],
            allowed_entity_types=["worker", "document"],
        )
        schedule = PlatformReviewSchedule(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            enabled=True,
            status="active",
        )
        session.add_all([proposal, schedule])
        session.flush()
        run = PlatformReviewRun(
            tenant_id=tenant.id,
            schedule_id=schedule.id,
            manifest_id=manifest.id,
            account_proposal_id=proposal.id,
            external_platform_id=platform.id,
            platform_slug="ctaima",
            platform_name="CTAIMA / CTAIMA CAE",
            operation="read_external_status",
            trigger_source="human_gateway_request",
            status="human_action_required",
            evidence_json={},
        )
        session.add(run)
        session.flush()

        result = sync_readonly_capture_observations(
            session,
            tenant_id=tenant.id,
            run=run,
            capture_summary={
                "observed_workers": [
                    {
                        "display_name": "BILBAO , ELEDER",
                        "identifier_last4": "388F",
                        "work_position": "TECNICO AUTOMATIZACION",
                        "active": True,
                        "external_worker_id": "2506",
                    }
                ],
                "observed_document_requests": [
                    {
                        "external_requirement_id": "ctaima-sofidel-epi-eleder",
                        "entity_scope": "worker",
                        "worker_display_name": "BILBAO , ELEDER",
                        "identifier_last4": "388F",
                        "document_type": "Entrega de EPIs",
                        "external_status": "pendiente",
                        "rejection_reason": "Falta entrega de EPIs",
                    }
                ],
            },
        )
        session.flush()

        entity = session.scalar(select(PlatformObservedEntity))
        request = session.scalar(select(PlatformObservedDocumentRequest))
        summary = build_observed_state_summary(session, tenant_id=tenant.id, account_proposal_id=proposal.id)

        assert result["entities"] == {"seen": 1, "matched": 1, "upserted": 1, "skipped": 0}
        assert result["document_requests"]["seen"] == 1
        assert result["document_requests"]["matched_entities"] == 1
        assert result["document_requests"]["matched_document_types"] == 1
        assert result["document_requests"]["upserted"] == 1
        assert entity is not None
        assert entity.local_worker_id == worker.id
        assert entity.external_status == "accepted"
        assert request is not None
        assert request.local_worker_id == worker.id
        assert request.document_type_id == document_type.id
        assert request.matched_document_version_id == version.id
        assert request.external_status == "manual_required"
        assert request.severity == "red"
        assert summary["document_requests"] == 1
        assert summary["actionable_document_requests"] == 1

        sync_readonly_capture_observations(
            session,
            tenant_id=tenant.id,
            run=run,
            capture_summary={
                "observed_document_requests": [
                    {
                        "external_requirement_id": "ctaima-sofidel-epi-eleder",
                        "entity_scope": "worker",
                        "worker_display_name": "BILBAO , ELEDER",
                        "identifier_last4": "388F",
                        "document_type": "Entrega de EPIs",
                        "external_status": "validado",
                    }
                ],
            },
        )
        session.flush()

        requests = list(session.scalars(select(PlatformObservedDocumentRequest)))
        assert len(requests) == 1
        assert requests[0].external_status == "accepted"
        assert requests[0].severity == "green"


def test_platform_reconciliation_map_marks_context_ready_only_with_read_write_evidence(monkeypatch: MonkeyPatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with TestingSessionLocal() as session:
        tenant = Tenant(name="ARM", tax_id="B00000000", status="active")
        session.add(tenant)
        session.flush()
        platform = ExternalPlatform(platform_key="ctaima_cae", name="CTAIMA / CTAIMA CAE", status="active")
        session.add(platform)
        session.flush()
        account = PlatformAccount(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            display_name="CTAIMA / Sofidel",
            auth_type="encrypted_db_ref",
            mode="send_receive",
        )
        session.add(account)
        session.flush()
        manifest = PlatformRpaManifest(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            platform_slug="ctaima",
            platform_name="CTAIMA / CTAIMA CAE",
            hosts=["www.ctaimacae.net"],
            entry_urls=["https://www.ctaimacae.net/CTAIMA_CAE/connections/valida.asp"],
            allowed_operations=["read_external_status", "upsert_worker", "upload_worker_document", "upload_company_document"],
            allowed_entity_types=["company", "worker", "document"],
            status="active",
        )
        session.add(manifest)
        session.flush()
        proposal = PlatformRpaAccountProposal(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            platform_account_id=account.id,
            source_platform_account_id="ctaima_arm_sofidel",
            external_company_name="SOFIDEL",
            entry_url="https://www.ctaimacae.net/CTAIMA_CAE/connections/valida.asp",
            host="www.ctaimacae.net",
            status="active",
            account_status="active_in_source",
            allowed_operations=["read_external_status", "upsert_worker", "upload_worker_document", "upload_company_document"],
            allowed_entity_types=["company", "worker", "document"],
        )
        schedule = PlatformReviewSchedule(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            enabled=True,
            status="scheduled",
            last_result_status="readonly_capture_synced",
            last_result_summary="Lectura sincronizada.",
        )
        session.add_all([proposal, schedule])
        session.flush()
        session.add(
            PlatformObservedEntity(
                tenant_id=tenant.id,
                manifest_id=manifest.id,
                account_proposal_id=proposal.id,
                external_platform_id=platform.id,
                platform_account_id=account.id,
                entity_type="worker",
                external_entity_key="ctaima-worker-2506",
                external_display_name="Eleder Bilbao Egusquiza",
                external_status="accepted",
                status_color="green",
                confidence=95,
            )
        )
        for operation in ("upsert_worker", "upload_worker_document", "upload_company_document"):
            session.add(
                PlatformWritePath(
                    tenant_id=tenant.id,
                    manifest_id=manifest.id,
                    account_proposal_id=proposal.id,
                    external_platform_id=platform.id,
                    platform_account_id=account.id,
                    operation=operation,
                    entity_scope="worker" if operation != "upload_company_document" else "company",
                    path_label=f"{operation} approved path",
                    host="www.ctaimacae.net",
                    entry_path="/mapped/read-write/path",
                    field_paths_json={"field": "observed"},
                    readback_paths_json={"list": "observed"},
                    source_evidence_ref="capture://redacted",
                    review_status="approved",
                    status="approved",
                )
            )
        session.flush()

        monkeypatch.setattr(
            platform_reconciliation,
            "build_platform_data_coverage",
            lambda *_args, **_kwargs: {
                "contexts": [
                    {
                        "manifest_id": manifest.id,
                        "account_proposal_id": proposal.id,
                        "external_company_name": "SOFIDEL",
                        "trace_label": "CTAIMA / SOFIDEL",
                        "host": "www.ctaimacae.net",
                        "entry_url_configured": True,
                    }
                ]
            },
        )
        monkeypatch.setattr(
            platform_reconciliation,
            "build_platform_edit_methods",
            lambda *_args, **_kwargs: {
                "contexts": [
                    {
                        "manifest_id": manifest.id,
                        "account_proposal_id": proposal.id,
                        "operations": [
                            {"operation": "upsert_worker", "status": "ready_for_preview"},
                            {"operation": "upload_worker_document", "status": "ready_for_preview"},
                            {"operation": "upload_company_document", "status": "ready_for_preview"},
                        ],
                    }
                ]
            },
        )
        monkeypatch.setattr(
            platform_reconciliation,
            "build_validation_surface_map",
            lambda *_args, **_kwargs: {
                "platforms": [
                    {
                        "platform_slug": "ctaima",
                        "summary": {"worker_readback": 1, "document_requests": 1},
                    }
                ]
            },
        )
        monkeypatch.setattr(
            platform_reconciliation,
            "live_write_adapter_catalog",
            lambda *_args, **_kwargs: {
                "rows": [
                    {
                        "manifest_id": manifest.id,
                        "live_adapter_status": "specific_live_adapter_available",
                        "helper_status": "live_implemented",
                    }
                ]
            },
        )

        result = platform_reconciliation.build_platform_reconciliation_map(session, tenant_id=tenant.id)

        assert result["policy"]["target"] == "map_all_active_platforms_for_read_and_write"
        assert result["summary"]["contexts"] == 1
        assert result["summary"]["read_ready"] == 1
        assert result["summary"]["write_ready"] == 1
        assert result["summary"]["fully_mapped_for_read_write"] == 1
        row = result["rows"][0]
        assert row["read_status"] == "ready"
        assert row["write_status"] == "ready"
        assert row["mapping_status"] == "complete"
        assert row["fully_mapped_for_read_write"] is True
        assert row["write_paths"]["approved"] == 3
        assert row["missing_core_operations"] == []
        assert row["blockers"] == []


def test_write_probe_matrix_blocks_worker_already_registered() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with TestingSessionLocal() as session:
        tenant = Tenant(name="ARM", tax_id="B00000000", status="active")
        session.add(tenant)
        session.flush()
        company = Company(tenant_id=tenant.id, name="ARM Industrial Assemblies, S.L.", company_type="own")
        platform = ExternalPlatform(platform_key="sixconecta", name="6conecta", status="active")
        session.add_all([company, platform])
        session.flush()
        worker = Worker(
            tenant_id=tenant.id,
            company_id=company.id,
            first_name="Joan",
            last_name="Ramos Pujol",
            identifier_type="dni",
            identifier_value="33896917T",
            identifier_last4="917T",
            nationality="ES",
            contract_type="Indefinido",
            work_position="TECNICO AUTOMATIZACION",
            status="active",
        )
        platform_account = PlatformAccount(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            display_name="6conecta / Velartia",
            auth_type="encrypted_db_ref",
            mode="send_receive",
        )
        session.add_all([worker, platform_account])
        session.flush()
        manifest = PlatformRpaManifest(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            platform_slug="seisconecta",
            platform_name="6conecta",
            hosts=["www.6conecta.com"],
            entry_urls=["https://www.6conecta.com"],
            allowed_operations=["upsert_worker"],
            allowed_entity_types=["worker"],
            status="active",
        )
        session.add(manifest)
        session.flush()
        account = PlatformRpaAccountProposal(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            platform_account_id=platform_account.id,
            source_platform_account_id="velartia",
            external_company_name="VELARTIA",
            entry_url="https://www.6conecta.com",
            host="www.6conecta.com",
            status="active",
            account_status="active_in_source",
            allowed_operations=["upsert_worker"],
            allowed_entity_types=["worker"],
        )
        session.add(account)
        session.flush()
        sixconecta_required_keys = (
            "worker.identifier_value",
            "worker.first_name",
            "worker.last_name",
            "worker.nationality",
            "worker.contract_type",
            "worker.work_position",
        )
        session.add(
            PlatformWritePath(
                tenant_id=tenant.id,
                manifest_id=manifest.id,
                account_proposal_id=account.id,
                external_platform_id=platform.id,
                platform_account_id=platform_account.id,
                operation="upsert_worker",
                entity_scope="worker",
                path_kind="editable_form",
                path_label="Alta trabajador 6conecta revisada",
                host="www.6conecta.com",
                entry_path="/captured/worker-edit",
                field_paths_json={
                    key: {
                        "strategy": "observed_label_or_stable_name",
                        "label": key,
                        "source": "redacted_capture",
                    }
                    for key in sixconecta_required_keys
                },
                selector_map_json={
                    "submit": {
                        "strategy": "observed_button",
                        "label": "Guardar",
                    }
                },
                readback_paths_json={
                    "worker.identifier_value": {
                        "strategy": "search_readback",
                        "label": "DNI/NIE",
                    }
                },
                source_evidence_ref="platform_review_run:test-redacted-capture",
                review_status="approved",
                status="approved_for_preview_and_readback",
                metadata_json={"source": "unit_test_redacted_capture"},
            )
        )
        session.add(
            WorkerPlatformRegistration(
                tenant_id=tenant.id,
                worker_id=worker.id,
                external_platform_id=platform.id,
                platform_account_id=platform_account.id,
                platform_name=platform.name,
                external_worker_id="5711223",
                registration_status="confirmed",
                source="connector_rpa_seisconecta_write",
            )
        )
        session.commit()

        matrix = asyncio.run(
            build_platform_write_probe_matrix(
                session,
                tenant_id=tenant.id,
                company_id=company.id,
                worker_id=worker.id,
                operations=("upsert_worker",),
            )
        )

        assert matrix["summary"]["external_writes_executed"] == 0
        assert matrix["rows"][0]["status"] == "already_registered"
        assert matrix["rows"][0]["preview_ready"] is True
        assert matrix["rows"][0]["mapping_ready"] is True
        assert matrix["rows"][0]["local_data_ready"] is True
        assert "ya consta" in matrix["rows"][0]["next_action"]


def test_write_maturation_approves_only_valid_captured_paths() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with TestingSessionLocal() as session:
        tenant = Tenant(name="ARM", tax_id="B00000000", status="active")
        session.add(tenant)
        session.flush()
        platform = ExternalPlatform(platform_key="ctaima_cae", name="CTAIMA / CTAIMA CAE", status="active")
        session.add(platform)
        session.flush()
        platform_account = PlatformAccount(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            display_name="CTAIMA / Sofidel",
            auth_type="encrypted_db_ref",
            mode="send_receive",
        )
        session.add(platform_account)
        session.flush()
        manifest = PlatformRpaManifest(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            platform_slug="ctaima",
            platform_name="CTAIMA / CTAIMA CAE",
            hosts=["www.ctaimacae.net"],
            entry_urls=["https://www.ctaimacae.net/CTAIMA_CAE/connections/valida.asp"],
            allowed_operations=["upsert_worker"],
            allowed_entity_types=["worker"],
            status="active",
        )
        session.add(manifest)
        session.flush()
        schedule = PlatformReviewSchedule(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            enabled=True,
            status="scheduled",
        )
        session.add(schedule)
        session.flush()
        account = PlatformRpaAccountProposal(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            platform_account_id=platform_account.id,
            source_platform_account_id="ctaima_sofidel",
            external_company_name="SOFIDEL",
            entry_url="https://www.ctaimacae.net/CTAIMA_CAE/connections/valida.asp",
            host="www.ctaimacae.net",
            status="active",
            account_status="active_in_source",
            allowed_operations=["upsert_worker"],
            allowed_entity_types=["worker"],
        )
        session.add(account)
        session.flush()
        run = PlatformReviewRun(
            tenant_id=tenant.id,
            schedule_id=schedule.id,
            manifest_id=manifest.id,
            account_proposal_id=account.id,
            external_platform_id=platform.id,
            platform_slug=manifest.platform_slug,
            platform_name=manifest.platform_name,
            operation="capture_write_screen",
            trigger_source="human_gateway_request",
            status="human_action_required",
            dry_run=True,
            manual_approval_required=True,
            evidence_json={
                "gateway": {
                    "requested_action": "capture_write_screen",
                    "external_browser_authorized": True,
                }
            },
        )
        session.add(run)
        session.flush()
        path = PlatformWritePath(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            account_proposal_id=account.id,
            external_platform_id=platform.id,
            platform_account_id=platform_account.id,
            capture_run_id=run.id,
            operation="upsert_worker",
            entity_scope="worker",
            path_kind="editable_form_capture",
            path_label="captured worker form",
            host="www.ctaimacae.net",
            entry_path="https://www.ctaimacae.net/redacted-worker-form",
            field_paths_json={
                "worker.identifier_value": {"strategy": "observed_label_or_stable_name", "raw_label": "DNI"},
            },
            selector_map_json={},
            readback_paths_json={
                "worker.identifier_value": {"strategy": "search_readback", "raw_label": "DNI"},
            },
            source_evidence_ref=f"platform_review_run:{run.id}",
            review_status="pending_review",
            status="captured_pending_review",
            metadata_json={"source": "gateway_readonly_capture"},
        )
        session.add(path)
        session.commit()

        result = mature_platform_write_readiness(
            session,
            tenant_id=tenant.id,
            actor_user_id=None,
            account_proposal_ids=[account.id],
            create_missing_capture_requests=False,
            authorize_capture_requests=True,
            launch_browsers=False,
            sync_available_captures=False,
            approve_valid_captured_paths=True,
        )

        session.refresh(path)
        assert result["summary"]["write_paths_approved"] == 1
        assert result["summary"]["external_write_executed"] == 0
        assert path.review_status == "approved"
        assert path.status == "approved_for_preview_and_readback"
