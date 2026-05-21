from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.connectors.base import ConnectorContext
from app.connectors.rpa.seisconecta import write as seisconecta_write_module
from app.connectors.rpa.e_coordina.readonly import _external_status_summary
from app.connectors.rpa.readonly_registry import get_readonly_connector, implemented_readonly_platform_slugs
from app.connectors.rpa.write_registry import implemented_write_connector_keys, write_connector_key_for_platform_slug
from app.connectors.registry import get_connector, list_connectors
from app.platforms.catalog import default_platform_catalog


WRITE_PLATFORM_CONNECTORS = {
    "ecoordina": "connector_rpa_e_coordina_write",
    "sixconecta": "connector_rpa_seisconecta_write",
    "ctaima_cae": "connector_rpa_ctaima_write",
    "nomio": "connector_rpa_nomio_write",
    "timenet": "connector_rpa_timenet_write",
    "validate": "connector_rpa_validate_write",
    "vitaly_cae": "connector_rpa_vitaly_cae_write",
}

WRITE_PLATFORM_SLUG_CONNECTORS = {
    "e_coordina": "connector_rpa_e_coordina_write",
    "seisconecta": "connector_rpa_seisconecta_write",
    "ctaima": "connector_rpa_ctaima_write",
    "nomio": "connector_rpa_nomio_write",
    "timenet": "connector_rpa_timenet_write",
    "validate": "connector_rpa_validate_write",
    "vitaly_cae": "connector_rpa_vitaly_cae_write",
}


def test_registry_exposes_only_allowed_initial_connectors() -> None:
    connector_keys = {connector.connector_key for connector in list_connectors()}

    assert {
        "connector_demo",
        "connector_manual_export",
        *WRITE_PLATFORM_CONNECTORS.values(),
    } == connector_keys


def test_manual_export_does_not_write_to_external_platform() -> None:
    connector = get_connector("connector_manual_export")
    context = ConnectorContext(tenant_id="tenant-demo", platform_key="mock_cae")

    result = asyncio.run(
        connector.upload_document(
            context,
            {
                "document_code": "CAE.WORKER.BASIC_PRL_COURSE",
                "filename": "course.pdf",
                "sha256": "a" * 64,
            },
        )
    )

    assert result.status == "manual_followup_required"
    assert result.external_status == "manual_required"
    assert result.audit_required is True

    worker_result = asyncio.run(
        connector.upsert_worker(
            context,
            {
                "worker_ref": "42",
                "prepared_fields": ["first_name", "last_name"],
            },
        )
    )

    assert worker_result.status == "manual_followup_required"
    assert worker_result.external_status == "manual_required"


def test_demo_connector_is_local_simulation() -> None:
    connector = get_connector("connector_demo")
    context = ConnectorContext(tenant_id="tenant-demo", platform_key="mock_cae")

    result = asyncio.run(connector.test_connection(context))

    assert result.status == "ok"
    assert "sin plataforma externa real" in result.message

    worker_result = asyncio.run(
        connector.upsert_worker(
            context,
            {
                "worker_ref": "42",
                "prepared_fields": ["first_name", "last_name"],
            },
        )
    )
    assert worker_result.status == "ok"
    assert worker_result.external_status == "accepted"


def test_e_coordina_summary_prefers_real_grid_status_counts() -> None:
    summary = _external_status_summary(
        [
            {
                "label": "after documentacion_solicitud",
                "status_candidates": [{"normalized_status": "accepted", "count": 99}],
                "status_column_counts": [
                    {
                        "field": "documentacion_estado",
                        "values": [
                            {"status_text": "Validado", "count": 5},
                            {"status_text": "Caducado", "count": 4},
                        ],
                    }
                ],
            }
        ]
    )

    assert summary["mode"] == "readonly_grid_status_counts"
    assert summary["status_counts"] == [("accepted", 5), ("expired_external", 4)]
    assert summary["term_status_counts"] == [("accepted", 99)]
    assert summary["pages_with_status_columns"] == ["after documentacion_solicitud"]
    assert summary["row_level_observations"] is False


def test_readonly_rpa_registry_covers_current_arm_platforms() -> None:
    expected = {
        "e_coordina",
        "seisconecta",
        "validate",
        "timenet",
        "nomio",
        "vitaly_cae",
        "ctaima",
    }

    assert expected <= implemented_readonly_platform_slugs()
    assert get_readonly_connector("ctaima") is not None
    assert get_readonly_connector("unknown_platform") is None


