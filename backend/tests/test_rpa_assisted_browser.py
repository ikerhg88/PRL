from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import (
    Company,
    ExternalPlatform,
    PlatformAccount,
    PlatformReviewRun,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    Tenant,
    Worker,
    WorkerPlatformRegistration,
)
from app.services.rpa_assisted_browser import _sync_observed_worker_registrations


def test_assisted_browser_derives_egestiona_client_from_entry_url() -> None:
    module = _load_assisted_browser_module()

    assert module.client_hint_from_entry_url("https://faurecia.egestiona.com/login?origen=subcontrata") == "faurecia"
    assert module.client_hint_from_entry_url("HTTPS://FAGOREDERLAN.EGESTIONA.ES/") == "fagorederlan"
    assert module.client_hint_from_entry_url("https://www.example.invalid/login") is None


def test_assisted_browser_prefers_configured_client_hint_over_host_default() -> None:
    module = _load_assisted_browser_module()
    credentials = type(
        "Credentials",
        (),
        {"metadata": {"login_hints": {"client": "configured-client"}}},
    )()

    assert (
        module.login_hint_value(credentials, "https://faurecia.egestiona.com/login?origen=subcontrata", "client")
        == "configured-client"
    )


def test_sync_observed_worker_registration_confirms_existing_external_worker() -> None:
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
        account = PlatformAccount(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            display_name="CTAIMA / Mitsubishi",
            auth_type="encrypted_db_ref",
            mode="send_receive",
        )
        session.add_all([worker, account])
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
        proposal = PlatformRpaAccountProposal(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            platform_account_id=account.id,
            source_platform_account_id="ctaima_arm_mitsubishi",
            external_company_name="Mitsubishi",
            entry_url="https://www.ctaimacae.net/CTAIMA_CAE/connections/valida.asp",
            host="www.ctaimacae.net",
            status="active",
            account_status="active_in_source",
            allowed_operations=["upsert_worker"],
            allowed_entity_types=["worker"],
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
            operation="capture_write_screen",
            trigger_source="human_gateway_request",
            status="human_action_required",
            evidence_json={},
        )
        session.add(run)
        session.flush()

        result = _sync_observed_worker_registrations(
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
                ]
            },
        )
        session.flush()

        registration = session.scalar(select(WorkerPlatformRegistration))
        assert result == {"seen": 1, "matched": 1, "upserted": 1, "skipped": 0}
        assert registration is not None
        assert registration.worker_id == worker.id
        assert registration.platform_account_id == account.id
        assert registration.registration_status == "confirmed"
        assert registration.source == "rpa_readback_capture"
        assert registration.external_worker_id == "2506"


def _load_assisted_browser_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "assisted_platform_browser.py"
    spec = importlib.util.spec_from_file_location("assisted_platform_browser_for_tests", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
