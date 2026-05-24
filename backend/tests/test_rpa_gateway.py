from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import (
    Company,
    ExternalPlatform,
    PlatformAccount,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    Tenant,
    Worker,
    WorkerPlatformRegistration,
)
from app.services.rpa_gateway import _target_context


def test_target_context_does_not_reuse_pending_registration_from_other_account() -> None:
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
        platform = ExternalPlatform(platform_key="ctaima_cae", name="CTAIMA / CTAIMA CAE", status="active")
        session.add_all([company, platform])
        session.flush()
        manifest = PlatformRpaManifest(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            platform_slug="ctaima",
            platform_name="CTAIMA / CTAIMA CAE",
            status="active",
        )
        sofidel_account = PlatformAccount(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            display_name="CTAIMA / SOFIDEL",
            status="active",
            mode="send_receive",
        )
        grupo_account = PlatformAccount(
            tenant_id=tenant.id,
            external_platform_id=platform.id,
            display_name="CTAIMA / GRUPO INVERBUR",
            status="active",
            mode="send_receive",
        )
        session.add_all([manifest, sofidel_account, grupo_account])
        session.flush()
        sofidel_proposal = PlatformRpaAccountProposal(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            platform_account_id=sofidel_account.id,
            source_platform_account_id="ctaima_sofidel",
            external_company_name="SOFIDEL,ITP,RENAULT,SEAT,MERCEDES",
            entry_url="https://www.ctaimacae.net/CTAIMA_CAE/connections/valida.asp",
            host="www.ctaimacae.net",
            status="active",
            account_status="active_in_source",
        )
        grupo_proposal = PlatformRpaAccountProposal(
            tenant_id=tenant.id,
            manifest_id=manifest.id,
            external_platform_id=platform.id,
            platform_account_id=grupo_account.id,
            source_platform_account_id="ctaima_grupo_inverbur",
            external_company_name="GRUPO INVERBUR, MITSUBISHI, BRIDGESTONE, GONBARRI",
            entry_url="https://www.ctaimacae.net/CTAIMA_CAE/connections/valida.asp",
            host="www.ctaimacae.net",
            status="active",
            account_status="active_in_source",
        )
        worker = Worker(
            tenant_id=tenant.id,
            company_id=company.id,
            first_name="Eleder",
            last_name="Bilbao Egusquiza",
            identifier_last4="388F",
            status="active",
        )
        session.add_all([sofidel_proposal, grupo_proposal, worker])
        session.flush()
        session.add(
            WorkerPlatformRegistration(
                tenant_id=tenant.id,
                worker_id=worker.id,
                platform_account_id=sofidel_account.id,
                external_platform_id=platform.id,
                platform_name="CTAIMA / CTAIMA CAE",
                registration_status="missing_required_document",
                assignment_scope="SOFIDEL",
                source="manual_observation",
            )
        )
        session.flush()

        assert (
            _target_context(session, tenant_id=tenant.id, manifest=manifest, account=grupo_proposal)
            == "GRUPO INVERBUR, MITSUBISHI, BRIDGESTONE, GONBARRI"
        )
        assert _target_context(session, tenant_id=tenant.id, manifest=manifest, account=sofidel_proposal) == "SOFIDEL"