def test_write_rpa_registry_covers_current_arm_platforms_and_blocks_until_mapping() -> None:
    expected_keys = set(WRITE_PLATFORM_CONNECTORS.values())
    assert expected_keys == implemented_write_connector_keys()
    for platform_slug, connector_key in WRITE_PLATFORM_SLUG_CONNECTORS.items():
        assert write_connector_key_for_platform_slug(platform_slug) == connector_key

    connector = get_connector("connector_rpa_seisconecta_write")
    context = ConnectorContext(tenant_id="tenant-demo", platform_key="sixconecta")
    result = asyncio.run(
        connector.upsert_worker(
            context,
            {
                "worker_ref": "42",
                "prepared_fields": ["first_name", "last_name", "identifier_last4"],
            },
        )
    )

    assert result.status == "blocked_mapping_review_required"
    assert result.external_status == "not_synced"
    assert result.evidence["external_write_executed"] is False
    assert result.evidence["persist_external_status"] is False


def test_write_rpa_connectors_are_preview_only_until_mapping_is_approved() -> None:
    for platform_key, connector_key in WRITE_PLATFORM_CONNECTORS.items():
        connector = get_connector(connector_key)
        context = ConnectorContext(tenant_id="tenant-demo", platform_key=platform_key)

        connection = asyncio.run(connector.test_connection(context))
        assert connection.status == "preview_available"
        assert connection.external_status == "not_synced"
        assert connection.evidence["connector_key"] == connector_key
        assert connection.evidence["captcha_bypass"] is False
        assert connection.evidence["manual_approval_required"] is True

        catalog = asyncio.run(connector.sync_catalog(context))
        assert catalog.status == "mapping_review_required"
        assert catalog.external_status == "not_synced"

        worker_result = asyncio.run(
            connector.upsert_worker(
                context,
                {
                    "worker_ref": "worker-redacted",
                    "prepared_fields": ["first_name", "last_name", "identifier_last4"],
                },
            )
        )
        assert worker_result.status == "blocked_mapping_review_required"
        assert worker_result.external_status == "not_synced"
        assert worker_result.evidence["connector_key"] == connector_key
        assert worker_result.evidence["external_write_executed"] is False
        assert worker_result.evidence["persist_external_status"] is False
        assert worker_result.evidence["captcha_bypass"] is False
        assert "field_mapping_approved" in worker_result.evidence["required_before_live_write"]

        document_result = asyncio.run(
            connector.upload_document(
                context,
                {
                    "operation": "upload_company_document",
                    "document_code": "CAE.COMPANY.RC_POLICY",
                    "filename": "rc.pdf",
                    "sha256": "c" * 64,
                },
            )
        )
        assert document_result.status == "blocked_mapping_review_required"
        assert document_result.external_status == "not_synced"
        assert document_result.evidence["connector_key"] == connector_key
        assert document_result.evidence["operation"] == "upload_company_document"
        assert document_result.evidence["external_write_executed"] is False
        assert document_result.evidence["persist_external_status"] is False
        assert document_result.evidence["metadata"]["sha256_present"] is True


def test_write_rpa_connectors_block_live_without_platform_specific_adapter() -> None:
    live_blocked_connectors = set(WRITE_PLATFORM_CONNECTORS.values()) - {"connector_rpa_seisconecta_write"}
    for connector_key in live_blocked_connectors:
        connector = get_connector(connector_key)
        result = asyncio.run(
            connector.upsert_worker(
                ConnectorContext(
                    tenant_id="tenant-demo",
                    platform_key="platform",
                    dry_run=False,
                    manual_approval_required=True,
                ),
                {
                    "worker_ref": "worker-redacted",
                    "prepared_fields": ["worker.identifier_value", "worker.first_name"],
                },
            )
        )

        assert result.status == "blocked_live_adapter_missing"
        assert result.external_status == "not_synced"
        assert result.evidence["external_write_executed"] is False
        assert result.evidence["post_write_read_confirmed"] is False
        assert result.evidence["valid_external_write"] is False
        assert result.evidence["persist_external_status"] is False
        assert "platform_specific_live_adapter" in result.evidence["required_before_live_write"]
        assert "post_write_readback_confirmation" in result.evidence["required_before_live_write"]


