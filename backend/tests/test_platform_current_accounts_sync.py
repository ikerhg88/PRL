from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    ExternalPlatform,
    PlatformAccount,
    PlatformReviewSchedule,
    PlatformRpaAccountProposal,
    PlatformRpaManifest,
    Tenant,
)
from app.services.platform_current_accounts_sync import (
    ACTIVE_ACCOUNT_STATUS,
    INACTIVE_ACCOUNT_STATUS,
    CurrentPlatformRow,
    load_current_platform_rows,
    sync_current_platform_accounts,
)
from app.services.platform_credentials import resolve_platform_credentials


def test_sync_current_platform_accounts_activates_excel_rows_and_marks_rest_baja(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(tmp_path / "documents"))
    get_settings.cache_clear()
    SessionLocal = _session_factory()
    with SessionLocal() as session:
        tenant = Tenant(name="Tenant", tax_id="T1", status="active")
        session.add(tenant)
        session.flush()
        active_account = _proposal(session, tenant_id=tenant.id, slug="e_coordina", name="e-coordina", company="ARITEX")
        inactive_account = _proposal(session, tenant_id=tenant.id, slug="nomio", name="Nomio", company="NOMIO")
        result = sync_current_platform_accounts(
            session,
            tenant_id=tenant.id,
            actor_user_id=None,
            source_path=tmp_path / "usuarios.xlsx",
            rows=[
                CurrentPlatformRow(
                    source_row=2,
                    external_company_name="ARITEX",
                    entry_url="https://v5.e-coordina.com/aritex",
                    host="v5.e-coordina.com",
                    platform_slug="e_coordina",
                    user_hint_masked="B9***43",
                    has_password=True,
                    username="B95868543",
                    password="secret",
                )
            ],
        )
        session.commit()

        session.refresh(active_account)
        session.refresh(inactive_account)
        assert result.accounts_activated == 1
        assert result.accounts_marked_baja == 1
        assert active_account.status == ACTIVE_ACCOUNT_STATUS
        assert active_account.account_status == "active_in_source"
        assert active_account.user_hint_masked == "B9***43"
        assert active_account.credential_secret_ref is not None
        assert active_account.credential_secret_ref.startswith("enc:v1:")
        resolved = resolve_platform_credentials(
            secret_ref=active_account.credential_secret_ref,
            platform_account_id=active_account.source_platform_account_id,
        )
        assert resolved.credentials is not None
        assert resolved.credentials.username == "B95868543"
        assert resolved.credentials.password == "secret"
        assert resolved.credentials.metadata["source"] == "current_platform_excel"
        assert resolved.credentials.metadata["source_row"] == 2
        assert inactive_account.status == INACTIVE_ACCOUNT_STATUS
        assert inactive_account.account_status == INACTIVE_ACCOUNT_STATUS
        active_platform_account = session.get(PlatformAccount, active_account.platform_account_id)
        inactive_platform_account = session.get(PlatformAccount, inactive_account.platform_account_id)
        assert active_platform_account is not None and active_platform_account.mode == "send_receive"
        assert active_platform_account.auth_type == "encrypted_db_ref"
        assert active_platform_account.encrypted_secret_ref == (
            f"db://platform_rpa_account_proposals/{active_account.id}/credential_secret_ref"
        )
        assert inactive_platform_account is not None and inactive_platform_account.mode == "disabled"
        schedules = list(session.scalars(select(PlatformReviewSchedule).order_by(PlatformReviewSchedule.id)))
        assert [(schedule.enabled, schedule.status) for schedule in schedules] == [
            (True, "scheduled"),
            (False, INACTIVE_ACCOUNT_STATUS),
        ]


def test_load_current_platform_rows_masks_credentials(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    excel = tmp_path / "usuarios.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(["CLIENTE", "LINK", "USUARIO", "CPNTRASEÑA", "", ""])
    worksheet.append(["ARITEX", "https://v5.e-coordina.com/aritex", "B95868543", "secret", "", ""])
    workbook.save(excel)

    rows = load_current_platform_rows(excel)

    assert len(rows) == 1
    assert rows[0].platform_slug == "e_coordina"
    assert rows[0].user_hint_masked == "B9***43"
    assert rows[0].has_password is True
    assert rows[0].username == "B95868543"
    assert rows[0].password == "secret"


def _session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _proposal(
    session,
    *,
    tenant_id: int,
    slug: str,
    name: str,
    company: str,
) -> PlatformRpaAccountProposal:
    platform = ExternalPlatform(platform_key=slug, name=name, status="cataloged")
    session.add(platform)
    session.flush()
    manifest = PlatformRpaManifest(
        tenant_id=tenant_id,
        external_platform_id=platform.id,
        platform_slug=slug,
        platform_name=name,
        status="proposal_disabled",
        priority_group="all",
        hosts=[],
        entry_urls=[],
        allowed_operations=["upsert_worker"],
        allowed_entity_types=["worker"],
    )
    session.add(manifest)
    session.flush()
    account = PlatformAccount(
        tenant_id=tenant_id,
        external_platform_id=platform.id,
        display_name=f"{name} - {company}",
        status="proposal_disabled",
        mode="disabled",
    )
    session.add(account)
    session.flush()
    proposal = PlatformRpaAccountProposal(
        tenant_id=tenant_id,
        manifest_id=manifest.id,
        external_platform_id=platform.id,
        platform_account_id=account.id,
        source_platform_account_id=f"{slug}:{company}",
        company_source_label="ARM",
        external_company_name=company,
        entry_url="https://example.invalid",
        host="example.invalid",
        account_status="active_in_source",
        status="proposal_disabled",
        dry_run=True,
        manual_approval_required=True,
        allowed_operations=["upsert_worker"],
        allowed_entity_types=["worker"],
    )
    session.add(proposal)
    session.flush()
    return proposal