def test_seisconecta_live_connector_uses_payload_file_without_command_pii(monkeypatch) -> None:
    captured_command: list[str] = []

    def fake_run(command, **kwargs):
        captured_command.extend(str(item) for item in command)
        payload_path = Path(captured_command[captured_command.index("--payload-file") + 1])
        assert payload_path.exists()
        assert "00000000T" in payload_path.read_text(encoding="utf-8")
        status_path = Path(captured_command[captured_command.index("--status-file") + 1])
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            '{"state":"confirmed_external","external_write_executed":true,"post_write_read_confirmed":true}',
            encoding="utf-8",
        )
        return SimpleNamespace(
            returncode=0,
            stdout='{"status":"confirmed_external","external_write_executed":true,"post_write_read_confirmed":true}\n',
            stderr="",
        )

    monkeypatch.setattr(seisconecta_write_module.subprocess, "run", fake_run)
    connector = get_connector("connector_rpa_seisconecta_write")
    result = asyncio.run(
        connector.upsert_worker(
            ConnectorContext(tenant_id="tenant-demo", platform_key="sixconecta", dry_run=False),
            {
                "live_write_authorized": True,
                "worker_ref": "42",
                "identifier_value": "00000000T",
                "identifier_last4": "000T",
                "first_name": "Prueba",
                "last_name": "Live",
                "nationality": "ES",
                "contract_type": "indefinido",
                "work_position": "Tecnico",
                "account": {
                    "entry_url": "https://www.6conecta.com/es/iniciar-sesion",
                    "source_platform_account_id": "seisconecta_arm_r33_dummy",
                    "external_company_name": "Dummy",
                },
            },
        )
    )

    assert result.status == "confirmed_external"
    assert result.external_status == "confirmed"
    assert result.evidence["external_write_executed"] is True
    assert result.evidence["post_write_read_confirmed"] is True
    assert result.evidence["valid_external_write"] is True
    assert "00000000T" not in " ".join(captured_command)


def test_seisconecta_live_connector_marks_submit_pending_without_readback(monkeypatch) -> None:
    def fake_run(command, **kwargs):
        status_path = Path(command[command.index("--status-file") + 1])
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            '{"state":"submitted_external_pending_readback","external_write_executed":true,"post_write_read_confirmed":false}',
            encoding="utf-8",
        )
        return SimpleNamespace(
            returncode=0,
            stdout='{"status":"submitted_external_pending_readback","external_write_executed":true,"post_write_read_confirmed":false}\n',
            stderr="",
        )

    monkeypatch.setattr(seisconecta_write_module.subprocess, "run", fake_run)
    connector = get_connector("connector_rpa_seisconecta_write")
    result = asyncio.run(
        connector.upsert_worker(
            ConnectorContext(tenant_id="tenant-demo", platform_key="sixconecta", dry_run=False),
            {
                "live_write_authorized": True,
                "worker_ref": "42",
                "identifier_value": "00000000T",
                "identifier_last4": "000T",
                "first_name": "Prueba",
                "last_name": "Live",
                "nationality": "ES",
                "contract_type": "indefinido",
                "work_position": "Tecnico",
                "account": {
                    "entry_url": "https://www.6conecta.com/es/iniciar-sesion",
                    "source_platform_account_id": "seisconecta_arm_r33_dummy",
                    "external_company_name": "Dummy",
                },
            },
        )
    )

    assert result.status == "submitted_external_pending_readback"
    assert result.external_status == "pending_readback"
    assert result.evidence["external_write_executed"] is True
    assert result.evidence["post_write_read_confirmed"] is False
    assert result.evidence["valid_external_write"] is False


def test_platform_catalog_links_current_arm_platforms_to_write_connectors() -> None:
    catalog_by_key = {item.platform_key: item for item in default_platform_catalog()}

    for platform_key, connector_key in WRITE_PLATFORM_CONNECTORS.items():
        platform = catalog_by_key[platform_key]
        method = next(item for item in platform.methods if item.method_key == "authorized_rpa")

        assert method.connector_type == "authorized_rpa_write"
        assert method.connector_key == connector_key
        assert method.status == "implemented_preview_blocked_until_mapping_approval"
        assert method.implemented is True
        assert method.dry_run_supported is True
        assert method.manual_approval_required is True
